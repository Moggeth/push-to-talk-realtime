# Consecutive sentence spacing

## Evidence and objective

The user's screenshot and message show two consecutive dictations joined after
a full stop. Structured events identify a recurring mechanism without storing
the dictated words: insertion 94 at 17:35:44 +11:00 saw empty preceding context
and one following newline, chose standalone, and omitted the trailing space.
Insertion 95 at 17:35:47 +11:00 fell back with outside_editor, so it did not add a
leading separator. Similar later fallback events were present. These records
explain the spacing failure pattern, but cannot identify the screenshot's exact
words because diagnostics intentionally exclude content.

The simple fix is to honor the configured output suffix at an Auto end-of-field
or final-paragraph boundary, rather than relying on every subsequent accessibility
read succeeding. No additional clipboard probing, hidden keystrokes, recent-text
guessing or weakening of scope checks is required.

## Behavior

An explicit automatic flag on the insertion plan distinguishes Auto's paragraph-
ending output from an explicit Insert fragment. At field end, or before a final
whitespace-only newline marker, retain a requested Space suffix. A requested
Newline is retained at a true empty suffix but not duplicated before an existing
newline. Existing real following prose still governs middle-of-text spacing.
None stays None; explicit Insert retains fragment suffix behavior. This also
preserves Auto's requested suffix when finishing an unfinished sentence at field
end. Healthy context still adds a leading space when preceding text ends directly
in a full stop. New suffix_mode metadata helps distinguish preference from error.

The outside_editor fallback remains visible and conservative. This fix prevents
its loss of leading-context information from joining standard Space-suffix
dictations. It does not claim to repair every native accessibility provider.

## Measured verification and lessons

- Total discovery, implementation and verification through handoff: 197.090 s.
- Initial structured-event inspection: 0.330 s; all reads were content-free.
- Account switch 0.116 s; fetch all 1.444 s; safe pull 0.779 s (already current).
- Red regression command: 1.383 s, pytest 0.23 s; four failed, one passed. The
  passing case established that ordinary leading-space repair already worked.
- Initial affected suite: 275 passed in 1.52 s (command 2.194 s).
- Final expanded affected suite: 305 passed in 7.71 s (command 8.347 s).
- Final Ruff lint 0.139 s; format 0.114 s; diff check 0.121 s.

The first test draft's expected capitalization was corrected for an existing
unfinished prefix; the earlier implementation already lowercased that opener.
A patch containing an unnecessary stale long-assertion hunk failed at 0.0 s
reported duration. Remove no-op hunks and anchor new tests on function definitions
to avoid repeating formatting-sensitive patch failures. Source changes were
verified with the affected suite; no redundant full-suite rerun was needed.

No app restart, clipboard mutation or desktop automation. Regression clipboard
and paste operations are fakes. Preserve these two-successive-output tests when
changing suffix policy; isolated single-insertion tests missed this interaction.
