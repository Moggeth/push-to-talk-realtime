"""Durable SQLite storage for raw and finalized transcripts."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class TranscriptEntry:
    id: int
    created_at: str
    mode: str
    audio_source: str
    transcription_engine: str
    transcription_model: str
    post_processing_enabled: bool
    post_process_model: str
    instruction_profile: str
    instructions: str
    raw_text: str
    final_text: str
    post_process_status: str
    post_process_error: str


class TranscriptStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._schema_lock = threading.Lock()
        self._schema_ready = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 30000")
            connection.execute("PRAGMA journal_mode = WAL")
            self._ensure_schema(connection)
        except Exception:
            connection.close()
            raise
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS transcript_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    audio_source TEXT NOT NULL,
                    transcription_engine TEXT NOT NULL,
                    transcription_model TEXT NOT NULL,
                    post_processing_enabled INTEGER NOT NULL DEFAULT 0,
                    post_process_model TEXT NOT NULL DEFAULT '',
                    instruction_profile TEXT NOT NULL DEFAULT '',
                    instructions TEXT NOT NULL DEFAULT '',
                    raw_text TEXT NOT NULL,
                    final_text TEXT NOT NULL DEFAULT '',
                    post_process_status TEXT NOT NULL,
                    post_process_error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_transcript_entries_created
                    ON transcript_entries(created_at DESC, id DESC);
                """
            )
            connection.commit()
            self._schema_ready = True

    def create_entry(
        self,
        *,
        mode: str,
        audio_source: str,
        transcription_engine: str,
        transcription_model: str,
        post_processing_enabled: bool,
        post_process_model: str,
        instruction_profile: str,
        instructions: str,
        raw_text: str,
    ) -> int:
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        status = "pending" if post_processing_enabled else "not_requested"
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                    INSERT INTO transcript_entries (
                        created_at, mode, audio_source, transcription_engine,
                        transcription_model, post_processing_enabled, post_process_model,
                        instruction_profile, instructions, raw_text, post_process_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                (
                    created_at,
                    mode,
                    audio_source,
                    transcription_engine,
                    transcription_model,
                    int(post_processing_enabled),
                    post_process_model,
                    instruction_profile,
                    instructions,
                    raw_text,
                    status,
                ),
            )
            entry_id = cursor.lastrowid
        if entry_id is None:
            raise RuntimeError("SQLite did not return a transcript entry id")
        return int(entry_id)

    def finalize_entry(
        self,
        entry_id: int,
        *,
        final_text: str,
        post_process_status: str,
        post_process_error: str = "",
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE transcript_entries
                SET final_text = ?, post_process_status = ?, post_process_error = ?
                WHERE id = ?
                """,
                (final_text, post_process_status, post_process_error, entry_id),
            )

    @staticmethod
    def _filters(
        *,
        search: str = "",
        from_date: str = "",
        to_date: str = "",
        mode: str = "",
        status: str = "",
    ) -> tuple[str, list[object]]:
        for value in (from_date, to_date):
            if value and (len(value) != 10 or date.fromisoformat(value).isoformat() != value):
                raise ValueError("Use a valid YYYY-MM-DD date.")
        if from_date and to_date and from_date > to_date:
            raise ValueError("Start date must be on or before end date.")
        clauses, params = [], []
        if search.strip():
            clauses.append("(raw_text LIKE ? ESCAPE '\\' OR final_text LIKE ? ESCAPE '\\')")
            literal = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.extend((f"%{literal}%", f"%{literal}%"))
        for value, clause in (
            (from_date, "substr(created_at, 1, 10) >= ?"),
            (to_date, "substr(created_at, 1, 10) <= ?"),
            (mode, "mode = ?"),
            (status, "post_process_status = ?"),
        ):
            if value:
                clauses.append(clause)
                params.append(value)
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def list_entries(
        self,
        *,
        search: str = "",
        limit: int = 500,
        from_date: str = "",
        to_date: str = "",
        mode: str = "",
        status: str = "",
    ) -> list[TranscriptEntry]:
        bounded_limit = max(1, min(int(limit), 2000))
        where, params = self._filters(
            search=search, from_date=from_date, to_date=to_date, mode=mode, status=status
        )
        query = (
            "SELECT * FROM transcript_entries"
            + where
            + " ORDER BY created_at DESC, id DESC LIMIT ?"
        )
        with closing(self._connect()) as connection:
            rows = connection.execute(query, [*params, bounded_limit]).fetchall()
        return [TranscriptEntry(**dict(row)) for row in rows]

    def count_entries(self, **filters: str) -> int:
        where, params = self._filters(**filters)
        with closing(self._connect()) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM transcript_entries" + where, params
                ).fetchone()[0]
            )

    def filter_options(self) -> tuple[list[str], list[str]]:
        with closing(self._connect()) as connection:
            modes = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT mode FROM transcript_entries ORDER BY mode"
                )
            ]
            statuses = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT post_process_status FROM transcript_entries ORDER BY post_process_status"
                )
            ]
        return modes, statuses

    def selected_entries(self, ids: list[int]) -> list[TranscriptEntry]:
        if (
            not ids
            or len(ids) > 500
            or len(set(ids)) != len(ids)
            or any(value <= 0 for value in ids)
        ):
            raise ValueError("Select 1 to 500 distinct entries.")
        placeholders = ",".join("?" for _ in ids)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT * FROM transcript_entries WHERE id IN ({placeholders})", ids
            ).fetchall()
        by_id = {row["id"]: TranscriptEntry(**dict(row)) for row in rows}
        if len(by_id) != len(ids):
            raise ValueError("A selected entry is no longer available. Review the selection again.")
        return [by_id[entry_id] for entry_id in ids]

    def delete_entry(self, entry_id: int) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM transcript_entries WHERE id = ?",
                (entry_id,),
            )
        return cursor.rowcount > 0
