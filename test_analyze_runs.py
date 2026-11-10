"""Tests for analyze_runs.py. Run: python test_analyze_runs.py"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_runs as A


def write_run(root, name, resolved_map, secs=100):
    d = os.path.join(root, name)
    os.makedirs(d)
    with open(os.path.join(d, 'summary.jsonl'), 'w') as f:
        for tid, ok in resolved_map.items():
            f.write(json.dumps({'instance_id': tid, 'resolved': ok, 'patch_chars': 10 if ok else 0,
                                'duration_seconds': secs}) + '\n')


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_wilson_known_values(self):
        lo, hi = A.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3)
        self.assertAlmostEqual(hi, 0.7634, places=3)
        self.assertEqual(A.wilson(0, 10)[0], 0.0)
        self.assertTrue(all(x != x for x in A.wilson(0, 0)))

    def test_mcnemar_exact(self):
        self.assertEqual(A.mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(A.mcnemar_exact(0, 6), 2 / 64)
        self.assertAlmostEqual(A.mcnemar_exact(3, 3), 1.0)
        self.assertLess(A.mcnemar_exact(1, 12), 0.01)

    def test_report_noise_floor_from_repeats(self):
        write_run(self.d, 'A0-r1', {'t1': True, 't2': False, 't3': True, 't4': False})
        write_run(self.d, 'A0-r2', {'t1': True, 't2': True, 't3': False, 't4': False})
        rep = A.arm_report(A.load_runs(self.d))['A0']
        self.assertEqual(rep['shared_tasks'], 4)
        self.assertEqual(rep['tasks_that_flip_between_repeats'], 2)
        self.assertEqual(rep['flip_rate'], 0.5)
        self.assertEqual(rep['pooled_rate'], 0.5)
        self.assertEqual(rep['runs']['r1']['rate'], 0.5)
        self.assertEqual(rep['no_patch'], 4)

    def test_compare_uses_shared_tasks_and_majority(self):
        write_run(self.d, 'A0-r1', {'t1': True, 't2': False, 't3': False, 'x': True})
        write_run(self.d, 'A1-r1', {'t1': True, 't2': True, 't3': True})
        c = A.compare(A.load_runs(self.d), 'A0', 'A1')
        self.assertEqual((c['shared_tasks'], c['both'], c['only_a'], c['only_b']), (3, 1, 0, 2))
        self.assertAlmostEqual(c['mcnemar_p'], 0.5)

    def test_load_ignores_dirs_without_summary_or_dash(self):
        os.makedirs(os.path.join(self.d, 'notarun'))
        os.makedirs(os.path.join(self.d, 'A0-empty'))
        self.assertEqual(A.load_runs(self.d), {})
        self.assertEqual(A.main([self.d]), 1)

    def test_token_stats_by_outcome(self):
        write_run(self.d, 'A0-r1', {'t1': True, 't2': False}, secs=100)
        tdir = os.path.join(self.d, 'A0-r1', 'results', 'traces')
        os.makedirs(tdir)
        for tid, comp in (('t1', 3000), ('t2', 500)):
            with open(os.path.join(tdir, 'trace_%s.json' % tid), 'w') as f:
                json.dump({'final_metrics': {'total_prompt_tokens': 10000, 'total_completion_tokens': comp, 'total_steps': 4}}, f)
        with open(os.path.join(tdir, 'trace_orphan.json'), 'w') as f:
            json.dump({'final_metrics': {}}, f)
        s = A.token_stats(os.path.join(self.d, 'A0-r1'))
        self.assertEqual(s['resolved'], {'n': 1, 'mean_prompt_tokens': 10000, 'mean_completion_tokens': 3000,
                                         'mean_steps': 4.0, 'completion_tokens_per_second': 30.0})
        self.assertEqual(s['finished_no_patch']['mean_completion_tokens'], 500)
        self.assertNotIn('orphan', json.dumps(s))

    def test_non_repeat_tags_are_separate(self):
        write_run(self.d, 'A0-r1', {'t1': True, 't2': False})
        write_run(self.d, 'A0-c1', {'t1': False})
        write_run(self.d, 'A0-h1', {'h1': True})
        runs = A.load_runs(self.d)
        self.assertEqual(sorted(runs), [('A0', 'r1'), ('A0@c1', 'c1'), ('A0@h1', 'h1')])
        rep = A.arm_report(runs)
        self.assertEqual(rep['A0']['pooled_rate'], 0.5)
        self.assertEqual(rep['A0@h1']['pooled_rate'], 1.0)
        c = A.compare(runs, 'A0', 'A0@c1')
        self.assertEqual((c['shared_tasks'], c['only_a']), (1, 1))


if __name__ == '__main__':
    unittest.main()
