"""Opt-in native layout and editor smoke test; no audio or API requests."""

import sys
import tkinter as tk
from pathlib import Path
from time import perf_counter, sleep

from PIL import Image, ImageDraw, ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import push_to_talk_realtime as app
from cursor_indicator import indicator_frame, render_indicator_image
from settings_window import SettingsWindow

output = Path(__file__).resolve().parents[1] / "output"
output.mkdir(exist_ok=True)
root = tk.Tk()
root.attributes("-topmost", True)
payload = app.settings_window_payload()
window = SettingsWindow(root, payload)
root.update()
notebook = root.winfo_children()[0]
for geometry in ("700x610", "560x480"):
    root.geometry(geometry)
    root.update()
    for index in range(4):
        notebook.select(index)
        root.update()
        page = notebook.nametowidget(notebook.select())
        for child in page.winfo_children():
            assert child.winfo_x() >= 0 and child.winfo_y() >= 0
            assert child.winfo_x() + child.winfo_width() <= page.winfo_width()
            assert child.winfo_y() + child.winfo_height() <= page.winfo_height()
        if index == 1 and geometry == "700x610":
            sleep(0.4)
            root.update()
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(
                output / "settings-tidy.png"
            )
window.editors["fun"].delete("1.0", "end")
window.editors["fun"].insert("1.0", "Test instructions")
window.save()
assert window.result["profiles"]["fun"]["instructions"] == "Test instructions"
assert window.result["profiles"]["tidy"] == payload["profiles"]["tidy"]

sheet = Image.new("RGB", (360, 120), "#202124")
draw = ImageDraw.Draw(sheet)
started = perf_counter()
for i in range(600):
    render_indicator_image(
        indicator_frame(i / 120), (235, 65, 90, 255), mode=("raw", "tidy", "fun")[i % 3]
    )
elapsed = perf_counter() - started
for index, mode in enumerate(("raw", "tidy", "fun")):
    image = render_indicator_image(indicator_frame(0.4), (235, 65, 90, 255), mode=mode)
    sheet.paste(image, (index * 120 + 16, 0), image)
    draw.text((index * 120 + 42, 98), mode.title(), fill="white")
sheet.save(output / "mode-shapes.png")
print(
    f"PASS: four tabs at both sizes; independent editor save; render mean {elapsed / 600 * 1000:.3f} ms"
)
