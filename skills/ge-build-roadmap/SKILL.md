---
name: ge-build-roadmap
description: Plan a roadmap with the user the way plan mode plans a change, then write it. Reads the project first, asks only what the goal leaves open, proposes the tasks with real dependencies and what each holds while it runs so independent tasks run side by side, and writes the rows once the user approves. Can also convert a plan file with --from. Writes ge/config.md if the project has none. Use when the user types /ge-build-roadmap <r> [goal | --from <plan.md>].
---

# /ge-build-roadmap <r> [<goal> | --from <plan.md>]

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root. The human is present: this is the skill that asks. It has two halves: plan (steps 0 to 3, read-only, in plan mode) and write (step 4, after approval). If `ge/<r>/roadmap.md` already exists, stop at once and say to use `/ge-revise-roadmap <r>`.

## 0. Go wide first

Call `EnterPlanMode` if the tool is available; the rest of the planning half runs under it, so nothing is written until the human approves. Then read the project before asking anything: up to three `Explore` subagents in one message, on (a) the code and docs the goal touches and what already exists there, (b) the build and test commands and where their verdict appears (the gate rows of step 1 come from this), and (c) what only one task at a time can use: an editor that must be closed for a build, a device, a database, a running server, a file family many tasks edit. Those become the `locks` of step 3. With `--from`, read the plan file too. Keep the findings short: what exists, what proves a task done, what must not run twice at once.

## 1. config.md (only when `ge/config.md` is missing)

Propose the answers from step 0 and ask, in one `AskUserQuestion` round, only what the reading left open: (a) "Which command proves a task done, and which line of its output (or which file) shows it?" — one gate row each: a short name, the command, the success regex (a capture group for the count; `\1` may repeat a capture), the artifact (`stdout`, or a file glob read newest-first), and the floor — "how many does it pass today?" — which is a ratchet: the first capture group must stay at or above it, so a suite that SHRANK stops reading green. Leave the floor cell empty for a gate whose success line has no count. A regex over a FILE is `re.search` over the whole text, so anchor it to the element that carries the run's verdict — for NUnit/JUnit XML that is the root (`<test-run [^>]*result="Passed"[^>]*total="(\d+)" passed="\1" failed="0"`), because every nested `<test-suite>` carries its own `total`/`passed`/`failed` and an unanchored pattern reads MATCH off the first green child of a red run; (b) "Is there anything that must not be running when a task starts?" — one guard row each: name, command, the regex that means blocked; (c) standing rules for an unattended session (may be none). Write:

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
    max parallel: 3

A `|` inside a regex cell is written `\|`. `max parallel` caps how many tasks run at once; 3 is right for most projects, 1 for a project where everything holds one lock anyway.

## 2. The goal

Without `--from`: the goal is the argument, or the answer to "What should be true when this roadmap is done — in your words?". Keep it verbatim. With `--from`: the goal is the plan's own goal/objective section (its `**Goal:**` line or its first heading's paragraph), read back to the human for a yes. Either way there must be a goal before step 4 — `GE init` refuses without one. Also take a SUBJECT: three to eight words for the roadmap's title line, asked as "and in a few words, what is this roadmap called?" or offered from the goal for a yes. Without one the title is the goal's first 60 characters, cut mid-word. Where the goal leaves something open that would change the roadmap (what "done" looks like, which of two readings is meant, whether an existing piece is reused or replaced), ask it in the same `AskUserQuestion` round as step 1, with your proposed answer first; never a question the project files already answer.

## 3. Phases and tasks

Draft, from what step 0 found, 1 to 6 phases (`<id> — <title>` and one paragraph naming the task ids in it) and, per task: id (`[A-Za-z0-9._-]+`, unique), subject (a read-first task's subject starts with `READ:`), deps, spec (a doc section, a file, or the text itself), gate names from config.md, and locks.

Deps are DATA dependencies only: B depends on A when B reads what A writes (a finding, a function, a file), or when B's spec cannot be written until A has settled something. A dep that exists only to make things happen one after another is not a dep; the `locks` column is where "not at the same time" goes. Four reads of four different files depend on nothing and run together.

Locks name what a task holds exclusively while it runs, from the list step 0 found: `editor` for a task that needs the editor open, `build` for one that runs the build, a file family (`ui-widgets`) for a set of files several tasks would edit, `tree` for a task that touches so much that nothing should run beside it. A `READ:` task holds nothing unless its cell says so; any other task with an empty cell holds `tree`, which is the safe default and also the slow one, so fill the column in. Two tasks that share a lock never run together; two that share none may.

Under the table, write the plan for the run: which tasks will run side by side in each phase and why that is safe, and which cannot and what they share. Put the table and that paragraph in the plan file and call `ExitPlanMode`; the human's approval of the plan is the yes for the table. Without plan mode, show the same in chat and get a yes.

`--from <plan.md>`: every `### Task N:` heading (or a task-table row, or a numbered task heading) becomes a task: id `T<N>` or the plan's own id; subject the heading text; spec `<plan.md> Task N`; gate = the config gates whose command appears in the task's run steps, else the first gate; deps inferred from what each task reads and writes as above, never "the previous task"; locks by the same rule. Show the table with the inferred deps and locks; the human confirms or edits each line; only then write.

## 4. Write (after approval)

`GE init <r> --goal "<goal>" --subject "<subject>"` (it refuses an existing roadmap); put the phases under `## Phases` in `ge/<r>/roadmap.md` (`### <id> — <title>` + paragraph); `GE add <r> --id <id> --subject "<subject>" --deps "<ids>" --spec "<spec>" --gate "<names>" --locks "<names>"` per task in order (`--deps`, `--gate` and `--locks` are comma-separated lists; `--locks none` for a task that may run beside anything); `GE validate <r>` until `OK`. Then `GE dispatchable <r>`, which prints one `<id> | <subject> | <gates> | <locks>` line per task that can start at once (its stderr `running:` lines, if any, are tasks in progress, not errors), and write `ge/<r>/kickoffs/<id>.md` for EACH: first line `# kickoff: <id>`, then a complete kickoff for a session that knows nothing (what to read, what to build, the pins or tests, its gate names, how to close). `GE validate <r>` again, until `OK`. `GE render <r>`. `GE commit <r> build --close -m "ge(<r>): roadmap — <the goal's first words>"`. Say which tasks will start together and `/ge-run-roadmap <r> dry` to see their briefs.
