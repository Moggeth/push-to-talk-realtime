# Blank-field diagnostics handoff

The old logs established that a one-character `other` boundary triggered
continuation, but could not identify an invisible marker. Do not infer its identity
or strip additional Unicode characters without evidence; joiners can be meaningful.

Version-2 insertion events now describe raw boundary Unicode categories and
codepoints only for controls, format characters, separators and U+FFFC. The
serializer validates that restriction independently. Normalized and paragraph
lengths plus word-presence flags show whether normalization removed an anchor.
Scoped caret-at-editor-start/end flags distinguish range boundaries. Existing
run/insertion IDs, source hashes, scope/status and output events provide correlation.
No surrounding text, field names, clipboard contents or visible codepoints are saved.

The restarted PID 93316 reported ready with zero diagnostic write failures before
implementation. This change is not loaded until the next normal tray Restart;
the running app was not interrupted. A recurrence still needs the approximate
time, application and observed blank/selection state to ground provider metadata.

## Measured work

- Discovery, implementation, documentation and verification checkpoint: 118 seconds.
- Git fetch: 0.848 seconds; correct personal account verified first.
- Initial focused suite: 177 passed in 1.17 seconds.
- Full suite: 644 passed in 32.94 seconds.
- Final strengthened integration assertions: 167 passed in 0.83 seconds.
- Final Ruff lint / format checks: 0.110 / 0.104 seconds, both passed.
- Diff check: 0.127 seconds, passed (existing CRLF policy warnings only).
- Initial lint caught import ordering; fixed. One combined documentation patch
  used an incorrect README heading anchor and was rejected without edits; read
  the actual underline-style heading before retrying successfully.

Tests are synthetic and do not inject desktop input. No live accessibility or API
call was made. Formatting behavior is unchanged. Public origin requires explicit
publication approval; no push is part of this change.
