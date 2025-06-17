#!/usr/bin/env python3

"""
Test edge cases for the IN predicate fix.
"""

import sys
import os
import pandas as pd

# Add the src directory to path
sys.path.append(os.path.abspath('.'))

from src.executor.match_recognize import match_recognize

def test_edge_cases():
    """Test edge cases for IN predicate with MATCH_NUMBER."""
    
    df = pd.DataFrame({
        'id': [1, 2, 3, 4],
        'value': [100, 200, 300, 400]
    })
    
    print("=== Testing Edge Cases for IN Predicate ===")
    
    # Test case 1: NOT IN predicate
    query1 = """
    SELECT val
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES MATCH_NUMBER() NOT IN (0, 5) AS val
        ONE ROW PER MATCH
        AFTER MATCH SKIP TO NEXT ROW
        PATTERN (A+)
        DEFINE A AS true
    ) AS m
    """
    
    print("\\nTest 1: NOT IN predicate")
    result1 = match_recognize(query1, df)
    print(f"Result: {list(result1['val']) if not result1.empty else 'Empty'}")
    print(f"Expected: [True, True, True, True] (since 1,2,3,4 NOT IN (0,5))")
    
    # Test case 2: IN with single value
    query2 = """
    SELECT val
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES MATCH_NUMBER() IN (2) AS val
        ONE ROW PER MATCH
        AFTER MATCH SKIP TO NEXT ROW
        PATTERN (A+)
        DEFINE A AS true
    ) AS m
    """
    
    print("\\nTest 2: IN with single value")
    result2 = match_recognize(query2, df)
    print(f"Result: {list(result2['val']) if not result2.empty else 'Empty'}")
    print(f"Expected: [False, True, False, False] (only match 2 is in (2))")
    
    # Test case 3: Mixed expression with arithmetic
    query3 = """
    SELECT val
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES (MATCH_NUMBER() + 1) IN (2, 3, 4, 5) AS val
        ONE ROW PER MATCH
        AFTER MATCH SKIP TO NEXT ROW
        PATTERN (A+)
        DEFINE A AS true
    ) AS m
    """
    
    print("\\nTest 3: Arithmetic expression with IN")
    result3 = match_recognize(query3, df)
    print(f"Result: {list(result3['val']) if not result3.empty else 'Empty'}")
    print(f"Expected: [True, True, True, True] (since 2,3,4,5 all in (2,3,4,5))")

if __name__ == "__main__":
    test_edge_cases()
