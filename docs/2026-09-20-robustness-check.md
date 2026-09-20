# Microphone recovery audit

The runtime log records `Device unavailable [PaErrorCode -9985]` at
2026-09-12 20:27:20 and 20:27:22. Recovery retried shortly afterward. Earlier
September 2 logs also contain missing-default and invalid-device failures.
September 19 has closely spaced startup markers, but no corresponding evidence
that establishes why each restart was needed. Recent captures show healthy
stream-ready/first-audio timings. Only one tray process was running at inspection.

Device enumeration currently exposes Wireless MICRO, VIVE Pro and Yeti Nano
microphone inputs, repeated across Windows host APIs. The selected source is
the system default. Multiple connected microphones alone are not evidence of
a failure. A fresh diagnostic process's device list does not prove which
device an already-open long-running stream is receiving.

Confirmed code weaknesses repaired:

- Normal and warm stream startup failures did not reliably close the partial
  stream before another attempt, potentially retaining device resources.
- Normal recorder shutdown skipped close when stop raised.
- An unexpected exception could terminate the microphone recovery watchdog.
- Recovery and consumer attachment had a race that could detach an active
  recording. Readiness/attachment is now atomic; idle reopening refuses an
  attached consumer and skips pending starts.

Added deterministic failure-injection tests. No recordings were sent to an API
for this audit, no microphone preference was changed, and raw transcript
logging/output behavior was not altered. Native driver hangs and default-device
topology changes remain areas for future investigation; these changes do not
claim to solve an unproven historical cause. Reopen logging now includes the
actual opened device index to improve future diagnosis.
