"""Synthetic concurrent recording/transcription render, with no hooks or API calls."""

import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cursor_indicator import (
    CursorIndicatorSnapshot,
    IndicatorAnimator,
    JobView,
    TerminalView,
    render_indicator_image,
)


def main():
    output = Path(__file__).resolve().parents[1] / "output"
    output.mkdir(exist_ok=True)
    animator = IndicatorAnimator()
    frames, samples, costs = [], [], []
    for index in range(480):
        now = index / 120
        jobs = (JobView(1),) if 0.5 <= now < 2 else ()
        terminals = (TerminalView(1, "success", 2),) if now >= 2 else ()
        snapshot = CursorIndicatorSnapshot(
            now < 3.5, (220, 53, 69, 255), jobs=jobs, terminals=terminals
        )
        start = time.perf_counter()
        visual = animator.update(snapshot, now)
        image = render_indicator_image(
            visual.frame, visual.color, opacity=visual.opacity, orbits=visual.orbits
        )
        costs.append(time.perf_counter() - start)
        canvas = Image.new("RGBA", (160, 180), (28, 30, 32, 255))
        canvas.alpha_composite(image, (32, 30))
        draw = ImageDraw.Draw(canvas)
        draw.polygon([(80, 74), (80, 84), (83, 81), (86, 81)], fill="white")
        draw.text((12, 150), f"{now:.2f}s", fill="white")
        if index % 2 == 0:
            frames.append(canvas.convert("RGB"))
        if index in (36, 120, 246, 266, 284, 336):
            samples.append(canvas)
    frames[0].save(
        output / "cursor-overlap.gif", save_all=True, append_images=frames[1:], duration=17, loop=0
    )
    sheet = Image.new("RGBA", (160 * len(samples), 180))
    for index, canvas in enumerate(samples):
        sheet.paste(canvas, (160 * index, 0))
    sheet.save(output / "cursor-overlap.png")
    print(
        f"480 frames: mean {sum(costs) / len(costs) * 1000:.3f} ms; p95 {sorted(costs)[455] * 1000:.3f} ms (120 Hz budget 8.33 ms)"
    )


if __name__ == "__main__":
    main()
