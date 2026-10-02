"""Small blocking process monitor; deliberately independent of audio and GUI imports."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from runtime_diagnostics import Diagnostics, app_health
from runtime_paths import rotate_file

SUPERVISED_ENV = "PUSH_TO_TALK_SUPERVISED"
EXPECTED_EXIT = 23


def supervise(
    command: list[str],
    cwd: Path,
    output_path: Path,
    *,
    existing_instance: Callable[[], bool] | None = None,
) -> int:
    log_path = output_path.with_name("push_to_talk_supervisor.log")
    diagnostics = Diagnostics("supervisor")
    diagnostics.begin(
        launch_source=os.getenv("PUSH_TO_TALK_LAUNCH_SOURCE", "unknown"),
        progress_source="process_monitor",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def log(message: str) -> None:
        entry = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
        try:
            rotate_file(log_path, 512 * 1024, 2)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(entry)
        except OSError:
            # A logging failure must not abandon a running child or spawn duplicates.
            try:
                if sys.stderr is not None:
                    sys.stderr.write(entry)
                    sys.stderr.flush()
            except OSError:
                pass

    failures = 0
    monitoring_existing = False
    environment = dict(
        os.environ, **{SUPERVISED_ENV: "1", "PUSH_TO_TALK_PARENT_RUN_ID": diagnostics.run_id}
    )
    log(f"Supervisor started pid={os.getpid()}")
    while True:
        started = time.monotonic()
        try:
            if existing_instance is not None and existing_instance():
                if not monitoring_existing:
                    log("Existing app detected; monitoring without interrupting it")
                    diagnostics.emit("existing_app_observed", readiness="unknown")
                    monitoring_existing = True
                diagnostics.heartbeat(
                    progress_source="process_monitor", **app_health(diagnostics.root)
                )
                time.sleep(1.0)
                continue
            if monitoring_existing:
                log("Existing app exited; starting replacement")
                diagnostics.emit("existing_app_disappeared", reason="unknown")
                monitoring_existing = False
            rotate_file(output_path, 2 * 1024 * 1024, 2)
            with output_path.open("a", encoding="utf-8"):
                child = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                log(f"Child started pid={child.pid}")
                diagnostics.emit("child_started", child_pid=child.pid)
                while True:
                    try:
                        code = child.wait(timeout=5)
                        break
                    except subprocess.TimeoutExpired:
                        diagnostics.heartbeat(
                            child_pid=child.pid,
                            progress_source="process_monitor",
                            **app_health(diagnostics.root, child.pid),
                        )
            lifetime = time.monotonic() - started
            log(f"Child exited pid={child.pid} code={code} lifetime_s={lifetime:.3f}")
            diagnostics.emit(
                "child_exited",
                child_pid=child.pid,
                exit_code=code,
                lifetime_s=round(lifetime, 3),
                intentional=code == EXPECTED_EXIT,
                reason="expected_exit" if code == EXPECTED_EXIT else "abnormal_exit",
            )
            if code == EXPECTED_EXIT:
                log("Intentional exit or existing instance; supervisor stopped")
                diagnostics.end("expected_exit")
                return 0
        except OSError as exc:
            lifetime = time.monotonic() - started
            log(f"Child launch failed: {type(exc).__name__}")
            diagnostics.emit("launch_failed", exception=exc, reason="launch_error")
        failures = 0 if lifetime >= 60.0 else failures + 1
        delay = min(60.0, 2.0 ** min(failures, 6))
        log(f"Unexpected exit; restarting in {delay:.0f}s")
        diagnostics.emit("recovery_scheduled", delay_s=delay, recovery_count=failures)
        time.sleep(delay)


def wait_for_windows_process(pid: int, timeout_ms: int = 30000) -> bool:
    """Wait without os.kill(pid, 0), which terminates processes on Windows."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: no such PID
    try:
        return kernel.WaitForSingleObject(handle, timeout_ms) == 0
    finally:
        kernel.CloseHandle(handle)
