# Cursor motion commission

Personal subscription identity verified in a cleaned child environment:
`fauxgrady@gmail.com`, `authMethod=claude.ai`, subscription `pro`.
Removed ANTHROPIC_*, CLAUDE_CODE_USE_* and CLAUDE_CODE_OAUTH_TOKEN variables.
Requested explicit `claude-opus-5-5`; returned modelUsage and canonicalModel both
confirm `claude-opus-5-5`, first-party provider. No fallback model, tools, MCP,
hooks, publication or paid extra usage were authorized. The reported cost field
is list-price metadata, not evidence of a subscription charge.

Isolated commission: C:/Users/mog/Documents/Codex/2026-09-28/ptt-motion-opus/
`brief.txt` and `commission-result.json` preserve the supplied source and complete
design handoff. Only cursor source and synthetic context were supplied, not user
audio/transcripts or credentials. Measured dispatch-to-result observation: 134.6s
(including the initial 10s tool yield); 180s commission cap.

## Integrated design

- Opus specifies a hollow half-size entry, 130 ms cubic-out rise to 1.05 scale,
  then 150 ms cosine settle to 1.0, with 80 ms quadratic-out opacity.
- A closed-form integrated entry sweep contributes 26.6 degrees over 280 ms.
- Existing audio smoothing drives bounded radius/width and arc length. A threshold
  crossing at 0.12 triggers a damped oscillator; rearm below 0.06, at least 160 ms
  between impulses. Keep at most three impulses, expiring after 350 ms.
- Jostle is deterministic, with radial/angular and sub-pixel center displacement.
  Silence and sustained audio do not continually retrigger it.
- Tidy diamond pops subtly; Fun sparkle also unwinds through 90 degrees on entry.
- No new draw layers, glow, dependencies, UI settings or audio backend changes.

## Integration adjustments

Preserved the existing collapse-to-pointer exit instead of adopting Opus's proposed
60%-size fade. A reversal uses existing continuous re-entry without replaying the
fresh-entry flourish. Entry marker/extent envelopes use the uninterrupted cycle
clock so quick releases cannot reset them. Head angle is explicitly independent
of changing arc length. Onset time is solved from the exponential audio smoother
instead of linear interpolation; fixed impulse strength improves frame-rate
consistency. Kept the existing restrained breathing rather than adding calm state.

Verified synthetic preview and clipping, interruption regressions and cross-rate
motion. Renderer benchmark: 600 frames, mean 1.03 ms, p95 1.58 ms, before final
entry-montage addition. Native target remains 120 Hz, not a measured display rate.
