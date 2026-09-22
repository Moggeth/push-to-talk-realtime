import subprocess
import sys
from unittest.mock import Mock

import pytest

import process_supervisor as monitor
import start_push_to_talk as starter


def test_restarts_even_zero_exit_until_explicit_intentional_exit(monkeypatch, tmp_path):
    codes = iter([0, 1, 0xC0000005, monitor.EXPECTED_EXIT])
    commands = []
    delays = []

    def launch(command, **kwargs):
        commands.append((command, kwargs))
        return Mock(pid=100, wait=Mock(return_value=next(codes)))

    monkeypatch.setattr(monitor.subprocess, "Popen", launch)
    monkeypatch.setattr(monitor.time, "sleep", delays.append)
    assert monitor.supervise(["child"], tmp_path, tmp_path / "child.log") == 0
    assert len(commands) == 4
    assert delays == [2, 4, 8]
    assert commands[0][1]["env"][monitor.SUPERVISED_ENV] == "1"
    assert commands[0][1]["env"]["PYTHONFAULTHANDLER"] == "1"
    log = (tmp_path / "push_to_talk_supervisor.log").read_text()
    assert "code=3221225477" in log
    assert "Intentional exit" in log


def test_launch_failure_backoff_is_bounded(monkeypatch, tmp_path):
    launch = Mock(
        side_effect=[OSError("fixture")] * 10
        + [
            Mock(pid=1, wait=Mock(return_value=monitor.EXPECTED_EXIT)),
        ]
    )
    delays = []
    monkeypatch.setattr(monitor.subprocess, "Popen", launch)
    monkeypatch.setattr(monitor.time, "sleep", delays.append)
    monitor.supervise(["child"], tmp_path, tmp_path / "child.log")
    assert delays[:3] == [2, 4, 8]
    assert max(delays) == 60


def test_stable_child_resets_backoff(monkeypatch, tmp_path):
    times = iter([0, 1, 3, 4, 8, 80, 81, 82])
    codes = iter([1, 1, 1, monitor.EXPECTED_EXIT])
    monkeypatch.setattr(monitor.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(
        monitor.subprocess,
        "Popen",
        lambda *a, **k: Mock(pid=1, wait=Mock(return_value=next(codes))),
    )
    delays = []
    monkeypatch.setattr(monitor.time, "sleep", delays.append)
    monitor.supervise(["child"], tmp_path, tmp_path / "child.log")
    assert delays == [2, 4, 1]


def test_unwritable_supervisor_log_does_not_abandon_or_duplicate_child(monkeypatch, tmp_path):
    (tmp_path / "push_to_talk_supervisor.log").mkdir()
    child = Mock(pid=1, wait=Mock(return_value=monitor.EXPECTED_EXIT))
    launch = Mock(return_value=child)
    monkeypatch.setattr(monitor.subprocess, "Popen", launch)
    assert monitor.supervise(["child"], tmp_path, tmp_path / "child.log") == 0
    launch.assert_called_once()
    child.wait.assert_called_once()


def test_windows_launch_uses_supervisor(monkeypatch, tmp_path):
    monkeypatch.setattr(starter.platform, "system", lambda: "Windows")
    monkeypatch.setattr(starter, "LAUNCHER_LOG_PATH", tmp_path / "child.log")
    monkeypatch.setattr(starter, "startup_python_executable", lambda _: "pythonw")
    launch = Mock()
    monkeypatch.setattr(starter.subprocess, "Popen", launch)
    starter.spawn_detached_background()
    assert launch.call_args.args[0][-1] == "--supervise"


def test_restart_wait_timeout_does_not_launch_duplicate(monkeypatch):
    monkeypatch.setattr(starter.platform, "system", lambda: "Windows")
    monkeypatch.setattr(starter, "wait_for_windows_process", lambda _: False)
    launch = Mock()
    monkeypatch.setattr(starter, "spawn_detached_background", launch)
    assert starter.main(["--restart-after", "123"]) == 1
    launch.assert_not_called()


def test_real_windows_wait_does_not_kill_child():
    if sys.platform != "win32":
        return
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    try:
        assert not monitor.wait_for_windows_process(child.pid, timeout_ms=20)
        assert child.poll() is None
    finally:
        child.terminate()
        child.wait(timeout=5)


def test_real_child_crash_recovers_and_intentional_quit_stops(monkeypatch, tmp_path):
    counter = tmp_path / "attempts"
    script = (
        "import os, pathlib, sys; "
        "p=pathlib.Path(sys.argv[1]); "
        "n=int(p.read_text()) if p.exists() else 0; "
        "p.write_text(str(n+1)); "
        f"os._exit(7 if n == 0 else {monitor.EXPECTED_EXIT})"
    )
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    assert (
        monitor.supervise(
            [sys.executable, "-c", script, str(counter)],
            tmp_path,
            tmp_path / "child.log",
        )
        == 0
    )
    assert counter.read_text() == "2"
    log = (tmp_path / "push_to_talk_supervisor.log").read_text()
    assert "code=7" in log
    assert "code=23" in log


@pytest.mark.parametrize(
    "supervised,result,expected",
    [
        (True, 0, monitor.EXPECTED_EXIT),
        (True, 1, 1),
        (False, 0, 0),
        (False, 1, 1),
    ],
)
def test_foreground_maps_only_intentional_exit(monkeypatch, supervised, result, expected):
    import push_to_talk_realtime as app

    monkeypatch.setenv(monitor.SUPERVISED_ENV, "1" if supervised else "0")
    monkeypatch.setattr(app, "main", lambda: result)
    monkeypatch.setattr(starter.signal, "signal", Mock())
    assert starter.run_foreground() == expected
