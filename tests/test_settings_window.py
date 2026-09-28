import json

import pytest

import push_to_talk_realtime as app
from cursor_indicator import (
    CursorIndicatorSnapshot,
    IndicatorAnimator,
    indicator_frame,
    render_indicator_image,
)


@pytest.fixture
def state(monkeypatch):
    state = app.SessionState()
    monkeypatch.setattr(app, "state", state)
    monkeypatch.setattr(app, "rebuild_tray_menu", lambda: None)
    monkeypatch.setattr(app, "log", lambda *_: None)
    monkeypatch.setattr(app, "realtime_dependency_error", lambda: None)
    return state


def test_legacy_profiles_migrate_to_editor_without_mutating_state(state):
    state.post_process_model = "gpt-5.6-terra"
    state.post_process_instruction_profile = "concise"
    payload = app.settings_window_payload()
    assert payload["profiles"]["tidy"]["model"] == "gpt-5.6-terra"
    assert payload["profiles"]["tidy"]["instructions"] == app.post_process_instructions("concise")
    assert (
        payload["profiles"]["fun"]["instructions"] == app.POST_PROCESS_INSTRUCTION_PROFILES["fun"]
    )
    assert state.rewrite_profiles == {}


def test_independent_profiles_and_feedback_survive_reload(state, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "SETTINGS_PATH", tmp_path / "settings.json")
    payload = app.settings_window_payload()
    payload["profiles"]["tidy"] = {
        "model": "gpt-5.6-luna",
        "instructions": "Keep technical terms exact.",
    }
    payload["profiles"]["fun"] = {"model": "gpt-5.6-sol", "instructions": "Add appropriate emojis."}
    payload["flags"]["show_mode_labels"] = True
    payload["suffix"] = 2
    payload["transcription"] = "GPT Live Transcribe"
    app.apply_settings_window_result(payload)
    saved = json.loads(app.SETTINGS_PATH.read_text())
    monkeypatch.setattr(app, "load_settings_from_disk", lambda: saved)
    state.rewrite_profiles = {}
    app.apply_persisted_settings()
    assert state.rewrite_profiles == payload["profiles"]
    assert state.show_mode_labels
    assert state.paste_suffix_mode == app.SUFFIX_NEWLINE
    assert state.transcription_engine == app.TRANSCRIPTION_ENGINE_LIVE


def test_invalid_profile_leaves_preferences_unchanged(state):
    payload = app.settings_window_payload()
    payload["profiles"]["fun"]["instructions"] = " "
    with pytest.raises(ValueError):
        app.apply_settings_window_result(payload)
    assert state.rewrite_profiles == {}


def test_mode_shapes_are_distinct_without_text():
    frames = [
        render_indicator_image(indicator_frame(0.4), (230, 40, 70, 255), mode=mode)
        for mode in ("raw", "tidy", "fun")
    ]
    assert len({image.tobytes() for image in frames}) == 3
    for image in frames:
        x, y, right, bottom = image.getbbox()
        assert 0 < x < right < image.width
        assert 0 < y < bottom < image.height


def test_mode_switch_keeps_phase_and_intro_clock():
    animator = IndicatorAnimator()
    animator.update(CursorIndicatorSnapshot(True, (230, 40, 70, 255)), 0)
    before = animator.update(CursorIndicatorSnapshot(True, (230, 40, 70, 255)), 1)
    after = animator.update(CursorIndicatorSnapshot(True, (230, 40, 70, 255), mode="fun"), 1.01)
    assert after.mode == "fun"
    before_head = (before.frame.arc_start + before.frame.arc_extent) % 360
    after_head = (after.frame.arc_start + after.frame.arc_extent) % 360
    assert after_head == pytest.approx((before_head + 1.9) % 360)
    assert after.opacity == 1
    assert animator.intro_started_at == 0
