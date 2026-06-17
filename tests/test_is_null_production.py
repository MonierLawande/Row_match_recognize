"""
Production-ready test suite for IS NULL and IS NOT NULL handling in MATCH_RECOGNIZE.

This test suite validates the fix for PREV(A.price) IS NULL and related cases,
ensuring production-level quality with edge cases, nested functions, and complex scenarios.

Test Categories:
1. Basic IS NULL handling
2. Navigation functions with IS NULL (PREV, NEXT, FIRST, LAST)
3. Nested function calls
4. Complex expressions
5. Edge cases and error conditions
6. Integration with full pattern matching
7. Performance and stress tests
"""

import pytest
import pandas as pd
from src.executor.match_recognize import match_recognize
from src.matcher.condition_evaluator import compile_condition, _sql_to_python_condition
from src.matcher.row_context import RowContext


class TestBasicIsNullHandling:
    """Test basic IS NULL and IS NOT NULL functionality."""
    
    def test_simple_column_is_null(self):
        """Test simple column IS NULL."""
        condition = "price IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(price)" in result
    
    def test_simple_column_is_not_null(self):
        """Test simple column IS NOT NULL."""
        condition = "price IS NOT NULL"
        result = _sql_to_python_condition(condition)
        assert "(not _is_null(price))" in result
    
    def test_dotted_column_is_null(self):
        """Test dotted notation IS NULL."""
        condition = "A.price IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(A.price)" in result
    
    def test_dotted_column_is_not_null(self):
        """Test dotted notation IS NOT NULL."""
        condition = "A.price IS NOT NULL"
        result = _sql_to_python_condition(condition)
        assert "(not _is_null(A.price))" in result


class TestNavigationFunctionIsNull:
    """Test IS NULL with navigation functions (PREV, NEXT, FIRST, LAST)."""
    
    def test_prev_is_null(self):
        """Test PREV(A.price) IS NULL - the main fix."""
        condition = "PREV(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result
        assert "PREV(A.price)" not in result.replace("_is_null(PREV(A.price))", "")
    
    def test_prev_is_not_null(self):
        """Test PREV(A.price) IS NOT NULL."""
        condition = "PREV(A.price) IS NOT NULL"
        result = _sql_to_python_condition(condition)
        assert "(not _is_null(PREV(A.price)))" in result
    
    def test_next_is_null(self):
        """Test NEXT(B.value) IS NULL."""
        condition = "NEXT(B.value) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(NEXT(B.value))" in result
    
    def test_first_is_null(self):
        """Test FIRST(A.price) IS NULL."""
        condition = "FIRST(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(FIRST(A.price))" in result
    
    def test_last_is_null(self):
        """Test LAST(C.value) IS NULL."""
        condition = "LAST(C.value) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(LAST(C.value))" in result
    
    def test_prev_with_steps_is_null(self):
        """Test PREV(A.price, 2) IS NULL."""
        condition = "PREV(A.price, 2) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price, 2))" in result


class TestNestedFunctionIsNull:
    """Test IS NULL with nested function calls."""
    
    def test_double_nested_is_null(self):
        """Test FUNC1(FUNC2(col)) IS NULL."""
        condition = "UPPER(LOWER(price)) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(UPPER(LOWER(price)))" in result
    
    def test_prev_of_classifier_is_null(self):
        """Test PREV(CLASSIFIER()) IS NULL."""
        condition = "PREV(CLASSIFIER()) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(CLASSIFIER()))" in result
    
    def test_deeply_nested_is_null(self):
        """Test deeply nested functions IS NULL."""
        condition = "FUNC1(FUNC2(FUNC3(FUNC4(col)))) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(FUNC1(FUNC2(FUNC3(FUNC4(col)))))" in result


class TestComplexExpressions:
    """Test IS NULL in complex expressions with AND/OR operators."""
    
    def test_or_with_is_null(self):
        """Test the original issue: A.price > PREV(A.price) OR PREV(A.price) IS NULL."""
        condition = "A.price > PREV(A.price) OR PREV(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result
        assert "or" in result.lower()
    
    def test_and_with_is_null(self):
        """Test AND with IS NULL."""
        condition = "A.price > 100 AND PREV(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result
        assert "and" in result.lower()
    
    def test_multiple_is_null_in_expression(self):
        """Test multiple IS NULL in one expression."""
        condition = "PREV(A.price) IS NULL OR NEXT(B.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result
        assert "_is_null(NEXT(B.price))" in result
    
    def test_mixed_is_null_and_is_not_null(self):
        """Test mixing IS NULL and IS NOT NULL."""
        condition = "PREV(A.price) IS NULL AND NEXT(B.price) IS NOT NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result
        assert "(not _is_null(NEXT(B.price)))" in result
    
    def test_parenthesized_is_null(self):
        """Test parenthesized expressions with IS NULL."""
        condition = "(PREV(A.price) IS NULL) OR (A.price > 100)"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result


class TestConditionCompilation:
    """Test that conditions compile and execute correctly."""
    
    def test_compile_prev_is_null_condition(self):
        """Test compiling PREV IS NULL condition."""
        condition = "A.price > PREV(A.price) OR PREV(A.price) IS NULL"
        
        # Should not raise an exception
        condition_func = compile_condition(condition, 'DEFINE')
        assert callable(condition_func)
    
    def test_execute_prev_is_null_first_row(self):
        """Test executing PREV IS NULL on first row (should return True)."""
        rows = [
            {'price': 100},
            {'price': 200},
        ]
        
        ctx = RowContext(rows)
        ctx.variables = {}
        ctx.current_idx = 0
        
        condition = "price > PREV(price) OR PREV(price) IS NULL"
        condition_func = compile_condition(condition, 'DEFINE')
        
        result = condition_func(rows[0], ctx)
        assert result is True, "First row should match when PREV IS NULL"
    
    def test_execute_prev_is_null_second_row_match(self):
        """Test executing PREV IS NULL on second row where condition matches."""
        rows = [
            {'price': 100},
            {'price': 200},
        ]
        
        ctx = RowContext(rows)
        ctx.variables = {}
        ctx.current_idx = 1
        
        condition = "price > PREV(price) OR PREV(price) IS NULL"
        condition_func = compile_condition(condition, 'DEFINE')
        
        result = condition_func(rows[1], ctx)
        assert result is True, "Second row should match: 200 > 100"
    
    def test_execute_prev_is_null_second_row_no_match(self):
        """Test executing PREV IS NULL on second row where condition doesn't match."""
        rows = [
            {'price': 200},
            {'price': 100},
        ]
        
        ctx = RowContext(rows)
        ctx.variables = {}
        ctx.current_idx = 1
        
        condition = "price > PREV(price) OR PREV(price) IS NULL"
        condition_func = compile_condition(condition, 'DEFINE')
        
        result = condition_func(rows[1], ctx)
        assert result is False, "Second row should not match: 100 is not > 200 and PREV is not NULL"


class TestFullPatternIntegration:
    """Test IS NULL handling in full MATCH_RECOGNIZE queries."""
    
    def test_simple_pattern_with_prev_is_null(self):
        """Test A+ pattern with PREV IS NULL condition."""
        data = [
            ('cust_1', '2020-05-11', 100),
            ('cust_1', '2020-05-12', 200),
            ('cust_1', '2020-05-13', 150),
        ]
        
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL
        );
        """
        
        result = match_recognize(query, df)
        
        # Should match first two rows: 100 (PREV IS NULL), 200 (200 > 100)
        assert len(result) == 2
        assert all(result['pattern_var'] == 'A')
    
    def test_abc_pattern_with_is_null(self):
        """Test A+ B+ C+ pattern - the original reported issue."""
        data = [
            ('cust_1', '2020-05-11', 100),
            ('cust_1', '2020-05-12', 200),
            ('cust_1', '2020-05-14', 100),
            ('cust_1', '2020-05-16', 50),
            ('cust_1', '2020-05-17', 100),
        ]
        
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var
            ALL ROWS PER MATCH
            PATTERN (A+ B+ C+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price),
                C AS C.price > PREV(C.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # Should match all 5 rows: A(100), A(200), B(100), B(50), C(100)
        assert len(result) == 5
        assert list(result['pattern_var']) == ['A', 'A', 'B', 'B', 'C']
    
    def test_multiple_partitions_with_is_null(self):
        """Test IS NULL handling across multiple partitions."""
        data = [
            ('cust_1', '2020-05-11', 100),
            ('cust_1', '2020-05-12', 200),
            ('cust_2', '2020-05-13', 8),
            ('cust_2', '2020-05-15', 4),
        ]
        
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL
        );
        """
        
        result = match_recognize(query, df)
        
        # Each partition should have at least the first row matched (PREV IS NULL)
        cust_1_matches = result[result['customer_id'] == 'cust_1']
        cust_2_matches = result[result['customer_id'] == 'cust_2']
        
        assert len(cust_1_matches) >= 1
        assert len(cust_2_matches) >= 1


class TestEdgeCases:
    """Test edge cases and potential failure scenarios."""
    
    def test_case_insensitivity(self):
        """Test that IS NULL is case-insensitive."""
        test_cases = [
            "PREV(A.price) IS NULL",
            "PREV(A.price) is null",
            "PREV(A.price) Is Null",
            "PREV(A.price) iS nULl",
        ]
        
        for condition in test_cases:
            result = _sql_to_python_condition(condition)
            assert "_is_null(PREV(A.price))" in result.lower() or "_is_null(PREV(A.price))" in result
    
    def test_whitespace_handling(self):
        """Test various whitespace patterns."""
        test_cases = [
            "PREV(A.price)IS NULL",
            "PREV(A.price)  IS  NULL",
            "PREV(A.price)\tIS\tNULL",
            "PREV(A.price)   IS   NULL",
        ]
        
        for condition in test_cases:
            result = _sql_to_python_condition(condition)
            assert "_is_null" in result
    
    def test_multiple_is_null_same_function(self):
        """Test multiple references to same function with IS NULL."""
        condition = "PREV(A.price) IS NULL OR PREV(A.price) == 0"
        result = _sql_to_python_condition(condition)
        # First PREV should be wrapped in _is_null, second should not
        assert result.count("_is_null") == 1
        assert result.count("PREV(A.price)") >= 1  # At least one unwrapped
    
    def test_no_false_positives(self):
        """Test that regular comparisons are not affected."""
        condition = "A.price > 100"
        result = _sql_to_python_condition(condition)
        assert "_is_null" not in result
        assert "IS NULL" not in result.upper()
    
    def test_function_with_multiple_args_is_null(self):
        """Test functions with multiple arguments."""
        condition = "SUBSTR(name, 1, 5) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(SUBSTR(name, 1, 5))" in result
    
    def test_empty_condition(self):
        """Test that empty conditions don't cause errors."""
        condition = ""
        result = _sql_to_python_condition(condition)
        assert result == ""
    
    def test_only_is_null(self):
        """Test condition that is only IS NULL."""
        condition = "price IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(price)" in result


class TestPerformanceAndStress:
    """Test performance with complex and large expressions."""
    
    def test_many_is_null_conditions(self):
        """Test performance with many IS NULL conditions."""
        # Build a condition with 20 IS NULL checks
        parts = [f"col{i} IS NULL" for i in range(20)]
        condition = " OR ".join(parts)
        
        result = _sql_to_python_condition(condition)
        
        # All should be converted
        assert result.count("_is_null") == 20
    
    def test_deeply_nested_functions(self):
        """Test deeply nested function calls."""
        condition = "F1(F2(F3(F4(F5(F6(col)))))) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(F1(F2(F3(F4(F5(F6(col)))))))" in result
    
    def test_mixed_complex_expression(self):
        """Test complex expression mixing many features."""
        condition = """
        (A.price > PREV(A.price) OR PREV(A.price) IS NULL) AND
        (B.value < NEXT(B.value) OR NEXT(B.value) IS NOT NULL) AND
        FIRST(C.amount) IS NULL AND
        LAST(D.total) > 100
        """
        
        result = _sql_to_python_condition(condition)
        
        # Should have multiple _is_null calls
        assert result.count("_is_null") >= 2
        assert "and" in result
        assert "or" in result


class TestRegressionPrevention:
    """Test that the fix doesn't break existing functionality."""
    
    def test_simple_prev_without_is_null(self):
        """Test that simple PREV still works."""
        condition = "A.price > PREV(A.price)"
        result = _sql_to_python_condition(condition)
        assert "PREV(A.price)" in result
        assert "_is_null" not in result
    
    def test_between_clause(self):
        """Test that BETWEEN clause still works."""
        condition = "price BETWEEN 10 AND 20"
        result = _sql_to_python_condition(condition)
        assert "10" in result and "20" in result
    
    def test_in_predicate(self):
        """Test that IN predicate still works."""
        condition = "status IN ('A', 'B', 'C')"
        result = _sql_to_python_condition(condition)
        assert "in" in result.lower()
    
    def test_regular_functions(self):
        """Test that regular functions are not affected."""
        condition = "UPPER(name) == 'JOHN'"
        result = _sql_to_python_condition(condition)
        assert "UPPER(name)" in result
        assert "_is_null" not in result


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
