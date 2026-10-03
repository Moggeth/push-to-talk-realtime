# Usage and Overlap Handoff (2026-10-03)

## Design and Boundaries

Claude subscription commission verified exact `claude-opus-5-5` metadata, with
tools/hooks disabled and only synthetic context plus cursor source. Duration
87.898 seconds. Design: independent r36 outer orbit, 120-degree/second travel,
queued pips, magenta rewrite identity, 560 ms green close/expand/tick completion,
amber fracture for errors. Canvas enlarged to 96 with 4x supersampling.
Codex integrated and verified behavior; no capture or output engine redesign.
The application retains its newest-job primary priority and existing entry
motion rather than adding a second slot-scheduling state machine. Secondary
phase is seeded from the primary when overlap starts; primary geometry remains
identical with/without concurrent jobs. Completion uses explicit bounded terminal
events, not a drop in busy counts or a change of color.

## Accounting

`usage_tracking.py` stores request metadata independently of transcript history.
No paid requests were needed to test accounting. Duration rates are verified
against official model pages, not inferred from token-priced model averages.
Text usage uses response token counts and stores applied price snapshots.
Incomplete requests remain unpriced. Provider-side retries and billing adjustments
cannot be reconciled from this ledger; it is explicitly an estimate.

The monthly report is a Codex heartbeat named `monthly-push-to-talk-spend`, not
an extra background app service. It reads the local content-free CLI report and
does not upload transcript history or invoke a paid transcription API.

## Verified Lessons

- WAL initialization can fail on simultaneous first opens before the normal
  busy timeout helps. Serialize the initial mode change and reuse it afterward.
  Reproduce with a fresh database and multiple writers, not a prewarmed fixture.
- Menu snapshot tests must include new top-level commands. The usage command
  initially failed the old expectation, not application execution.
- Official Markdown documentation endpoints may be rejected by the web tool's
  content-type handling. Direct `Invoke-WebRequest` of the same official `.md`
  URL provides the authoritative pricing/model unit fields.
- Read precise patch context before multi-file edits. One unmatched context
  rejects the entire patch; inspect the diff before retrying rather than assuming
  earlier files applied.
- App health is metadata, not a restart lease. Do not terminate an active user
  session just to load UI changes. Use the tray Restart after work completes.

## Verification Timing

- Opus design: 87.898 s, verified canonical model and personal subscription.
- Focused usage/live/rewrite suite: 32 passed in 2.10 s.
- First cursor/app suite: 162 passed, one outdated menu expectation; 1.81 s.
- First full suite: 362 passed, one fresh-WAL initialization race; 29.93 s.
- Focused usage/overlap regression: 17 passed in 1.70 s after the race fix.
- Full rerun: 363 passed in 28.13 s.
- Final suite including newest-job priority: 364 passed in 28.11 s; Ruff clean.
- Final targeted live/overlap/delivery checks: 21 passed in 1.51 s.
- Offline overlap preview command: 2.113 s; p95 frame render 1.503 ms.

No public GitHub push is authorized. Existing unrelated untracked directories
are preserved. Native physical-device acceptance remains distinct from rendering
tests and metadata-only process health checks.

The running app was deliberately left intact pending the user's answer about
restarting. Changes load on tray Restart; no physical recording or paid API
request was made as verification.
