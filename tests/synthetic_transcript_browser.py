"""Temporary synthetic browser only: no app startup, settings, devices or providers."""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transcript_browser import TranscriptBrowserServer
from transcript_store import TranscriptStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18477)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with tempfile.TemporaryDirectory(prefix="ptt-synthetic-browser-") as directory:
        store = TranscriptStore(Path(directory) / "synthetic.db")
        fixtures = [
            (
                "2026-01-01T00:00:00+11:00",
                "dictation",
                "completed",
                "SYNTHETIC alpha raw <script>literal only</script>",
                "Synthetic alpha final.",
            ),
            (
                "2026-01-02T23:59:59-12:00",
                "work_log",
                "failed",
                "SYNTHETIC beta raw =SUM(1,2)",
                "Synthetic beta retained.",
            ),
            (
                "2026-01-03T00:00:00+14:00",
                "dictation",
                "pending",
                "SYNTHETIC gamma raw - no final yet",
                "",
            ),
        ]
        for date, mode, status, raw, final in fixtures:
            identifier = store.create_entry(
                mode=mode,
                audio_source="synthetic",
                transcription_engine="synthetic",
                transcription_model="synthetic",
                post_processing_enabled=True,
                post_process_model="synthetic",
                instruction_profile="synthetic",
                instructions="Not included in exports",
                raw_text=raw,
            )
            store.finalize_entry(identifier, final_text=final, post_process_status=status)
            with sqlite3.connect(store.path) as connection:
                connection.execute(
                    "UPDATE transcript_entries SET created_at=? WHERE id=?", (date, identifier)
                )
        server = TranscriptBrowserServer(("127.0.0.1", args.port), store)
        print(f"SYNTHETIC ONLY: http://127.0.0.1:{server.server_address[1]}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
