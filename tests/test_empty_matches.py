"""
Tests for empty matches handling to ensure compliance with SQL:2016 standard.
These tests verify that empty matches are properly handled across different scenarios.
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

class TestEmptyMatches:
    """Test suite for empty matches handling functionality."""
    
    def test_empty_pattern_match(self):
        """Test handling of completely empty pattern matches."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        # Pattern () - empty pattern
        query = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (())
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Empty pattern should produce empty matches at each position
        expected = pd.DataFrame({
            'row_id': [1, 2, 3, 4],
            'match': [1, 2, 3, 4],
            'label': [None, None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_matches_with_measures(self):
        """Test empty matches behavior with various measures."""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'value': [10, 20, 30]
        })
        
        query = """
        SELECT 
            id AS row_id, 
            MATCH_NUMBER() AS match,
            CLASSIFIER() AS label,
            COUNT(*) AS row_count,
            SUM(value) AS sum_val,
            AVG(value) AS avg_val,
            FIRST(value) AS first_val,
            LAST(value) AS last_val
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                CLASSIFIER() AS label,
                COUNT(*) AS row_count,
                SUM(value) AS sum_val,
                AVG(value) AS avg_val,
                FIRST(value) AS first_val,
                LAST(value) AS last_val
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (())
        ) AS m
        """
        
        result = match_recognize(query, df)
        expected = pd.DataFrame({
            'row_id': [1, 2, 3],
            'match': [1, 2, 3],
            'label': [None, None, None],
            'row_count': [0, 0, 0],  # Empty matches have count 0
            'sum_val': [None, None, None],  # No values to sum
            'avg_val': [None, None, None],  # No values to average
            'first_val': [None, None, None],
            'last_val': [None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_matches_with_alternation(self):
        """Test empty matches in alternation patterns."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        # Pattern (() | A) - empty pattern as first alternative
        query = """
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
            PATTERN (() | A)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should prefer empty pattern (first alternative)
        expected = pd.DataFrame({
            'row_id': [1, 2, 3, 4],
            'match': [1, 2, 3, 4],
            'val': [None, None, None, None],
            'label': [None, None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_matches_with_non_preferred_alternation(self):
        """Test empty matches when not in preferred alternation branch."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        # Pattern (A | ()) - empty pattern as second alternative
        query = """
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
            PATTERN (A | ())
            DEFINE A AS false  -- A never matches, so empty pattern is used
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should fall back to empty pattern since A doesn't match
        expected = pd.DataFrame({
            'row_id': [1, 2, 3, 4],
            'match': [1, 2, 3, 4],
            'val': [None, None, None, None],
            'label': [None, None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_matches_skip_behavior(self):
        """Test skip behavior with empty matches."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        # Test SKIP TO NEXT ROW with empty matches
        query = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP TO NEXT ROW
            PATTERN (())
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should produce one empty match per row
        expected = pd.DataFrame({
            'row_id': [1, 2, 3, 4, 5],
            'match': [1, 2, 3, 4, 5],
            'label': [None, None, None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_matches_with_partitioning(self):
        """Test empty matches behavior with partitioning."""
        df = pd.DataFrame({
            'partition_id': [1, 1, 1, 2, 2],
            'id': [1, 2, 3, 1, 2],
            'value': [10, 20, 30, 40, 50]
        })
        
        query = """
        SELECT 
            partition_id,
            id AS row_id, 
            MATCH_NUMBER() AS match,
            CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY partition_id
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (())
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should produce empty matches in each partition
        expected = pd.DataFrame({
            'partition_id': [1, 1, 1, 2, 2],
            'row_id': [1, 2, 3, 1, 2],
            'match': [1, 2, 3, 1, 2],
            'label': [None, None, None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_matches_output_modes(self):
        """Test empty matches with different output modes."""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'value': [10, 20, 30]
        })
        
        # ONE ROW PER MATCH with empty pattern
        query_one_row = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                CLASSIFIER() AS label
            ONE ROW PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (())
        ) AS m
        """
        
        result = match_recognize(query_one_row, df)
        # Should produce one row per empty match
        expected = pd.DataFrame({
            'row_id': [1, 2, 3],  # Should still show the row IDs
            'match': [1, 2, 3],
            'label': [None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_matches_with_unmatched_rows(self):
        """Test empty matches interaction with unmatched rows."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        # Pattern that produces some empty matches and some real matches
        query = """
        SELECT id AS row_id, MATCH_NUMBER() AS match, value AS val, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                value AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH WITH UNMATCHED ROWS
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS value = 20  -- Only matches row 2
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should show actual match for row 2, empty matches for others, plus unmatched rows
        assert not result.empty
        matched_rows = result[result['label'].notna()]
        empty_matches = result[result['label'].isna() & result['match'].notna()]
        unmatched_rows = result[result['match'].isna()]
        
        assert len(matched_rows) >= 1  # At least one real match
        assert len(empty_matches) >= 1  # At least one empty match
        # Note: unmatched rows behavior depends on implementation

    def test_empty_matches_complex_pattern(self):
        """Test empty matches in complex pattern scenarios."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'type': ['A', 'B', 'C', 'A', 'B', 'C'],
            'value': [10, 20, 30, 40, 50, 60]
        })
        
        # Complex pattern with potential empty matches
        query = """
        SELECT 
            id AS row_id, 
            type,
            MATCH_NUMBER() AS match,
            CLASSIFIER() AS label,
            value
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                CLASSIFIER() AS label,
                value AS value
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (START MIDDLE* FINISH)
            DEFINE 
                START AS type = 'A',
                MIDDLE AS false,  -- Never matches, creates empty MIDDLE*
                FINISH AS type = 'B'
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should match START (empty MIDDLE*) FINISH pattern
        # With AFTER MATCH SKIP PAST LAST ROW, both valid matches are found
        expected = pd.DataFrame({
            'row_id': [1, 2, 4, 5],
            'type': ['A', 'B', 'A', 'B'],
            'match': [1, 1, 2, 2],
            'label': ['START', 'FINISH', 'START', 'FINISH'],
            'value': [10, 20, 40, 50]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

if __name__ == "__main__":
    pytest.main([__file__])
