#!/usr/bin/env python3

"""
Debug script for IN predicate with MATCH_NUMBER issue.
"""

import sys
import os
import pandas as pd

# Add the src directory to path
sys.path.append(os.path.abspath('.'))

from src.executor.match_recognize import match_recognize

def debug_in_predicate():
    """Debug the IN predicate with MATCH_NUMBER issue."""
    
    print("=== Debugging IN Predicate with MATCH_NUMBER ===")
    
    # Test data from the failing test
    df = pd.DataFrame({
        'id': [1, 2, 3, 4],
        'value': [100, 200, 300, 400]
    })
    
    print("Input Data:")
    print(df)
    
    query = """
    SELECT val
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES MATCH_NUMBER() IN (0, MATCH_NUMBER()) AS val
        ONE ROW PER MATCH
        AFTER MATCH SKIP TO NEXT ROW
        PATTERN (A+)
        DEFINE A AS true
    ) AS m
    """
    
    print("\\nQuery:")
    print(query)
    
    print("\\nRunning match_recognize...")
    result = match_recognize(query, df)
    
    print(f"\\nResult shape: {result.shape}")
    print(f"Result columns: {list(result.columns)}")
    print(f"Result empty: {result.empty}")
    
    if not result.empty:
        print("\\nResult DataFrame:")
        print(result)
        print(f"\\nResult dtypes: {result.dtypes}")
        
        print("\\n=== Detailed Analysis ===")
        print("Val column values:")
        for i, val in enumerate(result['val']):
            print(f"  Row {i}: {val} (type: {type(val)})")
        
        print("\\nExpected: All values should be True")
        print(f"Actual: {list(result['val'])}")
        
        # Check if any are True
        if result['val'].notna().any():
            print("\\nFound non-None values - checking types...")
            for i, val in enumerate(result['val']):
                if pd.notna(val):
                    print(f"  Row {i}: {val} == True -> {val == True}")
    
    # Test with simpler expression
    print("\\n=== Testing Simpler MATCH_NUMBER Expression ===")
    query2 = """
    SELECT MATCH_NUMBER() AS simple_match_num
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES MATCH_NUMBER() AS simple_match_num
        ONE ROW PER MATCH
        AFTER MATCH SKIP TO NEXT ROW
        PATTERN (A+)
        DEFINE A AS true
    ) AS m
    """
    
    result2 = match_recognize(query2, df)
    print("Simple MATCH_NUMBER result:")
    print(result2)

if __name__ == "__main__":
    debug_in_predicate()
