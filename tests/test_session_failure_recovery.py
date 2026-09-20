import threading
from unittest.mock import Mock

import pytest

import push_to_talk_realtime as app


@pytest.fixture
def state(monkeypatch):
    state = app.SessionState(session_start_pending=True)
    monkeypatch.setattr(app, "state", state)
    monkeypatch.setattr(app, "shutdown_event", threading.Event())
    monkeypatch.setattr(app, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(app, "enforce_transcription_engine_dependencies", Mock())
    monkeypatch.setattr(app, "capture_paste_target", Mock(return_value=None))
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(app, "update_tray_status", Mock())
    return state


def start():
    app.start_listening(app.MODE_DICTATION, "F13", "keyboard", ("F13",), None, "Default")


def test_dependency_error_releases_pending_start(state, monkeypatch):
    monkeypatch.setattr(
        app,
        "enforce_transcription_engine_dependencies",
        Mock(side_effect=RuntimeError("setup failed")),
    )
    start()
    assert not state.session_start_pending
    assert not state.is_listening


@pytest.mark.parametrize("stage", ["build", "start"])
def test_recorder_preparation_exception_releases_capture_and_output(state, monkeypatch, stage):
    recorder = Mock()
    monkeypatch.setattr(
        app,
        "build_session_recorder",
        Mock(
            return_value=(recorder, 0),
            side_effect=RuntimeError("build failed") if stage == "build" else None,
        ),
    )
    monkeypatch.setattr(
        app, "start_recorder_with_fallback", Mock(side_effect=RuntimeError("start failed"))
    )
    start()
    assert not state.is_listening
    assert not state.session_start_pending
    assert state.next_output_session_id == 2
    if stage == "start":
        recorder.stop.assert_called_once()


@pytest.mark.parametrize("reason", ["shutdown", "superseded", "inactive"])
def test_capture_monitor_exits_without_a_key_release(state, monkeypatch, reason):
    state.is_listening = reason != "inactive"
    state.active_session_id = 2 if reason == "superseded" else 1
    if reason == "shutdown":
        app.shutdown_event.set()
    sleep = Mock(side_effect=[None, AssertionError("monitor did not exit")])
    monkeypatch.setattr(app.time, "sleep", sleep)
    app.monitor_active_session(1)
    sleep.assert_called_once()
