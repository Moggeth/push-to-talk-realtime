from dataclasses import replace

import pytest

from cursor_indicator import (
    CursorIndicatorSnapshot,
    IndicatorAnimator,
    JobView,
    TerminalView,
    render_indicator_image,
)

RED = (220, 53, 69, 255)


def test_completion_does_not_change_recording_geometry():
    plain, overlap = IndicatorAnimator(), IndicatorAnimator()
    recording = CursorIndicatorSnapshot(True, RED)
    for index in range(150):
        now = index / 120
        snapshot = replace(
            recording,
            jobs=(JobView(1),) if now < 0.5 else (),
            terminals=(TerminalView(1, "success", 0.5),) if now >= 0.5 else (),
        )
        expected = plain.update(recording, now)
        actual = overlap.update(snapshot, now)
        assert actual.frame == expected.frame
        assert actual.color == expected.color
        assert actual.opacity == expected.opacity
        if 0.65 < now < 0.9:
            assert any(frame.color[1] > frame.color[0] for frame in actual.orbits)
        if now > 1.07:
            assert not actual.orbits
            assert actual.visible


def test_phase_change_is_not_completion_and_queue_survives_completion():
    animator = IndicatorAnimator()
    snapshot = CursorIndicatorSnapshot(True, RED, jobs=tuple(JobView(i) for i in range(5)))
    animator.update(snapshot, 0)
    visual = animator.update(snapshot, 0.1)
    assert visual.orbits[0].queued == 4
    snapshot = replace(snapshot, jobs=(JobView(0, "rewriting", "fun"), *snapshot.jobs[1:]))
    visual = animator.update(snapshot, 0.2)
    assert len(visual.orbits) == 1
    assert visual.orbits[0].split
    assert visual.orbits[0].mode == "fun"
    snapshot = replace(
        snapshot, jobs=snapshot.jobs[1:], terminals=(TerminalView(0, "success", 0.3),)
    )
    animator.update(snapshot, 0.3)
    visual = animator.update(snapshot, 0.5)
    assert len(visual.orbits) == 2
    assert visual.orbits[0].queued == 3
    assert visual.orbits[1].ticks > 0


def test_failure_is_not_green_and_unobserved_event_is_ignored():
    animator = IndicatorAnimator()
    snapshot = CursorIndicatorSnapshot(True, RED, jobs=(JobView(1),))
    animator.update(snapshot, 0)
    snapshot = replace(
        snapshot,
        jobs=(),
        terminals=(TerminalView(1, "error", 0.1), TerminalView(99, "success", 0.1)),
    )
    visual = animator.update(snapshot, 0.4)
    assert len(visual.orbits) == 1
    assert visual.orbits[0].failed
    assert visual.orbits[0].color[0] > visual.orbits[0].color[1]


@pytest.mark.parametrize("fps", [30, 60, 120, 144])
def test_completion_is_bounded_and_does_not_repeat(fps):
    animator = IndicatorAnimator()
    for index in range(fps * 2):
        now = index / fps
        snapshot = CursorIndicatorSnapshot(
            True,
            RED,
            jobs=(JobView(1),) if now < 0.5 else (),
            terminals=(TerminalView(1, "success", 0.5),) if now >= 0.5 else (),
        )
        visual = animator.update(snapshot, now)
        image = render_indicator_image(
            visual.frame, visual.color, opacity=visual.opacity, orbits=visual.orbits
        )
        bounds = image.getbbox()
        if bounds:
            assert min(bounds[:2]) >= 1
            assert max(bounds[2:]) <= 95
        if now > 1.1:
            assert not visual.orbits


def test_quiet_cancellation_fades_without_success():
    animator = IndicatorAnimator()
    snapshot = CursorIndicatorSnapshot(True, RED, jobs=(JobView(1),))
    animator.update(snapshot, 0)
    animator.update(snapshot, 0.25)
    visual = animator.update(replace(snapshot, jobs=()), 0.3)
    assert visual.orbits
    assert not visual.orbits[0].ticks
    assert not animator.update(replace(snapshot, jobs=()), 0.5).orbits


def test_snapshot_keeps_recording_source_and_job_metadata(monkeypatch):
    import push_to_talk_realtime as app

    state = app.SessionState(is_listening=True, active_audio_source=app.AUDIO_SOURCE_SYSTEM)
    state.indicator_jobs[1] = JobView(1, "rewriting", "fun")
    monkeypatch.setattr(app, "state", state)
    snapshot = app.cursor_indicator_snapshot()
    assert snapshot.activity == "recording"
    assert snapshot.color == app.TRAY_COLOR_SYSTEM_AUDIO_LISTENING
    assert snapshot.jobs == (JobView(1, "rewriting", "fun"),)


def test_idle_primary_uses_newest_job_not_an_older_rewrite(monkeypatch):
    import push_to_talk_realtime as app

    state = app.SessionState(is_transcribing=True, is_post_processing=True)
    state.indicator_jobs = {
        1: JobView(1, "rewriting", "fun"),
        2: JobView(2, "transcribing", "tidy"),
    }
    monkeypatch.setattr(app, "state", state)
    snapshot = app.cursor_indicator_snapshot()
    assert snapshot.activity == "transcribing"
    assert snapshot.mode == "tidy"
    assert snapshot.color == app.TRAY_COLOR_TRANSCRIBING
