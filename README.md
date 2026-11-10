# Out of Time, Not Out of Ideas

Code, agent configurations and per-task results behind our paper for the
[Gemma 4 Developer Agent](https://www.kaggle.com/competitions/gemma-4-developer-agent) paper track:
where a 31B open-model coding agent loses tasks under a fixed compute budget, and what a 30-task development set can
and cannot measure.

The paper is in [`paper/paper.md`](paper/paper.md); figures and the script that draws them are in
[`paper/figures/`](paper/figures/).

## What is here

| Path | What it is |
|---|---|
| `arms/<ARM>/` | One agent configuration per experiment arm: `arm.json` (model, tools, sampling, per-task budgets, skills, the hypothesis it tests) and `system.md` (the system prompt). Each arm changes one variable from the baseline `A0`. |
| `skills_src/`, `skills/` | ADK skills used by the structural arms: `locate` (one-call file ranking, BM25 with path and identifier boosts), per-repository field guides and the new-repo guide builder, and the pre-submit check. |
| `build_deveval.py` | Renders an arm into a Kaggle notebook (4x L4, the host's image, vLLM and swegemma versions) that evaluates it on a fixed task subset and writes `summary.json` / `summary.jsonl`. |
| `build_submission.py` | Renders the same arm into the competition `submission.zip`, so what was measured is what is submitted; optionally runs the host's own validator. |
| `run_queue.py` | Small queue that runs dev evaluations within the Kaggle GPU limits. |
| `analyze_runs.py`, `power.py`, `eval_locate.py` | Outcome taxonomy and token analysis, the sample-size table, and the offline evaluation of the `locate` skill. |
| `results/<ARM>-<tag>/` | Per-run `summary.json` and per-task `summary.jsonl` (task id, resolved, patch size, tool calls, duration, error). `r` = 30-task dev subset, `h` = 47 held-out tasks, `c` = one-task-at-a-time check. |
| `test_*.py` | Unit tests for the tools above (`python test_<name>.py`). |

## Method in one paragraph

The 129 public tasks are split by a stable hash of the task id into 82 development and 47 held-out tasks; held-out
tasks are never used for tuning. Every dev run uses the same 30-task subset, so arms can be compared paired (exact
McNemar test on discordant tasks) and against repeats of the unchanged baseline, which give the noise floor. A result
counts only if it holds on a repeat or on the held-out tasks.

## Reproducing a number

Every resolve count in the paper can be recomputed from `results/*/summary.jsonl`; for example the baseline's three
dev repeats are `results/A0-r1`, `A0-r2` and `A0-r3` (5, 4 and 7 of 30).

## Licence

MIT No Attribution (MIT-0), see `LICENSE`. Task data belongs to the competition host and is not included.
