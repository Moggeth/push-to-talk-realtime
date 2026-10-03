import math
import sqlite3
from dataclasses import replace

import pytest

from cursor_indicator import (
    CursorIndicatorSnapshot,
    IndicatorAnimator,
    JobView,
    render_indicator_image,
)
from transcription_progress import DAY, MAX_SAMPLES, TimingEstimator, estimated_progress


def trained(key="recorded:model", audio=30, elapsed=4, count=12, now=100 * DAY):
    estimator = TimingEstimator()
    for i in range(count):
        estimator.observe(key, audio, elapsed, now=now - i)
    return estimator


def test_cold_start_model_isolation_and_unfamiliar_lengths():
    estimator = trained(count=7)
    assert estimator.predict("recorded:model", 30, now=100 * DAY) is None
    estimator.observe("recorded:model", 30, 4, now=100 * DAY)
    assert estimator.predict("recorded:model", 30, now=100 * DAY) == 4
    assert estimator.predict("live:model", 30, now=100 * DAY) is None
    assert estimator.predict("recorded:new", 30, now=100 * DAY) is None
    assert estimator.predict("recorded:model", 300, now=100 * DAY) is None


def test_length_sensitive_without_linear_scaling_assumption():
    estimator = trained(audio=10, elapsed=3)
    for i in range(12):
        estimator.observe("recorded:model", 120, 9, now=100 * DAY - i)
    assert estimator.predict("recorded:model", 12, now=100 * DAY) == 3
    assert estimator.predict("recorded:model", 125, now=100 * DAY) == 9


def test_outlier_does_not_dominate_but_unpredictable_history_declines_estimate():
    estimator = trained()
    estimator.observe("recorded:model", 30, 200, now=100 * DAY)
    assert estimator.predict("recorded:model", 30, now=100 * DAY) == 4
    for _ in range(12):
        estimator.observe("recorded:model", 30, 100, now=100 * DAY)
    assert estimator.predict("recorded:model", 30, now=100 * DAY) is None


def test_recency_and_expiration():
    estimator = trained(now=20 * DAY)
    for i in range(12):
        estimator.observe("recorded:model", 30, 7, now=100 * DAY - i)
    assert estimator.predict("recorded:model", 30, now=100 * DAY) == 7
    assert estimator.predict("recorded:model", 30, now=191 * DAY) is None


def test_neighbor_limit_prefers_recent_not_fastest_identical_lengths():
    estimator = trained(count=80, elapsed=1, now=99 * DAY)
    for i in range(40):
        estimator.observe("recorded:model", 30, 7, now=100 * DAY - i)
    assert estimator.predict("recorded:model", 30, now=100 * DAY) == 7


@pytest.mark.parametrize("invalid", [0, -1, math.nan, math.inf])
def test_invalid_durations_do_not_train(invalid):
    estimator = TimingEstimator()
    estimator.observe("m", invalid, 2)
    estimator.observe("m", 2, invalid)
    assert not estimator._samples
    assert estimator.predict("m", invalid) is None


def test_progress_monotonic_and_never_complete_even_on_extreme_overrun():
    values = [estimated_progress(10, 4, t) for t in (9, 10, 11, 14, 30, 10000)]
    assert values == sorted(values)
    assert values[3] == pytest.approx(0.85, abs=0.002)
    assert values[-1] < 1
    assert estimated_progress(10, 0, 12) is None


def test_bounded_memory():
    estimator = trained(count=MAX_SAMPLES + 20)
    assert len(estimator._samples) == MAX_SAMPLES


def test_persistence_roundtrip_and_bounded_storage(tmp_path):
    path = tmp_path / "timings.db"
    estimator = TimingEstimator()
    estimator.start(path)
    for _ in range(12):
        estimator.observe("recorded:model", 30, 4)
    estimator.close()
    assert not estimator._worker.is_alive()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM timings").fetchone()[0] == 12
        # No transcript/audio payload or credentials are stored.
        assert [row[1] for row in db.execute("PRAGMA table_info(timings)")] == [
            "key",
            "audio",
            "elapsed",
            "at",
        ]
    restored = TimingEstimator()
    restored.start(path)
    restored.close()
    assert restored.predict("recorded:model", 30) == 4


def test_corrupt_storage_is_nonfatal(tmp_path, caplog):
    path = tmp_path / "timings.db"
    path.write_bytes(b"not a database")
    estimator = TimingEstimator()
    estimator.start(path)
    estimator._worker.join(timeout=2)
    estimator.observe("m", 10, 2)
    assert len(estimator._samples) == 1
    assert "dictation unaffected" in caplog.text


@pytest.mark.parametrize("mode", ["raw", "tidy", "fun"])
def test_primary_progress_grows_preserving_traveler_and_renders(mode):
    snapshot = CursorIndicatorSnapshot(
        True,
        (255, 165, 0, 255),
        activity="transcribing",
        mode=mode,
        jobs=(JobView(1, mode=mode, started_at=0, expected_s=4),),
    )
    animator = IndicatorAnimator()
    baseline = IndicatorAnimator()
    frames = []
    for now in (0, 1, 2, 4, 10):
        visual = animator.update(snapshot, now)
        original = baseline.update(replace(snapshot, jobs=()), now)
        assert (visual.frame.arc_start + visual.frame.arc_extent) % 360 == pytest.approx(
            (original.frame.arc_start + original.frame.arc_extent) % 360
        )
        frames.append(visual.frame.arc_extent)
    assert frames == sorted(frames)
    assert frames[-1] < 360
    image = render_indicator_image(visual.frame, visual.color, mode=mode)
    assert image.getbbox() is not None


def test_overlap_tracks_oldest_background_independently_of_recording():
    snapshot = CursorIndicatorSnapshot(
        True,
        (220, 53, 69, 255),
        activity="recording",
        jobs=(JobView(1, started_at=0, expected_s=4), JobView(2, started_at=2, expected_s=9)),
    )
    animator = IndicatorAnimator()
    animator.update(snapshot, 0)
    visual = animator.update(snapshot, 4)
    assert visual.orbits[0].extent == pytest.approx(64 + 286 * estimated_progress(0, 4, 4))
    assert not visual.frame.estimated
    assert visual.orbits[0].queued == 1
    assert JobView(1, "rewriting", expected_s=4).progress(4) is None


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("text", ["", "raw words"])
def test_stage_measurement_excludes_rewrite_and_empty_results(monkeypatch, live, text):
    from unittest.mock import Mock

    import numpy as np

    import push_to_talk_realtime as app

    clock = [100.0]
    estimator = Mock()
    estimator.predict.return_value = 4
    monkeypatch.setattr(app, "TRANSCRIPTION_TIMINGS", estimator)
    monkeypatch.setattr(app.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "log", lambda *_: None)
    for name in (
        "mark_transcription_started",
        "mark_post_processing_started",
        "mark_post_processing_finished",
        "archive_final_transcript",
    ):
        monkeypatch.setattr(app, name, lambda *a, **k: None)
    monkeypatch.setattr(app, "archive_raw_transcript", lambda **k: 1)
    monkeypatch.setattr(app, "apply_punctuation_options", lambda t: t)

    def transcribe(*_):
        clock[0] += 3
        return text

    def rewrite(*_):
        clock[0] += 20
        return "processed"

    monkeypatch.setattr(app, "transcribe_audio", transcribe)
    monkeypatch.setattr(app, "post_process_transcript", rewrite)
    worker = Mock()
    worker.join.side_effect = lambda **k: transcribe()
    worker.is_alive.return_value = False
    app.finalize_session_transcription(
        chunks=[np.zeros(app.SAMPLE_RATE)],
        mode="dictation",
        audio_source="microphone",
        transcription_engine=app.TRANSCRIPTION_ENGINE_LIVE
        if live
        else app.TRANSCRIPTION_ENGINE_RECORDED,
        recorded_model="gpt-transcribe",
        post_processing_enabled=True,
        post_process_model="gpt-6.1-sol",
        post_process_instruction_profile="clean_up",
        rewrite_instructions="tidy",
        realtime_worker=worker if live else None,
        realtime_stop_event=Mock() if live else None,
        realtime_cancel_event=None,
        realtime_result={"text": text},
        session_id=1,
    )
    if text:
        key, audio, elapsed = estimator.observe.call_args.args
        assert audio == 1
        assert elapsed == 3
        assert key.endswith(app.LIVE_TRANSCRIBE_MODEL if live else "gpt-transcribe")
    else:
        estimator.observe.assert_not_called()
