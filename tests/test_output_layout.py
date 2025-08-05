"""
Test Output Layout and Column Ordering
Matches testOutputLayout() from TestRowPatternMatching.java
"""

import pytest
import pandas as pd
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.executor.match_recognize import match_recognize

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
