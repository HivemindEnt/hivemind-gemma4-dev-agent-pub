"""Tests for build_deveval.py. Run: python test_build_deveval.py"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_deveval as B

IDS = (['fastapi_%d' % i for i in range(9000, 9067)] + ['rich_%d' % i for i in range(3000, 3048)]
       + ['requests_%d' % i for i in range(6500, 6513)] + ['httpx_3672'])


class T(unittest.TestCase):
    def test_split_is_stable_disjoint_and_order_independent(self):
        dev, held = B.split(IDS)
        self.assertEqual(set(dev) | set(held), set(IDS))
        self.assertFalse(set(dev) & set(held))
        dev2, held2 = B.split(list(reversed(IDS)))
        self.assertEqual((dev, held), (dev2, held2))
        self.assertTrue(0.2 < len(held) / len(IDS) < 0.45, len(held))

    def test_subset_is_repo_proportional_and_deterministic(self):
        dev, _ = B.split(IDS)
        s = B.subset(dev, 30)
        self.assertEqual(len(s), 30)
        self.assertEqual(s, B.subset(list(reversed(dev)), 30))
        self.assertTrue(set(s) <= set(dev))
        n_fast = sum(1 for i in s if i.startswith('fastapi_'))
        expect = 30 * sum(1 for i in dev if i.startswith('fastapi_')) / len(dev)
        self.assertLessEqual(abs(n_fast - expect), 1)
        self.assertEqual(len(B.subset(dev, 10 ** 6)), len(dev))

    def test_repo_of_handles_underscores(self):
        self.assertEqual(B.repo_of('fastapi_15661'), 'fastapi')
        self.assertEqual(B.repo_of('my_repo_12'), 'my_repo')

    def test_validate_arm_rejects_unsafe_configs(self):
        arm = B.load_arm('A0')
        bad = dict(arm, model='gpt-4')
        self.assertRaises(ValueError, B.validate_arm, bad)
        bad = dict(arm, tools=arm['tools'] + ['exec_python'])
        self.assertRaises(ValueError, B.validate_arm, bad)
        ev = dict(arm['evaluation']); ev.pop('max_time_minutes')
        self.assertRaises(ValueError, B.validate_arm, dict(arm, evaluation=ev))
        self.assertRaises(ValueError, B.validate_arm, dict(arm, system_prompt='  '))

    def test_render_agent_files(self):
        files = B.render_agent_files(B.load_arm('A0'))
        self.assertEqual(sorted(files), ['agent.yaml', 'configs/sampling.yaml', 'eval_config.yaml', 'prompts/system.md'])
        self.assertIn('model: gemma-4-31b-it-qat-w4a16-ct', files['agent.yaml'])
        self.assertIn('max_time_minutes: 6', files['eval_config.yaml'])
        self.assertIn('thinking_budget: 4096', files['configs/sampling.yaml'])
        self.assertIn('include_thoughts: true', files['configs/sampling.yaml'])

    def test_notebook_cells_compile_and_embed_run(self):
        arm = B.load_arm('A0')
        nb = B.build_notebook(arm, ['fastapi_9001', 'rich_3001'], 3, 'r9')
        code = [c['source'] for c in nb['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(code), 4)
        for src in code:
            compile(src, 'cell', 'exec')
        run = json.loads(code[1].split('RUN = json.loads(', 1)[1].split(')\n', 1)[0].strip()[1:-1].encode().decode('unicode_escape'))
        self.assertEqual(run['task_ids'], ['fastapi_9001', 'rich_3001'])
        self.assertEqual(run['concurrency'], 3)

    def test_written_agent_dir_matches_render(self):
        arm = B.load_arm('A0')
        nb = B.build_notebook(arm, ['x_1'], 1, 'r1')
        d = tempfile.mkdtemp()
        try:
            src = nb['cells'][2]['source'].replace('Path("/kaggle/working/agent")', 'Path(%r)' % d)
            exec(src, {'json': json, 'shutil': shutil, 'Path': __import__('pathlib').Path})
            for rel, text in B.render_agent_files(arm).items():
                with open(os.path.join(d, rel), encoding='utf-8') as f:
                    self.assertEqual(f.read(), text)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_kernel_metadata(self):
        m = B.kernel_metadata(B.load_arm('A0'), 'r1')
        self.assertEqual(m['id'], 'hivemindadmin/hm-gemma-deveval-a0-r1')
        self.assertTrue(m['is_private'])
        self.assertFalse(m['enable_internet'])
        self.assertEqual(m['machine_shape'], 'NvidiaL4')
        self.assertEqual(m['model_sources'], ['google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2'])
        self.assertLessEqual(len(B.kernel_slug('A' * 80, 'r1')), 50)

    def test_official_validator_accepts_rendered_dir(self):
        try:
            from adk_submission import validate_directory
            from swegemma.config import build_submission_limits
        except Exception:
            self.skipTest('adk_submission/swegemma not installed (Kaggle wheelhouse only)')
        d = tempfile.mkdtemp()
        try:
            for rel, text in B.render_agent_files(B.load_arm('A0')).items():
                p = os.path.join(d, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(text)
            limits, _ = build_submission_limits()
            validate_directory(d, limits=limits)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_install_cell_fails_clearly_without_wheelhouse(self):
        # A2-r1 died with an opaque "pip install" usage error when the wheelhouse mount was empty.
        self.assertIn('wheelhouse not mounted', B.INSTALL_CELL)
        compile(B.INSTALL_CELL, 'install_cell', 'exec')

    def test_cells_handle_both_mount_layouts(self):
        # Kaggle mounted inputs as /kaggle/input/<slug> in A2-r1 and /kaggle/input/competitions/<slug> in A0/A1.
        for cell in (B.SERVER_CELL, B.EVAL_CELL):
            compile(cell, 'cell', 'exec')
        self.assertIn("Path('/kaggle/input/gemma-4-developer-agent')", B.EVAL_CELL)
        self.assertIn('competition data not mounted', B.EVAL_CELL)
        self.assertIn('/kaggle/input/gemma-4/other/', B.SERVER_CELL)


if __name__ == '__main__':
    unittest.main()
