#!/usr/bin/env python3

import pandas as pd
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from executor.match_recognize import match_recognize

def test_empty_pattern_alternation():
    """Test the specific failing case: empty pattern in alternation (() | A)"""
    
    # Create test data
    df = pd.DataFrame({
        'id': [1, 2, 3, 4, 5],
        'price': [10, 11, 12, 13, 14]
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
    
    try:
        print("Testing pattern (() | A) with CLASSIFIER()...")
        print("Input DataFrame:")
        print(df)
        print("\nQuery:")
        print(query)
        
        result = match_recognize(query, df)
        print("\nResult:")
        print(result)
        
        if not result.empty:
            print(f"\nClassifier value: {result.iloc[0]['label']}")
            print(f"Type: {type(result.iloc[0]['label'])}")
            
            # Check if CLASSIFIER() returns None as expected
            if result.iloc[0]['label'] is None:
                print("✅ SUCCESS: CLASSIFIER() correctly returns None for empty pattern!")
                return True
            else:
                print(f"❌ FAILURE: CLASSIFIER() returned '{result.iloc[0]['label']}' instead of None")
                return False
        else:
            print("❌ FAILURE: No match found")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_empty_pattern_alternation()
    sys.exit(0 if success else 1)
