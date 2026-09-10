from unittest.mock import Mock

import pytest

import push_to_talk_realtime as app
from cursor_indicator import indicator_frame, render_indicator_image
from recording_modes import PASTE_EVENT_TAG, PasteCycleFilter


@pytest.fixture
def session(monkeypatch):
    state = app.SessionState()
    monkeypatch.setattr(app, "state", state)
    monkeypatch.setattr(app, "update_tray_status", lambda *_: None)
    monkeypatch.setattr(app.threading, "Thread", Mock())
    return state


def begin():
    return app.begin_session_start("dictation", "F13", "keyboard", ("F13",), None, "Default")


def test_cycle_during_start_and_capture_then_reset(session):
    session.recording_rewrite_mode = "fun"
    assert begin()
    assert session.recording_rewrite_mode == "raw"
    assert app.cycle_recording_mode()
    assert session.recording_rewrite_mode == "tidy"
    active = app.activate_session("dictation", "F13", "keyboard", ("F13",), "Default")
    assert session.recording_rewrite_mode == "tidy"
    assert app.cycle_recording_mode()
    assert session.recording_rewrite_mode == "fun"
    assert app.cycle_recording_mode()
    assert session.recording_rewrite_mode == "raw"
    app.cycle_recording_mode()
    session.should_stop = True
    assert not app.cycle_recording_mode()
    result = app.finish_capture_session(active.session_id)
    assert result.rewrite_mode == "tidy"
    assert begin()
    assert session.recording_rewrite_mode == "raw"
    assert result.rewrite_mode == "tidy"


def test_idle_and_released_pending_session_do_not_cycle(session):
    assert not app.cycle_recording_mode()
    begin()
    session.pending_start_stop_requested = True
    assert not app.cycle_recording_mode()


def test_chord_consumes_repeats_and_release_even_after_recording_ends():
    cycle = Mock(return_value=True)
    chord = PasteCycleFilter(cycle)
    assert not chord.consume(0x56, True, False)
    assert chord.consume(0x56, True, True)
    assert chord.consume(0x56, True, True)
    cycle.assert_called_once()
    cycle.return_value = False
    assert chord.consume(0x56, False, False)
    assert not chord.consume(0x56, True, True)
    assert not chord.consume(0x56, False, False)


def test_app_generated_paste_and_recording_key_are_never_consumed():
    cycle = Mock(return_value=True)
    chord = PasteCycleFilter(cycle)
    for down in (True, False):
        assert not chord.consume(0x56, down, True, PASTE_EVENT_TAG)
        assert not chord.consume(0x7C, down, True)
    cycle.assert_not_called()


@pytest.mark.parametrize("label", ["Raw", "Tidy", "Fun"])
def test_mode_labels_render_without_clipping(label):
    image = render_indicator_image(indicator_frame(0.7), (230, 40, 70, 255), label=label)
    unlabeled = render_indicator_image(indicator_frame(0.7), (230, 40, 70, 255))
    assert image.tobytes() != unlabeled.tobytes()
    left, top, right, bottom = image.getbbox()
    assert 0 < left < right < image.width
    assert 0 < top < bottom < image.height


@pytest.mark.parametrize("profile", ["clean_up", "fun"])
@pytest.mark.parametrize("failure", [None, "archive", "instructions"])
def test_raw_archived_before_rewrite_even_when_legacy_log_disabled(
    session, monkeypatch, profile, failure
):
    events = []
    session.dictation_history_enabled = False
    monkeypatch.setattr(app, "transcribe_audio", lambda *_: "original words")
    monkeypatch.setattr(app, "mark_transcription_started", lambda **_: None)
    monkeypatch.setattr(app, "mark_post_processing_started", lambda: None)
    monkeypatch.setattr(app, "mark_post_processing_finished", lambda: None)
    monkeypatch.setattr(app, "log", lambda *_: None)
    monkeypatch.setattr(app, "apply_punctuation_options", lambda text: text)
    monkeypatch.setattr(
        app,
        "archive_raw_transcript",
        lambda **kw: events.append(("raw", kw["raw_text"]))
        or (None if failure == "archive" else 1),
    )
    if failure == "instructions":
        monkeypatch.setattr(
            app, "post_process_instructions", Mock(side_effect=OSError("unreadable instructions"))
        )
    monkeypatch.setattr(
        app,
        "post_process_transcript",
        lambda text, *_: events.append(("rewrite", text)) or "rewritten words",
    )
    monkeypatch.setattr(
        app,
        "archive_final_transcript",
        lambda entry, **kw: events.append(("final", kw["final_text"])),
    )
    result = app.finalize_session_transcription(
        chunks=[],
        mode="dictation",
        audio_source="microphone",
        transcription_engine=app.TRANSCRIPTION_ENGINE_RECORDED,
        recorded_model="gpt-transcribe",
        post_processing_enabled=True,
        post_process_model="gpt-5.6-luna",
        post_process_instruction_profile=profile,
        realtime_worker=None,
        realtime_stop_event=None,
        realtime_cancel_event=None,
        realtime_result={},
    )
    if failure:
        assert result.final_text == "original words"
        assert events == [("raw", "original words"), ("final", "original words")]
    else:
        assert result.final_text == "rewritten words"
        assert events == [
            ("raw", "original words"),
            ("rewrite", "original words"),
            ("final", "rewritten words"),
        ]
