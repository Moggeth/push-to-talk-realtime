from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import push_to_talk_realtime as push_to_talk  # noqa: E402


class ThreadRecorder:
    instances: ClassVar[list[ThreadRecorder]] = []

    def __init__(self, target=None, args=(), daemon=None, kwargs=None) -> None:
        self.target = target
        self.args = args
        self.daemon = daemon
        self.kwargs = kwargs or {}
        self.started = False
        type(self).instances.append(self)

    def start(self) -> None:
        self.started = True


class HotkeySessionStartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_openai_key = push_to_talk.OPENAI_API_KEY
        with push_to_talk.state.lock:
            push_to_talk.state.is_listening = False
            push_to_talk.state.is_transcribing = False
            push_to_talk.state.session_start_pending = False
            push_to_talk.state.pending_start_hotkey_kind = ""
            push_to_talk.state.pending_start_hotkey_tokens = ()
            push_to_talk.state.pending_start_stop_hotkey_tokens = ()
            push_to_talk.state.pending_start_stop_requested = False
            push_to_talk.state.should_stop = False
            push_to_talk.state.toggle_mode_enabled = False
            push_to_talk.state.post_processing_enabled = False
            push_to_talk.state.is_post_processing = False
            push_to_talk.state.post_processing_session_count = 0
            push_to_talk.state.post_process_model = "gpt-5.6-luna"
            push_to_talk.state.post_process_instruction_profile = "clean_up"
            push_to_talk.state.transcription_engine = push_to_talk.TRANSCRIPTION_ENGINE_RECORDED
            push_to_talk.state.recorded_transcription_model = "gpt-transcribe"
            push_to_talk.state.active_hotkey = ""
            push_to_talk.state.active_hotkey_kind = ""
            push_to_talk.state.active_hotkey_tokens = ()
            push_to_talk.state.active_stop_hotkey_tokens = ()
            push_to_talk.state.dictation_hotkey_kind = push_to_talk.HOTKEY_KIND_KEYBOARD
            push_to_talk.state.dictation_hotkey_tokens = (push_to_talk.DEFAULT_HOTKEY_DICTATION,)
            push_to_talk.state.dictation_hotkey_label = push_to_talk.format_hotkey_tokens(
                push_to_talk.state.dictation_hotkey_tokens
            )
            push_to_talk.state.dictation_device_index = None
            push_to_talk.state.dictation_device_label = push_to_talk.DEFAULT_DEVICE_LABEL
            push_to_talk.state.worklog_device_index = None
            push_to_talk.state.worklog_device_label = push_to_talk.DEFAULT_DEVICE_LABEL
            push_to_talk.state.worklog_press_time = 0.0
            push_to_talk.state.last_worklog_tap_time = 0.0
            push_to_talk.state.worklog_double_tap_active = False
            push_to_talk.state.worklog_is_pressed = False
            push_to_talk.state.pressed_keys.clear()
            push_to_talk.state.shift_keys_down.clear()
            push_to_talk.state.session_counter = 0
            push_to_talk.state.next_output_session_id = 1
            push_to_talk.state.transcribing_session_count = 0

    def tearDown(self) -> None:
        push_to_talk.OPENAI_API_KEY = self.original_openai_key
        ThreadRecorder.instances.clear()
        with push_to_talk.state.lock:
            push_to_talk.state.is_listening = False
            push_to_talk.state.is_transcribing = False
            push_to_talk.state.session_start_pending = False
            push_to_talk.state.pending_start_hotkey_kind = ""
            push_to_talk.state.pending_start_hotkey_tokens = ()
            push_to_talk.state.pending_start_stop_hotkey_tokens = ()
            push_to_talk.state.pending_start_stop_requested = False
            push_to_talk.state.should_stop = False

    def test_repeated_dictation_keydown_only_queues_one_session(self) -> None:
        key = SimpleNamespace(name=push_to_talk.state.dictation_hotkey_tokens[0].lower())

        with patch.object(push_to_talk.threading, "Thread", ThreadRecorder):
            push_to_talk.on_press(key)
            push_to_talk.on_press(key)

        self.assertEqual(1, len(ThreadRecorder.instances))
        self.assertTrue(ThreadRecorder.instances[0].started)
        with push_to_talk.state.lock:
            self.assertTrue(push_to_talk.state.session_start_pending)

    def test_release_during_pending_start_is_remembered(self) -> None:
        key = SimpleNamespace(name=push_to_talk.state.dictation_hotkey_tokens[0].lower())

        with patch.object(push_to_talk.threading, "Thread", ThreadRecorder):
            push_to_talk.on_press(key)
            push_to_talk.on_release(key)

        with push_to_talk.state.lock:
            self.assertTrue(push_to_talk.state.session_start_pending)
            self.assertTrue(push_to_talk.state.pending_start_stop_requested)

    def test_shift_modified_dictation_stops_on_dictation_key_only(self) -> None:
        key_tokens = ("SHIFT", *push_to_talk.state.dictation_hotkey_tokens)

        self.assertEqual(
            push_to_talk.state.dictation_hotkey_tokens,
            push_to_talk.session_stop_hotkey_tokens(push_to_talk.MODE_DICTATION, key_tokens),
        )

    def test_start_listening_honors_release_that_arrived_during_start(self) -> None:
        push_to_talk.OPENAI_API_KEY = "test-key"
        key_tokens = push_to_talk.state.dictation_hotkey_tokens
        with push_to_talk.state.lock:
            push_to_talk.state.session_start_pending = True
            push_to_talk.state.pending_start_hotkey_kind = push_to_talk.HOTKEY_KIND_KEYBOARD
            push_to_talk.state.pending_start_hotkey_tokens = key_tokens
            push_to_talk.state.pending_start_stop_requested = True

        with (
            patch.object(push_to_talk, "enforce_transcription_engine_dependencies"),
            patch.object(
                push_to_talk,
                "start_recorder_with_fallback",
                return_value=(True, None, push_to_talk.DEFAULT_DEVICE_LABEL),
            ),
            patch.object(push_to_talk, "transcribe_audio", return_value=""),
            patch.object(push_to_talk, "maybe_beep"),
            patch.object(push_to_talk, "log"),
        ):
            push_to_talk.start_listening(
                push_to_talk.MODE_DICTATION,
                push_to_talk.HOTKEY_DICTATION,
                push_to_talk.HOTKEY_KIND_KEYBOARD,
                key_tokens,
                None,
                push_to_talk.DEFAULT_DEVICE_LABEL,
            )

        with push_to_talk.state.lock:
            self.assertFalse(push_to_talk.state.session_start_pending)
            self.assertFalse(push_to_talk.state.pending_start_stop_requested)
            self.assertFalse(push_to_talk.state.is_listening)

    def test_dictation_can_start_while_previous_audio_is_still_transcribing(self) -> None:
        key = SimpleNamespace(name=push_to_talk.state.dictation_hotkey_tokens[0].lower())
        with push_to_talk.state.lock:
            push_to_talk.state.is_transcribing = True
            push_to_talk.state.transcribing_session_count = 1

        with patch.object(push_to_talk.threading, "Thread", ThreadRecorder):
            push_to_talk.on_press(key)

        self.assertEqual(1, len(ThreadRecorder.instances))
        self.assertTrue(ThreadRecorder.instances[0].started)
        with push_to_talk.state.lock:
            self.assertTrue(push_to_talk.state.session_start_pending)

    def test_start_listening_clears_pending_flag_when_api_key_missing(self) -> None:
        push_to_talk.OPENAI_API_KEY = ""
        with push_to_talk.state.lock:
            push_to_talk.state.session_start_pending = True

        push_to_talk.start_listening(
            push_to_talk.MODE_DICTATION,
            push_to_talk.HOTKEY_DICTATION,
            push_to_talk.HOTKEY_KIND_KEYBOARD,
            push_to_talk.state.dictation_hotkey_tokens,
            None,
            push_to_talk.DEFAULT_DEVICE_LABEL,
        )

        with push_to_talk.state.lock:
            self.assertFalse(push_to_talk.state.session_start_pending)

    def test_post_processing_failure_falls_back_to_original_transcript(self) -> None:
        push_to_talk.OPENAI_API_KEY = "test-key"
        key_tokens = push_to_talk.state.dictation_hotkey_tokens
        pasted = []
        archive_events = []
        with push_to_talk.state.lock:
            push_to_talk.state.session_start_pending = True
            push_to_talk.state.pending_start_hotkey_kind = push_to_talk.HOTKEY_KIND_KEYBOARD
            push_to_talk.state.pending_start_hotkey_tokens = key_tokens
            push_to_talk.state.pending_start_stop_requested = True
            push_to_talk.state.post_processing_enabled = True
            push_to_talk.state.dictation_history_enabled = False

        with (
            patch.object(push_to_talk, "enforce_transcription_engine_dependencies"),
            patch.object(
                push_to_talk,
                "start_recorder_with_fallback",
                return_value=(True, None, push_to_talk.DEFAULT_DEVICE_LABEL),
            ),
            patch.object(push_to_talk, "transcribe_audio", return_value="raw transcript"),
            patch.object(
                push_to_talk,
                "archive_raw_transcript",
                side_effect=lambda **kwargs: archive_events.append(("raw", kwargs["raw_text"]))
                or 1,
            ),
            patch.object(
                push_to_talk,
                "archive_final_transcript",
                side_effect=lambda entry_id, **kwargs: archive_events.append(
                    ("final", entry_id, kwargs["final_text"], kwargs["post_process_status"])
                ),
            ),
            patch.object(
                push_to_talk,
                "post_process_transcript",
                side_effect=lambda text, *_args: archive_events.append(("post", text))
                or (_ for _ in ()).throw(RuntimeError("temporary API failure")),
            ),
            patch.object(
                push_to_talk,
                "paste_text",
                side_effect=lambda text, _target: pasted.append(text) or True,
            ),
            patch.object(push_to_talk, "maybe_beep"),
            patch.object(push_to_talk, "log"),
        ):
            push_to_talk.start_listening(
                push_to_talk.MODE_DICTATION,
                push_to_talk.HOTKEY_DICTATION,
                push_to_talk.HOTKEY_KIND_KEYBOARD,
                key_tokens,
                None,
                push_to_talk.DEFAULT_DEVICE_LABEL,
            )

        self.assertEqual(["raw transcript."], pasted)
        self.assertEqual(
            [
                ("raw", "raw transcript"),
                ("post", "raw transcript"),
                ("final", 1, "raw transcript.", "failed"),
            ],
            archive_events,
        )
        self.assertFalse(push_to_talk.state.is_post_processing)
        self.assertEqual(0, push_to_talk.state.post_processing_session_count)


if __name__ == "__main__":
    unittest.main()
