from __future__ import annotations

from pathlib import Path

from transcript_store import TranscriptStore


def create_entry(store: TranscriptStore, raw_text: str = "Raw words") -> int:
    return store.create_entry(
        mode="dictation",
        audio_source="microphone",
        transcription_engine="whisper",
        transcription_model="gpt-4o-mini-transcribe",
        post_processing_enabled=True,
        post_process_model="gpt-5.6-luna",
        instruction_profile="clean_up",
        instructions="Clean this up.",
        raw_text=raw_text,
    )


def test_store_preserves_raw_text_before_finalization(tmp_path: Path):
    store = TranscriptStore(tmp_path / "state" / "transcripts.db")

    entry_id = create_entry(store, "Um, raw words")

    entries = store.list_entries()
    assert len(entries) == 1
    assert entries[0].id == entry_id
    assert entries[0].raw_text == "Um, raw words"
    assert entries[0].final_text == ""
    assert entries[0].post_process_status == "pending"
    assert entries[0].instructions == "Clean this up."


def test_store_finalizes_searches_and_deletes_entry(tmp_path: Path):
    store = TranscriptStore(tmp_path / "transcripts.db")
    entry_id = create_entry(store)

    store.finalize_entry(
        entry_id,
        final_text="Final polished words.",
        post_process_status="completed",
    )

    entries = store.list_entries(search="polished")
    assert len(entries) == 1
    assert entries[0].raw_text == "Raw words"
    assert entries[0].final_text == "Final polished words."
    assert entries[0].post_process_status == "completed"
    assert store.list_entries(search="missing") == []
    assert store.delete_entry(entry_id) is True
    assert store.delete_entry(entry_id) is False
    assert store.list_entries() == []
