#!/usr/bin/env python3
"""Figures for Section 6.5.6 (ordered vs shuffled input / sorting scenarios).

Reads the ordered (canonical v3) and shuffled (unordered_scenario) result
CSVs and renders:
  * viz_ordering_scenarios.png -- avg time A(ordered) vs B(shuffled) per system.
  * viz_sort_cost_scaling.png  -- engine incremental sort cost per row vs size,
    raw (ns/row, super-linear) and normalised by n*log2(n) (flat -> O(n log n)).
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
ORD = os.path.join(HERE, "cross_system_matrix", "results_1core_5w20_v3")
UNO = os.path.join(HERE, "unordered_scenario")
IMG = os.path.abspath(os.path.join(HERE, "..", "thesis", "images"))

FILES = {"Engine": "pandas_results.csv", "Oracle": "oracle_results.csv",
         "Trino": "trino_results.csv"}
SYS_COLOR = {"Engine": "#2a78d6", "Oracle": "#199e70", "Trino": "#e3942f"}
ORDER = ["Engine", "Oracle", "Trino"]
SIZES = [100000, 200000, 400000, 800000, 1600000, 2222742]
C_ORD, C_SHUF = "#2a78d6", "#e34948"

plt.rcParams.update({
    "font.family": "serif", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": "#888888", "axes.linewidth": 0.7,
    "grid.color": "#dddddd", "grid.linewidth": 0.6, "savefig.dpi": 200,
})
size_fmt = FuncFormatter(lambda v, _: f"{v/1e6:.1f}M" if v >= 1e6 else f"{int(v/1e3)}K")

o = {k: pd.read_csv(os.path.join(ORD, v)) for k, v in FILES.items()}
u = {k: pd.read_csv(os.path.join(UNO, v)) for k, v in FILES.items()}


def ordering_scenarios():
    A = [o[k].execution_time_seconds.mean() for k in ORDER]
    B = [u[k].execution_time_seconds.mean() for k in ORDER]
    x = np.arange(len(ORDER))
    w = 0.36
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    b1 = ax.bar(x - w/2, A, w, color=C_ORD, label="A: ordered input",
                edgecolor="white", linewidth=0.6, zorder=3)
    b2 = ax.bar(x + w/2, B, w, color=C_SHUF, label="B: shuffled input",
                edgecolor="white", linewidth=0.6, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(ORDER, fontsize=9)
    ax.set_ylabel("Average execution time (s)")
    ax.set_ylim(0, max(B) * 1.22)
    ax.grid(True, axis="y", zorder=0)
    ax.set_axisbelow(True)
    for i in range(len(ORDER)):
        ax.annotate(f"{B[i]/A[i]:.2f}$\\times$",
                    (x[i], max(A[i], B[i])), textcoords="offset points",
                    xytext=(0, 4), ha="center", fontsize=8.5, color="#333333")
    for bars in (b1, b2):
        for b in bars:
            ax.annotate(f"{b.get_height():.2f}",
                        (b.get_x() + b.get_width()/2, b.get_height()),
                        textcoords="offset points", xytext=(0, 1.5),
                        ha="center", fontsize=6.8, color="#555555")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax.set_title("Slowdown from forcing a genuine sort (B/A shown above bars)",
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_ordering_scenarios.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_ordering_scenarios.png")


def sort_cost_scaling():
    # Intuitive view: the engine's execution time with ordered input (A, no
    # sort) and with shuffled input (B, must sort), across sizes.  Both grow
    # linearly; the shaded gap between them IS the ordering cost, and it stays a
    # small, roughly constant slice of the total as data scales.
    xlab = ["100K", "200K", "400K", "800K", "1.6M", "2.2M"]
    A = np.array([o["Engine"][o["Engine"].dataset_size == sz]
                  .execution_time_seconds.mean() for sz in SIZES])
    B = np.array([u["Engine"][u["Engine"].dataset_size == sz]
                  .execution_time_seconds.mean() for sz in SIZES])
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    xi = np.arange(len(SIZES))
    ax.fill_between(xi, A, B, color="#e34948", alpha=0.15, zorder=1,
                    label="ordering cost (the gap)")
    ax.plot(xi, A, color="#2a78d6", marker="o", markersize=6, linewidth=2,
            markeredgecolor="white", markeredgewidth=0.7, zorder=3,
            label="A: ordered input (no sort needed)")
    ax.plot(xi, B, color="#e34948", marker="s", markersize=6, linewidth=2,
            markeredgecolor="white", markeredgewidth=0.7, zorder=3,
            label="B: shuffled input (engine must sort)")
    for xv, yv, c in ((xi[-1], A[-1], "#2a78d6"), (xi[-1], B[-1], "#e34948")):
        ax.annotate(f"{yv:.2f}s", (xv, yv), textcoords="offset points",
                    xytext=(6, 2), fontsize=8, color=c)
    ax.set_xticks(xi)
    ax.set_xticklabels(xlab, fontsize=8.5)
    ax.set_xlim(-0.3, len(SIZES) - 0.7)
    ax.set_ylim(0, max(B) * 1.2)
    ax.set_xlabel("Dataset size (rows)")
    ax.set_ylabel("Engine execution time (s)")
    ax.set_title("Cost of sorting: engine on ordered vs shuffled input",
                 fontsize=10)
    ax.grid(True, zorder=0)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_sort_cost_scaling.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_sort_cost_scaling.png")


ordering_scenarios()
sort_cost_scaling()
print("done")
