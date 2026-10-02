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
from runtime_diagnostics import Diagnostics, source_hash
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
DIAGNOSTICS = Diagnostics("launcher")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the push-to-talk tray app.")
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run the tray app in the current process instead of delegating/detaching.",
    )
    parser.add_argument("--supervise", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--ptt-only", action="store_true", help="Disable idle microphone pre-roll capture."
    )
    parser.add_argument("--restart-after", type=int, help=argparse.SUPPRESS)
    parser.add_argument(
        "--launch-source",
        choices=["scheduled_task", "package_manager", "manual", "restart"],
        default=os.getenv("PUSH_TO_TALK_LAUNCH_SOURCE", "manual"),
    )
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
    with output_path.open("a", encoding="utf-8"):
        process = subprocess.Popen(
            command,
            cwd=SCRIPT_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            **detached_popen_kwargs(),
        )
        DIAGNOSTICS.emit("detached", child_pid=getattr(process, "pid", None))
    return 0


def run_foreground() -> int:
    import push_to_talk_realtime as app

    expected = EXPECTED_EXIT if os.getenv(SUPERVISED_ENV) == "1" else 0

    def terminate(*_):
        app.diagnostic_exit_reason = "sigterm"
        app.APP_DIAGNOSTICS.emit("shutdown_requested", reason="sigterm")
        sys.exit(expected)

    signal.signal(signal.SIGTERM, terminate)
    result = app.main()
    return expected if result == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    os.environ["PUSH_TO_TALK_LAUNCH_SOURCE"] = args.launch_source
    DIAGNOSTICS.emit(
        "started",
        source_hash=source_hash(SCRIPT_DIR),
        parent_run_id=os.getenv("PUSH_TO_TALK_PARENT_RUN_ID", ""),
        launch_source=args.launch_source,
        mode="supervise" if args.supervise else "foreground" if args.foreground else "detached",
    )
    if platform.system() == "Windows":
        os.environ.setdefault("MICROPHONE_PRE_ROLL_ENABLED", "0")
    if args.ptt_only:
        os.environ["MICROPHONE_PRE_ROLL_ENABLED"] = "0"
    if args.restart_after is not None:
        if platform.system() == "Windows":
            if not wait_for_windows_process(args.restart_after):
                DIAGNOSTICS.emit("restart_wait_timeout", previous_pid=args.restart_after)
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
        if platform.system() == "Windows":
            from windows_instance import (
                APP_MUTEX,
                SUPERVISOR_MUTEX,
                WindowsInstance,
                instance_exists,
            )

            with WindowsInstance(SUPERVISOR_MUTEX) as guard:
                if not guard.acquired:
                    DIAGNOSTICS.emit("duplicate_rejected", reason="duplicate", mode="supervise")
                    return 0
                return supervise(
                    [
                        startup_python_executable(sys.executable),
                        "-u",
                        str(SCRIPT_PATH),
                        "--foreground",
                    ],
                    SCRIPT_DIR,
                    LAUNCHER_LOG_PATH,
                    existing_instance=lambda: instance_exists(APP_MUTEX),
                )
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


def entrypoint() -> int:
    try:
        result = main()
        DIAGNOSTICS.emit("stopped", exit_code=result, reason="normal_return")
        return result
    except Exception as exc:
        DIAGNOSTICS.emit("exception", exception=exc, reason="unhandled")
        # No exception messages/source lines: provider errors can contain user content.
        path = LAUNCHER_LOG_PATH.with_name("push_to_talk_supervisor_bootstrap.log")
        path.parent.mkdir(parents=True, exist_ok=True)
        rotate_file(path, LAUNCHER_LOG_MAX_BYTES, LAUNCHER_LOG_BACKUP_COUNT)
        with path.open("a", encoding="utf-8") as output:
            output.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%S')} pid={os.getpid()} launcher failed\n"
            )
            output.write(
                f"exception_type={type(exc).__name__}; see diagnostics/launcher.events.jsonl\n"
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
