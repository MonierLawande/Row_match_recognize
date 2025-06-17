#!/usr/bin/env python3

"""
Test edge cases for SELECT * handling after the fix.
"""

import sys
import os
import pandas as pd

# Add the src directory to path
sys.path.append(os.path.abspath('.'))

from src.executor.match_recognize import match_recognize

def test_select_star_edge_cases():
    """Test various SELECT * edge cases to ensure robust handling."""
    
    print("=== Testing SELECT * Edge Cases ===")
    
    # Test data
    test_data = pd.DataFrame({
        'id': [1, 2, 3, 4],
        'value': [90, 80, 70, 80],
        'category': ['A', 'B', 'B', 'A']
    })
    
    print("Test Data:")
    print(test_data)
    
    # Test Case 1: Basic SELECT *
    print("\\n--- Test Case 1: Basic SELECT * ---")
    query1 = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES
            MATCH_NUMBER() AS match_num,
            CLASSIFIER() AS cls
        ONE ROW PER MATCH
        AFTER MATCH SKIP PAST LAST ROW
        PATTERN (A B+)
        DEFINE 
            A AS A.value > 85,
            B AS B.value < 85
    ) AS m
    """
    
    try:
        result1 = match_recognize(query1, test_data)
        print(f"Result shape: {result1.shape}")
        print(f"Columns: {list(result1.columns)}")
        print("Result:")
        print(result1)
        assert not result1.empty, "Result should not be empty"
        assert 'id' in result1.columns, "Should include original columns"
        assert 'match_num' in result1.columns, "Should include measures"
        print("✓ Test Case 1 PASSED")
    except Exception as e:
        print(f"✗ Test Case 1 FAILED: {e}")
    
    # Test Case 2: SELECT specific columns (should not be affected by our fix)
    print("\\n--- Test Case 2: SELECT specific columns ---")
    query2 = """
    SELECT id, match_num, cls
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES
            MATCH_NUMBER() AS match_num,
            CLASSIFIER() AS cls
        ONE ROW PER MATCH
        AFTER MATCH SKIP PAST LAST ROW
        PATTERN (A B+)
        DEFINE 
            A AS A.value > 85,
            B AS B.value < 85
    ) AS m
    """
    
    try:
        result2 = match_recognize(query2, test_data)
        print(f"Result shape: {result2.shape}")
        print(f"Columns: {list(result2.columns)}")
        print("Result:")
        print(result2)
        expected_cols = ['id', 'match_num', 'cls']
        assert set(result2.columns) == set(expected_cols), f"Should only have {expected_cols}"
        print("✓ Test Case 2 PASSED")
    except Exception as e:
        print(f"✗ Test Case 2 FAILED: {e}")
    
    # Test Case 3: ALL ROWS PER MATCH with SELECT *
    print("\\n--- Test Case 3: ALL ROWS PER MATCH with SELECT * ---")
    query3 = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES
            MATCH_NUMBER() AS match_num,
            CLASSIFIER() AS cls
        ALL ROWS PER MATCH
        AFTER MATCH SKIP PAST LAST ROW
        PATTERN (A B+)
        DEFINE 
            A AS A.value > 85,
            B AS B.value < 85
    ) AS m
    """
    
    try:
        result3 = match_recognize(query3, test_data)
        print(f"Result shape: {result3.shape}")
        print(f"Columns: {list(result3.columns)}")
        print("Result:")
        print(result3)
        assert not result3.empty, "Result should not be empty"
        assert 'id' in result3.columns, "Should include original columns"
        assert 'value' in result3.columns, "Should include original columns"
        assert 'category' in result3.columns, "Should include original columns"
        assert 'match_num' in result3.columns, "Should include measures"
        print("✓ Test Case 3 PASSED")
    except Exception as e:
        print(f"✗ Test Case 3 FAILED: {e}")

if __name__ == "__main__":
    test_select_star_edge_cases()
