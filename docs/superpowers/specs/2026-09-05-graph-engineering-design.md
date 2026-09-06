# Graph Engineering — design spec (v0.1)

Approved by the owner 2026-09-05. A first, project-specific version of this idea
(a `/run-roadmap` skill and four bespoke agents, written for a single private
repository) had already run real work end to end; this plugin is that pattern made
general: **a goal becomes a task graph; one interactive session runs the graph
unattended by dispatching a fresh subagent per node with an independent verifier
per close; the human pauses it to test, get a summary, or change the goal.**
Everything is files in the project's git. Any project, any gate.

## 1. Why

Long work in Claude Code dies in two ways: the session's context fills, and the
human has to paste a kickoff into every new session. A headless loop would remove
the pasting but depends on how headless use is metered (one pool with interactive
today; a separate-credit proposal is paused, not withdrawn). The pattern that
survives both is an interactive session that holds almost nothing and delegates
every task to a fresh subagent: its context grows by briefs and short reports, its
state lives on disk, and the human can watch or interrupt at any time.

## 2. Files in a project

All under `ge/` at the repository root, git-tracked, human-readable Markdown.
A project may hold several roadmaps.

```
ge/
  config.md                 project-level: gates, guards, rules, tiers, cadence
  <roadmap>/
    roadmap.md              THE GRAPH: goal, phases, one table row per task
    next.md                 the kickoff brief for the node the runner dispatches next
    ledger.md               append-only: one row per close / block / pause / revision
    calls.md                decisions only the human can make: open and decided
    status.html             regenerated at every close and on /ge-status
    summaries/              what `pause summary <topic>` produces (one file each)
    PAUSE                   present while paused: first line = reason, rest = note
    STOP                    present = hard stop
```

### 2.1 `roadmap.md`

```markdown
# <roadmap name> — <one-line subject>

## Goal
<the human's words, verbatim; the reviewer and the builder read this first>

## Phases
### <phase id> — <title>
<one paragraph; which task ids belong here>

## Tasks
| id | subject | status | deps | spec | gate | commit |
|---|---|---|---|---|---|---|
| P1.1 | ... | open | | docs/plan.md §1 | typecheck, unit | |
| P1.2 | ... | open | P1.1 | docs/plan.md §2 | typecheck, unit, e2e | |

## Notes
<anything the runner should know that is not a task: parked items, not-scheduled items>
```

* `id`: `[A-Za-z0-9._-]+`, unique. `deps`: comma-separated ids, may be empty.
* `status` ∈ `open` · `in progress (<session>)` · `done <hash>` · `blocked: <why>`
  · `skipped: <why>`. **`ready` is derived**: `open` and every dep `done`.
* `spec`: where the task is specified (a doc section, a file, or inline text).
  A node whose subject starts with `READ:` is dispatched to the reader agent.
* `gate`: comma-separated gate NAMES from `config.md`; the verifier checks each.
* Order matters: among ready nodes the runner takes the first in table order.

### 2.2 `config.md`

```markdown
# ge config — <project>

## Gates
| name | command | success | artifact |
|---|---|---|---|
| typecheck | npm run typecheck | `Found 0 errors` | stdout |
| unit | pytest -q | `(?m)^(\d+) passed` | stdout |
| e2e | npm run e2e | `(\d+) passing, 0 failing` | logs/e2e_*.log |

## Guards
| name | command | blocked when |
|---|---|---|
| migrating | docker ps --filter name=db-migrate --format '{{.Names}}' | `db-migrate` |

## Rules
<free text prepended to every brief: the project's standing rules for an unattended session>

## Tiers
| role | model | effort |
|---|---|---|
| task | opus | xhigh |
| reader | fable | high |
| verifier | opus | xhigh |
| reviewer | fable | high |

## Cadence
review every: 3
```

* A gate's `success` is a regex matched against the artifact (a file glob, or
  `stdout` of the command run by the verifier); a capture group `\1` may be
  compared across matches. The verifier never trusts a commit message's numbers.
* A guard's command output matched by `blocked when` means the runner waits: the
  row above holds every dispatch while a migration container is up. `blocked when`
  names the state that BLOCKS, never the healthy one.
* `Rules` replace a project's hand-pasted session preamble; the plugin ships a
  default rules block that a project's section is appended to (never ask; one
  task; finish edits before long gates; keep raw output out of context; close =
  row + ledger + next.md + commit).
* `Tiers` are the defaults the plugin's agents carry in their frontmatter. The
  override mechanism is the `model` argument the runner passes per dispatch when a
  `## Tiers` row names a different model for that role; effort stays the plugin
  agent's. (Shadowing a plugin agent by name from a project's `.claude/agents/`
  was never verified during the build, so it is not the documented route.)

### 2.3 `next.md`

The kickoff for the next node, complete for a session that knows nothing: what to
read, what to build, the pins/tests, the protocol, the gate, how to close. First
line: `# kickoff: <task id>`. The runner refuses a `next.md` whose id is not a
ready node (it then builds a minimal brief from the node's `spec` and says so in
the ledger).

### 2.4 `ledger.md`

```markdown
| date | session | task | event | outcome | commit |
```

Events: `done`, `miss` (verifier), `blocked`, `paused <reason>`, `resumed`,
`revised`, `review`. One row per event, appended only. `resumed` is written only
when a hold was actually lifted: `resume` on a roadmap that is neither paused nor
stopped removes nothing and adds no row, because a row saying a hold was lifted
when none was is a false ledger.

### 2.5 `calls.md`

Two lists: `## Open` and `## Decided`. A task agent that hits a decision only the
human can make writes it under Open (both sides, one line each), marks its node
`blocked: human call`, and the runner moves on. `/ge-revise-roadmap` and
`/ge-resume-roadmap` move items to Decided with the human's word.

### 2.6 `status.html`

One self-contained file (inline CSS/JS, no network): the goal; the graph as an
SVG laid out by dependency depth, nodes coloured by status (open grey, ready
blue, in progress amber, done green, blocked red, skipped hatched), edges as
arrows, phase bands; the ledger's last 20 rows; open calls; the last close's gate
numbers; generated-at; `<meta http-equiv="refresh" content="60">` so an open tab
follows the run.

## 3. `scripts/ge.py` — the only structured reader/writer

Python 3, stdlib only. Every skill calls it instead of reading files whole.

```
ge.py list                                   roadmaps in ./ge
ge.py validate <r>                           unknown deps, cycles, duplicate ids, bad status, next.md id not ready
ge.py ready <r>                              ready nodes in table order (id | subject | gate)
ge.py next <r>                               the first ready node, or "none"
ge.py node <r> <id>                          one node's fields
ge.py brief <r>                              default rules + config Rules + next.md (the dispatch prompt)
ge.py guards <r>                             STOP / PAUSE(reason) / tree dirty / each config guard
ge.py start <r> <id> <session>               status -> in progress (<session>)
ge.py close <r> <id> <hash> "<outcome>" [--session S]   status -> done <hash>; ledger row; render
ge.py block <r> <id> "<why>" [--session S]   status -> blocked: <why>; ledger row; render
ge.py ledger <r> [n]                         last n rows
ge.py event <r> <event> "<outcome>" [--session S]        a non-task ledger row (paused, resumed, revised, review)
ge.py render <r>                             status.html
ge.py gate <r> <name>                        run a gate's command (or read its artifact) and report match/no match with captures
ge.py init <r> --goal "<text>"               a new roadmap folder with an empty table
ge.py add <r> --id --subject --deps --spec --gate [--after id]   a task row
ge.py set <r> <id> --status|--deps|--spec|--gate|--subject
```

Exit codes: 0 ok, 1 not found / invalid, 2 validation failure (with the reasons).
`tests/test_ge.py` (pytest) covers parsing, ready selection, cycle detection,
close/block/ledger, render (the HTML contains every node id), and gate matching.

## 4. Commands (skills)

| skill | behaviour |
|---|---|
| `/ge-build-roadmap <r> [goal \| --from <plan.md>]` | with the human: goal in their words, phases, tasks with deps/spec/gate (uses `superpowers:brainstorming` and `writing-plans` when installed; otherwise its own short flow); writes `config.md` if missing (asks for the gates and guards); `ge.py init/add`; `next.md` for the first ready node; `render`. `--from` converts an existing plan's task list (deps inferred from order within phases, confirmed with the human). |
| `/ge-run-roadmap <r> [once \| dry \| --until <id>]` | the orchestrator loop (§5). |
| `/ge-pause-roadmap <r> human-test \| summary <topic> \| adjust [note]` | writes PAUSE; if the runner is live in this session it acts at the next boundary, else the next `/ge-run-roadmap` sees it. |
| `/ge-resume-roadmap <r>` | removes PAUSE; ledger `resumed`; if the runner is live, continues. |
| `/ge-stop-roadmap <r>` | writes STOP; the runner stops dispatching (a running node finishes its commit). |
| `/ge-status [r]` | `validate`, `render`, opens the HTML (`start`/`xdg-open`/`open`), prints ready / in progress / last 3 ledger rows / open calls. |
| `/ge-revise-roadmap <r>` | with the human: change the goal, add/remove/reorder nodes, deps, specs; `validate`; ledger `revised`; `render`; `next.md` rewritten if the next node changed. |
| `/ge-review-roadmap <r>` | dispatches the reviewer; shows its proposal; applies on the human's word (in the runner's cadence it applies automatically and records `review`). |

## 5. The runner (`/ge-run-roadmap`)

1. `ge.py guards <r>`: STOP → stop. PAUSE → act on its reason (§6) then wait
   for resume (`ScheduleWakeup` 1800 s, noop). A config guard blocked → wait the
   same way, never intervene. Dirty tree → continue; the rules tell the task
   agent how to handle it.
2. `ge.py next <r>` → none: stop ("nothing ready"; blocked nodes listed).
3. `ge.py brief <r>` (refuses an id mismatch, builds a minimal brief, notes it).
   `dry` prints and stops.
4. `ge.py start`; dispatch `ge-task` (or `ge-reader` for `READ:` nodes) with the
   brief verbatim plus the session link line. Wait for the notification.
5. Dispatch `ge-verifier` with the task id, the reported hash and the node's gate
   names only. PASS → `ge.py close`. MISS → re-dispatch `ge-task` once with the
   misses verbatim; a second MISS → `ge.py block`. A report `blocked: human call`
   or `blocked: guard <name>` → the agent already wrote the files; continue / wait.
6. Every N closes (config Cadence): dispatch `ge-reviewer`; apply its moves with
   `ge.py set`; ledger `review`; commit.
7. Loop unless `once` or `--until <id>` reached. Say one line per close (id,
   verdict, hash, the verifier's numbers) and one line at the stop.

Rate limit or credential failure from a subagent → `ScheduleWakeup` 3600 s and
retry the step; three in a row → stop. After a compaction: run step 1 again; the
files say where the run is.

## 6. Pause reasons

* **human-test** — hold. Print what to test: the last three closes' outcomes and
  the nodes' subjects, `status.html`'s path, and the ledger's tail. Wait for
  `/ge-resume-roadmap`.
* **summary `<topic>`** — dispatch `ge-reader` over the ledger, the commits since
  the last summary (`git log`, `--stat`, messages) and the docs the nodes name,
  filtered by the topic; it writes `summaries/<date>-<topic>.md` and the runner
  shows it. Then hold as human-test.
* **adjust** — run `/ge-revise-roadmap` with the human present; on its close,
  hold until resume.

## 7. Agents (plugin `agents/`)

`ge-task` (opus, xhigh, `memory: project`), `ge-reader` (fable, high,
`memory: project`), `ge-verifier` (opus, xhigh), `ge-reviewer` (fable, high,
`memory: project`). Their bodies are the first version's, made project-agnostic:
the gate comes from `config.md`'s names and the verifier runs `ge.py gate` per
name; the close protocol is `ge.py close`/`block` plus `next.md`; the report shape is fixed.

## 8. Hook

`SessionStart`: if `./ge` exists, print one line per roadmap that is `in
progress`, paused, stopped or has open calls, so a fresh session knows a run is
mid-flight. It reads the `ge/` files only — `ge.py`'s `roadmap_state` per
roadmap, never a guard command, so nothing a project put in `config.md` can hang
or write on a session start. A roadmap it cannot read is named on its own line
and the rest still print. Nothing else.

## 9. Packaging and publishing

PromptFu's layout: `.claude-plugin/plugin.json` and `marketplace.json` (name
`graph-engineering`, version 0.1.0, MIT, `Popschlock/graph-engineering`),
`skills/ge-*/SKILL.md`, `agents/ge-*.md`, `hooks/hooks.json` + the hook script,
`scripts/ge.py`, `tests/`, `examples/hello-roadmap/` (a tiny project with a
`ge/` folder whose gates are `python -m pytest`), `README.md` (the idea, install,
the commands, the file formats, the metering note), `docs/` (this spec, the plan).
Install locally while developing: `/plugin marketplace add <path to your checkout>`
then `/plugin install graph-engineering@graph-engineering`; from GitHub once pushed.
Pushing to GitHub is the owner's word, not automatic.

## 10. Dogfood and the first migration

The plugin's own roadmap (`ge/plugin/roadmap.md` in this repo) is written at the
end of the first build slice; from then on the plugin builds its remaining nodes
through `/ge-run-roadmap plugin`. Its last build node is the first migration of an
existing project onto the plugin: `/ge-build-roadmap <r> --from <its roadmap or
plan file>`, its standing preamble and its suite commands into `ge/config.md`, its
bespoke per-project agents retired, and its own `/run-roadmap` skill replaced by
`/ge-run-roadmap <r>`. Task 12 of the plan writes that move out step by step
against a fictional project, so the shape is readable without any one project's
details.

## 11. Non-goals for 0.1

Parallel dispatch of independent ready nodes (designed for: `ready` returns
several; the runner takes one), a headless loop, cloud routines, a web UI beyond
the static HTML, any store other than Markdown files.
