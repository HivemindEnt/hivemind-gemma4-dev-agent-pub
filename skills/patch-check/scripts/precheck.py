"""Deterministic pre-submit gate for /workspace (read-only)."""
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
