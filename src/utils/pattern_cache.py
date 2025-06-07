"""
Centralized cache utilities for pattern matching components.
Eliminates duplication of caching logic across different modules.
"""

import hashlib
from typing import Dict, Any, Tuple, List, Callable

# Global pattern cache for compiled patterns
_PATTERN_CACHE = {}

# Cache statistics
CACHE_STATS = {
    'hits': 0, 
    'misses': 0, 
    'compilation_time_saved': 0.0,
    'memory_used_mb': 0.0
}

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
    if key in _PATTERN_CACHE:
        CACHE_STATS['hits'] += 1
        return _PATTERN_CACHE[key]
    return None

def cache_pattern(key: str, dfa: Any, nfa: Any, compilation_time: float) -> None:
    """
    Cache a compiled pattern.
    
    Args:
        key: The cache key
        dfa: The DFA to cache
        nfa: The NFA to cache
        compilation_time: The time it took to compile the pattern
    """
    CACHE_STATS['misses'] += 1
    
    # Simple cache eviction - keep last 100 patterns
    if len(_PATTERN_CACHE) > 100:
        # Remove oldest entry (simple FIFO eviction)
        oldest_key = next(iter(_PATTERN_CACHE))
        del _PATTERN_CACHE[oldest_key]
    
    _PATTERN_CACHE[key] = (dfa, nfa, compilation_time)
    CACHE_STATS['memory_used_mb'] = len(_PATTERN_CACHE) * 0.1  # Rough estimate
