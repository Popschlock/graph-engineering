import json, subprocess, sys, time
from pathlib import Path
from conftest import write_roadmap, ROWS3
REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "hooks" / "session-start.py"

def test_hook_prints_mid_flight_roadmaps(project):
    (write_roadmap(project, "demo", ROWS3).parent / "PAUSE").write_text("human-test\n", encoding="utf-8")
    t = time.perf_counter()
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"cwd": str(project)}), capture_output=True, text=True, cwd=project)
    assert p.returncode == 0 and time.perf_counter() - t < 1.5  # spec: under 1 s; margin for a cold interpreter
    assert "ge: demo is paused (human-test), 0 of 3 tasks done. /ge-status demo" in p.stdout

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
    assert "ge: demo is working on A, 0 of 1 tasks done. /ge-status demo" in p.stdout

def test_hook_prints_a_non_latin_pause_reason(project):
    (write_roadmap(project, "demo", ROWS3).parent / "PAUSE").write_text("待测试\n", encoding="utf-8")
    p = run_hook(project)
    assert p.returncode == 0
    assert "ge: demo is paused (待测试), 0 of 3 tasks done. /ge-status demo" in p.stdout

def hooks_json_command():
    """The one SessionStart command string the plugin ships, with the plugin root filled in."""
    cfg = json.loads((REPO / "hooks/hooks.json").read_text(encoding="utf-8"))
    entry = cfg["hooks"]["SessionStart"][0]["hooks"][0]
    return entry["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(REPO))

def test_the_shipped_hook_command_runs_through_a_shell(project):
    """`python3 <script> || python <script>` is a fallback only when a SHELL reads it, and only a hook entry
    with no `args` array gets one. test_package pins the SHAPE; this runs the shipped string end to end.
    Either name being absent is the interesting case, and it is the case on any box with just one of them."""
    (write_roadmap(project, "demo", ROWS3).parent / "PAUSE").write_text("human-test\n", encoding="utf-8")
    p = subprocess.run(hooks_json_command(), shell=True, input=json.dumps({"cwd": str(project)}),
                       capture_output=True, encoding="utf-8", cwd=project)
    assert p.returncode == 0, p.stderr
    assert "ge: demo is paused (human-test), 0 of 3 tasks done" in p.stdout
    assert p.stdout.count("ge: demo is") == 1, "|| short-circuits: the script runs once, not twice"
