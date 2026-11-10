---
name: fastapi-guide
description: Field guide for the fastapi/fastapi repository - where fixes usually land, which test file checks which source file, the exact targeted test command, and the traps. Load it first when /workspace is fastapi/fastapi.
---

# fastapi/fastapi field guide

Built from 40 public tasks of this repo (dev split). Use it to skip exploration, not to skip reading the code.

## Where fixes land (share of gold-patch source files)
- `fastapi/` 32%
- `fastapi/dependencies/` 18%
- `fastapi/_compat/` 9%
- `fastapi/openapi/` 8%
- `docs_src/frontend/` 6%
- `docs_src/server_sent_events/` 5%
- `fastapi/security/` 5%
- `docs_src/dependencies/` 5%

## Source file -> test file (seen together in past fixes)
- `fastapi/routing.py` -> `tests/test_router_include_context.py`
- `fastapi/sse.py` -> `tests/test_sse.py`
- `fastapi/dependencies/utils.py` -> `tests/test_get_model_definitions_formfeed_escape.py`
- `fastapi/dependencies/utils.py` -> `tests/test_response_model_as_return_annotation.py`
- `fastapi/openapi/utils.py` -> `tests/test_router_include_context.py`
- `fastapi/dependencies/utils.py` -> `tests/benchmarks/test_general_performance.py`
- `fastapi/dependencies/utils.py` -> `tests/test_compat_params_v1.py`
- `fastapi/dependencies/utils.py` -> `tests/test_pydantic_v1_deprecation_warnings.py`
- `fastapi/dependencies/utils.py` -> `tests/test_tutorial/test_pydantic_v1_in_v2/test_tutorial002.py`
- `fastapi/dependencies/utils.py` -> `tests/test_tutorial/test_pydantic_v1_in_v2/test_tutorial003.py`
- `fastapi/dependencies/utils.py` -> `tests/test_tutorial/test_pydantic_v1_in_v2/test_tutorial004.py`
- `fastapi/dependencies/utils.py` -> `tests/test_tutorial/test_request_form_models/test_tutorial002_pv1.py`
- `fastapi/dependencies/utils.py` -> `tests/test_tutorial/test_schema_extra_example/test_tutorial001_pv1.py`
- `fastapi/routing.py` -> `tests/benchmarks/test_general_performance.py`
- `fastapi/routing.py` -> `tests/test_compat_params_v1.py`

## Run one test
`python -m pytest <test file> -x -q -k <test name or keyword>` (never the whole suite). If pytest is missing, `python -m unittest <module>`.

## Traps
- Documentation examples are executable code under docs_src/ (15 of 67 public fixes touched it) and are tested by tests/test_tutorial/...; when the issue is about a docs example, edit docs_src/, not docs/*.md.
- Many tests import the docs_src example by module path; the test file name usually mirrors the docs_src path.
- Never edit, create or delete test files (tests/, test_*.py, *_test.py, conftest.py): the grader resets them and an edit there can fail the task.
- Never run the whole test suite: one test file, ideally with -k <name>. A full run can take minutes and ends the task by timeout.
- A failing test that is unrelated to your change (missing fixture, network, import error elsewhere) is pre-existing. Ignore it; do not try to fix it.
- Most fixes touch 1-2 files (110 of the 129 public gold patches). If your diff spans more than 3 files, re-read the problem statement.
- Keep exact names from the problem statement: error messages, exception types, parameter names and defaults are checked by hidden tests.
- Only a submitted, non-empty patch can score. Leave time to submit: in past runs about a quarter of tasks ended by timeout with no patch at all.
