#!/usr/bin/env python3
"""
Example Usage of MATCH_RECOGNIZE Caching Strategy Performance Testing Suite

This script demonstrates how to use the performance testing suite programmatically
and shows various usage patterns for different scenarios.

Author: Performance Testing Team
Version: 1.0.0
"""

import sys
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.performance.test_caching_strategies import (
    CachingStrategyTester, PerformanceAnalyzer, PerformanceRegressionDetector,
    CachingStrategy, DatasetSize, PatternComplexity, TestCase
)

def example_basic_usage():
    """Example 1: Basic performance test execution."""
    print("=" * 60)
    print("Example 1: Basic Performance Test")
    print("=" * 60)
    
    # Initialize tester with 3 iterations per test
    tester = CachingStrategyTester(iterations_per_test=3)
    
    # Run a subset of tests for demonstration
    test_cases = [
        TestCase(CachingStrategy.LRU, DatasetSize.SIZE_1K, PatternComplexity.SIMPLE),
        TestCase(CachingStrategy.FIFO, DatasetSize.SIZE_1K, PatternComplexity.SIMPLE),
        TestCase(CachingStrategy.NO_CACHE, DatasetSize.SIZE_1K, PatternComplexity.SIMPLE)
    ]
    
    results = []
    for test_case in test_cases:
        print(f"Running test: {test_case.test_id}")
        try:
            result = tester.run_single_test(test_case)
            results.append(result)
            
            print(f"  Execution Time: {result.metrics.execution_time_ms:.2f}ms")
            print(f"  Memory Usage: {result.metrics.memory_usage_mb:.2f}MB")
            print(f"  Cache Hit Rate: {result.metrics.cache_hit_rate:.1f}%")
            
        except Exception as e:
            print(f"  Test failed: {e}")
    
    return results

def example_analysis_and_reporting(results):
    """Example 2: Analyze results and generate reports."""
    print("\n" + "=" * 60)
    print("Example 2: Analysis and Reporting")
    print("=" * 60)
    
    if not results:
        print("No results to analyze")
        return
    
    # Create analyzer
    analyzer = PerformanceAnalyzer(results)
    
    # Generate summary report
    summary = analyzer.generate_summary_report()
    
    print("Performance Summary:")
    print(f"  Total test cases: {summary['test_summary']['total_test_cases']}")
    print(f"  Strategies tested: {summary['test_summary']['strategies_tested']}")
    
    print("\nBest performing strategies:")
    for metric, strategy in summary['best_strategies'].items():
        print(f"  {metric.replace('_', ' ').title()}: {strategy}")
    
    print("\nRecommendations:")
    for key, recommendation in summary['recommendations'].items():
        print(f"  {key.replace('_', ' ').title()}: {recommendation}")
    
    # Generate charts (if matplotlib is available)
    try:
        analyzer.create_performance_charts()
        print("\n📊 Performance charts generated in results directory")
    except ImportError:
        print("\n⚠️  Matplotlib not available - skipping chart generation")
    
    # Export detailed results
    csv_file = analyzer.export_detailed_results()
    print(f"📄 Detailed results exported to: {csv_file}")
    
    return summary

def example_regression_detection(summary):
    """Example 3: Performance regression detection."""
    print("\n" + "=" * 60)
    print("Example 3: Regression Detection")
    print("=" * 60)
    
    # Initialize regression detector
    detector = PerformanceRegressionDetector()
    
    # Save current results as baseline (for demonstration)
    detector.save_as_baseline(summary)
    print("✅ Current results saved as baseline")
    
    # Simulate checking for regressions
    # In real usage, this would compare against a previous baseline
    regressions = detector.detect_regressions(summary, threshold_percent=5.0)
    
    if any(regressions.values()):
        print("\n⚠️  Performance regressions detected:")
        for category, issues in regressions.items():
            if issues:
                print(f"\n{category.replace('_', ' ').title()}:")
                for issue in issues:
                    print(f"  - {issue}")
    else:
        print("\n✅ No performance regressions detected")

def example_custom_test_scenario():
    """Example 4: Custom test scenario with specific parameters."""
    print("\n" + "=" * 60)
    print("Example 4: Custom Test Scenario")
    print("=" * 60)
    
    # Test only LRU vs No-Cache for medium complexity patterns
    tester = CachingStrategyTester(iterations_per_test=2)
    
    custom_tests = [
        TestCase(CachingStrategy.LRU, DatasetSize.SIZE_2K, PatternComplexity.MEDIUM),
        TestCase(CachingStrategy.NO_CACHE, DatasetSize.SIZE_2K, PatternComplexity.MEDIUM)
    ]
    
    print("Comparing LRU vs No-Cache for medium complexity patterns...")
    
    results = []
    for test_case in custom_tests:
        print(f"\nRunning: {test_case.test_id}")
        try:
            result = tester.run_single_test(test_case)
            results.append(result)
            
            print(f"  Strategy: {test_case.caching_strategy.value}")
            print(f"  Execution Time: {result.metrics.execution_time_ms:.2f}ms")
            print(f"  Memory Usage: {result.metrics.memory_usage_mb:.2f}MB")
            print(f"  Cache Hit Rate: {result.metrics.cache_hit_rate:.1f}%")
            
        except Exception as e:
            print(f"  Test failed: {e}")
    
    # Compare results
    if len(results) == 2:
        lru_result = results[0] if results[0].test_case.caching_strategy == CachingStrategy.LRU else results[1]
        no_cache_result = results[1] if results[1].test_case.caching_strategy == CachingStrategy.NO_CACHE else results[0]
        
        time_improvement = ((no_cache_result.metrics.execution_time_ms - lru_result.metrics.execution_time_ms) 
                           / no_cache_result.metrics.execution_time_ms * 100)
        memory_difference = lru_result.metrics.memory_usage_mb - no_cache_result.metrics.memory_usage_mb
        
        print(f"\nComparison Results:")
        print(f"  Time improvement with LRU: {time_improvement:.1f}%")
        print(f"  Memory overhead with LRU: {memory_difference:.2f}MB")
        print(f"  Cache hit rate: {lru_result.metrics.cache_hit_rate:.1f}%")
    
    return results

def example_statistical_analysis(results):
    """Example 5: Statistical analysis of performance data."""
    print("\n" + "=" * 60)
    print("Example 5: Statistical Analysis")
    print("=" * 60)
    
    if len(results) < 2:
        print("Need at least 2 results for statistical analysis")
        return
    
    import statistics
    
    # Group results by caching strategy
    strategy_groups = {}
    for result in results:
        strategy = result.test_case.caching_strategy.value
        if strategy not in strategy_groups:
            strategy_groups[strategy] = []
        strategy_groups[strategy].append(result)
    
    print("Statistical Summary by Strategy:")
    for strategy, strategy_results in strategy_groups.items():
        if len(strategy_results) > 1:
            times = [r.metrics.execution_time_ms for r in strategy_results]
            memories = [r.metrics.memory_usage_mb for r in strategy_results]
            
            print(f"\n{strategy}:")
            print(f"  Execution Time - Mean: {statistics.mean(times):.2f}ms, "
                  f"StdDev: {statistics.stdev(times):.2f}ms")
            print(f"  Memory Usage - Mean: {statistics.mean(memories):.2f}MB, "
                  f"StdDev: {statistics.stdev(memories):.2f}MB")
        else:
            result = strategy_results[0]
            print(f"\n{strategy} (single result):")
            print(f"  Execution Time: {result.metrics.execution_time_ms:.2f}ms")
            print(f"  Memory Usage: {result.metrics.memory_usage_mb:.2f}MB")

def main():
    """Main function demonstrating various usage examples."""
    print("MATCH_RECOGNIZE Caching Strategy Performance Testing Examples")
    print("=" * 80)
    
    # Set up basic logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    try:
        # Example 1: Basic usage
        results = example_basic_usage()
        
        # Example 2: Analysis and reporting
        summary = example_analysis_and_reporting(results)
        
        # Example 3: Regression detection
        if summary:
            example_regression_detection(summary)
        
        # Example 4: Custom test scenario
        custom_results = example_custom_test_scenario()
        
        # Example 5: Statistical analysis
        all_results = results + custom_results
        example_statistical_analysis(all_results)
        
        print("\n" + "=" * 80)
        print("✅ All examples completed successfully!")
        print("📁 Check tests/performance/results/ for generated files")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Example execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
