#!/usr/bin/env python3
"""
Comprehensive test suite for production-ready aggregate functions in SQL:2016 row pattern recognition.

This test suite covers all aggregate function scenarios including:
- Basic aggregates (SUM, COUNT, MIN, MAX, AVG)
- RUNNING vs FINAL semantics
- Variable-specific aggregation
- Special count syntax
- Array and string aggregation
- Multi-argument aggregates
- Conditional aggregates
- CLASSIFIER and MATCH_NUMBER in aggregate arguments
- Error handling and edge cases
"""

import pandas as pd
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.executor.match_recognize import match_recognize
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

def create_test_data():
    """Create comprehensive test data for aggregate function testing."""
    return pd.DataFrame([
        {'id': 1, 'value': 100, 'category': 'A', 'price': 10.5, 'quantity': 2},
        {'id': 2, 'value': 200, 'category': 'B', 'price': 20.0, 'quantity': 1},
        {'id': 3, 'value': 150, 'category': 'A', 'price': 15.5, 'quantity': 3},
        {'id': 4, 'value': 300, 'category': 'C', 'price': 30.0, 'quantity': 1},
        {'id': 5, 'value': 250, 'category': 'B', 'price': 25.0, 'quantity': 2},
        {'id': 6, 'value': 180, 'category': 'A', 'price': 18.0, 'quantity': 4},
        {'id': 7, 'value': 350, 'category': 'C', 'price': 35.0, 'quantity': 1},
        {'id': 8, 'value': 120, 'category': 'A', 'price': 12.0, 'quantity': 5}
    ])

class AggregateTestSuite:
    """Comprehensive test suite for aggregate functions."""
    
    def __init__(self):
        self.test_data = create_test_data()
        self.results = []
    
    def run_test(self, name: str, query: str, expected_description: str = None):
        """Run a single test case."""
        print(f"\n🔹 Running Test: {name}")
        print("=" * 60)
        
        try:
            result = match_recognize( query,self.test_data)

            print(f"✅ Success: {name}")
            print(f"Query: {query}")
            print(f"Result shape: {result.shape}")
            print("Result:")
            print(result.to_string(index=False))
            
            if expected_description:
                print(f"Expected behavior: {expected_description}")
            
            self.results.append({
                'test': name,
                'status': 'PASS',
                'result_count': len(result),
                'error': None
            })
            
        except Exception as e:
            print(f"❌ Failed: {name}")
            print(f"Error: {str(e)}")
            print(f"Query: {query}")
            
            self.results.append({
                'test': name,
                'status': 'FAIL',
                'result_count': 0,
                'error': str(e)
            })
    
    def test_basic_aggregates(self):
        """Test basic aggregate functions with pattern variables."""
        
        # Test SUM with pattern variable
        self.run_test(
            "SUM with Pattern Variable",
            """
            SELECT m.id, m.sum_a_value, m.sum_b_value
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    SUM(A.value) AS sum_a_value,
                    SUM(B.value) AS sum_b_value
                ALL ROWS PER MATCH
                PATTERN (A+ B+)
                DEFINE 
                    A AS category = 'A',
                    B AS category = 'B'
            ) AS m
            """,
            "Sum values for rows matching pattern variables A and B separately"
        )
        
        # Test COUNT with different variants
        self.run_test(
            "COUNT Variants",
            """
            SELECT m.id, m.count_all, m.count_a, m.count_a_star
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    COUNT(*) AS count_all,
                    COUNT(A.value) AS count_a,
                    COUNT(A.*) AS count_a_star
                ALL ROWS PER MATCH
                PATTERN (A+ B*)
                DEFINE 
                    A AS category = 'A',
                    B AS category = 'B'
            ) AS m
            """,
            "Count all rows, count A.value, and count A.* (variable wildcard)"
        )
        
        # Test MIN/MAX with type preservation
        self.run_test(
            "MIN/MAX with Type Preservation",
            """
            SELECT m.id, m.min_price, m.max_price, m.min_quantity, m.max_quantity
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    MIN(A.price) AS min_price,
                    MAX(A.price) AS max_price,
                    MIN(A.quantity) AS min_quantity,
                    MAX(A.quantity) AS max_quantity
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "MIN/MAX should preserve data types (float for price, int for quantity)"
        )
        
        # Test AVG
        self.run_test(
            "AVG Function",
            """
            SELECT m.id, m.avg_value, m.avg_price
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    AVG(A.value) AS avg_value,
                    AVG(A.price) AS avg_price
                ALL ROWS PER MATCH
                PATTERN (A{3,})
                DEFINE A AS value > 0
            ) AS m
            """,
            "Average values should be computed correctly with proper precision"
        )
    
    def test_running_vs_final_semantics(self):
        """Test RUNNING vs FINAL semantics."""
        
        # Test explicit RUNNING semantics
        self.run_test(
            "Explicit RUNNING Semantics",
            """
            SELECT m.id, m.running_sum, m.running_count
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    RUNNING SUM(value) AS running_sum,
                    RUNNING COUNT(*) AS running_count
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "RUNNING aggregates should show cumulative values up to current row"
        )
        
        # Test explicit FINAL semantics
        self.run_test(
            "Explicit FINAL Semantics",
            """
            SELECT m.id, m.final_sum, m.final_count
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    FINAL SUM(value) AS final_sum,
                    FINAL COUNT(*) AS final_count
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "FINAL aggregates should show final values for entire match"
        )
        
        # Test mixed RUNNING and FINAL
        self.run_test(
            "Mixed RUNNING and FINAL",
            """
            SELECT m.id, m.running_sum, m.final_sum, m.running_avg, m.final_avg
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    RUNNING SUM(value) AS running_sum,
                    FINAL SUM(value) AS final_sum,
                    RUNNING AVG(value) AS running_avg,
                    FINAL AVG(value) AS final_avg
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "Should correctly handle mixed RUNNING and FINAL semantics in same query"
        )
    
    def test_variable_specific_aggregation(self):
        """Test variable-specific vs universal aggregation."""
        
        # Test variable-specific aggregation
        self.run_test(
            "Variable-Specific Aggregation",
            """
            SELECT m.id, m.sum_a, m.sum_b, m.count_a, m.count_b
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    SUM(A.value) AS sum_a,
                    SUM(B.value) AS sum_b,
                    COUNT(A.*) AS count_a,
                    COUNT(B.*) AS count_b
                ALL ROWS PER MATCH
                PATTERN ((A|B)+)
                DEFINE 
                    A AS category IN ('A', 'C'),
                    B AS category = 'B'
            ) AS m
            """,
            "Aggregates should only include rows matching specific pattern variables"
        )
        
        # Test universal aggregation
        self.run_test(
            "Universal Aggregation",
            """
            SELECT m.id, m.total_value, m.total_count
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    SUM(value) AS total_value,
                    COUNT(*) AS total_count
                ALL ROWS PER MATCH
                PATTERN ((A|B)+)
                DEFINE 
                    A AS category IN ('A', 'C'),
                    B AS category = 'B'
            ) AS m
            """,
            "Universal aggregates should include all matched rows regardless of pattern variable"
        )
    
    def test_special_count_syntax(self):
        """Test special COUNT syntax variants."""
        
        # Test COUNT(*), COUNT(expr), COUNT(var.*)
        self.run_test(
            "Special COUNT Syntax",
            """
            SELECT m.id, m.count_star, m.count_value, m.count_a_star, m.count_u_star
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    COUNT(*) AS count_star,
                    COUNT(value) AS count_value,
                    COUNT(A.*) AS count_a_star,
                    COUNT(U.*) AS count_u_star
                ALL ROWS PER MATCH
                PATTERN (A+ B+)
                SUBSET U = (A, B)
                DEFINE 
                    A AS category IN ('A', 'C'),
                    B AS category = 'B'
            ) AS m
            """,
            "COUNT(*) counts all rows, COUNT(expr) counts non-null values, COUNT(var.*) counts variable rows"
        )
    
    def test_array_aggregation(self):
        """Test array aggregation functions."""
        
        # Test ARRAY_AGG
        self.run_test(
            "ARRAY_AGG Function",
            """
            SELECT m.match_id, m.values_array, m.categories_array
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    MATCH_NUMBER() AS match_id,
                    ARRAY_AGG(value) AS values_array,
                    ARRAY_AGG(category) AS categories_array
                ONE ROW PER MATCH
                PATTERN (A+ B+)
                DEFINE 
                    A AS category IN ('A', 'C'),
                    B AS category = 'B'
            ) AS m
            """,
            "ARRAY_AGG should collect values into arrays, excluding nulls"
        )
        
        # Test STRING_AGG
        self.run_test(
            "STRING_AGG Function",
            """
            SELECT m.match_id, m.category_string, m.id_string
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    MATCH_NUMBER() AS match_id,
                    STRING_AGG(category, ',') AS category_string,
                    STRING_AGG(CAST(id AS VARCHAR), '-') AS id_string
                ONE ROW PER MATCH
                PATTERN (A+ B+)
                DEFINE 
                    A AS category IN ('A', 'C'),
                    B AS category = 'B'
            ) AS m
            """,
            "STRING_AGG should concatenate values with specified separator"
        )
    
    def test_multi_argument_aggregates(self):
        """Test multi-argument aggregate functions."""
        
        # Test MAX_BY and MIN_BY
        self.run_test(
            "MAX_BY and MIN_BY Functions",
            """
            SELECT m.id, m.max_category, m.min_category, m.max_value_id, m.min_value_id
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    MAX_BY(category, value) AS max_category,
                    MIN_BY(category, value) AS min_category,
                    MAX_BY(id, price) AS max_value_id,
                    MIN_BY(id, price) AS min_value_id
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "MAX_BY/MIN_BY should return value corresponding to max/min of the key expression"
        )
    
    def test_conditional_aggregates(self):
        """Test conditional aggregate functions."""
        
        # Test COUNT_IF, SUM_IF, AVG_IF
        self.run_test(
            "Conditional Aggregates",
            """
            SELECT m.id, m.high_value_count, m.high_value_sum, m.high_value_avg
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    COUNT_IF(value, value > 200) AS high_value_count,
                    SUM_IF(value, value > 200) AS high_value_sum,
                    AVG_IF(value, value > 200) AS high_value_avg
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "Conditional aggregates should only include values meeting the condition"
        )
    
    def test_classifier_match_number_in_aggregates(self):
        """Test CLASSIFIER and MATCH_NUMBER in aggregate arguments."""
        
        # Test CLASSIFIER in aggregates
        self.run_test(
            "CLASSIFIER in Aggregates",
            """
            SELECT m.id, m.classifier_array, m.classifier_concat
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    ARRAY_AGG(CLASSIFIER()) AS classifier_array,
                    STRING_AGG(CLASSIFIER(), ',') AS classifier_concat
                ALL ROWS PER MATCH
                PATTERN ((A|B)+)
                DEFINE 
                    A AS category IN ('A', 'C'),
                    B AS category = 'B'
            ) AS m
            """,
            "CLASSIFIER() should be evaluable within aggregate function arguments"
        )
        
        # Test MATCH_NUMBER in aggregates
        self.run_test(
            "MATCH_NUMBER in Aggregates",
            """
            SELECT m.id, m.match_numbers, m.weighted_sum
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    ARRAY_AGG(MATCH_NUMBER()) AS match_numbers,
                    SUM(value * MATCH_NUMBER()) AS weighted_sum
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "MATCH_NUMBER() should be evaluable within aggregate function arguments"
        )
    
    def test_statistical_functions(self):
        """Test statistical aggregate functions."""
        
        # Test STDDEV and VARIANCE
        self.run_test(
            "Statistical Functions",
            """
            SELECT m.match_id, m.value_stddev, m.value_variance, m.price_stddev
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    MATCH_NUMBER() AS match_id,
                    STDDEV(value) AS value_stddev,
                    VARIANCE(value) AS value_variance,
                    STDDEV(price) AS price_stddev
                ONE ROW PER MATCH
                PATTERN (A{3,})
                DEFINE A AS value > 0
            ) AS m
            """,
            "Statistical functions should compute standard deviation and variance correctly"
        )
    
    def test_boolean_aggregates(self):
        """Test boolean aggregate functions."""
        
        # Test BOOL_AND and BOOL_OR
        self.run_test(
            "Boolean Aggregates",
            """
            SELECT m.id, m.all_high_value, m.any_high_value, m.all_category_a, m.any_category_a
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    BOOL_AND(value > 150) AS all_high_value,
                    BOOL_OR(value > 300) AS any_high_value,
                    BOOL_AND(category = 'A') AS all_category_a,
                    BOOL_OR(category = 'A') AS any_category_a
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "BOOL_AND/BOOL_OR should compute logical AND/OR over all values"
        )
    
    def test_edge_cases_and_errors(self):
        """Test edge cases and error handling."""
        
        # Test empty aggregates
        self.run_test(
            "Empty Aggregates",
            """
            SELECT m.id, m.sum_empty, m.count_empty, m.avg_empty
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    SUM(A.value) AS sum_empty,
                    COUNT(A.*) AS count_empty,
                    AVG(A.value) AS avg_empty
                ALL ROWS PER MATCH
                PATTERN (B+)
                DEFINE 
                    A AS category = 'NONEXISTENT',
                    B AS value > 0
            ) AS m
            """,
            "Aggregates with no matching data should return appropriate null/zero values"
        )
        
        # Test null handling
        self.run_test(
            "Null Handling",
            """
            SELECT m.id, m.sum_with_nulls, m.count_with_nulls, m.avg_with_nulls
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    SUM(CASE WHEN id % 2 = 0 THEN value ELSE NULL END) AS sum_with_nulls,
                    COUNT(CASE WHEN id % 2 = 0 THEN value ELSE NULL END) AS count_with_nulls,
                    AVG(CASE WHEN id % 2 = 0 THEN value ELSE NULL END) AS avg_with_nulls
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "Aggregates should properly handle null values (ignore in calculations)"
        )
    
    def test_complex_expressions_in_aggregates(self):
        """Test complex expressions within aggregate arguments."""
        
        # Test arithmetic expressions in aggregates
        self.run_test(
            "Complex Expressions in Aggregates",
            """
            SELECT m.id, m.total_amount, m.avg_unit_price, m.max_total_per_item
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    SUM(price * quantity) AS total_amount,
                    AVG(price / quantity) AS avg_unit_price,
                    MAX(price * quantity) AS max_total_per_item
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "Aggregates should handle complex arithmetic expressions in arguments"
        )
        
        # Test nested function calls in aggregates
        self.run_test(
            "Nested Functions in Aggregates",
            """
            SELECT m.id, m.rounded_avg, m.abs_sum
            FROM input_table t
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    AVG(ROUND(price, 0)) AS rounded_avg,
                    SUM(ABS(value - 200)) AS abs_sum
                ALL ROWS PER MATCH
                PATTERN (A+)
                DEFINE A AS value > 0
            ) AS m
            """,
            "Aggregates should handle nested function calls in arguments"
        )
    
    def run_all_tests(self):
        """Run all test categories."""
        print("🚀 Starting Comprehensive Aggregate Function Test Suite")
        print("=" * 80)
        
        # Run all test categories
        self.test_basic_aggregates()
        self.test_running_vs_final_semantics()
        self.test_variable_specific_aggregation()
        self.test_special_count_syntax()
        self.test_array_aggregation()
        self.test_multi_argument_aggregates()
        self.test_conditional_aggregates()
        self.test_classifier_match_number_in_aggregates()
        self.test_statistical_functions()
        self.test_boolean_aggregates()
        self.test_edge_cases_and_errors()
        self.test_complex_expressions_in_aggregates()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary."""
        print("\n" + "=" * 80)
        print("🏁 Test Suite Summary")
        print("=" * 80)
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r['status'] == 'PASS'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {passed_tests/total_tests*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ Failed Tests:")
            for result in self.results:
                if result['status'] == 'FAIL':
                    print(f"  - {result['test']}: {result['error']}")
        
        print("\n✅ Test suite completed!")


if __name__ == "__main__":
    test_suite = AggregateTestSuite()
    test_suite.run_all_tests()
