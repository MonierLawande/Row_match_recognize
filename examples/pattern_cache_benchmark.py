#!/usr/bin/env python3
"""
Pattern Cache Production Demo

This script demonstrates how to use the enhanced pattern caching system
in a production environment, including monitoring and management features.
"""

import time
import pandas as pd
import argparse
from src.executor.match_recognize import match_recognize
from src.utils.pattern_cache import (
    get_cache_stats, clear_pattern_cache, resize_cache, 
    is_caching_enabled, set_caching_enabled
)
from src.monitoring.cache_monitor import start_cache_monitoring, stop_cache_monitoring
from src.config.production_config import MatchRecognizeConfig

def run_benchmark(num_patterns=50, pattern_complexity=3, iterations=3):
    """
    Run a benchmark of pattern compilation and caching.
    
    Args:
        num_patterns: Number of unique patterns to compile
        pattern_complexity: Complexity level of patterns (1-3)
        iterations: Number of times to run each pattern
    """
    # Sample data
    df = pd.DataFrame({
        'id': range(1, 101),
        'value': [i % 10 for i in range(1, 101)],
        'category': ['A' if i % 3 == 0 else 'B' if i % 3 == 1 else 'C' for i in range(1, 101)],
        'timestamp': pd.date_range(start='2023-01-01', periods=100, freq='H')
    })
    
    # Generate patterns of varying complexity
    patterns = []
    if pattern_complexity == 1:
        # Simple patterns
        for i in range(num_patterns):
            cat1 = 'A' if i % 3 == 0 else 'B' if i % 3 == 1 else 'C'
            cat2 = 'B' if i % 3 == 0 else 'C' if i % 3 == 1 else 'A'
            patterns.append(f"PATTERN ({cat1} {cat2}+)")
    elif pattern_complexity == 2:
        # Medium complexity patterns
        for i in range(num_patterns):
            cat1 = 'A' if i % 3 == 0 else 'B' if i % 3 == 1 else 'C'
            cat2 = 'B' if i % 3 == 0 else 'C' if i % 3 == 1 else 'A'
            cat3 = 'C' if i % 3 == 0 else 'A' if i % 3 == 1 else 'B'
            patterns.append(f"PATTERN ({cat1}+ {cat2}* {cat3}+)")
    else:
        # Complex patterns with alternation and permutation
        for i in range(num_patterns):
            cat1 = 'A' if i % 3 == 0 else 'B' if i % 3 == 1 else 'C'
            cat2 = 'B' if i % 3 == 0 else 'C' if i % 3 == 1 else 'A'
            cat3 = 'C' if i % 3 == 0 else 'A' if i % 3 == 1 else 'B'
            if i % 3 == 0:
                patterns.append(f"PATTERN (({cat1} | {cat2})+ {cat3}*)")
            elif i % 3 == 1:
                patterns.append(f"PATTERN (PERMUTE({cat1}, {cat2}, {cat3}))")
            else:
                patterns.append(f"PATTERN ({cat1}+ {cat2}{{2,5}} {cat3}*)")
    
    # Define base query template
    query_template = """
    SELECT *
    FROM df
    MATCH_RECOGNIZE (
        PARTITION BY category
        ORDER BY timestamp
        MEASURES
            FIRST(A.value) AS first_value,
            LAST(B.value) AS last_value,
            COUNT(*) AS match_length
        {pattern}
        DEFINE
            A AS value > 5,
            B AS value <= 5,
            C AS value = 0
    )
    """
    
    # Start the cache monitor
    monitor = start_cache_monitoring()
    
    # Run the benchmark
    total_time = 0
    try:
        for iteration in range(iterations):
            print(f"\nIteration {iteration+1}/{iterations}")
            
            for i, pattern in enumerate(patterns):
                query = query_template.format(pattern=pattern)
                
                start = time.time()
                result = match_recognize(query, df)
                elapsed = time.time() - start
                total_time += elapsed
                
                # Print progress every 10 patterns
                if (i+1) % 10 == 0:
                    print(f"Processed {i+1}/{num_patterns} patterns")
                    
                    # Print cache stats
                    stats = get_cache_stats()
                    print(f"Cache stats: size={stats.get('size', 0)}, "
                          f"hits={stats.get('hits', 0)}, "
                          f"misses={stats.get('misses', 0)}, "
                          f"efficiency={stats.get('cache_efficiency', 0):.2f}%, "
                          f"memory={stats.get('memory_used_mb', 0):.2f}MB")
            
            # Clear cache between iterations if requested
            if iteration < iterations - 1:
                if args.clear_between_iterations:
                    print("Clearing cache between iterations")
                    clear_pattern_cache()
    finally:
        # Stop the cache monitor
        stop_cache_monitoring()
    
    # Final stats
    stats = get_cache_stats()
    print("\n--- Final Benchmark Results ---")
    print(f"Total execution time: {total_time:.2f}s")
    print(f"Average time per pattern: {total_time/(num_patterns*iterations):.4f}s")
    print(f"Cache efficiency: {stats.get('cache_efficiency', 0):.2f}%")
    print(f"Cache hits: {stats.get('hits', 0)}")
    print(f"Cache misses: {stats.get('misses', 0)}")
    print(f"Compilation time saved: {stats.get('compilation_time_saved', 0):.2f}s")
    print(f"Memory used: {stats.get('memory_used_mb', 0):.2f}MB")

def main():
    # Configure based on arguments
    if args.cache_size:
        resize_cache(args.cache_size)
        print(f"Cache size set to {args.cache_size}")
    
    if args.disable_cache:
        set_caching_enabled(False)
        print("Caching disabled")
    
    # Run the benchmark
    run_benchmark(
        num_patterns=args.num_patterns,
        pattern_complexity=args.complexity,
        iterations=args.iterations
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pattern Caching Benchmark")
    parser.add_argument("--num-patterns", type=int, default=50, help="Number of unique patterns")
    parser.add_argument("--complexity", type=int, choices=[1, 2, 3], default=2, 
                        help="Pattern complexity level (1-3)")
    parser.add_argument("--iterations", type=int, default=3, help="Number of iterations")
    parser.add_argument("--cache-size", type=int, help="Set cache size limit")
    parser.add_argument("--disable-cache", action="store_true", help="Disable caching")
    parser.add_argument("--clear-between-iterations", action="store_true", 
                        help="Clear cache between iterations")
    
    args = parser.parse_args()
    main()
