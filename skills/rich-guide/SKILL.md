---
name: rich-guide
description: Field guide for the Textualize/rich repository - where fixes usually land, which test file checks which source file, the exact targeted test command, and the traps. Load it first when /workspace is Textualize/rich.
---

# Textualize/rich field guide

Built from 33 public tasks of this repo (dev split). Use it to skip exploration, not to skip reading the code.

## Where fixes land (share of gold-patch source files)
- `rich/` 100%

## Source file -> test file (seen together in past fixes)
- `rich/console.py` -> `tests/test_console.py`
- `rich/cells.py` -> `tests/test_cells.py`
- `rich/markdown.py` -> `tests/test_markdown.py`
- `rich/table.py` -> `tests/test_table.py`
- `rich/ansi.py` -> `tests/test_ansi.py`
- `rich/traceback.py` -> `tests/test_traceback.py`
- `rich/diagnose.py` -> `tests/test_console.py`
- `rich/text.py` -> `tests/test_text.py`
- `rich/file_proxy.py` -> `tests/test_file_proxy.py`
- `rich/panel.py` -> `tests/test_panel.py`
- `rich/live.py` -> `tests/test_live.py`
- `rich/live_render.py` -> `tests/test_live.py`
- `rich/default_styles.py` -> `tests/_card_render.py`
- `rich/default_styles.py` -> `tests/test_markdown.py`
- `rich/default_styles.py` -> `tests/test_markdown_no_hyperlinks.py`

## Run one test
`python -m pytest <test file> -x -q -k <test name or keyword>` (never the whole suite). If pytest is missing, `python -m unittest <module>`.

## Traps
- Source lives in rich/ (one module per feature: rich/console.py, rich/cells.py, rich/segment.py, ...); tests mirror it as tests/test_<module>.py.
- Character-width issues land in rich/cells.py (and once, in the public tasks, in the rich/_unicode_data/ tables).
- Never edit, create or delete test files (tests/, test_*.py, *_test.py, conftest.py): the grader resets them and an edit there can fail the task.
- Never run the whole test suite: one test file, ideally with -k <name>. A full run can take minutes and ends the task by timeout.
- A failing test that is unrelated to your change (missing fixture, network, import error elsewhere) is pre-existing. Ignore it; do not try to fix it.
- Most fixes touch 1-2 files (110 of the 129 public gold patches). If your diff spans more than 3 files, re-read the problem statement.
- Keep exact names from the problem statement: error messages, exception types, parameter names and defaults are checked by hidden tests.
- Only a submitted, non-empty patch can score. Leave time to submit: in past runs about a quarter of tasks ended by timeout with no patch at all.
