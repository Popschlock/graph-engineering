# kickoff: none

`ge.py next plugin` prints `none`: every row in `ge/plugin/roadmap.md` is `done`, and
there is nothing for `/ge-run-roadmap plugin` to dispatch. It will say "nothing ready"
and stop. That is the correct state, not a fault.

## Where the plugin got to

`0.2-polish` closed at `b49fb18` with `pytest=62`, and the tree is **Graph Engineering
0.2.0**. `docs/superpowers/specs/2026-09-05-graph-engineering-design.md` is the
contract and its **section 12** lists the nine changes 0.2 made, each with the section
it lives in and each pinned by a test in `tests/`. Read that section before touching
anything; the two worth knowing without reading are:

* **A gate row takes an optional `floor`** (spec §2.2) — a ratchet on the first capture
  group, because `(\d+) passed` reads a suite that SHRANK exactly as green as one that
  grew. This repo's own `ge/config.md` carries `floor 62`, which is its test count: any
  session that adds tests should raise it, and a session that finds it refusing has
  either deleted tests or broken some.
* **Gate and guard commands run under a timeout that kills the whole process tree**
  (`GATE_TIMEOUT` 3600 s, `GUARD_TIMEOUT` 30 s). The first cut of this used
  `subprocess.run(..., timeout=)` and bounded nothing — with `shell=True` the real work
  is a grandchild, killing the shell leaves it holding the output pipe, and the read
  waits for it. Its NO MATCH assertion was green throughout; only the suite's clock
  (1.7 s → 62 s) saw it. `tests/test_gate.py::test_a_gate_timeout_bounds_the_wall_clock`
  is the pin that would now catch a regression, and the lesson is general: assert the
  property the feature exists to guarantee, never only the message it prints.

## The one thing waiting on the human

`ge/plugin/calls.md` has **one open call: whether to push 0.2.0 to GitHub** (`main`,
plus a `v0.2.0` tag). Both sides are written out there. Nothing is blocked on it — it
is recorded so `/ge-status plugin` and the SessionStart hook surface it.

**Never push to GitHub yourself.** It is the owner's word and never automatic (spec §9,
and `ge/config.md`'s `## Rules`). A local `.git/hooks/pre-push` refuses every ref but
`main` and tags; do not remove it.

## If you have been given work to do

There is no node to take, so do not invent one. Take whichever of these fits:

* **The human wants new work on this plugin** → `/ge-build-roadmap` is for a roadmap
  that does not exist yet; this one does, so use **`/ge-revise-roadmap plugin`**, which
  adds rows with `ge.py add` and rewrites this file for the new first node. Nodes go
  in `ge/plugin/roadmap.md` and never by hand — `ge.py` is the only writer.
* **The human wants the push decided** → `/ge-resume-roadmap plugin` walks the open
  calls, takes their word, and moves the call to `## Decided`.
* **A one-off fix, no roadmap** → then it is ordinary work: keep `scripts/ge.py` ONE
  stdlib-only file (3.9 syntax; `ast.parse(..., feature_version=(3,9))` is a cheap
  check), tests in `tests/`, run `python -m pytest tests/ -q` from the repo root, and
  change the spec BEFORE the behaviour. Raise `ge/config.md`'s floor to the new count
  in the same commit, or the ratchet goes stale.

## Gates and how a close works, if a node is ever added

The only gate is **`pytest`** (`ge/config.md`): `python -m pytest tests/ -q`, success
`(?m)^(\d+) passed(?![^\n]*\b(?:failed|error))`, artifact `stdout`, floor 62. Run it as
`ge.py gate plugin pytest` and keep the captures it prints — the verifier reads them
back out of the ledger, so a close's outcome string starts `pytest=<n>; ` and then one
line of summary. The close is, in order: the work commit ending with the session link →
`ge.py close plugin <id> <hash> "<outcome>" --session <id>` → `ge.py next plugin` and
this file rewritten for that node → `git add ge && git commit -m "ge(plugin): close
<id>; next <n>"`.
