import http.client
import json
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

import push_to_talk_realtime as app
import transcript_browser
import transcript_store


def test_concurrent_saves_serialize_snapshots(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "SETTINGS_PATH", tmp_path / "settings.json")
    entered = threading.Event()
    release = threading.Event()
    second_entered = threading.Event()
    second_started = threading.Event()
    original = app._write_settings_payload
    writes = []
    results = []

    def write(payload):
        writes.append(payload["post_process_model"])
        if len(writes) == 1:
            entered.set()
            assert release.wait(2)
        else:
            second_entered.set()
        original(payload)

    def second_save():
        second_started.set()
        results.append(app.save_settings_to_disk())

    monkeypatch.setattr(app, "_write_settings_payload", write)
    app.state.post_process_model = "gpt-5.6-terra"
    first = threading.Thread(target=lambda: results.append(app.save_settings_to_disk()))
    second = threading.Thread(target=second_save)
    first.start()
    try:
        assert entered.wait(2)
        with app.state.lock:
            app.state.post_process_model = "gpt-5.6-sol"
        second.start()
        assert second_started.wait(2)
        assert not second_entered.wait(0.05)
    finally:
        release.set()
        first.join(2)
        if second.ident is not None:
            second.join(2)
    assert not first.is_alive() and not second.is_alive()
    assert results == [True, True]
    assert writes == ["gpt-5.6-terra", "gpt-5.6-sol"]
    assert json.loads(app.SETTINGS_PATH.read_text())["post_process_model"] == "gpt-5.6-sol"


@pytest.mark.parametrize("value", ["false", "true", 1, 0, None, []])
def test_invalid_boolean_settings_keep_defaults(monkeypatch, value):
    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(
        app,
        "load_settings_from_disk",
        lambda: {
            "dictation_history_enabled": value,
            "post_processing_enabled": value,
        },
    )
    app.apply_persisted_settings()
    assert app.state.dictation_history_enabled == app.DEFAULT_DICTATION_HISTORY_ENABLED
    assert app.state.post_processing_enabled is False


def test_database_setup_failure_closes_connection(monkeypatch, tmp_path):
    connection = Mock()
    connection.execute.side_effect = RuntimeError("database locked")
    monkeypatch.setattr(transcript_store.sqlite3, "connect", Mock(return_value=connection))
    with pytest.raises(RuntimeError, match="database locked"):
        transcript_store.TranscriptStore(tmp_path / "db")._connect()
    connection.close.assert_called_once()


def test_failed_settings_replace_preserves_previous_file(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"post_process_model": "gpt-5.6-terra"}')
    previous = path.read_bytes()
    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "SETTINGS_PATH", path)
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(Path, "replace", Mock(side_effect=PermissionError("file busy")))
    assert app.save_settings_to_disk() is False
    assert path.read_bytes() == previous


@pytest.mark.parametrize(
    "length,body,status",
    [
        ("nope", b"", 400),
        ("-1", b"", 400),
        ("32769", b"", 400),
        ("1", b"\xff", 400),
        ("10", b"", 408),
    ],
)
def test_browser_rejects_invalid_or_stalled_body(monkeypatch, tmp_path, length, body, status):
    monkeypatch.setattr(transcript_browser.TranscriptBrowserHandler, "timeout", 0.1)
    server, _ = transcript_browser.launch_transcript_browser(
        transcript_store.TranscriptStore(tmp_path / "db"), open_browser=False
    )
    connection = http.client.HTTPConnection(*server.server_address, timeout=2)
    try:
        connection.request("POST", "/delete/1", body=body, headers={"Content-Length": length})
        response = connection.getresponse()
        assert response.status == status
        response.read()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
