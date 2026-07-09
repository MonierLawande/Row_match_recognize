"""
Faithful, value-asserting conversions of Trino reference test cases that the
existing tests/ files did not cover (or covered without value assertions).

Sources (exact expected values copied from the Java assertions):
  - src/TestRowPatternMatching.java :: testPatternQuantifiers  (32 cases)
  - src/TestRowPatternMatching.java :: testNavigationFunctions (23 cases)

Every case asserts the full expected output, row by row, like the Java
`.matches(VALUES ...)` blocks.  NULL columns are asserted with pd.isna.
"""

import sys
import os

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.executor.match_recognize import match_recognize


def run_query(query: str, df: pd.DataFrame) -> pd.DataFrame:
    result = match_recognize(query, df)
    assert result is not None
    return result.reset_index(drop=True)


def assert_rows(result: pd.DataFrame, expected_rows, columns):
    """Assert full result contents. None in expected means SQL NULL."""
    assert len(result) == len(expected_rows), (
        f"row count {len(result)} != expected {len(expected_rows)}\n{result}"
    )
    for i, expected in enumerate(expected_rows):
        for col, exp_val in zip(columns, expected):
            actual = result.iloc[i][col]
            if exp_val is None:
                assert actual is None or pd.isna(actual), (
                    f"row {i} col {col}: expected NULL, got {actual!r}\n{result}"
                )
            else:
                assert actual == exp_val, (
                    f"row {i} col {col}: expected {exp_val!r}, got {actual!r}\n{result}"
                )


# ----------------------------------------------------------------------------
# testPatternQuantifiers: 4-row dataset, DEFINE B AS B.value <= PREV(B.value)
# ----------------------------------------------------------------------------

QUANTIFIER_QUERY = """
SELECT m.id AS row_id, m.match, m.val, m.label
FROM data
MATCH_RECOGNIZE (
    ORDER BY id
    MEASURES
        match_number() AS match,
        RUNNING LAST(value) AS val,
        classifier() AS label
    ALL ROWS PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN ({pattern})
    DEFINE B AS B.value <= PREV (B.value)
) AS m
"""

# (pattern, expected rows of (row_id, match, val, label))  — exact Java values
QUANTIFIER_CASES = [
    ("B*", [(1, 1, None, None), (2, 2, 80, "B"), (3, 2, 70, "B"), (4, 2, 70, "B")]),
    ("B*?", [(1, 1, None, None), (2, 2, None, None), (3, 3, None, None), (4, 4, None, None)]),
    ("B+", [(2, 1, 80, "B"), (3, 1, 70, "B"), (4, 1, 70, "B")]),
    ("B+?", [(2, 1, 80, "B"), (3, 2, 70, "B"), (4, 3, 70, "B")]),
    ("B?", [(1, 1, None, None), (2, 2, 80, "B"), (3, 3, 70, "B"), (4, 4, 70, "B")]),
    ("B??", [(1, 1, None, None), (2, 2, None, None), (3, 3, None, None), (4, 4, None, None)]),
    ("B{,}", [(1, 1, None, None), (2, 2, 80, "B"), (3, 2, 70, "B"), (4, 2, 70, "B")]),
    ("B{,}?", [(1, 1, None, None), (2, 2, None, None), (3, 3, None, None), (4, 4, None, None)]),
    ("B{1,}", [(2, 1, 80, "B"), (3, 1, 70, "B"), (4, 1, 70, "B")]),
    ("B{1,}?", [(2, 1, 80, "B"), (3, 2, 70, "B"), (4, 3, 70, "B")]),
    ("B{2,}", [(2, 1, 80, "B"), (3, 1, 70, "B"), (4, 1, 70, "B")]),
    ("B{2,}?", [(2, 1, 80, "B"), (3, 1, 70, "B")]),
    ("B{5,}", []),
    ("B{5,}?", []),
    ("B{,1}", [(1, 1, None, None), (2, 2, 80, "B"), (3, 3, 70, "B"), (4, 4, 70, "B")]),
    ("B{,1}?", [(1, 1, None, None), (2, 2, None, None), (3, 3, None, None), (4, 4, None, None)]),
    ("B{,2}", [(1, 1, None, None), (2, 2, 80, "B"), (3, 2, 70, "B"), (4, 3, 70, "B")]),
    ("B{,2}?", [(1, 1, None, None), (2, 2, None, None), (3, 3, None, None), (4, 4, None, None)]),
    ("B{,5}", [(1, 1, None, None), (2, 2, 80, "B"), (3, 2, 70, "B"), (4, 2, 70, "B")]),
    ("B{,5}?", [(1, 1, None, None), (2, 2, None, None), (3, 3, None, None), (4, 4, None, None)]),
    ("B{1,1}", [(2, 1, 80, "B"), (3, 2, 70, "B"), (4, 3, 70, "B")]),
    ("B{1,1}?", [(2, 1, 80, "B"), (3, 2, 70, "B"), (4, 3, 70, "B")]),
    ("B{1,5}", [(2, 1, 80, "B"), (3, 1, 70, "B"), (4, 1, 70, "B")]),
    ("B{1,5}?", [(2, 1, 80, "B"), (3, 2, 70, "B"), (4, 3, 70, "B")]),
    ("B{5,7}", []),
    ("B{5,7}?", []),
    ("B{1}", [(2, 1, 80, "B"), (3, 2, 70, "B"), (4, 3, 70, "B")]),
    ("B{1}?", [(2, 1, 80, "B"), (3, 2, 70, "B"), (4, 3, 70, "B")]),
    ("B{2}", [(2, 1, 80, "B"), (3, 1, 70, "B")]),
    ("B{2}?", [(2, 1, 80, "B"), (3, 1, 70, "B")]),
    ("B{5}", []),
    ("B{5}?", []),
]


class TestPatternQuantifiersJavaMatrix:
    """testPatternQuantifiers from TestRowPatternMatching.java, all 32 cases."""

    @pytest.fixture
    def df(self):
        return pd.DataFrame({"id": [1, 2, 3, 4], "value": [90, 80, 70, 70]})

    @pytest.mark.parametrize("pattern,expected", QUANTIFIER_CASES,
                             ids=[c[0] for c in QUANTIFIER_CASES])
    def test_quantifier(self, df, pattern, expected):
        result = run_query(QUANTIFIER_QUERY.format(pattern=pattern), df)
        assert_rows(result, expected, ["row_id", "match", "val", "label"])


# ----------------------------------------------------------------------------
# testNavigationFunctions: measures over (10, 20, 30), PATTERN (A+)
# ----------------------------------------------------------------------------

NAVIGATION_QUERY = """
SELECT m.id, m.measure
FROM data
MATCH_RECOGNIZE (
    ORDER BY id
    MEASURES {measure} AS measure
    ALL ROWS PER MATCH
    PATTERN (A+)
    DEFINE A AS true
) AS m
"""

NAVIGATION_CASES = [
    ("value", [10, 20, 30]),                      # defaults to RUNNING LAST
    ("LAST(value)", [10, 20, 30]),
    ("RUNNING LAST(value)", [10, 20, 30]),
    ("FINAL LAST(value)", [30, 30, 30]),
    ("FIRST(value)", [10, 10, 10]),
    ("RUNNING FIRST(value)", [10, 10, 10]),
    ("FINAL FIRST(value)", [10, 10, 10]),
    ("FINAL LAST(value, 2)", [10, 10, 10]),       # logical offset
    ("FIRST(value, 2)", [30, 30, 30]),
    ("LAST(value, 10)", [None, None, None]),
    ("FIRST(value, 10)", [None, None, None]),
    ("PREV(value)", [None, 10, 20]),              # physical offset
    ("NEXT(value)", [20, 30, None]),
    ("NEXT(FIRST(value), 2)", [30, 30, 30]),
    ("NEXT(FIRST(value), 10)", [None, None, None]),
    ("PREV(FIRST(value), 10)", [None, None, None]),
    ("PREV(FIRST(value, 10), 2)", [None, None, None]),
    ("PREV(LAST(value, 10), 2)", [None, None, None]),
]

# lookup outside the match but within the partition: rows 3,4 are the only
# match (A=3, B=4); navigation starts from row 4 (last row matched to B).
NAVIGATION_PARTITION_QUERY = """
SELECT m.measure
FROM data
MATCH_RECOGNIZE (
    ORDER BY id
    MEASURES {measure} AS measure
    ONE ROW PER MATCH
    PATTERN (A B)
    DEFINE B AS B.value = PREV(B.value)
) AS m
"""

NAVIGATION_PARTITION_CASES = [
    ("PREV(B.value, 4)", None),   # before partition start
    ("PREV(B.value, 3)", 10),     # out of match, within partition
    ("PREV(B.value, 2)", 20),
    ("NEXT(B.value, 1)", 40),
    ("NEXT(B.value, 2)", None),   # past partition end
]


class TestNavigationFunctionsJavaMatrix:
    """testNavigationFunctions from TestRowPatternMatching.java, all 23 cases."""

    @pytest.fixture
    def df(self):
        return pd.DataFrame({"id": [1, 2, 3], "value": [10, 20, 30]})

    @pytest.fixture
    def df5(self):
        return pd.DataFrame({"id": [1, 2, 3, 4, 5], "value": [10, 20, 30, 30, 40]})

    @pytest.mark.parametrize("measure,expected", NAVIGATION_CASES,
                             ids=[c[0] for c in NAVIGATION_CASES])
    def test_navigation_measure(self, df, measure, expected):
        result = run_query(NAVIGATION_QUERY.format(measure=measure), df)
        expected_rows = [(i + 1, v) for i, v in enumerate(expected)]
        assert_rows(result, expected_rows, ["id", "measure"])

    @pytest.mark.parametrize("measure,expected", NAVIGATION_PARTITION_CASES,
                             ids=[c[0] for c in NAVIGATION_PARTITION_CASES])
    def test_navigation_outside_match(self, df5, measure, expected):
        result = run_query(NAVIGATION_PARTITION_QUERY.format(measure=measure), df5)
        assert_rows(result, [(expected,)], ["measure"])
