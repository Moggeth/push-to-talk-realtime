# Insertion context audit

## Findings and fixes

The user's prior incidents could not be reconstructed: the legacy log sanitizes
dynamic fields and previously had no structured insertion event. Inspecting the
structured runtime log confirmed no historical insertion decision/output records.
No raw transcript/history database or user caret text was read for this audit.

The native reader expanded a selection range by 256 characters without clamping
it to the focused editor document. A synthetic provider that expands into the
enclosing page reproduced an empty editor acquiring surrounding text. It also
accepted document patterns without evidence of editability and checked only the
native target window after reading, not the UIA element and selection endpoints.
These are demonstrated defects; they are not proof of the user's exact trigger.

The reader now verifies focused element identity and editability, requires the
document range to enclose the same focused element, verifies selection bounds,
clamps both adjacent ranges to that document, and checks the current element and
selection again after reading. It does not read ValuePattern.CurrentValue or any
other whole-field string. Unsupported/uncertain providers fall back visibly.
The 250 ms isolated helper timeout remains in place. Provider calls cannot block
the recording thread; no focus, selection or pointer manipulation is introduced.

Formatting now recognizes directional anchors and CR/Unicode paragraph breaks,
uses standalone starts for empty wrappers and list markers, and keeps sentence
punctuation when the next text is in a later paragraph. Mid-word joins, selection
replacements, existing whitespace/punctuation, names/acronyms/I, mode overrides
and suffix choices are covered by the finite boundary matrix and existing tests.
English capitalization and sentence-boundary rules remain conservative heuristics;
this does not establish perfect interpretation of every abbreviation or grammar.

## Diagnostics

Each prepared paste emits an insertion_decision event with the mode, style,
decision reason, context status, control type, context lengths, blankness, edge
categories, selection presence, empty-document flag, elapsed milliseconds,
input/output initial-case categories, terminal-punctuation setting and spacing/
punctuation/case transformation flags. The insertion_output event records direct
insertion, shortcut paste or refusal/failure. Both use the same insertion_id and
the standard per-process run_id. Existing rotated app.events.jsonl storage and
support-report sanitization are reused. IPC diagnostics pass an explicit field
allowlist before reaching the durable logger. No neighboring words, field names,
window titles, credentials, clipboard values or arbitrary exception strings are
added. Startup source fingerprints now include the insertion/helper modules.

Inspect these events, rather than the intentionally sanitized legacy log, after
the user reports a timestamp or the next surprising cue. If blank context is
reported but the input was already lowercase, this can be distinguished from a
lowered_initial transformation. If before_length is nonzero and context status
is unscoped/outside_editor/caret_changed, inspect the provider boundary behavior
using synthetic fixtures before considering a live native probe.

## Verification and measured work

- Total through this handoff: 530.270 s; edits/verification portion 406.493 s.
- Account switch: 0.141 s; fetch all: 1.477 s; safe pull: 0.757 s (already current).
- Source/log discovery steps: individual commands 0.06-0.23 s; no historical
  insertion events were present in inspected structured records.
- First affected suite: 196 passed in 7.44 s (command 8.217 s).
- Expanded insertion/scope suite: 88 passed in 0.69 s (command 1.289 s).
- Full suite: 568 passed in 32.94 s, including the 1,890-case loop matrix.
- Final logging refinements: 107 passed in 5.95 s (command 6.604 s).
- UIA constant verification via the installed generated typelib: 0.216 s;
  confirmed Edit=50004, Document=50030, ValuePattern=10002,
  IsTextEditPatternAvailable=30149. No user UI was queried.

## Failed strategies and future fast path

A read-only WorkCodex review was attempted with a 120-second cap. It failed after
9 seconds (initial command wait 10.009 s) because Azure returned 401: principal
does not have access to the operation. No independent review was obtained and no
retry/model/credential workaround was attempted; the local audit continued.
Do not retry this route until the company Azure authorization is repaired.

One patch used stale formatted regex context and failed at 0.0 s reported tool
duration. Reading current source and applying narrow hunks resolved it. Ruff
fixed a single import ordering issue before tests. All test operations used
synthetic provider/input dependencies; no running app restart was performed.

Activate with tray Restart. New public publication needs an explicit request.
