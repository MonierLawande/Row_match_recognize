#!/usr/bin/env python3

import pandas as pd
from src.executor.match_recognize import match_recognize

def test_exclusion_pattern():
    """Test the exclusion pattern fix with the exact case from your debug output."""
    
    # Create the test data matching your debug output
    data = [
        {"id": 1, "name": "Alice", "department": "Sales", "region": "West", "hire_date": "2021-01-01", "salary": 1200},
        {"id": 2, "name": "Bob", "department": "Sales", "region": "West", "hire_date": "2021-01-02", "salary": 1300},
        {"id": 3, "name": "Charlie", "department": "Sales", "region": "West", "hire_date": "2021-01-03", "salary": 900},
        {"id": 4, "name": "Diana", "department": "Sales", "region": "West", "hire_date": "2021-01-04", "salary": 1100},
    ]
    
    df = pd.DataFrame(data)
    
    # The query with exclusion pattern
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
    
    print("Testing exclusion pattern: A C* {- B+ -} C+")
    print("Data:")
    for i, row in enumerate(data):
        print(f"  Row {i}: {row['name']} - salary={row['salary']}")
    
    print("\nExpected behavior:")
    print("  Alice (A) matches A AS salary > 1000 ✓")
    print("  Bob (C) matches C AS salary > 1000 ✓") 
    print("  Charlie (excluded B) matches B AS salary < 1000 - should be excluded ✗")
    print("  Diana (C) matches C+ AS salary > 1000 ✓")
    print("  Expected single match: Alice(A) + Bob(C) + Charlie(excluded) + Diana(C)")
    
    try:
        result = match_recognize(query, df)
        print(f"\nActual result:")
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
