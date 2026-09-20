import threading
from unittest.mock import Mock

import pytest

import push_to_talk_realtime as app


@pytest.mark.parametrize(
    "text,error,expected",
    [
        ("Hello", None, "success"),
        ("", None, ""),
        ("", RuntimeError("offline"), "error"),
    ],
)
@pytest.mark.parametrize("recording", [False, True])
def test_delivery_feedback_tracks_outcome_without_interrupting_recording(
    monkeypatch,
    text,
    error,
    expected,
    recording,
):
    state = app.SessionState(is_listening=recording)
    monkeypatch.setattr(app, "state", state)
    monkeypatch.setattr(app, "shutdown_event", threading.Event())
    monkeypatch.setattr(app, "wait_for_output_turn", lambda _: True)
    monkeypatch.setattr(app, "advance_output_turn", Mock())
    monkeypatch.setattr(app, "mark_transcription_finished", Mock())
    monkeypatch.setattr(app, "append_dictation_history_entry", Mock())
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(app, "PASTE_ON_RELEASE", False)
    app.deliver_session_output(
        session_id=1,
        mode=app.MODE_DICTATION,
        outcome=app.TranscriptionOutcome(
            final_text=text,
            error=error,
            engine_used=app.TRANSCRIPTION_ENGINE_LIVE,
            transcription_ms=20,
            audio_duration_s=1,
        ),
        recorded_model="gpt-transcribe",
        paste_target=None,
        live_typing_enabled=False,
        realtime_delta_parts=[],
        realtime_delta_lock=threading.Lock(),
    )
    assert state.indicator_result == ("" if recording else expected)
