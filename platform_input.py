import platform
from dataclasses import dataclass
from typing import ClassVar

from pynput import keyboard as pynput_keyboard


@dataclass(frozen=True)
class PasteTarget:
    system_name: str
    foreground_hwnd: int
    focus_hwnd: int
    focus_class_name: str
    thread_id: int
    process_id: int


def supports_foreground_console_detection(system_name: str | None = None) -> bool:
    return (system_name or platform.system()) == "Windows"


def get_paste_modifier(system_name: str | None = None) -> pynput_keyboard.Key:
    if (system_name or platform.system()) == "Darwin":
        return pynput_keyboard.Key.cmd
    return pynput_keyboard.Key.ctrl


def send_paste_shortcut(controller: pynput_keyboard.Controller | None = None) -> None:
    if controller is None and platform.system() == "Windows":
        import ctypes

        from recording_modes import PASTE_EVENT_TAG

        # Tag our output so a new recording cannot mistake it for the mode chord.
        emit = ctypes.windll.user32.keybd_event
        emit.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_size_t]
        emit(0x11, 0, 0, PASTE_EVENT_TAG)
        try:
            emit(0x56, 0, 0, PASTE_EVENT_TAG)
            emit(0x56, 0, 2, PASTE_EVENT_TAG)
        finally:
            emit(0x11, 0, 2, PASTE_EVENT_TAG)
        return
    keyboard_controller = controller or pynput_keyboard.Controller()
    modifier = get_paste_modifier()
    with keyboard_controller.pressed(modifier):
        keyboard_controller.press("v")
        keyboard_controller.release("v")


def capture_paste_target(system_name: str | None = None) -> PasteTarget | None:
    """Remember the focused Windows control without changing focus."""
    resolved_system = system_name or platform.system()
    if resolved_system != "Windows":
        return None
    try:
        return _capture_windows_paste_target(resolved_system)
    except Exception:  # pylint: disable=broad-except
        return None


def foreground_matches_paste_target(target: PasteTarget | None) -> bool:
    if target is None or target.system_name != "Windows":
        return True
    try:
        import ctypes

        return int(ctypes.windll.user32.GetForegroundWindow()) == target.foreground_hwnd
    except Exception:  # pylint: disable=broad-except
        return False


def try_insert_text_into_target(text: str, target: PasteTarget | None) -> bool:
    if not text or target is None or target.system_name != "Windows":
        return False
    try:
        return _try_insert_text_into_windows_target(text, target)
    except Exception:  # pylint: disable=broad-except
        return False


def _capture_windows_paste_target(system_name: str) -> PasteTarget | None:
    import ctypes
    from ctypes import wintypes

    class GUITHREADINFO(ctypes.Structure):
        _fields_: ClassVar = [
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hwndActive", wintypes.HWND),
            ("hwndFocus", wintypes.HWND),
            ("hwndCapture", wintypes.HWND),
            ("hwndMenuOwner", wintypes.HWND),
            ("hwndMoveSize", wintypes.HWND),
            ("hwndCaret", wintypes.HWND),
            ("rcCaret", wintypes.RECT),
        ]

    user32 = ctypes.windll.user32
    foreground_hwnd = int(user32.GetForegroundWindow())
    if not foreground_hwnd:
        return None
    thread_id = int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return None
    focus_hwnd = int(info.hwndFocus or info.hwndCaret or foreground_hwnd)
    if not focus_hwnd:
        return None
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(focus_hwnd), ctypes.byref(process_id))
    return PasteTarget(
        system_name=system_name,
        foreground_hwnd=foreground_hwnd,
        focus_hwnd=focus_hwnd,
        focus_class_name=_windows_class_name(focus_hwnd),
        thread_id=thread_id,
        process_id=int(process_id.value),
    )


def _windows_class_name(hwnd: int) -> str:
    import ctypes

    buffer = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def _try_insert_text_into_windows_target(text: str, target: PasteTarget) -> bool:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPCWSTR,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(
            ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
        ),
    ]
    user32.SendMessageTimeoutW.restype = wintypes.LPARAM
    hwnd = wintypes.HWND(target.focus_hwnd)
    if not user32.IsWindow(hwnd):
        return False

    class_name = _windows_class_name(target.focus_hwnd).lower()
    supported_class_fragments = (
        "edit",
        "richedit",
        "rich edit",
        "scintilla",
        "windowsforms",
        "thundertextbox",
    )
    if not any(fragment in class_name for fragment in supported_class_fragments):
        return False

    EM_REPLACESEL = 0x00C2
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_ulonglong() if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong()
    sent = user32.SendMessageTimeoutW(
        hwnd,
        EM_REPLACESEL,
        True,
        text,
        SMTO_ABORTIFHUNG,
        250,
        ctypes.byref(result),
    )
    return bool(sent)
