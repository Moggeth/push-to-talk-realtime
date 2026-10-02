import os
import tempfile
from pathlib import Path

os.environ.setdefault("PYNPUT_BACKEND", "dummy")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")
runtime_root = Path(tempfile.gettempdir()) / f"push-to-talk-realtime-pytest-{os.getpid()}"
os.environ["PUSH_TO_TALK_SETTINGS_PATH"] = str(runtime_root / "settings.json")
os.environ["PUSH_TO_TALK_LOG_PATH"] = str(runtime_root / "app.log")
os.environ["PUSH_TO_TALK_DIAGNOSTICS_DIR"] = str(runtime_root / "diagnostics")
os.environ["PUSH_TO_TALK_LAUNCHER_LOG_PATH"] = str(runtime_root / "launcher.log")
os.environ["PUSH_TO_TALK_TRANSCRIPT_DB_PATH"] = str(runtime_root / "transcripts.db")
os.environ["WORK_LOG_PATH"] = str(runtime_root / "work_log.txt")
os.environ["OPENAI_POST_PROCESS_INSTRUCTIONS_PATH"] = str(runtime_root / "instructions.txt")
