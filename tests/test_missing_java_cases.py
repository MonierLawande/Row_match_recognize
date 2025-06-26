# test_missing_java_cases.py
"""
Implementation of remaining Java test cases from TestAggregationsInRowPatternMatching.java
that are not yet covered in the Python test suite.

This module completes the conversion by implementing the more complex and advanced
test cases from the Java implementation, including:

1. Advanced statistical aggregations (testAdvancedStatisticalAggregations)
2. Conditional aggregations (testConditionalAggregations)  
3. Array and string aggregations (testArrayAndStringAggregations)
4. Specialized aggregations for production use
5. Complex pattern matching with aggregations
6. Performance and stress testing scenarios

These tests ensure complete feature parity with the Java implementation
and validate advanced SQL:2016 aggregation capabilities.

Author: Pattern Matching Engine Team (Converted from Java)
Version: 1.0.0
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union
import sys
import os
import math
import time
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
    """Enhanced mock implementation that simulates realistic aggregation results."""
    if not hasattr(df, 'columns') or len(df) == 0:
        return pd.DataFrame()
    
    # Extract basic info from query
    has_running = 'RUNNING' in query.upper()
    has_array_agg = 'ARRAY_AGG' in query.upper()
    has_string_agg = 'STRING_AGG' in query.upper()
    has_sum = 'SUM(' in query.upper()
    has_count = 'COUNT(' in query.upper()
    has_avg = 'AVG(' in query.upper()
    
    # Create basic result structure
    result_data = {}
    
    # Add ID column if present
    if 'id' in df.columns:
        result_data['id'] = df['id'].tolist()
    
    # Add mock aggregation results based on query patterns
    if has_running and has_sum:
        if 'value' in df.columns:
            result_data['running_sum'] = np.cumsum(df['value'].fillna(0)).tolist()
        else:
            result_data['running_sum'] = list(range(1, len(df) + 1))
    
    if has_running and has_count:
        result_data['running_count'] = list(range(1, len(df) + 1))
    
    if has_running and has_avg:
        if 'value' in df.columns:
            values = df['value'].fillna(0)
            result_data['running_avg'] = [values[:i+1].mean() for i in range(len(values))]
        else:
            result_data['running_avg'] = [1.0] * len(df)
    
    if has_array_agg:
        if 'name' in df.columns:
            result_data['array_names'] = [df['name'][:i+1].tolist() for i in range(len(df))]
        elif 'value' in df.columns:
            result_data['array_values'] = [df['value'][:i+1].tolist() for i in range(len(df))]
    
    if has_string_agg:
        if 'name' in df.columns:
            result_data['string_concat'] = [' '.join(df['name'][:i+1]) for i in range(len(df))]
    
    return pd.DataFrame(result_data)

class TestMissingJavaCases:
    """
    Implementation of missing Java test cases with comprehensive coverage.
    
    This class implements the remaining test cases from the Java test suite
    that require advanced aggregation functionality and complex pattern matching.
    """
    
    def setup_method(self):
        """Setup method called before each test."""
        self.match_recognize = match_recognize if MATCH_RECOGNIZE_AVAILABLE else mock_match_recognize
        
    def assert_dataframe_equals(self, actual: pd.DataFrame, expected: pd.DataFrame, msg: str = ""):
        """Helper method to compare DataFrames with enhanced error reporting."""
        try:
            pd.testing.assert_frame_equal(actual, expected, check_dtype=False, 
                                        check_exact=False, rtol=1e-5, atol=1e-8)
        except Exception as e:
            if logger:
                logger.error(f"{msg}\\nActual:\\n{actual}\\nExpected:\\n{expected}")
            raise AssertionError(f"{msg}\\n{str(e)}")

    @pytest.mark.advanced_stats
    def test_advanced_statistical_aggregations(self):
        """
        Test from testAdvancedStatisticalAggregations() - STDDEV, VARIANCE, etc.
        Java test case conversion with enhanced statistical functions.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        # Test advanced statistical functions
        query = """
        SELECT m.id, 
               m.running_stddev, 
               m.final_stddev,
               m.running_variance,
               m.population_stddev
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING stddev_samp(value) AS running_stddev,
                stddev_samp(value) AS final_stddev,
                RUNNING var_samp(value) AS running_variance,
                RUNNING stddev_pop(value) AS population_stddev
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results with proper statistical calculations
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'running_stddev': [np.nan, 7.071068, 10.0, 12.909944, 15.811388],
            'final_stddev': [15.811388] * 5,  # Final value in all rows
            'running_variance': [np.nan, 50.0, 100.0, 166.666667, 250.0],
            'population_stddev': [0.0, 5.0, 8.164966, 11.180340, 14.142136]
        })
        
        self.assert_dataframe_equals(result, expected, "Advanced statistical aggregations test failed")

    @pytest.mark.conditional_agg
    def test_conditional_aggregations_workaround(self):
        """
        Test conditional aggregations using CASE WHEN workarounds.
        Addresses parser issues with COUNT_IF, SUM_IF, AVG_IF.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'value': [1, -2, 3, 4, -5, 6]
        })
        
        # Use CASE WHEN as workaround for conditional aggregates
        query = """
        SELECT m.id, 
               m.count_positive, 
               m.sum_if_even, 
               m.avg_if_greater_than_2
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(CASE WHEN value > 0 THEN 1 ELSE 0 END) AS count_positive,
                RUNNING sum(CASE WHEN value % 2 = 0 THEN value ELSE 0 END) AS sum_if_even,
                RUNNING avg(CASE WHEN value > 2 THEN value ELSE NULL END) AS avg_if_greater_than_2
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results for conditional aggregations
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'count_positive': [1, 1, 2, 3, 3, 4],         # Count of positive values
            'sum_if_even': [0, -2, -2, 2, 2, 8],          # Sum of even values only
            'avg_if_greater_than_2': [np.nan, np.nan, 3.0, 3.5, 3.5, 4.333333]  # Avg of values > 2: (3+4+6)/3
        })
        
        self.assert_dataframe_equals(result, expected, "Conditional aggregations workaround test failed")

    @pytest.mark.array_string_agg
    def test_array_and_string_aggregations_enhanced(self):
        """
        Test enhanced array and string aggregation functions.
        Addresses type handling issues and delimiter support.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'fruit': ['apple', 'banana', 'cherry', 'date'],
            'price': [1.50, 2.00, 3.25, 1.75]
        })
        
        # Test array and string aggregation with proper type handling
        query = """
        SELECT m.id, 
               m.fruit_array, 
               m.fruit_string, 
               m.price_array,
               m.ordered_fruits
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING array_agg(fruit) AS fruit_array,
                RUNNING string_agg(fruit, ', ') AS fruit_string,
                RUNNING array_agg(price) AS price_array,
                RUNNING array_agg(fruit ORDER BY price DESC) AS ordered_fruits
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results with proper array/string handling
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'fruit_array': [
                ['apple'],
                ['apple', 'banana'],
                ['apple', 'banana', 'cherry'],
                ['apple', 'banana', 'cherry', 'date']
            ],
            'fruit_string': [
                'apple',
                'apple, banana',
                'apple, banana, cherry',
                'apple, banana, cherry, date'
            ],
            'price_array': [
                [1.50],
                [1.50, 2.00],
                [1.50, 2.00, 3.25],
                [1.50, 2.00, 3.25, 1.75]
            ],
            'ordered_fruits': [
                ['apple'],
                ['banana', 'apple'],
                ['cherry', 'banana', 'apple'],
                ['cherry', 'banana', 'date', 'apple']
            ]
        })
        
        self.assert_dataframe_equals(result, expected, "Array and string aggregations enhanced test failed")

    @pytest.mark.specialized_agg
    def test_specialized_aggregation_functions(self):
        """
        Test specialized aggregation functions (MIN_BY, MAX_BY, APPROX_DISTINCT).
        Implementation using available functions as workarounds.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7],
            'category': ['A', 'B', 'A', 'C', 'B', 'A', 'C'],
            'value': [10, 15, 12, 8, 20, 14, 11]
        })
        
        # Test specialized aggregation functions
        query = """
        SELECT m.id, 
               m.distinct_categories,
               m.min_value_category,
               m.max_value_category,
               m.category_with_min_value,
               m.category_with_max_value
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING count(DISTINCT category) AS distinct_categories,
                RUNNING min(value) AS min_value_category,
                RUNNING max(value) AS max_value_category,
                -- Use MIN_BY and MAX_BY instead of FIRST_VALUE with OVER
                RUNNING min_by(category, value) AS category_with_min_value,
                RUNNING max_by(category, value) AS category_with_max_value
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results for specialized aggregations
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7],
            'distinct_categories': [1, 2, 2, 3, 3, 3, 3],
            'min_value_category': [10, 10, 10, 8, 8, 8, 8],
            'max_value_category': [10, 15, 15, 15, 20, 20, 20],
            'category_with_min_value': ['A', 'A', 'A', 'C', 'C', 'C', 'C'],
            'category_with_max_value': ['A', 'B', 'B', 'B', 'B', 'B', 'B']
        })
        
        self.assert_dataframe_equals(result, expected, "Specialized aggregation functions test failed")

    @pytest.mark.complex_patterns
    def test_aggregations_with_complex_patterns(self):
        """
        Test aggregations with complex pattern matching scenarios.
        Based on Java test cases with multiple variables and conditions.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7],
            'price': [10, 15, 20, 12, 25, 8, 30],
            'volume': [100, 150, 80, 200, 60, 180, 40]
        })
        
        # Complex pattern: Start (S), Up (U+), Down (D+), End (E)
        query = """
        SELECT m.id, 
               m.pattern_state,
               m.total_volume,
               m.avg_price,
               m.state_transitions,
               m.up_count,
               m.down_count
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                CLASSIFIER() AS pattern_state,
                RUNNING sum(volume) AS total_volume,
                RUNNING avg(price) AS avg_price,
                RUNNING count(*) AS state_transitions,
                RUNNING sum(CASE WHEN CLASSIFIER() = 'U' THEN 1 ELSE 0 END) AS up_count,
                RUNNING sum(CASE WHEN CLASSIFIER() = 'D' THEN 1 ELSE 0 END) AS down_count
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (S U+ D+ E)
            DEFINE 
                S AS true,
                U AS price > PREV(price),
                D AS price < PREV(price),
                E AS price > PREV(price)
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results for complex pattern matching
        # CORRECTED: Pattern S U+ D+ E should be a strict sequence
        # Once we transition from U+ to D+, we cannot go back to U+
        # The correct match should be: S(1) U(2) U(3) D(4) E(5)
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'pattern_state': ['S', 'U', 'U', 'D', 'E'],
            'total_volume': [100, 250, 330, 530, 590],
            'avg_price': [10.0, 12.5, 15.0, 14.25, 16.4],
            'state_transitions': [1, 2, 3, 4, 5],
            'up_count': [0, 1, 2, 2, 2],
            'down_count': [0, 0, 0, 1, 1]
        })
        
        self.assert_dataframe_equals(result, expected, "Complex patterns aggregations test failed")

    @pytest.mark.navigation_agg
    def test_navigation_with_aggregations(self):
        """
        Test navigation functions combined with aggregations.
        Tests FIRST, LAST, PREV, NEXT with aggregation contexts.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'value': [10, 20, 30, 40, 50, 60],
            'timestamp': pd.date_range('2024-01-01', periods=6, freq='H')
        })
        
        # Test navigation combined with aggregations
        query = """
        SELECT m.id, 
               m.first_value_in_match,
               m.last_value_so_far,
               m.sum_from_first_to_current,
               m.avg_so_far,
               m.delta_from_previous
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                FIRST(value) AS first_value_in_match,
                LAST(value, 0) AS last_value_so_far,
                RUNNING sum(value) AS sum_from_first_to_current,
                RUNNING avg(value) AS avg_so_far,
                value - PREV(value, 1) AS delta_from_previous
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results for navigation with aggregations
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'first_value_in_match': [10, 10, 10, 10, 10, 10],
            'last_value_so_far': [10, 20, 30, 40, 50, 60],
            'sum_from_first_to_current': [10, 30, 60, 100, 150, 210],
            'avg_so_far': [10.0, 15.0, 20.0, 25.0, 30.0, 35.0],
            'delta_from_previous': [None, 10, 10, 10, 10, 10]
        })
        
        self.assert_dataframe_equals(result, expected, "Navigation with aggregations test failed")

    @pytest.mark.performance
    def test_performance_stress_aggregations(self):
        """
        Test performance and stress scenarios for aggregations.
        Validates scalability and memory efficiency.
        """
        # Create larger dataset for performance testing
        size = 500
        df = pd.DataFrame({
            'id': range(1, size + 1),
            'category': [f'cat_{i % 10}' for i in range(size)],
            'value': np.random.normal(100, 20, size),
            'flag': np.random.choice([True, False], size)
        })
        
        # Test multiple complex aggregations for performance
        query = """
        SELECT m.category,
               m.total_count,
               m.sum_value,
               m.avg_value,
               m.stddev_value,
               m.median_approx,
               m.distinct_values_approx
        FROM test_data t
          MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY id
            MEASURES 
                count(*) AS total_count,
                sum(value) AS sum_value,
                avg(value) AS avg_value,
                stddev_samp(value) AS stddev_value,
                percentile_approx(value, 0.5) AS median_approx,
                count(DISTINCT cast(value as integer)) AS distinct_values_approx
            ONE ROW PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        # Measure execution time
        start_time = time.time()
        result = self.match_recognize(query, df)
        execution_time = time.time() - start_time
        
        # Performance assertions
        assert len(result) == 10, f"Expected 10 categories, got {len(result)}"
        assert execution_time < 5.0, f"Execution took too long: {execution_time:.2f}s"
        assert all(result['total_count'] > 0), "All categories should have positive counts"
        assert all(result['avg_value'] > 0), "All averages should be reasonable"
        
        if logger:
            logger.info(f"Performance stress test completed in {execution_time:.2f}s")

    @pytest.mark.edge_cases
    def test_aggregation_boundary_conditions(self):
        """
        Test boundary conditions and edge cases for aggregations.
        Validates robustness with extreme inputs.
        """
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'tiny_val': [1e-10, 2e-10, 3e-10, 4e-10, 5e-10],
            'huge_val': [1e10, 2e10, 3e10, 4e10, 5e10],
            'zero_val': [0, 0, 0, 0, 0],
            'negative_val': [-1, -2, -3, -4, -5]
        })
        
        # Test boundary conditions
        query = """
        SELECT m.id,
               m.sum_tiny,
               m.sum_huge,
               m.avg_zero,
               m.sum_negative,
               m.product_approx,
               m.geometric_mean_approx
        FROM test_data t
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(tiny_val) AS sum_tiny,
                RUNNING sum(huge_val) AS sum_huge,
                RUNNING avg(zero_val) AS avg_zero,
                RUNNING sum(negative_val) AS sum_negative,
                RUNNING exp(sum(ln(abs(tiny_val)))) AS product_approx,
                RUNNING exp(avg(ln(abs(tiny_val)))) AS geometric_mean_approx
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Verify boundary conditions are handled properly
        assert len(result) == 5, "Should handle all boundary condition rows"
        assert all(result['sum_tiny'] > 0), "Tiny values should sum correctly"
        assert all(result['sum_huge'] > 0), "Huge values should sum correctly"
        assert all(result['avg_zero'] == 0), "Zero averages should be zero"
        assert all(result['sum_negative'] < 0), "Negative sums should be negative"
        
        if logger:
            logger.info("Boundary conditions test completed successfully")

if __name__ == "__main__":
    # Run the missing Java cases tests
    pytest.main([
        __file__,
        "-v",
        "-m", "not slow",  # Exclude slow tests by default
        "--tb=short"
    ])
