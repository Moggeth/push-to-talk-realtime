from __future__ import annotations

import math
import platform
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

INDICATOR_SIZE = 76
INDICATOR_TARGET_FPS = 120
TRANSPARENT_RGB = (1, 2, 3)


@dataclass(frozen=True)
class IndicatorFrame:
    radius: float
    arc_start: float
    arc_extent: float
    arc_width: float


@dataclass(frozen=True)
class CursorIndicatorSnapshot:
    visible: bool
    color: tuple[int, int, int, int]
    motion_speed: float = 1.0


def indicator_frame(elapsed_s: float, motion_speed: float = 1.0) -> IndicatorFrame:
    pulse = math.sin(elapsed_s * math.tau * 0.8)
    return IndicatorFrame(
        radius=25.0 + pulse * 1.5,
        arc_start=(elapsed_s * 190.0 * motion_speed - 90.0) % 360.0,
        arc_extent=105.0 + math.sin(elapsed_s * math.tau * 0.55) * 14.0,
        arc_width=2.6 + (pulse + 1.0) * 0.35,
    )


def color_hex(color: tuple[int, int, int, int]) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def muted_color(color: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return (*tuple(round(channel * 0.42) for channel in color[:3]), 255)


def muted_color_hex(color: tuple[int, int, int, int]) -> str:
    return color_hex(muted_color(color))


class CursorActivityIndicator:
    def __init__(
        self,
        snapshot_provider: Callable[[], CursorIndicatorSnapshot],
        log: Callable[..., None],
    ) -> None:
        self.snapshot_provider = snapshot_provider
        self.log = log
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.hwnd = 0

    def start(self) -> bool:
        if platform.system() != "Windows":
            return False
        if self.thread is not None and self.thread.is_alive():
            return True
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            name="cursor-recording-indicator",
            daemon=True,
        )
        self.thread.start()
        return True

    def stop(self) -> None:
        self.stop_event.set()
        hwnd = self.hwnd
        if hwnd:
            import ctypes

            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        worker = self.thread
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.0)
        self.thread = None

    def _run(self) -> None:
        try:
            self._run_windows_message_loop()
        except Exception as exc:  # the recorder must never depend on overlay availability
            self.log(
                "[Cursor indicator] Disabled after initialization failure:",
                exc,
                traceback.format_exc(),
            )
        finally:
            self.hwnd = 0

    def _run_windows_message_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        kernel32 = ctypes.windll.kernel32
        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        class WndClass(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", wndproc_type),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class PaintStruct(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("hdc", wintypes.HDC),
                ("fErase", wintypes.BOOL),
                ("rcPaint", wintypes.RECT),
                ("fRestore", wintypes.BOOL),
                ("fIncUpdate", wintypes.BOOL),
                ("rgbReserved", ctypes.c_byte * 32),
            ]

        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WndClass)]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user32.UnregisterClassW.restype = wintypes.BOOL
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
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PaintStruct)]
        user32.BeginPaint.restype = wintypes.HDC
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.PeekMessageW.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.SetLayeredWindowAttributes.argtypes = [
            wintypes.HWND,
            wintypes.COLORREF,
            wintypes.BYTE,
            wintypes.DWORD,
        ]
        user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.InvalidateRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
            wintypes.BOOL,
        ]
        user32.InvalidateRect.restype = wintypes.BOOL
        user32.UpdateWindow.argtypes = [wintypes.HWND]
        user32.UpdateWindow.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = ctypes.c_ssize_t
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.FillRect.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(wintypes.RECT),
            wintypes.HBRUSH,
        ]
        user32.FillRect.restype = ctypes.c_int
        user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PaintStruct)]
        user32.EndPaint.restype = wintypes.BOOL
        gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
        gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
        gdi32.CreatePen.restype = wintypes.HANDLE
        gdi32.GetStockObject.argtypes = [ctypes.c_int]
        gdi32.GetStockObject.restype = wintypes.HANDLE
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        gdi32.SelectObject.restype = wintypes.HANDLE
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.Ellipse.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        gdi32.Ellipse.restype = wintypes.BOOL
        gdi32.Arc.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        gdi32.Arc.restype = wintypes.BOOL

        def color_ref(color: tuple[int, ...]) -> int:
            return color[0] | (color[1] << 8) | (color[2] << 16)

        started_at = time.monotonic()
        current_snapshot = CursorIndicatorSnapshot(False, (0, 0, 0, 255))

        def paint(hwnd: int) -> None:
            paint_struct = PaintStruct()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(paint_struct))
            rect = wintypes.RECT(0, 0, INDICATOR_SIZE, INDICATOR_SIZE)
            background = gdi32.CreateSolidBrush(color_ref(TRANSPARENT_RGB))
            user32.FillRect(hdc, ctypes.byref(rect), background)
            gdi32.DeleteObject(background)

            snapshot = current_snapshot
            color = snapshot.color
            frame = indicator_frame(
                time.monotonic() - started_at,
                snapshot.motion_speed,
            )
            center = INDICATOR_SIZE // 2
            radius = round(frame.radius)
            bounds = (
                center - radius,
                center - radius,
                center + radius,
                center + radius,
            )
            null_brush = gdi32.GetStockObject(5)  # NULL_BRUSH
            previous_brush = gdi32.SelectObject(hdc, null_brush)

            track_pen = gdi32.CreatePen(0, 1, color_ref(muted_color(color)))
            previous_pen = gdi32.SelectObject(hdc, track_pen)
            gdi32.Ellipse(hdc, *bounds)
            gdi32.SelectObject(hdc, previous_pen)
            gdi32.DeleteObject(track_pen)

            arc_pen = gdi32.CreatePen(0, max(2, round(frame.arc_width)), color_ref(color))
            previous_pen = gdi32.SelectObject(hdc, arc_pen)
            start_angle = math.radians(frame.arc_start)
            end_angle = math.radians(frame.arc_start + frame.arc_extent)
            start_x = round(center + radius * math.cos(start_angle))
            start_y = round(center - radius * math.sin(start_angle))
            end_x = round(center + radius * math.cos(end_angle))
            end_y = round(center - radius * math.sin(end_angle))
            gdi32.Arc(hdc, *bounds, start_x, start_y, end_x, end_y)
            gdi32.SelectObject(hdc, previous_pen)
            gdi32.SelectObject(hdc, previous_brush)
            gdi32.DeleteObject(arc_pen)
            user32.EndPaint(hwnd, ctypes.byref(paint_struct))

        def update_frame(hwnd: int) -> None:
            nonlocal current_snapshot
            snapshot = self.snapshot_provider()
            current_snapshot = snapshot
            if snapshot.visible:
                point = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(point))
                offset = INDICATOR_SIZE // 2
                user32.SetWindowPos(
                    hwnd,
                    ctypes.c_void_p(-1),  # HWND_TOPMOST
                    point.x - offset,
                    point.y - offset,
                    INDICATOR_SIZE,
                    INDICATOR_SIZE,
                    0x0010 | 0x0040,  # SWP_NOACTIVATE | SWP_SHOWWINDOW
                )
                user32.InvalidateRect(hwnd, None, False)
                user32.UpdateWindow(hwnd)
            else:
                user32.ShowWindow(hwnd, 0)  # SW_HIDE

        def wndproc(hwnd, message, wparam, lparam):
            if message == 0x000F:  # WM_PAINT
                paint(hwnd)
                return 0
            if message == 0x0014:  # WM_ERASEBKGND
                return 1
            if message == 0x0010:  # WM_CLOSE
                user32.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:  # WM_DESTROY
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        self._wndproc = wndproc_type(wndproc)
        instance = kernel32.GetModuleHandleW(None)
        class_name = f"PushToTalkCursorIndicator_{id(self)}"
        window_class = WndClass(
            0,
            self._wndproc,
            0,
            0,
            instance,
            None,
            None,
            None,
            None,
            class_name,
        )
        if not user32.RegisterClassW(ctypes.byref(window_class)):
            raise ctypes.WinError()

        extended_style = 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000 | 0x00000008
        hwnd = user32.CreateWindowExW(
            extended_style,
            class_name,
            "",
            0x80000000,  # WS_POPUP
            0,
            0,
            INDICATOR_SIZE,
            INDICATOR_SIZE,
            None,
            None,
            instance,
            None,
        )
        if not hwnd:
            user32.UnregisterClassW(class_name, instance)
            raise ctypes.WinError()
        self.hwnd = hwnd
        user32.SetLayeredWindowAttributes(hwnd, color_ref(TRANSPARENT_RGB), 0, 0x00000001)
        winmm = ctypes.windll.winmm
        winmm.timeBeginPeriod.argtypes = [wintypes.UINT]
        winmm.timeBeginPeriod.restype = wintypes.UINT
        winmm.timeEndPeriod.argtypes = [wintypes.UINT]
        winmm.timeEndPeriod.restype = wintypes.UINT
        high_resolution_timer = winmm.timeBeginPeriod(1) == 0
        try:
            message = wintypes.MSG()
            frame_interval_s = 1.0 / INDICATOR_TARGET_FPS
            next_frame_at = time.perf_counter()
            running = True
            while running:
                while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0x0001):  # PM_REMOVE
                    if message.message == 0x0012:  # WM_QUIT
                        running = False
                        break
                    user32.TranslateMessage(ctypes.byref(message))
                    user32.DispatchMessageW(ctypes.byref(message))
                if not running:
                    break
                if self.stop_event.is_set():
                    user32.DestroyWindow(hwnd)
                    continue
                update_frame(hwnd)
                next_frame_at += frame_interval_s
                sleep_s = next_frame_at - time.perf_counter()
                if sleep_s > 0:
                    time.sleep(sleep_s)
                else:
                    next_frame_at = time.perf_counter()
        finally:
            if high_resolution_timer:
                winmm.timeEndPeriod(1)
        user32.UnregisterClassW(class_name, instance)
