"""The README is for a first-time reader. The wlah checker grades it for the marks of machine writing;
strict NATURAL is the bar, and the test skips where wlah is not on this machine."""
import glob, importlib.util, sys
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[1]

def wlah():
    home = Path.home() / ".claude" / "plugins" / "cache" / "wlah" / "wlah"
    for c in [Path(r"C:\AI\Wlah\scripts\wlah_check.py")] + sorted(map(Path, glob.glob(str(home / "*" / "scripts" / "wlah_check.py"))), reverse=True):
        if c.is_file():
            spec = importlib.util.spec_from_file_location("wlah_check", c); m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m); return m
    return None

@pytest.mark.parametrize("path", ["README.md"])
def test_the_readme_reads_as_a_person_wrote_it(path):
    wc = wlah()
    if wc is None: pytest.skip("wlah is not installed here")
    r = wc.check((REPO / path).read_text(encoding="utf-8"), strict=True, with_unslop=False)
    assert r["grade"] == "NATURAL", [(f["line"], f["tell"], f["text"]) for f in r["findings"]]
    long = [s for s in wc.sentences(wc.strip_markup((REPO / path).read_text(encoding="utf-8"))) if len(s.split()) > 32]
    assert not long, long
