"""0.3: the live dashboard. The first production run reported a page that had never once shown a node in
progress: `start` wrote the row and nothing rendered until `close` painted it green."""
import json, re
import ge
from conftest import write_roadmap, ROWS3

def data_of(html):
    m = re.search(r'<script id="ge-data" type="application/json">(.*?)</script>', html, re.S)
    assert m, "no embedded data block"
    return json.loads(m.group(1))

def node(data, nid): return next(n for n in data["nodes"] if n["id"] == nid)

def test_start_renders_amber_and_writes_a_started_row(project):
    write_roadmap(project, "demo", ROWS3)
    assert ge.main(["start", "demo", "A", "s1"]) == 0
    d = project / "ge/demo"
    assert (d / "status.html").exists() and (d / "status.js").exists()
    a = node(data_of((d / "status.html").read_text(encoding="utf-8")), "A")
    assert a["kind"] == "in progress" and a["session"] == "s1" and a["started"]
    js = (d / "status.js").read_text(encoding="utf-8")
    assert js.startswith("geUpdate(") and js.rstrip().endswith(");")
    rows = ge.read_ledger("demo")
    assert [r[3] for r in rows] == ["started"] and rows[0][2] == "A" and rows[0][4] == "s1"
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", rows[0][0])

def test_ledger_verb_hides_started_rows_unless_all(project, capsys):
    """One row per dispatch would push the previous done row out of the windows the agents read."""
    write_roadmap(project, "demo", ROWS3)
    ge.main(["start", "demo", "A", "s1"]); ge.main(["close", "demo", "A", "abc1234", "unit=3; first"])
    capsys.readouterr(); ge.main(["ledger", "demo", "5"]); out = capsys.readouterr().out
    assert "started" not in out and "| done |" in out
    ge.main(["ledger", "demo", "5", "--all"]); out = capsys.readouterr().out
    assert "| started |" in out and "| done |" in out

def test_every_state_change_rewrites_status_js(project):
    d = write_roadmap(project, "demo", ROWS3).parent
    verbs = [["start", "demo", "A", "s1"], ["close", "demo", "A", "abc1234", "unit=3; ok"],
             ["block", "demo", "B", "human call"], ["set", "demo", "B", "--status", "open"],
             ["add", "demo", "--id", "D", "--subject", "fourth", "--deps", "C"], ["event", "demo", "review", "no change"],
             ["pause", "demo", "human-test", "look"], ["resume", "demo"], ["stop", "demo"], ["resume", "demo"]]
    for argv in verbs:
        for f in ("status.js", "status.html"):
            if (d / f).exists(): (d / f).unlink()
        assert ge.main(argv) == 0, argv
        assert (d / "status.js").exists() and (d / "status.html").exists(), argv
    assert not list(d.glob("*.tmp"))

def test_same_hash_reclose_still_writes_nothing(project):
    write_roadmap(project, "demo", ROWS3); ge.main(["close", "demo", "A", "abc1234", "unit=3; first"])
    d = project / "ge/demo"; before = (d / "status.js").read_bytes(); (d / "status.html").unlink()
    assert ge.main(["close", "demo", "A", "abc1234", "unit=3; again"]) == 0
    assert (d / "status.js").read_bytes() == before and not (d / "status.html").exists()

def test_gate_logs_activity_and_the_page_carries_it(project):
    d = write_roadmap(project, "demo", ROWS3).parent
    (project / "ge/config.md").write_text("# ge config\n\n## Gates\n| name | command | success | artifact |\n|---|---|---|---|\n"
                                          "| unit | echo passed 7 | passed (\\d+) | stdout |\n", encoding="utf-8")
    assert ge.main(["gate", "demo", "unit"]) == 0
    lines = (d / "activity.log").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2 and " gate unit running" in lines[0] and " gate unit MATCH 7" in lines[1]
    act = data_of((d / "status.html").read_text(encoding="utf-8"))["activity"]
    assert [a["state"] for a in act] == ["running", "MATCH"] and act[1]["name"] == "unit" and act[1]["detail"] == "7"

def test_render_writes_the_gitignore_once(project):
    write_roadmap(project, "demo", ROWS3); ge.render_to_file("demo")
    gi = project / "ge/.gitignore"; text = gi.read_text(encoding="utf-8")
    assert "*/status.js" in text and "*/activity.log" in text
    gi.write_text("mine\n", encoding="utf-8"); ge.render_to_file("demo")
    assert gi.read_text(encoding="utf-8") == "mine\n"

def test_embedded_json_survives_a_script_tag_in_a_subject(project):
    rows = [("A", "closes the </script> tag", "open", "", "s", "unit")]
    write_roadmap(project, "demo", rows); html = ge.render_to_file("demo").read_text(encoding="utf-8")
    assert html.count("</script>") == html.count("<script")  # the data block did not end early
    assert node(data_of(html), "A")["subject"] == "closes the </script> tag"

def test_no_meta_refresh_and_the_page_polls_status_js(project):
    write_roadmap(project, "demo", ROWS3); html = ge.render_to_file("demo").read_text(encoding="utf-8")
    assert "http-equiv" not in html and "status.js" in html and "geUpdate" in html
    bare = html.replace("http://www.w3.org/2000/svg", "")  # the SVG namespace is a name, not a fetch
    assert "http://" not in bare and "https://" not in bare  # no network: self-contained by the spec

def test_data_derives_dependents_history_summary_and_kickoff(project):
    d = write_roadmap(project, "demo", ROWS3).parent
    ge.main(["start", "demo", "A", "s1"]); ge.main(["close", "demo", "A", "abc1234", "unit=3 e2e=1; the first close", "--session", "s1"])
    (d / "next.md").write_text("# kickoff: B\n\nBuild B.\n", encoding="utf-8")
    ge.main(["start", "demo", "B", "s2"])
    data = data_of((d / "status.html").read_text(encoding="utf-8"))
    a, b, c = node(data, "A"), node(data, "B"), node(data, "C")
    assert a["dependents"] == ["B", "C"] and c["dependents"] == []
    assert [h["event"] for h in a["history"]] == ["started", "done"] and a["finished"] and a["started"]
    assert a["summary"] == {"gates": [{"name": "unit", "value": "3"}, {"name": "e2e", "value": "1"}], "text": "the first close"}
    assert b["kickoff"].startswith("Build B.") and a.get("kickoff", "") == "" and c.get("kickoff", "") == ""
    assert b["kind"] == "in progress" and c["kind"] == "open" and not c["ready"]
    assert data["counts"]["done"] == 1 and data["counts"]["in progress"] == 1 and data["state"].startswith("in progress")
    assert data["ledger"][-1]["event"] == "started" and data["ledger"][-1]["task"] == "B"

def test_hold_and_calls_in_the_data(project):
    d = write_roadmap(project, "demo", ROWS3).parent
    (d / "calls.md").write_text("# calls\n\n## Open\n* pick blue or green\n\n## Decided\n* DECIDED: red\n", encoding="utf-8")
    ge.main(["pause", "demo", "human-test", "try the menu"])
    data = data_of((d / "status.html").read_text(encoding="utf-8"))
    assert data["hold"] == {"kind": "paused", "reason": "human-test", "note": "try the menu", "text": "PAUSED: human-test — try the menu"}
    assert data["calls"] == {"open": ["pick blue or green"], "decided": ["DECIDED: red"]}
    ge.main(["stop", "demo"]); data = data_of((d / "status.html").read_text(encoding="utf-8"))
    assert data["hold"]["kind"] == "stopped" and data["state"] == "stopped"

def test_activity_under_a_done_node_reads_as_verification(project):
    d = write_roadmap(project, "demo", ROWS3).parent
    (project / "ge/config.md").write_text("# ge config\n\n## Gates\n| name | command | success | artifact |\n|---|---|---|---|\n"
                                          "| unit | echo passed 7 | passed (\\d+) | stdout |\n", encoding="utf-8")
    ge.main(["close", "demo", "A", "abc1234", "unit=7; done"]); ge.main(["gate", "demo", "unit"])
    act = data_of((d / "status.html").read_text(encoding="utf-8"))["activity"]
    assert act and all(a["ts"] for a in act) and act[-1]["state"] == "MATCH"
