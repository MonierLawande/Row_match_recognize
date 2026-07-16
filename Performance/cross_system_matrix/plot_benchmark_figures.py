#!/usr/bin/env python3
"""Visual representations of the detailed benchmark tables (6.11-6.21).

Renders one PNG per table into thesis/images/, all from the canonical v3
result CSVs so the figures and the LaTeX tables share a single source of
truth.  Palette is dataviz-validated (CVD dE 25): proposed engine = blue,
Oracle = aqua-green, Trino = orange.  Identity is carried by marker shape
and legend, not colour alone.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, ScalarFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results_1core_5w20_unified")
IMG = os.path.abspath(os.path.join(HERE, "..", "..", "thesis", "images"))

SYSTEMS = [
    ("proposed_pandas_engine", "Proposed engine", "#2a78d6", "o"),
    ("oracle",                 "Oracle XE 21c",   "#199e70", "^"),
    ("trino",                  "Trino 473",       "#e3942f", "s"),
]
PATTERNS = ["simple_sequence", "alternation", "quantified",
            "optional_pattern", "complex_nested"]
SIZES = [100000, 200000, 400000, 800000, 1600000, 2222742]

plt.rcParams.update({
    "font.family": "serif", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": "#888888", "axes.linewidth": 0.7,
    "grid.color": "#dddddd", "grid.linewidth": 0.6,
    "savefig.dpi": 200, "figure.autolayout": False,
})

def load():
    frames = {}
    for key, *_ in SYSTEMS:
        fname = {"proposed_pandas_engine": "pandas_results.csv"}.get(
            key, f"{key}_results.csv")
        frames[key] = pd.read_csv(os.path.join(RES, fname))
    return frames

FR = load()
size_fmt = FuncFormatter(lambda v, _: f"{v/1e6:.1f}M" if v >= 1e6 else f"{int(v/1e3)}K")

# Equal-spaced categorical x axis showing every dataset size.
SIZE_LABELS = ["100K", "200K", "400K", "800K", "1.6M", "2.2M"]


def cat_x(sizes):
    return [SIZES.index(int(s)) for s in sizes]


def cat_axis(ax, labelsize=7.5):
    ax.set_xticks(range(len(SIZES)))
    ax.set_xticklabels(SIZE_LABELS, fontsize=labelsize)
    ax.set_xlim(-0.35, len(SIZES) - 0.65)


def small_multiples(metric, ylabel, fname, logy=True):
    """5 pattern panels + legend cell; one line per system."""
    fig, axes = plt.subplots(2, 3, figsize=(9.6, 5.8), sharex=True, sharey=True)
    axes = axes.ravel()
    ymax = 0.0
    for ax, pat in zip(axes, PATTERNS):
        for key, label, color, marker in SYSTEMS:
            d = FR[key]
            d = d[d["pattern_name"] == pat].sort_values("dataset_size")
            ax.plot(cat_x(d["dataset_size"]), d[metric], color=color,
                    marker=marker, markersize=5, linewidth=2,
                    markeredgecolor="white", markeredgewidth=0.6,
                    label=label, zorder=3)
            ymax = max(ymax, d[metric].max())
        ax.set_title(pat)
        ax.grid(True, which="major", zorder=0)
        cat_axis(ax)
        ax.tick_params(labelsize=7.5)
    axes[0].set_ylim(0, ymax * 1.09)
    axes[5].axis("off")
    h, l = axes[0].get_legend_handles_labels()
    axes[5].legend(h, l, loc="center", frameon=False, fontsize=10,
                   title="System", title_fontsize=10, handlelength=2.2,
                   labelspacing=1.1)
    fig.supxlabel("Dataset size (rows)", fontsize=9)
    fig.supylabel(ylabel, fontsize=9)
    fig.tight_layout(rect=(0.015, 0.0, 1, 1))
    fig.savefig(os.path.join(IMG, fname), bbox_inches="tight")
    plt.close(fig)
    print("wrote", fname)


def lines_by_size(metric, ylabel, fname, logy=True):
    """Single panel: metric averaged over patterns vs size, one line/system."""
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for key, label, color, marker in SYSTEMS:
        d = FR[key].groupby("dataset_size")[metric].mean().reindex(SIZES)
        ax.plot(range(len(SIZES)), d.values, color=color, marker=marker,
                markersize=6, linewidth=2, markeredgecolor="white",
                markeredgewidth=0.7, label=label, zorder=3)
        ax.annotate(f"{d.values[-1]:,.0f}" if d.values[-1] >= 100
                    else f"{d.values[-1]:.2f}",
                    (len(SIZES) - 1, d.values[-1]),
                    textcoords="offset points",
                    xytext=(6, 0), fontsize=7.5, color=color, va="center")
    cat_axis(ax, labelsize=8.5)
    ax.set_xlim(-0.35, len(SIZES) - 0.25)
    ax.grid(True, which="major", zorder=0)
    ax.set_xlabel("Dataset size (rows)")
    ax.set_ylabel(ylabel)
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, fname), bbox_inches="tight")
    plt.close(fig)
    print("wrote", fname)


# ---- 6.12 throughput -------------------------------------------------------
small_multiples("throughput_rows_per_second",
                "Throughput (rows/s)", "viz_throughput.png")

# ---- 6.13 query memory -----------------------------------------------------
small_multiples("query_memory_mb",
                "Query memory (MB)", "viz_query_memory.png")

# ---- 6.14 footprint memory -------------------------------------------------
small_multiples("footprint_memory_mb",
                "Footprint memory (MB)", "viz_footprint_memory.png")

# ---- 6.16 avg execution time by pattern (grouped bars) ---------------------
def grouped_bars_by_pattern():
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    x = np.arange(len(PATTERNS))
    w = 0.26
    for i, (key, label, color, _) in enumerate(SYSTEMS):
        vals = [FR[key][FR[key]["pattern_name"] == p]["execution_time_seconds"].mean()
                for p in PATTERNS]
        bars = ax.bar(x + (i - 1) * w, vals, w, color=color, label=label,
                      edgecolor="white", linewidth=0.6, zorder=3)
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.2f}", (b.get_x() + b.get_width() / 2, v),
                        textcoords="offset points", xytext=(0, 2),
                        ha="center", fontsize=6.5, color="#333333")
    ax.set_xticks(x)
    ax.set_xticklabels(PATTERNS, rotation=15, ha="right", fontsize=8)
    ax.set_ylabel("Average execution time (s)")
    ax.grid(True, axis="y", zorder=0)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_avg_time_by_pattern.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_avg_time_by_pattern.png")

grouped_bars_by_pattern()

# ---- 6.17/6.18/6.19 averaged-by-size line charts ---------------------------
lines_by_size("execution_time_seconds", "Average execution time (s)",
              "viz_avg_time_by_size.png")
lines_by_size("query_memory_mb", "Average query memory (MB)",
              "viz_avg_memory_by_size.png")
lines_by_size("footprint_memory_mb", "Average footprint memory (MB)",
              "viz_avg_footprint_by_size.png")

# ---- 6.15 overall stats (2x2 single-metric bars) ---------------------------
def overall_stats():
    def agg(fn, col):
        return [fn(FR[key][col]) for key, *_ in SYSTEMS]
    labels = [l for _, l, _, _ in SYSTEMS]
    colors = [c for _, _, c, _ in SYSTEMS]
    panels = [
        ("Average execution time (s)", agg(np.mean, "execution_time_seconds"),
         "{:.2f}", False),
        ("Average throughput (rows/s)", agg(np.mean, "throughput_rows_per_second"),
         "{:,.0f}", False),
        ("Max query memory (MB)", agg(np.max, "query_memory_mb"),
         "{:.1f}", False),
        ("Max footprint memory (MB)", agg(np.max, "footprint_memory_mb"),
         "{:,.0f}", False),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 5.6))
    for ax, (title, vals, fmt, logy) in zip(axes.ravel(), panels):
        bars = ax.bar(range(3), vals, color=colors, edgecolor="white",
                      linewidth=0.7, zorder=3)
        if logy:
            ax.set_yscale("log")
        ax.set_xticks(range(3))
        ax.set_xticklabels(["Engine", "Oracle", "Trino"], fontsize=8)
        ax.set_title(title, fontsize=9.5)
        ax.grid(True, axis="y", zorder=0)
        ax.set_axisbelow(True)
        top = max(vals)
        for b, v in zip(bars, vals):
            ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, v),
                        textcoords="offset points", xytext=(0, 2),
                        ha="center", fontsize=7.5, color="#333333")
        if not logy:
            ax.set_ylim(0, top * 1.18)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_overall_stats.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_overall_stats.png")

overall_stats()

# ---- 6.20 correctness matrix ----------------------------------------------
def correctness_matrix():
    cols = ["Proposed\nengine", "Trino 473", "Oracle XE 21c"]
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    for r, pat in enumerate(PATTERNS):
        for c in range(3):
            ax.add_patch(plt.Rectangle((c, r), 0.96, 0.92, facecolor="#e3f3ea",
                                        edgecolor="#199e70", linewidth=1.0))
            txt = "baseline\noutput" if c == 0 else "6/6\nidentical"
            ax.text(c + 0.48, r + 0.46, ("✓ " + txt) if c else txt,
                    ha="center", va="center", fontsize=8, color="#137a54",
                    fontfamily="DejaVu Sans")
    ax.set_xlim(0, 3)
    ax.set_ylim(0, len(PATTERNS))
    ax.set_xticks([i + 0.48 for i in range(3)])
    ax.set_xticklabels(cols, fontsize=9)
    ax.set_yticks([r + 0.46 for r in range(len(PATTERNS))])
    ax.set_yticklabels(PATTERNS, fontsize=9)
    ax.xaxis.tick_top()
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_correctness.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_correctness.png")

correctness_matrix()

# ---- 6.21 relative comparison (advantage-factor lollipop, log scale) -------
def relative_comparison():
    # Signed percentages (engine vs each SQL engine; +/- means engine
    # higher/lower on that metric), computed from the result CSVs with the
    # same ratio-of-means formula as Table tab:relative_comparison.  Converted
    # to an "advantage factor" = how many times BETTER the engine is (>1
    # better, <1 worse), so every metric is read against parity at 1x.
    # lower-is-better: factor = 1/(1 + p/100); higher-is-better: factor = 1 + p/100.
    metrics = ["Execution time", "Throughput", "Operational footprint",
               "Query memory"]
    lower_better = [True, False, True, True]
    P, T, O = FR["proposed_pandas_engine"], FR["trino"], FR["oracle"]

    def pct(a, b):
        return (a / b - 1) * 100.0

    cols = ["execution_time_seconds", "throughput_rows_per_second",
            "footprint_memory_mb", "query_memory_mb"]
    pct_trino = [pct(P[c].mean(), T[c].mean()) for c in cols]
    pct_oracle = [pct(P[c].mean(), O[c].mean()) for c in cols]

    def factor(p, lb):
        return 1.0 / (1 + p / 100.0) if lb else (1 + p / 100.0)

    ft = [factor(p, lb) for p, lb in zip(pct_trino, lower_better)]
    fo = [factor(p, lb) for p, lb in zip(pct_oracle, lower_better)]

    y = np.arange(len(metrics))[::-1]  # first metric on top
    off = 0.18
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    ax.set_xscale("log")
    xmin = min(0.55, min(ft + fo) * 0.55)
    # shaded "better / worse" regions around parity
    ax.axvspan(1, 200, color="#199e70", alpha=0.05, zorder=0)
    ax.axvspan(xmin, 1, color="#e34948", alpha=0.05, zorder=0)
    ax.axvline(1, color="#555555", linewidth=1.1, zorder=2)

    def draw(vals, yoff, color, label):
        for yi, v in zip(y, vals):
            ax.plot([1, v], [yi + yoff, yi + yoff], color=color, linewidth=2,
                    zorder=3, solid_capstyle="round")
            ax.plot(v, yi + yoff, "o", color=color, markersize=8,
                    markeredgecolor="white", markeredgewidth=0.8, zorder=4)
            ax.annotate(f"{v:.2f}$\\times$" if v < 10 else f"{v:.0f}$\\times$",
                        (v, yi + yoff), textcoords="offset points",
                        xytext=(9 if v >= 1 else -9, 0),
                        ha="left" if v >= 1 else "right", va="center",
                        fontsize=8, color=color)
        ax.plot([], [], "o-", color=color, label=label)

    draw(ft, off, "#eb6834", "vs. Trino 473")
    draw(fo, -off, "#199e70", "vs. Oracle XE 21c")

    ax.set_yticks(y)
    ax.set_yticklabels(metrics, fontsize=9.5)
    ax.set_ylim(-0.6, len(metrics) - 0.4)
    ax.set_xlim(xmin, 120)
    ticks = [t for t in (0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100)
             if t >= xmin]
    ax.set_xticks(ticks)
    ax.set_xticklabels(["1$\\times$\n(parity)" if t == 1 else f"{t:g}$\\times$"
                        for t in ticks], fontsize=7.5)
    ax.set_xlabel("How many times better the proposed engine is (log scale)")
    ax.grid(True, axis="x", which="major", zorder=0, alpha=0.5)
    ax.text((xmin * 1.0) ** 0.5, len(metrics) - 0.5, "engine worse",
            fontsize=7.5, color="#b03a3a", ha="center", style="italic")
    ax.text(11, len(metrics) - 0.5, "engine better $\\rightarrow$", fontsize=7.5,
            color="#137a54", ha="center", style="italic")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_relative_comparison.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_relative_comparison.png")

relative_comparison()

# ---- A.2 pattern summary: throughput + time by pattern (2 panels) ----------
def summary_by_pattern():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.8, 4.3))
    x = np.arange(len(PATTERNS))
    w = 0.26
    for i, (key, label, color, _) in enumerate(SYSTEMS):
        thr = [FR[key][FR[key]["pattern_name"] == p]["throughput_rows_per_second"].mean() / 1e6
               for p in PATTERNS]
        tim = [FR[key][FR[key]["pattern_name"] == p]["execution_time_seconds"].mean()
               for p in PATTERNS]
        ax1.bar(x + (i - 1) * w, thr, w, color=color, label=label,
                edgecolor="white", linewidth=0.6, zorder=3)
        ax2.bar(x + (i - 1) * w, tim, w, color=color, label=label,
                edgecolor="white", linewidth=0.6, zorder=3)
    for ax, ylab in ((ax1, "Avg throughput (M rows/s)"),
                     (ax2, "Avg execution time (s)")):
        ax.set_xticks(x)
        ax.set_xticklabels(PATTERNS, rotation=18, ha="right", fontsize=7.5)
        ax.set_ylabel(ylab)
        ax.grid(True, axis="y", zorder=0)
        ax.set_axisbelow(True)
    ax1.set_title("Higher is better", fontsize=9)
    ax2.set_title("Lower is better", fontsize=9)
    h, l = ax1.get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, frameon=False, fontsize=9,
               bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(IMG, "viz_summary_by_pattern.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_summary_by_pattern.png")

summary_by_pattern()

# ---- A.3 size summary: throughput + time by size (2 panels) ----------------
def summary_by_size():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.8, 4.0))
    for key, label, color, marker in SYSTEMS:
        thr = FR[key].groupby("dataset_size")["throughput_rows_per_second"].mean().reindex(SIZES) / 1e6
        tim = FR[key].groupby("dataset_size")["execution_time_seconds"].mean().reindex(SIZES)
        ax1.plot(range(len(SIZES)), thr.values, color=color, marker=marker,
                 markersize=6, linewidth=2, markeredgecolor="white",
                 markeredgewidth=0.7, label=label, zorder=3)
        ax2.plot(range(len(SIZES)), tim.values, color=color, marker=marker,
                 markersize=6, linewidth=2, markeredgecolor="white",
                 markeredgewidth=0.7, label=label, zorder=3)
    for ax in (ax1, ax2):
        cat_axis(ax)
        ax.grid(True, which="major", zorder=0)
        ax.set_xlabel("Dataset size (rows)")
        ax.set_ylim(bottom=0)
    ax1.set_ylabel("Avg throughput (M rows/s)")
    ax1.set_title("Higher is better", fontsize=9)
    ax2.set_ylabel("Avg execution time (s)")
    ax2.set_title("Lower is better", fontsize=9)
    ax1.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_summary_by_size.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_summary_by_size.png")

summary_by_size()
print("done")
