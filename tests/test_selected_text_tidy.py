import re

import pytest

import push_to_talk_realtime as app
import selected_text_tidy as tidy
from recording_modes import PasteCycleFilter


class FakeDesktop:
    def __init__(self, *, selection="original", result="rewritten"):
        self.selection = selection
        self.result = result
        self.clipboard = "before"
        self.sequence = 1
        self.input = 10
        self.focus = "target"
        self.notifications = []
        self.archives = []
        self.pasted = False
        self.feedback = []
        self.archive_ok = True

    def copy(self):
        self.clipboard = self.selection
        self.sequence += 1

    def write(self, text):
        self.clipboard = text
        self.sequence += 1

    def dependencies(self):
        return tidy.SelectedTextTidyDependencies(
            capture_target=lambda: self.focus,
            foreground_matches=lambda target: target == self.focus,
            last_input=lambda: self.input,
            wait_for_release=lambda: True,
            clipboard_sequence=lambda: self.sequence,
            clipboard_read=lambda: self.clipboard,
            clipboard_write=self.write,
            copy_selection=self.copy,
            paste=lambda: setattr(self, "pasted", True),
            transform=lambda _: self.result,
            archive_raw=lambda raw: (self.archives.append([raw, None, None, None]) or 7)
            if self.archive_ok
            else None,
            archive_final=lambda _, final, status, error: self.archives[-1].__setitem__(
                slice(1, 4), [final, status, error]
            ),
            feedback_started=lambda: self.feedback.append("start"),
            feedback_finished=lambda: self.feedback.append("finish"),
            notify=self.notifications.append,
            busy=lambda: False,
        )


def test_success_replaces_same_selection_and_archives_both_versions():
    desktop = FakeDesktop()
    tidy.SelectedTextTidyJob(desktop.dependencies())._run(desktop.focus)
    assert desktop.pasted
    assert desktop.clipboard == "rewritten"
    assert desktop.archives == [["original", "rewritten", "completed", ""]]
    assert desktop.feedback == ["start", "finish"]


@pytest.mark.parametrize("selection,result", [("", "rewritten"), ("original", "   ")])
def test_no_selection_or_blank_response_never_pastes(selection, result):
    desktop = FakeDesktop(selection=selection, result=result)
    tidy.SelectedTextTidyJob(desktop.dependencies())._run(desktop.focus)
    assert not desktop.pasted
    assert desktop.clipboard == "before"


def test_copy_timeout_does_not_paste(monkeypatch):
    desktop = FakeDesktop()
    dependencies = desktop.dependencies()
    dependencies.copy_selection = lambda: None
    job = tidy.SelectedTextTidyJob(dependencies)
    values = iter((0.0, 1.0))
    monkeypatch.setattr(tidy.time, "monotonic", lambda: next(values))
    assert job._copy(desktop.sequence) is None
    assert not desktop.pasted


def test_focus_or_user_activity_change_keeps_result_for_clipboard_and_history():
    desktop = FakeDesktop()
    dependencies = desktop.dependencies()
    dependencies.transform = lambda _: (setattr(desktop, "input", 11) or "rewritten")
    tidy.SelectedTextTidyJob(dependencies)._run(desktop.focus)
    assert not desktop.pasted
    assert desktop.archives[-1][2] == "recovery"
    assert desktop.clipboard == "rewritten"


def test_independent_clipboard_change_is_not_overwritten():
    desktop = FakeDesktop()
    dependencies = desktop.dependencies()
    dependencies.transform = lambda _: (desktop.write("other") or "rewritten")
    tidy.SelectedTextTidyJob(dependencies)._run(desktop.focus)
    assert not desktop.pasted
    assert desktop.clipboard == "other"


def test_selection_change_before_final_paste_is_recovery():
    desktop = FakeDesktop()
    copies = 0

    def copy():
        nonlocal copies
        copies += 1
        desktop.selection = "changed" if copies == 2 else "original"
        FakeDesktop.copy(desktop)

    dependencies = desktop.dependencies()
    dependencies.copy_selection = copy
    tidy.SelectedTextTidyJob(dependencies)._run(desktop.focus)
    assert not desktop.pasted
    assert desktop.archives[-1][2] == "recovery"


def test_archive_failure_preserves_selection_and_skips_request():
    desktop = FakeDesktop()
    desktop.archive_ok = False
    tidy.SelectedTextTidyJob(desktop.dependencies())._run(desktop.focus)
    assert not desktop.pasted
    assert desktop.clipboard == "before"


def test_f15_filter_suppresses_repeats_and_release():
    calls = []
    hook = tidy.SelectedTextTidyFilter(lambda: calls.append("start") or True)
    assert hook.consume(tidy.F15_VK, True)
    assert hook.consume(tidy.F15_VK, True)
    assert hook.consume(tidy.F15_VK, False)
    assert calls == ["start"]


def test_job_does_not_start_while_dictation_side_reports_busy():
    desktop = FakeDesktop()
    dependencies = desktop.dependencies()
    dependencies.busy = lambda: True
    assert not tidy.SelectedTextTidyJob(dependencies).start()


def test_existing_ctrl_v_cycle_is_unaffected_by_f15_filter():
    cycles = []
    cycle = PasteCycleFilter(lambda: cycles.append("cycle") or True)
    assert cycle.consume(0x56, True, True)
    assert cycle.consume(0x56, False, False)
    assert cycles == ["cycle"]


def test_android_tidy_prompt_equivalence():
    source_path = (
        app.SCRIPT_DIR.parent
        / "power-dictation-android/android/app/src/main/java/com/mog/powerdictation/TranscriptStyle.java"
    )
    if not source_path.exists():
        pytest.skip("Optional Android source equivalence check requires sibling checkout")
    source = source_path.read_text(encoding="utf-8")
    tidy_block = re.search(r"TIDY_INSTRUCTION\s*=\s*(.*?);\s*\n", source, re.DOTALL).group(1)

    def decode(parts):
        return bytes("".join(parts), "utf-8").decode("unicode_escape")

    android_tidy = decode(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', tidy_block))
    wrapper_block = re.search(
        r"static String lunaInstructions.*?return (.*?);", source, re.DOTALL
    ).group(1)
    android_wrapper = decode(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', wrapper_block))
    assert android_tidy == app.SELECTED_TEXT_TIDY_INSTRUCTION
    assert android_wrapper == app.SELECTED_TEXT_TIDY_WRAPPER


def test_selected_tidy_request_rejects_truncated_response(monkeypatch):
    class Response:
        status = "incomplete"
        incomplete_details = object()
        output_text = "partial"

    class Client:
        class responses:
            @staticmethod
            def create(**_):
                return Response()

    monkeypatch.setattr(app, "openai_client_with_timeout", lambda _: Client())
    with pytest.raises(ValueError, match="incomplete"):
        app.transform_selected_text_tidy("input")


def test_selected_tidy_request_uses_terra_with_android_tidy_prompt(monkeypatch):
    request = {}

    class Response:
        status = "completed"
        incomplete_details = None
        output_text = "rewritten"

    class Client:
        class responses:
            @staticmethod
            def create(**kwargs):
                request.update(kwargs)
                return Response()

    monkeypatch.setattr(app, "openai_client_with_timeout", lambda _: Client())
    assert app.transform_selected_text_tidy("input") == "rewritten"
    assert request["model"] == "gpt-6.1-sol"
    assert request["instructions"] == app.selected_text_tidy_instructions()
    assert request["reasoning"] == {"effort": "low"}
    assert request["max_output_tokens"] == 8192
    assert request["store"] is False


def test_focus_changes_while_releasing_shortcut_never_copies_or_calls_api():
    desktop = FakeDesktop()
    dependencies = desktop.dependencies()
    dependencies.wait_for_release = lambda: (setattr(desktop, "focus", "other") or True)
    dependencies.copy_selection = lambda: pytest.fail("Must not copy from a different field")
    dependencies.transform = lambda _: pytest.fail("Must not send a different selection")
    tidy.SelectedTextTidyJob(dependencies)._run("target")
    assert desktop.clipboard == "before"
    assert not desktop.pasted


def test_unavailable_input_tracking_fails_closed():
    desktop = FakeDesktop()
    dependencies = desktop.dependencies()
    dependencies.last_input = lambda: None
    dependencies.copy_selection = lambda: pytest.fail("No trustworthy input snapshot")
    tidy.SelectedTextTidyJob(dependencies)._run("target")
    assert not desktop.pasted


def test_final_archive_failure_never_replaces_document():
    desktop = FakeDesktop()
    dependencies = desktop.dependencies()

    def broken_archive(*_):
        raise OSError("disk unavailable")

    dependencies.archive_final = broken_archive
    tidy.SelectedTextTidyJob(dependencies)._run("target")
    assert not desktop.pasted
    assert desktop.clipboard == "before"


def test_external_copy_between_result_write_and_paste_is_preserved():
    desktop = FakeDesktop()
    dependencies = desktop.dependencies()

    def write(text):
        desktop.write(text)
        if text == "rewritten":
            desktop.write("external clipboard")

    dependencies.clipboard_write = write
    tidy.SelectedTextTidyJob(dependencies)._run("target")
    assert not desktop.pasted
    assert desktop.clipboard == "external clipboard"


def test_start_thread_failure_releases_running_state(monkeypatch):
    desktop = FakeDesktop()
    job = tidy.SelectedTextTidyJob(desktop.dependencies())

    def fail_start(_):
        raise RuntimeError("thread unavailable")

    monkeypatch.setattr(tidy.threading.Thread, "start", fail_start)
    assert not job.start()
    assert not job.is_running()
