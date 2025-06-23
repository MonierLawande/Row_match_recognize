# test_utils.py
"""
Utility functions and base classes for aggregation testing.

This module provides common utilities, mock functions, and base classes
for testing the row pattern matching aggregation functionality.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockMatchRecognize:
    """
    Mock implementation of match_recognize for testing when the real implementation isn't available.
    
    This class provides basic functionality to validate test structure and data flow
    without requiring the full implementation.
    """
    
    def __init__(self):
        self.call_count = 0
        self.last_query = None
        self.last_dataframe = None
    
    def __call__(self, query: str, df: pd.DataFrame) -> pd.DataFrame:
        """Mock match_recognize function."""
        self.call_count += 1
        self.last_query = query
        self.last_dataframe = df.copy()
        
        logger.info(f"Mock match_recognize called (#{self.call_count})")
        logger.debug(f"Query: {query[:100]}...")
        logger.debug(f"DataFrame shape: {df.shape}")
        
        # Return a basic result structure for testing
        return self._generate_mock_result(df)
    
    def _generate_mock_result(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a mock result based on the input DataFrame."""
        # Create a simple result with running aggregations
        result_data = {}
        
        # Add basic columns
        if 'id' in df.columns:
            result_data['id'] = df['id'].tolist()
        
        # Add mock aggregation columns based on common patterns
        if 'value' in df.columns:
            values = df['value'].fillna(0)
            result_data['running_sum'] = values.cumsum().tolist()
            result_data['running_avg'] = values.expanding().mean().tolist()
            result_data['running_count'] = list(range(1, len(df) + 1))
        
        # Add classifier if pattern-like queries
        if 'CLASSIFIER()' in self.last_query.upper():
            result_data['classifier'] = ['A'] * len(df)
        
        return pd.DataFrame(result_data)

class TestDataGenerator:
    """Utility class for generating test data for aggregation testing."""
    
    @staticmethod
    def create_simple_numeric_data(size: int = 10) -> pd.DataFrame:
        """Create simple numeric data for basic aggregation testing."""
        return pd.DataFrame({
            'id': range(1, size + 1),
            'value': range(10, 10 + size * 10, 10)  # 10, 20, 30, ...
        })
    
    @staticmethod
    def create_financial_data(size: int = 20) -> pd.DataFrame:
        """Create financial-like data for testing."""
        np.random.seed(42)
        base_price = 100
        prices = [base_price]
        
        for _ in range(size - 1):
            change = np.random.normal(0, 2)
            new_price = max(prices[-1] + change, 10)  # Minimum price of 10
            prices.append(new_price)
        
        return pd.DataFrame({
            'day': pd.date_range('2024-01-01', periods=size),
            'price': prices,
            'volume': np.random.randint(100, 1000, size)
        })
    
    @staticmethod
    def create_sensor_data(size: int = 15) -> pd.DataFrame:
        """Create sensor-like data for testing."""
        np.random.seed(42)
        
        return pd.DataFrame({
            'id': range(1, size + 1),
            'sensor_id': [1] * size,
            'timestamp': pd.date_range('2024-01-01', periods=size, freq='H'),
            'value': np.random.uniform(10, 100, size),
            'confidence': np.random.uniform(0.7, 0.95, size)
        })
    
    @staticmethod
    def create_categorical_data(size: int = 10) -> pd.DataFrame:
        """Create data with categorical variables for testing."""
        np.random.seed(42)
        
        return pd.DataFrame({
            'id': range(1, size + 1),
            'label': np.random.choice(['A', 'B', 'C'], size),
            'value': np.random.randint(10, 100, size),
            'weight': np.random.uniform(1.0, 5.0, size)
        })
    
    @staticmethod
    def create_null_data(size: int = 10) -> pd.DataFrame:
        """Create data with NULL values for testing NULL handling."""
        np.random.seed(42)
        
        values = [10, None, 30, None, 50] * (size // 5 + 1)
        return pd.DataFrame({
            'id': range(1, size + 1),
            'value': values[:size]
        })

class TestValidator:
    """Utility class for validating test results."""
    
    @staticmethod
    def validate_dataframe_structure(df: pd.DataFrame, expected_columns: List[str]) -> bool:
        """Validate that DataFrame has expected structure."""
        if df.empty:
            logger.warning("DataFrame is empty")
            return False
        
        missing_columns = set(expected_columns) - set(df.columns)
        if missing_columns:
            logger.error(f"Missing columns: {missing_columns}")
            return False
        
        return True
    
    @staticmethod
    def validate_aggregation_results(df: pd.DataFrame, 
                                   aggregation_type: str,
                                   expected_pattern: str = "increasing") -> bool:
        """Validate that aggregation results follow expected patterns."""
        if df.empty:
            return False
        
        if aggregation_type == "running_sum" and expected_pattern == "increasing":
            # Running sums should generally be non-decreasing
            running_sum_col = None
            for col in df.columns:
                if 'sum' in col.lower():
                    running_sum_col = col
                    break
            
            if running_sum_col and not df[running_sum_col].isna().all():
                values = df[running_sum_col].dropna()
                is_increasing = all(values.iloc[i] <= values.iloc[i+1] 
                                  for i in range(len(values)-1))
                if not is_increasing:
                    logger.warning(f"Running sum is not increasing: {values.tolist()}")
                return is_increasing
        
        return True
    
    @staticmethod
    def compare_results_tolerance(actual: pd.DataFrame, 
                                expected: pd.DataFrame,
                                tolerance: float = 1e-6) -> bool:
        """Compare results with floating point tolerance."""
        try:
            pd.testing.assert_frame_equal(actual, expected, rtol=tolerance, atol=tolerance)
            return True
        except AssertionError as e:
            logger.error(f"DataFrames not equal within tolerance {tolerance}: {e}")
            return False

def setup_test_environment():
    """Setup the test environment with necessary configurations."""
    # Set pandas options for better test output
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 50)
    
    # Configure numpy for reproducible results
    np.random.seed(42)
    
    logger.info("Test environment configured")

def create_mock_aggregation_functions():
    """Create mock implementations of common aggregation functions."""
    
    def mock_stddev(values):
        """Mock standard deviation calculation."""
        clean_values = [v for v in values if v is not None and not pd.isna(v)]
        if len(clean_values) < 2:
            return None
        return np.std(clean_values, ddof=1)
    
    def mock_variance(values):
        """Mock variance calculation."""
        clean_values = [v for v in values if v is not None and not pd.isna(v)]
        if len(clean_values) < 2:
            return None
        return np.var(clean_values, ddof=1)
    
    def mock_geometric_mean(values):
        """Mock geometric mean calculation."""
        clean_values = [v for v in values if v is not None and not pd.isna(v) and v > 0]
        if not clean_values:
            return None
        return np.exp(np.mean(np.log(clean_values)))
    
    return {
        'stddev': mock_stddev,
        'variance': mock_variance,
        'geometric_mean': mock_geometric_mean
    }

# Create global instances
mock_match_recognize = MockMatchRecognize()
test_data_generator = TestDataGenerator()
test_validator = TestValidator()

# Export main functions
__all__ = [
    'MockMatchRecognize',
    'TestDataGenerator', 
    'TestValidator',
    'mock_match_recognize',
    'test_data_generator',
    'test_validator',
    'setup_test_environment',
    'create_mock_aggregation_functions'
]
