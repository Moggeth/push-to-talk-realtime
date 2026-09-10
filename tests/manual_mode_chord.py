"""Opt-in Windows smoke test in a temporary focused field; no audio/API calls."""

import ctypes
import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import push_to_talk_realtime as app
from platform_input import send_paste_shortcut

root = tk.Tk()
root.title("Push-to-talk shortcut verification")
entry = tk.Entry(root, width=60)
entry.pack(padx=20, pady=20)
root.update()
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
    ctypes.windll.user32.keybd_event(vk, 0, 2 if up else 0, 0)
    settle()


try:
    root.lift()
    entry.focus_force()
    settle()
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
    assert entry.get() == "PTT-SMOKE", entry.get()
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
