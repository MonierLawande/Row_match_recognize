#!/usr/bin/env python3
"""Worst-case coverage experiment (pattern-driven axis).

The cross-system matrix and the ordered/shuffled scenarios exercise the
input-scaling axis (best case Theta(n); worst case O(n log n) when a sort is
forced).  This script exercises the OTHER axis on the same Amazon dataset:
a state-dependent DEFINE predicate (a running aggregate, AVG(A.price)) that
cannot be vectorised, so the engine falls back to its exact preference-ordered
backtracking searcher -- the true algorithmic worst case, bounded by the
200,000-step budget.  It measures the row-local fast path (best case) against
the state-dependent query (worst case) at several sizes on the pandas engine,
saves a CSV, and renders viz_worstcase_coverage.png.
"""
import sys, os, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, NullFormatter
from src.matcher.matcher import EnhancedMatcher
from src.executor.match_recognize import match_recognize

HERE = os.path.dirname(os.path.abspath(__file__))
DATADIR = os.path.join(HERE, "cross_system_matrix", "datasets")
IMG = os.path.abspath(os.path.join(HERE, "..", "thesis", "images"))
SIZES = [50000, 100000, 200000, 400000]

# count backtracking-searcher invocations (proves the non-vectorised path)
_bt = {"n": 0}
if hasattr(EnhancedMatcher, "_find_single_match_condition_backtracking"):
    _orig = EnhancedMatcher._find_single_match_condition_backtracking
    def _wrap(self, *a, **k):
        _bt["n"] += 1
        return _orig(self, *a, **k)
    EnhancedMatcher._find_single_match_condition_backtracking = _wrap

ROW_LOCAL = "PATTERN (A+ B+) DEFINE A AS category='A', B AS category='B'"
STATE_DEP = ("PATTERN (A+ B+) DEFINE A AS category='A', "
             "B AS category='B' AND price > AVG(A.price)")


def q(body):
    return ("SELECT * FROM t MATCH_RECOGNIZE (ORDER BY seq_id "
            "MEASURES FIRST(seq_id) AS s, COUNT(*) AS n ONE ROW PER MATCH "
            f"{body})")


def best_of(df, body, reps=3):
    times = []
    _bt["n"] = 0
    for _ in range(reps):
        t = time.perf_counter()
        r = match_recognize(q(body), df)
        times.append(time.perf_counter() - t)
    return min(times), len(r), _bt["n"]


rows = []
for n in SIZES:
    df = pd.read_csv(os.path.join(DATADIR, f"benchmark_{n}.csv"))
    rl_t, rl_r, _ = best_of(df, ROW_LOCAL)
    sd_t, sd_r, bt = best_of(df, STATE_DEP)
    rows.append({"size": n, "rowlocal_s": rl_t, "statedep_s": sd_t,
                 "slowdown": sd_t / rl_t, "rowlocal_rows": rl_r,
                 "statedep_rows": sd_r, "bt_calls": bt})
    print(f"{n:>8}: rowlocal {rl_t:.3f}s  statedep {sd_t:.3f}s  "
          f"{sd_t/rl_t:.1f}x  bt={bt}")

res = pd.DataFrame(rows)
res.to_csv(os.path.join(HERE, "worstcase_coverage.csv"), index=False)

# ---- figure: best case vs pattern-driven worst case (log-log) ----
plt.rcParams.update({"font.family": "serif", "font.size": 9,
                     "axes.edgecolor": "#888888", "axes.linewidth": 0.7,
                     "grid.color": "#dddddd", "savefig.dpi": 200})
size_fmt = FuncFormatter(lambda v, _: f"{int(v/1e3)}K")
fig, ax = plt.subplots(figsize=(6.6, 4.2))
ax.plot(res["size"], res["rowlocal_s"], color="#2a78d6", marker="o",
        markersize=6, linewidth=2, markeredgecolor="white",
        label="Row-local fast path (best case, $\\Theta(n)$)")
ax.plot(res["size"], res["statedep_s"], color="#e34948", marker="s",
        markersize=6, linewidth=2, markeredgecolor="white",
        label="State-dependent DEFINE (pattern-driven worst case)")
for x, y in zip(res["size"], res["statedep_s"]):
    ax.annotate(f"{y:.1f}s", (x, y), textcoords="offset points",
                xytext=(0, 7), ha="center", fontsize=7.5, color="#e34948")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xticks(SIZES); ax.xaxis.set_major_formatter(size_fmt)
ax.xaxis.set_minor_formatter(NullFormatter())
ax.set_xlabel("Dataset size (rows, log scale)")
ax.set_ylabel("Pandas-engine time (s, log scale)")
ax.grid(True, which="major"); ax.grid(True, which="minor", alpha=0.3)
ax.legend(frameon=False, fontsize=8.5, loc="upper left")
ax.set_title("Same query shape, with vs without a state-dependent DEFINE",
             fontsize=9.5)
fig.tight_layout()
fig.savefig(os.path.join(IMG, "viz_worstcase_coverage.png"), bbox_inches="tight")
plt.close(fig)
print("wrote worstcase_coverage.csv and viz_worstcase_coverage.png")
