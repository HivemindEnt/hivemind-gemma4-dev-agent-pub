"""Queue runner for Gemma dev-eval kernels: one `tick` fetches finished runs and fills free GPU slots.

Why: each dev-eval run takes 40-70 minutes on Kaggle, and the account allows only 2 batch GPU
sessions at once. On 2026-11-03 every arm change needed a manual check-in to look at kernel status, fetch outputs and
push the next notebook. That meant 15+ check-ins a day, two lost runs from push errors the CLI reports with exit code 0,
and runs started late. This tool keeps an ordered queue of runs in a JSON file and does all of that in one idempotent
command. Running it from any check-in (or a scheduler) loses nothing and never exceeds the session cap.

Queue file (JSON): {"runs": [{"arm": "A2", "tag": "r2", "subset": 30, "concurrency": 4, "heldout": false,
                              "state": "pending"}, ...]}
States: pending -> running -> done | error. A run is identified by <ARM>-<TAG>; its outputs go to <runs_dir>/<ARM>-<TAG>.

Usage (Kaggle credentials come from the environment: KAGGLE_USERNAME / KAGGLE_API_TOKEN):
  python run_queue.py tick   --queue Q.json --runs-dir DIR --tasks tasks.jsonl [--max-sessions 2] [--dry-run]
  python run_queue.py add    --queue Q.json --arm A6 --tag r2 [--subset 30] [--concurrency 4] [--heldout]
  python run_queue.py status --queue Q.json
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_deveval as B  # noqa: E402

RUNNING, DONE, ERROR = 'running', 'done', 'error'
TERMINAL_OK = 'COMPLETE'
TERMINAL_BAD = ('ERROR', 'CANCEL_ACKNOWLEDGED', 'CANCELLED')


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class KaggleCLI:
    """Thin wrapper over the kaggle CLI. Every call returns (exit_code, combined_output)."""

    def __init__(self, user=None, exe=None):
        # KAGGLE_EXE: the scheduled tick on pc-2 points this at kg.cmd, which carries the credentials (2026-11-08)
        self.user = user or os.environ.get('KAGGLE_USERNAME', B.KAGGLE_USER)
        self.exe = exe or os.environ.get('KAGGLE_EXE', 'kaggle')

    def _run(self, args, timeout=600):
        p = subprocess.run([self.exe] + args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or '') + (p.stderr or '')

    def status(self, slug):
        rc, out = self._run(['kernels', 'status', '%s/%s' % (self.user, slug)], timeout=120)
        m = re.search(r'KernelWorkerStatus\.([A-Z_]+)', out)
        return m.group(1) if m else ('NOT_FOUND' if '404' in out else 'UNKNOWN')

    def push(self, folder):
        rc, out = self._run(['kernels', 'push', '-p', folder], timeout=300)
        # The CLI exits 0 even when it refuses the push (e.g. "Maximum batch GPU session count of 2 reached").
        ok = rc == 0 and 'push error' not in out.lower()
        return ok, out.strip()[-400:]

    def output(self, slug, dest):
        rc, out = self._run(['kernels', 'output', '%s/%s' % (self.user, slug), '-p', dest, '-o'], timeout=900)
        return rc == 0, out.strip()[-400:]


LOCK_STALE_SECONDS = 1800


def acquire_lock(queue_path, stale=LOCK_STALE_SECONDS):
    """Exclusive lock beside the queue file. Why: a tick that fetches outputs can outlast a caller's wait. A second
    tick started meanwhile would read the same pending run and push it twice. Returns the lock path, or None
    when another live tick holds it (locks older than `stale` seconds are taken over)."""
    lock = queue_path + '.lock'
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, now().encode())
            os.close(fd)
            return lock
        except FileExistsError:
            import time
            if time.time() - os.path.getmtime(lock) > stale:
                os.remove(lock)
                continue
            return None
    return None



def acquire_lock_wait(queue_path, timeout=1200, poll=5, acquire=None, sleep=None):
    """Like acquire_lock, but waits for a running tick to finish. Why (2026-11-08): `add` wrote the queue without the
    lock, so a tick holding it (minutes, while pushing) could save its own copy over the addition. Found while chasing
    two runs that went missing; that loss was a mistyped queue path (cmd expanded an unset %Q%), but the race is real."""
    import time
    acquire = acquire or acquire_lock; sleep = sleep or time.sleep
    waited = 0
    while True:
        lock = acquire(queue_path)
        if lock or waited >= timeout:
            return lock
        sleep(poll); waited += poll


def load_queue(path):
    if not os.path.exists(path):
        return {'runs': []}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_queue(path, q):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(q, f, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def run_id(r):
    return '%s-%s' % (r['arm'], r['tag'])


def add(q, arm, tag, subset=30, concurrency=4, heldout=False):
    if any(run_id(r) == '%s-%s' % (arm, tag) for r in q['runs']):
        raise ValueError('run %s-%s already queued' % (arm, tag))
    B.load_arm(arm)  # fail now, not at push time, on an invalid arm
    q['runs'].append({'arm': arm, 'tag': tag, 'subset': int(subset), 'concurrency': int(concurrency),
                      'heldout': bool(heldout), 'state': 'pending', 'added': now()})
    return q


def build_run(r, tasks, runs_dir):
    """Write the notebook + kernel metadata for run r into runs_dir/<ARM>-<TAG> (same as build_deveval build)."""
    arm = B.load_arm(r['arm'])
    ids = B.load_ids(tasks)
    dev, held = B.split(ids)
    task_ids = held if r.get('heldout') else B.subset(dev, r.get('subset', 30))
    out = os.path.join(runs_dir, run_id(r))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'notebook.ipynb'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(B.build_notebook(arm, task_ids, r.get('concurrency', 4), r['tag']), f, indent=1)
    with open(os.path.join(out, 'kernel-metadata.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(B.kernel_metadata(arm, r['tag']), f, indent=2)
    return out, len(task_ids)


def tick(q, kaggle, tasks, runs_dir, max_sessions=2, dry_run=False):
    """Advance the queue once. Returns a list of event strings; mutates q."""
    events = []
    # 1. Running runs: fetch the finished ones.
    for r in q['runs']:
        if r['state'] != RUNNING:
            continue
        slug = B.kernel_slug(r['arm'], r['tag'])
        st = kaggle.status(slug)
        r['last_status'] = st
        if st == TERMINAL_OK or st in TERMINAL_BAD:
            dest = os.path.join(runs_dir, run_id(r))
            if not dry_run:
                ok, msg = kaggle.output(slug, dest)
                if not ok:
                    events.append('%s: %s but output fetch failed (%s); will retry next tick' % (run_id(r), st, msg))
                    continue
            summary = os.path.join(dest, 'summary.json')
            if st == TERMINAL_OK and os.path.exists(summary):
                r['state'] = DONE
                with open(summary, encoding='utf-8') as f:
                    s = json.load(f)
                r['result'] = {k: s.get(k) for k in ('resolved', 'n', 'rate', 'no_patch', 'eval_seconds')}
            else:
                r['state'] = ERROR
                r['result'] = {'status': st, 'summary_present': os.path.exists(summary)}
            r['finished'] = now()
            events.append('%s: %s -> %s %s' % (run_id(r), st, r['state'], json.dumps(r['result'])))
    # 2. Fill free slots, in queue order. The cap counts our own running runs; Kaggle's refusal is the backstop.
    busy = sum(1 for r in q['runs'] if r['state'] == RUNNING)
    for r in q['runs']:
        if busy >= max_sessions:
            break
        if r['state'] != 'pending':
            continue
        folder, n = build_run(r, tasks, runs_dir)
        if dry_run:
            events.append('%s: would push %d tasks from %s' % (run_id(r), n, folder))
            busy += 1
            continue
        ok, msg = kaggle.push(folder)
        if not ok:
            events.append('%s: push refused (%s); stays pending' % (run_id(r), msg))
            break  # a refusal (usually the session cap) will refuse the rest too
        r['state'] = RUNNING
        r['pushed'] = now()
        busy += 1
        events.append('%s: pushed (%d tasks)' % (run_id(r), n))
    return events


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('tick')
    t.add_argument('--queue', required=True); t.add_argument('--runs-dir', required=True)
    t.add_argument('--tasks', required=True); t.add_argument('--max-sessions', type=int, default=2)
    t.add_argument('--dry-run', action='store_true')
    a_ = sub.add_parser('add')
    a_.add_argument('--queue', required=True); a_.add_argument('--arm', required=True); a_.add_argument('--tag', required=True)
    a_.add_argument('--subset', type=int, default=30); a_.add_argument('--concurrency', type=int, default=4)
    a_.add_argument('--heldout', action='store_true')
    s = sub.add_parser('status'); s.add_argument('--queue', required=True)
    a = ap.parse_args(argv)
    q = load_queue(a.queue)
    if a.cmd == 'add':
        lock = acquire_lock_wait(a.queue)
        if lock is None:
            print('ADD_SKIPPED a tick has held %s.lock for too long; try again' % a.queue)
            return 3
        try:
            save_queue(a.queue, add(load_queue(a.queue), a.arm, a.tag, a.subset, a.concurrency, a.heldout))
        finally:
            os.remove(lock)
        print('queued %s-%s' % (a.arm, a.tag))
    elif a.cmd == 'status':
        for r in q['runs']:
            print('%-8s %-8s %s' % (run_id(r), r['state'], json.dumps(r.get('result', ''))))
    else:
        lock = acquire_lock(a.queue)
        if lock is None:
            print('TICK_SKIPPED another tick holds %s.lock' % a.queue)
            return 3
        try:
            q = load_queue(a.queue)  # re-read under the lock
            events = tick(q, KaggleCLI(), a.tasks, a.runs_dir, a.max_sessions, a.dry_run)
            if not a.dry_run:
                save_queue(a.queue, q)
        finally:
            os.remove(lock)
        for e in events:
            print(e)
        print('TICK_DONE running=%d pending=%d' % (sum(r['state'] == RUNNING for r in q['runs']),
                                                  sum(r['state'] == 'pending' for r in q['runs'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
