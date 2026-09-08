---
name: ge-revise-roadmap
description: Change a roadmap with the user: the goal, tasks added or dropped, the order, specs, checks, and decisions made. Checks the result and records the change. Use when the user types /ge-revise-roadmap <r>, or from a pause with reason adjust.
---

# /ge-revise-roadmap <r>

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root. The human is present; this is the one time a whole roadmap is read into a session.

1. `GE validate <r>`; `GE ready <r>`; `GE calls <r>`; read `ge/<r>/roadmap.md` and show `## Goal` and the `## Tasks` table.
2. Ask what changes and apply each: the goal → edit `## Goal` verbatim; a new node → `GE add <r> --id .. --subject .. --deps .. --spec .. --gate .. [--after <id>]`; a node to drop → `GE set <r> <id> --status "skipped: <why>"` (rows are never deleted), then re-point each node that depended on it: `GE set <r> <dependent> --deps "<the skipped node's own deps, plus its other deps>"` (find dependents in the `## Tasks` table you already read) — a skipped node is never `done`, so a dependent left pointing at it can never be ready; order → `GE set <r> <id> --deps "<ids>"`; text → `GE set <r> <id> --spec|--gate|--subject`; a decided call → move it to `## Decided` in `calls.md` as `* <YYYY-MM-DD> <call> — <their word>` and `GE set <r> <id> --status open` for the node it blocked.
3. If the id `GE next <r>` prints — the first pipe-separated field of its `<id> | <subject> | <gates>` line on stdout; `none` is allowed. Any `in progress: <id> — in progress (<session>)` line `GE next <r>` prints is on STDERR: a node a dead session left marked, not an error and not part of the id — say `stranded: <id> (<session>)` once and carry on. If that id differs from the id on `next.md`'s first line (`# kickoff: <id>`), rewrite `ge/<r>/next.md` for the new node first: first line `# kickoff: <id>` (`# kickoff: none` when `GE next <r>` prints `none`), then a complete kickoff. Only then `GE validate <r>` until `OK` — it is what checks that first line, and it fails while `next.md` still names the old node. `GE event <r> revised "<one line: what changed>"`. `GE render <r>`. `git add ge && git commit -m "ge(<r>): revise — <what changed>"`.
