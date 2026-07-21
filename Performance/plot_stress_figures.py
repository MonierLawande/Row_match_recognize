#!/usr/bin/env python3
"""Stress-test figures (thesis subsec:eval-stress), from the real-data
Amazon Reviews 2023 VOLUME run under identical conditions for all three
systems (1 CPU, 58 GB, 5M-227.9M rows):

  viz_stress_volume.png    - time and abs-peak memory vs size, all three
                             systems, with Trino's time-walls marked
  viz_stress_patterns.png  - per-pattern time at the full 227.9M corpus,
                             grouped bars for the three systems

Style contract: engine #2a78d6, Oracle #199e70, Trino #e3942f,
wall/worst-case red #e34948; linear axes; every size labelled.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.abspath(os.path.join(HERE, "..", "thesis", "images"))
VOL = os.path.join(HERE, "stress_test", "volume")

plt.rcParams.update({
    "font.family": "serif", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": "#888888", "axes.linewidth": 0.7,
    "grid.color": "#dddddd", "grid.linewidth": 0.6,
    "savefig.dpi": 200,
})

C_ENGINE, C_ORACLE, C_TRINO, C_RED = "#2a78d6", "#199e70", "#e3942f", "#e34948"
SIZES = [5_000_000, 10_000_000, 20_000_000, 40_000_000, 80_000_000,
         160_000_000, 227_899_533]
LBL = ["5M", "10M", "20M", "40M", "80M", "160M", "228M"]
PATS = ["simple_sequence", "alternation", "quantified",
        "optional_pattern", "complex_nested"]
PAT_LBL = ["simple", "alternation", "quantified", "optional", "complex"]


def _load(name):
    df = pd.read_csv(os.path.join(VOL, name))
    if "success" in df.columns:
        df["ok"] = df["success"].astype(str).isin(["True", "1", "1.0"])
    else:
        df["ok"] = True
    return df


def _series(df, metric, agg="mean"):
    """Per-size aggregate over completed families (walls excluded)."""
    ok = df[df.ok]
    g = ok.groupby("dataset_size")[metric]
    s = (g.mean() if agg == "mean" else g.max()).reindex(SIZES)
    return s


def _endlabel(ax, v, color):
    """Annotate the last non-NaN point of a series with its value."""
    a = np.asarray(v, dtype=float)
    idx = np.where(~np.isnan(a))[0]
    if len(idx):
        i = int(idx[-1])
        s = f"{a[i]:.1f}" if a[i] < 20 else f"{a[i]:.0f}"
        ax.annotate(s, (i, a[i]), textcoords="offset points", xytext=(5, 3),
                    fontsize=7.2, color=color, zorder=5)


def volume_figure():
    e, t, o = _load("matrix_1cpu_58gb_summary.csv"), \
        _load("trino_results.csv"), _load("oracle_results.csv")

    et = _series(e, "execution_time_seconds")
    ot = _series(o, "execution_time_seconds")
    tt = _series(t, "execution_time_seconds")
    em = _series(e, "footprint_memory_mb", "max") / 1024
    om = _series(o, "footprint_memory_mb", "max") / 1024
    tm = _series(t, "footprint_memory_mb", "max") / 1024

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.2, 4.3))
    x = range(len(SIZES))

    def line(ax, y, color, marker, label):
        v = y.values
        ax.plot(x, v, color=color, marker=marker, markersize=6, linewidth=2,
                markeredgecolor="white", markeredgewidth=0.7, label=label,
                zorder=3)
        _endlabel(ax, v, color)

    # --- time ---
    line(ax1, et, C_ENGINE, "o", "Proposed engine")
    line(ax1, ot, C_ORACLE, "^", "Oracle 21c EE")
    line(ax1, tt, C_TRINO, "s", "Trino 473 (disk)")
    ax1.set_ylabel("Mean execution time over families (s)")
    ax1.set_title("Volume scaling: execution time", fontsize=9.5)
    ax1.legend(frameon=False, fontsize=8.5, loc="upper left")

    # --- memory (abs peak) ---
    line(ax2, em, C_ENGINE, "o", "Proposed engine")
    line(ax2, om, C_ORACLE, "^", "Oracle 21c EE")
    line(ax2, tm, C_TRINO, "s", "Trino 473 (disk)")
    ax2.set_ylabel("Peak resident memory, mean over families (GB)")
    ax2.set_title("Volume scaling: memory footprint", fontsize=9.5)
    ax2.legend(frameon=False, fontsize=8.5, loc="upper left")

    for ax in (ax1, ax2):
        ax.set_xticks(list(x))
        ax.set_xticklabels(LBL, fontsize=8.5)
        ax.set_xlim(-0.3, len(SIZES) - 0.6)
        ax.set_ylim(bottom=0)
        ax.grid(True, zorder=0)
        ax.set_xlabel("Dataset size (rows)")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_stress_volume.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_volume.png")


def patterns_figure():
    e, t, o = _load("matrix_1cpu_58gb_summary.csv"), \
        _load("trino_results.csv"), _load("oracle_results.csv")
    sz = 227_899_533

    def val(df, p):
        r = df[(df.dataset_size == sz) & (df.pattern_name == p)]
        if len(r) and bool(r.ok.iloc[0]):
            return float(r.execution_time_seconds.iloc[0])
        return None

    ev = [val(e, p) for p in PATS]
    ov = [val(o, p) for p in PATS]
    tv = [val(t, p) for p in PATS]

    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    xi = np.arange(len(PATS))
    w = 0.26
    for off, vals, color, lab in ((-w, ev, C_ENGINE, "Proposed engine"),
                                  (0.0, ov, C_ORACLE, "Oracle 21c EE"),
                                  (w, tv, C_TRINO, "Trino 473 (disk)")):
        heights = [v if v is not None else 0 for v in vals]
        bars = ax.bar(xi + off, heights, w, color=color, label=lab,
                      edgecolor="white", linewidth=0.6, zorder=3)
        for b, v in zip(bars, vals):
            if v is None:
                # attempted but exceeded the 600 s per-query budget: a faint
                # hatched placeholder + a clear "> 600 s" label
                ax.bar(b.get_x() + b.get_width() / 2, 90, w, color="none",
                       edgecolor=C_RED, linewidth=0.9, hatch="////",
                       alpha=0.6, zorder=2)
                ax.text(b.get_x() + b.get_width() / 2, 100,
                        "did not finish\n($>$600 s)", rotation=90,
                        ha="center", va="bottom", fontsize=7.0, color=C_RED)
            else:
                ax.text(b.get_x() + b.get_width() / 2, v + 8, f"{v:.0f}",
                        ha="center", va="bottom", fontsize=7.2, color=color)
    ax.set_xticks(xi)
    ax.set_xticklabels(PAT_LBL, fontsize=9)
    ax.set_ylabel("Execution time at 227.9M rows (s)")
    ax.set_title("Per-pattern time at the full 227.9M-row corpus "
                 "(1 CPU, 58 GB)", fontsize=9.5)
    ax.set_ylim(bottom=0)
    ax.grid(True, axis="y", zorder=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_stress_patterns.png"),
                bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_patterns.png")


def throughput_figure():
    e, t, o = _load("matrix_1cpu_58gb_summary.csv"), \
        _load("trino_results.csv"), _load("oracle_results.csv")
    et = _series(e, "throughput_rows_per_second") / 1e6
    ot = _series(o, "throughput_rows_per_second") / 1e6
    tt = _series(t, "throughput_rows_per_second") / 1e6
    fig, ax = plt.subplots(figsize=(7.4, 4.3))
    x = range(len(SIZES))
    for y, c, mk, lab in ((et, C_ENGINE, "o", "Proposed engine"),
                          (ot, C_ORACLE, "^", "Oracle 21c EE"),
                          (tt, C_TRINO, "s", "Trino 473 (disk)")):
        ax.plot(x, y.values, color=c, marker=mk, markersize=6, linewidth=2,
                markeredgecolor="white", markeredgewidth=0.7, label=lab,
                zorder=3)
        _endlabel(ax, y.values, c)
    ax.set_xticks(list(x))
    ax.set_xticklabels(LBL, fontsize=8.5)
    ax.set_xlim(-0.3, len(SIZES) - 0.6)
    ax.set_ylim(bottom=0)
    ax.grid(True, zorder=0)
    ax.set_xlabel("Dataset size (rows)")
    ax.set_ylabel("Throughput (million rows/s), mean over families")
    ax.set_title("Volume scaling: throughput (higher is better)", fontsize=9.5)
    ax.legend(frameon=False, fontsize=8.5, loc="center right")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_stress_throughput.png"),
                bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_throughput.png")


def memory_detail_figure():
    """Per-query working memory for all three systems, on one panel: the
    engine's cgroup incremental peak (it scans data held in RAM) against the
    databases' own internal counters (Oracle PGA, Trino peakMemoryBytes).
    Shows the engine towering over the two databases---the memory it pays for
    speed---while both databases stay small (labelled) because they stream."""
    e, t, o = _load("matrix_1cpu_58gb_summary.csv"), \
        _load("trino_results.csv"), _load("oracle_results.csv")
    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    x = range(len(SIZES))

    def line(y, c, mk, lab):
        ax.plot(x, y.values, color=c, marker=mk, markersize=6, linewidth=2,
                markeredgecolor="white", markeredgewidth=0.7, label=lab,
                zorder=3)
        _endlabel(ax, y.values, c)

    line(_series(e, "query_memory_mb") / 1024, C_ENGINE, "o",
         "Proposed engine")
    line(_series(o, "native_query_memory_mb") / 1024, C_ORACLE, "^",
         "Oracle 21c EE (PGA)")
    line(_series(t, "native_query_memory_mb") / 1024, C_TRINO, "s",
         "Trino 473 (peakMem.)")
    # short on-graph explanations in the two empty regions, each pointing to
    # its line: the engine loads all data into RAM; the databases only keep a
    # small query workspace (their data lives in the SGA/JVM buffer on disk).
    ax.annotate("engine keeps all\ndata in RAM\n($\\approx$ data size)",
                xy=(4.6, 11.5), xytext=(2.7, 19.0), fontsize=8.0, color=C_ENGINE,
                ha="left", va="center",
                arrowprops=dict(arrowstyle="->", color=C_ENGINE, lw=0.9))
    ax.annotate("databases stream\nfrom disk", xy=(6.0, 3.7),
                xytext=(4.35, 7.2), fontsize=8.0, color="#555555",
                ha="left", va="center",
                arrowprops=dict(arrowstyle="->", color="#888888", lw=0.9))
    ax.set_xticks(list(x))
    ax.set_xticklabels(LBL, fontsize=8.5)
    ax.set_xlim(-0.3, len(SIZES) - 0.6)
    ax.set_ylim(bottom=0)
    ax.grid(True, zorder=0)
    ax.set_xlabel("Dataset size (rows)")
    ax.set_ylabel("Per-query working memory (GB)")
    ax.set_title("Per-query working memory: the engine holds data in RAM, "
                 "the databases stream", fontsize=9.5)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_stress_memory.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_memory.png")


def time_grid_figure():
    """Per-pattern execution-time scaling, one panel per family."""
    e, t, o = _load("matrix_1cpu_58gb_summary.csv"), \
        _load("trino_results.csv"), _load("oracle_results.csv")
    fig, axes = plt.subplots(2, 3, figsize=(10.6, 6.2))
    x = range(len(SIZES))

    def pat_series(df, p):
        ok = df[df.ok & (df.pattern_name == p)]
        return ok.set_index("dataset_size")["execution_time_seconds"].reindex(SIZES)

    for i, p in enumerate(PATS):
        ax = axes[i // 3][i % 3]
        for df, c, mk in ((e, C_ENGINE, "o"), (o, C_ORACLE, "^"),
                          (t, C_TRINO, "s")):
            ax.plot(x, pat_series(df, p).values, color=c, marker=mk,
                    markersize=4.5, linewidth=1.6, markeredgecolor="white",
                    markeredgewidth=0.5, zorder=3)
        # mark Trino wall
        tw = t[(~t.ok) & (t.pattern_name == p)]
        for _, row in tw.iterrows():
            xi = SIZES.index(int(row.dataset_size))
            ax.scatter([xi], [ax.get_ylim()[1] * 0.04], marker="x", s=42,
                       color=C_RED, zorder=4)
        ax.set_title(PAT_LBL[i], fontsize=9)
        ax.set_xticks(list(x))
        ax.set_xticklabels(["5M", "", "20M", "", "80M", "", "228M"],
                           fontsize=7)
        ax.set_xlim(-0.3, len(SIZES) - 0.6)
        ax.set_ylim(bottom=0)
        ax.grid(True, zorder=0)
        if i % 3 == 0:
            ax.set_ylabel("time (s)", fontsize=8)
    axes[1][2].axis("off")
    axes[1][2].plot([], [], color=C_ENGINE, marker="o", label="Proposed engine")
    axes[1][2].plot([], [], color=C_ORACLE, marker="^", label="Oracle 21c EE")
    axes[1][2].plot([], [], color=C_TRINO, marker="s", label="Trino 473 (disk)")
    axes[1][2].scatter([], [], marker="x", color=C_RED, label="Trino time-wall")
    axes[1][2].legend(frameon=False, fontsize=9, loc="center")
    fig.suptitle("Per-pattern execution-time scaling (1 CPU, 58 GB)",
                 fontsize=10, y=1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_stress_time_grid.png"),
                bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_time_grid.png")


if __name__ == "__main__":
    volume_figure()
    patterns_figure()
    throughput_figure()
    memory_detail_figure()
    time_grid_figure()
