#!/usr/bin/env python3

import pandas as pd
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.executor.match_recognize import match_recognize

def debug_simple_query():
    """Debug the failing simple query test."""
    
    # Use the same data as the test
    df = pd.DataFrame({
        'id': [1, 2, 3, 4, 5, 6, 7, 8],
        'value': [90, 80, 70, 80, 90, 50, 40, 60]
    })
    
    print("=== Input Data ===")
    print(df)
    
    query = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES
            MATCH_NUMBER() AS match,
            RUNNING LAST(value) AS val,
            CLASSIFIER() AS label
        ALL ROWS PER MATCH
        AFTER MATCH SKIP PAST LAST ROW
        PATTERN (A B+ C+)
        DEFINE
            B AS B.value < PREV(B.value),
            C AS C.value > PREV(C.value)
    ) AS m
    """
    
    print("\n=== Query ===")
    print(query)
    
    try:
        result = match_recognize(query, df)
        
        print(f"\n=== Result ===")
        print(f"Result type: {type(result)}")
        print(f"Result shape: {result.shape}")
        print(f"Result columns: {list(result.columns)}")
        print(f"Result empty: {result.empty}")
        print(f"Result:\n{result}")
        
        # Expected pattern breakdown:
        print(f"\n=== Expected Pattern Analysis ===")
        print(f"Pattern: A B+ C+")
        print(f"A: No explicit condition (should default to TRUE)")
        print(f"B: B.value < PREV(B.value) (decreasing values)")
        print(f"C: C.value > PREV(C.value) (increasing values)")
        
        print(f"\nExpected matches:")
        print(f"Match 1: A(90) B(80) B(70) C(80) C(90) = rows 1-5")
        print(f"Match 2: A(50) B(40) C(60) = rows 6-8")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_simple_query()
