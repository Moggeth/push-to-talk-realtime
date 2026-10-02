import os
import subprocess
import sys
import time
import uuid
from unittest.mock import Mock

import pytest

import process_supervisor as monitor
import start_push_to_talk as starter
import startup_integration as startup


def test_existing_app_is_monitored_without_spawning_duplicate(monkeypatch, tmp_path):
    present = Mock(side_effect=[True, True, False])
    child = Mock(pid=10, wait=Mock(return_value=monitor.EXPECTED_EXIT))
    launch = Mock(return_value=child)
    monkeypatch.setattr(monitor.subprocess, "Popen", launch)
    monkeypatch.setattr(monitor.time, "sleep", Mock())
    assert (
        monitor.supervise(["fixture"], tmp_path, tmp_path / "child.log", existing_instance=present)
        == 0
    )
    launch.assert_called_once()
    assert present.call_count == 3
    log = (tmp_path / "push_to_talk_supervisor.log").read_text()
    assert log.count("Existing app detected") == 1
    assert "Existing app exited; starting replacement" in log


def test_instance_probe_error_retries_without_launching_duplicate(monkeypatch, tmp_path):
    present = Mock(side_effect=[OSError("access denied"), False])
    launch = Mock(return_value=Mock(pid=10, wait=Mock(return_value=monitor.EXPECTED_EXIT)))
    monkeypatch.setattr(monitor.subprocess, "Popen", launch)
    delay = Mock()
    monkeypatch.setattr(monitor.time, "sleep", delay)
    monitor.supervise(["fixture"], tmp_path, tmp_path / "child.log", existing_instance=present)
    launch.assert_called_once()
    delay.assert_called_once_with(2.0)


@pytest.mark.skipif(sys.platform != "win32", reason="Real Windows kernel mutex")
def test_real_mutex_excludes_duplicates_and_releases_on_process_death(tmp_path):
    from windows_instance import WindowsInstance, instance_exists

    name = "Local\\PTT_test_" + uuid.uuid4().hex
    ready = tmp_path / "ready"
    script = (
        "import pathlib,sys,time; from windows_instance import WindowsInstance; "
        "guard=WindowsInstance(sys.argv[1]); assert guard.acquired; "
        "pathlib.Path(sys.argv[2]).touch(); time.sleep(30)"
    )
    child = subprocess.Popen([sys.executable, "-c", script, name, str(ready)])
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        assert instance_exists(name)
        with WindowsInstance(name) as duplicate:
            assert not duplicate.acquired
        child.terminate()
        child.wait(timeout=5)
        assert not instance_exists(name)
        with WindowsInstance(name) as replacement:
            assert replacement.acquired
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)


def test_ptt_only_overrides_inherited_preroll_before_start(monkeypatch):
    monkeypatch.setenv("MICROPHONE_PRE_ROLL_ENABLED", "1")
    monkeypatch.setattr(
        starter, "run_foreground", lambda: int(os.environ["MICROPHONE_PRE_ROLL_ENABLED"])
    )
    assert starter.main(["--foreground", "--ptt-only"]) == 0


def test_windowless_bootstrap_failure_is_durable(monkeypatch, tmp_path):
    monkeypatch.setattr(starter, "LAUNCHER_LOG_PATH", tmp_path / "child.log")
    monkeypatch.setattr(starter, "main", Mock(side_effect=OSError("synthetic bootstrap failure")))
    assert starter.entrypoint() == 1
    assert (
        "synthetic bootstrap failure"
        in (tmp_path / "push_to_talk_supervisor_bootstrap.log").read_text()
    )


@pytest.mark.parametrize("enabled", [True, False])
def test_task_status_reads_settings_not_trigger_enabled(monkeypatch, enabled):
    xml = (
        '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Triggers><LogonTrigger><Enabled>true</Enabled></LogonTrigger></Triggers><Settings><Enabled>'
        + str(enabled).lower()
        + "</Enabled></Settings></Task>"
    )
    monkeypatch.setattr(
        startup.subprocess, "run", Mock(return_value=Mock(returncode=0, stdout=xml))
    )
    assert startup.windows_readiness_task_enabled() == enabled


def test_disable_startup_disables_task_without_stopping_active_app(monkeypatch, tmp_path):
    monkeypatch.setattr(startup.platform, "system", lambda: "Windows")
    monkeypatch.setattr(startup, "windows_readiness_task_enabled", lambda: True)
    change = Mock()
    monkeypatch.setattr(startup, "set_windows_readiness_task_enabled", change)
    legacy = tmp_path / "startup.cmd"
    legacy.touch()
    monkeypatch.setattr(startup, "windows_startup_script_path", lambda: legacy)
    assert startup.disable_run_on_startup(None)
    change.assert_called_once_with(False)
    assert not legacy.exists()


def test_app_guard_fails_closed(monkeypatch):
    import push_to_talk_realtime as app
    import windows_instance

    monkeypatch.setattr(app, "IS_WINDOWS", True)
    monkeypatch.setattr(
        windows_instance, "WindowsInstance", Mock(side_effect=OSError("mutex denied"))
    )
    with pytest.raises(OSError, match="mutex denied"):
        app.acquire_app_instance_guard()


def test_disabled_preroll_never_starts_idle_microphone(monkeypatch):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "MICROPHONE_PRE_ROLL_ENABLED", False)
    capture = Mock()
    monkeypatch.setattr(app, "warm_microphone_capture", capture)
    assert app.maintain_warm_microphone_capture()
    app.start_warm_microphone_watchdog()
    capture.start.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="Real Windows process recovery")
def test_real_supervisor_death_adoption_and_child_failure_recovery(tmp_path):
    from windows_instance import instance_exists

    name = "Local\\PTT_recovery_" + uuid.uuid4().hex
    child_script = tmp_path / "child.py"
    child_script.write_text(
        "import os, pathlib, sys, time\n"
        "from windows_instance import WindowsInstance\n"
        "guard = WindowsInstance(sys.argv[1])\n"
        "assert guard.acquired\n"
        "pid_path = pathlib.Path(sys.argv[2])\n"
        "pid_path.write_text(str(os.getpid()))\n"
        "stop = pid_path.with_name(str(os.getpid()) + '.stop')\n"
        "deadline = time.monotonic() + 30\n"
        "while time.monotonic() < deadline:\n"
        "    if stop.exists(): os._exit(7)\n"
        "    time.sleep(0.02)\n",
        encoding="utf-8",
    )
    pid_path = tmp_path / "child.pid"
    runner = (
        "import pathlib,sys; from windows_instance import WindowsInstance,instance_exists; "
        "from process_supervisor import supervise; "
        "guard=WindowsInstance(sys.argv[1]+'_supervisor'); "
        "sys.exit(0) if not guard.acquired else None; "
        "supervise([sys.executable,sys.argv[2],sys.argv[1],sys.argv[3]], "
        "pathlib.Path.cwd(),pathlib.Path(sys.argv[4]), "
        "existing_instance=lambda:instance_exists(sys.argv[1]))"
    )
    env = dict(os.environ, PYTHONPATH=str(starter.SCRIPT_DIR))

    def launch():
        return subprocess.Popen(
            [
                sys.executable,
                "-c",
                runner,
                name,
                str(child_script),
                str(pid_path),
                str(tmp_path / "child.log"),
            ],
            env=env,
        )

    def wait_until(check):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(0.05)
        pytest.fail("synthetic process recovery deadline exceeded")

    def kill_fixture_child():
        # Only the PID written by this unique synthetic fixture, never the live app.
        if pid_path.exists():
            pid_path.with_name(pid_path.read_text() + ".stop").touch()

    supervisor = launch()
    try:
        wait_until(pid_path.exists)
        first_pid = pid_path.read_text()
        duplicate = launch()
        assert duplicate.wait(timeout=5) == 0
        assert pid_path.read_text() == first_pid
        supervisor.terminate()
        supervisor.wait(timeout=5)
        assert instance_exists(name)  # Child survives losing its supervisor.
        supervisor = launch()
        wait_until(
            lambda: "Existing app detected"
            in (tmp_path / "push_to_talk_supervisor.log").read_text()
        )
        assert pid_path.read_text() == first_pid
        kill_fixture_child()
        wait_until(lambda: pid_path.read_text() != first_pid)
        assert supervisor.poll() is None
        assert instance_exists(name)
    finally:
        if supervisor.poll() is None:
            supervisor.terminate()
        supervisor.wait(timeout=5)
        kill_fixture_child()
