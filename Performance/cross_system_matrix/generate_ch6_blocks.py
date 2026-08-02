#!/usr/bin/env python3
"""Generate every data-driven LaTeX block for thesis ch6/ch7/appendix from
the cross_system_matrix result CSVs (pandas/trino/oracle_results.csv).

Prints delimited blocks (@@@BEGIN name ... @@@END name) containing the table
body rows exactly in the format used by the thesis tables, plus a
prose_numbers block with every inline statistic quoted in the chapters.
Run from anywhere; paths are resolved relative to this script.
"""
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent / "results_1core_5w20_unified"
P = pd.read_csv(BASE / "pandas_results.csv")
T = pd.read_csv(BASE / "trino_results.csv")
O = pd.read_csv(BASE / "oracle_results.csv")

PATTERNS = ["simple_sequence", "alternation", "quantified", "optional_pattern", "complex_nested"]
SIZES = [100000, 200000, 400000, 800000, 1600000, 2222742]
SYS = [("Pandas", P), ("Trino", T), ("Oracle", O)]


def texnum(n):
    return f"{n:,}".replace(",", "{,}")


def texnum2(v):
    """Thousands-separated with exactly two decimals.

    ``texnum(round(v, 2))`` silently drops a trailing zero for values
    >= 1000 (1993.00 -> "1,993.0"), which left mixed decimal widths in
    the same column.  This keeps every cell at two decimals.
    """
    return f"{v:,.2f}".replace(",", "{,}")


def texpat(p):
    return p.replace("_", r"\_")


def cell(df, pat, size, col):
    row = df[(df.pattern_name == pat) & (df.dataset_size == size)]
    assert len(row) == 1, (pat, size, col)
    return row.iloc[0][col]


def block(name, lines):
    print(f"@@@BEGIN {name}")
    print("\n".join(lines))
    print(f"@@@END {name}")
    print()


# ---- tab:execution_times ----
lines = []
for i, pat in enumerate(PATTERNS):
    if i:
        lines.append(r"\midrule")
    for size in SIZES:
        vals = []
        for _, df in SYS:
            m = cell(df, pat, size, "execution_time_seconds")
            s = cell(df, pat, size, "execution_time_std_seconds")
            vals.append(f"{m:.3f} $\\pm$ {s:.3f}")
        lines.append(f"{texpat(pat)} & {texnum(size)} & {vals[0]} & {vals[1]} & {vals[2]} \\\\")
block("execution_times", lines)

# ---- tab:throughput ----
lines = []
for i, pat in enumerate(PATTERNS):
    if i:
        lines.append(r"\midrule")
    for size in SIZES:
        vals = [texnum(round(cell(df, pat, size, "throughput_rows_per_second"))) for _, df in SYS]
        lines.append(f"{texpat(pat)} & {texnum(size)} & {vals[0]} & {vals[1]} & {vals[2]} \\\\")
block("throughput", lines)

# ---- tab:memory_cache ----
lines = []
for i, pat in enumerate(PATTERNS):
    if i:
        lines.append(r"\midrule")
    for size in SIZES:
        vals = [f"{cell(df, pat, size, 'query_memory_mb'):.2f}" for _, df in SYS]
        lines.append(f"{texpat(pat)} & {texnum(size)} & {vals[0]} & {vals[1]} & {vals[2]} \\\\")
block("memory_cache", lines)

# ---- tab:memory_footprint ----
lines = []
for i, pat in enumerate(PATTERNS):
    if i:
        lines.append(r"\midrule")
    for size in SIZES:
        vals = []
        for _, df in SYS:
            v = cell(df, pat, size, "footprint_memory_mb")
            vals.append(texnum2(v) if v >= 1000 else f"{v:.2f}")
        lines.append(f"{texpat(pat)} & {texnum(size)} & {vals[0]} & {vals[1]} & {vals[2]} \\\\")
block("memory_footprint", lines)


def sysstats(df):
    return {
        "total": df.execution_time_seconds.sum(),
        "avg": df.execution_time_seconds.mean(),
        "avgthr": df.throughput_rows_per_second.mean(),
        "minthr": df.throughput_rows_per_second.min(),
        "maxthr": df.throughput_rows_per_second.max(),
        "maxq": df.query_memory_mb.max(),
        "maxf": df.footprint_memory_mb.max(),
        "medcv": (df.execution_time_std_seconds / df.execution_time_seconds).median() * 100,
    }


SP, ST, SO = sysstats(P), sysstats(T), sysstats(O)

# ---- comment stats (ch6 comment block above tab:execution_times) ----
lines = []
for label, s in [("pandas", SP), ("Trino~473", ST), ("Oracle~21c EE", SO)]:
    lines.append(
        f"% {label}: total={s['total']:.2f}, avg={s['avg']:.2f}, avgthr={texnum(round(s['avgthr']))}, "
        f"minthr={texnum(round(s['minthr']))}, maxthr={texnum(round(s['maxthr']))}, "
        f"maxqmem={s['maxq']:.2f}, maxfmem={texnum2(s['maxf'])}, medCV={s['medcv']:.1f}%"
    )
block("comment_stats", lines)

# ---- tab:overall_stats ----
lines = []
for label, s in [("Proposed engine", SP), ("Trino~473", ST), ("Oracle~21c EE", SO)]:
    lines.append(
        f"{label} & 30 & {s['total']:.2f} & {s['avg']:.2f} & {texnum(round(s['avgthr']))} & "
        f"{texnum(round(s['minthr']))}--{texnum(round(s['maxthr']))} & {s['maxq']:.2f} & {texnum2(s['maxf'])} \\\\"
    )
block("overall_stats", lines)

# tab:cross_system_summary was removed from ch6 (its time/throughput/memory
# duplicated tab:overall_stats and its correctness column duplicated
# tab:cross_system_correctness); no block is emitted for it.

# ---- tab:avg_time_by_pattern ----
lines = []
for pat in PATTERNS:
    vals = [f"{df[df.pattern_name == pat].execution_time_seconds.mean():.2f}" for _, df in SYS]
    lines.append(f"{texpat(pat)} & {vals[0]} & {vals[1]} & {vals[2]} \\\\")
block("avg_time_by_pattern", lines)

# ---- tab:avg_time_by_size ----
lines = []
for size in SIZES:
    vals = [f"{df[df.dataset_size == size].execution_time_seconds.mean():.2f}" for _, df in SYS]
    lines.append(f"{texnum(size)} & {vals[0]} & {vals[1]} & {vals[2]} \\\\")
block("avg_time_by_size", lines)

# ---- tab:avg_memory_by_size ----
lines = []
for size in SIZES:
    vals = [f"{df[df.dataset_size == size].query_memory_mb.mean():.2f}" for _, df in SYS]
    lines.append(f"{texnum(size)} & {vals[0]} & {vals[1]} & {vals[2]} \\\\")
block("avg_memory_by_size", lines)

# ---- tab:avg_footprint_by_size ----
lines = []
for size in SIZES:
    vals = []
    for _, df in SYS:
        v = df[df.dataset_size == size].footprint_memory_mb.mean()
        vals.append(texnum2(v) if v >= 1000 else f"{v:.2f}")
    lines.append(f"{texnum(size)} & {vals[0]} & {vals[1]} & {vals[2]} \\\\")
block("avg_footprint_by_size", lines)


# ---- tab:relative_comparison ----
def pct(a, b):
    return (a / b - 1) * 100


def fmt_pct(v):
    return f"$+{v:.0f}\\%$" if v >= 0 else f"$-{abs(v):.0f}\\%$"


rel = [
    ("Execution time", pct(SP["avg"], ST["avg"]), pct(SP["avg"], SO["avg"])),
    ("Throughput", pct(SP["avgthr"], ST["avgthr"]), pct(SP["avgthr"], SO["avgthr"])),
    ("Query memory", pct(P.query_memory_mb.mean(), T.query_memory_mb.mean()),
     pct(P.query_memory_mb.mean(), O.query_memory_mb.mean())),
    ("Operational footprint", pct(P.footprint_memory_mb.mean(), T.footprint_memory_mb.mean()),
     pct(P.footprint_memory_mb.mean(), O.footprint_memory_mb.mean())),
]
lines = [f"{name} & {fmt_pct(a)} & {fmt_pct(b)} \\\\" for name, a, b in rel]
block("relative_comparison", lines)

# ---- appendix tab:pattern_summary ----
lines = []
for pat in PATTERNS:
    parts = [texpat(pat)]
    for _, df in SYS:
        sub = df[df.pattern_name == pat]
        parts.append(texnum(round(sub.throughput_rows_per_second.mean())))
        parts.append(f"{sub.execution_time_seconds.mean():.2f}")
    lines.append(" & ".join(parts) + " \\\\")
block("pattern_summary", lines)

# ---- appendix tab:size_summary ----
lines = []
for size in SIZES:
    parts = [texnum(size)]
    for _, df in SYS:
        sub = df[df.dataset_size == size]
        parts.append(texnum(round(sub.throughput_rows_per_second.mean())))
        parts.append(f"{sub.execution_time_seconds.mean():.2f}")
    lines.append(" & ".join(parts) + " \\\\")
block("size_summary", lines)

# ---- appendix tab:match_counts ----
lines = []
for size in SIZES:
    parts = [texnum(size)]
    for pat in PATTERNS:
        parts.append(texnum(int(cell(P, pat, size, "result_rows"))))
    lines.append(" & ".join(parts) + " \\\\")
block("match_counts", lines)

# ---- appendix ordered vs shuffled input ----
PERF = BASE.parent.parent
UNORDERED = pd.read_csv(
    PERF / "unordered_scenario" / "matrix_1cpu_32gb_summary.csv"
)
WORST = pd.read_csv(
    PERF / "worstcase_xsys" / "matrix_1cpu_32gb_summary.csv"
)
STRESS = pd.read_csv(
    PERF / "stress_test" / "volume" / "matrix_1cpu_58gb_summary.csv"
)

SYSTEM_KEYS = [
    ("Proposed engine", "proposed_pandas_engine", P),
    ("Trino~473", "trino_473", T),
    ("Oracle~21c EE", "oracle_21c_ee", O),
]

lines = []
for label, key, ordered in SYSTEM_KEYS:
    shuffled = UNORDERED[UNORDERED.system == key]
    a = ordered.execution_time_seconds.mean()
    b = shuffled.execution_time_seconds.mean()
    lines.append(f"{label} & {a:.3f} & {b:.3f} & ${b/a:.2f}\\times$ \\\\")
block("ordering_scenarios", lines)

lines = []
for size in SIZES:
    parts = [texnum(size)]
    for _, key, ordered in SYSTEM_KEYS:
        a = ordered[ordered.dataset_size == size].execution_time_seconds.mean()
        shuffled = UNORDERED[
            (UNORDERED.system == key) & (UNORDERED.dataset_size == size)
        ]
        b = shuffled.execution_time_seconds.mean()
        parts.extend([f"{a:.3f}", f"{b:.3f}", f"{b/a:.2f}$\\times$"])
    lines.append(" & ".join(parts) + " \\\\")
block("ordering_by_size", lines)

lines = []
shuffled_engine = UNORDERED[UNORDERED.system == "proposed_pandas_engine"]
for size in SIZES:
    a = P[P.dataset_size == size].execution_time_seconds.mean()
    b = shuffled_engine[
        shuffled_engine.dataset_size == size
    ].execution_time_seconds.mean()
    delta = b - a
    delta_ms = delta * 1e3
    ns_per_row = delta * 1e9 / size
    ns_per_nlogn = delta * 1e9 / (size * np.log2(size))
    lines.append(
        f"{texnum(size)} & {a:.3f} & {b:.3f} & {delta_ms:.1f} & "
        f"{ns_per_row:.1f} & {ns_per_nlogn:.2f} \\\\"
    )
block("sort_cost_by_size", lines)

# ---- appendix state-dependent aggregate comparison ----
lines = []
for size in SIZES:
    vals = []
    for key in ("proposed_pandas_engine", "trino_473", "oracle_21c_ee"):
        row = WORST[(WORST.system == key) & (WORST.dataset_size == size)]
        assert len(row) == 1, (key, size)
        vals.append(f"{row.iloc[0].execution_time_seconds:.3f}")
    lines.append(
        f"{texnum(size)} & {vals[0]} & {vals[1]} & {vals[2]} \\\\"
    )
block("worstcase_coverage", lines)

# ---- appendix stress-test matrices ----
STRESS_SIZES = sorted(int(s) for s in STRESS.dataset_size.unique())
STRESS_SYSTEMS = [
    ("Proposed engine", "proposed_pandas_engine"),
    ("Oracle~21c EE", "oracle_21c_ee"),
    ("Trino~473 (disk connector)", "trino_473"),
]


def stress_row(system, pattern, size):
    row = STRESS[
        (STRESS.system == system)
        & (STRESS.pattern_name == pattern)
        & (STRESS.dataset_size == size)
    ]
    assert len(row) == 1, (system, pattern, size)
    return row.iloc[0]


def stress_blocks(metric, formatter):
    lines = []
    for system_label, system_key in STRESS_SYSTEMS:
        lines.append(
            rf"\multicolumn{{6}}{{@{{}}l}}{{\textit{{{system_label}}}}}\\*"
        )
        for size in STRESS_SIZES:
            vals = []
            for pattern in PATTERNS:
                row = stress_row(system_key, pattern, size)
                vals.append(formatter(row, metric))
            lines.append(f"{texnum(size)} & " + " & ".join(vals) + r" \\")
        if system_key != STRESS_SYSTEMS[-1][1]:
            lines.append(r"\addlinespace[3pt]")
    return lines


def fmt_stress_time(row, _metric):
    if not bool(row.success):
        return r"\textit{wall}"
    return (
        f"{row.execution_time_seconds:.2f}\\,$\\pm$\\,"
        f"{row.execution_time_std_seconds:.2f}"
    )


def fmt_stress_gb(row, metric):
    if not bool(row.success):
        return r"\textit{wall}"
    return f"{getattr(row, metric) / 1024:.2f}"


def fmt_stress_inc_gb(row, metric):
    if not bool(row.success):
        return r"\textit{wall}"
    return f"{getattr(row, metric) / 1024:.3f}"


def fmt_stress_thr(row, metric):
    if not bool(row.success):
        return r"\textit{wall}"
    return f"{getattr(row, metric) / 1e6:.2f}"


block("stress_volume", stress_blocks("execution_time_seconds", fmt_stress_time))
block("stress_mem", stress_blocks("footprint_memory_mb", fmt_stress_gb))
block(
    "stress_throughput",
    stress_blocks("throughput_rows_per_second", fmt_stress_thr),
)
block(
    "stress_incremental_memory",
    stress_blocks("query_memory_mb", fmt_stress_inc_gb),
)

lines = []
for system_label, system_key in STRESS_SYSTEMS[1:]:
    lines.append(
        rf"\multicolumn{{6}}{{@{{}}l}}{{\textit{{{system_label}}}}}\\*"
    )
    for size in STRESS_SIZES:
        vals = []
        for pattern in PATTERNS:
            row = stress_row(system_key, pattern, size)
            vals.append(fmt_stress_inc_gb(row, "native_query_memory_mb"))
        lines.append(f"{texnum(size)} & " + " & ".join(vals) + r" \\")
    if system_key != STRESS_SYSTEMS[-1][1]:
        lines.append(r"\addlinespace[3pt]")
block("stress_native_memory", lines)

lines = []
stress_engine = STRESS[STRESS.system == "proposed_pandas_engine"]
for size in STRESS_SIZES:
    parts = [texnum(size)]
    for pattern in PATTERNS:
        row = stress_engine[
            (stress_engine.pattern_name == pattern)
            & (stress_engine.dataset_size == size)
        ]
        assert len(row) == 1, (pattern, size)
        parts.append(texnum(int(row.iloc[0].result_rows)))
    lines.append(" & ".join(parts) + " \\\\")
block("stress_match_counts", lines)

lines = []
for label, df in (
    ("main", pd.concat([P, T, O], ignore_index=True)),
    ("unordered", UNORDERED),
    ("worst", WORST),
    ("stress", STRESS),
):
    completed = int(df.success.sum())
    attempted = len(df)
    lines.append(f"{label}: {completed}/{attempted} successful")
block("appendix_coverage", lines)

# ---- prose numbers ----
lines = []
lines.append(f"pandas avg={SP['avg']:.2f} trino avg={ST['avg']:.2f} oracle avg={SO['avg']:.2f}")
lines.append(f"pandas vs trino: {pct(SP['avg'], ST['avg']):+.1f}% ; pandas/oracle time factor: {SP['avg']/SO['avg']:.2f}x")
lines.append(f"avg throughput pandas: {round(SP['avgthr']):,}")
cn_p = P[P.pattern_name == 'complex_nested'].execution_time_seconds.mean()
cn_t = T[T.pattern_name == 'complex_nested'].execution_time_seconds.mean()
lines.append(f"complex_nested avg: pandas {cn_p:.2f} vs trino {cn_t:.2f} (trino/pandas={cn_t/cn_p:.2f}x)")
by_size_thr = P.groupby('dataset_size').throughput_rows_per_second.mean()
lines.append(f"pandas per-size avg thr range: {round(by_size_thr.min()):,} .. {round(by_size_thr.max()):,}")
ps = P.groupby('dataset_size').execution_time_seconds.mean()
os_ = O.groupby('dataset_size').execution_time_seconds.mean()
lines.append(f"pandas/oracle per-size time factor: {min(ps/os_):.1f}..{max(ps/os_):.1f}")
pthr = P.groupby('dataset_size').throughput_rows_per_second.mean()
othr = O.groupby('dataset_size').throughput_rows_per_second.mean()
lines.append(f"oracle/pandas per-size thr factor: {min(othr/pthr):.1f}..{max(othr/pthr):.1f}")
lines.append(f"median CV: pandas {SP['medcv']:.1f}% trino {ST['medcv']:.1f}% oracle {SO['medcv']:.1f}%")
imax = P.query_memory_mb.idxmax()
lines.append(f"max query mem pandas: {SP['maxq']:.2f} (pattern {P.loc[imax,'pattern_name']} @ {P.loc[imax,'dataset_size']})")
big = P[P.dataset_size == 2222742][['pattern_name', 'query_memory_mb']].sort_values('query_memory_mb', ascending=False)
lines.append("pandas qmem @2.22M: " + ", ".join(f"{r.pattern_name}={r.query_memory_mb:.2f}" for r in big.itertuples()))
bigt = T[T.dataset_size == 2222742]['query_memory_mb']
bigo = O[O.dataset_size == 2222742]['query_memory_mb']
lines.append(f"trino qmem @2.22M range: {bigt.min():.2f}-{bigt.max():.2f}; oracle: {bigo.min():.2f}-{bigo.max():.2f}")
lines.append(f"max footprint: pandas {SP['maxf']:.2f} trino {ST['maxf']:.2f} oracle {SO['maxf']:.2f}")
lines.append(f"oracle-peak/pandas-peak footprint: {SO['maxf']/SP['maxf']:.1f}x")
lines.append(f"footprint mean: pandas {P.footprint_memory_mb.mean():.2f} trino {T.footprint_memory_mb.mean():.2f} oracle {O.footprint_memory_mb.mean():.2f}")
lines.append(f"footprint mean ratio trino/pandas: {T.footprint_memory_mb.mean()/P.footprint_memory_mb.mean():.0f}x ; oracle/pandas: {O.footprint_memory_mb.mean()/P.footprint_memory_mb.mean():.1f}x")
lines.append(f"query mem mean: pandas {P.query_memory_mb.mean():.2f} trino {T.query_memory_mb.mean():.2f} oracle {O.query_memory_mb.mean():.2f}")
corr_t = int(T.correctness_matches_pandas.sum())
corr_o = int(O.correctness_matches_pandas.sum())
lines.append(f"correctness: trino {corr_t}/30 oracle {corr_o}/30")
faster = [p for p in PATTERNS
          if P[P.pattern_name == p].execution_time_seconds.mean() < T[T.pattern_name == p].execution_time_seconds.mean()]
lines.append(f"pandas faster than trino on: {faster}")
# R^2 of time vs size per pattern (pandas)
r2s = {}
for pat in PATTERNS:
    sub = P[P.pattern_name == pat].sort_values('dataset_size')
    x = sub.dataset_size.to_numpy(dtype=float)
    y = sub.execution_time_seconds.to_numpy(dtype=float)
    coef = np.polyfit(x, y, 1)
    yhat = np.polyval(coef, x)
    ss_res = ((y - yhat) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2s[pat] = 1 - ss_res / ss_tot
lines.append("pandas R2 time-vs-size: " + ", ".join(f"{k}={v:.4f}" for k, v in r2s.items()))
lines.append(f"min R2: {min(r2s.values()):.4f}")
block("prose_numbers", lines)
