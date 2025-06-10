#!/usr/bin/env python3
"""
Enhanced Performance Comparison Benchmark for Row Match Recognize Cache System
"""

import sys
import os
import time
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for headless execution
import matplotlib.pyplot as plt
import seaborn as sns
import gc
import psutil
import random
from tabulate import tabulate
from typing import List, Dict, Any, Tuple, Optional
import threading
from collections import OrderedDict, defaultdict
import concurrent.futures
import json

# Add project root to path
sys.path.append('/home/monierashraf/Desktop/llm/Row_match_recognize')

# Import project modules
try:
    from src.executor.match_recognize import match_recognize
    from src.utils.pattern_cache import (
        get_cache_key, get_cached_pattern, cache_pattern, 
        clear_pattern_cache, resize_cache, get_cache_stats,
        set_caching_enabled, is_caching_enabled
    )
    from src.config.production_config import MatchRecognizeConfig, TESTING_CONFIG, PRODUCTION_CONFIG
    from src.monitoring.cache_monitor import start_cache_monitoring, stop_cache_monitoring
    print("✅ All project modules imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Set up visualization defaults
plt.style.use('default')
sns.set_palette("deep")
sns.set_context("notebook", font_scale=1.2)

def get_memory_usage():
    """Return the current memory usage in MB."""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    return memory_info.rss / (1024 * 1024)  # Convert to MB

def generate_test_data(rows=1000, pattern_complexity="medium"):
    """Generate test dataframe with controlled characteristics."""
    # Base data
    data = {
        'id': range(1, rows + 1),
        'timestamp': pd.date_range(start='2023-01-01', periods=rows, freq='1H'),
        'value': np.random.normal(100, 20, rows),
        'category': np.random.choice(['A', 'B', 'C', 'D'], rows),
        'status': np.random.choice(['active', 'inactive', 'pending'], rows),
    }
    
    # Add more columns based on complexity
    if pattern_complexity in ("medium", "complex"):
        data['secondary_value'] = np.random.normal(50, 10, rows)
        data['trend'] = np.sin(np.linspace(0, 10, rows)) * 20 + np.random.normal(0, 5, rows)
        
    if pattern_complexity == "complex":
        data['tertiary_value'] = np.random.gamma(5, 2, rows)
        data['priority'] = np.random.choice(['low', 'medium', 'high', 'critical'], rows)
        data['region'] = np.random.choice(['north', 'south', 'east', 'west', 'central'], rows)
        
    # Create predictable patterns in the data
    for i in range(1, rows):
        if pattern_complexity == "simple":
            if i % 10 < 5:  # Rising pattern every 10 rows
                data['value'][i] = data['value'][i-1] + np.random.uniform(1, 5)
        elif pattern_complexity == "medium":
            if i % 15 < 5:  # Rising pattern
                data['value'][i] = data['value'][i-1] + np.random.uniform(1, 5)
            elif i % 15 >= 10:  # Falling pattern
                data['value'][i] = data['value'][i-1] - np.random.uniform(1, 5)
        elif pattern_complexity == "complex":
            if i % 20 < 5:  # Complex multi-column patterns
                data['value'][i] = data['value'][i-1] + np.random.uniform(2, 7)
                if 'secondary_value' in data:
                    data['secondary_value'][i] = data['secondary_value'][i-1] - np.random.uniform(1, 3)
    
    return pd.DataFrame(data)

def generate_query(complexity="medium", pattern_type="basic", partition_by=None):
    """Generate a query with the specified complexity."""
    partition_clause = f"PARTITION BY {partition_by}" if partition_by else ""
    
    # Simple query for demonstration
    if complexity == "simple":
        return f"""
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            {partition_clause}
            ORDER BY id
            MEASURES
                FIRST(A.value) AS start_value,
                LAST(B.value) AS end_value,
                COUNT(*) AS pattern_length
            PATTERN (A+ B+)
            DEFINE
                A AS value > LAG(value),
                B AS value < LAG(value)
        )
        """
    elif complexity == "medium":
        return f"""
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            {partition_clause}
            ORDER BY id
            MEASURES
                FIRST(A.value) AS start_value,
                LAST(C.value) AS end_value,
                AVG(A.value) AS avg_a_value,
                COUNT(*) AS pattern_length
            PATTERN (A+ B+ A+)
            DEFINE
                A AS value > LAG(value),
                B AS value < LAG(value) AND secondary_value > 45
        )
        """
    else:  # complex
        return f"""
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            {partition_clause}
            ORDER BY id
            MEASURES
                FIRST(A.value) AS start_value,
                LAST(C.value) AS end_value,
                AVG(A.value) AS avg_a_value,
                MAX(B.secondary_value) AS max_b_secondary,
                COUNT(*) AS pattern_length
            PATTERN (A+ B+ C+)
            DEFINE
                A AS value > LAG(value),
                B AS value < LAG(value) AND secondary_value > tertiary_value,
                C AS value BETWEEN LAG(value) * 0.9 AND LAG(value) * 1.1
        )
        """

def configure_caching(cache_mode):
    """Configure caching based on the specified mode."""
    if cache_mode == "none":
        set_caching_enabled(False)
        return None
    elif cache_mode == "fifo":
        set_caching_enabled(True)
        # Configure for FIFO behavior (simple cache without LRU)
        return None
    elif cache_mode == "lru":
        set_caching_enabled(True)
        # Configure production LRU cache
        config = PRODUCTION_CONFIG
        config.performance.enable_caching = True
        config.performance.cache_size_limit = 1000
        return start_cache_monitoring()
    
    return None

def benchmark_single_query(query, df, cache_mode, repetitions=5):
    """Benchmark a single query with the specified cache mode."""
    # Configure caching
    monitor = configure_caching(cache_mode)
    
    # Clear any existing cache
    clear_pattern_cache()
    gc.collect()
    
    # Initial measurements
    initial_memory = get_memory_usage()
    execution_times = []
    memory_usages = [initial_memory]
    cache_hits = []
    cache_misses = []
    
    # Warm up run (not counted in results)
    try:
        _ = match_recognize(query, df)
    except Exception as e:
        print(f"Warning: Warm-up run failed: {e}")
    
    # Timed runs
    total_time = 0
    for i in range(repetitions):
        start_time = time.time()
        
        try:
            result = match_recognize(query, df)
            execution_time = time.time() - start_time
            execution_times.append(execution_time)
            total_time += execution_time
            
            # Memory measurement
            current_memory = get_memory_usage()
            memory_usages.append(current_memory)
            
            # Cache statistics
            if cache_mode != "none":
                current_stats = get_cache_stats()
                if i == 0:
                    initial_hits = current_stats.get('hits', 0)
                    initial_misses = current_stats.get('misses', 0)
                    cache_hits.append(0)
                    cache_misses.append(1)
                else:
                    cache_hits.append(current_stats.get('hits', 0) - initial_hits)
                    cache_misses.append(current_stats.get('misses', 0) - initial_misses)
            else:
                cache_hits.append(0)
                cache_misses.append(1 if i == 0 else 0)
            
        except Exception as e:
            print(f"Error in repetition {i}: {e}")
            execution_times.append(float('inf'))
            memory_usages.append(get_memory_usage())
            cache_hits.append(0)
            cache_misses.append(1)
    
    # Calculate metrics
    valid_times = [t for t in execution_times if t != float('inf')]
    if not valid_times:
        print(f"Warning: No valid execution times for {cache_mode}")
        return None
    
    avg_time = sum(valid_times) / len(valid_times)
    first_run_time = valid_times[0] if valid_times else 0
    subsequent_avg_time = sum(valid_times[1:]) / (len(valid_times) - 1) if len(valid_times) > 1 else 0
    max_memory = max(memory_usages)
    memory_increase = max_memory - initial_memory
    
    # Cache efficiency
    if cache_mode != "none":
        total_cache_hits = sum(cache_hits)
        total_cache_misses = sum(cache_misses)
        total_cache_lookups = total_cache_hits + total_cache_misses
        cache_hit_rate = (total_cache_hits / total_cache_lookups) * 100 if total_cache_lookups > 0 else 0
    else:
        total_cache_hits = 0
        total_cache_misses = repetitions
        cache_hit_rate = 0
    
    # Clean up
    if monitor:
        stop_cache_monitoring()
    
    return {
        "cache_mode": cache_mode,
        "avg_execution_time": avg_time,
        "first_run_time": first_run_time,
        "subsequent_avg_time": subsequent_avg_time,
        "execution_times": execution_times,
        "initial_memory": initial_memory,
        "max_memory": max_memory,
        "memory_increase": memory_increase,
        "memory_usages": memory_usages,
        "cache_hits": total_cache_hits,
        "cache_misses": total_cache_misses,
        "cache_hit_rate": cache_hit_rate,
        "result_size": len(result) if 'result' in locals() and result is not None else 0
    }

def run_enhanced_comparison_benchmark():
    """Run comprehensive benchmark comparing all three caching strategies."""
    print("=" * 80)
    print("STARTING ENHANCED PERFORMANCE COMPARISON BENCHMARK")
    print("=" * 80)
    print("Testing LRU vs FIFO vs No-Caching across multiple scenarios\n")
    
    # Test scenarios
    test_scenarios = [
        {"complexity": "simple", "pattern_type": "basic", "data_size": 1000, "description": "Basic patterns, small dataset"},
        {"complexity": "medium", "pattern_type": "basic", "data_size": 2000, "description": "Medium complexity patterns"},
        {"complexity": "medium", "pattern_type": "basic", "data_size": 3000, "description": "Medium complexity, larger dataset"},
        {"complexity": "complex", "pattern_type": "basic", "data_size": 2000, "description": "Complex patterns"},
        {"complexity": "complex", "pattern_type": "basic", "data_size": 4000, "description": "Complex patterns, large dataset"}
    ]
    
    cache_modes = ["none", "fifo", "lru"]
    repetitions = 5
    
    all_results = []
    scenario_summaries = []
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n{'=' * 60}")
        print(f"SCENARIO {i}: {scenario['description']}")
        print(f"Complexity: {scenario['complexity']}, Data Size: {scenario['data_size']}")
        print(f"{'=' * 60}")
        
        # Generate test data
        df = generate_test_data(rows=scenario['data_size'], pattern_complexity=scenario['complexity'])
        query = generate_query(complexity=scenario['complexity'], 
                             pattern_type=scenario['pattern_type'], 
                             partition_by="category")
        
        scenario_results = []
        
        for cache_mode in cache_modes:
            print(f"\n  Testing {cache_mode.upper()} caching...")
            
            # Run benchmark
            result = benchmark_single_query(query, df, cache_mode, repetitions)
            
            if result:
                # Add scenario metadata
                result.update({
                    "scenario_id": i,
                    "scenario_description": scenario['description'],
                    "complexity": scenario['complexity'],
                    "pattern_type": scenario['pattern_type'],
                    "data_size": scenario['data_size']
                })
                
                scenario_results.append(result)
                all_results.append(result)
                
                # Print immediate results
                print(f"    Avg execution time: {result['avg_execution_time']:.4f}s")
                print(f"    Cache hit rate: {result['cache_hit_rate']:.1f}%")
                print(f"    Memory increase: {result['memory_increase']:.2f}MB")
            else:
                print(f"    ❌ Failed to run {cache_mode} benchmark")
            
            # Clean up between tests
            clear_pattern_cache()
            gc.collect()
            time.sleep(1)
        
        # Calculate scenario summary
        if len(scenario_results) >= 3:  # We have results for all cache modes
            scenario_summary = calculate_scenario_summary(scenario_results, scenario)
            scenario_summaries.append(scenario_summary)
            
            print(f"\n  Scenario {i} Summary:")
            print(f"    LRU vs No-Cache: {scenario_summary['lru_vs_none_improvement']:+.1f}% performance change")
            print(f"    LRU vs FIFO: {scenario_summary['lru_vs_fifo_improvement']:+.1f}% performance change")
            print(f"    Best cache hit rate: {scenario_summary['best_hit_rate']:.1f}% ({scenario_summary['best_cache_mode']})")
    
    return pd.DataFrame(all_results), scenario_summaries

def calculate_scenario_summary(scenario_results, scenario_config):
    """Calculate summary statistics for a single test scenario."""
    # Extract results by cache mode
    results_by_mode = {r['cache_mode']: r for r in scenario_results}
    
    if 'lru' not in results_by_mode or 'fifo' not in results_by_mode or 'none' not in results_by_mode:
        print("Warning: Missing cache mode results")
        return {}
    
    lru_time = results_by_mode['lru']['avg_execution_time']
    fifo_time = results_by_mode['fifo']['avg_execution_time'] 
    none_time = results_by_mode['none']['avg_execution_time']
    
    lru_hit_rate = results_by_mode['lru']['cache_hit_rate']
    fifo_hit_rate = results_by_mode['fifo']['cache_hit_rate']
    
    # Calculate improvements
    lru_vs_none = ((none_time - lru_time) / none_time) * 100 if none_time > 0 else 0
    lru_vs_fifo = ((fifo_time - lru_time) / fifo_time) * 100 if fifo_time > 0 else 0
    
    # Determine best performers
    cache_times = [("lru", lru_time), ("fifo", fifo_time), ("none", none_time)]
    best_mode = min(cache_times, key=lambda x: x[1])[0]
    best_time = min(cache_times, key=lambda x: x[1])[1]
    
    cache_hit_rates = [("lru", lru_hit_rate), ("fifo", fifo_hit_rate)]
    best_cache_hit = max(cache_hit_rates, key=lambda x: x[1])
    
    return {
        'scenario_id': scenario_config.get('scenario_id', 0),
        'scenario_description': scenario_config['description'],
        'lru_vs_none_improvement': lru_vs_none,
        'lru_vs_fifo_improvement': lru_vs_fifo,
        'best_mode': best_mode,
        'best_time': best_time,
        'best_cache_mode': best_cache_hit[0],
        'best_hit_rate': best_cache_hit[1],
        'lru_time': lru_time,
        'fifo_time': fifo_time,
        'none_time': none_time,
        'lru_hit_rate': lru_hit_rate,
        'fifo_hit_rate': fifo_hit_rate
    }

def main():
    """Main execution function."""
    print("Enhanced Performance Comparison Benchmark")
    print("Row Match Recognize Cache System Analysis")
    print("=" * 50)
    
    try:
        # Run the enhanced benchmark
        enhanced_results_df, scenario_summaries = run_enhanced_comparison_benchmark()
        
        print("\n" + "=" * 80)
        print("BENCHMARK RESULTS SUMMARY")
        print("=" * 80)
        
        # Display summary
        for i, summary in enumerate(scenario_summaries, 1):
            print(f"\nScenario {i}: {summary['scenario_description']}")
            print(f"  • LRU vs No-cache: {summary['lru_vs_none_improvement']:+.1f}%")
            print(f"  • LRU vs FIFO: {summary['lru_vs_fifo_improvement']:+.1f}%")
            print(f"  • Best performance: {summary['best_mode']} ({summary['best_time']:.4f}s)")
        
        # Export results
        enhanced_results_df.to_csv('enhanced_benchmark_results.csv', index=False)
        
        with open('scenario_summaries.json', 'w') as f:
            json.dump(scenario_summaries, f, indent=2, default=str)
        
        print("\n✅ Results exported to:")
        print("   • enhanced_benchmark_results.csv")
        print("   • scenario_summaries.json")
        
        # Calculate overall improvements
        lru_times = enhanced_results_df[enhanced_results_df['cache_mode'] == 'lru']['avg_execution_time'].values
        fifo_times = enhanced_results_df[enhanced_results_df['cache_mode'] == 'fifo']['avg_execution_time'].values
        none_times = enhanced_results_df[enhanced_results_df['cache_mode'] == 'none']['avg_execution_time'].values
        
        if len(lru_times) > 0 and len(none_times) > 0:
            overall_lru_vs_none = ((np.mean(none_times) - np.mean(lru_times)) / np.mean(none_times)) * 100
            print(f"\n🚀 OVERALL PERFORMANCE:")
            print(f"   LRU vs No-cache: {overall_lru_vs_none:+.1f}% improvement")
        
        if len(lru_times) > 0 and len(fifo_times) > 0:
            overall_lru_vs_fifo = ((np.mean(fifo_times) - np.mean(lru_times)) / np.mean(fifo_times)) * 100
            print(f"   LRU vs FIFO: {overall_lru_vs_fifo:+.1f}% improvement")
            
        print(f"\n🎉 ANALYSIS COMPLETE!")
        
    except Exception as e:
        print(f"❌ Error running benchmark: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
