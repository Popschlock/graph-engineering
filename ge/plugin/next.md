# kickoff: 0.2-polish

Read `ge/config.md` and `ge/plugin/roadmap.md`; the node is `0.2-polish` (spec: the design doc §11 plus the final review's minors, listed in the node's subject). Work through the list in the subject in order, each item with its test in `tests/`, and keep `python -m pytest tests/ -q` green throughout. The gate is `pytest`. Bump `.claude-plugin/plugin.json` and `marketplace.json` to 0.2.0 in the same change (the plugin cache is keyed by version). One work commit per item is fine; the close takes the last one.
