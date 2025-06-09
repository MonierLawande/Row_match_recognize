"""
Centralized cache utilities for pattern matching components.
Eliminates duplication of caching logic across different modules.
Provides production-ready caching with LRU eviction policy, memory monitoring,
and detailed performance metrics.
"""

import hashlib
import time
import sys
import threading
from functools import lru_cache
from collections import OrderedDict
from typing import Dict, Any, Tuple, List, Callable, Optional, Union
from src.config.production_config import MatchRecognizeConfig

# Load configuration for cache parameters
try:
    config = MatchRecognizeConfig.from_env()
    CACHE_SIZE_LIMIT = config.performance.cache_size_limit
    ENABLE_CACHING = config.performance.enable_caching
except Exception:
    # Default values if config can't be loaded
    CACHE_SIZE_LIMIT = 10_000
    ENABLE_CACHING = True

# Enhanced pattern cache using OrderedDict for LRU functionality
class LRUPatternCache:
    """
    Thread-safe LRU cache implementation for pattern matching.
    Optimized for production use with memory tracking and metrics.
    """
    def __init__(self, max_size=CACHE_SIZE_LIMIT):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = threading.RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'compilation_time_saved': 0.0,
            'memory_used_mb': 0.0,
            'max_memory_used_mb': 0.0,
            'cache_efficiency': 0.0,
            'last_reset': time.time()
        }
    
    def get(self, key: str) -> Optional[Tuple[Any, Any, float]]:
        """Get an item from the cache with LRU tracking."""
        if not ENABLE_CACHING:
            return None
            
        with self.lock:
            if key in self.cache:
                # Move the accessed item to the end (most recently used)
                value = self.cache.pop(key)
                self.cache[key] = value
                self.stats['hits'] += 1
                self.stats['compilation_time_saved'] += value[2]  # Add compilation time
                return value
            
            self.stats['misses'] += 1
            return None
    
    def put(self, key: str, dfa: Any, nfa: Any, compilation_time: float) -> None:
        """Add an item to the cache with LRU eviction policy."""
        if not ENABLE_CACHING:
            return
            
        with self.lock:
            # Remove oldest item if we're at capacity
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)  # Remove first item (least recently used)
                self.stats['evictions'] += 1
            
            # Store the new item
            self.cache[key] = (dfa, nfa, compilation_time)
            
            # Update memory usage statistics
            self._update_memory_usage()
    
    def _update_memory_usage(self) -> None:
        """Estimate and update memory usage statistics."""
        # Rough estimation of memory usage
        # In a production environment, a more sophisticated tracking would be used
        avg_pattern_size_mb = 0.5  # Average pattern size in MB
        memory_estimate = len(self.cache) * avg_pattern_size_mb
        
        self.stats['memory_used_mb'] = memory_estimate
        if memory_estimate > self.stats['max_memory_used_mb']:
            self.stats['max_memory_used_mb'] = memory_estimate
        
        # Calculate cache efficiency
        total_lookups = self.stats['hits'] + self.stats['misses']
        if total_lookups > 0:
            self.stats['cache_efficiency'] = (self.stats['hits'] / total_lookups) * 100
    
    def clear(self) -> None:
        """Clear the cache and reset statistics."""
        with self.lock:
            self.cache.clear()
            self.stats['evictions'] += 1
            self.stats['memory_used_mb'] = 0.0
            self.stats['last_reset'] = time.time()
    
    def resize(self, new_size: int) -> None:
        """Resize the cache, removing oldest entries if necessary."""
        with self.lock:
            self.max_size = new_size
            while len(self.cache) > new_size:
                self.cache.popitem(last=False)
                self.stats['evictions'] += 1
            self._update_memory_usage()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get a copy of current cache statistics."""
        with self.lock:
            # Calculate cache age
            cache_age_seconds = time.time() - self.stats['last_reset']
            stats_copy = self.stats.copy()
            stats_copy['cache_age_seconds'] = cache_age_seconds
            stats_copy['size'] = len(self.cache)
            stats_copy['max_size'] = self.max_size
            return stats_copy

# Global pattern cache instance
_PATTERN_CACHE = LRUPatternCache(CACHE_SIZE_LIMIT)

# Public API for cache statistics
CACHE_STATS = _PATTERN_CACHE.stats

def get_cache_key(pattern_text: str, define: Dict[str, str] = None, subsets: Dict[str, List[str]] = None) -> str:
    """
    Generate a consistent cache key for pattern caching.
    
    Args:
        pattern_text: The pattern text
        define: Optional define conditions
        subsets: Optional subset definitions
        
    Returns:
        A hash string to use as a cache key
    """
    define_str = str(define) if define else ""
    subset_str = str(subsets) if subsets else ""
    return hashlib.md5(f"{pattern_text}{define_str}{subset_str}".encode()).hexdigest()

def get_cached_pattern(key: str) -> Tuple[Any, Any, float]:
    """
    Get a cached pattern by key.
    
    Args:
        key: The cache key
        
    Returns:
        Tuple of (dfa, nfa, compilation_time) if found in cache, or None
    """
    return _PATTERN_CACHE.get(key)

def cache_pattern(key: str, dfa: Any, nfa: Any, compilation_time: float) -> None:
    """
    Cache a compiled pattern.
    
    Args:
        key: The cache key
        dfa: The DFA to cache
        nfa: The NFA to cache
        compilation_time: The time it took to compile the pattern
    """
    _PATTERN_CACHE.put(key, dfa, nfa, compilation_time)

# Enhanced cache management functions for production use

def get_cache_stats() -> Dict[str, Any]:
    """
    Get detailed cache statistics for monitoring.
    
    Returns:
        Dictionary of cache statistics
    """
    return _PATTERN_CACHE.get_stats()

def clear_pattern_cache() -> None:
    """
    Clear the pattern cache and reset statistics.
    Useful for memory management in long-running applications.
    """
    _PATTERN_CACHE.clear()

def resize_cache(new_size: int) -> None:
    """
    Resize the pattern cache.
    
    Args:
        new_size: New maximum size for the cache
    """
    _PATTERN_CACHE.resize(new_size)

def is_caching_enabled() -> bool:
    """
    Check if caching is currently enabled.
    
    Returns:
        True if caching is enabled, False otherwise
    """
    return ENABLE_CACHING

def set_caching_enabled(enabled: bool) -> None:
    """
    Enable or disable pattern caching.
    
    Args:
        enabled: Whether to enable caching
    """
    global ENABLE_CACHING
    ENABLE_CACHING = enabled
