"""Tests for run_queue.py with a fake Kaggle client. Run: python test_run_queue.py"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_queue as Q  # noqa: E402


class FakeKaggle:
    def __init__(self, statuses=None, refuse_after=None):
        self.statuses = statuses or {}
        self.pushed = []
        self.refuse_after = refuse_after
        self.fetched = []

    def status(self, slug):
        return self.statuses.get(slug, 'RUNNING')

    def push(self, folder):
        if self.refuse_after is not None and len(self.pushed) >= self.refuse_after:
            return False, 'Kernel push error: Maximum batch GPU session count of 2 reached.'
        self.pushed.append(os.path.basename(folder))
        return True, 'ok'

    def output(self, slug, dest):
        self.fetched.append(slug)
        os.makedirs(dest, exist_ok=True)
        if self.statuses.get(slug) == 'COMPLETE':
            with open(os.path.join(dest, 'summary.json'), 'w') as f:
                json.dump({'resolved': 4, 'n': 30, 'rate': 4 / 30, 'no_patch': 2, 'eval_seconds': 100}, f)
        return True, 'ok'


def tasks_file(d):
    p = os.path.join(d, 'tasks.jsonl')
    with open(p, 'w') as f:
        for repo, n in (('fastapi', 40), ('rich', 30), ('requests', 9)):
            for i in range(n):
                f.write(json.dumps({'instance_id': '%s_%d' % (repo, 1000 + i)}) + '\n')
    return p


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.tasks = tasks_file(self.d)
        self.runs = os.path.join(self.d, 'runs')
        self.q = {'runs': []}
        for tag in ('r1', 'r2', 'r3'):
            Q.add(self.q, 'A0', tag)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_add_rejects_duplicates_and_bad_arms(self):
        with self.assertRaises(ValueError):
            Q.add(self.q, 'A0', 'r1')
        with self.assertRaises(Exception):
            Q.add(self.q, 'NO_SUCH_ARM', 'r1')

    def test_fills_up_to_cap_in_order(self):
        k = FakeKaggle()
        ev = Q.tick(self.q, k, self.tasks, self.runs, max_sessions=2)
        self.assertEqual(k.pushed, ['A0-r1', 'A0-r2'])
        self.assertEqual([r['state'] for r in self.q['runs']], ['running', 'running', 'pending'])
        self.assertTrue(os.path.exists(os.path.join(self.runs, 'A0-r1', 'kernel-metadata.json')))
        self.assertEqual(len(ev), 2)

    def test_complete_is_fetched_and_slot_refilled(self):
        k = FakeKaggle()
        Q.tick(self.q, k, self.tasks, self.runs)
        k.statuses['hm-gemma-deveval-a0-r1'] = 'COMPLETE'
        Q.tick(self.q, k, self.tasks, self.runs)
        st = [r['state'] for r in self.q['runs']]
        self.assertEqual(st, ['done', 'running', 'running'])
        self.assertEqual(self.q['runs'][0]['result']['resolved'], 4)
        self.assertEqual(k.pushed, ['A0-r1', 'A0-r2', 'A0-r3'])

    def test_error_is_marked_not_retried(self):
        k = FakeKaggle()
        Q.tick(self.q, k, self.tasks, self.runs)
        k.statuses['hm-gemma-deveval-a0-r2'] = 'ERROR'
        Q.tick(self.q, k, self.tasks, self.runs)
        self.assertEqual(self.q['runs'][1]['state'], 'error')
        self.assertFalse(self.q['runs'][1]['result']['summary_present'])
        self.assertEqual(self.q['runs'][2]['state'], 'running')

    def test_push_refusal_keeps_pending_and_stops(self):
        # CLI exit 0 with "Kernel push error" must not mark the run as running.
        k = FakeKaggle(refuse_after=1)
        ev = Q.tick(self.q, k, self.tasks, self.runs)
        self.assertEqual([r['state'] for r in self.q['runs']], ['running', 'pending', 'pending'])
        self.assertIn('push refused', ev[-1])

    def test_heldout_run_builds_heldout_tasks(self):
        q = {'runs': []}
        Q.add(q, 'A0', 'h1', heldout=True)
        k = FakeKaggle()
        ev = Q.tick(q, k, self.tasks, self.runs)
        dev, held = Q.B.split(Q.B.load_ids(self.tasks))
        self.assertIn('(%d tasks)' % len(held), ev[0])

    def test_dry_run_pushes_nothing(self):
        k = FakeKaggle()
        Q.tick(self.q, k, self.tasks, self.runs, dry_run=True)
        self.assertEqual(k.pushed, [])
        self.assertEqual([r['state'] for r in self.q['runs']], ['pending'] * 3)

    def test_queue_roundtrip_atomic(self):
        p = os.path.join(self.d, 'q.json')
        Q.save_queue(p, self.q)
        self.assertEqual(Q.load_queue(p), self.q)
        self.assertFalse(os.path.exists(p + '.tmp'))

    def test_lock_excludes_second_tick_and_expires(self):
        p = os.path.join(self.d, 'q.json')
        lock = Q.acquire_lock(p)
        self.assertTrue(lock and os.path.exists(lock))
        self.assertIsNone(Q.acquire_lock(p))
        old = os.path.getmtime(lock) - 4000
        os.utime(lock, (old, old))
        self.assertEqual(Q.acquire_lock(p), lock)
        os.remove(lock)


if __name__ == '__main__':
    unittest.main()
