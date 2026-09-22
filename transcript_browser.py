"""Loopback-only HTML browser for the local transcript database."""

from __future__ import annotations

import argparse
import hmac
import html
import logging
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse

from transcript_exports import (
    NOTICE,
    render_export,
    selected_dates,
    selection_fingerprint,
    selection_signature,
)
from transcript_store import TranscriptEntry, TranscriptStore

logger = logging.getLogger(__name__)


def _entry_html(entry: TranscriptEntry, delete_token: str, *, preview: bool = False) -> str:
    final_text = entry.final_text or "No final text recorded"
    status_class = "ok" if entry.post_process_status in {"completed", "not_requested"} else "warn"
    model_parts = [entry.transcription_model]
    if entry.post_processing_enabled:
        model_parts.append(entry.post_process_model)
    metadata = " · ".join(part for part in model_parts if part)
    error_html = ""
    if entry.post_process_error:
        error_html = f'<p class="error">{html.escape(entry.post_process_error)}</p>'
    selection = (
        ""
        if preview
        else f'<label class="selection"><input type="checkbox" autocomplete="off" name="entry_id" value="{entry.id}" form="export-selection"> Select entry {entry.id}</label>'
    )
    delete_form = (
        ""
        if preview
        else f'<form method="post" action="/delete/{entry.id}"><input type="hidden" name="token" value="{delete_token}"><button type="submit" title="Delete transcript">Delete</button></form>'
    )
    return f"""
    <article class="entry">
      <header>
        <div>
          {selection}
          <strong>{html.escape(entry.mode.title())}</strong>
          <span>{html.escape(entry.created_at)}</span>
          <span>{html.escape(entry.audio_source.replace("_", " ").title())}</span>
        </div>
        <span class="status {status_class}">{html.escape(entry.post_process_status.replace("_", " "))}</span>
      </header>
      <div class="texts">
        <section><h2>Raw transcript</h2><p>{html.escape(entry.raw_text)}</p></section>
        <section><h2>Final text</h2><p>{html.escape(final_text)}</p></section>
      </div>
      <footer>
        <span>{html.escape(metadata)}</span>
        <span>{html.escape(entry.instruction_profile.replace("_", " "))}</span>
        {delete_form}
      </footer>
      {error_html}
    </article>
    """


def render_browser_page(
    entries: list[TranscriptEntry],
    *,
    delete_token: str,
    search: str = "",
    from_date: str = "",
    to_date: str = "",
    mode: str = "",
    status: str = "",
    modes: list[str] | None = None,
    statuses: list[str] | None = None,
    total: int | None = None,
    review_selection: bool = False,
    back_query: str = "",
    export_signature: str = "",
) -> str:
    entry_markup = "".join(
        _entry_html(entry, delete_token, preview=review_selection) for entry in entries
    )

    def options(values: list[str], selected: str) -> str:
        values = sorted(set(values + ([selected] if selected else [])))
        return '<option value="">All</option>' + "".join(
            f'<option value="{html.escape(value)}" {"selected" if value == selected else ""}>{html.escape(value.replace("_", " "))}</option>'
            for value in values
        )

    if review_selection:
        fingerprint = selection_fingerprint(entries)
        signature = export_signature
        first, last = selected_dates(entries)
        fields = "".join(
            f'<input type="hidden" name="entry_id" value="{entry.id}">' for entry in entries
        )
        controls = f'''<section class="export-box" aria-label="Export review"><h2>Review selected export</h2>
          <p><strong>{len(entries)} selected entries</strong> · Recorded dates: {html.escape(first)} through {html.escape(last)}, inclusive.</p>
          <p>Only the entries below will be downloaded. Raw and final text remain separate. An empty final field is not replaced by raw text.</p>
          <p>{html.escape(NOTICE)}</p>
          <form method="post" action="/export"><input type="hidden" name="token" value="{delete_token}">{fields}
            <input type="hidden" name="fingerprint" value="{fingerprint}"><input type="hidden" name="signature" value="{signature}">
            <label class="confirm"><input type="checkbox" name="reviewed" value="yes" required> I reviewed these selected entries and understand the privacy notice.</label>
            <button name="format" value="text">Download text</button> <button name="format" value="json">Download JSON</button>
          </form><a href="/?{html.escape(back_query)}">Return to history (selection clears)</a>
        </section>'''
        filter_form = ""
    else:
        filter_form = f'''<form class="filters" method="get" action="/">
          <label>Search raw or final text<input type="search" name="q" value="{html.escape(search)}" placeholder="Search raw or final text" aria-label="Search transcripts"></label>
          <label>From date<input type="date" name="from_date" value="{html.escape(from_date)}"></label>
          <label>Through date<input type="date" name="to_date" value="{html.escape(to_date)}"></label>
          <label>Capture mode<select name="mode" aria-label="Capture mode">{options(modes or [], mode)}</select></label>
          <label>Processing status<select name="status" aria-label="Processing status">{options(statuses or [], status)}</select></label>
          <button type="submit">Apply filters</button><a href="/">Clear filters</a>
        </form>'''
        filters = urlencode(
            {
                "q": search,
                "from_date": from_date,
                "to_date": to_date,
                "mode": mode,
                "status": status,
            }
        )
        controls = f'''<section class="export-box" aria-label="Selected transcript export">
          <p>Showing {len(entries)} of {len(entries) if total is None else total} matching entries (up to 500). Narrow the filters to find older entries.</p>
          <p>Dates include both endpoints and use each entry's recorded calendar date, without timezone conversion. Applying filters, returning to history or refreshing clears the selection.</p>
          <p>Select individual entries below, then review the exact count, dates and content before downloading. No entries are selected automatically.</p>
          <form id="export-selection" method="post" action="/export/preview"><input type="hidden" name="token" value="{delete_token}"><input type="hidden" name="back_query" value="{html.escape(filters)}"><button type="submit">Review selected export</button></form>
        </section>'''
    if not entry_markup:
        entry_markup = '<p class="empty">No matching transcripts.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Transcript history</title>
  <style>
    :root {{ color-scheme: light dark; font-family: "Segoe UI", system-ui, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f4f5f7; color: #202124; }}
    main {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 48px; }}
    .topbar {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }}
    h1 {{ margin: 0; font-size: 24px; letter-spacing: 0; }}
    .search {{ display: flex; gap: 8px; width: min(460px, 100%); }}
    input[type="search"] {{ flex: 1; min-width: 0; border: 1px solid #c9cdd3; border-radius: 6px; padding: 9px 11px; background: #fff; color: #202124; }}
    button {{ border: 1px solid #aeb4bc; border-radius: 6px; padding: 8px 12px; background: #fff; color: #202124; cursor: pointer; }}
    button:hover {{ background: #eef0f2; }}
    .entry {{ margin-bottom: 12px; border: 1px solid #d4d7dc; border-radius: 8px; background: #fff; overflow: hidden; }}
    header, footer {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; background: #f8f9fa; }}
    header div, footer {{ flex-wrap: wrap; }}
    header span, footer span {{ margin-left: 10px; color: #646a73; font-size: 13px; }}
    .status {{ margin: 0; border-radius: 999px; padding: 3px 8px; text-transform: capitalize; }}
    .status.ok {{ background: #dff3e4; color: #176b2c; }}
    .status.warn {{ background: #fff0cc; color: #7a5300; }}
    .texts {{ display: grid; grid-template-columns: 1fr 1fr; }}
    .texts section {{ min-width: 0; padding: 14px; }}
    .texts section + section {{ border-left: 1px solid #e2e4e8; }}
    h2 {{ margin: 0 0 8px; color: #646a73; font-size: 12px; font-weight: 600; letter-spacing: 0; text-transform: uppercase; }}
    p {{ margin: 0; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }}
    footer form {{ margin-left: auto; }}
    footer button {{ color: #a22222; padding: 5px 9px; }}
    .error {{ padding: 0 14px 12px; color: #a22222; font-size: 13px; }}
    .filters {{ display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin-bottom:18px; }}
    .filters label {{ display:flex; flex-direction:column; gap:5px; font-size:13px; }}
    input, select {{ padding:9px; border:1px solid #c9cdd3; border-radius:6px; background:#fff; color:#202124; max-width:100%; }}
    input[type="checkbox"] {{ accent-color:#2465a0; width:17px; height:17px; vertical-align:middle; }}
    .export-box {{ padding:16px; background:#eaf2fc; border:1px solid #b8d0ec; border-radius:8px; margin-bottom:18px; }}
    .export-box p {{ margin-bottom:10px; font-size:14px; }}
    .export-box h2 {{ color:inherit; font-size:17px; }}
    .export-box a {{ display:inline-block; margin-top:12px; }}
    .confirm {{ display:block; margin:14px 0; }}
    .selection {{ display:inline-flex; align-items:center; gap:6px; margin-right:12px; font-size:13px; }}
    button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible {{ outline:3px solid #2465a0; outline-offset:2px; }}
    .empty {{ padding: 40px; text-align: center; color: #646a73; }}
    @media (max-width: 720px) {{
      main {{ width: min(100% - 20px, 1180px); padding-top: 16px; }}
      .topbar {{ align-items: stretch; flex-direction: column; }}
      .search {{ width: 100%; }}
      .filters label {{ flex:1 1 140px; }}
      .texts {{ grid-template-columns: 1fr; }}
      .texts section + section {{ border-left: 0; border-top: 1px solid #e2e4e8; }}
    }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #17191c; color: #e6e8eb; }}
      .entry, input[type="search"], button {{ background: #22252a; color: #e6e8eb; border-color: #41464e; }}
      header, footer {{ background: #1d2024; }}
      .texts section + section {{ border-color: #343941; }}
      button:hover {{ background: #2b2f35; }}
      .export-box {{ background:#202d3c; border-color:#405c7c; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="topbar">
      <h1>Transcript history</h1>
    </div>
    {filter_form}
    {controls}
    {entry_markup}
  </main>
</body>
</html>"""


class TranscriptBrowserServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: TranscriptStore) -> None:
        self.store = store
        self.delete_token = secrets.token_urlsafe(24)
        self.export_secret = secrets.token_urlsafe(32)
        super().__init__(address, TranscriptBrowserHandler)


class TranscriptBrowserHandler(BaseHTTPRequestHandler):
    server: TranscriptBrowserServer
    timeout = 5.0

    def _request_origin_allowed(self) -> bool:
        try:
            hosts = self.headers.get_all("Host", [])
            if len(hosts) != 1:
                raise ValueError("Expected one loopback host")
            host = urlparse("http://" + hosts[0])
            if (
                host.hostname not in {"127.0.0.1", "localhost"}
                or host.port != self.server.server_address[1]
                or host.username
                or host.password
                or host.path
                or host.query
                or host.fragment
            ):
                raise ValueError("Unexpected host")
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1:
                raise ValueError("Expected one origin")
            if origins:
                origin = urlparse(origins[0])
                if (
                    origin.scheme != "http"
                    or origin.hostname != host.hostname
                    or origin.port != host.port
                    or origin.username
                    or origin.password
                    or origin.path
                    or origin.query
                    or origin.fragment
                ):
                    raise ValueError("Unexpected origin")
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise ValueError("Cross-site request")
        except ValueError:
            self.send_error(
                HTTPStatus.FORBIDDEN, "Only this local transcript browser may make this request."
            )
            return False
        return True

    def _html(self, page: str) -> None:
        body = page.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._request_origin_allowed():
            return
        parsed = urlparse(self.path)
        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        query = parse_qs(parsed.query)
        filters = {
            key: query.get(name, [""])[0]
            for key, name in (
                ("search", "q"),
                ("from_date", "from_date"),
                ("to_date", "to_date"),
                ("mode", "mode"),
                ("status", "status"),
            )
        }
        try:
            entries = self.server.store.list_entries(**filters)
            total = self.server.store.count_entries(**filters)
        except ValueError as error:
            self.send_error(HTTPStatus.BAD_REQUEST, str(error))
            return
        modes, statuses = self.server.store.filter_options()
        self._html(
            render_browser_page(
                entries,
                delete_token=self.server.delete_token,
                modes=modes,
                statuses=statuses,
                total=total,
                **filters,
            )
        )

    def do_POST(self) -> None:
        if not self._request_origin_allowed():
            return
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        deletion = len(parts) == 2 and parts[0] == "delete" and parts[1].isdigit()
        if not deletion and parsed.path not in {"/export/preview", "/export"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= content_length <= 32768 or self.headers.get("Transfer-Encoding"):
                raise ValueError("Invalid body length")
            body = self.rfile.read(content_length)
            if len(body) != content_length:
                raise ValueError("Incomplete body")
            form = parse_qs(body.decode("utf-8"))
        except TimeoutError:
            self.send_error(HTTPStatus.REQUEST_TIMEOUT)
            return
        except (ValueError, UnicodeError):
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        token = form.get("token", [""])[0]
        if not hmac.compare_digest(token.encode("utf-8"), self.server.delete_token.encode("utf-8")):
            self.send_error(
                HTTPStatus.FORBIDDEN,
                "This form is no longer valid. Reload history and review the selection again.",
            )
            return
        if deletion:
            self.server.store.delete_entry(int(parts[1]))
            search = form.get("q", [""])[0]
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/?q={quote(search)}" if search else "/")
            self.end_headers()
            return
        try:
            raw_ids = form.get("entry_id", [])
            if len(raw_ids) > 500 or any(
                not value.isascii() or not value.isdigit() or len(value) > 18 for value in raw_ids
            ):
                raise ValueError("Select 1 to 500 valid entries.")
            ids = [int(value) for value in raw_ids]
            entries = self.server.store.selected_entries(ids)
            if parsed.path == "/export/preview":
                back = parse_qs(form.get("back_query", [""])[0])
                back_query = urlencode(
                    {
                        key: back.get(key, [""])[0]
                        for key in ("q", "from_date", "to_date", "mode", "status")
                    }
                )
                self._html(
                    render_browser_page(
                        entries,
                        delete_token=token,
                        review_selection=True,
                        back_query=back_query,
                        export_signature=selection_signature(
                            self.server.export_secret, ids, selection_fingerprint(entries)
                        ),
                    )
                )
                logger.info("Transcript export preview: count=%s", len(entries))
                return
            fingerprint = form.get("fingerprint", [""])[0]
            signature = form.get("signature", [""])[0]
            if not hmac.compare_digest(
                signature.encode("utf-8"),
                selection_signature(self.server.export_secret, ids, fingerprint).encode("utf-8"),
            ):
                self.send_error(
                    HTTPStatus.FORBIDDEN, "Export selection was not reviewed. Open a new preview."
                )
                return
            if not hmac.compare_digest(
                fingerprint.encode("utf-8"), selection_fingerprint(entries).encode("utf-8")
            ):
                self.send_error(
                    HTTPStatus.CONFLICT,
                    "Selected entries changed after preview. Nothing was downloaded; review a fresh selection.",
                )
                return
            if form.get("reviewed", [""])[0] != "yes":
                raise ValueError(
                    "Confirm that you reviewed the selected entries and privacy notice."
                )
            format_name = form.get("format", [""])[0]
            output = render_export(entries, format_name)
        except ValueError as error:
            self.send_error(HTTPStatus.BAD_REQUEST, str(error))
            return
        extension, mime = (
            ("json", "application/json") if format_name == "json" else ("txt", "text/plain")
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header(
            "Content-Disposition", f'attachment; filename="selected-transcripts.{extension}"'
        )
        self.send_header("Content-Length", str(len(output)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(output)
        logger.info("Transcript export downloaded: count=%s format=%s", len(entries), format_name)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def launch_transcript_browser(
    store: TranscriptStore,
    *,
    open_browser: bool = True,
    port: int = 0,
) -> tuple[TranscriptBrowserServer, str]:
    server = TranscriptBrowserServer(("127.0.0.1", port), store)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    thread = threading.Thread(
        target=server.serve_forever,
        name="transcript-browser-server",
        daemon=True,
    )
    thread.start()
    if open_browser:
        webbrowser.open(url)
    return server, url


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse the local transcript archive.")
    parser.add_argument("--database", type=Path, default=Path(__file__).with_name("transcripts.db"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = TranscriptBrowserServer(("127.0.0.1", args.port), TranscriptStore(args.database))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Transcript browser: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
