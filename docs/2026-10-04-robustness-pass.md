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

## Shutdown and Helper Ownership

- Shutdown now signals and wakes output waiters immediately. Polling also bounds
  cancellation when legacy code directly sets the event. Delivery and paste check
  shutdown again before output, including after the paste delay.
- Helper closure snapshots/detaches its process under the same lock as startup;
  old process callbacks cannot terminate a replacement. Capture sends and replies
  are tied to the process generation; closure wakes pending waiters.
- Partial helper startup, broken IPC and malformed JSON responses now clean up
  their owned process/pipes instead of leaving a broken helper marked alive.
- The supervisor deliberately permits readiness to adopt a still-running app.
  Rejected the review's suggestion to kill the child whenever supervision exits;
  that would contradict existing recovery tests and interrupt active dictation.
- The old live-typing correction path is disabled in the actual capture flow;
  its separate edit transactions are not a current runtime failure. Do not enable
  that legacy path without making correction one atomic output transaction.

Initial helper/app checks: 153 passed/1 failed in 3.26 s (the timeout test needed
the new expected-process argument). Expanded helper/app suite: 158 passed in
1.24 s. Tests use fake processes and dummy input backends, not the live application.
