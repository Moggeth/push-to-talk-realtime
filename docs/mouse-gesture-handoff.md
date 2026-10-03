# Mouse Gesture and Bullet Mode

## Behavior and Boundaries

- Recognition is enabled by default but only samples pointer position while the
  actual dictation trigger remains held. Work-log capture, idle time, transcription
  alone, and tap-to-record after releasing the trigger are excluded.
- Four alternating vertical legs, each at least 45 pointer-coordinate units,
  with no more than 45 units horizontal drift. The recognition window starts on
  the first completed leg and lasts 0.9 seconds; minimum elapsed time is 0.18 s.
  A 1.5-second cooldown plus 0.3-second quiet period rearms the detector.
- Sampling uses the existing pynput dependency, 60 Hz while held, 10 Hz state-only
  checks while idle. No low-level mouse hook, event suppression, input injection,
  coordinate storage or added service. Errors back off ten seconds and leave the
  dictation path intact. Initialization is optional and cannot block app startup.
- Bullet mode survives between recordings in memory, resets off on app restart,
  and is frozen per capture before concurrent transcription. The preference to
  disable gesture recognition persists in settings. The tray offers both controls.
- One capture is one Markdown bullet, with interior whitespace collapsed and a
  pasted trailing newline. It does not send Enter or inspect editor selection.
  Start on an empty line. Existing punctuation settings still apply. Raw history
  remains verbatim; both sides of a rewrite review use the same bullet formatting.
- Existing ring colors/animation remain unchanged; the current label surface shows
  three bullet dots, including when ordinary mode labels are disabled.
- Structured diagnostics retain boolean mode/enable changes and sanitized errors,
  never pointer coordinates or transcript content.

## Verification and Learning

Independent synthetic tests avoid controlling the user's desktop. The full suite
passed 424 tests in 28.41 s; physical mouse sensitivity remains unverified. The
user can disable the gesture without disabling Bullet mode if it is too sensitive.

Measured intervals, with nested tool/test durations not additive:

| Step | Outcome | Seconds |
| --- | --- | ---: |
| Repo/auth/sync, source inspection, interaction clarification | Complete | 104.913 |
| Implementation and focused test correction | 170 focused tests passed | 319.375 |
| Full-suite verification and source review | 424 passed | 114.920 |
| Initial focused suite | 160 passed, 7 failures | 4.82 |
| Failure-only rerun | Confirmed stale mock/settings expectations | 0.75 |
| Corrected focused suite | 170 passed | 1.06 |
| Full regression suite | 424 passed | 28.41 |

Initial failures were test doubles lacking the new keyword, expected settings
missing the new boolean, and a new fixture overlooking default terminal punctuation.
Update boundary mocks with explicit keyword support; set punctuation intentionally
in formatting tests. Review also caught a nested non-reentrant state lock before
execution: the toggle now uses a lock-owned predicate, with stale-session checks.
The gesture window must begin with motion, not recording start; a stationary lead-in
test guards against arbitrary timeout-boundary misses.

The sibling gesture_smoother has no README and its sole script interpolates robot
motor poses, not mouse gestures; no code was reused or changed. A failed patch
used pre-formatting test context; reread formatted source and apply smaller hunks.
Other concurrent readiness-task changes and generated tracked bytecode were not
included in this feature commit. No restart, live mic/API test, Computer Use or
public push. Activation waits for the user's normal tray Restart.
