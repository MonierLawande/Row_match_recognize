#!/usr/bin/env python3
"""Debug the properties test failure."""

import pandas as pd
import sys
import os

# Change to the project directory and add it to path
os.chdir('/home/monierashraf/Desktop/llm/Row_match_recognize')
sys.path.insert(0, os.getcwd())

from src.executor.match_recognize import match_recognize

def test_properties_debug():
    """Debug the properties test."""
    df = pd.DataFrame({
        'a': [1],
        'b': [1]
    })
    
    query = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        PARTITION BY a
        PATTERN (X)
        DEFINE X AS b = 1
    ) AS m
    """
    
    print("Input DataFrame:")
    print(df)
    print(f"Columns: {list(df.columns)}")
    print()
    
    result = match_recognize(query, df)
    
    print("Result:")
    print(result)
    if result is not None:
        print(f"Result columns: {list(result.columns)}")
        print(f"Result dtypes:\n{result.dtypes}")
        print(f"Result shape: {result.shape}")
        if not result.empty:
            print(f"First row: {result.iloc[0]}")
    print()

if __name__ == "__main__":
    test_properties_debug()
