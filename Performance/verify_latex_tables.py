#!/usr/bin/env python3
"""
Verify LaTeX Tables Against Actual Test Results
Compares Chapter 6 table values with the merged benchmark JSON.
"""

import json
import sys
from pathlib import Path

# Load the actual test results
RESULTS_PATH = Path(__file__).resolve().parent / 'merged_sizes_results_20260626_085544.json'
with RESULTS_PATH.open('r') as f:
    results = json.load(f)

print("=" * 80)
print("VERIFYING LATEX TABLES AGAINST ACTUAL TEST RESULTS")
print("=" * 80)

# Build lookup dictionary
data = {}
for r in results:
    pattern = r['pattern_name']
    size = r['dataset_size']
    key = (pattern, size)
    data[key] = r

# Define what's in the LaTeX tables
latex_tables = {
    "Execution Times (Table 4)": {
        ('simple_sequence', 25000): 1.96,
        ('simple_sequence', 35000): 2.82,
        ('simple_sequence', 50000): 3.91,
        ('simple_sequence', 75000): 6.07,
        ('simple_sequence', 100000): 8.34,
        ('simple_sequence', 150000): 13.07,
        ('simple_sequence', 200000): 16.27,
        ('simple_sequence', 300000): 26.35,
        ('alternation', 25000): 2.13,
        ('alternation', 35000): 3.26,
        ('alternation', 50000): 4.58,
        ('alternation', 75000): 7.15,
        ('alternation', 100000): 10.02,
        ('alternation', 150000): 15.29,
        ('alternation', 200000): 19.91,
        ('alternation', 300000): 31.44,
        ('quantified', 25000): 3.44,
        ('quantified', 35000): 5.23,
        ('quantified', 50000): 7.08,
        ('quantified', 75000): 10.73,
        ('quantified', 100000): 14.59,
        ('quantified', 150000): 22.27,
        ('quantified', 200000): 29.13,
        ('quantified', 300000): 45.37,
        ('optional_pattern', 25000): 2.06,
        ('optional_pattern', 35000): 3.01,
        ('optional_pattern', 50000): 4.15,
        ('optional_pattern', 75000): 6.52,
        ('optional_pattern', 100000): 8.88,
        ('optional_pattern', 150000): 13.49,
        ('optional_pattern', 200000): 18.18,
        ('optional_pattern', 300000): 27.56,
        ('complex_nested', 25000): 3.66,
        ('complex_nested', 35000): 5.29,
        ('complex_nested', 50000): 7.32,
        ('complex_nested', 75000): 11.65,
        ('complex_nested', 100000): 15.53,
        ('complex_nested', 150000): 26.93,
        ('complex_nested', 200000): 34.49,
        ('complex_nested', 300000): 51.21,
    },
    "Throughput (Table 5)": {
        ('simple_sequence', 25000): 12727,
        ('simple_sequence', 35000): 12403,
        ('simple_sequence', 50000): 12798,
        ('simple_sequence', 75000): 12348,
        ('simple_sequence', 100000): 11997,
        ('simple_sequence', 150000): 11477,
        ('simple_sequence', 200000): 12293,
        ('simple_sequence', 300000): 11383,
        ('alternation', 25000): 11762,
        ('alternation', 35000): 10741,
        ('alternation', 50000): 10906,
        ('alternation', 75000): 10482,
        ('alternation', 100000): 9977,
        ('alternation', 150000): 9809,
        ('alternation', 200000): 10047,
        ('alternation', 300000): 9541,
        ('quantified', 25000): 7275,
        ('quantified', 35000): 6690,
        ('quantified', 50000): 7058,
        ('quantified', 75000): 6988,
        ('quantified', 100000): 6854,
        ('quantified', 150000): 6735,
        ('quantified', 200000): 6866,
        ('quantified', 300000): 6612,
        ('optional_pattern', 25000): 12159,
        ('optional_pattern', 35000): 11641,
        ('optional_pattern', 50000): 12046,
        ('optional_pattern', 75000): 11497,
        ('optional_pattern', 100000): 11261,
        ('optional_pattern', 150000): 11116,
        ('optional_pattern', 200000): 11002,
        ('optional_pattern', 300000): 10885,
        ('complex_nested', 25000): 6825,
        ('complex_nested', 35000): 6618,
        ('complex_nested', 50000): 6828,
        ('complex_nested', 75000): 6436,
        ('complex_nested', 100000): 6439,
        ('complex_nested', 150000): 5570,
        ('complex_nested', 200000): 5798,
        ('complex_nested', 300000): 5858,
    },
    "Hits Found (Table 6)": {
        ('simple_sequence', 25000): 1915,
        ('simple_sequence', 35000): 3588,
        ('simple_sequence', 50000): 4322,
        ('simple_sequence', 75000): 6718,
        ('simple_sequence', 100000): 9067,
        ('alternation', 25000): 277,
        ('alternation', 35000): 326,
        ('alternation', 50000): 612,
        ('alternation', 75000): 1100,
        ('alternation', 100000): 1828,
        ('optional_pattern', 25000): 3174,
        ('optional_pattern', 35000): 5276,
        ('optional_pattern', 50000): 7081,
        ('optional_pattern', 75000): 10982,
        ('optional_pattern', 100000): 15247,
        ('quantified', 25000): 1023,
        ('quantified', 35000): 1516,
        ('quantified', 50000): 2219,
        ('quantified', 75000): 3756,
        ('quantified', 100000): 5643,
        ('complex_nested', 25000): 1669,
        ('complex_nested', 35000): 2262,
        ('complex_nested', 50000): 3800,
        ('complex_nested', 75000): 6333,
        ('complex_nested', 100000): 9420,
    },
    "Memory Usage (Table 7)": {
        ('simple_sequence', 25000): 14.09,
        ('alternation', 25000): 2.45,
        ('optional_pattern', 25000): 6.38,
        ('quantified', 25000): 1.27,
        ('complex_nested', 25000): 0.46,
        ('simple_sequence', 35000): 13.21,
        ('alternation', 35000): 1.23,
        ('optional_pattern', 35000): 7.68,
        ('quantified', 35000): 3.68,
        ('complex_nested', 35000): 10.95,
        ('simple_sequence', 50000): 11.27,
        ('alternation', 50000): 2.60,
        ('optional_pattern', 50000): 2.80,
        ('quantified', 50000): 4.66,
        ('complex_nested', 50000): 6.57,
        ('simple_sequence', 75000): 32.57,
        ('alternation', 75000): 8.71,
        ('optional_pattern', 75000): 8.86,
        ('quantified', 75000): 5.93,
        ('complex_nested', 75000): 15.51,
        ('simple_sequence', 100000): 23.37,
        ('alternation', 100000): 30.12,
        ('optional_pattern', 100000): 1.36,
        ('quantified', 100000): 20.60,
        ('complex_nested', 100000): 17.82,
        ('simple_sequence', 150000): 31.71,
        ('alternation', 150000): 44.97,
        ('optional_pattern', 150000): 24.47,
        ('quantified', 150000): 40.91,
        ('complex_nested', 150000): 7.31,
        ('simple_sequence', 200000): 53.64,
        ('alternation', 200000): 44.44,
        ('optional_pattern', 200000): 0.27,
        ('quantified', 200000): 9.16,
        ('complex_nested', 200000): 3.32,
        ('simple_sequence', 300000): 52.98,
        ('alternation', 300000): 57.32,
        ('optional_pattern', 300000): 31.94,
        ('quantified', 300000): 28.42,
        ('complex_nested', 300000): 2.82,
    },
}

errors_found = False
total_checks = 0
mismatches = []

for table_name, latex_data in latex_tables.items():
    print(f"\n{'='*80}")
    print(f"Checking: {table_name}")
    print(f"{'='*80}")
    
    for key, latex_value in latex_data.items():
        pattern, size = key
        actual_result = data.get(key)
        
        if actual_result is None:
            print(f"❌ Missing data for {pattern} @ {size:,} rows")
            errors_found = True
            continue
        
        total_checks += 1
        
        # Get actual value based on table type
        if "Execution" in table_name:
            actual_time = actual_result.get('execution_time_seconds',
                                            actual_result.get('execution_time'))
            actual_value = round(actual_time, 2)  # Already in seconds
            tolerance = 0.5  # 0.5 second tolerance
        elif "Throughput" in table_name:
            actual_value = int(actual_result['throughput_rows_per_sec'])
            tolerance = 500  # 500 rows/sec tolerance
        elif "Hits" in table_name:
            actual_value = actual_result['num_matches']
            tolerance = 0  # Exact match required
        elif "Memory" in table_name:
            actual_value = round(abs(actual_result['memory_used_mb']), 2)
            tolerance = 0.01  # Exact to displayed precision
        
        # Check if values match within tolerance
        diff = abs(actual_value - latex_value)
        
        if diff > tolerance:
            print(f"❌ MISMATCH: {pattern} @ {size:,} rows")
            if isinstance(latex_value, float):
                print(f"   LaTeX: {latex_value:,.2f}")
                print(f"   Actual: {actual_value:,.2f}")
                print(f"   Difference: {diff:,.2f}")
            else:
                print(f"   LaTeX: {latex_value:,}")
                print(f"   Actual: {actual_value:,}")
                print(f"   Difference: {diff:,}")
            errors_found = True
            mismatches.append({
                'table': table_name,
                'pattern': pattern,
                'size': size,
                'latex': latex_value,
                'actual': actual_value,
                'diff': diff
            })
        else:
            print(f"✅ {pattern:20s} @ {size:6,} rows: LaTeX={latex_value:10} | Actual={actual_value:10} | OK")

print(f"\n{'='*80}")
print(f"VERIFICATION SUMMARY")
print(f"{'='*80}")
print(f"Total checks performed: {total_checks}")
print(f"Mismatches found: {len(mismatches)}")

if errors_found:
    print(f"\n❌ VERIFICATION FAILED - Found {len(mismatches)} mismatches")
    print(f"\nMismatches by table:")
    for table_name in latex_tables.keys():
        table_mismatches = [m for m in mismatches if m['table'] == table_name]
        if table_mismatches:
            print(f"\n  {table_name}: {len(table_mismatches)} mismatches")
            for m in table_mismatches:
                print(f"    - {m['pattern']} @ {m['size']:,}: {m['latex']} → {m['actual']} (diff: {m['diff']})")
    sys.exit(1)
else:
    print(f"\n✅ ALL TABLES VERIFIED SUCCESSFULLY!")
    print(f"   All {total_checks} values match within acceptable tolerances")
    sys.exit(0)
