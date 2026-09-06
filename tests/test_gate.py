import datetime
import subprocess
import time
from pathlib import Path

import ge
from conftest import write_roadmap, ROWS3

REPO = Path(__file__).resolve().parents[1]
# what the shipped `pytest` gate rows must unescape to: a count at the START of a line, and not a line that
# also says failed or error. `(\d+) passed` alone MATCHes `1 failed, 1 passed` — a red suite reading green.
PYTEST_RE = r"(?m)^(\d+) passed(?![^\n]*\b(?:failed|error))"

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

# a second config for the fail-closed paths: a non-participating capture group (the pipe in the cell is
# escaped, as a markdown table demands), a malformed gate regex, a gate that cannot match, a malformed
# guard regex.
EDGES = """# ge config — edges

## Gates
| name | command | success | artifact |
|---|---|---|---|
| alt | python -c "print('GREEN (7)')" | `(?:GREEN \\((\\d+)\\)\\|RED \\((\\d+)\\))` | stdout |
| bad | python -c "print('x')" | `(unclosed` | stdout |
| tail | python -c "print('l1');print('l2');print('l3');print('l4');print('l5');print('l6');print('l7')" | `NEVER` | stdout |

## Guards
| name | command | blocked when |
|---|---|---|
| badguard | python -c "print('x')" | `(unclosed` |
"""

# three gates carrying the SHIPPED pytest regex over the three pytest tails that matter.
PYTEST_GATES = """# ge config — pytest-shaped

## Gates
| name | command | success | artifact |
|---|---|---|---|
| mixed | python -c "print('1 failed, 1 passed in 0.03s')" | `(?m)^(\\d+) passed(?![^\\n]*\\b(?:failed\\|error))` | stdout |
| clean | python -c "print('2 passed in 0.01s')" | `(?m)^(\\d+) passed(?![^\\n]*\\b(?:failed\\|error))` | stdout |
| errored | python -c "print('1 passed, 1 error in 0.03s')" | `(?m)^(\\d+) passed(?![^\\n]*\\b(?:failed\\|error))` | stdout |
"""

def setup(project):
    (project / "ge/config.md").write_text(CONFIG, encoding="utf-8"); return write_roadmap(project, "demo", ROWS3).parent

def setup_edges(project):
    d = setup(project); (project / "ge/config.md").write_text(EDGES, encoding="utf-8"); return d

def git(*args):  # in the fixture's cwd; identity passed in so a bare machine can still commit
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t"] + list(args), capture_output=True, text=True)

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

def test_pytest_gate_regex(project, capsys):
    setup(project); (project / "ge/config.md").write_text(PYTEST_GATES, encoding="utf-8")
    assert ge.main(["gate", "demo", "mixed"]) == 1        # '1 passed' is not at the start of its line
    assert "NO MATCH mixed" in capsys.readouterr().out
    assert ge.main(["gate", "demo", "clean"]) == 0
    assert "MATCH clean: 2" in capsys.readouterr().out
    assert ge.main(["gate", "demo", "errored"]) == 1      # the same line says error
    assert "NO MATCH errored" in capsys.readouterr().out

def test_shipped_pytest_gates_carry_that_regex(project):
    """The cell is escaped for the table (`\\|`); what parse_config hands re.search is what the test above pins."""
    for p in (REPO / "ge/config.md", REPO / "examples/hello-roadmap/ge/config.md"):
        assert ge.parse_config(p).gates["pytest"].success == PYTEST_RE, p

def test_gate_prints_the_artifact_mtime(project, capsys):
    """A MATCH read out of a file written before the work commit is a stale artifact; only the time shows it."""
    setup(project); (project / "logs").mkdir()
    f = project / "logs/e2e_1.log"; f.write_text("SUITE GREEN (42 checked)\n", encoding="utf-8")
    assert ge.main(["gate", "demo", "log"]) == 0
    want = datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")
    out = capsys.readouterr().out
    assert "MATCH log: 42 (" in out and f", {want})" in out
    assert ge.main(["gate", "demo", "echo"]) == 0         # a stdout gate has no file and gains no time
    assert capsys.readouterr().out.strip().endswith("(stdout of python -c \"print('total=3 passed=3 failed=0')\")")

def test_gate_non_participating_capture_group(project, capsys):
    setup_edges(project)
    assert ge.main(["gate", "demo", "alt"]) == 0          # the second group is None, not a string
    assert "MATCH alt: 7" in capsys.readouterr().out

def test_gate_bad_regex(project, capsys):
    setup_edges(project)
    assert ge.main(["gate", "demo", "bad"]) == 1
    assert "NO MATCH bad: bad regex" in capsys.readouterr().out

def test_gate_no_match_prints_the_tail(project, capsys):
    setup_edges(project)
    assert ge.main(["gate", "demo", "tail"]) == 1
    out = capsys.readouterr().out
    assert "NO MATCH tail" in out and "  l7" in out and "  l3" in out and "  l2" not in out  # last 5 of 7

def test_guards(project, capsys):
    d = setup(project)
    (d / "PAUSE").write_text("human-test\ntry the menu\n", encoding="utf-8"); (d / "STOP").write_text("", encoding="utf-8")
    assert ge.main(["guards", "demo"]) == 0
    out = capsys.readouterr().out
    assert "stop: PRESENT" in out and "pause: human-test | try the menu" in out and "guard busy: BLOCKED" in out
    assert "tree: UNKNOWN (git rc=" in out and "tree: clean" not in out   # not a repo: never fail open
    git("init", "-q"); git("add", "-A"); git("commit", "-qm", "init")     # the positive control
    assert ge.main(["guards", "demo"]) == 0 and "tree: clean" in capsys.readouterr().out
    (project / "untracked.txt").write_text("x", encoding="utf-8")
    assert ge.main(["guards", "demo"]) == 0 and "tree: DIRTY" in capsys.readouterr().out

def test_guard_bad_regex_is_an_error_not_ok(project, capsys):
    setup_edges(project)
    assert ge.main(["guards", "demo"]) == 0
    out = capsys.readouterr().out
    assert "guard badguard: ERROR bad regex" in out and "guard badguard: ok" not in out
    assert out.index("stop:") < out.index("guard badguard:")   # STOP is reported before any guard runs

def test_brief_mismatch_and_match(project, capsys):
    d = setup(project); (d / "next.md").write_text("# kickoff: B\n\nwrong node\n", encoding="utf-8")
    assert ge.main(["brief", "demo"]) == 2
    out = capsys.readouterr().out
    assert "# kickoff: A" in out and "docs/plan.md §1" in out and "Project rule one." in out and "Never ask a question" in out
    (d / "next.md").write_text("# kickoff: A\n\nthe real kickoff\n", encoding="utf-8")
    assert ge.main(["brief", "demo"]) == 0 and "the real kickoff" in capsys.readouterr().out

# a floor is a RATCHET on the first capture group; and a five-column table must not break a four-column one.
FLOORS = """# ge config — floors

## Gates
| name | command | success | artifact | floor |
|---|---|---|---|---|
| over | python -c "print('45 passed')" | `(?m)^(\\d+) passed` | stdout | 45 |
| under | python -c "print('44 passed')" | `(?m)^(\\d+) passed` | stdout | 45 |
| nofloor | python -c "print('1 passed')" | `(?m)^(\\d+) passed` | stdout | |
| words | python -c "print('all green')" | `all (\\w+)` | stdout | 3 |
| nogroup | python -c "print('3 passed')" | `passed` | stdout | 3 |
| badfloor | python -c "print('3 passed')" | `(\\d+) passed` | stdout | lots |
"""

def test_gate_floor_is_a_ratchet(project, capsys):
    """`(\\d+) passed` reads a suite that LOST half its tests exactly as green as one that grew."""
    setup(project); (project / "ge/config.md").write_text(FLOORS, encoding="utf-8")
    assert ge.main(["gate", "demo", "over"]) == 0 and "MATCH over: 45 (" in capsys.readouterr().out
    assert ge.main(["gate", "demo", "under"]) == 1
    out = capsys.readouterr().out
    assert "NO MATCH under: 44 — 44 is below the floor of 45" in out
    assert ge.main(["gate", "demo", "nofloor"]) == 0        # an empty floor cell is no floor at all
    assert "MATCH nofloor: 1 (" in capsys.readouterr().out

def test_gate_floor_fails_closed(project, capsys):
    """A floor that cannot be evaluated is a refusal, never a pass: each of these MATCHes its regex."""
    setup(project); (project / "ge/config.md").write_text(FLOORS, encoding="utf-8")
    assert ge.main(["gate", "demo", "words"]) == 1
    assert "the capture 'green' is not a number" in capsys.readouterr().out
    assert ge.main(["gate", "demo", "nogroup"]) == 1
    assert "no capture group to read" in capsys.readouterr().out
    assert ge.main(["gate", "demo", "badfloor"]) == 1
    assert "floor 'lots' is not a whole number" in capsys.readouterr().out

def test_a_four_column_gates_table_still_parses(project):
    """The shipped example keeps four columns on purpose: the positive control for the old shape."""
    setup(project)
    g = ge.parse_config(project / "ge/config.md").gates["echo"]
    assert g.artifact == "stdout" and g.floor == ""
    assert ge.parse_config(REPO / "examples/hello-roadmap/ge/config.md").gates["pytest"].floor == ""

SLOW = """# ge config — slow

## Gates
| name | command | success | artifact |
|---|---|---|---|
| hang | python -c "print('7 passed', flush=True); import time; time.sleep(30)" | `(\\d+) passed` | stdout |

## Guards
| name | command | blocked when |
|---|---|---|
| hangguard | python -c "import time; time.sleep(30)" | `RUNNING` |
"""

def test_a_gate_that_times_out_is_no_match_not_a_match_on_partial_output(project, capsys, monkeypatch):
    """The command prints the pattern and THEN hangs: a kill that kept the partial output and matched it
    would read green off a suite that never finished."""
    setup(project); (project / "ge/config.md").write_text(SLOW, encoding="utf-8")
    monkeypatch.setattr(ge, "GATE_TIMEOUT", 1)
    assert ge.main(["gate", "demo", "hang"]) == 1
    out = capsys.readouterr().out
    assert "NO MATCH hang: the command timed out after 1s" in out and "MATCH hang: 7" not in out
    assert "  7 passed" in out          # the tail proves the pattern WAS in the text and was refused anyway

def test_a_gate_timeout_bounds_the_wall_clock(project, monkeypatch):
    """A shell=True command is a SHELL whose child does the work. Kill only the shell and the child keeps
    the output pipe open, so the read that follows returns when the GRANDCHILD exits — 30 s here, and never
    for a real hang. The NO MATCH above is green either way; only the clock can see this."""
    setup(project); (project / "ge/config.md").write_text(SLOW, encoding="utf-8")
    monkeypatch.setattr(ge, "GATE_TIMEOUT", 1)
    t0 = time.perf_counter(); assert ge.main(["gate", "demo", "hang"]) == 1
    took = time.perf_counter() - t0
    assert took < 15, f"the 30 s grandchild outlived its 1 s timeout: {took:.1f}s"

def test_a_guard_that_times_out_is_an_error_not_ok(project, capsys, monkeypatch):
    """`ok` would dispatch a node. An unattended runner reads ERROR as blocking, which is what a check
    that could not run means."""
    setup(project); (project / "ge/config.md").write_text(SLOW, encoding="utf-8")
    monkeypatch.setattr(ge, "GUARD_TIMEOUT", 1)
    assert ge.main(["guards", "demo"]) == 0
    out = capsys.readouterr().out
    assert "guard hangguard: ERROR timed out after 1s" in out and "guard hangguard: ok" not in out
