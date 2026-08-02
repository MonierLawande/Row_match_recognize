#!/usr/bin/env python3
"""Visual representations of the canonical cross-system benchmark results.

Renders one PNG per view into thesis/images/, all from the canonical
result CSVs so the figures and the LaTeX tables share a single source of
truth.  Palette is dataviz-validated (CVD dE 25): proposed engine = blue,
Oracle = aqua-green, Trino = orange.  Identity is carried by marker shape
and legend, not colour alone.
"""
import os
import numpy as np
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chart_labels import label_points, declutter, series_dy
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results_1core_5w20_unified")
IMG = os.path.abspath(os.path.join(HERE, "..", "..", "thesis", "images"))

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
SIZES = [100000, 200000, 400000, 800000, 1600000, 2222742]

plt.rcParams.update({
    "font.family": "Tinos", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": "#888888", "axes.linewidth": 0.7,
    "grid.color": "#dddddd", "grid.linewidth": 0.6,
    "savefig.dpi": 300, "figure.autolayout": False,
})

def load():
    frames = {}
    for key, *_ in SYSTEMS:
        fname = {"proposed_pandas_engine": "pandas_results.csv"}.get(
            key, f"{key}_results.csv")
        frames[key] = pd.read_csv(os.path.join(RES, fname))
    return frames

FR = None

# Equal-spaced categorical x axis showing every dataset size.
SIZE_LABELS = ["100K", "200K", "400K", "800K", "1.6M", "2.2M"]


def cat_x(sizes):
    return [SIZES.index(int(s)) for s in sizes]


def cat_axis(ax, labelsize=7.5):
    ax.set_xticks(range(len(SIZES)))
    ax.set_xticklabels(SIZE_LABELS, fontsize=labelsize)
    # Leave room for endpoint annotations drawn to the right of the last point.
    ax.set_xlim(-0.35, len(SIZES) - 0.10)


def _fmt(v):
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 10:
        return f"{v:.0f}"
    if v >= 1:
        return f"{v:.1f}"
    return f"{v:.2f}"


def small_multiples(metric, ylabel, fname, scale=1.0, label_all=False):
    """5 pattern panels + legend cell; one line per system.

    Linear axes throughout, starting at zero, so a distance on the page keeps
    its plain meaning: twice as far up is twice the value.  Each panel scales
    to its own family, and the final value of every series is printed next to
    it, so a series that runs close to the baseline is still read as the number
    it measured rather than as zero.  Every panel keeps its own tick labels and
    both axis labels.
    """
    fig, axes = plt.subplots(2, 3, figsize=(9.6, 5.8), sharex=True, sharey=False)
    axes = axes.ravel()
    for ax, pat in zip(axes, PATTERNS):
        panel_max = 0.0
        panel_anns = []
        for key, label, color, marker in SYSTEMS:
            d = FR[key]
            d = d[d["pattern_name"] == pat].sort_values("dataset_size")
            y = d[metric].to_numpy(dtype=float) / scale
            ax.plot(cat_x(d["dataset_size"]), y, color=color,
                    marker=marker, markersize=5, linewidth=2,
                    markeredgecolor="white", markeredgewidth=0.6,
                    label=label, zorder=3)
            panel_max = max(panel_max, float(y.max()))
            if label_all:
                # every point, all above their own line
                panel_anns.extend(label_points(
                    ax, list(range(len(y))), y, color, _fmt,
                    fontsize=5.8, dy=6))
            else:
                ax.annotate(_fmt(y[-1]), (len(SIZES) - 1, y[-1]),
                            textcoords="offset points", xytext=(4, 2),
                            fontsize=6.6, color=color, zorder=5)
        ax.set_title(PRETTY[pat])
        ax.grid(True, which="major", zorder=0)
        cat_axis(ax)
        ax.tick_params(labelsize=7.5, labelbottom=True, labelleft=True)
        ax.set_ylim(0, panel_max * (1.34 if label_all else 1.18))
        if panel_anns:
            declutter(fig, panel_anns, obstacles=ax.get_xticklabels())
        ax.set_ylabel(ylabel, fontsize=8)
        ax.set_xlabel("Dataset size (rows)", fontsize=8)
    axes[5].axis("off")
    h, l = axes[0].get_legend_handles_labels()
    axes[5].legend(h, l, loc="center", frameon=False, fontsize=10,
                   title="System", title_fontsize=10, handlelength=2.2,
                   labelspacing=1.1)
    fig.text(
        0.5, 0.01,
        "Each pattern panel uses an independent linear y-axis starting at "
        "zero.",
        ha="center", fontsize=7.5, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(os.path.join(IMG, fname), bbox_inches="tight")
    plt.close(fig)
    print("wrote", fname)


def lines_by_size(metric, ylabel, fname, label_all=True, dy_override=None):
    """Single panel: metric averaged over patterns vs size, one line/system.

    Every point carries its value.  On a linear axis a series an order of
    magnitude below the largest one necessarily runs along the baseline, and
    without the numbers it reads as a flat line at zero when it is nothing of
    the kind.
    """
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    pt_anns = []
    for key, label, color, marker in SYSTEMS:
        d = FR[key].groupby("dataset_size")[metric].mean().reindex(SIZES)
        ax.plot(range(len(SIZES)), d.values, color=color, marker=marker,
                markersize=6, linewidth=2, markeredgecolor="white",
                markeredgewidth=0.7, label=label, zorder=3)
        idx = list(range(len(d.values))) if label_all else [len(d.values) - 1]
        pt_anns.extend(label_points(
            ax, idx, [d.values[i] for i in idx], color, _fmt,
            fontsize=6.4,
            dy=(dy_override or {}).get(label, series_dy(label))))
    cat_axis(ax, labelsize=8.5)
    ax.set_xlim(-0.35, len(SIZES) - 0.25)
    ax.grid(True, which="major", zorder=0)
    ax.set_xlabel("Dataset size (rows)")
    ax.set_ylabel(ylabel)
    ax.set_ylim(ax.get_ylim()[0], ax.get_ylim()[1] * 1.08)
    declutter(fig, pt_anns, obstacles=ax.get_xticklabels())
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.10)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, fname), bbox_inches="tight")
    plt.close(fig)
    print("wrote", fname)


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
    ax.set_xticklabels([PRETTY[p] for p in PATTERNS], rotation=15,
                       ha="right", fontsize=8)
    ax.set_xlabel("Pattern family")
    ax.set_ylabel("Average execution time (s)")
    ax.grid(True, axis="y", zorder=0)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_avg_time_by_pattern.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_avg_time_by_pattern.png")

# ---- 6.15 overall stats (2x2 single-metric bars) ---------------------------
def overall_stats():
    def agg(fn, col):
        return [fn(FR[key][col]) for key, *_ in SYSTEMS]
    labels = [l for _, l, _, _ in SYSTEMS]
    colors = [c for _, _, c, _ in SYSTEMS]
    # throughput is scaled to millions so the axis needs no 1e6 offset, and
    # matches the "M rows/s" unit used by the other throughput figures
    panels = [
        ("Average execution time (s)", agg(np.mean, "execution_time_seconds"),
         "{:.2f}", False, "lower is better"),
        ("Average throughput (M rows/s)",
         [v / 1e6 for v in agg(np.mean, "throughput_rows_per_second")],
         "{:.2f}", False, "higher is better"),
        ("Max query memory (MB)", agg(np.max, "query_memory_mb"),
         "{:.1f}", False, "lower is better"),
        ("Max footprint memory (MB)", agg(np.max, "footprint_memory_mb"),
         "{:,.0f}", False, "lower is better"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 5.6))
    for ax, (title, vals, fmt, logy, cue) in zip(axes.ravel(), panels):
        bars = ax.bar(range(3), vals, color=colors, edgecolor="white",
                      linewidth=0.7, zorder=3)
        if logy:
            ax.set_yscale("log")
        ax.set_xticks(range(3))
        ax.set_xticklabels([l.replace(" ", "\n", 1) for l in labels],
                           fontsize=8)
        ax.set_title(f"{title}\n({cue})", fontsize=9)
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

# ---- 6.20 correctness matrix ----------------------------------------------
def correctness_matrix():
    cols = ["Proposed\nengine", "Trino 473", "Oracle 21c EE"]
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    for r, pat in enumerate(PATTERNS):
        for c in range(3):
            ax.add_patch(plt.Rectangle((c, r), 0.96, 0.92, facecolor="#e3f3ea",
                                        edgecolor="#199e70", linewidth=1.0))
            if c == 0:
                txt = "baseline\noutput"
            else:
                key = "trino" if c == 1 else "oracle"
                rows = FR[key][FR[key]["pattern_name"] == pat]
                matched = int(rows["correctness_matches_pandas"].fillna(
                    False).astype(bool).sum())
                txt = f"{matched}/{len(rows)}\nidentical"
            ax.text(c + 0.48, r + 0.46, txt,
                    ha="center", va="center", fontsize=8, color="#137a54")
    ax.set_xlim(0, 3)
    ax.set_ylim(0, len(PATTERNS))
    ax.set_xticks([i + 0.48 for i in range(3)])
    ax.set_xticklabels(cols, fontsize=9)
    ax.set_yticks([r + 0.46 for r in range(len(PATTERNS))])
    ax.set_yticklabels([PRETTY[p] for p in PATTERNS], fontsize=9)
    ax.xaxis.tick_top()
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_correctness.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_correctness.png")

# ---- relative comparison ---------------------------------------------------
def relative_comparison():
    # Show the two databases relative to the proposed engine (= 1x) on the two
    # lower-is-better summary metrics, so the engine itself is the blue 1x
    # reference bar and each database bar reads directly as "N times the
    # engine's cost".  (Throughput mirrors execution time and is shown in its
    # own figure; the per-query memory trade-off is in Section eval-memory.)
    metrics = ["Execution time", "Operational footprint"]
    cols = ["execution_time_seconds", "footprint_memory_mb"]
    P, T, O = FR["proposed_pandas_engine"], FR["trino"], FR["oracle"]
    eng = [1.0 for _ in cols]
    ora = [O[c].mean() / P[c].mean() for c in cols]
    tri = [T[c].mean() / P[c].mean() for c in cols]

    y = np.arange(len(metrics))[::-1]  # first metric on top
    h = 0.26
    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    for lab, vals, color, dy in (
            ("Proposed engine", eng, "#2a78d6", h),
            ("Oracle 21c EE", ora, "#199e70", 0.0),
            ("Trino 473", tri, "#e3942f", -h)):
        bars = ax.barh(y + dy, vals, h, color=color, edgecolor="white",
                       linewidth=0.6, label=lab, zorder=3)
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.1f}$\\times$",
                        (v, b.get_y() + b.get_height() / 2),
                        xytext=(4, 0), textcoords="offset points",
                        va="center", fontsize=8.5)
    ax.axvline(1, color="#888888", linewidth=1.0, linestyle=":", zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(metrics, fontsize=10)
    ax.set_ylim(-0.55, len(metrics) - 0.45)
    ax.set_xlim(0, max(tri) * 1.16)
    ax.set_xlabel("Cost relative to the proposed engine "
                  "(engine baseline = 1×; lower is better)")
    ax.grid(True, axis="x", zorder=0, alpha=0.5)
    ax.legend(frameon=True, framealpha=0.95, edgecolor="#cccccc", fontsize=9,
              loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_relative_comparison.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_relative_comparison.png")

# ---- A.2 pattern summary: throughput + time by pattern (2 panels) ----------
def summary_by_pattern():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.8, 4.3))
    x = np.arange(len(PATTERNS))
    w = 0.26
    bar_anns = []
    for i, (key, label, color, _) in enumerate(SYSTEMS):
        thr = [FR[key][FR[key]["pattern_name"] == p]["throughput_rows_per_second"].mean() / 1e6
               for p in PATTERNS]
        tim = [FR[key][FR[key]["pattern_name"] == p]["execution_time_seconds"].mean()
               for p in PATTERNS]
        ax1.bar(x + (i - 1) * w, thr, w, color=color, label=label,
                edgecolor="white", linewidth=0.6, zorder=3)
        ax2.bar(x + (i - 1) * w, tim, w, color=color, label=label,
                edgecolor="white", linewidth=0.6, zorder=3)
        bar_anns.extend(label_points(ax1, x + (i - 1) * w, thr, "#333333",
                                     "{:.2f}", fontsize=6.2, dy=2))
        bar_anns.extend(label_points(ax2, x + (i - 1) * w, tim, "#333333",
                                     "{:.2f}", fontsize=6.2, dy=2))
    for ax, ylab in ((ax1, "Avg throughput (M rows/s)"),
                     (ax2, "Avg execution time (s)")):
        ax.set_xticks(x)
        ax.set_xticklabels([PRETTY[p] for p in PATTERNS], rotation=18,
                           ha="right", fontsize=7.5)
        ax.set_xlabel("Pattern family")
        ax.set_ylabel(ylab)
        ax.grid(True, axis="y", zorder=0)
        ax.set_axisbelow(True)
    ax1.set_title("Higher is better", fontsize=9)
    ax2.set_title("Lower is better", fontsize=9)
    for ax in (ax1, ax2):
        ax.set_ylim(0, ax.get_ylim()[1] * 1.12)
    declutter(fig, bar_anns)
    h, l = ax1.get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, frameon=False, fontsize=9,
               bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(IMG, "viz_summary_by_pattern.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_summary_by_pattern.png")

# ---- A.3 size summary: throughput + time by size (2 panels) ----------------
def summary_by_size():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.8, 4.0))
    # Throughput panel: Oracle and Trino run close together low on a linear
    # axis, so Oracle labels sit above its line and Trino labels below its
    # own line.  That keeps the narrow gap between the two curves clear.
    thr_dy = {"proposed_pandas_engine": 6, "oracle": 8, "trino": -9}
    # Time panel: the three curves fan apart, so everything stacks above.
    tim_dy = {"proposed_pandas_engine": 5, "oracle": 13, "trino": 21}
    pt_anns = ([], [])
    for key, label, color, marker in SYSTEMS:
        thr = FR[key].groupby("dataset_size")["throughput_rows_per_second"].mean().reindex(SIZES) / 1e6
        tim = FR[key].groupby("dataset_size")["execution_time_seconds"].mean().reindex(SIZES)
        ax1.plot(range(len(SIZES)), thr.values, color=color, marker=marker,
                 markersize=6, linewidth=2, markeredgecolor="white",
                 markeredgewidth=0.7, label=label, zorder=3)
        ax2.plot(range(len(SIZES)), tim.values, color=color, marker=marker,
                 markersize=6, linewidth=2, markeredgecolor="white",
                 markeredgewidth=0.7, label=label, zorder=3)
        # Label every point.  The engine's time series and both databases'
        # throughput series run close to the baseline on a linear axis, so
        # the staggered start below is only a hint; declutter() resolves any
        # pair that still overlaps once the figure has been laid out.
        pt_anns[0].extend(label_points(ax1, range(len(SIZES)), thr.values,
                                       color, "{:.2f}", fontsize=6.2,
                                       dy=thr_dy[key]))
        pt_anns[1].extend(label_points(ax2, range(len(SIZES)), tim.values,
                                       color, "{:.2f}", fontsize=6.2,
                                       dy=tim_dy[key]))
    for ax in (ax1, ax2):
        cat_axis(ax)
        ax.grid(True, which="major", zorder=0)
        ax.set_xlabel("Dataset size (rows)")
        ax.set_ylim(0, ax.get_ylim()[1] * 1.10)
    ax1.set_ylabel("Avg throughput (M rows/s)")
    ax1.set_title("Higher is better", fontsize=9)
    ax2.set_ylabel("Avg execution time (s)")
    ax2.set_title("Lower is better", fontsize=9)
    ax1.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    for ax, group in zip((ax1, ax2), pt_anns):
        ax.set_ylim(ax.get_ylim()[0], ax.get_ylim()[1] * 1.06)
        declutter(fig, group, obstacles=ax.get_xticklabels())
    fig.savefig(os.path.join(IMG, "viz_summary_by_size.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_summary_by_size.png")

def main():
    global FR
    FR = load()
    small_multiples(
        "throughput_rows_per_second",
        "Throughput (million rows/s)", "viz_throughput.png", scale=1e6)
    small_multiples(
        "query_memory_mb",
        "Query memory (MB)", "viz_query_memory.png")
    small_multiples(
        "footprint_memory_mb",
        "Footprint memory (MB)", "viz_footprint_memory.png",
        label_all=True)
    grouped_bars_by_pattern()
    lines_by_size(
        "execution_time_seconds", "Average execution time (s)",
        "viz_avg_time_by_size.png", dy_override={"Trino 473": 6})
    lines_by_size(
        "query_memory_mb", "Average query memory (MB)",
        "viz_avg_memory_by_size.png",
        dy_override={"Trino 473": 6})
    lines_by_size(
        "footprint_memory_mb", "Average footprint memory (MB)",
        "viz_avg_footprint_by_size.png",
        dy_override={"Trino 473": 6})
    overall_stats()
    correctness_matrix()
    relative_comparison()
    summary_by_pattern()
    summary_by_size()
    print("done")


if __name__ == "__main__":
    main()
