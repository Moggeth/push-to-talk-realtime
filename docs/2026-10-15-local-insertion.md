# Local caret-aware insertion

Auto is the missing-settings/default mode. Standalone preserves the existing
punctuation and suffix preferences; Insert uses fragment formatting even when
context is unavailable. Auto chooses based on nearby sentence/paragraph endings
and visibly falls back to standalone when context cannot be read.

The existing rewrite helper reads bounded UIA ranges around the selection.
It does not modify the selection or clipboard, rejects password controls and
checks the expected focused target. The app waits at most 250 ms for its reply;
a stalled provider causes helper termination and ordinary output fallback.
The helper is warmed through the existing background startup warmup. This adds
no new persistent process beyond the existing helper and no new dependency.
Adjacent text remains in local memory and is never added to logs/history/API
payloads. The app logs only the chosen style. Output rechecks the target after
context retrieval and again after the paste delay when contextual formatting
was applied. These checks cannot make separate OS operations atomic against
every external edit.

Formatting is deliberately conservative English prose logic. Only known common
opening words are lowered; unfamiliar words may be proper names. This cannot
perfectly distinguish every name from a common word. It preserves internal
sentences, acronyms, I, common abbreviations and ellipses. Code-specific parsing,
full grammatical rewriting, and deleting punctuation already in the editor are
outside this version. Existing raw transcript archival remains unchanged.

The insertion plan is also used to prepare the raw rewrite-review alternative,
so comparison/reversion works against the actual inserted text. Bullet mode
bypasses contextual formatting. Temporary decision feedback lasts 2.5 seconds
and uses the existing overlay, fitting text to its fixed width. Auto: unavailable
explicitly means standalone formatting without caret context.

## Measured work and lessons

- Discovery, implementation and verification through this handoff: 452.796 seconds.
- Account switch: 0.215 s; fetch all: 1.547 s; pull: 0.851 s (already current).
- First focused verification: command 4.204 s, 183 passed/2 failed (new setting
  and menu choices required updating exact schema/menu assertions).
- Updated focused integration: command 2.764 s, pytest 1.93 s, 186 passed.
- Final insertion subset: command 1.988 s, pytest 1.06 s, 26 passed.
- Render contact sheet: 0.432 s; inspected at native size.
- Full suite: pytest 34.27 s, 503 passed. Ruff lint 0.120 s; format 0.159 s.
- Diff check: 0.189 s, clean apart from normal Windows line-ending notices.

One patch failed because its hunks were out of source order; apply changes in
source order. A second patch matched Python string escapes incorrectly; narrower
patch context and Ruff's structural simplification resolved it. PowerShell rg
path wildcard usage failed again (0.220 s): pass explicit filenames or -g filters.
Ruff corrected imports and a nested condition before final verification.

No UI redesign, new model, remote service, live text capture or app restart.
User acceptance across actual native/browser editors remains outstanding.
