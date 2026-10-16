# Selected word case inheritance

The context reader previously discarded the selected word. Mid-sentence case
formatting could lower common opening words but retained other title-cased
replacement words, so a provider's Better. remained capitalized.

Read at most 257 selected characters locally to reject oversized selections.
Classify a bounded, single lowercase word and consumed trailing whitespace;
only those booleans accompany the already-bounded adjacent context through IPC.
No selected word is stored in diagnostics. A mid-sentence title-cased single
word inherits lowercase from that selection. I and all-uppercase acronyms retain
case. Sentence starts and explicit Standalone retain normal formatting. The
space consumed by selection is restored where required, including at field end.
Selection of multiple words or truncated/oversized text does not supply this
case signal. A title-cased proper name intentionally replacing a lowercase word
also inherits lowercase; Standalone is the explicit override.

The helper remains bounded by its existing 250 ms timeout and verifies scope and
selection stability. New diagnostic booleans selected_lowercase_word and
selected_trailing_space plus insertion_reason=word_replacement make this path
distinguishable from ordinary continuation.

## Measured verification

- Total investigation, implementation and verification through handoff: 186.008 s.
- Account switch 0.124 s; fetch all 1.384 s; divergence 0.075 s (zero behind,
  one earlier unpushed audit commit ahead; no pull required).
- Initial suite: 124 passed/2 failed in 6.04 s (command 6.573 s). Evidence showed
  the initialism rule incorrectly preserved I. in a fragment and inheritance
  did not recognize a word with a retained full stop at the end of a field.
- Corrected both: 126 passed in 5.94 s (command 6.688 s).
- Final IPC/app/punctuation checks: 179 passed in 1.11 s (command 1.657 s).
- Ruff lint 0.094 s; full format check 0.079 s, 76 files.

Use the punctuation-free lexical word for inheritance while preserving its
terminal punctuation separately. Keep the pronoun I separate from dotted initials.
This is the verified fast path for future replacement-word cases. No live user
text, clipboard or desktop automation was used. Activate via tray Restart.
