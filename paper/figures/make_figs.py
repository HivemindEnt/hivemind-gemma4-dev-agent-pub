"""Figures for the Gemma 4 developer-agent paper. Every number comes from the per-task run logs
(runs/<arm>/summary.jsonl), recomputed 2026-11-09; see gemma-paper-v2.md."""
import math, pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

OUT = pathlib.Path(__file__).parent
SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8984', '#e4e2dc'
BLUE, ORANGE, AQUA, YELLOW = '#2a78d6', '#eb6834', '#1baf7a', '#eda100'
BAND = '#e9e6de'
for f in fm.findSystemFonts():
    if 'Inter' in f: fm.fontManager.addfont(f)
plt.rcParams.update({'font.family': 'Inter', 'font.size': 11, 'text.color': INK, 'axes.labelcolor': INK2,
                     'xtick.color': INK2, 'ytick.color': INK2, 'axes.edgecolor': GRID, 'figure.facecolor': SURF,
                     'axes.facecolor': SURF, 'savefig.facecolor': SURF})

# dev runs on the same 30 tasks (resolved of 30)
DEV = [('A0 baseline, repeat 1', 5, 'base'), ('A0 baseline, repeat 2', 4, 'base'), ('A0 baseline, repeat 3', 7, 'base'),
       ('A1 thinking off', 4, 'set'), ('A2 4 min cap', 4, 'set'), ('A2 4 min cap, repeat', 4, 'set'),
       ('A3 time-box prompt', 5, 'set'), ('A5 thinking 1536', 7, 'set'), ('A5 thinking 1536, repeat', 4, 'set'),
       ('A6 A5 + A2', 4, 'set'), ('A7 3 min cap', 4, 'set'),
       ('B1 localizer stage', 4, 'struct'), ('B3 pre-submit gate', 6, 'struct'), ('C1 reproduce first', 5, 'struct'),
       ('C2 one-call locator', 5, 'struct')]
COL = {'base': INK2, 'set': BLUE, 'struct': ORANGE}


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def clean(ax):
    for s in ('top', 'right', 'left'): ax.spines[s].set_visible(False)
    ax.tick_params(length=0)


# ---------- Figure 1: every configuration inside the baseline's spread ----------
fig, ax = plt.subplots(figsize=(9, 6.2), dpi=200)
ys = list(range(len(DEV)))[::-1]
ax.axvspan(4, 7, color=BAND, zorder=0, lw=0)
ax.text(5.5, len(DEV) + 0.05, "baseline's own spread (4-7)", ha='center', va='bottom', color=INK2, fontsize=10)
for y, (name, k, kind) in zip(ys, DEV):
    ax.plot([k], [y], 'o', ms=9, color=COL[kind], mec=SURF, mew=2, zorder=3)
ax.set_yticks(ys); ax.set_yticklabels([d[0] for d in DEV])
ax.set_xlim(0, 12); ax.set_xticks(range(0, 13, 2)); ax.set_xlabel('Tasks resolved, of the same 30 dev tasks')
ax.set_ylim(-0.8, len(DEV) + 0.6); ax.grid(axis='x', color=GRID, lw=0.8); ax.set_axisbelow(True); clean(ax)
from matplotlib.lines import Line2D
ax.legend(handles=[Line2D([], [], marker='o', ls='', color=c, ms=8, label=l) for c, l in
                   ((INK2, 'Baseline (A0)'), (BLUE, 'Setting changes'), (ORANGE, 'Structural changes'))],
          loc='lower right', frameon=False)
fig.suptitle('Every configuration landed inside the baseline\'s own run-to-run spread', x=0.02, ha='left', fontsize=14, fontweight='semibold')
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.text(0.02, 0.915, '15 Kaggle runs on one fixed 30-task subset. Smallest paired p-value against any baseline repeat: 0.25 (exact McNemar).',
         fontsize=9.5, color=INK2); fig.savefig(OUT / 'fig1-noise-band.png'); plt.close(fig)

# ---------- Figure 2: where the baseline loses tasks (60 task-runs) ----------
parts = [('Resolved', 9, BLUE), ('Timeout, failing patch', 22, ORANGE), ('Timeout, no patch', 15, YELLOW),
         ('Finished, failing patch', 14, AQUA)]
fig, ax = plt.subplots(figsize=(9, 2.7), dpi=200)
x = 0
for name, n, c in parts:
    ax.barh([0], [n - 0.25], left=[x + 0.125], color=c, height=0.5)
    ax.text(x + n / 2, 0.36, f'{name}\n{n} ({round(100 * n / 60)}%)', ha='center', va='bottom', fontsize=10, color=INK)
    x += n
ax.set_xlim(0, 60); ax.set_ylim(-0.35, 0.95); ax.set_yticks([]); ax.set_xticks([0, 15, 30, 45, 60])
ax.set_xlabel('Task-runs (baseline, two repeats of 30)'); clean(ax)
fig.suptitle('Most failures are timeouts, not wrong answers: 37 of 51 ended at the 6-minute cap', x=0.02, ha='left',
             fontsize=13, fontweight='semibold')
fig.tight_layout(); fig.savefig(OUT / 'fig2-outcomes.png'); plt.close(fig)

# ---------- Figure 3: held-out check with Wilson intervals ----------
HO = [('A0 baseline', 9, INK2), ('A2 4 min cap, run 1', 11, BLUE), ('A2 4 min cap, run 2', 9, BLUE),
      ('A5 thinking 1536', 10, BLUE), ('B2 repo field guides', 11, ORANGE)]
fig, ax = plt.subplots(figsize=(9, 3.8), dpi=200)
for y, (name, k, c) in zip(range(len(HO))[::-1], HO):
    lo, hi = wilson(k, 47)
    ax.plot([lo, hi], [y, y], color=c, lw=2, solid_capstyle='round')
    ax.plot([k / 47], [y], 'o', ms=9, color=c, mec=SURF, mew=2, zorder=3)
    ax.text(hi + 0.01, y, f'{k}/47', va='center', fontsize=10, color=INK2)
ax.set_yticks(range(len(HO))[::-1]); ax.set_yticklabels([h[0] for h in HO])
ax.set_xlim(0, 0.5); ax.set_xticks([0, 0.1, 0.2, 0.3, 0.4, 0.5]); ax.set_xticklabels(['0', '10%', '20%', '30%', '40%', '50%'])
ax.set_xlabel('Resolve rate on 47 held-out tasks, with Wilson 95% interval'); ax.grid(axis='x', color=GRID, lw=0.8)
ax.set_axisbelow(True); clean(ax)
fig.suptitle('Held-out tasks repeat the dev result: no arm separates from the baseline', x=0.02, ha='left',
             fontsize=13, fontweight='semibold')
fig.tight_layout(); fig.savefig(OUT / 'fig3-heldout.png'); plt.close(fig)

# ---------- Card / thumbnail, 560 x 280 exactly (and a 2x copy) ----------
for scale, name in ((1, 'card-560x280.png'), (2, 'card-1120x560-2x.png')):
    fig = plt.figure(figsize=(5.6, 2.8), dpi=100 * scale)
    fig.text(0.05, 0.84, 'Out of Time,', fontsize=19, fontweight='bold', color=INK, va='top')
    fig.text(0.05, 0.66, 'Not Out of Ideas', fontsize=19, fontweight='bold', color=INK, va='top')
    fig.text(0.05, 0.43, 'A 31B open-model coding agent:\nwhere tasks are lost, and what\n30 tasks can and cannot measure',
             fontsize=9, color=INK2, va='top', linespacing=1.35)
    fig.text(0.05, 0.08, 'Gemma 4 Developer Agent · Hivemind', fontsize=7.5, color=MUTED)
    ax = fig.add_axes([0.58, 0.16, 0.38, 0.72])
    ax.axvspan(4, 7, color=BAND, lw=0)
    for i, (n, k, kind) in enumerate(DEV):
        ax.plot([k], [len(DEV) - i], 'o', ms=4.2, color=COL[kind], mec=SURF, mew=0.8)
    ax.set_xlim(0, 10); ax.set_ylim(0, len(DEV) + 2.2); ax.set_yticks([]); ax.set_xticks([0, 5, 10])
    ax.tick_params(labelsize=7, length=0); clean(ax)
    ax.set_xlabel('resolved of 30, 15 runs', fontsize=7, color=INK2, labelpad=2)
    ax.text(5.5, len(DEV) + 1.1, 'noise band', ha='center', fontsize=7, color=INK2)
    fig.savefig(OUT / name, dpi=100 * scale); plt.close(fig)
print('ok')
