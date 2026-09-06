# kickoff: H1

Read `hello.py` and `test_hello.py`; `greet` exists. Run `python -m pytest -q` (1 passed), then close H1 as the rules say: the work commit (even if only this file moves, commit the ge/ state), `ge.py close hello H1 <hash> "pytest 1 passed"`, next.md for H2, the close commit. H2's kickoff to write: add `shout(name)` returning `greet(name).upper() + "!"` and `test_shout` asserting `shout("graph") == "HELLO, GRAPH!"`; gate `pytest`.
