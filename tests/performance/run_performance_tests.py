#!/usr/bin/env python3
"""
Performance Test Runner for MATCH_RECOGNIZE Caching Strategies

This script provides a convenient interface to run the comprehensive performance test suite
with various configuration options and reporting capabilities.

Usage Examples:
    # Run full test suite
    python run_performance_tests.py

    # Run quick test for CI/CD
    python run_performance_tests.py --quick

    # Run with custom iterations
    python run_performance_tests.py --iterations 10

    # Check for regressions against baseline
    python run_performance_tests.py --regression-check

    # Save results as new baseline
    python run_performance_tests.py --baseline

    # Run specific strategies only
    python run_performance_tests.py --strategies LRU FIFO

Author: Performance Testing Team
Version: 1.0.0
"""

import sys
import argparse
import logging
from pathlib import Path
import yaml
from typing import List, Optional

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.performance.test_caching_strategies import (
    CachingStrategyTester, PerformanceAnalyzer, PerformanceRegressionDetector,
    CachingStrategy, DatasetSize, PatternComplexity
)

def load_config(config_file: Path) -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Failed to load config file {config_file}: {e}")
        return {}

def setup_logging(output_dir: Path, verbose: bool = False) -> None:
    """Set up logging configuration."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(output_dir / "performance_test.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='MATCH_RECOGNIZE Caching Strategy Performance Test Suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Test execution options
    parser.add_argument('--iterations', type=int, default=None,
                       help='Number of iterations per test case (overrides config)')
    parser.add_argument('--quick', action='store_true',
                       help='Run quick test with reduced parameters')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    # Strategy selection
    parser.add_argument('--strategies', nargs='+', 
                       choices=[s.value for s in CachingStrategy],
                       help='Specific caching strategies to test')
    parser.add_argument('--dataset-sizes', nargs='+',
                       choices=['size_1k', 'size_2k', 'size_4k', 'size_5k'],
                       help='Specific dataset sizes to test (size_1k, size_2k, size_4k, size_5k)')
    parser.add_argument('--pattern-complexities', nargs='+',
                       choices=[c.value.lower() for c in PatternComplexity],
                       help='Specific pattern complexities to test')
    
    # Output options
    parser.add_argument('--output-dir', type=Path, 
                       default=Path('tests/performance/results'),
                       help='Output directory for results')
    parser.add_argument('--config', type=Path,
                       default=Path('tests/performance/config.yaml'),
                       help='Configuration file path')
    
    # Analysis options
    parser.add_argument('--baseline', action='store_true',
                       help='Save results as new baseline for regression detection')
    parser.add_argument('--regression-check', action='store_true',
                       help='Check for performance regressions against baseline')
    parser.add_argument('--regression-threshold', type=float, default=10.0,
                       help='Regression threshold percentage (default: 10.0)')
    
    # Reporting options
    parser.add_argument('--no-charts', action='store_true',
                       help='Skip chart generation')
    parser.add_argument('--no-csv', action='store_true',
                       help='Skip CSV export')
    
    return parser.parse_args()

def filter_test_cases(config: dict, args: argparse.Namespace) -> dict:
    """Filter test cases based on command line arguments."""
    filtered_config = config.copy()
    
    # Filter strategies
    if args.strategies:
        available_strategies = {s.lower(): s for s in args.strategies}
        filtered_config['caching_strategies'] = {
            k: v for k, v in config['caching_strategies'].items()
            if k in available_strategies or v['name'] in args.strategies
        }
    
    # Filter dataset sizes
    if args.dataset_sizes:
        filtered_config['datasets'] = {
            k: v for k, v in config['datasets'].items()
            if k in args.dataset_sizes
        }
    
    # Filter pattern complexities
    if args.pattern_complexities:
        filtered_config['patterns'] = {
            k: v for k, v in config['patterns'].items()
            if k in args.pattern_complexities
        }
    
    return filtered_config

def main() -> int:
    """Main function to run the performance test suite."""
    args = parse_arguments()
    
    # Set up logging
    setup_logging(args.output_dir, args.verbose)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("MATCH_RECOGNIZE Caching Strategy Performance Test Suite")
    logger.info("=" * 80)
    
    try:
        # Load configuration
        config = load_config(args.config)
        if not config:
            logger.error("Failed to load configuration. Using defaults.")
            return 1
        
        # Apply command line filters
        config = filter_test_cases(config, args)
        
        # Determine test parameters
        if args.quick:
            iterations = config.get('quick_mode', {}).get('iterations_per_test', 2)
            logger.info("Running in quick mode with reduced parameters")
        else:
            iterations = args.iterations or config.get('execution', {}).get('iterations_per_test', 5)
        
        logger.info(f"Test configuration:")
        logger.info(f"  Iterations per test: {iterations}")
        logger.info(f"  Strategies: {list(config.get('caching_strategies', {}).keys())}")
        logger.info(f"  Dataset sizes: {list(config.get('datasets', {}).keys())}")
        logger.info(f"  Pattern complexities: {list(config.get('patterns', {}).keys())}")
        
        # Initialize and run tester
        tester = CachingStrategyTester(iterations_per_test=iterations)
        results = tester.run_full_test_suite()
        
        if not results:
            logger.error("No test results obtained. Exiting.")
            return 1
        
        logger.info(f"Test suite completed. {len(results)} test cases executed.")
        
        # Analyze results
        analyzer = PerformanceAnalyzer(results)
        summary = analyzer.generate_summary_report()
        
        # Generate outputs
        if not args.no_charts:
            analyzer.create_performance_charts()
            logger.info("Performance charts generated")
        
        if not args.no_csv:
            analyzer.export_detailed_results()
            logger.info("Detailed results exported to CSV")
        
        # Print summary
        print("\n" + "=" * 60)
        print("PERFORMANCE TEST SUMMARY")
        print("=" * 60)
        print(f"Total test cases: {summary['test_summary']['total_test_cases']}")
        print(f"Strategies tested: {summary['test_summary']['strategies_tested']}")
        
        print("\nBest performing strategies:")
        for metric, strategy in summary['best_strategies'].items():
            print(f"  {metric.replace('_', ' ').title()}: {strategy}")
        
        print("\nRecommendations:")
        for key, recommendation in summary['recommendations'].items():
            print(f"  {key.replace('_', ' ').title()}: {recommendation}")
        
        # Regression detection
        if args.regression_check:
            detector = PerformanceRegressionDetector()
            regressions = detector.detect_regressions(summary, args.regression_threshold)
            
            if any(regressions.values()):
                print("\n⚠️  PERFORMANCE REGRESSIONS DETECTED:")
                for category, issues in regressions.items():
                    if issues:
                        print(f"\n{category.replace('_', ' ').title()}:")
                        for issue in issues:
                            print(f"  - {issue}")
                return 1
            else:
                print("\n✅ No performance regressions detected")
        
        # Save baseline
        if args.baseline:
            detector = PerformanceRegressionDetector()
            detector.save_as_baseline(summary)
            print(f"\n📊 Results saved as new baseline")
        
        print(f"\n📁 Results saved to: {args.output_dir}")
        print("✅ Performance test suite completed successfully")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Test suite interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Test suite failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
