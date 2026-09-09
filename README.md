# Graph Engineering

Graph Engineering (GE) is a Claude Code plugin for long-running, large projects. It keeps a run on your original goal over many days without drifting or getting lost, and it works on a subscription plan: the orchestrating session holds only task statuses, so its context stays small and never needs to auto-compact.

GE turns a stated goal into an ordered list of tasks, and subagents implement and validate them one at a time. Each subagent leaves a completion note, a reviewer reads those notes every few tasks, and the roadmap updates itself as gaps are found. Anything that conflicts with the stated goal is raised as a question for you. You can watch the whole run on a local status page that updates on its own.

![The status page: a roadmap in progress, with one task amber](docs/dashboard.png)

## What it does

You describe your goal in your own words with `/ge-build-roadmap`. The plugin turns that goal into a table of tasks, each with its dependencies, its spec, and the validation check that proves it done. You then start the implementation with `/ge-run-roadmap` and follow the progress in `ge/<name>/status.html` inside your project.

Every few tasks a reviewer reads the whole roadmap and proposes changes if it finds gaps. Any decision that needs a human, because it could move the roadmap away from the stated goal, is written down as a question. That task is parked and the runner moves on to the next one. You can come back whenever you like, answer the questions, and the parked tasks unblock.

If at any point your goal changes or the roadmap needs a different shape, run `/ge-revise-roadmap` and say what has changed. `/ge-pause-roadmap` and `/ge-resume-roadmap` stop and restart a run. Every command takes the roadmap's name, so you can build and run several at once: `/ge-build-roadmap MySuperFeature` creates one, and `/ge-run-roadmap MySuperFeature` runs it.

## Getting Started

Install the plugin from GitHub and restart Claude Code so the commands and the session hook load:

```
claude plugin marketplace add Popschlock/graph-engineering
claude plugin install graph-engineering@graph-engineering
```

The quickest way to see the whole cycle is the example project that ships with the plugin. It is a two-file Python project with a three-task roadmap named `hello`, and its validation check is `python -m pytest -q`, so `pytest` needs to be installed. The plugin lives in your Claude Code plugin cache: `~/.claude/plugins/cache/graph-engineering/graph-engineering/<version>/` on Mac and Linux, and the same path under `%USERPROFILE%` on Windows. Copy the example out of there into a folder of its own and make it a git repository, because the runner reads `git status` before it starts each task:

```
cp -r ~/.claude/plugins/cache/graph-engineering/graph-engineering/*/examples/hello-roadmap ~/hello-roadmap
cd ~/hello-roadmap
git init && git add -A && git commit -m "hello-roadmap"
```

On Windows, `Copy-Item -Recurse` from the same cache path does the same in PowerShell.

Open Claude Code in that folder and run `/ge-status hello`. The status page opens in your browser with three tasks, none of them done. Then run `/ge-run-roadmap hello once`. The first task turns amber on the page while a subagent implements it, then green once a second subagent has verified it. The session prints one line for the round, `dispatched: H1`, and one for the close with the task id, `PASS`, the commit hash and what the check counted. Running `/ge-run-roadmap hello` without `once` works through the remaining tasks and stops when nothing is left to do.

For your own project, run `/ge-build-roadmap MyFeature` with the goal in your words. It reads your project first, asks one round of questions about anything the goal leaves open (including which command proves a task done and what only one task may use at a time), proposes the task table for your approval, and then writes `ge/config.md` and `ge/MyFeature/`. If you already have a plan with `### Task N:` headings or a task table, `/ge-build-roadmap MyFeature --from docs/plan.md` converts it and shows you the dependencies it inferred to confirm. Then `/ge-run-roadmap MyFeature` starts the run.

## Running Tasks Side by Side

The runner starts every task that can start, not one at a time. What decides that is the `locks` column of the task table: each task names what it holds while it runs, such as `editor` for a task that needs the game editor open, `build` for one that runs the build, or a file family that several tasks would edit. Two tasks that share a lock never run at the same time. Two that share none may, up to `max parallel` in `ge/config.md`, which is 3 unless you change it.

A task with an empty `locks` cell holds nothing if it is a `READ:` task, and otherwise holds `tree`, which means the whole working tree, so it runs alone. That keeps an older roadmap behaving as it did, and it is the safe default when you are not sure. The builder fills the column in for new roadmaps, and `/ge-revise-roadmap` changes it with `--locks`.

Tasks that run together work in the same checkout. Each one edits only the files its spec names and commits through `ge.py commit`, which adds only those files and takes a lock so two commits never race. If a verifier finds that two tasks interfered anyway, the failed task is retried on its own, the pair is recorded in the ledger, and the reviewer proposes a lock so it does not happen again.

## When a Task Fails Its Check

A task's close is verified by a second subagent that runs each gate itself and reads the commit, never the first subagent's report. When it finds a miss, the runner records it in the ledger and sends the task back once with the misses spelled out. A second miss blocks the task with the reason, and the runner moves on to whatever else is ready. You will see the blocked task on the status page and can unblock it with `/ge-revise-roadmap` once you have looked.

## Plugin Terms

| Term | Meaning |
|---|---|
| Roadmap | Your goal plus the table of tasks that reaches it, stored in `ge/<name>/roadmap.md`. A project can have several roadmaps, each with its own name. |
| Task | One row of that table. A task is open, ready (every dependency is done), in progress, done, blocked, or skipped. |
| Gate | A validation check a task must pass before it can close: a command and the pattern its output must match, such as a test count. Gates are named in `ge/config.md`, and a gate can carry a floor, the lowest count that still passes, so a suite that shrinks stops reading green. |
| Lock | What a task holds while it runs. Two tasks that share a lock never run at the same time. |
| Verifier | The subagent that checks a finished task from the evidence alone (the tests, the commit, the files). It never reads the implementing subagent's report. |
| Call | A decision only you can make. It is written to `ge/<name>/calls.md`, and the task waits until you answer it. |
| Hold | A pause or a stop. The runner finishes the tasks in progress and dispatches nothing more until you resume. |
| Ledger | The log of the run: one row each time a task is started, closed, blocked or reviewed, in `ge/<name>/ledger.md`. |
| Kickoff | The written instructions a subagent receives for one task, in `ge/<name>/kickoffs/<id>.md`. The subagent that finishes a task writes the kickoffs for the tasks it unblocked. |

## Commands

| Command | What it does |
|---|---|
| `/ge-build-roadmap <name> [goal or --from <file>]` | Plans a roadmap with you from a goal in your words, or converts a plan file you already have, and writes it once you approve. |
| `/ge-run-roadmap <name> [once, dry, --until <id>]` | Runs the roadmap unattended. `once` does one round of tasks, `dry` prints the briefs it would send, and `--until` stops once a named task closes or is blocked. |
| `/ge-status [name]` | Opens the status page, checks the roadmap, and prints what is ready, what is running, the last three ledger rows, and any decisions waiting on you. |
| `/ge-pause-roadmap <name> human-test, summary <topic>, or adjust` | Pauses after the tasks in progress. `human-test` holds so you can try the build, `summary <topic>` writes a summary on that topic to `ge/<name>/summaries/` first, and `adjust` opens the revise flow. |
| `/ge-resume-roadmap <name>` | Settles any open calls with you and lifts the pause. If the runner is still in this session it continues. Otherwise run `/ge-run-roadmap` again. |
| `/ge-stop-roadmap <name>` | Stops after the tasks in progress. |
| `/ge-revise-roadmap <name>` | Changes the goal, adds or drops tasks, reorders them, changes locks, or records a decision. |
| `/ge-review-roadmap <name>` | Asks the reviewer for its proposal now and applies it if you agree. |

When you start a session in a project whose roadmap is running, paused, stopped, or waiting on a decision, one line per such roadmap tells you where it is and ends with the `/ge-status` command to type.

## The Status Page

The page is how you follow a run without reading the ledger. `ge/<name>/status.html` is one self-contained file, so it opens straight from disk and needs no server, and while a run is on it refreshes itself every two seconds. The top of the page shows what is happening right now: each task in progress, how long it has been running, what it holds, and which gate it is on. Below that is the task graph, which you can drag and zoom. Under the graph is the task list, where any row expands to show its kickoff, its gate results, its completion summary once done, or the question it is blocked on. The page is dark by default and has a light theme switch.

## Files in Your Project

```
ge/config.md              your gates, guards, standing rules, how often to review, and max parallel
ge/<name>/roadmap.md      the goal and the task table
ge/<name>/kickoffs/       one kickoff file per task that is ready to start
ge/<name>/ledger.md       the log of the run
ge/<name>/calls.md        decisions waiting on you, and the ones already made
ge/<name>/summaries/      the summaries a pause asked for
ge/<name>/status.html     the status page
ge/<name>/PAUSE, STOP     present while the roadmap is paused or stopped
```

Two more files, `status.js` and `activity.log`, feed the status page and are ignored by git through a `ge/.gitignore` the plugin writes.

## Requirements

Python 3 on PATH as `python`. The session hook also accepts `python3`. The plugin itself uses only the standard library, while the example project and this repository's tests need `pytest`.

The `/ge-run-roadmap` session is an ordinary interactive session, so it runs on your normal Claude Code plan and never starts a headless one. Gate and guard commands from `ge/config.md` run through a shell, so point `ge.py --root` only at projects you trust.

## For Contributors

`docs/design.md` is the contract: every file format, every verb of `scripts/ge.py`, every command step by step, and how the runner decides what to do next. Change it before changing behaviour, and keep `python -m pytest tests/` passing. This repository runs on itself, and its own roadmap is in `ge/plugin/`.

MIT.
