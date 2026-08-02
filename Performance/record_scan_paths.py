#!/usr/bin/env python3
"""Record which candidate-scan path the engine takes, per pattern and size.

The evaluation reports how much of the frozen query budget the candidate-start
transient claims, and at which sizes the scan switches from full
materialisation to a sliding window.  That decision is deterministic given the
input and the resolved budget, so it can be reproduced without repeating a
timed campaign: one execution per cell is enough.

    python Performance/record_scan_paths.py --sizes 80000000 160000000

Writes scan_paths.json next to the stress results and prints a summary.
Timing printed here is a single untimed execution and is not a benchmark
figure; use the stress campaign for those.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Performance.run_cross_system_matrix as m  # noqa: E402
import Performance.stress_test.run_stress_test as stress  # noqa: E402
from src.matcher.matcher import EnhancedMatcher  # noqa: E402

RECORDS: list[dict] = []
_original = EnhancedMatcher._candidate_window_size


def _recording_window_size(self, count):
    """Wrap the sizing decision and record what it chose."""
    size = _original(self, count)
    try:
        budget = self._resource_profile.query_budget_bytes
    except Exception:  # noqa: BLE001 - the profile is always present in practice
        budget = 0
    entry = self._CANDIDATE_ENTRY_BYTES
    full = size == count
    transient = (count if full else size) * entry
    RECORDS.append({
        "candidates": int(count),
        "scan_path": "full" if full else "windowed",
        "window_entries": None if full else int(size),
        "query_budget_bytes": int(budget),
        "full_list_bytes_est": int(count * entry),
        "transient_bytes_est": int(transient),
        "full_list_pct_of_budget": round(100.0 * count * entry / budget, 3) if budget else None,
        "transient_pct_of_budget": round(100.0 * transient / budget, 3) if budget else None,
    })
    return size


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="+", type=int,
                    default=[5_000_000, 80_000_000, 160_000_000, 227_899_533])
    ap.add_argument("--out", default=str(ROOT / "Performance/stress_test/volume/scan_paths.json"))
    args = ap.parse_args()

    m.DATASET_DIR = stress.DATASETS
    m.PATTERNS = stress.VOLUME_PATTERNS
    EnhancedMatcher._candidate_window_size = _recording_window_size

    rows = []
    for size in args.sizes:
        df = m.load_input(size)
        for name in stress.VOLUME_PATTERNS:
            query = m.query_for_system("pandas", name)
            RECORDS.clear()
            t0 = time.monotonic()
            from src.executor.match_recognize import match_recognize
            out = match_recognize(query, df)
            elapsed = time.monotonic() - t0
            for rec in RECORDS:
                rows.append({"rows_in": int(size), "pattern": name,
                             "matches": int(len(out)), "elapsed_s": round(elapsed, 4),
                             **rec})
            last = RECORDS[-1] if RECORDS else {}
            print(f"{name:18} {size:>12,}  path={last.get('scan_path','-'):9} "
                  f"cand={last.get('candidates',0):>12,} "
                  f"({last.get('candidates',0)/size:.3f} of rows)  "
                  f"full={last.get('full_list_pct_of_budget')}% of budget  "
                  f"transient={last.get('transient_pct_of_budget')}%", flush=True)
        del df

    Path(args.out).write_text(json.dumps(rows, indent=1))
    print(f"\nwrote {args.out} ({len(rows)} records)")
    if rows:
        t = pd.DataFrame(rows)
        print(t.groupby(["rows_in", "scan_path"]).size().to_string())


if __name__ == "__main__":
    main()
