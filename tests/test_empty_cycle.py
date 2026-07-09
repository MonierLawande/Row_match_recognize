"""
Tests for empty cycle detection to ensure compliance with SQL:2016 standard.
These tests verify that empty cycles are properly detected and handled.
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

class TestEmptyCycle:
    """Test suite for empty cycle detection functionality."""
    
    def test_basic_empty_cycle_detection(self):
        """Test detection of basic empty cycles."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 70]
        })
        
        # Pattern A* where A never matches should create empty cycles
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
            PATTERN (A*)
            DEFINE A AS false  -- Never matches, creates empty cycles
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should produce empty matches for each row
        expected = pd.DataFrame({
            'row_id': [1, 2, 3, 4],
            'match': [1, 2, 3, 4],
            'val': [None, None, None, None],
            'label': [None, None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_cycle_with_plus_quantifier(self):
        """Test empty cycle detection with + quantifier."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 70]
        })
        
        # Pattern A+ where A never matches should not produce any results
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
            PATTERN (A+)
            DEFINE A AS false  -- Never matches
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result.empty

    def test_empty_cycle_with_complex_pattern(self):
        """Test empty cycle detection in complex patterns."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        # Pattern B* A* C where B and C match but A doesn't
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
            PATTERN (B* A* C)
            DEFINE 
                A AS false,  -- Never matches, empty cycle
                B AS value = 10,
                C AS value = 20
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should match B (empty A*) C pattern
        expected = pd.DataFrame({
            'row_id': [1, 2],
            'match': [1, 1],
            'val': [10, 20],
            'label': ['B', 'C']
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_cycle_alternation(self):
        """Test empty cycle detection with alternation."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        # Pattern (A | B)* where both A and B never match
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
            PATTERN ((A | B)*)
            DEFINE 
                A AS false,
                B AS false
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should produce empty matches
        expected = pd.DataFrame({
            'row_id': [1, 2, 3, 4],
            'match': [1, 2, 3, 4],
            'val': [None, None, None, None],
            'label': [None, None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_cycle_with_measures(self):
        """Test empty cycle behavior with various measures."""
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
            FIRST(value) AS first_val,
            LAST(value) AS last_val
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                CLASSIFIER() AS label,
                COUNT(*) AS row_count,
                FIRST(value) AS first_val,
                LAST(value) AS last_val
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS false
        ) AS m
        """
        
        result = match_recognize(query, df)
        expected = pd.DataFrame({
            'row_id': [1, 2, 3],
            'match': [1, 2, 3],
            'label': [None, None, None],
            'row_count': [0, 0, 0],  # Empty matches have count 0
            'first_val': [None, None, None],
            'last_val': [None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_cycle_prevention_infinite_loop(self):
        """Test that empty cycles don't cause infinite loops."""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'value': [10, 20, 30]
        })
        
        # Nested empty cycles that could cause infinite recursion
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
            PATTERN ((A*)*)
            DEFINE A AS false
        ) AS m
        """
        
        # Should complete without hanging and produce empty matches
        result = match_recognize(query, df)
        assert len(result) == 3  # Should not hang, should produce results
        assert all(result['label'].isna())  # All labels should be null

    def test_empty_cycle_with_reluctant_quantifier(self):
        """Test empty cycle with reluctant quantifiers."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        # Pattern A*? with condition that never matches
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
            PATTERN (A*?)
            DEFINE A AS false
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Reluctant quantifier should prefer empty match
        expected = pd.DataFrame({
            'row_id': [1, 2, 3, 4],
            'match': [1, 2, 3, 4],
            'val': [None, None, None, None],
            'label': [None, None, None, None]
        })
        pd.testing.assert_frame_equal(result.reset_index(drop=True), expected, check_dtype=False)

    def test_empty_cycle_detection_complex_scenario(self):
        """Test empty cycle detection in a complex real-world scenario."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'stock': ['A', 'A', 'A', 'B', 'B', 'B'],
            'price': [100, 105, 95, 200, 210, 190],
            'volume': [1000, 1500, 800, 2000, 2500, 1800]
        })
        
        # Look for pattern: UP* DOWN* SPIKE where some conditions might create empty cycles
        query = """
        SELECT 
            id AS row_id, 
            stock,
            MATCH_NUMBER() AS match,
            CLASSIFIER() AS label,
            price,
            volume
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY stock
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                CLASSIFIER() AS label,
                price AS price,
                volume AS volume
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (UP* DOWN* SPIKE)
            DEFINE 
                UP AS price > PREV(price),
                DOWN AS price < PREV(price),
                SPIKE AS volume > 2000  -- Only row 4 and 5 satisfy this
        ) AS m
        """
        
        result = match_recognize(query, df)
        # Should handle empty UP* and DOWN* cycles gracefully
        assert not result.empty
        # Should find matches where SPIKE condition is met
        spike_rows = result[result['label'] == 'SPIKE']
        assert len(spike_rows) > 0

# ----------------------------------------------------------------------------
# Faithful conversion of testEmptyCycle from src/TestRowPatternMatching.java
# (all 12 assertions, exact expected values).
# Data: (1,90),(2,80),(3,70),(4,70); DEFINE B AS B.value < PREV (B.value)
# ----------------------------------------------------------------------------

from tests.test_java_reference_parity import run_query, assert_rows

JAVA_EMPTY_CYCLE_QUERY = """
SELECT m.id AS row_id, m.match, m.val, m.label
FROM data
MATCH_RECOGNIZE (
    ORDER BY id
    MEASURES match_number() AS match, RUNNING LAST(value) AS val, classifier() AS label
    ALL ROWS PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN ({pattern})
    DEFINE B AS B.value < PREV (B.value)
) AS m
"""

_ALL_EMPTY4 = [(1, 1, None, None), (2, 2, None, None), (3, 3, None, None), (4, 4, None, None)]

_EMPTY_GROUP_XFAIL = pytest.mark.xfail(
    reason="engine gap: empty-group patterns crash (has_empty_alternation init order)")
_ANCHOR_QUANT_XFAIL = pytest.mark.xfail(
    reason="engine gap: quantified anchors (^*, $+, ...) unsupported")

JAVA_EMPTY_CYCLE_CASES = [
    ("()* | B", _ALL_EMPTY4),
    ("()+ | B", _ALL_EMPTY4),
    ("(){5,} | B", _ALL_EMPTY4),
    ("B | ()*", [(1, 1, None, None), (2, 2, 80, "B"), (3, 3, 70, "B"), (4, 4, None, None)]),
    ("(B ()*)*", [(1, 1, None, None), (2, 2, 80, "B"), (3, 2, 70, "B"), (4, 3, None, None)]),
    ("(B ()*)*?", _ALL_EMPTY4),
    ("^* | B", _ALL_EMPTY4),
    ("^+ | B", [(1, 1, None, None), (2, 2, 80, "B"), (3, 3, 70, "B")]),
    ("^* A B", [(1, 1, 90, "A"), (2, 1, 80, "B")]),
    ("$* | B", _ALL_EMPTY4),
    pytest.param("$+ | B", [(2, 1, 80, "B"), (3, 2, 70, "B")], marks=_ANCHOR_QUANT_XFAIL),
    ("B A $+", [(3, 1, 70, "B"), (4, 1, 70, "A")]),
]


class TestEmptyCycleJavaReference:
    """All 12 testEmptyCycle assertions with Trino's exact expected outputs."""

    @pytest.fixture
    def df4(self):
        return pd.DataFrame({"id": [1, 2, 3, 4], "value": [90, 80, 70, 70]})

    @pytest.mark.parametrize("pattern,expected", JAVA_EMPTY_CYCLE_CASES,
                             ids=[(c.values[0] if hasattr(c, 'values') else c[0]) for c in JAVA_EMPTY_CYCLE_CASES])
    def test_java_empty_cycle(self, df4, pattern, expected):
        result = run_query(JAVA_EMPTY_CYCLE_QUERY.format(pattern=pattern), df4)
        assert_rows(result, expected, ["row_id", "match", "val", "label"])


if __name__ == "__main__":
    pytest.main([__file__])
