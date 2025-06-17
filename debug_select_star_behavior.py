#!/usr/bin/env python3
"""Debug SELECT * behavior for ONE ROW PER MATCH vs ALL ROWS PER MATCH."""

import pandas as pd
import sys
import os

# Change to the project directory and add it to path
os.chdir('/home/monierashraf/Desktop/llm/Row_match_recognize')
sys.path.insert(0, os.getcwd())

from src.executor.match_recognize import match_recognize

def test_select_star_behavior():
    """Test SELECT * behavior for different output modes."""
    df = pd.DataFrame({
        'a': [1, 2],
        'b': [1, 2],
        'c': [10, 20]
    })
    
    print("Input DataFrame:")
    print(df)
    print(f"Columns: {list(df.columns)}")
    print()
    
    # Test 1: ONE ROW PER MATCH with PARTITION BY
    query1 = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        PARTITION BY a
        PATTERN (X)
        DEFINE X AS b = 1
    ) AS m
    """
    
    print("=== Test 1: ONE ROW PER MATCH with PARTITION BY ===")
    result1 = match_recognize(query1, df)
    print("Result:")
    print(result1)
    if result1 is not None:
        print(f"Columns: {list(result1.columns)}")
    print()
    
    # Test 2: ONE ROW PER MATCH without PARTITION BY
    query2 = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        PATTERN (X)
        DEFINE X AS b = 1
    ) AS m
    """
    
    print("=== Test 2: ONE ROW PER MATCH without PARTITION BY ===")
    result2 = match_recognize(query2, df)
    print("Result:")
    print(result2)
    if result2 is not None:
        print(f"Columns: {list(result2.columns)}")
    print()
    
    # Test 3: ALL ROWS PER MATCH with PARTITION BY
    query3 = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        PARTITION BY a
        ALL ROWS PER MATCH
        PATTERN (X)
        DEFINE X AS b = 1
    ) AS m
    """
    
    print("=== Test 3: ALL ROWS PER MATCH with PARTITION BY ===")
    result3 = match_recognize(query3, df)
    print("Result:")
    print(result3)
    if result3 is not None:
        print(f"Columns: {list(result3.columns)}")
    print()

if __name__ == "__main__":
    test_select_star_behavior()
