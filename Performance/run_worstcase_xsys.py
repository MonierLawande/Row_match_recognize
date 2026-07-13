#!/usr/bin/env python3
"""Cross-system pattern-driven worst case (Axis 2).

Runs a single state-dependent query -- the simple_sequence pattern with a
running aggregate added to B's DEFINE (price > AVG(A.price)) -- on all three
systems, on ORDERED input (so the sort is not involved; this isolates the
matching / pattern-driven axis, not the ordering axis).  For the proposed
engine this predicate cannot be vectorised and drops onto the bounded
backtracking searcher; Trino and Oracle run it on their native engines.  The
harness's per-system runners, memory sampling, and correctness checks are
reused unchanged.  Output goes to Performance/worstcase_xsys/.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import Performance.run_cross_system_matrix as m

OUT = m.PERFORMANCE_DIR / "worstcase_xsys"

STATE_DEP = {
    "pattern": "A+ B+ ; B AS price > AVG(A.price)",
    "description": "simple sequence with a state-dependent DEFINE on B",
    "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B' AND price > AVG(A.price)
    """,
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--systems", nargs="+",
                   choices=["pandas", "trino", "oracle"],
                   default=["pandas", "trino", "oracle"])
    p.add_argument("--sizes", nargs="+", type=int,
                   default=[50000, 100000, 200000, 400000])
    p.add_argument("--cpus", type=int, default=1)
    p.add_argument("--memory-gb", type=int, default=32)
    p.add_argument("--warmup-runs", type=int, default=1)
    p.add_argument("--measured-runs", type=int, default=3)
    p.add_argument("--chunk-size", type=int, default=20000)
    p.add_argument("--oracle-password", default="Oracle_12345")
    p.add_argument("--oracle-dsn", default="localhost:1521/XEPDB1")
    args = p.parse_args()

    # single state-dependent pattern; ordered input (no shuffle)
    m.PATTERNS = {"state_dependent": STATE_DEP}
    m.OUTPUT_DIR = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    m.apply_local_limits(args.cpus, args.memory_gb)
    m.create_shared_datasets(args.sizes)

    results, expected = [], {}
    if "pandas" in args.systems:
        pr, expected = m.run_pandas_system(args.sizes, args.warmup_runs, args.measured_runs)
        results.extend(pr)
    if "trino" in args.systems:
        results.extend(m.run_trino_system(args.sizes, expected, args.warmup_runs,
                                          args.measured_runs, args.chunk_size,
                                          args.cpus, args.memory_gb))
    if "oracle" in args.systems:
        results.extend(m.run_oracle_system(args.sizes, expected, args.warmup_runs,
                                           args.measured_runs, args.chunk_size,
                                           args.cpus, args.memory_gb,
                                           args.oracle_password, args.oracle_dsn))
    m.write_summary(results, args)
    print("\nSaved (worst-case cross-system):", OUT)


if __name__ == "__main__":
    main()
