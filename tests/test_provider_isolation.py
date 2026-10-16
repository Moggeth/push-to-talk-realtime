"""Verify provider boundaries fail locally before any transport is constructed."""

import os
from pathlib import Path

import openai
import pytest
import websockets.sync.client

pytest_plugins = ["pytester"]


def test_live_credentials_and_dotenv_are_disabled():
    assert os.environ["OPENAI_API_KEY"] == ""
    assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
    assert os.environ["OPENAI_BASE_URL"] == "http://127.0.0.1:9"
    assert os.environ["OPENAI_REALTIME_WS_URL"] == "ws://127.0.0.1:9"


def test_sdk_client_must_be_explicitly_mocked():
    with pytest.raises(pytest.fail.Exception, match="Provider client must be mocked"):
        openai.OpenAI(api_key="synthetic-test-key")


def test_realtime_transport_must_be_explicitly_mocked():
    with pytest.raises(pytest.fail.Exception, match="Provider client must be mocked"):
        websockets.sync.client.connect("ws://127.0.0.1:9")


def test_application_client_path_cannot_construct_real_client(monkeypatch):
    import push_to_talk_realtime as app

    monkeypatch.setattr(app, "openai_client", None)
    monkeypatch.setattr(app, "OPENAI_API_KEY", "synthetic-test-key")
    with pytest.raises(pytest.fail.Exception, match="Provider client must be mocked"):
        app.get_openai_client()


def test_live_engine_path_cannot_connect(monkeypatch):
    import queue
    import threading
    from contextlib import nullcontext
    from types import SimpleNamespace

    import transcription_engines as engines

    monkeypatch.setattr(engines, "UsageMeter", lambda *a, **k: nullcontext(None))
    config = SimpleNamespace(
        model="synthetic-model",
        websocket_url="ws://127.0.0.1:9",
        api_key="synthetic-test-key",
        session_ready_timeout_s=1,
    )
    with pytest.raises(pytest.fail.Exception, match="Provider client must be mocked"):
        engines.transcribe_live_stream(queue.Queue(), threading.Event(), config)


def test_background_provider_attempt_fails_the_test_run(pytester):
    pytester.makeconftest(Path(__file__).with_name("conftest.py").read_text())
    pytester.makeini(
        "[pytest]\nfilterwarnings = error::pytest.PytestUnhandledThreadExceptionWarning"
    )
    pytester.makepyfile(
        """
        import threading
        import openai

        def test_unmocked_background_provider():
            worker = threading.Thread(target=openai.OpenAI)
            worker.start()
            worker.join()
        """
    )
    result = pytester.runpytest_subprocess("-q", timeout=20)
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Provider client must be mocked*"])
