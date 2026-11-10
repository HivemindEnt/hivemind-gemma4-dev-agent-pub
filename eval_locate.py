"""Offline accuracy of skills_src/locate/scripts/locate.py against the gold patches in tasks.jsonl.

For each task: check out base_commit in a local clone, run locate.rank(problem_statement), and score whether the gold
patch's existing, non-test files are in the top 1 / 3 / 5. Tasks whose gold patch only creates new files are counted
separately (no locator can find a file that does not exist yet).

    python eval_locate.py TASKS.jsonl REPOS_DIR [--split dev|heldout|all] [--out report.json]
REPOS_DIR/<owner>__<name> must be a git clone (this script clones missing ones from GitHub).
"""
import argparse, json, os, pathlib, re, subprocess, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'skills_src' / 'locate' / 'scripts'))
import locate, build_deveval as B

DIFF_FILE = re.compile(r'^\+\+\+ b/(\S+)', re.M)


def git(repo, *a, check=True):
    return subprocess.run(['git', '-c', 'safe.directory=*', '-C', str(repo)] + list(a), capture_output=True, text=True, check=check).stdout


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument('tasks'); ap.add_argument('repos'); ap.add_argument('--split', default='dev')
    ap.add_argument('--out'); a = ap.parse_args(argv)
    tasks = [json.loads(l) for l in open(a.tasks, encoding='utf-8') if l.strip()]
    dev, held = B.split([t['instance_id'] for t in tasks])
    keep = set(dev) if a.split == 'dev' else set(held) if a.split == 'heldout' else {t['instance_id'] for t in tasks}
    repos = pathlib.Path(a.repos); repos.mkdir(parents=True, exist_ok=True)
    rows = []
    for t in sorted((t for t in tasks if t['instance_id'] in keep), key=lambda t: (t['repo'], t['created_at'])):
        rp = repos / t['repo'].replace('/', '__')
        if not rp.exists():
            subprocess.run(['git', 'clone', '-q', f"https://github.com/{t['repo']}.git", str(rp)], check=True)
        if git(rp, 'cat-file', '-t', t['base_commit'], check=False).strip() != 'commit':
            git(rp, 'fetch', '-q', 'origin', t['base_commit'], check=False)
        git(rp, 'checkout', '-q', '-f', t['base_commit']); git(rp, 'clean', '-qfdx')
        gold = sorted(set(DIFF_FILE.findall(t['patch'])))
        existing = [g for g in gold if (rp / g).exists() and not locate.is_test(g)]
        t0 = time.perf_counter(); res = locate.rank(str(rp), t['problem_statement'], top=5); dt = time.perf_counter() - t0
        got = [f for f, _ in res[0]] if res and res[0] else []
        row = {'id': t['instance_id'], 'gold': gold, 'gold_existing': existing, 'top5': got, 'seconds': round(dt, 2)}
        if existing:
            for k in (1, 3, 5): row[f'hit@{k}'] = any(g in got[:k] for g in existing)
        rows.append(row)
        print(t['instance_id'], 'new-files-only' if not existing else {k: row[f'hit@{k}'] for k in (1, 3, 5)}, f'{dt:.1f}s', flush=True)
    sc = [r for r in rows if r['gold_existing']]
    summ = {'split': a.split, 'tasks': len(rows), 'scorable': len(sc), 'new_files_only': len(rows) - len(sc),
            **{f'hit@{k}': round(sum(r[f'hit@{k}'] for r in sc) / max(len(sc), 1), 3) for k in (1, 3, 5)},
            'median_seconds': sorted(r['seconds'] for r in rows)[len(rows) // 2] if rows else None}
    print('SUMMARY', json.dumps(summ))
    if a.out: pathlib.Path(a.out).write_text(json.dumps({'summary': summ, 'rows': rows}, indent=1))


if __name__ == '__main__':
    main()
