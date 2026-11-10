# Out of Time, Not Out of Ideas: Where a 31B Open-Model Coding Agent Loses Tasks Under a Fixed Compute Budget

## 1. Abstract

We built a declarative (YAML-only) agent for the Gemma 4 developer-agent competition and asked how much of what we
measured during development was signal. Over 21 Kaggle runs on a fixed 30-task development subset and a 47-task
held-out set, the unchanged baseline resolved 5, 4 and 7 of 30 tasks across three repeats (pooled 0.18, Wilson
0.11-0.27). Eleven configurations landed inside that range. Six were setting changes: thinking off or reduced, a
time-box prompt, shorter per-task caps. Five were structural: a separate localizer stage, repo field guides, a
pre-submit gate, reproducing the bug first, and a one-call file locator. A single best run (7/30) did not repeat (4/30).
The one change that held up was operational, not a gain in resolve rate: cutting the per-task cap from 6 to 4 minutes
matched the baseline on held-out tasks while using about a quarter less evaluation time, which matters under a fixed
total budget. We report a failure taxonomy, the noise floor, how many tasks a comparison needs, and why, for this model
and harness, the obvious structural fixes did not move the binding constraint.

## 2. Introduction

The competition asks for a coding agent built only from configuration: a YAML agent tree compiled by the host's
`adk-submission` package, tools drawn from a closed registry of nine swegemma tools, and one allowed base model. The
scored run evaluates about 120 hidden bug-fix and feature tasks from private repositories on fixed hardware (4x NVIDIA
L4) within a 12-hour total runtime. A task scores 1 or 0, so the metric is a resolve rate. Per-task limits (wall time,
tool calls, turns) are ours to set in the submission's `eval_config.yaml`; the harness defaults are 60 minutes and 100
calls, far more than a 12-hour total allows across 120 tasks.

Under these rules most of the design space is a handful of knobs: prompts, sub-agents, skills, thinking budget, and
per-task caps. Participants compare settings by a single leaderboard number or a single local run. With about 60 tasks
per leaderboard split and resolve rates near 0.2, two configurations that differ by a few tasks are hard to tell
apart, yet that is the size of most differences we observed.

This paper is about measurement rather than a new agent. We ask three questions. Where does the baseline agent lose
tasks (Section 4)? Do the obvious interventions, simple or structural, change that (Section 5)? And can a development
setup of this size tell the difference (Sections 6-8)? Our answer to the last question is mostly no: the identical
configuration varied by 3 tasks out of 30 between repeats, which covers every arm we tested. The practical result is
that the per-task time cap, not the resolve rate, is the variable worth tuning, because it buys margin against the
total limit without a measurable loss.

## 3. Setup and method

**Harness.** All runs use the host's starter stack: swegemma 0.2.11, vLLM 0.19.1 with the host's server configuration,
and the starter-kit model `gemma-4-31b-it-qat-w4a16-ct`, on Kaggle 4x L4 notebooks, the same hardware class as the
scorer. The baseline (A0) is a single 31B agent with the host's sample system prompt, all nine tools, no sub-agent and
no adapter, sampling at temperature 0.2 with a 4096-token thinking budget, and a per-task cap of 6 minutes, 40 tool
calls and 120 turns. Runs evaluate four tasks at a time unless stated; Section 6 checks that choice against one at a
time.

**Task split.** The 129 public tasks (fastapi 67, rich 48, requests 13, httpx 1) are split by a stable hash of the task
name: a task is held out when the first 8 hex digits of `sha1(instance_id)`, modulo 1000, are divisible by 3. This
gives 82 development and 47 held-out tasks, independent of file order. Held-out tasks are never used for tuning. Dev
runs use a fixed 30-task subset, allocated across repositories in proportion to their dev counts, so that every arm
sees the same tasks.

**Arms.** Each arm changes one variable from A0 and lives in its own tracked directory, so a result maps to an exact
configuration commit. A small queue runs them within the weekly Kaggle GPU quota.

**Outcomes and statistics.** For every task we record how the session ended (resolved, session timeout with or without
a patch, or finished with a failing patch), plus wall time, tool calls and tokens. Resolve rates carry Wilson 95%
intervals. Arms on the same tasks are compared with an exact McNemar test on the discordant pairs, against each
baseline repeat separately. We treat a result as a finding only if it holds on a repeat or on the held-out set.

## 4. Where the agent loses tasks

We classify every task by how its session ended, not only by whether it was resolved. The harness tests whatever patch
is in the working tree when time runs out, so a timeout can still leave a patch.

**Table 1.** Outcomes of the baseline (A0, first two repeats, 60 task-runs). Token columns: run 1 / run 2.

| Outcome | Count | Share | Mean completion tokens | Mean prompt tokens |
|---|---|---|---|---|
| Resolved | 9 | 15% | 3.8k / 4.2k | 150k / 129k |
| Timeout, failing patch | 22 | 37% | 7.1k / 7.0k | 213k / 234k |
| Timeout, no patch | 15 | 25% | 5.7k / 6.2k | 176k / 216k |
| Finished, failing patch | 14 | 23% | 4.1k / 4.5k | 156k / 147k |
| Finished, no patch | 0 | 0% | - | - |

**Most failures are timeouts, not wrong answers.** 37 of the 51 failed task-runs (73%) ended at the 6-minute cap. The
agent never stopped on its own without a fix (0 of 60).

**Timeouts generate more text, not more searching.** Timed-out tasks used about 1.5-1.8 times the completion tokens of
resolved ones, with only a few more steps. With four tasks sharing the GPUs, each task generated about 15-22 completion
tokens per second, so about 6-7k generated tokens is the whole 6-minute budget.

**Successes are fast.** Resolved tasks took 186 s on average. A task still unresolved at 3-4 minutes is unlikely to be
resolved by 6; Section 5 tests this directly.

**Timed-out patches are mostly unfinished features, not wrong logic.** Of the 22 timeouts that left a failing patch, 9
failed before any test ran. Seven of the nine are ImportErrors (the hidden test imports a name the fix was supposed to
add), one is a missing keyword argument, and one a half-made edit. The same four tasks account for 8 of the 9: they need
a new public API, and the agent ran out of time before adding it.

## 5. Interventions: one variable at a time

### 5.1 Settings

**Table 2.** Setting changes on the same 30 dev tasks (A0 repeats: 5, 4 and 7).

| Arm | Change | Resolved | Main failure | Mean tool calls |
|---|---|---|---|---|
| A1 | thinking off | 4/30 | ran out of tool calls | 27.0 |
| A2 | 4 min, 28 calls (two runs) | 4/30, 4/30 | timeout | 17.6 |
| A3 | prompt time-box ("submit by call 14") | 5/30 | timeout | 22.7 |
| A5 | thinking budget 1536 (two runs) | 7/30, 4/30 | timeout | - |
| A6 | A5 + A2 | 4/30 | timeout | - |
| A7 | 3 min, 21 calls | 4/30 | timeout | - |

**Thinking off moves the failure; it does not remove it.** Without thinking, completion tokens per task fell by about
60% and timeouts fell from 18-19 to 5. But the agent took more, shorter steps, prompt tokens per task rose to 260-380k
because every step re-reads the context, and ten tasks ended with no patch after 34-40 calls. The binding constraint
changed from time to tool calls, and resolves did not move.

**The model does not follow budgets written in the prompt.** A3 told the agent to submit by its 14th call. Mean calls
rose to 22.7 and 19 tasks still timed out. Limits that matter have to be set in the harness configuration.

**Shorter per-task caps cost nothing measurable.** A2 (4 minutes) and A7 (3 minutes) scored 4/30, within the baseline's
4-7. Resolved tasks under A2 still took about 184 s, as under A0, so the minutes removed mostly belonged to tasks that
fail anyway. Evaluation time fell from about 40 minutes to 30-33 (A2) and 26 (A7).

### 5.2 Structural changes

After the setting changes came out flat, we tried changes aimed at the failure modes of Section 4, each with a written
hypothesis.

**Table 3.** Structural arms on the same 30 dev tasks; B2 on the held-out tasks. p is the exact McNemar test against
each baseline repeat on the same tasks (smallest to largest).

| Arm | Change and hypothesis | Resolved | Paired p | What moved |
|---|---|---|---|---|
| B1 | read-only localizer stage, then the A0 fixer: exploring eats the time | 4/30 | 0.25-1.0 | timeouts 19 of 30 (A0: 18-19) |
| B3 | deterministic pre-submit gate (non-empty diff, no protected test touched, code compiles, targeted test runs): bad patches get submitted | 6/30 | 0.50-1.0 | finished with a failing patch 6 (A0: 5-7) |
| C1 | reproduce the issue in a script first and submit only when it passes: wrong logic is invisible to a structural gate | 5/30 | 0.50-1.0 | timeouts with no patch 12 (A0: 6-8) |
| C2 | one-call file locator as the mandatory first step: searching delays the first edit | 5/30 | 0.62-1.0 | calls before the first edit 13 (A0: 10-11) |
| B2 | per-repository field guides as skills (where fixes land, test commands, traps) | 11/47 held-out (A0: 9/47) | 0.62 | - |

**Localization is not the binding constraint.** Resolved baseline tasks made their first edit after a median of 2-6
tool calls, unresolved ones after 10-13, which suggested that searching was the problem. The locator we built ranks
files against the issue text offline with the changed file in its top three for 77% of held-out tasks. Made the
mandatory first call, it did not bring the first edit forward: the agent still read around, and calls before the first
edit rose to 13. A separate localizer stage (B1) did not help either.

**Checks that need time compete with the fix for that time.** The pre-submit gate (B3) did not change how many finished
patches failed: the failures are wrong logic, which a structural check cannot see. Reproducing the issue first (C1)
targets exactly that, but writing and running the script used the time the fix needed: timeouts with no patch at all
rose to 12, from 6-8.

Every structural arm landed inside the baseline's spread. Within a 6-minute budget, each added step trades against the
same scarce resource, generated tokens, which Section 4 identified as the real limit.

## 6. Does the development setup measure what the score measures?

We run dev evaluations four tasks at a time to save GPU quota. We checked whether sharing the GPUs changes the outcome:
the baseline ran one task at a time on 12 of the dev tasks.

| | Four at a time (two repeats) | One at a time |
|---|---|---|
| Resolved (same 12 tasks) | 3 and 2 | 3 |
| Mean wall time per task | 297 s and 326 s | 279 s |
| Session timeouts | 6 and 7 | 4 |
| Mean tool calls | 18.8 and 22.6 | 24.8 |

Sharing the GPUs four ways costs only about 10% of per-task wall time; the time freed when running alone mostly goes
into more tool calls, not more resolves. Four-at-a-time dev runs are a fair, slightly pessimistic stand-in for a
sequential run. If the scored run is sequential, about 120 tasks at 280-310 s each take about 9.5-10.5 hours, close to
the 12-hour limit, so a shorter per-task cap is insurance as well as a saving.

## 7. Noise: how big a difference can 30 tasks detect?

The unchanged baseline, repeated three times on the same 30 dev tasks, resolved 5, 4 and 7 (pooled 16/90 = 0.18).
Across the repeats, 23 tasks were never resolved, 4 always and 3 only sometimes; between pairs of repeats, 1, 2 and 3
tasks changed outcome.

**The baseline's own spread covers every arm we tested.** All ten configurations run on the dev tasks scored between 4
and 7 of 30, and so did the unchanged baseline. No paired comparison reached significance; the smallest exact McNemar p was
0.25.

**A concrete winner's curse.** After six single runs, the thinking-budget arm (A5) looked best at 7/30, resolving every
task the baseline had ever resolved plus two more. Its repeat scored 4/30, and it gained nothing on the held-out tasks
(10/47 against 9/47). Picking the best of several single 30-task runs would have shipped a configuration no better than
the default.

**How many tasks would a real comparison need?** At the baseline rate of about 0.18 (alpha 0.05, power 0.8; normal
approximations, so order of magnitude):

| Design | Detect +10 points | Detect +5 points |
|---|---|---|
| Two independent runs on different tasks | about 270 tasks per arm | about 1,000 tasks per arm |
| Paired on the same tasks | about 115-155 tasks | about 310-470 tasks |

The paired row assumes the baseline's own churn of about 0.07. All 129 public tasks, paired, can just about detect a
10-point gain and cannot detect a 5-point gain. A leaderboard submission on about 60 public tasks is one unpaired draw.

## 8. Held-out and leaderboard check

| Arm | Held-out resolved | Wilson 95% | Paired vs A0 | Eval time |
|---|---|---|---|---|
| A0 baseline | 9/47 (0.19) | 0.10-0.33 | - | 66 min |
| A2 4 min / 28 calls (two runs) | 11/47 and 9/47 | 0.14-0.37, 0.10-0.33 | p = 0.69, 1.00 | 49 and 48 min |
| A5 thinking 1536 | 10/47 (0.21) | 0.12-0.35 | p = 1.00 | 65 min |
| B2 repo field guides | 11/47 (0.23) | 0.14-0.37 | p = 0.62 | - |

The held-out tasks repeat the dev result: the baseline's held-out rate (0.19) sits within noise of its dev rate (0.18),
and no arm improves resolves measurably. The 4-minute cap uses about a quarter less evaluation time with no measurable
loss, on tasks it was not tuned on.

Our first leaderboard entry used that configuration (A2) and scored 0.12 on the public split, below its held-out 0.21.
On about 60 public tasks, 0.12 is roughly 7 resolved, with a Wilson interval of about 0.06-0.22, which overlaps the
held-out interval. The gap may be noise, the shift from four open-source repositories to private ones, or both; one
leaderboard draw cannot separate them. A second entry (B2, at 6 minutes per task) also tests whether the longer cap
fits the total budget.

## 9. Limitations and related work

The public tasks come from four open-source repositories, and 52% are fastapi. The hidden tasks come from private
repositories with an unknown mix, so our resolve rates need not transfer, though the noise argument does not depend on
the mix. We ran at most three repeats of any arm and 30 dev tasks per run, limited by the weekly GPU quota, so small true
effects remain possible; our claim is that they are not detectable at this scale, not that they are absent. We tested
one model and the host's harness only.

The task format follows SWE-bench (Jimenez et al., 2024), and the tool-based agent design follows SWE-agent (Yang et
al., 2024). Our baseline is the host's starter kit.

## 10. Interim status

The paper deadline falls three weeks before the competition closes, so this is a midpoint report. Its main lesson
shapes the rest of our work: we stop choosing between configurations by single 30-task runs. A candidate must beat the
baseline paired on all 129 public tasks before it reaches the leaderboard, and only changes that address the generated-
token budget directly (fewer, cheaper steps per task) are worth that cost. The per-task cap remains the lever we tune
for the final entries.
