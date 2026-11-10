---
name: locate
description: First call on every task. Ranks the repository's files against the issue text in one call and prints the most likely files to edit, the matching lines, and the test file to run, so you can start editing early.
---

# Locate (run this first)

Call `run_skill_script` with `skill_name` `locate`, `file_path` `scripts/locate.py` and
`args` `{"query": "<the issue title and its key sentences, error messages and code names>"}`.
It reads files only and changes nothing.

- `LIKELY FILES TO EDIT` lists the most likely files first, followed by the lines that matched.
  On our past tasks the right file was first about half the time and in the top 3 about three times in four.
- Open the top file at the printed lines. If it is clearly not the right place, try the second file before searching
  by hand.
- `LIKELY TEST FILE TO RUN` is the test to run after your fix. Do not edit it.
If the script cannot run, search by hand: `grep -rn "<identifier from the issue>" --include=*.py .`
