# Testing (Plain Language)

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

14) Work log hotkey (F14 by default)
- Hold F14 for at least ~0.25s, speak a short sentence, release.
- Expected: a new timestamped line appears in `work_log.txt` with a `[Work log]` tag.

15) Mute monitor (optional)
- Enable `Text & behavior` -> `Mute monitor`, then start recording while silent.
- Expected: after ~1.5s, a "Muted?" hint appears in the console/tray tooltip.

16) Device hot-swap fallback
- While the app is running, unplug and replug the USB mic, then press F13.
- Expected: no crash; the console logs a retry/fallback message and recording
  continues or exits cleanly if no input device is available.

17) Work log double-tap
- Double-tap F14 while idle.
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

For a new Python module, use `ruff check --fix <file>` before the final `ruff format`; formatting alone does not organize imports. The cursor-indicator check initially stopped on that mechanical distinction before tests ran.

Do not create a Tk root on a worker thread for this overlay. The first live smoke test rendered correctly but emitted `Tcl_AsyncDelete` during interpreter cleanup. The maintained implementation uses a native Win32 window and message loop in its worker thread, which starts and shuts down without Tcl thread ownership.

Do not use Win32 `SetTimer` for the high-refresh cursor animation. An 8 ms timer request measured only about 64 painted frames per second on this machine because USER timers were quantized. The paced native message loop with balanced `timeBeginPeriod(1)` / `timeEndPeriod(1)` calls measured 120.5 painted frames per second at the 120 Hz target.

The cursor overlay uses a 32-bit top-down DIB and `UpdateLayeredWindow` with premultiplied alpha. Render the artwork at 4x resolution and downsample with Lanczos; returning to GDI pens or color-key transparency restores visibly aliased one-bit edges. The supersampled alpha path retained a measured 120.0 frames per second on this machine.

Cursor activity transitions share one stateful phase accumulator. Recording-to-transcription changes must update color and speed targets without constructing a new animation or recomputing the angle from a new speed multiplier; either approach visibly teleports the traveler. Only a fully completed lifecycle resets the starting phase.

Threaded tray tests must isolate every worker started by `tray_setup` and stop it in fixture teardown. The watchdog extraction initially exposed one test that mocked the animation worker but not the new microphone worker; the faster repeatable pattern is to mock the worker start in setup tests and call its stop helper in the shared fixture.

28) Windows cursor recording indicator
- Hold the dictation trigger and move the pointer across multiple windows. Expected: a thin red ring tracks the pointer without stealing focus or blocking clicks.
- Watch the first 160 ms after pressing the trigger. Expected: the ring expands smoothly from the cursor point instead of appearing at full size.
- Hold Shift before the dictation trigger. Expected: the ring is blue for the full latched system-audio capture, including after Shift is released.
- Release the recording trigger. Expected: the traveler keeps its current angular position while the ring eases into orange and accelerates; it must not restart from a fixed position.
- Watch completion. Expected: the still-moving orange ring contracts into the cursor over about 200 ms instead of disappearing abruptly.
- Watch the ring on a high-refresh display while recording. Expected: motion is fluid at the 120 Hz target without affecting pointer movement, capture, or transcription latency.
- Inspect the thin circular track against both light and dark windows. Expected: curved edges are smoothly alpha-blended with no dark halo, square background, or visibly stair-stepped pixels.
- Set `CURSOR_RECORDING_INDICATOR=0` and restart. Expected: recording behavior is unchanged and no pointer ring appears.
