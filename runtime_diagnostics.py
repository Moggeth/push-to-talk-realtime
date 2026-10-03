"""Content-free diagnostics. Never serialize messages, arguments, locals or environment."""

from __future__ import annotations

import faulthandler
import hashlib
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from runtime_paths import default_runtime_directory, rotate_file

MAX_BYTES = 4 * 1024 * 1024
BACKUPS = 4
COMPONENTS = {"app", "launcher", "supervisor", "manager", "task"}
EVENTS = {
    "bullet_mode_changed",
    "gesture_setting_changed",
    "rewrite_review",
    "started",
    "heartbeat",
    "stopped",
    "previous_run_unclosed",
    "duplicate_rejected",
    "child_started",
    "child_exited",
    "launch_failed",
    "recovery_scheduled",
    "existing_app_observed",
    "existing_app_disappeared",
    "exception",
    "shutdown_requested",
    "app_ready",
    "state_changed",
    "listener_restarted",
    "restart_wait_timeout",
    "detached",
    "manager_launch",
    "manager_failure",
    "manager_exit",
    "manager_event",
    "task_started",
    "cold_start_failed",
    "python_started",
    "python_exited",
    "task_failed",
}
NUMBERS = {
    "error_line",
    "child_pid",
    "previous_pid",
    "exit_code",
    "lifetime_s",
    "delay_s",
    "attempt",
    "previous_last_seen_epoch",
    "previous_closed_epoch",
    "thread_id",
    "winerror",
    "errno",
    "diagnostic_write_failures",
    "transcriptions",
    "postprocessing",
    "session_count",
    "health_age_s",
    "app_pid",
    "recovery_count",
}
BOOLEANS = {
    "bullet_mode",
    "gesture_enabled",
    "replace_available",
    "popup_mapped",
    "capture_active",
    "capture_start_pending",
    "listener_thread_alive",
    "setup_complete",
    "shutting_down",
    "pre_roll_enabled",
    "queue_state_known",
    "state_lock_available",
    "app_health_available",
    "app_health_fresh",
    "intentional",
    "supervised",
    "launcher_present",
    "python_present",
}
TOKENS = {
    "launch_source": {"scheduled_task", "package_manager", "manual", "restart", "unknown"},
    "mode": {"foreground", "supervise", "detached"},
    "reason": {
        "capture_timeout",
        "helper_start_failed",
        "helper_pipe_closed",
        "helper_response_failed",
        "helper_exited",
        "helper_queue_full",
        "helper_error",
        "visible",
        "quit",
        "restart",
        "sigterm",
        "keyboard_interrupt",
        "normal_return",
        "unexpected_return",
        "expected_exit",
        "abnormal_exit",
        "launch_error",
        "duplicate",
        "unknown",
        "unhandled",
        "thread_unhandled",
        "unraisable",
        "listener_rebind",
        "missing_executable_or_launcher",
    },
    "phase": {"initializing", "validate_paths", "start_python", "wait_python"},
    "readiness": {"reported_ready", "listener_down", "busy", "starting", "unknown", "stale"},
    "progress_source": {"tray_worker", "process_monitor"},
}
LEGACY_CATEGORIES = {
    "Audio",
    "Startup",
    "Tray",
    "Lifecycle",
    "Input",
    "Settings",
    "Crash",
    "Archive",
    "Output",
    "Warmup",
    "Hotkey",
    "Capture metrics",
    "Metrics",
    "Rewrite",
    "Final",
    "Logged",
    "Paste",
    "Pasted",
    "Storage",
    "Cursor indicator",
}


def root_directory() -> Path:
    override = os.getenv("PUSH_TO_TALK_DIAGNOSTICS_DIR")
    return Path(override) if override else default_runtime_directory() / "diagnostics"


def legacy_summary(parts) -> str:
    """Discard all dynamic content, including multiline provider errors and transcripts."""
    first = parts[0] if parts and isinstance(parts[0], str) else ""
    match = re.match(r"\s*\[([^\]]{1,32})\]", first)
    category = match[1] if match and match[1] in LEGACY_CATEGORIES else "Event"
    return f"[{category}] details omitted (see structured diagnostics)"


def safe_exception(exc: BaseException) -> dict:
    frames = []
    for frame in traceback.extract_tb(exc.__traceback__)[-12:]:
        filename = Path(frame.filename).name
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.py", filename):
            filename = "external"
        function = (
            frame.name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,80}", frame.name) else "call"
        )
        frames.append({"file": filename, "line": frame.lineno, "function": function})
    result = {"type": type(exc).__name__[:80], "frames": frames}
    for name in ("errno", "winerror"):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            result[name] = value
    return result


def safe_fields(fields: dict) -> dict:
    output = {}
    for name, value in fields.items():
        if (name in NUMBERS and type(value) in (int, float)) or (
            name in BOOLEANS and type(value) is bool
        ):
            output[name] = value
        elif name in TOKENS and isinstance(value, str):
            output[name] = value if value in TOKENS[name] else "unknown"
        elif (
            name in {"previous_run_id", "parent_run_id", "source_hash"}
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{12,64}", value)
        ):
            output[name] = value
        elif name == "exception" and isinstance(value, BaseException):
            output[name] = safe_exception(value)
    return output


@contextmanager
def file_lock(path: Path):
    """Bounded cross-process lock protects rotation during concurrent launches."""
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        acquired = False
        for _ in range(5):
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                time.sleep(0.01)
        if not acquired:
            raise OSError("diagnostic lock unavailable")
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_UN)


def source_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    for name in (
        "start_push_to_talk.py",
        "process_supervisor.py",
        "push_to_talk_realtime.py",
        "runtime_diagnostics.py",
    ):
        try:
            digest.update(name.encode())
            digest.update((directory / name).read_bytes())
        except OSError:
            digest.update(b"unavailable")
    return digest.hexdigest()[:16]


class Diagnostics:
    def __init__(self, component: str, root: Path | None = None):
        if component not in COMPONENTS:
            raise ValueError("Unknown diagnostic component")
        self.component = component
        self.root = root or root_directory()
        self.run_id = uuid.uuid4().hex
        self.started_ns = time.monotonic_ns()
        self.failures = 0
        self.lock = threading.RLock()
        self.last_heartbeat_ns = 0
        self.active = False
        self.path = self.root / f"{component}.events.jsonl"
        self.state_path = self.root / f"{component}.health.json"

    def _base(self, event: str) -> dict:
        record = {
            "schema": 1,
            "utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "epoch": time.time(),
            "elapsed_s": round((time.monotonic_ns() - self.started_ns) / 1e9, 3),
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "component": self.component,
            "run_id": self.run_id,
            "event": event,
            "python_version": ".".join(map(str, sys.version_info[:3])),
        }
        task_id = os.getenv("PUSH_TO_TALK_TASK_RUN_ID", "")
        if re.fullmatch(r"[0-9a-f]{32}", task_id):
            record["task_run_id"] = task_id
        return record

    def emit(self, event: str, **fields) -> None:
        if event not in EVENTS:
            return
        entry = self._base(event) | safe_fields(fields)
        with self.lock:
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                with file_lock(self.root / f"{self.component}.lock"):
                    rotate_file(self.path, MAX_BYTES, BACKUPS)
                    with self.path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
            except OSError:
                self.failures += 1

    def checkpoint(self, **fields) -> None:
        with self.lock:
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                entry = self._base("heartbeat") | safe_fields(fields)
                entry["diagnostic_write_failures"] = self.failures
                temporary = self.root / f".{self.component}.{os.getpid()}.tmp"
                temporary.write_text(json.dumps(entry), encoding="utf-8")
                temporary.replace(self.state_path)
            except OSError:
                self.failures += 1

    def begin(self, **fields) -> None:
        try:
            previous = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(previous, dict):
                raise ValueError("Invalid health record")
            if previous.get("event") != "stopped":
                self.emit(
                    "previous_run_unclosed",
                    previous_pid=previous.get("pid"),
                    previous_run_id=previous.get("run_id"),
                    previous_last_seen_epoch=previous.get("epoch"),
                    reason="unknown",
                )
        except (OSError, ValueError):
            pass
        self.active = True
        self.emit(
            "started",
            source_hash=source_hash(Path(__file__).parent),
            parent_run_id=os.getenv("PUSH_TO_TALK_PARENT_RUN_ID", ""),
            **fields,
        )
        self.checkpoint(**fields)

    def heartbeat(self, *, force: bool = False, **fields) -> None:
        now = time.monotonic_ns()
        if not self.active or (not force and now - self.last_heartbeat_ns < 5_000_000_000):
            return
        old = self.last_heartbeat_ns
        self.last_heartbeat_ns = now
        self.checkpoint(**fields)
        if force or old == 0 or now // 30_000_000_000 != old // 30_000_000_000:
            self.emit("heartbeat", **(fields | {"diagnostic_write_failures": self.failures}))

    def end(self, reason: str, exit_code: int = 0) -> None:
        if not self.active:
            return
        self.emit("stopped", reason=reason, exit_code=exit_code)
        self.checkpoint(reason=reason, exit_code=exit_code)
        try:
            entry = json.loads(self.state_path.read_text(encoding="utf-8"))
            entry["event"] = "stopped"
            temporary = self.root / f".{self.component}.{os.getpid()}.tmp"
            temporary.write_text(json.dumps(entry), encoding="utf-8")
            temporary.replace(self.state_path)
        except (OSError, ValueError):
            self.failures += 1
        self.active = False


def app_health(root: Path, expected_pid: int | None = None) -> dict:
    try:
        record = json.loads((root / "app.health.json").read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("Invalid health record")
        pid = record.get("pid")
        if expected_pid is not None and pid != expected_pid:
            return {"app_health_available": False, "readiness": "unknown"}
        age = max(0.0, time.time() - float(record["epoch"]))
        fresh = age < 20 and record.get("event") != "stopped"
        if type(pid) is not int:
            raise ValueError("Invalid PID")
        fields = {
            key: value
            for key, value in safe_fields(record).items()
            if key in BOOLEANS | {"transcriptions", "postprocessing", "session_count", "readiness"}
        }
        return fields | {
            "app_pid": pid,
            "app_health_available": True,
            "app_health_fresh": fresh,
            "health_age_s": round(age, 1),
            "readiness": fields.get("readiness", "unknown") if fresh else "stale",
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"app_health_available": False, "readiness": "unknown"}


def enable_native_trace(root: Path):
    """faulthandler writes stack locations only, not source lines/locals/messages."""
    if faulthandler.is_enabled():
        return None
    handle = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        path = root / "native-stacks.log"
        rotate_file(path, 2 * 1024 * 1024, 2)
        handle = path.open("a", encoding="utf-8")
        faulthandler.enable(file=handle, all_threads=True)
        return handle
    except (OSError, RuntimeError):
        if handle:
            handle.close()
        return None


def close_native_trace(handle) -> None:
    if handle is not None:
        faulthandler.disable()
        handle.close()
