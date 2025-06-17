"""
SQL:2016 compliance tests for the match_recognize implementation.

This module contains tests specifically targeting compliance with
SQL:2016 standard requirements for MATCH_RECOGNIZE.
"""

import pytest
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple

# Add the src directory to path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the match_recognize implementation
from src.executor.match_recognize import match_recognize

class TestSql2016Compliance:
    """Test suite for SQL:2016 compliance aspects of match_recognize."""
    
    def test_sql2016_pattern_syntax(self):
        """Test that pattern syntax complies with SQL:2016 standard."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 20, 10]
        })
        
        # Basic pattern
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B C)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        assert len(result) == 3  # Should match the pattern ABC
        
        # Pattern with anchors
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (^A B $)
            DEFINE
                A AS value = 10,
                B AS value = 20
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        # Should match only at the start and end of partition
        
        # Pattern with quantifiers
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B* C+)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value >= 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        
        # Pattern with alternation
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN ((A | D) B C)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30,
                D AS value = 40
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        
        # Pattern with range quantifiers
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B{1,2} C)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        
        # Pattern with reluctant quantifiers
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B*? C)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        
        # Pattern with permutation
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A PERMUTE(B, C))
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        
    def test_sql2016_navigation_functions(self):
        """Test that navigation functions comply with SQL:2016 standard."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        # PREV
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                PREV(value) AS prev_val,
                PREV(value, 2) AS prev_val_2
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # NEXT
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                NEXT(value) AS next_val,
                NEXT(value, 2) AS next_val_2
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # FIRST and LAST
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                FIRST(value) AS first_val,
                FIRST(value, 2) AS first_val_2,
                LAST(value) AS last_val,
                LAST(value, 2) AS last_val_2
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # RUNNING and FINAL semantics
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                RUNNING LAST(value) AS running_last_val,
                FINAL LAST(value) AS final_last_val,
                RUNNING FIRST(value) AS running_first_val,
                FINAL FIRST(value) AS final_first_val
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # Test navigation outside of match
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                PREV(value, 10) AS prev_val_10
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        # All PREV(value, 10) should be NULL as it's outside the data bounds
        for i in range(len(result)):
            assert pd.isna(result.iloc[i]['prev_val_10']) or result.iloc[i]['prev_val_10'] is None
        
    def test_sql2016_special_functions(self):
        """Test that special functions comply with SQL:2016 standard."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        # CLASSIFIER
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label,
                RUNNING LAST(CLASSIFIER()) AS running_label,
                FINAL LAST(CLASSIFIER()) AS final_label
            ALL ROWS PER MATCH
            PATTERN (A B+ C+)
            DEFINE
                A AS value = 10,
                B AS value > 10 AND value < 40,
                C AS value >= 40
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # MATCH_NUMBER
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num
            ONE ROW PER MATCH
            AFTER MATCH SKIP TO NEXT ROW
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        # Each row should have a different match number since ONE ROW PER MATCH with SKIP TO NEXT ROW
        # should produce one row per match starting from each position
        unique_match_numbers = result['match_num'].unique()
        assert len(unique_match_numbers) == len(result), f"Expected {len(result)} unique match numbers, got {len(unique_match_numbers)}"
        
    def test_sql2016_partition_handling(self):
        """Test that partitioning complies with SQL:2016 standard."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
            'part': ['A', 'A', 'A', 'A', 'A', 'B', 'B', 'B', 'B', 'B'],
            'value': [10, 20, 30, 40, 50, 15, 25, 35, 45, 55]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY part
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label,
                RUNNING LAST(value) AS val
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE
                A AS value = 10 OR value = 15,
                B AS value > PREV(value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # Should have separate match numbers for each partition
        part_a_rows = result[result['part'] == 'A']
        part_b_rows = result[result['part'] == 'B']
        
        assert not part_a_rows.empty, "No rows for partition A"
        assert not part_b_rows.empty, "No rows for partition B"
        
        # Verify we have a match in each partition
        part_a_matches = part_a_rows['match_num'].unique()
        part_b_matches = part_b_rows['match_num'].unique()
        
        assert len(part_a_matches) > 0, "No matches in partition A"
        assert len(part_b_matches) > 0, "No matches in partition B"
        
    def test_sql2016_subset_handling(self):
        """Test that SUBSET functionality complies with SQL:2016 standard."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 20, 10]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label,
                CLASSIFIER(U) AS u_label,
                CLASSIFIER(V) AS v_label
            ALL ROWS PER MATCH
            PATTERN (A B C)
            SUBSET
                U = (A, B),
                V = (B, C)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # Check that SUBSET labels are applied correctly
        for i in range(len(result)):
            if result.iloc[i]['label'] == 'A':
                assert result.iloc[i]['u_label'] == 'A'
                assert pd.isna(result.iloc[i]['v_label']) or result.iloc[i]['v_label'] is None
            elif result.iloc[i]['label'] == 'B':
                assert result.iloc[i]['u_label'] == 'B'
                assert result.iloc[i]['v_label'] == 'B'
            elif result.iloc[i]['label'] == 'C':
                assert pd.isna(result.iloc[i]['u_label']) or result.iloc[i]['u_label'] is None
                assert result.iloc[i]['v_label'] == 'C'
        
    def test_sql2016_output_modes(self):
        """Test that output modes comply with SQL:2016 standard."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        # ONE ROW PER MATCH
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label,
                RUNNING LAST(value) AS val
            ONE ROW PER MATCH
            PATTERN (A B+)
            DEFINE
                A AS value = 10,
                B AS value > A.value
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        # Should have only one row per match
        match_counts = result.groupby('match_num').size()
        for count in match_counts:
            assert count == 1
        
        # ALL ROWS PER MATCH
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label,
                RUNNING LAST(value) AS val
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE
                A AS value = 10,
                B AS value > A.value
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        # Should have multiple rows per match
        match_counts = result.groupby('match_num').size()
        for count in match_counts:
            assert count > 1
        
        # ALL ROWS PER MATCH WITH UNMATCHED ROWS
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label,
                RUNNING LAST(value) AS val
            ALL ROWS PER MATCH WITH UNMATCHED ROWS
            PATTERN (A B)
            DEFINE
                A AS value = 10,
                B AS value = 20
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        # Should include unmatched rows with NULL match_num
        unmatched_rows = [pd.isna(x) for x in result['match_num']]
        assert any(unmatched_rows)
        
    def test_sql2016_skip_modes(self):
        """Test that AFTER MATCH SKIP modes comply with SQL:2016 standard."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7, 8],
            'value': [10, 20, 30, 10, 20, 30, 10, 20]
        })
        
        # SKIP PAST LAST ROW
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A B C)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        # Should find 2 matches with 3 rows each
        assert len(result) == 6
        
        # SKIP TO NEXT ROW
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP TO NEXT ROW
            PATTERN (A B C)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        # Should find more matches due to overlapping
        
        # SKIP TO FIRST variable
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP TO FIRST B
            PATTERN (A B C)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # SKIP TO LAST variable
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP TO LAST B
            PATTERN (A B C)
            DEFINE
                A AS value = 10,
                B AS value = 20,
                C AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
