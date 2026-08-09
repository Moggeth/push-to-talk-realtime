from __future__ import annotations

from pathlib import Path

from runtime_paths import (
    default_runtime_directory,
    migrate_legacy_runtime_files,
    resolve_runtime_paths,
    rotate_file,
)


def test_windows_runtime_paths_use_local_app_data(tmp_path: Path):
    paths = resolve_runtime_paths(
        {"LOCALAPPDATA": str(tmp_path)}, system_name="Windows", home=tmp_path
    )

    assert paths.log == tmp_path / "PushToTalkRealtime" / "push_to_talk_realtime.log"
    assert paths.transcript_db == tmp_path / "PushToTalkRealtime" / "transcripts.db"
    assert paths.work_log == tmp_path / "PushToTalkRealtime" / "work_log.txt"


def test_linux_runtime_directory_uses_xdg_state_home(tmp_path: Path):
    assert (
        default_runtime_directory("Linux", {"XDG_STATE_HOME": str(tmp_path)}, tmp_path)
        == tmp_path / "push-to-talk-realtime"
    )


def test_legacy_runtime_files_migrate_once(tmp_path: Path):
    script_dir = tmp_path / "checkout"
    runtime_dir = tmp_path / "runtime"
    script_dir.mkdir()
    (script_dir / "transcripts.db").write_text("database", encoding="utf-8")
    (script_dir / "transcripts.db-wal").write_text("wal", encoding="utf-8")
    (script_dir / "work_log.txt").write_text("history", encoding="utf-8")
    paths = resolve_runtime_paths(
        {"LOCALAPPDATA": str(runtime_dir)}, system_name="Windows", home=tmp_path
    )

    moved, failures = migrate_legacy_runtime_files(paths, script_dir, {})

    assert failures == []
    assert (script_dir / "transcripts.db", paths.transcript_db) in moved
    assert paths.transcript_db.read_text(encoding="utf-8") == "database"
    assert Path(f"{paths.transcript_db}-wal").read_text(encoding="utf-8") == "wal"
    assert paths.work_log.read_text(encoding="utf-8") == "history"
    assert migrate_legacy_runtime_files(paths, script_dir, {}) == ([], [])


def test_explicit_path_prevents_legacy_migration(tmp_path: Path):
    script_dir = tmp_path / "checkout"
    script_dir.mkdir()
    legacy_log = script_dir / "push_to_talk_realtime.log"
    legacy_log.write_text("legacy", encoding="utf-8")
    explicit_log = tmp_path / "explicit.log"
    paths = resolve_runtime_paths(
        {"PUSH_TO_TALK_LOG_PATH": str(explicit_log)}, system_name="Windows", home=tmp_path
    )

    moved, failures = migrate_legacy_runtime_files(
        paths, script_dir, {"PUSH_TO_TALK_LOG_PATH": str(explicit_log)}
    )

    assert moved == []
    assert failures == []
    assert legacy_log.exists()


def test_legacy_log_is_prepended_to_startup_lines_already_at_destination(tmp_path: Path):
    script_dir = tmp_path / "checkout"
    script_dir.mkdir()
    legacy_log = script_dir / "push_to_talk_realtime.log"
    legacy_log.write_text("legacy line\n", encoding="utf-8")
    paths = resolve_runtime_paths(
        {"LOCALAPPDATA": str(tmp_path / "runtime")},
        system_name="Windows",
        home=tmp_path,
    )
    paths.log.parent.mkdir(parents=True)
    paths.log.write_text("new startup line\n", encoding="utf-8")

    moved, failures = migrate_legacy_runtime_files(paths, script_dir, {})

    assert failures == []
    assert moved == [(legacy_log, paths.log)]
    assert paths.log.read_text(encoding="utf-8") == "legacy line\nnew startup line\n"
    assert not legacy_log.exists()


def test_rotate_file_keeps_bounded_backups(tmp_path: Path):
    path = tmp_path / "app.log"
    path.write_text("first", encoding="utf-8")
    assert rotate_file(path, max_bytes=1, backup_count=2) is True
    path.write_text("second", encoding="utf-8")
    assert rotate_file(path, max_bytes=1, backup_count=2) is True
    path.write_text("third", encoding="utf-8")
    assert rotate_file(path, max_bytes=1, backup_count=2) is True

    assert path.with_name("app.log.1").read_text(encoding="utf-8") == "third"
    assert path.with_name("app.log.2").read_text(encoding="utf-8") == "second"
