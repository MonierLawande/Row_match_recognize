"""
Tests for anchor patterns (^ and $) to ensure compliance with SQL:2016 standard.
These tests verify partition start and end anchors work correctly.
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

class TestAnchorPatterns:
    """Test suite for anchor pattern functionality (^ and $)."""
    
    def test_partition_start_anchor(self):
        """Test partition start anchor (^) patterns."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 70]
        })
        
        # Pattern ^A should match only the first row
        query_start = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (^A)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query_start, df)
        
        # Check the specific columns we expect
        assert len(result) == 1
        assert result.iloc[0]['row_id'] == 1  # id is aliased to row_id
        assert result.iloc[0]['match'] == 1
        assert result.iloc[0]['val'] == 90
        assert result.iloc[0]['label'] == 'A'
        
        # Pattern A^ should return empty result (invalid anchor position)
        query_invalid = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A^)
            DEFINE A AS true
        ) AS m
        """
        
        result_invalid = match_recognize(query_invalid, df)
        assert result_invalid.empty
        
        # Pattern ^A^ should return empty result (conflicting anchors)
        query_conflict = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (^A^)
            DEFINE A AS true
        ) AS m
        """
        
        result_conflict = match_recognize(query_conflict, df)
        assert result_conflict.empty

    def test_partition_end_anchor(self):
        """Test partition end anchor ($) patterns."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 70]
        })
        
        # Pattern A$ should match only the last row
        query_end = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A$)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query_end, df)
        expected = pd.DataFrame({
            'row_id': [4],
            'match': [1],
            'val': [70],
            'label': ['A']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)
        
        # Pattern $A should return empty result (invalid anchor position)
        query_invalid = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN ($A)
            DEFINE A AS true
        ) AS m
        """
        
        result_invalid = match_recognize(query_invalid, df)
        assert result_invalid.empty
        
        # Pattern $A$ should return empty result (conflicting anchors)
        query_conflict = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN ($A$)
            DEFINE A AS true
        ) AS m
        """
        
        result_conflict = match_recognize(query_conflict, df)
        assert result_conflict.empty

    def test_anchors_with_conditions(self):
        """Test anchor patterns with specific conditions."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 20, 10]
        })
        
        # Start anchor with condition
        query_start_cond = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (^A)
            DEFINE A AS value = 10
        ) AS m
        """
        
        result = match_recognize(query_start_cond, df)
        expected = pd.DataFrame({
            'row_id': [1],
            'match': [1],
            'val': [10],
            'label': ['A']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)
        
        # End anchor with condition
        query_end_cond = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A$)
            DEFINE A AS value = 10
        ) AS m
        """
        
        result = match_recognize(query_end_cond, df)
        expected = pd.DataFrame({
            'row_id': [5],
            'match': [1],
            'val': [10],
            'label': ['A']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_anchors_with_multiple_patterns(self):
        """Test anchor patterns in complex scenarios."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'value': [10, 20, 30, 40, 50, 60]
        })
        
        # Pattern ^A B should start from first row
        query_complex = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (^A B)
            DEFINE 
                A AS value = 10,
                B AS value = 20
        ) AS m
        """
        
        result = match_recognize(query_complex, df)
        expected = pd.DataFrame({
            'row_id': [1, 2],
            'match': [1, 1],
            'val': [10, 20],
            'label': ['A', 'B']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)
        
        # Pattern B A$ should end at last row
        query_end_complex = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (B A$)
            DEFINE 
                A AS value = 60,
                B AS value = 50
        ) AS m
        """
        
        result = match_recognize(query_end_complex, df)
        expected = pd.DataFrame({
            'row_id': [5, 6],
            'match': [1, 1],
            'val': [50, 60],
            'label': ['B', 'A']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_anchors_with_partitioning(self):
        """Test anchor patterns with partitioning."""
        df = pd.DataFrame({
            'partition_id': [1, 1, 1, 2, 2, 2],
            'id': [1, 2, 3, 1, 2, 3],
            'value': [10, 20, 30, 40, 50, 60]
        })
        
        # Start anchor should work within each partition
        query_partitioned = """
        SELECT partition_id, id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY partition_id
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (^A)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query_partitioned, df)
        expected = pd.DataFrame({
            'partition_id': [1, 2],
            'row_id': [1, 1],
            'match': [1, 1],
            'val': [10, 40],
            'label': ['A', 'A']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

if __name__ == "__main__":
    pytest.main([__file__])
