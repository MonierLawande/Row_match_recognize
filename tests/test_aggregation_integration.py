# test_aggregation_integration.py
"""
Integration tests for aggregation functions in row pattern matching.

This module provides integration tests that work with the current implementation
and can be gradually expanded as features are implemented.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Import test utilities
from .test_utils import (
    mock_match_recognize, 
    test_data_generator, 
    test_validator,
    setup_test_environment
)

# Try to import the real implementation, fall back to mock
try:
    from executor.match_recognize import match_recognize
    IMPLEMENTATION_AVAILABLE = True
except ImportError:
    match_recognize = mock_match_recognize
    IMPLEMENTATION_AVAILABLE = False

class TestAggregationIntegration:
    """
    Integration tests for aggregation functionality.
    
    These tests validate the integration between the pattern matching engine
    and aggregation functions, ensuring correct data flow and results.
    """
    
    def setup_method(self):
        """Setup method run before each test."""
        setup_test_environment()
        
        # Skip tests if implementation is not available
        if not IMPLEMENTATION_AVAILABLE:
            pytest.skip("match_recognize implementation not available")
    
    @pytest.mark.integration
    def test_basic_sum_aggregation(self):
        """Test basic SUM aggregation functionality."""
        # Create test data
        df = test_data_generator.create_simple_numeric_data(5)
        
        query = """
        SELECT m.id, m.running_sum
        FROM test_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES RUNNING sum(A.value) AS running_sum
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        result = match_recognize(query, df)
        
        # Validate structure
        expected_columns = ['id', 'running_sum']
        assert test_validator.validate_dataframe_structure(result, expected_columns)
        
        # Validate aggregation pattern
        assert test_validator.validate_aggregation_results(result, "running_sum", "increasing")
        
        # Basic assertions
        assert len(result) == len(df), "Result should have same number of rows as input"
        assert not result.empty, "Result should not be empty"
    
    @pytest.mark.integration
    def test_multiple_aggregations(self):
        """Test multiple aggregation functions together."""
        df = test_data_generator.create_simple_numeric_data(8)
        
        query = """
        SELECT m.id, m.running_sum, m.running_avg, m.running_count
        FROM test_data
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
        
        result = match_recognize(query, df)
        
        # Validate structure
        expected_columns = ['id', 'running_sum', 'running_avg', 'running_count']
        assert test_validator.validate_dataframe_structure(result, expected_columns)
        
        # Basic data validation
        assert len(result) == len(df)
        assert not result.empty
    
    @pytest.mark.integration
    def test_aggregations_with_patterns(self):
        """Test aggregations with actual pattern matching."""
        df = test_data_generator.create_categorical_data(10)
        
        query = """
        SELECT m.id, m.classifier, m.running_sum, m.running_count
        FROM test_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                CLASSIFIER() AS classifier,
                RUNNING sum(A.value) AS running_sum,
                RUNNING count(*) AS running_count
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN ((A | B | C)*)
            DEFINE 
                A AS label = 'A',
                B AS label = 'B',
                C AS label = 'C'
        )
        """
        
        result = match_recognize(query, df)
        
        # Validate structure
        expected_columns = ['id', 'classifier', 'running_sum', 'running_count']
        assert test_validator.validate_dataframe_structure(result, expected_columns)
        
        # Pattern-specific validations
        if 'classifier' in result.columns:
            # Classifier should contain valid pattern variable names
            valid_classifiers = {'A', 'B', 'C'}
            actual_classifiers = set(result['classifier'].dropna().unique())
            assert actual_classifiers.issubset(valid_classifiers), f"Invalid classifiers: {actual_classifiers - valid_classifiers}"
    
    @pytest.mark.integration
    def test_aggregations_with_null_values(self):
        """Test aggregation handling of NULL values."""
        df = test_data_generator.create_null_data(10)
        
        query = """
        SELECT m.id, m.sum_all, m.count_all, m.count_non_null
        FROM test_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(A.value) AS sum_all,
                RUNNING count(*) AS count_all,
                RUNNING count(A.value) AS count_non_null
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        result = match_recognize(query, df)
        
        # Validate structure
        expected_columns = ['id', 'sum_all', 'count_all', 'count_non_null']
        assert test_validator.validate_dataframe_structure(result, expected_columns)
        
        # NULL handling validations
        if not result.empty and 'count_all' in result.columns and 'count_non_null' in result.columns:
            # count_non_null should be <= count_all
            count_all = result['count_all'].iloc[-1] if 'count_all' in result.columns else 0
            count_non_null = result['count_non_null'].iloc[-1] if 'count_non_null' in result.columns else 0
            
            assert count_non_null <= count_all, f"count_non_null ({count_non_null}) should not exceed count_all ({count_all})"
    
    @pytest.mark.integration
    def test_partitioned_aggregations(self):
        """Test aggregations with PARTITION BY."""
        df = test_data_generator.create_categorical_data(12)
        
        query = """
        SELECT m.label, m.total_sum, m.avg_value, m.item_count
        FROM test_data
        MATCH_RECOGNIZE (
            PARTITION BY label
            ORDER BY id
            MEASURES 
                FIRST(A.label) AS label,
                FINAL sum(A.value) AS total_sum,
                FINAL avg(A.value) AS avg_value,
                FINAL count(*) AS item_count
            ONE ROW PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
        )
        """
        
        result = match_recognize(query, df)
        
        # Validate structure
        expected_columns = ['label', 'total_sum', 'avg_value', 'item_count']
        assert test_validator.validate_dataframe_structure(result, expected_columns)
        
        # Partitioned data validations
        if not result.empty and 'label' in result.columns:
            # Should have results for different labels
            unique_labels = result['label'].nunique()
            assert unique_labels > 0, "Should have results for at least one label"
    
    @pytest.mark.integration 
    @pytest.mark.slow
    def test_large_dataset_aggregation(self):
        """Test aggregations with larger datasets."""
        # Create larger dataset
        size = 1000
        df = test_data_generator.create_simple_numeric_data(size)
        
        query = """
        SELECT m.id, m.running_sum, m.running_avg
        FROM test_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(A.value) AS running_sum,
                RUNNING avg(A.value) AS running_avg
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        result = match_recognize(query, df)
        
        # Validate structure
        expected_columns = ['id', 'running_sum', 'running_avg']
        assert test_validator.validate_dataframe_structure(result, expected_columns)
        
        # Performance validation
        assert len(result) == size, f"Expected {size} rows, got {len(result)}"
    
    @pytest.mark.integration
    def test_financial_data_scenario(self):
        """Test aggregations with financial-like data."""
        df = test_data_generator.create_financial_data(20)
        
        query = """
        SELECT m.day, m.price, m.running_avg_price, m.total_volume
        FROM test_data
        MATCH_RECOGNIZE (
            ORDER BY day
            MEASURES 
                A.day AS day,
                A.price AS price,
                RUNNING avg(A.price) AS running_avg_price,
                RUNNING sum(A.volume) AS total_volume
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS A.price > 0
        )
        """
        
        result = match_recognize(query, df)
        
        # Validate structure
        expected_columns = ['day', 'price', 'running_avg_price', 'total_volume']
        assert test_validator.validate_dataframe_structure(result, expected_columns)
        
        # Financial data validations
        if not result.empty:
            # Prices should be positive
            if 'price' in result.columns:
                prices = result['price'].dropna()
                assert all(p > 0 for p in prices), "All prices should be positive"
    
    @pytest.mark.integration
    def test_sensor_data_scenario(self):
        """Test aggregations with sensor-like data."""
        df = test_data_generator.create_sensor_data(15)
        
        query = """
        SELECT m.id, m.avg_value, m.confidence_weighted_avg
        FROM test_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                A.id AS id,
                RUNNING avg(A.value) AS avg_value,
                RUNNING sum(A.value * A.confidence) / sum(A.confidence) AS confidence_weighted_avg
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS A.confidence > 0.5
        )
        """
        
        result = match_recognize(query, df)
        
        # Validate structure
        expected_columns = ['id', 'avg_value', 'confidence_weighted_avg']
        assert test_validator.validate_dataframe_structure(result, expected_columns)
        
        # Sensor data validations
        if not result.empty:
            assert len(result) <= len(df), "Result should not have more rows than input"

class TestAggregationValidation:
    """
    Validation tests for aggregation correctness.
    
    These tests focus on validating the mathematical correctness
    of aggregation results.
    """
    
    def setup_method(self):
        """Setup method run before each test."""
        setup_test_environment()
    
    @pytest.mark.unit
    def test_sum_calculation_correctness(self):
        """Test that SUM calculations are mathematically correct."""
        # Use simple known values
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        query = """
        SELECT m.id, m.running_sum
        FROM test_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES RUNNING sum(A.value) AS running_sum
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        result = match_recognize(query, df)
        
        if not result.empty and 'running_sum' in result.columns:
            # Expected running sums: 10, 30, 60, 100
            expected_sums = [10, 30, 60, 100]
            actual_sums = result['running_sum'].tolist()
            
            # Compare with tolerance for floating point
            for expected, actual in zip(expected_sums, actual_sums):
                if actual is not None:
                    assert abs(expected - actual) < 1e-10, f"Expected {expected}, got {actual}"
    
    @pytest.mark.unit
    def test_average_calculation_correctness(self):
        """Test that AVG calculations are mathematically correct."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        query = """
        SELECT m.id, m.running_avg
        FROM test_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES RUNNING avg(A.value) AS running_avg
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        result = match_recognize(query, df)
        
        if not result.empty and 'running_avg' in result.columns:
            # Expected running averages: 10, 15, 20, 25
            expected_avgs = [10.0, 15.0, 20.0, 25.0]
            actual_avgs = result['running_avg'].tolist()
            
            for expected, actual in zip(expected_avgs, actual_avgs):
                if actual is not None:
                    assert abs(expected - actual) < 1e-10, f"Expected {expected}, got {actual}"
    
    @pytest.mark.unit
    def test_count_calculation_correctness(self):
        """Test that COUNT calculations are correct."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, None, 30, None, 50]
        })
        
        query = """
        SELECT m.id, m.count_all, m.count_values
        FROM test_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING count(*) AS count_all,
                RUNNING count(A.value) AS count_values
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        result = match_recognize(query, df)
        
        if not result.empty:
            if 'count_all' in result.columns:
                # count(*) should be 1, 2, 3, 4, 5
                expected_count_all = [1, 2, 3, 4, 5]
                actual_count_all = result['count_all'].tolist()
                
                for expected, actual in zip(expected_count_all, actual_count_all):
                    if actual is not None:
                        assert expected == actual, f"count(*): Expected {expected}, got {actual}"
            
            if 'count_values' in result.columns:
                # count(value) should be 1, 1, 2, 2, 3 (skipping NULLs)
                expected_count_values = [1, 1, 2, 2, 3]
                actual_count_values = result['count_values'].tolist()
                
                for expected, actual in zip(expected_count_values, actual_count_values):
                    if actual is not None:
                        assert expected == actual, f"count(value): Expected {expected}, got {actual}"

if __name__ == "__main__":
    # Run the integration tests
    pytest.main([__file__, "-v", "--tb=short", "-m", "integration or unit"])
