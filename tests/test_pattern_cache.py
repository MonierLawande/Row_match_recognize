#!/usr/bin/env python3
"""
Unit tests for the enhanced pattern caching system.
These tests verify that the production-ready caching implementation
works correctly under various conditions.
"""

import unittest
import threading
import time
import gc
import pandas as pd
from src.utils.pattern_cache import (
    get_cache_key, get_cached_pattern, cache_pattern, CACHE_STATS,
    get_cache_stats, clear_pattern_cache, resize_cache, 
    is_caching_enabled, set_caching_enabled
)
from src.monitoring.cache_monitor import start_cache_monitoring, stop_cache_monitoring
from src.executor.match_recognize import match_recognize

class MockDFA:
    """Mock DFA for testing."""
    def __init__(self, pattern_id):
        self.pattern_id = pattern_id
    
    def __eq__(self, other):
        if not isinstance(other, MockDFA):
            return False
        return self.pattern_id == other.pattern_id

class MockNFA:
    """Mock NFA for testing."""
    def __init__(self, pattern_id):
        self.pattern_id = pattern_id
        self.exclusion_ranges = []
    
    def __eq__(self, other):
        if not isinstance(other, MockNFA):
            return False
        return self.pattern_id == other.pattern_id

class PatternCacheTests(unittest.TestCase):
    """Test cases for enhanced pattern caching."""
    
    def setUp(self):
        """Set up the test environment."""
        # Ensure caching is enabled
        set_caching_enabled(True)
        # Clear the cache before each test
        clear_pattern_cache()
        # Create test data
        self.test_patterns = [
            ("A+ B+", {"A": "value > 5", "B": "value <= 5"}, {"U": ["A", "B"]}),
            ("A B* C+", {"A": "value > 7", "B": "value <= 7", "C": "value = 0"}, {}),
            ("(A | B)+", {"A": "value > 3", "B": "value <= 3"}, {}),
            ("PERMUTE(A, B, C)", {"A": "value > 5", "B": "value <= 5", "C": "value = 0"}, {}),
            ("A{2,5} B?", {"A": "value > 5", "B": "value <= 5"}, {}),
        ]
    
    def tearDown(self):
        """Clean up after each test."""
        clear_pattern_cache()
        # Stop monitoring if active
        try:
            stop_cache_monitoring()
        except:
            pass
        # Force garbage collection
        gc.collect()
    
    def test_cache_key_generation(self):
        """Test that cache keys are consistent and unique."""
        keys = []
        for pattern, define, subsets in self.test_patterns:
            key = get_cache_key(pattern, define, subsets)
            # Keys should be strings
            self.assertIsInstance(key, str)
            # Keys should be unique
            self.assertNotIn(key, keys)
            keys.append(key)
        
        # Same inputs should produce the same key
        pattern, define, subsets = self.test_patterns[0]
        key1 = get_cache_key(pattern, define, subsets)
        key2 = get_cache_key(pattern, define, subsets)
        self.assertEqual(key1, key2)
    
    def test_basic_caching(self):
        """Test basic caching functionality."""
        pattern, define, subsets = self.test_patterns[0]
        key = get_cache_key(pattern, define, subsets)
        
        # Cache a pattern
        dfa = MockDFA(1)
        nfa = MockNFA(1)
        cache_pattern(key, dfa, nfa, 0.5)
        
        # Retrieve it from cache
        cached = get_cached_pattern(key)
        self.assertIsNotNone(cached)
        cached_dfa, cached_nfa, cached_time = cached
        
        # Verify cached data
        self.assertEqual(cached_dfa, dfa)
        self.assertEqual(cached_nfa, nfa)
        self.assertEqual(cached_time, 0.5)
        
        # Stats should be updated
        stats = get_cache_stats()
        self.assertGreaterEqual(stats.get('hits', 0), 1)
    
    def test_cache_eviction(self):
        """Test that least recently used patterns are evicted."""
        # Cache several patterns
        for i, (pattern, define, subsets) in enumerate(self.test_patterns):
            key = get_cache_key(pattern, define, subsets)
            dfa = MockDFA(i)
            nfa = MockNFA(i)
            cache_pattern(key, dfa, nfa, 0.1)
        
        # Get the current cache size
        initial_size = get_cache_stats().get('size', 0)
        
        # Resize to a smaller size
        resize_cache(2)
        
        # Verify that cache size is reduced
        new_size = get_cache_stats().get('size', 0)
        self.assertLessEqual(new_size, 2)
        
        # The most recently used patterns should still be cached
        key = get_cache_key(*self.test_patterns[-1])
        self.assertIsNotNone(get_cached_pattern(key))
    
    def test_thread_safety(self):
        """Test that the cache is thread-safe."""
        # Prepare test data
        pattern, define, subsets = self.test_patterns[0]
        key = get_cache_key(pattern, define, subsets)
        
        # Function to cache and retrieve in a thread
        def cache_retrieve_thread(thread_id):
            for i in range(50):
                dfa = MockDFA(thread_id * 1000 + i)
                nfa = MockNFA(thread_id * 1000 + i)
                cache_pattern(key, dfa, nfa, 0.1)
                cached = get_cached_pattern(key)
                self.assertIsNotNone(cached)
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=cache_retrieve_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify that the cache is still functional
        cached = get_cached_pattern(key)
        self.assertIsNotNone(cached)
    
    def test_cache_monitoring(self):
        """Test that cache monitoring functions correctly."""
        # Start monitoring
        monitor = start_cache_monitoring()
        self.assertIsNotNone(monitor)
        
        # Cache some patterns
        for i, (pattern, define, subsets) in enumerate(self.test_patterns):
            key = get_cache_key(pattern, define, subsets)
            dfa = MockDFA(i)
            nfa = MockNFA(i)
            cache_pattern(key, dfa, nfa, 0.1)
        
        # Force a check
        stats = monitor.force_check()
        
        # Verify stats
        self.assertIsInstance(stats, dict)
        self.assertIn('size', stats)
        self.assertIn('memory_used_mb', stats)
        
        # Stop monitoring
        stop_cache_monitoring()
    
    def test_cache_disable_enable(self):
        """Test enabling and disabling the cache."""
        pattern, define, subsets = self.test_patterns[0]
        key = get_cache_key(pattern, define, subsets)
        
        # Disable caching
        set_caching_enabled(False)
        self.assertFalse(is_caching_enabled())
        
        # Cache a pattern (should be ignored)
        dfa = MockDFA(1)
        nfa = MockNFA(1)
        cache_pattern(key, dfa, nfa, 0.5)
        
        # Should not be cached
        self.assertIsNone(get_cached_pattern(key))
        
        # Enable caching
        set_caching_enabled(True)
        self.assertTrue(is_caching_enabled())
        
        # Cache again
        cache_pattern(key, dfa, nfa, 0.5)
        
        # Should be cached now
        self.assertIsNotNone(get_cached_pattern(key))
    
    def test_integration_with_match_recognize(self):
        """Test integration with the match_recognize function."""
        # Create a simple dataframe
        df = pd.DataFrame({
            'id': range(1, 11),
            'value': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            'category': ['A', 'B', 'A', 'B', 'A', 'B', 'A', 'B', 'A', 'B']
        })
        
        # Define a query
        query = """
        SELECT *
        FROM df
        MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY id
            MEASURES
                FIRST(A.value) AS first_value,
                LAST(B.value) AS last_value,
                COUNT(*) AS match_length
            PATTERN (A+ B+)
            DEFINE
                A AS value < 5,
                B AS value >= 5
        )
        """
        
        # Clear cache stats
        clear_pattern_cache()
        
        # First execution should be a cache miss
        result1 = match_recognize(query, df)
        stats1 = get_cache_stats()
        misses1 = stats1.get('misses', 0)
        
        # Second execution should be a cache hit
        result2 = match_recognize(query, df)
        stats2 = get_cache_stats()
        hits = stats2.get('hits', 0)
        
        # Verify results are the same
        self.assertEqual(len(result1), len(result2))
        
        # Verify cache was used
        self.assertGreater(hits, 0)

if __name__ == '__main__':
    unittest.main()
