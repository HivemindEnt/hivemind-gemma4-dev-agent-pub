---
name: requests-guide
description: Field guide for the psf/requests repository - where fixes usually land, which test file checks which source file, the exact targeted test command, and the traps. Load it first when /workspace is psf/requests.
---

# psf/requests field guide

Built from 8 public tasks of this repo (dev split). Use it to skip exploration, not to skip reading the code.

## Where fixes land (share of gold-patch source files)
- `src/requests/` 100%

## Source file -> test file (seen together in past fixes)
- `src/requests/models.py` -> `tests/test_requests.py`
- `src/requests/utils.py` -> `tests/test_requests.py`
- `src/requests/adapters.py` -> `tests/test_adapters.py`
- `src/requests/sessions.py` -> `tests/test_requests.py`
- `src/requests/utils.py` -> `tests/test_utils.py`
- `src/requests/compat.py` -> `tests/test_requests.py`
- `src/requests/status_codes.py` -> `tests/test_requests.py`

## Run one test
`python -m pytest <test file> -x -q -k <test name or keyword>` (never the whole suite). If pytest is missing, `python -m unittest <module>`.

## Traps
- Source is under src/requests/ in recent versions (older checkouts: requests/). Check which exists before editing.
- Most behaviour tests are in tests/test_requests.py; use -k to select one test, since that file is large.
- Never edit, create or delete test files (tests/, test_*.py, *_test.py, conftest.py): the grader resets them and an edit there can fail the task.
- Never run the whole test suite: one test file, ideally with -k <name>. A full run can take minutes and ends the task by timeout.
- A failing test that is unrelated to your change (missing fixture, network, import error elsewhere) is pre-existing. Ignore it; do not try to fix it.
- Most fixes touch 1-2 files (110 of the 129 public gold patches). If your diff spans more than 3 files, re-read the problem statement.
- Keep exact names from the problem statement: error messages, exception types, parameter names and defaults are checked by hidden tests.
- Only a submitted, non-empty patch can score. Leave time to submit: in past runs about a quarter of tasks ended by timeout with no patch at all.
