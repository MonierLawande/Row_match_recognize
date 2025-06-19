"""
Tests for back reference functionality in match_recognize.

This module tests the ability to reference previously matched pattern variables
in DEFINE conditions, which is a key feature for complex pattern matching.
"""

from src.executor.match_recognize import match_recognize
import pytest
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple

# Add the src directory to path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the match_recognize implementation


class TestBackReference:
    """Test suite for back reference functionality in match_recognize."""

    def test_simple_back_reference(self):
        """Test defining condition of X refers to input values at matched label A."""
        df = pd.DataFrame({
            'value': [1, 1]
        })

        query = """
        SELECT value, classy
        FROM data
        MATCH_RECOGNIZE (
            MEASURES CLASSIFIER() AS classy
            ALL ROWS PER MATCH
            PATTERN ((A | B)* X)
            DEFINE X AS value = A.value
        )
        """

        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty

        expected_rows = [
            (1, 'A'),
            (1, 'X')
        ]

        assert len(result) == len(expected_rows)

        for i, (value, classy) in enumerate(expected_rows):
            assert result.iloc[i]['value'] == value
            assert result.iloc[i]['classy'] == classy

    def test_back_reference_to_b_label(self):
        """Test defining condition of X refers to input values at matched label B."""
        df = pd.DataFrame({
            'value': [1, 1]
        })

        query = """
        SELECT value, classy
        FROM data
        MATCH_RECOGNIZE (
            MEASURES CLASSIFIER() AS classy
            ALL ROWS PER MATCH
            PATTERN ((A | B)* X)
            DEFINE X AS value = B.value
        )
        """

        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty

        expected_rows = [
            (1, 'B'),
            (1, 'X')
        ]

        assert len(result) == len(expected_rows)

        for i, (value, classy) in enumerate(expected_rows):
            assert result.iloc[i]['value'] == value
            assert result.iloc[i]['classy'] == classy

    def test_complex_back_reference(self):
        """Test defining condition of X refers to input values at matched labels A and B."""
        df = pd.DataFrame({
            'value': [1, 2, 3, 4, 5, 6]
        })

        query = """
        SELECT value, classy, defining_condition
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY value
            MEASURES
                CLASSIFIER() AS classy,
                PREV(LAST(A.value), 3) + FIRST(A.value) + PREV(LAST(B.value), 2) AS defining_condition
            ALL ROWS PER MATCH
            PATTERN ((A | B)* X)
            DEFINE X AS value = PREV(LAST(A.value), 3) + FIRST(A.value) + PREV(LAST(B.value), 2)
        )
        """

        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty

        expected_rows = [
            (1, 'B', None),
            (2, 'A', None),
            (3, 'A', None),
            (4, 'A', None),
            (5, 'B', 6),
            (6, 'X', 6)
        ]

        assert len(result) == len(expected_rows)

        for i, (value, classy, defining_condition) in enumerate(expected_rows):
            assert result.iloc[i]['value'] == value
            assert result.iloc[i]['classy'] == classy
            if defining_condition is None:
                assert pd.isna(result.iloc[i]['defining_condition']
                               ) or result.iloc[i]['defining_condition'] is None
            else:
                assert result.iloc[i]['defining_condition'] == defining_condition

    def test_back_reference_with_classifier(self):
        """Test defining condition of X refers to matched labels A and B using CLASSIFIER."""
        df = pd.DataFrame({
            'value': [1, 2, 3, 4, 5]
        })

        query = """
        SELECT value, classy, defining_condition
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY value
            MEASURES
                CLASSIFIER() AS classy,
                PREV(CLASSIFIER(U), 1) = 'A' AND LAST(CLASSIFIER(), 3) = 'B' AND FIRST(CLASSIFIER(U)) = 'B' AS defining_condition
            ALL ROWS PER MATCH
            PATTERN ((A | B)* X $)
            SUBSET U = (A, B)
            DEFINE X AS PREV(CLASSIFIER(U), 1) = 'A' AND LAST(CLASSIFIER(), 3) = 'B' AND FIRST(CLASSIFIER(U)) = 'B'
        )
        """

        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty

        expected_rows = [
            (1, 'B', None),
            (2, 'B', False),
            (3, 'A', False),
            (4, 'A', True),
            (5, 'X', True)
        ]

        assert len(result) == len(expected_rows)

        for i, (value, classy, defining_condition) in enumerate(expected_rows):
            assert result.iloc[i]['value'] == value
            assert result.iloc[i]['classy'] == classy
            if defining_condition is None:
                assert pd.isna(result.iloc[i]['defining_condition']
                               ) or result.iloc[i]['defining_condition'] is None
            else:
                assert result.iloc[i]['defining_condition'] == defining_condition

    def test_nested_navigation_functions(self):
        """Test navigation with various nested function combinations."""
        df = pd.DataFrame({
            'value': [1, 2, 3, 4, 5, 6, 7, 8]
        })

        test_cases = [
            # Test case 1: LAST(A.value) + 1 (simple nested function)
            (
                """
                PATTERN (A+ X)
                DEFINE X AS value = LAST(A.value) + 1
                """,
                [(1, 'A'), (2, 'X')],
                2  # X.value = LAST(A.value=1) + 1 = 2
            ),
            # Test case 2: FIRST(A.value) + 3 with longer A sequence  
            (
                """
                PATTERN (A{2,} X)
                DEFINE X AS value = FIRST(A.value) + 3
                """,
                [(1, 'A'), (2, 'A'), (3, 'A'), (4, 'X')],
                4  # X.value = FIRST(A.value=1) + 3 = 4
            ),
            # Test case 3: Complex nested navigation with alternation
            (
                """
                PATTERN ((A | B)+ X)
                DEFINE 
                    A AS value % 2 = 1,
                    B AS value % 2 = 0,
                    X AS value = LAST(A.value) + FIRST(B.value)
                """,
                [(1, 'A'), (2, 'B'), (3, 'X')],
                3  # X.value = LAST(A.value=1) + FIRST(B.value=2) = 3
            ),
        ]

        for pattern_def, expected_classes, expected_x_value in test_cases:
            query = f'''
            SELECT value, classy
            FROM data
            MATCH_RECOGNIZE (
                ORDER BY value
                MEASURES
                    CLASSIFIER() as classy
                ALL ROWS PER MATCH
                {pattern_def}
            )
            '''

            result = match_recognize(query, df)
            assert result is not None
            assert not result.empty

            # Verify classifications - get first match only
            actual_classes = list(zip(result['value'], result['classy']))
            match_1_classes = []
            for val, cls in actual_classes:
                match_1_classes.append((val, cls))
                if cls == 'X':  # Stop after first match ends
                    break
            
            assert match_1_classes == expected_classes

            # Verify X value matches expected
            x_row = result[result['classy'] == 'X'].iloc[0]
            assert x_row['value'] == expected_x_value
