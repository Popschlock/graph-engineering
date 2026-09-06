# Graph Engineering

A Claude Code plugin: **a goal becomes a task graph; one interactive session runs the graph unattended by dispatching a fresh subagent per node with an independent verifier per close; the human pauses it to test, get a summary, or change the goal.** Everything is Markdown files in the project's git under `ge/`. Any project, any gate.

## Why

Long work in Claude Code dies two ways: the session's context fills, and the human pastes a kickoff into every new session. A headless loop removes the pasting but depends on how headless use is metered (one pool with interactive today; a separate-credit proposal is paused, not withdrawn). An interactive session that holds almost nothing and delegates every task to a fresh subagent survives both: its context grows by briefs and short reports, its state lives on disk, and the human can watch or interrupt at any time.

## Install

From a local checkout: `/plugin marketplace add <path to your checkout>` then `/plugin install graph-engineering@graph-engineering`. A directory source is installed by copying the whole checkout, so keep it clean — whatever is sitting in it (a scratch file, a half-finished branch, another project's `ge/`) is copied too. The root `.claudeignore` names the caches and scratch paths a copy has no business carrying; whether the installer honours it is undocumented, so it is a statement of intent and cleaning the checkout is still the real answer.
From GitHub: `/plugin marketplace add Popschlock/graph-engineering` then the same install line.
Requires Python 3 on PATH. The `SessionStart` hook tries `python3` and falls back to `python`, so either name is enough for it; the skills invoke `python`. No other dependency; no network at runtime.
Installing also arms a `SessionStart` hook: it reads the `ge/` files only — never a guard command — and prints one line per roadmap that is in progress, paused, stopped, or has open calls, so a fresh session knows a run is mid-flight. One roadmap it cannot read is named on its own line and the rest still print.

## Commands

| skill | does |
|---|---|
| `/ge-build-roadmap <r> [goal \| --from <plan.md>]` | with you: goal in your words, phases, tasks with deps/spec/gate; writes `ge/config.md` if missing; `--from` converts a plan's task list |
| `/ge-run-roadmap <r> [once \| dry \| --until <id>]` | the loop: guards → next ready node → brief → `ge-task`/`ge-reader` → `ge-verifier` → close; review every N closes |
| `/ge-pause-roadmap <r> human-test \| summary <topic> \| adjust [note]` | writes PAUSE; the runner acts at its next boundary |
| `/ge-resume-roadmap <r>` | decides open calls with you, removes PAUSE/STOP, ledger `resumed` |
| `/ge-stop-roadmap <r>` | writes STOP; a running node finishes its commit |
| `/ge-status [r]` | validate, render, open `status.html`; ready / in progress / last 3 ledger rows / open calls |
| `/ge-revise-roadmap <r>` | change goal, nodes, deps, specs; ledger `revised` |
| `/ge-review-roadmap <r>` | the reviewer's proposal, applied on your word |

`scripts/ge.py` (stdlib Python, run from the project root) is the only STRUCTURED reader/writer of `ge/` files — agents write `next.md`, `calls.md` and `summaries/` by hand, and nothing else by hand. Inside a skill it is `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`; from a shell it is that same file under the plugin's cache directory, or `scripts/ge.py` in a checkout. Its verbs:
`list` · `validate <r>` · `ready <r>` · `next <r>` · `node <r> <id>` · `brief <r>` · `guards <r>` · `start <r> <id> <session>` · `close <r> <id> <hash> "<outcome>" [--session S]` · `block <r> <id> "<why>" [--session S]` · `ledger <r> [n]` · `event <r> <event> "<outcome>" [--session S]` · `render <r>` · `gate <r> <name>` · `init <r> --goal "<text>" [--subject "<text>"]` · `add <r> --id --subject --deps --spec --gate [--after id]` · `set <r> <id> --status|--deps|--spec|--gate|--subject` · `pause <r> <reason> [note]` · `resume <r>` · `stop <r>` · `open <r>` · `calls <r>`. Prefix `--root <dir>` to run against another project. Exit 0 ok, 1 not found or invalid (a `gate` `NO MATCH` is 1), 2 validation failure (`validate`; and `brief` when `next.md` does not name the ready node).

Four of them are worth knowing by their output. `guards` prints `stop:`, `pause:`, one `tree:` line, then one line per configured guard; a `tree: UNKNOWN (...)` or a `guard <name>: ERROR ...` is a check that could not run, and it fails closed — it means wait, exactly as `BLOCKED` does, and the runner never dispatches on one. `gate` prints `MATCH <name>: <captures> (<source>)` — the source being `stdout of <command>` or the artifact file it read — or, on `NO MATCH`, the last 5 lines of the text it searched, so an unattended agent has the evidence without re-running a long command; a `NO MATCH` that is a floor miss or a timeout says which, because neither looks like a regex that simply did not match. Gate commands are killed at 3600 s and guard commands at 30 s, and a killed command reads `NO MATCH` / `ERROR`, never `ok` — a command that never returns would otherwise hold an unattended runner for ever. `open` prints the path first and exits 0 even where no opener is installed — the line `rendered; no opener: ...` goes to stderr and the render still happened. `resume` on a roadmap that was neither paused nor stopped prints `nothing to resume` and adds no ledger row: `resumed` says a hold was lifted, and a row saying so when none was is a false ledger.

## Files in a project

`ge/config.md` — `## Gates` (`name | command | success regex | artifact | floor` — the artifact is `stdout` or a file glob read newest-first; the optional floor is a ratchet on the first capture group, so a suite that SHRANK stops reading green, and a four-column table still parses and means no floors), `## Guards` (`name | command | blocked when`), `## Rules` (free text appended to the plugin's default rules in every brief), `## Tiers`, `## Cadence` (`review every: 3`).
`ge/<r>/roadmap.md` — `## Goal` (your words), `## Phases` (`### <id> — <title>` + paragraph naming task ids), `## Tasks` table `| id | subject | status | deps | spec | gate | commit |`, `## Notes`. Status: `open`, `in progress (<session>)`, `done <hash>`, `blocked: <why>`, `skipped: <why>`; ready = open with every dep done; among ready nodes the first in table order runs. A subject starting `READ:` goes to the reader agent.
`ge/<r>/next.md` — the kickoff for the next node; first line `# kickoff: <id>`. `ledger.md` — `| date | session | task | event | outcome | commit |`, append-only (`done`, `re-closed`, `miss`, `blocked`, `paused <reason>`, `resumed`, `revised`, `review`); a node keeps exactly one `done` row, and a close repeated with a different hash appends `re-closed` naming the hash it replaced. `calls.md` — `## Open` / `## Decided`. `status.html` — self-contained graph page, refreshes every 60 s, with a `STOPPED` or `PAUSED: <reason>` banner under the title while a hold is on. `summaries/` — pause summaries. `PAUSE` / `STOP` — present while paused / stopped.

Close protocol (what a task agent does): work commit → `ge.py close` → `next.md` for `ge.py next`'s node → `git commit -m "ge(<r>): close <id>; next <n>"`. The verifier checks the artifacts through `ge.py gate`, never the maker's report.

## Requirements and caveats

Python 3 on PATH as `python`; `scripts/ge.py` is stdlib-only, and so is the hook. PyYAML is optional and development-only — one test in `tests/` reads the agent files' front matter and skips without it. A project's own gates are its own business: `examples/hello-roadmap/` and this repo's `tests/` need `pytest` (`pip install pytest`), the plugin itself does not.
`ge.py --root <dir>` runs THAT project's `ge/config.md` gate and guard commands through a shell, so point it only at checkouts you trust.
If the `Agent` tool does not know `ge-task`, the harness has namespaced the agents: use `graph-engineering:ge-task`, and the same for `ge-reader`, `ge-verifier` and `ge-reviewer`. `/ge-run-roadmap` says so where it dispatches.
In `/ge-status`, the step that opens `status.html` prints the path and then, where no opener is installed, `rendered; no opener: ...` on stderr. That is not a failure: the page is written, and the path is the line before it.

## Example

`examples/hello-roadmap/` is a two-file Python project with a three-node roadmap whose gate is `python -m pytest -q`, so `pytest` has to be installed for that gate to pass. Copy it, `cd` in, then `git init && git add -A && git commit -m "hello-roadmap"` — the guards read `git status`, and a directory that is not a repo reads `tree: UNKNOWN` while an uncommitted one reads `tree: DIRTY`, which sends the task agent into the cut-off-session rule with no commit to stash against. Then `/ge-status hello` and `/ge-run-roadmap hello once`.

## Metering note

The runner is an interactive session: it shares the interactive pool. It never spawns `claude -p`. If headless metering changes, the same files and script serve a headless loop; that loop is not in 0.1.

## Migrating an existing roadmap

`/ge-build-roadmap <r> --from <your plan or roadmap file>` converts a task table or `### Task N:` headings into `ge/<r>/roadmap.md`; you confirm the inferred dependencies. Put your preamble's standing rules under `## Rules` and your suite commands under `## Gates` in `ge/config.md` (an artifact glob lets the verifier read the file your suite wrote instead of re-running a long suite). Task 12 of `docs/superpowers/plans/2026-09-05-graph-engineering.md` is a worked example of the whole move: the plan's task list converted node by node, the project's standing preamble and suite commands moved into `ge/config.md`, its bespoke runner and agents retired, and its old roadmap file left as a pointer.
