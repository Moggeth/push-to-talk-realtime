# Four insertion regressions fixed

## Implementation

Carry selected_leading_space alongside the existing trailing-space boolean from
the native reader through validated IPC and diagnostics. Restore each consumed
separator independently; don't mistake a selection spanning word separators
for an insertion into the middle of an unbroken token.

Recognize an initially uppercase, otherwise lowercase lexical word even when
it contains an apostrophe. Preserve I and I-apostrophe contractions explicitly,
and retain acronym/mixed-case behavior. This fixes Don't and Don\u2019t during
selected-lowercase-word replacement without requiring a language model.

Reuse known abbreviations for both left-context sentence-boundary detection and
terminal-period protection. Titles such as Dr. continue the current sentence.
The ambiguous etc. can still end a sentence. Punctuation cleanup must not strip
meaningful abbreviation/initial periods or ellipses before adjacent punctuation.
Local heuristic ambiguity remains for unrestricted natural-language grammar.

Only the four requested findings are addressed here. The separate quoted-phrase
edge case mentioned in the ignored audit report is not changed in this commit.

## Exact verification and measured learning

- Total discovery/implementation/verification through handoff: 178.412 s.
- Fetch all: 1.461 s; divergence inspection 0.103 s (zero behind, three completed
  local commits ahead). Existing unrelated untracked directories were preserved.
- Red regressions: all five exact-example cases failed in 0.17 s (command 0.709 s),
  confirming the four defects, including both apostrophe styles.
- First affected suite after fixes: 122 passed in 1.04 s (command 1.641 s).
- Full final suite: 610 passed in 34.46 s.
- Final Ruff lint 0.093 s; format 0.098 s (76 files).
- Initial lint caught a nested condition in 0.140 s; combined the branches.
- One patch failed at 0.0 s reported duration because Ruff had wrapped a long
  assertion. Read the current test and anchor the patch on a function definition
  rather than a formatting-sensitive assertion. No files were partially changed.

The earlier broad matrix missed these because it asserted general invariants.
Keep these complete expected-sentence regressions, including the native context
transport for selected separators, as the fast path before future formatting
changes. Existing input scope, timing bounds, history and recording code remain.
No dependencies, desktop automation or running-app restart. Activate via tray
Restart. Publication of these additional public-repository changes is pending.
