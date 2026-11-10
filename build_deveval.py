"""Build a Kaggle dev-eval notebook for one agent arm (Gemma 4 Developer Agent, ).

Why: the competition scores a YAML-only ADK agent on ~120 hidden tasks, and community reports show the same submission
scoring 0.12 to 0.22 across runs. Ranking configurations therefore needs repeated local measurements on a fixed task
subset, run on the same hardware the scorer uses (4x L4, vLLM 0.19, swegemma 0.2.11). This builder turns an arm
definition (arms/<name>/arm.json + system.md) into a self-contained Kaggle notebook plus kernel-metadata.json, adapted
from the host's "Getting Started - Gemma 4 Developer Agent" notebook (ryanholbrook), so each run is reproducible from
tracked files.

Usage:
  python build_deveval.py build --arm A0 --tag r1 --tasks tasks.jsonl --subset 30 --concurrency 4 --out out/A0-r1
  python build_deveval.py split --tasks tasks.jsonl          # print the dev / held-out split sizes per repo
Push the output dir with `kaggle kernels push -p out/A0-r1`.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
KAGGLE_USER = 'hivemindadmin'
COMPETITION = 'gemma-4-developer-agent'
WHEELHOUSE = 'metric/gemma-4-developer-agent-wheelhouse'
ALLOWED_MODELS = ('gemma-4-31b-it-qat-w4a16-ct', 'gemma-4-12b-it-qat-w4a16-ct',
                  'gemma-4-e4b-it-qat-w4a16-ct', 'gemma-4-e2b-it-qat-w4a16-ct')
# The host notebook's docker image; pinning it keeps the CUDA/driver stack identical across runs.
DOCKER_IMAGE = 'gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461'
ALLOWED_TOOLS = ('run_command', 'read_file', 'edit_file', 'write_file', 'get_status', 'submit_patch',
                 'get_code_neighbors', 'search_similar_code', 'get_code_subgraph')
HELDOUT_MOD = 3  # 1 in 3 public tasks is held out by name (never used for tuning)


def bucket(instance_id):
    """Stable 0..999 bucket from the task name (sha1), so the split never depends on file order."""
    return int(hashlib.sha1(instance_id.encode('utf-8')).hexdigest()[:8], 16) % 1000


def order_key(instance_id):
    """Total order: bucket, then name (buckets collide, and a tie must not depend on input order)."""
    return (bucket(instance_id), instance_id)


def split(ids):
    """Return (dev, heldout) id lists. Held out = bucket % HELDOUT_MOD == 0."""
    dev = sorted((i for i in ids if bucket(i) % HELDOUT_MOD != 0), key=order_key)
    held = sorted((i for i in ids if bucket(i) % HELDOUT_MOD == 0), key=order_key)
    return dev, held


def repo_of(instance_id):
    return instance_id.rsplit('_', 1)[0]


def subset(dev_ids, n):
    """Deterministic, repo-proportional subset of n dev tasks (largest-remainder allocation, bucket order inside)."""
    by_repo = defaultdict(list)
    for i in dev_ids:
        by_repo[repo_of(i)].append(i)
    total = len(dev_ids)
    n = min(n, total)
    quotas = {r: n * len(v) / total for r, v in by_repo.items()}
    alloc = {r: int(q) for r, q in quotas.items()}
    for r in sorted(quotas, key=lambda r: (-(quotas[r] - alloc[r]), r))[: n - sum(alloc.values())]:
        alloc[r] += 1
    out = []
    for r in sorted(by_repo):
        out += sorted(by_repo[r], key=order_key)[: alloc[r]]
    return sorted(out, key=order_key)


def load_ids(tasks_path):
    with open(tasks_path, encoding='utf-8') as f:
        return [json.loads(line)['instance_id'] for line in f if line.strip()]


def load_arm(name, arms_dir=None):
    d = os.path.join(arms_dir or os.path.join(HERE, 'arms'), name)
    with open(os.path.join(d, 'arm.json'), encoding='utf-8') as f:
        arm = json.load(f)
    if arm.get('pipeline'):   # multi-agent arm: one prompt file per stage, <stage name>.md in the arm dir
        for st in arm['pipeline']:
            with open(os.path.join(d, st['name'] + '.md'), encoding='utf-8') as f:
                st['prompt'] = f.read()
        arm['system_prompt'] = arm['pipeline'][-1]['prompt']
    else:
        with open(os.path.join(d, 'system.md'), encoding='utf-8') as f:
            arm['system_prompt'] = f.read()
    validate_arm(arm)
    return arm


def validate_arm(arm):
    if arm.get('model') not in ALLOWED_MODELS:
        raise ValueError('model must be one of %s' % (ALLOWED_MODELS,))
    bad = [t for t in arm.get('tools', []) if t not in ALLOWED_TOOLS]
    if bad:
        raise ValueError('unknown tools: %s' % bad)
    ev = arm.get('evaluation', {})
    for k in ('max_tool_calls', 'max_time_minutes', 'max_turns', 'timeout_seconds'):
        if k not in ev:
            raise ValueError('evaluation.%s is required (the sample defaults cripple the agent)' % k)
    if not arm.get('system_prompt', '').strip():
        raise ValueError('empty system prompt')
    for name in arm.get('skills', []):
        if not os.path.isfile(os.path.join(HERE, 'skills', name, 'SKILL.md')):
            raise ValueError('skill %s has no skills/%s/SKILL.md (run build_guides.py)' % (name, name))
    for st in arm.get('pipeline', []):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,30}', st.get('name', '')):
            raise ValueError('pipeline stage names: lowercase identifiers')
        bad = [t for t in st.get('tools', []) if t not in ALLOWED_TOOLS]
        if bad:
            raise ValueError('unknown tools in stage %s: %s' % (st['name'], bad))
        if not st.get('prompt', '').strip():
            raise ValueError('empty prompt for stage %s' % st['name'])


def _yaml_scalar(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    return str(v)


def _sampling_lines(s, indent=''):
    lines = ['temperature: %s' % s['temperature'], 'top_p: %s' % s['top_p'], 'max_output_tokens: %s' % s['max_output_tokens']]
    tc = s.get('thinking_config')
    if tc:
        lines.append('thinking_config:')
        lines += ['  %s: %s' % (k, _yaml_scalar(v)) for k, v in tc.items()]
    return [indent + l for l in lines]


def render_pipeline_files(arm):
    """Multi-agent arm (2026-11-08 explore phase): a SequentialAgent root whose stages are LlmAgents in sub_agents/.
    adk_submission resolves !include relative to the INCLUDING file and blocks '..', so each stage's prompt sits next to
    its YAML in sub_agents/, and sampling is inlined. A stage with output_key publishes its final text to session state,
    which later stages read through {output_key} templating in their prompts."""
    root = ['agent_class: SequentialAgent', 'name: %s' % ('hm_' + arm['name'].lower()),
            'description: %s' % json.dumps(arm.get('description', '')[:900]), 'sub_agents:']
    files = {}
    for st in arm['pipeline']:
        root.append('  - config_path: sub_agents/%s.yaml' % st['name'])
        y = ['name: %s' % st['name'], 'model: %s' % arm['model'],
             'description: %s' % json.dumps(st.get('description', st['name'])),
             'instruction: !include %s.md' % st['name'], 'tools:'] + ['  - %s' % t for t in st['tools']]
        if st.get('output_key'):
            y.append('output_key: %s' % st['output_key'])
        y.append('disallow_transfer_to_parent: true')
        y.append('disallow_transfer_to_peers: true')
        y.append('generate_content_config:')
        y += _sampling_lines(st.get('sampling', arm['sampling']), '  ')
        files['sub_agents/%s.yaml' % st['name']] = '\n'.join(y) + '\n'
        files['sub_agents/%s.md' % st['name']] = st['prompt']
    ev = arm['evaluation']
    files['agent.yaml'] = '\n'.join(root) + '\n'
    files['eval_config.yaml'] = '\n'.join(['evaluation:'] + ['  %s: %s' % (k, ev[k]) for k in ('timeout_seconds', 'max_tool_calls', 'max_time_minutes', 'max_turns')]) + '\n'
    return files


def render_agent_files(arm):
    """Files of the submission directory for this arm (agent.yaml, prompts, configs, eval_config.yaml)."""
    if arm.get('pipeline'):
        return render_pipeline_files(arm)
    s = arm['sampling']
    lines = ['temperature: %s' % s['temperature'], 'top_p: %s' % s['top_p'],
             'max_output_tokens: %s' % s['max_output_tokens']]
    tc = s.get('thinking_config')
    if tc:
        lines.append('thinking_config:')
        lines += ['  %s: %s' % (k, _yaml_scalar(v)) for k, v in tc.items()]
    agent = ['name: %s' % ('hm_' + arm['name'].lower()), 'model: %s' % arm['model'],
             'instruction: !include prompts/system.md', 'tools:'] + ['  - %s' % t for t in arm['tools']]
    agent.append('generate_content_config: !include configs/sampling.yaml')
    skill_files = {}
    if arm.get('skills'):   # B2/B3 (2026-11-08): ADK skills from skills/<name>/ (built by build_guides.py)
        agent.append('skills:')
        for name in arm['skills']:
            agent.append('  - skills/%s' % name)
            sd = os.path.join(HERE, 'skills', name)
            for dp, _, fs in os.walk(sd):
                for f in fs:
                    if f.endswith(('.md', '.py', '.txt')):
                        rel = os.path.relpath(os.path.join(dp, f), os.path.join(HERE, 'skills')).replace(os.sep, '/')
                        with open(os.path.join(dp, f), encoding='utf-8') as fh:
                            skill_files['skills/' + rel] = fh.read()
    ev = arm['evaluation']
    evl = ['evaluation:'] + ['  %s: %s' % (k, ev[k]) for k in ('timeout_seconds', 'max_tool_calls', 'max_time_minutes', 'max_turns')]
    return {
        **skill_files,
        'agent.yaml': '\n'.join(agent) + '\n',
        'prompts/system.md': arm['system_prompt'],
        'configs/sampling.yaml': '\n'.join(lines) + '\n',
        'eval_config.yaml': '\n'.join(evl) + '\n',
    }


def _code(src):
    return {'cell_type': 'code', 'execution_count': None, 'metadata': {}, 'outputs': [], 'source': src}


def _md(src):
    return {'cell_type': 'markdown', 'metadata': {}, 'source': src}


INSTALL_CELL = r'''import glob, importlib, json, logging, os, re, shutil, subprocess, sys, time
from pathlib import Path
for k, v in {'TRANSFORMERS_NO_TF': '1', 'TRANSFORMERS_NO_FLAX': '1', 'TRANSFORMERS_OFFLINE': '1',
             'VLLM_NO_USAGE_STATS': '1', 'VLLM_WORKER_MULTIPROC_METHOD': 'spawn', 'VLLM_ENGINE_READY_TIMEOUT_S': '1200',
             'VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS': '1', 'NCCL_DEBUG': 'WARN', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
             'LITELLM_TELEMETRY': 'False', 'LITELLM_LOG': 'WARNING', 'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True',
             'OTEL_SDK_DISABLED': 'true', 'OTEL_PYTHON_DISABLED': 'true'}.items():
    os.environ[k] = v
os.environ.setdefault('OPENAI_API_KEY', 'EMPTY'); os.environ.setdefault('LOCAL_API_KEY', 'EMPTY')
for name in ('LiteLLM', 'LiteLLM Router', 'LiteLLM Proxy', 'litellm', 'httpx', 'httpcore', 'openai', 'urllib3', 'opentelemetry'):
    lg = logging.getLogger(name); lg.setLevel(logging.WARNING)
    if 'litellm' in name.lower():
        lg.propagate = False; lg.handlers.clear()
T0 = time.time()
_WH = [Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse'),
       Path('/kaggle/input/gemma-4-developer-agent-wheelhouse')]
_WH += sorted(Path(p).parent for p in glob.glob('/kaggle/input/**/*.whl', recursive=True) if 'wheelhouse' in p)
WHEELHOUSE_DIR = next((p for p in _WH if p.is_dir() and any(p.glob('*.whl'))), None)
if WHEELHOUSE_DIR is None:
    raise RuntimeError('wheelhouse not mounted; /kaggle/input has: %s' % sorted(glob.glob('/kaggle/input/*/*'))[:40])
print('wheelhouse:', WHEELHOUSE_DIR)
for pat in ('/usr/local/lib/python*/dist-packages/*cutlass*.pth', '/usr/local/lib/python*/site-packages/*cutlass*.pth'):
    for pth in glob.glob(pat):
        try: os.unlink(pth)
        except OSError: pass
tmp_whl = Path('/tmp/wheelhouse'); tmp_whl.mkdir(parents=True, exist_ok=True)
for w in WHEELHOUSE_DIR.glob('*.whl'):
    if 'cutlass' in w.name.lower(): continue
    t = tmp_whl / (w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name)
    if not t.exists():
        try: os.symlink(w, t)
        except OSError: shutil.copyfile(w, t)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *sorted(str(w) for w in tmp_whl.glob('*.whl'))], check=True)
importlib.invalidate_caches()
print('install done in %.0f s' % (time.time() - T0))
'''

SERVER_CELL = r'''import litellm, torch
from adk_submission import VllmConfig, VllmServer, discover_adapters
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS
litellm.drop_params = True
_MP = [Path('/kaggle/input/models/google/gemma-4/other/%s/2' % RUN['model']),
       Path('/kaggle/input/gemma-4/other/%s/2' % RUN['model'])]
_MP += [Path(p) for p in sorted(glob.glob('/kaggle/input/**/%s/2' % RUN['model'], recursive=True))]
MODEL_PATH = next((p for p in _MP if p.is_dir()), _MP[0])
assert MODEL_PATH.exists(), MODEL_PATH
adapters = discover_adapters(str(AGENT_DIR), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 1
tp_size = 4 if gpu_count >= 4 else (2 if gpu_count >= 2 else 1)
extra = ('--hf-overrides', '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}') if RUN['model'].startswith('gemma-4-12b') else ()
T1 = time.time()
server_instance = VllmServer(VllmConfig(
    model=str(MODEL_PATH), port=8000, host='127.0.0.1', tool_call_parser='gemma4', reasoning_parser='gemma4',
    max_model_len=32768, dtype='bfloat16' if torch.cuda.is_bf16_supported() else 'auto', gpu_memory_utilization=0.90,
    enable_auto_tool_choice=True, enable_lora=bool(getattr(adapters, 'adapters', None)), max_loras=1, max_lora_rank=128,
    scheduler_reserve_full_isl=False, tensor_parallel_size=tp_size, startup_timeout=60 * 20, extra_args=extra,
), adapter_manifest=adapters)
server_instance.start()
models = server_instance.create_model_registry(aliases=[RUN['model']], model_prefix='openai/', api_key=os.environ['LOCAL_API_KEY'])
SERVER_START_S = time.time() - T1
print('vLLM up in %.0f s (tp=%d, gpus=%d)' % (SERVER_START_S, tp_size, gpu_count))
'''

EVAL_CELL = r'''import asyncio, concurrent.futures, yaml
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
from swegemma.config import EvalConfig, build_submission_limits
from swegemma.evaluate import Evaluator
DATA_DIR = next((p for p in (Path('/kaggle/input/competitions/gemma-4-developer-agent'),
                             Path('/kaggle/input/gemma-4-developer-agent')) if (p / 'tasks.jsonl').exists()), None)
if DATA_DIR is None:
    raise RuntimeError('competition data not mounted; /kaggle/input has: %s' % sorted(glob.glob('/kaggle/input/*/*'))[:40])
print('competition data:', DATA_DIR)
ev = yaml.safe_load((AGENT_DIR / 'eval_config.yaml').read_text())['evaluation']
limits, gen_constraints = build_submission_limits()
RESULTS = Path('/kaggle/working/results')
cfg = EvalConfig(
    tasks_path=DATA_DIR / 'tasks.jsonl', snapshots_dir=DATA_DIR / 'snapshots', results_dir=RESULTS,
    submission_dir=AGENT_DIR, models=models, sandbox='subprocess',
    timeout_seconds=int(ev['timeout_seconds']), verification_timeout_seconds=300,
    max_time_minutes=float(ev['max_time_minutes']), max_tool_calls=int(ev['max_tool_calls']), max_turns=int(ev['max_turns']),
    limits=limits, generation_constraints=gen_constraints, adapter_manifest=adapters,
    context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
    events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=14336, event_retention_size=5),
    graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'), wheels_dir=DATA_DIR / 'wheels',
    task_ids=RUN['task_ids'], concurrency=RUN['concurrency'], display_mode='quiet', verbose=False,
)
T2 = time.time()
def _run():
    return asyncio.run(Evaluator(cfg).run())
try:
    asyncio.get_running_loop(); in_loop = True
except RuntimeError:
    in_loop = False
if in_loop:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        res = pool.submit(_run).result()
else:
    res = _run()
EVAL_S = time.time() - T2
rows = []
for r in res.task_results:
    g = lambda k, default=None: getattr(r, k, default)
    rows.append({'instance_id': g('instance_id') or g('task_id'), 'resolved': bool(g('resolved')),
                 'patch_chars': len(g('agent_patch') or ''), 'tool_calls': g('tool_calls'),
                 'duration_seconds': g('duration_seconds'), 'test_exit_code': g('test_exit_code'),
                 'error': str(g('error_message') or '')[:300]})
with open('/kaggle/working/summary.jsonl', 'w') as f:
    for row in rows: f.write(json.dumps(row) + '\n')
n = len(rows); k = sum(r['resolved'] for r in rows)
summary = {'arm': RUN['arm'], 'tag': RUN['tag'], 'model': RUN['model'], 'n': n, 'resolved': k,
           'rate': (k / n) if n else None, 'no_patch': sum(1 for r in rows if r['patch_chars'] == 0),
           'eval_seconds': round(EVAL_S), 'server_start_seconds': round(SERVER_START_S),
           'install_to_end_seconds': round(time.time() - T0), 'concurrency': RUN['concurrency'],
           'task_seconds_mean': (sum((r['duration_seconds'] or 0) for r in rows) / n) if n else None}
Path('/kaggle/working/summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
server_instance.stop()
'''


def build_notebook(arm, task_ids, concurrency, tag):
    files = render_agent_files(arm)
    run = {'arm': arm['name'], 'tag': tag, 'model': arm['model'], 'task_ids': list(task_ids), 'concurrency': int(concurrency)}
    write_cell = ('RUN = json.loads(%r)\n' % json.dumps(run) +
                  'AGENT_DIR = Path("/kaggle/working/agent")\nshutil.rmtree(AGENT_DIR, ignore_errors=True)\n'
                  'FILES = json.loads(%r)\n' % json.dumps(files) +
                  'for rel, text in FILES.items():\n    p = AGENT_DIR / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")\n'
                  'print("arm", RUN["arm"], "tag", RUN["tag"], "tasks", len(RUN["task_ids"]), "concurrency", RUN["concurrency"])\n')
    cells = [
        _md('# Hivemind dev-eval: arm %s, run %s\n\nFLEETINFRA-1380. Built by competitions/gemma-dev-agent/build_deveval.py '
            'from arms/%s. Adapted from the host notebook "Getting Started - Gemma 4 Developer Agent".\n' % (arm['name'], tag, arm['name'])),
        _code(INSTALL_CELL), _code(write_cell), _code(SERVER_CELL), _code(EVAL_CELL),
    ]
    return {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                                         'language_info': {'name': 'python'}}, 'nbformat': 4, 'nbformat_minor': 5}


def kernel_slug(arm_name, tag):
    s = ('hm-gemma-deveval-%s-%s' % (arm_name, tag)).lower()
    return ''.join(c if c.isalnum() or c == '-' else '-' for c in s)[:50]


def kernel_metadata(arm, tag):
    slug = kernel_slug(arm['name'], tag)
    return {'id': '%s/%s' % (KAGGLE_USER, slug), 'title': slug, 'code_file': 'notebook.ipynb', 'language': 'python',
            'kernel_type': 'notebook', 'is_private': True, 'enable_gpu': True, 'enable_tpu': False, 'enable_internet': False,
            'dataset_sources': [WHEELHOUSE], 'competition_sources': [COMPETITION], 'kernel_sources': [],
            'model_sources': ['google/gemma-4/Other/%s/2' % arm['model']], 'docker_image': DOCKER_IMAGE,
            'machine_shape': 'NvidiaL4'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('--arm', required=True); b.add_argument('--tag', required=True)
    b.add_argument('--tasks', required=True); b.add_argument('--subset', type=int, default=30)
    b.add_argument('--concurrency', type=int, default=4); b.add_argument('--out', required=True)
    b.add_argument('--heldout', action='store_true', help='evaluate the held-out tasks instead of the dev subset')
    s = sub.add_parser('split'); s.add_argument('--tasks', required=True)
    a = ap.parse_args(argv)
    ids = load_ids(a.tasks)
    dev, held = split(ids)
    if a.cmd == 'split':
        for name, group in (('dev', dev), ('heldout', held)):
            c = defaultdict(int)
            for i in group: c[repo_of(i)] += 1
            print(name, len(group), dict(sorted(c.items())))
        return 0
    arm = load_arm(a.arm)
    task_ids = held if a.heldout else subset(dev, a.subset)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'notebook.ipynb'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(build_notebook(arm, task_ids, a.concurrency, a.tag), f, indent=1)
    with open(os.path.join(a.out, 'kernel-metadata.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(kernel_metadata(arm, a.tag), f, indent=2)
    print('built %s: arm %s, %d tasks, concurrency %d -> %s' % (kernel_slug(a.arm, a.tag), a.arm, len(task_ids), a.concurrency, a.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
