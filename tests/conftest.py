import os
import tempfile
from pathlib import Path

os.environ.setdefault("PYNPUT_BACKEND", "dummy")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")
os.environ["PUSH_TO_TALK_SETTINGS_PATH"] = str(
    Path(tempfile.gettempdir()) / f"push-to-talk-realtime-pytest-{os.getpid()}.json"
)
