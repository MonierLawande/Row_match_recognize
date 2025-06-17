"""
Tests for PERMUTE pattern functionality to ensure compliance with SQL:2016 standard.
These tests verify that permutation patterns work correctly.
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

class TestPermutePatterns:
    """Test suite for PERMUTE pattern functionality."""
    
    def test_basic_permute(self):
        """Test basic PERMUTE pattern functionality."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 70]
        })
        
        # PERMUTE(B, C) should match when B and C appear in any order
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
            PATTERN (PERMUTE(B, C))
            DEFINE 
                B AS value < PREV(value),
                C AS value < PREV(value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should match rows 2,3 as B,C (first permutation in lexicographical order)
        expected = pd.DataFrame({
            'row_id': [2, 3],
            'match': [1, 1],
            'val': [80, 70],
            'label': ['B', 'C']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_permute_with_three_variables(self):
        """Test PERMUTE with three pattern variables."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 25, 15]
        })
        
        # PERMUTE(A, B, C) with different conditions
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
            PATTERN (PERMUTE(A, B, C))
            DEFINE 
                A AS value = 20,
                B AS value = 30,
                C AS value = 25
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should match rows 2,3,4 as A,B,C (lexicographical order)
        expected = pd.DataFrame({
            'row_id': [2, 3, 4],
            'match': [1, 1, 1],
            'val': [20, 30, 25],
            'label': ['A', 'B', 'C']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_permute_lexicographical_preference(self):
        """Test that PERMUTE prefers lexicographical order when multiple permutations match."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 15, 20, 25]
        })
        
        # Both (A,B) and (B,A) could match, but A,B should be preferred
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
            PATTERN (PERMUTE(A, B))
            DEFINE 
                A AS value >= 15 AND value <= 20,
                B AS value >= 15 AND value <= 20
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should prefer A,B order (lexicographical)
        expected = pd.DataFrame({
            'row_id': [2, 3],
            'match': [1, 1],
            'val': [15, 20],
            'label': ['A', 'B']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_permute_with_quantifiers(self):
        """Test PERMUTE patterns with quantifiers."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'value': [10, 20, 25, 30, 35, 40]
        })
        
        # PERMUTE(A+, B+) - permutation with quantified variables
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
            PATTERN (PERMUTE(A+, B+))
            DEFINE 
                A AS value BETWEEN 20 AND 30,
                B AS value BETWEEN 35 AND 40
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should match A+ first, then B+ (lexicographical order)
        expected = pd.DataFrame({
            'row_id': [2, 3, 4, 5, 6],
            'match': [1, 1, 1, 1, 1],
            'val': [20, 25, 30, 35, 40],
            'label': ['A', 'A', 'A', 'B', 'B']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_permute_nested_patterns(self):
        """Test PERMUTE with nested or complex patterns."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        # X PERMUTE(A, B) Y - permute in the middle
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
            PATTERN (X PERMUTE(A, B) Y)
            DEFINE 
                X AS value = 10,
                A AS value = 20,
                B AS value = 30,
                Y AS value = 40
        ) AS m
        """
        
        result = match_recognize(query, df)
        expected = pd.DataFrame({
            'row_id': [1, 2, 3, 4],
            'match': [1, 1, 1, 1],
            'val': [10, 20, 30, 40],
            'label': ['X', 'A', 'B', 'Y']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_permute_with_alternation(self):
        """Test PERMUTE with alternation patterns."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'value': [10, 20, 30, 40, 50, 60]
        })
        
        # PERMUTE(A | B, C | D) - permutation of alternations
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
            PATTERN (PERMUTE(A | B, C | D))
            DEFINE 
                A AS value = 20,
                B AS value = 30,
                C AS value = 40,
                D AS value = 50
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should match first alternation (A|B), then second (C|D)
        # Following lexicographical order: (A|B, C|D)
        expected = pd.DataFrame({
            'row_id': [2, 4],
            'match': [1, 1],
            'val': [20, 40],
            'label': ['A', 'C']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_permute_empty_match(self):
        """Test PERMUTE when no permutation matches."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        # PERMUTE(A, B) where conditions can't be satisfied
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
            PATTERN (PERMUTE(A, B))
            DEFINE 
                A AS value = 100,  -- No match
                B AS value = 200   -- No match
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result.empty

    def test_permute_with_measures(self):
        """Test PERMUTE patterns with various measures."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        query = """
        SELECT 
            id AS row_id, 
            MATCH_NUMBER() AS match, 
            CLASSIFIER() AS label,
            FIRST(value) AS first_val,
            LAST(value) AS last_val,
            COUNT(*) AS row_count
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                CLASSIFIER() AS label,
                FIRST(value) AS first_val,
                LAST(value) AS last_val,
                COUNT(*) AS row_count
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (PERMUTE(A, B))
            DEFINE 
                A AS value = 20,
                B AS value = 30
        ) AS m
        """
        
        result = match_recognize(query, df)
        expected = pd.DataFrame({
            'row_id': [2, 3],
            'match': [1, 1],
            'label': ['A', 'B'],
            'first_val': [20, 20],  # RUNNING semantics
            'last_val': [20, 30],   # RUNNING semantics  
            'row_count': [1, 2]     # RUNNING count
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

if __name__ == "__main__":
    pytest.main([__file__])
