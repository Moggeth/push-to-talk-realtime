"""Optional HTML clipboard flavor; ordinary Unicode text remains the fallback."""

from __future__ import annotations

import ctypes
import html
import platform
import time


def bullet_fragment(prepared: str) -> str:
    body = prepared.removeprefix("- ").rstrip("\r\n")
    # A final paragraph keeps the next dictation outside this list item.
    return f"<div><ul><li>{html.escape(body)}</li></ul><p><br></p></div>"


def html_clipboard_payload(fragment: str) -> bytes:
    template = (
        "Version:1.0\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\n"
        "StartFragment:{:010d}\r\nEndFragment:{:010d}\r\n"
    )
    prefix = b"<html><body><!--StartFragment-->"
    suffix = b"<!--EndFragment--></body></html>"
    content = fragment.encode("utf-8")
    start = len(template.format(0, 0, 0, 0).encode("ascii"))
    first = start + len(prefix)
    last = first + len(content)
    header = template.format(start, last + len(suffix), first, last).encode("ascii")
    return header + prefix + content + suffix + b"\0"


class WindowsClipboard:
    def __init__(self):
        from ctypes import wintypes

        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = (
            (self.user.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
            (self.user.CloseClipboard, [], wintypes.BOOL),
            (self.user.GetClipboardData, [wintypes.UINT], wintypes.HANDLE),
            (self.user.SetClipboardData, [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
            (self.user.RegisterClipboardFormatW, [wintypes.LPCWSTR], wintypes.UINT),
            (self.kernel.GlobalAlloc, [wintypes.UINT, ctypes.c_size_t], wintypes.HANDLE),
            (self.kernel.GlobalLock, [wintypes.HANDLE], ctypes.c_void_p),
            (self.kernel.GlobalUnlock, [wintypes.HANDLE], wintypes.BOOL),
            (self.kernel.GlobalSize, [wintypes.HANDLE], ctypes.c_size_t),
            (self.kernel.GlobalFree, [wintypes.HANDLE], wintypes.HANDLE),
        )
        for function, arguments, result in signatures:
            function.argtypes = arguments
            function.restype = result

    def open(self):
        return bool(self.user.OpenClipboard(None))

    def close(self):
        self.user.CloseClipboard()

    def text(self):
        handle = self.user.GetClipboardData(13)  # CF_UNICODETEXT
        size = self.kernel.GlobalSize(handle) if handle else 0
        if not size or size > 4 * 1024 * 1024 or size % 2:
            return None
        pointer = self.kernel.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.string_at(pointer, size).decode("utf-16-le").split("\0", 1)[0]
        finally:
            self.kernel.GlobalUnlock(handle)

    def publish(self, payload):
        format_id = self.user.RegisterClipboardFormatW("HTML Format")
        if not format_id:
            return False
        handle = self.kernel.GlobalAlloc(0x0002, len(payload))  # GMEM_MOVEABLE
        if not handle:
            return False
        try:
            pointer = self.kernel.GlobalLock(handle)
            if not pointer:
                return False
            try:
                ctypes.memmove(pointer, payload, len(payload))
            finally:
                self.kernel.GlobalUnlock(handle)
            if not self.user.SetClipboardData(format_id, handle):
                return False
            handle = None  # Successful transfer: Windows now owns this allocation.
            return True
        finally:
            if handle:
                self.kernel.GlobalFree(handle)


def add_bullet_html(prepared: str, *, clipboard=None, sleep=time.sleep) -> bool:
    """Augment only our still-current text; never empty or replace the clipboard."""
    if clipboard is None and platform.system() != "Windows":
        return False
    try:
        clipboard = clipboard or WindowsClipboard()
        payload = html_clipboard_payload(bullet_fragment(prepared))
        for attempt in range(6):
            if clipboard.open():
                break
            if attempt == 5:
                return False
            sleep(0.01)
        try:
            if clipboard.text() != prepared:
                return False
            return clipboard.publish(payload)
        finally:
            clipboard.close()
    except Exception:
        return False
