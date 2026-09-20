# Broad reliability pass

Scope: recording lifecycle, worker shutdown, allocation pressure, settings
persistence, transcript storage and the local browser. An independent read-only
WorkCodex review covered storage/settings/transcription; no runtime transcripts
or secrets were included in that review.

Verified weaknesses addressed:

- A dependency or recorder-preparation exception could leave a pending/active
  capture flag set, blocking future dictation. Explicit cleanup now releases
  capture and output ownership on those paths.
- Capture monitoring waited only for a release flag, including during shutdown
  or after losing ownership. It now exits for shutdown/inactive/superseded
  sessions; shutdown cancels the realtime worker rather than finalizing audio.
- Recorded PCM was copied block-by-block after capture despite no further
  mutation. Only the list of references is copied now. Live transcription kept
  delta strings only to test their presence; an item-ID set replaces that
  duplicate text, and the app skips collecting unused live-typing deltas.
- Concurrent preference saves shared a temporary filename and could publish an
  older snapshot or fail replacement. A reentrant I/O lock spans snapshot and
  replacement, including legacy migration writes.
- Non-boolean JSON values such as the string `false` became true through Python
  truthiness. Actual booleans are now required for those saved switches.
- Database setup errors leaked the newly opened connection; setup now closes
  it before propagating the error.
- Negative, malformed and oversized Content-Length values could crash or stall
  local browser handlers. Input validation, bounded reads, UTF-8 validation and
  a five-second socket timeout now limit those failure paths.

No dependencies, telemetry, services or recurring background polls were added.
Raw-text archiving, model choices, mouse bindings and default recording mode
are unchanged. This is not a guarantee against native driver deadlocks, OS hook
removal or power-loss/storage faults; no forced driver resets were introduced.

Tests reproduce failures using mocks, synchronized writer threads and real
loopback HTTP requests. No live transcription requests are needed for this pass.
