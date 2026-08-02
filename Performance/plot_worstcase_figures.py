#!/usr/bin/env python3
"""Regenerate the two worst-case figures from their saved CSVs, with the
thesis-wide palette (engine #2a78d6, Oracle #199e70, Trino #e3942f,
worst case #e34948), linear axes, and every dataset size labeled.

  - viz_worstcase_xsys.png     from Performance/worstcase_xsys/*_results.csv
  - viz_worstcase_coverage.png from Performance/worstcase_coverage.csv
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.abspath(os.path.join(HERE, "..", "thesis", "images"))

plt.rcParams.update({
    "font.family": "Tinos", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": "#888888", "axes.linewidth": 0.7,
    "grid.color": "#dddddd", "grid.linewidth": 0.6,
    "savefig.dpi": 300,
})

SYSTEMS = [
    ("pandas", "Proposed engine"      , "#2a78d6", "o"),
    ("trino",  "Trino 473",              "#e3942f", "s"),
    ("oracle", "Oracle 21c EE",          "#199e70", "^"),
]


def size_label(n):
    if n >= 1e6:
        value = f"{n / 1e6:.2f}".rstrip("0").rstrip(".")
        return f"{value}M"
    return f"{int(n / 1e3)}K"


# ---- cross-system state-dependent worst case --------------------------------
def worstcase_xsys():
    frames = {k: pd.read_csv(os.path.join(HERE, "worstcase_xsys",
                                          f"{k}_results.csv"))
              for k, *_ in SYSTEMS}
    sizes = sorted(frames["pandas"]["dataset_size"].unique())
    labels = [size_label(s) for s in sizes]
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for key, label, color, marker in SYSTEMS:
        d = frames[key].sort_values("dataset_size")
        ax.plot(range(len(sizes)), d["execution_time_seconds"], color=color,
                marker=marker, markersize=6, linewidth=2,
                markeredgecolor="white", markeredgewidth=0.7,
                label=label, zorder=3)
        # Label only the final point.  Labelling all three series at every
        # size caused the engine and Oracle values to overlap at small sizes.
        yv = float(d["execution_time_seconds"].iloc[-1])
        end_offset = {
            "pandas": (5, -7),
            "oracle": (5, 2),
            "trino": (5, 2),
        }[key]
        ax.annotate(f"{yv:.2f}", (len(sizes) - 1, yv),
                    textcoords="offset points", xytext=end_offset,
                    ha="left", fontsize=7.2, color=color, zorder=5)
    ax.set_xticks(range(len(sizes)))
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_xlim(-0.35, len(sizes) - 0.2)
    ax.set_ylim(bottom=0)
    ax.grid(True, zorder=0)
    ax.set_xlabel("Dataset size (rows)")
    ax.set_ylabel("Mean execution time (s)")
    ax.set_title("State-dependent DEFINE: cross-system execution time")
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_worstcase_xsys.png"),
                bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_worstcase_xsys.png")


# ---- engine-only fast path vs state-dependent path --------------------------
def worstcase_coverage():
    # This figure is not used by the thesis: the state-dependent worst case is
    # reported across all three systems by worstcase_xsys() above, and the
    # engine-only view duplicated it.  Its input is no longer maintained, so
    # skip rather than fail the whole regeneration run.
    src = os.path.join(HERE, "worstcase_coverage.csv")
    if not os.path.exists(src):
        print("skipped viz_worstcase_coverage.png (worstcase_coverage.csv not "
              "maintained; the figure is unused by the thesis)")
        return
    res = pd.read_csv(src)
    sizes = res["size"].tolist()
    labels = [size_label(s) for s in sizes]
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.plot(range(len(sizes)), res["rowlocal_s"], color="#2a78d6", marker="o",
            markersize=6, linewidth=2, markeredgecolor="white",
            markeredgewidth=0.7, label="Row-local DEFINE predicates",
            zorder=3)
    ax.plot(range(len(sizes)), res["statedep_s"], color="#e34948", marker="s",
            markersize=6, linewidth=2, markeredgecolor="white",
            markeredgewidth=0.7,
            label="State-dependent DEFINE predicates", zorder=3)
    for i, y in enumerate(res["statedep_s"]):
        ax.annotate(f"{y:.2f}s", (i, y), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=7.5, color="#e34948")
    ax.set_xticks(range(len(sizes)))
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_xlim(-0.35, len(sizes) - 0.65)
    ax.set_ylim(bottom=0)
    ax.grid(True, zorder=0)
    ax.set_xlabel("Dataset size (rows)")
    ax.set_ylabel("Mean execution time (s)")
    ax.set_title("Proposed engine: row-local vs. state-dependent DEFINE")
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_worstcase_coverage.png"),
                bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_worstcase_coverage.png")


if __name__ == "__main__":
    worstcase_xsys()
    worstcase_coverage()
