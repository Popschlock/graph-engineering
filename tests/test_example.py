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
