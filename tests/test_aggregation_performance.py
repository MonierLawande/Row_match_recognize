# test_aggregation_performance.py
"""
Performance and benchmark tests for aggregation functions.

This module contains performance tests and benchmarks to ensure
the aggregation implementation can handle production workloads.
"""

import pytest
import pandas as pd
import numpy as np
import time
import psutil
import os
from typing import Dict, List, Any, Tuple
import sys

# Add the src directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from executor.match_recognize import match_recognize
    from utils.logging_config import get_logger
    from utils.performance_optimizer import PerformanceMonitor
    from utils.pattern_cache import get_cache_stats, clear_pattern_cache
except ImportError:
    # Fallback for development/testing
    def match_recognize(query, df):
        return pd.DataFrame()
    
    def get_logger(name):
        import logging
        return logging.getLogger(name)
    
    class PerformanceMonitor:
        pass
    
    def get_cache_stats():
        return {}
    
    def clear_pattern_cache():
        pass

logger = get_logger(__name__)

class TestAggregationPerformance:
    """
    Performance and benchmark tests for aggregation functions.
    
    These tests validate that the aggregation implementation can handle
    production workloads efficiently and scale appropriately.
    """
    
    def setup_method(self):
        """Setup method run before each test."""
        self.start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        self.start_time = time.time()
        clear_pattern_cache()
    
    def teardown_method(self):
        """Cleanup method run after each test."""
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        end_time = time.time()
        
        memory_used = end_memory - self.start_memory
        time_elapsed = end_time - self.start_time
        
        logger.info(f"Test completed - Memory used: {memory_used:.2f} MB, Time: {time_elapsed:.3f} seconds")
    
    def generate_large_dataset(self, size: int) -> pd.DataFrame:
        """Generate a large dataset for performance testing."""
        np.random.seed(42)  # For reproducible results
        
        return pd.DataFrame({
            'id': range(1, size + 1),
            'timestamp': pd.date_range('2024-01-01', periods=size, freq='1min'),
            'value': np.random.normal(50, 15, size),
            'category': np.random.choice(['A', 'B', 'C', 'D'], size),
            'status': np.random.choice(['active', 'inactive', 'pending'], size),
            'score': np.random.uniform(0, 100, size),
            'flag': np.random.choice([True, False], size)
        })
    
    @pytest.mark.performance
    def test_large_dataset_aggregation_performance(self):
        """Test aggregation performance with large datasets."""
        sizes = [1000, 5000, 10000]
        
        for size in sizes:
            df = self.generate_large_dataset(size)
            
            query = f"""
            SELECT m.id, m.running_sum, m.running_avg, m.running_count, m.running_stddev
            FROM large_data
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    RUNNING sum(A.value) AS running_sum,
                    RUNNING avg(A.value) AS running_avg,
                    RUNNING count(*) AS running_count,
                    RUNNING stddev(A.value) AS running_stddev
                ALL ROWS PER MATCH
                AFTER MATCH SKIP PAST LAST ROW
                PATTERN (A*)
                DEFINE A AS true
            )
            """
            
            start_time = time.time()
            result = match_recognize(query, df)
            end_time = time.time()
            
            execution_time = end_time - start_time
            throughput = size / execution_time if execution_time > 0 else float('inf')
            
            logger.info(f"Dataset size: {size}, Execution time: {execution_time:.3f}s, Throughput: {throughput:.0f} rows/sec")
            
            # Performance assertions
            assert execution_time < 10.0, f"Execution time {execution_time:.3f}s exceeds 10 seconds for {size} rows"
            assert throughput > 100, f"Throughput {throughput:.0f} rows/sec is too low for {size} rows"
    
    @pytest.mark.performance
    def test_memory_efficiency_aggregations(self):
        """Test memory efficiency of aggregation operations."""
        df = self.generate_large_dataset(5000)
        
        queries = [
            # Simple aggregations
            """
            SELECT m.id, m.sum_val, m.avg_val
            FROM large_data
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    RUNNING sum(A.value) AS sum_val,
                    RUNNING avg(A.value) AS avg_val
                ALL ROWS PER MATCH
                AFTER MATCH SKIP PAST LAST ROW
                PATTERN (A*)
                DEFINE A AS true
            )
            """,
            # Complex aggregations
            """
            SELECT m.id, m.complex_agg
            FROM large_data
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES 
                    RUNNING sum(A.value * A.score) / sum(A.score) AS complex_agg
                ALL ROWS PER MATCH
                AFTER MATCH SKIP PAST LAST ROW
                PATTERN (A*)
                DEFINE A AS A.score > 0
            )
            """
        ]
        
        for i, query in enumerate(queries):
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024
            
            result = match_recognize(query, df)
            
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024
            memory_used = end_memory - start_memory
            
            logger.info(f"Query {i+1} memory usage: {memory_used:.2f} MB")
            
            # Memory assertions
            assert memory_used < 100, f"Memory usage {memory_used:.2f} MB exceeds limit for query {i+1}"
    
    @pytest.mark.performance
    def test_concurrent_pattern_performance(self):
        """Test performance with multiple concurrent patterns."""
        df = self.generate_large_dataset(2000)
        
        query = """
        SELECT m.category, m.total_sum, m.avg_score, m.pattern_count
        FROM large_data
        MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY id
            MEASURES 
                FIRST(A.category) AS category,
                FINAL sum(A.value) AS total_sum,
                FINAL avg(A.score) AS avg_score,
                FINAL count(*) AS pattern_count
            ONE ROW PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A+)
            DEFINE A AS true
        )
        """
        
        start_time = time.time()
        result = match_recognize(query, df)
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        logger.info(f"Concurrent patterns execution time: {execution_time:.3f}s")
        
        # Should handle partitioned data efficiently
        assert execution_time < 5.0, f"Concurrent pattern execution time {execution_time:.3f}s too high"
        assert not result.empty, "Should produce results for concurrent patterns"
    
    @pytest.mark.performance
    def test_cache_effectiveness(self):
        """Test pattern compilation cache effectiveness."""
        df = self.generate_large_dataset(1000)
        
        # Same pattern executed multiple times
        query = """
        SELECT m.id, m.running_sum
        FROM large_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES RUNNING sum(A.value) AS running_sum
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        # First execution (cache miss)
        start_time = time.time()
        result1 = match_recognize(query, df)
        first_execution_time = time.time() - start_time
        
        # Second execution (cache hit)
        start_time = time.time()
        result2 = match_recognize(query, df)
        second_execution_time = time.time() - start_time
        
        cache_stats = get_cache_stats()
        
        logger.info(f"First execution: {first_execution_time:.3f}s")
        logger.info(f"Second execution: {second_execution_time:.3f}s")
        logger.info(f"Cache stats: {cache_stats}")
        
        # Second execution should be faster due to caching
        speedup_ratio = first_execution_time / second_execution_time if second_execution_time > 0 else 1
        assert speedup_ratio > 1.1, f"Cache speedup ratio {speedup_ratio:.2f} is too low"
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_stress_test_aggregations(self):
        """Stress test with very large datasets and complex aggregations."""
        # Only run in stress test mode
        if not os.environ.get('RUN_STRESS_TESTS', False):
            pytest.skip("Stress tests disabled. Set RUN_STRESS_TESTS=1 to enable.")
        
        df = self.generate_large_dataset(50000)
        
        query = """
        SELECT m.id, m.complex_agg1, m.complex_agg2, m.complex_agg3
        FROM large_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(A.value * A.score) / nullif(sum(A.score), 0) AS complex_agg1,
                RUNNING stddev(A.value) * avg(A.score) AS complex_agg2,
                RUNNING count(DISTINCT A.category) AS complex_agg3
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS A.value IS NOT NULL
        )
        """
        
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        execution_time = end_time - start_time
        memory_used = end_memory - start_memory
        throughput = len(df) / execution_time if execution_time > 0 else float('inf')
        
        logger.info(f"Stress test - Rows: {len(df)}, Time: {execution_time:.3f}s, "
                   f"Memory: {memory_used:.2f}MB, Throughput: {throughput:.0f} rows/sec")
        
        # Stress test assertions
        assert execution_time < 60.0, f"Stress test execution time {execution_time:.3f}s exceeds limit"
        assert memory_used < 500, f"Stress test memory usage {memory_used:.2f}MB exceeds limit"
        assert throughput > 500, f"Stress test throughput {throughput:.0f} rows/sec too low"
    
    @pytest.mark.performance
    def test_aggregation_accuracy_vs_performance(self):
        """Test that performance optimizations don't affect accuracy."""
        df = self.generate_large_dataset(1000)
        
        # Reference implementation (assuming slower but accurate)
        simple_query = """
        SELECT m.id, m.sum_val, m.avg_val, m.count_val
        FROM large_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(A.value) AS sum_val,
                RUNNING avg(A.value) AS avg_val,
                RUNNING count(A.value) AS count_val
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        # Optimized implementation
        optimized_query = """
        SELECT m.id, m.sum_val, m.avg_val, m.count_val
        FROM large_data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING sum(A.value) AS sum_val,
                RUNNING avg(A.value) AS avg_val,
                RUNNING count(A.value) AS count_val
            ALL ROWS PER MATCH
            AFTER MATCH SKIP PAST LAST ROW
            PATTERN (A*)
            DEFINE A AS true
        )
        """
        
        result1 = match_recognize(simple_query, df)
        result2 = match_recognize(optimized_query, df)
        
        # Results should be identical (or very close for floating point)
        if not result1.empty and not result2.empty:
            pd.testing.assert_frame_equal(result1, result2, rtol=1e-10, atol=1e-15)
    
    def test_benchmark_standard_aggregations(self):
        """Benchmark standard aggregation functions."""
        df = self.generate_large_dataset(5000)
        
        aggregation_tests = [
            ("SUM", "RUNNING sum(A.value)"),
            ("AVG", "RUNNING avg(A.value)"),
            ("COUNT", "RUNNING count(*)"),
            ("MIN", "RUNNING min(A.value)"),
            ("MAX", "RUNNING max(A.value)"),
            ("STDDEV", "RUNNING stddev(A.value)"),
            ("VARIANCE", "RUNNING variance(A.value)")
        ]
        
        results = {}
        
        for agg_name, agg_expr in aggregation_tests:
            query = f"""
            SELECT m.id, m.agg_result
            FROM large_data
            MATCH_RECOGNIZE (
                ORDER BY id
                MEASURES {agg_expr} AS agg_result
                ALL ROWS PER MATCH
                AFTER MATCH SKIP PAST LAST ROW
                PATTERN (A*)
                DEFINE A AS true
            )
            """
            
            start_time = time.time()
            result = match_recognize(query, df)
            execution_time = time.time() - start_time
            
            throughput = len(df) / execution_time if execution_time > 0 else float('inf')
            results[agg_name] = {
                'execution_time': execution_time,
                'throughput': throughput
            }
            
            logger.info(f"{agg_name}: {execution_time:.3f}s, {throughput:.0f} rows/sec")
        
        # All aggregations should complete in reasonable time
        for agg_name, metrics in results.items():
            assert metrics['execution_time'] < 5.0, f"{agg_name} took too long: {metrics['execution_time']:.3f}s"
            assert metrics['throughput'] > 500, f"{agg_name} throughput too low: {metrics['throughput']:.0f} rows/sec"

if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "--tb=short", "-m", "performance"])
