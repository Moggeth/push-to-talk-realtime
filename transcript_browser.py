"""Loopback-only HTML browser for the local transcript database."""

from __future__ import annotations

import argparse
import html
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from transcript_store import TranscriptEntry, TranscriptStore


def _entry_html(entry: TranscriptEntry, delete_token: str) -> str:
    final_text = entry.final_text or "Pending final output"
    status_class = "ok" if entry.post_process_status in {"completed", "not_requested"} else "warn"
    model_parts = [entry.transcription_model]
    if entry.post_processing_enabled:
        model_parts.append(entry.post_process_model)
    metadata = " · ".join(part for part in model_parts if part)
    error_html = ""
    if entry.post_process_error:
        error_html = f'<p class="error">{html.escape(entry.post_process_error)}</p>'
    return f"""
    <article class="entry">
      <header>
        <div>
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
        <form method="post" action="/delete/{entry.id}">
          <input type="hidden" name="token" value="{delete_token}">
          <button type="submit" title="Delete transcript">Delete</button>
        </form>
      </footer>
      {error_html}
    </article>
    """


def render_browser_page(
    entries: list[TranscriptEntry],
    *,
    delete_token: str,
    search: str = "",
) -> str:
    entry_markup = "".join(_entry_html(entry, delete_token) for entry in entries)
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
    .empty {{ padding: 40px; text-align: center; color: #646a73; }}
    @media (max-width: 720px) {{
      main {{ width: min(100% - 20px, 1180px); padding-top: 16px; }}
      .topbar {{ align-items: stretch; flex-direction: column; }}
      .search {{ width: 100%; }}
      .texts {{ grid-template-columns: 1fr; }}
      .texts section + section {{ border-left: 0; border-top: 1px solid #e2e4e8; }}
    }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #17191c; color: #e6e8eb; }}
      .entry, input[type="search"], button {{ background: #22252a; color: #e6e8eb; border-color: #41464e; }}
      header, footer {{ background: #1d2024; }}
      .texts section + section {{ border-color: #343941; }}
      button:hover {{ background: #2b2f35; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="topbar">
      <h1>Transcript history</h1>
      <form class="search" method="get" action="/">
        <input type="search" name="q" value="{html.escape(search)}" placeholder="Search raw or final text" aria-label="Search transcripts">
        <button type="submit">Search</button>
      </form>
    </div>
    {entry_markup}
  </main>
</body>
</html>"""


class TranscriptBrowserServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: TranscriptStore) -> None:
        self.store = store
        self.delete_token = secrets.token_urlsafe(24)
        super().__init__(address, TranscriptBrowserHandler)


class TranscriptBrowserHandler(BaseHTTPRequestHandler):
    server: TranscriptBrowserServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        search = parse_qs(parsed.query).get("q", [""])[0]
        entries = self.server.store.list_entries(search=search)
        body = render_browser_page(
            entries,
            delete_token=self.server.delete_token,
            search=search,
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "delete" or not parts[1].isdigit():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_length = min(int(self.headers.get("Content-Length", "0")), 4096)
        form = parse_qs(self.rfile.read(content_length).decode("utf-8"))
        if form.get("token", [""])[0] != self.server.delete_token:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        self.server.store.delete_entry(int(parts[1]))
        search = form.get("q", [""])[0]
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/?q={quote(search)}" if search else "/")
        self.end_headers()

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
