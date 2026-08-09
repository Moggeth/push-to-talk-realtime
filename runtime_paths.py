from __future__ import annotations

import os
import platform
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_DIRECTORY_NAME = "PushToTalkRealtime"


def default_settings_path(
    system_name: str | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    system_name = system_name or platform.system()
    environment = environment if environment is not None else os.environ
    home = home or Path.home()
    if system_name == "Windows":
        root = environment.get("LOCALAPPDATA") or environment.get("APPDATA")
        base = Path(root) if root else home / "AppData" / "Local"
        return base / APP_DIRECTORY_NAME / "settings.json"
    if system_name == "Darwin":
        return home / "Library" / "Application Support" / APP_DIRECTORY_NAME / "settings.json"
    config_root = Path(environment.get("XDG_CONFIG_HOME") or (home / ".config"))
    return config_root / "push-to-talk-realtime" / "settings.json"


def default_runtime_directory(
    system_name: str | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    system_name = system_name or platform.system()
    environment = environment if environment is not None else os.environ
    home = home or Path.home()
    if system_name == "Windows":
        root = environment.get("LOCALAPPDATA") or environment.get("APPDATA")
        base = Path(root) if root else home / "AppData" / "Local"
        return base / APP_DIRECTORY_NAME
    if system_name == "Darwin":
        return home / "Library" / "Application Support" / APP_DIRECTORY_NAME
    state_root = Path(environment.get("XDG_STATE_HOME") or (home / ".local" / "state"))
    return state_root / "push-to-talk-realtime"


@dataclass(frozen=True)
class RuntimePaths:
    log: Path
    launcher_log: Path
    transcript_db: Path
    work_log: Path
    post_process_instructions: Path


def resolve_runtime_paths(
    environment: Mapping[str, str] | None = None,
    *,
    system_name: str | None = None,
    home: Path | None = None,
) -> RuntimePaths:
    environment = environment if environment is not None else os.environ
    runtime_dir = default_runtime_directory(system_name, environment, home)
    return RuntimePaths(
        log=Path(
            environment.get("PUSH_TO_TALK_LOG_PATH") or runtime_dir / "push_to_talk_realtime.log"
        ),
        launcher_log=Path(
            environment.get("PUSH_TO_TALK_LAUNCHER_LOG_PATH")
            or runtime_dir / "push_to_talk_starter.log"
        ),
        transcript_db=Path(
            environment.get("PUSH_TO_TALK_TRANSCRIPT_DB_PATH") or runtime_dir / "transcripts.db"
        ),
        work_log=Path(environment.get("WORK_LOG_PATH") or runtime_dir / "work_log.txt"),
        post_process_instructions=Path(
            environment.get("OPENAI_POST_PROCESS_INSTRUCTIONS_PATH")
            or runtime_dir / "post_process_instructions.txt"
        ),
    )


def migrate_legacy_runtime_files(
    paths: RuntimePaths,
    script_dir: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[list[tuple[Path, Path]], list[tuple[Path, Exception]]]:
    environment = environment if environment is not None else os.environ
    migrations = (
        ("PUSH_TO_TALK_LOG_PATH", script_dir / "push_to_talk_realtime.log", paths.log),
        ("PUSH_TO_TALK_TRANSCRIPT_DB_PATH", script_dir / "transcripts.db", paths.transcript_db),
        ("WORK_LOG_PATH", script_dir / "work_log.txt", paths.work_log),
        (
            "OPENAI_POST_PROCESS_INSTRUCTIONS_PATH",
            script_dir / "post_process_instructions.txt",
            paths.post_process_instructions,
        ),
    )
    moved: list[tuple[Path, Path]] = []
    failures: list[tuple[Path, Exception]] = []
    for environment_name, source, destination in migrations:
        if environment.get(environment_name) or not source.exists():
            continue
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if source.name != "push_to_talk_realtime.log":
                    continue
                migration_temp = destination.with_name(f"{destination.name}.migration.tmp")
                with migration_temp.open("wb") as output:
                    with source.open("rb") as legacy_input:
                        shutil.copyfileobj(legacy_input, output)
                    with destination.open("rb") as current_input:
                        shutil.copyfileobj(current_input, output)
                migration_temp.replace(destination)
                source.unlink()
                moved.append((source, destination))
                continue
            shutil.move(str(source), str(destination))
            moved.append((source, destination))
            if source.name == "transcripts.db":
                for suffix in ("-wal", "-shm"):
                    sidecar_source = Path(f"{source}{suffix}")
                    sidecar_destination = Path(f"{destination}{suffix}")
                    if sidecar_source.exists() and not sidecar_destination.exists():
                        shutil.move(str(sidecar_source), str(sidecar_destination))
                        moved.append((sidecar_source, sidecar_destination))
        except Exception as exc:  # migration failures must not prevent startup
            failures.append((source, exc))
    return moved, failures


def rotate_file(path: Path, max_bytes: int, backup_count: int) -> bool:
    if max_bytes <= 0 or backup_count <= 0 or not path.exists():
        return False
    try:
        if path.stat().st_size < max_bytes:
            return False
        oldest = path.with_name(f"{path.name}.{backup_count}")
        oldest.unlink(missing_ok=True)
        for index in range(backup_count - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.exists():
                source.replace(path.with_name(f"{path.name}.{index + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
        return True
    except OSError:
        return False
