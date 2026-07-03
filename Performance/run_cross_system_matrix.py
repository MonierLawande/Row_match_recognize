#!/usr/bin/env python3
"""
Sequential equal-resource cross-system benchmark matrix.

Systems:
- proposed pandas MATCH_RECOGNIZE engine
- Trino 473
- Oracle XE 21c

Benchmark matrix:
- sizes: 50K, 100K, 200K, 400K, 800K, 1M, 1.5M, 2M
- patterns: simple_sequence, alternation, quantified, optional_pattern,
  complex_nested

Fairness policy:
- same input rows for each size
- same derived category column
- same SQL pattern logic
- one system runs at a time
- database containers are limited to the same CPU/memory budget
- pandas is run in the same Python process with CPU affinity and memory limit

This script is intentionally simple and thesis-friendly.  It measures query
execution time only.  Loading data into Trino/Oracle is done before timing the
queries and is not included in the measured query times.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import resource
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PERFORMANCE_DIR = PROJECT_ROOT / "Performance"
SOURCE_DATASET = PERFORMANCE_DIR / "amz_uk_processed_data.csv"
OUTPUT_DIR = PERFORMANCE_DIR / "cross_system_matrix"
DATASET_DIR = OUTPUT_DIR / "datasets"
SQL_DIR = OUTPUT_DIR / "sql"

TABLE_NAME = "benchmark_matrix"
LOAD_COLUMNS = ["seq_id", "category", "stars", "price", "reviews", "category_name"]

DEFAULT_SIZES = [
    50_000,
    100_000,
    200_000,
    400_000,
    800_000,
    1_000_000,
    1_500_000,
    2_000_000,
]

sys.path.insert(0, str(PROJECT_ROOT))


PATTERNS: dict[str, dict[str, str]] = {
    "simple_sequence": {
        "pattern": "A+ B+",
        "description": "A followed by B",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row,
                COUNT(*) AS match_length,
                COUNT(A.seq_id) AS a_count,
                COUNT(B.seq_id) AS b_count
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B'
        """,
    },
    "alternation": {
        "pattern": "A (B|C)+ D",
        "description": "A followed by one or more B/C rows, then D",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(D.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A (B|C)+ D)
            DEFINE
                A AS category = 'A',
                B AS category = 'B',
                C AS category = 'C',
                D AS category = 'D'
        """,
    },
    "quantified": {
        "pattern": "A{1,5} B* C+",
        "description": "1--5 A rows, optional B rows, then one or more C rows",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(C.seq_id) AS end_row,
                COUNT(*) AS match_length,
                COUNT(A.seq_id) AS a_count,
                COUNT(B.seq_id) AS b_count,
                COUNT(C.seq_id) AS c_count
            ONE ROW PER MATCH
            PATTERN (A{1,5} B* C+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B',
                C AS category = 'C'
        """,
    },
    "optional_pattern": {
        "pattern": "A+ B? C*",
        "description": "A rows, optional B row, optional C rows",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A+ B? C*)
            DEFINE
                A AS category = 'A',
                B AS category = 'B',
                C AS category = 'C'
        """,
    },
    "complex_nested": {
        "pattern": "(A|B)+ (C{1,3} D*)+",
        "description": "nested alternation and bounded repetition",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN ((A|B)+ (C{1,3} D*)+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B',
                C AS category = 'C',
                D AS category = 'D'
        """,
    },
}


@dataclass
class RunResult:
    system: str
    dataset_size: int
    pattern_name: str
    pattern: str
    success: bool
    correctness_matches_pandas: bool | str | None
    execution_time_seconds: float | None
    throughput_rows_per_second: float | None
    memory_mb: float | None
    memory_metric: str
    result_rows: int | None
    error: str | None = None


def apply_local_limits(cpu_count: int, memory_gb: int) -> None:
    """Apply CPU affinity and virtual memory limit to this Python process."""
    try:
        os.sched_setaffinity(0, set(range(cpu_count)))
    except Exception:
        pass

    memory_bytes = memory_gb * 1024 * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except Exception:
        pass

    for var in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
        os.environ[var] = str(cpu_count)


def run_command(command: list[str], check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, check=check, timeout=timeout)


def docker_available() -> bool:
    return shutil.which("docker") is not None


def docker_stop(*containers: str) -> None:
    if not docker_available():
        return
    existing = [name for name in containers if name]
    if existing:
        run_command(["docker", "stop", *existing], check=False)


def docker_start(container: str) -> None:
    run_command(["docker", "start", container], check=True)


def docker_update(container: str, cpu_count: int, memory_gb: int) -> None:
    memory = f"{memory_gb}g"
    run_command(
        [
            "docker",
            "update",
            f"--cpus={cpu_count}",
            f"--memory={memory}",
            f"--memory-swap={memory}",
            container,
        ],
        check=True,
    )


def parse_memory_to_mb(value: str) -> float | None:
    first = value.split("/")[0].strip()
    units = [
        ("TiB", 1024 * 1024),
        ("GiB", 1024),
        ("MiB", 1),
        ("KiB", 1 / 1024),
        ("GB", 1000),
        ("MB", 1),
        ("kB", 1 / 1000),
        ("B", 1 / 1024 / 1024),
    ]
    for unit, factor in units:
        if first.endswith(unit):
            try:
                return float(first[: -len(unit)].strip()) * factor
            except ValueError:
                return None
    return None


def docker_memory_mb(container_name: str) -> float | None:
    completed = run_command(
        ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container_name],
        check=False,
        timeout=5,
    )
    if completed.returncode != 0:
        return None
    return parse_memory_to_mb(completed.stdout.strip())


def run_with_container_memory_sampling(container_name: str, func) -> tuple[Any, float | None]:
    samples: list[float] = []
    stop_event = threading.Event()

    def sampler() -> None:
        while not stop_event.is_set():
            value = docker_memory_mb(container_name)
            if value is not None:
                samples.append(value)
            time.sleep(0.25)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    try:
        result = func()
    finally:
        stop_event.set()
        thread.join(timeout=2)
    return result, max(samples) if samples else None


def get_rss_mb() -> float:
    try:
        import psutil

        return psutil.Process().memory_info().rss / 1024 / 1024
    except Exception:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return usage / 1024


def run_with_process_memory_sampling(func) -> tuple[Any, float]:
    start_mb = get_rss_mb()
    samples: list[float] = []
    stop_event = threading.Event()

    def sampler() -> None:
        while not stop_event.is_set():
            samples.append(get_rss_mb())
            time.sleep(0.02)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    try:
        result = func()
    finally:
        stop_event.set()
        thread.join(timeout=1)

    peak_mb = max(samples + [get_rss_mb()])
    # RSS sampling can show tiny negative deltas when the Python runtime frees
    # memory during the measured query.  Report those artifacts as zero rather
    # than as negative memory usage.
    return result, max(0.0, peak_mb - start_mb)


def make_price_category(price: pd.Series) -> pd.Series:
    clean_price = pd.to_numeric(price, errors="coerce").fillna(0)
    return pd.cut(
        clean_price,
        bins=[-float("inf"), 10, 25, 50, 100, float("inf")],
        labels=["A", "B", "C", "D", "E"],
    ).astype(str)


def dataset_path(size: int) -> Path:
    return DATASET_DIR / f"benchmark_{size}.csv"


def create_shared_dataset(size: int) -> Path:
    """Create one prepared CSV dataset that all systems use for this size."""
    path = dataset_path(size)
    if path.exists():
        return path

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(
        SOURCE_DATASET,
        nrows=size,
        usecols=["stars", "reviews", "price", "categoryName"],
    )
    prepared = pd.DataFrame(
        {
            "seq_id": range(len(df)),
            "category": make_price_category(df["price"]),
            "stars": pd.to_numeric(df["stars"], errors="coerce").fillna(0),
            "price": pd.to_numeric(df["price"], errors="coerce").fillna(0),
            "reviews": pd.to_numeric(df["reviews"], errors="coerce").fillna(0).astype("int64"),
            "category_name": df["categoryName"].fillna("").astype(str),
        }
    )
    prepared.to_csv(path, index=False)
    return path


def create_shared_datasets(sizes: list[int]) -> None:
    print("\n=== Preparing shared CSV datasets ===")
    for size in sizes:
        path = create_shared_dataset(size)
        print(f"  {size:,} rows -> {path}")


def load_input(size: int) -> pd.DataFrame:
    path = create_shared_dataset(size)
    return pd.read_csv(path)


def batched_rows(df: pd.DataFrame, size: int) -> Iterable[list[tuple[Any, ...]]]:
    for start in range(0, len(df), size):
        chunk = df.iloc[start : start + size]
        rows: list[tuple[Any, ...]] = []
        for row in chunk.itertuples(index=False):
            values: list[Any] = []
            for value in row:
                if isinstance(value, float) and math.isnan(value):
                    values.append(None)
                else:
                    values.append(value)
            rows.append(tuple(values))
        yield rows


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def query_for_system(system: str, pattern_name: str) -> str:
    source = "data" if system == "pandas" else TABLE_NAME
    body = PATTERNS[pattern_name]["body"]
    return f"SELECT *\nFROM {source}\nMATCH_RECOGNIZE (\n{body}\n)"


def save_sql_queries() -> None:
    """Save the exact benchmark SQL used for each system and pattern."""
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    for pattern_name in PATTERNS:
        common_body = PATTERNS[pattern_name]["body"]
        (SQL_DIR / f"common_{pattern_name}.sql").write_text(
            "MATCH_RECOGNIZE (\n" + common_body + "\n)\n"
        )
        for system in ["pandas", "trino", "oracle"]:
            (SQL_DIR / f"{system}_{pattern_name}.sql").write_text(
                query_for_system(system, pattern_name) + "\n"
            )


def normalize_result(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(col).lower() for col in normalized.columns]
    for col in normalized.columns:
        numeric = pd.to_numeric(normalized[col], errors="coerce")
        if not numeric.isna().any():
            normalized[col] = numeric.astype("int64")
    sort_cols = list(normalized.columns)
    if sort_cols:
        normalized = normalized.sort_values(sort_cols).reset_index(drop=True)
    return normalized


def wait_for_trino(timeout_seconds: int) -> None:
    import trino

    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            conn = trino.dbapi.connect(
                host="localhost",
                port=8080,
                user="benchmark",
                catalog="memory",
                schema="default",
            )
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchall()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(3)
    raise RuntimeError(f"Trino is not ready: {last_error}")


def connect_trino():
    import trino

    return trino.dbapi.connect(
        host="localhost",
        port=8080,
        user="benchmark",
        catalog="memory",
        schema="default",
    )


def load_trino_table(df: pd.DataFrame, chunk_size: int) -> None:
    conn = connect_trino()
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    cur.execute(
        f"""
        CREATE TABLE {TABLE_NAME} (
            seq_id INTEGER,
            category VARCHAR,
            stars DOUBLE,
            price DOUBLE,
            reviews BIGINT,
            category_name VARCHAR
        )
        """
    )
    inserted = 0
    for rows in batched_rows(df, chunk_size):
        values_sql = ", ".join(
            "(" + ", ".join(sql_literal(value) for value in row) + ")" for row in rows
        )
        cur.execute(f"INSERT INTO {TABLE_NAME} ({', '.join(LOAD_COLUMNS)}) VALUES {values_sql}")
        inserted += len(rows)
        print(f"    Trino load: {inserted:,}/{len(df):,}", end="\r")
    print()


def wait_for_oracle(password: str, dsn: str, timeout_seconds: int) -> None:
    import oracledb

    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            conn = oracledb.connect(user="system", password=password, dsn=dsn)
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM dual")
            cur.fetchall()
            conn.close()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(5)
    raise RuntimeError(f"Oracle is not ready: {last_error}")


def connect_oracle(password: str, dsn: str):
    import oracledb

    return oracledb.connect(user="system", password=password, dsn=dsn)


def load_oracle_table(df: pd.DataFrame, password: str, dsn: str, chunk_size: int) -> None:
    conn = connect_oracle(password, dsn)
    cur = conn.cursor()
    try:
        cur.execute(f"DROP TABLE {TABLE_NAME} PURGE")
    except Exception:
        pass
    cur.execute(
        f"""
        CREATE TABLE {TABLE_NAME} (
            seq_id NUMBER,
            category VARCHAR2(1),
            stars NUMBER,
            price NUMBER,
            reviews NUMBER,
            category_name VARCHAR2(4000)
        )
        """
    )
    insert_sql = f"""
        INSERT INTO {TABLE_NAME}
        (seq_id, category, stars, price, reviews, category_name)
        VALUES (:1, :2, :3, :4, :5, :6)
    """
    inserted = 0
    for rows in batched_rows(df, chunk_size):
        cur.executemany(insert_sql, rows)
        conn.commit()
        inserted += len(rows)
        print(f"    Oracle load: {inserted:,}/{len(df):,}", end="\r")
    print()


def fetch_dataframe(cursor, query: str) -> pd.DataFrame:
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [desc[0].lower() for desc in cursor.description]
    return pd.DataFrame(rows, columns=columns)


def run_pandas_pattern(df: pd.DataFrame, pattern_name: str, warmup_runs: int) -> tuple[pd.DataFrame, float, float]:
    from src.executor.match_recognize import match_recognize

    query = query_for_system("pandas", pattern_name)
    for _ in range(warmup_runs):
        match_recognize(query, df)
    start = time.perf_counter()
    result, memory_delta = run_with_process_memory_sampling(lambda: match_recognize(query, df))
    elapsed = time.perf_counter() - start
    return result, elapsed, memory_delta


def run_db_pattern(
    system: str,
    cursor,
    pattern_name: str,
    warmup_runs: int,
    container_name: str,
) -> tuple[pd.DataFrame, float, float | None]:
    query = query_for_system(system, pattern_name)
    for _ in range(warmup_runs):
        fetch_dataframe(cursor, query)
    start = time.perf_counter()
    result, peak_memory = run_with_container_memory_sampling(
        container_name,
        lambda: fetch_dataframe(cursor, query),
    )
    elapsed = time.perf_counter() - start
    return result, elapsed, peak_memory


def save_result_csv(system: str, size: int, pattern_name: str, df: pd.DataFrame) -> Path:
    path = OUTPUT_DIR / "results" / f"{system}_{size}_{pattern_name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    normalize_result(df).to_csv(path, index=False)
    return path


def system_file_prefix(system_label: str) -> str:
    if system_label == "proposed_pandas_engine":
        return "pandas"
    if system_label == "trino_473":
        return "trino"
    if system_label == "oracle_xe_21c":
        return "oracle"
    return system_label


def write_system_results(system_label: str, results: list[RunResult]) -> None:
    """Write one external timing/memory result file per system.

    This is called after each completed pattern, so long benchmark runs keep
    useful checkpoint files even if a later system or larger size fails.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = system_file_prefix(system_label)
    records = [result.__dict__ for result in results]
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "system": system_label,
        "records": records,
    }
    (OUTPUT_DIR / f"{prefix}_results.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )
    pd.DataFrame(records).to_csv(OUTPUT_DIR / f"{prefix}_results.csv", index=False)


def run_pandas_system(sizes: list[int], warmup_runs: int) -> tuple[list[RunResult], dict[tuple[int, str], pd.DataFrame]]:
    print("\n=== Running pandas system ===")
    docker_stop("trino-473", "oracle-free")
    all_results: list[RunResult] = []
    expected: dict[tuple[int, str], pd.DataFrame] = {}

    for size in sizes:
        df = load_input(size)
        print(f"  pandas size={size:,}")
        for pattern_name, info in PATTERNS.items():
            print(f"    pattern={pattern_name}")
            try:
                result_df, elapsed, memory_delta = run_pandas_pattern(df, pattern_name, warmup_runs)
                normalized = normalize_result(result_df)
                expected[(size, pattern_name)] = normalized
                save_result_csv("pandas", size, pattern_name, normalized)
                all_results.append(
                    RunResult(
                        system="proposed_pandas_engine",
                        dataset_size=size,
                        pattern_name=pattern_name,
                        pattern=info["pattern"],
                        success=True,
                        correctness_matches_pandas="baseline",
                        execution_time_seconds=elapsed,
                        throughput_rows_per_second=size / elapsed,
                        memory_mb=memory_delta,
                        memory_metric="process RSS peak delta MB",
                        result_rows=len(result_df),
                    )
                )
                write_system_results("proposed_pandas_engine", all_results)
            except Exception as exc:
                all_results.append(
                    RunResult(
                        system="proposed_pandas_engine",
                        dataset_size=size,
                        pattern_name=pattern_name,
                        pattern=info["pattern"],
                        success=False,
                        correctness_matches_pandas="baseline",
                        execution_time_seconds=None,
                        throughput_rows_per_second=None,
                        memory_mb=None,
                        memory_metric="process RSS peak delta MB",
                        result_rows=None,
                        error=str(exc),
                    )
                )
                write_system_results("proposed_pandas_engine", all_results)
    return all_results, expected


def run_trino_system(
    sizes: list[int],
    expected: dict[tuple[int, str], pd.DataFrame],
    warmup_runs: int,
    chunk_size: int,
    cpu_count: int,
    memory_gb: int,
) -> list[RunResult]:
    print("\n=== Running Trino system ===")
    docker_stop("oracle-free")
    docker_update("trino-473", cpu_count, memory_gb)
    docker_start("trino-473")
    wait_for_trino(900)

    conn = connect_trino()
    cur = conn.cursor()
    all_results: list[RunResult] = []

    for size in sizes:
        df = load_input(size)
        print(f"  Trino size={size:,}")
        load_trino_table(df, chunk_size)
        for pattern_name, info in PATTERNS.items():
            print(f"    pattern={pattern_name}")
            try:
                result_df, elapsed, peak_memory = run_db_pattern(
                    "trino", cur, pattern_name, warmup_runs, "trino-473"
                )
                normalized = normalize_result(result_df)
                save_result_csv("trino", size, pattern_name, normalized)
                correct = normalized.equals(expected.get((size, pattern_name), pd.DataFrame()))
                all_results.append(
                    RunResult(
                        system="trino_473",
                        dataset_size=size,
                        pattern_name=pattern_name,
                        pattern=info["pattern"],
                        success=True,
                        correctness_matches_pandas=correct,
                        execution_time_seconds=elapsed,
                        throughput_rows_per_second=size / elapsed,
                        memory_mb=peak_memory,
                        memory_metric="Docker container peak memory MB",
                        result_rows=len(result_df),
                    )
                )
                write_system_results("trino_473", all_results)
            except Exception as exc:
                all_results.append(
                    RunResult(
                        system="trino_473",
                        dataset_size=size,
                        pattern_name=pattern_name,
                        pattern=info["pattern"],
                        success=False,
                        correctness_matches_pandas=False,
                        execution_time_seconds=None,
                        throughput_rows_per_second=None,
                        memory_mb=None,
                        memory_metric="Docker container peak memory MB",
                        result_rows=None,
                        error=str(exc),
                    )
                )
                write_system_results("trino_473", all_results)
    docker_stop("trino-473")
    return all_results


def run_oracle_system(
    sizes: list[int],
    expected: dict[tuple[int, str], pd.DataFrame],
    warmup_runs: int,
    chunk_size: int,
    cpu_count: int,
    memory_gb: int,
    password: str,
    dsn: str,
) -> list[RunResult]:
    print("\n=== Running Oracle system ===")
    docker_stop("trino-473")
    docker_update("oracle-free", cpu_count, memory_gb)
    docker_start("oracle-free")
    wait_for_oracle(password, dsn, 900)

    conn = connect_oracle(password, dsn)
    cur = conn.cursor()
    all_results: list[RunResult] = []

    for size in sizes:
        df = load_input(size)
        print(f"  Oracle size={size:,}")
        load_oracle_table(df, password, dsn, chunk_size)
        for pattern_name, info in PATTERNS.items():
            print(f"    pattern={pattern_name}")
            try:
                result_df, elapsed, peak_memory = run_db_pattern(
                    "oracle", cur, pattern_name, warmup_runs, "oracle-free"
                )
                normalized = normalize_result(result_df)
                save_result_csv("oracle", size, pattern_name, normalized)
                correct = normalized.equals(expected.get((size, pattern_name), pd.DataFrame()))
                all_results.append(
                    RunResult(
                        system="oracle_xe_21c",
                        dataset_size=size,
                        pattern_name=pattern_name,
                        pattern=info["pattern"],
                        success=True,
                        correctness_matches_pandas=correct,
                        execution_time_seconds=elapsed,
                        throughput_rows_per_second=size / elapsed,
                        memory_mb=peak_memory,
                        memory_metric="Docker container peak memory MB",
                        result_rows=len(result_df),
                    )
                )
                write_system_results("oracle_xe_21c", all_results)
            except Exception as exc:
                all_results.append(
                    RunResult(
                        system="oracle_xe_21c",
                        dataset_size=size,
                        pattern_name=pattern_name,
                        pattern=info["pattern"],
                        success=False,
                        correctness_matches_pandas=False,
                        execution_time_seconds=None,
                        throughput_rows_per_second=None,
                        memory_mb=None,
                        memory_metric="Docker container peak memory MB",
                        result_rows=None,
                        error=str(exc),
                    )
                )
                write_system_results("oracle_xe_21c", all_results)
    docker_stop("oracle-free")
    return all_results


def write_summary(results: list[RunResult], args: argparse.Namespace) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records = [result.__dict__ for result in results]
    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "resource_policy": {
            "cpu_per_system": args.cpus,
            "memory_gb_per_system": args.memory_gb,
            "execution_mode": "sequential; one system at a time",
            "warmup_runs": args.warmup_runs,
            "measured_runs": 1,
            "database_load_chunk_size": args.chunk_size,
            "sizes": args.sizes,
            "patterns": list(PATTERNS.keys()),
            "shared_dataset_directory": str(DATASET_DIR),
            "sql_directory": str(SQL_DIR),
        },
        "records": records,
    }
    summary_stem = f"matrix_{args.cpus}cpu_{args.memory_gb}gb"
    (OUTPUT_DIR / f"{summary_stem}_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    pd.DataFrame(records).to_csv(OUTPUT_DIR / f"{summary_stem}_summary.csv", index=False)

    for system in sorted({result.system for result in results}):
        write_system_results(system, [result for result in results if result.system == system])

    successful = [r for r in results if r.success]
    aggregate_rows = []
    for system in sorted({r.system for r in successful}):
        group = [r for r in successful if r.system == system]
        aggregate_rows.append(
            {
                "system": system,
                "successful_tests": len(group),
                "avg_time_seconds": sum(r.execution_time_seconds for r in group if r.execution_time_seconds) / len(group),
                "avg_throughput_rows_per_second": sum(r.throughput_rows_per_second for r in group if r.throughput_rows_per_second) / len(group),
                "max_memory_mb": max(r.memory_mb for r in group if r.memory_mb is not None),
                "all_correct": all(r.correctness_matches_pandas in (True, "baseline") for r in group),
            }
        )
    pd.DataFrame(aggregate_rows).to_csv(OUTPUT_DIR / f"{summary_stem}_aggregate.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full cross-system benchmark matrix.")
    parser.add_argument("--systems", nargs="+", choices=["pandas", "trino", "oracle"], default=["pandas", "trino", "oracle"])
    parser.add_argument("--sizes", nargs="+", type=int, default=DEFAULT_SIZES)
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--memory-gb", type=int, default=32)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--chunk-size", type=int, default=20000)
    parser.add_argument("--oracle-password", default="Oracle_12345")
    parser.add_argument("--oracle-dsn", default="localhost:1521/XEPDB1")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    apply_local_limits(args.cpus, args.memory_gb)
    create_shared_datasets(args.sizes)
    save_sql_queries()

    all_results: list[RunResult] = []
    expected: dict[tuple[int, str], pd.DataFrame] = {}

    if "pandas" in args.systems:
        pandas_results, expected = run_pandas_system(args.sizes, args.warmup_runs)
        all_results.extend(pandas_results)
    else:
        for size in args.sizes:
            for pattern_name in PATTERNS:
                path = OUTPUT_DIR / "results" / f"pandas_{size}_{pattern_name}.csv"
                if path.exists():
                    expected[(size, pattern_name)] = normalize_result(pd.read_csv(path))

    if "trino" in args.systems:
        all_results.extend(
            run_trino_system(
                args.sizes,
                expected,
                args.warmup_runs,
                args.chunk_size,
                args.cpus,
                args.memory_gb,
            )
        )

    if "oracle" in args.systems:
        all_results.extend(
            run_oracle_system(
                args.sizes,
                expected,
                args.warmup_runs,
                args.chunk_size,
                args.cpus,
                args.memory_gb,
                args.oracle_password,
                args.oracle_dsn,
            )
        )

    write_summary(all_results, args)

    print("\nSaved:")
    summary_stem = f"matrix_{args.cpus}cpu_{args.memory_gb}gb"
    print(f"  {OUTPUT_DIR / f'{summary_stem}_summary.json'}")
    print(f"  {OUTPUT_DIR / f'{summary_stem}_summary.csv'}")
    print(f"  {OUTPUT_DIR / f'{summary_stem}_aggregate.csv'}")
    print(f"  {OUTPUT_DIR / 'pandas_results.csv'}")
    print(f"  {OUTPUT_DIR / 'trino_results.csv'}")
    print(f"  {OUTPUT_DIR / 'oracle_results.csv'}")
    print(f"  {DATASET_DIR}")
    print(f"  {SQL_DIR}")


if __name__ == "__main__":
    main()
