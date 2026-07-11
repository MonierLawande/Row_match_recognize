#!/usr/bin/env python3
"""Generate every data-driven LaTeX block for thesis ch6/ch7/appendix from
the cross_system_matrix result CSVs (pandas/trino/oracle_results.csv).

Prints delimited blocks (@@@BEGIN name ... @@@END name) containing the table
body rows exactly in the format used by the thesis tables, plus a
prose_numbers block with every inline statistic quoted in the chapters.
Run from anywhere; paths are absolute.
"""
import numpy as np
import pandas as pd

BASE = "/home/monierashraf/Desktop/llm/Row_match_recognize/Performance/cross_system_matrix"
P = pd.read_csv(f"{BASE}/pandas_results.csv")
T = pd.read_csv(f"{BASE}/trino_results.csv")
O = pd.read_csv(f"{BASE}/oracle_results.csv")

PATTERNS = ["simple_sequence", "alternation", "quantified", "optional_pattern", "complex_nested"]
SIZES = [100000, 200000, 400000, 800000, 1600000, 2222742]
SYS = [("Pandas", P), ("Trino", T), ("Oracle", O)]


def texnum(n):
    return f"{n:,}".replace(",", "{,}")


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
            vals.append(f"{m:.2f} $\\pm$ {s:.2f}")
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
            vals.append(texnum(round(v, 2)) if v >= 1000 else f"{v:.2f}")
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
for label, s in [("pandas", SP), ("Trino~473", ST), ("Oracle XE~21c", SO)]:
    lines.append(
        f"% {label}: total={s['total']:.2f}, avg={s['avg']:.2f}, avgthr={texnum(round(s['avgthr']))}, "
        f"minthr={texnum(round(s['minthr']))}, maxthr={texnum(round(s['maxthr']))}, "
        f"maxqmem={s['maxq']:.2f}, maxfmem={texnum(round(s['maxf'], 2))}, medCV={s['medcv']:.1f}%"
    )
block("comment_stats", lines)

# ---- tab:overall_stats ----
lines = []
for label, s in [("Proposed Pandas engine", SP), ("Trino~473", ST), ("Oracle XE~21c", SO)]:
    lines.append(
        f"{label} & 30 & {s['total']:.2f} & {s['avg']:.2f} & {texnum(round(s['avgthr']))} & "
        f"{texnum(round(s['minthr']))}--{texnum(round(s['maxthr']))} & {s['maxq']:.2f} & {texnum(round(s['maxf'], 2))} \\\\"
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
        vals.append(texnum(round(v, 2)) if v >= 1000 else f"{v:.2f}")
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
