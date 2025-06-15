"""
Pytest fixtures for the match_recognize tests.
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, List, Any

@pytest.fixture
def simple_data():
    """Basic dataset with a single increasing and decreasing pattern."""
    return pd.DataFrame({
        'id': [1, 2, 3, 4, 5, 6, 7, 8],
        'value': [90, 80, 70, 80, 90, 50, 40, 60]
    })

@pytest.fixture
def basic_data():
    """Smaller dataset for simpler tests."""
    return pd.DataFrame({
        'id': [1, 2, 3, 4],
        'value': [90, 80, 70, 70]
    })

@pytest.fixture
def skip_data():
    """Dataset for testing AFTER MATCH SKIP modes."""
    return pd.DataFrame({
        'id': [1, 2, 3, 4, 5, 6],
        'value': [90, 80, 70, 80, 70, 80]
    })

@pytest.fixture
def multi_partition_data():
    """Dataset with multiple partitions for testing PARTITION BY."""
    return pd.DataFrame({
        'id': [1, 2, 3, 4, 5, 1, 2, 3, 2, 1, 3, 3],
        'part': ['p1', 'p1', 'p1', 'p1', 'p1', 'p2', 'p2', 'p2', 'p3', 'p3', 'p3', 'p3'],
        'value': [90, 80, 70, 80, 90, 20, 20, 10, 60, 50, 70, 70]
    })

@pytest.fixture
def stock_data():
    """Dataset resembling stock price data for realistic test cases."""
    return pd.DataFrame({
        'date': pd.date_range(start='2023-01-01', periods=20),
        'symbol': ['AAPL'] * 10 + ['MSFT'] * 10,
        'price': [150, 155, 153, 157, 160, 158, 162, 165, 160, 167, 
                 250, 255, 260, 258, 265, 260, 270, 275, 273, 280]
    })

@pytest.fixture
def empty_data():
    """Empty dataset for edge case testing."""
    return pd.DataFrame({
        'id': [],
        'value': []
    })

@pytest.fixture
def null_data():
    """Dataset with NULL values for NULL handling testing."""
    return pd.DataFrame({
        'id': [1, 2, 3, 4, 5],
        'value': [90, None, 70, None, 90]
    })

@pytest.fixture
def expected_results():
    """Common expected results for test validation."""
    return {
        'simple_query': [
            (1, 1, 90, 'A'),
            (2, 1, 80, 'B'),
            (3, 1, 70, 'B'),
            (4, 1, 80, 'C'),
            (5, 1, 90, 'C'),
            (6, 2, 50, 'A'),
            (7, 2, 40, 'B'),
            (8, 2, 60, 'C')
        ],
        'empty_pattern': [
            (1, 1, None, None),
            (2, 2, None, None),
            (3, 3, None, None),
            (4, 4, None, None)
        ],
        # Additional expected results can be added here
    }
