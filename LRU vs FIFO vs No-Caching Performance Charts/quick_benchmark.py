#!/usr/bin/env python3
"""
Quick pattern cache benchmark script.

This script runs a minimal benchmark to compare the performance of different
caching strategies in the Row Match Recognize system.
"""

import sys
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tabulate import tabulate

# Add project root to path
sys.path.append('/home/monierashraf/Desktop/llm/Row_match_recognize')

# Import project modules
from src.executor.match_recognize import match_recognize
from src.utils.pattern_cache import (
    clear_pattern_cache, get_cache_stats,
    set_caching_enabled, is_caching_enabled
)
from src.config.production_config import TESTING_CONFIG, PRODUCTION_CONFIG
from src.monitoring.cache_monitor import start_cache_monitoring, stop_cache_monitoring

# Generate simple test data
def generate_test_data(rows=1000):
    """Generate test data for pattern matching."""
    data = {
        'id': range(1, rows + 1),
        'value': np.random.normal(100, 20, rows),
        'category': np.random.choice(['A', 'B', 'C'], rows)
    }
    
    # Create patterns in the data
    for i in range(1, rows):
        if i % 10 < 5:  # Create rising pattern every 10 rows
            data['value'][i] = data['value'][i-1] + np.random.uniform(1, 5)
    
    return pd.DataFrame(data)

# Simple test query
def get_test_query():
    """Generate a test query for benchmarking."""
    return """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        PARTITION BY category
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

def configure_caching(mode):
    """Configure the caching system based on mode."""
    # Clear any existing cache
    clear_pattern_cache()
    stop_cache_monitoring()
    
    if mode == "none":
        set_caching_enabled(False)
        return None
    
    # Enable caching
    set_caching_enabled(True)
    
    if mode == "lru":
        # Use production config with LRU caching
        config = PRODUCTION_CONFIG
        config.performance.enable_caching = True
        monitor = start_cache_monitoring(config)
        return monitor
    
    elif mode == "fifo":
        # Simulate old FIFO caching
        config = TESTING_CONFIG
        config.performance.enable_caching = True
        return None

def run_quick_benchmark():
    """Run a quick benchmark of different caching strategies."""
    # Generate test data
    df = generate_test_data()
    query = get_test_query()
    
    # Parameters
    cache_modes = ["none", "fifo", "lru"]
    repetitions = 5
    
    results = []
    
    for cache_mode in cache_modes:
        print(f"Testing {cache_mode} cache...")
        
        # Configure caching
        monitor = configure_caching(cache_mode)
        
        # Run query multiple times
        execution_times = []
        
        for i in range(repetitions):
            start_time = time.time()
            result = match_recognize(query, df)
            query_time = time.time() - start_time
            execution_times.append(query_time)
        
        # Calculate metrics
        avg_time = sum(execution_times) / repetitions
        first_run = execution_times[0]
        subsequent_avg = sum(execution_times[1:]) / (repetitions - 1) if repetitions > 1 else 0
        
        # Get cache stats if available
        if cache_mode != "none":
            stats = get_cache_stats()
            hit_rate = stats.get('cache_efficiency', 0)
        else:
            hit_rate = 0
        
        # Store results
        results.append({
            "cache_mode": cache_mode,
            "avg_execution_time": avg_time,
            "first_run_time": first_run,
            "subsequent_avg_time": subsequent_avg,
            "cache_hit_rate": hit_rate
        })
        
        # Clean up
        if monitor:
            stop_cache_monitoring()
        clear_pattern_cache()
    
    return pd.DataFrame(results)

def display_results(results):
    """Display and visualize benchmark results."""
    # Print table
    print("\nBenchmark Results:\n")
    print(tabulate(results, headers="keys", tablefmt="grid", showindex=False, floatfmt=".4f"))
    
    # Calculate improvements
    if len(results) >= 3:
        lru_time = results[results["cache_mode"] == "lru"]["avg_execution_time"].values[0]
        fifo_time = results[results["cache_mode"] == "fifo"]["avg_execution_time"].values[0]
        no_cache_time = results[results["cache_mode"] == "none"]["avg_execution_time"].values[0]
        
        lru_vs_fifo = ((fifo_time - lru_time) / fifo_time) * 100
        lru_vs_none = ((no_cache_time - lru_time) / no_cache_time) * 100
        
        print(f"\nPerformance Improvements:")
        print(f"- LRU vs FIFO: {lru_vs_fifo:.2f}% faster")
        print(f"- LRU vs No Cache: {lru_vs_none:.2f}% faster")
    
    # Create visualization
    plt.figure(figsize=(10, 6))
    
    # First vs subsequent runs
    first_subsequent = pd.melt(
        results,
        id_vars=["cache_mode"],
        value_vars=["first_run_time", "subsequent_avg_time"],
        var_name="run_type",
        value_name="execution_time"
    )
    
    ax = sns.barplot(
        data=first_subsequent, 
        x="cache_mode", 
        y="execution_time", 
        hue="run_type"
    )
    
    plt.title("Pattern Caching Performance Comparison", fontsize=14)
    plt.ylabel("Execution Time (seconds)", fontsize=12)
    plt.xlabel("Cache Mode", fontsize=12)
    plt.legend(title="Run Type")
    plt.tight_layout()
    
    # Save the plot
    plt.savefig("quick_benchmark_results.png")
    plt.close()
    
    print("\nBenchmark visualization saved as 'quick_benchmark_results.png'")

if __name__ == "__main__":
    print("Running quick pattern caching benchmark...")
    results = run_quick_benchmark()
    display_results(results)
