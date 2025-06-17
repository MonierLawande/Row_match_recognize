#!/usr/bin/env python3

"""
Debug script for test_output_modes failing test.
"""

import sys
import os
import pandas as pd

# Add the src directory to path
sys.path.append(os.path.abspath('.'))

from src.executor.match_recognize import match_recognize

def debug_output_modes():
    """Debug the failing test_output_modes test."""
    
    print("Starting debug_output_modes...")
    
    try:
        # Use the same test data as in the test
        basic_data = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 70]
        })
        
        print("=== Test Data ===")
        print(basic_data)
        print(f"Data types: {basic_data.dtypes}")
        
        query_template = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                RUNNING LAST(value) AS val,
                CLASSIFIER() AS label
            {rows_per_match}
            AFTER MATCH SKIP PAST LAST ROW
            {pattern}
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        # Test ONE ROW PER MATCH (default)
        query = query_template.format(
            rows_per_match="ONE ROW PER MATCH",
            pattern="PATTERN (B*)"
        )
        
        print("\\n=== Query ===")
        print(query)
        
        print("\\n=== Running match_recognize ===")
        result = match_recognize(query, basic_data)
        print(f"Result type: {type(result)}")
        print(f"Result shape: {result.shape}")
        print(f"Result columns: {list(result.columns)}")
        print(f"Result empty: {result.empty}")
        print(f"Result:\\n{result}")
        
        if not result.empty:
            print(f"Result dtypes: {result.dtypes}")
            print(f"Result values:")
            for i, row in result.iterrows():
                print(f"  Row {i}: {dict(row)}")
        else:
            print("*** RESULT IS EMPTY - THIS IS THE BUG ***")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_output_modes()
