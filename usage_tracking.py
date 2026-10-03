"""Content-free local usage ledger; billing estimates never control dictation."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from runtime_paths import resolve_runtime_paths

PRICE_DATE = "2026-10-03"
PRICE_SOURCE = "https://developers.openai.com/api/docs/pricing"
MINUTE_RATES = {"gpt-transcribe": 0.0045, "gpt-live-transcribe": 0.017}
TOKEN_RATES = {
    "gpt-6.1-sol": (2.0, 0.10, 10.0),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.6-terra": (2.0, 0.20, 12.0),
    "gpt-5.6-sol": (4.0, 0.40, 20.0),
}
_schema_lock = threading.Lock()
_initialized_paths: set[Path] = set()


def usage_path() -> Path:
    return Path(
        os.getenv("PUSH_TO_TALK_USAGE_DB_PATH") or resolve_runtime_paths().log.parent / "usage.db"
    )


def usage_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if callable(getattr(value, "model_dump", None)):
        result = value.model_dump()
        return result if isinstance(result, dict) else {}
    return {}


def estimate(model: str, seconds: float, usage: dict, completed: bool) -> tuple[int | None, dict]:
    """Return integer USD nanodollars and the exact applied rate snapshot."""
    if not completed:
        return None, {}
    if model in MINUTE_RATES:
        reported = usage.get("seconds") if usage.get("type") == "duration" else None
        if type(reported) not in (int, float):
            reported = None
        duration = reported if isinstance(reported, (int, float)) else seconds
        if not math.isfinite(duration) or duration < 0:
            return None, {}
        rate = MINUTE_RATES[model]
        amount = Decimal(str(duration)) * Decimal(str(rate)) / 60
        return round(amount * 10**9), {
            "per_minute": rate,
            "duration_basis": "reported" if reported is not None else "submitted",
        }
    if model not in TOKEN_RATES:
        return None, {}
    incoming, outgoing = usage.get("input_tokens"), usage.get("output_tokens")
    details = usage_dict(usage.get("input_tokens_details"))
    cached = details.get("cached_tokens", 0)
    if any(type(n) is not int or n < 0 for n in (incoming, outgoing, cached)) or cached > incoming:
        return None, {}
    if details.get("cache_creation_tokens", 0):
        return None, {}
    rates = TOKEN_RATES[model]
    if incoming > 272000:
        rates = (rates[0] * 2, rates[1] * 2, rates[2] * 1.5)
    amount = (
        sum(
            Decimal(str(rate)) * n
            for rate, n in zip(rates, (incoming - cached, cached, outgoing), strict=True)
        )
        / 10**6
    )
    return round(amount * 10**9), {
        "input_per_million": rates[0],
        "cached_per_million": rates[1],
        "output_per_million": rates[2],
    }


class UsageStore:
    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=1.0)
        try:
            db.row_factory = sqlite3.Row
            # WAL's initial mode change can fail immediately during concurrent opens.
            # Serialize initialization, not requests; subsequent connections reuse WAL.
            with _schema_lock:
                if self.path not in _initialized_paths:
                    db.execute("PRAGMA journal_mode=WAL")
                    _initialized_paths.add(self.path)
            db.execute("""CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, month TEXT NOT NULL,
                model TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL,
                seconds REAL NOT NULL DEFAULT 0, input_tokens INTEGER, output_tokens INTEGER,
                cached_tokens INTEGER, cost_nano INTEGER, rates TEXT NOT NULL DEFAULT '{}',
                price_date TEXT NOT NULL, source TEXT NOT NULL)""")
            db.commit()
            return db
        except Exception:
            db.close()
            raise

    def begin(self, model: str, kind: str) -> int:
        now = datetime.now().astimezone()
        with closing(self.connect()) as db, db:
            return db.execute(
                "INSERT INTO usage_events(created_at,month,model,kind,status,price_date,source) VALUES(?,?,?,?,?,?,?)",
                (
                    now.isoformat(timespec="seconds"),
                    now.strftime("%Y-%m"),
                    model,
                    kind,
                    "pending",
                    PRICE_DATE,
                    PRICE_SOURCE,
                ),
            ).lastrowid

    def finish(self, event: int, model: str, seconds: float, usage: dict, completed: bool):
        amount, rates = estimate(model, seconds, usage, completed)

        def count(value):
            return value if type(value) is int and value >= 0 else None

        details = usage_dict(usage.get("input_tokens_details"))
        with closing(self.connect()) as db, db:
            db.execute(
                """UPDATE usage_events SET status=?,seconds=?,input_tokens=?,output_tokens=?,
                cached_tokens=?,cost_nano=?,rates=? WHERE id=? AND status='pending'""",
                (
                    "completed" if completed else "unknown",
                    seconds,
                    count(usage.get("input_tokens")),
                    count(usage.get("output_tokens")),
                    count(details.get("cached_tokens")),
                    amount,
                    json.dumps(rates, sort_keys=True),
                    event,
                ),
            )

    def report(self, month: str) -> str:
        if datetime.strptime(month, "%Y-%m").strftime("%Y-%m") != month:
            raise ValueError("Month must be YYYY-MM")
        with closing(self.connect()) as db:
            rows = db.execute(
                """SELECT model,kind,COUNT(*) requests,SUM(seconds) seconds,
                SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,
                SUM(cost_nano) cost,SUM(cost_nano IS NULL) unknown
                FROM usage_events WHERE month=? GROUP BY model,kind ORDER BY model,kind""",
                (month,),
            ).fetchall()
            started = db.execute("SELECT MIN(created_at) FROM usage_events").fetchone()[0]
        total = sum(row["cost"] or 0 for row in rows) / 10**9
        unknown = sum(row["unknown"] for row in rows)
        lines = [
            f"Push-to-talk | {month}",
            f"Known estimated cost: US${total:.4f}",
            f"Unpriced / pending / failed requests: {unknown}",
            f"Tracking began: {started or 'No requests recorded yet'}",
            "",
        ]
        for row in rows:
            tokens = (
                f"{row['input_tokens']} in / {row['output_tokens']} out tokens"
                if row["input_tokens"] is not None
                else "tokens not reported"
            )
            cost = (
                "unpriced"
                if row["cost"] is None
                else f"US${row['cost'] / 10**9:.4f} known estimate"
            )
            lines.append(
                f"{row['model']} ({row['kind']}): {row['requests']} requests; {row['seconds'] / 60:.2f} min; {tokens}; {cost}; {row['unknown']} unknown"
            )
        live_seconds = sum(row["seconds"] for row in rows if row["model"] == "gpt-live-transcribe")
        if live_seconds:
            savings = (
                live_seconds
                / 60
                * (MINUTE_RATES["gpt-live-transcribe"] - MINUTE_RATES["gpt-transcribe"])
            )
            lines.extend(
                [
                    "",
                    f"Hypothetical: the same live-audio minutes on GPT Transcribe would cost US${savings:.4f} less at current saved rates. Latency/quality differ; this is not a recommendation.",
                ]
            )
        lines.extend(
            [
                "",
                f"USD estimates, not an invoice. Rates checked {PRICE_DATE}.",
                "No tax, exchange rate, credits or provider-side retries included. Unknown usage is not zero.",
                "Earlier months are not backfilled. Deleting transcripts does not delete this content-free ledger.",
                PRICE_SOURCE,
            ]
        )
        return "\n".join(lines)


class UsageMeter:
    def __init__(self, model: str, kind: str, *, completed: bool = True):
        self.model, self.kind = model, kind
        self.completed = completed
        self.seconds = 0.0
        self.usage = {}
        self.event = None
        self.store = UsageStore(usage_path())

    def __enter__(self):
        try:
            self.event = self.store.begin(self.model, self.kind)
        except Exception:
            logging.warning("Usage ledger unavailable; dictation continues", exc_info=True)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.event is not None:
            try:
                self.store.finish(
                    self.event,
                    self.model,
                    self.seconds,
                    usage_dict(self.usage),
                    self.completed and exc_type is None,
                )
            except Exception:
                logging.warning("Usage ledger update failed; entry remains pending", exc_info=True)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default=datetime.now().strftime("%Y-%m"))
    args = parser.parse_args()
    print(UsageStore(usage_path()).report(args.month))
