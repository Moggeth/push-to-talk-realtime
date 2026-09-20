import threading
from unittest.mock import Mock

import pytest

import push_to_talk_realtime as app


@pytest.mark.parametrize("warm", [False, True])
def test_failed_stream_start_closes_device_before_retry(monkeypatch, warm):
    failed = Mock()
    failed.start.side_effect = RuntimeError("device unavailable")
    healthy = Mock(active=True)
    monkeypatch.setattr(app.sd, "InputStream", Mock(side_effect=[failed, healthy]))
    monkeypatch.setattr(app, "log", Mock())
    recorder = app.WarmMicrophoneCapture(80) if warm else app.AudioRecorder(3, [], threading.Lock())
    if warm:
        assert not recorder.start(3)
    else:
        with pytest.raises(RuntimeError, match="device unavailable"):
            recorder.start()
    failed.close.assert_called_once()
    assert recorder.stream is None
    recorder.start(3) if warm else recorder.start()
    assert recorder.stream is healthy
    recorder.stop()


def test_stream_close_still_runs_when_stop_fails():
    recorder = app.AudioRecorder(3, [], threading.Lock())
    stream = Mock()
    stream.stop.side_effect = RuntimeError("disconnected")
    recorder.stream = stream
    with pytest.raises(RuntimeError, match="disconnected"):
        recorder.stop()
    stream.close.assert_called_once()
    assert recorder.stream is None


def test_watchdog_exception_is_logged_and_retried(monkeypatch):
    waits = []
    monkeypatch.setattr(app, "shutdown_event", threading.Event())
    stop = Mock()
    stop.wait.side_effect = lambda delay: waits.append(delay) or len(waits) > 2
    monkeypatch.setattr(app, "warm_microphone_watchdog_stop", stop)
    recovery = Mock(side_effect=[RuntimeError("driver reset"), True])
    monkeypatch.setattr(app, "maintain_warm_microphone_capture", recovery)
    log = Mock()
    monkeypatch.setattr(app, "log", log)
    app.warm_microphone_watchdog_loop()
    assert waits == [0.0, 2.0, app.WARM_MICROPHONE_HEALTH_CHECK_INTERVAL_S]
    assert recovery.call_count == 2
    assert "retrying" in log.call_args.args[0]


def test_watchdog_does_not_reopen_during_pending_capture(monkeypatch):
    monkeypatch.setattr(app, "state", app.SessionState(session_start_pending=True))
    capture = Mock()
    monkeypatch.setattr(app, "warm_microphone_capture", capture)
    assert app.maintain_warm_microphone_capture()
    capture.start.assert_not_called()


def test_stale_stream_with_attached_recording_is_not_discarded(monkeypatch):
    stream = Mock(active=True)
    monkeypatch.setattr(app.sd, "InputStream", Mock(return_value=stream))
    monkeypatch.setattr(app, "log", Mock())
    capture = app.WarmMicrophoneCapture(80)
    assert capture.start(3)
    token, _ = capture.attach(3, [], threading.Lock(), None)
    capture.last_callback_at = 0
    assert not capture.start(3)
    assert capture.active_token is token
    stream.close.assert_not_called()
    capture.detach(token)
    assert capture.start(3)
    stream.close.assert_called_once()
    capture.stop()
