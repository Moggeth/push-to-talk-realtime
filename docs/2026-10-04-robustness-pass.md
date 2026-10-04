# Robustness Pass - 2026-10-04

## Timing Worker

- Replaced queue-based shutdown sentinel with an independent stop event; close
  stops accepting persistence samples and drains already queued work within a
  bounded join. A full queue can no longer swallow the stop signal.
- Dead workers no longer collect unwritable queued samples. Starting after a
  failure/restart is supported; loaded observations are deduplicated from the
  still-live memory cache. Thread-start errors remain nonfatal.
- SQLite context managers commit/rollback but do not close connections. Explicit
  closing now releases the timing database deterministically.
- Invalid timestamps cannot contaminate observations or animation progress.
  Optional prediction/observation errors no longer abort transcript finalization.

Focused tests: first 26 passed/1 failed in 3.35 s; the closure test encountered
SQLite's thread-affinity check before the closed-connection check. The test-only
connection now disables thread affinity for inspection; production still confines
connections to their worker. Expanded suite: 35 passed in 3.10 s.

Inspection, independent review dispatch, timing fixes and verification took
140.419 measured seconds. WorkCodex reviewed lifecycle/output/helper source
read-only through the approved wrapper; no runtime logs, transcript content,
desktop interaction, paid API calls or edits were delegated.
