#!/usr/bin/env python3
"""ge.py — Graph Engineering. The ONLY reader/writer of a project's ge/ files.
Run from the project root (or with --root <dir>): python ge.py <command> [args].
Exit 0 ok, 1 not found/invalid, 2 validation failure (reasons printed).
Sections: 1 model+parse | 2 graph | 3 writers | 4 config+gate+guards+brief | 5 render | 6 pause+open | 7 cli
"""
import argparse, datetime, glob, json, os, re, signal, subprocess, sys, time
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
def flatten(s): return re.sub(r"[\r\n]+", " ", s or "").strip()
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
    if section(rm.lines, "## Tasks")[0] < 0:  # no heading = no rows parsed; "0 nodes" would read like an empty table
        probs.append("no ## Tasks section")
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
        # the node next.md names is READY before dispatch and IN PROGRESS during it -- validate runs in
        # both states (a revise or a review while a task agent holds the row), so both are the same "ok"
        rid |= {n.id for n in rm.nodes if kind(n.status) == "in progress"}
        if not m: probs.append("next.md: first line is not '# kickoff: <id>'")
        elif m.group(1) != "none" and m.group(1) not in rid: probs.append(f"next.md: {m.group(1)} is not a ready or in-progress node")
    return probs

def roadmap_state(r):
    """-> (name, done, total, state, open_calls) for ONE roadmap; state: idle | in progress (ids) | paused: <reason> | stopped"""
    d = rdir(r)
    rm = parse_roadmap(d / "roadmap.md"); ks = [kind(n.status) for n in rm.nodes]
    ip = [n.id for n in rm.nodes if kind(n.status) == "in progress"]
    if (d / "STOP").is_file(): state = "stopped"
    elif (d / "PAUSE").is_file(): state = "paused: " + (d / "PAUSE").read_text(encoding="utf-8").split("\n", 1)[0].strip()
    else: state = f"in progress ({', '.join(ip)})" if ip else "idle"
    return (d.name, ks.count("done"), len(ks), state, len(read_calls(r)[0]))

def list_roadmaps():
    """-> [(name, done, total, state, open_calls)] for every roadmap under ge/; one roadmap_state per directory"""
    out = []
    if not ge_root().is_dir(): return out
    for d in sorted(ge_root().iterdir()):
        if not (d / "roadmap.md").is_file(): continue
        out.append(roadmap_state(d.name))
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
    for x in rm.nodes:  # every row at or after the insert moved down one line
        if x.line >= at: x.line += 1
    n.line = at; rm.nodes.insert(sum(1 for x in rm.nodes if x.line < at), n)

def init_roadmap(r, goal_text, subject=""):
    d = rdir(r)
    if (d / "roadmap.md").exists(): raise FileExistsError(str(d / "roadmap.md"))
    def keep(p, text):  # an existing ledger/calls file survives: init is not a reset
        if not Path(p).exists(): wtext(p, text)
    keep(d / "summaries" / ".gitkeep", "")
    wtext(d / "roadmap.md", ROADMAP_TMPL.format(r=r, subject=subject or goal_text.split("\n")[0][:60], goal=goal_text))
    keep(d / "ledger.md", LEDGER_HEAD); keep(d / "calls.md", CALLS_TMPL.format(r=r)); return d


def today(): return datetime.date.today().isoformat()
def now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")  # ledger rows: the page shows durations

def append_ledger(r, task, event, outcome, commit="", session=""):
    p = rdir(r) / "ledger.md"
    if not p.is_file(): wtext(p, LEDGER_HEAD)
    row = f"| {now()} | {esc_cell(session)} | {esc_cell(task)} | {esc_cell(event)} | {esc_cell(outcome)} | {esc_cell(commit)} |\n"
    with open(p, "a", encoding="utf-8", newline="\n") as f: f.write(row)
    return row.strip()

def read_ledger(r, n=None, started=True):
    """Every row, oldest first, or the last n. `started` rows are one per dispatch: the `ledger` verb drops
    them unless --all, so the windows the verifier, the reviewer and the runner read keep their meaning."""
    p = rdir(r) / "ledger.md"
    rows = ([cells(l) for l in p.read_text(encoding="utf-8").split("\n") if re.match(r"\|\s*\d{4}-\d{2}-\d{2}", l)]
            if p.is_file() else [])
    if not started: rows = [x for x in rows if len(x) < 4 or x[3] != "started"]
    return rows[-n:] if n else rows

def start(r, nid, session):
    """status -> in progress (<session>); ledger `started`; render. The render is the 0.3 fix: without it the
    page was rebuilt when a node turned green and never while it was amber."""
    set_field(load(r), nid, "status", f"in progress ({session})"); append_ledger(r, nid, "started", session, "", session)
    render_to_file(r)

def close(r, nid, h, outcome, session=""):
    """status -> done <hash>, commit column, ledger row, render. -> "" on a first close, "already" when the
    SAME hash is closed twice — which writes NOTHING at all, not even status.html, whose generated-at stamp
    would otherwise make a second close a real change to a committed file — and "re-closed" when a DIFFERENT
    hash replaces one already recorded. A node keeps exactly ONE `done` row: a second would read as a node
    that was done twice, so a correction is appended as `re-closed` and names the hash it replaced."""
    rm = load(r); n = by_id(rm).get(nid)
    if n is None: raise KeyError(nid)
    prior = [x for x in read_ledger(r) if len(x) > 5 and x[2] == nid and x[3] in ("done", "re-closed")]
    if n.status == f"done {h}" and prior: return "already"
    n.status, n.commit = f"done {h}", h; rm.lines[n.line] = fmt_row(n); save(rm)
    if prior: append_ledger(r, nid, "re-closed", f"{outcome} (was {prior[-1][5] or 'no hash'})", h, session)
    else: append_ledger(r, nid, "done", outcome, h, session)
    render_to_file(r)
    return "re-closed" if prior else ""

def block(r, nid, why, session=""):
    set_field(load(r), nid, "status", "blocked: " + why); append_ledger(r, nid, "blocked", why, "", session)
    render_to_file(r)

# ---- 4. config + gate + guards + brief ----------------------------------------
@dataclass
class Gate: name: str; command: str; success: str; artifact: str; floor: str = ""
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
        r += [""] * 5; cfg.gates[r[0]] = Gate(r[0], r[1], r[2], r[3] or "stdout", r[4])
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

GATE_TIMEOUT, GUARD_TIMEOUT = 3600, 30
TIMEOUT_MARK = "ge: TIMEOUT after "

def kill_tree(p):
    """A shell=True command is a SHELL whose child does the work. Killing only the shell leaves that child
    running AND holding the output pipe, so the wait that follows returns when the GRANDCHILD exits — which
    for a hung command is never, and a timeout that does not bound the wall clock is worse than none,
    because it claims a safety it does not have."""
    try:
        if os.name == "nt": subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        else: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except Exception: pass
    try: p.kill()
    except Exception: pass

def run_cmd(cmd, timeout=None):
    """stdout+stderr, decoded the same way an artifact file is: utf-8, undecodable bytes replaced.
    A command that never returns would hold an unattended runner for ever, so its whole process tree is
    killed at <timeout> seconds. That fails CLOSED: whatever it had already written is kept and a
    TIMEOUT_MARK line is appended, which run_gate turns into NO MATCH and guards into ERROR — never a MATCH
    on partial output that happened to hold the pattern, and never `ok`."""
    kw = {} if os.name == "nt" else {"start_new_session": True}   # a group os.killpg can take out at once
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", **kw)
    try:
        return p.communicate(timeout=timeout)[0] or ""
    except subprocess.TimeoutExpired:
        kill_tree(p)
        try: out = p.communicate(timeout=30)[0] or ""   # the tree is down, so the pipe closes; retry is safe
        except Exception: out = ""
        return out + f"\n{TIMEOUT_MARK}{timeout}s: {cmd}\n"

def newest(pattern):
    hits = glob.glob(pattern, recursive=True)
    return max(hits, key=os.path.getmtime) if hits else None

def floor_refusal(g, caps):
    """-> "" when a gate clears its floor, else the reason it does not. A floor is a RATCHET on the first
    capture group: `(\\d+) passed` reads a suite that lost half its tests exactly as green as one that grew,
    and only a floor notices. It fails CLOSED — a floor that is not a whole number, a success regex with no
    capture group, and a capture that is not a number are each a refusal, never a pass."""
    if not (g.floor or "").strip(): return ""
    try: floor = int(g.floor.strip())
    except ValueError: return f"floor {g.floor!r} is not a whole number"
    if not caps: return f"floor {floor}, but the success regex has no capture group to read"
    try: got = int(str(caps[0]).strip())
    except (TypeError, ValueError): return f"floor {floor}, but the capture {caps[0]!r} is not a number"
    return "" if got >= floor else f"{got} is below the floor of {floor}"

def run_gate(g):
    """artifact 'stdout' -> run the command; else read the newest file matching the glob.
    -> (matched, captures, source, text, why). text is what was searched, so a NO MATCH can show its tail
    without the caller re-running a long command. A file source carries its mtime ('<path>, <ISO seconds>'):
    a MATCH read out of a file written before the work commit is a stale artifact, and the verifier can
    only see that if the time is printed. `why` names a refusal a bare regex miss cannot — a command that
    timed out, or a capture under the gate's floor — so a NO MATCH says which of the two it is. A malformed
    success regex raises re.error: the caller reports it rather than a traceback."""
    if g.artifact in ("", "stdout"): text, src = run_cmd(g.command, GATE_TIMEOUT), "stdout of " + g.command
    else:
        f = newest(g.artifact)
        if not f: return False, [], "no artifact matches " + g.artifact, "", ""
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).isoformat(timespec="seconds")
        text, src = Path(f).read_text(encoding="utf-8", errors="replace"), f"{f}, {mtime}"
    if TIMEOUT_MARK in text: return False, [], src, text, f"the command timed out after {GATE_TIMEOUT}s"
    m = re.search(g.success, text)
    if m is None: return False, [], src, text, ""
    caps = list(m.groups()); why = floor_refusal(g, caps)
    return why == "", caps, src, text, why

def pause_state(r):
    p = rdir(r) / "PAUSE"
    if not p.is_file(): return None
    t = p.read_text(encoding="utf-8").split("\n", 1)
    return t[0].strip(), (t[1].strip() if len(t) > 1 else "")

def guards(r, cfg):
    """Yields the lines, STOP and PAUSE first and BEFORE any subprocess runs, so a guard command that
    fails, hangs or explodes can never hide them. Fails CLOSED: git that did not run reads UNKNOWN and
    a guard that did not run reads ERROR — never 'clean', never 'ok'. list(guards(...)) for a list."""
    yield "stop: PRESENT" if (rdir(r) / "STOP").is_file() else "stop: absent"
    ps = pause_state(r); yield f"pause: {ps[0]} | {ps[1]}" if ps else "pause: absent"
    try:
        st = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if st.returncode: yield f"tree: UNKNOWN (git rc={st.returncode})"
        else: yield "tree: DIRTY" if st.stdout.strip() else "tree: clean"
    except Exception as e: yield f"tree: UNKNOWN (git {type(e).__name__}: {e})"
    for g in cfg.guards.values():
        try: out = run_cmd(g.command, GUARD_TIMEOUT)
        except Exception as e: yield f"guard {g.name}: ERROR {type(e).__name__}: {e}"; continue
        if TIMEOUT_MARK in out: yield f"guard {g.name}: ERROR timed out after {GUARD_TIMEOUT}s"; continue
        try: hit = re.search(g.blocked_when, out)
        except re.error as e: yield f"guard {g.name}: ERROR bad regex {e}"; continue
        yield f"guard {g.name}: {'BLOCKED' if hit else 'ok'}"

DEFAULT_RULES = """# Graph Engineering — the unattended rules (prepended to every brief)

You are an unattended session of the project at `{root}`, working roadmap `{r}` (`ge/{r}/roadmap.md`). Nobody is watching. Every read or write of the roadmap, the ledger and the status page goes through `ge.py` = `"{py}" "{ge}"`, run from `{root}`; you never edit `roadmap.md`, `ledger.md` or `status.html` by hand (you do write `next.md`, `calls.md` and `summaries/`). Read `ge/{r}/roadmap.md` whole before the kickoff below, then the kickoff, then work. These rules bind over anything the kickoff says that assumes a person is present:

1. **Never ask a question.** A decision only the human can make goes under `## Open` in `ge/{r}/calls.md` (both sides, one line each); then `ge.py block {r} {id} "human call"`, write `next.md` for `ge.py next {r}`'s node (rule 7d), commit, and report `blocked: human call`.
2. **ONE task**: `{id}`, which the kickoff below is. Its row already reads `in progress`; leave it. Nothing from other rows.
3. **Finish every edit, THEN run the long gates.** A gate is a name in `ge/config.md`; run each gate the row names with `ge.py gate {r} <name>` on the closing tree and keep the captures it prints for the commit message and your report. `NO MATCH` is not a close: fix and re-run, or block.
4. **Guards.** First run `ge.py guards {r}`. `stop: PRESENT` means stop now and report `stopped`. A `guard <name>: BLOCKED` at any point means stop after writing `next.md` and report `blocked: guard <name>`; never clear a guard yourself. A `tree: UNKNOWN (...)` or `guard <name>: ERROR ...` line is a check that could not run, and it fails closed: it blocks exactly like `BLOCKED` — stop the same way and report `blocked: guard tree` for the tree line, `blocked: guard <name>` for a named guard.
5. **Keep raw output out of your context**: `| tail`, `| grep`, background long commands and read their result line; reads that span many files go to a subagent whose short report you keep. Write-ups go to files, not to your report.
6. **A dirty tree at start** (`git status --porcelain`): if every change is under `ge/`, it is the runner's marks (status.html, ledger rows, your row, ge/.gitignore); continue — your close commit's `git add ge` carries them. Anything else is a cut-off session: finish what is finishable under its kickoff or `git stash` it with `ge.py event {r} revised "stashed: <what>"`, then take the task.
7. **Close, in this order:** (a) memory updated where a durable fact or a trap was found; (b) ONE work commit whose message quotes each gate's captures and ends with the session link you were given; (c) `ge.py close {r} {id} <hash> "<outcome>" --session <your session id>`, where `<outcome>` STARTS with one `<gate>=<captures>` token per gate the row names, separated by spaces, then `; ` and a one-line summary — `pytest=41 e2e=12; the close is idempotent now` — because the verifier reads those tokens back out of the ledger; (d) `ge.py next {r}`; write `ge/{r}/next.md` for that node: first line `# kickoff: <its id>` (or `# kickoff: none`), then a COMPLETE kickoff for a session that knows nothing — what to read, what to build, the pins or tests, its gate names, how to close; (e) `git add ge && git commit -m "ge({r}): close {id}; next <its id>"`.
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
    rules = DEFAULT_RULES.format(root=os.getcwd(), r=r, ge=Path(__file__).resolve(), id=n.id, py=sys.executable)
    return rules + ("\n## Project rules\n" + cfg.rules + "\n" if cfg.rules else "") + "\n---\n\n" + body, code

# ---- 5. render --------------------------------------------------------------
COLOURS = {"open": "#9aa0a6", "ready": "#3b82f6", "in progress": "#f59e0b", "done": "#22c55e",
           "blocked": "#ef4444", "skipped": "url(#hatch)"}
TEMPLATE = Path(__file__).with_name("status_template.html")
GITIGNORE = "# written by ge.py: the two files the live dashboard regenerates constantly\n*/status.js\n*/activity.log\n"
ACTIVITY_TAIL = 60

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

def depth_in_phase(rm):
    """longest path from a root counting only deps in the SAME phase, per node id: each phase band starts at
    column 0, so a roadmap of many phases wraps instead of running off the right of the page"""
    ids, memo, ph = by_id(rm), {}, {n.id: phase_of(rm, n.id) for n in rm.nodes}
    def d(i, seen=()):
        if i in memo: return memo[i]
        if i in seen: return 0
        ds = [d(x, seen + (i,)) + 1 for x in ids[i].deps if x in ids and ph[x] == ph[i]]
        memo[i] = max(ds) if ds else 0; return memo[i]
    return {n.id: d(n.id) for n in rm.nodes}

def layout(rm):
    """columns by depth inside the phase; rows by table order inside a phase band; bands in phase order, unphased nodes last"""
    dep = depth_in_phase(rm); order = [p[0] for p in rm.phases] + [""]; pos, bands, row = {}, [], 0
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

def log_activity(r, line):
    """activity.log: one timestamped line per gate event -- the only signal from inside a task's window"""
    p = rdir(r) / "activity.log"; p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {flatten(line)}\n")

def read_activity(r, n=ACTIVITY_TAIL):
    """-> [{ts, kind, name, state, detail, text}] for the last n lines; a gate line is
    `<ts> gate <name> running` or `<ts> gate <name> MATCH|NO MATCH <detail>`"""
    p = rdir(r) / "activity.log"
    if not p.is_file(): return []
    out = []
    for l in p.read_text(encoding="utf-8", errors="replace").split("\n")[-n - 1:]:
        if not l.strip(): continue
        ts, _, rest = l.partition(" ")
        m = re.match(r"gate (\S+) (running|MATCH|NO MATCH)\s*(.*)$", rest)
        if m: out.append({"ts": ts, "kind": "gate", "name": m.group(1), "state": m.group(2), "detail": m.group(3).strip(), "text": rest})
        else: out.append({"ts": ts, "kind": "note", "name": "", "state": "", "detail": rest, "text": rest})
    return out

def read_kickoff(r):
    """-> (id, body) from next.md: the kickoff the runner dispatches next, or ("", "")"""
    p = rdir(r) / "next.md"
    if not p.is_file(): return "", ""
    text = p.read_text(encoding="utf-8", errors="replace"); first, _, body = text.partition("\n")
    m = re.match(r"#\s*kickoff:\s*(\S+)", first)
    return (m.group(1), body.strip()) if m else ("", "")

def parse_ts(s):
    """'YYYY-MM-DD HH:MM' -> datetime; a date-only cell (a row older than 0.3) -> None: no duration from it"""
    try: return datetime.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M")
    except ValueError: return None

def split_outcome(outcome):
    """'unit=3 e2e=12; prose' -> {gates: [{name, value}], text: 'prose'}: the close protocol of rule 7c"""
    head, sep, text = outcome.partition("; ")
    toks = head.split(); gates = []
    for t in toks:
        m = re.match(r"^([A-Za-z0-9._-]+)=(.*)$", t)
        if m: gates.append({"name": m.group(1), "value": m.group(2)})
        else: gates = []; break
    if not gates: return {"gates": [], "text": outcome}
    return {"gates": gates, "text": text.strip() if sep else ""}

def status_data(rm, cfg, ledger_rows, calls_open, hold="", decided=(), activity=(), kickoff=("", "")):
    """ONE JSON document of the roadmap: what the page draws, embedded in status.html and mirrored to status.js"""
    pos, bands = layout(rm); rid = {n.id for n in ready(rm)}; ids = by_id(rm)
    rows = [{"ts": x[0], "session": x[1], "task": x[2], "event": x[3], "outcome": x[4], "commit": x[5]}
            for x in ledger_rows if len(x) > 5]
    dependents = {n.id: [] for n in rm.nodes}
    for n in rm.nodes:
        for d in n.deps:
            if d in dependents: dependents[d].append(n.id)
    nodes = []
    for n in rm.nodes:
        k = kind(n.status); hist = [x for x in rows if x["task"] == n.id]
        started = next((x["ts"] for x in reversed(hist) if x["event"] == "started"), "")
        fin = next((x for x in reversed(hist) if x["event"] in ("done", "re-closed", "blocked")), None)
        finished = fin["ts"] if fin and k in ("done", "blocked") else ""
        t0, t1 = parse_ts(started), parse_ts(finished)
        if k == "in progress" and t0: t1 = datetime.datetime.now()
        minutes = int((t1 - t0).total_seconds() // 60) if t0 and t1 and t1 >= t0 else None
        m = re.match(r"in progress \((.*)\)", n.status)
        done_row = next((x for x in reversed(hist) if x["event"] in ("done", "re-closed")), None)
        c, rw = pos.get(n.id, (0, 0))
        reason = n.status.split(": ", 1)[1] if k in ("blocked", "skipped") and ": " in n.status else ""
        nodes.append({"id": n.id, "subject": n.subject, "status": n.status, "kind": k, "ready": n.id in rid,
                      "deps": n.deps, "dependents": dependents[n.id], "spec": n.spec, "gates": n.gate, "commit": n.commit,
                      "phase": phase_of(rm, n.id), "col": c, "row": rw, "session": m.group(1) if m else "",
                      "reason": reason, "started": started, "finished": finished, "minutes": minutes, "history": hist,
                      "summary": split_outcome(done_row["outcome"]) if done_row and k == "done" else None,
                      "kickoff": kickoff[1] if kickoff[0] == n.id else ""})
    counts = {k: 0 for k in ("open", "ready", "in progress", "done", "blocked", "skipped")}
    for x in nodes: counts["ready" if x["ready"] else x["kind"]] = counts.get("ready" if x["ready"] else x["kind"], 0) + 1
    ip = [x["id"] for x in nodes if x["kind"] == "in progress"]
    if hold.startswith("STOPPED"): hk, state = "stopped", "stopped"
    elif hold.startswith("PAUSED"): hk, state = "paused", "paused: " + hold[8:].split(" — ", 1)[0]
    else: hk, state = None, (f"in progress ({', '.join(ip)})" if ip else "idle")
    reason, _, note = hold[8:].partition(" — ") if hk == "paused" else ("", "", "")
    return {"version": 1, "name": rm.name, "subject": (rm.lines[0].split("—", 1)[1].strip() if rm.lines and "—" in rm.lines[0] else ""),
            "goal": goal(rm), "generated": datetime.datetime.now().isoformat(timespec="seconds"), "project": Path.cwd().name,
            "state": state, "hold": {"kind": hk, "reason": reason, "note": note, "text": hold} if hk else None,
            "counts": counts, "total": len(nodes), "review_every": cfg.review_every,
            "gates": [{"name": g.name, "command": g.command, "success": g.success, "artifact": g.artifact, "floor": g.floor}
                      for g in cfg.gates.values()],
            "phases": [{"id": pid, "title": t, "text": x} for pid, t, x in rm.phases],
            "bands": [{"phase": p, "r0": r0, "r1": r1} for p, r0, r1 in bands], "nodes": nodes, "ledger": rows,
            "calls": {"open": list(calls_open), "decided": list(decided)}, "activity": list(activity), "colours": COLOURS}

def json_for_html(data):
    # `<` as \u003c: a `</script>` inside a subject would otherwise end the data block early
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

def render(rm, cfg, ledger_rows, calls_open, hold="", data=None, **kw):
    """-> the page. Pass `data` (from status_data) to skip rebuilding it; **kw go to status_data otherwise."""
    data = data or status_data(rm, cfg, ledger_rows, calls_open, hold, **kw)
    tmpl = TEMPLATE.read_text(encoding="utf-8")
    assert "/*__GE_DATA__*/" in tmpl, "status_template.html lost its data placeholder"
    return tmpl.replace("/*__GE_DATA__*/", json_for_html(data), 1).replace("__GE_TITLE__", esc(rm.name), 1)

def render_js(data): return "geUpdate(" + json.dumps(data, ensure_ascii=False) + ");\n"

def hold_line(r):
    """-> the banner status.html draws for a held roadmap, or "". STOP wins over PAUSE: a stopped roadmap
    dispatches nothing whatever a PAUSE file beside it says."""
    if (rdir(r) / "STOP").is_file(): return "STOPPED — no node is dispatched until /ge-resume-roadmap"
    ps = pause_state(r)
    return ("PAUSED: " + ps[0] + (" — " + ps[1] if ps[1] else "")) if ps else ""

def atomic_write(p, text):
    """temp + rename, so a page polling the file never reads it half-written; a browser or an antivirus holding
    the target on Windows raises PermissionError from the rename -- retry briefly, then write in place."""
    p = Path(p); tmp = p.with_name(p.name + ".tmp"); wtext(tmp, text)
    for i in range(5):
        try: os.replace(tmp, p); return
        except PermissionError: time.sleep(0.05 * (i + 1))
    wtext(p, text)
    try: tmp.unlink()
    except OSError: pass

def render_to_file(r):
    """status.html + status.js, and ge/.gitignore for the two generated files where it is absent"""
    rm = load(r); op, dec = read_calls(r)
    data = status_data(rm, parse_config(ge_root() / "config.md"), read_ledger(r), op, hold_line(r),
                       decided=dec, activity=read_activity(r), kickoff=read_kickoff(r))
    html = render(rm, None, None, None, data=data)
    gi = ge_root() / ".gitignore"
    if not gi.exists(): wtext(gi, GITIGNORE)
    atomic_write(rdir(r) / "status.js", render_js(data))
    atomic_write(rdir(r) / "status.html", html); return rdir(r) / "status.html"

# ---- 6. pause + open --------------------------------------------------------
def pause(r, reason, note=""):
    """PAUSE is line 1 = reason, line 2 = note, and pause_state, roadmap_state and the SessionStart hook all
    read exactly that. A newline inside the NOTE would become a third line nothing reads; a newline inside the
    REASON is worse — it truncates the reason and pushes the note onto a line nobody wrote. Both are flattened."""
    reason, note = flatten(reason), flatten(note)
    wtext(rdir(r) / "PAUSE", reason + ("\n" + note if note else "") + "\n"); append_ledger(r, "-", "paused " + reason, note)
    render_to_file(r)

def resume(r):
    """-> the files removed. A roadmap that was not paused or stopped gets no ledger row:
    `resumed` says a hold was lifted, and a row saying so when none was is a false ledger."""
    gone = []
    for f in ("PAUSE", "STOP"):
        p = rdir(r) / f
        if p.exists(): p.unlink(); gone.append(f)
    if gone: append_ledger(r, "-", "resumed", "")
    render_to_file(r); return gone

def stop(r): wtext(rdir(r) / "STOP", today() + "\n"); render_to_file(r)

def open_command(path, platform=sys.platform):
    if platform.startswith("win"): return ["cmd", "/c", "start", "", str(path)]
    if platform == "darwin": return ["open", str(path)]
    return ["xdg-open", str(path)]

# ---- 7. cli -----------------------------------------------------------------
class Argp(argparse.ArgumentParser):
    """Usage errors exit 1, not argparse's 2 — 2 is reserved for a validation failure."""
    def error(self, message):
        self.print_usage(sys.stderr); print(f"{self.prog}: error: {message}", file=sys.stderr); sys.exit(1)

def main(argv=None):
    # A brief, a subject or a gate's output may hold any character; on Windows the console's default is cp1252
    # and one '≥' would end the command with UnicodeEncodeError instead of the text the caller asked for.
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"): s.reconfigure(encoding="utf-8", errors="replace")
    ap = Argp(prog="ge.py"); ap.add_argument("--root", default=None)
    sp = ap.add_subparsers(dest="cmd", required=True)
    def sub(name, *pos, **opts):
        p = sp.add_parser(name)
        for x in pos: p.add_argument(x)
        for k, v in opts.items(): p.add_argument("--" + k, default=v)
        return p
    sub("list"); sub("validate", "r"); sub("ready", "r"); sub("next", "r"); sub("node", "r", "id"); sub("render", "r")
    sub("start", "r", "id", "session"); sub("close", "r", "id", "hash", "outcome", session="")
    sub("block", "r", "id", "why", session=""); sub("event", "r", "event", "outcome", session="")
    lg = sub("ledger", "r"); lg.add_argument("n", nargs="?", type=int, default=3); lg.add_argument("--all", action="store_true")
    sub("init", "r", goal="", subject=""); sub("add", "r", id="", subject="", deps="", spec="", gate="", after=None)
    sub("set", "r", "id", status=None, deps=None, spec=None, gate=None, subject=None)
    sub("gate", "r", "name"); sub("guards", "r"); sub("brief", "r")
    sub("pause", "r", "reason").add_argument("note", nargs="?", default=""); sub("resume", "r"); sub("stop", "r")
    sub("open", "r"); sub("calls", "r")
    a = ap.parse_args(argv)
    try:
        if a.root: os.chdir(a.root)
        return dispatch(a)
    except FileNotFoundError as e: print(f"not found: {e}", file=sys.stderr); return 1
    except FileExistsError as e: print(f"exists: {e}", file=sys.stderr); return 1  # init over a live roadmap
    except KeyError as e: print(f"no such node: {e}", file=sys.stderr); return 1

def dispatch(a):
    c = a.cmd
    if c == "list":
        for name, done, total, state, calls in list_roadmaps(): print(f"{name} | {done}/{total} done | {state} | {calls} open calls")
        return 0
    if c == "init":
        if not a.goal: print("--goal is required", file=sys.stderr); return 1
        print(f"created {init_roadmap(a.r, a.goal, a.subject)}"); return 0
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
        # a node left `in progress` by a session that died is stranded whether or not something else is ready,
        # so it is said every time — on stderr, where it cannot be read as the ready node's line
        for x in rm.nodes:
            if kind(x.status) == "in progress": print(f"in progress: {x.id} — {x.status}", file=sys.stderr)
        if n: print(f"{n.id} | {n.subject} | {', '.join(n.gate)}"); return 0
        print("none")
        for x in rm.nodes:
            if kind(x.status) == "blocked": print(f"blocked: {x.id} — {x.status}")
        return 0
    if c == "node":
        n = by_id(rm).get(a.id)
        if not n: raise KeyError(a.id)
        for k in ("id", "subject", "status", "deps", "spec", "gate", "commit"):
            v = getattr(n, k); print(f"{k}: {', '.join(v) if isinstance(v, list) else v}")
        return 0
    if c == "start": start(a.r, a.id, a.session); print(f"{a.id}: in progress ({a.session})"); return 0
    if c == "close":
        state = close(a.r, a.id, a.hash, a.outcome, a.session); print(f"{a.id}: {state + ' ' if state else ''}done {a.hash}"); return 0
    if c == "block": block(a.r, a.id, a.why, a.session); print(f"{a.id}: blocked: {a.why}"); return 0
    if c == "event": print(append_ledger(a.r, "-", a.event, a.outcome, "", a.session)); render_to_file(a.r); return 0
    if c == "ledger":
        for row in read_ledger(a.r, a.n, started=a.all): print("| " + " | ".join(row) + " |")
        return 0
    if c == "add":
        if not a.id or not a.subject: print("--id and --subject are required", file=sys.stderr); return 1
        add_node(rm, Node(a.id, a.subject, "open", split_list(a.deps), a.spec, split_list(a.gate), ""), a.after); print(f"added {a.id}")
        render_to_file(a.r); return 0
    if c == "set":
        if a.status is not None and kind(a.status) == "bad":  # a status no reader knows makes the node
            print(f"bad status {a.status!r}; accepted: open | in progress (<session>) | done <hash> | "  # neither ready nor done
                  "blocked: <why> | skipped: <why>", file=sys.stderr)
            return 1
        for k in ("status", "deps", "spec", "gate", "subject"):
            v = getattr(a, k)
            if v is not None: set_field(rm, a.id, k, v); print(f"{a.id}.{k} = {v}")
        render_to_file(a.r); return 0
    if c == "render": print(render_to_file(a.r)); return 0
    if c == "gate":
        g = parse_config(ge_root() / "config.md").gates.get(a.name)
        if not g: print(f"no gate named {a.name} in ge/config.md", file=sys.stderr); return 1
        log_activity(a.r, f"gate {a.name} running"); render_to_file(a.r)  # the page shows the gate while it runs
        try: ok, caps, src, text, why = run_gate(g)
        except re.error as e:
            log_activity(a.r, f"gate {a.name} NO MATCH bad regex {e}"); render_to_file(a.r)
            print(f"NO MATCH {a.name}: bad regex {e}"); return 1
        caught = " ".join(x or "" for x in caps).strip()  # a non-participating group is None, not a string
        detail = " — ".join(x for x in (caught, why) if x)  # why names a floor or a timeout, which no miss can
        log_activity(a.r, f"gate {a.name} {'MATCH' if ok else 'NO MATCH'} {detail}"); render_to_file(a.r)
        print(f"{'MATCH' if ok else 'NO MATCH'} {a.name}: {detail} ({src})".replace(":  (", ": ("))
        if not ok and text.strip():  # the evidence, so an unattended agent need not re-run a long command
            for line in text.splitlines()[-5:]: print("  " + line)
        return 0 if ok else 1
    if c == "guards":
        # flush per line: a guard command that hangs must not sit on the STOP/PAUSE lines already yielded
        for l in guards(a.r, parse_config(ge_root() / "config.md")): print(l, flush=True)
        return 0
    if c == "brief":
        text, code = brief(a.r); print(text)
        if code == 2: print("brief: next.md does not name the ready node; minimal brief built from the row", file=sys.stderr)
        return code
    if c == "pause":
        if not flatten(a.reason):  # an empty first line is a PAUSE the runner cannot act on
            print("pause: a reason is required (human-test | summary <topic> | adjust)", file=sys.stderr); return 1
        pause(a.r, a.reason, a.note); print(f"paused {a.r}: {flatten(a.reason)}"); return 0
    if c == "resume": print(f"resumed {a.r}" if resume(a.r) else f"nothing to resume for {a.r}"); return 0
    if c == "stop": stop(a.r); print(f"STOP written for {a.r}"); return 0
    if c == "open":
        p = render_to_file(a.r); print(p)  # the path first: the render is what /ge-status needs
        try: subprocess.Popen(open_command(p))
        except OSError as e: print(f"rendered; no opener: {e}", file=sys.stderr)
        return 0
    if c == "calls":
        for x in read_calls(a.r)[0]: print(x)
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())
