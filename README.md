# Graph Engineering

A Claude Code plugin for work that takes longer than one sitting. You write the goal. It becomes an ordered list of tasks. One Claude session then works through them on its own, a second subagent checks each finished task, and you watch it on a page that updates as it goes.

![The status page: a roadmap in progress, with one task amber](docs/dashboard.png)

## What it does

You describe what you want in your own words. The plugin turns that into a roadmap: a table of tasks, each with what it depends on, where its spec is, and the check that proves it done.

Then you start the runner. It picks the first task whose dependencies are done, hands it to a fresh subagent with a written brief, and waits. When that subagent reports back, a different subagent checks the work against the evidence (the tests, the commit, the files) without reading the first one's report. Pass, and the next task starts. Miss, and the task gets one more try before it is parked for you.

Every few tasks a reviewer reads the whole roadmap and proposes changes. Anything only you can decide is written down as a question, the task is parked, and the runner moves on. You come back when you like, answer the questions, and it continues.

Everything it writes is a Markdown file in your project's `ge/` folder, so the state of the run is in git and readable by hand.

## Try it in five minutes

Install:

```
claude plugin marketplace add Popschlock/graph-engineering
claude plugin install graph-engineering@graph-engineering
```

Restart Claude Code. Then copy the example into a folder of its own and make it a git repo. The runner reads `git status` before every task.

```
cp -r <plugin dir>/examples/hello-roadmap ~/hello-roadmap
cd ~/hello-roadmap
git init && git add -A && git commit -m "hello-roadmap"
```

The example is a two-file Python project with three tasks: a `greet` function, a `shout` function, and a command line. Its check is `python -m pytest -q`, so pytest must be installed.

Now, in Claude Code from that folder:

```
/ge-status hello
```

The status page opens in your browser. Three grey and blue boxes, none done.

```
/ge-run-roadmap hello once
```

The first task turns amber on the page while a subagent works on it, then green when the verifier passes it. The session prints one line: the task id, `PASS`, the commit hash, and what the check counted. Run it again without `once` and it works through the rest and stops when nothing is ready.

To build a roadmap for your own project, run `/ge-build-roadmap <name>` and answer its questions, or give it a plan file you already have with `--from`.

## The words it uses

| Word | Meaning |
|---|---|
| Roadmap | The goal plus the table of tasks, in `ge/<name>/roadmap.md`. One project can have several. |
| Task | One row of that table. It is open, ready (every dependency done), in progress, done, blocked, or skipped. |
| Gate | A check a task must pass to close: a command and the pattern its output must match, such as a test count. Named in `ge/config.md`. |
| Verifier | The subagent that checks a finished task from the evidence alone. It never reads the worker's report. |
| Call | A decision only you can make. Written to `ge/<name>/calls.md`, and the task waits until you answer. |
| Hold | A pause or a stop. The runner finishes the current task and dispatches nothing more until you resume. |
| Ledger | The log: one row per task started, closed, blocked, or reviewed, in `ge/<name>/ledger.md`. |
| Brief | The written instructions a worker subagent gets for one task, kept in `ge/<name>/next.md`. |

## Commands

| Command | What it does |
|---|---|
| `/ge-build-roadmap <name> [goal or --from file]` | Build a roadmap with you, or convert a plan file. |
| `/ge-run-roadmap <name> [once, dry, --until id]` | Run it unattended. `once` does one task. `dry` shows the brief it would send. |
| `/ge-status [name]` | Open the status page and print the ready tasks, the task in progress, and anything waiting on you. |
| `/ge-pause-roadmap <name> human-test, summary <topic>, or adjust` | Pause after the current task, to try the build, get a written summary, or change the goal. |
| `/ge-resume-roadmap <name>` | Answer any open calls, then continue. |
| `/ge-stop-roadmap <name>` | Stop after the current task. |
| `/ge-revise-roadmap <name>` | Change the goal, add or drop tasks, reorder, or record a decision. |
| `/ge-review-roadmap <name>` | Ask the reviewer for its proposal now and apply it if you agree. |

When you start a session in a project with a roadmap in flight, the first line you see says where it is and how many decisions are waiting.

## The status page

`ge/<name>/status.html` is one self-contained file, so it opens from disk and needs no server. It updates itself every two seconds while a run is on. The top says what is happening right now: the task in progress, how long it has run, and which check it is on. Below that is the task graph, which you can drag and zoom. Under it is the task list. Any row expands to its brief, its check results, its summary when done, or the question it is blocked on. Dark by default, with a light switch.

## Files in your project

```
ge/config.md            your gates, guards, standing rules, and how often to review
ge/<name>/roadmap.md    the goal and the task table
ge/<name>/next.md       the brief for the next task
ge/<name>/ledger.md     the log
ge/<name>/calls.md      decisions waiting on you, and the ones already made
ge/<name>/status.html   the page
```

Two more files, `status.js` and `activity.log`, feed the page and are ignored by git.

## Requirements

Python 3 on PATH as `python` or `python3`. The plugin uses the standard library only. The example and this repo's own tests need pytest.

The `/ge-run-roadmap` session is an ordinary interactive session: it uses your normal Claude Code plan, and it never starts a headless one.

Gate and guard commands from `ge/config.md` run through a shell. Point `ge.py --root` only at projects you trust.

## For contributors

`docs/design.md` is the contract: every file format, every verb of `scripts/ge.py`, every command step by step, and how the runner decides. Change it before changing behaviour. `python -m pytest tests/` must pass. This repo runs on itself: its own roadmap is in `ge/plugin/`.

MIT.
