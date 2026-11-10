"""locate skill: ranks the defining source file first, ignores .github templates and tests as edit targets, names the
test file, and degrades to os.walk without git. Arm C2 wiring: valid arm, skill present, first-call instruction."""
import os, shutil, subprocess, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'skills_src', 'locate', 'scripts'))
import locate

FILES = {
    'pkg/__init__.py': '',
    'pkg/routing.py': 'def add_api_route(path, endpoint):\n    """register a route"""\n    return path\n\nclass APIRouter:\n    pass\n',
    'pkg/encoders.py': 'def jsonable_encoder(obj):\n    return obj\n',
    'pkg/utils.py': 'def helper():\n    return 1\n',
    'tests/test_routing.py': 'from pkg.routing import add_api_route\n\ndef test_add_api_route():\n    assert add_api_route("/a", None)\n',
    '.github/pull_request_template.md': 'Please describe the change. Pull request checklist. routing route path endpoint.\n',
    'CHANGELOG.md': 'routing route add_api_route fixed\n',
}
ISSUE = '''<!-- Please start with a GitHub discussion -->
`add_api_route` ignores the endpoint when the path has a trailing slash.
- [ ] I searched the docs
Calling APIRouter.add_api_route("/items/", endpoint) registers the wrong route.'''


def make_repo(git=True):
    d = tempfile.mkdtemp()
    for p, c in FILES.items():
        os.makedirs(os.path.join(d, os.path.dirname(p)), exist_ok=True)
        open(os.path.join(d, p), 'w', encoding='utf-8').write(c)
    if git and shutil.which('git'):
        for cmd in (['init', '-q'], ['add', '-A'], ['-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'x']):
            subprocess.run(['git', '-C', d] + cmd, check=True, capture_output=True)
    return d


class Locate(unittest.TestCase):
    def test_defining_file_first_templates_and_tests_excluded(self):
        src, tests, *_ = locate.rank(make_repo(), ISSUE)
        names = [f for f, _ in src]
        self.assertEqual(names[0], 'pkg/routing.py')
        self.assertNotIn('.github/pull_request_template.md', names[:3])
        self.assertTrue(all(not locate.is_test(f) for f in names))
        self.assertEqual(tests[0][0], 'tests/test_routing.py')

    def test_without_git_walks_the_tree(self):
        src, *_ = locate.rank(make_repo(git=False), ISSUE)
        self.assertEqual(src[0][0], 'pkg/routing.py')

    def test_cli_prints_files_and_lines(self):
        import io, contextlib
        d = make_repo(); buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = locate.main(['--query', ISSUE, '--root', d])
        out = buf.getvalue()
        self.assertEqual(rc, 0); self.assertIn('LIKELY FILES TO EDIT', out); self.assertIn('pkg/routing.py:', out)
        self.assertIn('def add_api_route', out); self.assertLess(len(out.splitlines()), 140)

    def test_clean_query_drops_template_noise(self):
        q = locate.clean_query(ISSUE)
        self.assertNotIn('Please start', q); self.assertNotIn('I searched', q); self.assertIn('add_api_route', q)


class ArmC2(unittest.TestCase):
    def test_arm_valid_with_locate_and_first_call(self):
        import build_deveval as B
        arm = B.load_arm('C2'); B.validate_arm(arm)
        a0 = B.load_arm('A0')
        self.assertEqual(arm['evaluation'], a0['evaluation']); self.assertEqual(arm['skills'], ['locate'])
        sysmd = open(os.path.join(HERE, 'arms', 'C2', 'system.md'), encoding='utf-8').read()
        self.assertIn('## First call (mandatory): locate', sysmd)
        self.assertIn('NEVER modify, create, or delete test files', sysmd)
        files = B.render_agent_files(arm)
        self.assertTrue(any(k.endswith('locate/scripts/locate.py') for k in files))


if __name__ == '__main__':
    unittest.main()
