#!/usr/bin/env python3
"""Stress test on real data: system boundaries beyond the main benchmark.

Data: Amazon Reviews 2023 rating events (built by prepare_dataset.py; no
duplication), sizes 5M/10M/20M/40M/80M/160M/full (~230M), nested prefixes in
global timestamp order.  The pattern variables A..E are the ratings 1..5
stars, so every query reads as a rating-trajectory analysis.

Queries: five families corresponding to the main benchmark, re-adapted to
the rating alphabet so match density stays healthy on the 5-star-skewed
distribution. Four preserve the main structure. The optional family uses
the stress-specific `E D? C+ B*` form shown below:

  simple_sequence   E+ D+          run of 5-star, then run of 4-star
  alternation       D (C|B)+ E     dip into middling ratings, recovered
  quantified        E{1,5} D* C+   bounded high run, decline to 3-star
  optional_pattern  E D? C+ B*     stepwise decline with optional stage
  complex_nested    (E|D)+ (C{1,3} B*)+   high phase, structured decline

Pattern-complexity suite: PERMUTE(3/4/5) over rating letters, a deep nested
decline pattern, and the maximum-density ALL ROWS query (capped at 5M
because output == input).

Protocol: unified instrument, 2 warmups + 5 measured, 58GB limit, 1 CPU,
container restart before each size, and per-metric IQR. Trino scans a Hive
external table backed by local Parquet. Oracle 21c Enterprise Edition loads
each size into a native heap by direct path. A 600s per-query budget records
time-limit cells as boundary results.

Results -> volume/ and pattern/ next to this file; walls in walls.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import Performance.run_cross_system_matrix as m  # noqa: E402

# The containers run on the host's SYSTEM docker daemon (not Docker Desktop's
# VM, which sizes itself at all host RAM and OOM-crashes under a large-memory
# container).  Pin every docker subprocess here so it survives the
# systemd-run re-exec in ensure_dedicated_cgroup() regardless of launch env.
import os  # noqa: E402
os.environ.setdefault("DOCKER_HOST", "unix:///var/run/docker.sock")

HERE = Path(__file__).resolve().parent
DATASETS = HERE / "datasets"
OUT_VOLUME = HERE / "volume"
OUT_PATTERN = HERE / "pattern"

CPUS, MEMORY_GB = 1, 58  # 58 GB fits under 62 GB physical RAM (no swap/OOM);
# same budget for all three systems keeps the comparison symmetric
WARMUPS, MEASURED = 2, 5
CHUNK_ORACLE = 20000
CHUNK_TRINO = 100000
BUDGET_S = 600.0
# A single fetch beyond this is treated as a wedged server (client-side hard
# wall).  It sits above BUDGET_S + Trino's own query_max_run_time so a healthy
# large query is never cut, but the GC-death-spiral hang (which no per-HTTP-
# request timeout catches, because the coordinator answers briefly between
# 45s GC pauses and keeps resetting the client's retry counter) is bounded.
FETCH_HARD_S = BUDGET_S + 180.0
PASSWORD, DSN = "Oracle_12345", "localhost:1521/ORCLPDB1"  # Oracle EE PDB
# Oracle EE direct-path load (fair, native): the size's CSV is copied into the
# container, exposed as an external ORACLE_LOADER table, and bulk-loaded into a
# native heap table with INSERT /*+ APPEND */ (direct path).  No 12 GB edition
# cap (unlike XE), so it reaches the full 227.9 M under the same 58 GB budget.
ORACLE_BENCH_DIR_REAL = "/opt/oracle/bench_data"
ORACLE_DIR_OBJ = "BENCH_DIR"
ORACLE_TABLESPACE = "BENCHTS"


class ServerWedged(RuntimeError):
    """A DB fetch blew its client-side hard deadline; the container is assumed
    wedged and must be force-restarted before anything else is attempted."""


def bounded_fetch(cursor, query: str) -> pd.DataFrame:
    """Drop-in replacement for m.fetch_dataframe that can never hang forever.

    Runs execute+fetchall on a daemon thread and joins with FETCH_HARD_S; on
    overrun it best-effort cancels the query (Trino cursors expose .cancel())
    and, if the thread still will not return, abandons it and raises
    ServerWedged.  The abandoned socket is freed when the phase force-restarts
    the container, so no wedged connection is ever reused."""
    box: dict = {}

    def work():
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            cols = [d[0].lower() for d in cursor.description]
            box["v"] = pd.DataFrame(rows, columns=cols)
        except BaseException as exc:  # noqa: BLE001 - relayed to caller thread
            box["e"] = exc

    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(FETCH_HARD_S)
    if th.is_alive():
        cancel = getattr(cursor, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception:  # noqa: BLE001
                pass
        th.join(30)
    if th.is_alive():
        raise ServerWedged(
            f"fetch exceeded {FETCH_HARD_S:.0f}s hard wall (server wedged)")
    if "e" in box:
        raise box["e"]
    return box["v"]


BATCH_HARD_S = 180.0  # a healthy 100k-row INSERT is seconds; >3 min == wedged


def bounded_trino_execute(cur, sql: str) -> None:
    """Bound one Trino INSERT batch: a load that drives the memory connector's
    on-heap store into a GC death spiral hangs here (the coordinator is too
    GC-starved to honour query_max_run_time), so a client-side per-batch wall
    is the only thing that can end it.  Raises ServerWedged on overrun."""
    box: dict = {}

    def work():
        try:
            cur.execute(sql)
            box["v"] = True
        except BaseException as exc:  # noqa: BLE001
            box["e"] = exc

    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(BATCH_HARD_S)
    if th.is_alive():
        cancel = getattr(cur, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception:  # noqa: BLE001
                pass
        th.join(20)
    if th.is_alive():
        raise ServerWedged(
            f"INSERT batch exceeded {BATCH_HARD_S:.0f}s (Trino wedged during "
            f"load — memory connector cannot hold this size on the JVM heap)")
    if "e" in box:
        raise box["e"]


# ----------------------------------------------------------------------
# Trino disk connector (Hive file-metastore over local Parquet)
# ----------------------------------------------------------------------
# The memory connector is an on-heap store and cannot hold >~13-20M rows on a
# 64 GB machine, so the stress test reads Trino's table from disk instead: the
# size's rows are written to a Parquet file, copied into the container, and
# registered as an EXTERNAL Hive table.  Trino streams the scan from disk, so
# it is bound by disk/CPU, not the JVM heap, and reaches the full 227.9 M rows.
# Trino's native local file system roots `local://` at /tmp, so the URI
# local:///data/hive/ext/... is the real path /tmp/data/hive/ext/... (which
# survives the per-size `docker restart`).  Only the stress test uses this;
# the main benchmark keeps the memory connector for parity with its numbers.
TRINO_DISK_CATALOG = "hive"
TRINO_DISK_SCHEMA = "bench"
TRINO_EXT_URI = "local:///data/hive/ext/benchmark_matrix"
TRINO_EXT_REAL = "/tmp/data/hive/ext/benchmark_matrix"
_PARQUET_TMP = HERE / "datasets" / "_trino_parquet"
_TRINO_SCHEMA = pa.schema([
    ("seq_id", pa.int32()), ("category", pa.string()),
    ("stars", pa.float64()), ("price", pa.float64()),
    ("reviews", pa.int64()), ("category_name", pa.string()),
])
_TRINO_COLS = [f.name for f in _TRINO_SCHEMA]


def connect_trino_disk():
    import trino
    return trino.dbapi.connect(
        host="localhost", port=8080, user="benchmark",
        catalog=TRINO_DISK_CATALOG, schema=TRINO_DISK_SCHEMA,
        session_properties={"query_max_run_time": m.TRINO_QUERY_MAX_RUN_TIME})


def ensure_trino_hive() -> None:
    """Idempotently ensure the hive schema + writable external dir exist (the
    hive catalog itself is baked into the committed image / applied by
    apply_deployment_fixes)."""
    subprocess.run(
        ["docker", "exec", "-u", "root", "trino-473", "sh", "-c",
         "mkdir -p /tmp/data/hive/ext && chown -R 1000:1000 /tmp/data/hive"],
        check=True)
    conn = connect_trino_disk()
    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {TRINO_DISK_CATALOG}."
                f"{TRINO_DISK_SCHEMA}")
    cur.fetchall()
    conn.close()


def load_trino_disk(df: pd.DataFrame, size: int) -> None:
    """Write the size's rows to Parquet, copy into the container's external
    location, and (re)register the external Hive table so `FROM {TABLE_NAME}`
    resolves to it.  Verifies the row count."""
    _PARQUET_TMP.mkdir(parents=True, exist_ok=True)
    pj = _PARQUET_TMP / "part-0.parquet"
    table = pa.Table.from_pandas(df[_TRINO_COLS], schema=_TRINO_SCHEMA,
                                 preserve_index=False)
    pq.write_table(table, pj)
    del table
    subprocess.run(
        ["docker", "exec", "-u", "root", "trino-473", "sh", "-c",
         f"rm -rf {TRINO_EXT_REAL} && mkdir -p {TRINO_EXT_REAL}"], check=True)
    subprocess.run(["docker", "cp", str(pj),
                    f"trino-473:{TRINO_EXT_REAL}/part-0.parquet"], check=True)
    subprocess.run(["docker", "exec", "-u", "root", "trino-473", "chown",
                    "-R", "1000:1000", TRINO_EXT_REAL], check=True)
    pj.unlink(missing_ok=True)
    conn = connect_trino_disk()
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {m.TABLE_NAME}")
    cur.fetchall()
    cur.execute(
        f"""CREATE TABLE {m.TABLE_NAME} (
                seq_id INTEGER, category VARCHAR, stars DOUBLE,
                price DOUBLE, reviews BIGINT, category_name VARCHAR)
            WITH (format='PARQUET', external_location='{TRINO_EXT_URI}')""")
    cur.fetchall()
    cur.execute(f"SELECT COUNT(*) FROM {m.TABLE_NAME}")
    cnt = cur.fetchone()[0]
    conn.close()
    assert cnt == len(df), f"trino disk load {cnt:,} != {len(df):,}"


def completed_sizes(path: Path, patterns: dict) -> set[int]:
    """Sizes already fully recorded in a *_results / summary CSV (every pattern
    of the suite present and successful), so a resumed run can skip them."""
    if not path.exists():
        return set()
    df = pd.read_csv(path)
    if "success" in df.columns:
        df = df[df["success"].astype(str).isin(["True", "true", "1", "1.0"])]
    done = set()
    for size, grp in df.groupby("dataset_size"):
        need = {p for p in patterns
                if not (p == "high_density_all_rows" and size > ALL_ROWS_CAP)}
        if need and need <= set(grp["pattern_name"]):
            done.add(int(size))
    return done


def load_sizes() -> list[int]:
    manifest = DATASETS / "sizes.json"
    assert manifest.exists(), "run prepare_dataset.py first"
    return json.loads(manifest.read_text())["sizes"]


VOLUME_PATTERNS = {
    "simple_sequence": {
        "pattern": "E+ D+",
        "description": "run of 5-star ratings followed by a run of 4-star",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(E.seq_id) AS start_row,
                LAST(D.seq_id) AS end_row,
                COUNT(*) AS match_length,
                COUNT(E.seq_id) AS e_count,
                COUNT(D.seq_id) AS d_count
            ONE ROW PER MATCH
            PATTERN (E+ D+)
            DEFINE
                E AS category = 'E',
                D AS category = 'D'
        """,
    },
    "alternation": {
        "pattern": "D (C|B)+ E",
        "description": "4-star, a middling run, recovered to 5-star",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(D.seq_id) AS start_row,
                LAST(E.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (D (C|B)+ E)
            DEFINE
                D AS category = 'D',
                C AS category = 'C',
                B AS category = 'B',
                E AS category = 'E'
        """,
    },
    "quantified": {
        "pattern": "E{1,5} D* C+",
        "description": "bounded 5-star run, optional 4-star, decline to 3-star",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(E.seq_id) AS start_row,
                LAST(C.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (E{1,5} D* C+)
            DEFINE
                E AS category = 'E',
                D AS category = 'D',
                C AS category = 'C'
        """,
    },
    "optional_pattern": {
        "pattern": "E D? C+ B*",
        "description": "stepwise rating decline with an optional stage",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(E.seq_id) AS start_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (E D? C+ B*)
            DEFINE
                E AS category = 'E',
                D AS category = 'D',
                C AS category = 'C',
                B AS category = 'B'
        """,
    },
    "complex_nested": {
        "pattern": "(E|D)+ (C{1,3} B*)+",
        "description": "high-rating phase, then structured decline",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(E.seq_id) AS start_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN ((E|D)+ (C{1,3} B*)+)
            DEFINE
                E AS category = 'E',
                D AS category = 'D',
                C AS category = 'C',
                B AS category = 'B'
        """,
    },
}

STRESS_PATTERNS = {
    "permute3": {
        "pattern": "PERMUTE(C, D, E)",
        "description": "all orderings of three rating levels (3! = 6)",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(C.seq_id) AS c_row,
                FIRST(E.seq_id) AS e_row
            ONE ROW PER MATCH
            PATTERN (PERMUTE(C, D, E))
            DEFINE
                C AS category = 'C',
                D AS category = 'D',
                E AS category = 'E'
        """,
    },
    "permute4": {
        "pattern": "PERMUTE(B, C, D, E)",
        "description": "all orderings of four rating levels (4! = 24)",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(B.seq_id) AS b_row,
                FIRST(E.seq_id) AS e_row
            ONE ROW PER MATCH
            PATTERN (PERMUTE(B, C, D, E))
            DEFINE
                B AS category = 'B',
                C AS category = 'C',
                D AS category = 'D',
                E AS category = 'E'
        """,
    },
    "permute5": {
        "pattern": "PERMUTE(A, B, C, D, E)",
        "description": "all orderings of five rating levels (5! = 120)",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS a_row,
                FIRST(E.seq_id) AS e_row
            ONE ROW PER MATCH
            PATTERN (PERMUTE(A, B, C, D, E))
            DEFINE
                A AS category = 'A',
                B AS category = 'B',
                C AS category = 'C',
                D AS category = 'D',
                E AS category = 'E'
        """,
    },
    "deep_nested": {
        "pattern": "((E|D)+ (C (B|A)*)+)+",
        "description": "three-level nested rating-decline pattern",
        "body": """
            ORDER BY seq_id
            MEASURES
                FIRST(E.seq_id) AS start_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (((E|D)+ (C (B|A)*)+)+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B',
                C AS category = 'C',
                D AS category = 'D',
                E AS category = 'E'
        """,
    },
    "high_density_all_rows": {
        "pattern": "A+ (ALL ROWS PER MATCH)",
        "description": "every row matches; output size equals input size",
        "body": """
            ORDER BY seq_id
            MEASURES
                COUNT(*) AS running_length
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE
                A AS price >= 0
        """,
    },
}

# output == input for the ALL ROWS query: fetching >5M result rows per run
# is transfer-, not matcher-, bound, so it is capped
ALL_ROWS_CAP = 5_000_000


# ----------------------------------------------------------------------
# deployment configuration (also baked into the *-mrbench images)
# ----------------------------------------------------------------------
def apply_deployment_fixes() -> None:
    m.docker_start("trino-473")
    m.wait_for_trino(900)
    out = subprocess.run(
        ["docker", "exec", "trino-473", "sh", "-c",
         'grep -q "^memory.max-data-per-node=" /etc/trino/catalog/memory.properties'
         ' || { echo "memory.max-data-per-node=32GB"'
         ' >> /etc/trino/catalog/memory.properties; echo CHANGED; };'
         ' grep -q "^query.max-length=134217728" /etc/trino/config.properties'
         ' || { sed -i "s/^query.max-length=.*/query.max-length=134217728/"'
         ' /etc/trino/config.properties; echo CHANGED; };'
         # disk connector for the stress test: Hive file-metastore over local
         # Parquet, so Trino can scale past the memory connector's ~15M heap wall
         ' [ -f /etc/trino/catalog/hive.properties ]'
         ' || { printf "%s\\n"'
         ' "connector.name=hive"'
         ' "hive.metastore=file"'
         ' "hive.metastore.catalog.dir=local:///data/hive"'
         ' "fs.native-local.enabled=true"'
         ' "hive.non-managed-table-writes-enabled=true"'
         ' > /etc/trino/catalog/hive.properties; echo CHANGED; }'],
        capture_output=True, text=True).stdout
    if "CHANGED" in out:
        print("  Trino config updated; restarting")
        subprocess.run(["docker", "restart", "trino-473"], check=True)
        m.wait_for_trino(900)
    else:
        print("  Trino config already applied")
    ensure_trino_hive()

    # Oracle 21c Enterprise Edition (uncapped, fair): memory (SGA 14G,
    # pga_aggregate_target 18G, pga_aggregate_limit 36G -> peak ~54G, under the
    # 58G container) is baked into the spfile of oracle-mrbench:ee; the PDB
    # auto-opens (saved state).  Just start it, wait, and ensure the loader's
    # directory + big tablespaces exist.
    m.docker_start("oracle-21c-ee")
    m.wait_for_oracle(PASSWORD, DSN, 1800)
    oracle_ensure_setup()
    print("  Oracle EE ready (memory baked: SGA 14G / PGA 18-36G, uncapped)")


# ----------------------------------------------------------------------
# measurement plumbing
# ----------------------------------------------------------------------
def expected_for(part_dir: Path, size: int, pattern: str) -> pd.DataFrame:
    path = part_dir / "results" / f"pandas_{size}_{pattern}.csv"
    return m.normalize_result(pd.read_csv(path)) if path.exists() else pd.DataFrame()


def make_row(system: str, size: int, pattern: str, patterns: dict,
             stats: dict | None = None, success: bool = True, correct=None,
             error: str | None = None, result_rows=None) -> dict:
    label = {"trino": "trino_473", "oracle": "oracle_21c_ee"}[system]
    qmetric = (m.TRINO_QUERY_MEMORY_METRIC if system == "trino"
               else m.ORACLE_QUERY_MEMORY_METRIC)
    row = dict(system=label, dataset_size=size, pattern_name=pattern,
               pattern=patterns[pattern]["pattern"], success=success,
               correctness_matches_pandas=correct, measured_runs=MEASURED,
               query_memory_metric=qmetric,
               footprint_memory_metric=m.DB_FOOTPRINT_MEMORY_METRIC,
               error=error, result_rows=result_rows)
    if stats:
        row.update(
            execution_time_seconds=stats["time_mean"],
            execution_time_std_seconds=stats["time_std"],
            execution_time_min_seconds=stats["time_min"],
            execution_time_max_seconds=stats["time_max"],
            throughput_rows_per_second=stats["thr_mean"],
            throughput_std_rows_per_second=stats["thr_std"],
            query_memory_mb=stats["inc_mean"],
            footprint_memory_mb=stats["abs_mean"],
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
    return row


def merge_results(part_dir: Path, system_prefix: str, new_rows: list) -> None:
    if not new_rows:
        return
    path = part_dir / f"{system_prefix}_results.csv"
    new = pd.DataFrame(new_rows)
    if path.exists():
        old = pd.read_csv(path)
        keys = set(zip(new.dataset_size, new.pattern_name))
        old = old[~old.apply(
            lambda r: (r.dataset_size, r.pattern_name) in keys, axis=1)]
        new = pd.concat([old, new], ignore_index=True)
    new.sort_values(["dataset_size", "pattern_name"]).to_csv(path, index=False)
    print(f"  merged {len(new_rows)} rows -> {path}")


def probe_ok(system: str, pattern: str, size: int, records: list,
             patterns: dict, cur) -> bool:
    """One timed probe; a cell costs warmups+measured further runs, so a
    probe beyond BUDGET_S records the cell as a practical-time boundary."""
    query = m.query_for_system(system, pattern)
    t0 = time.monotonic()
    m.fetch_dataframe(cur, query)
    dt = time.monotonic() - t0
    if dt > BUDGET_S:
        records.append(make_row(system, size, pattern, patterns,
                                success=False,
                                error=f"single run {dt:.0f}s exceeds the "
                                      f"{BUDGET_S:.0f}s per-run time budget"))
        print(f"    !! budget: {pattern}@{size:,} probe {dt:.0f}s")
        return False
    print(f"    probe {pattern}@{size:,}: {dt:.1f}s (within budget)")
    return True


def run_cell(system: str, cur, pattern: str, size: int, part_dir: Path,
             records: list, patterns: dict) -> None:
    print(f"    cell {system}/{pattern}@{size:,}")
    try:
        if not probe_ok(system, pattern, size, records, patterns, cur):
            return
        if system == "trino":
            stats = m.run_trino_pattern(cur, pattern, WARMUPS, MEASURED, size)
        else:
            stats = m.run_oracle_pattern(cur, pattern, WARMUPS, MEASURED,
                                         PASSWORD, DSN, size)
        normalized = m.normalize_result(stats["result"])
        m.save_result_csv(system, size, pattern, normalized)
        exp = expected_for(part_dir, size, pattern)
        correct = normalized.equals(exp) if len(exp) else None
        records.append(make_row(system, size, pattern, patterns, stats=stats,
                                correct=correct,
                                result_rows=len(stats["result"])))
        print(f"      ok: {stats['time_mean']:.2f}s mean, correct={correct}")
    except Exception as exc:  # noqa: BLE001 - the wall IS the result
        records.append(make_row(system, size, pattern, patterns,
                                success=False,
                                error=f"{type(exc).__name__}: {exc}"))
        print(f"    !! cell failed: {exc}")
        traceback.print_exc()
        if isinstance(exc, ServerWedged):
            # container is unusable; let the phase force-restart before it
            # touches this connection again.
            raise


def oracle_restart() -> None:
    m.docker_stop("oracle-21c-ee")
    m.docker_update("oracle-21c-ee", CPUS, MEMORY_GB)
    m.docker_start("oracle-21c-ee")
    m.wait_for_oracle(PASSWORD, DSN, 900)
    print("    restarted oracle-21c-ee (clean instance state)")


def trino_restart() -> None:
    m.docker_stop("trino-473")
    m.docker_update("trino-473", CPUS, MEMORY_GB)
    m.docker_start("trino-473")
    m.wait_for_trino(900)
    print("    restarted trino-473 (clean instance state)")


def oracle_table_count() -> int:
    conn = m.connect_oracle(PASSWORD, DSN)
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {m.TABLE_NAME}")
        return cur.fetchone()[0]
    except Exception:
        return -1
    finally:
        conn.close()


def oracle_ensure_setup() -> None:
    """Idempotently ensure the OS directory, the Oracle DIRECTORY object, and a
    big autoextending tablespace exist (baked into the EE image / re-applied
    here so a recreated container self-heals)."""
    subprocess.run(
        ["docker", "exec", "-u", "root", "oracle-21c-ee", "sh", "-c",
         f"mkdir -p {ORACLE_BENCH_DIR_REAL} && "
         f"chown oracle:oinstall {ORACLE_BENCH_DIR_REAL} && "
         f"chmod 775 {ORACLE_BENCH_DIR_REAL}"], check=True)
    conn = m.connect_oracle(PASSWORD, DSN)
    cur = conn.cursor()
    cur.execute(f"CREATE OR REPLACE DIRECTORY {ORACLE_DIR_OBJ} "
                f"AS '{ORACLE_BENCH_DIR_REAL}'")
    cur.execute(
        f"""BEGIN
                EXECUTE IMMEDIATE 'CREATE BIGFILE TABLESPACE {ORACLE_TABLESPACE}
                    DATAFILE ''{ORACLE_TABLESPACE.lower()}.dbf''
                    SIZE 1G AUTOEXTEND ON NEXT 1G MAXSIZE UNLIMITED';
            EXCEPTION WHEN OTHERS THEN
                IF SQLCODE != -1543 THEN RAISE; END IF;  -- already exists
            END;""")
    # bigfile TEMP so large MATCH_RECOGNIZE sorts (227M rows) that spill past
    # PGA can extend past the ~32 GB smallfile limit; make it the PDB default.
    cur.execute(
        """BEGIN
               EXECUTE IMMEDIATE 'CREATE BIGFILE TEMPORARY TABLESPACE benchtmp
                   TEMPFILE ''benchtmp.dbf''
                   SIZE 1G AUTOEXTEND ON NEXT 1G MAXSIZE UNLIMITED';
           EXCEPTION WHEN OTHERS THEN
               IF SQLCODE != -1543 THEN RAISE; END IF;
           END;""")
    cur.execute(
        """BEGIN
               EXECUTE IMMEDIATE
                   'ALTER DATABASE DEFAULT TEMPORARY TABLESPACE benchtmp';
           EXCEPTION WHEN OTHERS THEN
               IF SQLCODE != -12907 THEN RAISE; END IF;  -- already default
           END;""")
    conn.commit()
    conn.close()


def oracle_direct_load(size: int) -> None:
    """Native, representative load: copy the size's CSV into the container,
    expose it as an external ORACLE_LOADER table, then direct-path
    INSERT /*+ APPEND */ into a fresh native heap table in BENCHTS.  Verifies
    the row count; an ORA-01653/edition/disk wall propagates as the result."""
    csv = DATASETS / f"benchmark_{size}.csv"
    subprocess.run(["docker", "cp", str(csv),
                    f"oracle-21c-ee:{ORACLE_BENCH_DIR_REAL}/data.csv"], check=True)
    subprocess.run(["docker", "exec", "-u", "root", "oracle-21c-ee", "chown",
                    "oracle:oinstall", f"{ORACLE_BENCH_DIR_REAL}/data.csv"],
                   check=True)
    conn = m.connect_oracle(PASSWORD, DSN)
    cur = conn.cursor()
    for stmt in (f"BEGIN EXECUTE IMMEDIATE 'DROP TABLE ext_benchmark'; "
                 f"EXCEPTION WHEN OTHERS THEN NULL; END;",
                 f"BEGIN EXECUTE IMMEDIATE 'DROP TABLE {m.TABLE_NAME} PURGE'; "
                 f"EXCEPTION WHEN OTHERS THEN NULL; END;"):
        cur.execute(stmt)
    cur.execute(
        f"""CREATE TABLE ext_benchmark (
                seq_id NUMBER, category VARCHAR2(1), stars NUMBER,
                price NUMBER, reviews NUMBER, category_name VARCHAR2(4000))
            ORGANIZATION EXTERNAL (
                TYPE ORACLE_LOADER DEFAULT DIRECTORY {ORACLE_DIR_OBJ}
                ACCESS PARAMETERS (
                    RECORDS DELIMITED BY NEWLINE
                    SKIP 1
                    BADFILE {ORACLE_DIR_OBJ}:'bench.bad'
                    LOGFILE {ORACLE_DIR_OBJ}:'bench.log'
                    FIELDS TERMINATED BY ',' MISSING FIELD VALUES ARE NULL
                    (seq_id, category CHAR(1), stars, price, reviews,
                     category_name CHAR(4000)))
                LOCATION ('data.csv'))
            REJECT LIMIT UNLIMITED""")
    cur.execute(
        f"""CREATE TABLE {m.TABLE_NAME} (
                seq_id NUMBER, category VARCHAR2(1), stars NUMBER,
                price NUMBER, reviews NUMBER, category_name VARCHAR2(4000))
            TABLESPACE {ORACLE_TABLESPACE}""")
    cur.execute(f"INSERT /*+ APPEND */ INTO {m.TABLE_NAME} "
                f"SELECT * FROM ext_benchmark")
    conn.commit()
    cur.execute(f"SELECT COUNT(*) FROM {m.TABLE_NAME}")
    cnt = cur.fetchone()[0]
    conn.close()
    assert cnt == size, f"oracle direct load {cnt:,} != {size:,}"


# ----------------------------------------------------------------------
# phases
# ----------------------------------------------------------------------
def engine_phase(sizes, patterns, out_dir, walls, *, force: bool = False) -> list:
    m.OUTPUT_DIR, m.PATTERNS = out_dir, patterns
    # Free the DB containers' resident memory (esp. Oracle's SGA) so the engine
    # gets the full host RAM: on the system daemon the containers hold host
    # memory directly (no lazy VM), so a running DB would compete with the
    # engine at the largest sizes.
    m.docker_stop("trino-473", "oracle-21c-ee")
    summary = out_dir / f"matrix_{CPUS}cpu_{MEMORY_GB}gb_summary.csv"
    done = set() if force else completed_sizes(summary, patterns)
    if done:
        print(f"  engine resume: skipping {sorted(done)}")
    results = []
    for size in sizes:
        if size in done:
            continue
        try:
            r, _ = m.run_pandas_system([size], WARMUPS, MEASURED)
            results.extend(r)
        except Exception as exc:  # noqa: BLE001
            walls[f"pandas@{size}"] = f"{type(exc).__name__}: {exc}"
            print(f"    !! engine wall at {size:,}: {exc}")
            traceback.print_exc()
    return results


def trino_phase(sizes, patterns, out_dir, walls) -> None:
    m.docker_stop("oracle-21c-ee")
    done = completed_sizes(out_dir / "trino_results.csv", patterns)
    if done:
        print(f"  trino resume: skipping {sorted(done)}")
    for size in sizes:
        if size in done:
            continue
        rows: list = []
        try:
            trino_restart()
            ensure_trino_hive()
            df = m.load_input(size)
            t0 = time.monotonic()
            try:
                load_trino_disk(df, size)
            except ServerWedged as exc:
                walls[f"trino@{size}:load"] = str(exc)
                print(f"    !! trino LOAD wall at {size:,}: {exc}")
                print("       larger sizes cannot load either; stopping Trino")
                merge_results(out_dir, "trino", rows)
                break
            print(f"    load {size:,}: {time.monotonic()-t0:.0f}s (disk/Parquet)")
            conn = connect_trino_disk()
            cur = conn.cursor()
            m.OUTPUT_DIR, m.PATTERNS = out_dir, patterns
            for pattern in patterns:
                if pattern == "high_density_all_rows" and size > ALL_ROWS_CAP:
                    continue
                try:
                    run_cell("trino", cur, pattern, size, out_dir, rows,
                             patterns)
                except ServerWedged as exc:
                    walls[f"trino@{size}:{pattern}"] = str(exc)
                    print(f"    !! trino wedged on {pattern}@{size:,}; "
                          f"abandoning this size, fresh restart for the next")
                    break
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - a wedged conn need not close
                pass
        except Exception as exc:  # noqa: BLE001 - each size is independent
            walls[f"trino@{size}"] = f"{type(exc).__name__}: {exc}"
            print(f"    !! trino wall at {size:,}: {exc}")
            traceback.print_exc()
        merge_results(out_dir, "trino", rows)


def oracle_phase(sizes, patterns, out_dir, walls) -> None:
    m.docker_stop("trino-473")
    done = completed_sizes(out_dir / "oracle_results.csv", patterns)
    if done:
        print(f"  oracle resume: skipping {sorted(done)}")
    for size in sizes:
        if size in done:
            continue
        rows: list = []
        try:
            oracle_restart()
            oracle_ensure_setup()
            t0 = time.monotonic()
            try:
                oracle_direct_load(size)
            except Exception as exc:  # noqa: BLE001
                # cannot even load this size (edition/disk/tablespace wall):
                # no larger size can either, so record and stop Oracle.
                walls[f"oracle@{size}:load"] = f"{type(exc).__name__}: {exc}"
                print(f"    !! oracle LOAD wall at {size:,}: {exc}")
                print("       larger sizes cannot load either; stopping Oracle")
                merge_results(out_dir, "oracle", rows)
                break
            print(f"    load {size:,}: {time.monotonic()-t0:.0f}s (direct-path)")
            conn = m.connect_oracle(PASSWORD, DSN)
            cur = conn.cursor()
            m.OUTPUT_DIR, m.PATTERNS = out_dir, patterns
            for pattern in patterns:
                if pattern == "high_density_all_rows" and size > ALL_ROWS_CAP:
                    continue
                try:
                    run_cell("oracle", cur, pattern, size, out_dir, rows,
                             patterns)
                except ServerWedged as exc:
                    walls[f"oracle@{size}:{pattern}"] = str(exc)
                    print(f"    !! oracle wedged on {pattern}@{size:,}; "
                          f"abandoning this size, fresh restart for the next")
                    break
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001 - each size is independent
            walls[f"oracle@{size}"] = f"{type(exc).__name__}: {exc}"
            print(f"    !! oracle wall at {size:,}: {exc}")
            traceback.print_exc()
        merge_results(out_dir, "oracle", rows)


def main() -> None:
    m.ensure_dedicated_cgroup()
    parser = argparse.ArgumentParser(
        description="Run the large-volume and pattern-complexity stress suites.")
    parser.add_argument(
        "--systems", nargs="+", choices=["pandas", "trino", "oracle"],
        default=["pandas", "trino", "oracle"],
        help="systems to run; unselected result files are left unchanged")
    parser.add_argument(
        "--suites", nargs="+", choices=["volume", "pattern"],
        default=["volume", "pattern"],
        help="stress suites to run")
    parser.add_argument(
        "--force-engine", action="store_true",
        help="rerun completed Pandas sizes instead of resuming them")
    args = parser.parse_args()

    m.apply_local_limits(CPUS, MEMORY_GB)
    m.DATASET_DIR = DATASETS
    # Every DB fetch (probe, warmup, measured) and every Trino INSERT batch
    # goes through a bounded wrapper so a GC-wedged coordinator can never hang
    # the run forever.
    m.fetch_dataframe = bounded_fetch
    m.trino_execute = bounded_trino_execute
    sizes = load_sizes()
    print("stress sizes:", [f"{s:,}" for s in sizes])
    if "trino" in args.systems or "oracle" in args.systems:
        apply_deployment_fixes()
    walls: dict[str, str] = {}

    # The PATTERN suite is a pattern-COMPLEXITY probe (PERMUTE 6->120 orderings,
    # deep nesting), not a scaling probe -- the VOLUME suite already covers
    # scaling to 227.9M for all three systems.  Its message is fully made by
    # 80M, and PERMUTE at 160M/227.9M costs ~a day on the engine alone plus days
    # on the databases, so cap it at 80M.
    PATTERN_MAX = 80_000_000
    for out_dir, patterns, label, suite_sizes in (
            (OUT_VOLUME, VOLUME_PATTERNS, "volume", sizes),
            (OUT_PATTERN, STRESS_PATTERNS, "pattern",
             [s for s in sizes if s <= PATTERN_MAX])):
        if label not in args.suites:
            continue
        print(f"\n########## {label.upper()} suite ##########  sizes="
              f"{[f'{s:,}' for s in suite_sizes]}")
        out_dir.mkdir(parents=True, exist_ok=True)
        if "pandas" in args.systems:
            results = engine_phase(
                suite_sizes, patterns, out_dir, walls,
                force=args.force_engine)
            if results:
                m.write_summary(results, argparse.Namespace(
                    systems=["pandas"], sizes=suite_sizes, cpus=CPUS,
                    memory_gb=MEMORY_GB, warmup_runs=WARMUPS,
                    measured_runs=MEASURED, chunk_size=CHUNK_TRINO))
        if "trino" in args.systems:
            trino_phase(suite_sizes, patterns, out_dir, walls)
        if "oracle" in args.systems:
            oracle_phase(suite_sizes, patterns, out_dir, walls)
        if "trino" in args.systems or "oracle" in args.systems:
            (out_dir / "walls.json").write_text(json.dumps(
                {"timestamp": datetime.now().isoformat(timespec="seconds"),
                 "memory_gb": MEMORY_GB, "walls": walls}, indent=2))

    print("\nStress test complete; walls:", walls or "none hit")


if __name__ == "__main__":
    main()
