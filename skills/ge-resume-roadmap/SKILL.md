---
name: ge-resume-roadmap
description: Resume a paused or stopped roadmap. Settles any decisions waiting on the user first, then clears the pause and records it. Use when the user types /ge-resume-roadmap <r>.
---

# /ge-resume-roadmap <r>

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. `GE guards <r>`: `pause: absent` and `stop: absent` → say "not paused" and stop.
2. `GE calls <r>`: for each open call ask the human for their word (one line each); move each decided one in `ge/<r>/calls.md` from `## Open` to `## Decided` as `* <YYYY-MM-DD> <the call> — <their word>`; a call they leave open stays. A decided call that unblocks a node (`blocked: human call`) → `GE set <r> <id> --status open`; `GE next <r>` lists the `blocked:` ids when nothing is ready, otherwise find the node in `ge/<r>/roadmap.md`.
3. `GE resume <r>` (removes PAUSE and STOP; ledger `resumed`); `GE validate <r>`; `GE render <r>`.
4. `GE commit <r> resume --close -m "ge(<r>): resume"`.
5. If the runner is live in this session, continue its loop at step 1; otherwise say "resumed; run /ge-run-roadmap <r>".
