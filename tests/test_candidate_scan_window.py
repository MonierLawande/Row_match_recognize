"""Candidate-start scan sizing and windowed-scan equivalence.

The fast one-row scan materialises the sorted candidate-start array as a Python
list to remove NumPy scalar boxing.  That transient scales with the number of
candidates, so it is sized against the frozen per-query budget: the full list
when it comfortably fits, a bounded sliding window when it does not.

Every test here is machine independent.  The sizing tests inject the budget
directly, the equivalence tests force the windowed path by shrinking the class
constants rather than by relying on the host's real memory, and none of them
assert on timing.
"""

import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.executor.match_recognize import match_recognize
from src.matcher.matcher import EnhancedMatcher

MIB = 1024 ** 2


class _SizerStub:
    """Minimal stand-in carrying only what ``_candidate_window_size`` reads."""

    _CANDIDATE_ENTRY_BYTES = EnhancedMatcher._CANDIDATE_ENTRY_BYTES
    _CANDIDATE_FULL_BUDGET_FRACTION = EnhancedMatcher._CANDIDATE_FULL_BUDGET_FRACTION
    _CANDIDATE_WINDOW_BUDGET_FRACTION = EnhancedMatcher._CANDIDATE_WINDOW_BUDGET_FRACTION
    _CANDIDATE_WINDOW_MIN = EnhancedMatcher._CANDIDATE_WINDOW_MIN

    def __init__(self, budget):
        self._resource_profile = SimpleNamespace(query_budget_bytes=budget)


def window_size(budget, count):
    return EnhancedMatcher._candidate_window_size(_SizerStub(budget), count)


# --------------------------------------------------------------------------
# sizing
# --------------------------------------------------------------------------

def test_zero_candidates_need_no_window():
    assert window_size(16 * 1024 * MIB, 0) == 0


def test_large_budget_keeps_the_full_list():
    # 1 M candidates = 40 MB, far inside a quarter of a 16 GiB budget.
    assert window_size(16 * 1024 * MIB, 1_000_000) == 1_000_000


def test_small_budget_falls_back_to_a_bounded_window():
    budget = 64 * MIB
    size = window_size(budget, 5_000_000)
    assert size < 5_000_000
    assert size * EnhancedMatcher._CANDIDATE_ENTRY_BYTES < budget


def test_window_never_drops_below_the_floor():
    assert window_size(1 * MIB, 10_000_000) == EnhancedMatcher._CANDIDATE_WINDOW_MIN


def test_window_never_exceeds_the_candidate_count():
    assert window_size(1 * MIB, 17) == 17


def test_unknown_budget_fails_closed_to_a_window():
    # A profile that reports no budget must not authorise a full materialisation.
    assert window_size(0, 10_000_000) == EnhancedMatcher._CANDIDATE_WINDOW_MIN


def test_missing_profile_fails_closed_to_a_window():
    class _NoProfile:
        _CANDIDATE_ENTRY_BYTES = EnhancedMatcher._CANDIDATE_ENTRY_BYTES
        _CANDIDATE_FULL_BUDGET_FRACTION = EnhancedMatcher._CANDIDATE_FULL_BUDGET_FRACTION
        _CANDIDATE_WINDOW_BUDGET_FRACTION = EnhancedMatcher._CANDIDATE_WINDOW_BUDGET_FRACTION
        _CANDIDATE_WINDOW_MIN = EnhancedMatcher._CANDIDATE_WINDOW_MIN

        @property
        def _resource_profile(self):
            raise AttributeError("no profile")

    size = EnhancedMatcher._candidate_window_size(_NoProfile(), 10_000_000)
    assert size == EnhancedMatcher._CANDIDATE_WINDOW_MIN


def test_sizing_is_monotone_in_the_budget():
    counts = 8_000_000
    sizes = [window_size(b * MIB, counts) for b in (1, 8, 64, 512, 4096, 65536)]
    assert sizes == sorted(sizes)
    assert sizes[-1] == counts


def test_a_reduced_budget_reduces_the_window():
    # The sizing is a pure function of the frozen budget, so a later query in a
    # tighter envelope is windowed even though an earlier one was not.
    assert window_size(16 * 1024 * MIB, 2_000_000) == 2_000_000
    assert window_size(32 * MIB, 2_000_000) < 2_000_000


# --------------------------------------------------------------------------
# end-to-end equivalence between the full and the windowed scan
# --------------------------------------------------------------------------

SIMPLE = """SELECT * FROM data MATCH_RECOGNIZE (ORDER BY seq_id
  MEASURES FIRST(A.seq_id) AS start_row, LAST(B.seq_id) AS end_row,
           COUNT(*) AS match_length, CLASSIFIER() AS cls, MATCH_NUMBER() AS mno
  ONE ROW PER MATCH PATTERN (A+ B+)
  DEFINE A AS category = 'A', B AS category = 'B')"""

NESTED = """SELECT * FROM data MATCH_RECOGNIZE (ORDER BY seq_id
  MEASURES FIRST(A.seq_id) AS start_row, COUNT(*) AS match_length
  ONE ROW PER MATCH PATTERN ((A|B)+ (C{1,3} D*)+)
  DEFINE A AS category='A', B AS category='B', C AS category='C', D AS category='D')"""

PARTITIONED = """SELECT * FROM data MATCH_RECOGNIZE (PARTITION BY part ORDER BY seq_id
  MEASURES FIRST(A.seq_id) AS start_row, COUNT(*) AS match_length
  ONE ROW PER MATCH PATTERN (A+ B+)
  DEFINE A AS category='A', B AS category='B')"""

ALL_ROWS = """SELECT * FROM data MATCH_RECOGNIZE (ORDER BY seq_id
  MEASURES CLASSIFIER() AS cls, MATCH_NUMBER() AS mno
  ALL ROWS PER MATCH PATTERN (A+ B+)
  DEFINE A AS category='A', B AS category='B')"""

SKIP_PAST = """SELECT * FROM data MATCH_RECOGNIZE (ORDER BY seq_id
  MEASURES FIRST(A.seq_id) AS start_row, COUNT(*) AS match_length
  ONE ROW PER MATCH AFTER MATCH SKIP PAST LAST ROW PATTERN (A+ B+)
  DEFINE A AS category='A', B AS category='B')"""

SKIP_TO_NEXT = """SELECT * FROM data MATCH_RECOGNIZE (ORDER BY seq_id
  MEASURES FIRST(A.seq_id) AS start_row, COUNT(*) AS match_length
  ONE ROW PER MATCH AFTER MATCH SKIP TO NEXT ROW PATTERN (A+ B+)
  DEFINE A AS category='A', B AS category='B')"""


def frame(n, categories, seed=20260727, parts=0):
    rng = np.random.default_rng(seed)
    data = {
        "seq_id": np.arange(n),
        "category": rng.choice(list(categories), size=n),
        "price": np.round(rng.random(n) * 100, 2),
    }
    if parts:
        data["part"] = np.arange(n) % parts
    return pd.DataFrame(data)


def normalise(df):
    out = df.copy()
    for col in out.columns:
        out[col] = out[col].astype(str)
    cols = sorted(out.columns)
    return out.reindex(cols, axis=1).sort_values(cols, kind="mergesort").reset_index(drop=True)


@pytest.fixture
def windowed(monkeypatch):
    """Force the windowed scan with tiny windows, so refills happen often."""
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_FULL_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_MIN", 3)


def run_both_paths(query, df, monkeypatch):
    """Result on the full path and on a heavily refilled windowed path."""
    full = match_recognize(query, df)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_FULL_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_MIN", 3)
    win = match_recognize(query, df)
    monkeypatch.undo()
    return full, win


def assert_same(full, win):
    assert list(full.columns) == list(win.columns)
    assert len(full) == len(win)
    pd.testing.assert_frame_equal(normalise(full), normalise(win))


@pytest.mark.parametrize("query", [SIMPLE, NESTED, ALL_ROWS, SKIP_PAST, SKIP_TO_NEXT])
def test_dense_candidates_identical_on_both_paths(query, monkeypatch):
    df = frame(4000, "AABBCD")
    assert_same(*run_both_paths(query, df, monkeypatch))


def test_sparse_candidates_identical_on_both_paths(monkeypatch):
    # 'A' on roughly one row in twelve: few candidates, many window refills.
    df = frame(4000, "ACCCCCCCCCCB")
    assert_same(*run_both_paths(SIMPLE, df, monkeypatch))


def test_zero_candidates_identical_on_both_paths(monkeypatch):
    df = frame(2000, "CD")
    full, win = run_both_paths(SIMPLE, df, monkeypatch)
    assert len(full) == 0
    assert_same(full, win)


def test_single_candidate_identical_on_both_paths(monkeypatch):
    df = pd.DataFrame({
        "seq_id": np.arange(50),
        "category": ["C"] * 20 + ["A", "B"] + ["C"] * 28,
        "price": np.arange(50, dtype=float),
    })
    full, win = run_both_paths(SIMPLE, df, monkeypatch)
    assert len(full) == 1
    assert_same(full, win)


def test_every_row_is_a_candidate_identical_on_both_paths(monkeypatch):
    df = pd.DataFrame({
        "seq_id": np.arange(600),
        "category": ["A", "B"] * 300,
        "price": np.arange(600, dtype=float),
    })
    assert_same(*run_both_paths(SIMPLE, df, monkeypatch))


def test_multiple_partitions_identical_on_both_paths(monkeypatch):
    df = frame(3000, "AABBCD", parts=16)
    assert_same(*run_both_paths(PARTITIONED, df, monkeypatch))


def test_empty_frame_identical_on_both_paths(monkeypatch):
    df = pd.DataFrame({"seq_id": [], "category": [], "price": []})
    full, win = run_both_paths(SIMPLE, df, monkeypatch)
    assert len(full) == 0 and len(win) == 0


def test_cache_hit_and_cache_miss_agree_on_the_windowed_path(windowed):
    df = frame(3000, "AABBCD")
    from src.utils.pattern_cache import clear_pattern_cache

    clear_pattern_cache()
    miss = match_recognize(SIMPLE, df)      # cold compile
    hit = match_recognize(SIMPLE, df)       # cached automaton
    assert_same(miss, hit)


def test_cache_built_on_one_path_is_safe_to_reuse_on_the_other(monkeypatch):
    """A budget change between queries must not reuse a wrong-shaped result."""
    df = frame(3000, "AABBCD")
    from src.utils.pattern_cache import clear_pattern_cache

    clear_pattern_cache()
    full_first = match_recognize(SIMPLE, df)          # populate the cache, full path
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_FULL_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_MIN", 3)
    windowed_second = match_recognize(SIMPLE, df)     # same cache, windowed path
    assert_same(full_first, windowed_second)
    monkeypatch.undo()
    full_third = match_recognize(SIMPLE, df)          # back to the full path
    assert_same(full_first, full_third)


def test_repeated_queries_are_stable_on_the_windowed_path(windowed):
    df = frame(2500, "AABBCD")
    first = match_recognize(SIMPLE, df)
    for _ in range(4):
        assert_same(first, match_recognize(SIMPLE, df))


def test_window_of_one_still_matches_the_full_path(monkeypatch):
    """The smallest legal window refills on every single candidate."""
    df = frame(1200, "AABBCD")
    full = match_recognize(SIMPLE, df)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_FULL_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_MIN", 1)
    assert_same(full, match_recognize(SIMPLE, df))


def test_window_larger_than_the_candidate_list_matches_the_full_path(monkeypatch):
    df = frame(1200, "AABBCD")
    full = match_recognize(SIMPLE, df)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_FULL_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_BUDGET_FRACTION", 0.0)
    monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_MIN", 10 ** 9)
    assert_same(full, match_recognize(SIMPLE, df))


def test_sizing_is_not_cached_between_queries(monkeypatch):
    """Two queries in one process, two different envelopes, both correct."""
    df = frame(2000, "AABBCD")
    baseline = match_recognize(SIMPLE, df)
    for floor in (1, 7, 64, 10 ** 9):
        monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_FULL_BUDGET_FRACTION", 0.0)
        monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_BUDGET_FRACTION", 0.0)
        monkeypatch.setattr(EnhancedMatcher, "_CANDIDATE_WINDOW_MIN", floor)
        assert_same(baseline, match_recognize(SIMPLE, df))
        monkeypatch.undo()
