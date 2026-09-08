"""What the PACKAGE promises, pinned: the hook's launcher, the two manifests' version, the
directory-install .claudeignore, and the two skills that read `ge.py next`'s stdout."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

def read(rel): return (REPO / rel).read_text(encoding="utf-8")

def hook_entry():
    h = json.loads(read("hooks/hooks.json"))["hooks"]["SessionStart"]
    assert len(h) == 1 and len(h[0]["hooks"]) == 1, "one entry, or the hook prints twice"
    return h[0]["hooks"][0]

def test_hook_falls_back_from_python3_to_python():
    """`python` does not exist on a box whose only interpreter is `python3`. The fallback needs a SHELL,
    and a hook entry is only run through one when it has no `args` array — with `args` it is spawned
    directly and the `||` would be a literal argument to python3."""
    e = hook_entry()
    assert "args" not in e, "an args array makes this exec form: the || would stop being an operator"
    cmd = e["command"]
    assert cmd.index("python3 ") < cmd.index("|| python "), cmd
    assert cmd.count('"${CLAUDE_PLUGIN_ROOT}/hooks/session-start.py"') == 2, cmd
    assert (REPO / "hooks/session-start.py").is_file()

def test_the_two_manifests_carry_the_same_version():
    """The plugin cache is keyed by version: a bump in one file and not the other serves stale code."""
    plugin = json.loads(read(".claude-plugin/plugin.json"))
    market = json.loads(read(".claude-plugin/marketplace.json"))
    entries = [p for p in market["plugins"] if p["name"] == plugin["name"]]
    assert len(entries) == 1 and entries[0]["version"] == plugin["version"] == "0.3.1"

def test_claudeignore_names_the_caches_and_never_the_package():
    """A directory source is installed by copying the checkout. Whether the installer honours this file is
    undocumented, so the test pins its CONTENT: the caches in, and everything spec section 9 ships out."""
    lines = [l.strip() for l in read(".claudeignore").split("\n") if l.strip() and not l.startswith("#")]
    for noise in (".git/", "__pycache__/", ".pytest_cache/", "*.pyc", "*.log"):
        assert noise in lines, noise
    shipped = ("skills", "agents", "hooks", "scripts", "tests", "examples", "docs", "README.md", ".claude-plugin")
    for l in lines:
        assert not any(l.strip("/*").startswith(s) for s in shipped), f".claudeignore would drop {l}"

def test_build_roadmap_reaches_the_config_and_init_it_writes():
    """A flag with no caller is a mechanism nothing can get to. /ge-build-roadmap is the ONLY skill that
    writes a fresh ge/config.md and the only caller of `init`, so the floor column and --subject live or
    die here."""
    t = read("skills/ge-build-roadmap/SKILL.md")
    assert "| name | command | success | artifact | floor |" in t, "the config template it writes"
    assert "floor" in t and "ratchet" in t, "and it has to ask the human for the number"
    assert '--goal "<goal>" --subject "<subject>"' in t, "init's subject has no other caller"

def test_build_and_revise_are_told_about_nexts_stderr_lines():
    """`ge.py next` writes `in progress:` lines on stderr. /ge-run-roadmap already knew; a skill that reads
    the id off a 2>&1 capture and does not would take `in progress:` for the node's id."""
    for skill in ("ge-build-roadmap", "ge-revise-roadmap", "ge-run-roadmap"):
        t = read(f"skills/{skill}/SKILL.md")
        assert "stderr" in t.lower() and "in progress:" in t, skill
        assert "stranded" in t, skill
