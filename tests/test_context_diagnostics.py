import json

import pytest

from runtime_diagnostics import Diagnostics, context_shape, safe_fields


@pytest.mark.parametrize("marker", ["\x00", "\u200b", "\u200c", "\u200d", "\ufeff", "\ufffc"])
def test_invisible_boundary_identified_without_text(marker):
    fields = safe_fields(context_shape(marker, "\n"))
    assert fields["before_marker_codepoint"] == ord(marker)
    assert fields["after_marker_codepoint"] == 10
    assert fields["before_has_word"] is False
    assert fields["before_raw_category"] in {"Cc", "Cf", "So"}


def test_removed_marker_and_retained_marker_are_distinguishable():
    assert context_shape("\u200b", "")["before_visible_length"] == 0
    assert context_shape("\u200d", "")["before_visible_length"] == 1


@pytest.mark.parametrize(
    "value", [ord("A"), ord("!"), ord("\U0001f600"), -1, 0x110000, True, "secret"]
)
def test_codepoint_allowlist_rejects_visible_content(value):
    assert safe_fields({"before_marker_codepoint": value}) == {}


def test_durable_shape_contains_no_surrounding_content(tmp_path):
    logger = Diagnostics("app", tmp_path)
    logger.emit(
        "insertion_decision",
        insertion_id=7,
        **context_shape("PRIVATE SENTENCE\u200d", "\nSECRET"),
        caret_at_editor_start=False,
        caret_at_editor_end=True,
        surrounding_text="SECRET",
    )
    serialized = logger.path.read_text()
    assert "PRIVATE" not in serialized and "SECRET" not in serialized
    entry = json.loads(serialized)
    assert entry["before_has_word"]
    assert entry["after_paragraph_length"] == 0
    assert entry["before_marker_codepoint"] == 0x200D
    assert entry["caret_at_editor_end"]
    assert entry["context_diagnostics_version"] == 2
