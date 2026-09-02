from __future__ import annotations

import math

from PIL import Image

from cursor_indicator import (
    INDICATOR_IDLE_POLL_FPS,
    INDICATOR_SIZE,
    INDICATOR_SUPERSAMPLE_SCALE,
    INDICATOR_TARGET_FPS,
    color_hex,
    indicator_frame,
    muted_color_hex,
    premultiplied_bgra_bytes,
    render_indicator_image,
)


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
    microphone = (220, 53, 69, 255)
    system_audio = (0, 123, 255, 255)

    assert color_hex(microphone) == "#dc3545"
    assert color_hex(system_audio) == "#007bff"
    assert muted_color_hex(microphone) == "#5c161d"


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
