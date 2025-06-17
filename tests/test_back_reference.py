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
