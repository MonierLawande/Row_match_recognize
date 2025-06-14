#!/usr/bin/env python3
"""
Row Match Recognize Performance Stress Testing Tool

This script executes comprehensive stress tests on the Row Match Recognize implementation
and generates detailed performance visualizations.

Usage:
  python run_stress_tests.py [--output-dir OUTPUT_DIR] [--test-type {all,scaling,patterns,cache,partition}]

Options:
  --output-dir OUTPUT_DIR    Directory to store test results and visualizations
  --test-type TEST_TYPE      Type of test to run (default: all)
"""

import os
import argparse
import time
import json
import gc
import psutil
from datetime import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

# Import system modules
from src.executor.match_recognize import match_recognize
from src.utils.pattern_cache import clear_pattern_cache, get_cache_stats, set_caching_enabled
from src.matcher.matcher import SkipMode, RowsPerMatch

def setup_output_directory(output_dir):
    """Create output directory if it doesn't exist."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")
    
    # Create subdirectories
    for subdir in ['charts', 'data', 'logs']:
        path = os.path.join(output_dir, subdir)
        if not os.path.exists(path):
            os.makedirs(path)

def generate_time_series_data(num_rows=1000, num_partitions=10, pattern_complexity='simple'):
    """
    Generate synthetic time series data for testing pattern matching.
    
    Args:
        num_rows: Number of rows in the dataset
        num_partitions: Number of distinct partition values
        pattern_complexity: 'simple', 'medium', or 'complex' pattern structure
        
    Returns:
        pandas DataFrame with customer_id, timestamp, price and other columns
    """
    np.random.seed(42)  # For reproducibility
    
    # Generate partition keys
    partition_keys = [f"cust_{i}" for i in range(1, num_partitions + 1)]
    
    # Distribute rows across partitions
    customer_ids = np.random.choice(partition_keys, num_rows)
    
    # Generate timestamps in ascending order within each partition
    base_timestamps = pd.date_range(start='2020-01-01', periods=num_rows//num_partitions, freq='D')
    timestamps = []
    
    for cust_id in partition_keys:
        cust_rows = sum(customer_ids == cust_id)
        if cust_rows > 0:
            partition_times = pd.date_range(
                start='2020-01-01', 
                periods=cust_rows, 
                freq='D'
            ) + pd.Timedelta(days=np.random.randint(0, 10))
            timestamps.extend(partition_times)
    
    # Sort the data by customer_id and timestamp
    df = pd.DataFrame({
        'customer_id': customer_ids,
        'timestamp': timestamps[:num_rows]
    })
    df = df.sort_values(['customer_id', 'timestamp']).reset_index(drop=True)
    
    # Generate price values based on complexity
    if pattern_complexity == 'simple':
        # Simple pattern: generally increasing prices with occasional dips
        df['price'] = np.random.normal(100, 20, num_rows)
        
    elif pattern_complexity == 'medium':
        # Medium pattern: fluctuating prices with clear up-down cycles
        base_prices = np.random.normal(100, 10, num_rows)
        cycles = np.sin(np.arange(num_rows) * 0.5) * 30
        df['price'] = base_prices + cycles
        
    elif pattern_complexity == 'complex':
        # Complex pattern: multiple overlapping patterns with trends and seasonality
        base_prices = np.random.normal(100, 5, num_rows)
        trend = np.arange(num_rows) * 0.1
        cycles = np.sin(np.arange(num_rows) * 0.2) * 20
        spikes = np.random.binomial(1, 0.05, num_rows) * np.random.normal(0, 50, num_rows)
        df['price'] = base_prices + trend + cycles + spikes
    
    # Add categorical columns for more complex pattern matching
    df['event_type'] = np.random.choice(['order', 'view', 'return'], num_rows)
    df['product_category'] = np.random.choice(['A', 'B', 'C', 'D'], num_rows)
    
    # Round prices to make patterns more distinct
    df['price'] = np.round(df['price'], 2)
    
    # Ensure prices are positive
    df['price'] = np.abs(df['price']) + 1
    
    return df

def run_performance_test(df, query, test_name="Unnamed Test", cache_enabled=True):
    """
    Run a performance test with detailed metrics.
    
    Args:
        df: DataFrame to test against
        query: SQL query with MATCH_RECOGNIZE
        test_name: Name of the test for reporting
        cache_enabled: Whether pattern caching is enabled
        
    Returns:
        Dict with performance metrics
    """
    # Set caching mode
    set_caching_enabled(cache_enabled)
    
    # Clear cache and garbage collect to get clean memory measurement
    clear_pattern_cache()
    gc.collect()
    
    # Get initial memory usage
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / (1024 * 1024)  # MB
    
    # Run the query and time it
    start_time = time.time()
    
    try:
        result = match_recognize(query, df)
        success = True
        error = None
        
        # Capture number of results
        num_results = len(result) if result is not None else 0
        
    except Exception as e:
        success = False
        error = str(e)
        num_results = 0
    
    execution_time = time.time() - start_time
    
    # Get memory usage after execution
    final_memory = process.memory_info().rss / (1024 * 1024)  # MB
    memory_used = final_memory - initial_memory
    
    # Get cache stats
    cache_stats = get_cache_stats()
    
    # Collect comprehensive metrics
    metrics = {
        "test_name": test_name,
        "timestamp": datetime.now().isoformat(),
        "data_size": len(df),
        "num_partitions": df['customer_id'].nunique(),
        "execution_time_seconds": execution_time,
        "memory_used_mb": memory_used,
        "success": success,
        "error": error,
        "num_results": num_results,
        "cache_enabled": cache_enabled,
        "cache_hits": cache_stats.get("hits", 0),
        "cache_misses": cache_stats.get("misses", 0),
        "cache_hit_rate": cache_stats.get("hits", 0) / (cache_stats.get("hits", 0) + cache_stats.get("misses", 1) or 1),
        "memory_used_by_cache_mb": cache_stats.get("memory_used_mb", 0),
    }
    
    return metrics

def get_test_queries():
    """Return a dictionary of test queries with varying complexity."""
    return {
        "simple_pattern": """
        SELECT customer_id, start_price, bottom_price, end_price
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                A.price AS start_price,
                LAST(B.price) AS bottom_price,
                LAST(C.price) AS end_price
            PATTERN (A B+ C+)
            DEFINE
                B AS B.price < PREV(price),
                C AS C.price > PREV(price)
        )
        """,
        
        "complex_pattern": """
        SELECT customer_id, start_price, peak_price, bottom_price, recovery_price
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                A.price AS start_price,
                LAST(B.price) AS peak_price,
                LAST(C.price) AS bottom_price,
                LAST(D.price) AS recovery_price
            PATTERN (A B+ C+ D+)
            DEFINE
                A AS price > 50,
                B AS B.price > PREV(price) AND event_type = 'order',
                C AS C.price < B.price,
                D AS D.price > C.price AND D.price < B.price
        )
        """,
        
        "with_permute": """
        SELECT customer_id, a_timestamp, b_timestamp, c_timestamp
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                A.timestamp AS a_timestamp,
                B.timestamp AS b_timestamp,
                C.timestamp AS c_timestamp
            PATTERN (PERMUTE(A, B, C))
            DEFINE
                A AS event_type = 'order',
                B AS event_type = 'view',
                C AS event_type = 'return'
        )
        """,
        
        "with_exclusion": """
        SELECT customer_id, start_time, end_time, event_sequence
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                A.timestamp AS start_time,
                LAST(C.timestamp) AS end_time,
                CLASSIFIER() AS event_sequence
            PATTERN (A {- B+ -} C+)
            DEFINE
                A AS event_type = 'order',
                B AS product_category = 'A',
                C AS price > 100
        )
        """
    }

def get_stress_test_queries():
    """Return a dictionary of stress test queries for extreme cases."""
    return {
        "long_chain": """
        SELECT customer_id, start_price, end_price
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                A.price AS start_price,
                LAST(Z.price) AS end_price
            PATTERN (A B C D E F G H I J K L M N O P Q R S T U V W X Y Z)
            DEFINE
                A AS A.price > 0,
                B AS B.price > 0, C AS C.price > 0, D AS D.price > 0,
                E AS E.price > 0, F AS F.price > 0, G AS G.price > 0,
                H AS H.price > 0, I AS I.price > 0, J AS J.price > 0,
                K AS K.price > 0, L AS L.price > 0, M AS M.price > 0,
                N AS N.price > 0, O AS O.price > 0, P AS P.price > 0,
                Q AS Q.price > 0, R AS R.price > 0, S AS S.price > 0,
                T AS T.price > 0, U AS U.price > 0, V AS V.price > 0,
                W AS W.price > 0, X AS X.price > 0, Y AS Y.price > 0,
                Z AS Z.price > 0
        )
        """,
        
        "nested_exclusion": """
        SELECT customer_id, start_price, end_price
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                A.price AS start_price,
                LAST(E.price) AS end_price
            PATTERN (A {- B+ {- C D -} -} E+)
            DEFINE
                A AS A.price > 50,
                B AS B.price > A.price,
                C AS C.price < B.price,
                D AS D.price > C.price,
                E AS E.price > PREV(price)
        )
        """,
        
        "backtracking": """
        SELECT customer_id, first_price, last_price
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                FIRST(price) AS first_price,
                LAST(price) AS last_price
            PATTERN ((A | B | C | D | E)+)
            DEFINE
                A AS price > 100 AND PREV(price) < 100,
                B AS price < 50 AND NEXT(price) > 60,
                C AS price BETWEEN 70 AND 80,
                D AS price > FIRST(price) + 20,
                E AS price < LAST(price, 2)
        )
        """,
        
        "highly_selective": """
        SELECT customer_id, match_num, pattern_var
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                MATCH_NUMBER() AS match_num,
                CLASSIFIER() AS pattern_var
            PATTERN (X Y Z)
            DEFINE
                X AS price > 99.9 AND price < 100.1,
                Y AS price > 149.9 AND price < 150.1,
                Z AS price > 199.9 AND price < 200.1
        )
        """
    }

def run_scaling_tests(output_dir):
    """Run tests with increasing dataset sizes."""
    print("Running scaling tests...")
    
    # Define dataset sizes to test
    data_sizes = [100, 500, 1000, 5000, 10000, 20000]
    
    scaling_test_results = []
    test_queries = get_test_queries()
    
    for size in data_sizes:
        # Generate dataset of this size
        df = generate_time_series_data(size, min(size//100, 50), 'medium')
        
        # Run tests with different query patterns
        for query_name, query in test_queries.items():
            # Run with cache enabled
            cache_enabled_result = run_performance_test(
                df, 
                query, 
                test_name=f"Size:{size} Query:{query_name} Cache:On",
                cache_enabled=True
            )
            scaling_test_results.append(cache_enabled_result)
            
            # Also run without cache to see the difference
            if size <= 10000:  # Skip larger sizes without cache to avoid timeouts
                cache_disabled_result = run_performance_test(
                    df, 
                    query, 
                    test_name=f"Size:{size} Query:{query_name} Cache:Off",
                    cache_enabled=False
                )
                scaling_test_results.append(cache_disabled_result)
            
            # Show progress
            print(f"Completed test: Size:{size} Query:{query_name}")
            print(f"  Execution time with cache: {cache_enabled_result['execution_time_seconds']:.4f}s")
            print(f"  Memory used: {cache_enabled_result['memory_used_mb']:.2f}MB")
            print(f"  Results returned: {cache_enabled_result['num_results']}")
            if size <= 10000:
                print(f"  Execution time without cache: {cache_disabled_result['execution_time_seconds']:.4f}s")
            print()
    
    # Convert results to DataFrame and save
    scaling_results_df = pd.DataFrame(scaling_test_results)
    scaling_results_df.to_csv(os.path.join(output_dir, 'data', 'scaling_results.csv'), index=False)
    
    # Create visualization
    create_scaling_visualizations(scaling_results_df, output_dir)
    
    return scaling_results_df

def run_partition_tests(output_dir):
    """Run tests with different numbers of partitions."""
    print("Running partition scaling tests...")
    
    partition_test_results = []
    
    # Fixed data size
    fixed_size = 10000
    
    # Varying number of partitions
    partition_counts = [1, 5, 10, 50, 100, 500]
    
    for num_partitions in partition_counts:
        # Generate dataset with specified number of partitions
        df = generate_time_series_data(fixed_size, num_partitions, 'medium')
        
        # Run the simple pattern test
        result = run_performance_test(
            df, 
            get_test_queries()['simple_pattern'], 
            test_name=f"Partitions:{num_partitions} Size:{fixed_size}",
            cache_enabled=True
        )
        
        partition_test_results.append(result)
        
        print(f"Completed partition test: {num_partitions} partitions")
        print(f"  Execution time: {result['execution_time_seconds']:.4f}s")
        print(f"  Memory used: {result['memory_used_mb']:.2f}MB")
        print()
    
    # Convert to DataFrame and save
    partition_results_df = pd.DataFrame(partition_test_results)
    partition_results_df.to_csv(os.path.join(output_dir, 'data', 'partition_scaling.csv'), index=False)
    
    # Create visualization
    create_partition_visualizations(partition_results_df, output_dir)
    
    return partition_results_df

def run_stress_tests(output_dir):
    """Run stress tests for extreme cases."""
    print("Running stress tests...")
    
    stress_test_results = []
    stress_test_df = generate_time_series_data(5000, 20, 'complex')
    
    for test_name, query in get_stress_test_queries().items():
        print(f"Running stress test: {test_name}")
        
        try:
            result = run_performance_test(
                stress_test_df, 
                query, 
                test_name=f"StressTest:{test_name}",
                cache_enabled=True
            )
            stress_test_results.append(result)
            
            print(f"  Result: {'Success' if result['success'] else 'Failed'}")
            print(f"  Execution time: {result['execution_time_seconds']:.4f}s")
            print(f"  Memory used: {result['memory_used_mb']:.2f}MB")
            print(f"  Matches found: {result['num_results']}")
        except Exception as e:
            print(f"  Error: {str(e)}")
        
        print()
    
    # Convert to DataFrame and save
    stress_results_df = pd.DataFrame(stress_test_results)
    if not stress_results_df.empty:
        stress_results_df.to_csv(os.path.join(output_dir, 'data', 'stress_tests.csv'), index=False)
        
        # Create visualization
        create_stress_test_visualization(stress_results_df, output_dir)
    
    return stress_results_df

def create_scaling_visualizations(scaling_results_df, output_dir):
    """Create visualizations for scaling test results."""
    # Extract metadata
    plot_data = scaling_results_df.copy()
    plot_data['query_name'] = plot_data['test_name'].str.extract(r'Query:(\w+)')
    plot_data['cache_status'] = plot_data['test_name'].str.extract(r'Cache:(\w+)')
    plot_data['data_size'] = plot_data['data_size'].astype(int)
    
    # Plot execution time by data size with and without cache
    plt.figure(figsize=(12, 8))
    for query in plot_data['query_name'].unique():
        # With cache
        with_cache = plot_data[(plot_data['query_name'] == query) & (plot_data['cache_status'] == 'On')]
        plt.plot(with_cache['data_size'], with_cache['execution_time_seconds'], 
                 marker='o', label=f"{query} (Cache On)")
        
        # Without cache
        without_cache = plot_data[(plot_data['query_name'] == query) & (plot_data['cache_status'] == 'Off')]
        if not without_cache.empty:
            plt.plot(without_cache['data_size'], without_cache['execution_time_seconds'], 
                    marker='x', linestyle='--', label=f"{query} (Cache Off)")
    
    plt.title('Execution Time Scaling by Data Size', fontsize=16)
    plt.xlabel('Number of Rows', fontsize=14)
    plt.ylabel('Execution Time (seconds)', fontsize=14)
    plt.xscale('log')
    plt.yscale('log')
    plt.grid(True, alpha=0.3)
    plt.legend(title='Query Pattern', fontsize=12)
    plt.tight_layout()
    
    # Save the chart
    plt.savefig(os.path.join(output_dir, 'charts', 'performance_scaling_chart.png'), dpi=300)
    
    # Create memory usage chart
    plt.figure(figsize=(12, 8))
    for query in plot_data['query_name'].unique():
        # With cache
        with_cache = plot_data[(plot_data['query_name'] == query) & (plot_data['cache_status'] == 'On')]
        plt.plot(with_cache['data_size'], with_cache['memory_used_mb'], 
                 marker='o', label=f"{query}")
    
    plt.title('Memory Usage Scaling by Data Size', fontsize=16)
    plt.xlabel('Number of Rows', fontsize=14)
    plt.ylabel('Memory Used (MB)', fontsize=14)
    plt.xscale('log')
    plt.grid(True, alpha=0.3)
    plt.legend(title='Query Pattern', fontsize=12)
    plt.tight_layout()
    
    # Save the chart
    plt.savefig(os.path.join(output_dir, 'charts', 'memory_scaling_chart.png'), dpi=300)
    
    # Cache analysis
    cache_analysis = scaling_results_df.copy()
    cache_analysis['cache_status'] = cache_analysis['test_name'].str.extract(r'Cache:(\w+)')
    cache_analysis['query_name'] = cache_analysis['test_name'].str.extract(r'Query:(\w+)')
    
    # Calculate cache speedup ratio
    cache_speedup = []
    
    for size in cache_analysis['data_size'].unique():
        for query in cache_analysis['query_name'].unique():
            with_cache = cache_analysis[(cache_analysis['data_size'] == size) & 
                                      (cache_analysis['query_name'] == query) & 
                                      (cache_analysis['cache_status'] == 'On')]
            
            without_cache = cache_analysis[(cache_analysis['data_size'] == size) & 
                                         (cache_analysis['query_name'] == query) & 
                                         (cache_analysis['cache_status'] == 'Off')]
            
            if not with_cache.empty and not without_cache.empty:
                speedup = without_cache['execution_time_seconds'].values[0] / with_cache['execution_time_seconds'].values[0]
                
                cache_speedup.append({
                    'data_size': size,
                    'query_name': query,
                    'cache_speedup_ratio': speedup,
                    'cache_hit_rate': with_cache['cache_hit_rate'].values[0],
                    'cache_memory_mb': with_cache['memory_used_by_cache_mb'].values[0]
                })
    
    cache_speedup_df = pd.DataFrame(cache_speedup)
    
    if not cache_speedup_df.empty:
        # Plot cache speedup
        plt.figure(figsize=(12, 8))
        
        for query in cache_speedup_df['query_name'].unique():
            query_data = cache_speedup_df[cache_speedup_df['query_name'] == query]
            plt.plot(query_data['data_size'], query_data['cache_speedup_ratio'], 
                   marker='o', linewidth=2, label=query)
        
        plt.axhline(y=1.0, color='r', linestyle='--', alpha=0.5, label='No Speedup')
        plt.title('Cache Speedup Ratio by Data Size', fontsize=16)
        plt.xlabel('Data Size (rows)', fontsize=14)
        plt.ylabel('Speedup Ratio (No Cache / With Cache)', fontsize=14)
        plt.xscale('log')
        plt.grid(True, alpha=0.3)
        plt.legend(title='Pattern Type', fontsize=12)
        plt.tight_layout()
        
        # Save the chart
        plt.savefig(os.path.join(output_dir, 'charts', 'cache_speedup_ratio.png'), dpi=300)
        
        # Save the data
        cache_speedup_df.to_csv(os.path.join(output_dir, 'data', 'cache_analysis.csv'), index=False)

def create_partition_visualizations(partition_results_df, output_dir):
    """Create visualizations for partition test results."""
    if partition_results_df.empty:
        return
    
    # Plot partition scaling results
    plt.figure(figsize=(12, 8))
    
    plt.plot(partition_results_df['num_partitions'], partition_results_df['execution_time_seconds'], 
           marker='o', linewidth=2, color='blue')
    
    plt.title(f'Execution Time by Number of Partitions (Fixed Size: {partition_results_df["data_size"].iloc[0]} rows)', 
             fontsize=16)
    plt.xlabel('Number of Partitions', fontsize=14)
    plt.ylabel('Execution Time (seconds)', fontsize=14)
    plt.xscale('log')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Save the chart
    plt.savefig(os.path.join(output_dir, 'charts', 'partition_scaling.png'), dpi=300)
    
    # Plot memory usage by partitions
    plt.figure(figsize=(12, 8))
    
    plt.plot(partition_results_df['num_partitions'], partition_results_df['memory_used_mb'], 
           marker='o', linewidth=2, color='green')
    
    plt.title(f'Memory Usage by Number of Partitions (Fixed Size: {partition_results_df["data_size"].iloc[0]} rows)', 
             fontsize=16)
    plt.xlabel('Number of Partitions', fontsize=14)
    plt.ylabel('Memory Used (MB)', fontsize=14)
    plt.xscale('log')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Save the chart
    plt.savefig(os.path.join(output_dir, 'charts', 'partition_memory_usage.png'), dpi=300)

def create_stress_test_visualization(stress_results_df, output_dir):
    """Create visualization for stress test results."""
    if stress_results_df.empty:
        return
    
    plt.figure(figsize=(12, 8))
    
    # Extract test names for better display
    stress_results_df['test_type'] = stress_results_df['test_name'].str.extract(r'StressTest:(\w+)')
    
    # Create bar chart
    bars = plt.bar(stress_results_df['test_type'], stress_results_df['execution_time_seconds'])
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.4f}s',
                ha='center', va='bottom', fontsize=12)
    
    plt.title('Stress Test Performance', fontsize=16)
    plt.xlabel('Test Type', fontsize=14)
    plt.ylabel('Execution Time (seconds)', fontsize=14)
    plt.yscale('log')
    plt.grid(True, axis='y', alpha=0.3)
    plt.tight_layout()
    
    # Save the chart
    plt.savefig(os.path.join(output_dir, 'charts', 'stress_test_performance.png'), dpi=300)

def create_performance_dashboard(scaling_results_df, partition_results_df, stress_results_df, output_dir):
    """Create a comprehensive performance dashboard."""
    if scaling_results_df.empty:
        return
    
    plt.figure(figsize=(20, 15))
    
    # Define grid layout
    grid = plt.GridSpec(3, 2, hspace=0.4, wspace=0.3)
    
    # Extract metadata for plotting
    plot_data = scaling_results_df.copy()
    plot_data['query_name'] = plot_data['test_name'].str.extract(r'Query:(\w+)')
    plot_data['cache_status'] = plot_data['test_name'].str.extract(r'Cache:(\w+)')
    
    # Calculate cache speedup
    cache_speedup = []
    for size in plot_data['data_size'].unique():
        for query in plot_data['query_name'].unique():
            with_cache = plot_data[(plot_data['data_size'] == size) & 
                                  (plot_data['query_name'] == query) & 
                                  (plot_data['cache_status'] == 'On')]
            
            without_cache = plot_data[(plot_data['data_size'] == size) & 
                                     (plot_data['query_name'] == query) & 
                                     (plot_data['cache_status'] == 'Off')]
            
            if not with_cache.empty and not without_cache.empty:
                speedup = without_cache['execution_time_seconds'].values[0] / with_cache['execution_time_seconds'].values[0]
                
                cache_speedup.append({
                    'data_size': size,
                    'query_name': query,
                    'cache_speedup_ratio': speedup,
                    'cache_hit_rate': with_cache['cache_hit_rate'].values[0],
                    'cache_memory_mb': with_cache['memory_used_by_cache_mb'].values[0]
                })
    
    cache_speedup_df = pd.DataFrame(cache_speedup)
    
    # 1. Execution Time Scaling
    ax1 = plt.subplot(grid[0, 0])
    for query in plot_data['query_name'].unique():
        with_cache = plot_data[(plot_data['query_name'] == query) & (plot_data['cache_status'] == 'On')]
        ax1.plot(with_cache['data_size'], with_cache['execution_time_seconds'], 
               marker='o', linewidth=2, label=query)
    
    ax1.set_title('Execution Time Scaling', fontsize=14)
    ax1.set_xlabel('Number of Rows', fontsize=12)
    ax1.set_ylabel('Time (seconds)', fontsize=12)
    ax1.set_xscale('log')
    ax1.set_yscale('log')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10)
    
    # 2. Cache Speedup
    ax2 = plt.subplot(grid[0, 1])
    if not cache_speedup_df.empty:
        for query in cache_speedup_df['query_name'].unique():
            query_data = cache_speedup_df[cache_speedup_df['query_name'] == query]
            ax2.plot(query_data['data_size'], query_data['cache_speedup_ratio'], 
                   marker='o', linewidth=2, label=query)
        
        ax2.axhline(y=1.0, color='r', linestyle='--', alpha=0.5)
        ax2.set_title('Cache Speedup Ratio', fontsize=14)
        ax2.set_xlabel('Data Size (rows)', fontsize=12)
        ax2.set_ylabel('Speedup Ratio', fontsize=12)
        ax2.set_xscale('log')
        ax2.grid(True, alpha=0.3)
        ax2.legend(fontsize=10)
    
    # 3. Memory Usage
    ax3 = plt.subplot(grid[1, 0])
    for query in plot_data['query_name'].unique():
        with_cache = plot_data[(plot_data['query_name'] == query) & (plot_data['cache_status'] == 'On')]
        ax3.plot(with_cache['data_size'], with_cache['memory_used_mb'], 
               marker='o', linewidth=2, label=query)
    
    ax3.set_title('Memory Usage', fontsize=14)
    ax3.set_xlabel('Number of Rows', fontsize=12)
    ax3.set_ylabel('Memory (MB)', fontsize=12)
    ax3.set_xscale('log')
    ax3.grid(True, alpha=0.3)
    ax3.legend(fontsize=10)
    
    # 4. Cache Hit Rate
    ax4 = plt.subplot(grid[1, 1])
    if not cache_speedup_df.empty:
        for query in cache_speedup_df['query_name'].unique():
            query_data = cache_speedup_df[cache_speedup_df['query_name'] == query]
            ax4.plot(query_data['data_size'], query_data['cache_hit_rate'] * 100, 
                   marker='o', linewidth=2, label=query)
        
        ax4.set_title('Cache Hit Rate', fontsize=14)
        ax4.set_xlabel('Data Size (rows)', fontsize=12)
        ax4.set_ylabel('Hit Rate (%)', fontsize=12)
        ax4.set_xscale('log')
        ax4.grid(True, alpha=0.3)
        ax4.legend(fontsize=10)
    
    # 5. Partition Scaling
    ax5 = plt.subplot(grid[2, 0])
    if not partition_results_df.empty:
        ax5.plot(partition_results_df['num_partitions'], partition_results_df['execution_time_seconds'], 
               marker='o', linewidth=2, color='blue')
        
        ax5.set_title('Partition Scaling', fontsize=14)
        ax5.set_xlabel('Number of Partitions', fontsize=12)
        ax5.set_ylabel('Time (seconds)', fontsize=12)
        ax5.set_xscale('log')
        ax5.grid(True, alpha=0.3)
    
    # 6. Stress Test Results
    ax6 = plt.subplot(grid[2, 1])
    if not stress_results_df.empty:
        stress_results_df['test_type'] = stress_results_df['test_name'].str.extract(r'StressTest:(\w+)')
        bars = ax6.bar(stress_results_df['test_type'], stress_results_df['execution_time_seconds'])
        ax6.set_title('Stress Test Performance', fontsize=14)
        ax6.set_xlabel('Test Type', fontsize=12)
        ax6.set_ylabel('Time (seconds)', fontsize=12)
        ax6.set_xticklabels(stress_results_df['test_type'], rotation=45, ha='right')
        
        # Add value labels
        for bar in bars:
            height = bar.get_height()
            ax6.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.3f}s',
                    ha='center', va='bottom', rotation=0, fontsize=9)
    
    # Add dashboard title
    plt.suptitle('Row Match Recognize Performance Dashboard', fontsize=20, y=0.98)
    
    # Save the dashboard
    plt.savefig(os.path.join(output_dir, 'charts', 'performance_dashboard.png'), dpi=300, bbox_inches='tight')

def generate_performance_recommendations(scaling_results_df, partition_results_df, stress_results_df):
    """Generate performance recommendations based on test results."""
    recommendations = []
    
    # Check if we have enough data
    if len(scaling_results_df) < 5:
        return ["Insufficient test data to generate recommendations."]
    
    # 1. Analyze cache effectiveness
    cache_enabled = scaling_results_df[scaling_results_df['cache_enabled'] == True]
    cache_disabled = scaling_results_df[scaling_results_df['cache_enabled'] == False]
    
    if not cache_enabled.empty and not cache_disabled.empty:
        # Calculate average speedup
        avg_speedup = cache_disabled['execution_time_seconds'].mean() / cache_enabled['execution_time_seconds'].mean()
        
        if avg_speedup > 5:
            recommendations.append(f"✅ Pattern caching is highly effective (avg {avg_speedup:.1f}x speedup). "
                                  "Keep caching enabled for production workloads.")
        elif avg_speedup > 1.5:
            recommendations.append(f"✅ Pattern caching is effective (avg {avg_speedup:.1f}x speedup). "
                                 "Recommended for most workloads.")
        elif avg_speedup > 1:
            recommendations.append(f"⚠️ Pattern caching provides marginal benefit (avg {avg_speedup:.1f}x speedup). "
                                 "Consider tuning cache size parameters.")
        else:
            recommendations.append("❌ Pattern caching appears to be adding overhead without performance benefits. "
                                 "Review cache implementation.")
    
    # 2. Analyze data size scaling
    large_dataset = scaling_results_df[scaling_results_df['data_size'] > 10000]
    if not large_dataset.empty:
        max_time = large_dataset['execution_time_seconds'].max()
        if max_time > 10:
            recommendations.append(f"⚠️ Performance degradation detected with large datasets (max {max_time:.1f}s). "
                                 "Consider adding data size limits for queries.")
    
    # 3. Analyze pattern complexity
    if 'with_permute' in ' '.join(scaling_results_df['test_name'].astype(str)):
        permute_tests = scaling_results_df[scaling_results_df['test_name'].str.contains('with_permute')]
        if not permute_tests.empty:
            avg_permute_time = permute_tests['execution_time_seconds'].mean()
            avg_simple_time = scaling_results_df[
                scaling_results_df['test_name'].str.contains('simple_pattern')
            ]['execution_time_seconds'].mean()
            
            if avg_permute_time > avg_simple_time * 5:
                recommendations.append(f"⚠️ PERMUTE patterns are significantly slower ({avg_permute_time/avg_simple_time:.1f}x). "
                                     "Consider using them sparingly and monitoring their performance.")
    
    # 4. Analyze partition scaling
    if not partition_results_df.empty:
        # Check if increasing partitions increases time super-linearly
        partition_correlation = np.corrcoef(
            partition_results_df['num_partitions'], 
            partition_results_df['execution_time_seconds']
        )[0, 1]
        
        if partition_correlation > 0.9:
            recommendations.append("⚠️ Strong correlation between partition count and execution time detected. "
                                 "Consider optimizing partition handling for large partition counts.")
        
        # Check memory usage pattern with partitions
        mem_correlation = np.corrcoef(
            partition_results_df['num_partitions'], 
            partition_results_df['memory_used_mb']
        )[0, 1]
        
        if mem_correlation > 0.9:
            recommendations.append("⚠️ Memory usage scales linearly with partition count. "
                                 "Monitor memory usage for workloads with many partitions.")
    
    # 5. Check stress test results
    if not stress_results_df.empty:
        failed_tests = stress_results_df[stress_results_df['success'] == False]
        if not failed_tests.empty:
            failed_names = failed_tests['test_name'].tolist()
            recommendations.append(f"❌ Some stress tests failed: {', '.join(failed_names)}. "
                                 "Review implementation for extreme pattern cases.")
        
        # Check for excessive execution times
        slow_tests = stress_results_df[stress_results_df['execution_time_seconds'] > 5]
        if not slow_tests.empty:
            slow_names = slow_tests['test_name'].str.extract(r'StressTest:(\w+)').tolist()
            recommendations.append(f"⚠️ Slow performance detected for pattern types: {', '.join(slow_names)}. "
                                 "Consider optimizing these specific pattern matching cases.")
    
    # General recommendations
    recommendations.append("✅ Enable query timeouts to prevent runaway pattern matching operations.")
    recommendations.append("✅ Monitor memory usage carefully for production workloads with complex patterns.")
    recommendations.append("✅ Consider adding a query complexity analyzer to warn about potentially expensive patterns.")
    
    return recommendations

def save_performance_recommendations(recommendations, output_dir):
    """Save performance recommendations to a file and create a visualization."""
    # Save to text file
    with open(os.path.join(output_dir, 'performance_recommendations.txt'), 'w') as f:
        f.write("# Row Match Recognize Performance Recommendations\n\n")
        for i, rec in enumerate(recommendations):
            f.write(f"{i+1}. {rec}\n\n")
    
    # Create a visualization
    plt.figure(figsize=(12, len(recommendations) * 0.5 + 2))
    plt.axis('off')
    plt.title('Performance Optimization Recommendations', fontsize=16, pad=20)
    
    # Format and display recommendations
    rec_text = '\n\n'.join([f"{i+1}. {rec}" for i, rec in enumerate(recommendations)])
    plt.text(0.05, 0.5, rec_text, fontsize=12, va='center', ha='left', wrap=True)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'charts', 'performance_recommendations.png'), dpi=300, bbox_inches='tight')

def main():
    parser = argparse.ArgumentParser(description='Run stress tests for Row Pattern Recognition')
    parser.add_argument('--output-dir', type=str, default='stress_test_results',
                        help='Directory to store test results and visualizations')
    parser.add_argument('--test-type', type=str, choices=['all', 'scaling', 'patterns', 'cache', 'partition'], 
                        default='all', help='Type of test to run')
    
    args = parser.parse_args()
    
    # Setup output directory
    setup_output_directory(args.output_dir)
    
    # Run tests based on selected type
    scaling_results_df = pd.DataFrame()
    partition_results_df = pd.DataFrame()
    stress_results_df = pd.DataFrame()
    
    if args.test_type in ['all', 'scaling', 'patterns', 'cache']:
        scaling_results_df = run_scaling_tests(args.output_dir)
    
    if args.test_type in ['all', 'partition']:
        partition_results_df = run_partition_tests(args.output_dir)
    
    if args.test_type in ['all', 'patterns']:
        stress_results_df = run_stress_tests(args.output_dir)
    
    # Create combined dashboard
    create_performance_dashboard(scaling_results_df, partition_results_df, stress_results_df, args.output_dir)
    
    # Generate recommendations
    recommendations = generate_performance_recommendations(scaling_results_df, partition_results_df, stress_results_df)
    save_performance_recommendations(recommendations, args.output_dir)
    
    print(f"\nStress tests completed. Results saved to {args.output_dir}")
    print("Dashboard: " + os.path.join(args.output_dir, 'charts', 'performance_dashboard.png'))
    print("Recommendations: " + os.path.join(args.output_dir, 'performance_recommendations.txt'))

if __name__ == "__main__":
    main()
