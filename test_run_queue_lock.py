"""`add` must wait for a running tick's lock , so a tick cannot save over an addition (2026-11-08)."""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_queue as Q


class LockWait(unittest.TestCase):
    def test_waits_until_the_tick_releases(self):
        tries = iter([None, None, '/q.lock'])
        slept = []
        self.assertEqual(Q.acquire_lock_wait('/q', timeout=60, poll=5, acquire=lambda p: next(tries), sleep=slept.append), '/q.lock')
        self.assertEqual(slept, [5, 5])

    def test_gives_up_after_timeout(self):
        self.assertIsNone(Q.acquire_lock_wait('/q', timeout=10, poll=5, acquire=lambda p: None, sleep=lambda s: None))

    def test_add_through_main_keeps_runs_written_meanwhile(self):
        d = tempfile.mkdtemp(); qp = os.path.join(d, 'q.json')
        Q.save_queue(qp, {'runs': [{'arm': 'A0', 'tag': 'r1', 'state': 'done'}]})
        Q.main(['add', '--queue', qp, '--arm', 'A0', '--tag', 'r9'])
        ids = [Q.run_id(r) for r in Q.load_queue(qp)['runs']]
        self.assertEqual(ids, ['A0-r1', 'A0-r9'])
        self.assertFalse(os.path.exists(qp + '.lock'))


if __name__ == '__main__':
    unittest.main()
