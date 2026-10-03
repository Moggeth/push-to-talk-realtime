"""Focused tests for the GUI-subsystem scheduled-task entry point."""

import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.skipif(not hasattr(subprocess, "STARTUPINFO"), reason="Windows startup flags")
def test_hidden_task_preserves_result_and_arguments(monkeypatch, tmp_path):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "readiness_task.pyw"))
    run = Mock(return_value=SimpleNamespace(returncode=7))
    monkeypatch.setattr(subprocess, "run", run)
    assert (
        module["main"](
            [
                "--python",
                "C:/Example/pythonw.exe",
                "--launcher",
                "C:/Example/test.py",
                "--diagnostics-directory",
                str(tmp_path),
            ]
        )
        == 7
    )
    args, kwargs = run.call_args
    assert "-WindowStyle" in args[0] and "Hidden" in args[0]
    assert args[0][-2:] == ["-Launcher", "C:/Example/test.py"]
    assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert kwargs["startupinfo"].wShowWindow == subprocess.SW_HIDE


@pytest.mark.skipif(not hasattr(subprocess, "STARTUPINFO"), reason="Windows startup flags")
def test_launch_failure_is_durable_and_redacted(monkeypatch, tmp_path):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "readiness_task.pyw"))
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=OSError("sensitive diagnostic")))
    assert (
        module["main"](["--python", "pythonw.exe", "--diagnostics-directory", str(tmp_path)]) == 1
    )
    log = (tmp_path / "windowless-task-error.jsonl").read_text()
    assert "OSError" in log and "sensitive diagnostic" not in log
