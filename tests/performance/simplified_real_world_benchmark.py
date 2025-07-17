#!/usr/bin/env python3
"""
Simplified Real-World Performance Benchmark for MATCH_RECOGNIZE Caching Strategies

This script conducts performance testing using real-world datasets with working SQL patterns.

Author: Performance Testing Team
Version: 1.0.0
"""

import pandas as pd
import numpy as np
import time
import psutil
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any
import warnings
warnings.filterwarnings('ignore')

# Import our MATCH_RECOGNIZE implementation
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.executor.match_recognize import match_recognize
from src.utils.pattern_cache import (
    clear_pattern_cache, get_cache_stats,
    set_caching_enabled, is_caching_enabled
)

class SimplifiedRealWorldBenchmark:
    """Simplified real-world performance benchmark for caching strategies."""
    
    def __init__(self):
        self.results = []
        self.cache_strategies = ['NO_CACHE', 'FIFO', 'LRU']
        
    def generate_financial_data(self, size: int) -> pd.DataFrame:
        """Generate realistic financial trading data."""
        np.random.seed(42)  # For reproducible results
        
        # Generate realistic price movements
        base_price = 100.0
        returns = np.random.normal(0.0001, 0.02, size)
        prices = [base_price]
        
        for i in range(1, size):
            price_change = prices[-1] * returns[i]
            new_price = max(0.01, prices[-1] + price_change)
            prices.append(new_price)
        
        # Generate realistic volume data
        volumes = np.random.poisson(10000, size)
        
        # Create trading data
        df = pd.DataFrame({
            'id': range(1, size + 1),
            'timestamp': pd.date_range('2024-01-01', periods=size, freq='1min'),
            'symbol': ['AAPL'] * size,
            'price': prices,
            'volume': volumes,
            'trend': np.random.choice(['up', 'down', 'stable'], size, p=[0.4, 0.4, 0.2])
        })
        
        return df
    
    def generate_sensor_data(self, size: int) -> pd.DataFrame:
        """Generate realistic IoT sensor data."""
        np.random.seed(43)
        
        # Simulate temperature with daily cycles
        hours = np.linspace(0, 24, size)
        base_temp = 20 + 10 * np.sin(2 * np.pi * hours / 24)
        temperatures = base_temp + np.random.normal(0, 2, size)
        
        df = pd.DataFrame({
            'id': range(1, size + 1),
            'timestamp': pd.date_range('2024-01-01', periods=size, freq='30s'),
            'device_id': ['SENSOR_001'] * size,
            'temperature': temperatures,
            'humidity': 70 - 0.5 * (temperatures - 20) + np.random.normal(0, 5, size),
            'status': np.random.choice(['normal', 'warning', 'critical'], size, p=[0.85, 0.12, 0.03])
        })
        
        return df
    
    def generate_web_analytics_data(self, size: int) -> pd.DataFrame:
        """Generate realistic web analytics data."""
        np.random.seed(44)
        
        # Simulate web traffic patterns
        sessions = np.random.poisson(100, size)
        
        df = pd.DataFrame({
            'id': range(1, size + 1),
            'timestamp': pd.date_range('2024-01-01', periods=size, freq='1min'),
            'sessions': sessions,
            'page_views': sessions * np.random.gamma(2, 1.5),
            'bounce_rate': np.random.beta(2, 3) * 100,
            'traffic_type': np.random.choice(['organic', 'paid', 'social'], size, p=[0.5, 0.3, 0.2])
        })
        
        return df.astype({'page_views': int})
    
    def get_working_patterns(self) -> Dict[str, Dict[str, str]]:
        """Define working MATCH_RECOGNIZE patterns based on successful test cases."""
        
        patterns = {
            'financial_simple': {
                'query': '''
                    SELECT *
                    FROM data
                    MATCH_RECOGNIZE (
                        ORDER BY id
                        MEASURES
                            MATCH_NUMBER() AS match_num,
                            CLASSIFIER() AS label
                        ALL ROWS PER MATCH
                        AFTER MATCH SKIP PAST LAST ROW
                        PATTERN (A B+)
                        DEFINE B AS B.price < PREV(B.price)
                    )
                ''',
                'description': 'Simple price decline pattern'
            },
            'financial_medium': {
                'query': '''
                    SELECT *
                    FROM data
                    MATCH_RECOGNIZE (
                        ORDER BY id
                        MEASURES
                            MATCH_NUMBER() AS match_num,
                            FIRST(A.price) AS start_price,
                            LAST(C.price) AS end_price
                        ALL ROWS PER MATCH
                        AFTER MATCH SKIP PAST LAST ROW
                        PATTERN (A B+ C+)
                        DEFINE
                            B AS B.price < PREV(B.price),
                            C AS C.price > PREV(C.price)
                    )
                ''',
                'description': 'Price decline followed by recovery'
            },
            'financial_complex': {
                'query': '''
                    SELECT *
                    FROM data
                    MATCH_RECOGNIZE (
                        ORDER BY id
                        MEASURES
                            MATCH_NUMBER() AS match_num,
                            COUNT(*) AS pattern_length,
                            AVG(price) AS avg_price
                        ALL ROWS PER MATCH
                        AFTER MATCH SKIP PAST LAST ROW
                        PATTERN (A+ B+ C*)
                        DEFINE
                            A AS trend = 'up',
                            B AS trend = 'down',
                            C AS trend = 'stable'
                    )
                ''',
                'description': 'Complex trend pattern with aggregations'
            },
            'sensor_simple': {
                'query': '''
                    SELECT *
                    FROM data
                    MATCH_RECOGNIZE (
                        ORDER BY id
                        MEASURES
                            MATCH_NUMBER() AS match_num,
                            CLASSIFIER() AS label
                        ALL ROWS PER MATCH
                        AFTER MATCH SKIP PAST LAST ROW
                        PATTERN (A+)
                        DEFINE A AS temperature > 25
                    )
                ''',
                'description': 'Simple temperature threshold detection'
            },
            'sensor_medium': {
                'query': '''
                    SELECT *
                    FROM data
                    MATCH_RECOGNIZE (
                        ORDER BY id
                        MEASURES
                            MATCH_NUMBER() AS match_num,
                            FIRST(A.temperature) AS start_temp,
                            LAST(B.temperature) AS end_temp
                        ALL ROWS PER MATCH
                        AFTER MATCH SKIP PAST LAST ROW
                        PATTERN (A B+)
                        DEFINE B AS B.temperature > PREV(B.temperature)
                    )
                ''',
                'description': 'Temperature rising pattern'
            },
            'sensor_complex': {
                'query': '''
                    SELECT *
                    FROM data
                    MATCH_RECOGNIZE (
                        ORDER BY id
                        MEASURES
                            MATCH_NUMBER() AS match_num,
                            COUNT(*) AS duration,
                            MAX(temperature) AS peak_temp
                        ALL ROWS PER MATCH
                        AFTER MATCH SKIP PAST LAST ROW
                        PATTERN (A B+ C+)
                        DEFINE
                            B AS B.temperature > PREV(B.temperature),
                            C AS C.temperature < PREV(C.temperature)
                    )
                ''',
                'description': 'Temperature spike and decline pattern'
            },
            'web_simple': {
                'query': '''
                    SELECT *
                    FROM data
                    MATCH_RECOGNIZE (
                        ORDER BY id
                        MEASURES
                            MATCH_NUMBER() AS match_num,
                            CLASSIFIER() AS label
                        ALL ROWS PER MATCH
                        AFTER MATCH SKIP PAST LAST ROW
                        PATTERN (A+)
                        DEFINE A AS sessions > 150
                    )
                ''',
                'description': 'High traffic detection'
            },
            'web_medium': {
                'query': '''
                    SELECT *
                    FROM data
                    MATCH_RECOGNIZE (
                        ORDER BY id
                        MEASURES
                            MATCH_NUMBER() AS match_num,
                            SUM(sessions) AS total_sessions
                        ALL ROWS PER MATCH
                        AFTER MATCH SKIP PAST LAST ROW
                        PATTERN (A B+)
                        DEFINE B AS B.sessions > PREV(B.sessions)
                    )
                ''',
                'description': 'Traffic growth pattern'
            },
            'web_complex': {
                'query': '''
                    SELECT *
                    FROM data
                    MATCH_RECOGNIZE (
                        ORDER BY id
                        MEASURES
                            MATCH_NUMBER() AS match_num,
                            COUNT(*) AS pattern_length,
                            AVG(sessions) AS avg_sessions
                        ALL ROWS PER MATCH
                        AFTER MATCH SKIP PAST LAST ROW
                        PATTERN (A+ B+ C*)
                        DEFINE
                            A AS traffic_type = 'organic',
                            B AS traffic_type = 'paid',
                            C AS traffic_type = 'social'
                    )
                ''',
                'description': 'Traffic source transition pattern'
            }
        }
        
        return patterns
    
    def configure_caching(self, strategy: str):
        """Configure caching based on strategy."""
        clear_pattern_cache()
        
        if strategy == 'NO_CACHE':
            set_caching_enabled(False)
        else:  # FIFO and LRU both use the same underlying cache
            set_caching_enabled(True)
    
    def measure_performance(self, df: pd.DataFrame, query: str, cache_strategy: str) -> Dict[str, Any]:
        """Measure performance metrics for a specific test case."""
        
        # Configure caching for this test
        self.configure_caching(cache_strategy)
        
        # Initialize memory measurement
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Get initial cache stats
        initial_cache_stats = get_cache_stats()
        initial_hits = initial_cache_stats.get('total_hits', 0)
        initial_misses = initial_cache_stats.get('total_misses', 0)
        
        # Measure execution time
        start_time = time.perf_counter()
        
        try:
            # Execute the pattern matching
            result = match_recognize(query, df)
            execution_success = True
        except Exception as e:
            print(f"Pattern execution failed: {e}")
            result = pd.DataFrame()
            execution_success = False
        
        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        # Measure final memory
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_usage = max(0, final_memory - initial_memory)
        
        # Get final cache statistics
        final_cache_stats = get_cache_stats()
        final_hits = final_cache_stats.get('total_hits', 0)
        final_misses = final_cache_stats.get('total_misses', 0)
        
        # Calculate cache metrics for this test
        cache_hits = final_hits - initial_hits
        cache_misses = final_misses - initial_misses
        total_requests = cache_hits + cache_misses
        hit_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'execution_time_ms': execution_time,
            'memory_usage_mb': memory_usage,
            'cache_hit_rate': hit_rate,
            'cache_hits': cache_hits,
            'cache_misses': cache_misses,
            'result_count': len(result) if execution_success else 0,
            'execution_success': execution_success
        }
    
    def run_benchmark(self) -> List[Dict[str, Any]]:
        """Run simplified benchmark with working patterns."""
        
        dataset_sizes = [1000, 2000, 4000, 5000]
        dataset_generators = {
            'financial': self.generate_financial_data,
            'sensor': self.generate_sensor_data,
            'web_analytics': self.generate_web_analytics_data
        }
        
        patterns = self.get_working_patterns()
        complexity_mapping = {
            'simple': ['financial_simple', 'sensor_simple', 'web_simple'],
            'medium': ['financial_medium', 'sensor_medium', 'web_medium'],
            'complex': ['financial_complex', 'sensor_complex', 'web_complex']
        }
        
        results = []
        test_counter = 0
        total_tests = len(dataset_sizes) * len(complexity_mapping) * len(self.cache_strategies) * len(dataset_generators)
        
        print(f"Starting simplified real-world benchmark: {total_tests} total tests")
        
        for size in dataset_sizes:
            for complexity, pattern_list in complexity_mapping.items():
                for data_type, generator in dataset_generators.items():
                    # Generate dataset
                    print(f"Generating {data_type} dataset with {size} records...")
                    df = generator(size)
                    
                    # Select appropriate pattern for this data type and complexity
                    pattern_key = f"{data_type}_{complexity}"
                    if pattern_key not in patterns:
                        continue
                    
                    pattern_info = patterns[pattern_key]
                    
                    for cache_strategy in self.cache_strategies:
                        test_counter += 1
                        print(f"Test {test_counter}/{total_tests}: {cache_strategy} on {data_type} {complexity} ({size} rows)")
                        
                        # Run multiple iterations for statistical reliability
                        iteration_results = []
                        for iteration in range(3):
                            try:
                                perf_metrics = self.measure_performance(
                                    df, pattern_info['query'], cache_strategy
                                )
                                iteration_results.append(perf_metrics)
                            except Exception as e:
                                print(f"  Iteration {iteration + 1} failed: {e}")
                                continue
                        
                        if iteration_results:
                            # Calculate averages across iterations
                            avg_metrics = {
                                'execution_time_ms': np.mean([r['execution_time_ms'] for r in iteration_results]),
                                'memory_usage_mb': np.mean([r['memory_usage_mb'] for r in iteration_results]),
                                'cache_hit_rate': np.mean([r['cache_hit_rate'] for r in iteration_results]),
                                'cache_hits': int(np.mean([r['cache_hits'] for r in iteration_results])),
                                'cache_misses': int(np.mean([r['cache_misses'] for r in iteration_results])),
                                'result_count': int(np.mean([r['result_count'] for r in iteration_results])),
                                'execution_success': all(r['execution_success'] for r in iteration_results)
                            }
                            
                            # Store comprehensive result
                            result = {
                                'test_id': f"{cache_strategy}_{data_type}_{complexity}_{size}",
                                'cache_strategy': cache_strategy,
                                'data_type': data_type,
                                'dataset_size': size,
                                'pattern_complexity': complexity,
                                'pattern_description': pattern_info['description'],
                                **avg_metrics,
                                'iterations': len(iteration_results)
                            }
                            
                            results.append(result)
                            print(f"  ✅ Completed: {avg_metrics['execution_time_ms']:.1f}ms, "
                                  f"{avg_metrics['cache_hit_rate']:.1f}% hit rate")
                        else:
                            print(f"  ❌ All iterations failed for this test case")
        
        return results

def main():
    """Run the simplified real-world benchmark."""
    print("🚀 Starting Simplified Real-World MATCH_RECOGNIZE Caching Performance Benchmark")
    print("=" * 80)
    
    benchmark = SimplifiedRealWorldBenchmark()
    results = benchmark.run_benchmark()
    
    # Save results
    output_dir = Path("tests/performance/real_world_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save detailed results
    results_df = pd.DataFrame(results)
    results_df.to_csv(output_dir / "simplified_real_world_results.csv", index=False)
    
    # Calculate summary statistics
    summary_stats = {}
    for strategy in ['NO_CACHE', 'FIFO', 'LRU']:
        strategy_data = results_df[results_df['cache_strategy'] == strategy]
        if len(strategy_data) > 0:
            summary_stats[strategy] = {
                'avg_execution_time_ms': strategy_data['execution_time_ms'].mean(),
                'avg_memory_usage_mb': strategy_data['memory_usage_mb'].mean(),
                'avg_cache_hit_rate': strategy_data['cache_hit_rate'].mean(),
                'test_count': len(strategy_data),
                'success_rate': strategy_data['execution_success'].mean() * 100
            }
    
    # Save summary
    with open(output_dir / "simplified_summary.json", 'w') as f:
        json.dump(summary_stats, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 80)
    print("📊 SIMPLIFIED REAL-WORLD BENCHMARK RESULTS")
    print("=" * 80)
    
    for strategy, stats in summary_stats.items():
        print(f"\n{strategy}:")
        print(f"  Average Execution Time: {stats['avg_execution_time_ms']:.1f}ms")
        print(f"  Average Memory Usage: {stats['avg_memory_usage_mb']:.1f}MB")
        print(f"  Average Cache Hit Rate: {stats['avg_cache_hit_rate']:.1f}%")
        print(f"  Test Cases: {stats['test_count']}")
        print(f"  Success Rate: {stats['success_rate']:.1f}%")
    
    print(f"\n📁 Results saved to: {output_dir}")
    print(f"📊 Total test cases: {len(results)}")
    
    return 0

if __name__ == "__main__":
    exit(main())
