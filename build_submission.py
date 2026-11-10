#!/usr/bin/env python3
"""Gemma 4 Developer Agent: build the competition submission.zip for one arm.

    python build_submission.py --arm A2 --out <dir> [--validate]

Writes <dir>/submission/ (the rendered agent directory, same renderer as the dev-eval notebooks, so what was measured is
what is submitted) and <dir>/submission.zip with the files at the zip root, plus <dir>/manifest.json (arm, sha256 of
every file and of the zip). --validate runs the host's own validator (adk_submission.validate_directory with
swegemma's submission limits) and fails the build if it rejects the directory; it needs those wheels installed.
"""
import argparse, hashlib, json, os, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_deveval as B

MAX_BYTES = 3 * 1024 ** 3   # swegemma: total unpacked submission < 3 GiB


def write_dir(arm, root):
    files = B.render_agent_files(arm)
    for rel, text in files.items():
        p = os.path.join(root, *rel.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    return sorted(files)


def zip_dir(root, rels, zpath):
    # fixed timestamps and order: the same arm gives a byte-identical zip
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in rels:
            info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(os.path.join(root, *rel.split('/')), 'rb') as f:
                z.writestr(info, f.read())


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def structural_checks(root, rels):
    """The rules we can check without the host's wheels: one root config, an allowed model, size, no traversal."""
    roots = [r for r in rels if r in ('agent.yaml', 'agent.yml', 'root_agent.yaml', 'root_agent.yml')]
    if len(roots) != 1: raise ValueError('exactly one root config is required, found %r' % roots)
    allowed = {'gemma-4-31b-it-qat-w4a16-ct', 'gemma-4-12b-it-qat-w4a16-ct', 'gemma-4-e4b-it-qat-w4a16-ct', 'gemma-4-e2b-it-qat-w4a16-ct'}
    models = set()
    for r in rels:
        if r.endswith(('.yaml', '.yml')):
            for line in open(os.path.join(root, *r.split('/')), encoding='utf-8'):
                if line.startswith('model:'): models.add(line.split(':', 1)[1].strip())
    if len(models) != 1 or not models <= allowed: raise ValueError('one allowed base model required, found %r' % sorted(models))
    if any(r.startswith('/') or '..' in r.split('/') for r in rels): raise ValueError('path traversal in submission')
    size = sum(os.path.getsize(os.path.join(root, *r.split('/'))) for r in rels)
    if size >= MAX_BYTES: raise ValueError('submission is %d bytes, limit < 3 GiB' % size)
    return sorted(models)[0], size


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--arm', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--validate', action='store_true')
    a = ap.parse_args(argv)
    arm = B.load_arm(a.arm); B.validate_arm(arm)
    root = os.path.join(a.out, 'submission'); os.makedirs(root, exist_ok=True)
    rels = write_dir(arm, root)
    model, size = structural_checks(root, rels)
    validated = False
    if a.validate:
        from adk_submission import validate_directory
        from swegemma.config import build_submission_limits
        limits, _ = build_submission_limits()
        validate_directory(root, limits=limits)
        validated = True
    zpath = os.path.join(a.out, 'submission.zip'); zip_dir(root, rels, zpath)
    man = {'arm': arm['name'], 'model': model, 'bytes': size, 'files': {r: sha(os.path.join(root, *r.split('/'))) for r in rels},
           'zip_sha256': sha(zpath), 'host_validator': validated, 'evaluation': arm['evaluation']}
    with open(os.path.join(a.out, 'manifest.json'), 'w', encoding='utf-8') as f: json.dump(man, f, indent=2)
    print(json.dumps(man, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
