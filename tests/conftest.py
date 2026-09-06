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
