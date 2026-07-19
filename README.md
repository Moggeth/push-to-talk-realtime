Push-to-talk Transcription
==========================

Hold a hotkey to record from your microphone, transcribe audio, and paste
the transcript into the active window. A second hotkey logs dictations as
timestamped work entries. The app runs from a compact system tray menu with a
flat set of common controls and one submenu for less common preferences.

This repository is standalone. It does not depend on Personal Package Manager,
although external launchers can still start it by pointing at this checkout.

Features
--------
- Push-to-talk dictation: record and paste on release.
- Transcript history: dictations are saved to `work_log.txt` with date/time stamps by default, so each person can review what they said later.
- Always-on transcript archive: every non-empty dictation and work-log transcript is stored in local SQLite with both the raw speech-to-text result and final output.
- Local transcript browser: inspect, search, compare, and delete archived entries from a loopback-only HTML interface opened through the tray.
- Configurable dictation hotkey: set a single key or key combo from the tray menu.
- Shift-modified dictation: hold `Shift` while pressing the dictation hotkey to capture system audio instead of the microphone.
- Work log capture: record and append a timestamped entry to `work_log.txt`.
- Transcription mode toggle: choose record-then-paste or GPT-4o Realtime from the tray menu.
- Recorded model selector: choose GPT-4o Transcribe, GPT-4o Mini Transcribe, or Whisper for the record-then-paste path.
- Optional GPT post-processing: revise finished transcripts before paste or work-log output, with selectable models and instruction profiles.
- Realtime live dictation: GPT-4o Realtime streams server-side transcript deltas while you are still holding the hotkey.
- Transcription preferences are saved and restored on next launch.
- GPT post-processing is off by default and falls back to the original transcript if the additional API call fails or returns no text.
- Tray controls expose common toggles and active selections directly, alongside transcript browsing, restart, and quit actions.
- Busy tray feedback: non-AppIndicator backends update the tray icon live; recording from the microphone is red, system-audio recording is blue, transcription is orange, and GPT post-processing is an animated magenta. Ubuntu AppIndicator stays on a static icon for stability and writes status changes to the app log.
- Single-instance guard: accidental duplicate launches exit before installing a second global hotkey listener.
- Startup hardening: the ready message is logged only after the global hotkey listener starts, and a watchdog restarts the listener if it stops unexpectedly.
- First-press reliability: if the dictation key is released while the audio session is still starting, the release is remembered and applied as soon as recording becomes active.
- Tray menu controls:
  - Select one shared input device for both dictation and work-log capture.
  - Toggle beeps, status tooltip, tap-to-toggle mode, and mute monitor.
  - Punctuation options and paste suffix selection.

Hotkeys
-------
- Dictation: `F13` by default, intended for a mouse button remapped to F13.
- System audio dictation: hold `Shift + F13` to capture the currently playing system output on Windows; if output loopback is unavailable, it falls back to a Stereo Mix-style input when available.
- System audio source latches at recording start: after starting with `Shift + F13`, releasing `Shift` keeps recording system audio until `F13` is released.
- Work log: `F14` by default
- Work log: hold `F14` (more than ~0.25s) to record, or double-tap `F14` to open `work_log.txt`.
- `Set Hotkey...` captures the exact drafted key or key combo and asks you to accept it before saving.
- The dictation keyboard hotkey only fires when the drafted keys are the only keys being held, except for the special `Shift + hotkey` system-audio path.
- Recommended Windows setup: map your mouse side button to `F13` in your mouse software. It is usually much less collision-prone than common keyboard keys.
- Override hotkeys with `DICTATION_HOTKEY` / `WORKLOG_HOTKEY`, or set `dictation_hotkey`, `dictation_hotkey_kind`, `dictation_hotkey_tokens`, and `worklog_hotkey` in `settings.json`.

Tray Menu
---------
- GPT post-processing: one-click checkbox for the additional text-revision call.
- Tap to start / stop: one-click alternative to hold-to-record.
- Input device, transcription mode, recorded model, GPT model, and GPT instructions are direct submenus. Each label shows the active selection.
- Text output: paste suffix and punctuation behavior.
- Dictation hotkey: shows the current binding and opens the capture dialog directly.
- More settings: work-log hotkey, startup, legacy transcript history, beeps, status tooltip, and mute monitor.
- Open transcript browser: starts a private `127.0.0.1` web interface and opens it in the default browser. Raw and final text appear side by side, with search and per-entry deletion.
- Open transcript history: opens `work_log.txt`.
- Restart service: restarts the systemd user service when managed by systemd, otherwise waits for the current tray instance to exit before relaunching the tracked entry point.
- Quit: exits the tray app, or stops the systemd user service when managed by systemd.

Controls:
- Dictation hotkey: opens a small capture window, shows the drafted key combo, then saves it only after you click `Accept`.
- Recorded model:
  - Whisper: default recorded model for the original conservative boot-time behavior.
  - GPT-4o Transcribe: optional quality/latency trade-off for the record-then-paste path.
  - GPT-4o Mini Transcribe: usually fastest recorded model.
- Transcription mode:
  - Record then paste: transcribes after key release and preserves the original clipboard/paste workflow.
  - GPT-4o Realtime: strict server-side websocket transcription with server VAD; streams deltas while recording, then finalizes on release.
- GPT post-processing is a root checkbox that turns the additional text-revision call on or off immediately. It is off by default.
- GPT model and instructions:
  - Model: choose GPT-5.6 Luna (fast), Terra (balanced), or Sol (highest quality).
  - Instructions: choose Clean up speech, Make concise, Light touch, or Custom instructions.
  - Edit custom instructions...: appears in the instructions submenu and opens the local `post_process_instructions.txt` file. The app creates it on first use and rereads it for every custom-profile request, so edits do not require a restart.
  - Applies to both pasted dictation and work-log entries. If post-processing is enabled with GPT-4o Realtime, live typing is withheld until the revised final text is ready.
- Text output:
  - Suffix: None / Space / Newline (affects pasted dictation only).
  - Ensure terminal punctuation (adds "." if missing; enabled by default).
  - Capitalize first letter.
  - Normalize whitespace.
- More settings -> Run at login: installs or removes the platform startup hook for the current checkout.
- More settings -> Save legacy transcript history: on by default; when enabled, each final dictation is appended to `work_log.txt`.
  This controls only the legacy text file; the raw/final SQLite archive remains always on.
- Refresh devices appears at the bottom of the Input device submenu.

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
The easiest path is the tray menu: open `More settings` -> `Run at login`.

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
The app writes timestamped runtime logs to `push_to_talk_realtime.log` in the
repo folder by default. Override that location with `PUSH_TO_TALK_LOG_PATH` if
you want the log somewhere else.

On Ubuntu/AppIndicator, the tray backend now favors stability over live icon
animation. Status changes still show up in the log file, which makes it easier
to diagnose hotkey/listener/tray issues when the desktop shell is flaky.

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
pytest -vv --cov=push_to_talk_realtime --cov=platform_input --cov=text_processing --cov-report=term-missing
```

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
- `OPENAI_TRANSCRIBE_MODEL` (optional): recorded-transcription model, default `gpt-4o-transcribe`.
- `OPENAI_TRANSCRIBE_PROMPT` (optional): punctuation/style hint for recorded transcription.
- `OPENAI_WHISPER_MODEL` / `OPENAI_WHISPER_PROMPT` are still accepted as legacy aliases.
- `TRANSCRIPTION_ENGINE` (optional): `whisper` (default) or `gpt4o_realtime`.
- `OPENAI_REALTIME_TRANSCRIBE_MODEL` (optional): defaults to `gpt-4o-transcribe`.
- `OPENAI_REALTIME_SESSION_MODEL` (optional): preferred realtime transcription model override (for example `gpt-4o-transcribe`).
- `OPENAI_REALTIME_TRANSCRIBE_LANGUAGE` (optional): ISO-639-1 language hint.
- `OPENAI_REALTIME_TRANSCRIBE_PROMPT` (optional): transcription prompt for realtime mode.
- `OPENAI_REALTIME_WS_URL` (optional): websocket URL for realtime transcription, default `wss://api.openai.com/v1/realtime?intent=transcription`.
- `OPENAI_REALTIME_WS_USE_BETA_HEADER` (optional): `0` (default) uses GA websocket headers; set to `1` only if you intentionally need legacy beta header behavior.
- `OPENAI_POST_PROCESS_MODEL` (optional): initial GPT post-processing model, default `gpt-5.6-luna`; tray selections are persisted in `settings.json`.
- `OPENAI_POST_PROCESS_INSTRUCTIONS_PATH` (optional): custom instruction file path, default `post_process_instructions.txt` beside the app.
- `REALTIME_LIVE_TYPING` (optional): `1` (default) enables live delta typing for dictation, `0` disables it.
- `REALTIME_SERVER_VAD_THRESHOLD` (optional): server VAD threshold, default `0.5`.
- `REALTIME_SERVER_VAD_PREFIX_MS` (optional): server VAD prefix padding in ms, default `300`.
- `REALTIME_SERVER_VAD_SILENCE_MS` (optional): server VAD silence duration in ms, default `700`.
- `PUSH_TO_TALK_SETTINGS_PATH` (optional): override path for persisted tray settings (`settings.json` by default).
- `PUSH_TO_TALK_TRANSCRIPT_DB_PATH` (optional): override the always-on SQLite archive path (`transcripts.db` beside the app by default).
- `DICTATION_HOTKEY` (optional): single-key trigger for dictation, default `F13`.
- `WORKLOG_HOTKEY` (optional): single-key trigger for work log capture, default `F14`.
- `PUSH_TO_TALK_SERVICE_NAME` (optional): service name used by the tray `Restart` / `Quit` actions, default `push-to-talk-realtime.service`.
- `DICTATION_DEVICE` (optional): device index or name fragment for the shared microphone input.
- `WORKLOG_DEVICE` (optional): legacy alias for the shared microphone input when `DICTATION_DEVICE` is unset.
- `SYSTEM_AUDIO_DEVICE` (optional): output device name fragment used by `Shift + DICTATION_HOTKEY` on Windows loopback, or an input device index/name fragment for Stereo Mix fallback; if unset, the app uses the default Windows output loopback first.
- `WORK_LOG_PATH` (optional): custom path for `work_log.txt`.
- `PUSH_TO_TALK_HELPER_PYTHON` (optional): override the interpreter used for the hotkey capture helper on Linux.
- `STEREO_MIX_SEARCH` (optional): name fragment for Stereo Mix device search.
- `MUTE_RMS_THRESHOLD` (optional): RMS threshold for mute monitor, default `0.01`.
- `MUTE_WARNING_AFTER_S` (optional): seconds before mute warning, default `1.5`.

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
- `work_log.txt` is a plain text history file. Dictations are tagged as `[Dictation]` and manual work-log captures are tagged as `[Work log]`.
- `transcripts.db` is the authoritative local archive for new captures. The raw transcript is committed before GPT post-processing begins, then the same row receives the final text and processing status. Existing `work_log.txt` rows are not retroactively imported.
- The transcript browser binds only to `127.0.0.1`, loads no external assets, escapes transcript content, and requires a per-server token for deletion requests. It stops when the tray app exits.
- Deleting an entry in the browser removes it from `transcripts.db`; it does not rewrite older lines already appended to `work_log.txt`.
- Punctuation options affect both dictation and work log text content.
- GPT post-processing runs before local punctuation options. It uses the Responses API with response storage disabled and sends only the transcript plus the selected instructions.
- A post-processing error is logged and the untouched transcript continues through the normal punctuation, history, work-log, and paste paths.
- Paste suffix options affect dictation paste only.
- Tray icon color: green when idle, red for microphone recording, blue for system-audio recording, orange while transcribing, and magenta while GPT post-processing. Non-AppIndicator backends animate a spinner during transcription and post-processing.
- While an earlier transcript is still processing, you can start a new recording; completed dictations are pasted in the order the recordings started.
- Realtime live typing applies only to dictation mode and may need app focus to stay in the target field.
- GPT-4o Realtime is hard-switched to server-side mode (no local chunking and no Whisper fallback inside realtime mode).
- If realtime dependencies are missing, GPT-4o Realtime selection logs an install hint and stays on record-then-paste mode.
- VAD auto-stop and retry queues are not implemented yet.
