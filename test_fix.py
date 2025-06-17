#!/usr/bin/env python3

import sys
import os
import pandas as pd

# Add the current directory to path
sys.path.append('.')

def test_output_modes_fix():
    """Test the fix for output modes."""
    print("=== Testing output modes fix ===")
    
    try:
        from src.executor.match_recognize import match_recognize
        
        # Test data from the failing test  
        basic_data = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 70]
        })
        
        print("Input data:")
        print(basic_data)
        print()
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match,
                RUNNING LAST(value) AS val,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH WITH UNMATCHED ROWS
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        print("Query (WITH UNMATCHED ROWS):")
        print(query)
        print()
        
        result = match_recognize(query, basic_data)
        
        print("Actual result:")
        print(result)
        print(f"Result length: {len(result)}")
        print()
        
        print("Expected result:")
        expected_rows = [
            (1, None, None, None),  # Unmatched row
            (2, 1, 80, 'B'),       # Start of match
            (3, 1, 70, 'B'),
            (4, None, None, None)  # Unmatched row
        ]
        print(f"Expected length: {len(expected_rows)}")
        for i, row in enumerate(expected_rows):
            print(f"  Row {i}: id={row[0]}, match={row[1]}, val={row[2]}, label={row[3]}")
        print()
        
        print("=== Analysis ===")
        if len(result) == len(expected_rows):
            print("✓ Length matches")
            
            all_match = True
            for i, (expected_id, expected_match, expected_val, expected_label) in enumerate(expected_rows):
                actual_id = result.iloc[i]['id']
                actual_match = result.iloc[i]['match']
                actual_val = result.iloc[i]['val']
                actual_label = result.iloc[i]['label']
                
                print(f"Row {i}:")
                print(f"  Expected: id={expected_id}, match={expected_match}, val={expected_val}, label={expected_label}")
                print(f"  Actual:   id={actual_id}, match={actual_match}, val={actual_val}, label={actual_label}")
                
                if actual_id != expected_id:
                    print(f"  ✗ ID mismatch: expected {expected_id}, got {actual_id}")
                    all_match = False
                elif (expected_match is None and pd.isna(actual_match)) or actual_match == expected_match:
                    if (expected_val is None and (pd.isna(actual_val) or actual_val is None)) or actual_val == expected_val:
                        if actual_label == expected_label:
                            print(f"  ✓ Row {i} matches")
                        else:
                            print(f"  ✗ Label mismatch: expected {expected_label}, got {actual_label}")
                            all_match = False
                    else:
                        print(f"  ✗ Value mismatch: expected {expected_val}, got {actual_val}")
                        all_match = False
                else:
                    print(f"  ✗ Match mismatch: expected {expected_match}, got {actual_match}")
                    all_match = False
            
            if all_match:
                print("\n🎉 ALL TESTS PASS!")
                return True
            else:
                print("\n❌ Some tests failed")
                return False
        else:
            print(f"❌ Length mismatch: expected {len(expected_rows)}, got {len(result)}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_output_modes_fix()
