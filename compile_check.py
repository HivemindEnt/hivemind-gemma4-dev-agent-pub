"""Compile an arm's rendered submission with the competition's own adk_submission compiler (no model server needed),
so structural errors (bad YAML, include paths, unknown fields, templating) surface on pc-2 instead of in a Kaggle run.

  python compile_check.py <ARM>      (run with the gemma .vvenv python, which has adk_submission 0.2.13)
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_deveval as B


def main(name):
    arm = B.load_arm(name)
    d = tempfile.mkdtemp(prefix='arm-%s-' % name)
    for rel, text in B.render_agent_files(arm).items():
        p = os.path.join(d, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8', newline='\n') as f: f.write(text)
    from adk_submission import compiler
    import inspect
    from adk_submission.compiler import compile_submission
    mr_mod = __import__('adk_submission', fromlist=['ModelRegistry'])
    ModelRegistry = getattr(mr_mod, 'ModelRegistry')
    try:
        reg = ModelRegistry()
        reg.register(arm['model'], 'openai/%s' % arm['model']) if hasattr(reg, 'register') else None
    except Exception as e:
        print('model registry setup:', repr(e)); reg = ModelRegistry
    tools = {t: (lambda *a, **k: None) for t in B.ALLOWED_TOOLS}
    for t in tools: tools[t].__name__ = t
    agent = compile_submission(d, tools, reg)
    def walk(a, depth=0):
        print('  ' * depth + '%s (%s) tools=%s output_key=%s' % (a.name, type(a).__name__, [getattr(t, 'name', str(t)) for t in getattr(a, 'tools', [])][:10], getattr(a, 'output_key', None)))
        for s in getattr(a, 'sub_agents', []) or []: walk(s, depth + 1)
    walk(agent)
    print('COMPILED OK', d)


if __name__ == '__main__':
    main(sys.argv[1])
