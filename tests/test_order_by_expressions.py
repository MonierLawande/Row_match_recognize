"""
Test Expressions in the MATCH_RECOGNIZE ORDER BY clause

SQL:2016 allows an ORDER BY item to be any value expression, not only a column
reference.  These tests cover the supported expression forms, confirm that an
expression key produces the same row order a manual sort would, and check that
the evaluator rejects anything outside its whitelist.
"""

import pytest
import pandas as pd
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.executor.match_recognize import (
    OrderExpressionError,
    _evaluate_order_expression,
    match_recognize,
)


def _frame():
    """Deliberately unsorted so ordering mistakes change the result."""
    return pd.DataFrame(
        {
            "id": [1, 1, 1, 1, 1, 1],
            "ts": [3, 1, 5, 2, 6, 4],
            "price": [30, 10, 50, 20, 60, 40],
            "name": ["c", "a", "e", "b", "f", "d"],
        }
    )


def _query(order_by, measures="FIRST(A.price) AS first_p, LAST(A.price) AS last_p"):
    return f"""
        SELECT * FROM t MATCH_RECOGNIZE (
            PARTITION BY id
            ORDER BY {order_by}
            MEASURES {measures}
            ONE ROW PER MATCH
            PATTERN (A+)
            DEFINE A AS price > 0
        )
    """


# ---------------------------------------------------------------------------
# Supported expression forms
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "order_by, expected_first, expected_last",
    [
        ("ts", 10, 60),
        ("ts * 2", 10, 60),
        ("ts + 100", 10, 60),
        ("-ts", 60, 10),
        ("ts * -1", 60, 10),
        ("ABS(ts)", 10, 60),
        ("SQRT(price)", 10, 60),
        ("POWER(ts, 2)", 10, 60),
        ("ROUND(price / 10)", 10, 60),
        ("UPPER(name)", 10, 60),
        ("LENGTH(name), ts", 10, 60),
        ("price / 10 DESC", 60, 10),
    ],
)
def test_expression_order_by_produces_expected_order(
    order_by, expected_first, expected_last
):
    result = match_recognize(_query(order_by), _frame())
    assert len(result) == 1
    assert result["first_p"].iloc[0] == expected_first
    assert result["last_p"].iloc[0] == expected_last


def test_monotonic_expression_matches_plain_column():
    """A strictly increasing transform must not change the row order."""
    frame = _frame()
    plain = match_recognize(_query("ts"), frame)
    scaled = match_recognize(_query("ts * 2"), frame)
    shifted = match_recognize(_query("ts + 7"), frame)
    assert plain.equals(scaled)
    assert plain.equals(shifted)


def test_expression_respects_desc_and_multiple_keys():
    frame = _frame()
    descending = match_recognize(_query("ts * 2 DESC"), frame)
    assert descending["first_p"].iloc[0] == 60
    assert descending["last_p"].iloc[0] == 10

    mixed = match_recognize(_query("MOD(ts, 2), ts"), frame)
    # Even ts first (2, 4, 6 -> 20, 40, 60), then odd (1, 3, 5).
    assert mixed["first_p"].iloc[0] == 20
    assert mixed["last_p"].iloc[0] == 50


def test_expression_order_is_applied_per_partition():
    frame = pd.DataFrame(
        {
            "id": [1, 1, 1, 2, 2, 2],
            "ts": [3, 1, 2, 6, 4, 5],
            "price": [30, 10, 20, 60, 40, 50],
        }
    )
    result = match_recognize(_query("ts * 2"), frame).sort_values("id")
    assert result["first_p"].tolist() == [10, 40]
    assert result["last_p"].tolist() == [30, 60]


def test_all_rows_per_match_is_sorted_and_leaks_no_key_columns():
    frame = _frame()
    sql = """
        SELECT * FROM t MATCH_RECOGNIZE (
            PARTITION BY id
            ORDER BY ts * 2
            MEASURES FIRST(A.price) AS first_p
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS price > 0
        )
    """
    result = match_recognize(sql, frame)
    assert result["ts"].tolist() == [1, 2, 3, 4, 5, 6]
    assert not [c for c in result.columns if "__mr_" in str(c)]


def test_expression_handles_nulls_with_explicit_placement():
    frame = pd.DataFrame(
        {
            "id": [1, 1, 1, 1],
            "ts": [2.0, None, 1.0, 3.0],
            "price": [20, 99, 10, 30],
        }
    )
    last = match_recognize(_query("ts * 2 NULLS LAST"), frame)
    assert last["first_p"].iloc[0] == 10
    assert last["last_p"].iloc[0] == 99

    first = match_recognize(_query("ts * 2 NULLS FIRST"), frame)
    assert first["first_p"].iloc[0] == 99
    assert first["last_p"].iloc[0] == 30


# ---------------------------------------------------------------------------
# Rejection of unsupported forms
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "order_by",
    [
        "nosuchcolumn",
        "nosuchcolumn * 2",
        "WEIRDFUNCTION(ts)",
        "__import__('os')",
    ],
)
def test_unsupported_order_by_raises(order_by):
    with pytest.raises(ValueError):
        match_recognize(_query(order_by), _frame())


def test_order_expression_error_is_a_value_error():
    assert issubclass(OrderExpressionError, ValueError)


@pytest.mark.parametrize(
    "expression",
    [
        "ts.values",           # attribute access
        "ts[0]",               # subscript
        "open('/etc/passwd')", # unknown function
        "[x for x in ts]",     # comprehension
        "lambda: 1",           # lambda
    ],
)
def test_evaluator_rejects_unsafe_constructs(expression):
    with pytest.raises(OrderExpressionError):
        _evaluate_order_expression(_frame(), expression)


def test_evaluator_rejects_overlong_expression():
    with pytest.raises(OrderExpressionError):
        _evaluate_order_expression(_frame(), "ts + " * 400 + "ts")


# ---------------------------------------------------------------------------
# The evaluator itself
# ---------------------------------------------------------------------------

def test_evaluator_returns_a_vectorized_series():
    frame = _frame()
    key = _evaluate_order_expression(frame, "ts * 2")
    assert isinstance(key, pd.Series)
    assert len(key) == len(frame)
    assert key.tolist() == [6, 2, 10, 4, 12, 8]


def test_evaluator_resolves_columns_case_insensitively():
    frame = _frame()
    assert _evaluate_order_expression(frame, "TS * 2").tolist() == [6, 2, 10, 4, 12, 8]


def test_evaluator_folds_constants_to_full_length():
    frame = _frame()
    key = _evaluate_order_expression(frame, "1")
    assert len(key) == len(frame)
    assert key.nunique() == 1


def test_evaluator_supports_coalesce():
    frame = pd.DataFrame({"a": [1.0, None, 3.0], "b": [9.0, 8.0, 7.0]})
    assert _evaluate_order_expression(frame, "COALESCE(a, b)").tolist() == [1.0, 8.0, 3.0]
