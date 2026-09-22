from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import pytest

from transcript_browser import launch_transcript_browser, render_browser_page
from transcript_exports import render_export
from transcript_store import TranscriptStore


def entry(
    store,
    raw,
    *,
    date="2026-01-01T12:00:00+11:00",
    mode="dictation",
    status="completed",
    final="Synthetic final",
):
    identifier = store.create_entry(
        mode=mode,
        audio_source="microphone",
        transcription_engine="synthetic",
        transcription_model="synthetic",
        post_processing_enabled=True,
        post_process_model="synthetic",
        instruction_profile="synthetic",
        instructions="PRIVATE SYNTHETIC INSTRUCTIONS",
        raw_text=raw,
    )
    store.finalize_entry(
        identifier,
        final_text=final,
        post_process_status=status,
        post_process_error="PRIVATE SYNTHETIC ERROR",
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE transcript_entries SET created_at = ? WHERE id = ?", (date, identifier)
        )
    return identifier


@pytest.fixture
def store(tmp_path):
    return TranscriptStore(tmp_path / "synthetic.db")


class HiddenFields(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.fields = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and values.get("type") == "hidden":
            self.fields.append((values["name"], values.get("value", "")))


def request(url, fields=None):
    body = urllib.parse.urlencode(fields, doseq=True).encode() if fields is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=5) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, error.headers, error.read()


@pytest.fixture
def browser(store):
    server, url = launch_transcript_browser(store, open_browser=False)
    yield server, url
    server.shutdown()
    server.server_close()


def preview(browser, ids):
    server, url = browser
    status, _, body = request(
        url + "export/preview", {"token": server.delete_token, "entry_id": ids}
    )
    assert status == 200
    return body.decode(), HiddenFields(body.decode()).fields


def download(browser, fields, **extra):
    return request(
        browser[1] + "export", [*fields, ("reviewed", "yes"), ("format", "json"), *extra.items()]
    )


def test_inclusive_recorded_date_boundaries_and_combined_filters(store):
    before = entry(store, "same words", date="2025-12-31T23:59:59-12:00")
    first = entry(store, "same words", date="2026-01-01T00:00:00+14:00")
    last = entry(store, "same words", date="2026-01-02T23:59:59-12:00")
    after = entry(store, "same words", date="2026-01-03T00:00:00+14:00")
    entry(store, "same words", mode="work_log")
    entry(store, "same words", status="pending")
    filters = {
        "from_date": "2026-01-01",
        "to_date": "2026-01-02",
        "mode": "dictation",
        "status": "completed",
        "search": "same",
    }
    assert [row.id for row in store.list_entries(**filters)] == [last, first]
    assert store.count_entries(**filters) == 2
    assert before not in [first, last] and after not in [first, last]


@pytest.mark.parametrize(
    "filters",
    [
        {"from_date": "2026-02-29"},
        {"to_date": "2026-1-1"},
        {"from_date": "2026-02-01", "to_date": "2026-01-31"},
    ],
)
def test_invalid_dates_are_rejected(store, filters):
    with pytest.raises(ValueError):
        store.list_entries(**filters)


def test_literal_search_and_mode_query_cannot_broaden_results(store):
    selected = entry(store, "100% synthetic_value")
    entry(store, "1000 synthetic value")
    assert [row.id for row in store.list_entries(search="% synthetic_")] == [selected]
    assert store.list_entries(mode="' OR 1=1 --") == []


def test_json_preserves_selected_only_raw_final_empty_and_unicode(store, browser):
    first = entry(store, '<script>literal</script>\n"quoted" \\ Ω', final="=SUM(1,2)")
    second = entry(store, "Pending synthetic", status="pending", final="")
    entry(store, "UNSELECTED SECRET SYNTHETIC")
    page, fields = preview(browser, [second, first])
    assert "2 selected entries" in page and "2026-01-01 through 2026-01-01" in page
    assert "&lt;script&gt;literal&lt;/script&gt;" in page and "<script>literal" not in page
    status, headers, body = download(browser, fields)
    assert status == 200 and headers["Content-Disposition"].endswith('selected-transcripts.json"')
    content = json.loads(body)
    assert content["entry_count"] == 2
    assert [row["id"] for row in content["entries"]] == [second, first]
    assert content["entries"][0]["final_text"] == ""
    assert content["entries"][1]["raw_text"] == '<script>literal</script>\n"quoted" \\ Ω'
    assert content["entries"][1]["final_text"] == "=SUM(1,2)"
    assert (
        b"UNSELECTED" not in body and b"INSTRUCTIONS" not in body and b"SYNTHETIC ERROR" not in body
    )
    assert headers["Cache-Control"] == "no-store"


def test_text_export_labels_raw_final_without_fallback(store):
    identifier = entry(store, "RAW ONLY", status="failed", final="")
    text = render_export(store.selected_entries([identifier]), "text").decode()
    assert "Entries: 1" in text and "RAW TRANSCRIPT (as archived):\nRAW ONLY" in text
    assert "[No final text recorded]" in text and "Status: failed" in text


def test_changed_entry_rejects_entire_export(store, browser):
    identifier = entry(store, "Original")
    _, fields = preview(browser, [identifier])
    store.finalize_entry(identifier, final_text="Changed final", post_process_status="completed")
    status, headers, body = download(browser, fields)
    assert status == 409 and "Content-Disposition" not in headers
    assert b"Changed final" not in body
    assert store.selected_entries([identifier])[0].final_text == "Changed final"


def test_deleted_selection_does_not_export_remaining_subset(store, browser):
    first, second = entry(store, "First"), entry(store, "Second")
    _, fields = preview(browser, [first, second])
    store.delete_entry(first)
    status, headers, _ = download(browser, fields)
    assert status == 400 and "Content-Disposition" not in headers
    assert store.selected_entries([second])[0].raw_text == "Second"


def test_tampered_selection_and_missing_acknowledgement_are_rejected(store, browser):
    first, second = entry(store, "First"), entry(store, "Unselected")
    _, fields = preview(browser, [first])
    changed = [(key, str(second) if key == "entry_id" else value) for key, value in fields]
    assert download(browser, changed)[0] == 403
    assert request(browser[1] + "export", [*fields, ("format", "json")])[0] == 400


@pytest.mark.parametrize("ids", [[], [1, 1], [0], [-1], [1] * 501, [999]])
def test_invalid_selection_never_exports(store, browser, ids):
    entry(store, "Keep")
    status, headers, _ = request(
        browser[1] + "export/preview", {"token": browser[0].delete_token, "entry_id": ids}
    )
    assert status == 400 and "Content-Disposition" not in headers
    assert store.count_entries() == 1


def test_invalid_unicode_token_is_rejected_without_server_exception(store, browser):
    identifier = entry(store, "Keep")
    assert request(browser[1] + "export/preview", {"token": "Ω", "entry_id": identifier})[0] == 403


def test_browser_restart_keeps_archive_and_requires_fresh_selection(store, browser):
    identifier = entry(store, "Survives restart")
    _, fields = preview(browser, [identifier])
    fresh_store = TranscriptStore(store.path)
    restarted, url = launch_transcript_browser(fresh_store, open_browser=False)
    try:
        assert request(url + "export", [*fields, ("reviewed", "yes"), ("format", "json")])[0] == 403
        status, _, page = request(url)
        assert status == 200 and b"Survives restart" in page
        assert len(fresh_store.list_entries()) == 1
    finally:
        restarted.shutdown()
        restarted.server_close()


def test_filter_values_and_metadata_are_html_escaped(store):
    identifier = entry(store, "Safe", mode="<img src=x onerror=alert(1)>")
    page = render_browser_page(
        store.selected_entries([identifier]),
        delete_token="test",
        mode='" autofocus',
        modes=["<script>bad</script>"],
    )
    assert "<img src=x" not in page and "<script>bad" not in page
    assert "&quot; autofocus" in page


@pytest.mark.parametrize(
    "header,value",
    [
        ("Host", "unrelated.invalid"),
        ("Host", "127.0.0.1:65536"),
        ("Host", "127.0.0.1:bad"),
        ("Host", "user@127.0.0.1:1"),
        ("Origin", "https://unrelated.invalid"),
        ("Origin", "http://127.0.0.1:65536"),
        ("Sec-Fetch-Site", "cross-site"),
    ],
)
def test_foreign_or_malformed_host_origin_cannot_read_entries(store, browser, header, value):
    entry(store, "PRIVATE SYNTHETIC RECORD")
    req = urllib.request.Request(browser[1], headers={header: value})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(req, timeout=5)
    with caught.value as response:
        assert response.code == 403
        assert b"PRIVATE SYNTHETIC RECORD" not in response.read()


def test_client_visible_token_cannot_sign_an_unreviewed_export(store, browser):
    from transcript_exports import selection_fingerprint, selection_signature

    identifier = entry(store, "Selected without preview")
    fingerprint = selection_fingerprint(store.selected_entries([identifier]))
    forged = selection_signature(browser[0].delete_token, [identifier], fingerprint)
    status, headers, body = request(
        browser[1] + "export",
        {
            "token": browser[0].delete_token,
            "entry_id": identifier,
            "fingerprint": fingerprint,
            "signature": forged,
            "reviewed": "yes",
            "format": "json",
        },
    )
    assert status == 403 and "Content-Disposition" not in headers
    assert b"Selected without preview" not in body


def test_preview_metadata_change_also_requires_fresh_review(store, browser):
    identifier = entry(store, "Raw")
    _, fields = preview(browser, [identifier])
    store.finalize_entry(
        identifier,
        final_text="Synthetic final",
        post_process_status="completed",
        post_process_error="Changed metadata",
    )
    assert download(browser, fields)[0] == 409
