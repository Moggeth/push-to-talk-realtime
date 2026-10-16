"""Isolated, bounded IPC for the optional rewrite comparison UI."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path


class ReviewLifetime:
    def __init__(self, now: float):
        self.created = now
        self.fade_at = now + 5.0
        self.hovered = False

    def hover(self, inside: bool, now: float):
        if inside:
            self.hovered = True
        elif self.hovered:
            self.hovered = False
            self.fade_at = now

    def opacity(self, now: float, busy=False) -> float:
        if busy or self.hovered:
            return 1.0
        return max(0.0, min(1.0, (now - self.created) / 0.1, 1 - (now - self.fade_at)))


class RewriteReviewManager:
    def __init__(self, log=lambda *_: None):
        self.log = log
        self.process = None
        self.lock = threading.Lock()
        self.outgoing = queue.Queue(maxsize=8)
        self.pending = {}
        self.responses = {}
        self.context_diagnostics = {}
        self.sequence = 0

    def start(self):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                return True
            try:
                self.process = subprocess.Popen(
                    [sys.executable, str(Path(__file__).with_name("rewrite_review_window.py"))],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self.outgoing = queue.Queue(maxsize=8)
                threading.Thread(
                    target=self._write, args=(self.process, self.outgoing), daemon=True
                ).start()
                threading.Thread(
                    target=self._read, args=(self.process, self.outgoing), daemon=True
                ).start()
                return True
            except Exception as exc:
                process, self.process = self.process, None
                with suppress(queue.Full):
                    self.outgoing.put_nowait(None)
                if process is not None:
                    with suppress(OSError):
                        process.terminate()
                self.log("[Review] helper_start_failed", type(exc).__name__)
                return False

    def _write(self, process, outgoing):
        try:
            while True:
                message = outgoing.get()
                if message is None:
                    process.stdin.close()
                    return
                process.stdin.write(json.dumps(message, ensure_ascii=True) + "\n")
                process.stdin.flush()
        except (OSError, ValueError):
            self.log("[Review] helper_pipe_closed")
            self.close(wait=False, expected_process=process)
        finally:
            with suppress(OSError, ValueError):
                process.stdin.close()

    def _read(self, process, outgoing):
        try:
            for line in process.stdout:
                response = json.loads(line)
                if not isinstance(response, dict) or (
                    response.get("id") is not None and type(response["id"]) is not int
                ):
                    raise ValueError("invalid_helper_response")
                if response.get("error"):
                    self.log("[Review] helper_error", response["error"])
                if response.get("event") == "review_visible":
                    self.log(
                        "[Review] visible",
                        bool(response.get("replace_available")),
                        bool(response.get("mapped")),
                    )
                with self.lock:
                    waiter = (
                        self.pending.get(response.get("id")) if self.process is process else None
                    )
                    if waiter is not None:
                        self.responses[response["id"]] = response
                        waiter.set()
        except (OSError, ValueError):
            self.log("[Review] helper_response_failed")
        finally:
            self.close(wait=False, expected_process=process)
            with suppress(queue.Full):
                outgoing.put_nowait(None)
            with suppress(OSError, ValueError):
                process.stdout.close()
            if process.poll() not in (None, 0):
                self.log("[Review] helper_exited", process.returncode)

    def _send(self, message, *, expected_process=None):
        try:
            with self.lock:
                if expected_process is not None and self.process is not expected_process:
                    return False
                self.outgoing.put_nowait(message)
            return True
        except queue.Full:
            self.log("[Review] helper_queue_full")
            return False

    def capture(self, target):
        if not self.start():
            return None
        with self.lock:
            process = self.process
            if process is None:
                return None
            self.sequence += 1
            token = self.sequence
            waiter = self.pending[token] = threading.Event()
        sent = self._send(
            {
                "command": "capture",
                "id": token,
                "target": asdict(target) if target is not None else None,
            },
            expected_process=process,
        )
        # Slow or unresponsive accessibility providers must never block dictation.
        ready = sent and waiter.wait(0.25)
        with self.lock:
            self.pending.pop(token, None)
            self.responses.pop(token, None)
            ready = ready and self.process is process
        if not ready:
            self.log("[Review] capture_timeout")
            self.close(wait=False, expected_process=process)
            return None
        return token

    def caret_context(self, target):
        self.context_diagnostics = {"context_status": "unavailable"}
        if target is None or not self.start():
            return None
        with self.lock:
            process = self.process
            if process is None:
                return None
            self.sequence += 1
            token = self.sequence
            waiter = self.pending[token] = threading.Event()
        sent = self._send(
            {"command": "context", "id": token, "target": asdict(target)},
            expected_process=process,
        )
        ready = sent and waiter.wait(0.25)
        with self.lock:
            self.pending.pop(token, None)
            response = self.responses.pop(token, {})
            ready = ready and self.process is process
        if not ready:
            self.context_diagnostics = {"context_status": "timeout"}
            self.close(wait=False, expected_process=process)
            return None
        from runtime_diagnostics import safe_fields

        metadata = response.get("context_diagnostics", {})
        self.context_diagnostics = safe_fields(metadata) if isinstance(metadata, dict) else {}
        context = response.get("context")
        if not isinstance(context, dict):
            return None
        from insertion_formatting import CaretContext

        before, after = context.get("before"), context.get("after")
        if not isinstance(before, str) or not isinstance(after, str):
            self.context_diagnostics = {"context_status": "invalid_response"}
            return None
        if len(before) > 256 or len(after) > 256:
            self.context_diagnostics = {"context_status": "invalid_response"}
            return None
        return CaretContext(before, after)

    def show(self, raw, processed, token=None, pasted=False):
        if not raw.strip() or raw == processed or not self.start():
            return
        self._send(
            {"command": "show", "id": token, "raw": raw, "processed": processed, "pasted": pasted}
        )

    def dismiss(self):
        with self.lock:
            process = self.process
            running = process is not None and process.poll() is None
        if running:
            self._send({"command": "dismiss"}, expected_process=process)

    def close(self, *, wait=True, expected_process=None):
        with self.lock:
            process = self.process
            if expected_process is not None and process is not expected_process:
                return
            self.process = None
            with suppress(queue.Full):
                self.outgoing.put_nowait(None)
            for waiter in self.pending.values():
                waiter.set()
        if process is not None and process.poll() is None:
            # This helper owns no capture, API request or persistent state.
            try:
                process.terminate()
                if wait:
                    process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                pass
