---
name: ge-stop-roadmap
description: Hard-stop a Graph Engineering roadmap - writes STOP so the runner stops dispatching at its next boundary. Use when the user types /ge-stop-roadmap <r>.
---

# /ge-stop-roadmap <r>

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. `GE stop <r>` — writes `ge/<r>/STOP`.
2. `GE render <r>` — regenerates `ge/<r>/status.html` so an open tab is current as of the stop.
3. `git add ge/<r> && git commit -m "ge(<r>): stop"`.
4. Say one line: the runner stops dispatching at its next boundary; a running node finishes its commit; `/ge-resume-roadmap <r>` clears the STOP.
