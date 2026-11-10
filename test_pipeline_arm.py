"""Multi-agent (pipeline) arms, 2026-11-08 explore phase: B1 localize-then-edit."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_deveval as B


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.arm = B.load_arm('B1')
        self.files = B.render_agent_files(self.arm)

    def test_root_is_sequential_over_the_stages(self):
        root = self.files['agent.yaml']
        self.assertIn('agent_class: SequentialAgent', root)
        self.assertLess(root.index('sub_agents/localizer.yaml'), root.index('sub_agents/fixer.yaml'))

    def test_includes_stay_next_to_their_yaml(self):
        # adk_submission resolves !include relative to the including file and blocks '..'
        for rel, text in self.files.items():
            if rel.endswith('.yaml'):
                for line in text.splitlines():
                    if '!include' in line:
                        target = line.split('!include', 1)[1].strip()
                        self.assertNotIn('..', target)
                        self.assertIn(os.path.join(os.path.dirname(rel), target).replace('\\', '/'), self.files)

    def test_localizer_is_read_only_and_publishes_state(self):
        y = self.files['sub_agents/localizer.yaml']
        for t in ('edit_file', 'write_file', 'submit_patch'):
            self.assertNotIn('- ' + t, y)
        self.assertIn('output_key: localization', y)

    def test_fixer_reads_the_report_and_can_submit(self):
        self.assertIn('{localization}', self.files['sub_agents/fixer.md'])
        self.assertIn('- submit_patch', self.files['sub_agents/fixer.yaml'])

    def test_one_model_everywhere(self):
        models = {l.split(':', 1)[1].strip() for t in self.files.values() for l in t.splitlines() if l.startswith('model:')}
        self.assertEqual(models, {self.arm['model']})

    def test_bad_stage_tool_rejected(self):
        arm = dict(self.arm, pipeline=[dict(self.arm['pipeline'][0], tools=['rm_rf'])])
        with self.assertRaises(ValueError):
            B.validate_arm(arm)


if __name__ == '__main__':
    unittest.main()
