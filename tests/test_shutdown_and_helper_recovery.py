import io
import queue
import threading
from unittest.mock import Mock

import pytest

from rewrite_review import RewriteReviewManager


@pytest.fixture
def app(monkeypatch):
    import push_to_talk_realtime as module

    monkeypatch.setattr(module, "state", module.SessionState())
    monkeypatch.setattr(module, "shutdown_event", threading.Event())
    monkeypatch.setattr(module, "log", Mock())
    monkeypatch.setattr(module, "mark_transcription_finished", Mock())
    return module


def test_shutdown_wakes_waiting_output_without_skipping_sessions(app):
    entered = threading.Event()
    result = []

    def wait():
        entered.set()
        result.append(app.wait_for_output_turn(2))

    thread = threading.Thread(target=wait)
    thread.start()
    assert entered.wait(1)
    app.request_shutdown()
    thread.join(1)
    assert not thread.is_alive()
    assert result == [False]
    assert app.state.next_output_session_id == 1
    assert app.wait_for_output_turn(1) is False


@pytest.mark.parametrize("during_paste", [False, True])
def test_shutdown_prevents_clipboard_output_or_late_paste(app, monkeypatch, during_paste):
    copy, send = Mock(), Mock()
    monkeypatch.setattr(app.pyperclip, "copy", copy)
    monkeypatch.setattr(app, "send_paste_shortcut", send)
    if during_paste:
        monkeypatch.setattr(app.time, "sleep", lambda _: app.request_shutdown())
    else:
        app.request_shutdown()
    assert app.paste_text("not after quitting") is False
    send.assert_not_called()
    if not during_paste:
        copy.assert_not_called()


def test_shutdown_between_output_grant_and_delivery_does_not_paste(app, monkeypatch):
    def grant(_):
        app.request_shutdown()
        return True

    monkeypatch.setattr(app, "wait_for_output_turn", grant)
    paste, history = Mock(), Mock()
    monkeypatch.setattr(app, "paste_text", paste)
    monkeypatch.setattr(app, "append_dictation_history_entry", history)
    app.deliver_session_output(
        session_id=1,
        mode=app.MODE_DICTATION,
        outcome=app.TranscriptionOutcome("finished", "recorded", 20, 1),
        recorded_model="gpt-transcribe",
        paste_target=None,
        live_typing_enabled=False,
        realtime_delta_parts=[],
        realtime_delta_lock=threading.Lock(),
    )
    paste.assert_not_called()
    history.assert_not_called()
    app.mark_transcription_finished.assert_called_once()


def test_stale_helper_close_cannot_terminate_replacement():
    manager = RewriteReviewManager()
    old, new = Mock(), Mock()
    manager.process = new
    manager.close(expected_process=old)
    new.terminate.assert_not_called()
    assert manager.process is new


def test_close_targets_snapshot_even_if_new_helper_starts_during_termination():
    manager = RewriteReviewManager()
    old, new = Mock(), Mock()
    old.poll.return_value = None
    manager.process = old
    old.terminate.side_effect = lambda: setattr(manager, "process", new)
    waiter = threading.Event()
    manager.pending[1] = waiter
    manager.close()
    assert manager.process is new
    old.terminate.assert_called_once()
    old.wait.assert_called_once_with(timeout=0.5)
    new.terminate.assert_not_called()
    assert waiter.is_set()


@pytest.mark.parametrize("response", ["[]\n", '{"id": []}\n', "not json\n"])
def test_bad_helper_protocol_closes_old_helper_and_pipe(response):
    manager = RewriteReviewManager()
    process = Mock()
    process.poll.return_value = None
    process.stdout = io.StringIO(response)
    manager.process = process
    manager._read(process, queue.Queue())
    assert manager.process is None
    process.terminate.assert_called_once()
    assert process.stdout.closed


def test_stale_helper_reader_does_not_acknowledge_or_close_new_generation():
    manager = RewriteReviewManager()
    old, new = Mock(), Mock()
    old.poll.return_value = 0
    old.stdout = io.StringIO('{"id": 1}\n')
    manager.process = new
    waiter = manager.pending[1] = threading.Event()
    manager._read(old, queue.Queue())
    assert not waiter.is_set()
    assert manager.process is new
    new.terminate.assert_not_called()


def test_closed_generation_rejects_capture_send():
    manager = RewriteReviewManager()
    old, new = Mock(), Mock()
    manager.process = new
    assert not manager._send({"command": "capture"}, expected_process=old)
    assert manager.outgoing.empty()
