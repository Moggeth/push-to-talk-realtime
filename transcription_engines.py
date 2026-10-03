"""Recorded and live transcription engine implementations."""

from __future__ import annotations

import base64
import io
import json
import queue
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from usage_tracking import UsageMeter


@dataclass(frozen=True)
class RecordedTranscriptionConfig:
    model: str
    prompt: str
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class LiveTranscriptionConfig:
    api_key: str
    websocket_url: str
    model: str
    source_sample_rate: int
    input_sample_rate: int
    languages: tuple[str, ...] = ()
    prompt: str = ""
    delay: str = "low"
    session_ready_timeout_s: float = 8.0
    final_timeout_s: float = 10.0


def transcribe_recording(
    chunks: list[np.ndarray],
    config: RecordedTranscriptionConfig,
    client: Any,
) -> str:
    if not chunks:
        return ""
    pcm = np.concatenate(chunks, axis=0)
    wav_bytes = io.BytesIO()
    with wave.open(wav_bytes, "wb") as wav_file:
        wav_file.setnchannels(config.channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(config.sample_rate)
        wav_file.writeframes(pcm.tobytes())
    wav_bytes.seek(0)
    wav_bytes.name = "recording.wav"
    request: dict[str, Any] = {
        "model": config.model,
        "file": wav_bytes,
        "response_format": "json",
    }
    if config.prompt:
        request["prompt"] = config.prompt
    with UsageMeter(config.model, "transcription") as meter:
        meter.seconds = len(pcm) / config.sample_rate
        response = client.audio.transcriptions.create(**request)
        meter.usage = getattr(response, "usage", None)
    return getattr(response, "text", "") or ""


def resample_pcm16_mono(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if pcm.size == 0:
        return np.array([], dtype=np.int16)
    if src_rate == dst_rate:
        return pcm.astype(np.int16, copy=False)
    source = pcm.astype(np.float32)
    source_index = np.arange(source.shape[0], dtype=np.float32)
    destination_length = max(1, round(source.shape[0] * dst_rate / src_rate))
    destination_index = np.linspace(
        0,
        max(0, source.shape[0] - 1),
        num=destination_length,
        dtype=np.float32,
    )
    destination = np.interp(destination_index, source_index, source)
    return np.clip(np.round(destination), -32768, 32767).astype(np.int16)


def build_live_session_update(config: LiveTranscriptionConfig) -> dict[str, Any]:
    transcription: dict[str, Any] = {"model": config.model}
    if config.languages:
        transcription["languages"] = list(config.languages)
    if config.prompt:
        transcription["prompt"] = config.prompt
    if config.delay:
        transcription["delay"] = config.delay
    return {
        "type": "session.update",
        "session": {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": config.input_sample_rate},
                    "transcription": transcription,
                    "turn_detection": None,
                }
            },
        },
    }


def realtime_error_message(event: dict[str, Any]) -> str:
    error = event.get("error", {})
    if not isinstance(error, dict):
        return str(error)
    parts = [error.get("type"), error.get("code"), error.get("message")]
    return ": ".join(str(part) for part in parts if part) or "unknown realtime error"


def run_live_session(
    websocket: Any,
    audio_queue: queue.Queue[np.ndarray],
    stop_event: threading.Event,
    config: LiveTranscriptionConfig,
    on_delta: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    meter: UsageMeter | None = None,
) -> str:
    websocket.send(json.dumps(build_live_session_update(config)))
    session_ready_deadline = time.monotonic() + config.session_ready_timeout_s
    session_ready = False
    committed = False
    sent_audio = False
    final_deadline = 0.0
    items_with_deltas: set[str] = set()
    completed_by_item: dict[str, str] = {}

    while True:
        if cancel_event is not None and cancel_event.is_set():
            return ""
        if session_ready and not committed:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    return ""
                try:
                    chunk = audio_queue.get_nowait()
                except queue.Empty:
                    break
                if not chunk.size:
                    continue
                pcm = resample_pcm16_mono(
                    chunk.astype(np.int16, copy=False),
                    config.source_sample_rate,
                    config.input_sample_rate,
                )
                if not pcm.size:
                    continue
                websocket.send(
                    json.dumps(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(pcm.tobytes()).decode("ascii"),
                        }
                    )
                )
                sent_audio = True
                if meter is not None:
                    meter.seconds += len(pcm) / config.input_sample_rate

            if stop_event.is_set() and audio_queue.empty():
                if not sent_audio:
                    return ""
                websocket.send(json.dumps({"type": "input_audio_buffer.commit"}))
                committed = True
                final_deadline = time.monotonic() + config.final_timeout_s

        now = time.monotonic()
        if not session_ready and now >= session_ready_deadline:
            raise TimeoutError("GPT Live Transcribe session did not become ready")
        if committed and now >= final_deadline:
            raise TimeoutError("GPT Live Transcribe did not return a completed transcript")

        try:
            message = websocket.recv(timeout=0.05)
        except TimeoutError:
            continue
        if message is None:
            continue
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="replace")
        event = json.loads(message)
        event_type = str(event.get("type", ""))
        if event_type == "error":
            raise RuntimeError(f"GPT Live Transcribe error: {realtime_error_message(event)}")
        if event_type == "session.updated":
            session_ready = True
            continue
        if event_type == "conversation.item.input_audio_transcription.delta":
            item_id = str(event.get("item_id", "") or "default")
            delta = str(event.get("delta", "") or "")
            if delta:
                items_with_deltas.add(item_id)
                if on_delta is not None:
                    on_delta(delta)
            continue
        if event_type == "conversation.item.input_audio_transcription.completed":
            item_id = str(event.get("item_id", "") or "default")
            transcript = str(event.get("transcript", "") or "").strip()
            completed_by_item[item_id] = transcript
            if on_delta is not None and transcript and item_id not in items_with_deltas:
                on_delta(transcript)
            if committed:
                if meter is not None:
                    meter.completed = True
                return " ".join(text for text in completed_by_item.values() if text).strip()


def transcribe_live_stream(
    audio_queue: queue.Queue[np.ndarray],
    stop_event: threading.Event,
    config: LiveTranscriptionConfig,
    on_delta: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    from websockets.sync.client import connect

    with (
        UsageMeter(config.model, "live transcription", completed=False) as meter,
        connect(
            config.websocket_url,
            additional_headers={"Authorization": f"Bearer {config.api_key}"},
            open_timeout=config.session_ready_timeout_s,
            close_timeout=2,
            max_size=2**22,
        ) as websocket,
    ):
        return run_live_session(
            websocket,
            audio_queue,
            stop_event,
            config,
            on_delta,
            cancel_event,
            meter,
        )
