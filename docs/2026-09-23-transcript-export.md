# Reviewed transcript export: implementation and verification

Date: 2026-09-22 UTC / 2026-09-23 Australia/Sydney. Scope: local transcript-browser filters and selected-entry handoff. Capture, provider, hotkey, paste, settings and retention paths were not changed or exercised. All data used for verification was invented and held in temporary SQLite databases.

## Measured steps

Checkpoint durations include implementation/reasoning and the stated checks. Command timings are measured wall time; they overlap checkpoint intervals.

| Step | UTC checkpoints or command | Seconds | Outcome |
| --- | --- | ---: | --- |
| Repository/instructions/store/browser discovery | 15:56:02–15:56:34 | 32 | Main already ahead 17; two unrelated untracked folders preserved. Origin verified public with per-process Moggeth credentials. Fetch completed; safe pull was already current. No push authorized. |
| Filters, exact selection access and export document | 15:56:34–15:58:19 | 105 | Reused SQLite store; no schema/capture changes. |
| Server-rendered preview/download integration | 15:58:19–16:00:26 | 127 | Explicit selection, date/count preview, separate raw/final, privacy acknowledgement. |
| Encoding repair and existing tests | command | 1.867 | Existing five browser/store cases passed (1.25 s pytest body). |
| Focused regressions | completed 16:02:57; command | 9.317 | 24 cases passed (8.63 s pytest body). |
| Synthetic headless harness | 16:02:57–16:05:03 | 126 | Temporary DB, no-JavaScript browser flow, no external requests. |
| Accessible-label adjustment and browser check | 16:05:03–16:06:02 | 59 | Full 10-flow browser check passed (1.002 s body, 1.272 s command). Desktop/mobile screenshots inspected. |
| Independent-review fixes and regression expansion | 16:06:02–16:08:26 | 144 | Strict Host/Origin and server-only signing secret; fingerprints include full reviewed rows. |
| Final focused pytest | runner measurement | 13.45 | 33/33 passed. |
| Final headless/Ruff checks | completed 16:09:22; command | 1.304 | 10 browser flows passed (0.973 s body), JavaScript disabled; targeted lint/format clean. |

Usage: 56% used at start; 57% at 16:00/16:03/16:06; 58% at 16:09. No reset, redemption, paid calls or public publication.

## Failures and verified faster paths

- Python's platform-default encoding caused an added middle-dot UI character to be written as CP1252 inside otherwise UTF-8 source. Ruff and pytest rejected the file before execution; the failed check took 0.956 s. Normalize and explicitly write UTF-8/newlines, then format. No archive was involved.
- The first browser smoke used an exact implicit label for the capture-mode select; option text affected its accessible name. It timed out after 8 s (8.556 s command). Added explicit accessible select labels; the next headless run passed.
- Independent review reproduced a foreign-Host request reaching transcript HTML and a client-visible CSRF token being usable as the export HMAC key. The focused synthetic reproduction took 0.763 s command / 0.586 s body. Requests now require expected loopback Host/port, matching Origin when present, and non-cross-site fetch metadata. The signing secret is separate, server-only, and never rendered. Recheck: all three boundary requests rejected with 403, no transcript exposure (0.719 s command / 0.539 s body).
- Full-row fingerprinting includes metadata visible in the preview, even when that metadata is omitted from the downloaded document. Any changed selected row requires a fresh review; deletion never produces a partial export.
- Only target files are staged. The existing 17 local commits and untracked `.codex-remote-attachments/` and `reports/` are not part of this change. The public origin prevents a private push; the feature remains a local, reviewable commit pending a publication decision.

Documentation completed 16:10:57 UTC (95 s after final verification). Synthetic server stopped at 16:11:45 UTC; port 18477 has zero listeners and test browsers are closed. Last usage remains 58% used, no reset. Engineering, documentation and cleanup span 943 seconds from the 15:56:02 start; no real running app was restarted.
