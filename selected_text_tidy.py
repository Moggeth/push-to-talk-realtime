"""Safe, testable selected-text rewrite workflow for the Windows desktop app."""

from __future__ import annotations

import platform
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import ClassVar

F15_VK = 0x7E


class SelectedTextTidyFilter:
    """Consumes one F15 chord, including repeat presses and its key-up."""

    def __init__(self, start: Callable[[], bool]) -> None:
        self._start = start
        self._consuming = False

    def consume(self, vk: int, down: bool) -> bool:
        if vk != F15_VK:
            return False
        if self._consuming:
            if not down:
                self._consuming = False
            return True
        if down:
            # F15 is a dedicated shortcut even while a job or dictation is busy.
            self._consuming = True
            self._start()
            return True
        return False


@dataclass(frozen=True)
class InputSnapshot:
    foreground: object
    last_input: object


@dataclass
class SelectedTextTidyDependencies:
    capture_target: Callable[[], object | None]
    foreground_matches: Callable[[object], bool]
    last_input: Callable[[], object]
    wait_for_release: Callable[[], bool]
    clipboard_sequence: Callable[[], object]
    clipboard_read: Callable[[], str]
    clipboard_write: Callable[[str], None]
    copy_selection: Callable[[], None]
    paste: Callable[[], None]
    transform: Callable[[str], str]
    archive_raw: Callable[[str], object | None]
    archive_final: Callable[[object, str, str, str], None]
    feedback_started: Callable[[], None]
    feedback_finished: Callable[[], None]
    notify: Callable[[str], None]
    busy: Callable[[], bool]
    log: Callable[[str], None] = lambda _: None
    before_paste: Callable[[object], object] = lambda _: None
    after_paste: Callable[[str, str, object], None] = lambda *_: None


class SelectedTextTidyJob:
    """One non-blocking selected-text job; never changes focus or selection on failure."""

    def __init__(self, dependencies: SelectedTextTidyDependencies) -> None:
        self._d = dependencies
        self._lock = threading.Lock()
        self._running = False

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            try:
                if self._d.busy():
                    self._running = False
                    return False
                target = self._d.capture_target()
                if target is None:
                    self._running = False
                    return False
                threading.Thread(target=self._run, args=(target,), daemon=True).start()
            except Exception as exc:
                self._running = False
                self._d.log(f"[Selected Tidy] start_failure={type(exc).__name__}")
                return False
        return True

    def is_running(self) -> bool:
        # A lock-free bool read avoids inversion with the app's session-state lock.
        return self._running

    def _copy(self, previous_sequence: object) -> tuple[str, object] | None:
        self._d.copy_selection()
        deadline = time.monotonic() + 0.75
        while time.monotonic() < deadline:
            sequence = self._d.clipboard_sequence()
            if sequence != previous_sequence:
                text = self._d.clipboard_read()
                # Copy's key-up may still be queued after the clipboard updates.
                time.sleep(0.08)
                if self._d.clipboard_sequence() != sequence:
                    return None
                return text, sequence
            time.sleep(0.02)
        return None

    def _changed(self, snapshot: InputSnapshot) -> bool:
        return (
            snapshot.last_input is None
            or self._d.capture_target() != snapshot.foreground
            or not self._d.foreground_matches(snapshot.foreground)
            or self._d.last_input() != snapshot.last_input
        )

    def _run(self, target: object) -> None:
        entry_id: object | None = None
        raw = ""
        original_clipboard = ""
        owned_sequence: object | None = None
        completed = False
        final = ""
        started = time.perf_counter()
        outcome = "cancelled"

        def recover(reason: str) -> None:
            nonlocal completed, outcome
            self._d.archive_final(entry_id, final, "recovery", reason)
            outcome = "recovery"
            if self._d.clipboard_sequence() == owned_sequence:
                self._d.clipboard_write(final)
                completed = True  # Keep the deliberate clipboard-only result.
                self._d.notify("Tidy ready on clipboard; paste when you are ready.")
            else:
                self._d.notify("Tidy saved in Transcript history; clipboard changed.")

        try:
            if not self._d.wait_for_release():
                self._d.notify("Selected-text Tidy cancelled: shortcut did not settle.")
                return
            if (
                self._d.capture_target() != target
                or not self._d.foreground_matches(target)
                or self._d.last_input() is None
            ):
                self._d.notify("Selected-text Tidy cancelled: focus changed.")
                return
            original_clipboard = self._d.clipboard_read()
            copied = self._copy(self._d.clipboard_sequence())
            if copied is None:
                self._d.notify("Selected-text Tidy: no copied selection.")
                return
            raw, owned_sequence = copied
            if not raw.strip():
                self._d.notify("Selected-text Tidy: no copied selection.")
                return
            if self._d.capture_target() != target:
                self._d.notify("Selected-text Tidy cancelled: focus changed during copy.")
                return
            snapshot = InputSnapshot(target, self._d.last_input())
            if self._changed(snapshot) or self._d.clipboard_sequence() != owned_sequence:
                self._d.log(
                    "[Selected Tidy] capture_cancelled "
                    f"focus_changed={self._d.capture_target() != target} "
                    f"input_changed={self._d.last_input() != snapshot.last_input} "
                    f"clipboard_changed={self._d.clipboard_sequence() != owned_sequence}"
                )
                return
            entry_id = self._d.archive_raw(raw)
            if entry_id is None:
                self._d.notify("Selected-text Tidy saved no replacement: history unavailable.")
                return
            self._d.feedback_started()
            try:
                final = self._d.transform(raw).strip()
            finally:
                self._d.feedback_finished()
            if not final:
                raise ValueError("The rewrite response was blank or incomplete")
            if self._changed(snapshot) or self._d.clipboard_sequence() != owned_sequence:
                recover("target or clipboard changed")
                return

            # Copy again immediately before replacement: this is the conservative selection check
            # available without UI Automation. It must still be the text originally submitted.
            refreshed = self._copy(self._d.clipboard_sequence())
            if refreshed is None or refreshed[0] != raw:
                # A changed copy is not proof of clipboard ownership.
                recover("selection changed")
                return
            _, owned_sequence = refreshed
            snapshot = InputSnapshot(target, self._d.last_input())
            # Persist final before altering the document; a failed archive stops delivery.
            self._d.archive_final(entry_id, final, "recovery", "awaiting delivery")
            if self._changed(snapshot) or self._d.clipboard_sequence() != owned_sequence:
                recover("target changed before clipboard write")
                return
            review_token = self._d.before_paste(target)
            self._d.clipboard_write(final)
            final_sequence = self._d.clipboard_sequence()
            if self._d.clipboard_read() != final:
                recover("clipboard changed before paste")
                return
            owned_sequence = final_sequence
            if self._changed(snapshot) or self._d.clipboard_sequence() != owned_sequence:
                recover("target changed before paste")
                return
            self._d.paste()
            completed = True
            outcome = "completed"
            self._d.archive_final(entry_id, final, "completed", "")
            self._d.notify("Selected-text Tidy complete.")
            self._d.after_paste(raw, final, review_token)
        except Exception as exc:  # intentionally never logs selected text
            outcome = "failed"
            self._d.log(f"[Selected Tidy] failure={type(exc).__name__}")
            if entry_id is not None:
                with suppress(Exception):
                    self._d.archive_final(entry_id, final or raw, "failed", type(exc).__name__)
            self._d.notify(
                "Tidy could not finish; check Transcript history."
                if completed
                else "Selected-text Tidy failed; original selection was preserved."
            )
        finally:
            # Do not overwrite a clipboard changed by the user or another application.
            if not completed and owned_sequence is not None:
                try:
                    if self._d.clipboard_sequence() == owned_sequence:
                        self._d.clipboard_write(original_clipboard)
                except Exception:
                    pass
            with self._lock:
                self._running = False
            self._d.log(
                f"[Selected Tidy] outcome={outcome} elapsed_s={time.perf_counter() - started:.3f}"
            )


def windows_last_input() -> int | None:
    """Return Windows' user-input tick count, or None where it is unavailable."""
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_: ClassVar = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return int(info.dwTime)
    except Exception:
        pass
    return None


def wait_for_windows_f15_release(timeout_s: float = 3.0) -> bool:
    """Wait briefly for the mouse chord and common modifiers to be released."""
    if platform.system() != "Windows":
        return False
    try:
        import ctypes

        keys = (F15_VK, 0x01, 0x02, 0x10, 0x11, 0x12, 0x5B, 0x5C)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not any(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000 for key in keys):
                return True
            time.sleep(0.02)
    except Exception:
        return False
    return False
