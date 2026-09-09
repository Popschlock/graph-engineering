"""0.4: tasks run side by side. Locks say what a task holds; dispatchable says what can start now; commit
serialises git and adds only the paths it is given; kickoffs are one file per ready task."""
import json, os, re, subprocess, sys, threading, time
from pathlib import Path
import ge
from conftest import write_roadmap, ROWS3

def rows8(*rows):
    """(id, subject, status, deps, spec, gate, commit, locks)"""
    return [list(r) + [""] * (8 - len(r)) for r in rows]

def write8(root, r, rows, phases=None):
    d = root / "ge" / r; d.mkdir(parents=True, exist_ok=True)
    ph = phases or [("P1", "phase", " ".join(x[0] for x in rows))]
    text = f"# {r} — eight columns\n\n## Goal\ngo\n\n## Phases\n" + "".join(f"### {p} — {t}\n{b}\n\n" for p, t, b in ph)
    text += "## Tasks\n| id | subject | status | deps | spec | gate | commit | locks |\n|---|---|---|---|---|---|---|---|\n"
    for row in rows8(*rows): text += "| " + " | ".join(row) + " |\n"
    text += "\n## Notes\n"; (d / "roadmap.md").write_text(text, encoding="utf-8"); return d

READS = [("R1", "READ: the menu", "open", "", "s", ""), ("R2", "READ: the lobby", "open", "", "s", ""),
         ("R3", "READ: the map", "open", "", "s", ""), ("T1", "settings button", "open", "R1", "s", "build", "", "editor"),
         ("T2", "minimap clamp", "open", "R3", "s", "build", "", "build"), ("T3", "engine flames", "open", "R2", "s", "", "", "editor"),
         ("T4", "the write-up", "open", "T1, T2, T3", "s", "")]

def test_seven_and_eight_column_roadmaps_both_load(project):
    write_roadmap(project, "old", ROWS3); rm = ge.load("old")
    assert [n.locks for n in rm.nodes] == [[], [], []] and ge.effective_locks(rm.nodes[0]) == ["tree"]
    write8(project, "new", READS); rm = ge.load("new"); n = ge.by_id(rm)
    assert n["T1"].locks == ["editor"] and ge.effective_locks(n["R1"]) == [] and ge.effective_locks(n["T4"]) == ["tree"]
    ge.main(["set", "new", "T4", "--locks", "none"]); assert ge.effective_locks(ge.by_id(ge.load("new"))["T4"]) == []
    ge.main(["set", "new", "T4", "--locks", "db, editor"]); assert ge.by_id(ge.load("new"))["T4"].locks == ["db", "editor"]
    head = [l for l in (project / "ge/new/roadmap.md").read_text(encoding="utf-8").split("\n") if l.startswith("| id |")][0]
    assert head.rstrip().endswith("| locks |")

def test_add_writes_locks_and_the_old_table_grows_a_column(project):
    write_roadmap(project, "old", ROWS3)
    assert ge.main(["add", "old", "--id", "D", "--subject", "fourth", "--deps", "C", "--locks", "editor"]) == 0
    n = ge.by_id(ge.load("old"))["D"]; assert n.locks == ["editor"]
    ge.main(["set", "old", "A", "--status", "in progress (s1)"])  # a seven-column row rewritten carries eight cells
    line = [l for l in (project / "ge/old/roadmap.md").read_text(encoding="utf-8").split("\n") if l.startswith("| A |")][0]
    assert line.count("|") == 9

def test_dispatchable_respects_locks_and_the_cap(project, capsys):
    write8(project, "p", READS)
    assert [n.id for n in ge.dispatchable(ge.load("p"), 3)] == ["R1", "R2", "R3"]  # three reads share nothing
    assert [n.id for n in ge.dispatchable(ge.load("p"), 2)] == ["R1", "R2"]
    for x in ("R1", "R2", "R3"): ge.main(["close", "p", x, "abc1234", "ok"])
    ids = [n.id for n in ge.dispatchable(ge.load("p"), 5)]
    assert ids == ["T1", "T2"]  # T3 shares `editor` with T1; T4 waits on deps
    ge.main(["start", "p", "T1", "s1"])
    assert [n.id for n in ge.dispatchable(ge.load("p"), 5)] == ["T2"]
    assert ge.main(["start", "p", "T3", "s2"]) == 1  # editor is held
    assert "editor" in capsys.readouterr().err and ge.by_id(ge.load("p"))["T3"].status == "open"
    assert ge.main(["start", "p", "T2", "s2"]) == 0
    assert ge.dispatchable(ge.load("p"), 5) == []
    capsys.readouterr(); ge.main(["dispatchable", "p"]); out, err = capsys.readouterr()
    assert out.strip() == "none" and "running: T1 (s1) holds editor" in err and "running: T2 (s2) holds build" in err

def test_dispatchable_counts_running_lanes_against_the_cap(project):
    write8(project, "p", READS); ge.main(["start", "p", "R1", "s1"])
    assert [n.id for n in ge.dispatchable(ge.load("p"), 2)] == ["R2"]

def test_tree_is_exclusive_by_default(project):
    write_roadmap(project, "old", [("A", "first", "open", "", "s", "unit"), ("B", "second", "open", "", "s", "unit")])
    assert [n.id for n in ge.dispatchable(ge.load("old"), 3)] == ["A"]
    ge.main(["start", "old", "A", "s1"]); assert ge.dispatchable(ge.load("old"), 3) == []

def test_tree_fights_every_lock_but_not_a_read(project):
    """`tree` means the whole working tree: a task holding it cannot run beside a task holding `cli`, and a task
    holding `cli` cannot start beside it. A READ: task holds nothing and runs beside either."""
    rows = [("A", "edits everything", "open", "", "s", "", "", "tree"), ("B", "the cli", "open", "", "s", "", "", "cli"),
            ("R", "READ: notes", "open", "", "s", "")]
    write8(project, "p", rows)
    assert [n.id for n in ge.dispatchable(ge.load("p"), 5)] == ["A", "R"]
    ge.main(["start", "p", "B", "s1"])  # B first instead
    assert ge.collision(ge.load("p"), ge.by_id(ge.load("p"))["A"]) == ["B (cli)"]
    assert [n.id for n in ge.dispatchable(ge.load("p"), 5)] == ["R"]
    assert ge.clash(["tree"], ["tree"]) == ["tree"] and ge.clash([], ["tree"]) == [] and ge.clash(["a"], ["b"]) == []

def test_max_parallel_comes_from_config(project):
    write8(project, "p", READS)
    (project / "ge/config.md").write_text("# c\n\n## Cadence\nreview every: 2\nmax parallel: 1\n", encoding="utf-8")
    cfg = ge.parse_config(project / "ge/config.md"); assert cfg.max_parallel == 1 and cfg.review_every == 2
    assert ge.parse_config(project / "ge/nope.md").max_parallel == 3

def test_unlocked_names_the_nodes_a_close_made_ready(project, capsys):
    write8(project, "p", READS)
    ge.main(["close", "p", "R1", "a1", "ok"]); ge.main(["close", "p", "R2", "a2", "ok"])
    assert [n.id for n in ge.unlocked(ge.load("p"), "R2")] == ["T3"]
    for x in ("R3", "T1", "T2"): ge.main(["close", "p", x, "a3", "ok"])
    ge.main(["close", "p", "T3", "a4", "ok"]); capsys.readouterr()
    ge.main(["unlocked", "p", "T3"]); assert capsys.readouterr().out.strip() == "T4"

def test_brief_reads_the_kickoff_file_then_next_md_then_builds_one(project, capsys):
    d = write8(project, "p", READS); (d / "kickoffs").mkdir()
    (d / "kickoffs" / "R2.md").write_text("# kickoff: R2\n\nRead the lobby.\n", encoding="utf-8")
    (d / "next.md").write_text("# kickoff: R1\n\nRead the menu.\n", encoding="utf-8")
    t, code = ge.brief("p", "R2"); assert code == 0 and "Read the lobby." in t and "you hold: none" in t
    t, code = ge.brief("p", "R1"); assert code == 0 and "Read the menu." in t
    t, code = ge.brief("p", "R3"); assert code == 2 and "kickoff: R3" in t and "built from the roadmap row" in t
    ge.main(["close", "p", "R1", "a1", "ok"]); t, code = ge.brief("p", "T1"); assert "you hold: editor" in t
    assert ge.main(["brief", "p", "R2"]) == 0 and "Read the lobby." in capsys.readouterr().out
    assert ge.main(["brief", "p", "T4"]) == 1  # not ready

def git(*args, cwd): return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)

def repo(project):
    git("init", "-q", cwd=project); git("config", "user.email", "t@t", cwd=project); git("config", "user.name", "t", cwd=project)
    write8(project, "p", READS); git("add", "-A", cwd=project); git("commit", "-q", "-m", "init", cwd=project)

def test_commit_adds_only_the_paths_it_is_given(project, capsys):
    repo(project)
    (project / "mine.txt").write_text("mine\n", encoding="utf-8"); (project / "theirs.txt").write_text("theirs\n", encoding="utf-8")
    assert ge.main(["commit", "p", "R1", "-m", "r1 work", "mine.txt"]) == 0
    h = capsys.readouterr().out.strip(); assert re.match(r"^[0-9a-f]{7,40}$", h)
    shown = git("show", "--stat", "--format=%s", h, cwd=project).stdout
    assert "mine.txt" in shown and "theirs.txt" not in shown and shown.startswith("r1 work")
    assert "theirs.txt" in git("status", "--porcelain", cwd=project).stdout and not (project / "ge/.commit.lock").exists()

def test_close_commit_carries_the_ge_files_and_the_kickoffs(project, capsys):
    repo(project); d = project / "ge/p"
    ge.main(["start", "p", "R1", "s1"]); ge.main(["close", "p", "R1", "abc1234", "ok"])
    (d / "kickoffs").mkdir(exist_ok=True); (d / "kickoffs" / "T1.md").write_text("# kickoff: T1\n", encoding="utf-8")
    (project / "stray.txt").write_text("x", encoding="utf-8")
    assert ge.main(["commit", "p", "R1", "--close", "-m", "ge(p): close R1"]) == 0
    shown = git("show", "--stat", "--format=", capsys.readouterr().out.strip().split("\n")[-1], cwd=project).stdout
    for f in ("roadmap.md", "ledger.md", "status.html", "kickoffs/T1.md"): assert f in shown, f
    assert "stray.txt" not in shown and "status.js" not in shown

def test_commit_waits_for_the_lock_and_two_commits_both_land(project, capsys):
    repo(project); lock = project / "ge/.commit.lock"; lock.mkdir()
    (project / "a.txt").write_text("a", encoding="utf-8")
    def release(): time.sleep(0.4); lock.rmdir()
    threading.Thread(target=release).start(); t0 = time.time()
    assert ge.main(["commit", "p", "R1", "-m", "a", "a.txt"]) == 0 and time.time() - t0 >= 0.3
    (project / "b.txt").write_text("b", encoding="utf-8"); (project / "c.txt").write_text("c", encoding="utf-8")
    args = lambda f: [sys.executable, str(Path(ge.__file__)), "commit", "p", "R1", "-m", f, f + ".txt"]
    ps = [subprocess.Popen(args(f), cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for f in ("b", "c")]
    outs = [p.communicate(timeout=60) for p in ps]
    assert all(p.returncode == 0 for p in ps), outs
    log = git("log", "--format=%s", "-3", cwd=project).stdout.split()
    assert set(log[:2]) == {"b", "c"}

def test_commit_gives_up_when_the_lock_never_clears(project, capsys, monkeypatch):
    repo(project); (project / "ge/.commit.lock").mkdir(); monkeypatch.setattr(ge, "COMMIT_WAIT", 0.3)
    (project / "a.txt").write_text("a", encoding="utf-8")
    assert ge.main(["commit", "p", "R1", "-m", "a", "a.txt"]) == 1 and "commit.lock" in capsys.readouterr().err

def test_collide_serialises_the_retry_and_writes_the_row(project):
    write8(project, "p", READS)
    assert ge.main(["collide", "p", "T1", "T3"]) == 0
    assert ge.by_id(ge.load("p"))["T1"].locks == ["tree"]
    row = ge.read_ledger("p")[-1]; assert row[3] == "revised" and row[4].startswith("collision: T1 with T3")

def test_start_records_the_locks_held(project):
    write8(project, "p", READS); ge.main(["start", "p", "T1", "s1"])
    assert ge.read_ledger("p")[-1][4] == "s1 holds editor"

def test_guards_report_the_lanes(project, capsys):
    write8(project, "p", READS); ge.main(["start", "p", "R1", "s1"]); ge.main(["start", "p", "T1", "s2"])
    lines = list(ge.guards("p", ge.Config()))
    assert "lanes: 2 in progress, holding editor" in lines

def test_next_still_reports_stranded_but_dispatchable_does_not(project, capsys):
    write8(project, "p", READS); ge.main(["start", "p", "R1", "s1"]); capsys.readouterr()
    ge.main(["next", "p"]); assert "in progress: R1" in capsys.readouterr().err
    ge.main(["dispatchable", "p"]); err = capsys.readouterr().err
    assert "in progress:" not in err and "running: R1 (s1) holds none" in err

def test_close_removes_the_consumed_kickoff(project):
    d = write8(project, "p", READS); (d / "kickoffs").mkdir(); (d / "kickoffs" / "R1.md").write_text("# kickoff: R1\n", encoding="utf-8")
    ge.main(["close", "p", "R1", "a1", "ok"]); assert not (d / "kickoffs" / "R1.md").exists()

def test_dashboard_shows_every_running_lane(project):
    d = write8(project, "p", READS); ge.main(["start", "p", "R1", "s1"]); ge.main(["start", "p", "R2", "s2"])
    html = (d / "status.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r'<script id="ge-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    assert data["counts"]["in progress"] == 2 and {n["id"] for n in data["nodes"] if n["kind"] == "in progress"} == {"R1", "R2"}
    assert [n for n in data["nodes"] if n["id"] == "T1"][0]["locks"] == ["editor"] and data["max_parallel"] == 3
