---
name: ge-status
description: Show where a Graph Engineering roadmap is - validate, render and open status.html, then print ready nodes, in-progress nodes, the last 3 ledger rows and open calls. Use when the user types /ge-status [r].
---

# /ge-status [r]

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. `GE list`. Print it. No `<r>` given: use the roadmap whose state is `in progress` or `paused`, else the only one, else ask which.
2. `GE validate <r>` — print its lines (exit 2 is reported, not fatal).
3. `GE open <r>` — renders `ge/<r>/status.html` and opens it (Windows `start`, macOS `open`, Linux `xdg-open`).
4. Print, each under its own one-word heading: `GE ready <r>`; the `in progress (...)` ids from the list line; `GE ledger <r> 3`; `GE calls <r>`.
5. Nothing else; do not open the roadmap file.
