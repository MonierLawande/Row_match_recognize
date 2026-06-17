"""
Test suite for IS NULL handling in MATCH_RECOGNIZE conditions.

This test file specifically validates the production-ready fix for handling
IS NULL and IS NOT NULL with complex expressions including function calls.

Focus areas:
1. Basic IS NULL/IS NOT NULL with simple identifiers
2. IS NULL with navigation functions (PREV, NEXT, FIRST, LAST)
3. IS NULL with nested function calls
4. IS NULL with complex expressions
5. Edge cases and error handling
"""

import pytest
import pandas as pd
from src.executor.match_recognize import match_recognize
from src.matcher.condition_evaluator import _sql_to_python_condition, compile_condition
from src.matcher.row_context import RowContext


class TestBasicIsNullHandling:
    """Test basic IS NULL and IS NOT NULL functionality."""
    
    def test_simple_column_is_null(self):
        """Test IS NULL with simple column reference."""
        condition = "price IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(price)" in result
    
    def test_simple_column_is_not_null(self):
        """Test IS NOT NULL with simple column reference."""
        condition = "price IS NOT NULL"
        result = _sql_to_python_condition(condition)
        assert "(not _is_null(price))" in result
    
    def test_dotted_column_is_null(self):
        """Test IS NULL with dotted notation (A.price)."""
        condition = "A.price IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(A.price)" in result
    
    def test_case_insensitive_is_null(self):
        """Test case insensitivity of IS NULL."""
        conditions = [
            "price is null",
            "price IS NULL",
            "price Is Null",
            "price iS nUlL"
        ]
        for condition in conditions:
            result = _sql_to_python_condition(condition)
            assert "_is_null(price)" in result.lower()


class TestNavigationFunctionIsNull:
    """Test IS NULL with navigation functions."""
    
    def test_prev_function_is_null(self):
        """Test PREV(column) IS NULL."""
        condition = "PREV(price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(price))" in result
    
    def test_prev_with_variable_is_null(self):
        """Test PREV(A.price) IS NULL."""
        condition = "PREV(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result
    
    def test_prev_with_offset_is_null(self):
        """Test PREV(A.price, 2) IS NULL."""
        condition = "PREV(A.price, 2) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price, 2))" in result
    
    def test_next_function_is_null(self):
        """Test NEXT(A.price) IS NULL."""
        condition = "NEXT(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(NEXT(A.price))" in result
    
    def test_first_function_is_null(self):
        """Test FIRST(A.price) IS NULL."""
        condition = "FIRST(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(FIRST(A.price))" in result
    
    def test_last_function_is_null(self):
        """Test LAST(A.price) IS NULL."""
        condition = "LAST(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(LAST(A.price))" in result


class TestNestedFunctionIsNull:
    """Test IS NULL with nested function calls."""
    
    def test_nested_prev_is_null(self):
        """Test nested navigation functions IS NULL."""
        condition = "PREV(FIRST(A.price)) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(FIRST(A.price)))" in result
    
    def test_deeply_nested_is_null(self):
        """Test deeply nested functions IS NULL."""
        condition = "PREV(NEXT(FIRST(A.price))) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(NEXT(FIRST(A.price))))" in result
    
    def test_nested_with_multiple_args_is_null(self):
        """Test nested functions with multiple arguments IS NULL."""
        condition = "PREV(A.price, 2) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price, 2))" in result


class TestComplexExpressionIsNull:
    """Test IS NULL in complex expressions."""
    
    def test_or_with_is_null(self):
        """Test OR condition with IS NULL."""
        condition = "A.price > PREV(A.price) OR PREV(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "or" in result
        assert "_is_null(PREV(A.price))" in result
    
    def test_and_with_is_null(self):
        """Test AND condition with IS NULL."""
        condition = "A.price > 100 AND PREV(A.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert "and" in result
        assert "_is_null(PREV(A.price))" in result
    
    def test_multiple_is_null_in_condition(self):
        """Test multiple IS NULL in same condition."""
        condition = "PREV(A.price) IS NULL OR NEXT(B.price) IS NULL"
        result = _sql_to_python_condition(condition)
        assert result.count("_is_null") == 2
        assert "_is_null(PREV(A.price))" in result
        assert "_is_null(NEXT(B.price))" in result
    
    def test_is_null_with_parentheses(self):
        """Test IS NULL with parenthesized expressions."""
        condition = "(PREV(A.price) IS NULL) OR (A.price > 100)"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result


class TestEdgeCases:
    """Test edge cases and special scenarios."""
    
    def test_no_space_before_is_null(self):
        """Test IS NULL without space before IS."""
        condition = "PREV(A.price)IS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result
    
    def test_multiple_spaces_is_null(self):
        """Test IS NULL with multiple spaces."""
        condition = "PREV(A.price)    IS    NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result
    
    def test_is_null_with_newlines(self):
        """Test IS NULL with newlines."""
        condition = "PREV(A.price)\nIS NULL"
        result = _sql_to_python_condition(condition)
        assert "_is_null(PREV(A.price))" in result
    
    def test_is_not_null_with_or(self):
        """Test IS NOT NULL in OR condition."""
        condition = "A.price > 100 OR PREV(A.price) IS NOT NULL"
        result = _sql_to_python_condition(condition)
        assert "(not _is_null(PREV(A.price)))" in result


class TestIntegrationWithMatchRecognize:
    """Integration tests with full MATCH_RECOGNIZE queries."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing."""
        data = [
            ('cust_1', '2020-05-11', 100),
            ('cust_1', '2020-05-12', 200),
            ('cust_1', '2020-05-14', 100),
            ('cust_2', '2020-05-13', 8),
            ('cust_2', '2020-05-15', 4),
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        return df
    
    def test_prev_is_null_allows_first_row_match(self, sample_data):
        """Test that PREV IS NULL allows first row to match."""
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
        result = match_recognize(query, sample_data)
        
        # Should get matches starting from first row in each partition
        assert not result.empty
        assert len(result) > 0
        
        # Check that first rows of each partition are included
        cust_1_first = result[result['customer_id'] == 'cust_1'].iloc[0]
        assert cust_1_first['order_date'] == pd.Timestamp('2020-05-11')
    
    def test_complex_pattern_with_is_null(self, sample_data):
        """Test complex pattern (A+ B+) with IS NULL conditions."""
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        result = match_recognize(query, sample_data)
        
        # Should get matches with both A and B
        assert not result.empty
        assert 'A' in result['pattern_var'].values
        assert 'B' in result['pattern_var'].values
    
    def test_is_not_null_in_condition(self, sample_data):
        """Test IS NOT NULL in DEFINE condition."""
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
                A AS PREV(A.price) IS NOT NULL
        );
        """
        result = match_recognize(query, sample_data)
        
        # Should NOT match first rows (where PREV is NULL)
        # Should only match rows that have a previous row
        if not result.empty:
            for _, row in result.iterrows():
                # None of the matches should be the first row in a partition
                partition_data = sample_data[sample_data['customer_id'] == row['customer_id']]
                first_date = partition_data['order_date'].min()
                assert row['order_date'] != first_date


class TestConditionCompilation:
    """Test condition compilation with IS NULL."""
    
    def test_compile_condition_with_prev_is_null(self):
        """Test compiling condition with PREV IS NULL."""
        rows = [
            {'customer_id': 'cust_1', 'price': 100},
            {'customer_id': 'cust_1', 'price': 200},
        ]
        ctx = RowContext(rows)
        ctx.variables = {}
        ctx.current_idx = 0
        
        condition = "A.price > PREV(A.price) OR PREV(A.price) IS NULL"
        condition_func = compile_condition(condition, 'DEFINE')
        
        # Should return True for first row (PREV is NULL)
        result = condition_func(rows[0], ctx)
        assert result is True
    
    def test_compile_condition_with_is_not_null(self):
        """Test compiling condition with IS NOT NULL."""
        rows = [
            {'customer_id': 'cust_1', 'price': 100},
        ]
        ctx = RowContext(rows)
        ctx.variables = {}
        ctx.current_idx = 0
        
        condition = "PREV(A.price) IS NOT NULL"
        condition_func = compile_condition(condition, 'DEFINE')
        
        # Should return False for first row (PREV is NULL)
        result = condition_func(rows[0], ctx)
        assert result is False


class TestRegressionPrevention:
    """Tests to prevent regression of the IS NULL fix."""
    
    def test_original_bug_scenario(self):
        """Test the exact scenario from the original bug report."""
        data = [
            ('cust_1', '2020-05-11', 100),
            ('cust_1', '2020-05-12', 200),
            ('cust_2', '2020-05-13', 8),
            ('cust_1', '2020-05-14', 100),
            ('cust_2', '2020-05-15', 4),
            ('cust_1', '2020-05-16', 50),
            ('cust_1', '2020-05-17', 100),
            ('cust_2', '2020-05-18', 6),
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
                CLASSIFIER() AS pattern_var,
                MATCH_NUMBER() AS match_num,
                A.price AS a_price,
                A.order_date AS a_date
            ALL ROWS PER MATCH
            PATTERN (A+ B+ C+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price),
                C AS C.price > PREV(C.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # Before fix: returned 0 rows
        # After fix: should return 8 rows (matching Trino)
        assert len(result) == 8
        
        # Verify pattern classifications
        assert set(result['pattern_var'].unique()) == {'A', 'B', 'C'}
        
        # Verify both customers have matches
        assert 'cust_1' in result['customer_id'].values
        assert 'cust_2' in result['customer_id'].values


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
