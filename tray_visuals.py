"""Pure rendering helpers and visual constants for the system tray icon."""

from __future__ import annotations

from PIL import Image, ImageDraw

TRAY_ICON_SIZE = 64
TRAY_COLOR_READY = (46, 160, 67, 255)
TRAY_COLOR_LISTENING = (220, 53, 69, 255)
TRAY_COLOR_SYSTEM_AUDIO_LISTENING = (0, 123, 255, 255)
TRAY_COLOR_TRANSCRIBING = (255, 166, 0, 255)
TRAY_COLOR_POST_PROCESSING = (186, 85, 211, 255)
TRAY_ACTIVITY_READY = "ready"
TRAY_ACTIVITY_LISTENING = "listening"
TRAY_ACTIVITY_TRANSCRIBING = "transcribing"
TRAY_ACTIVITY_FINALIZING = "finalizing"
TRAY_ACTIVITY_POST_PROCESSING = "post_processing"
TRAY_SPINNER_STEPS = 16
TRAY_SPINNER_SWEEP_DEG = 64


def blend_tray_colors(
    start: tuple[int, int, int, int],
    end: tuple[int, int, int, int],
    amount: float,
) -> tuple[int, int, int, int]:
    progress = min(1.0, max(0.0, amount))
    return tuple(round(a + (b - a) * progress) for a, b in zip(start, end, strict=True))


def create_tray_icon_image(
    size: int = TRAY_ICON_SIZE,
    color: tuple[int, int, int, int] = TRAY_COLOR_READY,
    spinner_step: int | None = None,
    activity: str = TRAY_ACTIVITY_READY,
) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    outer_bounds = (1, 1, size - 2, size - 2)
    draw.ellipse(outer_bounds, fill=color)

    sheen = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sheen_draw = ImageDraw.Draw(sheen)
    edge_width = max(2, int(size * 0.055))
    sheen_draw.arc(
        outer_bounds,
        start=205,
        end=335,
        fill=(255, 255, 255, 72),
        width=edge_width,
    )
    sheen_draw.arc(
        outer_bounds,
        start=20,
        end=145,
        fill=(8, 12, 18, 58),
        width=edge_width,
    )
    image = Image.alpha_composite(image, sheen)
    draw = ImageDraw.Draw(image)

    processing = activity in {
        TRAY_ACTIVITY_TRANSCRIBING,
        TRAY_ACTIVITY_POST_PROCESSING,
    }
    if not processing:
        inset = int(size * 0.29)
        radius = max(2, int(size * 0.045))
        draw.rounded_rectangle(
            (inset, inset, size - inset, size - inset),
            radius=radius,
            fill=(255, 255, 255, 255),
        )
        return image

    inner_inset = int(size * 0.225)
    draw.ellipse(
        (inner_inset, inner_inset, size - inner_inset, size - inner_inset),
        fill=(25, 29, 35, 255),
    )
    ring_inset = int(size * 0.075)
    ring_width = max(4, int(size * 0.105))
    step = spinner_step or 0
    step_degrees = 360 / TRAY_SPINNER_STEPS
    start_angle = int((step % TRAY_SPINNER_STEPS) * step_degrees)

    orbit = Image.new("RGBA", image.size, (0, 0, 0, 0))
    orbit_draw = ImageDraw.Draw(orbit)
    ring_bounds = (ring_inset, ring_inset, size - ring_inset, size - ring_inset)
    orbit_draw.arc(
        ring_bounds,
        start=0,
        end=359,
        fill=(255, 255, 255, 58),
        width=ring_width,
    )
    orbit_draw.arc(
        ring_bounds,
        start=start_angle - 48,
        end=start_angle + 8,
        fill=(255, 255, 255, 128),
        width=ring_width,
    )
    orbit_draw.arc(
        ring_bounds,
        start=start_angle,
        end=start_angle + TRAY_SPINNER_SWEEP_DEG,
        fill=(255, 255, 255, 248),
        width=ring_width,
    )
    image = Image.alpha_composite(image, orbit)
    draw = ImageDraw.Draw(image)

    if activity == TRAY_ACTIVITY_TRANSCRIBING:
        patterns = ((12, 22, 16), (18, 13, 23), (23, 17, 12), (16, 23, 18))
        heights = patterns[(step // 2) % len(patterns)]
        bar_width = max(4, int(size * 0.075))
        gap = max(3, int(size * 0.06))
        total_width = bar_width * 3 + gap * 2
        left = (size - total_width) // 2
        center_y = size // 2
        for index, height in enumerate(heights):
            x = left + index * (bar_width + gap)
            draw.rounded_rectangle(
                (x, center_y - height // 2, x + bar_width, center_y + height // 2),
                radius=bar_width // 2,
                fill=(255, 248, 229, 255),
            )
    else:
        center = size // 2
        outer = int(size * (0.17 if step % 4 in (1, 2) else 0.155))
        inner = max(3, int(size * 0.052))
        draw.polygon(
            (
                (center, center - outer),
                (center + inner, center - inner),
                (center + outer, center),
                (center + inner, center + inner),
                (center, center + outer),
                (center - inner, center + inner),
                (center - outer, center),
                (center - inner, center - inner),
            ),
            fill=(255, 248, 255, 255),
        )
    return image
