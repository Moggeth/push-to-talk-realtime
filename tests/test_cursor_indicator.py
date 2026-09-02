from __future__ import annotations

import math

from cursor_indicator import color_hex, indicator_frame, muted_color_hex


def test_indicator_frame_rotates_and_gently_pulses():
    first = indicator_frame(0.0)
    later = indicator_frame(0.5)

    assert first.arc_start != later.arc_start
    assert 23.5 <= first.radius <= 26.5
    assert 23.5 <= later.radius <= 26.5
    assert 91.0 <= later.arc_extent <= 119.0
    assert math.isfinite(later.arc_width)


def test_indicator_colors_preserve_source_identity():
    microphone = (220, 53, 69, 255)
    system_audio = (0, 123, 255, 255)

    assert color_hex(microphone) == "#dc3545"
    assert color_hex(system_audio) == "#007bff"
    assert muted_color_hex(microphone) == "#5c161d"
