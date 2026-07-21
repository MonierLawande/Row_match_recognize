#!/usr/bin/env python3
"""Reproducible stress profile for the proposed MATCH_RECOGNIZE engine.

This complements (and never overwrites) the ordinary cross-system matrix.  It
targets execution paths that a row-local benchmark does not expose:

* ordered versus shuffled input (ORDER BY cost),
* state-dependent DEFINE predicates (exact backtracking),
* scalar navigation predicates,
* terminal-anchor rollback,
* nonlinear ambiguous label assignment,
* partitioning, large outputs, and rejection-heavy scans.

Query time includes result construction but excludes CSV loading and DataFrame
shuffling.  RSS is sampled with the same helper used by the cross-system
benchmark.  Results are checkpointed after every case.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

# Set native-library limits before importing pandas/numpy.
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import pandas as pd
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import Performance.run_cross_system_matrix as matrix
from src.executor.match_recognize import match_recognize


OUTPUT_DIR = PROJECT_ROOT / "Performance" / "engine_stress"
CSV_PATH = OUTPUT_DIR / "engine_stress_results.csv"
JSON_PATH = OUTPUT_DIR / "engine_stress_results.json"


@dataclass
class StressRecord:
    family: str
    case: str
    input_rows: int
    input_order: str
    expected_engine_path: str
    success: bool
    correct: bool
    mean_seconds: float | None
    std_seconds: float | None
    min_seconds: float | None
    max_seconds: float | None
    throughput_rows_per_second: float | None
    mean_query_rss_delta_mb: float | None
    mean_process_peak_rss_mb: float | None
    result_rows: int | None
    result_digest: str | None
    warmup_runs: int
    measured_runs: int
    error: str | None = None


@dataclass
class StressCase:
    family: str
    name: str
    size: int
    input_order: str
    expected_path: str
    make_input: Callable[[], pd.DataFrame]
    query: str
    validate: Callable[[pd.DataFrame], bool]


def _query(body: str) -> str:
    return f"SELECT * FROM data MATCH_RECOGNIZE (\n{body}\n)"


SIMPLE_QUERY = matrix.query_for_system("pandas", "simple_sequence")

STATE_DEPENDENT_QUERY = _query(
    """
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
    """
)

NAVIGATION_QUERY = _query(
    """
    ORDER BY seq_id
    MEASURES
        FIRST(A.seq_id) AS start_row,
        LAST(B.seq_id) AS end_row,
        COUNT(*) AS match_length
    ONE ROW PER MATCH
    PATTERN (A B+)
    DEFINE
        A AS category = 'A',
        B AS category = 'B' AND price > PREV(price)
    """
)

PARTITION_QUERY = _query(
    """
    PARTITION BY category_name
    ORDER BY seq_id
    MEASURES
        FIRST(A.seq_id) AS start_row,
        LAST(B.seq_id) AS end_row,
        COUNT(*) AS match_length
    ONE ROW PER MATCH
    PATTERN (A+ B+)
    DEFINE
        A AS category = 'A',
        B AS category = 'B'
    """
)

ALL_ROWS_QUERY = _query(
    """
    ORDER BY seq_id
    MEASURES MATCH_NUMBER() AS match_number
    ALL ROWS PER MATCH
    PATTERN (A+)
    DEFINE A AS category = 'A'
    """
)

NO_MATCH_QUERY = _query(
    """
    ORDER BY seq_id
    MEASURES COUNT(*) AS match_length
    ONE ROW PER MATCH
    PATTERN (A+)
    DEFINE A AS category = '__NEVER_PRESENT__'
    """
)


def load_common(size: int, *, shuffled: bool = False) -> pd.DataFrame:
    df = matrix.load_input(size)
    if shuffled:
        # Data preparation is deliberately outside the measured query.
        df = df.sample(frac=1.0, random_state=20260715).reset_index(drop=True)
    return df


def anchor_input(size: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "seq_id": range(size),
            "price": [1.0] + [100.0] * (size - 2) + [40.0],
        }
    )


def anchor_query() -> str:
    return _query(
        """
        ORDER BY seq_id
        MEASURES
            FIRST(A.seq_id) AS start_row,
            LAST(B.seq_id) AS end_row,
            COUNT(*) AS match_length
        ONE ROW PER MATCH
        PATTERN (A+ B+ $)
        DEFINE B AS price > AVG(A.price)
        """
    )


def ambiguous_input(label_rows: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "seq_id": range(label_rows + 1),
            "value": [1] * label_rows + [0],
        }
    )


def ambiguous_query() -> str:
    return _query(
        """
        ORDER BY seq_id
        MEASURES
            COUNT(*) AS match_length,
            COUNT(A.value) AS a_count,
            COUNT(B.value) AS b_count
        ONE ROW PER MATCH
        PATTERN ((A | B)+ FINAL $)
        DEFINE FINAL AS value = 0 AND SUM(A.value) = SUM(B.value)
        """
    )


def digest_result(df: pd.DataFrame) -> str:
    normalized = matrix.normalize_result(df)
    row_hashes = pd.util.hash_pandas_object(normalized, index=False).values
    return hashlib.sha256(row_hashes.tobytes()).hexdigest()[:16]


def save(records: list[StressRecord], args: argparse.Namespace) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_stem = getattr(args, "output_stem", "engine_stress_results")
    csv_path = OUTPUT_DIR / f"{output_stem}.csv"
    json_path = OUTPUT_DIR / f"{output_stem}.json"
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "protocol": {
            "cpu_limit": args.cpus,
            "memory_limit_gb": args.memory_gb,
            "warmup_runs": args.warmup_runs,
            "measured_runs": args.measured_runs,
            "case_timeout_seconds": args.case_timeout_seconds,
            "timing_scope": "match_recognize call including result construction; excludes input loading/shuffling",
            "memory_metric": matrix.PANDAS_QUERY_MEMORY_METRIC,
        },
        "records": [asdict(record) for record in records],
    }
    json_path.write_text(json.dumps(payload, indent=2))
    pd.DataFrame([asdict(record) for record in records]).to_csv(csv_path, index=False)


def scale_boundary_input(size: int, *, dense_matches: bool) -> pd.DataFrame:
    """Build a deterministic narrow table for input-scale boundary tests.

    ``dense_matches=False`` creates one very long ``A+ B+`` match and isolates
    input/assignment scaling.  ``dense_matches=True`` repeats five A rows and
    five B rows, producing exactly ``size / 10`` matches and exposing
    per-match/output scaling.  Categorical labels avoid making Python string
    objects the dominant memory cost of the boundary test.
    """
    if size <= 0 or (dense_matches and size % 10):
        raise ValueError("boundary sizes must be positive and dense sizes divisible by 10")
    if dense_matches:
        codes = np.resize(
            np.asarray([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], dtype=np.int8),
            size,
        )
    else:
        codes = np.zeros(size, dtype=np.int8)
        codes[size // 2:] = 1
    return pd.DataFrame({
        "seq_id": np.arange(size, dtype=np.int64),
        "category": pd.Categorical.from_codes(codes, categories=["A", "B"]),
        "price": codes.astype(np.float64) + 1.0,
    })


def make_scale_boundary_cases() -> list[StressCase]:
    cases: list[StressCase] = []
    for size in (4_000_000, 8_000_000, 16_000_000):
        cases.append(StressCase(
            family="scale_boundary",
            name="single_long_state_dependent_match",
            size=size,
            input_order="ordered",
            expected_path="compiled exact linear backtracking; one long match",
            make_input=lambda size=size: scale_boundary_input(
                size, dense_matches=False
            ),
            query=STATE_DEPENDENT_QUERY,
            validate=lambda result, size=size: result.to_dict("records") == [{
                "start_row": 0,
                "end_row": size - 1,
                "match_length": size,
            }],
        ))
    for size in (4_000_000, 8_000_000):
        expected_matches = size // 10

        def validate_dense(result, size=size, expected_matches=expected_matches):
            if len(result) != expected_matches:
                return False
            first = result.iloc[0].to_dict()
            last = result.iloc[-1].to_dict()
            return (
                first == {"start_row": 0, "end_row": 9, "match_length": 10}
                and last == {
                    "start_row": size - 10,
                    "end_row": size - 1,
                    "match_length": 10,
                }
            )

        cases.append(StressCase(
            family="scale_boundary",
            name="dense_state_dependent_matches",
            size=size,
            input_order="ordered",
            expected_path="compiled exact linear backtracking; high match density",
            make_input=lambda size=size: scale_boundary_input(
                size, dense_matches=True
            ),
            query=STATE_DEPENDENT_QUERY,
            validate=validate_dense,
        ))
    return cases


def call_with_timeout(func, timeout_seconds: int):
    """Run a query with a hard wall-clock guard on POSIX systems."""
    if timeout_seconds <= 0 or not hasattr(signal, "SIGALRM"):
        return func()

    def handler(_signum, _frame):
        raise TimeoutError(f"query exceeded {timeout_seconds} seconds")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout_seconds)
    try:
        return func()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def run_case(case: StressCase, args: argparse.Namespace) -> StressRecord:
    print(f"[{case.family}] {case.name}: {case.size:,} rows", flush=True)
    df = case.make_input()
    measurements: list[tuple[pd.DataFrame, float, float, float]] = []
    try:
        for _ in range(args.warmup_runs):
            call_with_timeout(
                lambda: match_recognize(case.query, df),
                args.case_timeout_seconds,
            )
        for run in range(args.measured_runs):
            result, rss_delta, rss_peak, elapsed = matrix.run_with_process_memory_sampling(
                lambda: call_with_timeout(
                    lambda: match_recognize(case.query, df),
                    args.case_timeout_seconds,
                )
            )
            measurements.append((result, elapsed, rss_delta, rss_peak))
            print(
                f"  run {run + 1}/{args.measured_runs}: {elapsed:.6f}s, "
                f"rows={len(result):,}, RSS delta={rss_delta:.1f} MB",
                flush=True,
            )

        times = [item[1] for item in measurements]
        results = [item[0] for item in measurements]
        digests = [digest_result(result) for result in results]
        stable = len(set(digests)) == 1 and len({len(result) for result in results}) == 1
        correct = stable and all(case.validate(result) for result in results)
        mean_time = statistics.fmean(times)
        std_time = statistics.stdev(times) if len(times) > 1 else 0.0
        return StressRecord(
            family=case.family,
            case=case.name,
            input_rows=case.size,
            input_order=case.input_order,
            expected_engine_path=case.expected_path,
            success=True,
            correct=correct,
            mean_seconds=mean_time,
            std_seconds=std_time,
            min_seconds=min(times),
            max_seconds=max(times),
            throughput_rows_per_second=case.size / mean_time,
            mean_query_rss_delta_mb=statistics.fmean(item[2] for item in measurements),
            mean_process_peak_rss_mb=statistics.fmean(item[3] for item in measurements),
            result_rows=len(results[0]),
            result_digest=digests[0],
            warmup_runs=args.warmup_runs,
            measured_runs=args.measured_runs,
        )
    except Exception as exc:
        return StressRecord(
            family=case.family,
            case=case.name,
            input_rows=case.size,
            input_order=case.input_order,
            expected_engine_path=case.expected_path,
            success=False,
            correct=False,
            mean_seconds=None,
            std_seconds=None,
            min_seconds=None,
            max_seconds=None,
            throughput_rows_per_second=None,
            mean_query_rss_delta_mb=None,
            mean_process_peak_rss_mb=None,
            result_rows=None,
            result_digest=None,
            warmup_runs=args.warmup_runs,
            measured_runs=args.measured_runs,
            error=f"{type(exc).__name__}: {exc}",
        )


def make_cases() -> list[StressCase]:
    cases: list[StressCase] = []

    # Isolate the cost of ORDER BY with the same query and rows.
    for size in (100_000, 400_000, 800_000, 2_222_742):
        for shuffled in (False, True):
            order = "shuffled" if shuffled else "ordered"
            cases.append(
                StressCase(
                    family="ordering",
                    name=f"simple_sequence_{order}",
                    size=size,
                    input_order=order,
                    expected_path="row-local vector/DFA plus ordering",
                    make_input=lambda size=size, shuffled=shuffled: load_common(size, shuffled=shuffled),
                    query=SIMPLE_QUERY,
                    validate=lambda result: not result.empty,
                )
            )

    # Exact state-dependent path, including a multi-million-row run.
    for size in (100_000, 200_000, 400_000, 800_000, 1_600_000, 2_222_742):
        cases.append(
            StressCase(
                family="state_dependent",
                name="running_avg_define",
                size=size,
                input_order="ordered",
                expected_path="compiled exact linear backtracking",
                make_input=lambda size=size: load_common(size),
                query=STATE_DEPENDENT_QUERY,
                validate=lambda result: not result.empty,
            )
        )

    # Scalar navigation cannot use the purely row-local vectorized predicate.
    for size in (100_000, 400_000, 800_000):
        cases.append(
            StressCase(
                family="navigation",
                name="prev_price_define",
                size=size,
                input_order="ordered",
                expected_path="scalar navigation fallback",
                make_input=lambda size=size: load_common(size),
                query=NAVIGATION_QUERY,
                validate=lambda result: isinstance(result, pd.DataFrame),
            )
        )

    # Large rollback distance with a terminal partition anchor.
    for size in (1_000, 10_000, 100_000, 500_000):
        cases.append(
            StressCase(
                family="terminal_anchor",
                name="aggregate_rollback_to_end_anchor",
                size=size,
                input_order="ordered",
                expected_path="compiled exact linear backtracking with terminal bound",
                make_input=lambda size=size: anchor_input(size),
                query=anchor_query(),
                validate=lambda result, size=size: result.to_dict("records") == [
                    {"start_row": 0, "end_row": size - 1, "match_length": size}
                ],
            )
        )

    # True nonlinear ambiguity.  Growth here is in pattern choices, not rows.
    for label_rows in (8, 12, 16, 20, 24):
        cases.append(
            StressCase(
                family="nonlinear_ambiguity",
                name="balanced_alternate_labels",
                size=label_rows + 1,
                input_order="ordered",
                expected_path="generic iterative DFS with rollback-safe aggregates",
                make_input=lambda label_rows=label_rows: ambiguous_input(label_rows),
                query=ambiguous_query(),
                validate=lambda result, label_rows=label_rows: result.to_dict("records") == [
                    {
                        "match_length": label_rows + 1,
                        "a_count": label_rows // 2,
                        "b_count": label_rows // 2,
                    }
                ],
            )
        )

    # Additional production pressures at a useful but bounded size.
    cases.extend(
        [
            StressCase(
                family="partitioning",
                name="many_partitions_simple_sequence",
                size=800_000,
                input_order="ordered",
                expected_path="partition preparation plus row-local matching",
                make_input=lambda: load_common(800_000),
                query=PARTITION_QUERY,
                validate=lambda result: isinstance(result, pd.DataFrame),
            ),
            StressCase(
                family="rejection_scan",
                name="no_rows_satisfy_start",
                size=2_222_742,
                input_order="ordered",
                expected_path="vectorized start-candidate rejection",
                make_input=lambda: load_common(2_222_742),
                query=NO_MATCH_QUERY,
                validate=lambda result: result.empty,
            ),
        ]
    )
    # Output construction has a different scaling envelope from ONE ROW
    # matching.  Keep both the historical 800K point and the full common
    # 2.22M dataset so result-volume regressions cannot hide behind the
    # ordinary low-output matrix.
    for size in (800_000, 2_222_742):
        cases.append(
            StressCase(
                family="output_pressure",
                name="all_rows_per_match",
                size=size,
                input_order="ordered",
                expected_path=(
                    "row-local matching plus compiled columnar ALL ROWS output"
                ),
                make_input=lambda size=size: load_common(size),
                query=ALL_ROWS_QUERY,
                validate=lambda result: not result.empty,
            )
        )
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--memory-gb", type=int, default=32)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--measured-runs", type=int, default=3)
    parser.add_argument(
        "--case-timeout-seconds",
        type=int,
        default=30,
        help="Hard timeout for each warmup or measured query; 0 disables it",
    )
    parser.add_argument(
        "--families",
        nargs="+",
        help="Optional subset of stress families to run",
    )
    parser.add_argument(
        "--extended-scale",
        action="store_true",
        help="Add deterministic 4M--16M proposed-engine boundary cases",
    )
    parser.add_argument(
        "--output-stem",
        default="engine_stress_results",
        help="Output filename stem inside Performance/engine_stress",
    )
    args = parser.parse_args()
    if args.measured_runs < 1 or args.warmup_runs < 0:
        parser.error("measured-runs must be >= 1 and warmup-runs must be >= 0")

    matrix.apply_local_limits(args.cpus, args.memory_gb)
    cases = make_cases()
    if args.extended_scale:
        cases.extend(make_scale_boundary_cases())
    if args.families:
        selected = set(args.families)
        cases = [case for case in cases if case.family in selected]
        available_families = {case.family for case in make_cases()}
        if args.extended_scale:
            available_families.update(
                case.family for case in make_scale_boundary_cases()
            )
        unknown = selected - available_families
        if unknown:
            parser.error(f"unknown stress families: {sorted(unknown)}")

    records: list[StressRecord] = []
    for case in cases:
        record = run_case(case, args)
        records.append(record)
        save(records, args)
        if not record.success:
            print(f"  FAILED: {record.error}", flush=True)
        elif not record.correct:
            print("  FAILED CORRECTNESS VALIDATION", flush=True)

    succeeded = sum(record.success for record in records)
    correct = sum(record.correct for record in records)
    print(
        f"Saved {len(records)} cases to "
        f"{OUTPUT_DIR / (args.output_stem + '.csv')} "
        f"({succeeded} executed, {correct} correct)",
        flush=True,
    )


if __name__ == "__main__":
    main()
