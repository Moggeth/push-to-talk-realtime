from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from insertion_formatting import CaretContext, choose_plan, format_insertion
from platform_input import PasteTarget
from rewrite_replacement import WindowsTextReplacement
from rewrite_review import RewriteReviewManager


@pytest.mark.parametrize(
    "before,after,text,expected",
    [
        ("The process that, ", " you would use", "For any given changes.", "for any given changes"),
        ("I think", " this works", "That.", " that"),
        ("I think ", "this works", "That.", "that "),
        ("I think ", ", actually", "That!", "that"),
        ("We use ", ".", "Python.", "Python"),
        ("We use ", " daily", "GPT.", "GPT"),
        ("She said ", " yesterday", "I agree.", "I agree"),
        ("It was ", " yesterday", "Alice.", "Alice"),
        ("It was ", " yesterday", "May.", "May"),
        ("We need ", " now", "A version 2.5.", "a version 2.5"),
        ("We need ", " now", "An API, e.g.", "an API, e.g."),
        ("We need ", " now", "That...", "that..."),
        ("", "", "Hello.", "Hello. "),
        ("Finished. ", "", "Hello.", "Hello. "),
        ("Finished.\n  ", "", "Hello.", "Hello. "),
        ("", ".", "Hello.", "Hello"),
        ("", " rest", "Hello.", "Hello."),
    ],
)
def test_contextual_splices(before, after, text, expected):
    context = CaretContext(before, after)
    plan = choose_plan("auto", context)
    assert format_insertion(text, plan, text + " ") == expected


def test_modes_fallback_bullets_and_blank():
    assert choose_plan("auto", None).label == "Auto: unavailable"
    assert format_insertion("Hello.", choose_plan("auto", None), "Hello.\n") == "Hello.\n"
    assert (
        format_insertion("The thought.", choose_plan("insert", None), "The thought. ")
        == "the thought"
    )
    assert format_insertion("", choose_plan("auto", CaretContext("a ", "")), "") == ""
    assert choose_plan("auto", CaretContext("ongoing ", "")).style == "insert"
    assert choose_plan("auto", CaretContext("ongoing\n", "")).style == "standalone"
    assert choose_plan("auto", CaretContext("ongoing ", ""), bullet=True).label == "Bullets"
    assert (
        format_insertion("The thought.", choose_plan("standalone", None), "The thought. ")
        == "The thought. "
    )


@pytest.fixture
def target():
    return PasteTarget("Windows", 11, 12, "Edit", 13, 14)


def test_native_context_only_reads_adjacent_ranges(monkeypatch, target):
    from tests.test_rewrite_review import Document, Range

    def move(self, endpoint, unit, count):
        assert unit == 0
        assert abs(count) == 256
        if endpoint == 0:
            self.start = max(0, self.start + count)
        else:
            self.end = min(len(self.document.text), self.end + count)

    monkeypatch.setattr(Range, "MoveEndpointByUnit", move, raising=False)
    document = Document()
    document.text = "a" * 400 + "selected" + "b" * 400
    document.selection = Range(document, 400, 408)
    backend = WindowsTextReplacement.__new__(WindowsTextReplacement)
    backend.automation = object()
    backend._focused = lambda: (target, (1,), document, document.selection.Clone())
    monkeypatch.setattr("platform_input.capture_paste_target", lambda: target)
    result = backend.caret_context(asdict(target))
    assert result == {"before": "a" * 256, "after": "b" * 256}
    assert document.selection.start == 400
    assert document.selection.end == 408
    monkeypatch.setattr("platform_input.capture_paste_target", lambda: None)
    assert backend.caret_context(asdict(target)) is None
    backend._focused = Mock(side_effect=ValueError("protected_control"))
    assert backend.caret_context(asdict(target)) is None


def test_context_timeout_cleans_up_and_rejects_old_generation(monkeypatch, target):
    manager = RewriteReviewManager()
    manager.process = process = Mock()
    monkeypatch.setattr(manager, "start", lambda: True)
    close = Mock()
    monkeypatch.setattr(manager, "close", close)
    assert manager.caret_context(target) is None
    close.assert_called_once_with(wait=False, expected_process=process)
    assert not manager.pending
    assert not manager.responses


def test_context_response_is_bounded_and_validated(monkeypatch, target):
    manager = RewriteReviewManager()
    manager.process = Mock()
    monkeypatch.setattr(manager, "start", lambda: True)
    context = {"before": "a ", "after": " b"}

    def reply(message, **kwargs):
        token = message["id"]
        manager.responses[token] = {"context": context}
        manager.pending[token].set()
        return True

    monkeypatch.setattr(manager, "_send", reply)
    assert manager.caret_context(target) == CaretContext("a ", " b")
    context["before"] = "a" * 257
    assert manager.caret_context(target) is None
    context["before"] = 4
    assert manager.caret_context(target) is None
    assert not manager.responses


def test_paste_uses_local_context_and_visual_feedback(monkeypatch, target):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "shutdown_event", SimpleNamespace(is_set=lambda: False))
    monkeypatch.setattr(app, "log", Mock())
    context = CaretContext("I think ", " it works")
    manager = SimpleNamespace(caret_context=Mock(return_value=context))
    monkeypatch.setattr(app, "rewrite_review_manager", manager)
    monkeypatch.setattr(app, "capture_paste_target", lambda: target)
    copy = Mock()
    monkeypatch.setattr(app.pyperclip, "copy", copy)
    monkeypatch.setattr(app, "try_insert_text_into_target", Mock(return_value=True))
    assert app._paste_text_unlocked("That.", target)
    copy.assert_called_once_with("that")
    assert app.cursor_indicator_snapshot().label == "Auto: insert"
    app.state.insertion_feedback_at -= 3
    assert not app.cursor_indicator_snapshot().label
    assert app.state.insertion_mode == "auto"


def test_context_failures_preserve_legacy_output(monkeypatch, target):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "shutdown_event", SimpleNamespace(is_set=lambda: False))
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(
        app, "rewrite_review_manager", SimpleNamespace(caret_context=Mock(side_effect=OSError))
    )
    copy = Mock()
    monkeypatch.setattr(app.pyperclip, "copy", copy)
    monkeypatch.setattr(app, "try_insert_text_into_target", Mock(return_value=True))
    assert app._paste_text_unlocked("Hello.", target)
    copy.assert_called_once_with("Hello. ")
    assert app.cursor_indicator_snapshot().label == "Auto: unavailable"


def test_contextual_paste_refuses_changed_focus(monkeypatch, target):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "shutdown_event", SimpleNamespace(is_set=lambda: False))
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(
        app,
        "rewrite_review_manager",
        SimpleNamespace(caret_context=lambda _: CaretContext("a ", "")),
    )
    monkeypatch.setattr(app, "capture_paste_target", lambda: None)
    monkeypatch.setattr(app.pyperclip, "copy", Mock())
    insert = Mock()
    monkeypatch.setattr(app, "try_insert_text_into_target", insert)
    assert not app._paste_text_unlocked("That.", target)
    insert.assert_not_called()


def test_insertion_setting_roundtrip_and_validation(monkeypatch, tmp_path):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(app, "refresh_tray_menu", Mock())
    monkeypatch.setattr(app, "log", Mock())
    assert app.settings_window_payload()["insertion_mode"] == "auto"
    app.set_insertion_mode("insert")
    saved = app.load_settings_from_disk()
    assert saved["insertion_mode"] == "insert"
    app.state.insertion_mode = "standalone"
    monkeypatch.setattr(app, "load_settings_from_disk", lambda: saved)
    app.apply_persisted_settings()
    assert app.state.insertion_mode == "insert"
    app.set_insertion_mode("bad value")
    assert app.state.insertion_mode == "insert"


def test_feedback_labels_render_inside_fixed_surface():
    from cursor_indicator import indicator_frame, render_indicator_image

    for label in ("Auto: standalone", "Auto: insert", "Auto: unavailable"):
        image = render_indicator_image(indicator_frame(0.3), (200, 50, 60, 255), label=label)
        left, _, right, _ = image.getbbox()
        assert left > 0
        assert right < image.width
