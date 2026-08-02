#!/usr/bin/env python3
"""Stress-test figures (thesis subsec:eval-stress), from the real-data
Amazon Reviews 2023 VOLUME run under identical conditions for all three
systems (1 CPU, 58 GB, 5M-227.9M rows):

  viz_stress_volume.png    - time and abs-peak memory vs size, averaged over
                             the four families completed by every system
  viz_stress_patterns.png  - per-pattern time at the full 227.9M corpus,
                             grouped bars for the three systems, including
                             explicit 600-second timeout markers

Style contract: engine #2a78d6, Oracle #199e70, Trino #e3942f,
wall/worst-case red #e34948; linear axes; every size labelled.
"""
import os
from functools import lru_cache

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_labels import label_points, declutter, series_dy
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.abspath(os.path.join(HERE, "..", "thesis", "images"))
VOL = os.path.join(HERE, "stress_test", "volume")

plt.rcParams.update({
    "font.family": "Tinos", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": "#888888", "axes.linewidth": 0.7,
    "grid.color": "#dddddd", "grid.linewidth": 0.6,
    "savefig.dpi": 300,
})

C_ENGINE, C_ORACLE, C_TRINO, C_RED = "#2a78d6", "#199e70", "#e3942f", "#e34948"
TIMEOUT_SECONDS = 600.0
SIZES = [5_000_000, 10_000_000, 20_000_000, 40_000_000, 80_000_000,
         160_000_000, 227_899_533]
LBL = ["5M", "10M", "20M", "40M", "80M", "160M", "228M"]
PATS = ["simple_sequence", "alternation", "quantified",
        "optional_pattern", "complex_nested"]
PAT_LBL = ["Simple sequence", "Alternation", "Quantified",
           "Optional pattern", "Complex nested"]


def _load(name, system=None):
    df = pd.read_csv(os.path.join(VOL, name))
    if system is not None and "system" in df.columns:
        df = df[df["system"] == system].copy()
        if df.empty:
            raise ValueError(f"{name} contains no rows for system {system!r}")
    if "success" in df.columns:
        df["ok"] = df["success"].astype(str).isin(["True", "1", "1.0"])
    else:
        df["ok"] = True
    duplicates = df.duplicated(["dataset_size", "pattern_name"])
    if duplicates.any():
        keys = df.loc[duplicates, ["dataset_size", "pattern_name"]]
        raise ValueError(f"{name} has duplicate measurement keys:\n{keys}")
    return df


def _load_all_systems():
    """Load one validated frame per system from the current saved results."""
    engine = _load(
        "matrix_1cpu_58gb_summary.csv", "proposed_pandas_engine")
    trino = _load("trino_results.csv", "trino_473")
    oracle = _load("oracle_results.csv", "oracle_21c_ee")
    return engine, trino, oracle


@lru_cache(maxsize=1)
def common_families():
    """Families every system completed at every size.

    Averaging each size over "whatever completed there" would change the
    composition of the mean along the x axis.  Every size-average therefore
    uses one fixed family set.
    """
    keep = set(PATS)
    for d in _load_all_systems():
        done = {p for p in PATS
                if d[(d.pattern_name == p) & d.ok].dataset_size.nunique() == len(SIZES)}
        keep &= done
    return tuple(sorted(keep))


def _series(df, metric, agg="mean", families=None):
    """Per-size aggregate over one fixed family set, so the mean is
    comparable across sizes.  Walls are excluded rather than counted as zero;
    because the family set is fixed, excluding them cannot shift the mean."""
    fams = common_families() if families is None else families
    ok = df[df.ok & df.pattern_name.isin(fams)]
    g = ok.groupby("dataset_size")[metric]
    return (g.mean() if agg == "mean" else g.max()).reindex(SIZES)


def _validate_common_families():
    families = common_families()
    if len(families) != 4:
        raise ValueError(
            "Stress aggregates require the four families completed by every "
            f"system at every size; found {len(families)}: {families}")


def _endlabel(ax, v, color, offset=(5, 3), decimals=None):
    """Annotate the last non-NaN point of a series with its value."""
    a = np.asarray(v, dtype=float)
    idx = np.where(~np.isnan(a))[0]
    if len(idx):
        i = int(idx[-1])
        if decimals is not None:
            s = f"{a[i]:.{decimals}f}"
        else:
            s = f"{a[i]:.1f}" if a[i] < 20 else f"{a[i]:.0f}"
        ax.annotate(s, (i, a[i]), textcoords="offset points", xytext=offset,
                    fontsize=7.2, color=color, zorder=5)


def volume_figure():
    e, t, o = _load_all_systems()

    et = _series(e, "execution_time_seconds")
    ot = _series(o, "execution_time_seconds")
    tt = _series(t, "execution_time_seconds")
    # Mean over families, matching the axis label, the left-hand time panel,
    # and the values quoted in the text.  This panel previously aggregated
    # with max while labelling itself "mean", so the plotted line and the
    # prose disagreed by up to 8 GB at the largest size.
    em = _series(e, "footprint_memory_mb") / 1024
    om = _series(o, "footprint_memory_mb") / 1024
    tm = _series(t, "footprint_memory_mb") / 1024

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.2, 4.3))
    x = range(len(SIZES))

    vol_anns = {}

    def line(ax, y, color, marker, label, dy=None, above_at=()):
        """``above_at`` lifts individual points to the other side of the
        line, for places where the default side would crowd a neighbour."""
        v = y.values
        ax.plot(x, v, color=color, marker=marker, markersize=6, linewidth=2,
                markeredgecolor="white", markeredgewidth=0.7, label=label,
                zorder=3)
        base = series_dy(label) if dy is None else dy
        anns = label_points(ax, list(x), v, color, "{:.2f}", fontsize=6.0,
                            dy=base, skip=lambda i: i in above_at)
        if above_at:
            idx = sorted(above_at)
            anns += label_points(ax, idx, [v[i] for i in idx], color,
                                 "{:.2f}", fontsize=6.0, dy=abs(base) or 6)
        vol_anns.setdefault(id(ax), []).extend(anns)

    # --- time ---
    line(ax1, et, C_ENGINE, "o", "Proposed engine")
    line(ax1, ot, C_ORACLE, "^", "Oracle 21c EE")
    # time panel: Trino is the top curve, so its labels go above it
    line(ax1, tt, C_TRINO, "s", "Trino 473", dy=6)
    ax1.set_ylabel("Mean execution time (s)")
    ax1.set_title("Execution time: four common families", fontsize=9.5)
    ax1.legend(frameon=False, fontsize=8.5, loc="upper left")

    # --- memory (abs peak) ---
    line(ax2, em, C_ENGINE, "o", "Proposed engine")
    line(ax2, om, C_ORACLE, "^", "Oracle 21c EE")
    # footprint panel: Trino labels stay below its line, except at 40M where
    # it has just crossed above Oracle and a label below would land in the
    # narrow gap between the two curves.
    line(ax2, tm, C_TRINO, "s", "Trino 473",
         above_at={SIZES.index(40_000_000)})
    ax2.set_ylabel("Mean peak resident footprint (GB)")
    ax2.set_title("Memory footprint: four common families", fontsize=9.5)
    ax2.legend(frameon=False, fontsize=8.5, loc="upper left")

    for ax in (ax1, ax2):
        ax.set_xticks(list(x))
        ax.set_xticklabels(LBL, fontsize=8.5)
        ax.set_xlim(-0.3, len(SIZES) - 0.6)
        ax.set_ylim(bottom=0)
        ax.grid(True, zorder=0)
        ax.set_xlabel("Dataset size (rows)")
    fig.tight_layout()
    for ax in (ax1, ax2):
        # headroom first, so a stacked label is not pushed past the frame
        ax.set_ylim(ax.get_ylim()[0], ax.get_ylim()[1] * 1.14)
        declutter(fig, vol_anns.get(id(ax), []),
                  obstacles=ax.get_xticklabels())
    fig.savefig(os.path.join(IMG, "viz_stress_volume.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_volume.png")


def patterns_figure():
    e, t, o = _load_all_systems()
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
                                  (w, tv, C_TRINO, "Trino 473")):
        heights = [min(v, TIMEOUT_SECONDS) if v is not None
                   else TIMEOUT_SECONDS for v in vals]
        bars = ax.bar(xi + off, heights, w, color=color, label=lab,
                      edgecolor="white", linewidth=0.6, zorder=3)
        for b, v in zip(bars, vals):
            if v is None:
                # The true runtime is unknown beyond the wall.  Draw the
                # marker at the 600-second boundary, not near zero.
                b.set_facecolor("none")
                b.set_edgecolor(C_RED)
                b.set_hatch("////")
                b.set_linewidth(1.0)
                ax.text(b.get_x() + b.get_width() / 2,
                        TIMEOUT_SECONDS * 1.006, "timeout\n($\\geq$600 s)",
                        ha="center", va="bottom", fontsize=7.0, color=C_RED)
            else:
                ax.text(b.get_x() + b.get_width() / 2,
                        min(v, TIMEOUT_SECONDS) + 8, f"{v:.0f}",
                        ha="center", va="bottom", fontsize=7.2, color=color)
    ax.set_xticks(xi)
    ax.set_xticklabels(PAT_LBL, rotation=12, ha="right", fontsize=8.5)
    ax.set_xlabel("Pattern family")
    ax.set_ylabel("Execution time at 227.9M rows (s)")
    ax.set_title("Per-pattern time at the full 227.9M-row corpus "
                 "(1 CPU, 58 GB)", fontsize=9.5)
    ax.set_ylim(0, TIMEOUT_SECONDS * 1.12)
    ax.grid(True, axis="y", zorder=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "viz_stress_patterns.png"),
                bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_patterns.png")


def throughput_figure():
    e, t, o = _load_all_systems()
    et = _series(e, "throughput_rows_per_second") / 1e6
    ot = _series(o, "throughput_rows_per_second") / 1e6
    tt = _series(t, "throughput_rows_per_second") / 1e6
    fig, ax = plt.subplots(figsize=(7.4, 4.3))
    x = range(len(SIZES))
    thr_anns = []
    for y, c, mk, lab, offset in (
            (et, C_ENGINE, "o", "Proposed engine", (5, 5)),
            (ot, C_ORACLE, "^", "Oracle 21c EE", (5, 13)),
            (tt, C_TRINO, "s", "Trino 473", (5, 21))):
        ax.plot(x, y.values, color=c, marker=mk, markersize=6, linewidth=2,
                markeredgecolor="white", markeredgewidth=0.7, label=lab,
                zorder=3)
        thr_anns.extend(label_points(ax, list(x), y.values, c, "{:.2f}",
                                     fontsize=6.0, dy=series_dy(lab)))
    ax.set_xticks(list(x))
    ax.set_xticklabels(LBL, fontsize=8.5)
    ax.set_xlim(-0.3, len(SIZES) - 0.6)
    ax.set_ylim(bottom=0)
    ax.grid(True, zorder=0)
    ax.set_xlabel("Dataset size (rows)")
    ax.set_ylabel("Mean throughput (million rows/s)")
    ax.set_title("Throughput: four common families (higher is better)",
                 fontsize=9.5)
    ax.legend(frameon=False, fontsize=8.5, loc="center right")
    fig.tight_layout()
    ax.set_ylim(ax.get_ylim()[0], ax.get_ylim()[1] * 1.10)
    declutter(fig, thr_anns, obstacles=ax.get_xticklabels())
    fig.savefig(os.path.join(IMG, "viz_stress_throughput.png"),
                bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_throughput.png")


def memory_detail_figure():
    """Plot the available query-memory metric for each system.

    The metrics have different definitions: incremental cgroup peak for the
    proposed engine, PGA delta for Oracle, and peakMemoryBytes for Trino.
    The figure reports the measurements without assigning an unmeasured cause.
    """
    e, t, o = _load_all_systems()
    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    x = range(len(SIZES))

    def line(y, c, mk, lab):
        ax.plot(x, y.values, color=c, marker=mk, markersize=6, linewidth=2,
                markeredgecolor="white", markeredgewidth=0.7, label=lab,
                zorder=3)
        # The series are identified by marker as well as colour.  One precise
        # endpoint label keeps the smaller database series readable without
        # placing three labels on every early-size point.
        _endlabel(ax, y.values, c, decimals=2)

    eng = _series(e, "query_memory_mb") / 1024
    tri = _series(t, "native_query_memory_mb") / 1024
    # Each legend entry names the metric and how that system holds the input,
    # because the three curves are only comparable once the reader knows the
    # engine keeps the data resident in RAM while both databases read from
    # disk.  The storage modes are the ones stated in Section 6.5.8.
    line(eng, C_ENGINE, "o",
         "Engine: incremental cgroup peak\n(input held in RAM as a DataFrame)")
    line(_series(o, "native_query_memory_mb") / 1024, C_ORACLE, "^",
         "Oracle 21c EE: PGA delta\n(input on disk, native heap table)")
    line(tri, C_TRINO, "s",
         "Trino 473: peakMemoryBytes\n(input on disk, Hive/Parquet table)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(LBL, fontsize=8.5)
    ax.set_xlim(-0.3, len(SIZES) - 0.6)
    ax.set_ylim(bottom=0)
    ax.grid(True, zorder=0)
    ax.set_xlabel("Dataset size (rows)")
    ax.set_ylabel("Per-query working memory (GB)")
    ax.set_title("Reported query-memory metrics", fontsize=9.5)
    ax.legend(frameon=False, fontsize=8.0, loc="upper left",
              labelspacing=0.9, handlelength=2.2)
    fig.text(0.5, 0.01,
             "All three systems share one envelope: 1 CPU core and 58\u2009GB of "
             "RAM.  Metric definitions and storage modes differ by system; "
             "values are reported without a causal interpretation.",
             ha="center", fontsize=7.5, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(os.path.join(IMG, "viz_stress_memory.png"), bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_memory.png")


def time_grid_figure():
    """Per-pattern execution-time scaling, one independent axis per family."""
    e, t, o = _load_all_systems()
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
        # Mark a timeout at the actual 600-second wall.  A point at zero would
        # incorrectly imply a fast completed query.
        tw = t[(~t.ok) & (t.pattern_name == p)]
        panel_values = []
        for df in (e, o, t):
            panel_values.extend(
                pat_series(df, p).dropna().to_numpy(dtype=float).tolist())
        for _, row in tw.iterrows():
            xi = SIZES.index(int(row.dataset_size))
            ax.scatter([xi], [TIMEOUT_SECONDS], marker="x", s=42,
                       color=C_RED, zorder=4)
            ax.annotate("$\\geq$600", (xi, TIMEOUT_SECONDS),
                        textcoords="offset points", xytext=(0, 4),
                        ha="center", fontsize=6.5, color=C_RED)
        ax.set_title(PAT_LBL[i], fontsize=9)
        ax.set_xticks(list(x))
        ax.set_xticklabels(["5M", "", "20M", "", "80M", "", "228M"],
                           fontsize=7)
        ax.set_xlim(-0.3, len(SIZES) - 0.6)
        ceiling = max(panel_values + ([TIMEOUT_SECONDS] if len(tw) else []))
        ax.set_ylim(0, ceiling * 1.10)
        ax.grid(True, zorder=0)
        ax.set_xlabel("Dataset size (rows)", fontsize=7.5)
        ax.set_ylabel("Execution time (s)", fontsize=7.5)
    axes[1][2].axis("off")
    axes[1][2].plot([], [], color=C_ENGINE, marker="o", label="Proposed engine")
    axes[1][2].plot([], [], color=C_ORACLE, marker="^", label="Oracle 21c EE")
    axes[1][2].plot([], [], color=C_TRINO, marker="s", label="Trino 473")
    axes[1][2].scatter([], [], marker="x", color=C_RED,
                       label="Timeout at 600 s")
    axes[1][2].legend(frameon=False, fontsize=9, loc="center")
    fig.suptitle("Per-pattern execution-time scaling (1 CPU, 58 GB)",
                 fontsize=10, y=1.0)
    fig.text(0.5, 0.01,
             "Each pattern panel uses an independent linear y-axis "
             "starting at zero.",
             ha="center", fontsize=7.5, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 0.98))
    fig.savefig(os.path.join(IMG, "viz_stress_time_grid.png"),
                bbox_inches="tight")
    plt.close(fig)
    print("wrote viz_stress_time_grid.png")


if __name__ == "__main__":
    _validate_common_families()
    volume_figure()
    patterns_figure()
    throughput_figure()
    memory_detail_figure()
    time_grid_figure()
