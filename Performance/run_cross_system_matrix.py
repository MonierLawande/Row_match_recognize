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

# Unified memory methodology: every system is measured with the same
# instrument (cgroup v2 memory.current, 50 ms sampling) and the same
# per-run protocol (5 s pre-query baseline mean -> absolute peak during the
# query -> incremental peak = absolute - baseline), aggregated as the
# IQR-filtered mean +/- std over the measured runs.  The engine runs in a
# dedicated transient systemd user scope so its cgroup is its own.
UNIFIED_QUERY_MEMORY_METRIC = (
    "cgroup v2 memory.current incremental peak MB over 5s pre-query baseline "
    "(50ms sampling, IQR-filtered mean)")
UNIFIED_FOOTPRINT_MEMORY_METRIC = (
    "cgroup v2 memory.current absolute peak MB during query "
    "(50ms sampling, IQR-filtered mean)")
PANDAS_QUERY_MEMORY_METRIC = UNIFIED_QUERY_MEMORY_METRIC
PANDAS_FOOTPRINT_MEMORY_METRIC = UNIFIED_FOOTPRINT_MEMORY_METRIC
TRINO_QUERY_MEMORY_METRIC = UNIFIED_QUERY_MEMORY_METRIC
ORACLE_QUERY_MEMORY_METRIC = UNIFIED_QUERY_MEMORY_METRIC
DB_FOOTPRINT_MEMORY_METRIC = UNIFIED_FOOTPRINT_MEMORY_METRIC

# Memory sampling parameters of the unified methodology.
SAMPLE_INTERVAL_S = 0.05
BASELINE_SECONDS = 5.0

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
    # Mean over the measured runs; std and min/max show run-to-run spread.
    execution_time_seconds: float | None
    execution_time_std_seconds: float | None
    execution_time_min_seconds: float | None
    execution_time_max_seconds: float | None
    measured_runs: int
    throughput_rows_per_second: float | None
    # Comparable across systems: peak additional memory attributable to
    # executing the measured query, excluding stored data and idle engine.
    query_memory_mb: float | None
    query_memory_metric: str
    # Not comparable per-query: what it costs to have the system running
    # (whole Python process for pandas, whole container for Trino/Oracle).
    footprint_memory_mb: float | None
    footprint_memory_metric: str
    result_rows: int | None
    error: str | None = None
    # Unified-methodology extras (IQR-filtered mean +/- std over measured
    # runs; query_memory_mb above holds the incremental-peak mean and
    # footprint_memory_mb the absolute-peak mean).
    throughput_std_rows_per_second: float | None = None
    baseline_memory_mb: float | None = None
    abs_peak_memory_std_mb: float | None = None
    inc_peak_memory_std_mb: float | None = None
    mem_per_million_rows_mb: float | None = None
    # The system's own per-query counter, kept for reference (Trino
    # peakMemoryBytes / Oracle session PGA delta; None for the engine).
    native_query_memory_mb: float | None = None
    outliers_excluded_time: int | None = None
    outliers_excluded_throughput: int | None = None
    outliers_excluded_abs_peak: int | None = None
    outliers_excluded_inc_peak: int | None = None


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
    # Pin the container to the same physical cores the pandas engine is
    # pinned to (sched_setaffinity uses cores 0..cpu_count-1), in addition to
    # the CPU quota, so both mechanisms restrict to identical cores.
    memory = f"{memory_gb}g"
    cpuset = ",".join(str(core) for core in range(cpu_count))
    run_command(
        [
            "docker",
            "update",
            f"--cpus={cpu_count}",
            f"--cpuset-cpus={cpuset}",
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


def run_with_container_memory_sampling(container_name: str, func) -> tuple[Any, float | None, float]:
    """Run func while sampling container memory in a background thread.

    Returns (result, peak_memory_mb, elapsed_seconds).  Elapsed time is
    measured tightly around func itself: a single `docker stats` call takes
    on the order of seconds, so including sampler-thread startup/shutdown in
    the timed region would quantize every measurement to the sampler cycle
    length instead of reporting the real query time.
    """
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
        start = time.perf_counter()
        result = func()
        elapsed = time.perf_counter() - start
    finally:
        stop_event.set()
        thread.join(timeout=10)
    return result, max(samples) if samples else None, elapsed


def get_rss_mb() -> float:
    try:
        import psutil

        return psutil.Process().memory_info().rss / 1024 / 1024
    except Exception:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return usage / 1024


def clean_process_memory() -> None:
    """Release freed-but-pooled memory back to the OS before a measurement.

    Python's small-object allocator and glibc keep freed memory in internal
    pools instead of returning it, so a plain RSS peak-delta on a long-lived
    process reads near zero whenever a query's working set fits in already
    resident pages (the source of the spurious 0.00 readings).  Forcing a
    garbage collection and a glibc ``malloc_trim`` gives each measured query a
    clean baseline, so the RSS delta reflects the memory that query actually
    allocates.
    """
    import gc

    gc.collect()
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def run_with_process_memory_sampling(func) -> tuple[Any, float, float, float]:
    """Run func while sampling process RSS in a background thread.

    Returns (result, RSS peak delta MB, RSS absolute peak MB, elapsed
    seconds).  Memory is cleaned to the OS before the baseline is taken
    (clean_process_memory) so the delta is the query's real allocation rather
    than an artifact of allocator pooling.  As with container sampling, elapsed
    time is measured tightly around func so sampler startup/shutdown does not
    inflate small measurements.
    """
    clean_process_memory()
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
        start = time.perf_counter()
        result = func()
        elapsed = time.perf_counter() - start
    finally:
        stop_event.set()
        thread.join(timeout=1)

    peak_mb = max(samples + [get_rss_mb()])
    # RSS sampling can show tiny negative deltas when the Python runtime frees
    # memory during the measured query.  Report those artifacts as zero rather
    # than as negative memory usage.
    return result, max(0.0, peak_mb - start_mb), peak_mb, elapsed


# ----------------------------------------------------------------------------
# Unified memory methodology (same instrument and protocol for all systems)
# ----------------------------------------------------------------------------

def ensure_dedicated_cgroup() -> None:
    """Re-exec this process inside a transient systemd user scope.

    The scope gives the engine its own cgroup v2 subtree, so its memory is
    read from the same instrument (memory.current) as the database
    containers'.  A no-op on re-entry or when systemd-run is unavailable."""
    if os.environ.get("MR_BENCH_CGROUP") == "1":
        return
    os.environ["MR_BENCH_CGROUP"] = "1"
    if shutil.which("systemd-run") is None:
        print("WARNING: systemd-run not available; engine sampled from the "
              "shared user cgroup (RSS fallback)")
        return
    os.execvp("systemd-run", [
        "systemd-run", "--user", "--scope", "-p", "MemoryAccounting=yes",
        "--quiet", sys.executable] + sys.argv)


def self_cgroup_memory_path() -> Path | None:
    try:
        cg = Path("/proc/self/cgroup").read_text().strip().split(":")[-1]
        path = Path("/sys/fs/cgroup") / cg.lstrip("/") / "memory.current"
        path.read_text()
        return path
    except Exception:
        return None


class MemorySampler:
    """Sample memory (MB) every SAMPLE_INTERVAL_S with wall-clock timestamps.

    container=None reads this process's own cgroup memory.current (RSS
    fallback); otherwise one long-lived ``docker exec`` loop prints the
    container's memory.current, avoiding the ~2 s cost of ``docker stats``."""

    def __init__(self, container: str | None = None):
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._read_now_fn = None
        if container is None:
            path = self_cgroup_memory_path()
            if path is not None:
                def read() -> float:
                    return int(path.read_text()) / 1048576
            else:
                read = get_rss_mb
            self._read_now_fn = read

            def pump() -> None:
                while not self._stop.is_set():
                    try:
                        self.samples.append((time.monotonic(), read()))
                    except Exception:
                        pass
                    time.sleep(SAMPLE_INTERVAL_S)
        else:
            self._proc = subprocess.Popen(
                ["docker", "exec", container, "sh", "-c",
                 f"while :; do cat /sys/fs/cgroup/memory.current; "
                 f"sleep {SAMPLE_INTERVAL_S}; done"],
                stdout=subprocess.PIPE, text=True)

            def pump() -> None:
                for line in self._proc.stdout:
                    if self._stop.is_set():
                        break
                    line = line.strip()
                    if line.isdigit():
                        self.samples.append(
                            (time.monotonic(), int(line) / 1048576))
        self._thread = threading.Thread(target=pump, daemon=True)
        self._thread.start()

    def read_now(self) -> None:
        if self._read_now_fn is not None:
            try:
                self.samples.append((time.monotonic(), self._read_now_fn()))
            except Exception:
                pass

    def window(self, t0: float, t1: float) -> list[float]:
        return [v for (t, v) in self.samples if t0 <= t <= t1]

    def close(self) -> None:
        self._stop.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass


def measure_run(sampler: MemorySampler, func):
    """One measured execution under the unified protocol.

    5 s pre-query baseline (mean of samples) -> timed query -> absolute peak
    = max sample inside the query window -> incremental peak = absolute -
    baseline.  Returns (result, elapsed_s, baseline_mb, abs_peak_mb,
    inc_peak_mb)."""
    b0 = time.monotonic()
    time.sleep(BASELINE_SECONDS)
    b1 = time.monotonic()
    base_samples = sampler.window(b0, b1)
    baseline = sum(base_samples) / len(base_samples) if base_samples else None

    sampler.read_now()
    q0 = time.monotonic()
    start = time.perf_counter()
    result = func()
    elapsed = time.perf_counter() - start
    sampler.read_now()
    q1 = time.monotonic()

    query_samples = sampler.window(q0, q1)
    if not query_samples:
        # Query finished between two sampler ticks: use the first sample after
        # completion as the peak estimate (memory is not reclaimed instantly).
        deadline = time.monotonic() + 3 * SAMPLE_INTERVAL_S
        while not query_samples and time.monotonic() < deadline:
            time.sleep(SAMPLE_INTERVAL_S / 5)
            query_samples = sampler.window(q0, time.monotonic())
    abs_peak = max(query_samples) if query_samples else baseline
    inc_peak = None
    if abs_peak is not None and baseline is not None:
        inc_peak = max(0.0, abs_peak - baseline)
    return result, elapsed, baseline, abs_peak, inc_peak


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
    """Create one prepared CSV dataset that all systems use for this size.

    The source CSV has ~2.2M rows.  For requested sizes at or below that, the
    dataset is the first ``size`` rows (nested prefixes).  For larger sizes the
    source rows are tiled (duplicated) to reach the target count; ``seq_id`` is
    then reassigned 0..size-1 so the ordering and single-partition semantics are
    preserved and the systems still process an identical row sequence.
    """
    path = dataset_path(size)
    if path.exists():
        return path

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(
        SOURCE_DATASET,
        nrows=size,
        usecols=["stars", "reviews", "price", "categoryName"],
    )
    if len(df) < size:
        # Requested size exceeds the source; tile the rows to reach it.
        reps = -(-size // len(df))  # ceil division
        df = pd.concat([df] * reps, ignore_index=True).iloc[:size].reset_index(drop=True)
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


def trino_query_peak_mb(cursor) -> float | None:
    """Peak user memory of the last executed query, from Trino's own
    per-query memory accounting (client protocol stats)."""
    stats = getattr(cursor, "stats", None) or {}
    peak_bytes = stats.get("peakMemoryBytes")
    if peak_bytes is None:
        return None
    return peak_bytes / 1024 / 1024


ORACLE_PGA_MAX_SQL = """
    SELECT ms.value
    FROM v$mystat ms
    JOIN v$statname sn ON ms.statistic# = sn.statistic#
    WHERE sn.name = 'session pga memory max'
"""


def oracle_session_pga_max_mb(cursor) -> float | None:
    """High-water mark of this session's PGA allocation.  MATCH_RECOGNIZE
    workareas are PGA allocations, so the delta of this counter around a
    query on a fresh session is the query's peak working memory."""
    try:
        cursor.execute(ORACLE_PGA_MAX_SQL)
        row = cursor.fetchone()
    except Exception:
        return None
    if row is None or row[0] is None:
        return None
    return float(row[0]) / 1024 / 1024


# Each per-run measurement below is
# (result, elapsed, baseline_mb, abs_peak_mb, inc_peak_mb, native_mb).
Measurement = tuple[
    pd.DataFrame, float, float | None, float | None, float | None, float | None
]


def _mean_or_none(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _iqr_filter(values: list[float | None]) -> tuple[list[float], int]:
    """Drop values outside [Q1 - 1.5 IQR, Q3 + 1.5 IQR]; return (kept, n_excluded)."""
    vals = [v for v in values if v is not None]
    if len(vals) < 4:
        return vals, 0
    s = sorted(vals)

    def quantile(p: float) -> float:
        idx = p * (len(s) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(s) - 1)
        frac = idx - lo
        return s[lo] * (1 - frac) + s[hi] * frac

    q1, q3 = quantile(0.25), quantile(0.75)
    iqr = q3 - q1
    lo_b, hi_b = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    kept = [v for v in vals if lo_b <= v <= hi_b]
    return kept, len(vals) - len(kept)


def _mean_std(vals: list[float]) -> tuple[float | None, float | None]:
    if not vals:
        return None, None
    mu = sum(vals) / len(vals)
    if len(vals) > 1:
        sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1))
    else:
        sd = 0.0
    return mu, sd


def aggregate_runs(measurements: list[Measurement], size: int) -> dict:
    """IQR-filtered mean +/- std over the measured runs, per the methodology.

    Applied independently to execution time, throughput, absolute peak
    memory, and incremental peak memory; the number of excluded outliers is
    recorded per metric.  The result DataFrame is taken from the first run
    (results are identical across runs, which the correctness check
    verifies)."""
    times = [m[1] for m in measurements]
    kept_t, excl_t = _iqr_filter(times)
    t_mu, t_sd = _mean_std(kept_t)
    throughputs = [size / t for t in times]
    kept_thr, excl_thr = _iqr_filter(throughputs)
    thr_mu, thr_sd = _mean_std(kept_thr)
    kept_abs, excl_abs = _iqr_filter([m[3] for m in measurements])
    abs_mu, abs_sd = _mean_std(kept_abs)
    kept_inc, excl_inc = _iqr_filter([m[4] for m in measurements])
    inc_mu, inc_sd = _mean_std(kept_inc)
    return {
        "result": measurements[0][0],
        "time_mean": t_mu, "time_std": t_sd,
        "time_min": min(times), "time_max": max(times), "time_excl": excl_t,
        "thr_mean": thr_mu, "thr_std": thr_sd, "thr_excl": excl_thr,
        "baseline_mean": _mean_or_none([m[2] for m in measurements]),
        "abs_mean": abs_mu, "abs_std": abs_sd, "abs_excl": excl_abs,
        "inc_mean": inc_mu, "inc_std": inc_sd, "inc_excl": excl_inc,
        "native_mean": _mean_or_none([m[5] for m in measurements]),
        "mem_per_mrow": (inc_mu / (size / 1e6)) if inc_mu is not None else None,
    }


def _progress(msg: str) -> None:
    """Per-run progress line (warmup / measured k of n), flushed immediately."""
    print(f"      {msg}", flush=True)


def run_pandas_pattern(
    df: pd.DataFrame, pattern_name: str, warmup_runs: int, measured_runs: int
) -> dict:
    from src.executor.match_recognize import match_recognize

    query = query_for_system("pandas", pattern_name)
    for i in range(warmup_runs):
        match_recognize(query, df)
        _progress(f"warmup {i + 1}/{warmup_runs} done")
    sampler = MemorySampler()
    try:
        measurements: list[Measurement] = []
        for i in range(measured_runs):
            # Trim allocator pools before the baseline window so the baseline
            # reflects a settled state and the incremental peak is the
            # query's real growth.
            clean_process_memory()
            result, elapsed, baseline, abs_peak, inc_peak = measure_run(
                sampler, lambda: match_recognize(query, df))
            measurements.append(
                (result, elapsed, baseline, abs_peak, inc_peak, None))
            _progress(f"measured {i + 1}/{measured_runs} done ({elapsed * 1000:.1f} ms)")
    finally:
        sampler.close()
    return aggregate_runs(measurements, len(df))


def run_trino_pattern(
    cursor,
    pattern_name: str,
    warmup_runs: int,
    measured_runs: int,
    size: int,
) -> dict:
    query = query_for_system("trino", pattern_name)
    for i in range(warmup_runs):
        fetch_dataframe(cursor, query)
        _progress(f"warmup {i + 1}/{warmup_runs} done")
    sampler = MemorySampler(container="trino-473")
    try:
        measurements: list[Measurement] = []
        for i in range(measured_runs):
            result, elapsed, baseline, abs_peak, inc_peak = measure_run(
                sampler, lambda: fetch_dataframe(cursor, query))
            measurements.append((result, elapsed, baseline, abs_peak,
                                 inc_peak, trino_query_peak_mb(cursor)))
            _progress(f"measured {i + 1}/{measured_runs} done ({elapsed * 1000:.1f} ms)")
    finally:
        sampler.close()
    return aggregate_runs(measurements, size)


def run_oracle_pattern(
    warmup_cursor,
    pattern_name: str,
    warmup_runs: int,
    measured_runs: int,
    password: str,
    dsn: str,
    size: int,
) -> dict:
    query = query_for_system("oracle", pattern_name)
    for i in range(warmup_runs):
        fetch_dataframe(warmup_cursor, query)
        _progress(f"warmup {i + 1}/{warmup_runs} done")

    # 'session pga memory max' is a per-session high-water mark, so every
    # measured run uses a fresh session: otherwise earlier runs would already
    # have raised the mark and the delta would read as zero.
    sampler = MemorySampler(container="oracle-free")
    try:
        measurements: list[Measurement] = []
        for i in range(measured_runs):
            conn = connect_oracle(password, dsn)
            try:
                cur = conn.cursor()
                pga_baseline = oracle_session_pga_max_mb(cur)
                result, elapsed, baseline, abs_peak, inc_peak = measure_run(
                    sampler, lambda: fetch_dataframe(cur, query))
                pga_after = oracle_session_pga_max_mb(cur)
            finally:
                conn.close()
            native = None
            if pga_baseline is not None and pga_after is not None:
                native = max(0.0, pga_after - pga_baseline)
            measurements.append(
                (result, elapsed, baseline, abs_peak, inc_peak, native))
            _progress(f"measured {i + 1}/{measured_runs} done ({elapsed * 1000:.1f} ms)")
    finally:
        sampler.close()
    return aggregate_runs(measurements, size)


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


def run_pandas_system(sizes: list[int], warmup_runs: int, measured_runs: int) -> tuple[list[RunResult], dict[tuple[int, str], pd.DataFrame]]:
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
                stats = run_pandas_pattern(
                    df, pattern_name, warmup_runs, measured_runs
                )
                result_df = stats["result"]
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
                        execution_time_seconds=stats["time_mean"],
                        execution_time_std_seconds=stats["time_std"],
                        execution_time_min_seconds=stats["time_min"],
                        execution_time_max_seconds=stats["time_max"],
                        measured_runs=measured_runs,
                        throughput_rows_per_second=stats["thr_mean"],
                        query_memory_mb=stats["inc_mean"],
                        query_memory_metric=PANDAS_QUERY_MEMORY_METRIC,
                        footprint_memory_mb=stats["abs_mean"],
                        footprint_memory_metric=PANDAS_FOOTPRINT_MEMORY_METRIC,
                        result_rows=len(result_df),
                        throughput_std_rows_per_second=stats["thr_std"],
                        baseline_memory_mb=stats["baseline_mean"],
                        abs_peak_memory_std_mb=stats["abs_std"],
                        inc_peak_memory_std_mb=stats["inc_std"],
                        mem_per_million_rows_mb=stats["mem_per_mrow"],
                        native_query_memory_mb=stats["native_mean"],
                        outliers_excluded_time=stats["time_excl"],
                        outliers_excluded_throughput=stats["thr_excl"],
                        outliers_excluded_abs_peak=stats["abs_excl"],
                        outliers_excluded_inc_peak=stats["inc_excl"],
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
                        execution_time_std_seconds=None,
                        execution_time_min_seconds=None,
                        execution_time_max_seconds=None,
                        measured_runs=measured_runs,
                        throughput_rows_per_second=None,
                        query_memory_mb=None,
                        query_memory_metric=PANDAS_QUERY_MEMORY_METRIC,
                        footprint_memory_mb=None,
                        footprint_memory_metric=PANDAS_FOOTPRINT_MEMORY_METRIC,
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
    measured_runs: int,
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
                stats = run_trino_pattern(
                    cur, pattern_name, warmup_runs, measured_runs, size
                )
                result_df = stats["result"]
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
                        execution_time_seconds=stats["time_mean"],
                        execution_time_std_seconds=stats["time_std"],
                        execution_time_min_seconds=stats["time_min"],
                        execution_time_max_seconds=stats["time_max"],
                        measured_runs=measured_runs,
                        throughput_rows_per_second=stats["thr_mean"],
                        query_memory_mb=stats["inc_mean"],
                        query_memory_metric=TRINO_QUERY_MEMORY_METRIC,
                        footprint_memory_mb=stats["abs_mean"],
                        footprint_memory_metric=DB_FOOTPRINT_MEMORY_METRIC,
                        result_rows=len(result_df),
                        throughput_std_rows_per_second=stats["thr_std"],
                        baseline_memory_mb=stats["baseline_mean"],
                        abs_peak_memory_std_mb=stats["abs_std"],
                        inc_peak_memory_std_mb=stats["inc_std"],
                        mem_per_million_rows_mb=stats["mem_per_mrow"],
                        native_query_memory_mb=stats["native_mean"],
                        outliers_excluded_time=stats["time_excl"],
                        outliers_excluded_throughput=stats["thr_excl"],
                        outliers_excluded_abs_peak=stats["abs_excl"],
                        outliers_excluded_inc_peak=stats["inc_excl"],
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
                        execution_time_std_seconds=None,
                        execution_time_min_seconds=None,
                        execution_time_max_seconds=None,
                        measured_runs=measured_runs,
                        throughput_rows_per_second=None,
                        query_memory_mb=None,
                        query_memory_metric=TRINO_QUERY_MEMORY_METRIC,
                        footprint_memory_mb=None,
                        footprint_memory_metric=DB_FOOTPRINT_MEMORY_METRIC,
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
    measured_runs: int,
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
                stats = run_oracle_pattern(
                    cur, pattern_name, warmup_runs, measured_runs, password, dsn, size
                )
                result_df = stats["result"]
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
                        execution_time_seconds=stats["time_mean"],
                        execution_time_std_seconds=stats["time_std"],
                        execution_time_min_seconds=stats["time_min"],
                        execution_time_max_seconds=stats["time_max"],
                        measured_runs=measured_runs,
                        throughput_rows_per_second=stats["thr_mean"],
                        query_memory_mb=stats["inc_mean"],
                        query_memory_metric=ORACLE_QUERY_MEMORY_METRIC,
                        footprint_memory_mb=stats["abs_mean"],
                        footprint_memory_metric=DB_FOOTPRINT_MEMORY_METRIC,
                        result_rows=len(result_df),
                        throughput_std_rows_per_second=stats["thr_std"],
                        baseline_memory_mb=stats["baseline_mean"],
                        abs_peak_memory_std_mb=stats["abs_std"],
                        inc_peak_memory_std_mb=stats["inc_std"],
                        mem_per_million_rows_mb=stats["mem_per_mrow"],
                        native_query_memory_mb=stats["native_mean"],
                        outliers_excluded_time=stats["time_excl"],
                        outliers_excluded_throughput=stats["thr_excl"],
                        outliers_excluded_abs_peak=stats["abs_excl"],
                        outliers_excluded_inc_peak=stats["inc_excl"],
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
                        execution_time_std_seconds=None,
                        execution_time_min_seconds=None,
                        execution_time_max_seconds=None,
                        measured_runs=measured_runs,
                        throughput_rows_per_second=None,
                        query_memory_mb=None,
                        query_memory_metric=ORACLE_QUERY_MEMORY_METRIC,
                        footprint_memory_mb=None,
                        footprint_memory_metric=DB_FOOTPRINT_MEMORY_METRIC,
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
            "measured_runs": args.measured_runs,
            "reported_time": "mean of measured runs (min/max recorded per cell)",
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
        query_memories = [r.query_memory_mb for r in group if r.query_memory_mb is not None]
        footprint_memories = [r.footprint_memory_mb for r in group if r.footprint_memory_mb is not None]
        aggregate_rows.append(
            {
                "system": system,
                "successful_tests": len(group),
                "avg_time_seconds": sum(r.execution_time_seconds for r in group if r.execution_time_seconds) / len(group),
                "avg_throughput_rows_per_second": sum(r.throughput_rows_per_second for r in group if r.throughput_rows_per_second) / len(group),
                "max_query_memory_mb": max(query_memories) if query_memories else None,
                "max_footprint_memory_mb": max(footprint_memories) if footprint_memories else None,
                "all_correct": all(r.correctness_matches_pandas in (True, "baseline") for r in group),
            }
        )
    pd.DataFrame(aggregate_rows).to_csv(OUTPUT_DIR / f"{summary_stem}_aggregate.csv", index=False)


def main() -> None:
    ensure_dedicated_cgroup()
    parser = argparse.ArgumentParser(description="Run full cross-system benchmark matrix.")
    parser.add_argument("--systems", nargs="+", choices=["pandas", "trino", "oracle"], default=["pandas", "trino", "oracle"])
    parser.add_argument("--sizes", nargs="+", type=int, default=DEFAULT_SIZES)
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--memory-gb", type=int, default=32)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--measured-runs", type=int, default=6,
                        help="measured executions per cell; the mean time is reported")
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
        pandas_results, expected = run_pandas_system(args.sizes, args.warmup_runs, args.measured_runs)
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
                args.measured_runs,
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
                args.measured_runs,
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
