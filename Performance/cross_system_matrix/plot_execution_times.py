#!/usr/bin/env python3
"""Small-multiples execution-time figure.

The script reads the canonical result CSVs and renders one panel per pattern
into ``thesis/images/execution_times.png``.  Every panel has a linear y-axis
that starts at zero.  The y-axis range is independent for each pattern, and
the figure states this explicitly so cross-panel distances are not compared.
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results_1core_5w20_unified")
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "thesis", "images",
                                   "execution_times.png"))

# Categorical palette (dataviz-validated: CVD dE 25 >> 12).
SYSTEMS = [
    ("proposed_pandas_engine", "Proposed engine", "#2a78d6", "o"),
    ("oracle",                 "Oracle 21c EE",   "#199e70", "^"),
    ("trino",                  "Trino 473",       "#e3942f", "s"),
]
PATTERNS = ["simple_sequence", "alternation", "quantified",
            "optional_pattern", "complex_nested"]
PRETTY = {
    "simple_sequence": "Simple sequence",
    "alternation": "Alternation",
    "quantified": "Quantified",
    "optional_pattern": "Optional pattern",
    "complex_nested": "Complex nested",
}

def load():
    frames = {}
    for key, _, _, _ in SYSTEMS:
        fname = {"proposed_pandas_engine": "pandas_results.csv"}.get(
            key, f"{key}_results.csv")
        df = pd.read_csv(os.path.join(RES, fname))
        frames[key] = df
    return frames

plt.rcParams.update({
    "font.family": "Tinos",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.edgecolor": "#888888",
    "axes.linewidth": 0.7,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.6,
    "savefig.dpi": 300,
})


def main():
    frames = load()
    fig, axes = plt.subplots(
        2, 3, figsize=(9.6, 5.8), sharex=True, sharey=False)
    axes = axes.ravel()
    sizes = [100000, 200000, 400000, 800000, 1600000, 2222742]

    for ax, pat in zip(axes, PATTERNS):
        panel_max = 0.0
        for key, label, color, marker in SYSTEMS:
            d = frames[key]
            d = d[d["pattern_name"] == pat].sort_values("dataset_size")
            xpos = [sizes.index(int(v)) for v in d["dataset_size"]]
            y = d["execution_time_seconds"].to_numpy(dtype=float)
            ax.plot(
                xpos, y, color=color, marker=marker, markersize=5,
                linewidth=2, markeredgecolor="white", markeredgewidth=0.6,
                label=label, zorder=3)
            panel_max = max(panel_max, float(y.max()))
            ax.annotate(
                f"{y[-1]:.2f}", (xpos[-1], y[-1]),
                textcoords="offset points", xytext=(4, 2),
                fontsize=6.6, color=color, zorder=5)
        ax.set_title(PRETTY[pat])
        ax.grid(True, which="major", zorder=0)
        ax.set_xticks(range(6))
        ax.set_xticklabels(
            ["100K", "200K", "400K", "800K", "1.6M", "2.2M"],
            fontsize=7.5)
        ax.set_xlim(-0.35, 5.35)
        ax.tick_params(labelsize=7.5, labelbottom=True, labelleft=True)
        ax.set_ylabel("Execution time (s)", fontsize=8)
        ax.set_xlabel("Dataset size (rows)", fontsize=8)
        ax.set_ylim(0, panel_max * 1.16 if panel_max else 1)

    # Sixth cell: legend only.
    leg_ax = axes[5]
    leg_ax.axis("off")
    handles, labels = axes[0].get_legend_handles_labels()
    leg_ax.legend(
        handles, labels, loc="center", frameon=False,
        fontsize=10, title="System", title_fontsize=10,
        handlelength=2.2, labelspacing=1.1)

    fig.text(
        0.5, 0.01,
        "Each pattern panel uses an independent linear y-axis starting at "
        "zero.",
        ha="center", fontsize=7.5, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(OUT, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
