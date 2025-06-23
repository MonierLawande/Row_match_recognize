# test_java_aggregations_converted.py
"""
Direct conversion of Java test cases from TestAggregationsInRowPatternMatching.java
to Python, adapted for the current pandas-based MATCH_RECOGNIZE implementation.

This module focuses on converting the exact test cases from the Java implementation
to ensure compatibility and correctness validation against the reference implementation.

Test Categories:
1. Simple queries (basic aggregations)
2. Partitioning (multiple partition handling)
3. Tentative label matching
4. Aggregation arguments (complex expressions)
5. Selective aggregation (subset-based)
6. Count aggregations
7. Label and column names
8. One row per match
9. Seek operations
10. Exclusions
11. Balancing sums
12. Set partitioning
13. Multiple aggregations
14. Running vs final semantics

Author: Pattern Matching Engine Team (Converted from Java)
Version: 1.0.0
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import sys
import os

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
    # Return empty dataframe with expected structure
    return pd.DataFrame()

class TestJavaAggregationsConverted:
    """
    Direct conversion of Java aggregation test cases to Python.
    
    This class implements the exact same test scenarios as the Java version,
    ensuring compatibility and correctness validation.
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

    @pytest.mark.basic
    def test_simple_query_running_sum(self):
        """
        Test from testSimpleQuery() - basic running sum aggregation.
        Converted from Java test case with BIGINT coercion.
        """
        # Test data from Java VALUES clause
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7, 8]
        })
        
        query = """
        SELECT m.id, m.running_sum
        FROM (VALUES
                 (1),
                 (2),
                 (3),
                 (4),
                 (5),
                 (6),
                 (7),
                 (8)
             ) t(id)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES RUNNING sum(id) AS running_sum
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results from Java test (BIGINT values)
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7, 8],
            'running_sum': [1, 3, 6, 10, 15, 21, 28, 36]  # BIGINT values as int
        })
        
        self.assert_dataframe_equals(result, expected, "Simple running sum test failed")

    @pytest.mark.basic  
    def test_simple_query_running_array_agg(self):
        """
        Test from testSimpleQuery() - RUNNING array_agg(CLASSIFIER()) test.
        Converted from Java test case.
        """
        # Test data from Java VALUES clause
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7, 8]
        })
        
        query = """
        SELECT m.id, m.running_labels
        FROM (VALUES
                 (1),
                 (2),
                 (3),
                 (4),
                 (5),
                 (6),
                 (7),
                 (8)
             ) t(id)
               MATCH_RECOGNIZE (
                 ORDER BY id
                 MEASURES RUNNING array_agg(CLASSIFIER(A)) AS running_labels
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (A*)
                 DEFINE A AS true
              ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results from Java test - arrays of 'A' classifiers
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7, 8],
            'running_labels': [
                ['A'], 
                ['A', 'A'], 
                ['A', 'A', 'A'], 
                ['A', 'A', 'A', 'A'],
                ['A', 'A', 'A', 'A', 'A'], 
                ['A', 'A', 'A', 'A', 'A', 'A'],
                ['A', 'A', 'A', 'A', 'A', 'A', 'A'], 
                ['A', 'A', 'A', 'A', 'A', 'A', 'A', 'A']
            ]
        })
        
        self.assert_dataframe_equals(result, expected, "Simple running array_agg(CLASSIFIER) test failed")

    @pytest.mark.partitioning
    def test_partitioning_basic(self):
        """
        Test from testPartitioning() - multiple partitions with rolling sum.
        Converted from Java test case.
        """
        # Test data from Java VALUES clause (unordered input)
        df = pd.DataFrame({
            'id': [1, 2, 6, 2, 2, 1, 3, 4, 5, 1, 3, 3],
            'part': ['p1', 'p1', 'p1', 'p2', 'p3', 'p3', 'p1', 'p1', 'p1', 'p2', 'p3', 'p2'],
            'value': [1, 1, 1, 10, 100, 100, 1, 1, 1, 10, 100, 10]
        })
        
        query = """
        SELECT m.part as partition, m.id AS row_id, m.running_sum
        FROM (VALUES
                 (1, 'p1', 1),
                 (2, 'p1', 1),
                 (6, 'p1', 1),
                 (2, 'p2', 10),
                 (2, 'p3', 100),
                 (1, 'p3', 100),
                 (3, 'p1', 1),
                 (4, 'p1', 1),
                 (5, 'p1', 1),
                 (1, 'p2', 10),
                 (3, 'p3', 100),
                 (3, 'p2', 10)
             ) t(id, part, value)
               MATCH_RECOGNIZE (
                 PARTITION BY part
                 ORDER BY id
                 MEASURES RUNNING sum(value) AS running_sum
                 ALL ROWS PER MATCH
                 AFTER MATCH SKIP PAST LAST ROW
                 PATTERN (B+)
                 DEFINE B AS true
              ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results from Java test - ordered by partition and id
        expected = pd.DataFrame({
            'partition': ['p1', 'p1', 'p1', 'p1', 'p1', 'p1', 'p2', 'p2', 'p2', 'p3', 'p3', 'p3'],
            'row_id': [1, 2, 3, 4, 5, 6, 1, 2, 3, 1, 2, 3],
            'running_sum': [1, 2, 3, 4, 5, 6, 10, 20, 30, 100, 200, 300]
        })
        
        self.assert_dataframe_equals(result, expected, "Partitioning basic test failed")

    @pytest.mark.aggregation_args
    def test_aggregation_arguments_basic(self):
        """
        Test from testAggregationArguments() - combining source data and CLASSIFIER().
        Converted from Java test case.
        """
        # Test data from Java VALUES clause 
        df = pd.DataFrame({
            'part': ['p1', 'p1', 'p1', 'p1', 'p1', 'p1', 'p2', 'p2', 'p2', 'p3', 'p3', 'p3'],
            'id': [1, 2, 3, 4, 5, 6, 1, 2, 3, 1, 2, 3],
            'value': ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']
        })
        
        query = """
        SELECT m.part, m.id, m.measure
        FROM (VALUES
                 ('p1', 1, 'a'),
                 ('p1', 2, 'b'),
                 ('p1', 3, 'c'),
                 ('p1', 4, 'd'),
                 ('p1', 5, 'e'),
                 ('p1', 6, 'f'),
                 ('p2', 1, 'g'),
                 ('p2', 2, 'h'),
                 ('p2', 3, 'i'),
                 ('p3', 1, 'j'),
                 ('p3', 2, 'k'),
                 ('p3', 3, 'l')
        ) t(part, id, value)
          MATCH_RECOGNIZE (
            PARTITION BY part
            ORDER BY id
            MEASURES array_agg(concat(value, CLASSIFIER())) AS measure
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (X Y Z+)
            DEFINE X AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results from Java test - string concatenation with classifier
        expected = pd.DataFrame({
            'part': ['p1', 'p1', 'p1', 'p1', 'p1', 'p1', 'p2', 'p2', 'p2', 'p3', 'p3', 'p3'],
            'id': [1, 2, 3, 4, 5, 6, 1, 2, 3, 1, 2, 3],
            'measure': [
                ['aX'], 
                ['aX', 'bY'], 
                ['aX', 'bY', 'cZ'],
                ['aX', 'bY', 'cZ', 'dZ'], 
                ['aX', 'bY', 'cZ', 'dZ', 'eZ'],
                ['aX', 'bY', 'cZ', 'dZ', 'eZ', 'fZ'],
                ['gX'], 
                ['gX', 'hY'], 
                ['gX', 'hY', 'iZ'],
                ['jX'], 
                ['jX', 'kY'], 
                ['jX', 'kY', 'lZ']
            ]
        })
        
        self.assert_dataframe_equals(result, expected, "Aggregation arguments basic test failed")

    @pytest.mark.selective
    def test_selective_aggregation(self):
        """
        Test from testSelectiveAggregation() - aggregation applied only to subset rows.
        Converted from Java test case.
        """
        # Test data from Java VALUES clause
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': ['a', 'b', 'c', 'd']
        })
        
        query = """
        SELECT m.id, m.measure_1, m.measure_2, m.measure_3
        FROM (VALUES
                 (1, 'a'),
                 (2, 'b'),
                 (3, 'c'),
                 (4, 'd')
        ) t(id, value)
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                    array_agg(U.id) AS measure_1,
                    array_agg(CLASSIFIER(U)) AS measure_2,
                    array_agg(concat(U.value, CLASSIFIER(U))) AS measure_3
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (X Y Z Y)
            SUBSET U = (X, Z)
            DEFINE X AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results from Java test - only rows with labels X and Z
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'measure_1': [[1], [1], [1, 3], [1, 3]],
            'measure_2': [['X'], ['X'], ['X', 'Z'], ['X', 'Z']],
            'measure_3': [['aX'], ['aX'], ['aX', 'cZ'], ['aX', 'cZ']]
        })
        
        self.assert_dataframe_equals(result, expected, "Selective aggregation test failed")

    @pytest.mark.count
    def test_count_aggregation_basic(self):
        """
        Test from testCountAggregation() - various COUNT operations.
        Converted from Java test case.
        """
        # Test data from Java VALUES clause
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, None, 40, 50]
        })
        
        query = """
        SELECT m.id, m.count_all, m.count_value
        FROM (VALUES
                 (1, 10),
                 (2, 20),
                 (3, CAST(NULL AS INTEGER)),
                 (4, 40),
                 (5, 50)
        ) t(id, value)
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING count(*) AS count_all,
                RUNNING count(value) AS count_value
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results from Java test - COUNT(*) includes nulls, COUNT(value) excludes nulls
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'count_all': [1, 2, 3, 4, 5],
            'count_value': [1, 2, 2, 3, 4]  # NULL is excluded from count(value)
        })
        
        self.assert_dataframe_equals(result, expected, "Count aggregation basic test failed")

    @pytest.mark.window
    def test_one_row_per_match(self):
        """
        Test from testOneRowPerMatch() - final aggregation values.
        Converted from Java test case.
        """
        # Test data from Java VALUES clause
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [1, 2, 3, 4, 5]
        })
        
        query = """
        SELECT m.total_sum, m.total_count, m.final_array
        FROM (VALUES
                 (1, 1),
                 (2, 2),
                 (3, 3),
                 (4, 4),
                 (5, 5)
        ) t(id, value)
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                sum(value) AS total_sum,
                count(*) AS total_count,
                array_agg(value) AS final_array
            ONE ROW PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results from Java test - single row with final values
        expected = pd.DataFrame({
            'total_sum': [15],  # 1+2+3+4+5
            'total_count': [5],
            'final_array': [[1, 2, 3, 4, 5]]
        })
        
        self.assert_dataframe_equals(result, expected, "One row per match test failed")

    @pytest.mark.running_final
    def test_running_and_final_aggregations(self):
        """
        Test from testRunningAndFinalAggregations() - mix of RUNNING and FINAL.
        Converted from Java test case.
        """
        # Test data from Java VALUES clause
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        query = """
        SELECT m.id, m.running_sum, m.final_sum, m.running_count, m.final_count
        FROM (VALUES
                 (1, 10),
                 (2, 20),
                 (3, 30),
                 (4, 40)
        ) t(id, value)
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(value) AS running_sum,
                sum(value) AS final_sum,
                RUNNING count(*) AS running_count,
                count(*) AS final_count
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results from Java test - RUNNING vs FINAL semantics
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'running_sum': [10, 30, 60, 100],     # Running totals
            'final_sum': [100, 100, 100, 100],    # Final total in all rows
            'running_count': [1, 2, 3, 4],        # Running counts
            'final_count': [4, 4, 4, 4]           # Final count in all rows
        })
        
        self.assert_dataframe_equals(result, expected, "Running and final aggregations test failed")

    @pytest.mark.multiple
    def test_multiple_aggregation_arguments(self):
        """
        Test from testMultipleAggregationArguments() - complex aggregation expressions.
        Converted from Java test case.
        """
        # Test data from Java VALUES clause
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'x': [1, 2, 3],
            'y': [10, 20, 30]
        })
        
        query = """
        SELECT m.id, m.sum_product, m.avg_sum, m.array_concat
        FROM (VALUES
                 (1, 1, 10),
                 (2, 2, 20),
                 (3, 3, 30)
        ) t(id, x, y)
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(x * y) AS sum_product,
                RUNNING avg(x + y) AS avg_sum,
                RUNNING array_agg(concat(cast(x as varchar), ':', cast(y as varchar))) AS array_concat
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected results from Java test - complex expressions
        expected = pd.DataFrame({
            'id': [1, 2, 3],
            'sum_product': [10, 50, 140],        # 1*10, 1*10+2*20, 1*10+2*20+3*30
            'avg_sum': [11.0, 16.5, 22.0],       # avg(1+10), avg(1+10,2+20), avg(1+10,2+20,3+30)
            'array_concat': [['1:10'], ['1:10', '2:20'], ['1:10', '2:20', '3:30']]
        })
        
        self.assert_dataframe_equals(result, expected, "Multiple aggregation arguments test failed")

    @pytest.mark.edge_cases
    def test_empty_match_handling(self):
        """
        Test edge case - handling when no matches occur.
        Custom test to validate robustness.
        """
        # Test data that won't match the pattern
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'value': [1, 2, 3]
        })
        
        query = """
        SELECT m.id, m.sum_val
        FROM (VALUES
                 (1, 1),
                 (2, 2),
                 (3, 3)
        ) t(id, value)
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES RUNNING sum(value) AS sum_val
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS value > 10  -- This will never match
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: empty result set
        expected = pd.DataFrame(columns=['id', 'sum_val'])
        
        self.assert_dataframe_equals(result, expected, "Empty match handling test failed")

    @pytest.mark.nullable
    def test_null_handling_in_aggregations(self):
        """
        Test aggregation behavior with NULL values.
        Custom test based on SQL:2016 NULL handling rules.
        """
        # Test data with NULL values
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, None, 30, None, 50]
        })
        
        query = """
        SELECT m.id, m.sum_val, m.count_all, m.count_val, m.avg_val
        FROM (VALUES
                 (1, 10),
                 (2, CAST(NULL AS INTEGER)),
                 (3, 30),
                 (4, CAST(NULL AS INTEGER)),
                 (5, 50)
        ) t(id, value)
          MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(value) AS sum_val,
                RUNNING count(*) AS count_all,
                RUNNING count(value) AS count_val,
                RUNNING avg(value) AS avg_val
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        result = self.match_recognize(query, df)
        
        # Expected: NULL handling per SQL:2016 rules
        expected = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'sum_val': [10, 10, 40, 40, 90],       # SUM ignores NULLs
            'count_all': [1, 2, 3, 4, 5],          # COUNT(*) includes all rows
            'count_val': [1, 1, 2, 2, 3],          # COUNT(value) excludes NULLs
            'avg_val': [10.0, 10.0, 20.0, 20.0, 30.0]  # AVG ignores NULLs
        })
        
        self.assert_dataframe_equals(result, expected, "NULL handling in aggregations test failed")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_large_dataset_performance(self):
        """
        Test aggregation performance with larger dataset.
        Performance validation test.
        """
        # Create larger test dataset
        size = 1000
        df = pd.DataFrame({
            'id': range(1, size + 1),
            'value': range(1, size + 1),
            'category': [i % 10 for i in range(size)]
        })
        
        query = """
        SELECT m.id, m.running_sum, m.running_avg, m.running_count
        FROM test_data t
          MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY id
            MEASURES 
                RUNNING sum(value) AS running_sum,
                RUNNING avg(value) AS running_avg,
                RUNNING count(*) AS running_count
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
         ) AS m
        """
        
        import time
        start_time = time.time()
        result = self.match_recognize(query, df)
        end_time = time.time()
        
        # Verify we got results and performance is reasonable
        assert len(result) > 0, "Large dataset should produce results"
        execution_time = end_time - start_time
        assert execution_time < 10.0, f"Execution took too long: {execution_time:.2f}s"
        
        if logger:
            logger.info(f"Large dataset test completed in {execution_time:.2f}s with {len(result)} results")

if __name__ == "__main__":
    # Run specific test categories
    pytest.main([
        __file__,
        "-v",
        "-m", "basic or partitioning",  # Run basic tests
        "--tb=short"
    ])
