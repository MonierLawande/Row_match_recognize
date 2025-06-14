#!/usr/bin/env python3
"""
Row Match Recognize Performance Analysis Command Line Tool

This script provides a command-line interface for running specialized performance
tests on the Row Match Recognize implementation, focusing on targeted aspects
that would help identify optimization opportunities.

It builds upon the existing stress testing framework, adding specialized tests for:
1. Memory leak detection
2. Thread safety and concurrency analysis
3. Pattern complexity impact assessment
4. Query optimization suggestions

Usage:
  python performance_analyzer.py [--output-dir OUTPUT_DIR] [--test-type TYPE] [--threads NUM]

Options:
  --output-dir OUTPUT_DIR    Directory to store test results (default: performance_results)
  --test-type TYPE           Test type: memory, concurrency, complexity, all (default: all)
  --threads NUM              Number of threads to use for concurrency tests (default: 4)
  --data-size SIZE           Size of test dataset (default: auto-scaled)
"""

import os
import sys
import argparse
import time
import json
import gc
import psutil
import threading
import multiprocessing
from datetime import datetime
import tracemalloc
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.ticker import FuncFormatter
import warnings
warnings.filterwarnings('ignore')

# Import system modules
from src.executor.match_recognize import match_recognize
from src.utils.pattern_cache import clear_pattern_cache, get_cache_stats, set_caching_enabled
from src.matcher.matcher import SkipMode, RowsPerMatch

def setup_output_directory(output_dir):
    """Create output directory structure if it doesn't exist."""
    for subdir in ['', 'charts', 'data', 'logs', 'recommendations']:
        path = os.path.join(output_dir, subdir)
        if not os.path.exists(path):
            os.makedirs(path)
            print(f"Created directory: {path}")

def generate_time_series_data(num_rows=1000, num_partitions=10, pattern_complexity='simple', 
                              add_noise=False, create_outliers=False):
    """
    Generate synthetic time series data for testing pattern matching.
    
    Args:
        num_rows: Number of rows in the dataset
        num_partitions: Number of distinct partition values
        pattern_complexity: 'simple', 'medium', or 'complex' pattern structure
        add_noise: Whether to add random noise to make patterns less predictable
        create_outliers: Whether to add outliers to test robustness
        
    Returns:
        pandas DataFrame with customer_id, timestamp, price and other columns
    """
    np.random.seed(42)  # For reproducibility
    
    # Generate partition keys
    partition_keys = [f"cust_{i}" for i in range(1, num_partitions + 1)]
    
    # Distribute rows across partitions
    customer_ids = np.random.choice(partition_keys, num_rows)
    
    # Generate timestamps in ascending order within each partition
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
    
    # Add numeric columns for aggregation testing
    df['quantity'] = np.random.randint(1, 10, num_rows)
    df['revenue'] = df['price'] * df['quantity']
    
    # Add timestamp-derived columns
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['month'] = df['timestamp'].dt.month
    
    # Round prices to make patterns more distinct
    df['price'] = np.round(df['price'], 2)
    
    # Ensure prices are positive
    df['price'] = np.abs(df['price']) + 1
    
    # Add noise if requested
    if add_noise:
        df['price'] += np.random.normal(0, 5, num_rows)
        
    # Add outliers if requested
    if create_outliers:
        outlier_indices = np.random.choice(num_rows, size=int(num_rows * 0.02), replace=False)
        df.loc[outlier_indices, 'price'] *= 5
    
    return df

def run_performance_test(df, query, test_name="Unnamed Test", cache_enabled=True, 
                         track_memory=False, detailed_stats=False):
    """
    Run a performance test with detailed metrics.
    
    Args:
        df: DataFrame to test against
        query: SQL query with MATCH_RECOGNIZE
        test_name: Name of the test for reporting
        cache_enabled: Whether pattern caching is enabled
        track_memory: Whether to track detailed memory usage
        detailed_stats: Whether to collect detailed statistics
        
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
    
    # Start memory tracking if requested
    if track_memory:
        tracemalloc.start()
        memory_start = tracemalloc.take_snapshot()
    
    # Run the query and time it
    start_time = time.time()
    cpu_start = time.process_time()
    
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
    
    # Calculate execution times
    execution_time = time.time() - start_time
    cpu_time = time.process_time() - cpu_start
    
    # Get memory usage after execution
    final_memory = process.memory_info().rss / (1024 * 1024)  # MB
    memory_used = final_memory - initial_memory
    
    # Get detailed memory information if requested
    memory_details = {}
    if track_memory:
        memory_end = tracemalloc.take_snapshot()
        memory_diff = memory_end.compare_to(memory_start, 'lineno')
        
        # Store top 10 memory allocations
        memory_details['top_allocations'] = [
            {
                'file': str(stat.traceback.frame.filename), 
                'line': stat.traceback.frame.lineno,
                'size_kb': stat.size / 1024
            }
            for stat in memory_diff[:10]
        ]
        
        tracemalloc.stop()
    
    # Get cache stats
    cache_stats = get_cache_stats()
    
    # Collect comprehensive metrics
    metrics = {
        "test_name": test_name,
        "timestamp": datetime.now().isoformat(),
        "data_size": len(df),
        "num_partitions": df['customer_id'].nunique(),
        "execution_time_seconds": execution_time,
        "cpu_time_seconds": cpu_time,
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
    
    # Add detailed stats if requested
    if detailed_stats:
        metrics["io_wait_time"] = execution_time - cpu_time
        metrics["cpu_utilization"] = cpu_time / execution_time if execution_time > 0 else 0
    
    # Add memory details if tracking was enabled
    if track_memory:
        metrics["memory_details"] = memory_details
    
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
        """,
        
        # Query with aggregation functions
        "with_aggregation": """
        SELECT customer_id, 
               MIN(A.price) AS min_price, 
               MAX(B.price) AS max_price,
               SUM(C.quantity) AS total_quantity,
               AVG(B.revenue) AS avg_revenue
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                FIRST(A.price) AS first_price,
                LAST(C.price) AS last_price
            PATTERN (A+ B+ C+)
            DEFINE
                A AS price < 120,
                B AS B.price > A.price,
                C AS C.price > B.price
        )
        """,
        
        # Query with ALL ROWS PER MATCH mode
        "all_rows_per_match": """
        SELECT customer_id, price, event_type, CLASSIFIER() as match_position
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                CLASSIFIER() AS pattern_pos
            ALL ROWS PER MATCH
            PATTERN (A B+ C+)
            DEFINE
                A AS price < 100,
                B AS B.price > PREV(price),
                C AS C.price > 150
        )
        """,
        
        # Query with multiple navigation functions
        "complex_navigation": """
        SELECT customer_id, first_timestamp, last_timestamp
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                FIRST(timestamp) AS first_timestamp,
                LAST(timestamp) AS last_timestamp
            PATTERN (A B+ C+)
            DEFINE
                A AS price > 50,
                B AS B.price > PREV(price) AND B.price > FIRST(price),
                C AS C.price < PREV(price) AND C.price > FIRST(price) + 10
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
        
        "deep_backtracking": """
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
        """,
        
        "nested_alternation": """
        SELECT customer_id, pattern_var
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                CLASSIFIER() AS pattern_var
            PATTERN ((A | (B (C | D) E) | F)+)
            DEFINE
                A AS price > 100,
                B AS price < 90,
                C AS price < 80,
                D AS price < 70,
                E AS price < 60,
                F AS price > 120
        )
        """,
        
        "complex_kleene_plus": """
        SELECT customer_id, match_num
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                MATCH_NUMBER() AS match_num
            PATTERN (A (B+ C+)+ D+)
            DEFINE
                A AS price > 100,
                B AS B.price < PREV(price),
                C AS C.price > B.price,
                D AS D.price > 150
        )
        """,
        
        "many_pattern_variables": """
        SELECT customer_id, first_price, last_price
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                FIRST(price) AS first_price,
                LAST(price) AS last_price
            PATTERN (A B C D E F G H I J K L M N O P)
            DEFINE
                A AS A.price > 50,
                B AS B.price > A.price,
                C AS C.price > B.price,
                D AS D.price > C.price,
                E AS E.price > D.price,
                F AS F.price > E.price,
                G AS G.price < F.price,
                H AS H.price < G.price,
                I AS I.price < H.price,
                J AS J.price < I.price,
                K AS K.price < J.price,
                L AS L.price > K.price,
                M AS M.price > L.price,
                N AS N.price > M.price,
                O AS O.price > N.price,
                P AS P.price > O.price
        )
        """
    }

def run_memory_tests(output_dir):
    """Run specialized memory usage tests to detect leaks and inefficiencies."""
    print("Running memory usage tests...")
    
    memory_test_results = []
    
    # Test repeated executions with the same pattern to check for memory leaks
    print("Testing for memory leaks with repeated executions...")
    df = generate_time_series_data(5000, 20, 'medium')
    query = get_test_queries()['complex_pattern']
    
    # Run the same query repeatedly to check for memory accumulation
    for i in range(10):
        print(f"  Run {i+1}/10")
        result = run_performance_test(
            df, 
            query, 
            test_name=f"MemoryLeak:Run{i+1}",
            cache_enabled=True,
            track_memory=True
        )
        memory_test_results.append(result)
        
        # Force garbage collection to ensure clean measurement
        gc.collect()
    
    # Test different cache configurations
    print("Testing different cache configurations...")
    for cache_size in [0, 100, 1000, 10000]:
        # We'd modify the cache size configuration here in a real implementation
        
        result = run_performance_test(
            df, 
            query, 
            test_name=f"CacheSize:{cache_size}",
            cache_enabled=cache_size > 0,
            track_memory=True
        )
        memory_test_results.append(result)
    
    # Save results
    memory_results_df = pd.DataFrame(memory_test_results)
    memory_results_df.to_csv(os.path.join(output_dir, 'data', 'memory_test_results.csv'), index=False)
    
    # Create memory usage visualizations
    create_memory_visualizations(memory_results_df, output_dir)
    
    return memory_results_df

def run_concurrent_query(df, query, results, index, track_memory=False):
    """Run a query in a separate thread or process."""
    try:
        result = run_performance_test(
            df, 
            query, 
            test_name=f"Concurrent:Thread{index}",
            cache_enabled=True,
            track_memory=track_memory
        )
        results[index] = result
    except Exception as e:
        results[index] = {
            "test_name": f"Concurrent:Thread{index}",
            "error": str(e),
            "success": False
        }

def run_concurrency_tests(output_dir, num_threads=4):
    """Run tests to evaluate performance under concurrent execution."""
    print(f"Running concurrency tests with {num_threads} threads...")
    
    concurrency_results = []
    
    # Generate dataset
    df = generate_time_series_data(10000, 50, 'medium')
    
    # Get queries to test
    test_queries = get_test_queries()
    
    # Test with different levels of concurrency
    for num_concurrent in [1, 2, 4, 8]:
        actual_threads = min(num_concurrent, num_threads)
        
        print(f"Testing with {actual_threads} concurrent queries...")
        
        # Create threads and shared results
        threads = []
        thread_results = [None] * actual_threads
        
        # Launch concurrent queries
        for i in range(actual_threads):
            query_name = list(test_queries.keys())[i % len(test_queries)]
            query = test_queries[query_name]
            
            t = threading.Thread(
                target=run_concurrent_query,
                args=(df, query, thread_results, i, False)
            )
            threads.append(t)
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Collect results
        for result in thread_results:
            if result:
                concurrency_results.append(result)
    
    # Save results
    concurrency_df = pd.DataFrame(concurrency_results)
    concurrency_df.to_csv(os.path.join(output_dir, 'data', 'concurrency_results.csv'), index=False)
    
    # Create concurrency visualizations
    create_concurrency_visualizations(concurrency_df, output_dir)
    
    return concurrency_df

def run_pattern_complexity_tests(output_dir):
    """Run tests to analyze the impact of pattern complexity on performance."""
    print("Running pattern complexity tests...")
    
    complexity_results = []
    
    # Generate a consistent dataset
    df = generate_time_series_data(10000, 20, 'complex')
    
    # Test standard patterns
    for name, query in get_test_queries().items():
        print(f"Testing standard pattern: {name}")
        result = run_performance_test(
            df, 
            query, 
            test_name=f"Standard:{name}",
            cache_enabled=True,
            detailed_stats=True
        )
        complexity_results.append(result)
    
    # Test stress patterns
    for name, query in get_stress_test_queries().items():
        print(f"Testing stress pattern: {name}")
        result = run_performance_test(
            df, 
            query, 
            test_name=f"Stress:{name}",
            cache_enabled=True,
            detailed_stats=True
        )
        complexity_results.append(result)
    
    # Generate synthetic patterns with increasing complexity
    pattern_sizes = [5, 10, 20, 30, 40, 50]
    for size in pattern_sizes:
        print(f"Testing synthetic pattern of size {size}")
        
        # Generate a pattern with 'size' variables
        variables = [chr(65 + i % 26) for i in range(size)]
        pattern_str = " ".join(variables)
        
        # Generate DEFINE clauses
        define_clauses = []
        for i, var in enumerate(variables):
            if i == 0:
                define_clauses.append(f"{var} AS price > 50")
            else:
                prev_var = variables[i-1]
                define_clauses.append(f"{var} AS {var}.price > {prev_var}.price")
        
        # Construct the query
        synthetic_query = f"""
        SELECT customer_id, first_price, last_price
        FROM data
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY timestamp
            MEASURES
                FIRST(price) AS first_price,
                LAST(price) AS last_price
            PATTERN ({pattern_str})
            DEFINE
                {", ".join(define_clauses)}
        )
        """
        
        result = run_performance_test(
            df, 
            synthetic_query, 
            test_name=f"Synthetic:Size{size}",
            cache_enabled=True,
            detailed_stats=True
        )
        complexity_results.append(result)
    
    # Save results
    complexity_df = pd.DataFrame(complexity_results)
    complexity_df.to_csv(os.path.join(output_dir, 'data', 'pattern_complexity_results.csv'), index=False)
    
    # Create pattern complexity visualizations
    create_pattern_complexity_visualizations(complexity_df, output_dir)
    
    return complexity_df

def create_memory_visualizations(memory_results_df, output_dir):
    """Create visualizations for memory test results."""
    # Setup the visualization style
    plt.style.use('ggplot')
    sns.set_palette("viridis")
    
    # Memory usage over repeated runs (to detect leaks)
    leak_tests = memory_results_df[memory_results_df['test_name'].str.contains('MemoryLeak')]
    
    if not leak_tests.empty:
        # Extract run numbers
        leak_tests['run_number'] = leak_tests['test_name'].str.extract(r'MemoryLeak:Run(\d+)').astype(int)
        leak_tests = leak_tests.sort_values('run_number')
        
        plt.figure(figsize=(12, 8))
        
        # Plot total memory usage
        plt.plot(leak_tests['run_number'], leak_tests['memory_used_mb'], 
                marker='o', linewidth=2, label='Total Memory')
        
        # Plot cache memory usage
        plt.plot(leak_tests['run_number'], leak_tests['memory_used_by_cache_mb'], 
                marker='s', linewidth=2, label='Cache Memory')
        
        plt.title('Memory Usage Over Repeated Runs', fontsize=16)
        plt.xlabel('Run Number', fontsize=14)
        plt.ylabel('Memory Usage (MB)', fontsize=14)
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=12)
        plt.tight_layout()
        
        # Save the chart
        plt.savefig(os.path.join(output_dir, 'charts', 'memory_leak_analysis.png'), dpi=300)
        plt.close()
    
    # Cache size impact
    cache_tests = memory_results_df[memory_results_df['test_name'].str.contains('CacheSize')]
    
    if not cache_tests.empty:
        # Extract cache sizes
        cache_tests['cache_size'] = cache_tests['test_name'].str.extract(r'CacheSize:(\d+)').astype(int)
        cache_tests = cache_tests.sort_values('cache_size')
        
        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # Memory usage by cache size
        ax1.plot(cache_tests['cache_size'], cache_tests['memory_used_mb'], 
                marker='o', linewidth=2)
        ax1.set_title('Memory Usage by Cache Size', fontsize=14)
        ax1.set_xlabel('Cache Size (entries)', fontsize=12)
        ax1.set_ylabel('Memory Usage (MB)', fontsize=12)
        ax1.grid(True, alpha=0.3)
        
        # Execution time by cache size
        ax2.plot(cache_tests['cache_size'], cache_tests['execution_time_seconds'], 
                marker='o', linewidth=2)
        ax2.set_title('Execution Time by Cache Size', fontsize=14)
        ax2.set_xlabel('Cache Size (entries)', fontsize=12)
        ax2.set_ylabel('Execution Time (seconds)', fontsize=12)
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save the chart
        plt.savefig(os.path.join(output_dir, 'charts', 'cache_size_impact.png'), dpi=300)
        plt.close()

def create_concurrency_visualizations(concurrency_df, output_dir):
    """Create visualizations for concurrency test results."""
    if concurrency_df.empty:
        return
    
    # Setup the visualization style
    plt.style.use('ggplot')
    sns.set_palette("viridis")
    
    # Extract thread numbers
    concurrency_df['thread_num'] = concurrency_df['test_name'].str.extract(r'Concurrent:Thread(\d+)').astype(int)
    
    # Group by number of concurrent threads
    thread_counts = concurrency_df['thread_num'].nunique()
    concurrency_df['concurrent_count'] = concurrency_df['thread_num'].apply(lambda x: min(x+1, thread_counts))
    
    # Calculate average metrics by concurrency level
    concurrency_summary = concurrency_df.groupby('concurrent_count').agg({
        'execution_time_seconds': 'mean',
        'cpu_time_seconds': 'mean',
        'memory_used_mb': 'mean',
        'success': 'mean'
    }).reset_index()
    
    # Create visualization
    plt.figure(figsize=(12, 8))
    
    # Plot execution time by concurrency level
    plt.plot(concurrency_summary['concurrent_count'], concurrency_summary['execution_time_seconds'], 
            marker='o', linewidth=2, label='Execution Time')
    
    plt.title('Performance Under Concurrent Execution', fontsize=16)
    plt.xlabel('Number of Concurrent Queries', fontsize=14)
    plt.ylabel('Average Execution Time (seconds)', fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=12)
    plt.tight_layout()
    
    # Save the chart
    plt.savefig(os.path.join(output_dir, 'charts', 'concurrency_performance.png'), dpi=300)
    plt.close()
    
    # Create a heatmap for concurrency impact
    if len(concurrency_df) > 4:
        plt.figure(figsize=(10, 8))
        
        # Pivot data for heatmap
        concurrency_pivot = concurrency_df.pivot_table(
            index='concurrent_count',
            values=['execution_time_seconds', 'memory_used_mb', 'success'],
            aggfunc='mean'
        )
        
        # Normalize values for better visualization
        normalized_pivot = concurrency_pivot.copy()
        for col in normalized_pivot.columns:
            normalized_pivot[col] = normalized_pivot[col] / normalized_pivot[col].max()
        
        # Create heatmap
        sns.heatmap(normalized_pivot, annot=concurrency_pivot, fmt='.3g', cmap='viridis')
        plt.title('Concurrency Impact Heatmap (Normalized)', fontsize=16)
        plt.tight_layout()
        
        # Save the chart
        plt.savefig(os.path.join(output_dir, 'charts', 'concurrency_heatmap.png'), dpi=300)
        plt.close()

def create_pattern_complexity_visualizations(complexity_df, output_dir):
    """Create visualizations for pattern complexity test results."""
    if complexity_df.empty:
        return
    
    # Setup the visualization style
    plt.style.use('ggplot')
    sns.set_palette("viridis")
    
    # Extract pattern types and create a more manageable label
    complexity_df['pattern_type'] = complexity_df['test_name'].str.split(':').str[0]
    complexity_df['pattern_name'] = complexity_df['test_name'].str.split(':').str[1]
    
    # Plot performance by pattern complexity
    plt.figure(figsize=(14, 10))
    
    # Group standard and stress patterns
    standard_patterns = complexity_df[complexity_df['pattern_type'] == 'Standard']
    stress_patterns = complexity_df[complexity_df['pattern_type'] == 'Stress']
    synthetic_patterns = complexity_df[complexity_df['pattern_type'] == 'Synthetic']
    
    # Create subplots
    fig, axes = plt.subplots(2, 1, figsize=(14, 16))
    
    # 1. Standard vs Stress Patterns
    combined_patterns = pd.concat([standard_patterns, stress_patterns])
    if not combined_patterns.empty:
        # Sort by execution time for better visualization
        combined_patterns = combined_patterns.sort_values('execution_time_seconds')
        
        # Plot as a horizontal bar chart
        colors = ['#3498db' if t == 'Standard' else '#e74c3c' for t in combined_patterns['pattern_type']]
        
        axes[0].barh(combined_patterns['pattern_name'], combined_patterns['execution_time_seconds'], color=colors)
        axes[0].set_title('Execution Time by Pattern Type', fontsize=16)
        axes[0].set_xlabel('Execution Time (seconds)', fontsize=14)
        axes[0].set_ylabel('Pattern Name', fontsize=14)
        
        # Add a legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='#3498db', label='Standard Patterns'),
            Patch(facecolor='#e74c3c', label='Stress Patterns')
        ]
        axes[0].legend(handles=legend_elements, loc='upper right', fontsize=12)
        
        # Annotate bars with execution time
        for i, v in enumerate(combined_patterns['execution_time_seconds']):
            axes[0].text(v + 0.01, i, f'{v:.3f}s', va='center', fontsize=10)
    
    # 2. Synthetic Pattern Scaling
    if not synthetic_patterns.empty:
        # Extract pattern sizes
        synthetic_patterns['pattern_size'] = synthetic_patterns['pattern_name'].str.extract(r'Size(\d+)').astype(int)
        synthetic_patterns = synthetic_patterns.sort_values('pattern_size')
        
        # Plot execution time by pattern size
        axes[1].plot(synthetic_patterns['pattern_size'], synthetic_patterns['execution_time_seconds'], 
                    marker='o', linewidth=2, color='#2ecc71')
        axes[1].set_title('Execution Time by Synthetic Pattern Size', fontsize=16)
        axes[1].set_xlabel('Pattern Size (number of variables)', fontsize=14)
        axes[1].set_ylabel('Execution Time (seconds)', fontsize=14)
        axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save the chart
    plt.savefig(os.path.join(output_dir, 'charts', 'pattern_complexity_analysis.png'), dpi=300)
    plt.close()
    
    # Create a correlation heatmap for performance factors
    plt.figure(figsize=(12, 10))
    
    # Select numerical columns for correlation
    numeric_cols = complexity_df.select_dtypes(include=[np.number]).columns
    relevant_cols = [col for col in numeric_cols if col not in ['thread_num', 'concurrent_count', 'pattern_size']]
    
    if len(relevant_cols) > 1:
        # Calculate correlation matrix
        corr_matrix = complexity_df[relevant_cols].corr()
        
        # Create heatmap
        sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', fmt='.2f', linewidths=0.5)
        plt.title('Correlation Between Performance Metrics', fontsize=16)
        plt.tight_layout()
        
        # Save the chart
        plt.savefig(os.path.join(output_dir, 'charts', 'performance_correlation_heatmap.png'), dpi=300)
        plt.close()

def create_comprehensive_dashboard(memory_df, concurrency_df, complexity_df, output_dir):
    """Create a comprehensive dashboard combining all test results."""
    # Setup the visualization style
    plt.style.use('ggplot')
    sns.set_palette("viridis")
    
    # Create a large figure for the dashboard
    plt.figure(figsize=(24, 18))
    
    # Define grid layout
    grid = plt.GridSpec(3, 3, hspace=0.4, wspace=0.3)
    
    # 1. Memory Usage Analysis
    ax1 = plt.subplot(grid[0, 0])
    if 'run_number' in memory_df.columns:
        leak_tests = memory_df[memory_df['test_name'].str.contains('MemoryLeak')]
        if not leak_tests.empty:
            ax1.plot(leak_tests['run_number'], leak_tests['memory_used_mb'], 
                    marker='o', linewidth=2, label='Memory Usage')
            ax1.set_title('Memory Stability Analysis', fontsize=14)
            ax1.set_xlabel('Run Number', fontsize=12)
            ax1.set_ylabel('Memory (MB)', fontsize=12)
            ax1.grid(True, alpha=0.3)
    
    # 2. Cache Performance
    ax2 = plt.subplot(grid[0, 1])
    cache_tests = memory_df[memory_df['test_name'].str.contains('CacheSize')]
    if 'cache_size' in memory_df.columns and not cache_tests.empty:
        ax2.plot(cache_tests['cache_size'], cache_tests['execution_time_seconds'], 
                marker='o', linewidth=2)
        ax2.set_title('Cache Size Impact', fontsize=14)
        ax2.set_xlabel('Cache Size', fontsize=12)
        ax2.set_ylabel('Time (seconds)', fontsize=12)
        ax2.grid(True, alpha=0.3)
    
    # 3. Concurrency Performance
    ax3 = plt.subplot(grid[0, 2])
    if 'concurrent_count' in concurrency_df.columns:
        concurrency_summary = concurrency_df.groupby('concurrent_count').agg({
            'execution_time_seconds': 'mean'
        }).reset_index()
        
        if not concurrency_summary.empty:
            ax3.plot(concurrency_summary['concurrent_count'], concurrency_summary['execution_time_seconds'], 
                    marker='o', linewidth=2)
            ax3.set_title('Concurrency Impact', fontsize=14)
            ax3.set_xlabel('Concurrent Queries', fontsize=12)
            ax3.set_ylabel('Time (seconds)', fontsize=12)
            ax3.grid(True, alpha=0.3)
    
    # 4. Pattern Complexity - Standard vs Stress
    ax4 = plt.subplot(grid[1, 0:2])
    if 'pattern_type' in complexity_df.columns and 'pattern_name' in complexity_df.columns:
        combined_patterns = complexity_df[
            (complexity_df['pattern_type'] == 'Standard') | 
            (complexity_df['pattern_type'] == 'Stress')
        ]
        
        if not combined_patterns.empty:
            # Sort by execution time
            combined_patterns = combined_patterns.sort_values('execution_time_seconds')
            
            # Select top patterns for readability
            top_patterns = combined_patterns.tail(10)
            
            colors = ['#3498db' if t == 'Standard' else '#e74c3c' for t in top_patterns['pattern_type']]
            
            ax4.barh(top_patterns['pattern_name'], top_patterns['execution_time_seconds'], color=colors)
            ax4.set_title('Top 10 Patterns by Execution Time', fontsize=14)
            ax4.set_xlabel('Time (seconds)', fontsize=12)
            ax4.set_ylabel('Pattern', fontsize=12)
            
            # Add a legend
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor='#3498db', label='Standard'),
                Patch(facecolor='#e74c3c', label='Stress')
            ]
            ax4.legend(handles=legend_elements, loc='upper right', fontsize=10)
    
    # 5. Synthetic Pattern Scaling
    ax5 = plt.subplot(grid[1, 2])
    synthetic_patterns = complexity_df[complexity_df['pattern_type'] == 'Synthetic']
    if 'pattern_size' in complexity_df.columns and not synthetic_patterns.empty:
        ax5.plot(synthetic_patterns['pattern_size'], synthetic_patterns['execution_time_seconds'], 
                marker='o', linewidth=2, color='#2ecc71')
        ax5.set_title('Pattern Size Scaling', fontsize=14)
        ax5.set_xlabel('Pattern Size', fontsize=12)
        ax5.set_ylabel('Time (seconds)', fontsize=12)
        ax5.grid(True, alpha=0.3)
    
    # 6-8. Performance Metrics Overview - All Tests Combined
    all_results = pd.concat([memory_df, concurrency_df, complexity_df], ignore_index=True)
    
    # 6. Success Rate by Test Type
    ax6 = plt.subplot(grid[2, 0])
    if not all_results.empty:
        test_types = all_results['test_name'].str.split(':').str[0].unique()
        success_rates = []
        
        for test_type in test_types:
            type_data = all_results[all_results['test_name'].str.contains(test_type)]
            if not type_data.empty:
                success_rate = type_data['success'].mean() * 100
                success_rates.append((test_type, success_rate))
        
        if success_rates:
            types, rates = zip(*success_rates)
            ax6.bar(types, rates, color='#9b59b6')
            ax6.set_title('Success Rate by Test Type', fontsize=14)
            ax6.set_xlabel('Test Type', fontsize=12)
            ax6.set_ylabel('Success Rate (%)', fontsize=12)
            ax6.set_ylim(0, 105)
            
            # Add value labels
            for i, v in enumerate(rates):
                ax6.text(i, v + 2, f'{v:.1f}%', ha='center', fontsize=10)
    
    # 7. Execution Time Distribution
    ax7 = plt.subplot(grid[2, 1])
    if 'execution_time_seconds' in all_results.columns:
        # Filter out extreme outliers for better visualization
        q1 = all_results['execution_time_seconds'].quantile(0.25)
        q3 = all_results['execution_time_seconds'].quantile(0.75)
        iqr = q3 - q1
        filtered_times = all_results[
            (all_results['execution_time_seconds'] >= q1 - 1.5 * iqr) &
            (all_results['execution_time_seconds'] <= q3 + 1.5 * iqr)
        ]['execution_time_seconds']
        
        if not filtered_times.empty:
            sns.histplot(filtered_times, kde=True, ax=ax7, color='#3498db')
            ax7.set_title('Execution Time Distribution', fontsize=14)
            ax7.set_xlabel('Time (seconds)', fontsize=12)
            ax7.set_ylabel('Frequency', fontsize=12)
    
    # 8. Memory Usage Distribution
    ax8 = plt.subplot(grid[2, 2])
    if 'memory_used_mb' in all_results.columns:
        # Filter out extreme outliers
        q1 = all_results['memory_used_mb'].quantile(0.25)
        q3 = all_results['memory_used_mb'].quantile(0.75)
        iqr = q3 - q1
        filtered_memory = all_results[
            (all_results['memory_used_mb'] >= q1 - 1.5 * iqr) &
            (all_results['memory_used_mb'] <= q3 + 1.5 * iqr)
        ]['memory_used_mb']
        
        if not filtered_memory.empty:
            sns.histplot(filtered_memory, kde=True, ax=ax8, color='#2ecc71')
            ax8.set_title('Memory Usage Distribution', fontsize=14)
            ax8.set_xlabel('Memory (MB)', fontsize=12)
            ax8.set_ylabel('Frequency', fontsize=12)
    
    # Add dashboard title
    plt.suptitle('Row Match Recognize Performance Analysis Dashboard', fontsize=20, y=0.98)
    
    # Save the dashboard
    plt.savefig(os.path.join(output_dir, 'charts', 'comprehensive_performance_dashboard.png'), dpi=300, bbox_inches='tight')
    plt.close()

def generate_performance_recommendations(memory_df, concurrency_df, complexity_df, output_dir):
    """Generate detailed performance recommendations based on test results."""
    recommendations = []
    
    # Memory-related recommendations
    if not memory_df.empty:
        leak_tests = memory_df[memory_df['test_name'].str.contains('MemoryLeak')]
        if not leak_tests.empty:
            # Check for memory growth trend
            leak_tests['run_number'] = leak_tests['test_name'].str.extract(r'MemoryLeak:Run(\d+)').astype(int)
            leak_tests = leak_tests.sort_values('run_number')
            
            # Calculate linear regression to detect trend
            if len(leak_tests) > 3:
                from scipy import stats
                slope, intercept, r_value, p_value, std_err = stats.linregress(
                    leak_tests['run_number'], 
                    leak_tests['memory_used_mb']
                )
                
                if slope > 0.1 and p_value < 0.05:
                    recommendations.append({
                        "category": "Memory",
                        "severity": "High",
                        "finding": "Potential memory leak detected",
                        "description": f"Memory usage increases by approximately {slope:.2f}MB per run",
                        "recommendation": "Review resource cleanup in pattern matching engine, particularly in automata construction and row context management."
                    })
                else:
                    recommendations.append({
                        "category": "Memory",
                        "severity": "Low",
                        "finding": "Memory usage is stable across repeated runs",
                        "description": "No significant memory growth detected during repeated pattern executions",
                        "recommendation": "Current memory management approach appears effective."
                    })
        
        # Cache size recommendations
        cache_tests = memory_df[memory_df['test_name'].str.contains('CacheSize')]
        if not cache_tests.empty:
            cache_tests['cache_size'] = cache_tests['test_name'].str.extract(r'CacheSize:(\d+)').astype(int)
            cache_tests = cache_tests.sort_values('cache_size')
            
            # Find optimal cache size
            if len(cache_tests) > 2:
                # Calculate diminishing returns point
                exec_times = cache_tests['execution_time_seconds'].values
                cache_sizes = cache_tests['cache_size'].values
                
                improvements = []
                for i in range(1, len(exec_times)):
                    if exec_times[i-1] > 0:
                        improvement = (exec_times[i-1] - exec_times[i]) / exec_times[i-1]
                        improvements.append((cache_sizes[i], improvement))
                
                # Find point of diminishing returns
                significant_improvements = [(size, imp) for size, imp in improvements if imp > 0.05]
                if significant_improvements:
                    optimal_size = max(size for size, _ in significant_improvements)
                    recommendations.append({
                        "category": "Cache",
                        "severity": "Medium",
                        "finding": "Optimal cache size identified",
                        "description": f"Cache size of {optimal_size} entries provides the best performance-memory tradeoff",
                        "recommendation": f"Configure cache size to approximately {optimal_size} entries for optimal performance."
                    })
                else:
                    recommendations.append({
                        "category": "Cache",
                        "severity": "Medium",
                        "finding": "Limited cache benefit observed",
                        "description": "Cache provides minimal performance improvement",
                        "recommendation": "Consider reducing cache size or disabling caching for this workload to save memory."
                    })
    
    # Concurrency recommendations
    if not concurrency_df.empty and 'concurrent_count' in concurrency_df.columns:
        # Calculate average metrics by concurrency level
        concurrency_summary = concurrency_df.groupby('concurrent_count').agg({
            'execution_time_seconds': 'mean',
            'success': 'mean'
        }).reset_index()
        
        if not concurrency_summary.empty and len(concurrency_summary) > 1:
            # Analyze how performance scales with concurrency
            # Linear scaling would mean time stays constant as concurrency increases
            # Sub-linear would show increasing times
            
            # Calculate performance degradation at max concurrency
            min_concurrency = concurrency_summary['concurrent_count'].min()
            max_concurrency = concurrency_summary['concurrent_count'].max()
            
            min_time = concurrency_summary[concurrency_summary['concurrent_count'] == min_concurrency]['execution_time_seconds'].values[0]
            max_time = concurrency_summary[concurrency_summary['concurrent_count'] == max_concurrency]['execution_time_seconds'].values[0]
            
            # Ideal time should stay constant (perfect scaling)
            degradation = (max_time / min_time) - 1
            
            if degradation > 1.0:
                recommendations.append({
                    "category": "Concurrency",
                    "severity": "High",
                    "finding": "Significant performance degradation under concurrent load",
                    "description": f"Performance degrades by {degradation*100:.1f}% at {max_concurrency}x concurrency",
                    "recommendation": "Review thread synchronization in pattern matching engine. Consider implementing partition-level parallelism instead of query-level parallelism."
                })
            elif degradation > 0.2:
                recommendations.append({
                    "category": "Concurrency",
                    "severity": "Medium",
                    "finding": "Moderate performance degradation under concurrent load",
                    "description": f"Performance degrades by {degradation*100:.1f}% at {max_concurrency}x concurrency",
                    "recommendation": "Consider implementing a query queue with prioritization for better resource management under concurrent load."
                })
            else:
                recommendations.append({
                    "category": "Concurrency",
                    "severity": "Low",
                    "finding": "Good scalability under concurrent load",
                    "description": f"Performance degradation is minimal ({degradation*100:.1f}%) even at {max_concurrency}x concurrency",
                    "recommendation": "Current concurrency approach is effective. Consider adding monitoring for thread pool utilization in production."
                })
    
    # Pattern complexity recommendations
    if not complexity_df.empty and 'pattern_type' in complexity_df.columns:
        # Analyze performance across different pattern types
        pattern_summary = complexity_df.groupby('pattern_type').agg({
            'execution_time_seconds': ['mean', 'max'],
            'memory_used_mb': ['mean', 'max'],
            'success': 'mean'
        })
        
        if not pattern_summary.empty:
            # Find most problematic pattern types
            pattern_summary = pattern_summary.reset_index()
            pattern_summary.columns = ['pattern_type', 'avg_time', 'max_time', 'avg_memory', 'max_memory', 'success_rate']
            
            # Check for patterns with excessive execution time
            slow_patterns = pattern_summary[pattern_summary['max_time'] > 1.0]
            for _, row in slow_patterns.iterrows():
                severity = "High" if row['max_time'] > 5.0 else "Medium"
                recommendations.append({
                    "category": "Pattern Complexity",
                    "severity": severity,
                    "finding": f"Slow execution for {row['pattern_type']} patterns",
                    "description": f"Maximum execution time of {row['max_time']:.2f}s, average of {row['avg_time']:.2f}s",
                    "recommendation": f"Optimize {row['pattern_type']} pattern handling, particularly automata construction and backtracking logic."
                })
            
            # Check synthetic pattern scaling
            synthetic_patterns = complexity_df[complexity_df['pattern_type'] == 'Synthetic']
            if 'pattern_size' in complexity_df.columns and len(synthetic_patterns) > 3:
                # Calculate growth rate
                synthetic_patterns['pattern_size'] = synthetic_patterns['pattern_name'].str.extract(r'Size(\d+)').astype(int)
                synthetic_patterns = synthetic_patterns.sort_values('pattern_size')
                
                # Linear regression to determine scaling factor
                from scipy import stats
                slope, intercept, r_value, p_value, std_err = stats.linregress(
                    synthetic_patterns['pattern_size'], 
                    synthetic_patterns['execution_time_seconds']
                )
                
                if slope > 0.1 and p_value < 0.05:
                    growth_type = "linear" if r_value > 0.95 else "super-linear"
                    recommendations.append({
                        "category": "Pattern Scaling",
                        "severity": "Medium",
                        "finding": f"{growth_type.capitalize()} growth in execution time with pattern size",
                        "description": f"Time increases by ~{slope:.3f}s per additional pattern variable (r²={r_value:.2f})",
                        "recommendation": "Implement pattern size limits in production. Consider optimizing the automata construction algorithm for large patterns."
                    })
        
        # Identify problematic individual patterns
        if 'pattern_name' in complexity_df.columns:
            # Find patterns with highest execution times
            worst_patterns = complexity_df.nlargest(3, 'execution_time_seconds')
            for _, row in worst_patterns.iterrows():
                if row['execution_time_seconds'] > 2.0:
                    recommendations.append({
                        "category": "Specific Patterns",
                        "severity": "Medium",
                        "finding": f"Slow pattern: {row['pattern_name']}",
                        "description": f"Execution time: {row['execution_time_seconds']:.2f}s, Memory: {row['memory_used_mb']:.2f}MB",
                        "recommendation": "Review this specific pattern type for optimization opportunities. Consider adding specialized handling for this pattern structure."
                    })
    
    # General recommendations
    recommendations.append({
        "category": "Production Readiness",
        "severity": "Medium",
        "finding": "Query timeout mechanism needed",
        "description": "Complex patterns can lead to excessive execution times",
        "recommendation": "Implement a configurable timeout mechanism for pattern matching operations to prevent runaway queries."
    })
    
    recommendations.append({
        "category": "Production Readiness",
        "severity": "Medium",
        "finding": "Pattern complexity analyzer",
        "description": "Some pattern structures can lead to excessive resource consumption",
        "recommendation": "Implement a pattern complexity analyzer that can warn about or reject potentially expensive patterns before execution."
    })
    
    # Save recommendations to JSON
    with open(os.path.join(output_dir, 'recommendations', 'performance_recommendations.json'), 'w') as f:
        json.dump(recommendations, f, indent=2)
    
    # Create a formatted text version
    with open(os.path.join(output_dir, 'recommendations', 'performance_recommendations.md'), 'w') as f:
        f.write("# Row Match Recognize Performance Recommendations\n\n")
        
        # Group recommendations by category
        categories = {}
        for rec in recommendations:
            if rec['category'] not in categories:
                categories[rec['category']] = []
            categories[rec['category']].append(rec)
        
        # Write recommendations by category
        for category, recs in categories.items():
            f.write(f"## {category}\n\n")
            
            # Sort by severity
            severity_order = {"High": 0, "Medium": 1, "Low": 2}
            sorted_recs = sorted(recs, key=lambda x: severity_order.get(x['severity'], 3))
            
            for rec in sorted_recs:
                severity_marker = "🔴" if rec['severity'] == "High" else "🟠" if rec['severity'] == "Medium" else "🟢"
                f.write(f"### {severity_marker} {rec['finding']}\n\n")
                f.write(f"**Severity:** {rec['severity']}\n\n")
                f.write(f"**Description:** {rec['description']}\n\n")
                f.write(f"**Recommendation:** {rec['recommendation']}\n\n")
    
    print(f"Generated {len(recommendations)} performance recommendations")
    return recommendations

def main():
    parser = argparse.ArgumentParser(description='Row Match Recognize Performance Analysis Tool')
    parser.add_argument('--output-dir', type=str, default='performance_results',
                        help='Directory to store test results and visualizations')
    parser.add_argument('--test-type', type=str, choices=['memory', 'concurrency', 'complexity', 'all'], 
                        default='all', help='Type of test to run')
    parser.add_argument('--threads', type=int, default=4,
                        help='Number of threads to use for concurrency tests')
    parser.add_argument('--data-size', type=int, default=0,
                        help='Size of test dataset (0 for auto-scaled)')
    
    args = parser.parse_args()
    
    # Setup output directory
    setup_output_directory(args.output_dir)
    
    # Run tests based on selected type
    memory_df = pd.DataFrame()
    concurrency_df = pd.DataFrame()
    complexity_df = pd.DataFrame()
    
    if args.test_type in ['all', 'memory']:
        print("\n=== Running Memory Usage Tests ===\n")
        memory_df = run_memory_tests(args.output_dir)
    
    if args.test_type in ['all', 'concurrency']:
        print("\n=== Running Concurrency Tests ===\n")
        concurrency_df = run_concurrency_tests(args.output_dir, args.threads)
    
    if args.test_type in ['all', 'complexity']:
        print("\n=== Running Pattern Complexity Tests ===\n")
        complexity_df = run_pattern_complexity_tests(args.output_dir)
    
    # Create combined dashboard
    print("\n=== Creating Comprehensive Dashboard ===\n")
    create_comprehensive_dashboard(memory_df, concurrency_df, complexity_df, args.output_dir)
    
    # Generate recommendations
    print("\n=== Generating Performance Recommendations ===\n")
    recommendations = generate_performance_recommendations(memory_df, concurrency_df, complexity_df, args.output_dir)
    
    print(f"\nPerformance analysis completed. Results saved to {args.output_dir}")
    print("Dashboard: " + os.path.join(args.output_dir, 'charts', 'comprehensive_performance_dashboard.png'))
    print("Recommendations: " + os.path.join(args.output_dir, 'recommendations', 'performance_recommendations.md'))

if __name__ == "__main__":
    main()
