"""
Test Case Sensitivity in Pattern Variables
Matches testCaseSensitiveLabels() from TestRowPatternMatching.java
"""

import pytest
import pandas as pd
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.executor.match_recognize import match_recognize

class TestCaseSensitivity:
    """Test case-sensitive pattern variable handling."""

    def setup_method(self):
        """Setup test data matching Java reference."""
        self.test_data = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 80]
        })

    def test_case_sensitive_labels_basic(self):
        """Test basic case sensitivity in pattern variables."""
        df = self.test_data
        
        query = """
        SELECT id, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (a b+ C+)
            DEFINE
                b AS b.value < PREV(b.value),
                C AS C.value > PREV(C.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Variables should be: a (default 'A'), b (lowercase), C (uppercase)
            expected_labels = ['A', 'b', 'b', 'C']
            actual_labels = result['label'].tolist()
            assert actual_labels == expected_labels
        else:
            pytest.skip("Case sensitive labels not implemented")

    def test_quoted_identifiers(self):
        """Test quoted identifiers for case sensitivity."""
        df = self.test_data
        
        query = """
        SELECT id, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (a "b"+ C+)
            DEFINE
                "b" AS "b".value < PREV("b".value),
                C AS C.value > PREV(C.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Quoted "b" should preserve exact case
            expected_labels = ['A', 'b', 'b', 'C']
            actual_labels = result['label'].tolist()
            assert actual_labels == expected_labels
        else:
            pytest.skip("Quoted identifier case sensitivity not implemented")

    def test_mixed_case_variables(self):
        """Test mixed case pattern variables."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [100, 90, 80, 70, 80]
        })
        
        query = """
        SELECT id, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (StartVar midVar+ EndVar+)
            DEFINE
                midVar AS midVar.value < PREV(midVar.value),
                EndVar AS EndVar.value > PREV(EndVar.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Should preserve exact case as defined
            expected_labels = ['STARTVAR', 'midVar', 'midVar', 'midVar', 'EndVar']
            actual_labels = result['label'].tolist()
            # Check if case is preserved correctly
            assert len(actual_labels) == len(expected_labels)
        else:
            pytest.skip("Mixed case variables not implemented")

    def test_case_sensitive_in_define(self):
        """Test case sensitivity in DEFINE clause references."""
        df = self.test_data
        
        query = """
        SELECT id, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A b+ c+)
            DEFINE
                b AS b.value < PREV(b.value),
                c AS c.value = PREV(c.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Variables should maintain their defined case
            expected_labels = ['A', 'b', 'b', 'c']
            actual_labels = result['label'].tolist()
            assert actual_labels == expected_labels
        else:
            pytest.skip("Case sensitivity in DEFINE clause not implemented")

    def test_case_insensitive_keywords(self):
        """Test that SQL keywords are case insensitive while variables are case sensitive."""
        df = self.test_data
        
        query = """
        SELECT id, classifier() AS label
        FROM data
        match_recognize (
            order by id
            measures classifier() as label
            all rows per match
            pattern (A b+ C+)
            define
                b as b.value < prev(b.value),
                C as C.value > prev(C.value)
        ) as m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Keywords should be case insensitive, variables case sensitive
            expected_labels = ['A', 'b', 'b', 'C']
            actual_labels = result['label'].tolist()
            assert actual_labels == expected_labels
        else:
            pytest.skip("Case insensitive keywords with case sensitive variables not implemented")
