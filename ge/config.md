# ge config — graph-engineering

## Gates
| name | command | success | artifact |
|---|---|---|---|
| pytest | python -m pytest tests/ -q | `(?m)^(\d+) passed(?![^\n]*\b(?:failed\|error))` | stdout |

## Guards
| name | command | blocked when |
|---|---|---|

## Rules
`scripts/ge.py` stays ONE stdlib-only file (3.9+ syntax) and the only reader/writer of `ge/` files; tests in `tests/`, run `python -m pytest tests/ -q` from the repo root. Skills are Markdown a fresh session can follow; agents are project-agnostic. Never push to GitHub. The spec `docs/superpowers/specs/2026-09-05-graph-engineering-design.md` is the contract; change it before changing behaviour.

## Tiers
| role | model | effort |
|---|---|---|
| task | opus | xhigh |
| reader | fable | high |
| verifier | opus | xhigh |
| reviewer | fable | high |

## Cadence
review every: 3
