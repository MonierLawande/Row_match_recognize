#!/usr/bin/env python3
"""Aggregate cross_system_matrix results into the numbers needed for
thesis chapter 6 tables (6.6-6.16). Prints LaTeX-ready rows."""
import pandas as pd

pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 25)
pd.set_option('display.max_rows', 200)

BASE = 'Performance/cross_system_matrix'

pandas_df = pd.read_csv(f'{BASE}/pandas_results.csv')
trino_df = pd.read_csv(f'{BASE}/trino_results.csv')
oracle_df = pd.read_csv(f'{BASE}/oracle_results.csv')

for df, name in [(pandas_df, 'pandas'), (trino_df, 'trino'), (oracle_df, 'oracle')]:
    df['system'] = name

all_df = pd.concat([pandas_df, trino_df, oracle_df], ignore_index=True)

PATTERNS = ['simple_sequence', 'alternation', 'quantified', 'optional_pattern', 'complex_nested']
SIZES = [50000, 100000, 200000, 400000, 800000, 1000000, 1500000, 2000000]

def fmt_int(n):
    return f"{n:,}"

def fmt(n, dec=2):
    return f"{n:,.{dec}f}"

print("="*80)
print("TABLE 6.6-equivalent: Pattern Performance Summary — ALL 3 SYSTEMS")
print("="*80)
for pat in PATTERNS:
    row = [pat]
    for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
        sub = df[df.pattern_name == pat]
        avg_thr = sub.throughput_rows_per_second.mean()
        avg_time = sub.execution_time_seconds.mean()
        row.append(f"{sysname}: thr={fmt_int(round(avg_thr))} time={fmt(avg_time)}")
    print(pat, '|', ' || '.join(row[1:]))

print()
print("="*80)
print("TABLE 6.7-equivalent: Performance Summary by Dataset Size — ALL 3 SYSTEMS")
print("="*80)
for size in SIZES:
    row = [str(size)]
    for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
        sub = df[df.dataset_size == size]
        avg_thr = sub.throughput_rows_per_second.mean()
        avg_time = sub.execution_time_seconds.mean()
        row.append(f"{sysname}: thr={fmt_int(round(avg_thr))} time={fmt(avg_time)}")
    print(size, '|', ' || '.join(row[1:]))

print()
print("="*80)
print("TABLE 6.8-equivalent: Execution Time (s) by Pattern x Size x System")
print("="*80)
for pat in PATTERNS:
    for size in SIZES:
        vals = []
        for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
            v = df[(df.pattern_name == pat) & (df.dataset_size == size)].execution_time_seconds.values
            vals.append(fmt(v[0]) if len(v) else 'NA')
        print(f"{pat:20s} {size:>9,} : pandas={vals[0]:>8} trino={vals[1]:>8} oracle={vals[2]:>8}")

print()
print("="*80)
print("TABLE 6.9-equivalent: Throughput (rows/s) by Pattern x Size x System")
print("="*80)
for pat in PATTERNS:
    for size in SIZES:
        vals = []
        for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
            v = df[(df.pattern_name == pat) & (df.dataset_size == size)].throughput_rows_per_second.values
            vals.append(fmt_int(round(v[0])) if len(v) else 'NA')
        print(f"{pat:20s} {size:>9,} : pandas={vals[0]:>10} trino={vals[1]:>10} oracle={vals[2]:>10}")

print()
print("="*80)
print("TABLE 6.10-equivalent: Memory (MB) by Pattern x Size x System")
print("="*80)
for pat in PATTERNS:
    for size in SIZES:
        vals = []
        for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
            v = df[(df.pattern_name == pat) & (df.dataset_size == size)].memory_mb.values
            vals.append(fmt(v[0]) if len(v) else 'NA')
        print(f"{pat:20s} {size:>9,} : pandas={vals[0]:>10} trino={vals[1]:>10} oracle={vals[2]:>10}")

print()
print("="*80)
print("TABLE 6.11-equivalent: Overall stats per system")
print("="*80)
for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
    total_time = df.execution_time_seconds.sum()
    avg_time = df.execution_time_seconds.mean()
    avg_thr = df.throughput_rows_per_second.mean()
    min_thr = df.throughput_rows_per_second.min()
    max_thr = df.throughput_rows_per_second.max()
    max_mem = df.memory_mb.max()
    print(f"{sysname}: total_time={fmt(total_time)} avg_time={fmt(avg_time)} avg_thr={fmt_int(round(avg_thr))} min_thr={fmt_int(round(min_thr))} max_thr={fmt_int(round(max_thr))} max_mem={fmt(max_mem)} tests={len(df)}")

print()
print("="*80)
print("TABLE 6.12-equivalent: Cross-system summary")
print("="*80)
for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
    n = len(df)
    avg_time = df.execution_time_seconds.mean()
    avg_thr = df.throughput_rows_per_second.mean()
    max_mem = df.memory_mb.max()
    correct = df.correctness_matches_pandas
    if sysname == 'pandas':
        correct_str = 'baseline'
    else:
        correct_str = f"{(correct == True).sum()}/{n} match"
    print(f"{sysname}: n={n} avg_time={fmt(avg_time)} avg_thr={fmt_int(round(avg_thr))} max_mem={fmt(max_mem)} correctness={correct_str}")

print()
print("="*80)
print("TABLE 6.13-equivalent: Avg execution time by pattern (all systems)")
print("="*80)
for pat in PATTERNS:
    row = []
    for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
        v = df[df.pattern_name == pat].execution_time_seconds.mean()
        row.append(fmt(v))
    print(f"{pat:20s} pandas={row[0]:>8} trino={row[1]:>8} oracle={row[2]:>8}")

print()
print("="*80)
print("TABLE 6.14-equivalent: Avg execution time by size (all systems)")
print("="*80)
for size in SIZES:
    row = []
    for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
        v = df[df.dataset_size == size].execution_time_seconds.mean()
        row.append(fmt(v))
    print(f"{size:>10,} pandas={row[0]:>8} trino={row[1]:>8} oracle={row[2]:>8}")

print()
print("="*80)
print("TABLE 6.15-equivalent: Avg memory by size (all systems)")
print("="*80)
for size in SIZES:
    row = []
    for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
        v = df[df.dataset_size == size].memory_mb.mean()
        row.append(fmt(v))
    print(f"{size:>10,} pandas={row[0]:>8} trino={row[1]:>8} oracle={row[2]:>8}")

print()
print("="*80)
print("TABLE 6.16-equivalent: Correctness by pattern")
print("="*80)
for pat in PATTERNS:
    trino_c = trino_df[trino_df.pattern_name == pat].correctness_matches_pandas
    oracle_c = oracle_df[oracle_df.pattern_name == pat].correctness_matches_pandas
    print(f"{pat:20s} trino_all_match={(trino_c==True).all()} ({(trino_c==True).sum()}/{len(trino_c)})  oracle_all_match={(oracle_c==True).all()} ({(oracle_c==True).sum()}/{len(oracle_c)})")

print()
print("Overall min/max throughput per system (for prose):")
for sysname, df in [('pandas', pandas_df), ('trino', trino_df), ('oracle', oracle_df)]:
    print(sysname, 'min', fmt_int(round(df.throughput_rows_per_second.min())), 'max', fmt_int(round(df.throughput_rows_per_second.max())))
