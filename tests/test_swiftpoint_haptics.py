from unittest.mock import Mock

import pytest

import swiftpoint_haptics as haptics


@pytest.mark.parametrize(
    "enabled,command", [(True, b"Vibrate 45 65\n"), (False, b"Vibrate 90 40\n")]
)
def test_protocol_and_handle_cleanup(monkeypatch, enabled, command):
    monkeypatch.setattr(haptics.os, "O_BINARY", 0, raising=False)
    monkeypatch.setattr(haptics.os, "open", Mock(return_value=7))
    write = Mock(return_value=len(command))
    close = Mock()
    monkeypatch.setattr(haptics.os, "write", write)
    monkeypatch.setattr(haptics.os, "close", close)
    monkeypatch.setattr(haptics.os, "read", Mock(return_value=b"OK\n"))
    assert haptics.send_pulse(enabled)
    write.assert_called_once_with(7, command)
    close.assert_called_once_with(7)
    monkeypatch.setattr(haptics.os, "read", Mock(side_effect=OSError))
    with pytest.raises(OSError):
        haptics.send_pulse(enabled)
    assert close.call_count == 2


def test_worker_timeout_is_nonfatal_and_releases_gate(monkeypatch):
    monkeypatch.setattr(haptics.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    run = Mock(side_effect=haptics.subprocess.TimeoutExpired("helper", 1))
    monkeypatch.setattr(haptics.subprocess, "run", run)
    feedback = haptics.BulletHaptics()
    feedback._busy.acquire()
    feedback._send(True)
    assert not feedback._busy.locked()
    assert run.call_args.kwargs["timeout"] == 1.0


def test_busy_worker_drops_new_requests_and_start_failure_recovers(monkeypatch):
    monkeypatch.setattr(haptics.sys, "platform", "win32")
    thread = Mock()
    thread.return_value.start.side_effect = RuntimeError("no thread")
    monkeypatch.setattr(haptics.threading, "Thread", thread)
    feedback = haptics.BulletHaptics()
    feedback._busy.acquire()
    feedback.notify(True)
    thread.assert_not_called()
    feedback._busy.release()
    feedback.notify(True)
    assert not feedback._busy.locked()


def test_unsupported_platform_does_not_start_worker(monkeypatch):
    monkeypatch.setattr(haptics.sys, "platform", "linux")
    thread = Mock()
    monkeypatch.setattr(haptics.threading, "Thread", thread)
    haptics.BulletHaptics().notify(True)
    thread.assert_not_called()
