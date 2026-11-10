---
name: httpx-guide
description: Field guide for the encode/httpx repository - where fixes usually land, which test file checks which source file, the exact targeted test command, and the traps. Load it first when /workspace is encode/httpx.
---

# encode/httpx field guide

Built from 1 public tasks of this repo (dev split). Use it to skip exploration, not to skip reading the code.

## Where fixes land (share of gold-patch source files)
- `src/httpx/` 57%
- `src/ahttpx/` 43%

## Source file -> test file (seen together in past fixes)
- `src/ahttpx/_parsers.py` -> `tests/test_parsers.py`
- `src/ahttpx/_pool.py` -> `tests/test_parsers.py`
- `src/ahttpx/_server.py` -> `tests/test_parsers.py`
- `src/httpx/_network.py` -> `tests/test_parsers.py`
- `src/httpx/_parsers.py` -> `tests/test_parsers.py`
- `src/httpx/_pool.py` -> `tests/test_parsers.py`
- `src/httpx/_server.py` -> `tests/test_parsers.py`

## Run one test
`python -m pytest <test file> -x -q -k <test name or keyword>` (never the whole suite). If pytest is missing, `python -m unittest <module>`.

## Traps
- Source is src/httpx/ (this checkout also has src/ahttpx/); private modules start with _. Tests are under tests/.
- Never edit, create or delete test files (tests/, test_*.py, *_test.py, conftest.py): the grader resets them and an edit there can fail the task.
- Never run the whole test suite: one test file, ideally with -k <name>. A full run can take minutes and ends the task by timeout.
- A failing test that is unrelated to your change (missing fixture, network, import error elsewhere) is pre-existing. Ignore it; do not try to fix it.
- Most fixes touch 1-2 files (110 of the 129 public gold patches). If your diff spans more than 3 files, re-read the problem statement.
- Keep exact names from the problem statement: error messages, exception types, parameter names and defaults are checked by hidden tests.
- Only a submitted, non-empty patch can score. Leave time to submit: in past runs about a quarter of tasks ended by timeout with no patch at all.
