"""Local, explicitly selected transcript handoffs; no capture or provider access."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict
from datetime import UTC, datetime

from transcript_store import TranscriptEntry

MAX_SELECTION = 500
NOTICE = (
    "Local download only. Raw and final text may contain private or sensitive information. "
    "Nothing is redacted automatically. Review the selected text before sharing. "
    "The browser does not send this export to a provider or change archive retention. "
    "Your downloaded copy is separate from the archive; deleting an entry does not delete that copy."
)


def export_records(entries: list[TranscriptEntry]) -> list[dict[str, object]]:
    return [
        {
            "id": entry.id,
            "created_at": entry.created_at,
            "mode": entry.mode,
            "audio_source": entry.audio_source,
            "status": entry.post_process_status,
            "raw_text": entry.raw_text,
            "final_text": entry.final_text,
        }
        for entry in entries
    ]


def selection_fingerprint(entries: list[TranscriptEntry]) -> str:
    content = json.dumps([asdict(entry) for entry in entries], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def selection_signature(token: str, ids: list[int], fingerprint: str) -> str:
    message = json.dumps([ids, fingerprint], separators=(",", ":")).encode("utf-8")
    return hmac.new(token.encode("utf-8"), message, hashlib.sha256).hexdigest()


def selected_dates(entries: list[TranscriptEntry]) -> tuple[str, str]:
    dates = [entry.created_at[:10] for entry in entries]
    return min(dates), max(dates)


def render_export(entries: list[TranscriptEntry], format_name: str) -> bytes:
    if not entries or len(entries) > MAX_SELECTION:
        raise ValueError("Select between 1 and 500 entries.")
    records = export_records(entries)
    first, last = selected_dates(entries)
    created = datetime.now(UTC).isoformat(timespec="seconds")
    if format_name == "json":
        document = {
            "schema": "push-to-talk-transcript-handoff.v1",
            "exported_at": created,
            "entry_count": len(entries),
            "recorded_date_range": {"first": first, "last": last},
            "date_basis": "Calendar date as recorded, without timezone conversion",
            "selection_fingerprint": selection_fingerprint(entries),
            "privacy_notice": NOTICE,
            "entries": records,
        }
        return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if format_name != "text":
        raise ValueError("Choose text or JSON.")
    sections = [
        "SELECTED TRANSCRIPT HANDOFF",
        f"Exported: {created}",
        f"Entries: {len(entries)} | Recorded dates: {first} through {last} (inclusive)",
        "Dates retain their recorded offset; no timezone conversion is applied.",
        NOTICE,
        "",
    ]
    for entry in entries:
        sections.extend(
            [
                f"--- Entry {entry.id} ---",
                f"Recorded: {entry.created_at}",
                f"Mode: {entry.mode} | Source: {entry.audio_source} | Status: {entry.post_process_status}",
                "RAW TRANSCRIPT (as archived):",
                entry.raw_text,
                "FINAL TEXT (as archived; empty means no final text recorded):",
                entry.final_text if entry.final_text else "[No final text recorded]",
                "",
            ]
        )
    return "\n".join(sections).encode("utf-8")
