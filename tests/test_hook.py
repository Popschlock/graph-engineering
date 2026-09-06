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

def run_hook(project):
    """The hook against <project>, its stdout decoded as UTF-8 (the hook reconfigures stdout)."""
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"cwd": str(project)}),
                          capture_output=True, encoding="utf-8", cwd=project)

def test_hook_reports_a_bad_roadmap_and_keeps_going(project):
    write_roadmap(project, "demo", [("A", "first", "in progress (s1)", "", "docs/plan.md §1", "unit")])
    bad = project / "ge" / "aaa"; bad.mkdir(parents=True)          # sorts BEFORE demo, so it is read first
    (bad / "roadmap.md").write_bytes(b"# \xff\xfe not utf-8\n")    # parse_roadmap raises UnicodeDecodeError
    p = run_hook(project)
    assert p.returncode == 0
    assert "ge: could not read roadmap aaa (" in p.stdout          # named, not blamed on ./ge
    assert "ge: could not read ./ge" not in p.stdout
    assert "ge: roadmap demo is in progress (A), 0/1 done, 0 open call(s)" in p.stdout

def test_hook_prints_a_non_latin_pause_reason(project):
    (write_roadmap(project, "demo", ROWS3).parent / "PAUSE").write_text("待测试\n", encoding="utf-8")
    p = run_hook(project)
    assert p.returncode == 0
    assert "ge: roadmap demo is paused: 待测试, 0/3 done, 0 open call(s) — /ge-status demo" in p.stdout
