"""Find the files most likely to need the fix for an issue, in ONE tool call, so the agent can start editing early.

Measured on our own runs (2026-11-08): resolved tasks made their first edit after a median of 2-6 tool calls, unresolved
ones after 10-13 (A0-r1..r3, A0-h1). Searching eats the budget. This script does the search in one call: it scores every
tracked text file against the issue (BM25 over identifiers, plus boosts for file-path matches, exact code spans and
quoted strings, and for files that DEFINE an identifier the issue names) and prints the top files with the lines that
matched, plus the test file that most likely covers them.

    python locate.py --query "<issue text>" [--root /workspace] [--top 5]
    python locate.py --query-file issue.txt
Standard library only. Output is capped (about 120 lines).
"""
import argparse, math, os, re, subprocess, sys
from collections import Counter

TEXT_EXT = {'.py', '.pyi', '.md', '.rst', '.toml', '.cfg', '.ini', '.yaml', '.yml', '.json', '.txt', '.html', '.js', '.ts', '.css'}
SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'site', 'build', 'dist', '.tox', '.mypy_cache'}
STOP = set('the a an and or of to in on for is it this that with as be by are was were from at not no but if then else when '
           'which what how should would could can will do does did have has had i we you they he she there here use using used '
           'get set new add fix issue bug error file code line return value true false none self def class import pull request '
           'please thanks example expected actual behavior behaviour version python'.split())
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]{2,}')
MAX_BYTES = 400_000


def tokens(text):
    out = []
    for w in IDENT.findall(text):
        lw = w.lower()
        if lw in STOP: continue
        out.append(lw)
        parts = re.findall(r'[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])', w) if not w.islower() else w.split('_')
        if len(parts) > 1: out.extend(p.lower() for p in parts if len(p) > 2 and p.lower() not in STOP)
    return out


def clean_query(q):
    q = re.sub(r'<!--.*?-->', ' ', q, flags=re.S)                       # template comments
    q = re.sub(r'(?m)^\s*[-*]\s*\[[ xX]\].*$', ' ', q)                  # checklists
    q = re.sub(r'(?im)^\s*#+\s*(pull request|checklist|description|privileged).*$', ' ', q)
    return q


def query_terms(q):
    q = clean_query(q)
    spans = [s.strip() for s in re.findall(r'`([^`\n]{3,80})`', q)]
    quoted = [s.strip() for s in re.findall(r'"([^"\n]{6,100})"|\'([^\'\n]{6,100})\'', q) for s in s if s]
    paths = re.findall(r'[\w./-]+\.(?:py|md|toml|ya?ml|json|rst)\b', q)
    idents = [w for w in IDENT.findall(q) if (('_' in w or any(c.isupper() for c in w[1:])) and w.lower() not in STOP)]
    for s in spans: idents += IDENT.findall(s)
    return Counter(tokens(q)), spans + quoted, paths, sorted(set(idents), key=len, reverse=True)[:40]


def list_files(root):
    try:
        r = subprocess.run(['git', '-c', 'safe.directory=*', '-C', root, 'ls-files'], capture_output=True, text=True, timeout=30)
        files = [f for f in r.stdout.splitlines() if f]
    except Exception:
        files = []
    if not files:
        for d, ds, fs in os.walk(root):
            ds[:] = [x for x in ds if x not in SKIP_DIRS]
            files += [os.path.relpath(os.path.join(d, f), root).replace('\\', '/') for f in fs]
    return [f for f in files if os.path.splitext(f)[1].lower() in TEXT_EXT and not any(p in SKIP_DIRS for p in f.split('/'))]


def is_test(path):
    p = path.lower(); b = os.path.basename(p)
    return p.startswith('tests/') or '/tests/' in p or b.startswith('test_') or b.endswith('_test.py') or b == 'conftest.py'


def churn(root, n=3000):
    """How often each file changed in the last n commits (fixes cluster in a few hot files); {} without git."""
    try:
        r = subprocess.run(['git', '-c', 'safe.directory=*', '-C', root, 'log', f'-n{n}', '--name-only', '--format='],
                           capture_output=True, text=True, timeout=30)
        return Counter(l for l in r.stdout.splitlines() if l)
    except Exception:
        return {}


def main_packages(files):
    """Top-level dirs (or src/<dir>) holding an __init__.py: the project's own code."""
    pk = set()
    for f in files:
        parts = f.split('/')
        if parts[-1] == '__init__.py':
            if len(parts) == 2: pk.add(parts[0])
            elif len(parts) == 3 and parts[0] in ('src', 'lib'): pk.add(parts[0] + '/' + parts[1])
    return pk - {'tests', 'test', 'docs', 'docs_src', 'scripts', 'examples', 'benchmarks'}


def area_weight(f, pkgs):
    if f.startswith('.github/') or os.path.basename(f).upper().startswith(('CHANGELOG', 'CONTRIBUTING', 'README', 'LICENSE', 'CODE_OF')):
        return 0.0
    if f.endswith('.py') and any(f.startswith(p + '/') for p in pkgs): return 1.0
    if f.startswith('docs_src/') and f.endswith('.py'): return 0.35
    if f.endswith('.py'): return 0.3
    return 0.12


def rank(root, q, top=5):
    qtf, phrases, qpaths, idents = query_terms(q)
    docs = {}
    for f in list_files(root):
        try:
            with open(os.path.join(root, f), 'rb') as fh: raw = fh.read(MAX_BYTES)
            docs[f] = raw.decode('utf-8', 'replace')
        except OSError:
            continue
    if not docs: return [], []
    pkgs = main_packages(list(docs)); ch = churn(root)
    tf = {f: Counter(tokens(t)) for f, t in docs.items()}
    N = len(docs); avg = sum(sum(c.values()) for c in tf.values()) / N
    df = Counter(w for c in tf.values() for w in c)
    defs = [re.compile(r'^\s*(?:async\s+)?(?:def|class)\s+' + re.escape(i) + r'\b|^' + re.escape(i) + r'\s*=', re.M) for i in idents]
    scores = {}
    for f, c in tf.items():
        n = sum(c.values()) or 1; s = 0.0
        for w, qn in qtf.items():
            if w not in c: continue
            idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
            s += min(qn, 3) * idf * c[w] * 2.2 / (c[w] + 1.2 * (0.25 + 0.75 * n / avg))
        pl = f.lower(); ptoks = set(tokens(f.replace('/', ' ').replace('.', ' ')))
        s += 3.0 * sum(1 for w in qtf if w in ptoks and len(w) > 3)
        s += 12.0 * sum(1 for p in qpaths if pl.endswith(p.lower().lstrip('./')))
        text = docs[f]
        s += 5.0 * sum(1 for ph in phrases if ph and ph in text)
        s += 6.0 * sum(1 for rx in defs if rx.search(text))
        s *= area_weight(f, pkgs)
        s += 0.8 * math.log1p(ch.get(f, 0)) * (1.0 if area_weight(f, pkgs) == 1.0 else 0.0)
        scores[f] = s
    order = sorted(scores, key=scores.get, reverse=True)
    src = [f for f in order if not is_test(f) and scores[f] > 0][:top]
    tests = [f for f in order if is_test(f) and scores[f] > 0][:2]
    return [(f, scores[f]) for f in src], [(f, scores[f]) for f in tests], docs, qtf, phrases, idents


def windows(text, qtf, phrases, idents, k=3, radius=3):
    lines = text.splitlines(); key = set(qtf); hits = []
    for i, line in enumerate(lines):
        lt = set(tokens(line)); s = len(lt & key)
        s += 4 * sum(1 for ph in phrases if ph and ph in line) + 3 * sum(1 for idn in idents if re.search(r'\b(?:def|class)\s+' + re.escape(idn) + r'\b', line))
        if s: hits.append((s, i))
    hits.sort(reverse=True); picked = []
    for s, i in hits:
        if all(abs(i - j) > 2 * radius for j in picked): picked.append(i)
        if len(picked) == k: break
    return [(max(0, i - radius), lines[max(0, i - radius):i + radius + 1]) for i in sorted(picked)]


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument('--query'); ap.add_argument('--query-file')
    ap.add_argument('--root', default='/workspace'); ap.add_argument('--top', type=int, default=5)
    a = ap.parse_args(argv)
    q = a.query or (open(a.query_file, encoding='utf-8').read() if a.query_file else sys.stdin.read())
    res = rank(a.root, q, a.top)
    if not res[0]:
        print('No candidate files found. Search by hand: grep -rn "<identifier>" --include=*.py .'); return 1
    src, tests, docs, qtf, phrases, idents = res
    print('LIKELY FILES TO EDIT (most likely first):')
    for f, s in src: print(f'  {f}   (score {s:.1f})')
    if tests: print('LIKELY TEST FILE TO RUN (do not edit it): ' + tests[0][0])
    budget = 110
    for f, _ in src[:3]:
        for start, block in windows(docs[f], qtf, phrases, idents):
            if budget <= 0: break
            print(f'\n--- {f}:{start + 1}')
            for j, line in enumerate(block): print(f'{start + 1 + j:5d}  {line[:160]}')
            budget -= len(block) + 1
    print('\nNext: open the top file at those lines, make the fix, run the likely test file.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
