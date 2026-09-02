from __future__ import annotations

import math
import platform
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from PIL import Image, ImageChops, ImageDraw

INDICATOR_SIZE = 76
INDICATOR_TARGET_FPS = 120
INDICATOR_IDLE_POLL_FPS = 30
INDICATOR_SUPERSAMPLE_SCALE = 4
TRACK_WIDTH = 1.25


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


def render_indicator_image(
    frame: IndicatorFrame,
    color: tuple[int, int, int, int],
    *,
    size: int = INDICATOR_SIZE,
    scale: int = INDICATOR_SUPERSAMPLE_SCALE,
) -> Image.Image:
    render_size = size * scale
    center = render_size / 2
    radius = frame.radius * scale
    bounds = (
        round(center - radius),
        round(center - radius),
        round(center + radius),
        round(center + radius),
    )
    image = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    track_rgb = muted_color(color)[:3]
    draw.ellipse(
        bounds,
        outline=(*track_rgb, 178),
        width=max(1, round(TRACK_WIDTH * scale)),
    )
    draw.arc(
        bounds,
        start=frame.arc_start,
        end=frame.arc_start + frame.arc_extent,
        fill=color,
        width=max(1, round(frame.arc_width * scale)),
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def premultiplied_bgra_bytes(image: Image.Image) -> bytes:
    red, green, blue, alpha = image.convert("RGBA").split()
    premultiplied = Image.merge(
        "RGBA",
        (
            ImageChops.multiply(red, alpha),
            ImageChops.multiply(green, alpha),
            ImageChops.multiply(blue, alpha),
            alpha,
        ),
    )
    return premultiplied.tobytes("raw", "BGRA")


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
            name="cursor-activity-indicator",
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

        class BitmapInfoHeader(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class RgbQuad(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("rgbBlue", wintypes.BYTE),
                ("rgbGreen", wintypes.BYTE),
                ("rgbRed", wintypes.BYTE),
                ("rgbReserved", wintypes.BYTE),
            ]

        class BitmapInfo(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("bmiHeader", BitmapInfoHeader),
                ("bmiColors", RgbQuad * 1),
            ]

        class BlendFunction(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("BlendOp", wintypes.BYTE),
                ("BlendFlags", wintypes.BYTE),
                ("SourceConstantAlpha", wintypes.BYTE),
                ("AlphaFormat", wintypes.BYTE),
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
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = ctypes.c_ssize_t
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND,
            wintypes.HDC,
            ctypes.POINTER(wintypes.POINT),
            ctypes.POINTER(wintypes.SIZE),
            wintypes.HDC,
            ctypes.POINTER(wintypes.POINT),
            wintypes.COLORREF,
            ctypes.POINTER(BlendFunction),
            wintypes.DWORD,
        ]
        user32.UpdateLayeredWindow.restype = wintypes.BOOL
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(BitmapInfo),
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.HANDLE,
            wintypes.DWORD,
        ]
        gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL

        def wndproc(hwnd, message, wparam, lparam):
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

        memory_dc = gdi32.CreateCompatibleDC(None)
        if not memory_dc:
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(class_name, instance)
            raise ctypes.WinError()
        bitmap_info = BitmapInfo(
            BitmapInfoHeader(
                ctypes.sizeof(BitmapInfoHeader),
                INDICATOR_SIZE,
                -INDICATOR_SIZE,
                1,
                32,
                0,
                INDICATOR_SIZE * INDICATOR_SIZE * 4,
                0,
                0,
                0,
                0,
            ),
            (RgbQuad * 1)(),
        )
        pixel_buffer = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(
            memory_dc,
            ctypes.byref(bitmap_info),
            0,
            ctypes.byref(pixel_buffer),
            None,
            0,
        )
        if not bitmap or not pixel_buffer.value:
            gdi32.DeleteDC(memory_dc)
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(class_name, instance)
            raise ctypes.WinError()
        previous_bitmap = gdi32.SelectObject(memory_dc, bitmap)

        started_at = time.monotonic()
        shown = False
        source_point = wintypes.POINT(0, 0)
        window_size = wintypes.SIZE(INDICATOR_SIZE, INDICATOR_SIZE)
        blend = BlendFunction(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA

        def update_frame() -> bool:
            nonlocal shown
            snapshot = self.snapshot_provider()
            if not snapshot.visible:
                if shown:
                    user32.ShowWindow(hwnd, 0)  # SW_HIDE
                    shown = False
                return False
            frame = indicator_frame(
                time.monotonic() - started_at,
                snapshot.motion_speed,
            )
            image = render_indicator_image(frame, snapshot.color)
            pixels = premultiplied_bgra_bytes(image)
            ctypes.memmove(pixel_buffer, pixels, len(pixels))
            cursor = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cursor))
            offset = INDICATOR_SIZE // 2
            destination = wintypes.POINT(cursor.x - offset, cursor.y - offset)
            if not user32.UpdateLayeredWindow(
                hwnd,
                None,
                ctypes.byref(destination),
                ctypes.byref(window_size),
                memory_dc,
                ctypes.byref(source_point),
                0,
                ctypes.byref(blend),
                0x00000002,  # ULW_ALPHA
            ):
                raise ctypes.WinError()
            if not shown:
                user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
                shown = True
            return True

        winmm = ctypes.windll.winmm
        winmm.timeBeginPeriod.argtypes = [wintypes.UINT]
        winmm.timeBeginPeriod.restype = wintypes.UINT
        winmm.timeEndPeriod.argtypes = [wintypes.UINT]
        winmm.timeEndPeriod.restype = wintypes.UINT
        high_resolution_timer = False
        try:
            message = wintypes.MSG()
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
                active = update_frame()
                if active and not high_resolution_timer:
                    high_resolution_timer = winmm.timeBeginPeriod(1) == 0
                elif not active and high_resolution_timer:
                    winmm.timeEndPeriod(1)
                    high_resolution_timer = False
                frame_interval_s = 1.0 / (
                    INDICATOR_TARGET_FPS if active else INDICATOR_IDLE_POLL_FPS
                )
                next_frame_at += frame_interval_s
                sleep_s = next_frame_at - time.perf_counter()
                if sleep_s > 0:
                    time.sleep(sleep_s)
                else:
                    next_frame_at = time.perf_counter()
        finally:
            if high_resolution_timer:
                winmm.timeEndPeriod(1)
            gdi32.SelectObject(memory_dc, previous_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            if user32.IsWindow(hwnd):
                user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(class_name, instance)
