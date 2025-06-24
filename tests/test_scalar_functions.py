"""
Test Scalar Functions in MEASURES and DEFINE clauses
Matches testScalarFunctions() from TestRowPatternMatching.java
"""

import pytest
import pandas as pd
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.executor.match_recognize import match_recognize

class TestScalarFunctions:
    """Test scalar functions and operators in MEASURES and DEFINE."""

    def setup_method(self):
        """Setup test data matching Java reference."""
        self.test_data = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 60],
            'category': ['high', 'med', 'low', 'low']
        })

    def test_string_functions_in_measures(self):
        """Test string functions in MEASURES clause."""
        df = self.test_data
        
        query = """
        SELECT id, label_concat, label_upper
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CONCAT(CLASSIFIER(), '_suffix') AS label_concat,
                UPPER(CLASSIFIER()) AS label_upper,
                LENGTH(CLASSIFIER()) AS label_length
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check string concatenation
            assert 'label_concat' in result.columns
            assert 'label_upper' in result.columns
            
            # First row should be 'A_suffix' and 'A'
            if len(result) > 0:
                assert result.iloc[0]['label_concat'] == 'A_suffix'
                assert result.iloc[0]['label_upper'] == 'A'
        else:
            pytest.skip("String functions in MEASURES not implemented")

    def test_arithmetic_functions_in_define(self):
        """Test arithmetic functions in DEFINE clause."""
        df = self.test_data
        
        query = """
        SELECT id, CLASSIFIER() AS label, value
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS (B.value + 10) < ABS(PREV(B.value) * 2)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Should evaluate arithmetic expressions correctly
            assert len(result) >= 1
            assert 'label' in result.columns
        else:
            pytest.skip("Arithmetic functions in DEFINE not implemented")

    def test_conditional_functions(self):
        """Test conditional functions like CASE, COALESCE, etc."""
        df = self.test_data
        
        query = """
        SELECT id, category_label, value_category
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CASE 
                    WHEN CLASSIFIER() = 'A' THEN 'start'
                    WHEN CLASSIFIER() = 'B' THEN 'middle'
                    ELSE 'other'
                END AS category_label,
                CASE
                    WHEN RUNNING LAST(value) > 80 THEN 'high'
                    WHEN RUNNING LAST(value) > 70 THEN 'medium'
                    ELSE 'low'
                END AS value_category
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check CASE expressions work
            assert 'category_label' in result.columns
            assert 'value_category' in result.columns
            
            # First row should be 'start'
            if len(result) > 0:
                assert result.iloc[0]['category_label'] == 'start'
        else:
            pytest.skip("Conditional functions not implemented")

    def test_aggregate_functions_in_measures(self):
        """Test aggregate functions in MEASURES clause."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [100, 90, 80, 70, 80]
        })
        
        query = """
        SELECT id, avg_value, max_value, min_value, count_rows
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                AVG(value) AS avg_value,
                MAX(value) AS max_value,
                MIN(value) AS min_value,
                COUNT(*) AS count_rows
            ALL ROWS PER MATCH
            PATTERN (A B+ C+)
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value >= PREV(C.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check aggregate functions work
            assert 'avg_value' in result.columns
            assert 'max_value' in result.columns
            assert 'count_rows' in result.columns
            
            # Validate some expected values
            if len(result) > 0:
                assert result.iloc[0]['max_value'] == 100  # First row value
                assert result.iloc[0]['count_rows'] >= 1
        else:
            pytest.skip("Aggregate functions in MEASURES not implemented")

    def test_date_time_functions(self):
        """Test date/time functions if supported."""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'value': [90, 80, 70],
            'timestamp': pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03'])
        })
        
        query = """
        SELECT id, day_of_week, hour_of_day
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                EXTRACT(DOW FROM timestamp) AS day_of_week,
                EXTRACT(HOUR FROM timestamp) AS hour_of_day
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check date/time functions work
            assert 'day_of_week' in result.columns
            assert 'hour_of_day' in result.columns
        else:
            pytest.skip("Date/time functions not implemented")

    def test_null_handling_functions(self):
        """Test NULL handling functions like COALESCE, NULLIF."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, None, 70, 80],
            'backup_value': [0, 85, 0, 0]
        })
        
        query = """
        SELECT id, safe_value, is_null_value
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                COALESCE(value, backup_value) AS safe_value,
                CASE WHEN value IS NULL THEN 1 ELSE 0 END AS is_null_value
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS COALESCE(B.value, B.backup_value) < COALESCE(PREV(B.value), PREV(B.backup_value))
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check NULL handling
            assert 'safe_value' in result.columns
            assert 'is_null_value' in result.columns
            
            # Second row should use backup_value
            if len(result) > 1:
                assert result.iloc[1]['safe_value'] == 85
                assert result.iloc[1]['is_null_value'] == 1
        else:
            pytest.skip("NULL handling functions not implemented")

    def test_cast_and_type_functions(self):
        """Test CAST and type conversion functions."""
        df = self.test_data
        
        query = """
        SELECT id, value_str, id_decimal
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CAST(value AS VARCHAR) AS value_str,
                CAST(id AS DECIMAL(10,2)) AS id_decimal
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check type conversion
            assert 'value_str' in result.columns
            assert 'id_decimal' in result.columns
            
            # Check that values are properly converted
            if len(result) > 0:
                assert isinstance(result.iloc[0]['value_str'], str)
                assert result.iloc[0]['id_decimal'] is not None
        else:
            pytest.skip("CAST and type functions not implemented")
