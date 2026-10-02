"""Session-local named mutexes with pointer-sized Win32 handles; no audio imports."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

APP_MUTEX = "Local\\PushToTalkRealtime_Instance"
SUPERVISOR_MUTEX = "Local\\PushToTalkRealtime_Supervisor"


def instance_exists(name: str) -> bool:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenMutexW(0x00100000, False, name)  # SYNCHRONIZE only
    if not handle:
        error = ctypes.get_last_error()
        if error == 2:  # ERROR_FILE_NOT_FOUND
            return False
        raise ctypes.WinError(error)
    kernel.CloseHandle(handle)
    return True


class WindowsInstance:
    def __init__(self, name: str):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        self.handle = self.kernel.CreateMutexW(None, False, name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.acquired = ctypes.get_last_error() != 183
        if not self.acquired:
            self.release()

    def release(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()
