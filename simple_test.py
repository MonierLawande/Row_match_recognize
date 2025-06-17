#!/usr/bin/env python3

import pandas as pd
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_simple():
    """Simple test"""
    try:
        from executor.match_recognize import match_recognize
        
        # Create test data
        df = pd.DataFrame({
            'id': [1, 2],
            'price': [10, 11]
        })
        
        # Query with empty pattern in alternation
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label
            ONE ROW PER MATCH
            PATTERN (() | A)
            DEFINE
                A AS price > 10
        ) AS result
        """
        
        print("Running test...")
        result = match_recognize(query, df)
        print("Result:")
        print(result)
        
        # Check specific result
        if not result.empty:
            first_label = result.iloc[0]['label']
            print(f"First label: {first_label} (type: {type(first_label)})")
            if len(result) > 1:
                second_label = result.iloc[1]['label']
                print(f"Second label: {second_label} (type: {type(second_label)})")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple()
