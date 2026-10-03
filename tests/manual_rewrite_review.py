"""Synthetic Windows editor and comparison popup; no microphone or API request."""

import ctypes
import sys
import threading
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from platform_input import capture_paste_target
from rewrite_review import RewriteReviewManager

RAW = "Um, the meeting is Tuesday, no sorry, Thursday at two."
PROCESSED = "The meeting is Thursday at two."


def main():
    root = tk.Tk()
    root.title("Synthetic PTT review test")
    root.geometry("1000x850+100+100")
    label = tk.Label(root, text="Synthetic draft - no API calls", font=("Segoe UI", 12))
    label.pack(pady=12)
    host = tk.Frame(root, height=180)
    host.pack(fill="both", expand=True, padx=15)
    root.update_idletasks()
    user32 = ctypes.windll.user32
    ctypes.windll.kernel32.LoadLibraryW("msftedit.dll")
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    edit = user32.CreateWindowExW(
        0,
        "RICHEDIT50W",
        "Draft: ",
        0x50000000 | 0x800000 | 4 | 0x1000,
        0,
        0,
        600,
        160,
        host.winfo_id(),
        None,
        None,
        None,
    )
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    manager = RewriteReviewManager(lambda *args: print(*args, flush=True))
    manager.start()

    def insert():
        user32.SetFocus(edit)
        user32.SendMessageW(edit, 0xB1, -1, -1)
        root.after(80, finish_insert)

    def finish_insert():
        target = capture_paste_target()

        def captured():
            token = manager.capture(target)

            def deliver():
                value = ctypes.create_unicode_buffer(PROCESSED)
                user32.SendMessageW(edit, 0xC2, 1, ctypes.cast(value, ctypes.c_void_p).value)
                manager.show(RAW, PROCESSED, token, True)

            root.after(0, deliver)

        threading.Thread(target=captured, daemon=True).start()

    tk.Button(root, text="Insert example", command=insert).pack(pady=15)

    def preview():
        from types import SimpleNamespace

        from rewrite_review_window import ReviewPopup

        backend = SimpleNamespace(verify=lambda: False, replace=lambda _: False)
        ReviewPopup(root, RAW, PROCESSED, backend, False)

    tk.Button(root, text="Popup preview", command=preview).pack()

    def close():
        manager.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(180000, close)
    root.mainloop()


if __name__ == "__main__":
    main()
