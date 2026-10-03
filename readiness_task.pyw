"""Windowless entry point for the scheduled readiness task.

Task Scheduler must start pythonw, not a console executable: -WindowStyle Hidden
is interpreted only after Windows may already have opened its terminal host.
The existing PowerShell wrapper retains lifecycle diagnostics and exit behavior.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True)
    parser.add_argument("--launcher")
    parser.add_argument("--diagnostics-directory")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    diagnostics = Path(
        args.diagnostics_directory
        or Path(os.environ["LOCALAPPDATA"]) / "PushToTalkRealtime" / "diagnostics"
    )
    command = [
        str(Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
        "-NoProfile",
        "-NonInteractive",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(root / "readiness_task.ps1"),
        "-Python",
        args.python,
        "-DiagnosticsDirectory",
        str(diagnostics),
    ]
    if args.launcher:
        command.extend(["-Launcher", args.launcher])
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    started = time.monotonic()
    try:
        return subprocess.run(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startup,
            check=False,
        ).returncode
    except Exception as error:
        # Metadata only: never persist inherited credentials or process output.
        try:
            diagnostics.mkdir(parents=True, exist_ok=True)
            with (diagnostics / "windowless-task-error.jsonl").open("a", encoding="utf-8") as log:
                log.write(
                    json.dumps(
                        {
                            "epoch": time.time(),
                            "event": "windowless_launch_failed",
                            "exception_type": type(error).__name__,
                            "elapsed_s": time.monotonic() - started,
                        }
                    )
                    + "\n"
                )
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
