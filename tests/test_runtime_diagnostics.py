import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

import diagnostic_report
import process_supervisor
import runtime_diagnostics as diag


def read_events(root, component):
    return [
        json.loads(line)
        for line in (root / f"{component}.events.jsonl")
        .read_text(encoding="utf-8-sig")
        .splitlines()
    ]


def test_secret_content_messages_locals_and_unknown_fields_are_dropped(tmp_path):
    logger = diag.Diagnostics("app", tmp_path)
    secret = "SYNTHETIC_SECRET_TRANSCRIPT_CLIPBOARD"
    try:
        raise RuntimeError(secret)
    except RuntimeError as exc:
        logger.emit(
            "exception",
            exception=exc,
            message=secret,
            transcript=secret,
            clipboard=secret,
            launch_source=secret,
        )
    text = logger.path.read_text()
    assert secret not in text
    event = json.loads(text)
    assert event["exception"]["type"] == "RuntimeError"
    assert event["exception"]["frames"][0]["function"].startswith("test_")
    assert event["launch_source"] == "unknown"
    assert all("locals" not in frame for frame in event["exception"]["frames"])
    assert "line" in event["exception"]["frames"][0]


def test_legacy_sink_cannot_leak_multiline_or_exception_contents():
    secret = "SYNTHETIC_PAYLOAD"
    for parts in [
        ("[Final]: " + secret,),
        ("[Audio] " + secret, RuntimeError(secret)),
        (secret,),
        ("[Settings] " + secret,),
    ]:
        assert secret not in diag.legacy_summary(parts)


def test_unclean_previous_run_is_distinguished_from_deliberate_shutdown(tmp_path):
    first = diag.Diagnostics("supervisor", tmp_path)
    first.begin()
    second = diag.Diagnostics("supervisor", tmp_path)
    second.begin()
    unclosed = [
        event
        for event in read_events(tmp_path, "supervisor")
        if event["event"] == "previous_run_unclosed"
    ]
    assert len(unclosed) == 1
    assert unclosed[0]["previous_run_id"] == first.run_id
    assert unclosed[0]["reason"] == "unknown"
    second.end("quit")
    third = diag.Diagnostics("supervisor", tmp_path)
    third.begin()
    assert (
        len(
            [
                event
                for event in read_events(tmp_path, "supervisor")
                if event["event"] == "previous_run_unclosed"
            ]
        )
        == 1
    )


def test_rotation_and_report_are_bounded_and_drop_unknown_content(monkeypatch, tmp_path):
    monkeypatch.setattr(diag, "MAX_BYTES", 600)
    monkeypatch.setattr(diag, "BACKUPS", 2)
    logger = diag.Diagnostics("launcher", tmp_path)
    for _ in range(25):
        logger.emit("duplicate_rejected", reason="duplicate", message="SYNTHETIC_SECRET")
    assert len(list(tmp_path.glob("launcher.events.jsonl*"))) == 3
    assert "SYNTHETIC_SECRET" not in json.dumps(diagnostic_report.snapshot(tmp_path))
    for path in tmp_path.glob("launcher.events.jsonl*"):
        for line in path.read_text().splitlines():
            assert json.loads(line)["event"] == "duplicate_rejected"


def test_heartbeat_distinguishes_unknown_ready_stale_and_pid_mismatch(tmp_path):
    assert diag.app_health(tmp_path)["readiness"] == "unknown"
    logger = diag.Diagnostics("app", tmp_path)
    logger.begin()
    logger.heartbeat(
        force=True,
        readiness="reported_ready",
        listener_thread_alive=True,
        queue_state_known=False,
        progress_source="tray_worker",
    )
    assert diag.app_health(tmp_path, os.getpid())["app_health_fresh"]
    assert diag.app_health(tmp_path, os.getpid() + 1)["readiness"] == "unknown"
    state = json.loads(logger.state_path.read_text())
    state["epoch"] = time.time() - 60
    logger.state_path.write_text(json.dumps(state))
    assert diag.app_health(tmp_path)["readiness"] == "stale"


def test_diagnostic_disk_failure_does_not_raise_or_hide_counter(tmp_path):
    root = tmp_path / "not_a_directory"
    root.write_text("fixture")
    logger = diag.Diagnostics("app", root)
    logger.begin()
    logger.heartbeat(force=True)
    logger.end("quit")
    assert logger.failures > 0


def test_supervisor_events_capture_launch_failure_exit_and_recovery_without_payload(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("PUSH_TO_TALK_DIAGNOSTICS_DIR", str(tmp_path))
    launch = Mock(
        side_effect=[
            OSError("SYNTHETIC_SECRET"),
            Mock(pid=10, wait=Mock(return_value=0xC0000005)),
            Mock(pid=11, wait=Mock(return_value=23)),
        ]
    )
    monkeypatch.setattr(process_supervisor.subprocess, "Popen", launch)
    monkeypatch.setattr(process_supervisor.time, "sleep", lambda _: None)
    assert process_supervisor.supervise(["fixture"], tmp_path, tmp_path / "child.log") == 0
    events = read_events(tmp_path, "supervisor")
    assert any(
        e["event"] == "launch_failed" and e["exception"]["type"] == "OSError" for e in events
    )
    assert any(e.get("exit_code") == 0xC0000005 for e in events)
    assert len([e for e in events if e["event"] == "recovery_scheduled"]) == 2
    assert "SYNTHETIC_SECRET" not in "".join(path.read_text() for path in tmp_path.glob("*.log"))
    assert "SYNTHETIC_SECRET" not in json.dumps(events)


def test_heartbeat_observation_does_not_claim_hang_recovery(monkeypatch, tmp_path):
    monkeypatch.setenv("PUSH_TO_TALK_DIAGNOSTICS_DIR", str(tmp_path))
    child = Mock(pid=10, wait=Mock(side_effect=[subprocess.TimeoutExpired("fixture", 5), 23]))
    monkeypatch.setattr(process_supervisor.subprocess, "Popen", Mock(return_value=child))
    process_supervisor.supervise(["fixture"], tmp_path, tmp_path / "child.log")
    events = read_events(tmp_path, "supervisor")
    assert any(e["event"] == "heartbeat" and e["readiness"] == "unknown" for e in events)
    child.terminate.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows task wrapper")
def test_task_wrapper_records_cold_start_failure_without_python_or_secret(tmp_path):
    wrapper = Path(process_supervisor.__file__).with_name("readiness_task.ps1")
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(wrapper),
            "-Python",
            str(tmp_path / "SYNTHETIC_SECRET_missing.exe"),
            "-DiagnosticsDirectory",
            str(tmp_path),
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 1
    events = read_events(tmp_path, "task")
    assert any(event["event"] == "cold_start_failed" for event in events)
    assert "SYNTHETIC_SECRET" not in json.dumps(events)


def test_app_heartbeat_busy_and_listener_down_are_metadata_only(monkeypatch, tmp_path):
    import push_to_talk_realtime as app

    logger = diag.Diagnostics("app", tmp_path)
    logger.begin()
    monkeypatch.setattr(app, "APP_DIAGNOSTICS", logger)
    monkeypatch.setattr(app, "diagnostic_setup_complete", True)
    monkeypatch.setattr(app, "keyboard_listener_is_running", lambda: False)
    monkeypatch.setattr(
        app,
        "state",
        app.SessionState(transcribing_session_count=1, transcript_final="SYNTHETIC_SECRET"),
    )
    app.publish_diagnostic_health(force=True)
    assert diag.app_health(tmp_path)["readiness"] == "busy"
    app.state.transcribing_session_count = 0
    app.publish_diagnostic_health(force=True)
    assert diag.app_health(tmp_path)["readiness"] == "listener_down"
    assert "SYNTHETIC_SECRET" not in logger.state_path.read_text()
    assert diag.app_health(tmp_path)["queue_state_known"] is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows task wrapper")
@pytest.mark.parametrize("exit_code", [0, 7])
def test_real_wrapper_exits_and_discards_raw_output(tmp_path, exit_code):
    wrapper = Path(process_supervisor.__file__).with_name("readiness_task.ps1")
    child = tmp_path / "fixture.py"
    child.write_text(
        f"import sys; print('SYNTHETIC_SECRET'); print('SYNTHETIC_SECRET', file=sys.stderr); sys.exit({exit_code})"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(wrapper),
            "-Python",
            sys.executable,
            "-Launcher",
            str(child),
            "-DiagnosticsDirectory",
            str(tmp_path),
        ],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == exit_code, result.stderr.decode(errors="replace")
    events = read_events(tmp_path, "task")
    assert events[-1]["event"] == "python_exited"
    assert events[-1]["exit_code"] == exit_code
    assert events[-1]["epoch"] > 0
    assert "SYNTHETIC_SECRET" not in json.dumps(events)
    assert b"SYNTHETIC_SECRET" not in result.stdout + result.stderr


def test_native_stack_dump_contains_locations_not_contents(tmp_path):
    script = "import pathlib,sys,faulthandler; from runtime_diagnostics import enable_native_trace,close_native_trace; secret='SYNTHETIC_SECRET'; h=enable_native_trace(pathlib.Path(sys.argv[1])); assert h is not None; faulthandler.dump_traceback(file=h); close_native_trace(h)"
    environment = os.environ.copy()
    environment.pop("PYTHONFAULTHANDLER", None)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env=environment,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    dump = (tmp_path / "native-stacks.log").read_text()
    assert "File" in dump
    assert "SYNTHETIC_SECRET" not in dump


def test_corrupt_health_and_event_json_do_not_break_reporting(tmp_path):
    (tmp_path / "app.health.json").write_text("[]")
    (tmp_path / "app.events.jsonl").write_text("[]\nnot-json\n")
    assert diagnostic_report.snapshot(tmp_path)["app_health"]["readiness"] == "unknown"
    logger = diag.Diagnostics("app", tmp_path)
    logger.begin()
    assert logger.active


def test_duplicate_launch_records_sanitized_rejection(monkeypatch, tmp_path):
    import start_push_to_talk as starter
    import windows_instance

    logger = diag.Diagnostics("launcher", tmp_path)
    monkeypatch.setattr(starter, "DIAGNOSTICS", logger)
    monkeypatch.setattr(starter.platform, "system", lambda: "Windows")
    guard = Mock(acquired=False)
    context = Mock()
    context.__enter__ = Mock(return_value=guard)
    context.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(windows_instance, "WindowsInstance", Mock(return_value=context))
    assert starter.main(["--supervise", "--ptt-only"]) == 0
    assert read_events(tmp_path, "launcher")[-1]["event"] == "duplicate_rejected"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows support report")
def test_support_report_excludes_legacy_content_and_preserves_failure_metadata(tmp_path):
    script = Path(process_supervisor.__file__).with_name("support_report.ps1")
    manager_log = tmp_path / "manager.log"
    manager_log.write_text(
        "[2026-10-02 12:00:00] Start exception: SYNTHETIC_SECRET\n[2026-10-02 12:00:01] Exited with code 7.\n[Final]: SYNTHETIC_SECRET\n"
    )
    environment = dict(os.environ, PUSH_TO_TALK_DIAGNOSTICS_DIR=str(tmp_path))
    logger = diag.Diagnostics("launcher", tmp_path)
    logger.emit("exception", exception=RuntimeError("SYNTHETIC_SECRET"))
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
            "-Python",
            sys.executable,
            "-ManagerLog",
            str(manager_log),
        ],
        capture_output=True,
        timeout=30,
        env=environment,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    report = json.loads(result.stdout.decode("utf-8-sig"))
    assert "SYNTHETIC_SECRET" not in json.dumps(report)
    assert any(event.get("exit_code") == 7 for event in report["manager_events"])
    assert report["diagnostics"]["recent_events"][0]["exception_type"] == "RuntimeError"
