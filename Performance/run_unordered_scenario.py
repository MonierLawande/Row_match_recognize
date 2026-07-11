#!/usr/bin/env python3
"""Unordered-input benchmark scenario (Scenario B).

The canonical matrix (Scenario A, ``run_cross_system_matrix.py``) orders by an
already-sorted ``seq_id``, so the proposed engine detects monotonic input and
skips ``sort_values`` entirely (the O(n) path).  That is realistic for
append-ordered DataFrames but flatters the engine relative to the two database
systems, which have no guaranteed table order and therefore sort on every
query regardless.

This script reruns the identical 90-cell matrix with the SAME queries, sizes,
resource policy, and sampling, but with the physical row order of every input
SHUFFLED (deterministically, per size).  ``ORDER BY seq_id`` then forces a real
sort in all three systems.  Because the logical order after sorting is
identical to Scenario A, the match results and counts are identical; only the
sort cost is added.  This isolates exactly one variable -- input orderedness --
and gives the honest picture of how the engine compares when the data is not
pre-sorted.

The harness machinery (pattern definitions, per-system runners, memory
sampling, aggregation) is reused unchanged via monkeypatching; only
``load_input`` (now shuffles) and ``OUTPUT_DIR`` (separate directory) are
redirected.  The original canonical results are never touched.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import Performance.run_cross_system_matrix as m

SHUFFLE_SEED_BASE = 1234
UNORDERED_OUTPUT_DIR = m.PERFORMANCE_DIR / "unordered_scenario"

# Canonical dataset loader, wrapped so we ensure the prepared CSV exists.
_orig_create_shared_dataset = m.create_shared_dataset


def load_input_shuffled(size: int) -> pd.DataFrame:
    """Return the prepared dataset with its physical row order shuffled.

    Deterministic per size, so every system in this run receives byte-identical
    shuffled input for a given size.  ``seq_id`` is left intact but is no longer
    monotonic in row order, so the engine's ordered-input shortcut does not fire
    and ``ORDER BY seq_id`` forces a genuine sort.
    """
    path = _orig_create_shared_dataset(size)
    df = pd.read_csv(path)
    shuffled = df.sample(frac=1.0, random_state=SHUFFLE_SEED_BASE + size)
    return shuffled.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the unordered-input benchmark scenario.")
    parser.add_argument("--systems", nargs="+", choices=["pandas", "trino", "oracle"],
                        default=["pandas", "trino", "oracle"])
    parser.add_argument("--sizes", nargs="+", type=int, default=m.DEFAULT_SIZES)
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--memory-gb", type=int, default=32)
    parser.add_argument("--warmup-runs", type=int, default=5)
    parser.add_argument("--measured-runs", type=int, default=20)
    parser.add_argument("--chunk-size", type=int, default=20000)
    parser.add_argument("--oracle-password", default="Oracle_12345")
    parser.add_argument("--oracle-dsn", default="localhost:1521/XEPDB1")
    args = parser.parse_args()

    # Redirect all output into the separate scenario directory and swap in the
    # shuffling loader.  Both are module globals read at call time by the
    # harness writers/runners, so patching them here reroutes everything.
    m.OUTPUT_DIR = UNORDERED_OUTPUT_DIR
    m.load_input = load_input_shuffled

    UNORDERED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    m.apply_local_limits(args.cpus, args.memory_gb)
    # Datasets are the SAME prepared CSVs as Scenario A (shuffled in memory).
    m.create_shared_datasets(args.sizes)

    all_results = []
    expected = {}

    if "pandas" in args.systems:
        pandas_results, expected = m.run_pandas_system(args.sizes, args.warmup_runs, args.measured_runs)
        all_results.extend(pandas_results)
    else:
        for size in args.sizes:
            for pattern_name in m.PATTERNS:
                path = UNORDERED_OUTPUT_DIR / "results" / f"pandas_{size}_{pattern_name}.csv"
                if path.exists():
                    expected[(size, pattern_name)] = m.normalize_result(pd.read_csv(path))

    if "trino" in args.systems:
        all_results.extend(
            m.run_trino_system(args.sizes, expected, args.warmup_runs, args.measured_runs,
                               args.chunk_size, args.cpus, args.memory_gb)
        )

    if "oracle" in args.systems:
        all_results.extend(
            m.run_oracle_system(args.sizes, expected, args.warmup_runs, args.measured_runs,
                                args.chunk_size, args.cpus, args.memory_gb,
                                args.oracle_password, args.oracle_dsn)
        )

    m.write_summary(all_results, args)
    print("\nSaved (unordered scenario):")
    print(f"  {UNORDERED_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
