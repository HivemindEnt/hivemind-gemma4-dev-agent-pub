"""Repo field guides for the Gemma dev agent (B2, explore phase 2026-11-08). Design: one guide per known repo, plus a way
to produce a guide for a repo the agent has never seen, inheriting what the known repos have in common.

Generates ADK skills (skills/<name>/SKILL.md, plus scripts/) from the DEV split of the public tasks only, so the
held-out split stays clean for scoring:
  - <repo>-guide: where fixes land (directory frequencies of the gold patches), source -> test file pairs (from the
    test patches), the targeted test command, and the traps that apply to that repo;
  - new-repo-guide: a procedure plus scripts/scout.py, which derives a guide at run time for ANY repo from the
    patterns the known repos share (package layout, tests/test_<module>.py naming, pytest -k, docs examples, protected
    test files). Its output is the same shape as a known-repo guide.
  - patch-check: scripts/precheck.py, a deterministic pre-submit gate (B3): non-empty diff, no protected test files
    touched, changed .py files compile, and the targeted tests for the changed modules.

  python build_guides.py --tasks tasks.jsonl --out skills
"""
import argparse, collections, json, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_deveval as B

HERE = os.path.dirname(os.path.abspath(__file__))
DIFF_FILE = re.compile(r'^(?:diff --git a/(\S+) b/\S+|\+\+\+ b/(\S+))', re.M)   # the task patches use ---/+++ headers

# Traps that hold across the known repos (from the harness rules and the A0-A7 runs); inherited by every guide,
# including the ones scout.py derives for a new repo.
COMMON_TRAPS = [
    'Never edit, create or delete test files (tests/, test_*.py, *_test.py, conftest.py): the grader resets them and an edit there can fail the task.',
    'Never run the whole test suite: one test file, ideally with -k <name>. A full run can take minutes and ends the task by timeout.',
    'A failing test that is unrelated to your change (missing fixture, network, import error elsewhere) is pre-existing. Ignore it; do not try to fix it.',
    'Most fixes touch 1-2 files (110 of the 129 public gold patches). If your diff spans more than 3 files, re-read the problem statement.',
    'Keep exact names from the problem statement: error messages, exception types, parameter names and defaults are checked by hidden tests.',
    'Only a submitted, non-empty patch can score. Leave time to submit: in past runs about a quarter of tasks ended by timeout with no patch at all.',
]
REPO_NOTES = {   # repo-specific traps; only things the public tasks or the harness guide show
    'fastapi/fastapi': ['Documentation examples are executable code under docs_src/ (15 of 67 public fixes touched it) and are tested by tests/test_tutorial/...; when the issue is about a docs example, edit docs_src/, not docs/*.md.',
                        'Many tests import the docs_src example by module path; the test file name usually mirrors the docs_src path.'],
    'Textualize/rich': ['Source lives in rich/ (one module per feature: rich/console.py, rich/cells.py, rich/segment.py, ...); tests mirror it as tests/test_<module>.py.',
                        'Character-width issues land in rich/cells.py (and once, in the public tasks, in the rich/_unicode_data/ tables).'],
    'psf/requests': ['Source is under src/requests/ in recent versions (older checkouts: requests/). Check which exists before editing.',
                     'Most behaviour tests are in tests/test_requests.py; use -k to select one test, since that file is large.'],
    'encode/httpx': ['Source is src/httpx/ (this checkout also has src/ahttpx/); private modules start with _. Tests are under tests/.'],
}


def files_in(diff):
    return sorted({a or b for a, b in DIFF_FILE.findall(diff or '')})


def repo_stats(tasks):
    src_dirs, pairs, test_files = collections.Counter(), collections.Counter(), collections.Counter()
    for t in tasks:
        src = [f for f in files_in(t['patch']) if f.endswith('.py')]
        tst = [f for f in files_in(t['test_patch']) if f.endswith('.py')]
        for f in src: src_dirs[os.path.dirname(f) or '.'] += 1
        for f in tst: test_files[f] += 1
        for s in src:
            for x in tst: pairs[(s, x)] += 1
    return src_dirs, pairs, test_files


def slug(repo):
    return re.sub(r'[^a-z0-9]+', '-', repo.split('/')[-1].lower()).strip('-') + '-guide'


def guide_md(repo, tasks):
    src_dirs, pairs, test_files = repo_stats(tasks)
    name = slug(repo)
    L = ['---', 'name: %s' % name,
         'description: Field guide for the %s repository - where fixes usually land, which test file checks which source file, the exact targeted test command, and the traps. Load it first when /workspace is %s.' % (repo, repo),
         '---', '', '# %s field guide' % repo, '',
         'Built from %d public tasks of this repo (dev split). Use it to skip exploration, not to skip reading the code.' % len(tasks), '',
         '## Where fixes land (share of gold-patch source files)']
    tot = sum(src_dirs.values()) or 1
    for d, n in src_dirs.most_common(8):
        L.append('- `%s/` %d%%' % (d, round(100 * n / tot)))
    L += ['', '## Source file -> test file (seen together in past fixes)']
    for (s, x), _ in pairs.most_common(15):
        L.append('- `%s` -> `%s`' % (s, x))
    L += ['', '## Run one test',
          '`python -m pytest <test file> -x -q -k <test name or keyword>` (never the whole suite). If pytest is missing, `python -m unittest <module>`.', '',
          '## Traps']
    L += ['- ' + t for t in REPO_NOTES.get(repo, []) + COMMON_TRAPS]
    return name, '\n'.join(L) + '\n'


NEW_REPO_MD = """---
name: new-repo-guide
description: For a repository that has no field guide of its own. Builds one at run time from the patterns the known repos share - package layout, how tests are named and run, the docs-example convention, and the traps. Load it when no other *-guide skill matches /workspace.
---

# New repository: build the field guide yourself

The known repos (fastapi, rich, requests, httpx) share a shape. Assume this repo does too until it shows otherwise.

1. Run the scout script once: `run_skill_script` with skill `new-repo-guide` and script `scripts/scout.py` (it reads
   /workspace, edits nothing, and prints a guide in the same format as the known-repo guides). If scripts cannot run,
   do the same by hand with these commands:
   - layout: `ls /workspace` and `ls /workspace/src 2>/dev/null` (the package is the directory with `__init__.py`)
   - tests: `ls /workspace/tests | head -50`
   - runner: `grep -n -A3 "\\[tool.pytest" /workspace/pyproject.toml /workspace/setup.cfg /workspace/tox.ini /workspace/pytest.ini 2>/dev/null`
2. Map the issue to source: the module named in the problem statement, else `search_similar_code` with the error text.
3. Find the test: `tests/test_<module>.py` first (all known repos use this), else `grep -rln "<function name>" tests | head`.
4. Run one test only: `python -m pytest <file> -x -q -k <name>`.

## Inherited traps (true in every known repo)
""" + '\n'.join('- ' + t for t in COMMON_TRAPS) + '\n'

SCOUT_PY = r'''"""Derive a field guide for the repository in /workspace (read-only). Prints Markdown in the known-guide format."""
import configparser, os, re, subprocess, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else '/workspace'


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ''


def packages():
    out = []
    for base in ('', 'src', 'lib'):
        b = os.path.join(ROOT, base)
        if not os.path.isdir(b): continue
        for d in sorted(os.listdir(b)):
            p = os.path.join(b, d)
            if os.path.isfile(os.path.join(p, '__init__.py')) and 'test' not in d and d not in ('docs', 'docs_src', 'scripts', 'examples'):
                out.append((base + '/' + d) if base else d)
    return out


def test_dirs():
    return [d for d in ('tests', 'test', 'testing') if os.path.isdir(os.path.join(ROOT, d))]


def runner():
    for f in ('pyproject.toml', 'setup.cfg', 'tox.ini', 'pytest.ini'):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            t = open(p, encoding='utf-8', errors='replace').read()
            if 'pytest' in t: return 'pytest (configured in %s)' % f
    return 'pytest if installed, else unittest'


def find_test(tdirs, mod):
    # pure Python (no shell find), so it behaves the same in any container
    names = {'test_%s.py' % mod, '%s_test.py' % mod}
    for td in tdirs:
        for dp, _, fs in os.walk(os.path.join(ROOT, td)):
            for f in sorted(fs):
                if f in names:
                    return os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, '/')
    return None


def pairs(pkgs, tdirs, limit=12):
    out = []
    for pkg in pkgs:
        for dp, _, fs in os.walk(os.path.join(ROOT, pkg)):
            for f in fs:
                if not f.endswith('.py') or f == '__init__.py': continue
                mod = f[:-3].lstrip('_')
                hit = find_test(tdirs, mod)
                if hit:
                    out.append((os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, '/'), hit))
                if len(out) >= limit: return out
    return out


pkgs, tds = packages(), test_dirs()
print('# %s field guide (derived by scout.py)' % os.path.basename(os.path.abspath(ROOT)))
print('\n## Layout')
print('- packages: ' + (', '.join('`%s/`' % p for p in pkgs) or 'none found (single-module repo? check top-level *.py)'))
print('- tests: ' + (', '.join('`%s/`' % t for t in tds) or 'no tests/ directory; grep for test_*.py'))
if os.path.isdir(os.path.join(ROOT, 'docs_src')):
    print('- `docs_src/` exists: documentation examples are code and are likely tested; edit them there, not in docs/*.md')
print('- runner: ' + runner())
print('\n## Source file -> test file (by name)')
for s, t in pairs(pkgs, tds):
    print('- `%s` -> `%s`' % (s, t))
print('\n## Run one test\n`python -m pytest <test file> -x -q -k <name>` (never the whole suite)')
'''

PATCH_CHECK_MD = """---
name: patch-check
description: Pre-submit gate. Run it after your edit and before submit_patch - it checks the diff is non-empty, touches no protected test files, compiles, and prints the targeted test command for each changed module.
---

# Patch check (run before submit_patch)

Run `run_skill_script` with skill `patch-check` and script `scripts/precheck.py`. It edits nothing.

- `RESULT: OK` -> run the printed targeted test once; if it passes (or fails only for a pre-existing reason), submit.
- `RESULT: UNKNOWN` -> the script could not read git; check `git -C /workspace status --short` yourself.
- `RESULT: FIX` -> fix every listed problem first. Typical: you touched a test file (revert it with `git checkout -- <file>`),
  a changed file does not compile (read the error line), or the diff is empty.
If scripts cannot run, do it by hand: `git -C /workspace diff --stat`, `python -m py_compile <changed files>`.
"""

PRECHECK_PY = r'''"""Deterministic pre-submit gate for /workspace (read-only)."""
import os, re, subprocess, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else '/workspace'
PROTECTED = re.compile(r'(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$')


def git(*a):
    # safe.directory: the repo may belong to another user than the one running this (git then refuses and prints
    # nothing, which must not be mistaken for an empty diff; found by running the ADK wrapper as root, 2026-11-08)
    r = subprocess.run(['git', '-c', 'safe.directory=*', '-C', ROOT] + list(a), capture_output=True, text=True)
    if r.returncode != 0:
        print('PROBLEM: git failed (%s); check the diff by hand with: git -C %s status --short' % (r.stderr.strip()[:160], ROOT))
        print('RESULT: UNKNOWN')
        sys.exit(0)
    return r.stdout


changed = [l[3:].strip() for l in git('status', '--porcelain', '--untracked-files=all').splitlines() if l.strip()]
changed = [c.split(' -> ')[-1] for c in changed]
problems = []
if not changed:
    problems.append('the diff is empty: nothing would be submitted')
prot = [c for c in changed if PROTECTED.search(c)]
for c in prot:
    problems.append('protected test file changed (revert it: git checkout -- %s, or delete it if you created it)' % c)
for c in changed:
    p = os.path.join(ROOT, c)
    if c.endswith('.py') and os.path.exists(p) and c not in prot:
        r = subprocess.run([sys.executable, '-m', 'py_compile', p], capture_output=True, text=True)
        if r.returncode != 0:
            problems.append('does not compile: %s: %s' % (c, (r.stderr.strip().splitlines() or ['?'])[-1][:200]))
print('changed: ' + (', '.join(changed) or '(none)'))
for c in changed:
    if c.endswith('.py') and c not in prot:
        mod = os.path.basename(c)[:-3].lstrip('_')
        hits = []
        for td in ('tests', 'test'):
            for dp, _, fs in os.walk(os.path.join(ROOT, td)):
                hits += [os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, '/') for f in fs if f == 'test_%s.py' % mod]
        for h in sorted(hits)[:2]:
            print('targeted test: python -m pytest %s -x -q -k <name>' % h)
for p in problems:
    print('PROBLEM: ' + p)
print('RESULT: ' + ('FIX' if problems else 'OK'))
'''


def build(tasks_path, out):
    tasks = [json.loads(l) for l in open(tasks_path, encoding='utf-8') if l.strip()]
    dev, held = B.split([t['instance_id'] for t in tasks])
    dev = set(dev)
    by_repo = collections.defaultdict(list)
    for t in tasks:
        if t['instance_id'] in dev: by_repo[t['repo']].append(t)
    if os.path.isdir(out): shutil.rmtree(out)
    made = {}
    for repo in sorted(set(t['repo'] for t in tasks)):
        name, md = guide_md(repo, by_repo.get(repo, []))
        os.makedirs(os.path.join(out, name), exist_ok=True)
        open(os.path.join(out, name, 'SKILL.md'), 'w', encoding='utf-8', newline='\n').write(md)
        made[name] = len(by_repo.get(repo, []))
    for name, md, scripts in (('new-repo-guide', NEW_REPO_MD, {'scout.py': SCOUT_PY}),
                              ('patch-check', PATCH_CHECK_MD, {'precheck.py': PRECHECK_PY})):
        os.makedirs(os.path.join(out, name, 'scripts'), exist_ok=True)
        open(os.path.join(out, name, 'SKILL.md'), 'w', encoding='utf-8', newline='\n').write(md)
        for f, src in scripts.items():
            open(os.path.join(out, name, 'scripts', f), 'w', encoding='utf-8', newline='\n').write(src)
        made[name] = 0
    # hand-written skills (C2, 2026-11-08): skills_src/<name>/ is copied as is, so a rebuild never loses them
    src_root = os.path.join(HERE, 'skills_src')
    for name in sorted(os.listdir(src_root)) if os.path.isdir(src_root) else []:
        if os.path.isfile(os.path.join(src_root, name, 'SKILL.md')):
            shutil.copytree(os.path.join(src_root, name), os.path.join(out, name),
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            made[name] = 0
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument('--tasks', required=True); ap.add_argument('--out', default=os.path.join(HERE, 'skills'))
    a = ap.parse_args(argv)
    print(json.dumps(build(a.tasks, a.out)))


if __name__ == '__main__':
    sys.exit(main())
