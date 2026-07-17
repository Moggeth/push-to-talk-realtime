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
pytest -vv --cov=push_to_talk_realtime --cov=platform_input --cov=text_processing --cov-report=term-missing
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
  - Persisted dictation hotkey kind/tokens, conservative Whisper recorded-model default, default-on transcript history, startup toggle helpers, hotkey capture helper parsing, tray restart/quit actions, menu builders, tray startup/shutdown, and `main()` bootstrap wiring.
  - GPT post-processing model/profile persistence, tray controls, custom instruction loading, Responses API payloads, blank-input handling, raw-transcript fallback on API failure, reference-counted processing state, and distinct tray feedback.
  - Single-instance startup guard, hotkey-listener watchdog restart, and delayed restart helper behavior.

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

3) Set Hotkey dialog
- Open the tray menu, click `Settings` -> `Set dictation hotkey...`, press a key or combo, confirm the drafted label looks right, then click `Accept`.
- Expected: the tray menu immediately shows the new dictation hotkey.
- Expected: the hotkey only starts dictation when the drafted keys are the only keys being held, except for `Shift + hotkey` system-audio capture.

4) Realtime live typing (GPT-4o Realtime)
- In tray menu, set "Settings" -> "Transcription mode" -> "GPT-4o Realtime".
- Hold the mouse button remapped to F13 and speak 1-2 sentences.
- Expected: text starts appearing before key release; releasing F13 finalizes punctuation/suffix.
- Expected: realtime behavior is server-side; no local chunking fallback should appear in logs.
- Expected: no `invalid_model` websocket errors when using the default realtime websocket URL.

5) Shared input device menu
- Open the tray menu, choose `Settings` -> `Input device`, then select a different microphone/input.
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
  "Normalize whitespace" from `Settings` -> `Punctuation`.
- Expected: dictation + work log reflect the settings on the next run.

10) Transcription mode and recorded model toggles
- In tray menu, switch "Settings" -> "Transcription mode" between Record then paste and GPT-4o Realtime.
- Expected: selected radio item updates immediately and next dictation uses that engine.
- Expected: when GPT-4o Realtime is active, there is no automatic Whisper fallback.
- In tray menu, switch "Settings" -> "Recorded model" between GPT-4o Transcribe, GPT-4o Mini Transcribe, and Whisper.
- Expected: next record-then-paste dictation uses the selected recorded model.

11) Engine preference persistence
- Set mode to GPT-4o Realtime and recorded model to Whisper, exit app, relaunch app.
- Expected: tray still shows GPT-4o Realtime selected, and the recorded model selection is preserved.

12) Dictation hotkey persistence
- Use `Set Hotkey...` to save a new dictation key or combo, exit the app, relaunch it.
- Expected: the tray still shows the saved dictation hotkey and it works without reconfiguration.

13) Transcript history (default on)
- Dictate once with the normal dictation hotkey, then open the history file from the tray.
- Expected: a new line is appended with a full date/time stamp and a `[Dictation]` tag.
- In `Settings`, toggle `Save transcript history` off, dictate again, and confirm no new dictation history line is added.

14) Work log hotkey (F14 by default)
- Hold F14 for at least ~0.25s, speak a short sentence, release.
- Expected: a new timestamped line appears in `work_log.txt` with a `[Work log]` tag.

15) Mute monitor (optional)
- Enable "Mute monitor", then start recording while silent.
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

- Open `Settings` -> `GPT post-processing`, select `Clean up speech`, choose a model, and enable it.
- Dictate a sentence with filler words or a false start, then release the hotkey.
- Expected: the final pasted text is revised according to the selected instructions; the recording behavior is unchanged.
- Expected: after orange transcription begins, the tray icon changes to an animated magenta while GPT revises the text, then returns to green when output finishes. The tooltip says `Post-processing` when tooltips are enabled.
- Switch to `Custom instructions`, open the custom instructions file, add a small rule such as preserving a product name exactly, save it, and dictate again.
- Expected: the next result uses the edited instruction without restarting the tray app.
- Temporarily disconnect the network and dictate again.
- Expected: the post-processing failure is logged and the original transcript is still pasted instead of being lost.
- With GPT-4o Realtime selected, expected: enabling post-processing suppresses live delta typing and pastes the revised final text after release.

20) Run on startup toggle
- Open `Settings` -> `Run at login`.
- Expected on Linux: a user systemd service is written/enabled for the current checkout and starts immediately.
- Expected on Windows/macOS: the platform startup artifact is created for the current checkout.
- Toggle it off again.
- Expected: the startup artifact is disabled or removed cleanly.

21) Tray restart and quit actions
- If running under the included user systemd service on Linux, click `Restart service` and `Quit` from the tray.
- Expected: `Restart service` restarts the service cleanly and the tray returns.
- Expected: the dictation hotkey still works after the restart without needing a second manual relaunch.
- Expected: `Quit` stops the service.
- If running the script directly instead of under systemd, `Restart service` should relaunch `push_to_talk_realtime.py` and `Quit` should only close the current process.
- Start the app twice manually.
- Expected: the second launch exits without creating another tray icon or second global hotkey listener.

22) Starter script
- Run `python start_push_to_talk.py`.
- Expected on Linux with the user service installed: the command returns quickly and the service becomes active.
- Expected otherwise: the command returns quickly and a detached tray process keeps running after the terminal closes.
- For debugging, run `python start_push_to_talk.py --foreground`.

23) Mouse-side-button remap
- Map a spare mouse button to `F13`, relaunch the app, then hold that button and speak.
- Expected: dictation starts/stops cleanly and other apps do not react to the remapped mouse button.

24) Ubuntu tray interactivity
- On Ubuntu GNOME/Wayland, launch the app from `python start_push_to_talk.py`.
- Left-click or right-click the tray icon.
- Expected: the tray menu opens and actions such as `Settings`, `Restart service`, and `Quit` are clickable.
- Expected: there are no preset entries such as `Default (no frills)` or `Bells and whistles`; individual toggles remain under `Settings` -> `Advanced`.

25) Runtime logging
- Use dictation once, then inspect `push_to_talk_realtime.log`.
- Expected: each line has a timestamp and thread name.
- Expected: tray state changes, startup details, and any unhandled thread exception are written there.
