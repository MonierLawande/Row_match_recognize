#!/usr/bin/env python3

"""
Debug script for column ordering issue in ALL ROWS PER MATCH with SELECT *.
"""

import sys
import os
import pandas as pd

# Add the src directory to path
sys.path.append(os.path.abspath('.'))

from src.executor.match_recognize import match_recognize

def debug_column_ordering():
    """Debug the column ordering issue."""
    
    print("=== Debugging Column Ordering Issue ===")
    
    # Test data from the failing test
    df = pd.DataFrame({
        'id': ['ordering'],
        'part': ['partitioning'], 
        'value': [90]
    })
    
    print("Input Data:")
    print(df)
    print(f"Input columns: {list(df.columns)}")
    
    query = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        PARTITION BY part
        ORDER BY id
        MEASURES CLASSIFIER() AS classy
        ALL ROWS PER MATCH
        PATTERN (A)
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
        
        print("\\n=== EXPECTED vs ACTUAL ===")
        expected_order = ['part', 'id', 'classy', 'value']
        actual_order = list(result.columns)
        
        print(f"Expected order: {expected_order}")
        print(f"Actual order:   {actual_order}")
        
        print("\\nComparison:")
        for i, (exp, act) in enumerate(zip(expected_order, actual_order)):
            status = "✓" if exp == act else "✗"
            print(f"  Position {i}: {status} Expected '{exp}', Got '{act}'")

if __name__ == "__main__":
    debug_column_ordering()
