#!/usr/bin/env python3

import sys
import os

# Add the src directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

def analyze_coverage():
    """Analyze test coverage and identify areas that need more testing."""
    
    print("=== TEST COVERAGE ANALYSIS ===")
    print()
    
    # Coverage data from pytest --cov output
    coverage_data = {
        'src/executor/match_recognize.py': {'statements': 697, 'missed': 280, 'coverage': 60},
        'src/matcher/condition_evaluator.py': {'statements': 1029, 'missed': 720, 'coverage': 30},
        'src/matcher/measure_evaluator.py': {'statements': 767, 'missed': 447, 'coverage': 42},
        'src/matcher/row_context.py': {'statements': 601, 'missed': 448, 'coverage': 25},
        'src/matcher/pattern_tokenizer.py': {'statements': 548, 'missed': 260, 'coverage': 53},
        'src/matcher/automata.py': {'statements': 744, 'missed': 256, 'coverage': 66},
        'src/matcher/matcher.py': {'statements': 777, 'missed': 212, 'coverage': 73},
        'src/ast_nodes/ast_nodes.py': {'statements': 416, 'missed': 90, 'coverage': 78},
        'src/matcher/dfa.py': {'statements': 203, 'missed': 45, 'coverage': 78},
        'src/parser/match_recognize_extractor.py': {'statements': 639, 'missed': 185, 'coverage': 71},
        'src/config/production_config.py': {'statements': 140, 'missed': 57, 'coverage': 59},
        'src/utils/pattern_cache.py': {'statements': 92, 'missed': 3, 'coverage': 97},
        'src/monitoring/cache_monitor.py': {'statements': 97, 'missed': 37, 'coverage': 62},
        # Note: Some files have 0% coverage (production_aggregates, health_check, etc.)
    }
    
    print("FILES WITH LOW COVERAGE (<50%):")
    print("-" * 50)
    low_coverage = []
    for file, data in coverage_data.items():
        if data['coverage'] < 50:
            low_coverage.append((file, data['coverage'], data['missed']))
            print(f"{file}: {data['coverage']}% ({data['missed']} lines missed)")
    
    print()
    print("PRIORITY AREAS FOR TEST IMPROVEMENT:")
    print("-" * 50)
    
    # Sort by number of missed lines (impact)
    low_coverage.sort(key=lambda x: x[2], reverse=True)
    
    for i, (file, coverage, missed) in enumerate(low_coverage[:5], 1):
        print(f"{i}. {file}")
        print(f"   Coverage: {coverage}% | Missed lines: {missed}")
        
        if 'condition_evaluator' in file:
            print("   Areas: Navigation functions, conditional logic, error handling")
        elif 'measure_evaluator' in file:
            print("   Areas: Aggregation functions, measure calculations, special functions")
        elif 'row_context' in file:
            print("   Areas: Row navigation, context management, partition handling")
        elif 'match_recognize' in file:
            print("   Areas: Query parsing, result formatting, error scenarios")
        elif 'pattern_tokenizer' in file:
            print("   Areas: Complex patterns, error handling, edge cases")
        print()
    
    print("UNCOVERED PRODUCTION FILES (0% coverage):")
    print("-" * 50)
    uncovered_files = [
        'src/matcher/production_aggregates.py',
        'src/monitoring/health_check.py', 
        'src/monitoring/production_logging.py',
        'src/utils/performance_optimizer.py',
        'src/parser/query_parser.py'
    ]
    
    for file in uncovered_files:
        print(f"- {file}")
    
    print()
    print("CURRENT TEST SUITE SUMMARY:")
    print("-" * 50)
    test_files = {
        'tests/test_match_recognize.py': 12,
        'tests/test_sql2016_compliance.py': 7,
        'tests/test_navigation_and_conditions.py': 9,
        'tests/test_production_aggregates.py': 12,
        'tests/test_pattern_tokenizer.py': 10,
        'tests/test_pattern_cache.py': 7,
    }
    
    total_tests = sum(test_files.values())
    print(f"Total test functions: {total_tests}")
    for file, count in test_files.items():
        print(f"  {file}: {count} tests")
    
    print()
    print("RECOMMENDATIONS:")
    print("-" * 50)
    print("1. IMMEDIATE PRIORITY: Add tests for condition_evaluator.py")
    print("   - Navigation function edge cases")
    print("   - Error handling in condition compilation")
    print("   - Complex conditional expressions")
    print()
    print("2. HIGH PRIORITY: Expand measure_evaluator.py tests")
    print("   - Aggregation function variations")
    print("   - Running vs final semantics edge cases")
    print("   - Classifier with complex patterns")
    print()
    print("3. MEDIUM PRIORITY: Row context management tests")
    print("   - Partition boundary handling")
    print("   - Navigation at partition edges")
    print("   - Memory management scenarios")
    print()
    print("4. PRODUCTION READINESS: Test uncovered files")
    print("   - Add tests for production_aggregates.py")
    print("   - Test health monitoring and logging")
    print("   - Performance optimizer edge cases")
    print()
    print("5. INTEGRATION TESTS: End-to-end scenarios")
    print("   - Complex multi-pattern queries")
    print("   - Large dataset performance")
    print("   - Error recovery scenarios")

if __name__ == "__main__":
    analyze_coverage()
