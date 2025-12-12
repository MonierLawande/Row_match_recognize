#!/usr/bin/env python3
"""
Verify LaTeX Tables Against Actual Test Results
Compares all numbers in LATEX_TABLES.tex with medium_sizes_results JSON
"""

import json
import sys

# Load the actual test results
with open('medium_sizes_results_20251027_140201.json', 'r') as f:
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
        ('simple_sequence', 25000): 1.94,
        ('simple_sequence', 35000): 2.77,
        ('simple_sequence', 50000): 3.82,
        ('simple_sequence', 75000): 6.12,
        ('simple_sequence', 100000): 8.20,
        ('alternation', 25000): 2.19,
        ('alternation', 35000): 3.19,
        ('alternation', 50000): 4.41,
        ('alternation', 75000): 7.18,
        ('alternation', 100000): 9.75,
        ('quantified', 25000): 3.45,
        ('quantified', 35000): 5.07,
        ('quantified', 50000): 7.06,
        ('quantified', 75000): 10.87,
        ('quantified', 100000): 14.19,
        ('optional_pattern', 25000): 1.98,
        ('optional_pattern', 35000): 2.92,
        ('optional_pattern', 50000): 4.13,
        ('optional_pattern', 75000): 6.58,
        ('optional_pattern', 100000): 8.69,
        ('complex_nested', 25000): 3.55,
        ('complex_nested', 35000): 5.22,
        ('complex_nested', 50000): 7.31,
        ('complex_nested', 75000): 11.57,
        ('complex_nested', 100000): 15.29,
    },
    "Throughput (Table 5)": {
        ('simple_sequence', 25000): 12918,
        ('simple_sequence', 35000): 12619,
        ('simple_sequence', 50000): 13097,
        ('simple_sequence', 75000): 12256,
        ('simple_sequence', 100000): 12202,
        ('alternation', 25000): 11402,
        ('alternation', 35000): 10979,
        ('alternation', 50000): 11328,
        ('alternation', 75000): 10441,
        ('alternation', 100000): 10255,
        ('quantified', 25000): 7243,
        ('quantified', 35000): 6901,
        ('quantified', 50000): 7082,
        ('quantified', 75000): 6898,
        ('quantified', 100000): 7048,
        ('optional_pattern', 25000): 12642,
        ('optional_pattern', 35000): 11993,
        ('optional_pattern', 50000): 12108,
        ('optional_pattern', 75000): 11400,
        ('optional_pattern', 100000): 11513,
        ('complex_nested', 25000): 7045,
        ('complex_nested', 35000): 6710,
        ('complex_nested', 50000): 6842,
        ('complex_nested', 75000): 6481,
        ('complex_nested', 100000): 6542,
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
        ('simple_sequence', 25000): 15.20,
        ('alternation', 25000): 2.51,
        ('optional_pattern', 25000): 6.73,
        ('quantified', 25000): 1.02,
        ('complex_nested', 25000): 0.56,
        ('simple_sequence', 35000): 15.75,
        ('alternation', 35000): 3.20,
        ('optional_pattern', 35000): 8.48,
        ('quantified', 35000): 2.76,
        ('complex_nested', 35000): 5.92,
        ('simple_sequence', 50000): 7.21,
        ('alternation', 50000): 27.80,
        ('optional_pattern', 50000): 27.16,
        ('quantified', 50000): 3.60,
        ('complex_nested', 50000): 13.88,
        ('simple_sequence', 75000): 21.85,
        ('alternation', 75000): 18.51,
        ('optional_pattern', 75000): 11.83,
        ('quantified', 75000): 5.73,
        ('complex_nested', 75000): 6.89,
        ('simple_sequence', 100000): 22.61,
        ('alternation', 100000): 29.12,
        ('optional_pattern', 100000): 3.34,
        ('quantified', 100000): 20.99,
        ('complex_nested', 100000): 23.29,
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
            actual_value = round(actual_result['execution_time'], 2)  # Already in seconds
            tolerance = 0.5  # 0.5 second tolerance
        elif "Throughput" in table_name:
            actual_value = int(actual_result['throughput_rows_per_sec'])
            tolerance = 500  # 500 rows/sec tolerance
        elif "Hits" in table_name:
            actual_value = actual_result['num_matches']
            tolerance = 0  # Exact match required
        elif "Memory" in table_name:
            actual_value = round(abs(actual_result['memory_used_mb']), 2)
            tolerance = 2.0  # 2 MB tolerance
        
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
