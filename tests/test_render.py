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

def test_render_draws_the_hold_banner(project):
    """A graph of green nodes that has quietly stopped dispatching looks exactly like one still running."""
    d = write_roadmap(project, "demo", ROWS3).parent
    assert ge.hold_line("demo") == ""
    assert 'class="hold"' not in ge.render_to_file("demo").read_text(encoding="utf-8")
    (d / "PAUSE").write_text("human-test\ntry the menu\n", encoding="utf-8")
    html = ge.render_to_file("demo").read_text(encoding="utf-8")
    assert "PAUSED: human-test — try the menu" in html and 'class="hold"' in html
    (d / "STOP").write_text("", encoding="utf-8")           # STOP wins: it dispatches nothing either way
    html = ge.render_to_file("demo").read_text(encoding="utf-8")
    assert "STOPPED" in html and "PAUSED" not in html
    (d / "STOP").unlink(); (d / "PAUSE").unlink()
    assert 'class="hold"' not in ge.render_to_file("demo").read_text(encoding="utf-8")

def test_render_escapes_a_pause_reason(project):
    """The reason is whatever the human typed at /ge-pause-roadmap."""
    d = write_roadmap(project, "demo", ROWS3).parent
    (d / "PAUSE").write_text("<script>alert(1)</script>\n", encoding="utf-8")
    html = ge.render_to_file("demo").read_text(encoding="utf-8")
    assert "&lt;script&gt;" in html and "<script>" not in html
