from __future__ import annotations

import base64
import json
import queue
import threading
from types import SimpleNamespace

import numpy as np

import push_to_talk_realtime as app


class FakeWebSocket:
    def __init__(self, events: list[dict]) -> None:
        self.events = [json.dumps(event) for event in events]
        self.sent: list[dict] = []

    def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    def recv(self, timeout: float | None = None) -> str:
        del timeout
        if not self.events:
            raise TimeoutError
        return self.events.pop(0)


def test_live_session_event_uses_current_transcription_contract(monkeypatch):
    monkeypatch.setattr(app, "LIVE_TRANSCRIBE_LANGUAGES", ("en", "fr"))
    monkeypatch.setattr(app, "LIVE_TRANSCRIBE_PROMPT", "Names: Ada, Linus")
    monkeypatch.setattr(app, "LIVE_TRANSCRIBE_DELAY", "low")

    event = app.build_live_transcription_session_update_event()
    input_config = event["session"]["audio"]["input"]

    assert event["type"] == "session.update"
    assert event["session"]["type"] == "transcription"
    assert input_config["format"] == {"type": "audio/pcm", "rate": 24000}
    assert input_config["turn_detection"] is None
    assert input_config["transcription"] == {
        "model": "gpt-live-transcribe",
        "languages": ["en", "fr"],
        "prompt": "Names: Ada, Linus",
        "delay": "low",
    }


def test_live_session_streams_audio_commits_once_and_returns_completed_text():
    audio_queue: queue.Queue[np.ndarray] = queue.Queue()
    audio_queue.put(np.arange(160, dtype=np.int16))
    stop_event = threading.Event()
    stop_event.set()
    deltas: list[str] = []
    ws = FakeWebSocket(
        [
            {"type": "session.created", "session": {"type": "transcription"}},
            {"type": "session.updated", "session": {"type": "transcription"}},
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "item_id": "item-1",
                "delta": "Hello ",
            },
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "item-1",
                "transcript": "Hello world.",
            },
        ]
    )

    text = app.run_live_transcription_session(ws, audio_queue, stop_event, deltas.append)

    assert text == "Hello world."
    assert deltas == ["Hello "]
    assert [event["type"] for event in ws.sent] == [
        "session.update",
        "input_audio_buffer.append",
        "input_audio_buffer.commit",
    ]
    audio = base64.b64decode(ws.sent[1]["audio"])
    assert len(audio) == 240 * np.dtype(np.int16).itemsize


def test_live_session_surfaces_structured_api_errors():
    ws = FakeWebSocket(
        [
            {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "code": "bad_model",
                    "message": "Unsupported model",
                },
            }
        ]
    )

    try:
        app.run_live_transcription_session(ws, queue.Queue(), threading.Event())
    except RuntimeError as exc:
        assert "bad_model" in str(exc)
        assert "Unsupported model" in str(exc)
    else:
        raise AssertionError("Expected the realtime API error to be raised")


def test_live_session_honors_explicit_cancellation():
    cancel_event = threading.Event()
    cancel_event.set()
    ws = FakeWebSocket([])

    text = app.run_live_transcription_session(
        ws,
        queue.Queue(),
        threading.Event(),
        cancel_event=cancel_event,
    )

    assert text == ""
    assert [event["type"] for event in ws.sent] == ["session.update"]


def test_recorded_transcription_sends_gpt_transcribe_model(monkeypatch):
    calls: list[dict] = []

    class FakeTranscriptions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text="Daily workhorse")

    client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=FakeTranscriptions()),
    )
    monkeypatch.setattr(app, "get_openai_client", lambda: client)

    text = app.transcribe_with_whisper(
        [np.arange(160, dtype=np.int16)],
        "gpt-transcribe",
    )

    assert text == "Daily workhorse"
    assert calls[0]["model"] == "gpt-transcribe"
    assert calls[0]["response_format"] == "json"
