# Auto punctuation regression

Two reproducible edge cases in the initial Auto implementation could remove a
full stop unexpectedly. Invisible rich-editor anchors counted as preceding text,
so an apparently blank paragraph could choose Insert. Auto also removed final
punctuation when extending an unfinished sentence with nothing after the caret.

Interpret known editor anchors as empty context without changing the document
or transcript. Make terminal punctuation trimming an explicit part of the
insertion plan: Auto trims for actual continuation text; explicit Insert keeps
its fragment behavior. Raw history and surrounding editor text are unchanged.

Live metadata inspection found no recent insertion-decision log entries and the
on-disk legacy settings lacked insertion/punctuation keys. This did not establish
the actual live editor trigger; no live caret text was read. The assistant asked
which cursor cue was shown; no answer was available during the implementation.

## Measured work

- Investigation, fixes, and targeted verification through documentation: 156.904 s.
- Git account switch 0.169 s; fetch all 1.482 s; divergence check 0.090 s:
  main zero behind, one prior unpushed feature commit ahead.
- First insertion regression suite: 33 passed in 0.77 s (command 1.593 s).
- Final insertion, text processing and app integration suite: 179 passed in
  1.24 s (command 1.837 s).
- Initial lint 0.242 s; format 0.096 s; final formatting 0.081 s.

Read-only Windows process inspection initially filtered on a script filename
that was absent because the app executes through the start launcher. Inspection
of script paths identified the launcher and review helper. Prefer known runtime
metadata and launcher paths, never print unrestricted process command lines.
PowerShell Select-Object -ExpandProperty PSObject did not work for JSON-adapted
objects; use explicit known properties. Settings inspection was not evidence
that the live app had disabled terminal punctuation.

No app restart or user-input simulation. Activate via the normal tray Restart.
