from __future__ import annotations

import math

from PIL import Image

from cursor_indicator import (
    INDICATOR_IDLE_POLL_FPS,
    INDICATOR_SIZE,
    INDICATOR_SUPERSAMPLE_SCALE,
    INDICATOR_TARGET_FPS,
    CursorIndicatorSnapshot,
    IndicatorAnimator,
    color_hex,
    indicator_frame,
    muted_color_hex,
    premultiplied_bgra_bytes,
    render_indicator_image,
)

MICROPHONE_COLOR = (220, 53, 69, 255)
TRANSCRIBING_COLOR = (255, 166, 0, 255)


def test_indicator_frame_rotates_and_gently_pulses():
    first = indicator_frame(0.0)
    later = indicator_frame(0.5)

    assert first.arc_start != later.arc_start
    assert 23.5 <= first.radius <= 26.5
    assert 23.5 <= later.radius <= 26.5
    assert 91.0 <= later.arc_extent <= 119.0
    assert math.isfinite(later.arc_width)


def test_indicator_targets_high_refresh_and_faster_processing_motion():
    normal = indicator_frame(0.1)
    processing = indicator_frame(0.1, motion_speed=2.6)

    assert INDICATOR_TARGET_FPS == 120
    assert INDICATOR_IDLE_POLL_FPS == 30
    assert math.isclose(processing.arc_start - normal.arc_start, 30.4)


def test_indicator_colors_preserve_source_identity():
    system_audio = (0, 123, 255, 255)

    assert color_hex(MICROPHONE_COLOR) == "#dc3545"
    assert color_hex(system_audio) == "#007bff"
    assert muted_color_hex(MICROPHONE_COLOR) == "#5c161d"


def test_indicator_animator_expands_from_cursor_on_entry():
    animator = IndicatorAnimator()
    recording = CursorIndicatorSnapshot(True, MICROPHONE_COLOR)

    first = animator.update(recording, 0.0)
    middle = animator.update(recording, 0.08)
    settled = animator.update(recording, 0.16)

    assert first.visible is True
    assert first.opacity == 0.0
    assert first.frame.radius < middle.frame.radius < settled.frame.radius
    assert middle.opacity < settled.opacity == 1.0


def test_indicator_animator_preserves_traveler_phase_across_transcription():
    animator = IndicatorAnimator()
    recording = CursorIndicatorSnapshot(True, MICROPHONE_COLOR)
    transcribing = CursorIndicatorSnapshot(True, TRANSCRIBING_COLOR, motion_speed=2.6)
    animator.update(recording, 0.0)
    before = animator.update(recording, 0.2)

    crossing = animator.update(transcribing, 0.201)
    phase_delta = (crossing.frame.arc_start - before.frame.arc_start) % 360.0
    settled = animator.update(transcribing, 0.3)

    assert 0.0 < phase_delta < 1.0
    assert crossing.color != MICROPHONE_COLOR
    assert crossing.color != TRANSCRIBING_COLOR
    assert all(
        abs(actual - target) <= 2
        for actual, target in zip(settled.color, TRANSCRIBING_COLOR, strict=True)
    )


def test_indicator_animator_contracts_into_cursor_after_completion():
    animator = IndicatorAnimator()
    recording = CursorIndicatorSnapshot(True, MICROPHONE_COLOR)
    hidden = CursorIndicatorSnapshot(False, MICROPHONE_COLOR)
    animator.update(recording, 0.0)
    settled = animator.update(recording, 0.16)

    outro_start = animator.update(hidden, 0.17)
    retracting = animator.update(hidden, 0.27)
    finished = animator.update(hidden, 0.38)

    assert outro_start.visible is True
    assert retracting.visible is True
    assert retracting.frame.radius < settled.frame.radius
    assert 0.0 < retracting.opacity < 1.0
    assert finished.visible is False


def test_supersampled_indicator_has_smooth_alpha_edges():
    image = render_indicator_image(indicator_frame(0.25), (220, 53, 69, 255))
    alpha_values = set(image.getchannel("A").getdata())

    assert image.size == (INDICATOR_SIZE, INDICATOR_SIZE)
    assert INDICATOR_SUPERSAMPLE_SCALE == 4
    assert 0 in alpha_values
    assert 255 in alpha_values
    assert any(0 < alpha < 255 for alpha in alpha_values)


def test_premultiplied_bgra_bytes_scale_color_channels_by_alpha():
    image = Image.new("RGBA", (1, 1), (200, 100, 50, 128))

    assert premultiplied_bgra_bytes(image) == bytes((25, 50, 100, 128))
