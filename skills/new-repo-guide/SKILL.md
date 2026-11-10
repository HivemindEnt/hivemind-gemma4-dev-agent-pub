---
name: new-repo-guide
description: For a repository that has no field guide of its own. Builds one at run time from the patterns the known repos share - package layout, how tests are named and run, the docs-example convention, and the traps. Load it when no other *-guide skill matches /workspace.
---

# New repository: build the field guide yourself

The known repos (fastapi, rich, requests, httpx) share a shape. Assume this repo does too until it shows otherwise.

1. Run the scout script once: `run_skill_script` with skill `new-repo-guide` and script `scripts/scout.py` (it reads
   /workspace, edits nothing, and prints a guide in the same format as the known-repo guides). If scripts cannot run,
   do the same by hand with these commands:
   - layout: `ls /workspace` and `ls /workspace/src 2>/dev/null` (the package is the directory with `__init__.py`)
   - tests: `ls /workspace/tests | head -50`
   - runner: `grep -n -A3 "\[tool.pytest" /workspace/pyproject.toml /workspace/setup.cfg /workspace/tox.ini /workspace/pytest.ini 2>/dev/null`
2. Map the issue to source: the module named in the problem statement, else `search_similar_code` with the error text.
3. Find the test: `tests/test_<module>.py` first (all known repos use this), else `grep -rln "<function name>" tests | head`.
4. Run one test only: `python -m pytest <file> -x -q -k <name>`.

## Inherited traps (true in every known repo)
- Never edit, create or delete test files (tests/, test_*.py, *_test.py, conftest.py): the grader resets them and an edit there can fail the task.
- Never run the whole test suite: one test file, ideally with -k <name>. A full run can take minutes and ends the task by timeout.
- A failing test that is unrelated to your change (missing fixture, network, import error elsewhere) is pre-existing. Ignore it; do not try to fix it.
- Most fixes touch 1-2 files (110 of the 129 public gold patches). If your diff spans more than 3 files, re-read the problem statement.
- Keep exact names from the problem statement: error messages, exception types, parameter names and defaults are checked by hidden tests.
- Only a submitted, non-empty patch can score. Leave time to submit: in past runs about a quarter of tasks ended by timeout with no patch at all.
