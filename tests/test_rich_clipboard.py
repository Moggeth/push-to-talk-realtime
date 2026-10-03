import re
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest

from rich_clipboard import (
    WindowsClipboard,
    add_bullet_html,
    bullet_fragment,
    html_clipboard_payload,
)


@pytest.mark.parametrize("text", ["Hello", "caf\u00e9 \U0001f600", "<script>&\"'", "\u4f60\u597d"])
def test_real_list_structure_escaping_and_utf8_byte_offsets(text):
    fragment = bullet_fragment(f"- {text}\n")
    root = ElementTree.fromstring(fragment.replace("<br>", "<br />"))
    assert root.find("ul/li").text == text
    assert root.find("p/br") is not None
    assert root.find(".//script") is None
    payload = html_clipboard_payload(fragment)
    offsets = {
        name.decode(): int(value)
        for name, value in re.findall(
            rb"(StartHTML|EndHTML|StartFragment|EndFragment):(\d+)", payload
        )
    }
    assert payload[offsets["StartFragment"] : offsets["EndFragment"]].decode() == fragment
    assert payload[offsets["StartHTML"] : offsets["EndHTML"]].startswith(b"<html>")
    assert payload[offsets["StartHTML"] : offsets["EndHTML"]].endswith(b"</html>")
    assert payload[offsets["EndHTML"] :] == b"\0"


def test_adds_html_without_removing_plain_text():
    clipboard = Mock()
    clipboard.text.return_value = "- hello\n"
    clipboard.publish.return_value = True
    assert add_bullet_html("- hello\n", clipboard=clipboard)
    clipboard.close.assert_called_once()
    clipboard.publish.assert_called_once()
    clipboard.empty.assert_not_called()


def test_different_clipboard_owner_text_is_not_overwritten():
    clipboard = Mock()
    clipboard.text.return_value = "user copied something else"
    assert not add_bullet_html("- hello\n", clipboard=clipboard)
    clipboard.publish.assert_not_called()
    clipboard.close.assert_called_once()


def test_busy_clipboard_is_bounded_and_not_closed_without_ownership():
    clipboard = Mock()
    clipboard.open.return_value = False
    sleep = Mock()
    assert not add_bullet_html("- hello\n", clipboard=clipboard, sleep=sleep)
    assert clipboard.open.call_count == 6
    assert sleep.call_count == 5
    clipboard.close.assert_not_called()
    clipboard.publish.assert_not_called()


def test_publish_failure_keeps_plain_fallback_and_releases_lock():
    clipboard = Mock()
    clipboard.text.return_value = "- hello\n"
    clipboard.publish.side_effect = OSError("unavailable")
    assert not add_bullet_html("- hello\n", clipboard=clipboard)
    clipboard.close.assert_called_once()


@pytest.mark.parametrize("rich", [False, True])
def test_app_rich_paste_does_not_use_plain_insert_shortcut(monkeypatch, rich):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(app.pyperclip, "copy", Mock())
    monkeypatch.setattr(app.pyperclip, "paste", lambda: "- hello.\n")
    monkeypatch.setattr(app, "add_bullet_html", Mock(return_value=rich))
    direct = Mock(return_value=True)
    send = Mock()
    monkeypatch.setattr(app, "try_insert_text_into_target", direct)
    monkeypatch.setattr(app, "send_paste_shortcut", send)
    monkeypatch.setattr(app, "foreground_matches_paste_target", lambda target: True)
    assert app.paste_text("hello", object(), bullet_mode=True)
    if rich:
        direct.assert_not_called()
        send.assert_called_once()
    else:
        direct.assert_called_once()
        send.assert_not_called()


def test_rich_paste_does_not_send_to_changed_foreground(monkeypatch):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(app, "IS_WINDOWS", True)
    monkeypatch.setattr(app.pyperclip, "copy", Mock())
    monkeypatch.setattr(app.pyperclip, "paste", lambda: "- hello.\n")
    monkeypatch.setattr(app, "add_bullet_html", Mock(return_value=True))
    send = Mock()
    monkeypatch.setattr(app, "send_paste_shortcut", send)
    monkeypatch.setattr(app, "foreground_matches_paste_target", lambda target: False)
    assert not app.paste_text("hello", object(), bullet_mode=True)
    send.assert_not_called()


@pytest.mark.parametrize("failure", [None, "register", "allocate", "lock", "set"])
def test_native_memory_ownership_and_cleanup_without_system_clipboard(failure):
    import ctypes

    clipboard = WindowsClipboard.__new__(WindowsClipboard)
    clipboard.user = Mock()
    clipboard.kernel = Mock()
    payload = b"example\0"
    allocation = ctypes.create_string_buffer(len(payload))
    clipboard.user.RegisterClipboardFormatW.return_value = 0 if failure == "register" else 500
    clipboard.kernel.GlobalAlloc.return_value = 0 if failure == "allocate" else 123
    clipboard.kernel.GlobalLock.return_value = (
        0 if failure == "lock" else ctypes.addressof(allocation)
    )
    clipboard.user.SetClipboardData.return_value = 0 if failure == "set" else 123
    assert clipboard.publish(payload) == (failure is None)
    if failure in ("lock", "set"):
        clipboard.kernel.GlobalFree.assert_called_once_with(123)
    else:
        clipboard.kernel.GlobalFree.assert_not_called()
    if failure in (None, "set"):
        assert allocation.raw == payload
        clipboard.kernel.GlobalUnlock.assert_called_once_with(123)


def test_native_unicode_read_uses_bounded_global_memory():
    import ctypes

    clipboard = WindowsClipboard.__new__(WindowsClipboard)
    clipboard.user = Mock()
    clipboard.kernel = Mock()
    data = "- caf\u00e9 \U0001f642\n\0".encode("utf-16-le")
    allocation = ctypes.create_string_buffer(data, len(data))
    clipboard.user.GetClipboardData.return_value = 123
    clipboard.kernel.GlobalSize.return_value = len(data)
    clipboard.kernel.GlobalLock.return_value = ctypes.addressof(allocation)
    assert clipboard.text() == "- caf\u00e9 \U0001f642\n"
    clipboard.kernel.GlobalUnlock.assert_called_once_with(123)


def test_app_skips_output_when_clipboard_changes_during_rich_preparation(monkeypatch):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(app.pyperclip, "copy", Mock())
    monkeypatch.setattr(app.pyperclip, "paste", lambda: "new user clipboard")
    monkeypatch.setattr(app, "add_bullet_html", Mock(return_value=False))
    send = Mock()
    insert = Mock()
    monkeypatch.setattr(app, "send_paste_shortcut", send)
    monkeypatch.setattr(app, "try_insert_text_into_target", insert)
    assert not app.paste_text("hello", object(), bullet_mode=True)
    send.assert_not_called()
    insert.assert_not_called()
