#!/usr/bin/env python3
"""Small-multiples visualisation of Table 6.11 (execution time by pattern,
dataset size, and system).  Reads the canonical v3 result CSVs and renders a
log-log panel per pattern into thesis/images/execution_times.png.

One panel per pattern; three lines per panel (proposed pandas engine, Trino,
Oracle).  Log-log axes so the near-power-law growth reads as a slope and all
three systems stay legible despite the ~600x spread in absolute time.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results_1core_5w20_unified")
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "thesis", "images",
                                   "execution_times.png"))

# Categorical palette (dataviz-validated: CVD dE 25 >> 12).
SYSTEMS = [
    ("proposed_pandas_engine", "Proposed engine", "#2a78d6", "o"),
    ("oracle",                 "Oracle XE 21c",   "#199e70", "^"),
    ("trino",                  "Trino 473",       "#e3942f", "s"),
]
PATTERNS = ["simple_sequence", "alternation", "quantified",
            "optional_pattern", "complex_nested"]
PRETTY = {p: p for p in PATTERNS}

def load():
    frames = {}
    for key, _, _, _ in SYSTEMS:
        fname = {"proposed_pandas_engine": "pandas_results.csv"}.get(
            key, f"{key}_results.csv")
        df = pd.read_csv(os.path.join(RES, fname))
        frames[key] = df
    return frames

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.edgecolor": "#888888",
    "axes.linewidth": 0.7,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.6,
    "savefig.dpi": 200,
})

frames = load()
fig, axes = plt.subplots(2, 3, figsize=(9.6, 5.8), sharex=True, sharey=True)
axes = axes.ravel()

sizes_fmt = FuncFormatter(lambda v, _:
                          f"{v/1e6:g}M" if v >= 1e6 else f"{int(v/1e3)}K")

for ax, pat in zip(axes, PATTERNS):
    for key, label, color, marker in SYSTEMS:
        d = frames[key]
        d = d[d["pattern_name"] == pat].sort_values("dataset_size")
        sizes = [100000, 200000, 400000, 800000, 1600000, 2222742]
        xpos = [sizes.index(int(v)) for v in d["dataset_size"]]
        ax.plot(xpos, d["execution_time_seconds"],
                color=color, marker=marker, markersize=5, linewidth=2,
                markeredgecolor="white", markeredgewidth=0.6, label=label,
                zorder=3)
    ax.set_title(PRETTY[pat])
    ax.grid(True, which="major", zorder=0)
    ax.set_xticks(range(6))
    ax.set_xticklabels(["100K", "200K", "400K", "800K", "1.6M", "2.2M"],
                       fontsize=7.5)
    ax.set_xlim(-0.35, 5.35)
    ax.set_ylim(bottom=0)
    ax.tick_params(labelsize=7.5)

# Sixth cell: legend only.
leg_ax = axes[5]
leg_ax.axis("off")
handles, labels = axes[0].get_legend_handles_labels()
leg_ax.legend(handles, labels, loc="center", frameon=False,
              fontsize=10, title="System", title_fontsize=10,
              handlelength=2.2, labelspacing=1.1)

# Shared axis labels.
fig.supxlabel("Dataset size (rows)", fontsize=9)
fig.supylabel("Execution time (s)", fontsize=9)
fig.tight_layout(rect=(0.015, 0.0, 1, 1))
fig.savefig(OUT, bbox_inches="tight")
print("wrote", OUT)
