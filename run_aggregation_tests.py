#!/usr/bin/env python3
"""
Comprehensive Test Runner for Row Pattern Matching Aggregation Tests

This script provides flexible execution of the complete aggregation test suite
with support for different test categories, output formats, and execution modes.

Features:
- Category-based test selection (unit, integration, performance, java-conversion)
- Parallel execution support for faster testing
- Comprehensive reporting with coverage analysis
- Performance profiling and metrics collection
- CI/CD integration support
- Detailed failure analysis and debugging output

Usage Examples:
    python run_aggregation_tests.py --all                    # Run all tests
    python run_aggregation_tests.py --unit --integration     # Run specific categories
    python run_aggregation_tests.py --performance --slow     # Run performance tests
    python run_aggregation_tests.py --java-converted         # Run Java conversion tests
    python run_aggregation_tests.py --parallel --workers 4   # Parallel execution
    python run_aggregation_tests.py --coverage --html        # With coverage report

Author: Pattern Matching Engine Team
Version: 3.0.0
"""

import argparse
import sys
import os
import subprocess
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def run_command(cmd: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    """Execute a command and return the result."""
    try:
        result = subprocess.run(
            cmd, 
            capture_output=capture_output, 
            text=True, 
            check=False
        )
        return result
    except Exception as e:
        print(f"Error running command {' '.join(cmd)}: {e}")
        return subprocess.CompletedProcess(cmd, 1, "", str(e))

def get_test_categories() -> Dict[str, List[str]]:
    """Define test categories and their corresponding test files/markers."""
    return {
        'unit': [
            'tests/test_production_aggregations.py',
            '-m', 'not slow and not performance'
        ],
        'integration': [
            'tests/test_aggregation_integration.py',
            '-m', 'integration'
        ],
        'performance': [
            'tests/test_aggregation_performance.py',
            '-m', 'performance or slow'
        ],
        'java_converted': [
            'tests/test_java_aggregations_converted.py',
            'tests/test_missing_java_cases.py',
            '-m', 'basic or partitioning or aggregation_args or selective or count or window'
        ],
        'fixes': [
            'tests/test_aggregation_fixes.py',
            '-m', 'parser_fixes or statistical_fixes or array_fixes or string_fixes or null_handling'
        ],
        'advanced': [
            'tests/test_missing_java_cases.py',
            '-m', 'advanced_stats or specialized_agg or complex_patterns or navigation_agg'
        ],
        'original': [
            'tests/test_production_aggregations.py',
            '-m', 'not slow'
        ],
        'comprehensive': [
            'tests/test_java_aggregations_converted.py',
            'tests/test_aggregation_fixes.py', 
            'tests/test_missing_java_cases.py',
            '-m', 'not slow and not performance'
        ]
    }

def build_pytest_command(
    categories: List[str], 
    parallel: bool = False, 
    workers: int = 4,
    coverage: bool = False,
    verbose: bool = True,
    html_report: bool = False,
    junit_xml: bool = False,
    extra_args: List[str] = None
) -> List[str]:
    """Build the pytest command with specified options."""
    cmd = ['python', '-m', 'pytest']
    
    # Add test files and markers for selected categories
    test_files = set()
    markers = []
    
    test_categories = get_test_categories()
    for category in categories:
        if category in test_categories:
            category_config = test_categories[category]
            # Extract test files (those ending with .py)
            files = [item for item in category_config if item.endswith('.py')]
            test_files.update(files)
            # Extract markers (those starting with -m)
            if '-m' in category_config:
                marker_idx = category_config.index('-m')
                if marker_idx + 1 < len(category_config):
                    markers.append(category_config[marker_idx + 1])
    
    # Add test files
    if test_files:
        cmd.extend(list(test_files))
    else:
        cmd.append('tests/')
    
    # Add markers
    if markers:
        combined_markers = ' or '.join(f'({m})' for m in markers)
        cmd.extend(['-m', combined_markers])
    
    # Add verbosity
    if verbose:
        cmd.append('-v')
    
    # Add parallel execution
    if parallel:
        cmd.extend(['-n', str(workers)])
    
    # Add coverage
    if coverage:
        cmd.extend([
            '--cov=src',
            '--cov-report=term-missing',
            '--cov-report=xml'
        ])
        if html_report:
            cmd.append('--cov-report=html')
    
    # Add JUnit XML output
    if junit_xml:
        cmd.extend(['--junit-xml=test-results.xml'])
    
    # Add extra arguments
    if extra_args:
        cmd.extend(extra_args)
    
    return cmd

def check_dependencies():
    """Check if required test dependencies are available."""
    missing_deps = []
    
    try:
        import pytest
    except ImportError:
        missing_deps.append('pytest')
    
    try:
        import pandas
    except ImportError:
        missing_deps.append('pandas')
    
    try:
        import numpy
    except ImportError:
        missing_deps.append('numpy')
    
    if missing_deps:
        print(f"Missing required dependencies: {', '.join(missing_deps)}")
        print("Please install them using: pip install " + ' '.join(missing_deps))
        return False
    
    return True

def print_test_summary(categories: List[str], result: subprocess.CompletedProcess, execution_time: float):
    """Print a summary of test execution."""
    print("\n" + "="*80)
    print("TEST EXECUTION SUMMARY")
    print("="*80)
    print(f"Categories: {', '.join(categories)}")
    print(f"Execution time: {execution_time:.2f} seconds")
    print(f"Exit code: {result.returncode}")
    
    if result.returncode == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    
    # Parse output for test counts
    if result.stdout:
        lines = result.stdout.split('\n')
        for line in lines:
            if 'passed' in line and ('failed' in line or 'error' in line or 'skipped' in line):
                print(f"Results: {line}")
                break
    
    print("="*80)

def list_available_tests():
    """List all available test files and categories."""
    print("Available Test Categories:")
    print("-" * 40)
    
    categories = get_test_categories()
    for category, config in categories.items():
        files = [item for item in config if item.endswith('.py')]
        markers = []
        if '-m' in config:
            marker_idx = config.index('-m')
            if marker_idx + 1 < len(config):
                markers.append(config[marker_idx + 1])
        
        print(f"\n{category.upper()}:")
        print(f"  Files: {', '.join(files)}")
        if markers:
            print(f"  Markers: {', '.join(markers)}")

def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(
        description='Run aggregation tests with flexible options',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all                    # Run all tests
  %(prog)s --unit --integration     # Run specific categories
  %(prog)s --java-converted         # Run Java conversion tests
  %(prog)s --comprehensive          # Run comprehensive test suite
  %(prog)s --performance --slow     # Run performance tests
  %(prog)s --parallel --workers 8   # Use parallel execution
  %(prog)s --coverage --html        # Generate coverage report
  %(prog)s --list                   # List available test categories
        """
    )
    
    # Test category options
    parser.add_argument('--all', action='store_true', help='Run all test categories')
    parser.add_argument('--unit', action='store_true', help='Run unit tests')
    parser.add_argument('--integration', action='store_true', help='Run integration tests')
    parser.add_argument('--performance', action='store_true', help='Run performance tests')
    parser.add_argument('--java-converted', action='store_true', help='Run Java converted tests')
    parser.add_argument('--fixes', action='store_true', help='Run aggregation fixes tests')
    parser.add_argument('--advanced', action='store_true', help='Run advanced scenario tests')
    parser.add_argument('--original', action='store_true', help='Run original production tests')
    parser.add_argument('--comprehensive', action='store_true', help='Run comprehensive test suite')
    
    # Execution options
    parser.add_argument('--parallel', action='store_true', help='Run tests in parallel')
    parser.add_argument('--workers', type=int, default=4, help='Number of parallel workers')
    parser.add_argument('--slow', action='store_true', help='Include slow tests')
    
    # Reporting options
    parser.add_argument('--coverage', action='store_true', help='Generate coverage report')
    parser.add_argument('--html', action='store_true', help='Generate HTML coverage report')
    parser.add_argument('--junit-xml', action='store_true', help='Generate JUnit XML report')
    parser.add_argument('--verbose', action='store_true', default=True, help='Verbose output')
    parser.add_argument('--quiet', action='store_true', help='Quiet output')
    
    # Additional options
    parser.add_argument('--dry-run', action='store_true', help='Show command without running')
    parser.add_argument('--list', action='store_true', help='List available test categories')
    parser.add_argument('--check-deps', action='store_true', help='Check test dependencies')
    parser.add_argument('--extra-args', nargs='*', help='Additional pytest arguments')
    
    args = parser.parse_args()
    
    # Handle special commands
    if args.list:
        list_available_tests()
        return 0
    
    if args.check_deps:
        if check_dependencies():
            print("✅ All dependencies are available")
            return 0
        else:
            return 1
    
    # Check dependencies before running tests
    if not check_dependencies():
        return 1
    
    # Determine which test categories to run
    categories = []
    if args.all:
        categories = ['unit', 'integration', 'performance', 'java_converted', 'fixes', 'advanced']
    elif args.comprehensive:
        categories = ['comprehensive']
    else:
        if args.unit: categories.append('unit')
        if args.integration: categories.append('integration')
        if args.performance: categories.append('performance')
        if args.java_converted: categories.append('java_converted')
        if args.fixes: categories.append('fixes')
        if args.advanced: categories.append('advanced')
        if args.original: categories.append('original')
    
    # Default to comprehensive tests if no category specified
    if not categories:
        categories = ['comprehensive']
    
    # Handle verbosity
    verbose = args.verbose and not args.quiet
    
    # Build pytest command
    cmd = build_pytest_command(
        categories=categories,
        parallel=args.parallel,
        workers=args.workers,
        coverage=args.coverage,
        verbose=verbose,
        html_report=args.html,
        junit_xml=args.junit_xml,
        extra_args=args.extra_args or []
    )
    
    # Add slow test marker if requested
    if args.slow:
        if '-m' not in cmd:
            cmd.extend(['-m', 'slow'])
        else:
            # Find and modify existing marker
            marker_idx = cmd.index('-m') + 1
            cmd[marker_idx] = f"({cmd[marker_idx]}) or slow"
    
    print(f"Running tests for categories: {', '.join(categories)}")
    print(f"Command: {' '.join(cmd)}")
    
    if args.dry_run:
        print("Dry run - command not executed")
        return 0
    
    # Execute the tests
    start_time = time.time()
    result = run_command(cmd, capture_output=False)
    execution_time = time.time() - start_time
    
    # Print summary
    print_test_summary(categories, result, execution_time)
    
    return result.returncode

if __name__ == '__main__':
    sys.exit(main())
    
    # Add test selection based on type
    if args.test_type == "unit":
        cmd_parts.extend(["-m", "unit"])
    elif args.test_type == "integration":
        cmd_parts.extend(["-m", "integration"])
    elif args.test_type == "performance":
        cmd_parts.extend(["-m", "performance"])
    
    # Add slow tests if requested
    if not args.slow:
        if "-m" in cmd_parts:
            # Modify existing marker expression
            marker_idx = cmd_parts.index("-m") + 1
            cmd_parts[marker_idx] += " and not slow"
        else:
            cmd_parts.extend(["-m", "not slow"])
    
    # Add verbosity
    if args.verbose:
        cmd_parts.append("-v")
    
    # Add parallel execution
    if args.parallel:
        cmd_parts.extend(["-n", str(args.parallel)])
    
    # Add coverage if requested
    if args.coverage:
        cmd_parts.extend([
            "--cov=src",
            "--cov-report=html",
            "--cov-report=term-missing",
            "--cov-report=xml"
        ])
    
    # Add test paths
    test_files = [
        "tests/test_production_aggregations.py",
        "tests/test_advanced_aggregation_scenarios.py",
        "tests/test_aggregation_performance.py"
    ]
    
    # Filter test files that exist
    existing_files = [f for f in test_files if Path(f).exists()]
    cmd_parts.extend(existing_files)
    
    # Run the tests
    cmd = " ".join(cmd_parts)
    success = run_command(cmd, f"Aggregation Tests ({args.test_type})")
    
    if success:
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        
        if args.coverage:
            print("\n📊 Coverage report generated in htmlcov/index.html")
    else:
        print("\n" + "="*60)
        print("❌ SOME TESTS FAILED!")
        print("="*60)
        sys.exit(1)

if __name__ == "__main__":
    main()
