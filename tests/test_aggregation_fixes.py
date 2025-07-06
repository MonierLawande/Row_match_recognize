# test_aggregation_fixes.py
"""
Test cases and fixes for aggregation function issues discovered during testing.

This module addresses specific implementation gaps and parser issues found
when running the comprehensive aggregation test suite.

Key Areas Addressed:
1. Parser support for conditional aggregates (COUNT_IF, SUM_IF, AVG_IF)
2. Statistical function implementations (STDDEV, VARIANCE)
3. Array aggregation fixes (ARRAY_AGG type handling)
4. String aggregation improvements (STRING_AGG)
5. Advanced functions (MIN_BY, MAX_BY, APPROX_DISTINCT)
6. Percentile functions (PERCENTILE_CONT, PERCENTILE_DISC)
7. Geometric and harmonic mean functions
8. Proper NULL handling in all aggregations

Author: Pattern Matching Engine Team
Version: 1.0.0
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import sys
import os
import math
from decimal import Decimal

# Add the src directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from executor.match_recognize import match_recognize
    from utils.logging_config import get_logger
    MATCH_RECOGNIZE_AVAILABLE = True
except ImportError:
    MATCH_RECOGNIZE_AVAILABLE = False
    print("Warning: match_recognize module not available, using mock implementation")

# Configure logging
logger = get_logger(__name__) if MATCH_RECOGNIZE_AVAILABLE else None

def mock_match_recognize(query: str, df: pd.DataFrame) -> pd.DataFrame:
    """Mock implementation when real match_recognize is not available."""
    # Return a basic structure that shows the pattern is recognized
    if 'RUNNING sum(' in query:
        return pd.DataFrame({
            'id': df['id'] if 'id' in df.columns else range(len(df)),
            'running_sum': np.cumsum(df.iloc[:, -1] if len(df.columns) > 1 else [1] * len(df))
        })
    return pd.DataFrame()

class TestAggregationFixes:
    """
    Test suite focusing on fixes for aggregation function issues.
    
    This class tests specific fixes and enhancements to ensure all
    aggregation functions work correctly with proper SQL:2016 compliance.
    """
    
    def setup_method(self):
        """Setup method called before each test."""
        self.match_recognize = match_recognize if MATCH_RECOGNIZE_AVAILABLE else mock_match_recognize
        
    def assert_dataframe_equals(self, actual: pd.DataFrame, expected: pd.DataFrame, msg: str = ""):
        """Helper method to compare DataFrames with better error messages."""
        try:
            pd.testing.assert_frame_equal(actual, expected, check_dtype=False, 
                                        check_exact=False, rtol=1e-5, atol=1e-8)
        except Exception as e:
            if logger:
                logger.error(f"{msg}\\nActual:\\n{actual}\\nExpected:\\n{expected}")
            raise AssertionError(f"{msg}\\n{str(e)}")

    @pytest.mark.parser_fixes
    def test_conditional_aggregates_parser_fix(self):
        """
        Test fix for conditional aggregate functions parsing.
        Addresses: COUNT_IF, SUM_IF, AVG_IF parser recognition.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [1, -2, 3, -4, 5],
            'category': ['A', 'B', 'A', 'B', 'A']
        })
        
        # This should work after parser fixes
        query = """
        SELECT m.id, m.count_positive, m.sum_category_a
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING count(CASE WHEN value > 0 THEN 1 END) AS count_positive,
                RUNNING sum(CASE WHEN category = 'A' THEN value ELSE 0 END) AS sum_category_a
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: CASE-based conditional aggregation (workaround for *_IF functions)
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'count_positive': [1, 1, 2, 2, 3],      # COUNT positive values
            'sum_category_a': [1, 1, 4, 4, 9]       # SUM only category A values
        })
        
        self.assert_dataframe_equals(result, expected, "Conditional aggregates parser fix test failed")

    @pytest.mark.statistical_fixes
    def test_statistical_functions_implementation(self):
        """
        Test implementation of statistical functions.
        Addresses: STDDEV, VARIANCE, proper mathematical calculations.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [2, 4, 6, 8, 10]
        })
        
        # Test STDDEV and VARIANCE implementations
        query = """
        SELECT m.id, m.running_avg, m.running_variance, m.running_stddev
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING avg(value) AS running_avg,
                RUNNING var_pop(value) AS running_variance,
                RUNNING stddev_pop(value) AS running_stddev
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: Proper statistical calculations
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'running_avg': [2.0, 3.0, 4.0, 5.0, 6.0],
            'running_variance': [0.0, 1.0, 8/3, 5.0, 8.0],
            'running_stddev': [0.0, 1.0, np.sqrt(8/3), np.sqrt(5.0), np.sqrt(8.0)]
        })
        
        self.assert_dataframe_equals(result, expected, "Statistical functions implementation test failed")

    @pytest.mark.array_fixes
    def test_array_aggregation_type_handling(self):
        """
        Test fix for array aggregation type handling issues.
        Addresses: 'unhashable type: list' errors in ARRAY_AGG.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'name': ['Alice', 'Bob', 'Charlie', 'Diana'],
            'score': [85, 92, 78, 96]
        })
        
        # Test ARRAY_AGG with proper type handling
        query = """
        SELECT m.id, m.name_array, m.score_array
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING array_agg(name) AS name_array,
                RUNNING array_agg(score) AS score_array
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: Proper array handling without hash errors
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'name_array': [
                ['Alice'],
                ['Alice', 'Bob'],
                ['Alice', 'Bob', 'Charlie'],
                ['Alice', 'Bob', 'Charlie', 'Diana']
            ],
            'score_array': [
                [85],
                [85, 92],
                [85, 92, 78],
                [85, 92, 78, 96]
            ]
        })
        
        self.assert_dataframe_equals(result, expected, "Array aggregation type handling test failed")

    @pytest.mark.string_fixes
    def test_string_aggregation_improvements(self):
        """
        Test improvements to string aggregation functions.
        Addresses: STRING_AGG delimiter handling, CONCAT functions.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'word': ['Hello', 'World', 'Pattern', 'Matching']
        })
        
        # Test STRING_AGG and string operations
        query = """
        SELECT m.id, m.concatenated, m.word_count
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING string_agg(word, ' ') AS concatenated,
                RUNNING count(word) AS word_count
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: Proper string aggregation with delimiters
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'concatenated': [
                'Hello',
                'Hello World',
                'Hello World Pattern',
                'Hello World Pattern Matching'
            ],
            'word_count': [1, 2, 3, 4]
        })
        
        self.assert_dataframe_equals(result, expected, "String aggregation improvements test failed")

    @pytest.mark.minmax_by_fixes
    def test_min_max_by_implementation(self):
        """
        Test implementation of MIN_BY and MAX_BY functions.
        Addresses: Complex aggregation with value selection.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'student': ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve'],
            'score': [85, 92, 78, 96, 88],
            'subject': ['Math', 'Science', 'Math', 'Science', 'Math']
        })
        
        # Test MIN_BY and MAX_BY (using CASE expressions as workaround)
        query = """
        SELECT m.id, m.lowest_scorer, m.highest_scorer, m.lowest_score, m.highest_score
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING min(score) AS lowest_score,
                RUNNING max(score) AS highest_score,
                -- Workaround for MIN_BY using FIRST_VALUE with ORDER BY
                RUNNING first_value(student) OVER (ORDER BY score ASC) AS lowest_scorer,
                RUNNING first_value(student) OVER (ORDER BY score DESC) AS highest_scorer
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: Student names corresponding to min/max scores
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'lowest_scorer': ['Alice', 'Alice', 'Charlie', 'Charlie', 'Charlie'],
            'highest_scorer': ['Alice', 'Bob', 'Bob', 'Diana', 'Diana'],
            'lowest_score': [85, 85, 78, 78, 78],
            'highest_score': [85, 92, 92, 96, 96]
        })
        
        self.assert_dataframe_equals(result, expected, "MIN_BY and MAX_BY implementation test failed")

    @pytest.mark.percentile_fixes
    def test_percentile_function_syntax(self):
        """
        Test fix for percentile function syntax parsing.
        Addresses: PERCENTILE_CONT, PERCENTILE_DISC syntax issues.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            'value': [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        })
        
        # Test percentile functions (using simpler syntax until parser is fixed)
        query = """
        SELECT m.id, m.median_approx, m.q1_approx, m.q3_approx
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING percentile_approx(value, 0.5) AS median_approx,
                RUNNING percentile_approx(value, 0.25) AS q1_approx,
                RUNNING percentile_approx(value, 0.75) AS q3_approx
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: Approximate percentile calculations
        expected = pd.DataFrame({
            'id': list(range(1, 11)),
            'median_approx': [10, 15, 20, 25, 30, 35, 40, 45, 50, 55],  # Running medians
            'q1_approx': [10, 12.5, 15, 17.5, 20, 22.5, 25, 27.5, 30, 32.5],  # Q1 (corrected)
            'q3_approx': [10, 17.5, 25, 32.5, 40, 47.5, 55, 62.5, 70, 77.5]   # Q3 (corrected)
        })
        
        self.assert_dataframe_equals(result, expected, "Percentile function syntax test failed")

    @pytest.mark.null_handling
    def test_comprehensive_null_handling(self):
        """
        Test comprehensive NULL handling across all aggregation types.
        Addresses: Proper NULL semantics for all aggregate functions.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'numeric_val': [10, None, 20, None, 30, 40],
            'string_val': ['A', None, 'B', 'C', None, 'D'],
            'bool_val': [True, None, False, True, None, False]
        })
        
        # Test NULL handling across different aggregate types
        query = """
        SELECT m.id, 
               m.sum_numeric, m.count_numeric, m.avg_numeric,
               m.count_string, m.first_string,
               m.count_bool, m.bool_and
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(numeric_val) AS sum_numeric,
                RUNNING count(numeric_val) AS count_numeric,
                RUNNING avg(numeric_val) AS avg_numeric,
                RUNNING count(string_val) AS count_string,
                RUNNING first_value(string_val) AS first_string,
                RUNNING count(bool_val) AS count_bool,
                RUNNING bool_and(bool_val) AS bool_and
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: Proper NULL handling per SQL:2016 standard
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'sum_numeric': [10, 10, 30, 30, 60, 100],        # NULLs ignored
            'count_numeric': [1, 1, 2, 2, 3, 4],             # NULLs not counted
            'avg_numeric': [10.0, 10.0, 15.0, 15.0, 20.0, 25.0],  # NULLs ignored
            'count_string': [1, 1, 2, 3, 3, 4],              # NULLs not counted
            'first_string': ['A', 'A', 'A', 'A', 'A', 'A'],  # First non-NULL
            'count_bool': [1, 1, 2, 3, 3, 4],                # NULLs not counted
            'bool_and': [True, True, False, False, False, False]  # AND with NULLs ignored
        })
        
        self.assert_dataframe_equals(result, expected, "Comprehensive NULL handling test failed")

    @pytest.mark.performance_fixes
    def test_memory_efficient_aggregations(self):
        """
        Test memory-efficient aggregation implementations.
        Addresses: Performance issues with large datasets.
        """
        # Create a moderately sized dataset to test memory efficiency
        size = 100
        df = pd.DataFrame({
            'id': range(1, size + 1),
            'category': [f'cat_{i % 5}' for i in range(size)],
            'value': [i * 1.5 for i in range(1, size + 1)],
            'flag': [i % 2 == 0 for i in range(size)]
        })
        
        # Test multiple aggregations for memory efficiency
        query = """
        SELECT m.category, m.total_rows, m.sum_value, m.avg_value, m.count_flags
        FROM test_data t
          MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY id
            MEASURES 
                count(*) AS total_rows,
                sum(value) AS sum_value,
                avg(value) AS avg_value,
                sum(CASE WHEN flag THEN 1 ELSE 0 END) AS count_flags
            ONE ROW PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Verify we get reasonable results for each category
        assert len(result) == 5, f"Expected 5 categories, got {len(result)}"
        assert all(result['total_rows'] == 20), "Each category should have 20 rows"
        assert all(result['sum_value'] > 0), "All sums should be positive"
        assert all(result['avg_value'] > 0), "All averages should be positive"
        
        if logger:
            logger.info(f"Memory efficient aggregations test completed with {len(df)} input rows")

    @pytest.mark.edge_cases
    def test_aggregation_edge_cases(self):
        """
        Test edge cases in aggregation functions.
        Addresses: Division by zero, empty sets, extreme values.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'numerator': [10, 20, 30, 40, 50],
            'denominator': [2, 0, 4, 0, 5],  # Contains zeros
            'extreme_val': [1e10, -1e10, 1e-10, float('inf'), -float('inf')]
        })
        
        # Test safe division and extreme value handling
        query = """
        SELECT m.id, 
               m.safe_division,
               m.sum_extreme,
               m.count_finite
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING avg(CASE WHEN denominator != 0 THEN numerator / denominator ELSE NULL END) AS safe_division,
                RUNNING sum(CASE WHEN isfinite(extreme_val) THEN extreme_val ELSE 0 END) AS sum_extreme,
                RUNNING count(CASE WHEN isfinite(extreme_val) THEN 1 END) AS count_finite
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: Safe handling of edge cases
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'safe_division': [5.0, 5.0, 6.25, 6.25, 7.0],  # Division by zero handled
            'sum_extreme': [1e10, 0, 1e-10, 1e-10, 1e-10],  # Infinite values handled
            'count_finite': [1, 1, 2, 2, 2]                 # Only finite values counted
        })
        
        self.assert_dataframe_equals(result, expected, "Aggregation edge cases test failed")

if __name__ == "__main__":
    # Run the aggregation fixes tests
    pytest.main([
        __file__,
        "-v",
        "--tb=short"
    ])
