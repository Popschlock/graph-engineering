---
name: ge-pause-roadmap
description: Pause a running roadmap after the current task, so the user can try the build, read a summary on a topic, or change the goal. Use when the user types /ge-pause-roadmap <r> human-test | summary <topic> | adjust [note].
---

# /ge-pause-roadmap <r> <reason> [note]

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. The reason is `human-test`, `summary <topic>` or `adjust`; anything else: name the three and stop.
2. `GE pause <r> "<reason>" "<note>"` — writes `ge/<r>/PAUSE` (first line the reason, the rest the note) and a `paused <reason>` ledger row.
3. `GE render <r>` — `ge/<r>/status.html`'s ledger tail then carries the `paused <reason>` row, so an open tab shows the hold.
4. `GE commit <r> pause --close -m "ge(<r>): pause <reason>"`.
5. Say one line: if `/ge-run-roadmap <r>` is live in this session it acts at its next boundary (step 1 of its loop); otherwise the next `/ge-run-roadmap <r>` sees the PAUSE first. A node already dispatched finishes its commit.
