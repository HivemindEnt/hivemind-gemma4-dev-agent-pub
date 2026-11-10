"""Field guides (B2) and the pre-submit gate (B3), 2026-11-08."""
import json, os, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_guides as G
import build_deveval as B

PATCH = '--- a/pkg/mod.py\n+++ b/pkg/mod.py\n@@ -1 +1 @@\n-a\n+b\n'
TPATCH = '--- a/tests/test_mod.py\n+++ b/tests/test_mod.py\n@@ -1 +1 @@\n-a\n+b\n'


class Guides(unittest.TestCase):
    def test_files_from_both_header_styles(self):
        self.assertEqual(G.files_in(PATCH), ['pkg/mod.py'])
        self.assertEqual(G.files_in('diff --git a/x.py b/x.py\n'), ['x.py'])

    def test_guides_use_dev_split_only(self):
        d = tempfile.mkdtemp(); tasks = os.path.join(d, 't.jsonl')
        ids = ['org__repo-%d' % i for i in range(60)]
        with open(tasks, 'w') as f:
            for i in ids: f.write(json.dumps({'instance_id': i, 'repo': 'org/repo', 'patch': PATCH, 'test_patch': TPATCH}) + '\n')
        made = G.build(tasks, os.path.join(d, 'skills'))
        dev, held = B.split(ids)
        self.assertEqual(made['repo-guide'], len(dev))
        md = open(os.path.join(d, 'skills', 'repo-guide', 'SKILL.md')).read()
        self.assertTrue(md.startswith('---\nname: repo-guide\n'))
        self.assertIn('`pkg/mod.py` -> `tests/test_mod.py`', md)
        for name in ('new-repo-guide', 'patch-check'):
            self.assertTrue(os.path.isfile(os.path.join(d, 'skills', name, 'SKILL.md')))

    def _repo(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, 'src', 'pkg')); os.makedirs(os.path.join(d, 'tests'))
        open(os.path.join(d, 'src', 'pkg', '__init__.py'), 'w').close()
        open(os.path.join(d, 'src', 'pkg', 'core.py'), 'w').write('x = 1\n')
        open(os.path.join(d, 'tests', 'test_core.py'), 'w').write('def test_x():\n    pass\n')
        open(os.path.join(d, 'pyproject.toml'), 'w').write('[tool.pytest.ini_options]\n')
        for c in (['init', '-q'], ['add', '.'], ['-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'i']):
            subprocess.run(['git', '-C', d] + c, check=True, capture_output=True)
        return d

    def _run(self, src, root):
        p = os.path.join(tempfile.mkdtemp(), 's.py'); open(p, 'w').write(src)
        return subprocess.run([sys.executable, p, root], capture_output=True, text=True).stdout

    def test_scout_on_an_unknown_repo(self):
        out = self._run(G.SCOUT_PY, self._repo())
        self.assertIn('`src/pkg/`', out); self.assertIn('`src/pkg/core.py` -> `tests/test_core.py`', out); self.assertIn('pytest', out)

    def test_precheck_gate(self):
        d = self._repo()
        self.assertIn('RESULT: FIX', self._run(G.PRECHECK_PY, d))           # empty diff
        open(os.path.join(d, 'src', 'pkg', 'core.py'), 'a').write('y = 2\n')
        out = self._run(G.PRECHECK_PY, d)
        self.assertIn('RESULT: OK', out); self.assertIn('tests/test_core.py', out)
        open(os.path.join(d, 'tests', 'test_core.py'), 'a').write('# edited\n')
        open(os.path.join(d, 'src', 'pkg', 'core.py'), 'a').write('def broken(:\n')
        out = self._run(G.PRECHECK_PY, d)
        self.assertIn('protected test file changed', out); self.assertIn('does not compile', out); self.assertIn('RESULT: FIX', out)

    def test_precheck_says_unknown_when_git_cannot_read(self):
        self.assertIn('RESULT: UNKNOWN', self._run(G.PRECHECK_PY, tempfile.mkdtemp()))

    def test_arms_carry_their_skills(self):
        for name, skills in (('B2', 'new-repo-guide'), ('B3', 'patch-check')):
            files = B.render_agent_files(B.load_arm(name))
            self.assertIn('  - skills/%s' % skills, files['agent.yaml'])
            self.assertIn('skills/%s/SKILL.md' % skills, files)


if __name__ == '__main__':
    unittest.main()
