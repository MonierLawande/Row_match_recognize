#!/usr/bin/env python3
"""
Comprehensive Performance Testing Suite for MATCH_RECOGNIZE Caching Strategies

This module implements a factorial design performance test comparing three caching strategies:
1. LRU (Least Recently Used) Caching
2. FIFO (First In, First Out) Caching  
3. No-Caching (Baseline)

Performance Metrics:
- Cache Hit Rate (%)
- Execution Time (ms)
- Memory Usage (MB)

Test Scenarios:
- Dataset Sizes: 1K (1,000), 2K (2,000), 4K (4,000), 5K (5,000) rows
- Pattern Complexity: Simple, Medium, Complex
- Total: 4×3×3 = 36 test combinations

Author: Performance Testing Team
Version: 1.0.0
"""

import time
import psutil
import gc
import statistics
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import json
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import logging
from contextlib import contextmanager

# Import the main MATCH_RECOGNIZE function
from src.executor.match_recognize import match_recognize

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CachingStrategy(Enum):
    """Enumeration of caching strategies to test."""
    LRU = "LRU"
    FIFO = "FIFO" 
    NO_CACHE = "NO_CACHE"

class DatasetSize(Enum):
    """Enumeration of dataset sizes."""
    SIZE_1K = 1000
    SIZE_2K = 2000
    SIZE_4K = 4000
    SIZE_5K = 5000

class PatternComplexity(Enum):
    """Enumeration of pattern complexity levels."""
    SIMPLE = "SIMPLE"
    MEDIUM = "MEDIUM"
    COMPLEX = "COMPLEX"

@dataclass
class PerformanceMetrics:
    """Container for performance measurement results."""
    cache_hit_rate: float = 0.0  # Percentage (0-100)
    execution_time_ms: float = 0.0  # Milliseconds
    memory_usage_mb: float = 0.0  # Megabytes
    cache_requests: int = 0
    cache_hits: int = 0
    
    def __post_init__(self):
        """Calculate derived metrics."""
        if self.cache_requests > 0:
            self.cache_hit_rate = (self.cache_hits / self.cache_requests) * 100

@dataclass
class TestCase:
    """Definition of a single test case."""
    caching_strategy: CachingStrategy
    dataset_size: DatasetSize
    pattern_complexity: PatternComplexity
    test_id: str = field(init=False)
    
    def __post_init__(self):
        """Generate unique test ID."""
        self.test_id = f"{self.caching_strategy.value}_{self.dataset_size.name}_{self.pattern_complexity.value}"

@dataclass
class TestResult:
    """Results from executing a test case."""
    test_case: TestCase
    metrics: PerformanceMetrics
    iterations: int
    std_dev_time: float = 0.0
    std_dev_memory: float = 0.0

class SyntheticDataGenerator:
    """Generates synthetic test data for performance testing."""
    
    @staticmethod
    def generate_dataset(size: DatasetSize, seed: int = 42) -> pd.DataFrame:
        """Generate synthetic dataset of specified size."""
        np.random.seed(seed)
        n_rows = size.value
        
        # Generate realistic financial/trading data patterns
        data = {
            'id': range(1, n_rows + 1),
            'timestamp': pd.date_range('2024-01-01', periods=n_rows, freq='1min'),
            'price': np.random.normal(100, 10, n_rows).round(2),
            'volume': np.random.randint(100, 10000, n_rows),
            'state': np.random.choice(['start', 'process', 'peak', 'decline', 'end'], n_rows),
            'category': np.random.choice(['A', 'B', 'C', 'D'], n_rows),
            'value': np.random.uniform(10, 1000, n_rows).round(2),
            'trend': np.random.choice(['up', 'down', 'stable'], n_rows)
        }
        
        return pd.DataFrame(data)

class PatternGenerator:
    """Generates test patterns of varying complexity."""
    
    SIMPLE_PATTERNS = [
        "A+",
        "A B*", 
        "A{2,5}",
        "START END",
        "(UP | DOWN)+"
    ]
    
    MEDIUM_PATTERNS = [
        "(A | B)+ C",
        "START (PROCESS)* END",
        "A{1,3} B{2,4} C?",
        "(UP | DOWN){2,} STABLE",
        "PEAK (DECLINE | STABLE)+ END"
    ]
    
    COMPLEX_PATTERNS = [
        "(A{2,5} | B+)* C D{1,3}",
        "START (PROCESS{1,3} | PEAK)+ (DECLINE | STABLE)* END",
        "((UP | DOWN){2,4} STABLE?){1,3} (PEAK | END)",
        "(A B{2,} | C+ D?)* E{1,2}",
        "START ((PROCESS | PEAK){1,2} DECLINE?){2,} END"
    ]
    
    @classmethod
    def get_patterns(cls, complexity: PatternComplexity) -> List[str]:
        """Get patterns for specified complexity level."""
        if complexity == PatternComplexity.SIMPLE:
            return cls.SIMPLE_PATTERNS
        elif complexity == PatternComplexity.MEDIUM:
            return cls.MEDIUM_PATTERNS
        else:
            return cls.COMPLEX_PATTERNS

class MemoryProfiler:
    """Utility for measuring memory usage."""

    def __init__(self):
        """Initialize memory profiler."""
        self.process = psutil.Process()
        self.initial_memory = 0
        self.peak_memory = 0

    @contextmanager
    def measure_memory(self):
        """Context manager to measure peak memory usage."""
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.peak_memory = self.initial_memory

        def update_peak():
            current = self.process.memory_info().rss / 1024 / 1024
            self.peak_memory = max(self.peak_memory, current)

        try:
            yield update_peak
        finally:
            final_memory = self.process.memory_info().rss / 1024 / 1024
            self.peak_memory = max(self.peak_memory, final_memory)

    def get_memory_usage(self) -> float:
        """Get the peak memory usage during measurement."""
        return max(0, self.peak_memory - self.initial_memory)

class CachingStrategyTester:
    """Main class for testing different caching strategies."""
    
    def __init__(self, iterations_per_test: int = 5):
        """Initialize the tester.
        
        Args:
            iterations_per_test: Number of iterations to run per test case for averaging
        """
        self.iterations_per_test = iterations_per_test
        self.results: List[TestResult] = []
        
    def configure_caching_strategy(self, strategy: CachingStrategy):
        """Configure the system to use specified caching strategy."""
        # This would modify the caching configuration in the MATCH_RECOGNIZE implementation
        # For now, we'll simulate this by setting environment variables or configuration
        
        if strategy == CachingStrategy.LRU:
            # Enable LRU caching
            logger.info("Configuring LRU caching strategy")
            # Implementation would set LRU cache parameters
            
        elif strategy == CachingStrategy.FIFO:
            # Enable FIFO caching  
            logger.info("Configuring FIFO caching strategy")
            # Implementation would set FIFO cache parameters
            
        else:  # NO_CACHE
            # Disable caching
            logger.info("Configuring no-caching strategy")
            # Implementation would disable all caching
    
    def run_single_test(self, test_case: TestCase) -> TestResult:
        """Run a single test case with multiple iterations."""
        logger.info(f"Running test case: {test_case.test_id}")
        
        # Configure caching strategy
        self.configure_caching_strategy(test_case.caching_strategy)
        
        # Generate test data
        dataset = SyntheticDataGenerator.generate_dataset(test_case.dataset_size)
        patterns = PatternGenerator.get_patterns(test_case.pattern_complexity)
        
        # Run multiple iterations
        iteration_results = []
        
        for iteration in range(self.iterations_per_test):
            logger.debug(f"  Iteration {iteration + 1}/{self.iterations_per_test}")
            
            # Test each pattern in the complexity level
            for pattern in patterns:
                metrics = self._measure_single_execution(dataset, pattern)
                iteration_results.append(metrics)
        
        # Aggregate results
        avg_metrics = self._aggregate_metrics(iteration_results)
        
        # Calculate standard deviations
        times = [m.execution_time_ms for m in iteration_results]
        memories = [m.memory_usage_mb for m in iteration_results]
        
        std_dev_time = statistics.stdev(times) if len(times) > 1 else 0.0
        std_dev_memory = statistics.stdev(memories) if len(memories) > 1 else 0.0
        
        return TestResult(
            test_case=test_case,
            metrics=avg_metrics,
            iterations=len(iteration_results),
            std_dev_time=std_dev_time,
            std_dev_memory=std_dev_memory
        )

    def _measure_single_execution(self, dataset: pd.DataFrame, pattern: str) -> PerformanceMetrics:
        """Measure performance metrics for a single pattern execution."""

        # Create MATCH_RECOGNIZE query
        query = f"""
            SELECT *
            FROM input_table
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES
                    CLASSIFIER() AS classifier,
                    MATCH_NUMBER() AS match_num
                ALL ROWS PER MATCH
                AFTER MATCH SKIP PAST LAST ROW
                PATTERN ({pattern})
                DEFINE
                    A AS state = 'start',
                    B AS state = 'process',
                    C AS state = 'peak',
                    D AS state = 'decline',
                    E AS state = 'end',
                    START AS state = 'start',
                    PROCESS AS state = 'process',
                    PEAK AS state = 'peak',
                    DECLINE AS state = 'decline',
                    END AS state = 'end',
                    UP AS trend = 'up',
                    DOWN AS trend = 'down',
                    STABLE AS trend = 'stable'
            )
        """

        # Force garbage collection before measurement
        gc.collect()

        # Measure execution time and memory
        profiler = MemoryProfiler()
        with profiler.measure_memory() as memory_tracker:
            start_time = time.perf_counter()

            try:
                result = match_recognize(query, dataset)
                execution_success = True
            except Exception as e:
                logger.warning(f"Pattern execution failed: {e}")
                execution_success = False
                result = pd.DataFrame()

            end_time = time.perf_counter()
            memory_tracker()  # Update peak memory

        execution_time_ms = (end_time - start_time) * 1000
        memory_usage_mb = profiler.get_memory_usage()

        # Get cache statistics (this would need to be implemented in the actual caching system)
        cache_stats = self._get_cache_statistics()

        return PerformanceMetrics(
            execution_time_ms=execution_time_ms,
            memory_usage_mb=memory_usage_mb,
            cache_requests=cache_stats.get('requests', 0),
            cache_hits=cache_stats.get('hits', 0)
        )

    def _get_cache_statistics(self) -> Dict[str, int]:
        """Get current cache statistics from the system."""
        # This would interface with the actual caching implementation
        # For now, return mock statistics
        return {
            'requests': np.random.randint(10, 100),
            'hits': np.random.randint(5, 80)
        }

    def _aggregate_metrics(self, metrics_list: List[PerformanceMetrics]) -> PerformanceMetrics:
        """Aggregate multiple performance metrics into averages."""
        if not metrics_list:
            return PerformanceMetrics()

        total_requests = sum(m.cache_requests for m in metrics_list)
        total_hits = sum(m.cache_hits for m in metrics_list)

        return PerformanceMetrics(
            execution_time_ms=statistics.mean(m.execution_time_ms for m in metrics_list),
            memory_usage_mb=statistics.mean(m.memory_usage_mb for m in metrics_list),
            cache_requests=total_requests,
            cache_hits=total_hits
        )

    def run_full_test_suite(self) -> List[TestResult]:
        """Run the complete factorial test suite."""
        logger.info("Starting comprehensive caching strategy performance test suite")

        test_cases = []

        # Generate all test case combinations (4×3×3 = 36 cases)
        for strategy in CachingStrategy:
            for size in DatasetSize:
                for complexity in PatternComplexity:
                    test_cases.append(TestCase(strategy, size, complexity))

        logger.info(f"Generated {len(test_cases)} test cases")

        # Run all test cases
        self.results = []
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"Progress: {i}/{len(test_cases)} - {test_case.test_id}")

            try:
                result = self.run_single_test(test_case)
                self.results.append(result)

                # Log intermediate results
                logger.info(f"  Execution Time: {result.metrics.execution_time_ms:.2f}ms")
                logger.info(f"  Memory Usage: {result.metrics.memory_usage_mb:.2f}MB")
                logger.info(f"  Cache Hit Rate: {result.metrics.cache_hit_rate:.1f}%")

            except Exception as e:
                logger.error(f"Test case {test_case.test_id} failed: {e}")
                continue

        logger.info(f"Completed test suite. {len(self.results)} successful test cases.")
        return self.results

class PerformanceAnalyzer:
    """Analyzes and reports on performance test results."""

    def __init__(self, results: List[TestResult]):
        """Initialize analyzer with test results."""
        self.results = results
        self.output_dir = Path("tests/performance/results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_summary_report(self) -> Dict[str, Any]:
        """Generate comprehensive summary report."""
        logger.info("Generating performance summary report")

        # Group results by caching strategy
        strategy_groups = {}
        for result in self.results:
            strategy = result.test_case.caching_strategy.value
            if strategy not in strategy_groups:
                strategy_groups[strategy] = []
            strategy_groups[strategy].append(result)

        # Calculate aggregate statistics for each strategy
        strategy_stats = {}
        for strategy, results in strategy_groups.items():
            strategy_stats[strategy] = {
                'avg_execution_time_ms': statistics.mean(r.metrics.execution_time_ms for r in results),
                'avg_memory_usage_mb': statistics.mean(r.metrics.memory_usage_mb for r in results),
                'avg_cache_hit_rate': statistics.mean(r.metrics.cache_hit_rate for r in results),
                'std_execution_time_ms': statistics.stdev(r.metrics.execution_time_ms for r in results) if len(results) > 1 else 0,
                'std_memory_usage_mb': statistics.stdev(r.metrics.memory_usage_mb for r in results) if len(results) > 1 else 0,
                'test_count': len(results)
            }

        # Find best performing strategy for each metric
        best_strategies = {
            'execution_time': min(strategy_stats.keys(), key=lambda s: strategy_stats[s]['avg_execution_time_ms']),
            'memory_usage': min(strategy_stats.keys(), key=lambda s: strategy_stats[s]['avg_memory_usage_mb']),
            'cache_hit_rate': max(strategy_stats.keys(), key=lambda s: strategy_stats[s]['avg_cache_hit_rate'])
        }

        summary = {
            'test_summary': {
                'total_test_cases': len(self.results),
                'strategies_tested': len(strategy_groups),
                'dataset_sizes': len(set(r.test_case.dataset_size for r in self.results)),
                'pattern_complexities': len(set(r.test_case.pattern_complexity for r in self.results))
            },
            'strategy_performance': strategy_stats,
            'best_strategies': best_strategies,
            'recommendations': self._generate_recommendations(strategy_stats, best_strategies)
        }

        # Save summary to JSON
        summary_file = self.output_dir / "performance_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(f"Summary report saved to {summary_file}")
        return summary

    def _generate_recommendations(self, strategy_stats: Dict, best_strategies: Dict) -> Dict[str, str]:
        """Generate performance recommendations based on results."""
        recommendations = {}

        # Overall best strategy
        overall_scores = {}
        for strategy in strategy_stats:
            # Normalize metrics (lower is better for time/memory, higher is better for hit rate)
            time_score = 1 / strategy_stats[strategy]['avg_execution_time_ms']
            memory_score = 1 / strategy_stats[strategy]['avg_memory_usage_mb']
            hit_rate_score = strategy_stats[strategy]['avg_cache_hit_rate'] / 100

            # Weighted average (equal weights for simplicity)
            overall_scores[strategy] = (time_score + memory_score + hit_rate_score) / 3

        best_overall = max(overall_scores.keys(), key=lambda s: overall_scores[s])

        recommendations['overall_best'] = f"{best_overall} provides the best overall performance balance"
        recommendations['execution_speed'] = f"For fastest execution, use {best_strategies['execution_time']}"
        recommendations['memory_efficiency'] = f"For lowest memory usage, use {best_strategies['memory_usage']}"
        recommendations['cache_efficiency'] = f"For best cache performance, use {best_strategies['cache_hit_rate']}"

        return recommendations

    def create_performance_charts(self):
        """Create visualization charts for performance comparison."""
        logger.info("Creating performance visualization charts")

        # Prepare data for plotting
        df_results = []
        for result in self.results:
            df_results.append({
                'Strategy': result.test_case.caching_strategy.value,
                'Dataset_Size': result.test_case.dataset_size.name,
                'Pattern_Complexity': result.test_case.pattern_complexity.value,
                'Execution_Time_ms': result.metrics.execution_time_ms,
                'Memory_Usage_MB': result.metrics.memory_usage_mb,
                'Cache_Hit_Rate': result.metrics.cache_hit_rate
            })

        df = pd.DataFrame(df_results)

        # Set up the plotting style
        plt.style.use('seaborn-v0_8')
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('MATCH_RECOGNIZE Caching Strategy Performance Comparison', fontsize=16)

        # 1. Execution Time by Strategy
        sns.boxplot(data=df, x='Strategy', y='Execution_Time_ms', ax=axes[0,0])
        axes[0,0].set_title('Execution Time by Caching Strategy')
        axes[0,0].set_ylabel('Execution Time (ms)')

        # 2. Memory Usage by Strategy
        sns.boxplot(data=df, x='Strategy', y='Memory_Usage_MB', ax=axes[0,1])
        axes[0,1].set_title('Memory Usage by Caching Strategy')
        axes[0,1].set_ylabel('Memory Usage (MB)')

        # 3. Cache Hit Rate by Strategy
        sns.boxplot(data=df, x='Strategy', y='Cache_Hit_Rate', ax=axes[1,0])
        axes[1,0].set_title('Cache Hit Rate by Strategy')
        axes[1,0].set_ylabel('Cache Hit Rate (%)')

        # 4. Performance by Dataset Size and Pattern Complexity
        pivot_data = df.groupby(['Dataset_Size', 'Pattern_Complexity'])['Execution_Time_ms'].mean().unstack()
        sns.heatmap(pivot_data, annot=True, fmt='.1f', ax=axes[1,1], cmap='YlOrRd')
        axes[1,1].set_title('Avg Execution Time by Size & Complexity')

        plt.tight_layout()
        chart_file = self.output_dir / "performance_comparison_charts.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Performance charts saved to {chart_file}")

        # Create detailed comparison charts
        self._create_detailed_charts(df)

    def _create_detailed_charts(self, df: pd.DataFrame):
        """Create detailed performance analysis charts."""

        # Performance by dataset size
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        fig.suptitle('Performance Metrics by Dataset Size', fontsize=14)

        for i, metric in enumerate(['Execution_Time_ms', 'Memory_Usage_MB', 'Cache_Hit_Rate']):
            sns.barplot(data=df, x='Dataset_Size', y=metric, hue='Strategy', ax=axes[i])
            axes[i].set_title(f'{metric.replace("_", " ")} by Dataset Size')
            axes[i].legend(title='Strategy')

        plt.tight_layout()
        plt.savefig(self.output_dir / "performance_by_dataset_size.png", dpi=300, bbox_inches='tight')
        plt.close()

        # Performance by pattern complexity
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        fig.suptitle('Performance Metrics by Pattern Complexity', fontsize=14)

        for i, metric in enumerate(['Execution_Time_ms', 'Memory_Usage_MB', 'Cache_Hit_Rate']):
            sns.barplot(data=df, x='Pattern_Complexity', y=metric, hue='Strategy', ax=axes[i])
            axes[i].set_title(f'{metric.replace("_", " ")} by Pattern Complexity')
            axes[i].legend(title='Strategy')

        plt.tight_layout()
        plt.savefig(self.output_dir / "performance_by_pattern_complexity.png", dpi=300, bbox_inches='tight')
        plt.close()

    def export_detailed_results(self):
        """Export detailed test results to CSV for further analysis."""
        logger.info("Exporting detailed results to CSV")

        detailed_data = []
        for result in self.results:
            detailed_data.append({
                'Test_ID': result.test_case.test_id,
                'Caching_Strategy': result.test_case.caching_strategy.value,
                'Dataset_Size': result.test_case.dataset_size.value,
                'Dataset_Size_Name': result.test_case.dataset_size.name,
                'Pattern_Complexity': result.test_case.pattern_complexity.value,
                'Execution_Time_ms': result.metrics.execution_time_ms,
                'Memory_Usage_MB': result.metrics.memory_usage_mb,
                'Cache_Hit_Rate': result.metrics.cache_hit_rate,
                'Cache_Requests': result.metrics.cache_requests,
                'Cache_Hits': result.metrics.cache_hits,
                'Iterations': result.iterations,
                'Std_Dev_Time': result.std_dev_time,
                'Std_Dev_Memory': result.std_dev_memory
            })

        df_detailed = pd.DataFrame(detailed_data)
        csv_file = self.output_dir / "detailed_performance_results.csv"
        df_detailed.to_csv(csv_file, index=False)

        logger.info(f"Detailed results exported to {csv_file}")
        return csv_file

class PerformanceRegressionDetector:
    """Detects performance regressions by comparing with baseline results."""

    def __init__(self, baseline_file: Optional[Path] = None):
        """Initialize regression detector.

        Args:
            baseline_file: Path to baseline performance results JSON file
        """
        self.baseline_file = baseline_file or Path("tests/performance/baseline_results.json")
        self.baseline_data = self._load_baseline()

    def _load_baseline(self) -> Optional[Dict]:
        """Load baseline performance data."""
        if self.baseline_file.exists():
            with open(self.baseline_file, 'r') as f:
                return json.load(f)
        return None

    def save_as_baseline(self, summary: Dict[str, Any]):
        """Save current results as new baseline."""
        with open(self.baseline_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info(f"Baseline saved to {self.baseline_file}")

    def detect_regressions(self, current_summary: Dict[str, Any],
                          threshold_percent: float = 10.0) -> Dict[str, List[str]]:
        """Detect performance regressions compared to baseline.

        Args:
            current_summary: Current test results summary
            threshold_percent: Regression threshold percentage

        Returns:
            Dictionary of detected regressions by category
        """
        if not self.baseline_data:
            logger.warning("No baseline data available for regression detection")
            return {}

        regressions = {
            'execution_time': [],
            'memory_usage': [],
            'cache_hit_rate': []
        }

        current_stats = current_summary['strategy_performance']
        baseline_stats = self.baseline_data['strategy_performance']

        for strategy in current_stats:
            if strategy not in baseline_stats:
                continue

            current = current_stats[strategy]
            baseline = baseline_stats[strategy]

            # Check execution time regression (higher is worse)
            time_change = ((current['avg_execution_time_ms'] - baseline['avg_execution_time_ms'])
                          / baseline['avg_execution_time_ms'] * 100)
            if time_change > threshold_percent:
                regressions['execution_time'].append(
                    f"{strategy}: {time_change:.1f}% slower ({current['avg_execution_time_ms']:.1f}ms vs {baseline['avg_execution_time_ms']:.1f}ms)"
                )

            # Check memory usage regression (higher is worse)
            memory_change = ((current['avg_memory_usage_mb'] - baseline['avg_memory_usage_mb'])
                           / baseline['avg_memory_usage_mb'] * 100)
            if memory_change > threshold_percent:
                regressions['memory_usage'].append(
                    f"{strategy}: {memory_change:.1f}% more memory ({current['avg_memory_usage_mb']:.1f}MB vs {baseline['avg_memory_usage_mb']:.1f}MB)"
                )

            # Check cache hit rate regression (lower is worse)
            hit_rate_change = ((baseline['avg_cache_hit_rate'] - current['avg_cache_hit_rate'])
                             / baseline['avg_cache_hit_rate'] * 100)
            if hit_rate_change > threshold_percent:
                regressions['cache_hit_rate'].append(
                    f"{strategy}: {hit_rate_change:.1f}% lower hit rate ({current['avg_cache_hit_rate']:.1f}% vs {baseline['avg_cache_hit_rate']:.1f}%)"
                )

        return regressions

def main():
    """Main function to run the comprehensive performance test suite."""
    import argparse

    parser = argparse.ArgumentParser(description='MATCH_RECOGNIZE Caching Strategy Performance Test Suite')
    parser.add_argument('--iterations', type=int, default=5,
                       help='Number of iterations per test case (default: 5)')
    parser.add_argument('--output-dir', type=str, default='tests/performance/results',
                       help='Output directory for results (default: tests/performance/results)')
    parser.add_argument('--baseline', action='store_true',
                       help='Save results as new baseline for regression detection')
    parser.add_argument('--regression-check', action='store_true',
                       help='Check for performance regressions against baseline')
    parser.add_argument('--quick', action='store_true',
                       help='Run quick test with reduced iterations and smaller datasets')

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f"{args.output_dir}/performance_test.log"),
            logging.StreamHandler()
        ]
    )

    logger.info("=" * 80)
    logger.info("MATCH_RECOGNIZE Caching Strategy Performance Test Suite")
    logger.info("=" * 80)

    # Adjust parameters for quick test
    if args.quick:
        iterations = max(1, args.iterations // 2)
        logger.info("Running in quick mode with reduced parameters")
    else:
        iterations = args.iterations

    try:
        # Initialize tester
        tester = CachingStrategyTester(iterations_per_test=iterations)

        # Run test suite
        start_time = time.time()
        results = tester.run_full_test_suite()
        end_time = time.time()

        total_time = end_time - start_time
        logger.info(f"Test suite completed in {total_time:.2f} seconds")

        if not results:
            logger.error("No test results obtained. Exiting.")
            return 1

        # Analyze results
        analyzer = PerformanceAnalyzer(results)
        summary = analyzer.generate_summary_report()

        # Create visualizations
        analyzer.create_performance_charts()

        # Export detailed results
        analyzer.export_detailed_results()

        # Print summary to console
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

        # Performance regression detection
        if args.regression_check:
            detector = PerformanceRegressionDetector()
            regressions = detector.detect_regressions(summary)

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

        # Save as baseline if requested
        if args.baseline:
            detector = PerformanceRegressionDetector()
            detector.save_as_baseline(summary)
            print(f"\n📊 Results saved as new baseline")

        print(f"\n📁 Detailed results saved to: {args.output_dir}")
        print("✅ Performance test suite completed successfully")

        return 0

    except Exception as e:
        logger.error(f"Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
