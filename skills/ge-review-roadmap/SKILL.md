---
name: ge-review-roadmap
description: Ask the reviewer to look at a roadmap now, show what it proposes (reordering, tasks to redo, decisions for the user), and apply it if the user agrees. Use when the user types /ge-review-roadmap <r>.
---

# /ge-review-roadmap <r>

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. `Agent` with `subagent_type` `graph-engineering:ge-reviewer` and the prompt `review roadmap <r> now; ge: python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`. If the Agent tool does not know the namespaced name, use the bare `ge-reviewer`. If `ge/config.md`'s `## Tiers` names a different model on the reviewer row, pass it as the Agent call's `model` — that per-dispatch argument is the tier override. Wait.
2. Show the proposal verbatim and ask "apply?".
3. Yes → `moves: none` means no move and `calls: none` means no call: apply nothing for either, and the same for `reruns: none`. Otherwise each `moves` line is `X deps=<ids> — <reason>`, so first read `GE node <r> X` and keep its current `deps:` line, then `GE set <r> X --deps "<list>"` where the list is what follows `deps=` up to the em dash (` — `), trimmed — the reason is never part of `--deps`; each rerun id → `GE set <r> <id> --status open`; each `calls` line → `* <line>` under `## Open` in `ge/<r>/calls.md`; `GE validate <r>` (exit 2 → restore each moved node with `GE set <r> X --deps "<the ids after 'deps: ' on the kept line>"`, and say so). Then, ALWAYS — an all-`none` proposal included, because a review that happened is a ledger row whether or not it moved anything: `GE event <r> review "<the REVIEW line>; next <id>"`; `GE render <r>`; `git add ge && git commit -m "ge(<r>): review — <no change|reorder>"`.
   No → `GE event <r> review "declined: <the REVIEW line>"`, then `git add ge/<r> && git commit -m "ge(<r>): review declined"` so the ledger row is not left uncommitted, and change nothing else.
