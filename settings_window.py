"""Isolated native settings editor. JSON in/out keeps Tk off the tray thread."""

import json
import os
import platform
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


class SettingsWindow:
    def __init__(self, root, payload):
        self.root = root
        self.payload = payload
        self.result = None
        self.editors = {}
        self.models = {}
        self.flags = {}
        root.title("Push-to-talk settings")
        root.geometry("700x610")
        root.minsize(560, 480)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        style = ttk.Style(root)
        style.configure(".", font=("Segoe UI", 11))
        style.configure("TNotebook.Tab", padding=(18, 10))
        notebook = ttk.Notebook(root)
        notebook.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 8))
        recording = ttk.Frame(notebook, padding=20)
        notebook.add(recording, text="Recording")
        recording.columnconfigure(0, weight=1)
        ttk.Label(recording, text="Transcription model").grid(sticky="w")
        self.transcription = ttk.Combobox(
            recording, state="readonly", values=payload["transcription_options"]
        )
        self.transcription.set(payload["transcription"])
        self.transcription.grid(sticky="ew", pady=(6, 22))
        ttk.Label(recording, text="Microphone").grid(sticky="w")
        self.device = ttk.Combobox(recording, state="readonly", values=payload["devices"])
        self.device.set(payload["device"])
        self.device.grid(sticky="ew", pady=(6, 22))
        self.add_flag(recording, "toggle_mode_enabled", "Tap to start / stop")
        ttk.Label(recording, text="Paste suffix").grid(sticky="w", pady=(22, 6))
        self.suffix = ttk.Combobox(recording, state="readonly", values=["None", "Space", "Newline"])
        self.suffix.current(payload["suffix"])
        self.suffix.grid(sticky="ew")
        for mode in ("tidy", "fun"):
            page = ttk.Frame(notebook, padding=20)
            page.columnconfigure(0, weight=1)
            page.rowconfigure(3, weight=1)
            notebook.add(page, text=mode.title())
            ttk.Label(page, text="Model").grid(row=0, sticky="w")
            model = ttk.Combobox(
                page, state="readonly", values=list(payload["model_labels"].values())
            )
            model.set(payload["model_labels"][payload["profiles"][mode]["model"]])
            model.grid(row=1, sticky="ew", pady=(6, 18))
            ttk.Label(page, text="Instructions").grid(row=2, sticky="w", pady=(0, 6))
            editor = scrolledtext.ScrolledText(
                page, wrap="word", undo=True, font=("Segoe UI", 11), padx=10, pady=10, height=9
            )
            editor.insert("1.0", payload["profiles"][mode]["instructions"])
            editor.grid(row=3, sticky="nsew")
            self.models[mode] = model
            self.editors[mode] = editor
            ttk.Button(
                page, text="Restore default instructions", command=lambda m=mode: self.restore(m)
            ).grid(row=4, sticky="w", pady=(12, 0))
        feedback = ttk.Frame(notebook, padding=20)
        notebook.add(feedback, text="Feedback")
        for key, label in (
            ("show_mode_labels", "Show mode names below cursor symbols"),
            ("beeps_enabled", "Recording sounds"),
            ("tooltip_enabled", "Detailed tray tooltip"),
            ("monitor_enabled", "Warn when microphone is quiet"),
            ("punctuation_terminal", "Add terminal punctuation"),
            ("punctuation_capitalize", "Capitalize first letter"),
            ("punctuation_normalize_spaces", "Normalize whitespace"),
            ("dictation_history_enabled", "Save additional plain-text history"),
        ):
            self.add_flag(feedback, key, label)
        ttk.Button(feedback, text="Open plain-text history", command=self.open_legacy_log).grid(
            sticky="w", pady=(10, 0)
        )
        footer = ttk.Frame(root, padding=(16, 8, 16, 16))
        footer.grid(row=1, column=0, sticky="ew")
        ttk.Button(footer, text="Cancel", command=root.destroy).pack(side="right")
        ttk.Button(footer, text="Save", command=self.save).pack(side="right", padx=8)
        root.bind("<Escape>", lambda _: root.destroy())
        root.bind("<Control-s>", lambda _: self.save())
        for combo in (self.transcription, self.device, self.suffix, *self.models.values()):
            combo.configure(font=("Segoe UI", 11))
        root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 11))
        root.after(100, root.lift)

    def add_flag(self, page, key, label):
        variable = tk.BooleanVar(value=self.payload["flags"][key])
        ttk.Checkbutton(page, text=label, variable=variable).grid(sticky="w", pady=4)
        self.flags[key] = variable

    def restore(self, mode):
        editor = self.editors[mode]
        editor.delete("1.0", "end")
        editor.insert("1.0", self.payload["defaults"][mode])

    def open_legacy_log(self):
        try:
            path = self.payload["legacy_log_path"]
            if platform.system() == "Windows":
                os.startfile(path)
            else:
                subprocess.Popen(["open" if platform.system() == "Darwin" else "xdg-open", path])
        except Exception as exc:
            messagebox.showerror("Unable to open history", str(exc), parent=self.root)

    def save(self):
        reverse_models = {label: model for model, label in self.payload["model_labels"].items()}
        profiles = {
            mode: {
                "model": reverse_models[self.models[mode].get()],
                "instructions": editor.get("1.0", "end-1c").strip(),
            }
            for mode, editor in self.editors.items()
        }
        if any(not profile["instructions"] for profile in profiles.values()):
            messagebox.showerror(
                "Instructions required",
                "Enter instructions for both Tidy and Fun.",
                parent=self.root,
            )
            return
        self.result = {
            "profiles": profiles,
            "flags": {key: variable.get() for key, variable in self.flags.items()},
            "transcription": self.transcription.get(),
            "device": self.device.get(),
            "suffix": self.suffix.current(),
        }
        self.root.destroy()


def main():
    payload = json.load(sys.stdin)
    root = tk.Tk()
    window = SettingsWindow(root, payload)
    root.mainloop()
    print(json.dumps(window.result))


if __name__ == "__main__":
    main()
