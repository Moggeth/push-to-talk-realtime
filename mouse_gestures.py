"""Passive, recording-gated mouse gestures. Never suppress or inject input."""

from __future__ import annotations

import threading
import time


class VerticalShake:
    def __init__(self):
        self.reset()

    def reset(self):
        self.origin = None
        self.direction = 0
        self.legs = 0
        self.started = 0.0
        self.extreme = 0.0
        self.latched = False
        self.last = None
        self.quiet_since = 0.0

    def feed(self, x, y, now):
        if self.latched:
            if self.last is None or abs(y - self.last[1]) + abs(x - self.last[0]) > 3:
                self.quiet_since = now
            self.last = (x, y)
            if now - self.quiet_since < 0.3 or now - self.started < 1.5:
                return False
            self.reset()
        if (
            self.origin is None
            or (self.direction and now - self.started > 0.9)
            or abs(x - self.origin[0]) > 45
        ):
            self.origin = (x, y)
            self.extreme = y
            self.started = now
            self.direction = self.legs = 0
            return False
        if not self.direction:
            distance = y - self.extreme
            if abs(distance) >= 45:
                self.started = now
                self.direction = 1 if distance > 0 else -1
                self.extreme = y
                self.legs = 1
        elif (y - self.extreme) * self.direction > 0:
            self.extreme = y
        elif (y - self.extreme) * self.direction <= -45:
            self.direction *= -1
            self.extreme = y
            self.legs += 1
        if self.legs >= 4 and now - self.started >= 0.18:
            self.latched = True
            self.quiet_since = self.started = now
            self.last = (x, y)
            return True
        return False


class GestureMonitor:
    def __init__(self, active_token, toggle, log, position=None):
        self.active_token = active_token
        self.toggle = toggle
        self.log = log
        self.position = position
        self.stop_event = threading.Event()
        self.thread = None
        self.detector = VerticalShake()
        self.token = None

    def poll(self, now):
        token = self.active_token()
        if token != self.token or token is None:
            self.detector.reset()
            self.token = token
        if token is None:
            return False
        if self.position is None:
            from pynput.mouse import Controller

            controller = Controller()
            self.position = lambda: controller.position
        x, y = self.position()
        if self.detector.feed(x, y, now):
            self.toggle(token)
        return True

    def _run(self):
        while not self.stop_event.is_set():
            delay = 0.1
            try:
                if self.poll(time.monotonic()):
                    delay = 1 / 60
            except Exception as exc:
                self.detector.reset()
                self.log("[Gesture] Mouse sampling unavailable; retrying:", exc)
                delay = 10
            self.stop_event.wait(delay)

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name="mouse-gesture")
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=0.5)
