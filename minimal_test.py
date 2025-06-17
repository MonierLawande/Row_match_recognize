#!/usr/bin/env python3

import pandas as pd
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_minimal():
    """Minimal test for empty pattern precedence"""
    try:
        from executor.match_recognize import match_recognize
        
        # Create simple test data
        df = pd.DataFrame({
            'id': [1, 2],
            'value': [10, 20]
        })
        
        print("Testing pattern (() | A) with DEFINE A AS value > 15...")
        print("Expected: Both rows should match empty pattern with CLASSIFIER() = None")
        print()
        
        # Query where A only matches row 2 (value=20 > 15)
        # But (() | A) should prefer empty pattern for all rows
        query = """
        SELECT id, CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ONE ROW PER MATCH
            PATTERN (() | A)
            DEFINE A AS value > 15
        ) AS result
        """
        
        result = match_recognize(query, df)
        print("Actual result:")
        print(result)
        print()
        
        # Check results
        if not result.empty:
            for i, row in result.iterrows():
                label = row['label']
                row_id = row['id']
                print(f"Row {row_id}: CLASSIFIER() = {label} (type: {type(label)})")
                
            # Check if all labels are None (empty pattern)
            all_none = all(pd.isna(row['label']) or row['label'] is None for _, row in result.iterrows())
            print()
            if all_none:
                print("✅ SUCCESS: All rows correctly match empty pattern!")
            else:
                print("❌ FAILURE: Some rows match non-empty pattern")
        else:
            print("❌ FAILURE: No results returned")
                
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_minimal()
