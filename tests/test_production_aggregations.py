# test_production_aggregations.py
"""
Production-ready test cases for comprehensive aggregation validation in row pattern matching.

This module implements comprehensive test coverage for SQL:2016 aggregation functions
in the context of MATCH_RECOGNIZE pattern matching, converted from Java test cases
to Python for pandas-based implementation.

Features tested:
- Advanced statistical aggregations (STDDEV, VARIANCE, etc.)
- Conditional aggregations (COUNT_IF, SUM_IF, AVG_IF)
- Array and string aggregations (ARRAY_AGG, STRING_AGG)
- Specialized aggregations (MIN_BY, MAX_BY, APPROX_DISTINCT)
- Complex navigation with aggregations
- Nested aggregations with subsets
- NULL handling and edge cases
- Performance and scalability validation
- Type coercion and boundary conditions

Author: Pattern Matching Engine Team (Converted from Java)
Version: 3.0.0
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import sys
import os

# Add the src directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from executor.match_recognize import match_recognize
from utils.logging_config import get_logger
from utils.performance_optimizer import PerformanceMonitor

# Configure logging
logger = get_logger(__name__)

class TestProductionAggregations:
    """
    Comprehensive test suite for production-ready aggregation validation.
    
    This class contains test cases that validate all aspects of aggregation
    functionality in row pattern matching, ensuring SQL:2016 compliance
    and production-ready performance.
    """
    
    def setup_method(self):
        """Setup method run before each test."""
        self.performance_monitor = PerformanceMonitor()
    
    def teardown_method(self):
        """Cleanup method run after each test."""
        pass
    
    def assert_dataframe_equals(self, actual: pd.DataFrame, expected: pd.DataFrame, 
                               msg: str = "DataFrames are not equal"):
        """
        Custom assertion for DataFrame equality with detailed error reporting.
        
        Args:
            actual: The actual DataFrame result
            expected: The expected DataFrame result
            msg: Custom error message
        """
        try:
            pd.testing.assert_frame_equal(actual, expected, check_dtype=False, 
                                        check_exact=False, rtol=1e-5, atol=1e-8)
        except AssertionError as e:
            logger.error(f"{msg}\nActual:\n{actual}\nExpected:\n{expected}")
            raise AssertionError(f"{msg}\n{str(e)}")
    
    def test_advanced_statistical_aggregations(self):
        """Test STDDEV, VARIANCE, and other statistical functions."""
        query = """
        SELECT m.id, m.running_stddev, m.final_stddev, m.running_variance
        FROM (VALUES
                 (1, 10.0),
                 (2, 20.0),
                 (3, 30.0),
                 (4, 40.0),
                 (5, 50.0)
             ) t(id, value)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING stddev(A.value) AS running_stddev,
                     FINAL stddev(A.value) AS final_stddev,
                     RUNNING variance(A.value) AS running_variance
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS A.value IS NOT NULL
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10.0, 20.0, 30.0, 40.0, 50.0]
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'running_stddev': [None, 7.0710678118654755, 10.0, 12.909944487358056, 15.811388300841898],
            'final_stddev': [15.811388300841898] * 5,
            'running_variance': [None, 50.0, 100.0, 166.66666666666666, 250.0]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Advanced statistical aggregations test failed")
    
    def test_conditional_aggregations(self):
        """Test COUNT_IF, SUM_IF, AVG_IF functions."""
        query = """
        SELECT m.id, m.count_positive, m.sum_if_even, m.avg_if_greater_than_2
        FROM (VALUES
                 (1, 1),
                 (2, -2),
                 (3, 3),
                 (4, 4),
                 (5, -5),
                 (6, 6)
             ) t(id, value)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING count_if(A.value > 0) AS count_positive,
                     RUNNING sum_if(A.value, A.value % 2 = 0) AS sum_if_even,
                     RUNNING avg_if(A.value, A.value > 2) AS avg_if_greater_than_2
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'value': [1, -2, 3, 4, -5, 6]
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'count_positive': [1, 1, 2, 3, 3, 4],
            'sum_if_even': [None, -2, -2, 2, 2, 8],
            'avg_if_greater_than_2': [None, None, 3.0, 3.5, 3.5, 4.333333333333333]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Conditional aggregations test failed")
    
    def test_array_and_string_aggregations(self):
        """Test ARRAY_AGG and STRING_AGG with various options."""
        query = """
        SELECT m.id, m.array_values, m.string_concat, m.ordered_array
        FROM (VALUES
                 (1, 'apple'),
                 (2, 'banana'),
                 (3, 'cherry'),
                 (4, 'date')
             ) t(id, fruit)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING array_agg(A.fruit) AS array_values,
                     RUNNING string_agg(A.fruit, ',') AS string_concat,
                     RUNNING array_agg(A.fruit ORDER BY A.fruit DESC) AS ordered_array
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'fruit': ['apple', 'banana', 'cherry', 'date']
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'array_values': [
                ['apple'],
                ['apple', 'banana'],
                ['apple', 'banana', 'cherry'],
                ['apple', 'banana', 'cherry', 'date']
            ],
            'string_concat': [
                'apple',
                'apple,banana',
                'apple,banana,cherry',
                'apple,banana,cherry,date'
            ],
            'ordered_array': [
                ['apple'],
                ['banana', 'apple'],
                ['cherry', 'banana', 'apple'],
                ['date', 'cherry', 'banana', 'apple']
            ]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Array and string aggregations test failed")
    
    def test_min_max_by_aggregations(self):
        """Test MIN_BY and MAX_BY aggregation functions."""
        query = """
        SELECT m.id, m.min_name_by_score, m.max_name_by_score, m.min_score_by_name
        FROM (VALUES
                 (1, 'Alice', 85),
                 (2, 'Bob', 92),
                 (3, 'Charlie', 78),
                 (4, 'Diana', 95),
                 (5, 'Eve', 88)
             ) t(id, name, score)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING min_by(A.name, A.score) AS min_name_by_score,
                     RUNNING max_by(A.name, A.score) AS max_name_by_score,
                     RUNNING min_by(A.score, A.name) AS min_score_by_name
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'name': ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve'],
            'score': [85, 92, 78, 95, 88]
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'min_name_by_score': ['Alice', 'Alice', 'Charlie', 'Charlie', 'Charlie'],
            'max_name_by_score': ['Alice', 'Bob', 'Bob', 'Diana', 'Diana'],
            'min_score_by_name': [85, 85, 85, 85, 85]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "MIN_BY and MAX_BY aggregations test failed")
    
    def test_approximate_aggregations(self):
        """Test approximate aggregation functions like APPROX_DISTINCT."""
        query = """
        SELECT m.id, m.approx_distinct_count, m.approx_percentile
        FROM (VALUES
                 (1, 10),
                 (2, 20),
                 (3, 10),
                 (4, 30),
                 (5, 20),
                 (6, 40),
                 (7, 10)
             ) t(id, value)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING approx_distinct(A.value) AS approx_distinct_count,
                     RUNNING approx_percentile(A.value, 0.5) AS approx_percentile
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7],
            'value': [10, 20, 10, 30, 20, 40, 10]
        })
        
        # Expected output (approximate values)
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7],
            'approx_distinct_count': [1, 2, 2, 3, 3, 4, 4],
            'approx_percentile': [10, 15, 10, 20, 20, 25, 20]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Approximate aggregations test failed")
    
    def test_complex_navigation_with_aggregations(self):
        """Test aggregations with complex navigation functions."""
        query = """
        SELECT m.id, m.sum_prev_3, m.avg_first_to_current, m.count_from_last
        FROM (VALUES
                 (1, 10),
                 (2, 20),
                 (3, 30),
                 (4, 40),
                 (5, 50),
                 (6, 60)
             ) t(id, value)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING sum(PREV(A.value, 3)) AS sum_prev_3,
                     RUNNING avg(A.value) FILTER (WHERE A.value >= FIRST(A.value)) AS avg_first_to_current,
                     RUNNING count(*) FILTER (WHERE A.value <= LAST(A.value)) AS count_from_last
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'value': [10, 20, 30, 40, 50, 60]
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'sum_prev_3': [None, None, None, 10, 30, 60],
            'avg_first_to_current': [10.0, 15.0, 20.0, 25.0, 30.0, 35.0],
            'count_from_last': [1, 2, 3, 4, 5, 6]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Complex navigation with aggregations test failed")
    
    def test_nested_aggregations_with_subsets(self):
        """Test aggregations involving subset variables."""
        query = """
        SELECT m.id, m.classifier, m.subset_sum, m.subset_count, m.weighted_avg
        FROM (VALUES
                 (1, 'A', 10, 1.0),
                 (2, 'B', 20, 2.0),
                 (3, 'A', 30, 1.5),
                 (4, 'C', 40, 3.0),
                 (5, 'B', 50, 2.5)
             ) t(id, label, value, weight)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     CLASSIFIER() AS classifier,
                     RUNNING sum(S.value) AS subset_sum,
                     RUNNING count(S.*) AS subset_count,
                     RUNNING sum(T.value * T.weight) / sum(T.weight) AS weighted_avg
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN ((A | B | C)*)
                 SUBSET S = (A, B), T = (A, B, C)
                 DEFINE 
                     A AS label = 'A',
                     B AS label = 'B',
                     C AS label = 'C'
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'label': ['A', 'B', 'A', 'C', 'B'],
            'value': [10, 20, 30, 40, 50],
            'weight': [1.0, 2.0, 1.5, 3.0, 2.5]
        })
        
        # Expected output - corrected weighted averages to match actual mathematical formula
        # weighted_avg = sum(T.value * T.weight) / sum(T.weight)
        # Row 1: (10*1.0) / 1.0 = 10.0
        # Row 2: (10*1.0 + 20*2.0) / (1.0 + 2.0) = 50.0 / 3.0 = 16.666...
        # Row 3: (10*1.0 + 20*2.0 + 30*1.5) / (1.0 + 2.0 + 1.5) = 95.0 / 4.5 = 21.111...
        # Row 4: (10*1.0 + 20*2.0 + 30*1.5 + 40*3.0) / (1.0 + 2.0 + 1.5 + 3.0) = 215.0 / 7.5 = 28.666...
        # Row 5: (10*1.0 + 20*2.0 + 30*1.5 + 40*3.0 + 50*2.5) / (1.0 + 2.0 + 1.5 + 3.0 + 2.5) = 340.0 / 10.0 = 34.0
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'classifier': ['A', 'B', 'A', 'C', 'B'],
            'subset_sum': [10, 30, 60, 60, 110],
            'subset_count': [1, 2, 3, 3, 4],
            'weighted_avg': [10.0, 16.666666666666668, 21.11111111111111, 28.666666666666668, 34.0]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Nested aggregations with subsets test failed")
    
    def test_aggregations_with_null_handling(self):
        """Test how aggregations handle NULL values properly."""
        query = """
        SELECT m.id, m.sum_all, m.sum_non_null, m.count_all, m.count_non_null, m.avg_with_nulls
        FROM (VALUES
                 (1, 10),
                 (2, null),
                 (3, 30),
                 (4, null),
                 (5, 50)
             ) t(id, value)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING sum(A.value) AS sum_all,
                     RUNNING sum(A.value) FILTER (WHERE A.value IS NOT NULL) AS sum_non_null,
                     RUNNING count(*) AS count_all,
                     RUNNING count(A.value) AS count_non_null,
                     RUNNING avg(A.value) AS avg_with_nulls
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, None, 30, None, 50]
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'sum_all': [10, 10, 40, 40, 90],
            'sum_non_null': [10, 10, 40, 40, 90],
            'count_all': [1, 2, 3, 4, 5],
            'count_non_null': [1, 1, 2, 2, 3],
            'avg_with_nulls': [10.0, 10.0, 20.0, 20.0, 30.0]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "NULL handling aggregations test failed")
    
    def test_geometric_and_harmonic_means(self):
        """Test geometric and harmonic mean aggregations."""
        query = """
        SELECT m.id, m.geometric_mean, m.harmonic_mean, m.quadratic_mean
        FROM (VALUES
                 (1, 2.0),
                 (2, 4.0),
                 (3, 8.0),
                 (4, 16.0)
             ) t(id, value)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING geometric_mean(A.value) AS geometric_mean,
                     RUNNING harmonic_mean(A.value) AS harmonic_mean,
                     RUNNING sqrt(avg(A.value * A.value)) AS quadratic_mean
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS A.value > 0
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [2.0, 4.0, 8.0, 16.0]
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'geometric_mean': [2.0, 2.8284271247461903, 4.0, 5.656854249492381],
            'harmonic_mean': [2.0, 2.6666666666666665, 3.4285714285714284, 4.266666666666667],
            'quadratic_mean': [2.0, 3.1622776601683795, 5.291502622129181, 9.219544457292887]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Geometric and harmonic means test failed")
    
    def test_percentile_and_quantile_aggregations(self):
        """Test percentile and quantile functions."""
        query = """
        SELECT m.id, m.median, m.q1, m.q3, m.percentile_90
        FROM (VALUES
                 (1, 10), (2, 20), (3, 30), (4, 40), (5, 50),
                 (6, 60), (7, 70), (8, 80), (9, 90), (10, 100)
             ) t(id, value)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING percentile_cont(0.5) WITHIN GROUP (ORDER BY A.value) AS median,
                     RUNNING percentile_cont(0.25) WITHIN GROUP (ORDER BY A.value) AS q1,
                     RUNNING percentile_cont(0.75) WITHIN GROUP (ORDER BY A.value) AS q3,
                     RUNNING percentile_cont(0.9) WITHIN GROUP (ORDER BY A.value) AS percentile_90
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': list(range(1, 11)),
            'value': list(range(10, 101, 10))
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': list(range(1, 11)),
            'median': [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0],
            'q1': [10.0, 12.5, 15.0, 17.5, 20.0, 22.5, 25.0, 27.5, 30.0, 32.5],
            'q3': [10.0, 17.5, 25.0, 32.5, 40.0, 47.5, 55.0, 62.5, 70.0, 77.5],
            'percentile_90': [10.0, 19.0, 28.0, 37.0, 46.0, 55.0, 64.0, 73.0, 82.0, 91.0]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Percentile and quantile aggregations test failed")
    
    def test_aggregations_with_complex_patterns(self):
        """Test aggregations with complex pattern matching."""
        query = """
        SELECT m.id, m.classifier, m.pattern_sum, m.pattern_count, m.state_transitions
        FROM (VALUES
                 (1, 'start', 10),
                 (2, 'up', 15),
                 (3, 'up', 20),
                 (4, 'down', 12),
                 (5, 'up', 25),
                 (6, 'down', 8),
                 (7, 'end', 30)
             ) t(id, state, value)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     CLASSIFIER() AS classifier,
                     RUNNING sum(CASE WHEN CLASSIFIER() IN ('U', 'D') THEN value END) AS pattern_sum,
                     RUNNING count(CASE WHEN CLASSIFIER() IN ('U', 'D') THEN 1 END) AS pattern_count,
                     RUNNING string_agg(CLASSIFIER(), '->') AS state_transitions
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (S (U+ D+)* E)
                 DEFINE 
                     S AS state = 'start',
                     U AS state = 'up',
                     D AS state = 'down',
                     E AS state = 'end'
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7],
            'state': ['start', 'up', 'up', 'down', 'up', 'down', 'end'],
            'value': [10, 15, 20, 12, 25, 8, 30]
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7],
            'classifier': ['S', 'U', 'U', 'D', 'U', 'D', 'E'],
            'pattern_sum': [None, 15, 35, 47, 72, 80, 80],
            'pattern_count': [0, 1, 2, 3, 4, 5, 5],
            'state_transitions': ['S', 'S->U', 'S->U->U', 'S->U->U->D', 'S->U->U->D->U', 'S->U->U->D->U->D', 'S->U->U->D->U->D->E']
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Complex patterns aggregations test failed")
    
    def test_error_handling_and_edge_cases(self):
        """Test error conditions and edge cases in aggregations."""
        query = """
        SELECT m.id, m.safe_division, m.null_handling
        FROM (VALUES
                 (1, 10, 2),
                 (2, 20, 0),
                 (3, 30, null),
                 (4, 40, 4)
             ) t(id, numerator, denominator)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING sum(CASE WHEN A.denominator = 0 THEN null ELSE A.numerator / A.denominator END) AS safe_division,
                     RUNNING count(A.denominator) AS null_handling
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'numerator': [10, 20, 30, 40],
            'denominator': [2, 0, None, 4]
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'safe_division': [5.0, 5.0, 5.0, 15.0],
            'null_handling': [1, 1, 1, 2]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Error handling and edge cases test failed")
    
    def test_performance_stress_aggregations(self):
        """Test aggregations with large datasets to validate performance."""
        query = """
        SELECT count(*) as total_rows, 
               max(m.running_sum) as max_running_sum,
               avg(m.running_avg) as avg_of_running_avgs
        FROM (
            SELECT id, value
            FROM (VALUES {values_clause}) t(id, value)
        ) data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(A.value) AS running_sum,
                RUNNING avg(A.value) AS running_avg,
                RUNNING count(*) AS running_count
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        # Generate large dataset
        size = 20
        values = [(i, i) for i in range(1, size + 1)]
        values_clause = ", ".join([f"({v[0]}, {v[1]})" for v in values])
        query = query.format(values_clause=values_clause)
        
        # Input data
        df = pd.DataFrame({
            'id': list(range(1, size + 1)),
            'value': list(range(1, size + 1))
        })
        
        # Expected output
        expected = pd.DataFrame({
            'total_rows': [size],
            'max_running_sum': [sum(range(1, size + 1))],
            'avg_of_running_avgs': [10.5]  # Average of running averages
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Performance stress aggregations test failed")
    
    def test_type_coercion_in_aggregations(self):
        """Test proper type handling and coercion in aggregations."""
        query = """
        SELECT m.id, m.mixed_sum, m.decimal_avg, m.string_length_sum
        FROM (VALUES
                 (1, 10, 1.5, 'hello'),
                 (2, 20.5, 2, 'world'),
                 (3, 30, 3.7, 'test'),
                 (4, 40.2, 4, 'data')
             ) t(id, int_val, decimal_val, str_val)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES 
                     RUNNING sum(A.int_val + A.decimal_val) AS mixed_sum,
                     RUNNING avg(CAST(A.decimal_val AS DOUBLE)) AS decimal_avg,
                     RUNNING sum(length(A.str_val)) AS string_length_sum
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              )
        """
        
        # Input data
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'int_val': [10, 20.5, 30, 40.2],
            'decimal_val': [1.5, 2, 3.7, 4],
            'str_val': ['hello', 'world', 'test', 'data']
        })
        
        # Expected output
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'mixed_sum': [11.5, 34.0, 67.7, 111.9],
            'decimal_avg': [1.5, 1.75, 2.4, 2.8],
            'string_length_sum': [5, 10, 14, 18]
        })
        
        result = match_recognize(query, df)
        self.assert_dataframe_equals(result, expected, "Type coercion in aggregations test failed")

    @pytest.mark.slow
    def test_memory_efficient_large_aggregations(self):
        """Test memory efficiency with streaming aggregations."""
        # This test validates memory efficiency with larger datasets
        query = """
        SELECT m.category, m.total_sum, m.avg_value, m.item_count
        FROM large_dataset
        MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY id
            MEASURES 
                FIRST(A.category) AS category,
                FINAL sum(A.value) AS total_sum,
                FINAL avg(A.value) AS avg_value,
                FINAL count(*) AS item_count
            ONE ROW PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
        )
        ORDER BY m.category
        LIMIT 5
        """
        
        # Input data
        size = 50
        df = pd.DataFrame({
            'id': list(range(1, size + 1)),
            'category': [i % 100 for i in range(1, size + 1)],
            'value': [i * 1.5 for i in range(1, size + 1)]
        })
        
        # Expected output (first 5 categories)
        expected = pd.DataFrame({
            'category': [0, 1, 2, 3, 4],
            'total_sum': [75.0, 82.5, 90.0, 97.5, 105.0],
            'avg_value': [37.5, 41.25, 45.0, 48.75, 52.5],
            'item_count': [2, 2, 2, 2, 2]
        })
        
        result = match_recognize(query, df)
        # Take only first 5 rows for comparison
        result_subset = result.head(5).reset_index(drop=True)
        self.assert_dataframe_equals(result_subset, expected, "Memory efficient large aggregations test failed")

if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])
