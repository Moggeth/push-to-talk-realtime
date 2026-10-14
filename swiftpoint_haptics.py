"""Optional X1 API feedback, isolated from recording and gesture threads."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

PIPE_PATH = r"\\.\pipe\swiftpoint.x1.v2.command"


class BulletHaptics:
    def __init__(self):
        self._busy = threading.Lock()

    def notify(self, enabled: bool) -> None:
        if sys.platform != "win32" or not self._busy.acquire(blocking=False):
            return
        try:
            threading.Thread(target=self._send, args=(enabled,), daemon=True).start()
        except Exception:
            self._busy.release()
            logging.getLogger(__name__).debug("Haptic worker unavailable", exc_info=True)

    def _send(self, enabled: bool) -> None:
        try:
            # A helper process bounds even a stalled native pipe read. No permanent
            # process, queue, retries, or device polling is needed for rare toggles.
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "on" if enabled else "off"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
            if result.returncode:
                logging.getLogger(__name__).debug("X1 haptics unavailable (enable X1 API)")
        except Exception:
            logging.getLogger(__name__).debug("X1 haptic request failed", exc_info=True)
        finally:
            self._busy.release()


def send_pulse(enabled: bool) -> bool:
    command = b"Vibrate 45 65\n" if enabled else b"Vibrate 90 40\n"
    pipe = os.open(PIPE_PATH, os.O_RDWR | os.O_BINARY)
    try:
        if os.write(pipe, command) != len(command):
            return False
        return os.read(pipe, 1024).strip() == b"OK"
    finally:
        os.close(pipe)


if __name__ == "__main__":
    try:
        success = sys.platform == "win32" and send_pulse(sys.argv[1] == "on")
    except (OSError, IndexError):
        success = False
    raise SystemExit(0 if success else 1)
