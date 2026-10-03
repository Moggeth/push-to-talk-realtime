# Rewrite Review Handoff - 2026-10-03

## Implementation

- GPT-6.1 Sol is the new rewrite default and selected-text Tidy default. A
  one-time settings migration preserves instructions, capture settings and
  shortcuts; subsequent choices survive restart. Explicit model env overrides
  remain supported. Low reasoning and an 8192-token output budget replace the
  incompatible none setting for Sol. Standard token pricing is in usage_tracking.
- Opus 5.5 supplied the stacked popup design, neutral palette/magenta active
  marker, Segoe typography and reversible hover lifetime. Verified canonical
  model: claude-opus-5-5, personal claude.ai subscription; 69.940 seconds. The
  isolated specification lives in the user's Codex design-output folder, not
  the repository or runtime logs. No metered Anthropic key was used.
- rewrite_review.py is bounded asynchronous IPC plus the independently testable
  lifetime model. rewrite_review_window.py is the Tk helper; rewrite_replacement.py
  is the conservative Windows UI Automation adapter. The main capture process
  never holds COM pointers or runs popup widgets. The helper has no API credentials
  in its command line or transcript files. Its IPC carries the displayed text.
- Replacement validates focused control identity, full surrounding document,
  current text and caret. Exact TextPattern ranges avoid character-count deletion
  and Unicode offset mistakes. Unknown or edited targets fall back to copying.
- output_transaction.py coordinates this app's paste/live output with helper
  replacements through a named Windows mutex. It cannot stop a user or unrelated
  application from editing between OS operations; repeated checks fail closed
  when a change is observed. Do not claim atomic editing across all applications.

## Verification and Lessons

- Model suite: first pass 161 passed, two old default/menu expectations; 2.41 s.
  Updated expectations: 163 passed in 2.06 s.
- Initial full suite: 366 passed in 28.84 s. Initial review tests: 8 passed in
  0.09 s. Later background full suite: 374 passed in 36.06 s. Expanded review
  regression: 10 passed in 0.35 s.
- Final background-only full suite: 376 passed in 28.35 s; Ruff lint and all
  nine touched Python formatting checks passed.
- UIA is available on this installation. The native comparison popup was seen
  and the synthetic editor retained focus. Full one-click acceptance in Codex
  remains unverified: the user stopped Computer Use and requested no further
  desktop interaction. Synthetic windows/processes were then stopped, leaving
  the user's running PTT service untouched. No paid OpenAI request was used.
- Do not block a synthetic editor's own UI thread while requesting UI Automation
  inspection: the provider may need that thread. The manual fixture now captures
  on a worker, matching production's delivery-worker architecture. A copy-only
  result from a blocked fixture is not evidence about Codex's accessibility.
- Computer Use's tool-window listing did not expose the no-activate popup as a
  separate target. The synthetic parent screenshot showed part of the overlay.
  Do not repeatedly attempt guessed window IDs or treat absence from that list
  as proof the popup failed. Fresh screenshots are needed for geometric clicks;
  text-only observations can produce geometry-unavailable errors.
- Prefer headless verification here. Do not run the optional visible fixture,
  Computer Use, or restart the user app while the user is working unless asked.

## Deployment

Pending the user's normal tray Restart. The update does not change running
processes. Native editor compatibility remains provider-dependent and clearly
falls back to Copy raw. Set PUSH_TO_TALK_REWRITE_REVIEW=0 to disable just the popup.
Public GitHub remote: no push performed without approval.
