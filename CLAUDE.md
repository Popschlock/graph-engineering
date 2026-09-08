# Graph Engineering — a Claude Code plugin (Popschlock)

Turn a goal into a task graph, run it unattended from ONE interactive session
(a fresh subagent per node, an independent verifier per close, a review on a
cadence), and let the human pause it to human-test, get a summary, or change the
goal. Files in the project's git; any project, any gate.

The spec is `docs/design.md` and
it is the contract: the file formats in §2, the `scripts/ge.py` CLI in §3, the
skills in §4, the runner in §5. Change the spec before changing the behaviour.

Rules for building it:
- `scripts/ge.py` is stdlib-only Python 3 and the ONLY thing that parses or writes
  the `ge/` files; every skill calls it. `python -m pytest tests/` must pass.
- The skills are Markdown that a fresh session can follow with no other context;
  the agents are project-agnostic (a project's specifics live in its `ge/config.md`).
- Layout mirrors PromptFu (`.claude-plugin/`, `skills/`, `agents/`, `hooks/`).
- Pushing to GitHub is the owner's word, never automatic.
