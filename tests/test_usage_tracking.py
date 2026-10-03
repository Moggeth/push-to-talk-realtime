import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

from transcription_engines import RecordedTranscriptionConfig, transcribe_recording
from usage_tracking import UsageMeter, UsageStore, estimate


@pytest.mark.parametrize(
    "model,cost", [("gpt-transcribe", 4500000), ("gpt-live-transcribe", 17000000)]
)
def test_duration(model, cost):
    assert estimate(model, 60, {}, True)[0] == cost
    assert estimate(model, 60, {}, False)[0] is None
    assert estimate(model, float("nan"), {}, True)[0] is None


def test_token_rates_and_cache():
    usage = {
        "input_tokens": 1000,
        "output_tokens": 100,
        "input_tokens_details": {"cached_tokens": 500},
    }
    assert estimate("gpt-5.6-terra", 0, usage, True)[0] == 2300000
    assert estimate("unlisted-model", 0, usage, True)[0] is None
    usage["input_tokens_details"]["cached_tokens"] = 1001
    assert estimate("gpt-5.6-terra", 0, usage, True)[0] is None
    assert estimate("gpt-5.6-terra", 0, {}, True)[0] is None


def test_report_preserves_pending_and_idempotence(tmp_path):
    store = UsageStore(tmp_path / "usage.db")
    event = store.begin("gpt-transcribe", "transcription")
    store.finish(event, "gpt-transcribe", 60, {}, True)
    store.finish(event, "gpt-transcribe", 600, {}, True)
    store.begin("gpt-live-transcribe", "live transcription")
    report = store.report(datetime.now().strftime("%Y-%m"))
    assert "US$0.0045" in report
    assert "failed requests: 1" in report
    assert "No requests recorded" not in report
    assert "US$0.0000" in store.report("2000-01")
    with pytest.raises(ValueError):
        store.report("2026-1")


def test_concurrent_requests(tmp_path):
    store = UsageStore(tmp_path / "usage.db")

    def record(_):
        event = store.begin("gpt-transcribe", "transcription")
        store.finish(event, "gpt-transcribe", 60, {}, True)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(record, range(20)))
    assert "US$0.0900" in store.report(datetime.now().strftime("%Y-%m"))


def test_ledger_failure_does_not_block_or_swallow(monkeypatch, tmp_path):
    monkeypatch.setenv("PUSH_TO_TALK_USAGE_DB_PATH", str(tmp_path / "usage.db"))
    monkeypatch.setattr(UsageStore, "begin", lambda *a: (_ for _ in ()).throw(OSError("locked")))
    with UsageMeter("gpt-transcribe", "transcription"):
        pass
    with pytest.raises(ValueError, match="network"), UsageMeter("gpt-transcribe", "transcription"):
        raise ValueError("network")


def test_recorded_engine_records_only_metadata(monkeypatch, tmp_path):
    path = tmp_path / "usage.db"
    monkeypatch.setenv("PUSH_TO_TALK_USAGE_DB_PATH", str(path))
    client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(text="private synthetic words", usage=None)
            )
        )
    )
    text = transcribe_recording(
        [np.zeros(16000, dtype=np.int16)],
        RecordedTranscriptionConfig("gpt-transcribe", "private prompt", 16000, 1),
        client,
    )
    assert text == "private synthetic words"
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT seconds,cost_nano,status FROM usage_events").fetchone()
        assert row == (1.0, 75000, "completed")
        assert "private" not in str(list(db.iterdump()))


def test_cancelled_live_is_unknown(monkeypatch, tmp_path):
    path = tmp_path / "usage.db"
    monkeypatch.setenv("PUSH_TO_TALK_USAGE_DB_PATH", str(path))
    with UsageMeter("gpt-live-transcribe", "live transcription", completed=False) as meter:
        meter.seconds = 12
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status,cost_nano FROM usage_events").fetchone() == (
            "unknown",
            None,
        )
