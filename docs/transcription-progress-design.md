# Learned transcription progress

Independent design recorded before inspecting Power Dictation (2026-10-03).

- Measure release-to-transcript, excluding rewrite, archive and output delivery.
  Separate engine/model keys keep live finalization and recorded requests apart.
- Retain only duration metadata, no audio or text. Bound history to 512 samples
  and 90 days; recent observations have greater weight (14-day half-life).
- Predict from nearby audio lengths in log space, using a weighted 70th percentile
  rather than a fragile seconds-times-length assumption. This tolerates network
  outliers and accounts for request overhead without assuming linear scaling.
- Require eight nearby observations, reasonable spread, and length support.
  Unfamiliar lengths/models and insufficient history retain the existing spinner.
- Freeze each job's prediction at submission. A monotonic eased arc reaches 85%
  of its available fill at the predicted duration, then approaches but never
  reaches completion. Continued rotation signals an outstanding request during
  overruns. Only the actual terminal event triggers completion animation.
- Apply the same mapping to the primary orange ring and the existing outer
  concurrent-transcription ring. Preserve colors, traveler phase and recording.
  Rewrite remains indeterminate; its time is not transcription training data.
- Disk work runs on a bounded background queue, never the audio or render path.
  Failed/empty requests do not become successful timing samples. Persistence
  failures must not disrupt dictation. Do not backfill old mixed-stage metrics.

This is a functional extension of the existing ring design, not a redesign.
Verification must stay headless and leave the running app untouched.

## Implementation and Comparison

`transcription_progress.py` owns bounded in-memory learning and a daemon SQLite
writer. `transcription_timings.db` lives alongside the runtime app log (normally
`%LOCALAPPDATA%\PushToTalkRealtime` on Windows). It stores only engine/model,
audio seconds, transcription seconds and timestamp, independently of transcript
history settings. Shutdown drains queued writes within a bounded wait; an abrupt
exit can lose the latest samples, never the transcript. To reset learning, stop
the app, delete only this database, and start normally. A corrupt database is
logged and ignored; memory-only learning continues until reset/restart.

Once this design was recorded, Power Dictation's `ProcessingTimingStore.java`
was inspected read-only. It uses three duration buckets, defaults and bounded
EWMA updates. We retained our independent nearby-length quantile approach,
per-model separation and indeterminate cold start. No sibling files were changed.

The 40 nearest samples are weighted by log-length similarity and 14-day recency;
ties prefer recent observations, not low latency. Effective sample size and
10th/90th percentile spread gate predictions. Estimates are frozen per job and
the grow-behind-traveler arc preserves its tip position. The existing animation
design/colors are retained; this is not a newly commissioned UI design.

## Verification, Timing and Lessons

Measured wall-clock intervals (nested test timings are not additive):

| Step | Outcome | Seconds |
| --- | --- | ---: |
| Discovery, fetch/pull, independent design and source inspection | Complete; main already current, no publish | 286.577 |
| Implementation, comparison, tests and initial regression launch | Complete | 245.217 |
| Verification follow-through and performance measurement | Complete | 38.202 |
| First focused tests | 40 passed | 1.28 |
| Full regression tests | 397 passed | 28.22 |
| 2,000 full-history prediction calls | 0.180 ms average | 0.359303 |

The older `TranscriptionOutcome.transcription_ms` includes rewrite/archive work;
do not use it to train transcription-only predictions or backfill this database.
Failures and empty transcripts are intentionally excluded. Live measures the
post-release wait, not the full streaming session. Network/server load remains
unpredictable; do not promise exact completion timing.

Review caught a potential bias from sorting equal-distance neighbors by latency;
explicit recency tie-breaking and a regression test prevent fastest-only history.
PowerShell does not expand `tests/test*` as a directory argument to rg: search
`tests` with rg's own glob filtering instead. One initial search failed for this
reason; the directory search succeeded. Patch context must be refreshed after
Ruff formatting; stale context caused two rejected patch attempts, repaired with
fresh source reads and smaller hunks. No unrelated edits were reverted.

Activation is pending normal tray Restart. No Computer Use, native preview,
recording, paid request or app restart was performed. Public GitHub publishing
requires approval; this change is committed locally only.
