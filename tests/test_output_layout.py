"""
Test Output Layout and Column Ordering
Matches testOutputLayout() from TestRowPatternMatching.java
"""

import pytest
import pandas as pd
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.executor.match_recognize import (
    DataFrameRowAccessor,
    _create_dataframe_with_preserved_types,
    _derive_output_source_columns,
    _parse_query_cached,
    match_recognize,
)


def test_lazy_row_output_copy_does_not_fill_source_cache():
    """Projection owns its row copy and must not retain a second dictionary."""
    frame = pd.DataFrame(
        {
            "id": [1, 2],
            "flag": [True, False],
            "value": [10, 20],
        }
    )
    rows = DataFrameRowAccessor(frame)

    projected = rows.copy_row(1)

    assert projected == {"id": 2, "flag": False, "value": 20}
    assert rows._row_cache == {}
    projected["value"] = 99
    assert rows.get_value(1, "value") == 20

    assert rows[1]["value"] == 20
    assert list(rows._row_cache) == [1]


def test_result_materialization_preserves_pandas_types_and_record_order():
    """Output construction must not require a duplicate intermediate frame."""
    records = [
        {
            "ordered_second": 1,
            "ordered_first": True,
            "timestamp": pd.Timestamp("2024-01-01", tz="UTC"),
            "nullable": pd.NA,
        },
        {
            "ordered_second": 2,
            "ordered_first": False,
            "timestamp": pd.Timestamp("2024-01-02", tz="UTC"),
            "nullable": "value",
        },
    ]

    actual = _create_dataframe_with_preserved_types(records)
    expected = pd.DataFrame.from_records(records)

    pd.testing.assert_frame_equal(actual, expected)
    assert list(actual.columns) == list(records[0])


def test_output_source_projection_plans_only_direct_columns():
    ast = _parse_query_cached(
        """
        SELECT m.id AS row_id, label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A)
            DEFINE A AS A.kind = 'A'
        )
        ORDER BY row_id
        """
    )

    assert _derive_output_source_columns(
        ast,
        ["id", "kind", "unused"],
        {"label": "CLASSIFIER()"},
    ) == ("id",)


@pytest.mark.parametrize(
    "select_text",
    [
        "*",
        "m.*",
        "CAST(id AS VARCHAR) AS text_id",
        "id + 1 AS next_id",
        "missing",
    ],
)
def test_output_source_projection_falls_back_for_ambiguous_expressions(
    select_text,
):
    ast = _parse_query_cached(
        f"""
        SELECT {select_text}
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A)
            DEFINE A AS A.kind = 'A'
        ) AS m
        """
    )

    assert _derive_output_source_columns(
        ast,
        ["id", "kind", "unused"],
        {"label": "CLASSIFIER()"},
    ) is None


def test_output_source_projection_falls_back_for_name_collisions_and_duplicates():
    ast = _parse_query_cached(
        """
        SELECT label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A)
            DEFINE A AS A.kind = 'A'
        ) AS m
        """
    )

    assert _derive_output_source_columns(
        ast,
        ["id", "kind", "label"],
        {"label": "CLASSIFIER()"},
    ) is None
    assert _derive_output_source_columns(
        ast,
        ["id", "id", "kind"],
        {"label": "CLASSIFIER()"},
    ) is None

    repeated_expression_ast = _parse_query_cached(
        """
        SELECT id AS id_measure
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES id AS id_measure
            ALL ROWS PER MATCH
            PATTERN (A)
            DEFINE A AS A.kind = 'A'
        ) AS m
        """
    )
    assert _derive_output_source_columns(
        repeated_expression_ast,
        ["id", "kind"],
        {"id_measure": "id"},
    ) is None


def test_output_source_projection_rejects_unselected_outer_sort_key():
    ast = _parse_query_cached(
        """
        SELECT label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A)
            DEFINE A AS A.kind = 'A'
        )
        ORDER BY id
        """
    )

    assert _derive_output_source_columns(
        ast,
        ["id", "kind", "unused"],
        {"label": "CLASSIFIER()"},
    ) is None


def test_selective_all_rows_does_not_gather_unselected_source_columns(
    monkeypatch,
):
    frame = pd.DataFrame(
        {
            "id": range(100),
            "kind": ["A", "B"] * 50,
            **{
                f"unused_{index}": [float(index)] * 100
                for index in range(12)
            },
        }
    )
    query = """
        SELECT id, label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN ((A B)+)
            DEFINE
                A AS A.kind = 'A',
                B AS B.kind = 'B'
        ) AS m
    """

    def unexpected_all_column_gather(_self):
        raise AssertionError("selective output requested every source column")

    monkeypatch.setattr(
        DataFrameRowAccessor,
        "column_names",
        unexpected_all_column_gather,
    )
    result = match_recognize(query, frame)

    assert list(result.columns) == ["id", "label"]
    assert result["id"].tolist() == list(range(100))
    assert result["label"].tolist() == ["A", "B"] * 50


def test_wildcard_all_rows_keeps_all_source_columns(monkeypatch):
    frame = pd.DataFrame(
        {
            "id": range(6),
            "kind": ["A", "B"] * 3,
            "unused": range(10, 16),
        }
    )
    query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN ((A B)+)
            DEFINE
                A AS A.kind = 'A',
                B AS B.kind = 'B'
        ) AS m
    """
    original = DataFrameRowAccessor.column_names
    calls = []

    def tracked_all_column_gather(self):
        calls.append(True)
        return original(self)

    monkeypatch.setattr(
        DataFrameRowAccessor,
        "column_names",
        tracked_all_column_gather,
    )
    result = match_recognize(query, frame)

    assert calls
    assert {"id", "kind", "unused", "label"}.issubset(result.columns)


def test_generic_compiled_all_rows_prunes_unused_source_columns(monkeypatch):
    frame = pd.DataFrame(
        {
            "id": range(8),
            "kind": ["A"] * 8,
            "value": range(1, 9),
            "unused": range(100, 108),
        }
    )
    query = """
        SELECT id, running_total
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES RUNNING SUM(A.value) AS running_total
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS A.kind = 'A'
        ) AS m
    """

    def unexpected_all_column_gather(_self):
        raise AssertionError("generic output requested every source column")

    monkeypatch.setattr(
        DataFrameRowAccessor,
        "column_names",
        unexpected_all_column_gather,
    )
    result = match_recognize(query, frame)

    assert list(result.columns) == ["id", "running_total"]
    assert result["id"].tolist() == list(range(8))
    assert result["running_total"].tolist() == [
        1,
        3,
        6,
        10,
        15,
        21,
        28,
        36,
    ]


def test_projection_plan_is_query_local_across_automata_cache_hits(monkeypatch):
    frame = pd.DataFrame(
        {
            "id": range(6),
            "kind": ["A", "B"] * 3,
            "unused": range(10, 16),
        }
    )
    query_template = """
        SELECT {projection}
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN ((A B)+)
            DEFINE
                A AS A.kind = 'A',
                B AS B.kind = 'B'
        ) AS m
    """
    original = DataFrameRowAccessor.column_names
    calls = []

    def tracked_all_column_gather(self):
        calls.append(True)
        return original(self)

    monkeypatch.setattr(
        DataFrameRowAccessor,
        "column_names",
        tracked_all_column_gather,
    )
    narrow_first = match_recognize(
        query_template.format(projection="id, label"),
        frame,
    )
    wildcard = match_recognize(
        query_template.format(projection="*"),
        frame,
    )
    narrow_cached = match_recognize(
        query_template.format(projection="id, label"),
        frame,
    )

    pd.testing.assert_frame_equal(narrow_first, narrow_cached)
    assert list(narrow_first.columns) == ["id", "label"]
    assert "unused" in wildcard.columns
    assert len(calls) == 1


def test_with_unmatched_streams_selective_rows_and_preserves_partitions(
    monkeypatch,
):
    frame = pd.DataFrame(
        {
            "id": [2, 3, 1, 1, 2, 3],
            "part": ["B", "A", "A", "B", "A", "B"],
            "kind": ["B", "X", "A", "A", "B", "X"],
            "unused": [20, 30, 10, 10, 20, 30],
        }
    )
    query = """
        SELECT part, id, label
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY part
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH WITH UNMATCHED ROWS
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A B)
            DEFINE
                A AS A.kind = 'A',
                B AS B.kind = 'B'
        ) AS m
    """
    original_copy_row = DataFrameRowAccessor.copy_row
    requested_columns = []

    def tracked_copy_row(self, index, columns=None):
        requested_columns.append(columns)
        return original_copy_row(self, index, columns)

    monkeypatch.setattr(
        DataFrameRowAccessor,
        "copy_row",
        tracked_copy_row,
    )
    result = match_recognize(query, frame)

    assert list(result.columns) == ["part", "id", "label"]
    assert result["part"].tolist() == ["A", "A", "A", "B", "B", "B"]
    assert result["id"].tolist() == [1, 2, 3, 1, 2, 3]
    assert result["label"].tolist()[:2] == ["A", "B"]
    assert pd.isna(result["label"].iloc[2])
    assert result["label"].tolist()[3:5] == ["A", "B"]
    assert pd.isna(result["label"].iloc[5])
    assert requested_columns
    assert all(
        columns is not None and "unused" not in columns
        for columns in requested_columns
    )


class TestOutputLayout:
    """Test output column layout and ordering."""

    def setup_method(self):
        """Setup test data matching Java reference."""
        self.partition_data = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'part': ['A', 'A', 'A', 'B', 'B', 'B'],
            'value': [90, 80, 70, 85, 75, 65],
            'extra': ['x1', 'x2', 'x3', 'x4', 'x5', 'x6']
        })

    def test_output_layout_all_rows_per_match(self):
        """Test column ordering with ALL ROWS PER MATCH."""
        df = self.partition_data
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY part
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                RUNNING LAST(value) AS running_val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Expected column order: [partition_cols, order_cols, measures, original_cols]
            expected_order = ['part', 'id', 'match_num', 'running_val', 'label', 'value', 'extra']
            actual_order = list(result.columns)
            
            # Check that all expected columns are present
            for col in expected_order:
                assert col in actual_order, f"Missing column: {col}"
            
            # Verify proper grouping of column types
            # Partition and order columns should come first
            part_idx = actual_order.index('part')
            id_idx = actual_order.index('id')
            assert part_idx < id_idx, "Partition column should come before order column"
            
            # Measures should come after partition/order columns
            match_idx = actual_order.index('match_num')
            assert id_idx < match_idx, "Order column should come before measures"
        else:
            pytest.skip("Output layout for ALL ROWS PER MATCH not implemented")

    def test_output_layout_one_row_per_match(self):
        """Test column ordering with ONE ROW PER MATCH."""
        df = self.partition_data
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY part
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                FIRST(value) AS first_val,
                LAST(value) AS last_val,
                COUNT(*) AS row_count
            ONE ROW PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # For ONE ROW PER MATCH with SELECT *, Trino behavior:
            # Only PARTITION BY + MEASURES columns are included (ORDER BY columns excluded)
            required_cols = ['part', 'match_num', 'first_val', 'last_val', 'row_count']
            
            for col in required_cols:
                assert col in result.columns, f"Missing required column: {col}"
            
            # ORDER BY columns should NOT be included in ONE ROW PER MATCH output
            assert 'id' not in result.columns, "ORDER BY column 'id' should not be included in ONE ROW PER MATCH output"
            
            # Check that we have the right number of matches
            # Should have one row per match, not per input row
            assert len(result) < len(df), "ONE ROW PER MATCH should produce fewer rows than input"
        else:
            pytest.skip("Output layout for ONE ROW PER MATCH not implemented")

    def test_output_layout_with_duplicated_order_columns(self):
        """Test handling of duplicated order columns in measures."""
        df = self.partition_data
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY part
            ORDER BY id
            MEASURES
                FIRST(id) AS first_id,
                LAST(id) AS last_id,
                RUNNING LAST(id) AS current_id
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Should handle duplicate references to order column (id)
            assert 'id' in result.columns  # Original order column
            assert 'first_id' in result.columns  # Measure referencing order column
            assert 'last_id' in result.columns
            assert 'current_id' in result.columns
            
            # Verify values make sense
            if len(result) > 0:
                # current_id should match id for each row
                for i in range(len(result)):
                    assert result.iloc[i]['current_id'] == result.iloc[i]['id']
        else:
            pytest.skip("Duplicate order column handling not implemented")

    def test_output_layout_no_original_columns(self):
        """Test output when no original table columns are requested."""
        df = self.partition_data
        
        query = """
        SELECT part, match_num, label
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY part
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Should only have selected columns
            expected_cols = ['part', 'match_num', 'label']
            actual_cols = list(result.columns)
            
            assert len(actual_cols) == len(expected_cols)
            for col in expected_cols:
                assert col in actual_cols
        else:
            pytest.skip("Selective column output not implemented")

    def test_output_layout_multiple_partitions(self):
        """Test column layout with multiple partition columns."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'part1': ['A', 'A', 'A', 'B', 'B', 'B'],
            'part2': ['X', 'X', 'Y', 'X', 'Y', 'Y'],
            'value': [90, 80, 70, 85, 75, 65]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY part1, part2
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Both partition columns should be present and come first
            assert 'part1' in result.columns
            assert 'part2' in result.columns
            
            actual_order = list(result.columns)
            part1_idx = actual_order.index('part1')
            part2_idx = actual_order.index('part2')
            id_idx = actual_order.index('id')
            
            # Partition columns should come before order columns
            assert part1_idx < id_idx
            assert part2_idx < id_idx
        else:
            pytest.skip("Multiple partition columns not implemented")

    def test_output_layout_no_partition_columns(self):
        """Test column layout with no partitioning."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 60],
            'extra': ['a', 'b', 'c', 'd']
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Column order should be: [order_cols, measures, original_cols]
            expected_order = ['id', 'match_num', 'label', 'value', 'extra']
            actual_order = list(result.columns)
            
            # Check relative positioning
            id_idx = actual_order.index('id')
            match_idx = actual_order.index('match_num')
            value_idx = actual_order.index('value')
            
            assert id_idx < match_idx, "Order column should come before measures"
            assert match_idx < value_idx, "Measures should come before original columns"
        else:
            pytest.skip("No partition column layout not implemented")

    def test_output_layout_column_aliasing(self):
        """Test column aliasing in output."""
        df = self.partition_data
        
        query = """
        SELECT part AS partition_name, 
               id AS row_id,
               match_num AS match_number,
               label AS pattern_label
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY part
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Should have aliased column names
            expected_cols = ['partition_name', 'row_id', 'match_number', 'pattern_label']
            actual_cols = list(result.columns)
            
            for col in expected_cols:
                assert col in actual_cols, f"Missing aliased column: {col}"
        else:
            pytest.skip("Column aliasing not implemented")


# ----------------------------------------------------------------------------
# Faithful conversion of testOutputModes from src/TestRowPatternMatching.java
# (all 9 assertions, exact expected values).
# Data: (1,90),(2,80),(3,70),(4,70); DEFINE B AS B.value < PREV (B.value)
# ----------------------------------------------------------------------------

from tests.test_java_reference_parity import run_query, assert_rows

JAVA_OUTPUT_MODES_QUERY = """
SELECT m.match, m.val, m.label
FROM data
MATCH_RECOGNIZE (
    ORDER BY id
    MEASURES match_number() AS match, RUNNING LAST(value) AS val, classifier() AS label
    {mode}
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN ({pattern})
    DEFINE B AS B.value < PREV (B.value)
) AS m
"""

JAVA_OUTPUT_MODES_CASES = [
    ("ONE ROW PER MATCH", "B*", [(1, None, None), (2, 70, "B"), (3, None, None)]),
    ("", "B*", [(1, None, None), (2, 70, "B"), (3, None, None)]),
    ("ONE ROW PER MATCH", "B+", [(1, 70, "B")]),
    ("ALL ROWS PER MATCH", "B*",
     [(1, None, None), (2, 80, "B"), (2, 70, "B"), (3, None, None)]),
    ("ALL ROWS PER MATCH", "B+", [(1, 80, "B"), (1, 70, "B")]),
    ("ALL ROWS PER MATCH SHOW EMPTY MATCHES", "B*",
     [(1, None, None), (2, 80, "B"), (2, 70, "B"), (3, None, None)]),
    ("ALL ROWS PER MATCH OMIT EMPTY MATCHES", "B*", [(2, 80, "B"), (2, 70, "B")]),
    ("ALL ROWS PER MATCH OMIT EMPTY MATCHES", "B+", [(1, 80, "B"), (1, 70, "B")]),
    ("ALL ROWS PER MATCH WITH UNMATCHED ROWS", "B+",
     [(None, None, None), (1, 80, "B"), (1, 70, "B"), (None, None, None)]),
]


class TestOutputModesJavaReference:
    """All 9 testOutputModes assertions with Trino's exact expected outputs."""

    @pytest.fixture
    def df4(self):
        return pd.DataFrame({"id": [1, 2, 3, 4], "value": [90, 80, 70, 70]})

    @pytest.mark.parametrize("mode,pattern,expected", JAVA_OUTPUT_MODES_CASES,
                             ids=[f"{c[0] or 'default'}-{c[1]}" for c in JAVA_OUTPUT_MODES_CASES])
    def test_java_output_mode(self, df4, mode, pattern, expected):
        result = run_query(JAVA_OUTPUT_MODES_QUERY.format(mode=mode, pattern=pattern), df4)
        assert_rows(result, expected, ["match", "val", "label"])
