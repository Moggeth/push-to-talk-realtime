# Bullet feedback fix

The default Pillow font did not provide the bullet glyph used by the cursor
label. Bullet mode is now explicit snapshot/visual state and renders three
supersampled circles, including during mode blends. Optional text labels occupy
a separate row. Gesture thresholds and recording behavior are unchanged.

Swiftpoint's documented X1 API v2 supports Vibrate duration/strength commands.
Windows feedback uses a hidden short-lived process to isolate synchronous pipe
I/O; a one-second timeout kills and reaps a stalled helper. At most one request
is in flight, with no queued stale feedback. Other platforms skip feedback.
No bindings, profiles or X1 settings are changed. Enable/disable via X1 API.
Reference: https://support.swiftpoint.com/portal/en/kb/articles/x1-api

## Verification and measured timing

- Git account corrected to repository owner Moggeth: 0.196 s.
- Fetch all remotes: 1.566 s; fast-forward pull: 0.880 s (already current).
- Implementation through final verification: 108.196 s (includes nested steps below).
- Focused tests: 53 passed, pytest 1.49 s; command 2.764 s.
- Full tests: 477 passed, pytest 36.08 s.
- Native pulse probe: X1 returned OK, 0.265 s. User must assess perceived feel.
- Final Ruff lint: 0.218 s; format: 0.134 s; diff check: 0.156 s.

## Lessons and boundaries

PowerShell does not expand filename wildcards for rg path arguments: the first
search using cursor* failed in 0.114 s. Use rg -g filters instead. Initial lint
found an import-order error (0.146 s); ruff check --fix corrected it (0.181 s).
No Computer Use, pointer injection, clipboard manipulation or app restart.
Public upstream publication requires approval for these new changes.
