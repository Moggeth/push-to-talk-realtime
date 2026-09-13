# Selected-text Tidy timing and recovery

The Windows F15 hook starts one background selected-text rewrite only after the gesture keys and mouse buttons settle (bounded at three seconds). This prevents held buttons and Ctrl from interfering with Copy. Release the gesture promptly; repeats are consumed.

The job checks exact focus before copying and records a `GetLastInputInfo` snapshot after Copy settles. Replacement requires unchanged field, input and clipboard, plus a fresh copy equal to the submitted selection. Failed safety checks retain both versions in Transcript history and copy the result only if the job still owns the clipboard. API/copy failures preserve the document and restore the previous text clipboard only while ownership is retained. Arbitrary rich clipboard formats are not restored. Focus checks and paste are sequential Windows operations, not an atomic transaction.

The dedicated profile uses the Android uncategorized Tidy instruction and Luna wrapper, `reasoning.effort: none`, `max_output_tokens: 4096`, and `store: false`. It is intentionally independent of desktop dictation Tidy preferences; its default is GPT-5.6 Terra (updated at the user's request), with an optional `SELECTED_TEXT_TIDY_MODEL` override.

## Run and recovery

Start with `python start_push_to_talk.py`; tray Restart loads changes and Quit stops it. No extra daemon or startup entry is required. Metadata-only `[Selected Tidy]` messages in the platform runtime log include outcome and elapsed seconds. History retains original and rewritten text; editor Undo reverses an ordinary paste. Use F15 with selected text for a keyboard-only test. Allow processing to finish without moving/clicking/typing for automatic replacement.

## Validated lessons

- WorkCodex completed the delegated implementation in 245 seconds, but its WSL environment lacked Ruff/pytest. Run this repo's checks using existing Windows Python instead of installing a second test environment.
- The first prompt-equivalence test matched a semicolon inside a Java string. Match the statement-ending semicolon followed by newline. Complete Tidy prompt and wrapper now match Android exactly when the optional sibling checkout exists.
- Review added pre-copy exact-focus validation, fail-closed input tracking, final archive-before-paste, clipboard content/ownership checks and a lock-order-safe recording interlock.
- First live run cancelled because clipboard notification preceded Copy key-up. Wait 80 ms after Copy and require stable clipboard sequence before taking the input snapshot.
- Swiftpoint Simple/Expert mode changes the window handle. Re-select the returned window. Popup indexes may be unavailable: refresh and use screenshot-backed coordinates. Check Manage Devices rather than inferring connection from the Firmware Update Required banner. No firmware change was performed.
- A hidden Notepad process had no usable window; launching its registered app through Computer Use exposed a fresh test editor.
- Runtime can be `start_push_to_talk.py --foreground` or `push_to_talk_realtime.py`; recognize both, verify Ready before restarting, and verify only one tray instance remains.

## Measured validation

- Baseline focused checks: 26/27 passed, 2.22 seconds including inspection; prompt parser failed as described above.
- After review: 39 focused tests, 0.47 seconds; lint/format/test command 1.33 seconds.
- Full suite: 231 passed in 2.26 seconds; lint/format/test command 3.17 seconds.
- Copy settling fix: 19 focused tests in 1.34 seconds; command 2.06 seconds.
- Live F15 test: real Copy, Responses request, visible replacement in fresh Notepad, and archived original/result; 2.396 seconds. The model misread one ambiguous spoken date correction in the synthetic sample; we retained Android's exact behavior, not an assertion of perfect factual accuracy. Review important dates after rewriting.
- Profile backup 0.038 seconds; structural comparison 0.085 seconds. Removing the single added nested record makes before/after configuration identical. HID usage 106 is F15.
- Z3 reconnected at 13:35:15 local time. Swiftpoint logged saveToRAM at .657 and saveToFlash at .924. The nested binding was saved to the PC earlier at 13:30:13. Physical finger-pressure activation still requires a user check; the host F15 path was verified live.
- App reload commands took 0.55 and 0.53 seconds. A duplicate launcher exited through the single-instance guard; one updated tray instance remained.

## Terra model update
Selected-text Tidy now defaults to gpt-5.6-terra, including blank-override fallbacks and archive metadata. Android wording and request parameters are preserved. Verified 19 focused tests (1.39 s), Ruff lint/format, and effective model import. Measured steps: discovery 0.189 s; configuration inspection 0.543 s; edit/test/lint 2.255 s; runtime inspection 0.919 s. No local or user/machine model override was present.
