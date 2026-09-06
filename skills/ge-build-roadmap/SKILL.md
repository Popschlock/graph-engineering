---
name: ge-build-roadmap
description: Build a Graph Engineering roadmap with the human - the goal in their words, phases, tasks with deps, spec and gate - or convert an existing plan with --from. Creates ge/config.md when missing. Use when the user types /ge-build-roadmap <r> [goal | --from <plan.md>].
---

# /ge-build-roadmap <r> [<goal> | --from <plan.md>]

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root. The human is present: this is the skill that asks.

## 1. config.md (only when `ge/config.md` is missing)

Ask, in one message: (a) "Which command proves a task done, and which line of its output (or which file) shows it?" — one gate row each: a short name, the command, the success regex (a capture group for the count; `\1` may repeat a capture), the artifact (`stdout`, or a file glob read newest-first), and the floor — "how many does it pass today?" — which is a ratchet: the first capture group must stay at or above it, so a suite that SHRANK stops reading green. Leave the floor cell empty for a gate whose success line has no count; (b) "Is there anything that must not be running when a task starts?" — one guard row each: name, command, the regex that means blocked; (c) standing rules for an unattended session (may be none). Write:

    # ge config — <project>

    ## Gates
    | name | command | success | artifact | floor |
    |---|---|---|---|---|
    | <name> | <command> | `<regex>` | stdout | <count today, or empty> |

    ## Guards
    | name | command | blocked when |
    |---|---|---|

    ## Rules
    <their rules, verbatim>

    ## Tiers
    | role | model | effort |
    |---|---|---|
    | task | opus | xhigh |
    | reader | fable | high |
    | verifier | opus | xhigh |
    | reviewer | fable | high |

    ## Cadence
    review every: 3

A `|` inside a regex cell is written `\|`.

## 2. The goal

Without `--from`: the goal is the argument, or the answer to "What should be true when this roadmap is done — in your words?". Keep it verbatim. With `--from`: the goal is the plan's own goal/objective section (its `**Goal:**` line or its first heading's paragraph), read back to the human for a yes. Either way there must be a goal before step 4 — `GE init` refuses without one. Also take a SUBJECT: three to eight words for the roadmap's title line, asked as "and in a few words, what is this roadmap called?" or offered from the goal for a yes. Without one the title is the goal's first 60 characters, cut mid-word. If the `superpowers:brainstorming` skill is installed, run it on the goal to settle scope before phases, and `superpowers:writing-plans` when the phases need one; otherwise ask three questions: what exists now, what must not change, what proves it done.

## 3. Phases and tasks

With the human, name 1–6 phases (`<id> — <title>` and one paragraph naming the task ids in it) and, per task: id (`[A-Za-z0-9._-]+`, unique), subject (a read-first task's subject starts with `READ:`), deps (ids that must be done first), spec (a doc section, a file, or the text itself), gate names from config.md. Show the table; get a yes.

`--from <plan.md>`: read the plan. Every `### Task N:` heading (or a task-table row, or a numbered task heading) becomes a task: id `T<N>` or the plan's own id; subject the heading text; spec `<plan.md> Task N`; gate = the config gates whose command appears in the task's run steps, else the first gate; deps = the previous task in the same phase (phases = the plan's `##` sections that hold tasks; a plan without such sections is one chain). Show the table with the inferred deps; the human confirms or edits each dep line; only then write.

## 4. Write

If `ge/<r>/roadmap.md` already exists, stop and say to use `/ge-revise-roadmap <r>` (`GE init` refuses an existing roadmap).

`GE init <r> --goal "<goal>" --subject "<subject>"`; put the phases under `## Phases` in `ge/<r>/roadmap.md` (`### <id> — <title>` + paragraph); `GE add <r> --id <id> --subject "<subject>" --deps "<ids>" --spec "<spec>" --gate "<names>"` per task in order (`--deps` and `--gate` are comma-separated lists); `GE validate <r>` until `OK`. Write `ge/<r>/next.md` for `GE next <r>`'s node — `GE next <r>` prints `<id> | <subject> | <gates>` on stdout, so the node's id is the first pipe-separated field. Any `in progress: <id> — in progress (<session>)` line `GE next <r>` prints is on STDERR: a node a dead session left marked, not an error and not part of the id — say `stranded: <id> (<session>)` once and carry on. The kickoff: first line `# kickoff: <id>`, then a complete kickoff for a session that knows nothing (what to read, what to build, the pins or tests, its gate names, how to close). If `GE next <r>` prints `none`, the first line is `# kickoff: none`. `GE validate <r>` again, until `OK`. `GE render <r>`. `git add ge && git commit -m "ge(<r>): roadmap — <the goal's first words>"`. Say the next node and `/ge-run-roadmap <r> dry` to see its brief.
