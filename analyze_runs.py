"""Aggregate Gemma dev-eval runs: resolve rates with intervals, run-to-run noise, and paired arm comparisons.

Why: one leaderboard score cannot rank agent configurations when the same submission scores 0.12 to 0.22 across runs.
Each dev-eval notebook writes summary.jsonl (one row per task: instance_id, resolved, patch_chars, tool_calls,
duration_seconds). This tool reads several runs and reports, per arm: the resolve rate with a Wilson 95% interval,
per-task agreement between repeats of the same arm (the noise floor), and for two arms on the same tasks an exact
two-sided McNemar test on the discordant pairs, so "arm B beats arm A" is a measured claim with a p-value.

Usage:
  python analyze_runs.py <runs_dir>                 # runs_dir/<ARM>-<TAG>/summary.jsonl
  python analyze_runs.py <runs_dir> --compare A0 A1
"""
import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict


def wilson(k, n, z=1.96):
    """Wilson score interval for k successes in n trials; (nan, nan) for n == 0."""
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_exact(b, c):
    """Exact two-sided McNemar p-value from the discordant counts b (A only) and c (B only)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def load_runs(runs_dir):
    """{(arm, tag): {instance_id: row}} from runs_dir/<ARM>-<TAG>/summary.jsonl (tag = text after the first '-')."""
    out = {}
    for name in sorted(os.listdir(runs_dir)):
        p = os.path.join(runs_dir, name, 'summary.jsonl')
        if '-' not in name or not os.path.isfile(p):
            continue
        arm, tag = name.split('-', 1)
        if not re.fullmatch(r'r\d+', tag):
            # Why: A0-c1 (concurrency 1, 12 tasks) and A0-h1 (held-out) are different conditions, not repeats.
            arm = '%s@%s' % (arm, tag)
        with open(p, encoding='utf-8') as f:
            rows = [json.loads(line) for line in f if line.strip()]
        out[(arm, tag)] = {r['instance_id']: r for r in rows}
    return out


def arm_report(runs):
    """Per arm: pooled rate + interval, per-run rates, and repeat agreement on shared tasks."""
    by_arm = defaultdict(dict)
    for (arm, tag), rows in runs.items():
        by_arm[arm][tag] = rows
    rep = {}
    for arm, tags in sorted(by_arm.items()):
        per_run = {t: (sum(r['resolved'] for r in rows.values()), len(rows)) for t, rows in sorted(tags.items())}
        k = sum(v[0] for v in per_run.values())
        n = sum(v[1] for v in per_run.values())
        shared = set.intersection(*(set(rows) for rows in tags.values())) if len(tags) > 1 else set()
        flips = sum(1 for i in shared if len({tags[t][i]['resolved'] for t in tags}) > 1)
        rep[arm] = {
            'runs': {t: {'resolved': a, 'n': b, 'rate': a / b if b else None} for t, (a, b) in per_run.items()},
            'pooled_rate': k / n if n else None, 'wilson95': wilson(k, n),
            'shared_tasks': len(shared), 'tasks_that_flip_between_repeats': flips,
            'flip_rate': (flips / len(shared)) if shared else None,
            'no_patch': sum(1 for rows in tags.values() for r in rows.values() if not r.get('patch_chars')),
            'mean_task_seconds': _mean([r.get('duration_seconds') for rows in tags.values() for r in rows.values()]),
        }
    return rep


OUTCOMES = ('resolved', 'timeout_no_patch', 'timeout_patch_failed', 'finished_patch_failed', 'finished_no_patch')


def outcome(row):
    """Classify one task row. Why: in A0-r1 most failures were session timeouts, which a single rate hides; the
    paper's failure taxonomy and the budget-allocation argument both need this split."""
    if row.get('resolved'):
        return 'resolved'
    timed_out = 'timeout' in str(row.get('error') or '').lower()
    patched = bool(row.get('patch_chars'))
    if timed_out:
        return 'timeout_patch_failed' if patched else 'timeout_no_patch'
    return 'finished_patch_failed' if patched else 'finished_no_patch'


def taxonomy(runs):
    """Per arm: counts of each outcome over all its runs, plus mean seconds of resolved tasks."""
    out = {}
    for (arm, _tag), rows in sorted(runs.items()):
        t = out.setdefault(arm, {k: 0 for k in OUTCOMES})
        for r in rows.values():
            t[outcome(r)] += 1
    for arm in out:
        out[arm]['resolved_mean_seconds'] = _mean([r.get('duration_seconds') for (a, _), rows in runs.items()
                                                   if a == arm for r in rows.values() if r.get('resolved')])
    return out


def token_stats(run_dir):
    """Mean prompt/completion tokens and effective completion tokens/s per outcome, from results/traces/*.json.

    Why: A0-r1 showed timeouts generate far more completion tokens than resolved tasks; the paper's mechanism claim
    (generation volume, not search, runs out the 6-minute cap) needs these numbers per run, reproducibly.
    Joins each trace_<id>.json (final_metrics) with summary.jsonl rows; tasks without a trace are skipped.
    """
    rows = {}
    with open(os.path.join(run_dir, 'summary.jsonl'), encoding='utf-8') as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                rows[r['instance_id']] = r
    groups = defaultdict(list)
    tdir = os.path.join(run_dir, 'results', 'traces')
    for name in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        if not (name.startswith('trace_') and name.endswith('.json')):
            continue
        iid = name[len('trace_'):-len('.json')]
        if iid not in rows:
            continue
        with open(os.path.join(tdir, name), encoding='utf-8') as f:
            fm = json.load(f).get('final_metrics') or {}
        groups[outcome(rows[iid])].append((fm.get('total_prompt_tokens') or 0, fm.get('total_completion_tokens') or 0,
                                           rows[iid].get('duration_seconds') or 0, fm.get('total_steps') or 0))
    out = {}
    for k, g in sorted(groups.items()):
        secs = sum(x[2] for x in g)
        out[k] = {'n': len(g), 'mean_prompt_tokens': round(sum(x[0] for x in g) / len(g)),
                  'mean_completion_tokens': round(sum(x[1] for x in g) / len(g)),
                  'mean_steps': round(sum(x[3] for x in g) / len(g), 1),
                  'completion_tokens_per_second': round(sum(x[1] for x in g) / secs, 1) if secs else None}
    return out


def _mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return sum(xs) / len(xs) if xs else None


def majority(rows_by_tag, task):
    votes = [rows[task]['resolved'] for rows in rows_by_tag.values() if task in rows]
    return sum(votes) * 2 > len(votes)


def compare(runs, arm_a, arm_b):
    """Paired comparison on tasks both arms ran (majority vote across each arm's repeats)."""
    a = {t: r for (arm, t), r in runs.items() if arm == arm_a}
    b = {t: r for (arm, t), r in runs.items() if arm == arm_b}
    if not a or not b:
        raise ValueError('no runs for %s or %s' % (arm_a, arm_b))
    tasks_a = set.union(*(set(r) for r in a.values()))
    tasks_b = set.union(*(set(r) for r in b.values()))
    shared = sorted(tasks_a & tasks_b)
    only_a = sum(1 for t in shared if majority(a, t) and not majority(b, t))
    only_b = sum(1 for t in shared if majority(b, t) and not majority(a, t))
    both = sum(1 for t in shared if majority(a, t) and majority(b, t))
    return {'arm_a': arm_a, 'arm_b': arm_b, 'shared_tasks': len(shared), 'both': both,
            'only_a': only_a, 'only_b': only_b, 'mcnemar_p': mcnemar_exact(only_a, only_b)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('runs_dir')
    ap.add_argument('--compare', nargs=2, metavar=('ARM_A', 'ARM_B'))
    ap.add_argument('--tokens', action='store_true', help='per-run token stats by outcome from traces')
    a = ap.parse_args(argv)
    runs = load_runs(a.runs_dir)
    if not runs:
        print('no runs with summary.jsonl under %s' % a.runs_dir)
        return 1
    print(json.dumps(arm_report(runs), indent=2))
    print(json.dumps({'taxonomy': taxonomy(runs)}, indent=2))
    if a.tokens:
        for name in sorted(os.listdir(a.runs_dir)):
            d = os.path.join(a.runs_dir, name)
            if os.path.isfile(os.path.join(d, 'summary.jsonl')):
                print(json.dumps({'tokens': name, 'by_outcome': token_stats(d)}, indent=2))
    if a.compare:
        print(json.dumps(compare(runs, *a.compare), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
