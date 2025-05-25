#!/usr/bin/env python3
"""
Test script to verify the exclusion pattern aggregation bug fix.

Expected output for RUNNING SUM with exclusion patterns:
- Row 0 (Alice): running_sum = 1200 (salary: 1200)
- Row 1 (Bob): running_sum = 2500 (salary: 1300, sum: 1200 + 1300 = 2500)
- Row 3 (David): running_sum = 4500 (salary: 1100, sum: 1200 + 1300 + 900 + 1100 = 4500)

Note: Row 2 (Charlie, salary: 900) should be INCLUDED in the aggregation but EXCLUDED from output.
"""

import pandas as pd
import sys
import os

# Add the src directory to the path  
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from executor.match_recognize import match_recognize

def test_exclusion_pattern_fix():
    """Test the exclusion pattern aggregation fix."""
    
    # Create test data - using the same data from the debug output
    data = [
        {"id": 1, "name": "Alice", "department": "Sales", "region": "West", "hire_date": "2021-01-01", "salary": 1200},
        {"id": 2, "name": "Bob", "department": "Sales", "region": "West", "hire_date": "2021-01-02", "salary": 1300},
        {"id": 3, "name": "Charlie", "department": "Sales", "region": "West", "hire_date": "2021-01-03", "salary": 900},
        {"id": 4, "name": "Diana", "department": "Sales", "region": "West", "hire_date": "2021-01-04", "salary": 1100},
    ]
    
    df = pd.DataFrame(data)
    
    print("Input data:")
    print(df[['name', 'salary']])
    print()
    
    # Test query with exclusion pattern - matching the debug case
    query = """
    SELECT * FROM memory.default.employees MATCH_RECOGNIZE(
        PARTITION BY department, region
        ORDER BY hire_date
        MEASURES 
            CLASSIFIER() AS pattern_var,
            salary AS current_salary,
            RUNNING SUM(salary) AS running_sum
        ALL ROWS PER MATCH
        PATTERN (A C* {- B+ -} C+)
        DEFINE 
            A AS salary > 1000,
            B AS salary < 1000,
            C AS salary > 1000
    );
    """
    
    print("Query with exclusion pattern: A C* {- B+ -} C+")
    print("Expected match: Alice(A) + Bob(C) + Charlie(excluded B) + Diana(C)")
    print()
    
    # Execute the query
    try:
        result = match_recognize(query, df)
        print("Result:")
        print(result[['name', 'pattern_var', 'current_salary', 'running_sum']])
        print()
        
        # Extract running_sum values for analysis
        if not result.empty and 'running_sum' in result.columns:
            running_sums = result['running_sum'].tolist()
            names = result['name'].tolist()
            
            print("RUNNING SUM Analysis:")
            for i, (name, sum_val) in enumerate(zip(names, running_sums)):
                print(f"  Row {i}: {name} -> running_sum = {sum_val}")
            print()
            
            # Expected values according to Trino behavior:
            # Alice: 1200 (just Alice)
            # Bob: 2500 (Alice + Bob = 1200 + 1300)  
            # Diana: 4500 (Alice + Bob + Charlie + Diana = 1200 + 1300 + 900 + 1100)
            expected_running_sums = [1200.0, 2500.0, 4500.0]  # Trino-compatible output
            
            print("Expected running_sum values (Trino-compatible):", expected_running_sums)
            print("Actual running_sum values:", running_sums)
            
            if running_sums == expected_running_sums:
                print("✅ SUCCESS: Exclusion pattern aggregation bug is FIXED!")
                print("The implementation now correctly includes excluded rows in RUNNING aggregations.")
                return True
            else:
                print("❌ FAILED: Bug still exists.")
                print("Expected:", expected_running_sums)
                print("Got:", running_sums)
                
                # Show the difference
                print("\nDifference analysis:")
                if len(running_sums) >= 3:
                    print(f"  Diana's running_sum should be 4500 (including Charlie's 900)")
                    print(f"  Actual Diana's running_sum: {running_sums[2]}")
                    if running_sums[2] == 3600.0:
                        print("  This indicates Charlie's salary (900) was excluded from aggregation - BUG!")
                    elif running_sums[2] == 4500.0:
                        print("  Charlie's salary (900) was correctly included in aggregation - FIXED!")
                return False
        else:
            print("❌ FAILED: No running_sum column found in result")
            return False
            
    except Exception as e:
        print(f"Error executing query: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_exclusion_pattern_fix()
    if success:
        print("\n🎉 All tests passed! The exclusion pattern aggregation bug has been fixed.")
    else:
        print("\n❌ Tests failed. The bug still needs to be fixed.")
        print(result)
        
        # Analyze the result
        print(f"\nResult analysis:")
        print(f"  Number of rows in result: {len(result)}")
        
        if len(result) > 0:
            # Check if MATCH_NUMBER column exists
            if 'MATCH_NUMBER' in result.columns:
                match_numbers = result['MATCH_NUMBER'].unique()
                print(f"  Number of matches: {len(match_numbers)}")
                
                for match_num in match_numbers:
                    match_rows = result[result['MATCH_NUMBER'] == match_num]
                    print(f"  Match {match_num}: {len(match_rows)} rows")
                    for _, row in match_rows.iterrows():
                        pattern_var = row.get('pattern_var', 'None')
                        name = row.get('name', 'Unknown')
                        salary = row.get('salary', 'Unknown')
                        print(f"    - {name} ({pattern_var}) salary={salary}")
            else:
                # Assume single match if no MATCH_NUMBER column
                print(f"  Assuming single match with {len(result)} rows")
                for _, row in result.iterrows():
                    pattern_var = row.get('pattern_var', 'None')
                    name = row.get('name', 'Unknown')
                    salary = row.get('salary', 'Unknown')
                    print(f"    - {name} ({pattern_var}) salary={salary}")
        
        # Check if this matches expected Trino behavior
        has_single_match = 'MATCH_NUMBER' not in result.columns or len(result['MATCH_NUMBER'].unique()) == 1
        has_three_rows = len(result) == 3  # Should exclude Charlie
        has_correct_assignments = (
            len(result) > 0 and
            result.iloc[0].get('pattern_var') == 'A' and  # Alice
            result.iloc[1].get('pattern_var') == 'C' and  # Bob  
            result.iloc[2].get('pattern_var') == 'C'      # Diana
        )
        
        print(f"\nValidation:")
        print(f"  ✓ Single match: {has_single_match}")
        print(f"  ✓ Three rows (excluding Charlie): {has_three_rows}")
        print(f"  ✓ Correct pattern assignments: {has_correct_assignments}")
        
        if has_single_match and has_three_rows and has_correct_assignments:
            print("  ✅ SUCCESS: Pattern matching works as expected!")
            print("  ✅ Exclusion pattern {- B+ -} correctly excludes Charlie from output")
            print("  ✅ Single continuous match spans all 4 rows as expected")
        else:
            print("  ❌ ISSUE: Pattern matching doesn't match expected behavior")
            
    except Exception as e:
        print(f"Error running test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_exclusion_pattern()
