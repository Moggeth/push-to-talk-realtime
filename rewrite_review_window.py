"""Non-activating comparison popup. Text travels through pipes, never files."""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import ClassVar

from rewrite_replacement import WindowsTextReplacement
from rewrite_review import ReviewLifetime

BG, SURFACE, BORDER = "#202124", "#2A2B2F", "#3A3B40"
FG, SECONDARY, ACCENT = "#ECECEE", "#A8A8B0", "#E07AD0"


def work_area(root):
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_: ClassVar = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    try:
        user32 = ctypes.windll.user32
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(user32.MonitorFromPoint(point, 2), ctypes.byref(info)):
            raise OSError("monitor_unavailable")
        r = info.rcWork
        return (point.x, point.y), (r.left, r.top, r.right, r.bottom)
    except Exception:
        return root.winfo_pointerxy(), (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())


def no_activate(window):
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    hwnd = user32.GetParent(window.winfo_id())
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    style = user32.GetWindowLongPtrW(hwnd, -20)
    user32.SetWindowLongPtrW(hwnd, -20, style | 0x08000000 | 0x80 | 0x8)
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x13)
    if not hasattr(window, "_noactivate_callback"):
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )
        old_proc = user32.GetWindowLongPtrW(hwnd, -4)
        user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CallWindowProcW.restype = ctypes.c_ssize_t

        def wndproc(handle, message, wparam, lparam):
            if message == 0x21:
                return 3  # MA_NOACTIVATE: clicks must not steal the editor's caret.
            return user32.CallWindowProcW(old_proc, handle, message, wparam, lparam)

        window._noactivate_callback = callback_type(wndproc)
        window._old_proc = (hwnd, old_proc)
        user32.SetWindowLongPtrW(
            hwnd, -4, ctypes.cast(window._noactivate_callback, ctypes.c_void_p).value
        )


class ReviewPopup:
    def __init__(self, root, raw, processed, backend, can_replace):
        self.root, self.backend = root, backend
        self.raw, self.processed = raw, processed
        self.active = "processed"
        self.can_replace = can_replace
        self.closed = False
        self.busy = False
        self.status_until = 0.0
        self.next_verify = time.monotonic() + 0.3
        self.lifetime = ReviewLifetime(time.monotonic())
        self.window = w = tk.Toplevel(root, bg=BORDER)
        w.withdraw()
        w.title("Push-to-talk comparison")
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.0)
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)
        pointer, area = work_area(root)
        self.width = min(round(420 * self.scale), area[2] - area[0] - 16)
        body = tk.Frame(w, bg=BG, padx=10, pady=10)
        body.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(body, bg=BG)
        header.pack(fill="x", pady=(0, 6))
        self.status = tk.Label(
            header,
            text="Inserted" if can_replace else "Copy only",
            font=("Segoe UI", 9),
            fg=SECONDARY,
            bg=BG,
            anchor="w",
        )
        self.status.pack(side="left", fill="x", expand=True)
        families = tkfont.families(root)
        icon_font = next(
            (f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None
        )
        close = tk.Label(
            header,
            text="\ue711" if icon_font else "\u00d7",
            fg=SECONDARY,
            bg=BG,
            font=(icon_font or "Segoe UI", 10),
            padx=5,
            pady=3,
            cursor="hand2",
        )
        close.pack(side="right")
        close.bind("<Button-1>", lambda _: self.close())
        self.bars, self.editors = {}, []
        for key, label, text in (("processed", "Processed", processed), ("raw", "Raw", raw)):
            tk.Label(
                body, text=label, bg=BG, fg=FG, anchor="w", font=("Segoe UI Semibold", 9)
            ).pack(fill="x", pady=(2, 3))
            region = tk.Frame(body, bg=SURFACE)
            region.pack(fill="both", expand=True, pady=(0, 8))
            self.bars[key] = tk.Frame(region, width=2, bg=ACCENT if key == self.active else SURFACE)
            self.bars[key].pack(side="left", fill="y")
            editor = tk.Text(
                region,
                height=min(7, max(2, len(text) // 54 + text.count("\n") + 1)),
                width=1,
                wrap="word",
                bg=SURFACE,
                fg=FG,
                borderwidth=0,
                font=("Segoe UI", 10),
                padx=6,
                pady=4,
                takefocus=False,
                insertwidth=0,
                highlightthickness=0,
            )
            scrollbar = tk.Scrollbar(region, command=editor.yview, width=10, takefocus=False)
            editor.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            editor.pack(side="left", fill="both", expand=True)
            editor.insert("1.0", text[:20000] + ("\n..." if len(text) > 20000 else ""))
            editor.configure(state="disabled")
            editor.bind("<Button-1>", lambda _: "break")
            editor.bind("<MouseWheel>", lambda event, e=editor: self.scroll(e, event))
            self.editors.append(editor)
        footer = tk.Frame(body, bg=BG)
        footer.pack(fill="x")
        self.copy_button = tk.Label(
            footer,
            text="Copy processed",
            bg=BG,
            fg=SECONDARY,
            font=("Segoe UI", 9),
            padx=5,
            pady=6,
            cursor="hand2",
        )
        self.copy_button.pack(side="left")
        self.copy_button.bind("<Button-1>", lambda _: self.copy_active())
        self.action = tk.Label(
            footer,
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 9),
            padx=12,
            pady=6,
            highlightthickness=1,
            highlightbackground=ACCENT,
            cursor="hand2",
        )
        self.action.pack(side="right")
        self.action.bind("<Button-1>", lambda _: self.choose())
        self.action.bind("<Enter>", lambda _: self.action.configure(bg="#3A2236"))
        self.action.bind("<Leave>", lambda _: self.action.configure(bg=BG))
        w.geometry(f"{self.width}x{round(390 * self.scale)}")
        w.update_idletasks()
        height = min(round(400 * self.scale), area[3] - area[1] - 16, w.winfo_reqheight())
        x = pointer[0] + round(58 * self.scale)
        y = pointer[1] + round(20 * self.scale)
        if x + self.width > area[2] - 8:
            x = pointer[0] - self.width - round(58 * self.scale)
        if y + height > area[3] - 8:
            y = pointer[1] - height - 20
        x = max(area[0] + 8, min(x, area[2] - self.width - 8))
        y = max(area[1] + 8, min(y, area[3] - height - 8))
        self.position = (x, y, height)
        w.geometry(f"{self.width}x{height}{x:+d}{y:+d}")
        w.update_idletasks()
        no_activate(w)
        w.deiconify()
        no_activate(w)
        self.lifetime = ReviewLifetime(time.monotonic())
        self.update_labels()
        self.tick()
        print(
            json.dumps(
                {
                    "event": "review_visible",
                    "replace_available": bool(can_replace),
                    "mapped": bool(w.winfo_viewable()),
                }
            ),
            flush=True,
        )

    def scroll(self, editor, event):
        editor.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def update_labels(self):
        other = "raw" if self.active == "processed" else "processed"
        self.action.configure(text=("Use " if self.can_replace else "Copy ") + other)
        self.copy_button.configure(text="Copy " + self.active)
        for key, bar in self.bars.items():
            bar.configure(bg=ACCENT if key == self.active else SURFACE)

    def copy_active(self):
        import pyperclip

        try:
            pyperclip.copy(self.processed if self.active == "processed" else self.raw)
            self.status.configure(text="Copied")
        except Exception:
            self.status.configure(text="Clipboard unavailable")
        self.status_until = time.monotonic() + 1.5

    def choose(self):
        import pyperclip

        if self.busy:
            return
        self.busy = True
        self.status.configure(text="Replacing...")
        self.window.update_idletasks()
        other = "raw" if self.active == "processed" else "processed"
        text = self.raw if other == "raw" else self.processed
        try:
            if self.can_replace and self.backend.replace(text):
                self.active = other
                self.status.configure(
                    text="Raw restored" if other == "raw" else "Processed restored"
                )
            else:
                self.can_replace = False
                pyperclip.copy(text)
                self.status.configure(text=other.title() + " copied - target unchanged")
        except Exception:
            self.can_replace = False
            self.status.configure(text="Copy only")
        finally:
            self.busy = False
            self.status_until = time.monotonic() + 1.5
            self.update_labels()

    def tick(self):
        if self.closed:
            return
        now = time.monotonic()
        x, y = self.window.winfo_pointerxy()
        wx, wy = self.window.winfo_rootx(), self.window.winfo_rooty()
        inside = (
            wx <= x < wx + self.window.winfo_width() and wy <= y < wy + self.window.winfo_height()
        )
        self.lifetime.hover(inside, now)
        opacity = self.lifetime.opacity(now, self.busy)
        if now - self.lifetime.created > 0.1 and opacity <= 0:
            self.close()
            return
        self.window.attributes("-alpha", opacity)
        entry = min(1.0, (now - self.lifetime.created) / 0.1)
        if entry < 1:
            px, py, height = self.position
            offset = round(6 * (1 - entry) ** 3)
            self.window.geometry(f"{self.width}x{height}{px:+d}{py + offset:+d}")
        if sys.platform == "win32":
            import ctypes

            if ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
                self.close()
                return
        if now >= max(self.status_until, self.next_verify) and self.can_replace:
            self.next_verify = now + 0.25
            if not self.backend.verify():
                self.can_replace = False
                self.status.configure(text="Copy only - target changed")
                self.update_labels()
        self.window.after(33, self.tick)

    def close(self):
        if not self.closed:
            self.closed = True
            for editor in self.editors:
                editor.configure(state="normal")
                editor.delete("1.0", "end")
            self.raw = self.processed = ""
            self.backend.anchor = self.backend.caret = None
            self.backend.current = ""
            if hasattr(self.window, "_old_proc"):
                import ctypes

                hwnd, old = self.window._old_proc
                ctypes.windll.user32.SetWindowLongPtrW(hwnd, -4, old)
            self.window.destroy()


def main():
    root = tk.Tk()
    root.withdraw()
    incoming = queue.Queue(maxsize=16)
    backend = WindowsTextReplacement()
    popup = None
    captured = None

    def enable_when_settled(view, token, processed, deadline):
        if view is not popup or view.closed or token != captured or view.status_until:
            return
        if backend.attach(processed):
            view.can_replace = True
            view.status.configure(text="Inserted")
            view.update_labels()
        elif time.monotonic() < deadline:
            root.after(50, lambda: enable_when_settled(view, token, processed, deadline))

    def read():
        try:
            for line in sys.stdin:
                incoming.put(json.loads(line))
        finally:
            incoming.put({"command": "exit"})

    def poll():
        nonlocal popup, captured
        try:
            while True:
                message = incoming.get_nowait()
                command = message.get("command")
                if command == "exit":
                    root.destroy()
                    return
                if command in ("capture", "dismiss", "show") and popup is not None:
                    popup.close()
                    popup = None
                if command == "capture":
                    captured = message["id"]
                    ok = backend.capture(message.get("target"))
                    print(json.dumps({"id": captured, "ready": ok}), flush=True)
                elif command == "dismiss":
                    captured = None
                    backend.anchor = None
                elif command == "show":
                    enabled = (
                        message.get("pasted")
                        and captured is not None
                        and captured == message.get("id")
                        and backend.attach(message["processed"])
                    )
                    popup = ReviewPopup(
                        root, message["raw"], message["processed"], backend, bool(enabled)
                    )
                    if not enabled and message.get("pasted") and captured == message.get("id"):
                        view, token, processed = popup, captured, message["processed"]
                        root.after(
                            50,
                            lambda v=view, t=token, p=processed: enable_when_settled(
                                v, t, p, time.monotonic() + 0.4
                            ),
                        )
        except queue.Empty:
            pass
        except Exception as exc:
            # Protocol diagnostics contain no transcript or exception message.
            print(json.dumps({"error": type(exc).__name__}), flush=True)
        root.after(25, poll)

    threading.Thread(target=read, daemon=True).start()
    root.after(25, poll)
    root.mainloop()


if __name__ == "__main__":
    main()
