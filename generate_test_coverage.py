#!/usr/bin/env python3
"""
Test summary generator for match_recognize test suite.
Analyzes the test files and generates a summary of test coverage.
"""

import os
import re
import sys
import ast
import argparse
from typing import Dict, List, Any, Set, Tuple

def analyze_test_file(filepath: str) -> Dict[str, Any]:
    """
    Analyze a test file to extract test methods and features covered.
    
    Args:
        filepath: Path to the test file
        
    Returns:
        A dictionary with analysis results
    """
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Extract class and method names
    test_classes = []
    
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                if class_name.startswith('Test'):
                    methods = []
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name.startswith('test_'):
                            methods.append({
                                'name': item.name,
                                'docstring': ast.get_docstring(item) or 'No docstring'
                            })
                    test_classes.append({
                        'name': class_name,
                        'methods': methods,
                        'docstring': ast.get_docstring(node) or 'No docstring'
                    })
    except SyntaxError:
        return {
            'file': os.path.basename(filepath),
            'error': 'Syntax error in file',
            'classes': []
        }
    
    # Extract feature keywords
    feature_keywords = {
        'pattern_syntax': ['pattern', 'concat', 'alternation', 'permute', 'grouping', 'quantifier'],
        'quantifiers': ['*', '+', '?', '{', 'reluctant', 'greedy'],
        'anchors': ['^', '$', 'anchor'],
        'exclusion': ['{-', 'exclusion'],
        'empty_patterns': ['empty', '()'],
        'skip_modes': ['skip', 'past last row', 'next row', 'first', 'last'],
        'output_modes': ['one row per match', 'all rows per match', 'unmatched rows'],
        'classifier': ['classifier'],
        'match_number': ['match_number', 'match number'],
        'navigation': ['prev', 'next', 'first', 'last'],
        'running_final': ['running', 'final'],
        'partition_by': ['partition', 'partition by'],
        'order_by': ['order', 'order by'],
        'subset': ['subset'],
        'permute': ['permute'],
        'empty_matches': ['empty match'],
        'variable_references': ['reference', 'A.value', 'B.value']
    }
    
    features_found = {}
    for feature, keywords in feature_keywords.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', content, re.IGNORECASE):
                features_found[feature] = features_found.get(feature, 0) + 1
    
    return {
        'file': os.path.basename(filepath),
        'classes': test_classes,
        'features': features_found
    }

def generate_coverage_report(analysis_results: List[Dict[str, Any]]) -> str:
    """
    Generate a test coverage report from analysis results.
    
    Args:
        analysis_results: List of analysis results for each file
        
    Returns:
        A formatted coverage report string
    """
    report = []
    report.append("=" * 80)
    report.append("MATCH_RECOGNIZE Test Coverage Report")
    report.append("=" * 80)
    report.append("")
    
    # Summary stats
    total_files = len(analysis_results)
    total_classes = sum(len(result['classes']) for result in analysis_results)
    total_methods = sum(sum(len(cls['methods']) for cls in result['classes']) for result in analysis_results)
    
    report.append(f"Total test files: {total_files}")
    report.append(f"Total test classes: {total_classes}")
    report.append(f"Total test methods: {total_methods}")
    report.append("")
    
    # Feature coverage
    all_features = set()
    feature_counts = {}
    for result in analysis_results:
        for feature, count in result.get('features', {}).items():
            all_features.add(feature)
            feature_counts[feature] = feature_counts.get(feature, 0) + count
    
    report.append("Feature Coverage:")
    report.append("-" * 80)
    for feature in sorted(all_features):
        report.append(f"  {feature}: {feature_counts.get(feature, 0)} occurrences")
    report.append("")
    
    # Missing features
    all_possible_features = {
        'pattern_syntax', 'quantifiers', 'anchors', 'exclusion', 
        'empty_patterns', 'skip_modes', 'output_modes', 'classifier',
        'match_number', 'navigation', 'running_final', 'partition_by',
        'order_by', 'subset', 'permute', 'empty_matches', 'variable_references'
    }
    missing_features = all_possible_features - all_features
    
    if missing_features:
        report.append("Potentially Missing Features:")
        report.append("-" * 80)
        for feature in sorted(missing_features):
            report.append(f"  {feature}")
        report.append("")
    
    # File details
    report.append("Test File Details:")
    report.append("-" * 80)
    for result in analysis_results:
        report.append(f"File: {result['file']}")
        for cls in result['classes']:
            report.append(f"  Class: {cls['name']}")
            report.append(f"    {cls['docstring']}")
            for method in cls['methods']:
                report.append(f"    Method: {method['name']}")
                report.append(f"      {method['docstring']}")
        report.append("")
    
    return "\n".join(report)

def main():
    """Main function to analyze test files and generate a report."""
    parser = argparse.ArgumentParser(description='Generate test coverage report for match_recognize test suite.')
    parser.add_argument('-d', '--directory', type=str, default='tests', help='Directory containing test files')
    parser.add_argument('-o', '--output', type=str, help='Output file for the report')
    
    args = parser.parse_args()
    
    # Find all test files
    test_files = []
    for root, dirs, files in os.walk(args.directory):
        for file in files:
            if file.startswith('test_') and file.endswith('.py'):
                test_files.append(os.path.join(root, file))
    
    if not test_files:
        print(f"No test files found in directory: {args.directory}")
        return 1
    
    # Analyze each file
    analysis_results = []
    for filepath in test_files:
        print(f"Analyzing {filepath}...")
        result = analyze_test_file(filepath)
        analysis_results.append(result)
    
    # Generate the report
    report = generate_coverage_report(analysis_results)
    
    # Output the report
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
