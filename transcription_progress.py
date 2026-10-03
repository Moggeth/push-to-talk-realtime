"""Local, metadata-only latency learning; no disk work on capture/render threads."""

from __future__ import annotations

import logging
import math
import queue
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

DAY = 86400
MAX_SAMPLES = 512


@dataclass(frozen=True)
class Sample:
    key: str
    audio_s: float
    elapsed_s: float
    at: float


def estimated_progress(started_at: float, expected_s: float, now: float) -> float | None:
    if expected_s <= 0:
        return None
    elapsed = max(0.0, now - started_at)
    # 85% at the estimate; an outstanding request never paints a complete ring.
    return 0.97 * (1 - math.exp(-2.09 * elapsed / expected_s))


class TimingEstimator:
    def __init__(self):
        self._samples: deque[Sample] = deque(maxlen=MAX_SAMPLES)
        self._lock = threading.Lock()
        self._queue: queue.Queue[Sample | None] = queue.Queue(maxsize=MAX_SAMPLES)
        self._worker: threading.Thread | None = None

    def predict(self, key: str, audio_s: float, *, now: float | None = None) -> float | None:
        if not math.isfinite(audio_s) or audio_s <= 0:
            return None
        now = time.time() if now is None else now
        with self._lock:
            samples = list(self._samples)
        neighbors = []
        for sample in samples:
            age = now - sample.at
            distance = abs(math.log((audio_s + 5) / (sample.audio_s + 5)))
            if sample.key == key and 0 <= age <= 90 * DAY and distance <= math.log(2):
                weight = math.exp(-3 * distance) * 0.5 ** (age / (14 * DAY))
                neighbors.append((distance, sample.elapsed_s, weight))
        neighbors = sorted(neighbors, key=lambda row: (row[0], -row[2]))[:40]
        if len(neighbors) < 8:
            return None
        values = sorted((elapsed, weight) for _, elapsed, weight in neighbors)
        total = sum(weight for _, weight in values)
        effective_n = total**2 / sum(weight**2 for _, weight in values)
        if effective_n < 6:
            return None

        def quantile(fraction):
            cumulative = 0.0
            for elapsed, weight in values:
                cumulative += weight
                if cumulative >= total * fraction:
                    return elapsed
            return values[-1][0]

        if quantile(0.9) > 4 * quantile(0.1):
            return None
        return max(0.05, quantile(0.7))

    def observe(self, key: str, audio_s: float, elapsed_s: float, *, now=None):
        if not all(math.isfinite(v) and v > 0 for v in (audio_s, elapsed_s)):
            return
        sample = Sample(key, audio_s, elapsed_s, time.time() if now is None else now)
        with self._lock:
            self._samples.append(sample)
        if self._worker is not None:
            try:
                self._queue.put_nowait(sample)
            except queue.Full:
                logging.getLogger(__name__).warning("Timing persistence queue full; sample skipped")

    def start(self, path: Path):
        if self._worker is not None:
            return
        self._worker = threading.Thread(target=self._persist, args=(path,), daemon=True)
        self._worker.start()

    def close(self):
        if self._worker is not None:
            try:
                self._queue.put(None, timeout=0.1)
            except queue.Full:
                return
            self._worker.join(timeout=0.5)

    def _persist(self, path):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(path, timeout=0.2) as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS timings "
                    "(key TEXT, audio REAL, elapsed REAL, at REAL)"
                )
                db.execute("DELETE FROM timings WHERE at < ?", (time.time() - 90 * DAY,))
                db.commit()
                rows = db.execute(
                    "SELECT key,audio,elapsed,at FROM timings ORDER BY rowid DESC LIMIT ?",
                    (MAX_SAMPLES,),
                ).fetchall()
                loaded = []
                for key, audio, elapsed, at in reversed(rows):
                    if isinstance(key, str) and all(
                        isinstance(v, (int, float)) and math.isfinite(v) and v > 0
                        for v in (audio, elapsed, at)
                    ):
                        loaded.append(Sample(key, audio, elapsed, at))
                with self._lock:
                    self._samples = deque([*loaded, *self._samples], maxlen=MAX_SAMPLES)
                while True:
                    sample = self._queue.get()
                    if sample is None:
                        break
                    db.execute(
                        "INSERT INTO timings VALUES (?,?,?,?)",
                        (sample.key, sample.audio_s, sample.elapsed_s, sample.at),
                    )
                    db.execute(
                        "DELETE FROM timings WHERE at < ? OR rowid NOT IN "
                        "(SELECT rowid FROM timings ORDER BY rowid DESC LIMIT ?)",
                        (time.time() - 90 * DAY, MAX_SAMPLES),
                    )
                    db.commit()
        except Exception:
            logging.getLogger(__name__).exception(
                "Timing history unavailable; dictation unaffected"
            )
