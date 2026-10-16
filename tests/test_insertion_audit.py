from dataclasses import asdict
from itertools import product
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from insertion_formatting import CaretContext, choose_plan, format_insertion
from platform_input import PasteTarget
from rewrite_replacement import WindowsTextReplacement
from text_processing import prepare_clipboard_text


@pytest.mark.parametrize(
    "before",
    ["", " ", "\u200b", "\u200e\u200f", "\u2066\u2069", "\r", "old\r", "old\u2028", "old\u2029"],
)
@pytest.mark.parametrize("after", ["", " ", "\u200b", "\n", "\u200e\u2069"])
def test_blank_paragraph_never_adds_leading_space_or_lowercases(before, after):
    plan = choose_plan("auto", CaretContext(before, after))
    result = format_insertion("That works.", plan, "That works. ")
    assert plan.style == "standalone"
    assert result.startswith("That")
    assert result.rstrip().endswith(".")


def test_insertion_combination_matrix():
    before_values = [
        "",
        " ",
        "\u200b",
        "Ready?",
        "Ready. ",
        "ongoing ",
        "ongoing",
        "line\n",
        "(",
        "- ",
    ]
    after_values = ["", " next", "next", ", next", ".", "\nnext paragraph", "\u200b"]
    for mode, before, after, suffix, text in product(
        ("auto", "standalone", "insert"),
        before_values,
        after_values,
        ("none", "space", "newline"),
        ("That works.", "I agree!", "Python?"),
    ):
        plan = choose_plan(mode, CaretContext(before, after))
        baseline = prepare_clipboard_text(text, suffix_mode=suffix)
        result = format_insertion(text, plan, baseline)
        assert result.strip(), (mode, before, after, text)
        assert not result.startswith("  "), (mode, before, after, text)
        if mode == "standalone":
            assert result == baseline
        if text.startswith("I "):
            assert result.lstrip().startswith("I ")
        if text.startswith("Python"):
            assert result.lstrip().startswith("Python")
        if mode == "auto" and after == "\nnext paragraph":
            assert result.rstrip().endswith(text[-1]), (before, text)


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("Ready?", " That works. "),
        ("Ready!", " That works. "),
        ("(", "That works. "),
        ("- ", "That works. "),
    ],
)
def test_sentence_and_opening_boundaries(prefix, expected):
    assert (
        format_insertion(
            "That works.", choose_plan("auto", CaretContext(prefix, "")), "That works. "
        )
        == expected
    )


@pytest.fixture
def scoped_backend(monkeypatch):
    from tests.test_rewrite_review import Range

    target = PasteTarget("Windows", 1, 2, "Edit", 3, 4)
    element = SimpleNamespace(CurrentControlType=50004, GetRuntimeId=lambda: (9,))

    class ScopedDocument:
        text = "UNRELATED OUTSIDE TEXT" + "" + "UNRELATED AFTER"
        start = len("UNRELATED OUTSIDE TEXT")
        end = start

        @property
        def DocumentRange(self):
            return Range(self, self.start, self.end)

    document = ScopedDocument()
    document.selection = Range(document, document.start, document.end)

    def move(self, endpoint, unit, count):
        # Simulate a provider that expands into the enclosing page.
        if endpoint == 0:
            self.start = max(0, self.start + count)
        else:
            self.end = min(len(self.document.text), self.end + count)

    monkeypatch.setattr(Range, "MoveEndpointByUnit", move, raising=False)
    monkeypatch.setattr(Range, "GetEnclosingElement", lambda _: element, raising=False)
    backend = WindowsTextReplacement.__new__(WindowsTextReplacement)
    backend.automation = SimpleNamespace(GetFocusedElement=lambda: element)
    backend._focused = lambda: (target, (9,), document, document.selection.Clone())
    return backend, document, target, element


def test_blank_editor_cannot_read_enclosing_page_text(scoped_backend):
    backend, document, target, _ = scoped_backend
    result = backend.caret_context(asdict(target))
    assert result == {
        "before": "",
        "after": "",
        "selected_lowercase_word": False,
        "selected_trailing_space": False,
    }
    assert backend.context_diagnostics["editor_empty"]
    assert document.selection.start == document.start


def test_unscoped_document_pattern_falls_back(scoped_backend, monkeypatch):
    backend, _, target, _ = scoped_backend
    from tests.test_rewrite_review import Range

    monkeypatch.setattr(
        Range, "GetEnclosingElement", lambda _: SimpleNamespace(GetRuntimeId=lambda: (88,))
    )
    assert backend.caret_context(asdict(target)) is None
    assert backend.context_diagnostics["context_status"] == "unscoped"


def test_selection_changed_during_read_is_rejected(scoped_backend):
    backend, document, target, _ = scoped_backend
    from tests.test_rewrite_review import Range

    first = document.selection.Clone()
    moved = Range(document, document.start + 1, document.start + 1)
    backend._focused = Mock(
        side_effect=[(target, (9,), document, first), (target, (9,), document, moved)]
    )
    assert backend.caret_context(asdict(target)) is None
    assert backend.context_diagnostics["context_status"] == "caret_changed"


def test_selection_outside_editor_is_rejected(scoped_backend):
    backend, document, target, _ = scoped_backend
    from tests.test_rewrite_review import Range

    document.selection = Range(document, 0, 0)
    assert backend.caret_context(asdict(target)) is None
    assert backend.context_diagnostics["context_status"] == "outside_editor"


@pytest.mark.parametrize("editable", [False, True])
def test_document_requires_evidence_of_editability(scoped_backend, editable):
    backend, _, target, element = scoped_backend
    element.CurrentControlType = 50030
    element.GetCurrentPropertyValue = lambda property_id: editable
    result = backend.caret_context(asdict(target))
    assert (result is not None) == editable
    assert backend.context_diagnostics["context_status"] == ("ok" if editable else "not_editable")


def test_readonly_value_control_is_rejected(scoped_backend):
    backend, _, target, element = scoped_backend
    backend.uia = SimpleNamespace(IUIAutomationValuePattern=object())
    element.GetCurrentPattern = lambda _: SimpleNamespace(
        QueryInterface=lambda _: SimpleNamespace(CurrentIsReadOnly=True)
    )
    assert backend.caret_context(asdict(target)) is None
    assert backend.context_diagnostics["context_status"] == "not_editable"


@pytest.mark.parametrize("selected", ["good", "good ", "good\u00a0"])
def test_double_click_word_replacement_end_to_end(scoped_backend, selected):
    backend, document, target, _ = scoped_backend
    from tests.test_rewrite_review import Range

    prefix, suffix = "That is a ", "result."
    # Without selected whitespace, leave the separator outside the selection.
    if not selected[-1].isspace():
        suffix = " " + suffix
    document.text = prefix + selected + suffix
    document.start, document.end = 0, len(document.text)
    document.selection = Range(document, len(prefix), len(prefix) + len(selected))
    data = backend.caret_context(asdict(target))
    context = CaretContext(**data)
    assert context.selected_lowercase_word
    assert context.selected_trailing_space == selected[-1].isspace()
    plan = choose_plan("auto", context)
    inserted = format_insertion("Better.", plan, "Better. ")
    assert prefix + inserted + suffix == "That is a better result."
    assert plan.reason == "word_replacement"


@pytest.mark.parametrize(
    "replacement,expected", [("Better.", "better"), ("GPT.", "GPT"), ("I.", "I")]
)
def test_selected_lowercase_case_inheritance(replacement, expected):
    context = CaretContext("Use ", " now", selected_lowercase_word=True)
    result = format_insertion(replacement, choose_plan("auto", context), replacement + " ")
    assert result == expected


def test_selected_word_at_sentence_start_keeps_capitalization():
    context = CaretContext("", "result.", True, True)
    assert format_insertion("Better.", choose_plan("auto", context), "Better. ") == "Better. "
    context = CaretContext("We need ", "", True, True)
    assert format_insertion("Better.", choose_plan("auto", context), "Better. ") == "better. "


def test_unselected_unknown_word_keeps_conservative_case():
    context = CaretContext("Use ", " now")
    assert format_insertion("Python.", choose_plan("auto", context), "Python. ") == "Python"


def test_multiword_selection_does_not_supply_single_word_case(scoped_backend):
    backend, document, target, _ = scoped_backend
    from tests.test_rewrite_review import Range

    document.text = "Use two words now."
    document.start, document.end = 0, len(document.text)
    document.selection = Range(document, 4, 14)
    data = backend.caret_context(asdict(target))
    assert not data["selected_lowercase_word"]


def test_insertion_metadata_is_durable_without_text(tmp_path):
    import json

    from runtime_diagnostics import Diagnostics

    logger = Diagnostics("app", tmp_path)
    logger.emit(
        "insertion_decision",
        insertion_id=12,
        insertion_mode="auto",
        insertion_style="insert",
        insertion_reason="continuation",
        context_status="ok",
        before_length=14,
        before_boundary="word",
        added_leading_space=True,
        surrounding_text="SYNTHETIC_SECRET",
        document_title="SYNTHETIC_SECRET",
    )
    logger.emit("insertion_output", insertion_id=12, insertion_outcome="shortcut")
    data = logger.path.read_text()
    assert "SYNTHETIC_SECRET" not in data
    entries = [json.loads(line) for line in data.splitlines()]
    assert entries[0]["insertion_reason"] == "continuation"
    assert entries[0]["added_leading_space"] is True
    assert entries[0]["before_boundary"] == "word"
    assert entries[1]["insertion_id"] == 12
