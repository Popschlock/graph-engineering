import ge
from conftest import write_roadmap, ROWS3

def test_render_contains_ids_colours_refresh(project):
    rows = [("A", "first", "done abc1234", "", "s", "unit", "abc1234"), ("B", "second", "open", "A", "s", "unit"),
            ("C", "third", "skipped: later", "A", "s", "")]
    d = write_roadmap(project, "demo", rows).parent
    ge.append_ledger("demo", "A", "done", "unit 12/12", "abc1234", "s1")
    (d / "calls.md").write_text("# calls\n\n## Open\n* pick blue or green\n\n## Decided\n", encoding="utf-8")
    html = ge.render(ge.load("demo"), ge.Config(), ge.read_ledger("demo"), ge.read_calls("demo")[0])
    for nid in ("A", "B", "C"): assert f">{nid}<" in html
    assert 'fill="#22c55e"' in html and 'fill="#3b82f6"' in html and "url(#hatch)" in html
    assert '<meta http-equiv="refresh" content="60">' in html
    assert "pick blue or green" in html and "unit 12/12" in html and "marker-end" in html

def test_layout_depth_and_bands(project):
    pos, bands = ge.layout(ge.parse_roadmap(write_roadmap(project, "demo", ROWS3)))
    assert pos["A"][0] == 0 and pos["B"][0] == 1 and pos["C"][0] == 2 and bands == [("P1", 0, 1)]

def test_close_writes_status_html(project):
    write_roadmap(project, "demo", ROWS3); ge.main(["close", "demo", "A", "abc1234", "ok"])
    assert (project / "ge/demo/status.html").exists()

def test_render_escapes_gate_names(project):
    rm = ge.parse_roadmap(write_roadmap(project, "demo", ROWS3))
    cfg = ge.Config(gates={"x": ge.Gate(name="<x>", command="c", success="", artifact="stdout")})
    html = ge.render(rm, cfg, [], [])
    assert "&lt;x&gt;" in html and "<x>" not in html
