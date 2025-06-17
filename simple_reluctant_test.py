#!/usr/bin/env python3

# Direct test of reluctant quantifier behavior
# This bypasses all the complex imports and focuses on the core issue

import pandas as pd

def simple_reluctant_test():
    """Test reluctant quantifier behavior directly"""
    
    print("=== Testing Reluctant Quantifier Issue ===")
    print()
    
    # Test data
    df = pd.DataFrame({'val': [10, 80, 90, 20, 30]})
    print("Test data:")
    print(df)
    print()
    
    # The issue: B*? should prefer empty matches
    print("Pattern: B*? (reluctant zero or more)")
    print("Define: B AS val > 50")
    print()
    
    # What SHOULD happen with reluctant quantifier B*?:
    print("Expected behavior (SQL:2016 compliant):")
    print("- Reluctant quantifiers prefer shorter matches")
    print("- B*? means 'zero or more B, but prefer zero'")
    print("- For each row, try empty match first")
    print("- Empty match succeeds without checking conditions")
    print("- Result: All rows get empty matches")
    print()
    
    expected_results = []
    for i, row in df.iterrows():
        expected_results.append({
            'row': i,
            'val': row['val'],
            'match_number': i + 1,
            'avg_val': None,  # Empty match
            'classifier': None  # Empty match
        })
    
    print("Expected test results:")
    for result in expected_results:
        print(f"Row {result['row']}: val={result['val']}, avg_val={result['avg_val']}, classifier={result['classifier']}")
    
    print()
    print("Key insight: The current implementation is probably treating B*? as greedy")
    print("instead of reluctant, causing it to match actual B patterns instead of empty matches.")

if __name__ == "__main__":
    simple_reluctant_test()
