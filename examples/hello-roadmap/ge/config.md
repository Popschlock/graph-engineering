# ge config — hello-roadmap

## Gates
| name | command | success | artifact |
|---|---|---|---|
| pytest | python -m pytest -q | `(?m)^(\d+) passed(?![^\n]*\b(?:failed\|error))` | stdout |

## Guards
| name | command | blocked when |
|---|---|---|

## Rules
Python 3, stdlib only. One module `hello.py`; its tests in `test_hello.py`; `python -m pytest -q` from this directory.

## Tiers
| role | model | effort |
|---|---|---|
| task | opus | xhigh |
| reader | fable | high |
| verifier | opus | xhigh |
| reviewer | fable | high |

## Cadence
review every: 3
max parallel: 3
