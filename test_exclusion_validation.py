#!/usr/bin/env python3

import pandas as pd
from src.executor.match_recognize import match_recognize

def test_exclusion_comprehensive():
    """Comprehensive test of the exclusion pattern fix."""
    
    # Test 1: Original problematic case
    print("=== Test 1: Original Case (A C* {- B+ -} C+) ===")
    data1 = [
        {"id": 1, "name": "Alice", "department": "Sales", "region": "West", "hire_date": "2021-01-01", "salary": 1200},
        {"id": 2, "name": "Bob", "department": "Sales", "region": "West", "hire_date": "2021-01-02", "salary": 1300},
        {"id": 3, "name": "Charlie", "department": "Sales", "region": "West", "hire_date": "2021-01-03", "salary": 900},
        {"id": 4, "name": "Diana", "department": "Sales", "region": "West", "hire_date": "2021-01-04", "salary": 1100},
    ]
    
    df1 = pd.DataFrame(data1)
    
    query1 = """
    SELECT * FROM memory.default.employees MATCH_RECOGNIZE(
        PARTITION BY department, region
        ORDER BY hire_date
        MEASURES 
            CLASSIFIER() AS pattern_var,
            salary AS current_salary
        ALL ROWS PER MATCH
        PATTERN (A C* {- B+ -} C+)
        DEFINE 
            A AS salary > 1000,
            B AS salary < 1000,
            C AS salary > 1000
    );
    """
    
    result1 = match_recognize(query1, df1)
    print(f"Result: {len(result1)} rows")
    for _, row in result1.iterrows():
        print(f"  {row['name']} ({row['pattern_var']}) - salary: {row['salary']}")
    
    success1 = (len(result1) == 3 and 
                result1.iloc[0]['pattern_var'] == 'A' and
                result1.iloc[1]['pattern_var'] == 'C' and  
                result1.iloc[2]['pattern_var'] == 'C' and
                'Charlie' not in result1['name'].values)
    
    print(f"✅ Test 1 {'PASSED' if success1 else 'FAILED'}")
    
    # Test 2: Multiple exclusions
    print("\n=== Test 2: Multiple Exclusions (A {- B+ -} {- C+ -} D) ===")
    data2 = [
        {"id": 1, "name": "Alice", "value": 100},   # A
        {"id": 2, "name": "Bob", "value": 50},     # B (excluded)
        {"id": 3, "name": "Charlie", "value": 30}, # C (excluded)  
        {"id": 4, "name": "Diana", "value": 80},   # D
    ]
    
    df2 = pd.DataFrame(data2)
    
    query2 = """
    SELECT * FROM memory.default.test MATCH_RECOGNIZE(
        ORDER BY id
        MEASURES 
            CLASSIFIER() AS pattern_var,
            value AS current_value
        ALL ROWS PER MATCH
        PATTERN (A {- B+ -} {- C+ -} D)
        DEFINE 
            A AS value > 80,
            B AS value BETWEEN 40 AND 60,
            C AS value < 40,
            D AS value > 70
    );
    """
    
    result2 = match_recognize(query2, df2)
    print(f"Result: {len(result2)} rows")
    for _, row in result2.iterrows():
        print(f"  {row['name']} ({row['pattern_var']}) - value: {row['value']}")
    
    success2 = (len(result2) == 2 and 
                'Bob' not in result2['name'].values and
                'Charlie' not in result2['name'].values)
    
    print(f"✅ Test 2 {'PASSED' if success2 else 'FAILED'}")
    
    # Test 3: Exclusion with quantifiers
    print("\n=== Test 3: Exclusion with Quantifiers (A+ {- B* -} C+) ===")
    data3 = [
        {"id": 1, "name": "Alice", "type": "good", "value": 100},    # A
        {"id": 2, "name": "Alice2", "type": "good", "value": 110},   # A  
        {"id": 3, "name": "Bob", "type": "bad", "value": 50},       # B (excluded)
        {"id": 4, "name": "Charlie", "type": "good", "value": 90},  # C
        {"id": 5, "name": "Diana", "type": "good", "value": 95},    # C
    ]
    
    df3 = pd.DataFrame(data3)
    
    query3 = """
    SELECT * FROM memory.default.test MATCH_RECOGNIZE(
        ORDER BY id
        MEASURES 
            CLASSIFIER() AS pattern_var,
            value AS current_value
        ALL ROWS PER MATCH
        PATTERN (A+ {- B* -} C+)
        DEFINE 
            A AS type = 'good' AND value > 100,
            B AS type = 'bad',
            C AS type = 'good' AND value < 100
    );
    """
    
    result3 = match_recognize(query3, df3)
    print(f"Result: {len(result3)} rows")
    for _, row in result3.iterrows():
        print(f"  {row['name']} ({row['pattern_var']}) - value: {row['value']}")
    
    success3 = (len(result3) == 4 and 
                'Bob' not in result3['name'].values)
    
    print(f"✅ Test 3 {'PASSED' if success3 else 'FAILED'}")
    
    overall_success = success1 and success2 and success3
    print(f"\n🎉 Overall: {'ALL TESTS PASSED' if overall_success else 'SOME TESTS FAILED'}")
    
    return overall_success

if __name__ == "__main__":
    test_exclusion_comprehensive()
