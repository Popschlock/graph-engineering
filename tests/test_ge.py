import os
import re
import subprocess
import sys
from pathlib import Path
import pytest
import ge
from conftest import write_roadmap, ROWS3

GE_PY = Path(__file__).resolve().parents[1] / "scripts" / "ge.py"

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
    assert ge.main(["add", "demo", "--id", "D", "--subject", "a | piped subject", "--spec", "s4", "--gate", "unit"]) == 0
    assert ge.by_id(ge.load("demo"))["D"].subject == "a | piped subject"

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

def test_usage_error_exits_1(project, capsys):
    with pytest.raises(SystemExit) as e:
        ge.main(["nosuchcmd"])
    assert e.value.code == 1
    assert "nosuchcmd" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        ge.main(["node", "demo"])  # missing the <id> positional
    assert e.value.code == 1

def test_bad_root_exits_1(project, capsys):
    assert ge.main(["--root", str(project / "definitely-missing"), "next", "demo"]) == 1
    assert "not found" in capsys.readouterr().err

CALLS_WITH_ONE_OPEN = """# calls

## Open
- a real call

## Decided
"""

def test_init_keeps_an_existing_ledger_and_calls(project):
    ge.append_ledger("demo", "-", "review", "logged before the roadmap existed")
    ge.wtext(ge.rdir("demo") / "calls.md", CALLS_WITH_ONE_OPEN)
    assert ge.main(["init", "demo", "--goal", "ship it"]) == 0
    assert [r[3] for r in ge.read_ledger("demo")] == ["review"]
    assert ge.read_calls("demo")[0] == ["a real call"]

def test_add_then_set_on_one_roadmap(project):
    write_roadmap(project, "demo", ROWS3)
    rm = ge.load("demo")
    ge.add_node(rm, ge.Node("X", "inserted", "open", ["A"], "sx", ["unit"], ""), after="A")
    ge.set_field(rm, "C", "subject", "third!")
    assert [n.id for n in rm.nodes] == ["A", "X", "B", "C"]
    back = ge.load("demo")
    assert [n.id for n in back.nodes] == ["A", "X", "B", "C"]
    assert ge.by_id(back)["C"].subject == "third!" and ge.by_id(back)["B"].subject == "second"

def test_agent_frontmatter():
    from pathlib import Path
    want = {"ge-task": ("opus", "xhigh", True), "ge-reader": ("fable", "high", True),
            "ge-verifier": ("opus", "xhigh", False), "ge-reviewer": ("fable", "high", True)}
    for name, (model, effort, mem) in want.items():
        head = (Path(__file__).resolve().parents[1] / "agents" / f"{name}.md").read_text(encoding="utf-8").split("---")[1]
        assert f"name: {name}" in head and f"model: {model}" in head and f"effort: {effort}" in head
        assert ("memory: project" in head) == mem

def test_agent_frontmatter_is_yaml():
    """A head that does not parse is an agent no loader can read; substrings cannot see that."""
    from pathlib import Path
    yaml = pytest.importorskip("yaml")  # dev-only; ge.py and the plugin stay stdlib
    want = {"ge-task": ("opus", "xhigh", True), "ge-reader": ("fable", "high", True),
            "ge-verifier": ("opus", "xhigh", False), "ge-reviewer": ("fable", "high", True)}
    for name, (model, effort, mem) in want.items():
        head = (Path(__file__).resolve().parents[1] / "agents" / f"{name}.md").read_text(encoding="utf-8").split("---")[1]
        fm = yaml.safe_load(head)
        assert fm["name"] == name and fm["model"] == model and fm["effort"] == effort
        assert ("memory" in fm) == mem and fm["description"].strip()

def test_pause_resume_stop(project, capsys):
    write_roadmap(project, "demo", ROWS3); d = project / "ge/demo"
    assert ge.main(["pause", "demo", "summary lighting", "what changed in lighting"]) == 0
    assert (d / "PAUSE").read_text(encoding="utf-8") == "summary lighting\nwhat changed in lighting\n"
    assert ge.pause_state("demo") == ("summary lighting", "what changed in lighting")
    assert ge.read_ledger("demo")[-1][3] == "paused summary lighting"
    assert ge.main(["stop", "demo"]) == 0 and (d / "STOP").exists()
    assert ge.main(["resume", "demo"]) == 0 and not (d / "PAUSE").exists() and not (d / "STOP").exists()
    assert ge.read_ledger("demo")[-1][3] == "resumed"
    rows = len(ge.read_ledger("demo")); capsys.readouterr()  # drain, then resume an idle roadmap
    assert ge.main(["resume", "demo"]) == 0
    assert capsys.readouterr().out.strip() == "nothing to resume for demo"
    assert len(ge.read_ledger("demo")) == rows  # no hold was lifted, so no `resumed` row

def test_open_command_and_calls(project, capsys):
    assert ge.open_command("x.html", "win32") == ["cmd", "/c", "start", "", "x.html"]
    assert ge.open_command("x.html", "darwin") == ["open", "x.html"]
    assert ge.open_command("x.html", "linux") == ["xdg-open", "x.html"]
    d = write_roadmap(project, "demo", ROWS3).parent
    (d / "calls.md").write_text("# calls\n\n## Open\n* blue or green\n\n## Decided\n* red\n", encoding="utf-8")
    assert ge.main(["calls", "demo"]) == 0 and capsys.readouterr().out.strip() == "blue or green"

def test_brief_rule_4_blocks_on_a_check_that_could_not_run(project, capsys):
    """A guards line that failed closed must block the task agent too; the brief is where it reads that."""
    write_roadmap(project, "demo", ROWS3)
    assert ge.main(["brief", "demo"]) == 2
    rules = capsys.readouterr().out.split("---\n")[0]
    assert "tree: UNKNOWN" in rules and "guard <name>: ERROR" in rules
    assert "blocked: guard tree" in rules and "blocked: guard <name>" in rules

def test_open_renders_then_launches(project, capsys, monkeypatch):
    """/ge-status step 3 runs this branch; stub Popen so the suite itself launches nothing."""
    write_roadmap(project, "demo", ROWS3)
    seen = []
    monkeypatch.setattr(ge.subprocess, "Popen", lambda argv, *a, **k: seen.append(argv))
    assert ge.main(["open", "demo"]) == 0
    html = project / "ge/demo/status.html"
    assert html.is_file() and capsys.readouterr().out.strip() == str(html)
    assert seen == [ge.open_command(html)]

def test_open_still_renders_when_there_is_no_opener(project, capsys, monkeypatch):
    """No xdg-open on the box is not a failed status: /ge-status needs the render, not the window."""
    write_roadmap(project, "demo", ROWS3)
    def boom(argv, *a, **k): raise FileNotFoundError(2, "No such file or directory", argv[0])
    monkeypatch.setattr(ge.subprocess, "Popen", boom)
    assert ge.main(["open", "demo"]) == 0
    out, err = capsys.readouterr()
    html = project / "ge/demo/status.html"
    assert html.is_file() and out.strip() == str(html) and "no opener" in err

def test_subprocess_stdout_is_utf8(tmp_path):
    """The in-process suite never meets the console's codec. A real child with a narrow PYTHONIOENCODING is the
    positive control: without main()'s reconfigure it dies on the first '≥' of a subject."""
    write_roadmap(tmp_path, "demo", [("A", "waves ≥ 3 per grade", "open", "", "docs/plan.md §1", "unit")])
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    p = subprocess.run([sys.executable, str(GE_PY), "next", "demo"], cwd=str(tmp_path), capture_output=True, env=env)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert "waves ≥ 3 per grade" in p.stdout.decode("utf-8")

def test_next_says_a_stranded_node_on_stderr(project, capsys):
    """A node left `in progress` by a session that died is said every time, and never on the line the runner parses."""
    write_roadmap(project, "demo", [("A", "first", "in progress (s1)", "", "s", "unit"),
                                    ("B", "second", "open", "", "s", "unit")])
    assert ge.main(["next", "demo"]) == 0
    out, err = capsys.readouterr()
    assert out.strip() == "B | second | unit" and err.strip() == "in progress: A — in progress (s1)"

def test_second_close_writes_nothing(project, monkeypatch):
    """An idempotent close is a no-op: status.html's generated-at stamp would otherwise dirty a committed file."""
    write_roadmap(project, "demo", ROWS3)
    assert ge.main(["close", "demo", "A", "abc1234", "unit=3; first"]) == 0
    html = project / "ge/demo/status.html"; before = html.read_bytes()
    monkeypatch.setattr(ge, "render", lambda *a, **k: "<html>a second render</html>")  # would be visible if it ran
    assert ge.main(["close", "demo", "A", "abc1234", "unit=3; again"]) == 0
    assert html.read_bytes() == before and len(ge.read_ledger("demo")) == 1

def test_validate_reports_a_missing_tasks_section(project, capsys):
    """0 nodes reads like an empty table; a roadmap with no `## Tasks` heading is a different fault."""
    d = project / "ge/demo"; d.mkdir(parents=True)
    (d / "roadmap.md").write_text("# demo — no table\n\n## Goal\nship it\n\n## Notes\n", encoding="utf-8")
    assert "no ## Tasks section" in ge.validate(ge.load("demo"))
    assert ge.main(["validate", "demo"]) == 2 and "no ## Tasks section" in capsys.readouterr().out

def test_set_refuses_a_bad_status(project, capsys):
    write_roadmap(project, "demo", ROWS3)
    assert ge.main(["set", "demo", "A", "--status", "opened"]) == 1
    assert "accepted:" in capsys.readouterr().err
    assert ge.by_id(ge.load("demo"))["A"].status == "open"
    assert ge.main(["set", "demo", "B", "--status", "done"]) == 1          # `done` without a hash is not a status
    assert ge.by_id(ge.load("demo"))["B"].status == "open"
    assert ge.main(["set", "demo", "B", "--status", "nope", "--subject", "changed"]) == 1
    assert ge.by_id(ge.load("demo"))["B"].subject == "second"              # nothing half-applied beside it
    assert ge.main(["set", "demo", "C", "--status", "skipped: later"]) == 0
    assert ge.by_id(ge.load("demo"))["C"].status == "skipped: later"

def test_pause_refuses_an_empty_reason_and_flattens_the_note(project, capsys):
    write_roadmap(project, "demo", ROWS3)
    assert ge.main(["pause", "demo", "  "]) == 1
    assert "reason is required" in capsys.readouterr().err
    assert not (project / "ge/demo/PAUSE").exists() and ge.read_ledger("demo") == []
    assert ge.main(["pause", "demo", "summary lighting", "line one\nline two"]) == 0
    assert (project / "ge/demo/PAUSE").read_text(encoding="utf-8") == "summary lighting\nline one line two\n"
    assert ge.pause_state("demo") == ("summary lighting", "line one line two")

def test_init_over_an_existing_roadmap_exits_1(project, capsys):
    assert ge.main(["init", "demo", "--goal", "ship it"]) == 0
    assert ge.main(["init", "demo", "--goal", "ship it again"]) == 1
    assert "exists:" in capsys.readouterr().err
