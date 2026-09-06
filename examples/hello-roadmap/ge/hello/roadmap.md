# hello — a greeter that shouts and runs from the command line

## Goal
A `hello.py` that greets, can shout, and runs from the command line, each step proven by pytest.

## Phases
### H — the greeter
H1, H2 and H3, in that order.

## Tasks
| id | subject | status | deps | spec | gate | commit |
|---|---|---|---|---|---|---|
| H1 | `greet(name)` returns `hello, <name>` | open | | inline: one function, one test | pytest | |
| H2 | `shout(name)` returns `greet(name).upper() + "!"` | open | H1 | inline: one function, one test | pytest | |
| H3 | `python hello.py <name>` prints `shout(name)` | open | H2 | inline: a `__main__` block, one subprocess test | pytest | |

## Notes
H1 is already written, so a first `/ge-run-roadmap hello once` closes it fast and shows the whole cycle.
