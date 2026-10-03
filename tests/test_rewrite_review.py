from types import SimpleNamespace

import pytest

from rewrite_replacement import WindowsTextReplacement
from rewrite_review import ReviewLifetime, RewriteReviewManager


def test_lifetime_hover_leave_and_rescue():
    life = ReviewLifetime(0)
    assert life.opacity(0.05) == pytest.approx(0.5)
    assert life.opacity(5.5) == pytest.approx(0.5)
    life.hover(True, 5.6)
    assert life.opacity(60) == 1
    life.hover(False, 60)
    assert life.opacity(60.5) == pytest.approx(0.5)
    life.hover(True, 60.9)
    assert life.opacity(61) == 1
    life.hover(False, 62)
    assert life.opacity(63) == 0


class Range:
    def __init__(self, document, start=0, end=None):
        self.document, self.start = document, start
        self.end = len(document.text) if end is None else end

    def Clone(self):
        return Range(self.document, self.start, self.end)

    def GetText(self, limit):
        return self.document.text[self.start : self.end][:limit]

    def MoveEndpointByRange(self, which, other, endpoint):
        value = other.start if endpoint == 0 else other.end
        if which == 0:
            self.start = value
        else:
            self.end = value

    def FindText(self, text, *_):
        index = self.document.text.find(text, self.start, self.end)
        return None if index < 0 else Range(self.document, index, index + len(text))

    def Select(self):
        self.document.selection = self.Clone()

    def CompareEndpoints(self, which, other, endpoint):
        return (self.start if which == 0 else self.end) - (
            other.start if endpoint == 0 else other.end
        )


class Document:
    def __init__(self):
        self.text = "same prefix: same suffix"
        self.selection = Range(self, 17, 17)
        self.target = "target"

    @property
    def DocumentRange(self):
        return Range(self)


@pytest.fixture
def backend(monkeypatch):
    document = Document()
    value = WindowsTextReplacement.__new__(WindowsTextReplacement)
    value.anchor = ("target", (1,), "same prefix: ", " suffix")
    value.current = "same"
    value.caret = None
    value._focused = lambda: (document.target, (1,), document, document.selection.Clone())
    clipboard = SimpleNamespace(text="")
    monkeypatch.setattr("pyperclip.copy", lambda text: setattr(clipboard, "text", text))
    monkeypatch.setattr("pyperclip.paste", lambda: clipboard.text)

    def paste():
        selection = document.selection
        document.text = (
            document.text[: selection.start] + clipboard.text + document.text[selection.end :]
        )
        caret = selection.start + len(clipboard.text)
        document.selection = Range(document, caret, caret)

    monkeypatch.setattr("platform_input.send_paste_shortcut", paste)
    return value, document, clipboard


def test_exact_replacement_including_duplicate_text_and_reverse(backend):
    value, document, _ = backend
    assert value.attach("same")
    assert value.replace("raw \U0001f642")
    assert document.text == "same prefix: raw \U0001f642 suffix"
    assert value.replace("same")
    assert document.text == "same prefix: same suffix"


@pytest.mark.parametrize("change", ["text", "focus", "caret"])
def test_external_change_refuses_to_touch_document_or_clipboard(backend, change):
    value, document, clipboard = backend
    assert value.attach("same")
    if change == "text":
        document.text += " new edits"
    elif change == "focus":
        document.target = "other field"
    else:
        document.selection = Range(document, 0, 0)
    before = document.text
    assert not value.replace("raw")
    assert document.text == before
    assert clipboard.text == ""


def test_failed_paste_restores_only_owned_caret(backend, monkeypatch):
    value, document, _ = backend
    assert value.attach("same")

    def fail():
        raise OSError("injection unavailable")

    monkeypatch.setattr("platform_input.send_paste_shortcut", fail)
    assert not value.replace("raw")
    assert document.text == "same prefix: same suffix"
    assert document.selection.start == document.selection.end == 17


def test_helper_start_failure_is_optional(monkeypatch):
    def fail(*_, **__):
        raise OSError("no process")

    monkeypatch.setattr("subprocess.Popen", fail)
    manager = RewriteReviewManager()
    assert manager.capture(None) is None
    manager.show("raw", "tidy")
    manager.close()


def test_empty_or_unchanged_rewrite_needs_no_popup(monkeypatch):
    manager = RewriteReviewManager()
    monkeypatch.setattr(manager, "start", lambda: pytest.fail("unnecessary helper"))
    manager.show("", "result")
    manager.show("same", "same")


def test_multiline_provider_newlines(backend):
    value, document, _ = backend
    document.text = "same prefix: first\rsecond suffix"
    document.selection = Range(document, 25, 25)
    assert value.attach("first\nsecond")
    assert value.replace("raw")
    assert document.text == "same prefix: raw suffix"


def test_stalled_helper_capture_is_bounded_and_recovers(monkeypatch):
    manager = RewriteReviewManager()
    monkeypatch.setattr(manager, "start", lambda: True)
    calls = []
    monkeypatch.setattr(manager, "close", lambda **kwargs: calls.append(kwargs))
    assert manager.capture(None) is None
    assert calls == [{"wait": False}]
    assert not manager.pending
