"""Opt-in Windows smoke test in a temporary focused field; no audio/API calls."""

import ctypes
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import push_to_talk_realtime as app
from platform_input import send_paste_shortcut

root = tk.Tk()
root.title("Push-to-talk shortcut verification")
root.attributes("-topmost", True)
entry = tk.Entry(root, width=60)
entry.pack(padx=20, pady=20)
events = []
entry.bind("<KeyPress>", lambda event: events.append((event.keysym, event.state)))
root.update()
user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
window = user32.GetAncestor(root.winfo_id(), 2)
old_clipboard = app.pyperclip.paste()
app.pyperclip.copy("PTT-SMOKE")
listener = app.create_keyboard_listener()
listener.start()
listener.wait()


def settle():
    deadline = time.monotonic() + 0.12
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)


def key(vk, up=False):
    assert root.focus_displayof() == entry, "Smoke-test text field lost focus"
    assert user32.GetForegroundWindow() == window, (
        "Windows did not foreground the test window; no input sent"
    )
    ctypes.windll.user32.keybd_event(vk, 0, 2 if up else 0, 0)
    settle()


try:
    root.lift()
    user32.SetForegroundWindow(window)
    entry.focus_force()
    settle()
    assert root.focus_displayof() == entry, "Unable to focus smoke-test text field"
    app.state.is_listening = True
    for expected in ("tidy", "fun", "raw"):
        key(0x11)
        key(0x56)
        key(0x56)  # Repeat must not advance again.
        assert app.state.recording_rewrite_mode == expected
        key(0x56, True)
        key(0x11, True)
        assert entry.get() == "", entry.get()
    app.state.is_listening = False
    key(0x11)
    key(0x56)
    key(0x56, True)
    key(0x11, True)
    assert entry.get() == "PTT-SMOKE", f"Paste failed; focused-field key events: {events[-12:]}"
    entry.delete(0, "end")
    app.state.is_listening = True
    send_paste_shortcut()
    settle()
    assert entry.get() == "PTT-SMOKE", entry.get()
    assert app.state.recording_rewrite_mode == "raw"
    print("PASS: three modes, repeat suppression, ordinary paste, tagged application paste")
finally:
    listener.stop()
    listener.join(timeout=2)
    app.pyperclip.copy(old_clipboard)
    root.destroy()
