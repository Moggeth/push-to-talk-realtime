"""Conservative UI Automation replacement, confined to the review helper process."""

from __future__ import annotations

import platform
import re
import time

from output_transaction import output_transaction


def canonical(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


class WindowsTextReplacement:
    LIMIT = 200000

    def __init__(self):
        self.automation = None
        self.anchor = None
        self.caret = None
        self.current = ""
        if platform.system() == "Windows":
            try:
                import comtypes.client

                self.uia = comtypes.client.GetModule("UIAutomationCore.dll")
                self.automation = comtypes.client.CreateObject(
                    self.uia.CUIAutomation, interface=self.uia.IUIAutomation
                )
            except Exception:
                pass

    def _focused(self):
        from platform_input import capture_paste_target

        target = capture_paste_target()
        element = self.automation.GetFocusedElement()
        if element.CurrentIsPassword:
            raise ValueError("protected_control")
        pattern = element.GetCurrentPattern(10014).QueryInterface(self.uia.IUIAutomationTextPattern)
        selection = pattern.GetSelection()
        if selection.Length != 1:
            raise ValueError("no_single_selection")
        return target, tuple(element.GetRuntimeId()), pattern, selection.GetElement(0)

    def _text(self, text_range):
        text = canonical(text_range.GetText(self.LIMIT))
        if len(text) >= self.LIMIT:
            raise ValueError("document_too_large")
        return text

    def capture(self, expected_target):
        self.anchor = self.caret = None
        if self.automation is None or not expected_target:
            return False
        try:
            from dataclasses import asdict

            target, runtime_id, pattern, selection = self._focused()
            if target is None or asdict(target) != expected_target:
                return False
            prefix = pattern.DocumentRange.Clone()
            prefix.MoveEndpointByRange(1, selection, 0)
            suffix = pattern.DocumentRange.Clone()
            suffix.MoveEndpointByRange(0, selection, 1)
            self.anchor = (target, runtime_id, self._text(prefix), self._text(suffix))
            return True
        except Exception:
            return False

    def caret_context(self, expected_target):
        """Read bounded adjacent text; never select, copy, or read passwords."""
        self.context_diagnostics = {"context_status": "unavailable"}
        if self.automation is None or not expected_target:
            return None
        try:
            from dataclasses import asdict

            target, runtime_id, pattern, selection = self._focused()
            if target is None or asdict(target) != expected_target:
                self.context_diagnostics["context_status"] = "target_changed"
                return None
            element = self.automation.GetFocusedElement()
            control_type = int(element.CurrentControlType)
            self.context_diagnostics["control_type"] = control_type
            if tuple(element.GetRuntimeId()) != runtime_id:
                self.context_diagnostics["context_status"] = "target_changed"
                return None
            document = pattern.DocumentRange.Clone()
            editable = control_type == 50004
            try:
                value = element.GetCurrentPattern(10002).QueryInterface(
                    self.uia.IUIAutomationValuePattern
                )
                editable = not bool(value.CurrentIsReadOnly)
            except Exception:
                if control_type == 50030:
                    editable = bool(element.GetCurrentPropertyValue(30149))
            if not editable:
                self.context_diagnostics["context_status"] = "not_editable"
                return None
            # Chromium may enclose the text range in an internal text node or
            # expose a page-wide pattern. Establish containment, not identity.
            enclosing = document.GetEnclosingElement()
            scope = "direct"
            if tuple(enclosing.GetRuntimeId()) != runtime_id:
                scope = "unavailable"
                try:
                    document = pattern.RangeFromChild(element).Clone()
                    scope = "child_range"
                except Exception:
                    try:
                        node = enclosing
                        for _ in range(16):
                            node = self.automation.RawViewWalker.GetParentElement(node)
                            if not node:
                                break
                            if tuple(node.GetRuntimeId()) == runtime_id:
                                scope = "descendant"
                                break
                    except Exception:
                        pass
                if scope == "unavailable":
                    self.context_diagnostics.update(context_status="unscoped", context_scope=scope)
                    return None
            self.context_diagnostics["context_scope"] = scope
            if (
                selection.CompareEndpoints(0, document, 0) < 0
                or selection.CompareEndpoints(1, document, 1) > 0
            ):
                self.context_diagnostics["context_status"] = "outside_editor"
                return None
            before = selection.Clone()
            before.MoveEndpointByRange(1, selection, 0)
            before.MoveEndpointByUnit(0, 0, -256)
            if before.CompareEndpoints(0, document, 0) < 0:
                before.MoveEndpointByRange(0, document, 0)
            after = selection.Clone()
            after.MoveEndpointByRange(0, selection, 1)
            after.MoveEndpointByUnit(1, 0, 256)
            if after.CompareEndpoints(1, document, 1) > 0:
                after.MoveEndpointByRange(1, document, 1)
            before_text, after_text = canonical(before.GetText(256)), canonical(after.GetText(256))
            selected = canonical(selection.GetText(257))
            word = selected.strip()
            selected_lowercase_word = bool(
                len(selected) <= 256
                and word.islower()
                and re.fullmatch(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*", word)
            )
            selected_trailing_space = bool(
                selected and len(selected) <= 256 and selected[-1].isspace()
            )
            selected_leading_space = bool(
                selected and len(selected) <= 256 and selected[0].isspace()
            )
            current_target, current_id, _, current_selection = self._focused()
            if (
                current_target != target
                or current_id != runtime_id
                or selection.CompareEndpoints(0, current_selection, 0) != 0
                or selection.CompareEndpoints(1, current_selection, 1) != 0
            ):
                self.context_diagnostics["context_status"] = "caret_changed"
                return None
            self.context_diagnostics.update(
                context_status="ok",
                selection_active=selection.CompareEndpoints(0, selection, 1) != 0,
                editor_empty=not document.GetText(1),
                selected_lowercase_word=selected_lowercase_word,
                selected_trailing_space=selected_trailing_space,
                selected_leading_space=selected_leading_space,
            )
            return {
                "before": before_text,
                "after": after_text,
                "selected_lowercase_word": selected_lowercase_word,
                "selected_trailing_space": selected_trailing_space,
                "selected_leading_space": selected_leading_space,
            }
        except Exception:
            self.context_diagnostics["context_status"] = "provider_error"
            return None

    def attach(self, processed):
        self.current = canonical(processed)
        self.caret = None
        return self.verify(check_caret=False)

    def verify(self, *, check_caret=True):
        if self.anchor is None:
            return False
        try:
            target, runtime_id, pattern, selection = self._focused()
            original, expected_id, prefix, suffix = self.anchor
            if target != original or runtime_id != expected_id:
                return False
            if self._text(pattern.DocumentRange) != prefix + self.current + suffix:
                return False
            if self._text(selection):
                return False
            before_caret = pattern.DocumentRange.Clone()
            before_caret.MoveEndpointByRange(1, selection, 0)
            if self._text(before_caret) != prefix + self.current:
                return False
            if (
                check_caret
                and self.caret is not None
                and selection.CompareEndpoints(0, self.caret, 0) != 0
            ):
                return False
            self.caret = selection.Clone()
            return True
        except Exception:
            return False

    def replace(self, replacement):
        with output_transaction():
            return self._replace_locked(replacement)

    def _replace_locked(self, replacement):
        import pyperclip

        from platform_input import send_paste_shortcut

        if not self.verify():
            return False
        try:
            target, runtime_id, pattern, _ = self._focused()
            original, expected_id, prefix, suffix = self.anchor
            match = None
            # FindText avoids Python codepoint vs provider UTF-16/grapheme offsets.
            for needle in dict.fromkeys(
                (self.current, self.current.replace("\n", "\r"), self.current.replace("\n", "\r\n"))
            ):
                search = pattern.DocumentRange.Clone()
                for _ in range(32):
                    candidate = search.FindText(needle, False, False)
                    if not candidate:
                        break
                    before = pattern.DocumentRange.Clone()
                    before.MoveEndpointByRange(1, candidate, 0)
                    if self._text(before) == prefix:
                        match = candidate
                        break
                    search.MoveEndpointByRange(0, candidate, 1)
                if match is not None:
                    break
            if match is None or self._text(match) != self.current or not self.verify():
                return False
            match.Select()
            target, runtime_id, pattern, selected = self._focused()
            if (
                target != original
                or runtime_id != expected_id
                or self._text(selected) != self.current
                or self._text(pattern.DocumentRange) != prefix + self.current + suffix
            ):
                return False
            pyperclip.copy(replacement)
            target, runtime_id, pattern, selected = self._focused()
            if (
                target != original
                or runtime_id != expected_id
                or self._text(selected) != self.current
                or self._text(pattern.DocumentRange) != prefix + self.current + suffix
                or pyperclip.paste() != replacement
            ):
                return False
            send_paste_shortcut()
            previous = self.current
            self.current = canonical(replacement)
            self.caret = None
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                if self.verify(check_caret=False):
                    return True
                time.sleep(0.025)
            self.current = previous
            self.anchor = None
            return False
        except Exception:
            return False
        finally:
            # Restore only a selection still owned by this attempted replacement.
            # Never move the caret after an external edit or focus change.
            try:
                target, runtime_id, pattern, selected = self._focused()
                if (
                    self.caret is not None
                    and self.anchor is not None
                    and target == self.anchor[0]
                    and runtime_id == self.anchor[1]
                    and self._text(selected) == self.current
                    and self._text(pattern.DocumentRange)
                    == self.anchor[2] + self.current + self.anchor[3]
                ):
                    self.caret.Select()
            except Exception:
                pass
