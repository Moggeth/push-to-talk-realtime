from unittest.mock import Mock

import pytest

from mouse_gestures import GestureMonitor, VerticalShake
from text_processing import prepare_clipboard_text


def test_deliberate_vertical_shake_toggles_once():
    detector = VerticalShake()
    results = [detector.feed(100, y, i * 0.1) for i, y in enumerate((100, 160, 90, 160, 90))]
    assert results == [False, False, False, False, True]
    assert not any(detector.feed(100, 90 if i % 2 else 160, 0.5 + i * 0.1) for i in range(40))
    for i in range(6):
        detector.feed(100, 90, 4.5 + i * 0.1)
    assert any(detector.feed(100, y, 5.1 + i * 0.1) for i, y in enumerate((150, 80, 150, 80)))


@pytest.mark.parametrize(
    "points,step",
    [
        ([(i * 60, 100) for i in range(10)], 0.1),
        ([(100, i * 60) for i in range(10)], 0.1),
        ([(100, 100 + (i % 2) * 12) for i in range(20)], 0.03),
        ([(100, 100 + (i % 2) * 60) for i in range(10)], 0.4),
        ([(i * 60, (i % 2) * 60) for i in range(10)], 0.1),
    ],
)
def test_normal_motion_tremor_horizontal_and_slow_movement_do_not_toggle(points, step):
    detector = VerticalShake()
    assert not any(detector.feed(x, y, i * step) for i, (x, y) in enumerate(points))


def test_gesture_window_starts_with_motion_not_start_of_recording():
    detector = VerticalShake()
    detector.feed(100, 100, 0)
    detector.feed(100, 100, 50.8)
    results = [detector.feed(100, y, 50.9 + i * 0.1) for i, y in enumerate((160, 90, 160, 90))]
    assert results == [False, False, False, True]


def test_monitor_never_reads_pointer_when_not_held_and_resets_between_sessions():
    token = [None]
    position = Mock(return_value=(100, 100))
    toggle = Mock()
    monitor = GestureMonitor(lambda: token[0], toggle, Mock(), position)
    assert not monitor.poll(0)
    position.assert_not_called()
    token[0] = 1
    for i, y in enumerate((100, 160, 90)):
        position.return_value = (100, y)
        monitor.poll(i * 0.1)
    token[0] = 2
    for i, y in enumerate((160, 90, 160)):
        position.return_value = (100, y)
        monitor.poll(0.3 + i * 0.1)
    toggle.assert_not_called()
    for i, y in enumerate((90, 160)):
        position.return_value = (100, y)
        monitor.poll(0.6 + i * 0.1)
    toggle.assert_called_once_with(2)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("First thought.", "- First thought.\n"),
        ("- Already a bullet", "- Already a bullet\n"),
        ("* A thought\ncontinued here", "- A thought continued here\n"),
        ("\u2022 Hello", "- Hello\n"),
        ("   ", ""),
    ],
)
def test_one_capture_one_bullet_with_pasted_newline(text, expected):
    assert prepare_clipboard_text(text, bullet_mode=True) == expected


def test_bullets_do_not_change_plain_output():
    assert prepare_clipboard_text("Hello") == "Hello "


@pytest.fixture
def app_state(monkeypatch):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "state", app.SessionState())
    monkeypatch.setattr(app, "log", Mock())
    monkeypatch.setattr(app, "refresh_tray_menu", Mock())
    monkeypatch.setattr(app, "update_tray_status", Mock())
    monkeypatch.setattr(app, "shutdown_event", Mock(is_set=lambda: False))
    app.state.is_listening = True
    app.state.mode = app.MODE_DICTATION
    app.state.active_session_id = 12
    app.state.active_stop_hotkey_tokens = ("F13",)
    app.state.pressed_keys = {"F13"}
    app.state.punctuation_terminal = False
    return app


@pytest.mark.parametrize("change", ["released", "stopped", "disabled", "worklog", "idle", "stale"])
def test_toggle_is_gated_and_revalidates_session_under_lock(app_state, change):
    app = app_state
    assert app.gesture_recording_token() == 12
    if change == "released":
        app.state.pressed_keys.clear()
    elif change == "stopped":
        app.state.should_stop = True
    elif change == "disabled":
        app.state.mouse_gesture_enabled = False
    elif change == "worklog":
        app.state.mode = app.MODE_WORKLOG
    elif change == "idle":
        app.state.is_listening = False
    elif change == "stale":
        app.state.active_session_id = 13
    app.toggle_bullet_mode(recording_token=12)
    assert not app.state.bullet_mode


def test_toggle_feedback_and_release_latching(app_state):
    app = app_state
    app.toggle_bullet_mode(recording_token=12)
    assert app.state.bullet_mode
    assert "\u2022" in app.cursor_indicator_snapshot().label
    captured = app.finish_capture_session(12)
    assert captured.bullet_mode
    app.toggle_bullet_mode()
    assert not app.state.bullet_mode
    assert captured.bullet_mode


def test_bullet_paste_and_raw_review_use_same_format(app_state, monkeypatch):
    app = app_state
    copy = Mock()
    send = Mock()
    monkeypatch.setattr(app.pyperclip, "copy", copy)
    monkeypatch.setattr(app.pyperclip, "paste", lambda: "- A thought\n")
    monkeypatch.setattr(app, "add_bullet_html", Mock(return_value=True))
    monkeypatch.setattr(app, "send_paste_shortcut", send)
    assert app.paste_text("A thought", bullet_mode=True)
    copy.assert_called_once_with("- A thought\n")
    send.assert_called_once_with()
    assert app.prepare_clipboard_text("raw thought", bullet_mode=True) == "- raw thought\n"


def test_worker_recovers_from_sampling_failure_without_input_injection():
    monitor = GestureMonitor(lambda: 1, Mock(), Mock(), Mock(side_effect=OSError("unavailable")))
    waits = []

    def wait(delay):
        waits.append(delay)
        monitor.stop_event.set()

    monitor.stop_event.wait = wait
    monitor._run()
    assert waits == [10]
    monitor.toggle.assert_not_called()
    monitor.log.assert_called_once()


def test_close_is_safe_when_thread_could_not_start():
    monitor = GestureMonitor(Mock(), Mock(), Mock())
    monitor.thread = Mock()
    monitor.thread.is_alive.return_value = False
    monitor.close()
    monitor.thread.join.assert_not_called()


def test_shift_release_does_not_disarm_held_record_button(app_state):
    app = app_state
    app.state.active_hotkey_tokens = ("SHIFT", "F13")
    assert app.gesture_recording_token() == 12


def test_gesture_setting_persists_but_bullet_mode_starts_off(app_state, monkeypatch, tmp_path):
    import json

    app = app_state
    path = tmp_path / "settings.json"
    monkeypatch.setattr(app, "SETTINGS_PATH", path)
    app.state.bullet_mode = True
    app.toggle_mouse_gesture()
    assert json.loads(path.read_text())["mouse_gesture_enabled"] is False
    app.state = app.SessionState()
    app.apply_persisted_settings()
    assert app.state.mouse_gesture_enabled is False
    assert app.state.bullet_mode is False
