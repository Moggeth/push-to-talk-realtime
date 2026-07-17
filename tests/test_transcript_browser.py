from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from transcript_browser import launch_transcript_browser, render_browser_page
from transcript_store import TranscriptStore


def add_entry(store: TranscriptStore, raw_text: str) -> int:
    entry_id = store.create_entry(
        mode="dictation",
        audio_source="system",
        transcription_engine="whisper",
        transcription_model="gpt-4o-mini-transcribe",
        post_processing_enabled=False,
        post_process_model="",
        instruction_profile="",
        instructions="",
        raw_text=raw_text,
    )
    store.finalize_entry(
        entry_id,
        final_text="Final text",
        post_process_status="not_requested",
    )
    return entry_id


def test_render_browser_page_escapes_transcript_content(tmp_path: Path):
    store = TranscriptStore(tmp_path / "transcripts.db")
    add_entry(store, "<script>alert('no')</script>")

    page = render_browser_page(store.list_entries(), delete_token="token")

    assert "<script>" not in page
    assert "&lt;script&gt;alert(&#x27;no&#x27;)&lt;/script&gt;" in page
    assert "Raw transcript" in page
    assert "Final text" in page


def test_browser_lists_and_deletes_entries_over_loopback(tmp_path: Path):
    store = TranscriptStore(tmp_path / "transcripts.db")
    entry_id = add_entry(store, "Delete me")
    server, url = launch_transcript_browser(store, open_browser=False)
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            page = response.read().decode("utf-8")
        assert "Delete me" in page

        body = urllib.parse.urlencode({"token": server.delete_token}).encode("ascii")
        request = urllib.request.Request(
            f"{url}delete/{entry_id}",
            data=body,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
        assert store.list_entries() == []
    finally:
        server.shutdown()
        server.server_close()


def test_browser_rejects_delete_without_token(tmp_path: Path):
    store = TranscriptStore(tmp_path / "transcripts.db")
    entry_id = add_entry(store, "Keep me")
    server, url = launch_transcript_browser(store, open_browser=False)
    try:
        request = urllib.request.Request(
            f"{url}delete/{entry_id}",
            data=b"token=wrong",
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request, timeout=5)
        assert exc_info.value.code == 403
        exc_info.value.close()
        assert len(store.list_entries()) == 1
    finally:
        server.shutdown()
        server.server_close()
