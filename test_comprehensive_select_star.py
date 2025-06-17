#!/usr/bin/env python3

"""
Comprehensive test for SELECT * column ordering fixes.
Tests both ONE ROW PER MATCH and ALL ROWS PER MATCH column ordering.
"""

import sys
import os
import pandas as pd

# Add the src directory to path
sys.path.append(os.path.abspath('.'))

from src.executor.match_recognize import match_recognize

def test_comprehensive_select_star():
    """Test comprehensive SELECT * behavior for both output modes."""
    
    print("=== Comprehensive SELECT * Column Ordering Test ===")
    
    # Test data with multiple columns
    test_data = pd.DataFrame({
        'id': [1, 2, 3],
        'part': ['A', 'A', 'B'], 
        'value': [90, 80, 70],
        'extra': ['x', 'y', 'z']
    })
    
    print("Input Data:")
    print(test_data)
    
    # Test 1: ONE ROW PER MATCH with SELECT *
    print("\\n=== Test 1: ONE ROW PER MATCH ===")
    query1 = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        PARTITION BY part
        ORDER BY id
        MEASURES 
            MATCH_NUMBER() AS match_num,
            CLASSIFIER() AS cls
        ONE ROW PER MATCH
        AFTER MATCH SKIP PAST LAST ROW
        PATTERN (A)
        DEFINE A AS A.value > 70
    ) AS m
    """
    
    result1 = match_recognize(query1, test_data)
    print(f"Result columns: {list(result1.columns)}")
    print("Result:")
    print(result1)
    
    # Verify ONE ROW PER MATCH column ordering: PARTITION BY + MEASURES only
    expected_one_row = ['part', 'match_num', 'cls']  # Should only have partition + measures
    actual_one_row = list(result1.columns)
    
    # Check that we have partition and measures
    assert 'part' in actual_one_row, "Should include partition column"
    assert 'match_num' in actual_one_row, "Should include measures"
    assert 'cls' in actual_one_row, "Should include measures"
    
    # Check that we DON'T have ORDER BY or extra input columns
    assert 'id' not in actual_one_row, "Should NOT include ORDER BY columns in ONE ROW PER MATCH"
    assert 'value' not in actual_one_row, "Should NOT include extra input columns in ONE ROW PER MATCH"
    assert 'extra' not in actual_one_row, "Should NOT include extra input columns in ONE ROW PER MATCH"
    
    print("✓ ONE ROW PER MATCH column ordering is correct")
    
    # Test 2: ALL ROWS PER MATCH with SELECT *
    print("\\n=== Test 2: ALL ROWS PER MATCH ===")
    query2 = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        PARTITION BY part
        ORDER BY id
        MEASURES 
            MATCH_NUMBER() AS match_num,
            CLASSIFIER() AS cls
        ALL ROWS PER MATCH
        AFTER MATCH SKIP PAST LAST ROW
        PATTERN (A)
        DEFINE A AS A.value > 70
    ) AS m
    """
    
    result2 = match_recognize(query2, test_data)
    print(f"Result columns: {list(result2.columns)}")
    print("Result:")
    print(result2)
    
    # Verify ALL ROWS PER MATCH column ordering: PARTITION BY + ORDER BY + MEASURES + remaining
    actual_all_rows = list(result2.columns)
    
    # Check SQL:2016 ordering
    partition_idx = actual_all_rows.index('part') if 'part' in actual_all_rows else -1
    order_idx = actual_all_rows.index('id') if 'id' in actual_all_rows else -1
    measure1_idx = actual_all_rows.index('match_num') if 'match_num' in actual_all_rows else -1
    measure2_idx = actual_all_rows.index('cls') if 'cls' in actual_all_rows else -1
    
    assert partition_idx >= 0, "Should include partition column"
    assert order_idx >= 0, "Should include ORDER BY columns in ALL ROWS PER MATCH"
    assert measure1_idx >= 0, "Should include measures"
    assert measure2_idx >= 0, "Should include measures"
    
    # Check ordering: PARTITION BY before ORDER BY before MEASURES
    assert partition_idx < order_idx, "PARTITION BY should come before ORDER BY"
    assert order_idx < measure1_idx, "ORDER BY should come before MEASURES"
    assert order_idx < measure2_idx, "ORDER BY should come before MEASURES"
    
    print("✓ ALL ROWS PER MATCH column ordering is correct")
    
    # Test 3: Specific column selection (should not be affected)
    print("\\n=== Test 3: Specific Column Selection ===")
    query3 = """
    SELECT id, match_num
    FROM data
    MATCH_RECOGNIZE (
        PARTITION BY part
        ORDER BY id
        MEASURES MATCH_NUMBER() AS match_num
        ONE ROW PER MATCH
        PATTERN (A)
        DEFINE A AS A.value > 70
    ) AS m
    """
    
    result3 = match_recognize(query3, test_data)
    print(f"Result columns: {list(result3.columns)}")
    print("Result:")
    print(result3)
    
    # Should only have specified columns
    expected_specific = ['id', 'match_num']
    actual_specific = list(result3.columns)
    assert set(actual_specific) == set(expected_specific), f"Should only have {expected_specific}"
    
    print("✓ Specific column selection works correctly")
    
    print("\\n🎉 All tests passed! SELECT * column ordering is working correctly.")

if __name__ == "__main__":
    test_comprehensive_select_star()
