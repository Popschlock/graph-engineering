# plugin — Graph Engineering builds itself

## Goal
A goal becomes a task graph; one interactive session runs the graph unattended by dispatching a fresh subagent per node with an independent verifier per close; the human pauses it to test, get a summary, or change the goal. Everything is files in the project's git. Any project, any gate. (Spec `docs/superpowers/specs/2026-09-05-graph-engineering-design.md`.)

## Phases
### M — migration and release
T12 is the first migration of an existing project onto the plugin; publish waits for the owner's word.

## Tasks
| id | subject | status | deps | spec | gate | commit |
|---|---|---|---|---|---|---|
| T12 | the first external project migration (anonymised) | done 96e0322 |  | docs/superpowers/plans/2026-09-05-graph-engineering.md Task 12 | pytest | 96e0322 |
| publish | push 0.1.2 to Popschlock/graph-engineering (public) | done b5b9c5c | T12 | docs/superpowers/specs/2026-09-05-graph-engineering-design.md §9 | pytest | b5b9c5c |
| 0.2-polish | 0.2 polish: hook launcher python3/python; a floor column on gates; init --subject; PAUSE/STOP drawn in status.html; run_cmd timeout; pause reason newline; a second done row for a re-closed node; revise/build told about next's stderr lines; a directory-install .claudeignore | open | T12 | docs/superpowers/specs/2026-09-05-graph-engineering-design.md §11 plus the final review's minors (this session's ledger) | pytest |  |

## Notes
Tasks 1–11 of the plan were built by hand before this roadmap existed (see git log). Publishing is the owner's word, never automatic. T12's own migration ran against a private project, so its worked form in the plan is anonymised and its project-specific gate is not shipped here.
