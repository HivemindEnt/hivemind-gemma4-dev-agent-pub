---
name: patch-check
description: Pre-submit gate. Run it after your edit and before submit_patch - it checks the diff is non-empty, touches no protected test files, compiles, and prints the targeted test command for each changed module.
---

# Patch check (run before submit_patch)

Run `run_skill_script` with skill `patch-check` and script `scripts/precheck.py`. It edits nothing.

- `RESULT: OK` -> run the printed targeted test once; if it passes (or fails only for a pre-existing reason), submit.
- `RESULT: UNKNOWN` -> the script could not read git; check `git -C /workspace status --short` yourself.
- `RESULT: FIX` -> fix every listed problem first. Typical: you touched a test file (revert it with `git checkout -- <file>`),
  a changed file does not compile (read the error line), or the diff is empty.
If scripts cannot run, do it by hand: `git -C /workspace diff --stat`, `python -m py_compile <changed files>`.
