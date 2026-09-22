#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

from process_supervisor import EXPECTED_EXIT, SUPERVISED_ENV, supervise, wait_for_windows_process
from runtime_paths import resolve_runtime_paths, rotate_file
from startup_integration import linux_user_service_path, startup_python_executable

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = SCRIPT_DIR / "start_push_to_talk.py"
LAUNCHER_LOG_PATH = resolve_runtime_paths().launcher_log
LAUNCHER_LOG_MAX_BYTES = max(
    64 * 1024,
    int(os.getenv("PUSH_TO_TALK_LAUNCHER_LOG_MAX_BYTES", str(2 * 1024 * 1024))),
)
LAUNCHER_LOG_BACKUP_COUNT = 2
SYSTEMD_SERVICE_NAME = os.getenv("PUSH_TO_TALK_SERVICE_NAME", "push-to-talk-realtime.service")
SYSTEMD_MANAGED_ENV = "PUSH_TO_TALK_MANAGED_BY_SYSTEMD"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the push-to-talk tray app.")
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run the tray app in the current process instead of delegating/detaching.",
    )
    parser.add_argument("--supervise", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--restart-after", type=int, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def should_delegate_to_linux_service() -> bool:
    if platform.system() != "Linux":
        return False
    if os.getenv(SYSTEMD_MANAGED_ENV) == "1":
        return False
    return linux_user_service_path(SYSTEMD_SERVICE_NAME).exists()


def start_linux_service() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "start", SYSTEMD_SERVICE_NAME],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return False
    return result.returncode == 0


def detached_popen_kwargs() -> dict[str, object]:
    if platform.system() == "Windows":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return {"creationflags": creationflags}
    return {"start_new_session": True}


def spawn_detached_background() -> int:
    LAUNCHER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rotate_file(LAUNCHER_LOG_PATH, LAUNCHER_LOG_MAX_BYTES, LAUNCHER_LOG_BACKUP_COUNT)
    python_executable = startup_python_executable(sys.executable)
    mode = "--supervise" if platform.system() == "Windows" else "--foreground"
    command = [python_executable, str(SCRIPT_PATH), mode]
    output_path = (
        LAUNCHER_LOG_PATH.with_name("push_to_talk_supervisor_bootstrap.log")
        if mode == "--supervise"
        else LAUNCHER_LOG_PATH
    )
    rotate_file(output_path, LAUNCHER_LOG_MAX_BYTES, LAUNCHER_LOG_BACKUP_COUNT)
    with output_path.open("a", encoding="utf-8") as handle:
        subprocess.Popen(
            command,
            cwd=SCRIPT_DIR,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **detached_popen_kwargs(),
        )
    return 0


def run_foreground() -> int:
    from push_to_talk_realtime import main

    expected = EXPECTED_EXIT if os.getenv(SUPERVISED_ENV) == "1" else 0
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(expected))
    result = main()
    return expected if result == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.restart_after is not None:
        if platform.system() == "Windows":
            if not wait_for_windows_process(args.restart_after):
                return 1
        else:
            for _ in range(300):
                try:
                    os.kill(args.restart_after, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                return 1
    if args.supervise:
        return supervise(
            [startup_python_executable(sys.executable), "-u", str(SCRIPT_PATH), "--foreground"],
            SCRIPT_DIR,
            LAUNCHER_LOG_PATH,
        )
    if args.foreground or os.getenv(SYSTEMD_MANAGED_ENV) == "1":
        return run_foreground()
    if should_delegate_to_linux_service() and start_linux_service():
        return 0
    return spawn_detached_background()


if __name__ == "__main__":
    raise SystemExit(main())
