# Testing (Plain Language)

## Content-free lifecycle diagnostics (2026-10-02)

`test_runtime_diagnostics.py` verifies strict payload omission (including provider
exception messages and multiline text), sanitized stack locations, bounded rotation,
unclean versus deliberate previous exits, corrupt-record handling, stale/mismatched
health, busy versus listener-down state, logging failure isolation, supervisor launch
failure/native-like exit/retry events, duplicate launch events, native stack dumps
without variable contents, and real PowerShell wrapper cold/normal/abnormal exits.
The Windows support report test reads a synthetic manager log containing a secret
sentinel and asserts it preserves only failure/exit metadata. No mic/API recording,
clipboard access or injected hotkey is used. The wrapper test prints sentinels to
both stdout and stderr and proves they are drained without appearing in diagnostics.

Run this with the existing supervisor/readiness/app/start-script regression suites.
Use an isolated workspace --basetemp and -p no:cacheprovider when cache ACLs differ.
Initial tests found duplicate heartbeat keys, a test asserting against its own
function name, and a Windows PowerShell default-parameter $PSScriptRoot issue;
resolve script-relative defaults in the body. A further real-child test found
Get-FileHash missing in a nested PowerShell session despite working interactively.
The bootstrap now computes hashes with .NET SHA256, avoiding that module dependency.
These failures were resolved before installation. Do not infer success from only
the cold-path test: exercise both executable-present and executable-missing paths.

Keep native log handles open until faulthandler is disabled. Do not rotate an open
native descriptor; startup rotation occurs before installation. Native stack dumps
contain locations, not source lines or locals (Python faulthandler documentation).
No forced native crash is required to verify the stack output format.

Live deployment must preserve the app PID while replacing only supervision. Verify
outer task/Python run correlation, app-health unknown for old app code, and an
injected supervisor-only failure yielding task python_exited plus a replacement
supervisor previous_run_unclosed event. App heartbeat/privacy activation remains
pending until a separately approved app restart. Health is not a queue-drained lease.

## Windows readiness recovery (2026-10-02)

`tests/test_windows_readiness.py` checks orphan adoption without interruption,
duplicate supervisor exclusion, real mutex release on process death, synthetic
supervisor death followed by adoption and child crash recovery, fail-closed app
mutex errors, durable bootstrap exceptions, task-aware startup toggles, and no idle
microphone startup with pre-roll disabled. Fixtures use unique kernel object names
and temporary paths; they do not control the live app, hotkeys, clipboard or mic.
Combined lifecycle/audio/session/startup/supervisor regression: 186 passed in 4.64 s.
Ruff check and format check passed for all changed Python files.

Use a fresh workspace `--basetemp` on this machine: the shared pytest temp folder
may reject sandbox access. One cache warning occurred under an existing copied
pytest cache; it did not affect assertions. Initial synthetic process termination
with taskkill could not terminate the fixture in the sandbox; the corrected fixture
signals its own child to `os._exit(7)`, testing abrupt failure without host process
enumeration. Copied bytecode can display old source paths in pytest; sources under
the selected worktree still execute. If the execution transport disconnects,
reconnect before assuming the app or test failed.

Live acceptance must export/inspect the registered task, confirm interactive limited
user, logon and unlimited one-minute trigger, PT0S execution limit, IgnoreNew and
battery-safe settings. Terminate only the supervisor PID and observe a new task
supervisor monitoring the unchanged app PID. Do not kill an active dictation process,
reboot, log off, inject a hotkey or test the microphone for this check. A synthetic
task may test fresh launch/crash recovery without importing audio/GUI code.

Limits: process and synthetic tests do not prove physical microphone/API/hotkey
end-to-end behavior, a real next logon, or recovery from an entirely frozen app.

This project has quick automated checks plus a manual checklist for the audio
and tray behavior. The automated checks are meant to be fast and verbose.

## Automated checks (run these every time)

1) Lint (Ruff)

```
ruff check .
```

Expected result:
- If clean: a short "All checks passed" message.
- If not: a list of rule codes + file/line so you can fix them.

2) Format check (Ruff)

```
ruff format --check .
```

Expected result:
- If formatted: "All files are formatted".
- If not: file names + a diff of what Ruff would change.

3) Unit tests (Pytest, verbose)

```
pytest -vv
```

Expected result:
- Each test name shows up as `PASSED`.
- Final summary looks like `77 passed in X.XXs` (or higher as coverage grows).

4) Coverage gate (matches the Linux CI quality job)

```
pytest -vv --cov --cov-report=term-missing
```

Expected result:
- A coverage table is printed.
- Total coverage stays at or above `70%`.

CI now runs:
- A Linux quality job on Python 3.12 for Ruff + the coverage gate.
- Compatibility pytest jobs on Ubuntu, Windows, and macOS using Python 3.11.
- Dummy `pynput`/`pystray` backends so headless CI can still import and test the app logic.

## Unit tests included (what they validate)

  - App orchestration and state helpers:
  - Device descriptor resolution, fallback device picking, and device list refresh.
  - Clipboard paste flow, work-log append behavior, and tray status updates.
  - Keyboard and mouse hotkey press/release transitions, double-tap work-log handling, and toggle mode stop behavior.
  - First-press startup race handling: a release that arrives while a session is still starting is remembered and stops the new recording cleanly.
  - Persisted dictation hotkey kind/tokens, GPT Live default, archived GPT-4o/Whisper model migration to GPT Transcribe, checkout-to-user-data settings migration, default-on transcript history, startup toggle helpers, hotkey capture helper parsing, tray restart/quit actions, grouped menu hierarchy and bounded active-value labels, tray startup/shutdown, and `main()` bootstrap wiring.
  - GPT Live Transcribe session configuration, 16-to-24 kHz audio streaming, append/commit ordering, completed transcript reconciliation, and structured API errors.
  - Direct transcription-engine contracts, including recorded request payloads and realtime websocket events; tests do not rely on forwarding functions in the tray module.
  - Warm microphone stream lifecycle, bounded pre-roll ordering, stale-callback detection, automatic reopen, first-audio measurement, and static realtime finalizing visuals.
  - GPT post-processing model/profile persistence, tray controls, custom instruction loading, Responses API payloads, blank-input handling, raw-transcript fallback on API failure, reference-counted processing state, target-dominant color transitions, and distinct activity animation frames.
  - Always-on SQLite transcript storage, raw-before-GPT ordering, finalization and failure status, search, deletion, HTML escaping, loopback browser requests, deletion-token validation, and browser shutdown.
  - Single-instance startup guard, hotkey-listener watchdog restart, and delayed restart helper behavior.
  - Shared session lifecycle cleanup for pending starts, aborted capture, normal completion, and ordered transcript delivery.
  - Recorder shutdown failure recovery, abandoned output-slot advancement, bounded output waits, and late-result rejection.

- `test_apply_punctuation_options_normalize_capitalize_terminal`
  - Input: `"  hello   world  "`
  - Expected: `"Hello world."`
  - Logic: whitespace normalized, first letter capitalized, terminal period added.

- `test_apply_punctuation_options_trims_spaces_before_newline`
  - Input: `"First sentence. \nSecond sentence."`
  - Expected: `"First sentence.\nSecond sentence."`
  - Logic: no trailing space before the line break.

- `test_apply_punctuation_options_keeps_terminal_punct`
  - Input: `"Already!"`
  - Expected: `"Already!"`
  - Logic: do not add an extra period.

- `test_apply_punctuation_options_empty_input`
  - Input: `""`
  - Expected: `""`
  - Logic: empty input short-circuits cleanly.

- `test_prepare_clipboard_text_suffix_space_only_at_end`
  - Input: `"First sentence. \nSecond sentence."`
  - Expected: `"First sentence.\nSecond sentence. "`
  - Logic: only one trailing space, at the very end.

- `test_prepare_clipboard_text_terminal_punctuation_with_space_suffix`
  - Input: `"first sentence second sentence"`
  - Expected: `"first sentence second sentence. "`
  - Logic: enforce terminal punctuation and keep exactly one trailing space.

- `test_prepare_clipboard_text_suffix_newline`
  - Input: `"Hello"`
  - Expected: `"Hello\n"`
  - Logic: newline suffix appends once.

- `test_prepare_clipboard_text_suffix_none`
  - Input: `"Hello"`
  - Expected: `"Hello"`
  - Logic: no suffix added.

- `test_prepare_clipboard_text_empty_input`
  - Input: `"   "`
  - Expected: `""`
  - Logic: empty/whitespace input yields empty output.

- `test_get_paste_modifier_uses_ctrl_on_linux`
  - Input: `"Linux"`
  - Expected: `Key.ctrl`
  - Logic: Linux paste uses `Ctrl+V`, without the root-only `keyboard` package.

- `test_supports_foreground_console_detection_only_on_windows`
  - Input: `"Windows"`, `"Linux"`, `"Darwin"`
  - Expected: `True`, `False`, `False`
  - Logic: the global spacebar shortcut only runs where console foreground
    detection is actually supported.

- `test_get_paste_modifier_uses_ctrl_on_windows`
  - Input: `"Windows"`
  - Expected: `Key.ctrl`
  - Logic: Windows paste keeps using `Ctrl+V`.

- `test_get_paste_modifier_uses_cmd_on_macos`
  - Input: `"Darwin"`
  - Expected: `Key.cmd`
  - Logic: macOS paste uses `Cmd+V`.

- `test_send_paste_shortcut_presses_modifier_then_v`
  - Input: fake controller
  - Expected: modifier pressed, `v` pressed/released, modifier released
  - Logic: the app sends one paste chord in the right order.

## Manual tests (audio + tray behavior)

1) Startup
- Run: `python .\push_to_talk_realtime.py`
- Expected: a tray icon appears and the console prints the ready message after the hotkey listener is active.
- Expected: `push_to_talk_realtime.log` is created in the repo root.

2) Dictation hotkey (F13 by default)
- Hold the mouse button remapped to F13, speak one sentence, release.
- Expected: beep on start/stop (if enabled), a transcript appears, and the text
  pastes into the active app.
- While transcription is processing after key release, non-AppIndicator backends update the tray icon.
- On Ubuntu/AppIndicator, the tray icon stays static for stability and the status change is written to `push_to_talk_realtime.log`.
- Immediately after launch, do one short hold/release. Expected: the release is honored even if the audio session is still starting.
- After a fresh Windows login, wait at least 90 seconds and then press F13 once. Expected: the service has rebound the listener after startup and dictation begins without manually restarting the tray.
- Speak immediately as F13 is pressed. Expected: the opening syllable is retained, and the log records `[Capture metrics]` with stream-ready, first-audio, and pre-roll timings.
- Leave the app running through a microphone disconnect, sleep/wake, or device reset. Expected: the log records `[Audio] Warm microphone stream is inactive or stale; reopening it.` and subsequent captures contain audio.
- Expected: tray animation and hotkey-listener recovery remain responsive while the microphone watchdog is attempting a slow or failing reopen.

3) Set Hotkey dialog
- Open `Shortcuts & startup`, click `Dictation: <current>...`, press a key or combo, confirm the drafted label looks right, then click `Accept`.
- Expected: the tray menu immediately shows the new dictation hotkey.
- Expected: the hotkey only starts dictation when the drafted keys are the only keys being held, except for `Shift + hotkey` system-audio capture.

4) Realtime live typing (GPT Live Transcribe)
- In the tray menu, open `Transcription: <current>` and select `GPT Live Transcribe`.
- Hold the mouse button remapped to F13 and speak 1-2 sentences.
- Expected: text starts appearing before key release; releasing F13 finalizes punctuation/suffix.
- Expected: logs identify `gpt-live-transcribe`; no fallback model or local chunking path appears.
- Expected: releasing F13 sends one explicit audio-buffer commit and the completed transcript replaces any partial result.
- Expected: after release, any brief server reconciliation uses a static orange finalizing icon rather than the spinning orange recorded-transcription waveform.
- Interrupt connectivity during a live capture. Expected: the worker exits after the bounded ready/final deadline and cancellation grace period, with no recorded-model fallback and no lingering realtime thread.
- If a deliberately constrained `REALTIME_AUDIO_QUEUE_MAX_CHUNKS` overflows, expected: the dropped 40 ms chunk count is written to the log after capture.

5) Shared input device menu
- Open the tray menu, choose `Audio input: <current>`, then select a different microphone/input.
- Expected: both normal dictation and work-log capture switch to the same selected device.

6) System audio dictation
- Start playing a video or song.
- Hold `Shift + F13` while the audio is playing, then release.
- Expected: on Windows, the app captures the active system output loopback instead of the microphone and transcribes that audio on release.
- Expected: on non-AppIndicator tray backends, the tray icon is blue while system audio is recording instead of the normal red microphone recording color.
- Expected: if `Shift` is released before `F13`, the icon stays blue and system-audio recording continues until `F13` is released.
- If the default output is not the target, set `SYSTEM_AUDIO_DEVICE` to a speakers/headphones name fragment. If loopback is unavailable, set it to a Stereo Mix-style input name or index.

7) Linux non-root paste path
- Run the app as a regular user on Linux, hold F13, speak a short phrase, release.
- Expected: no `ImportError: You must be root to use this library on linux.`
- If the target app does not accept simulated paste, expected fallback: the app
  logs that the transcript stayed on the clipboard instead of crashing.

8) Multi-sentence spacing (your request)
- Hold F13, speak 3-5 sentences with clear full stops, release.
- Expected: the pasted text has normal spacing between sentences, and only a
  single trailing space at the very end (no extra spaces at line breaks).

9) Punctuation toggles
- Toggle "Ensure terminal punctuation", "Capitalize first letter", and
  "Normalize whitespace" from `Text output`.
- Expected: dictation + work log reflect the settings on the next run.

10) Unified transcription selector
- Open `Transcription: <current>` and switch between GPT Live Transcribe and GPT Transcribe.
- Expected: selecting any recorded model switches to record-then-paste and uses that model on the next dictation.
- Expected: selecting GPT Live Transcribe switches to streaming with no automatic recorded-model fallback.

11) Engine preference persistence
- Select GPT Live Transcribe, exit app, and relaunch it.
- Expected: the tray still shows GPT Live Transcribe selected.
- Then select GPT Transcribe, relaunch again, and confirm it remains selected in recorded mode.
- Update or replace the repository checkout and relaunch.
- Expected: the previous selection is retained from the platform user-data settings file.

12) Dictation hotkey persistence
- Use `Set Hotkey...` to save a new dictation key or combo, exit the app, relaunch it.
- Expected: the tray still shows the saved dictation hotkey and it works without reconfiguration.

13) Transcript history (default on)
- Dictate once with the normal dictation hotkey, then open the history file from the tray.
- Expected: a new line is appended with a full date/time stamp and a `[Dictation]` tag.
- In `History`, toggle `Save legacy text log` off, dictate again, and confirm no new dictation history line is added.

14) Work log hotkey (disabled by default; configure F16 for this test)
- Hold F16 for at least ~0.25s, speak a short sentence, release.
- Expected: a new timestamped line appears in `work_log.txt` with a `[Work log]` tag.

15) Mute monitor (optional)
- Enable `Text & behavior` -> `Mute monitor`, then start recording while silent.
- Expected: after ~1.5s, a "Muted?" hint appears in the console/tray tooltip.

16) Device hot-swap fallback
- While the app is running, unplug and replug the USB mic, then press F13.
- Expected: no crash; the console logs a retry/fallback message and recording
  continues or exits cleanly if no input device is available.

17) Work log double-tap
- Double-tap F16 while idle.
- Expected: `work_log.txt` opens and no new recording starts.

18) Overlap while transcribing
- Dictate once with F13, release, then press F13 again before the first transcript finishes.
- Expected: the second recording starts immediately.
- Expected: both transcripts still appear, and they paste in the order the recordings were made.

19) GPT transcript post-processing

- Under `Cleanup settings`, select `Clean up speech` from Instructions and choose a model, then enable the root `GPT cleanup` checkbox.
- Dictate a sentence with filler words or a false start, then release the hotkey.
- Expected: the final pasted text is revised according to the selected instructions; the recording behavior is unchanged.
- Expected: after orange transcription begins, the tray icon changes to an animated magenta while GPT revises the text, then returns to green when output finishes. The tooltip says `Post-processing` when tooltips are enabled.
- Expected: each color change is recognizable on its first frame and settles smoothly within the next two frames; orange shows a moving waveform and magenta shows a subtly pulsing sparkle inside the orbit.
- Switch to `Custom instructions`, open the custom instructions file, add a small rule such as preserving a product name exactly, save it, and dictate again.
- Expected: the next result uses the edited instruction without restarting the tray app.
- Temporarily disconnect the network and dictate again.
- Expected: the post-processing failure is logged and the original transcript is still pasted instead of being lost.
- With GPT Live Transcribe selected, expected: enabling cleanup suppresses live delta typing and pastes the revised final text after release.

20) Raw transcript archive and browser

- Capture one normal dictation and one `Shift + F13` system-audio dictation, with GPT post-processing enabled for at least one of them.
- Open `Open transcript browser` from the tray.
- Expected: the browser opens on a `127.0.0.1` address and shows each capture with raw and final text side by side, source/model metadata, and processing status.
- Search for a phrase from either raw or final text.
- Expected: matching entries remain visible.
- Delete one entry.
- Expected: it disappears after the redirect and remains gone after closing and reopening the browser.
- Disable `History` -> `Save legacy text log`, dictate again, and reopen the browser.
- Expected: the new raw/final entry is still archived because the toggle controls only `work_log.txt`.

21) Run on startup toggle
- Open `Shortcuts & startup` -> `Run at login`.
- Expected on Linux: a user systemd service is written/enabled for the current checkout and starts immediately.
- Expected on Windows/macOS: the platform startup artifact is created for the current checkout.
- Toggle it off again.
- Expected: the startup artifact is disabled or removed cleanly.

22) Tray restart and quit actions
- If running under the included user systemd service on Linux, click `Restart service` and `Quit` from the tray.
- Expected: `Restart service` restarts the service cleanly and the tray returns.
- Expected: the dictation hotkey still works after the restart without needing a second manual relaunch.
- Expected: `Quit` stops the service.
- If running the script directly instead of under systemd, `Restart` should relaunch `push_to_talk_realtime.py` and `Quit` should only close the current process.
- Start the app twice manually.
- Expected: the second launch exits without creating another tray icon or second global hotkey listener.

23) Starter script
- Run `python start_push_to_talk.py`.
- Expected on Linux with the user service installed: the command returns quickly and the service becomes active.
- Expected otherwise: the command returns quickly and a detached tray process keeps running after the terminal closes.
- For debugging, run `python start_push_to_talk.py --foreground`.

24) Mouse-side-button remap
- Map a spare mouse button to `F13`, relaunch the app, then hold that button and speak.
- Expected: dictation starts/stops cleanly and other apps do not react to the remapped mouse button.

25) Ubuntu tray interactivity
- On Ubuntu GNOME/Wayland, launch the app from `python start_push_to_talk.py`.
- Left-click or right-click the tray icon.
- Expected: the tray menu opens and root actions such as `GPT cleanup`, `Transcription`, `Restart`, and `Quit` are clickable.
- Expected: active transcription, audio input, and cleanup model appear in their submenu labels.
- Expected: GPT cleanup takes one click; selectors take two; low-frequency toggles are grouped by task.

26) Runtime logging
- Use dictation once, then inspect `%LOCALAPPDATA%\PushToTalkRealtime\push_to_talk_realtime.log` on Windows (or the documented platform runtime-data directory).
- Expected: each line has a timestamp and thread name.
- Expected: tray state changes, startup details, and any unhandled thread exception are written there.
- Expected: detached-launcher output is written to `push_to_talk_starter.log`, not appended by a second writer to the application log.
- Set `PUSH_TO_TALK_LOG_MAX_BYTES=65536`, generate enough log output to cross the threshold, and restart or continue using the app.
- Expected: `.1` through the configured backup count are retained and the active log continues accepting entries.

27) Runtime-data migration
- With the app stopped, place a legacy `work_log.txt` or test `transcripts.db` beside the script and ensure the corresponding runtime-data destination does not exist.
- Start the app once. Expected: the file moves to the platform runtime-data directory and the migration is logged.
- For the legacy app log, expected: older checkout lines are preserved before any new startup lines already written at the destination, and the checkout copy is removed.
- Expected: an explicit `WORK_LOG_PATH`, `PUSH_TO_TALK_TRANSCRIPT_DB_PATH`, `PUSH_TO_TALK_LOG_PATH`, or `OPENAI_POST_PROCESS_INSTRUCTIONS_PATH` prevents migration for that file.

Development note: after structural Python edits, run `ruff format` on the changed files as the final step after the last patch, then run `ruff check` and `ruff format --check`. This avoids repeating the import-order and wrapping-only failures seen during the runtime-path and watchdog extractions; behavioral tests had already passed in the first case, and the second check stopped before tests.

Microphone recovery regression checks (2026-09-20):
- `tests/test_session_failure_recovery.py` injects dependency, recorder-construction and recorder-start exceptions and verifies pending/active recording and output-slot recovery. It also checks monitor exit after shutdown, session replacement and inactive capture without relying on a key-release event.
- `tests/test_persistence_resilience.py` forces overlapping settings saves using events, checks malformed persisted boolean types, forces database setup failure, and sends malformed/oversized/non-UTF-8 and stalled requests to the loopback browser. These tests use temporary state and no API calls. The browser socket timeout must bound reads, not merely cap declared body length.
- Session tests must isolate `shutdown_event`. Adding the shutdown upload guard exposed an old test-order dependency: an earlier tray-exit test left the shared event set. Give each session test its own event rather than weakening production shutdown cancellation. Failed settings replacement must preserve the previous file unchanged.
- Native shortcut smoke tests require the actual Windows foreground HWND to match the test window before injecting keys. On 2026-09-20 Tk reported entry focus but Windows retained another foreground window, resulting in no field key events and failed Paste assertions. Topmost/focus_force and removing the tray's other hook did not resolve it. The test now checks the Win32 foreground directly and aborts without injection if activation is denied; rerun from an interactive foreground terminal, not by repeatedly retrying an inactive GUI test.
- `tests/test_audio_recovery.py` injects failed warm/normal stream starts, stop errors, a watchdog exception, pending capture startup, and a stale stream with an attached consumer. Verify close-before-retry, close-even-after-stop-failure, bounded retry, and preservation of the active recording token.
- When investigating restarts, filter runtime logs for audio/startup/capture metrics rather than dumping transcript text. Windows exposes each physical microphone through multiple host APIs; the number of device-list entries is not the number of physical microphones.
- Keep the readiness check and consumer attachment under the same capture lock. Background reopening must atomically refuse an attached consumer, even if the stream became stale between the watchdog's state check and acquisition of the stream lock.

For a new Python module, use `ruff check --fix <file>` before the final `ruff format`; formatting alone does not organize imports. The cursor-indicator check initially stopped on that mechanical distinction before tests ran.

Do not create a Tk root on a worker thread for this overlay. The first live smoke test rendered correctly but emitted `Tcl_AsyncDelete` during interpreter cleanup. The maintained implementation uses a native Win32 window and message loop in its worker thread, which starts and shuts down without Tcl thread ownership.

Do not use Win32 `SetTimer` for the high-refresh cursor animation. An 8 ms timer request measured only about 64 painted frames per second on this machine because USER timers were quantized. The paced native message loop with balanced `timeBeginPeriod(1)` / `timeEndPeriod(1)` calls measured 120.5 painted frames per second at the 120 Hz target.

The cursor overlay uses a 32-bit top-down DIB and `UpdateLayeredWindow` with premultiplied alpha. Render the artwork at 4x resolution and downsample with Lanczos; returning to GDI pens or color-key transparency restores visibly aliased one-bit edges. The supersampled alpha path retained a measured 120.0 frames per second on this machine.

Cursor activity transitions share one stateful phase accumulator. Recording-to-transcription changes must update color and speed targets without constructing a new animation or recomputing the angle from a new speed multiplier; either approach visibly teleports the traveler. Only a fully completed lifecycle resets the starting phase.

Threaded tray tests must isolate every worker started by `tray_setup` and stop it in fixture teardown. The watchdog extraction initially exposed one test that mocked the animation worker but not the new microphone worker; the faster repeatable pattern is to mock the worker start in setup tests and call its stop helper in the shared fixture.

28) Windows cursor recording indicator
- During an active overlay smoke test, hide its window with `ShowWindow(hwnd, 0)`. It must become visible on the next frame without stealing focus. Overlay startup logs `Alpha overlay ready`; unexpected shutdowns retry after five seconds.
- Hold the dictation trigger and move the pointer across multiple windows. Expected: a thin red ring tracks the pointer without stealing focus or blocking clicks.
- Watch the first 160 ms after pressing the trigger. Expected: the ring expands smoothly from the cursor point instead of appearing at full size.
- Hold Shift before the dictation trigger. Expected: the ring is blue for the full latched system-audio capture, including after Shift is released.
- Release the recording trigger. Expected: the traveler keeps its current angular position while the ring eases into orange and accelerates; it must not restart from a fixed position.
- Watch completion. Expected: the still-moving orange ring contracts into the cursor over about 200 ms instead of disappearing abruptly.
- Watch the ring on a high-refresh display while recording. Expected: motion is fluid at the 120 Hz target without affecting pointer movement, capture, or transcription latency.
- Inspect the thin circular track against both light and dark windows. Expected: curved edges are smoothly alpha-blended with no dark halo, square background, or visibly stair-stepped pixels.
- Set `CURSOR_RECORDING_INDICATOR=0` and restart. Expected: recording behavior is unchanged and no pointer ring appears.

- With the work-log key empty, pressing/releasing F14 must not create a capture or a delayed work-log thread. F13 dictation remains active. Covered by `test_disabled_worklog_does_not_handle_f14`.

29) Per-recording Raw / Tidy / Fun
- `tests/test_recording_modes.py` covers reset to Raw, cycling during pending startup and capture, immutable mode after release, repeat suppression, release after recording ends, passthrough outside recording, and tagged application output. It checks raw archival before either rewrite profile even with legacy logging disabled.
- `python tests/manual_mode_chord.py` is an opt-in native Windows smoke test. It briefly focuses its own text field, temporarily replaces/restores the text clipboard, and checks suppression, all three modes, ordinary Paste and tagged application Paste. It makes no audio or API requests. Do not use the keyboard/mouse during its approximately four-second run.
- Physically hold Rear Edge and click right fingertip once/twice/three times: cursor label must read Tidy/Fun/Raw. Hold fingertip down: no further cycling. Release Rear Edge first, then fingertip: capture must stop without a stray paste. Repeat with Shift system-audio capture. Start another recording: Raw again.
- Open Transcript history and compare raw/final versions of a Tidy and a Fun capture. API failures must retain raw output; archive failures must skip rewriting. Settings retains the user's selected model and custom Tidy instructions.
- Native suppression must use `win32_event_filter` and `suppress_event`, not a normal `on_press` callback (which cannot prevent Paste reaching the application). App-generated Paste carries `PASTE_EVENT_TAG` so overlapping recordings cannot reinterpret their own output as a mode change.
- Earlier tests assumed persistent cleanup and the old menu layout; update those expectations when testing per-recording mode selection, rather than restoring the obsolete behavior.
- Mode-label pixel bounds are tested for Raw/Tidy/Fun. The first 76-pixel surface clipped antialiasing below the label; an 88-pixel transparent surface with a five-pixel bottom inset preserves the existing ring radius and gives the larger label room.

30) Flat settings window and symbolic feedback
- `tests/test_settings_window.py` verifies migration of existing Tidy instructions, independent Tidy/Fun preferences across save/reload, invalid-profile rejection, symbol pixel bounds and phase continuity on a mode switch.
- `python tests/manual_settings_window.py` opens a temporary native window, checks all four tabs at 700x610 and 560x480, exercises independent editor saving without applying changes to the live app, and generates screenshots plus a 600-frame rendering benchmark in ignored `output/`. No audio or API requests are made.
- Native screenshot verification must lift the test window and wait for Windows' opening animation before capture; immediate screenshots can show translucent/occluded application content. The minimum-size test caught feedback rows overflowing after the legacy-history control was added; reduced row padding is covered by the same bounds check.
- Open Settings from the tray and by double-click. Opening again restores the existing window instead of creating duplicates. Save independent models/instructions, restart, and check both tabs. Cancel must leave runtime settings unchanged. Recording should remain responsive with the settings window open.
- Cursor symbols: Raw is a plain arc; Tidy adds a diamond and shorter trail; Fun adds a pulsing sparkle and trailing dots. No words are required by default. Feedback -> Show mode names restores labels. Symbols must retain angular continuity through recording/transcribing colour changes.

31) Selected-text Tidy (Windows)

- Map the Swiftpoint left deep-click held plus right fingertip gesture to `F15`, then select text in a disposable editor, trigger the gesture and release within three seconds. Expected: the existing selection is replaced after a magenta processing indicator; the host handler sends no Select All, Enter, or auto-submit.
- While the request is pending, change focus, type, alter the selection, or change the clipboard. Expected: the editor is not changed and Transcript history contains the raw and rewritten recovery entry. The clipboard is not overwritten after an independent clipboard change.
- Trigger F15 repeatedly or hold it. Expected: exactly one job starts and the F15 release is consumed. Verify ordinary right-fingertip Paste and the F13 + Ctrl+V Raw/Tidy/Fun cycle still behave normally.
- `tests/test_selected_text_tidy.py` covers pre-copy focus changes, missing input tracking, archival failures, clipboard races, thread-start recovery, API completion validation, Android prompt equivalence, GPT-5.6 Terra model routing and debounce. Live Copy must settle before user-input snapshotting; see the dated implementation note for measured results.
# Cursor Motion Verification

2026-09-28 Opus motion refinement: `tests/test_cursor_indicator.py` verifies the
5% entry overshoot, settling by 280 ms, exact 26.6-degree extra sweep, bounded
single-onset jostle, sustained-input settling, silent/non-finite/threshold input,
refresh-rate consistency at 60/120/144/240 Hz and high-audio clipping bounds.
The offline preview also generates `output/cursor-entry-preview.png`.
The original opacity assertion expected a 160 ms fade; the commissioned design
reaches full opacity at 80 ms, so its halfway assertion now samples at 40 ms.
Keep interruption tests unchanged: capture the last displayed envelope at reversal.
Mode-switch angular checks must compare `arc_start + arc_extent` (the traveler),
not the trailing edge: the new audio/entry treatment intentionally varies arc length.

History-body test maintenance (2026-09-23): exports increased the shared request
limit to 32768 bytes. The old 4097-byte oversized fixture now correctly waits for
the body and returns 408, not 400. Use 32769 for the oversized-body regression.

### Windows Process Recovery (2026-09-23)

- `tests/test_process_supervisor.py` covers zero/nonzero/native-like crash codes,
  explicit exit, bounded retry delays, recovery after stable uptime, launch errors,
  unavailable supervisor logs, foreground exit mapping and restart wait timeouts.
- A real synthetic subprocess exits abruptly, is restarted, then deliberately exits;
  this verifies recovery without recording audio or making API requests.
- A Windows process-wait test proves the child remains alive while waiting. Never
  use `os.kill(pid, 0)` as a Windows liveness probe: it calls process termination,
  unlike POSIX. Use a SYNCHRONIZE handle and WaitForSingleObject instead.
- Application tests distinguish unexpected tray-loop return from intentional
  shutdown and duplicate-instance exit. Linux service delegation stays unchanged.
- Launch through `start_push_to_talk.py`, not the application module, to verify
  recovery. Do not deliberately kill a live dictation; use the synthetic fixture.

- `python tests/manual_cursor_preview.py` generates an offline animation and contact
  sheet in ignored `output/`, and benchmarks 600 rendered frames without microphone,
  keyboard hooks, network calls or touching the live app. The GIF is a 30 fps preview;
  native rendering still targets 120 Hz.
- Tests cover audio attack/release smoothing, stale audio, non-finite levels,
  mode continuity, unclipped tiny entry frames, rewrite/error geometry, result expiry,
  output success/failure/silence and recording priority over earlier output results.
- Initial verification: 264 tests passed in 8.41 seconds; renderer mean 0.92 ms,
  p95 1.15 ms (8.33 ms frame budget). This measures rendering, not display presentation.
- PowerShell search lesson: pass the directory and `rg -g 'test*.py'` rather than
  a wildcard filename argument. Use single-quoted regexes containing double quotes.
- Ruff requires dictionary literals and rejects unused noqa markers; check before commit.
- Interrupted-animation regressions (2026-09-21): quick release previously jumped
  from radius 11.21 to 25.06; resuming during collapse jumped from 16.72 to 25.44.
  The animator now retains the displayed scale/opacity at each reversal. Test both
  sides of a transition at the same timestamp to separate jumps from normal motion.
  Reset terminal activity timing on fresh appearance, including repeated success.
- Four added regressions include a 600-frame interrupted-animation stress test.
  Full suite: 274 passed in 8.50 seconds. Offline 600-frame preview: mean 0.98 ms,
  p95 1.30 ms. No live microphone, API calls, user history, or app restart used.


## Reviewed transcript export (synthetic only)

For work confined to the transcript browser/store/export layer, run the focused suite instead of starting capture or the tray app:

```powershell
python -m pytest -vv tests/test_transcript_browser.py tests/test_transcript_store.py tests/test_transcript_exports.py
ruff check transcript_browser.py transcript_store.py transcript_exports.py tests/test_transcript_exports.py tests/synthetic_transcript_browser.py
ruff format --check transcript_browser.py transcript_store.py transcript_exports.py tests/test_transcript_exports.py tests/synthetic_transcript_browser.py
```

The 33 focused cases cover the existing archive/browser behavior plus inclusive recorded dates (including offset boundaries), combined filters, literal search, invalid dates/selections, selected-only JSON/text, raw/final distinction, Unicode/HTML escaping, changed/deleted records, tampered or unreviewed export, acknowledgement, server restart, foreign Host/Origin, malformed ports and client-visible-token forgery. All stores use temporary synthetic databases; no settings, microphone, system audio, hotkeys, provider calls or clipboard are required.

A temporary browser fixture is available without starting the user app:

```powershell
python tests/synthetic_transcript_browser.py
```

It creates three clearly synthetic entries in a temporary directory and binds `127.0.0.1:18477`. It does not open a desktop browser or read the real archive. Stop its own terminal with Ctrl+C; its temporary directory is removed on normal exit. Do not point this fixture or its tests at real transcripts. Its metadata-only preview/download log goes to that terminal.

With Playwright already available, run the headless check from another terminal:

```powershell
# If Playwright is installed outside this project, point to its ESM package entry:
$env:PLAYWRIGHT_MODULE = 'file:///absolute/path/to/playwright/index.mjs'
node tests/transcript_browser_smoke.mjs
```

Omit the variable if `playwright` resolves normally. The script disables JavaScript, blocks external requests, verifies filters and selection reset, downloads both formats, checks exact contents, captures desktop/390px mobile previews under ignored `output/transcript-export-qa/`, and closes its own browser. It neither installs dependencies nor accesses the clipboard. This is an isolated fixture test, not a restart or verification of the running tray app.

When editing these Python files on Windows, specify UTF-8 and normalized newlines explicitly; platform-default `Path.write_text()` can create mixed encodings when adding non-ASCII UI punctuation. Filter selects have explicit accessible labels so browser checks do not accidentally include option text in the control name. Reuse the scoped fixtures and avoid broad device/provider suites for this UI-only change.

Live acceptance on DeskMog: task supervisor PID 23864 was terminated alone;
Task Scheduler replaced it automatically in 52.003 seconds while app PID 65208
remained unchanged. A separate temporary task using the same principal/settings
started a synthetic child, observed abrupt code 7, retried after 2 seconds and
finished with code 0 on its second child; 2.064 seconds total. Test task removed.
Installed duplicate launcher exited 0 in 0.144 seconds with one app/one supervisor.
Actual registered settings exported and verified: Interactive/Limited, logon plus
PT1M indefinite repetition, PT0S execution limit, IgnoreNew, battery-safe settings.
Task startup status returned True. Settings SHA256 matched pre-repair backup.
Rollback -WhatIf verified scope without changing running services or settings.

Task result interpretation on DeskMog: while a long-running instance is Running,
an overlapping start suppressed by IgnoreNew can set LastTaskResult to 2147946720
(0x800710E0). A five-second same-settings synthetic task reproduced that code on a
second start and returned to result 0 on completion. Read State, process PIDs and
supervisor logs together; do not interpret that last-trigger result alone as a
stopped service. Operational scheduler history was disabled and left unchanged.
Scheduled-user prerequisite check found API configuration and sounddevice/pynput/
pystray/openai/PIL/numpy available, using only boolean presence and no mic/API call.

Diagnostic acceptance: 180 tests passed in 5.83 seconds; Ruff check/format passed.
Live diagnostic supervisor-only failure recovered in 34.049 seconds, retaining app
PID 65208. Task event recorded child exit -1; new supervisor logged previous unclosed
run with PID/run ID/last heartbeat and reason unknown. Startup wrapper and safe report
are active; old app privacy/health activation awaits explicit user restart approval.
# Usage Accounting

`python -m pytest tests/test_usage_tracking.py tests/test_live_transcription.py
tests/test_selected_text_tidy.py -vv` tests duration/cached-token estimates,
concurrent SQLite writers, pending/unknown accounting, idempotent finalization,
metadata-only storage, ledger failures and existing transcription/rewrite paths.
Tests isolate the usage database and make no paid API calls.
