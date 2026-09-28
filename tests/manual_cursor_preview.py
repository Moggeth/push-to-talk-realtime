"""Offline animation preview and rendering benchmark; no input hooks or API calls."""

import math
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cursor_indicator import (
    CursorIndicatorSnapshot,
    IndicatorAnimator,
    render_indicator_image,
)


def main():
    output = Path(__file__).resolve().parents[1] / "output"
    output.mkdir(exist_ok=True)
    animator = IndicatorAnimator()
    frames = []
    costs = []
    samples = []
    entry_samples = []
    for index in range(600):
        now = index / 120
        mode = "raw" if now < 0.8 else "tidy" if now < 1.6 else "fun"
        activity = "recording" if now < 2.4 else "transcribing" if now < 3.2 else "rewriting"
        color = (220, 53, 69, 255) if now < 2.4 else (255, 166, 0, 255)
        if now >= 3.2:
            color = (210, 65, 170, 255)
        if now >= 4.1:
            activity, color = "success", (40, 167, 69, 255)
        snapshot = CursorIndicatorSnapshot(
            now < 4.45,
            color,
            1 if now < 2.4 else 2.6,
            mode=mode,
            activity=activity,
            audio_level=(math.sin(now * 13) + 1) / 2,
        )
        started = time.perf_counter()
        visual = animator.update(snapshot, now)
        rendered = (
            render_indicator_image(
                visual.frame,
                visual.color,
                opacity=visual.opacity,
                mode=visual.mode,
                previous_mode=visual.previous_mode,
                mode_mix=visual.mode_mix,
                activity=visual.activity,
            )
            if visual.visible
            else Image.new("RGBA", (88, 88))
        )
        costs.append(time.perf_counter() - started)
        if index in (2, 6, 12, 16, 24, 34):
            entry = Image.new("RGBA", (132, 132), (28, 30, 32, 255))
            entry.alpha_composite(rendered, (22, 12))
            ImageDraw.Draw(entry).text((12, 108), f"{now * 1000:.0f} ms", fill="white")
            entry_samples.append(entry)
        if index % 4 == 0:
            canvas = Image.new("RGBA", (176, 176), (28, 30, 32, 255))
            canvas.alpha_composite(rendered, (44, 44))
            frames.append(canvas.convert("RGB"))
        if index in (60, 150, 250, 340, 430, 510):
            sample = Image.new("RGBA", (176, 200), (28, 30, 32, 255))
            sample.alpha_composite(rendered, (44, 44))
            ImageDraw.Draw(sample).text((12, 170), f"{activity} / {mode}", fill="white")
            samples.append(sample)
    frames[0].save(
        output / "cursor-preview.gif", save_all=True, append_images=frames[1:], duration=33, loop=0
    )
    sheet = Image.new("RGBA", (176 * len(samples), 200))
    for index, sample in enumerate(samples):
        sheet.paste(sample, (index * 176, 0))
    sheet.save(output / "cursor-preview.png")
    entry_sheet = Image.new("RGBA", (132 * len(entry_samples), 132))
    for index, sample in enumerate(entry_samples):
        entry_sheet.paste(sample, (index * 132, 0))
    entry_sheet.save(output / "cursor-entry-preview.png")
    print(
        f"600 frames: mean={sum(costs) / len(costs) * 1000:.2f}ms "
        f"p95={sorted(costs)[569] * 1000:.2f}ms; 120Hz budget=8.33ms"
    )


if __name__ == "__main__":
    main()
