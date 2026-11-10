"""Derive a field guide for the repository in /workspace (read-only). Prints Markdown in the known-guide format."""
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
