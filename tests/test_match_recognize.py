"""
Comprehensive test suite for pandas-based MATCH_RECOGNIZE implementation.

Based on TestRowPatternMatching.java from Trino, this file contains test cases
that validate compliance with the SQL:2016 standard and compatibility with Trino's behavior.
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple, Optional

# Add the src directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the match_recognize implementation
from src.executor.match_recognize import match_recognize

class TestRowPatternMatching:
    """
    Test suite for the match_recognize implementation, mirroring Trino's TestRowPatternMatching.java.
    """

    def setup_method(self):
        """Setup for each test method."""
        # Common test data used across multiple tests
        self.simple_data = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7, 8],
            'value': [90, 80, 70, 80, 90, 50, 40, 60]
        })
        
        self.basic_data = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 70]
        })
        
        self.skip_data = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'value': [90, 80, 70, 80, 70, 80]
        })

    def test_simple_query(self):
        """Test a simple match_recognize query with various features."""
        df = self.simple_data
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                RUNNING LAST(value) AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A B+ C+)
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value > PREV(C.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        # Validate result structure
        assert result is not None
        assert not result.empty
        assert 'id' in result.columns
        assert 'match' in result.columns
        assert 'val' in result.columns
        assert 'label' in result.columns
        
        # Validate match results - should match Trino's expected output
        expected_rows = [
            (1, 1, 90, 'A'),
            (2, 1, 80, 'B'),
            (3, 1, 70, 'B'),
            (4, 1, 80, 'C'),
            (5, 1, 90, 'C'),
            (6, 2, 50, 'A'),
            (7, 2, 40, 'B'),
            (8, 2, 60, 'C')
        ]
        
        # Check row count
        assert len(result) == len(expected_rows)
        
        # Check each row's values
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label

    def test_row_pattern(self):
        """Test various row pattern syntax features."""
        df = self.basic_data
        
        # Test empty pattern
        query_template = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                RUNNING LAST(value) AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            {pattern_define}
        ) AS m
        """
        
        # Empty pattern test
        query = query_template.format(
            pattern_define="""
            PATTERN (() | A)
            DEFINE A AS true
            """
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        assert len(result) == 4  # Should match all rows with empty pattern
        
        # Check for null values in classifier
        for i in range(len(result)):
            assert result.iloc[i]['label'] is None
            
        # Test anchor pattern: partition start (^)
        query = query_template.format(
            pattern_define="""
            PATTERN (^A)
            DEFINE A AS true
            """
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        assert len(result) == 1  # Should match only the first row
        assert result.iloc[0]['id'] == 1
        assert result.iloc[0]['label'] == 'A'
        
        # Test anchor pattern: partition end ($)
        query = query_template.format(
            pattern_define="""
            PATTERN (A$)
            DEFINE A AS true
            """
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        assert len(result) == 1  # Should match only the last row
        assert result.iloc[0]['id'] == 4
        assert result.iloc[0]['label'] == 'A'
        
        # Test pattern concatenation
        query = query_template.format(
            pattern_define="""
            PATTERN (A B C)
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value = PREV(C.value)
            """
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        assert len(result) == 3  # Should match a sequence of 3 rows
        
        expected_rows = [
            (2, 1, 80, 'A'),
            (3, 1, 70, 'B'),
            (4, 1, 70, 'C')
        ]
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Test pattern alternation
        query = query_template.format(
            pattern_define="""
            PATTERN (B | C | A)
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value <= PREV(C.value)
            """
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        assert len(result) == 4  # Should match all rows
        
        expected_rows = [
            (1, 1, 90, 'A'),
            (2, 2, 80, 'B'),
            (3, 3, 70, 'B'),
            (4, 4, 70, 'C')
        ]
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Test pattern permutation
        query = query_template.format(
            pattern_define="""
            PATTERN (PERMUTE(B, C))
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value < PREV(C.value)
            """
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        assert len(result) == 2  # Should match a sequence of 2 rows
        
        expected_rows = [
            (2, 1, 80, 'B'),
            (3, 1, 70, 'C')
        ]
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Test grouped pattern
        query = query_template.format(
            pattern_define="""
            PATTERN (((A) (B (C))))
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value = PREV(C.value)
            """
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        assert len(result) == 3  # Should match a sequence of 3 rows
        
        expected_rows = [
            (2, 1, 80, 'A'),
            (3, 1, 70, 'B'),
            (4, 1, 70, 'C')
        ]
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label

    def test_pattern_quantifiers(self):
        """Test pattern quantifiers (*, +, ?, {n,m}, etc.)."""
        df = self.basic_data
        
        query_template = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                RUNNING LAST(value) AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            {pattern}
            DEFINE B AS B.value <= PREV(B.value)
        ) AS m
        """
        
        # Test * quantifier (greedy)
        query = query_template.format(
            pattern="PATTERN (B*)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 1, None, None),  # Empty match
            (2, 2, 80, 'B'),     # Start of non-empty match
            (3, 2, 70, 'B'),
            (4, 2, 70, 'B')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            if value is None:
                assert pd.isna(result.iloc[i]['val']) or result.iloc[i]['val'] is None
            else:
                assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Test *? quantifier (reluctant)
        query = query_template.format(
            pattern="PATTERN (B*?)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # Should match all rows with empty matches
        expected_rows = [
            (1, 1, None, None),
            (2, 2, None, None),
            (3, 3, None, None),
            (4, 4, None, None)
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            if value is None:
                assert pd.isna(result.iloc[i]['val']) or result.iloc[i]['val'] is None
            else:
                assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Test + quantifier (greedy)
        query = query_template.format(
            pattern="PATTERN (B+)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (2, 1, 80, 'B'),
            (3, 1, 70, 'B'),
            (4, 1, 70, 'B')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Test +? quantifier (reluctant)
        query = query_template.format(
            pattern="PATTERN (B+?)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (2, 1, 80, 'B'),
            (3, 2, 70, 'B'),
            (4, 3, 70, 'B')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label

    def test_exclusion_syntax(self):
        """Test exclusion syntax in patterns {- pattern -}."""
        df = self.simple_data
        
        query_template = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                RUNNING LAST(value) AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            {pattern}
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value > PREV(C.value)
        ) AS m
        """
        
        # No exclusion -- outputting all matched rows
        query = query_template.format(
            pattern="PATTERN (A B+ C+)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 1, 90, 'A'),
            (2, 1, 80, 'B'),
            (3, 1, 70, 'B'),
            (4, 1, 80, 'C'),
            (5, 1, 90, 'C'),
            (6, 2, 50, 'A'),
            (7, 2, 40, 'B'),
            (8, 2, 60, 'C')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Exclude rows matched to 'B'
        query = query_template.format(
            pattern="PATTERN (A {- B+ -} C+)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 1, 90, 'A'),
            (4, 1, 80, 'C'),
            (5, 1, 90, 'C'),
            (6, 2, 50, 'A'),
            (8, 2, 60, 'C')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Adjacent exclusions: exclude rows matched to 'A' and 'B'
        query = query_template.format(
            pattern="PATTERN ({- A -} {- B+ -} C+)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (4, 1, 80, 'C'),
            (5, 1, 90, 'C'),
            (8, 2, 60, 'C')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label

    def test_after_match_skip(self):
        """Test AFTER MATCH SKIP modes."""
        df = self.skip_data
        
        query_template = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                RUNNING LAST(value) AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            {skip_mode}
            PATTERN (A B+ C+ D?)
            SUBSET U = (C, D)
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value > PREV(C.value),
                D AS false
        ) AS m
        """
        
        # SKIP PAST LAST ROW
        query = query_template.format(
            skip_mode="AFTER MATCH SKIP PAST LAST ROW"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 1, 90, 'A'),
            (2, 1, 80, 'B'),
            (3, 1, 70, 'B'),
            (4, 1, 80, 'C')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # SKIP TO NEXT ROW
        query = query_template.format(
            skip_mode="AFTER MATCH SKIP TO NEXT ROW"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 1, 90, 'A'),
            (2, 1, 80, 'B'),
            (3, 1, 70, 'B'),
            (4, 1, 80, 'C'),
            (2, 2, 80, 'A'),
            (3, 2, 70, 'B'),
            (4, 2, 80, 'C'),
            (4, 3, 80, 'A'),
            (5, 3, 70, 'B'),
            (6, 3, 80, 'C')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # SKIP TO FIRST C
        query = query_template.format(
            skip_mode="AFTER MATCH SKIP TO FIRST C"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 1, 90, 'A'),
            (2, 1, 80, 'B'),
            (3, 1, 70, 'B'),
            (4, 1, 80, 'C'),
            (4, 2, 80, 'A'),
            (5, 2, 70, 'B'),
            (6, 2, 80, 'C')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label

    def test_output_modes(self):
        """Test output modes (ONE ROW PER MATCH, ALL ROWS PER MATCH, etc.)."""
        df = self.basic_data
        
        query_template = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                RUNNING LAST(value) AS val,
                CLASSIFIER() AS label
            {rows_per_match}
            AFTER MATCH SKIP PAST LAST ROW
            {pattern}
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        # Test ONE ROW PER MATCH (default)
        query = query_template.format(
            rows_per_match="ONE ROW PER MATCH",
            pattern="PATTERN (B*)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, None, None),  # Empty match
            (2, 70, 'B'),     # Non-empty match
            (3, None, None)   # Empty match at end
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['match'] == match_num
            if value is None:
                assert pd.isna(result.iloc[i]['val']) or result.iloc[i]['val'] is None
            else:
                assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Test ALL ROWS PER MATCH
        query = query_template.format(
            rows_per_match="ALL ROWS PER MATCH",
            pattern="PATTERN (B*)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 1, None, None),  # Empty match
            (2, 2, 80, 'B'),     # Start of non-empty match
            (3, 2, 70, 'B'),
            (4, 3, None, None)   # Empty match at end
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            if value is None:
                assert pd.isna(result.iloc[i]['val']) or result.iloc[i]['val'] is None
            else:
                assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Test ALL ROWS PER MATCH OMIT EMPTY MATCHES
        query = query_template.format(
            rows_per_match="ALL ROWS PER MATCH OMIT EMPTY MATCHES",
            pattern="PATTERN (B*)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (2, 2, 80, 'B'),
            (3, 2, 70, 'B')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label
            
        # Test ALL ROWS PER MATCH WITH UNMATCHED ROWS
        query = query_template.format(
            rows_per_match="ALL ROWS PER MATCH WITH UNMATCHED ROWS",
            pattern="PATTERN (B+)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, None, None, None),  # Unmatched row
            (2, 1, 80, 'B'),       # Start of match
            (3, 1, 70, 'B'),
            (4, None, None, None)  # Unmatched row
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, value, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            if match_num is None:
                assert pd.isna(result.iloc[i]['match']) or result.iloc[i]['match'] is None
            else:
                assert result.iloc[i]['match'] == match_num
            if value is None:
                assert pd.isna(result.iloc[i]['val']) or result.iloc[i]['val'] is None
            else:
                assert result.iloc[i]['val'] == value
            assert result.iloc[i]['label'] == label

    def test_classifier_function(self):
        """Test CLASSIFIER() function."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 80]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label,
                NEXT(CLASSIFIER()) AS next_label
            ALL ROWS PER MATCH
            PATTERN (A B+ C+)
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value > PREV(C.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 'A', 'B'),
            (2, 'B', 'B'),
            (3, 'B', 'C'),
            (4, 'C', None)
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, label, next_label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['label'] == label
            if next_label is None:
                assert pd.isna(result.iloc[i]['next_label']) or result.iloc[i]['next_label'] is None
            else:
                assert result.iloc[i]['next_label'] == next_label

    def test_navigation_functions(self):
        """Test navigation functions (PREV, NEXT, FIRST, LAST)."""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'value': [10, 20, 30]
        })
        
        query_template = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES {measure} AS measure
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        # Test RUNNING LAST(value) - default
        query = query_template.format(
            measure="value"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 10),
            (2, 20),
            (3, 30)
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, measure) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['measure'] == measure
            
        # Test FINAL LAST(value)
        query = query_template.format(
            measure="FINAL LAST(value)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 30),
            (2, 30),
            (3, 30)
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, measure) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['measure'] == measure
            
        # Test RUNNING FIRST(value)
        query = query_template.format(
            measure="RUNNING FIRST(value)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 10),
            (2, 10),
            (3, 10)
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, measure) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['measure'] == measure
            
        # Test with logical offset
        query = query_template.format(
            measure="FINAL LAST(value, 2)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 10),
            (2, 10),
            (3, 10)
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, measure) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['measure'] == measure
            
        # Test with physical offset (PREV)
        query = query_template.format(
            measure="PREV(value)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, None),
            (2, 10),
            (3, 20)
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, measure) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            if measure is None:
                assert pd.isna(result.iloc[i]['measure']) or result.iloc[i]['measure'] is None
            else:
                assert result.iloc[i]['measure'] == measure
                
        # Test with physical offset (NEXT)
        query = query_template.format(
            measure="NEXT(value)"
        )
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 20),
            (2, 30),
            (3, None)
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, measure) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            if measure is None:
                assert pd.isna(result.iloc[i]['measure']) or result.iloc[i]['measure'] is None
            else:
                assert result.iloc[i]['measure'] == measure

    def test_partitioning_and_ordering(self):
        """Test PARTITION BY and ORDER BY."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 1, 2, 3, 2, 1, 3, 3],
            'part': ['p1', 'p1', 'p1', 'p1', 'p1', 'p2', 'p2', 'p2', 'p3', 'p3', 'p3', 'p3'],
            'value': [90, 80, 70, 80, 90, 20, 20, 10, 60, 50, 70, 70]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY part
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                PREV(RUNNING LAST(value)) AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            ('p1', 2, 1, 90, 'B'),
            ('p1', 3, 1, 80, 'B'),
            ('p1', 5, 2, 90, 'B'),
            ('p2', 3, 1, 20, 'B')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (part, id_val, match_num, val, label) in enumerate(expected_rows):
            assert result.iloc[i]['part'] == part
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == val
            assert result.iloc[i]['label'] == label

    def test_subset_functionality(self):
        """Test SUBSET functionality."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 80]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                RUNNING LAST(value) AS val,
                CLASSIFIER(U) AS lower_or_higher,
                CLASSIFIER(W) AS label
            ALL ROWS PER MATCH
            PATTERN ((L | H) A)
            SUBSET
                U = (L, H),
                W = (A, L, H)
            DEFINE
                A AS A.value = 80,
                L AS L.value < 80,
                H AS H.value > 80
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 1, 90, 'H', 'H'),
            (2, 1, 80, 'H', 'A'),
            (3, 2, 70, 'L', 'L'),
            (4, 2, 80, 'L', 'A')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, val, lower_or_higher, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match'] == match_num
            assert result.iloc[i]['val'] == val
            assert result.iloc[i]['lower_or_higher'] == lower_or_higher
            assert result.iloc[i]['label'] == label

    def test_match_number_function(self):
        """Test MATCH_NUMBER() function."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 80]
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
            AFTER MATCH SKIP TO NEXT ROW
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 1, 'A'),
            (2, 2, 'A'),
            (3, 3, 'A'),
            (4, 4, 'A')
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, match_num, label) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['match_num'] == match_num
            assert result.iloc[i]['label'] == label

    def test_running_and_final_semantics(self):
        """Test RUNNING and FINAL semantics."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [90, 80, 70, 100, 200]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label,
                FINAL LAST(CLASSIFIER()) AS final_label,
                RUNNING LAST(value) AS running_value,
                FINAL LAST(value) AS final_value,
                RUNNING LAST(A.value) AS A_running_value,
                FINAL LAST(A.value) AS A_final_value,
                RUNNING LAST(B.value) AS B_running_value,
                FINAL LAST(B.value) AS B_final_value,
                RUNNING LAST(C.value) AS C_running_value,
                FINAL LAST(C.value) AS C_final_value
            ALL ROWS PER MATCH
            PATTERN (A B+ C+)
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value > PREV(C.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        expected_rows = [
            (1, 'A', 'C', 90, 200, 90, 90, None, 70, None, 200),
            (2, 'B', 'C', 80, 200, 90, 90, 80, 70, None, 200),
            (3, 'B', 'C', 70, 200, 90, 90, 70, 70, None, 200),
            (4, 'C', 'C', 100, 200, 90, 90, 70, 70, 100, 200),
            (5, 'C', 'C', 200, 200, 90, 90, 70, 70, 200, 200)
        ]
        
        assert len(result) == len(expected_rows)
        
        for i, (id_val, label, final_label, running_value, final_value, 
                A_running_value, A_final_value, B_running_value, B_final_value, 
                C_running_value, C_final_value) in enumerate(expected_rows):
            assert result.iloc[i]['id'] == id_val
            assert result.iloc[i]['label'] == label
            assert result.iloc[i]['final_label'] == final_label
            assert result.iloc[i]['running_value'] == running_value
            assert result.iloc[i]['final_value'] == final_value
            assert result.iloc[i]['A_running_value'] == A_running_value
            assert result.iloc[i]['A_final_value'] == A_final_value
            
            # Handle None values
            if B_running_value is None:
                assert pd.isna(result.iloc[i]['B_running_value']) or result.iloc[i]['B_running_value'] is None
            else:
                assert result.iloc[i]['B_running_value'] == B_running_value
                
            if B_final_value is None:
                assert pd.isna(result.iloc[i]['B_final_value']) or result.iloc[i]['B_final_value'] is None
            else:
                assert result.iloc[i]['B_final_value'] == B_final_value
                
            if C_running_value is None:
                assert pd.isna(result.iloc[i]['C_running_value']) or result.iloc[i]['C_running_value'] is None
            else:
                assert result.iloc[i]['C_running_value'] == C_running_value
                
            if C_final_value is None:
                assert pd.isna(result.iloc[i]['C_final_value']) or result.iloc[i]['C_final_value'] is None
            else:
                assert result.iloc[i]['C_final_value'] == C_final_value
