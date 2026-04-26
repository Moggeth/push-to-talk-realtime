from __future__ import annotations

from pathlib import Path

import start_push_to_talk as starter


def test_main_runs_foreground_when_managed_by_systemd(monkeypatch):
    monkeypatch.setenv(starter.SYSTEMD_MANAGED_ENV, "1")
    monkeypatch.setattr(starter, "run_foreground", lambda: 7)

    assert starter.main([]) == 7


def test_main_delegates_to_linux_service_when_available(monkeypatch, tmp_path: Path):
    service_path = tmp_path / starter.SYSTEMD_SERVICE_NAME
    service_path.write_text("[Unit]\n", encoding="utf-8")
    calls = []

    monkeypatch.delenv(starter.SYSTEMD_MANAGED_ENV, raising=False)
    monkeypatch.setattr(starter.platform, "system", lambda: "Linux")
    monkeypatch.setattr(starter, "linux_user_service_path", lambda _name: service_path)
    monkeypatch.setattr(
        starter,
        "start_linux_service",
        lambda: calls.append("service") or True,
    )
    monkeypatch.setattr(
        starter,
        "spawn_detached_background",
        lambda: calls.append("detached") or 0,
    )

    assert starter.main([]) == 0
    assert calls == ["service"]


def test_main_falls_back_to_detached_when_service_unavailable(monkeypatch, tmp_path: Path):
    service_path = tmp_path / starter.SYSTEMD_SERVICE_NAME
    calls = []

    monkeypatch.delenv(starter.SYSTEMD_MANAGED_ENV, raising=False)
    monkeypatch.setattr(starter.platform, "system", lambda: "Linux")
    monkeypatch.setattr(starter, "linux_user_service_path", lambda _name: service_path)
    monkeypatch.setattr(
        starter,
        "spawn_detached_background",
        lambda: calls.append("detached") or 0,
    )

    assert starter.main([]) == 0
    assert calls == ["detached"]


def test_spawn_detached_background_passes_foreground_flag(monkeypatch, tmp_path: Path):
    log_path = tmp_path / "push_to_talk_realtime.log"
    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

        class DummyProcess:
            pass

        return DummyProcess()

    monkeypatch.setattr(starter, "LOG_PATH", log_path)
    monkeypatch.setattr(starter, "startup_python_executable", lambda executable: executable)
    monkeypatch.setattr(starter.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(starter.platform, "system", lambda: "Linux")

    assert starter.spawn_detached_background() == 0
    assert captured["command"] == [starter.sys.executable, str(starter.SCRIPT_PATH), "--foreground"]
    assert captured["kwargs"]["cwd"] == starter.SCRIPT_DIR
    assert captured["kwargs"]["start_new_session"] is True
