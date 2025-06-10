#!/usr/bin/env python3
"""
Performance benchmark script for Row Match Recognize pattern caching.

This script measures the performance of different caching strategies:
1. LRU (Least Recently Used) - New production implementation
2. FIFO (First In, First Out) - Original implementation
3. No caching - For baseline comparison

Run this script to generate performance data and visualizations.
"""

import os
import sys
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import gc
import random
from tabulate import tabulate
import argparse
from pathlib import Path
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import project modules
from src.executor.match_recognize import match_recognize
from src.utils.pattern_cache import (
    get_cache_key, get_cached_pattern, cache_pattern, 
    clear_pattern_cache, resize_cache, get_cache_stats,
    set_caching_enabled, is_caching_enabled
)
from src.config.production_config import MatchRecognizeConfig, TESTING_CONFIG, PRODUCTION_CONFIG
from src.monitoring.cache_monitor import start_cache_monitoring, stop_cache_monitoring

# Set up visualization
plt.style.use('ggplot')
sns.set_context("talk")
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['figure.dpi'] = 120

# Directory for saving results
RESULTS_DIR = Path(__file__).parent / "benchmark_results"
RESULTS_DIR.mkdir(exist_ok=True)

# Generate test data 
def generate_test_data(rows=1000, pattern_complexity="medium"):
    """Generate test data with controlled characteristics for benchmarking."""
    # Base data
    data = {
        'id': range(1, rows + 1),
        'timestamp': pd.date_range(start='2023-01-01', periods=rows, freq='1H'),
        'value': np.random.normal(100, 20, rows),
        'category': np.random.choice(['A', 'B', 'C', 'D'], rows),
    }
    
    # Add complexity
    if pattern_complexity in ("medium", "complex"):
        data['secondary_value'] = np.random.normal(50, 10, rows)
        
    if pattern_complexity == "complex":
        data['tertiary_value'] = np.random.gamma(5, 2, rows)
        
    # Create patterns in the data
    if pattern_complexity == "simple":
        for i in range(1, rows):
            if i % 10 < 5:
                data['value'][i] = data['value'][i-1] + np.random.uniform(1, 5)
    
    elif pattern_complexity == "medium":
        for i in range(2, rows):
            if i % 15 < 5:
                data['value'][i] = data['value'][i-1] + np.random.uniform(1, 5)
            elif i % 15 >= 10:
                data['value'][i] = data['value'][i-1] - np.random.uniform(1, 5)
    
    elif pattern_complexity == "complex":
        for i in range(2, rows):
            if i % 20 < 5:
                data['value'][i] = data['value'][i-1] + np.random.uniform(2, 7)
                if 'secondary_value' in data:
                    data['secondary_value'][i] = data['secondary_value'][i-1] - np.random.uniform(1, 3)
            elif i % 20 >= 15:
                data['value'][i] = data['value'][i-1] - np.random.uniform(2, 7)
                if 'secondary_value' in data:
                    data['secondary_value'][i] = data['secondary_value'][i-1] + np.random.uniform(1, 3)
    
    return pd.DataFrame(data)

# Generate test queries
def generate_query(complexity="medium", pattern_type="basic"):
    """Generate a test query with specific complexity and pattern type."""
    # Basic query structure
    partition_clause = "PARTITION BY category"
    
    # Pattern based on complexity and type
    if pattern_type == "basic":
        if complexity == "simple":
            pattern = "PATTERN (A+ B+)"
            define = """
                DEFINE
                    A AS value > LAG(value),
                    B AS value < LAG(value)
            """
        elif complexity == "medium":
            pattern = "PATTERN (A+ B+ A+)"
            define = """
                DEFINE
                    A AS value > LAG(value),
                    B AS value < LAG(value) AND secondary_value > 45
            """
        else:  # complex
            pattern = "PATTERN (A+ B+ C+)"
            define = """
                DEFINE
                    A AS value > LAG(value),
                    B AS value < LAG(value) AND secondary_value > tertiary_value,
                    C AS value BETWEEN LAG(value) * 0.9 AND LAG(value) * 1.1
            """
    
    elif pattern_type == "permute":
        if complexity == "simple":
            pattern = "PATTERN (PERMUTE(A, B))"
            define = """
                DEFINE
                    A AS value > 100,
                    B AS value <= 100
            """
        elif complexity == "medium":
            pattern = "PATTERN (PERMUTE(A, B, C))"
            define = """
                DEFINE
                    A AS value > 100,
                    B AS value BETWEEN 80 AND 100,
                    C AS value < 80
            """
        else:  # complex
            pattern = "PATTERN (X PERMUTE(A, B, C, D))"
            define = """
                DEFINE
                    X AS value > 120,
                    A AS value BETWEEN 100 AND 120,
                    B AS value BETWEEN 80 AND 100,
                    C AS value BETWEEN 60 AND 80,
                    D AS value < 60
            """
    
    elif pattern_type == "exclusion":
        if complexity == "simple":
            pattern = "PATTERN (A {-B-} C)"
            define = """
                DEFINE
                    A AS value > 100,
                    B AS value BETWEEN 80 AND 100,
                    C AS value < 80
            """
        else:  # medium/complex
            pattern = "PATTERN (A {-B-} C {-D-} E)"
            define = """
                DEFINE
                    A AS value > 100,
                    B AS value BETWEEN 90 AND 100,
                    C AS value BETWEEN 80 AND 90,
                    D AS value BETWEEN 70 AND 80,
                    E AS value < 70
            """
    
    # Measures based on complexity
    if complexity == "simple":
        measures = """
            MEASURES
                FIRST(A.value) AS start_value,
                LAST(B.value) AS end_value,
                COUNT(*) AS pattern_length
        """
    else:  # medium/complex
        measures = """
            MEASURES
                FIRST(A.value) AS start_value,
                LAST(B.value) AS end_value,
                AVG(A.value) AS avg_a_value,
                COUNT(*) AS pattern_length
        """
    
    # Assemble the query
    query = f"""
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        {partition_clause}
        ORDER BY id
        {measures}
        {pattern}
        {define}
    )
    """
    
    return query

def configure_caching(mode):
    """Configure the caching system based on mode."""
    # Clear any existing cache
    clear_pattern_cache()
    stop_cache_monitoring()
    gc.collect()
    
    if mode == "none":
        set_caching_enabled(False)
        return None
    
    # Enable caching
    set_caching_enabled(True)
    
    if mode == "lru":
        # Use production config with LRU caching
        config = PRODUCTION_CONFIG
        config.performance.enable_caching = True
        config.performance.cache_size_limit = 1000
        monitor = start_cache_monitoring(config)
        return monitor
    
    elif mode == "fifo":
        # Simulate old FIFO caching
        config = TESTING_CONFIG
        config.performance.enable_caching = True
        config.performance.cache_size_limit = 1000
        return None

def run_benchmark(query, df, cache_mode, repetitions=5):
    """Run benchmark for a single query with specified caching mode."""
    # Configure caching
    monitor = configure_caching(cache_mode)
    
    # Prepare metrics
    execution_times = []
    cache_hits = []
    cache_misses = []
    
    # Get initial cache stats
    if cache_mode != "none":
        initial_stats = get_cache_stats()
        initial_hits = initial_stats.get('hits', 0)
        initial_misses = initial_stats.get('misses', 0)
    else:
        initial_hits = 0
        initial_misses = 0
    
    # Run the query multiple times
    for i in range(repetitions):
        start_time = time.time()
        result = match_recognize(query, df)
        query_time = time.time() - start_time
        
        execution_times.append(query_time)
        
        if cache_mode != "none":
            current_stats = get_cache_stats()
            cache_hits.append(current_stats.get('hits', 0) - initial_hits)
            cache_misses.append(current_stats.get('misses', 0) - initial_misses)
            initial_hits = current_stats.get('hits', 0)
            initial_misses = current_stats.get('misses', 0)
        else:
            cache_hits.append(0)
            cache_misses.append(1 if i == 0 else 0)
    
    # Calculate results
    avg_time = sum(execution_times) / repetitions
    first_run_time = execution_times[0]
    subsequent_avg_time = sum(execution_times[1:]) / (repetitions - 1) if repetitions > 1 else 0
    
    # Calculate cache efficiency
    if cache_mode != "none":
        total_cache_hits = sum(cache_hits)
        total_cache_misses = sum(cache_misses)
        total_cache_lookups = total_cache_hits + total_cache_misses
        cache_hit_rate = (total_cache_hits / total_cache_lookups) * 100 if total_cache_lookups > 0 else 0
        
        # Get final cache stats
        final_stats = get_cache_stats()
        cache_size = final_stats.get('size', 0)
        memory_used = final_stats.get('memory_used_mb', 0)
    else:
        total_cache_hits = 0
        total_cache_misses = repetitions
        cache_hit_rate = 0
        cache_size = 0
        memory_used = 0
    
    # Clean up
    if monitor:
        stop_cache_monitoring()
    
    return {
        "cache_mode": cache_mode,
        "avg_execution_time": avg_time,
        "first_run_time": first_run_time,
        "subsequent_avg_time": subsequent_avg_time,
        "execution_times": execution_times,
        "cache_hits": total_cache_hits,
        "cache_misses": total_cache_misses,
        "cache_hit_rate": cache_hit_rate,
        "cache_size": cache_size,
        "memory_used_mb": memory_used
    }

def run_all_benchmarks(complexities=["simple", "medium", "complex"], 
                      pattern_types=["basic", "permute", "exclusion"],
                      cache_modes=["none", "fifo", "lru"],
                      data_sizes=[1000, 5000],
                      repetitions=5):
    """Run comprehensive benchmarks."""
    results = []
    
    for data_size in data_sizes:
        for complexity in complexities:
            df = generate_test_data(rows=data_size, pattern_complexity=complexity)
            
            for pattern_type in pattern_types:
                # Skip combinations that might not be compatible
                if complexity == "complex" and pattern_type == "exclusion":
                    continue
                    
                query = generate_query(complexity=complexity, pattern_type=pattern_type)
                
                print(f"Benchmarking: size={data_size}, complexity={complexity}, pattern={pattern_type}")
                
                for cache_mode in cache_modes:
                    result = run_benchmark(query, df, cache_mode, repetitions)
                    
                    # Add metadata
                    result["data_size"] = data_size
                    result["complexity"] = complexity
                    result["pattern_type"] = pattern_type
                    
                    results.append(result)
                    
                    # Clean up
                    clear_pattern_cache()
                    gc.collect()
                    time.sleep(1)
    
    return pd.DataFrame(results)

def create_visualizations(results_df, output_dir):
    """Create and save visualizations of benchmark results."""
    # Ensure output directory exists
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # 1. Average execution time by complexity and cache mode
    plt.figure(figsize=(14, 8))
    ax = sns.barplot(
        data=results_df, 
        x="complexity", 
        y="avg_execution_time", 
        hue="cache_mode"
    )
    plt.title("Average Execution Time by Complexity", fontsize=16)
    plt.ylabel("Execution Time (seconds)", fontsize=14)
    plt.xlabel("Complexity", fontsize=14)
    plt.legend(title="Cache Mode")
    plt.tight_layout()
    plt.savefig(output_dir / "execution_time_by_complexity.png")
    plt.close()
    
    # 2. Cache hit rate by pattern type
    cache_data = results_df[results_df["cache_mode"] != "none"].copy()
    plt.figure(figsize=(14, 8))
    ax = sns.barplot(
        data=cache_data, 
        x="pattern_type", 
        y="cache_hit_rate", 
        hue="cache_mode"
    )
    plt.title("Cache Hit Rate by Pattern Type", fontsize=16)
    plt.ylabel("Cache Hit Rate (%)", fontsize=14)
    plt.xlabel("Pattern Type", fontsize=14)
    plt.legend(title="Cache Mode")
    plt.tight_layout()
    plt.savefig(output_dir / "cache_hit_rate.png")
    plt.close()
    
    # 3. First run vs subsequent runs
    first_vs_subsequent = pd.melt(
        results_df,
        id_vars=["cache_mode", "complexity", "pattern_type"],
        value_vars=["first_run_time", "subsequent_avg_time"],
        var_name="run_type",
        value_name="execution_time"
    )
    
    g = sns.catplot(
        data=first_vs_subsequent,
        kind="bar",
        x="cache_mode",
        y="execution_time",
        hue="run_type",
        col="complexity",
        height=6,
        aspect=0.8,
        sharey=True
    )
    g.fig.suptitle("First Run vs Subsequent Runs", fontsize=16)
    g.fig.subplots_adjust(top=0.85)
    plt.savefig(output_dir / "first_vs_subsequent.png")
    plt.close()
    
    # 4. LRU vs FIFO improvement
    # Filter data for LRU and FIFO only
    cache_comparison = results_df[results_df["cache_mode"].isin(["lru", "fifo"])].copy()
    
    # Merge the data
    lru_data = cache_comparison[cache_comparison["cache_mode"] == "lru"]
    fifo_data = cache_comparison[cache_comparison["cache_mode"] == "fifo"]
    
    lru_fifo_comparison = pd.merge(
        lru_data,
        fifo_data,
        on=["complexity", "pattern_type", "data_size"],
        suffixes=("_lru", "_fifo")
    )
    
    # Calculate percentage improvements
    lru_fifo_comparison["time_improvement"] = ((lru_fifo_comparison["avg_execution_time_fifo"] - 
                                             lru_fifo_comparison["avg_execution_time_lru"]) / 
                                            lru_fifo_comparison["avg_execution_time_fifo"]) * 100
    
    lru_fifo_comparison["hit_rate_improvement"] = (lru_fifo_comparison["cache_hit_rate_lru"] - 
                                                lru_fifo_comparison["cache_hit_rate_fifo"])
    
    plt.figure(figsize=(14, 8))
    ax = sns.barplot(
        data=lru_fifo_comparison, 
        x="pattern_type", 
        y="time_improvement", 
        hue="complexity"
    )
    plt.title("Execution Time Improvement: LRU vs FIFO (%)", fontsize=16)
    plt.ylabel("Time Improvement (%)", fontsize=14)
    plt.axhline(y=0, color='r', linestyle='-', alpha=0.3)
    plt.legend(title="Complexity")
    plt.tight_layout()
    plt.savefig(output_dir / "lru_vs_fifo_improvement.png")
    plt.close()
    
    # 5. Summary table as CSV
    summary = results_df.groupby(['cache_mode', 'complexity'])[
        'avg_execution_time', 'cache_hit_rate', 'memory_used_mb'
    ].mean().reset_index()
    
    summary.to_csv(output_dir / "performance_summary.csv", index=False)
    
    # 6. Create a summary JSON with key findings
    key_findings = {
        "lru_vs_no_cache_improvement": float(
            ((results_df[results_df["cache_mode"] == "none"]["avg_execution_time"].mean() - 
              results_df[results_df["cache_mode"] == "lru"]["avg_execution_time"].mean()) / 
             results_df[results_df["cache_mode"] == "none"]["avg_execution_time"].mean() * 100)
        ),
        "lru_vs_fifo_improvement": float(
            ((results_df[results_df["cache_mode"] == "fifo"]["avg_execution_time"].mean() - 
              results_df[results_df["cache_mode"] == "lru"]["avg_execution_time"].mean()) / 
             results_df[results_df["cache_mode"] == "fifo"]["avg_execution_time"].mean() * 100)
        ),
        "lru_hit_rate": float(results_df[results_df["cache_mode"] == "lru"]["cache_hit_rate"].mean()),
        "fifo_hit_rate": float(results_df[results_df["cache_mode"] == "fifo"]["cache_hit_rate"].mean()),
        "complex_patterns_lru_advantage": float(
            lru_fifo_comparison[lru_fifo_comparison["complexity"] == "complex"]["time_improvement"].mean()
        )
    }
    
    with open(output_dir / "key_findings.json", "w") as f:
        json.dump(key_findings, f, indent=2)
    
    return True

def main():
    parser = argparse.ArgumentParser(description="Run pattern caching performance benchmarks")
    parser.add_argument('--quick', action='store_true', help='Run a quick benchmark with fewer tests')
    parser.add_argument('--output', default=str(RESULTS_DIR), help='Output directory for results')
    args = parser.parse_args()
    
    if args.quick:
        print("Running quick benchmark...")
        results = run_all_benchmarks(
            complexities=["simple", "medium"],
            pattern_types=["basic", "permute"],
            data_sizes=[1000],
            repetitions=3
        )
    else:
        print("Running full benchmark suite...")
        results = run_all_benchmarks(
            complexities=["simple", "medium", "complex"],
            pattern_types=["basic", "permute", "exclusion"],
            data_sizes=[1000, 5000],
            repetitions=5
        )
    
    # Save raw results
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    results.to_csv(output_dir / "benchmark_results.csv", index=False)
    
    # Create visualizations
    print("Creating visualizations...")
    create_visualizations(results, output_dir)
    
    print(f"Benchmark complete. Results saved to {output_dir}")
    
    # Print summary table
    summary = results.groupby(['cache_mode', 'complexity'])['avg_execution_time', 'cache_hit_rate'].mean().reset_index()
    print("\nPerformance Summary:\n")
    print(tabulate(summary, headers="keys", tablefmt="grid", showindex=False, floatfmt=".4f"))

if __name__ == "__main__":
    main()
