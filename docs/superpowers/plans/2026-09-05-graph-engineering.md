# Graph Engineering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `graph-engineering` Claude Code plugin: `scripts/ge.py` (the only reader/writer of a project's `ge/` files), four agents, eight skills, a SessionStart hook, an example, a README, then dogfood it on this repo and migrate an existing project onto it.

**Architecture:** Every skill and agent is Markdown that calls `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py" <cmd>` from the project root and never reads a `ge/` file whole. `ge.py` is one stdlib-only file in numbered sections (model/parse, graph, writers, config/gate/guards/brief, render, pause/open, CLI); `ge/<r>/roadmap.md`'s `## Tasks` table is the graph, `ledger.md` is append-only, `status.html` is a self-contained SVG page. The runner skill holds only briefs and short reports; fresh subagents do the work.

**Tech Stack:** Python 3.9+ syntax (3.14 on this machine), pytest, Markdown, JSON manifests, git.

**Spec:** `docs/superpowers/specs/2026-09-05-graph-engineering-design.md` (the contract; §2 files, §3 CLI, §4 skills, §5 runner, §6 pause, §7 agents, §8 hook, §9 packaging, §10 dogfood/migration, §11 non-goals).

## Global Constraints

- `scripts/ge.py` is stdlib-only Python 3, ONE file, 3.9+ syntax; the ONLY parser/writer of `ge/` files. Tests run with `python -m pytest tests/ -q` from the repository root and must pass at every commit.
- `ge.py` resolves `./ge` under the current directory (or `--root <dir>` before the subcommand); every skill runs it from the project root. Exit codes: 0 ok, 1 not found/invalid, 2 validation failure (reasons printed).
- Skills are Markdown a fresh session can follow with no other context; agents are project-agnostic (project specifics live in `ge/config.md`).
- Model tiers: `ge-task` and `ge-verifier` `model: opus` `effort: xhigh`; `ge-reader` and `ge-reviewer` `model: fable` `effort: high`; `memory: project` on task/reader/reviewer.
- No network at runtime: `status.html` is self-contained (inline CSS/JS, SVG drawn by `ge.py`).
- Layout mirrors PromptFu: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/ge-*/SKILL.md`, `agents/ge-*.md`, `hooks/hooks.json`, `scripts/`, `tests/`, `examples/`.
- Every commit message ends with the executing session's `Claude-Session: <link>` line. Pushing to GitHub is the owner's word, never automatic.
- Ledger rows: `| date | session | task | event | outcome | commit |`, ISO date, session optional, task `-` for non-task events. Node status values: `open` · `in progress (<session>)` · `done <hash>` · `blocked: <why>` · `skipped: <why>`; `ready` is derived.

## File structure

- `scripts/ge.py` — sections 1–7 below; all logic. `tests/conftest.py` — the fixture builder; `tests/test_ge.py` (parse, graph, writers, pause), `tests/test_render.py`, `tests/test_gate.py`, `tests/test_hook.py`, `tests/test_example.py`.
- `agents/ge-task.md`, `ge-reader.md`, `ge-verifier.md`, `ge-reviewer.md`.
- `skills/ge-run-roadmap/`, `ge-pause-roadmap/`, `ge-resume-roadmap/`, `ge-stop-roadmap/`, `ge-status/`, `ge-build-roadmap/`, `ge-revise-roadmap/`, `ge-review-roadmap/` — one `SKILL.md` each.
- `hooks/hooks.json`, `hooks/session-start.py`. `examples/hello-roadmap/`. `README.md`. `ge/` (this repo's own roadmap, Task 11).

---

### Task 1: ge.py — model, parser, graph queries, read-only CLI

**Files:**
- Create: `scripts/ge.py`
- Create: `tests/conftest.py`
- Test: `tests/test_ge.py`

**Interfaces:**
- Produces: `Node(id, subject, status, deps: list, spec, gate: list, commit, line)`; `Roadmap(name, path, lines, nodes, phases)` where `phases: list[tuple[id, title, text]]`; `ge_root() -> Path`; `rdir(r) -> Path`; `parse_roadmap(path) -> Roadmap`; `load(r) -> Roadmap`; `by_id(rm) -> dict`; `kind(status) -> str` in `open|in progress|done|blocked|skipped|bad`; `ready(rm) -> list[Node]`; `next_node(rm) -> Node|None`; `find_cycle(rm) -> list|None`; `validate(rm, next_md=None) -> list[str]`; `goal(rm) -> str`; `section(lines, heading) -> (start, end)`; `cells(line) -> list[str]`; `split_list(s) -> list[str]`; `list_roadmaps() -> list[tuple]`; `main(argv) -> int`; `dispatch(a) -> int`.
- Test helper: `tests/conftest.py: write_roadmap(root, r, rows, goal, phases) -> Path`, `ROWS3`, fixture `project` (chdir to tmp with `ge/`).

- [ ] **Step 1: Write the fixture builder and the failing tests**

`tests/conftest.py`:
```python
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ge  # noqa: E402

ROWS3 = [("A", "first", "open", "", "docs/plan.md §1", "unit"),
         ("B", "second", "open", "A", "docs/plan.md §2", "unit"),
         ("C", "third", "open", "A, B", "docs/plan.md §3", "unit, e2e")]

def write_roadmap(root, r, rows, goal="make it work", phases=None):
    d = root / "ge" / r; d.mkdir(parents=True, exist_ok=True)
    ph = phases or [("P1", "the only phase", " ".join(row[0] for row in rows))]
    text = f"# {r} — test roadmap\n\n## Goal\n{goal}\n\n## Phases\n"
    text += "".join(f"### {pid} — {title}\n{body}\n\n" for pid, title, body in ph)
    text += "## Tasks\n| id | subject | status | deps | spec | gate | commit |\n|---|---|---|---|---|---|---|\n"
    for row in rows:
        row = list(row) + [""] * (7 - len(row)); text += "| " + " | ".join(row) + " |\n"
    text += "\n## Notes\n"
    (d / "roadmap.md").write_text(text, encoding="utf-8"); return d / "roadmap.md"

@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); (tmp_path / "ge").mkdir(); return tmp_path
```

`tests/test_ge.py`:
```python
import re
import ge
from conftest import write_roadmap, ROWS3

def test_parse_nodes(project):
    rm = ge.parse_roadmap(write_roadmap(project, "demo", ROWS3))
    assert [n.id for n in rm.nodes] == ["A", "B", "C"]
    assert rm.nodes[2].deps == ["A", "B"] and rm.nodes[2].gate == ["unit", "e2e"]
    assert rm.nodes[1].spec == "docs/plan.md §2" and rm.phases[0][0] == "P1"

def test_ready_and_next(project):
    rows = [("A", "first", "done abc1234", "", "s", "unit", "abc1234")] + ROWS3[1:]
    rm = ge.parse_roadmap(write_roadmap(project, "demo", rows))
    assert [n.id for n in ge.ready(rm)] == ["B"] and ge.next_node(rm).id == "B"

def test_validate_finds_problems(project):
    rows = [("A", "a", "open", "Z", "s", ""), ("A", "dup", "opened", "", "s", ""),
            ("B", "b", "open", "C", "s", ""), ("C", "c", "open", "B", "s", "")]
    probs = ge.validate(ge.parse_roadmap(write_roadmap(project, "demo", rows)))
    assert any("unknown dep Z" in p for p in probs) and any("duplicate id A" in p for p in probs)
    assert any("bad status" in p for p in probs) and any(p.startswith("cycle:") for p in probs)

def test_validate_next_md_id(project):
    d = write_roadmap(project, "demo", ROWS3).parent
    (d / "next.md").write_text("# kickoff: C\n\nbody\n", encoding="utf-8")
    rm = ge.parse_roadmap(d / "roadmap.md")
    assert any("C is not a ready node" in p for p in ge.validate(rm, d / "next.md"))
    assert ge.validate(rm) == []

def test_cli_reads(project, capsys):
    write_roadmap(project, "demo", ROWS3)
    assert ge.main(["next", "demo"]) == 0 and capsys.readouterr().out.strip() == "A | first | unit"
    assert ge.main(["node", "demo", "C"]) == 0 and "deps: A, B" in capsys.readouterr().out
    assert ge.main(["validate", "demo"]) == 0
    assert ge.main(["list"]) == 0 and "demo | 0/3 done" in capsys.readouterr().out
    assert ge.main(["next", "nope"]) == 1
```

- [ ] **Step 2: Run to see it fail**

Run: `python -m pytest tests/ -q`
Expected: ImportError / ModuleNotFoundError `ge` (collection error).

- [ ] **Step 3: Write scripts/ge.py sections 1–2 and the CLI skeleton**

```python
#!/usr/bin/env python3
"""ge.py — Graph Engineering. The ONLY reader/writer of a project's ge/ files.
Run from the project root (or with --root <dir>): python ge.py <command> [args].
Exit 0 ok, 1 not found/invalid, 2 validation failure (reasons printed).
Sections: 1 model+parse | 2 graph | 3 writers | 4 config+gate+guards+brief | 5 render | 6 pause+open | 7 cli
"""
import argparse, datetime, glob, os, re, subprocess, sys
from dataclasses import dataclass, field
from pathlib import Path

# ---- 1. model + parse -------------------------------------------------------
ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

@dataclass
class Node:
    id: str; subject: str; status: str; deps: list; spec: str; gate: list; commit: str
    line: int = -1  # index into Roadmap.lines

@dataclass
class Roadmap:
    name: str; path: Path; lines: list; nodes: list; phases: list  # phases: [(id, title, text)]

def ge_root(): return (Path.cwd() / "ge").resolve()
def rdir(r): return ge_root() / r
def split_list(s): return [x.strip() for x in s.split(",") if x.strip()]
def is_sep(line): return re.match(r"^\|?\s*:?-{3,}", line.strip()) is not None

def cells(line):
    s = line.strip()
    if s.startswith("|"): s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"): s = s[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]

def section(lines, heading):
    """(start, end) line indices of the body under a '## ' heading, or (-1, -1)."""
    for i, l in enumerate(lines):
        if l.strip() == heading:
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "): j += 1
            return i + 1, j
    return -1, -1

def wtext(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f: f.write(s)

def parse_roadmap(path):
    path = Path(path)
    if not path.is_file(): raise FileNotFoundError(str(path))
    lines = path.read_text(encoding="utf-8").split("\n"); nodes = []; head = False
    a, b = section(lines, "## Tasks")
    for i in range(max(a, 0), max(b, 0)):
        l = lines[i]
        if not l.lstrip().startswith("|"): continue
        if not head: head = True; continue
        if is_sep(l): continue
        c = cells(l) + [""] * 7
        nodes.append(Node(c[0], c[1], c[2], split_list(c[3]), c[4], split_list(c[5]), c[6], i))
    phases = []
    a, b = section(lines, "## Phases")
    for i in range(max(a, 0), max(b, 0)):
        m = re.match(r"^### (\S+) [—-]+ (.*)$", lines[i])
        if m: phases.append((m.group(1), m.group(2).strip(), ""))
        elif phases and lines[i].strip():
            pid, t, txt = phases[-1]; phases[-1] = (pid, t, (txt + " " + lines[i].strip()).strip())
    return Roadmap(path.parent.name, path, lines, nodes, phases)

def load(r): return parse_roadmap(rdir(r) / "roadmap.md")
def goal(rm):
    a, b = section(rm.lines, "## Goal"); return "\n".join(rm.lines[a:b]).strip() if a >= 0 else ""

# ---- 2. graph ---------------------------------------------------------------
def by_id(rm): return {n.id: n for n in rm.nodes}

def kind(status):
    s = status.strip()
    if s == "open": return "open"
    for k in ("in progress (", "done ", "blocked: ", "skipped: "):
        if s.startswith(k): return k.rstrip(" (:")
    return "bad"

def is_ready(n, ids):
    return kind(n.status) == "open" and all(d in ids and kind(ids[d].status) == "done" for d in n.deps)
def ready(rm): ids = by_id(rm); return [n for n in rm.nodes if is_ready(n, ids)]
def next_node(rm): r = ready(rm); return r[0] if r else None

def find_cycle(rm):
    ids = by_id(rm); state = {}; stack = []
    def dfs(i):
        state[i] = 1; stack.append(i)
        for d in ids[i].deps:
            if d not in ids: continue
            if state.get(d) == 1: return stack[stack.index(d):] + [d]
            if state.get(d) is None:
                c = dfs(d)
                if c: return c
        stack.pop(); state[i] = 2; return None
    for n in rm.nodes:
        if state.get(n.id) is None:
            c = dfs(n.id)
            if c: return c
    return None

def validate(rm, next_md=None):
    probs, seen, ids = [], set(), by_id(rm)
    for n in rm.nodes:
        if not ID_RE.match(n.id): probs.append(f"bad id {n.id!r}")
        if n.id in seen: probs.append(f"duplicate id {n.id}")
        seen.add(n.id)
        if kind(n.status) == "bad": probs.append(f"{n.id}: bad status {n.status!r}")
        for d in n.deps:
            if d not in ids: probs.append(f"{n.id}: unknown dep {d}")
    c = find_cycle(rm)
    if c: probs.append("cycle: " + " -> ".join(c))
    if next_md and Path(next_md).is_file():
        first = Path(next_md).read_text(encoding="utf-8").split("\n", 1)[0]
        m = re.match(r"#\s*kickoff:\s*(\S+)", first); rid = {n.id for n in ready(rm)}
        if not m: probs.append("next.md: first line is not '# kickoff: <id>'")
        elif m.group(1) != "none" and m.group(1) not in rid: probs.append(f"next.md: {m.group(1)} is not a ready node")
    return probs

def list_roadmaps():
    """-> [(name, done, total, state, open_calls)]; state: idle | in progress (ids) | paused: <reason> | stopped"""
    out = []
    if not ge_root().is_dir(): return out
    for d in sorted(ge_root().iterdir()):
        if not (d / "roadmap.md").is_file(): continue
        rm = parse_roadmap(d / "roadmap.md"); ks = [kind(n.status) for n in rm.nodes]
        ip = [n.id for n in rm.nodes if kind(n.status) == "in progress"]
        if (d / "STOP").is_file(): state = "stopped"
        elif (d / "PAUSE").is_file(): state = "paused: " + (d / "PAUSE").read_text(encoding="utf-8").split("\n", 1)[0].strip()
        else: state = f"in progress ({', '.join(ip)})" if ip else "idle"
        out.append((d.name, ks.count("done"), len(ks), state, len(read_calls(d.name)[0])))
    return out

def read_calls(r):
    """-> (open items, decided items) from calls.md"""
    p = rdir(r) / "calls.md"
    if not p.is_file(): return [], []
    lines = p.read_text(encoding="utf-8").split("\n")
    def items(h):
        a, b = section(lines, h)
        return [l.lstrip("*- ").strip() for l in lines[max(a, 0):max(b, 0)] if l.strip().startswith(("*", "-"))]
    return items("## Open"), items("## Decided")

# ---- 7. cli -----------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="ge.py"); ap.add_argument("--root", default=None)
    sp = ap.add_subparsers(dest="cmd", required=True)
    def sub(name, *pos, **opts):
        p = sp.add_parser(name)
        for x in pos: p.add_argument(x)
        for k, v in opts.items(): p.add_argument("--" + k, default=v)
        return p
    sub("list"); sub("validate", "r"); sub("ready", "r"); sub("next", "r"); sub("node", "r", "id")
    a = ap.parse_args(argv)
    if a.root: os.chdir(a.root)
    try: return dispatch(a)
    except FileNotFoundError as e: print(f"not found: {e}", file=sys.stderr); return 1
    except KeyError as e: print(f"no such node: {e}", file=sys.stderr); return 1

def dispatch(a):
    c = a.cmd
    if c == "list":
        for name, done, total, state, calls in list_roadmaps(): print(f"{name} | {done}/{total} done | {state} | {calls} open calls")
        return 0
    rm = load(a.r)
    if c == "validate":
        probs = validate(rm, rdir(a.r) / "next.md")
        for p in probs: print(p)
        if probs: return 2
        print(f"OK {a.r}: {len(rm.nodes)} nodes, {len(ready(rm))} ready"); return 0
    if c == "ready":
        for n in ready(rm): print(f"{n.id} | {n.subject} | {', '.join(n.gate)}")
        return 0
    if c == "next":
        n = next_node(rm)
        if n: print(f"{n.id} | {n.subject} | {', '.join(n.gate)}"); return 0
        print("none")
        for x in rm.nodes:
            if kind(x.status) in ("blocked", "in progress"): print(f"{kind(x.status)}: {x.id} — {x.status}")
        return 0
    if c == "node":
        n = by_id(rm).get(a.id)
        if not n: raise KeyError(a.id)
        for k in ("id", "subject", "status", "deps", "spec", "gate", "commit"):
            v = getattr(n, k); print(f"{k}: {', '.join(v) if isinstance(v, list) else v}")
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to pass**

Run: `python -m pytest tests/ -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/ge.py tests/conftest.py tests/test_ge.py
git commit -m "ge.py: roadmap parser, ready/next/validate, list/node CLI"
```

---

### Task 2: ge.py writers — init, add, set, start, close, block, event, ledger

**Files:**
- Modify: `scripts/ge.py` (add section 3 between sections 2 and 7; add subparsers and dispatch branches)
- Test: `tests/test_ge.py`

**Interfaces:**
- Consumes: Task 1's `load`, `by_id`, `section`, `is_sep`, `wtext`, `split_list`.
- Produces: `fmt_row(n) -> str`; `save(rm)`; `set_field(rm, nid, field_name, value)` (value str; deps/gate split); `add_node(rm, n, after=None)`; `init_roadmap(r, goal, subject="") -> Path`; `today() -> str`; `append_ledger(r, task, event, outcome, commit="", session="") -> str`; `read_ledger(r, n=None) -> list[list[str]]`; `close(r, nid, h, outcome, session="") -> bool` (True if already closed; idempotent); `block(r, nid, why, session="")`; constants `ROADMAP_TMPL`, `LEDGER_HEAD`, `CALLS_TMPL`.

- [ ] **Step 1: Append the failing tests to tests/test_ge.py**

```python
def test_init_add_set(project):
    assert ge.main(["init", "demo", "--goal", "ship it"]) == 0
    assert (project / "ge/demo/ledger.md").read_text(encoding="utf-8").startswith("| date | session | task | event | outcome | commit |")
    assert ge.main(["add", "demo", "--id", "A", "--subject", "first", "--spec", "s1", "--gate", "unit"]) == 0
    assert ge.main(["add", "demo", "--id", "C", "--subject", "third", "--deps", "A", "--spec", "s3", "--gate", "unit"]) == 0
    assert ge.main(["add", "demo", "--id", "B", "--subject", "second", "--deps", "A", "--spec", "s2", "--gate", "unit", "--after", "A"]) == 0
    assert [n.id for n in ge.load("demo").nodes] == ["A", "B", "C"]
    assert ge.main(["set", "demo", "C", "--deps", "A, B", "--subject", "third!"]) == 0
    n = ge.by_id(ge.load("demo"))["C"]
    assert n.deps == ["A", "B"] and n.subject == "third!" and n.spec == "s3" and n.gate == ["unit"]

def test_start_close_block_ledger(project, capsys):
    write_roadmap(project, "demo", ROWS3)
    assert ge.main(["start", "demo", "A", "s1"]) == 0
    assert ge.by_id(ge.load("demo"))["A"].status == "in progress (s1)"
    assert ge.main(["close", "demo", "A", "abc1234", "3 tests green", "--session", "s1"]) == 0
    n = ge.by_id(ge.load("demo"))["A"]
    assert n.status == "done abc1234" and n.commit == "abc1234" and n.spec == "docs/plan.md §1"
    row = ge.read_ledger("demo")[-1]
    assert row[1:] == ["s1", "A", "done", "3 tests green", "abc1234"] and re.match(r"\d{4}-\d{2}-\d{2}$", row[0])
    assert ge.main(["close", "demo", "A", "abc1234", "again"]) == 0 and len(ge.read_ledger("demo")) == 1
    assert ge.main(["block", "demo", "B", "human call"]) == 0
    assert ge.by_id(ge.load("demo"))["B"].status == "blocked: human call"
    assert ge.main(["event", "demo", "review", "no change"]) == 0
    assert [r[3] for r in ge.read_ledger("demo")] == ["done", "blocked", "review"]
    capsys.readouterr(); ge.main(["ledger", "demo", "2"])
    assert capsys.readouterr().out.count("\n") == 2
```

- [ ] **Step 2: Run to see it fail**

Run: `python -m pytest tests/test_ge.py -q`
Expected: 2 failed (`argparse` error: invalid choice 'init' / 'start').

- [ ] **Step 3: Add section 3 and the CLI branches**

Insert after section 2:
```python
# ---- 3. writers -------------------------------------------------------------
ROADMAP_TMPL = "# {r} — {subject}\n\n## Goal\n{goal}\n\n## Phases\n\n## Tasks\n| id | subject | status | deps | spec | gate | commit |\n|---|---|---|---|---|---|---|\n\n## Notes\n"
LEDGER_HEAD = "| date | session | task | event | outcome | commit |\n|---|---|---|---|---|---|\n"
CALLS_TMPL = "# calls — {r}\n\n## Open\n\n## Decided\n"

def esc_cell(s): return (s or "").replace("|", "\\|").replace("\n", " ")
def fmt_row(n):
    return (f"| {esc_cell(n.id)} | {esc_cell(n.subject)} | {esc_cell(n.status)} | {', '.join(n.deps)} | "
            f"{esc_cell(n.spec)} | {', '.join(n.gate)} | {n.commit} |")
def save(rm): wtext(rm.path, "\n".join(rm.lines))

def set_field(rm, nid, field_name, value):
    n = by_id(rm).get(nid)
    if n is None: raise KeyError(nid)
    setattr(n, field_name, split_list(value) if field_name in ("deps", "gate") else value)
    rm.lines[n.line] = fmt_row(n); save(rm)

def add_node(rm, n, after=None):
    a, b = section(rm.lines, "## Tasks")
    if a < 0: raise ValueError("no ## Tasks section")
    if after:
        prev = by_id(rm).get(after)
        if prev is None: raise KeyError(after)
        at = prev.line + 1
    elif rm.nodes: at = max(x.line for x in rm.nodes) + 1
    else: at = next(i for i in range(a, b) if is_sep(rm.lines[i])) + 1
    rm.lines.insert(at, fmt_row(n)); save(rm)

def init_roadmap(r, goal_text, subject=""):
    d = rdir(r)
    if (d / "roadmap.md").exists(): raise FileExistsError(str(d / "roadmap.md"))
    wtext(d / "summaries" / ".gitkeep", "")
    wtext(d / "roadmap.md", ROADMAP_TMPL.format(r=r, subject=subject or goal_text.split("\n")[0][:60], goal=goal_text))
    wtext(d / "ledger.md", LEDGER_HEAD); wtext(d / "calls.md", CALLS_TMPL.format(r=r)); return d


def today(): return datetime.date.today().isoformat()

def append_ledger(r, task, event, outcome, commit="", session=""):
    p = rdir(r) / "ledger.md"
    if not p.is_file(): wtext(p, LEDGER_HEAD)
    row = f"| {today()} | {esc_cell(session)} | {esc_cell(task)} | {esc_cell(event)} | {esc_cell(outcome)} | {esc_cell(commit)} |\n"
    with open(p, "a", encoding="utf-8", newline="\n") as f: f.write(row)
    return row.strip()

def read_ledger(r, n=None):
    p = rdir(r) / "ledger.md"
    rows = ([cells(l) for l in p.read_text(encoding="utf-8").split("\n") if re.match(r"\|\s*\d{4}-\d{2}-\d{2}", l)]
            if p.is_file() else [])
    return rows[-n:] if n else rows

def close(r, nid, h, outcome, session=""):
    """status -> done <hash>, commit column, ledger row. Idempotent: a node already done <hash> with a done row adds nothing."""
    rm = load(r); n = by_id(rm).get(nid)
    if n is None: raise KeyError(nid)
    already = n.status == f"done {h}" and any(x[2] == nid and x[3] == "done" for x in read_ledger(r))
    if not already:
        n.status, n.commit = f"done {h}", h; rm.lines[n.line] = fmt_row(n); save(rm)
        append_ledger(r, nid, "done", outcome, h, session)
    return already

def block(r, nid, why, session=""):
    set_field(load(r), nid, "status", "blocked: " + why); append_ledger(r, nid, "blocked", why, "", session)
```

In `main`, after the Task 1 `sub(...)` line add:
```python
    sub("start", "r", "id", "session"); sub("close", "r", "id", "hash", "outcome", session="")
    sub("block", "r", "id", "why", session=""); sub("event", "r", "event", "outcome", session="")
    sub("ledger", "r").add_argument("n", nargs="?", type=int, default=3)
    sub("init", "r", goal=""); sub("add", "r", id="", subject="", deps="", spec="", gate="", after=None)
    sub("set", "r", "id", status=None, deps=None, spec=None, gate=None, subject=None)
```
In `dispatch`, before `rm = load(a.r)`:
```python
    if c == "init":
        if not a.goal: print("--goal is required", file=sys.stderr); return 1
        print(f"created {init_roadmap(a.r, a.goal)}"); return 0
```
In `dispatch`, before the final `return 1`:
```python
    if c == "start": set_field(rm, a.id, "status", f"in progress ({a.session})"); print(f"{a.id}: in progress ({a.session})"); return 0
    if c == "close":
        already = close(a.r, a.id, a.hash, a.outcome, a.session); print(f"{a.id}: {'already ' if already else ''}done {a.hash}"); return 0
    if c == "block": block(a.r, a.id, a.why, a.session); print(f"{a.id}: blocked: {a.why}"); return 0
    if c == "event": print(append_ledger(a.r, "-", a.event, a.outcome, "", a.session)); return 0
    if c == "ledger":
        for row in read_ledger(a.r, a.n): print("| " + " | ".join(row) + " |")
        return 0
    if c == "add":
        if not a.id or not a.subject: print("--id and --subject are required", file=sys.stderr); return 1
        add_node(rm, Node(a.id, a.subject, "open", split_list(a.deps), a.spec, split_list(a.gate), ""), a.after); print(f"added {a.id}"); return 0
    if c == "set":
        for k in ("status", "deps", "spec", "gate", "subject"):
            v = getattr(a, k)
            if v is not None: set_field(rm, a.id, k, v); print(f"{a.id}.{k} = {v}")
        return 0
```

- [ ] **Step 4: Run to pass**

Run: `python -m pytest tests/ -q` — Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/ge.py tests/test_ge.py
git commit -m "ge.py: init/add/set/start/close/block/event/ledger writers"
```

---

### Task 3: ge.py render — status.html

**Files:**
- Modify: `scripts/ge.py` (add section 5; `render` subparser; `render_to_file(r)` call at the end of `close()` and `block()`)
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `load`, `by_id`, `ready`, `kind`, `goal`, `read_ledger`, `read_calls`, `wtext`, `Config` (Task 4 defines it; this task defines a minimal `Config` dataclass that Task 4 extends — see Step 3).
- Produces: `COLOURS: dict`; `depth(rm) -> dict[id, int]`; `phase_of(rm, nid) -> str`; `layout(rm) -> (pos: dict[id, (col, row)], bands: list[(phase, row0, row1)])`; `node_colour(n, ready_ids) -> str`; `esc(s) -> str`; `render(rm, cfg, ledger_rows, calls_open) -> str`; `render_to_file(r) -> Path`.

- [ ] **Step 1: Write the failing tests**

`tests/test_render.py`:
```python
import ge
from conftest import write_roadmap, ROWS3

def test_render_contains_ids_colours_refresh(project):
    rows = [("A", "first", "done abc1234", "", "s", "unit", "abc1234"), ("B", "second", "open", "A", "s", "unit"),
            ("C", "third", "skipped: later", "A", "s", "")]
    d = write_roadmap(project, "demo", rows).parent
    ge.append_ledger("demo", "A", "done", "unit 12/12", "abc1234", "s1")
    (d / "calls.md").write_text("# calls\n\n## Open\n* pick blue or green\n\n## Decided\n", encoding="utf-8")
    html = ge.render(ge.load("demo"), ge.Config(), ge.read_ledger("demo"), ge.read_calls("demo")[0])
    for nid in ("A", "B", "C"): assert f">{nid}<" in html
    assert "#22c55e" in html and "#3b82f6" in html and "url(#hatch)" in html
    assert '<meta http-equiv="refresh" content="60">' in html
    assert "pick blue or green" in html and "unit 12/12" in html and "marker-end" in html

def test_layout_depth_and_bands(project):
    pos, bands = ge.layout(ge.parse_roadmap(write_roadmap(project, "demo", ROWS3)))
    assert pos["A"][0] == 0 and pos["B"][0] == 1 and pos["C"][0] == 2 and bands == [("P1", 0, 1)]

def test_close_writes_status_html(project):
    write_roadmap(project, "demo", ROWS3); ge.main(["close", "demo", "A", "abc1234", "ok"])
    assert (project / "ge/demo/status.html").exists()
```

- [ ] **Step 2: Run to see it fail**

Run: `python -m pytest tests/test_render.py -q` — Expected: 3 failed (`AttributeError: module 'ge' has no attribute 'render'`/`Config`/`layout`).

- [ ] **Step 3: Add section 5 (and a Config stub that Task 4 completes)**

Insert before section 7:
```python
# ---- 4. config (completed in Task 4) ----------------------------------------
@dataclass
class Config:
    gates: dict = field(default_factory=dict); guards: dict = field(default_factory=dict)
    rules: str = ""; tiers: dict = field(default_factory=dict); review_every: int = 3

# ---- 5. render --------------------------------------------------------------
COLOURS = {"open": "#9aa0a6", "ready": "#3b82f6", "in progress": "#f59e0b", "done": "#22c55e",
           "blocked": "#ef4444", "skipped": "url(#hatch)"}

def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def depth(rm):
    """longest path from a root, per node id"""
    ids, memo = by_id(rm), {}
    def d(i, seen=()):
        if i in memo: return memo[i]
        if i in seen: return 0
        ds = [d(x, seen + (i,)) + 1 for x in ids[i].deps if x in ids]
        memo[i] = max(ds) if ds else 0; return memo[i]
    return {n.id: d(n.id) for n in rm.nodes}

def phase_of(rm, nid):
    for pid, _t, text in rm.phases:
        if re.search(r"(?<![\w.])" + re.escape(nid) + r"(?![\w.])", text): return pid
    for pid, _t, _x in rm.phases:
        if nid == pid or nid.startswith(pid + ".") or nid.startswith(pid + "-"): return pid
    return ""

def layout(rm):
    """columns by depth; rows by table order inside a phase band; bands in phase order, unphased nodes last"""
    dep = depth(rm); order = [p[0] for p in rm.phases] + [""]; pos, bands, row = {}, [], 0
    for p in order:
        group = [n for n in rm.nodes if phase_of(rm, n.id) == p]
        if not group: continue
        cols = {}
        for n in group:
            c = dep[n.id]; pos[n.id] = (c, row + len(cols.get(c, []))); cols.setdefault(c, []).append(n.id)
        h = max(len(v) for v in cols.values()); bands.append((p, row, row + h)); row += h
    return pos, bands

def node_colour(n, ready_ids):
    return COLOURS["ready"] if n.id in ready_ids else COLOURS.get(kind(n.status), COLOURS["open"])

def render(rm, cfg, ledger_rows, calls_open):
    pos, bands = layout(rm); rid = {n.id for n in ready(rm)}
    CW, RH, W, H, X0, Y0 = 210, 46, 180, 34, 20, 30
    ncols = max([c for c, _r in pos.values()], default=0) + 1; nrows = max([r for _c, r in pos.values()], default=0) + 1
    width, height = X0 * 2 + ncols * CW, Y0 * 2 + nrows * RH
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="system-ui,sans-serif" font-size="11">',
           '<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#555"/></marker>',
           '<pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<rect width="6" height="6" fill="#ddd"/><line x1="0" y1="0" x2="0" y2="6" stroke="#777" stroke-width="2"/></pattern></defs>']
    for i, (p, r0, r1) in enumerate(bands):
        fill = "#f3f4f6" if i % 2 else "#fafafa"
        svg.append(f'<rect x="4" y="{Y0 + r0 * RH - 8}" width="{width - 8}" height="{(r1 - r0) * RH}" fill="{fill}" stroke="#e5e7eb"/>')
        svg.append(f'<text x="8" y="{Y0 + r0 * RH + 4}" fill="#666">{esc(p or "other")}</text>')
    def xy(nid): c, r = pos[nid]; return X0 + c * CW, Y0 + r * RH
    for n in rm.nodes:
        x, y = xy(n.id)
        for d in n.deps:
            if d in pos:
                dx, dy = xy(d)
                svg.append(f'<line x1="{dx + W}" y1="{dy + H / 2}" x2="{x}" y2="{y + H / 2}" stroke="#555" marker-end="url(#arr)"/>')
    for n in rm.nodes:
        x, y = xy(n.id); c = node_colour(n, rid); tc = "#000" if c in ("url(#hatch)", "#9aa0a6") else "#fff"
        svg.append(f'<g><title>{esc(n.id)}: {esc(n.subject)} [{esc(n.status)}]</title><rect x="{x}" y="{y}" width="{W}" height="{H}" rx="4" fill="{c}"/>'
                   f'<text x="{x + 6}" y="{y + 14}" fill="{tc}" font-weight="bold">{esc(n.id)}</text>'
                   f'<text x="{x + 6}" y="{y + 27}" fill="{tc}">{esc(n.subject[:28])}</text></g>')
    svg.append("</svg>")
    last = next((x for x in reversed(ledger_rows) if len(x) > 4 and x[3] == "done"), None)
    last_txt = esc(" | ".join(last)) if last else "none yet"
    tail = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in x) + "</tr>" for x in ledger_rows[-20:])
    calls = "".join(f"<li>{esc(c)}</li>" for c in calls_open) or "<li>none</li>"
    gates = ", ".join(f"{g.name}: {esc(g.command)}" for g in cfg.gates.values()) or "none in ge/config.md"
    legend = "".join(f'<span style="background:{v};color:{"#000" if k in ("open", "skipped") else "#fff"}">{k}</span>'
                     for k, v in COLOURS.items() if k != "skipped") + '<span style="background:#ddd;color:#000">skipped</span>'
    now = datetime.datetime.now().isoformat(timespec="seconds"); name = esc(rm.name); g = esc(goal(rm)); graph = "".join(svg)
    return ('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="60">'
            f'<title>ge: {name}</title><style>body{{font-family:system-ui,sans-serif;margin:20px;color:#222}}'
            'table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #ddd;padding:3px 6px;text-align:left}'
            '.legend span{display:inline-block;padding:2px 8px;margin-right:6px;border-radius:3px}pre{white-space:pre-wrap}</style></head><body>'
            f'<h1>{name}</h1><p>generated {now} — refreshes every 60 s — gates: {gates}</p><h2>Goal</h2><pre>{g}</pre>'
            f'<p class="legend">{legend}</p>{graph}<h2>Last close</h2><p>{last_txt}</p><h2>Open calls</h2><ul>{calls}</ul>'
            '<h2>Ledger (last 20)</h2><table><tr><th>date</th><th>session</th><th>task</th><th>event</th><th>outcome</th><th>commit</th></tr>'
            f'{tail}</table></body></html>')

def render_to_file(r):
    rm = load(r); html = render(rm, parse_config(ge_root() / "config.md"), read_ledger(r), read_calls(r)[0])
    wtext(rdir(r) / "status.html", html); return rdir(r) / "status.html"
```
Also add, in section 4 for now (Task 4 replaces it with the real parser): `def parse_config(path): return Config()`. Append `render_to_file(r)` as the last statement of `close()` (before `return already`) and of `block()`. In `main`: `sub("render", "r")`. In `dispatch` before `return 1`: `if c == "render": print(render_to_file(a.r)); return 0`.

- [ ] **Step 4: Run to pass**

Run: `python -m pytest tests/ -q` — Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/ge.py tests/test_render.py
git commit -m "ge.py: render status.html (layered SVG, phase bands, ledger tail, open calls)"
```

---

### Task 4: ge.py config, gate, guards, brief

**Files:**
- Modify: `scripts/ge.py` (replace the section-4 stub with the full section; add `gate`, `guards`, `brief` subparsers and branches)
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `Config` (Task 3), `load`, `next_node`, `section`, `cells`, `is_sep`, `rdir`, `ge_root`.
- Produces: `Gate(name, command, success, artifact)`; `Guard(name, command, blocked_when)`; `parse_config(path) -> Config`; `table(lines, heading) -> list[list[str]]`; `unquote(c) -> str`; `run_cmd(cmd) -> str` (stdout+stderr); `newest(pattern) -> str|None`; `run_gate(g) -> (matched: bool, captures: list, source: str)`; `pause_state(r) -> (reason, note)|None`; `guards(r, cfg) -> list[str]`; `DEFAULT_RULES: str`; `minimal_brief(rm, n) -> str`; `brief(r) -> (text, code)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_gate.py`:
```python
import ge
from conftest import write_roadmap, ROWS3

CONFIG = """# ge config — demo

## Gates
| name | command | success | artifact |
|---|---|---|---|
| echo | python -c "print('total=3 passed=3 failed=0')" | `total=(\\d+) passed=\\1 failed=0` | stdout |
| log | python -c "print('never run')" | `GREEN \\((\\d+) checked\\)` | logs/e2e_*.log |

## Guards
| name | command | blocked when |
|---|---|---|
| busy | python -c "print('RUNNING')" | `RUNNING` |

## Rules
Project rule one.

## Tiers
| role | model | effort |
|---|---|---|
| task | opus | xhigh |

## Cadence
review every: 2
"""

def setup(project):
    (project / "ge/config.md").write_text(CONFIG, encoding="utf-8"); return write_roadmap(project, "demo", ROWS3).parent

def test_parse_config(project):
    setup(project); cfg = ge.parse_config(project / "ge/config.md")
    assert cfg.gates["echo"].success == r"total=(\d+) passed=\1 failed=0" and cfg.gates["log"].artifact == "logs/e2e_*.log"
    assert cfg.guards["busy"].blocked_when == "RUNNING" and cfg.rules == "Project rule one."
    assert cfg.tiers["task"] == ("opus", "xhigh") and cfg.review_every == 2

def test_gate_stdout_and_artifact(project, capsys):
    setup(project)
    assert ge.main(["gate", "demo", "echo"]) == 0 and capsys.readouterr().out.startswith("MATCH echo: 3")
    assert ge.main(["gate", "demo", "log"]) == 1
    (project / "logs").mkdir(); (project / "logs/e2e_1.log").write_text("SUITE GREEN (42 checked)\n", encoding="utf-8")
    assert ge.main(["gate", "demo", "log"]) == 0 and "MATCH log: 42" in capsys.readouterr().out
    assert ge.main(["gate", "demo", "nope"]) == 1

def test_guards(project, capsys):
    d = setup(project)
    (d / "PAUSE").write_text("human-test\ntry the menu\n", encoding="utf-8"); (d / "STOP").write_text("", encoding="utf-8")
    assert ge.main(["guards", "demo"]) == 0
    out = capsys.readouterr().out
    assert "stop: PRESENT" in out and "pause: human-test | try the menu" in out and "guard busy: BLOCKED" in out and "tree: clean" in out

def test_brief_mismatch_and_match(project, capsys):
    d = setup(project); (d / "next.md").write_text("# kickoff: B\n\nwrong node\n", encoding="utf-8")
    assert ge.main(["brief", "demo"]) == 2
    out = capsys.readouterr().out
    assert "# kickoff: A" in out and "docs/plan.md §1" in out and "Project rule one." in out and "Never ask a question" in out
    (d / "next.md").write_text("# kickoff: A\n\nthe real kickoff\n", encoding="utf-8")
    assert ge.main(["brief", "demo"]) == 0 and "the real kickoff" in capsys.readouterr().out
```

- [ ] **Step 2: Run to see it fail**

Run: `python -m pytest tests/test_gate.py -q` — Expected: 4 failed (`AttributeError`/argparse invalid choice).

- [ ] **Step 3: Replace section 4 with the full one**

```python
# ---- 4. config + gate + guards + brief ----------------------------------------
@dataclass
class Gate: name: str; command: str; success: str; artifact: str
@dataclass
class Guard: name: str; command: str; blocked_when: str
@dataclass
class Config:
    gates: dict = field(default_factory=dict); guards: dict = field(default_factory=dict)
    rules: str = ""; tiers: dict = field(default_factory=dict); review_every: int = 3

def unquote(c): return c[1:-1] if len(c) >= 2 and c[0] == c[-1] == "`" else c

def table(lines, heading):
    a, b = section(lines, heading); rows, head = [], False
    for i in range(max(a, 0), max(b, 0)):
        l = lines[i]
        if not l.lstrip().startswith("|"): continue
        if not head: head = True; continue
        if is_sep(l): continue
        rows.append([unquote(c) for c in cells(l)])
    return rows

def parse_config(path):
    cfg = Config(); path = Path(path)
    if not path.is_file(): return cfg
    lines = path.read_text(encoding="utf-8").split("\n")
    for r in table(lines, "## Gates"):
        r += [""] * 4; cfg.gates[r[0]] = Gate(r[0], r[1], r[2], r[3] or "stdout")
    for r in table(lines, "## Guards"):
        r += [""] * 3; cfg.guards[r[0]] = Guard(r[0], r[1], r[2])
    for r in table(lines, "## Tiers"):
        r += [""] * 3; cfg.tiers[r[0]] = (r[1], r[2])
    a, b = section(lines, "## Rules"); cfg.rules = "\n".join(lines[a:b]).strip() if a >= 0 else ""
    a, b = section(lines, "## Cadence")
    for l in lines[max(a, 0):max(b, 0)]:
        m = re.match(r"review every:\s*(\d+)", l.strip())
        if m: cfg.review_every = int(m.group(1))
    return cfg

def run_cmd(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return (p.stdout or "") + (p.stderr or "")

def newest(pattern):
    hits = glob.glob(pattern, recursive=True)
    return max(hits, key=os.path.getmtime) if hits else None

def run_gate(g):
    """artifact 'stdout' -> run the command; else read the newest file matching the glob. -> (matched, captures, source)"""
    if g.artifact in ("", "stdout"): text, src = run_cmd(g.command), "stdout of " + g.command
    else:
        f = newest(g.artifact)
        if not f: return False, [], "no artifact matches " + g.artifact
        text, src = Path(f).read_text(encoding="utf-8", errors="replace"), f
    m = re.search(g.success, text)
    return m is not None, (list(m.groups()) if m else []), src

def pause_state(r):
    p = rdir(r) / "PAUSE"
    if not p.is_file(): return None
    t = p.read_text(encoding="utf-8").split("\n", 1)
    return t[0].strip(), (t[1].strip() if len(t) > 1 else "")

def guards(r, cfg):
    out = ["stop: PRESENT" if (rdir(r) / "STOP").is_file() else "stop: absent"]
    ps = pause_state(r); out.append(f"pause: {ps[0]} | {ps[1]}" if ps else "pause: absent")
    st = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    out.append("tree: DIRTY" if st.returncode == 0 and st.stdout.strip() else "tree: clean")
    for g in cfg.guards.values():
        out.append(f"guard {g.name}: {'BLOCKED' if re.search(g.blocked_when, run_cmd(g.command)) else 'ok'}")
    return out

DEFAULT_RULES = """# Graph Engineering — the unattended rules (prepended to every brief)

You are an unattended session of the project at `{root}`, working roadmap `{r}` (`ge/{r}/roadmap.md`). Nobody is watching. Every read or write of the roadmap, the ledger and the status page goes through `ge.py` = `python "{ge}"`, run from `{root}`; you never edit `roadmap.md`, `ledger.md` or `status.html` by hand (you do write `next.md`, `calls.md` and `summaries/`). Read `ge/{r}/roadmap.md` whole before the kickoff below, then the kickoff, then work. These rules bind over anything the kickoff says that assumes a person is present:

1. **Never ask a question.** A decision only the human can make goes under `## Open` in `ge/{r}/calls.md` (both sides, one line each); then `ge.py block {r} {id} "human call"`, write `next.md` for `ge.py next {r}`'s node (rule 7d), commit, and report `blocked: human call`.
2. **ONE task**: `{id}`, which the kickoff below is. Its row already reads `in progress`; leave it. Nothing from other rows.
3. **Finish every edit, THEN run the long gates.** A gate is a name in `ge/config.md`; run each gate the row names with `ge.py gate {r} <name>` on the closing tree and keep the captures it prints for the commit message and your report. `NO MATCH` is not a close: fix and re-run, or block.
4. **Guards.** First run `ge.py guards {r}`. `stop: PRESENT` means stop now and report `stopped`. A `guard <name>: BLOCKED` at any point means stop after writing `next.md` and report `blocked: guard <name>`; never clear a guard yourself.
5. **Keep raw output out of your context**: `| tail`, `| grep`, background long commands and read their result line; reads that span many files go to a subagent whose short report you keep. Write-ups go to files, not to your report.
6. **A dirty tree at start** (`git status --porcelain`): if the only change is `ge/{r}/roadmap.md`, it is the runner's mark on your row; continue. Anything else is a cut-off session: finish what is finishable under its kickoff or `git stash` it with `ge.py event {r} revised "stashed: <what>"`, then take the task.
7. **Close, in this order:** (a) memory updated where a durable fact or a trap was found; (b) ONE work commit whose message quotes each gate's captures and ends with the session link you were given; (c) `ge.py close {r} {id} <hash> "<one-line outcome with the gate captures>" --session <your session id>`; (d) `ge.py next {r}`; write `ge/{r}/next.md` for that node: first line `# kickoff: <its id>` (or `# kickoff: none`), then a COMPLETE kickoff for a session that knows nothing — what to read, what to build, the pins or tests, its gate names, how to close; (e) `git add ge && git commit -m "ge({r}): close {id}; next <its id>"`.
8. **Your report**, under 150 words, exactly: `commit: <work hash>`; one line per gate `gate <name>: <captures>`; `closed: {id}` or `blocked: <why>` or `stopped`; `next: <id>`. Audit each line against a tool result first; an unverified claim is written as unverified.
"""

def minimal_brief(rm, n):
    return (f"# kickoff: {n.id}\n\nTask {n.id}: {n.subject}\n\nRead the spec first: {n.spec}\nBuild exactly what it states for {n.id}, nothing of other tasks.\n"
            f"Deps already done: {', '.join(n.deps) or 'none'}. Gate names (ge/config.md): {', '.join(n.gate) or 'none'}.\n"
            f"This brief was built from the roadmap row because next.md did not name {n.id}; write next.md properly at your close (rule 7d).\n")

def brief(r):
    """-> (text, code): 0 = next.md matched the ready node; 2 = mismatch or missing, minimal brief built; 1 = nothing ready"""
    rm = load(r); n = next_node(rm)
    if n is None: return "nothing ready", 1
    nx = rdir(r) / "next.md"; body, code = "", 2
    if nx.is_file():
        body = nx.read_text(encoding="utf-8"); m = re.match(r"#\s*kickoff:\s*(\S+)", body.split("\n", 1)[0])
        if m and m.group(1) == n.id: code = 0
    if code: body = minimal_brief(rm, n)
    cfg = parse_config(ge_root() / "config.md")
    rules = DEFAULT_RULES.format(root=os.getcwd(), r=r, ge=Path(__file__).resolve(), id=n.id)
    return rules + ("\n## Project rules\n" + cfg.rules + "\n" if cfg.rules else "") + "\n---\n\n" + body, code
```
In `main`: `sub("gate", "r", "name"); sub("guards", "r"); sub("brief", "r")`. In `dispatch` before `return 1`:
```python
    if c == "gate":
        g = parse_config(ge_root() / "config.md").gates.get(a.name)
        if not g: print(f"no gate named {a.name} in ge/config.md", file=sys.stderr); return 1
        ok, caps, src = run_gate(g)
        print(f"{'MATCH' if ok else 'NO MATCH'} {a.name}: {' '.join(caps)} ({src})".replace(":  (", ": ("))
        return 0 if ok else 1
    if c == "guards":
        for l in guards(a.r, parse_config(ge_root() / "config.md")): print(l)
        return 0
    if c == "brief":
        text, code = brief(a.r); print(text)
        if code == 2: print("brief: next.md does not name the ready node; minimal brief built from the row", file=sys.stderr)
        return code
```

- [ ] **Step 4: Run to pass**

Run: `python -m pytest tests/ -q` — Expected: `14 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/ge.py tests/test_gate.py
git commit -m "ge.py: config parser, gate runner, guards, brief with the default rules"
```

---

### Task 5: The four agents

**Files:**
- Create: `agents/ge-task.md`, `agents/ge-reader.md`, `agents/ge-verifier.md`, `agents/ge-reviewer.md`
- Test: `tests/test_ge.py` (frontmatter check)

**Interfaces:**
- Consumes: the prompt shapes Task 6's runner sends (brief + two lines; the verifier's five lines; the reviewer's one line).
- Produces: report shapes the runner parses: task `commit:/gate <name>:/closed:|blocked:|stopped/next:`; verifier `VERDICT: PASS|MISS`; reviewer `REVIEW:/next:/moves:/reruns:/calls:`.

- [ ] **Step 1: Write the failing test (append to tests/test_ge.py)**

```python
def test_agent_frontmatter():
    from pathlib import Path
    want = {"ge-task": ("opus", "xhigh", True), "ge-reader": ("fable", "high", True),
            "ge-verifier": ("opus", "xhigh", False), "ge-reviewer": ("fable", "high", True)}
    for name, (model, effort, mem) in want.items():
        head = (Path(__file__).resolve().parents[1] / "agents" / f"{name}.md").read_text(encoding="utf-8").split("---")[1]
        assert f"name: {name}" in head and f"model: {model}" in head and f"effort: {effort}" in head
        assert ("memory: project" in head) == mem
```

- [ ] **Step 2: Run to see it fail** — `python -m pytest tests/test_ge.py::test_agent_frontmatter -q` — Expected: FAIL `FileNotFoundError`.

- [ ] **Step 3: Write the four agents**

`agents/ge-task.md`:
```markdown
---
name: ge-task
description: Implements ONE Graph Engineering roadmap node from its brief, unattended - reads what the brief names, edits, runs the node's gates through ge.py, commits, closes the node with ge.py close and writes next.md. Dispatched by /ge-run-roadmap; never by a user directly.
model: opus
effort: xhigh
memory: project
color: blue
---

You are one unattended implementation session. The human is not present. Your prompt is a brief: the Graph Engineering rules block (it names the project root, the roadmap, your node id and the exact `python ".../ge.py"` command), the project's own rules from `ge/config.md`, and the kickoff for one node. Follow the rules block first and exactly; the project's CLAUDE.md and memory apply too.

What matters most when nobody is watching:
- Do ONE node. Read what the kickoff names before editing. Finish every edit, then run each gate the row names with `ge.py gate <r> <name>`; every gate must print `MATCH` on the closing tree.
- Keep raw output out of your context (`| tail`, `| grep`, background the long ones).
- Never ask a question: a human-only decision goes under `## Open` in `ge/<r>/calls.md` and the node is blocked with `ge.py block <r> <id> "human call"`.
- Close exactly as rule 7 says: memory, the work commit ending with the session link, `ge.py close`, `next.md` for `ge.py next`'s node, the close commit.

Final report, under 150 words, this shape and nothing else:

    commit: <work hash>
    gate <name>: <the captures ge.py printed>      (one line per gate; "gates: none owed" if the row names none)
    closed: <id> | blocked: human call | blocked: guard <name> | stopped
    next: <id or none>

Audit each line against a tool result from this session before writing it; an unverified claim is written as unverified.
```

`agents/ge-reader.md`:
```markdown
---
name: ge-reader
description: Reads before anything is built - a READ: node of a Graph Engineering roadmap (settle a mechanism, write a findings file or a plan section) or a pause summary over the ledger and recent commits. Dispatched by /ge-run-roadmap; returns findings with file:line, never edits code.
model: fable
effort: high
memory: project
color: purple
---

You are a reading session; the human is not present. Your prompt is either (a) a brief for a `READ:` node — the rules block, the project's rules and a kickoff naming what to read and which decision the read must settle — or (b) a summary request naming a roadmap `<r>`, a topic and the `ge.py` command.

For a READ: node: read the project's own notes before its sources (a finding may already be written); follow every pointer (a field naming another file is not read until you opened it); test claims for structure before describing them; prefer the exact source over the derived one; name what you could NOT resolve and why. You may write docs (a findings file, a plan section) when the kickoff asks, never code. Close per rule 7 (`ge.py close`, `next.md`, the two commits); the work commit holds the docs.

For a summary: read `ge.py ledger <r> 50`, `git log --stat` since the newest file in `ge/<r>/summaries/` (or the first ledger row) — messages and file lists, not diffs — and the docs the closed nodes' `spec` cells name, filtered by the topic. Write `ge/<r>/summaries/<YYYY-MM-DD>-<topic>.md` (what changed, what proves it, what is open; under 600 words) and commit it `ge(<r>): summary <topic>`.

Report under 300 words: the findings with file:line pointers and the decision they settle (or the summary's path and its first paragraph), then one line `closed: <id>` | `summary: <path>` | `blocked: <why>`. Audit each claim against a tool result first.
```

`agents/ge-verifier.md`:
```markdown
---
name: ge-verifier
description: Maker-never-grader for a Graph Engineering node just closed by ge-task. Given only the roadmap, the node id, the work commit hash, the gate names and the ge.py path, it checks the artifacts (ge.py gate per name, git log and status, next.md's first line, the ledger row) and reports PASS or named misses. Never reads the maker's report; never edits.
model: opus
effort: xhigh
color: green
---

You verify ONE closed node. Your prompt gives `roadmap: <r>`, `task: <id>`, `commit: <hash>`, `gates: <names>` and `ge: python "<path>/ge.py"`, and nothing the implementer wrote about its own work. From the project root, judge the artifacts:

1. `git status --porcelain` is empty. `git log -3 --format="%H %s"` contains `<hash>`, and HEAD's subject starts with `ge(<r>): close <id>`. `git show --stat <hash>` touches what the node's spec names (`ge.py node <r> <id>`, then read that spec section) and nothing outside it without a reason in the message.
2. Each gate name: `ge.py gate <r> <name>` prints `MATCH` (exit 0) on this tree. `NO MATCH`, a missing artifact, or a gate you cannot run is a MISS naming it. Never take a number from the commit message.
3. `ge.py node <r> <id>` reads `status: done <hash>`; `ge.py ledger <r> 5` has a `done` row for `<id>` with that hash; `ge/<r>/next.md`'s first line is `# kickoff: <n>` where `<n>` is what `ge.py next <r>` prints (`none` allowed), and the kickoff under it names what to read, what to build, the pins and the gate.
4. A gate whose first capture is a count below the same gate's capture in the previous `done` row of `ge.py ledger <r> 10` is a MISS ("count went down").

Read only what these checks need; keep raw logs out of your context. Report in this exact shape, under 200 words:

    VERDICT: PASS | MISS
    task: <id>  commit: <hash>
    gates: <name>=<captures> ... | none owed
    misses: <one per line, naming the artifact that shows it; "none" on PASS>
```

`agents/ge-reviewer.md`:
```markdown
---
name: ge-reviewer
description: The cadence review of a Graph Engineering roadmap - reads the goal, the graph, the ledger's recent rows and the commits they name, and proposes dependency moves, re-runs and new human calls with reasons (or "no change"). Dispatched by /ge-run-roadmap or /ge-review-roadmap; proposes, never applies.
model: fable
effort: high
memory: project
color: yellow
---

You review roadmap `<r>` of the project in the current directory; the human is not present. Their priorities are `## Goal` in `ge/<r>/roadmap.md` (their words) and `## Decided` in `ge/<r>/calls.md`, in that order. Your prompt names `<r>` and the `ge.py` command.

Read: `ge/<r>/roadmap.md` whole; `ge.py ledger <r> 6`; `git show --stat <hash>` for the last three `done` rows (messages and file lists, not diffs); the first line of `ge/<r>/next.md`; `ge/<r>/calls.md`. Then answer, under 400 words:

1. Is `ge.py next <r>`'s node still the right next node, given what the last closes found (a blocked node, a READ: node that changed a later node's shape, a decided call)? If not, the new order expressed as dependency edits, one reason each. Never reorder against the goal's words; never schedule anything `## Notes` calls parked or not scheduled.
2. Any node whose gate at close was below the rule (a captured count that went down; an outcome naming a fallback): name it for a re-run.
3. Anything under `## Open` that a ledger row or a commit shows was decided; any new call a close raised.

Output shape, nothing else:

    REVIEW: no change | reorder
    next: <id>
    moves: none | <id> deps=<comma-separated ids> — <reason>    (one per line)
    reruns: none | <ids>
    calls: none | <one per line>

The runner applies moves with `ge.py set <r> <id> --deps` and reruns with `--status open`; you do not edit.
```

- [ ] **Step 4: Run to pass** — `python -m pytest tests/ -q` — Expected: `15 passed`.

- [ ] **Step 5: Commit**

```bash
git add agents/ tests/test_ge.py
git commit -m "agents: ge-task, ge-reader, ge-verifier, ge-reviewer"
```

---

### Task 6: skills/ge-run-roadmap

**Files:**
- Create: `skills/ge-run-roadmap/SKILL.md`

**Interfaces:**
- Consumes: `ge.py guards|next|brief|start|close|block|event|set|validate|render|ledger|node`; the agent report shapes of Task 5.

- [ ] **Step 1: Write the skill**

```markdown
---
name: ge-run-roadmap
description: Run a Graph Engineering roadmap unattended from ONE interactive session - dispatch each ready node's brief to a fresh ge-task (or ge-reader) subagent, verify each close with a fresh ge-verifier, review on the config cadence with ge-reviewer, honour PAUSE and STOP, and loop until a stop. Use when the user types /ge-run-roadmap <r> [once|dry|--until <id>].
---

# /ge-run-roadmap <r> [once | dry | --until <id>]

You are the orchestrator. You hold almost nothing: one brief and two short reports per node. Every read is one of the `GE` commands below, run from the project root (the directory holding `ge/`); you never open a log, a suite's output, a source file or a whole doc into your context. The work happens in fresh subagents whose definitions carry their model and effort (`ge-task` opus xhigh, `ge-reader` fable high, `ge-verifier` opus xhigh, `ge-reviewer` fable high). If the project's `ge/config.md` `## Tiers` names a different model for a role, pass it as the Agent call's `model`.

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`. `<session>` = the 8 characters after `session_` in this session's Claude-Session link. Arguments: none = loop until a stop; `once` = one node then stop; `dry` = print the brief you would dispatch and stop; `--until <id>` = stop after `<id>` closes. `<r>` must appear in `GE list`; otherwise say so and stop.

## The loop

1. **Guards** — `GE guards <r>`.
   - `stop: PRESENT` → say "stopped by ge/<r>/STOP" and stop.
   - `pause: <reason> | <note>` → act on the reason (below), then `ScheduleWakeup` 1800 s (`noop: true`, reason "paused"); on wake run step 1 again.
   - `guard <name>: BLOCKED` → say which, `ScheduleWakeup` 1800 s (`noop: true`, reason "guard <name>"), re-check on wake. Never run or close anything to clear it.
   - `tree: DIRTY` → continue; the rules tell the task agent what to do.
2. **Next** — `GE next <r>`. `none` → say "nothing ready" plus the `blocked:` / `in progress:` lines it printed, and stop. Keep the id, subject and gate names.
3. **Brief** — `GE brief <r>`; keep stdout and the exit code. Exit 2 → the last close mis-wrote `next.md` and `GE` printed a minimal brief from the row: use it and, unless `dry`, record `GE event <r> revised "next.md did not name <id>; minimal brief from its spec"`. `dry` → print the brief and stop.
4. **Dispatch** — `GE start <r> <id> <session>`. Then the `Agent` tool, `subagent_type` `ge-task`, or `ge-reader` when the subject starts with `READ:`. The prompt is the brief verbatim plus two lines: `Your session link for the commit footer: <this session's Claude-Session URL>; your session id is <session>.` and `ge.py is: python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`. Wait for the notification; do nothing meanwhile (no polling, no reading).
5. **Verify** — `Agent` `ge-verifier`; the prompt is exactly five lines: `roadmap: <r>`, `task: <id>`, `commit: <the hash from the task's report>`, `gates: <the gate names from step 2>`, `ge: python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`. Never forward the task agent's report. Wait.
   - `VERDICT: PASS` → `GE close <r> <id> <hash> "<the verifier's gates line>" --session <session>` (a no-op re-render when the agent already closed it). Count the close; say the close line.
   - `VERDICT: MISS` → re-dispatch `ge-task` ONCE with the brief plus `The verifier found:`, the misses verbatim, and `Fix exactly those, re-run the gates they name, change nothing else, and close again.` Verify again. A second MISS → `GE block <r> <id> "<the first miss line>"`, then `git add ge && git commit -m "ge(<r>): block <id> after two verifier misses"`; continue at step 1.
   - The task's report says `blocked: human call` → its files are written; continue at step 1. `blocked: guard <name>` → step 1's wait. `stopped` → stop.
6. **Review** — after every N closes (`review every` in `ge/config.md`; 3 when absent): `Agent` `ge-reviewer` with `review roadmap <r> now; ge: python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`. Apply its answer: each `moves` line `X deps=<list>` → `GE set <r> X --deps "<list>"`; each rerun id → `GE set <r> <id> --status open`; each `calls` line → append `* <line>` under `## Open` in `ge/<r>/calls.md`. Then `GE validate <r>` (exit 2 → undo each move with `GE set` back to its previous deps from `GE node`, and say so); `GE event <r> review "<the REVIEW line>; next <its next id>"`; `GE render <r>`; `git add ge && git commit -m "ge(<r>): review — <no change|reorder>"`.
7. **Loop** to step 1 unless `once`, or `--until <id>` just closed.

## Pause reasons (step 1)

- `human-test` — print what to test: `GE ledger <r> 3`, each row's node subject from `GE node <r> <id>`, the path `ge/<r>/status.html`, and "resume with /ge-resume-roadmap <r>". Then wait.
- `summary <topic>` — if `ge/<r>/summaries/` has no `<today>-<topic>.md`: `Agent` `ge-reader` with `Write the pause summary for roadmap <r>, topic: <topic>; ge: python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`; show its path and first paragraph. Then hold as `human-test`.
- `adjust` — the human is present (they paused): run the `ge-revise-roadmap` skill for `<r>`; when it closes, hold as `human-test` until resume.

## Rate limits and compaction

A subagent that returns a limit or credential failure (its report says so, or the notification is an error) → `ScheduleWakeup` 3600 s (`noop: true`, reason "usage window") and retry the same step on wake; three consecutive → stop and say so. After a compaction: run step 1 again; the files say where the run is. Do not try to remember what the reports said.

## What you say

One line per close: `<id> PASS <hash> — <the verifier's gates line>`. One line at a stop and why. Nothing else; the files carry the rest. The human can Ctrl-C at any time and `/ge-run-roadmap <r>` later.
```

- [ ] **Step 2: Check it against the spec** — read §5 and §6 of the spec side by side; every numbered step in §5 has a numbered step here; `dry`, `once`, `--until`, both wakeups, the three pause reasons are present.

- [ ] **Step 3: Commit**

```bash
git add skills/ge-run-roadmap/SKILL.md
git commit -m "skills: ge-run-roadmap (the orchestrator loop)"
```

---

### Task 7: pause/resume/stop/open/calls in ge.py + the four small skills

**Files:**
- Modify: `scripts/ge.py` (add section 6; subparsers `pause`, `resume`, `stop`, `open`, `calls`)
- Create: `skills/ge-pause-roadmap/SKILL.md`, `skills/ge-resume-roadmap/SKILL.md`, `skills/ge-stop-roadmap/SKILL.md`, `skills/ge-status/SKILL.md`
- Test: `tests/test_ge.py`

**Interfaces:**
- Produces: `pause(r, reason, note="")`; `resume(r)` (removes PAUSE and STOP, ledger `resumed`); `stop(r)`; `open_command(path, platform=sys.platform) -> list[str]`; CLI `calls <r>` (open items, one per line).

- [ ] **Step 1: Append the failing tests to tests/test_ge.py**

```python
def test_pause_resume_stop(project):
    write_roadmap(project, "demo", ROWS3); d = project / "ge/demo"
    assert ge.main(["pause", "demo", "summary lighting", "what changed in lighting"]) == 0
    assert (d / "PAUSE").read_text(encoding="utf-8") == "summary lighting\nwhat changed in lighting\n"
    assert ge.pause_state("demo") == ("summary lighting", "what changed in lighting")
    assert ge.read_ledger("demo")[-1][3] == "paused summary lighting"
    assert ge.main(["stop", "demo"]) == 0 and (d / "STOP").exists()
    assert ge.main(["resume", "demo"]) == 0 and not (d / "PAUSE").exists() and not (d / "STOP").exists()
    assert ge.read_ledger("demo")[-1][3] == "resumed"

def test_open_command_and_calls(project, capsys):
    assert ge.open_command("x.html", "win32") == ["cmd", "/c", "start", "", "x.html"]
    assert ge.open_command("x.html", "darwin") == ["open", "x.html"]
    assert ge.open_command("x.html", "linux") == ["xdg-open", "x.html"]
    d = write_roadmap(project, "demo", ROWS3).parent
    (d / "calls.md").write_text("# calls\n\n## Open\n* blue or green\n\n## Decided\n* red\n", encoding="utf-8")
    assert ge.main(["calls", "demo"]) == 0 and capsys.readouterr().out.strip() == "blue or green"
```

- [ ] **Step 2: Run to see it fail** — `python -m pytest tests/test_ge.py -q` — Expected: 2 failed (argparse invalid choice 'pause').

- [ ] **Step 3: Add section 6 and the branches**

```python
# ---- 6. pause + open --------------------------------------------------------
def pause(r, reason, note=""):
    wtext(rdir(r) / "PAUSE", reason + ("\n" + note if note else "") + "\n"); append_ledger(r, "-", "paused " + reason, note)

def resume(r):
    for f in ("PAUSE", "STOP"):
        p = rdir(r) / f
        if p.exists(): p.unlink()
    append_ledger(r, "-", "resumed", "")

def stop(r): wtext(rdir(r) / "STOP", today() + "\n")

def open_command(path, platform=sys.platform):
    if platform.startswith("win"): return ["cmd", "/c", "start", "", str(path)]
    if platform == "darwin": return ["open", str(path)]
    return ["xdg-open", str(path)]
```
In `main`: `sub("pause", "r", "reason").add_argument("note", nargs="?", default=""); sub("resume", "r"); sub("stop", "r"); sub("open", "r"); sub("calls", "r")`. In `dispatch` before `return 1`:
```python
    if c == "pause": pause(a.r, a.reason, a.note); print(f"paused {a.r}: {a.reason}"); return 0
    if c == "resume": resume(a.r); print(f"resumed {a.r}"); return 0
    if c == "stop": stop(a.r); print(f"STOP written for {a.r}"); return 0
    if c == "open": p = render_to_file(a.r); subprocess.Popen(open_command(p)); print(p); return 0
    if c == "calls":
        for x in read_calls(a.r)[0]: print(x)
        return 0
```

- [ ] **Step 4: Run to pass** — `python -m pytest tests/ -q` — Expected: `17 passed`.

- [ ] **Step 5: Write the four skills**

`skills/ge-pause-roadmap/SKILL.md`:
```markdown
---
name: ge-pause-roadmap
description: Pause a Graph Engineering roadmap at its next boundary to human-test, get a summary on a topic, or adjust the goal. Use when the user types /ge-pause-roadmap <r> human-test | summary <topic> | adjust [note].
---

# /ge-pause-roadmap <r> <reason> [note]

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. The reason is `human-test`, `summary <topic>` or `adjust`; anything else: name the three and stop.
2. `GE pause <r> "<reason>" "<note>"` — writes `ge/<r>/PAUSE` (first line the reason, the rest the note) and a `paused <reason>` ledger row.
3. `git add ge/<r> && git commit -m "ge(<r>): pause <reason>"`.
4. Say one line: if `/ge-run-roadmap <r>` is live in this session it acts at its next boundary (step 1 of its loop); otherwise the next `/ge-run-roadmap <r>` sees the PAUSE first. A node already dispatched finishes its commit.
```

`skills/ge-resume-roadmap/SKILL.md`:
```markdown
---
name: ge-resume-roadmap
description: Resume a paused or stopped Graph Engineering roadmap - decide open calls with the human, remove PAUSE and STOP, ledger resumed. Use when the user types /ge-resume-roadmap <r>.
---

# /ge-resume-roadmap <r>

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. `GE guards <r>`: `pause: absent` and `stop: absent` → say "not paused" and stop.
2. `GE calls <r>`: for each open call ask the human for their word (one line each); move each decided one in `ge/<r>/calls.md` from `## Open` to `## Decided` as `* <YYYY-MM-DD> <the call> — <their word>`; a call they leave open stays. A decided call that unblocks a node (`blocked: human call`) → `GE set <r> <id> --status open`.
3. `GE resume <r>` (removes PAUSE and STOP; ledger `resumed`); `GE validate <r>`; `GE render <r>`.
4. `git add ge/<r> && git commit -m "ge(<r>): resume"`.
5. If the runner is live in this session, continue its loop at step 1; otherwise say "resumed; run /ge-run-roadmap <r>".
```

`skills/ge-stop-roadmap/SKILL.md`:
```markdown
---
name: ge-stop-roadmap
description: Hard-stop a Graph Engineering roadmap - writes STOP so the runner stops dispatching at its next boundary. Use when the user types /ge-stop-roadmap <r>.
---

# /ge-stop-roadmap <r>

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. `GE stop <r>` — writes `ge/<r>/STOP`.
2. `git add ge/<r> && git commit -m "ge(<r>): stop"`.
3. Say one line: the runner stops dispatching at its next boundary; a running node finishes its commit; `/ge-resume-roadmap <r>` clears the STOP.
```

`skills/ge-status/SKILL.md`:
```markdown
---
name: ge-status
description: Show where a Graph Engineering roadmap is - validate, render and open status.html, then print ready nodes, in-progress nodes, the last 3 ledger rows and open calls. Use when the user types /ge-status [r].
---

# /ge-status [r]

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. `GE list`. Print it. No `<r>` given: use the roadmap whose state is `in progress` or `paused`, else the only one, else ask which.
2. `GE validate <r>` — print its lines (exit 2 is reported, not fatal).
3. `GE open <r>` — renders `ge/<r>/status.html` and opens it (Windows `start`, macOS `open`, Linux `xdg-open`).
4. Print, each under its own one-word heading: `GE ready <r>`; the `in progress (...)` ids from the list line; `GE ledger <r> 3`; `GE calls <r>`.
5. Nothing else; do not open the roadmap file.
```

- [ ] **Step 6: Commit**

```bash
git add scripts/ge.py tests/test_ge.py skills/ge-pause-roadmap skills/ge-resume-roadmap skills/ge-stop-roadmap skills/ge-status
git commit -m "ge.py pause/resume/stop/open/calls; skills: pause, resume, stop, status"
```

---

### Task 8: skills ge-build-roadmap, ge-revise-roadmap, ge-review-roadmap

**Files:**
- Create: `skills/ge-build-roadmap/SKILL.md`, `skills/ge-revise-roadmap/SKILL.md`, `skills/ge-review-roadmap/SKILL.md`

- [ ] **Step 1: Write ge-build-roadmap**

```markdown
---
name: ge-build-roadmap
description: Build a Graph Engineering roadmap with the human - the goal in their words, phases, tasks with deps, spec and gate - or convert an existing plan with --from. Creates ge/config.md when missing. Use when the user types /ge-build-roadmap <r> [goal | --from <plan.md>].
---

# /ge-build-roadmap <r> [<goal> | --from <plan.md>]

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root. The human is present: this is the skill that asks.

## 1. config.md (only when `ge/config.md` is missing)

Ask, in one message: (a) "Which command proves a task done, and which line of its output (or which file) shows it?" — one gate row each: a short name, the command, the success regex (a capture group for the count; `\1` may repeat a capture), the artifact (`stdout`, or a file glob read newest-first); (b) "Is there anything that must not be running when a task starts?" — one guard row each: name, command, the regex that means blocked; (c) standing rules for an unattended session (may be none). Write:

    # ge config — <project>

    ## Gates
    | name | command | success | artifact |
    |---|---|---|---|
    | <name> | <command> | `<regex>` | stdout |

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

Without `--from`: the goal is the argument, or the answer to "What should be true when this roadmap is done — in your words?". Keep it verbatim. If the `superpowers:brainstorming` skill is installed, run it on the goal to settle scope before phases; otherwise ask three questions: what exists now, what must not change, what proves it done.

## 3. Phases and tasks

With the human, name 1–6 phases (`<id> — <title>` and one paragraph naming the task ids in it) and, per task: id (`[A-Za-z0-9._-]+`, unique), subject (a read-first task's subject starts with `READ:`), deps (ids that must be done first), spec (a doc section, a file, or the text itself), gate names from config.md. Show the table; get a yes.

`--from <plan.md>`: read the plan. Every `### Task N:` heading (or a task-table row, or a numbered task heading) becomes a task: id `T<N>` or the plan's own id; subject the heading text; spec `<plan.md> Task N`; gate = the config gates whose command appears in the task's run steps, else the first gate; deps = the previous task in the same phase (phases = the plan's `##` sections that hold tasks; a plan without such sections is one chain). Show the table with the inferred deps; the human confirms or edits each dep line; only then write.

## 4. Write

`GE init <r> --goal "<goal>"`; put the phases under `## Phases` in `ge/<r>/roadmap.md` (`### <id> — <title>` + paragraph); `GE add <r> --id <id> --subject "<subject>" --deps "<ids>" --spec "<spec>" --gate "<names>"` per task in order; `GE validate <r>` until `OK`. Write `ge/<r>/next.md` for `GE next <r>`'s node: first line `# kickoff: <id>`, then a complete kickoff for a session that knows nothing (what to read, what to build, the pins or tests, its gate names, how to close). `GE render <r>`. `git add ge && git commit -m "ge(<r>): roadmap — <the goal's first words>"`. Say the next node and `/ge-run-roadmap <r> dry` to see its brief.
```

- [ ] **Step 2: Write ge-revise-roadmap**

```markdown
---
name: ge-revise-roadmap
description: Change a Graph Engineering roadmap with the human - the goal, nodes added or skipped, dependencies, specs, gates, decided calls - validated and recorded. Use when the user types /ge-revise-roadmap <r>, or from a pause with reason adjust.
---

# /ge-revise-roadmap <r>

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root. The human is present; this is the one time a whole roadmap is read into a session.

1. `GE validate <r>`; `GE ready <r>`; `GE calls <r>`; read `ge/<r>/roadmap.md` and show `## Goal` and the `## Tasks` table.
2. Ask what changes and apply each: the goal → edit `## Goal` verbatim; a new node → `GE add <r> --id .. --subject .. --deps .. --spec .. --gate .. [--after <id>]`; a node to drop → `GE set <r> <id> --status "skipped: <why>"` (rows are never deleted); order → `GE set <r> <id> --deps "<ids>"`; text → `GE set <r> <id> --spec|--gate|--subject`; a decided call → move it to `## Decided` in `calls.md` as `* <YYYY-MM-DD> <call> — <their word>` and `GE set <r> <id> --status open` for the node it blocked.
3. `GE validate <r>` until `OK`. `GE event <r> revised "<one line: what changed>"`. If `GE next <r>`'s id differs from `next.md`'s first line, rewrite `ge/<r>/next.md` for the new node (first line `# kickoff: <id>`, complete kickoff). `GE render <r>`. `git add ge && git commit -m "ge(<r>): revise — <what changed>"`.
```

- [ ] **Step 3: Write ge-review-roadmap**

```markdown
---
name: ge-review-roadmap
description: Dispatch the Graph Engineering reviewer on a roadmap now, show its proposal, and apply it on the human's word. Use when the user types /ge-review-roadmap <r>.
---

# /ge-review-roadmap <r>

`GE` = `python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`, from the project root.

1. `Agent` with `subagent_type` `ge-reviewer` and the prompt `review roadmap <r> now; ge: python "${CLAUDE_PLUGIN_ROOT}/scripts/ge.py"`. Wait.
2. Show the proposal verbatim and ask "apply?".
3. Yes → each `moves` line `X deps=<list>` → `GE set <r> X --deps "<list>"`; each rerun id → `GE set <r> <id> --status open`; each `calls` line → `* <line>` under `## Open` in `ge/<r>/calls.md`; `GE validate <r>` (exit 2 → undo the moves and say so); `GE event <r> review "<the REVIEW line>; next <id>"`; `GE render <r>`; `git add ge && git commit -m "ge(<r>): review — <no change|reorder>"`.
   No → `GE event <r> review "declined: <the REVIEW line>"` and change nothing else.
```

- [ ] **Step 4: Commit**

```bash
git add skills/ge-build-roadmap skills/ge-revise-roadmap skills/ge-review-roadmap
git commit -m "skills: ge-build-roadmap, ge-revise-roadmap, ge-review-roadmap"
```

---

### Task 9: The SessionStart hook

**Files:**
- Create: `hooks/hooks.json`, `hooks/session-start.py`
- Test: `tests/test_hook.py`

**Interfaces:**
- Consumes: `ge.list_roadmaps()` (Task 1). Reads the hook's stdin JSON for `cwd`; no guard command is run (they may be slow).

- [ ] **Step 1: Write the failing tests**

```python
import json, subprocess, sys, time
from pathlib import Path
from conftest import write_roadmap, ROWS3
HOOK = Path(__file__).resolve().parents[1] / "hooks" / "session-start.py"

def test_hook_prints_mid_flight_roadmaps(project):
    (write_roadmap(project, "demo", ROWS3).parent / "PAUSE").write_text("human-test\n", encoding="utf-8")
    t = time.perf_counter()
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"cwd": str(project)}), capture_output=True, text=True, cwd=project)
    assert p.returncode == 0 and time.perf_counter() - t < 1.5  # spec: under 1 s; margin for a cold interpreter
    assert "ge: roadmap demo is paused: human-test, 0/3 done, 0 open call(s)" in p.stdout

def test_hook_silent_without_ge(tmp_path):
    p = subprocess.run([sys.executable, str(HOOK)], input="{}", capture_output=True, text=True, cwd=tmp_path)
    assert p.returncode == 0 and p.stdout == ""
```

- [ ] **Step 2: Run to see it fail** — `python -m pytest tests/test_hook.py -q` — Expected: 2 failed (`FileNotFoundError`, or returncode 2).

- [ ] **Step 3: Write the hook files**

`hooks/hooks.json`:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/session-start.py"],
            "timeout": 5,
            "statusMessage": "Graph Engineering: roadmaps in flight"
          }
        ]
      }
    ]
  }
}
```

`hooks/session-start.py`:
```python
#!/usr/bin/env python3
"""SessionStart hook: one line per roadmap under ./ge that is in progress, paused, stopped or has open calls.
Exit 0 always; under 1 s (reads files only; no guard command is run)."""
import json, os, sys
from pathlib import Path

def main():
    try:
        raw = sys.stdin.read()
        cwd = json.loads(raw).get("cwd") if raw.strip() else None
    except Exception:
        cwd = None
    root = Path(cwd or os.getcwd())
    if not (root / "ge").is_dir(): return 0
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts")); os.chdir(root)
    try:
        import ge
        for name, done, total, state, calls in ge.list_roadmaps():
            if state == "idle" and calls == 0: continue
            print(f"ge: roadmap {name} is {state}, {done}/{total} done, {calls} open call(s) — /ge-status {name}")
    except Exception as e:
        print(f"ge: could not read ./ge ({e})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to pass** — `python -m pytest tests/ -q` — Expected: `19 passed`.

- [ ] **Step 5: Commit**

```bash
git add hooks/ tests/test_hook.py
git commit -m "hooks: SessionStart prints roadmaps in flight"
```

---

### Task 10: examples/hello-roadmap, README, smoke test

**Files:**
- Create: `examples/hello-roadmap/hello.py`, `test_hello.py`, `ge/config.md`, `ge/hello/roadmap.md`, `ge/hello/next.md`, `ge/hello/ledger.md`, `ge/hello/calls.md`, `ge/hello/summaries/.gitkeep`
- Create: `README.md`
- Test: `tests/test_example.py`

- [ ] **Step 1: Write the failing smoke test**

```python
import shutil
from pathlib import Path
import ge
EX = Path(__file__).resolve().parents[1] / "examples" / "hello-roadmap"

def test_example_validates_renders_and_gates(tmp_path, monkeypatch, capsys):
    shutil.copytree(EX, tmp_path / "hello-roadmap"); monkeypatch.chdir(tmp_path / "hello-roadmap")
    assert ge.main(["validate", "hello"]) == 0
    assert ge.main(["ready", "hello"]) == 0 and capsys.readouterr().out.splitlines()[-1].startswith("H1 |")
    assert ge.main(["render", "hello"]) == 0 and (tmp_path / "hello-roadmap/ge/hello/status.html").exists()
    assert ge.main(["gate", "hello", "pytest"]) == 0 and "MATCH pytest: 1" in capsys.readouterr().out
```

- [ ] **Step 2: Run to see it fail** — `python -m pytest tests/test_example.py -q` — Expected: FAIL `FileNotFoundError` (copytree).

- [ ] **Step 3: Write the example**

`examples/hello-roadmap/hello.py`:
```python
def greet(name: str) -> str:
    return f"hello, {name}"
```
`examples/hello-roadmap/test_hello.py`:
```python
from hello import greet

def test_greet():
    assert greet("graph") == "hello, graph"
```
`examples/hello-roadmap/ge/config.md`:
```markdown
# ge config — hello-roadmap

## Gates
| name | command | success | artifact |
|---|---|---|---|
| pytest | python -m pytest -q | `(\d+) passed` | stdout |

## Guards
| name | command | blocked when |
|---|---|---|

## Rules
Python 3, stdlib only. One module `hello.py`; its tests in `test_hello.py`; `python -m pytest -q` from this directory.

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
`examples/hello-roadmap/ge/hello/roadmap.md`:
```markdown
# hello — a greeter that shouts and runs from the command line

## Goal
A `hello.py` that greets, can shout, and runs from the command line, each step proven by pytest.

## Phases
### H — the greeter
H1, H2 and H3, in that order.

## Tasks
| id | subject | status | deps | spec | gate | commit |
|---|---|---|---|---|---|---|
| H1 | `greet(name)` returns `hello, <name>` | open | | inline: one function, one test | pytest | |
| H2 | `shout(name)` returns `greet(name).upper() + "!"` | open | H1 | inline: one function, one test | pytest | |
| H3 | `python hello.py <name>` prints `shout(name)` | open | H2 | inline: a `__main__` block, one subprocess test | pytest | |

## Notes
H1 is already written, so a first `/ge-run-roadmap hello once` closes it fast and shows the whole cycle.
```
`examples/hello-roadmap/ge/hello/next.md`:
```markdown
# kickoff: H1

Read `hello.py` and `test_hello.py`; `greet` exists. Run `python -m pytest -q` (1 passed), then close H1 as the rules say: the work commit (even if only this file moves, commit the ge/ state), `ge.py close hello H1 <hash> "pytest 1 passed"`, next.md for H2, the close commit. H2's kickoff to write: add `shout(name)` returning `greet(name).upper() + "!"` and `test_shout` asserting `shout("graph") == "HELLO, GRAPH!"`; gate `pytest`.
```
`ge/hello/ledger.md`: the two `LEDGER_HEAD` lines. `ge/hello/calls.md`: `# calls — hello`, `## Open`, `## Decided`. `ge/hello/summaries/.gitkeep`: empty.

- [ ] **Step 4: Write README.md**

```markdown
# Graph Engineering

A Claude Code plugin: **a goal becomes a task graph; one interactive session runs the graph unattended by dispatching a fresh subagent per node with an independent verifier per close; the human pauses it to test, get a summary, or change the goal.** Everything is Markdown files in the project's git under `ge/`. Any project, any gate.

## Why

Long work in Claude Code dies two ways: the session's context fills, and the human pastes a kickoff into every new session. A headless loop removes the pasting but depends on how headless use is metered (one pool with interactive today; a separate-credit proposal is paused, not withdrawn). An interactive session that holds almost nothing and delegates every task to a fresh subagent survives both: its context grows by briefs and short reports, its state lives on disk, and the human can watch or interrupt at any time.

## Install

From a local checkout: `/plugin marketplace add <path to your checkout>` then `/plugin install graph-engineering@graph-engineering`.
From GitHub (once published): `/plugin marketplace add Popschlock/graph-engineering` then the same install line.
Requires Python 3 on PATH (`python`). No other dependency; no network at runtime.

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

`scripts/ge.py` (stdlib Python, run from the project root) is the only thing that reads or writes `ge/` files:
`list` · `validate <r>` · `ready <r>` · `next <r>` · `node <r> <id>` · `brief <r>` · `guards <r>` · `start <r> <id> <session>` · `close <r> <id> <hash> "<outcome>" [--session S]` · `block <r> <id> "<why>" [--session S]` · `ledger <r> [n]` · `event <r> <event> "<outcome>" [--session S]` · `render <r>` · `gate <r> <name>` · `init <r> --goal "<text>"` · `add <r> --id --subject --deps --spec --gate [--after id]` · `set <r> <id> --status|--deps|--spec|--gate|--subject` · `pause <r> <reason> [note]` · `resume <r>` · `stop <r>` · `open <r>` · `calls <r>`. Prefix `--root <dir>` to run against another project. Exit 0 ok, 1 not found, 2 validation failure.

## Files in a project

`ge/config.md` — `## Gates` (`name | command | success regex | artifact` — `stdout`, or a file glob read newest-first), `## Guards` (`name | command | blocked when`), `## Rules` (free text appended to the plugin's default rules in every brief), `## Tiers`, `## Cadence` (`review every: 3`).
`ge/<r>/roadmap.md` — `## Goal` (your words), `## Phases` (`### <id> — <title>` + paragraph naming task ids), `## Tasks` table `| id | subject | status | deps | spec | gate | commit |`, `## Notes`. Status: `open`, `in progress (<session>)`, `done <hash>`, `blocked: <why>`, `skipped: <why>`; ready = open with every dep done; among ready nodes the first in table order runs. A subject starting `READ:` goes to the reader agent.
`ge/<r>/next.md` — the kickoff for the next node; first line `# kickoff: <id>`. `ledger.md` — `| date | session | task | event | outcome | commit |`, append-only (`done`, `miss`, `blocked`, `paused <reason>`, `resumed`, `revised`, `review`). `calls.md` — `## Open` / `## Decided`. `status.html` — self-contained graph page, refreshes every 60 s. `summaries/` — pause summaries. `PAUSE` / `STOP` — present while paused / stopped.

Close protocol (what a task agent does): work commit → `ge.py close` → `next.md` for `ge.py next`'s node → `git commit -m "ge(<r>): close <id>; next <n>"`. The verifier checks the artifacts through `ge.py gate`, never the maker's report.

## Example

`examples/hello-roadmap/` is a two-file Python project with a three-node roadmap whose gate is `python -m pytest -q`. Copy it, `cd` in, `/ge-status hello`, then `/ge-run-roadmap hello once`.

## Metering note

The runner is an interactive session: it shares the interactive pool. It never spawns `claude -p`. If headless metering changes, the same files and script serve a headless loop; that loop is not in 0.1.
```

- [ ] **Step 5: Run to pass** — `python -m pytest tests/ -q` — Expected: `20 passed`.

- [ ] **Step 6: Commit**

```bash
git add examples/ README.md tests/test_example.py
git commit -m "examples: hello-roadmap; README; smoke test"
```

---

### Task 11: Dogfood — this repo's own roadmap

**Files:**
- Create: `ge/config.md`, `ge/plugin/roadmap.md`, `ge/plugin/next.md`, `ge/plugin/ledger.md`, `ge/plugin/calls.md`, `ge/plugin/summaries/.gitkeep`

- [ ] **Step 1: Write ge/config.md**

```markdown
# ge config — graph-engineering

## Gates
| name | command | success | artifact |
|---|---|---|---|
| pytest | python -m pytest tests/ -q | `(\d+) passed` | stdout |

## Guards
| name | command | blocked when |
|---|---|---|

## Rules
`scripts/ge.py` stays ONE stdlib-only file (3.9+ syntax) and the only reader/writer of `ge/` files; tests in `tests/`, run `python -m pytest tests/ -q` from the repo root. Skills are Markdown a fresh session can follow; agents are project-agnostic. Never push to GitHub. The spec `docs/superpowers/specs/2026-09-05-graph-engineering-design.md` is the contract; change it before changing behaviour.

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

- [ ] **Step 2: Write the roadmap files**

`ge/plugin/roadmap.md`:
```markdown
# plugin — Graph Engineering builds itself

## Goal
A goal becomes a task graph; one interactive session runs the graph unattended by dispatching a fresh subagent per node with an independent verifier per close; the human pauses it to test, get a summary, or change the goal. Everything is files in the project's git. Any project, any gate. (Spec `docs/superpowers/specs/2026-09-05-graph-engineering-design.md`.)

## Phases
### M — migration and release
T12 is the first migration of an existing project onto the plugin; publish waits for the owner's word.

## Tasks
| id | subject | status | deps | spec | gate | commit |
|---|---|---|---|---|---|---|
| T12 | the first external project migration (anonymised) | open | | docs/superpowers/plans/2026-09-05-graph-engineering.md Task 12 | pytest | |
| publish | push 0.1.0 to Popschlock/graph-engineering | blocked: human call | T12 | docs/superpowers/specs/2026-09-05-graph-engineering-design.md §9 | pytest | |

## Notes
Tasks 1–11 of the plan were built by hand before this roadmap existed (see git log). Publishing is the owner's word, never automatic.
```
`ge/plugin/next.md`:
```markdown
# kickoff: T12

Read `docs/superpowers/plans/2026-09-05-graph-engineering.md` Task 12 whole, then `README.md`. Do Task 12's steps exactly, in order, in the two repositories it names -- this one and the project being migrated; its deps table is the human's confirmed word for that project's dependencies. Gate: `pytest` (`ge.py gate plugin pytest`). The work commit in THIS repo is the README section Task 12 adds; the migrated project's own commits are named in the close outcome. Close per rule 7; `ge.py next plugin` will print `none` (publish is blocked), so next.md's first line becomes `# kickoff: none`.
```
`ge/plugin/ledger.md`: the `LEDGER_HEAD` two lines. `ge/plugin/calls.md`:
```markdown
# calls — plugin

## Open
* publish 0.1.0 to GitHub now, or after the first external migration has run a real node through it — the owner's call

## Decided
```

- [ ] **Step 3: Validate and render**

Run: `python scripts/ge.py validate plugin` — Expected: `OK plugin: 2 nodes, 1 ready`. Run: `python scripts/ge.py render plugin` — Expected: the path of `ge/plugin/status.html`. Run: `python -m pytest tests/ -q` — Expected: `20 passed`.

- [ ] **Step 4: Commit**

```bash
git add ge/
git commit -m "ge(plugin): the plugin's own roadmap — T12 next, publish on the owner's word"
```

- [ ] **Step 5: Acceptance** — in a Claude Code session in this checkout with the plugin installed from the local marketplace: `/ge-run-roadmap plugin dry` prints the brief for T12; `/ge-run-roadmap plugin once` dispatches T12 and closes it (Task 12 is what that run does). Expected close line: `T12 PASS <hash> — gates: pytest=20`.

---

### Task 12: The first migration — an existing project onto the plugin

A project that already runs a roadmap by hand moves onto the plugin. The project
below is fictional — `acme`, a Python service with a small TypeScript front end,
whose gates are `pytest` and `npm` scripts — and every path is relative to its
repository root, so the shape reads without any one project's details. Substitute
the real names when you run it.

**Files (in the project being migrated):**
- Create: `ge/config.md`, `ge/acme/roadmap.md`, `ge/acme/next.md`, `ge/acme/ledger.md`, `ge/acme/calls.md`, `ge/acme/summaries/.gitkeep`
- Delete: its bespoke runner — `.claude/agents/acme-task.md`, `acme-reader.md`, `acme-verifier.md`, `acme-review.md`, `.claude/skills/run-roadmap/SKILL.md`, and the shell wrapper and session preamble those used (`tools/roadmap.sh`, `tools/session_preamble.md`)
- Modify: `docs/ROADMAP.md` (left as a pointer), the file that held its live kickoff (a pointer line at the top), `docs/DECISIONS.md` (one dated entry)
- Modify: the project memory entry that described the old runner, and that memory's index line
- **Files (in this repo):** Modify: `README.md` (section "Migrating an existing roadmap")

`GE` below = `python "<this checkout>/scripts/ge.py" --root <the project root>`.

- [ ] **Step 1: config.md** — write `ge/config.md` in the project. Its gates are the commands its humans already run before calling a task done, one row each; its guard is whatever must not be running while an unattended session works; its rules are its standing session preamble, verbatim.

```markdown
# ge config — acme

## Gates
| name | command | success | artifact |
|---|---|---|---|
| unit | python -m pytest -q | `(?m)^(\d+) passed` | stdout |
| typecheck | npm run typecheck | `Found 0 errors` | stdout |
| e2e | npm test -- --reporter=tap | `(\d+) passing, 0 failing` | logs/e2e_*.log |

## Guards
| name | command | blocked when |
|---|---|---|
| migrating | docker ps --filter name=db-migrate --format "{{.Names}}" | `db-migrate` |

## Rules
1. The human's own words come first: nothing else is the work while a `docs/FEEDBACK-*.md` is newer than the ledger's last row. If one is, that round is the work and the kickoff waits.
2. `ge.py guards acme` before anything else; `guard migrating: BLOCKED` means wait, and never kill the container.
3. `e2e` writes its own artifact: `npm test -- --reporter=tap 2>&1 | tee logs/e2e_<task id>.log`; its passing count never goes down.
4. Every code edit BEFORE a long gate; `e2e` is owed whenever `api/` or `web/` moves.
5. The service's contract tests are the oracle; a number you cannot resolve is named in a log line or a refusal, never defaulted silently.

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

- [ ] **Step 2: init and add the nodes** — `GE init acme --goal "<the goal paragraph of the project's own roadmap, verbatim>"`. Then put its phases into `## Phases` of `ge/acme/roadmap.md` (`### <id> — <title>` plus that phase's paragraph, one per phase; whatever the old file called parked or not scheduled moves to `## Notes`). Then one `GE add acme --id <id> --subject "<subject cell>" --deps "<deps>" --spec "<spec cell>" --gate "<gate>"` per row, in table order.

The deps and the gates are the human's confirmed word, agreed BEFORE the run and written into the plan so that an unattended session never has to infer them. `acme`'s eleven nodes (the gate column is the conversion of its old "gate at close" column; a task-specific script's green line stays in the spec cell):

| id | deps | gate |
|---|---|---|
| A1 | | unit |
| A2.1 | A1 | unit, typecheck |
| A2.2 | A2.1 | unit, e2e |
| A2.3 | A2.2 | unit |
| A3.1 | A1 | unit |
| A3.2 | A3.1 | unit, typecheck |
| A3.3 | A3.2 | e2e |
| A4.1 | A2.3, A3.3 | e2e |
| A4.2 | A4.1 | e2e |
| A5 | A4.2 | unit, e2e |
| A6 | A5 | e2e |

Then mark what is already finished: `GE set acme A1 --status "done <its commit hash>"`. Run `GE validate acme` — Expected: `OK acme: 11 nodes, 2 ready`; `GE next acme` — Expected: `A2.1 | ... | unit, typecheck`.

- [ ] **Step 3: ledger, calls, next.md** — `ge/acme/ledger.md`: the two `LEDGER_HEAD` lines, then one row per close the old roadmap already recorded, in the new shape (`| <date> | <session> | <id> | done | <the outcome it recorded> | <hash> |`). `ge/acme/calls.md`: `## Open` holds the questions still waiting on the human, `## Decided` the rulings the old roadmap recorded, one dated line each. `ge/acme/next.md`: first line `# kickoff: A2.1`, then the project's existing live kickoff with its quoting stripped and its closing sentence replaced by `Close per the rules block (ge.py close acme A2.1 ..., next.md for the node ge.py next names, the close commit).` Run `GE validate acme` — Expected `OK`. `GE render acme`.

- [ ] **Step 4: Retire the bespoke runner** — in the project: `git rm .claude/agents/acme-task.md .claude/agents/acme-reader.md .claude/agents/acme-verifier.md .claude/agents/acme-review.md .claude/skills/run-roadmap/SKILL.md tools/roadmap.sh tools/session_preamble.md`. Replace `docs/ROADMAP.md` with a pointer:

```markdown
# ROADMAP — moved to `ge/acme/roadmap.md`

The graph, the ledger and the human's calls live under `ge/acme/` and are read and written only through the Graph Engineering plugin (`/ge-status acme`, `/ge-run-roadmap acme`, `/ge-pause-roadmap acme ...`). The base goal is `## Goal` there, verbatim. The kickoff for the next node is `ge/acme/next.md`; the standing rules are `ge/config.md` `## Rules`. History: this file's last full form is commit <hash>.
```

Prepend a pointer line to the old kickoff file: `> The live kickoff is now ge/acme/next.md; this file is history.` Append to `docs/DECISIONS.md` a dated entry, "The roadmap runs on the Graph Engineering plugin", with three lines: what moved (`ge/acme/`, `ge/config.md`), what was retired (the four bespoke agents, `/run-roadmap`, the shell wrapper, the preamble), why (the pattern was made general; one script, any project).

- [ ] **Step 5: Memory** — rewrite the project memory entry that described the old runner: what exists now (`ge/acme/roadmap.md` the graph, `ge/config.md` the gates, the guard and the rules, `/ge-run-roadmap acme` the runner from the `graph-engineering` plugin, `ge.py` the only reader and writer), why (the pattern was made general), how to apply (never edit `ge/acme/roadmap.md` or `ledger.md` by hand; `/ge-status acme` first; the guard). Update its `description:` and its memory index line to say `/ge-run-roadmap acme` and `ge/acme/`.

- [ ] **Step 6: Commit in the project** — `git add -A ge docs .claude tools && git commit -m "ge(acme): migrate the roadmap to the Graph Engineering plugin; the bespoke agents, /run-roadmap, roadmap.sh and the preamble retired"`.

- [ ] **Step 7: The plugin-side work commit** — append to this repo's `README.md`:

```markdown
## Migrating an existing roadmap

`/ge-build-roadmap <r> --from <your plan or roadmap file>` converts a task table or `### Task N:` headings into `ge/<r>/roadmap.md`; you confirm the inferred dependencies. Put your preamble's standing rules under `## Rules` and your suite commands under `## Gates` in `ge/config.md` (an artifact glob lets the verifier read the file your suite wrote instead of re-running a long suite). Task 12 of `docs/superpowers/plans/2026-09-05-graph-engineering.md` is a worked example of the whole move: the plan's task list converted node by node, the project's standing preamble and suite commands moved into `ge/config.md`, its bespoke runner and agents retired, and its old roadmap file left as a pointer.
```

Run `python -m pytest tests/ -q` — Expected `20 passed`. `git add README.md && git commit -m "README: migrating an existing roadmap"`.

- [ ] **Step 8: Acceptance** — in a Claude Code session in the migrated project with the plugin installed: `/ge-run-roadmap acme dry` prints the brief whose kickoff's first line is `# kickoff: A2.1`, with the plugin's default rules, then the project's five rules, then the kickoff. `python "<this checkout>/scripts/ge.py" --root <the project root> validate acme` prints `OK acme: 11 nodes, 2 ready`. When this task runs as the dogfood node T12, close it per rule 7 in this repo (`ge.py close plugin T12 <the README commit hash> "pytest 20 passed; the migrated project's roadmap validates"`).

---

## Self-review

**Spec coverage.** §2.1 roadmap format → Task 1 parser, Task 2 writers; `READ:` dispatch → Task 6 step 4. §2.2 config (gates, guards, rules, tiers, cadence; default rules block; tier override) → Task 4, Task 6 preamble line. §2.3 next.md refusal + minimal brief + ledger note → Task 4 `brief` (exit 2) and Task 6 step 3 (`event revised`). §2.4 ledger shape/events → Task 2. §2.5 calls → Task 1 `read_calls`, Task 7 `calls`, resume/revise skills. §2.6 status.html (SVG by depth, colours incl. hatched, arrows, phase bands, ledger 20, open calls, last close, generated-at, refresh meta) → Task 3. §3 every listed subcommand → Tasks 1, 2, 3, 4, 7; exit codes → Task 1 `main`; the named test areas → test_ge/test_render/test_gate. §4 eight skills → Tasks 6, 7, 8. §5 seven steps, rate limit, compaction → Task 6. §6 three reasons → Task 6. §7 four agents with tiers → Task 5. §8 hook → Task 9. §9 packaging (manifests already in repo), example, README, docs → Task 10. §10 dogfood → Task 11; migration → Task 12. §11 non-goals: nothing here dispatches in parallel or headless.

**Placeholder scan.** No TBD/TODO; every code step shows the code; Task 3's `parse_config` stub is a real function Task 4 replaces in full; Task 11/12 kickoff text is complete for a session that knows nothing.

**Type consistency.** `append_ledger(r, task, event, outcome, commit="", session="")` is used with that argument order in Tasks 2, 3, 7. `render(rm, cfg, ledger_rows, calls_open)` matches its test and `render_to_file`. `list_roadmaps()` 5-tuples match the hook and the `list` CLI line (`name | d/t done | state | n open calls`; the hook prints its own sentence from the tuple). `brief()` returns `(text, code)`; `close()` returns `bool`; `run_gate()` returns `(bool, list, str)`; `layout()` returns `(pos, bands)` as tested. The verifier's `gates:` line format (`name=captures`) is what the runner quotes into `ge.py close`'s outcome and the close line.

## Resolved ambiguities (recorded by the plan writer)

- Who closes: the task agent runs `ge.py close`; `close` is idempotent so the runner's `ge.py close` on PASS is a harmless re-render.
- Two commits per close: the work commit (hash recorded) then `ge(<r>): close <id>; next <n>`; the verifier checks `git log -3` contains the hash and HEAD is the close commit.
- `brief` is side-effect free (exit 2 + stderr) so `dry` never writes; the runner records `event revised` when not dry.
- Reviewer moves are dependency edits (`X deps=...`) applied with `ge.py set`; reruns are `--status open`.
- `resume` clears both PAUSE and STOP.
- The hook reads files only and never runs guard commands.
- A migrated project's long gates are read from files its own suite already writes: the config's `artifact` column takes a glob, newest file first, so the verifier never re-runs a suite that takes minutes. A project whose suite writes nothing keeps `stdout` and pays for the re-run.
- The runner's `start` mark dirties the tree by design, so rule 6 exempts a change limited to `ge/<r>/roadmap.md`.
- T12 runs unattended as the dogfood node, so its deps table in the plan is the human's confirmed word; its plugin-side work commit is the README migration section.
- `ge.py --root <dir>` and `ge.py calls <r>` were added beyond §3 so gates can target another project and skills can list open calls without reading calls.md whole.
