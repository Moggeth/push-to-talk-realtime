"""Serialize our own desktop output across the tray and comparison helper."""

import platform
from contextlib import contextmanager


@contextmanager
def output_transaction():
    if platform.system() != "Windows":
        yield
        return
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, "Local\\PushToTalkRewriteOutput")
    if not handle:
        raise OSError("output_mutex_unavailable")
    acquired = False
    try:
        acquired = kernel.WaitForSingleObject(handle, 1000) in (0, 0x80)
        if not acquired:
            raise TimeoutError("output_busy")
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)
