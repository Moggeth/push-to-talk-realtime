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

    def _read(self, process, outgoing):
        try:
            for line in process.stdout:
                response = json.loads(line)
                if response.get("error"):
                    self.log("[Review] helper_error", response["error"])
                if response.get("event") == "review_visible":
                    self.log(
                        "[Review] visible",
                        bool(response.get("replace_available")),
                        bool(response.get("mapped")),
                    )
                with self.lock:
                    waiter = self.pending.get(response.get("id"))
                if waiter is not None:
                    waiter.set()
        except (OSError, ValueError):
            self.log("[Review] helper_response_failed")
        finally:
            with suppress(queue.Full):
                outgoing.put_nowait(None)
            if process.poll() not in (None, 0):
                self.log("[Review] helper_exited", process.returncode)

    def _send(self, message):
        try:
            self.outgoing.put_nowait(message)
            return True
        except queue.Full:
            self.log("[Review] helper_queue_full")
            return False

    def capture(self, target):
        if not self.start():
            return None
        with self.lock:
            self.sequence += 1
            token = self.sequence
            waiter = self.pending[token] = threading.Event()
        self._send(
            {
                "command": "capture",
                "id": token,
                "target": asdict(target) if target is not None else None,
            }
        )
        # Slow or unresponsive accessibility providers must never block dictation.
        ready = waiter.wait(0.25)
        with self.lock:
            self.pending.pop(token, None)
        if not ready:
            self.log("[Review] capture_timeout")
            self.close(wait=False)
            return None
        return token

    def show(self, raw, processed, token=None, pasted=False):
        if not raw.strip() or raw == processed or not self.start():
            return
        self._send(
            {"command": "show", "id": token, "raw": raw, "processed": processed, "pasted": pasted}
        )

    def dismiss(self):
        if self.process is not None and self.process.poll() is None:
            self._send({"command": "dismiss"})

    def close(self, *, wait=True):
        self.dismiss()
        if self.process is not None and self.process.poll() is None:
            # This helper owns no capture, API request or persistent state.
            try:
                self.process.terminate()
                if wait:
                    self.process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                pass
