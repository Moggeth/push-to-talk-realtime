# Replacement scope follow-up

## Confirmed runtime cause

Unlike the earlier incidents, the new logs identify the user's failing tests.
Eight consecutive recent decision events showed Auto, control_type=50004,
context_status=unscoped, insertion_reason=no_context, standalone formatting,
uppercase input/output, and no terminal punctuation removal. This establishes
why the app kept sentence formatting: it rejected context before the replacement
logic could run. It does not establish the exact provider tree shape.

The strict range-enclosing-element identity check introduced in the audit was
too restrictive. A legitimate editor range may be enclosed by an internal text
node rather than the focused editor element itself. Scope now accepts a verified
descendant relationship through at most 16 raw-tree parents. An inherited page
pattern can instead be narrowed with RangeFromChild(focused_editor). Selection
bounds, range clamping, editability and after-read stability checks remain.
Unproven containment still falls back. Diagnostics record the scope path.

The selected-word case rule also previously required the entire replacement to
be a single word. It now applies to the first lexical word of a phrase replacing
an explicitly lowercase selected word mid-sentence. I and all-cap acronyms are
preserved. Joining actual following text removes sentence-ending punctuation;
sentence starts remain standalone and selected separators are restored.

## Measured verification and learning

- Total investigation/implementation/verification through handoff: 159.465 s.
- Runtime decision metadata inspection: 0.346 s; focused follow-up 0.200 s.
- Account switch 0.134 s; fetch all 1.448 s; divergence check 0.085 s:
  zero behind, two already-completed local commits ahead.
- A one-line metadata probe failed with a PowerShell/Python quote SyntaxError
  in 0.127 s. Use a saved ignored probe script rather than nested exec strings.
- Saved metadata-only probe: 0.298 s, unavailable with ValueError because no
  usable selection was exposed by the then-focused element. No user text,
  names, selections or clipboard values were read or changed. Do not infer the
  provider tree shape from this unavailable probe; rely on regression fixtures
  and context_scope during the next normal user test.
- Focused suite: 265 passed in 1.53 s (command 2.232 s).
- Initial test lint found an unused fixture binding in 0.100 s. Replaced it
  with an underscore; final lint 0.104 s, format 0.093 s, diff check 0.097 s.

No app restart or desktop automation. Activate via tray Restart, then inspect
context_scope and insertion_reason for the next selected-word replacement.
This corrects the earlier audit's assumption that enclosing-element identity was
necessary for editor containment; it is sufficient, but not necessary.
