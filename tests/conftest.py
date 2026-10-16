import os
import tempfile
from pathlib import Path

import pytest

# Tests must never inherit live provider credentials or load a checkout's .env.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:9"
os.environ["OPENAI_REALTIME_WS_URL"] = "ws://127.0.0.1:9"

os.environ.setdefault("PYNPUT_BACKEND", "dummy")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")
runtime_root = Path(tempfile.gettempdir()) / f"push-to-talk-realtime-pytest-{os.getpid()}"
os.environ["PUSH_TO_TALK_SETTINGS_PATH"] = str(runtime_root / "settings.json")
os.environ["PUSH_TO_TALK_LOG_PATH"] = str(runtime_root / "app.log")
os.environ["PUSH_TO_TALK_DIAGNOSTICS_DIR"] = str(runtime_root / "diagnostics")
os.environ["PUSH_TO_TALK_LAUNCHER_LOG_PATH"] = str(runtime_root / "launcher.log")
os.environ["PUSH_TO_TALK_TRANSCRIPT_DB_PATH"] = str(runtime_root / "transcripts.db")
os.environ["PUSH_TO_TALK_USAGE_DB_PATH"] = str(runtime_root / "usage.db")
os.environ["WORK_LOG_PATH"] = str(runtime_root / "work_log.txt")
os.environ["OPENAI_POST_PROCESS_INSTRUCTIONS_PATH"] = str(runtime_root / "instructions.txt")


@pytest.fixture(scope="session", autouse=True)
def require_mocked_provider_clients():
    # Patch the actual factories used by get_openai_client and transcribe_live_stream.
    # Tests supply their own fake clients/sockets above these boundaries.
    import openai
    import websockets.sync.client

    def unmocked_provider(*args, **kwargs):
        pytest.fail("Provider client must be mocked; live API calls are forbidden in tests")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(openai, "OpenAI", unmocked_provider)
        patch.setattr(websockets.sync.client, "connect", unmocked_provider)
        yield
