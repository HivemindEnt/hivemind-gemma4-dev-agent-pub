"""Arm C1 (reproduce-first): valid arm, renders, keeps A0's protected-test rule, and its repro never enters the patch."""
import os, re, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_deveval as B


class C1(unittest.TestCase):
    def setUp(self):
        self.arm = B.load_arm('C1')
        self.sys = open(os.path.join(HERE, 'arms', 'C1', 'system.md'), encoding='utf-8').read()

    def test_valid_and_same_budget_as_a0(self):
        B.validate_arm(self.arm)
        a0 = B.load_arm('A0')
        self.assertEqual(self.arm['evaluation'], a0['evaluation'])      # one change at a time: the prompt, not the budget
        self.assertEqual(self.arm['tools'], a0['tools'])
        self.assertEqual(self.arm.get('family'), 'reproduce-first')

    def test_prompt_keeps_a0_and_adds_the_repro_step(self):
        a0 = open(os.path.join(HERE, 'arms', 'A0', 'system.md'), encoding='utf-8').read().replace('\r\n', '\n')
        self.assertTrue(self.sys.startswith(a0.rstrip('\n')))
        self.assertIn('NEVER modify, create, or delete test files', self.sys)
        self.assertIn('## Reproduce first (mandatory)', self.sys)

    def test_repro_lives_outside_the_workspace(self):
        paths = set(re.findall(r'`(?:python3 )?(/[\w./-]*repro[\w.]*)`', self.sys))
        self.assertTrue(paths)
        for p in paths:
            self.assertTrue(p.startswith('/tmp/'), p)

    def test_renders(self):
        files = B.render_agent_files(self.arm)
        self.assertTrue(files)
        blob = '\n'.join(v if isinstance(v, str) else '' for v in files.values())
        self.assertIn('/tmp/repro.py', blob)


if __name__ == '__main__':
    unittest.main()
