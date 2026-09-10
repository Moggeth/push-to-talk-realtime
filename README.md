Push-to-talk Transcription
==========================

Hold a hotkey to record from your microphone, transcribe audio, and paste
the transcript into the active window. A second hotkey logs dictations as
timestamped work entries. The app runs from a compact system tray menu with a
task-focused controls with infrequent preferences grouped into submenus.

This repository is standalone. It does not depend on Personal Package Manager,
although external launchers can still start it by pointing at this checkout.

Features
--------
- Cursor overlay recovery: externally hidden windows are restored on the next active frame. An unexpected overlay shutdown retries after five seconds; startup and failures are recorded in the app log.
- Push-to-talk dictation: record and paste on release.
- Transcript history: dictations are saved to `work_log.txt` with date/time stamps by default, so each person can review what they said later.
- Always-on transcript archive: every non-empty dictation and work-log transcript is stored in local SQLite with both the raw speech-to-text result and final output.
- Local transcript browser: inspect, search, compare, and delete archived entries from a loopback-only HTML interface opened through the tray.
- Configurable dictation hotkey: set a single key or key combo from the tray menu.
- Shift-modified dictation: hold `Shift` while pressing the dictation hotkey to capture system audio instead of the microphone.
- Work log capture: record and append a timestamped entry to `work_log.txt`.
- Unified transcription selector: GPT Live Transcribe is the default and GPT Transcribe is the recorded backup.
- Optional GPT post-processing: revise finished transcripts before paste or work-log output, with selectable models and instruction profiles.
- Realtime live dictation: GPT Live Transcribe streams server-side transcript deltas while you are still holding the hotkey and commits the turn on release.
- Transcription preferences are saved and restored on next launch.
- GPT post-processing is off by default and falls back to the original transcript if the additional API call fails or returns no text.
- Tray controls expose common toggles and active selections directly, alongside transcript browsing, restart, and quit actions.
- Busy tray feedback: non-AppIndicator backends update the tray icon live; microphone recording is red, system-audio recording is blue, recorded transcription is orange with an animated waveform, GPT Live Transcribe uses a static orange finalizing state after release, and GPT post-processing is magenta with an animated sparkle. State changes switch immediately into a destination-dominant color and settle over two short frames. Ubuntu AppIndicator stays on a static icon for stability and writes status changes to the app log.
- Windows cursor feedback: a small click-through ring expands from the pointer and gently pulses at a 120 Hz target. Its alpha-blended artwork is rendered at 4x resolution and downsampled for smooth edges. It follows the tray colors while recording (red microphone, blue system audio), then preserves the traveler's position while easing into a faster orange transcription orbit. When processing completes, the moving ring contracts back into the pointer. Set `CURSOR_RECORDING_INDICATOR=0` to disable it.
- Single-instance guard: accidental duplicate launches exit before installing a second global hotkey listener.
- Startup hardening: the ready message is logged only after the global hotkey listener starts, and a watchdog restarts the listener if it stops unexpectedly.
- First-press reliability: if the dictation key is released while the audio session is still starting, the release is remembered and applied as soon as recording becomes active.
- Instant-start microphone capture: the selected microphone stays warm with a bounded 400 ms local pre-roll buffer, so speech begun immediately with the trigger is retained. Each capture logs hotkey-to-stream-ready and hotkey-to-first-audio timings.
- Tray menu controls:
  - Select one shared input device for both dictation and work-log capture.
  - Toggle beeps, status tooltip, tap-to-toggle mode, and mute monitor.
  - Punctuation options and paste suffix selection.

Hotkeys
-------
- Dictation: `F13` by default, intended for a mouse button remapped to F13.
- System audio dictation: hold `Shift + F13` to capture the currently playing system output on Windows; if output loopback is unavailable, it falls back to a Stereo Mix-style input when available.
- System audio source latches at recording start: after starting with `Shift + F13`, releasing `Shift` keeps recording system audio until `F13` is released.
- Work log: disabled by default, leaving F14 available to Radial Launcher. Set `WORKLOG_HOTKEY` or `worklog_hotkey` to opt in with another key; an empty value disables it.
- When configured, hold the work-log key (more than ~0.25s) to record, or double-tap it to open `work_log.txt`.
- `Set Hotkey...` captures the exact drafted key or key combo and asks you to accept it before saving.
- The dictation keyboard hotkey only fires when the drafted keys are the only keys being held, except for the special `Shift + hotkey` system-audio path.
- Recommended Windows setup: map your mouse side button to `F13` in your mouse software. It is usually much less collision-prone than common keyboard keys.
- Override hotkeys with `DICTATION_HOTKEY` / `WORKLOG_HOTKEY`, or set `dictation_hotkey`, `dictation_hotkey_kind`, `dictation_hotkey_tokens`, and `worklog_hotkey` in `settings.json`.

Tray Menu
---------
- GPT cleanup: one-click checkbox for the additional text-revision call; model and instructions live together under Cleanup settings.
- Transcription: one radio list for all recorded models and GPT Live Transcribe. Choosing a recorded model also switches back to recorded mode.
- Audio input: shared microphone/input device selection and device refresh.
- Text & behavior: tap-to-toggle, paste suffix, punctuation, beeps, tooltip, and mute monitor.
- Shortcuts & startup: dictation binding, work-log binding, and run-at-login.
- History: opens the local transcript browser or legacy text log and controls legacy text logging.
- Restart: restarts the systemd user service when managed by systemd, otherwise waits for the current tray instance to exit before relaunching the tracked entry point.
- Quit: exits the tray app, or stops the systemd user service when managed by systemd.

Controls:
- Dictation hotkey: opens a small capture window, shows the drafted key combo, then saves it only after you click `Accept`.
- Transcription:
  - GPT Live Transcribe: default; streams one transcription session while recording and explicitly commits it when the trigger is released.
  - GPT Transcribe: recorded backup used when live dependencies are unavailable.
  - Saved GPT-4o Transcribe, GPT-4o Mini Transcribe, and Whisper selections migrate to GPT Transcribe.
- GPT cleanup is a root checkbox that turns the additional text-revision call on or off immediately. It is off by default.
- GPT model and instructions:
  - Model: choose GPT-5.6 Luna (fast), Terra (balanced), or Sol (highest quality).
  - Instructions: choose Clean up speech, Make concise, Light touch, or Custom instructions.
  - Edit custom instructions...: appears in the instructions submenu and opens the local `post_process_instructions.txt` file. The app creates it on first use and rereads it for every custom-profile request, so edits do not require a restart.
  - Applies to both pasted dictation and work-log entries. If cleanup is enabled with GPT Live Transcribe, live typing is withheld until the revised final text is ready.
- Text output:
  - Suffix: None / Space / Newline (affects pasted dictation only).
  - Ensure terminal punctuation (adds "." if missing; enabled by default).
  - Capitalize first letter.
  - Normalize whitespace.
- Shortcuts & startup -> Run at login: installs or removes the platform startup hook for the current checkout.
- History -> Save legacy text log: on by default; when enabled, each final dictation is appended to `work_log.txt`.
  This controls only the legacy text file; the raw/final SQLite archive remains always on.
- Refresh devices appears at the bottom of the Audio input submenu.

Setup
-----
Install dependencies from `requirements.txt`:

```powershell
python -m pip install -r requirements.txt
```

Ubuntu install commands (including system packages needed by audio/tray/clipboard libs):

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-tk python3-gi portaudio19-dev libportaudio2 libasound2-dev gir1.2-ayatanaappindicator3-0.1 python3-xlib xclip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create a `.env` file in the same folder:

```ini
OPENAI_API_KEY=your_key_here
```

Run:

```powershell
python .\start_push_to_talk.py
```

By default, `start_push_to_talk.py` starts the already-installed user service
on Linux when available; otherwise it detaches a background tray process and
returns immediately so you do not have to keep a terminal open.

For debugging, run the same script with `--foreground`.

Run on startup
--------------
The easiest path is the tray menu: open `Shortcuts & startup` -> `Run at login`.

That toggle writes the right startup hook for the current platform:
- Linux: a user systemd service in `~/.config/systemd/user/`
- Windows: a startup script in the user Startup folder
- macOS: a LaunchAgent plist in `~/Library/LaunchAgents/`

If you prefer the manual Linux route, the included service file is still here as
an example:

```bash
mkdir -p ~/.config/systemd/user
cp push-to-talk-realtime.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now push-to-talk-realtime.service
```

The Linux service reads `~/.config/push-to-talk-realtime.env` for variables such
as `OPENAI_API_KEY`.

Logging
-------
The app writes timestamped runtime logs to the platform runtime-data directory.
On Windows this is `%LOCALAPPDATA%\PushToTalkRealtime\push_to_talk_realtime.log`.
The log rotates at 5 MiB and retains three backups by default. Detached-launcher
output uses the separate `push_to_talk_starter.log`, so it cannot contend with
the application log. Override either location with `PUSH_TO_TALK_LOG_PATH` or
`PUSH_TO_TALK_LAUNCHER_LOG_PATH`.

On Ubuntu/AppIndicator, the tray backend now favors stability over live icon
animation. Status changes still show up in the log file, which makes it easier
to diagnose hotkey/listener/tray issues when the desktop shell is flaky.

Troubleshooting
---------------
- If the tray icon and hotkey are both absent, run `python .\start_push_to_talk.py`.
  A startup-manager launch may retain `..` in its command line, so diagnostics
  should search all Python command lines for `push_to_talk_realtime.py` rather
  than comparing only against the resolved checkout path.
- If a long-running microphone session produces `first-audio=0 ms` and
  `pre-roll=0 ms`, the warm PortAudio stream has stopped delivering callbacks.
  The app now checks that stream once per second and automatically reopens it;
  the next press also uses the normal recorder if recovery has not completed.
- The current process, selected engine, listener startup, stream recovery, and
  capture timing can be checked in `push_to_talk_realtime.log`.

Development
-----------
Basic checks (see `TESTING.md` for the full, plain-language plan):

```powershell
ruff check .
ruff format --check .
pytest -vv
```

Coverage gate used by CI:

```powershell
pytest -vv --cov --cov-report=term-missing
```

Architecture
------------
- `push_to_talk_realtime.py` owns application state, device selection, hotkeys,
  the warm microphone stream, and the capture-session lifecycle. A session now
  moves through explicit activation, recording, transcription, and ordered
  output phases, with shared cleanup for abort and normal completion paths.
- `transcription_engines.py` owns recorded WAV requests and the GPT Live
  Transcribe websocket protocol. It has no tray, hotkey, or application-state
  dependencies, so API contract changes can be tested independently.
- `tray_visuals.py` is the pure icon renderer and color-transition helper.
- `text_processing.py`, `transcript_store.py`, and `transcript_browser.py` own
  final text rules and local transcript persistence/browsing respectively.
- `platform_input.py` and `startup_integration.py` isolate platform-specific
  paste/focus and startup behavior.

Keep latency-sensitive warm microphone ownership in the main application unless
an extraction preserves its single stream, bounded pre-roll, and first-audio
metrics as one tested unit.

GitHub Actions now runs:
- A Linux quality job on Python 3.12 with Ruff plus a 70% coverage gate.
- Compatibility test jobs on Ubuntu, Windows, and macOS using Python 3.11.

The test suite is headless-safe in CI by forcing dummy `pynput` and `pystray`
backends, so the regression checks do not depend on a live tray session or
audio hardware.

Configuration
-------------
Environment variables:

- `OPENAI_API_KEY` (required): OpenAI API key with speech-to-text access.
- `OPENAI_TRANSCRIBE_MODEL` (optional): recorded-transcription model, default `gpt-transcribe`.
- `OPENAI_TRANSCRIBE_PROMPT` (optional): punctuation/style hint for recorded transcription.
- `RECORDED_TRANSCRIPTION_TIMEOUT_S` (optional): maximum recorded transcription request time, default `120` seconds.
- `POST_PROCESS_TIMEOUT_S` (optional): maximum GPT cleanup request time, default `45` seconds.
- `OPENAI_MAX_RETRIES` (optional): SDK retries for recorded transcription and cleanup, default `1`.
- `OUTPUT_TURN_WAIT_TIMEOUT_S` (optional): maximum time a completed session waits behind an earlier result before failing open, default `90` seconds.
- `OPENAI_WHISPER_MODEL` / `OPENAI_WHISPER_PROMPT` are still accepted as legacy aliases.
- `TRANSCRIPTION_ENGINE` (optional): `live` (default) or `recorded`. Legacy realtime values migrate to recorded mode.
- `OPENAI_LIVE_TRANSCRIBE_LANGUAGES` (optional): comma-separated language hints such as `en,fr`.
- `OPENAI_LIVE_TRANSCRIBE_PROMPT` (optional): contextual vocabulary or names for live transcription.
- `OPENAI_LIVE_TRANSCRIBE_DELAY` (optional): live model latency preference, default `low`.
- `OPENAI_REALTIME_WS_URL` (optional): websocket URL for realtime transcription, default `wss://api.openai.com/v1/realtime?intent=transcription`.
- `REALTIME_AUDIO_QUEUE_MAX_CHUNKS` (optional): bounded number of 40 ms chunks awaiting realtime upload, default `512`; overflow is counted and logged after capture.
- `CURSOR_RECORDING_INDICATOR` (optional): `1` (default) shows the Windows recording ring around the pointer; set `0` to disable it.
- `OPENAI_POST_PROCESS_MODEL` (optional): initial GPT post-processing model, default `gpt-5.6-luna`; tray selections are persisted in `settings.json`.
- `OPENAI_POST_PROCESS_INSTRUCTIONS_PATH` (optional): custom instruction file path, default `post_process_instructions.txt` in the platform runtime-data directory.
- `REALTIME_LIVE_TYPING` (optional): `1` (default) enables live delta typing for dictation, `0` disables it.
- `PUSH_TO_TALK_SETTINGS_PATH` (optional): override the platform user-data path used for persisted tray settings.
- `PUSH_TO_TALK_TRANSCRIPT_DB_PATH` (optional): override the always-on SQLite archive path (`transcripts.db` in the platform runtime-data directory by default).
- `PUSH_TO_TALK_LOG_PATH` (optional): override the application log path.
- `PUSH_TO_TALK_LAUNCHER_LOG_PATH` (optional): override detached-launcher output, which is separate from the application log.
- `PUSH_TO_TALK_LOG_MAX_BYTES` (optional): rotate the application log at this size, default 5 MiB.
- `PUSH_TO_TALK_LOG_BACKUP_COUNT` (optional): number of rotated application logs to retain, default `3`.
- `DICTATION_HOTKEY` (optional): single-key trigger for dictation, default `F13`.
- `WORKLOG_HOTKEY` (optional): single-key trigger for work log capture, disabled by default (empty string).
- `PUSH_TO_TALK_SERVICE_NAME` (optional): service name used by the tray `Restart` / `Quit` actions, default `push-to-talk-realtime.service`.
- `DICTATION_DEVICE` (optional): device index or name fragment for the shared microphone input.
- `WORKLOG_DEVICE` (optional): legacy alias for the shared microphone input when `DICTATION_DEVICE` is unset.
- `SYSTEM_AUDIO_DEVICE` (optional): output device name fragment used by `Shift + DICTATION_HOTKEY` on Windows loopback, or an input device index/name fragment for Stereo Mix fallback; if unset, the app uses the default Windows output loopback first.
- `WORK_LOG_PATH` (optional): custom path for `work_log.txt`; the default is in the platform runtime-data directory.
- `PUSH_TO_TALK_HELPER_PYTHON` (optional): override the interpreter used for the hotkey capture helper on Linux.
- `STEREO_MIX_SEARCH` (optional): name fragment for Stereo Mix device search.
- `MUTE_RMS_THRESHOLD` (optional): RMS threshold for mute monitor, default `0.01`.
- `MUTE_WARNING_AFTER_S` (optional): seconds before mute warning, default `1.5`.
- `MICROPHONE_PRE_ROLL_ENABLED` (optional): `1` (default) keeps the selected microphone stream warm; set to `0` to use open-on-press capture.
- `MICROPHONE_PRE_ROLL_MS` (optional): local audio retained immediately before the trigger, default `400` ms.

Device selection
----------------
Use the tray menu to switch input devices on the fly. For scripted setup, set
`DICTATION_DEVICE` to a device index or a partial name match
(case-insensitive). `WORKLOG_DEVICE` is kept as a compatibility alias if
`DICTATION_DEVICE` is unset. On Windows, `Shift + DICTATION_HOTKEY` captures the
default output device through WASAPI loopback. Set `SYSTEM_AUDIO_DEVICE` to a
headphones/speakers name fragment to target a specific output, or to a Stereo
Mix-style input name/index if loopback is unavailable. The input-device submenu
also includes `Refresh devices`. If a selected device
disappears (for example, USB unplug/replug), the app retries and falls back to
another available input instead of crashing. Reselect the desired device after
it reconnects.

Notes and tips
--------------
- Settings and mutable runtime data are stored outside the checkout so pulls, OneDrive synchronization, and application updates do not interfere with them. On Windows the default directory is `%LOCALAPPDATA%\PushToTalkRealtime`; macOS uses `~/Library/Application Support/PushToTalkRealtime`; Linux settings use `${XDG_CONFIG_HOME:-~/.config}/push-to-talk-realtime` and runtime data uses `${XDG_STATE_HOME:-~/.local/state}/push-to-talk-realtime`.
- The first exclusive startup migrates checkout-local `settings.json`, `push_to_talk_realtime.log`, `transcripts.db` (including SQLite sidecars), `work_log.txt`, and `post_process_instructions.txt` when their destination paths do not already exist. Explicit path overrides are never migrated.
- Startup settings can emit a few new log lines before exclusive migration begins. If a legacy checkout log still exists, migration atomically places its older content before those startup lines instead of skipping or duplicating it.
- Paste uses the standard shortcut for your platform: `Ctrl+V` on Windows/Linux
  and `Cmd+V` on macOS.
- On Windows, record-then-paste remembers the focused control when dictation
  starts. For standard edit controls it inserts the final transcript into that
  remembered control even if another app is foreground later. If the remembered
  target cannot accept direct insertion and the foreground window has changed,
  the transcript stays on the clipboard instead of sending `Ctrl+V` to the wrong
  app.
- If you bind a mouse button through Logitech/G Hub, Razer Synapse, X-Mouse, or similar software, prefer `F13`-`F24`; those keys are usually unused by other apps.
- System audio capture on Windows uses output loopback when possible, so Bluetooth headphones and other non-Realtek outputs can be captured directly. If loopback is unavailable, use a loopback-capable input such as `Stereo Mix`; if yours uses a different name, set `SYSTEM_AUDIO_DEVICE`.
- On Linux, paste injection does not require the root-only `keyboard` package.
  If simulated paste fails, the transcript still remains on the clipboard.
- On Ubuntu GNOME/Wayland, tray clicks and menus rely on the AppIndicator path.
  Keep `python3-gi` and `gir1.2-ayatanaappindicator3-0.1` installed; otherwise
  the fallback Xorg tray backend can show an icon but not a working menu.
- The `Set Hotkey...` dialog uses `tkinter` where available and falls back to GTK on Linux when launched through the system `python3` interpreter.
- If a target app blocks simulated paste, trigger paste manually from the
  clipboard or try running the console with elevated permissions on Windows.
- `work_log.txt` is a plain text history file in the runtime-data directory. Dictations are tagged as `[Dictation]` and manual work-log captures are tagged as `[Work log]`.
- `transcripts.db` is the authoritative local archive for new captures. The raw transcript is committed before GPT post-processing begins, then the same row receives the final text and processing status. Existing `work_log.txt` rows are not retroactively imported.
- The transcript browser binds only to `127.0.0.1`, loads no external assets, escapes transcript content, and requires a per-server token for deletion requests. It stops when the tray app exits.
- Deleting an entry in the browser removes it from `transcripts.db`; it does not rewrite older lines already appended to `work_log.txt`.
- Punctuation options affect both dictation and work log text content.
- GPT post-processing runs before local punctuation options. It uses the Responses API with response storage disabled and sends only the transcript plus the selected instructions.
- A post-processing error is logged and the untouched transcript continues through the normal punctuation, history, work-log, and paste paths.
- Paste suffix options affect dictation paste only.
- Tray icon color: green when idle, red for microphone recording, blue for system-audio recording, orange while transcribing, and magenta while GPT post-processing. Non-AppIndicator backends use a crisp comet ring plus an animated waveform for transcription and sparkle for GPT work; color changes settle over two target-dominant frames without delaying the state change.
- The warm microphone pre-roll remains local and is discarded continuously while idle. Only the bounded audio immediately preceding an actual trigger is included in that recording. If the warm stream cannot open, the app logs the failure and retains the previous open-on-press fallback.
- The warm microphone stream is considered stale after two seconds without an audio callback and is reopened automatically while idle. Recovery runs on a dedicated watchdog with bounded retry backoff, so a slow device open cannot stall tray animation or hotkey-listener checks.
- While an earlier transcript is still processing, you can start a new recording; completed dictations are pasted in the order the recordings started.
- Failed or aborted sessions release their output slot immediately. If an earlier API request remains stalled beyond the configured output wait, newer completed dictation proceeds and any late older result is discarded instead of pasting out of order.
- Realtime live typing applies only to dictation mode and may need app focus to stay in the target field.
- GPT Live Transcribe has no fallback model or local chunking path. A failed live session is logged instead of silently changing transcription engines. Realtime shutdown allows the configured ready and final-response deadlines, then explicitly cancels the worker; queue overflow is reported rather than silently ignored.
- If realtime dependencies are missing, GPT Live Transcribe selection logs an install hint and stays on recorded mode.

### Releasing a conflicting shortcut

Hotkeys are loaded at startup. Changing the default alone does not replace a saved `worklog_hotkey`: set it to an empty string in the active settings file and restart the tray app. Check `WORKLOG_HOTKEY` overrides too. Normal F13 dictation remains available.
