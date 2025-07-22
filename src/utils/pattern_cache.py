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
import re
from functools import lru_cache
from collections import OrderedDict
from typing import Dict, Any, Tuple, List, Callable, Optional, Union
from dataclasses import dataclass
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

# Condition caching structures
@dataclass
class CompiledCondition:
    """Represents a pre-compiled condition with metadata."""
    compiled_func: Callable
    dependencies: List[str]
    complexity_score: float
    template_type: str
    cache_hits: int = 0

class ConditionTemplateCache:
    """Advanced condition compilation caching with template matching."""
    
    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.templates = OrderedDict()
        self.max_size = max_size
        self.lock = threading.RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'template_matches': 0,
            'compilation_time_saved': 0.0
        }
        
        # Pre-compile common condition templates
        self._initialize_common_templates()
    
    def _initialize_common_templates(self):
        """Initialize common condition templates for faster matching."""
        common_patterns = [
            (r'\w+\s*>\s*\d+', 'numeric_comparison'),
            (r'\w+\s*=\s*\w+', 'equality_check'),
            (r'\w+\s+IN\s+\(.*\)', 'in_predicate'),
            (r'\w+\s+LIKE\s+\'.*\'', 'like_pattern'),
            (r'\w+\s+BETWEEN\s+\w+\s+AND\s+\w+', 'range_check')
        ]
        
        for pattern, template_type in common_patterns:
            self.templates[pattern] = template_type
    
    def get(self, condition_text: str) -> Optional[CompiledCondition]:
        """Get cached condition or match against templates."""
        with self.lock:
            # Direct cache hit
            if condition_text in self.cache:
                condition = self.cache.pop(condition_text)
                self.cache[condition_text] = condition  # Move to end
                condition.cache_hits += 1
                self.stats['hits'] += 1
                return condition
            
            # Template matching for similar patterns
            for template_pattern, template_type in self.templates.items():
                if re.match(template_pattern, condition_text, re.IGNORECASE):
                    self.stats['template_matches'] += 1
                    # Create a new condition based on template
                    return self._create_from_template(condition_text, template_type)
            
            self.stats['misses'] += 1
            return None
    
    def _create_from_template(self, condition_text: str, template_type: str) -> CompiledCondition:
        """Create a condition from a template match."""
        # For now, return None to disable template-based condition creation
        # This ensures we don't interfere with existing condition evaluation
        return None
    
    def put(self, condition_text: str, condition: CompiledCondition):
        """Add condition to cache with LRU eviction."""
        with self.lock:
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)
            self.cache[condition_text] = condition

# Tokenization optimization structures
@dataclass
class TokenCache:
    """Cache for tokenized patterns."""
    tokens: List[str]
    token_types: List[str]
    complexity: float
    fragments: Dict[str, List[str]]

class TokenizationOptimizer:
    """Optimizes pattern tokenization with caching and templates."""
    
    def __init__(self, max_cache_size: int = 500):
        self.cache = OrderedDict()
        self.fragment_cache = OrderedDict()
        self.max_cache_size = max_cache_size
        self.lock = threading.RLock()
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'fragment_reuse': 0,
            'tokenization_time_saved': 0.0
        }
    
    def get_tokens(self, pattern: str) -> Optional[TokenCache]:
        """Get cached tokenization result."""
        with self.lock:
            if pattern in self.cache:
                result = self.cache.pop(pattern)
                self.cache[pattern] = result  # Move to end
                self.stats['cache_hits'] += 1
                return result
            
            self.stats['cache_misses'] += 1
            return None
    
    def cache_tokens(self, pattern: str, tokens: List[str], token_types: List[str]):
        """Cache tokenization result with fragment analysis."""
        with self.lock:
            if len(self.cache) >= self.max_cache_size:
                self.cache.popitem(last=False)
            
            # Analyze fragments for reuse
            fragments = self._analyze_fragments(tokens)
            complexity = len(tokens) + len(set(token_types))
            
            cache_entry = TokenCache(
                tokens=tokens,
                token_types=token_types,
                complexity=complexity,
                fragments=fragments
            )
            
            self.cache[pattern] = cache_entry
            self._update_fragment_cache(fragments)
    
    def _analyze_fragments(self, tokens: List[str]) -> Dict[str, List[str]]:
        """Analyze common fragments in tokenized patterns."""
        fragments = {}
        
        # Look for common subsequences
        for i in range(len(tokens)):
            for j in range(i + 2, min(i + 5, len(tokens) + 1)):
                fragment = ' '.join(tokens[i:j])
                if fragment not in fragments:
                    fragments[fragment] = tokens[i:j]
        
        return fragments
    
    def _update_fragment_cache(self, fragments: Dict[str, List[str]]):
        """Update the global fragment cache."""
        for fragment, tokens in fragments.items():
            if fragment in self.fragment_cache:
                self.stats['fragment_reuse'] += 1
            self.fragment_cache[fragment] = tokens
            
            # Keep fragment cache size manageable
            if len(self.fragment_cache) > self.max_cache_size:
                self.fragment_cache.popitem(last=False)

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
        """Get an item from the cache with enhanced LRU tracking."""
        if not ENABLE_CACHING:
            return None
            
        with self.lock:
            if key in self.cache:
                # Move the accessed item to the end (most recently used)
                dfa, nfa, comp_time, metadata = self.cache.pop(key)
                
                # Update access statistics
                metadata['access_count'] += 1
                metadata['last_access'] = time.time()
                
                # Put back at the end
                self.cache[key] = (dfa, nfa, comp_time, metadata)
                
                self.stats['hits'] += 1
                self.stats['compilation_time_saved'] += comp_time
                return (dfa, nfa, comp_time)
            
            self.stats['misses'] += 1
            return None
    
    def put(self, key: str, dfa: Any, nfa: Any, compilation_time: float) -> None:
        """Add an item to the cache with enhanced LRU eviction policy."""
        if not ENABLE_CACHING:
            return
            
        with self.lock:
            # Smart eviction based on usage patterns and memory pressure
            while len(self.cache) >= self.max_size:
                self._smart_eviction()
                self.stats['evictions'] += 1
            
            # Store the new item with timestamp and access count
            entry_metadata = {
                'timestamp': time.time(),
                'access_count': 0,
                'compilation_time': compilation_time,
                'estimated_size': self._estimate_entry_size(dfa, nfa)
            }
            self.cache[key] = (dfa, nfa, compilation_time, entry_metadata)
            
            # Update memory usage statistics
            self._update_memory_usage()
    
    def _smart_eviction(self) -> None:
        """Enhanced eviction policy considering access patterns and memory usage."""
        if not self.cache:
            return
            
        # Calculate eviction score for each entry
        current_time = time.time()
        eviction_scores = []
        
        for key, (dfa, nfa, comp_time, metadata) in self.cache.items():
            # Score based on: recency, access frequency, size, and compilation time
            age = current_time - metadata['timestamp']
            access_frequency = metadata['access_count'] / max(age / 3600, 1)  # accesses per hour
            size_penalty = metadata['estimated_size']
            compilation_value = comp_time  # Higher compilation time = more valuable to keep
            
            # Lower score = better candidate for eviction
            score = (age / 3600) + size_penalty - (access_frequency * 10) - (compilation_value * 5)
            eviction_scores.append((score, key))
        
        # Remove the entry with the highest eviction score
        eviction_scores.sort(reverse=True)
        key_to_evict = eviction_scores[0][1]
        self.cache.pop(key_to_evict, None)
    
    def _estimate_entry_size(self, dfa: Any, nfa: Any) -> float:
        """Estimate the memory size of a cache entry in MB."""
        # Simplified size estimation - in production, use more sophisticated tracking
        try:
            dfa_states = len(dfa.states) if hasattr(dfa, 'states') else 10
            nfa_states = len(nfa.states) if hasattr(nfa, 'states') else 10
            
            # Rough estimation: each state ~1KB, transitions ~500B each
            estimated_size_bytes = (dfa_states * 1024) + (nfa_states * 512)
            return estimated_size_bytes / (1024 * 1024)  # Convert to MB
        except:
            return 0.5  # Default estimate
    
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

# Global cache instances
_PATTERN_CACHE = LRUPatternCache(CACHE_SIZE_LIMIT)
_CONDITION_CACHE = ConditionTemplateCache()
_TOKENIZATION_OPTIMIZER = TokenizationOptimizer()

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

def get_pattern_cache():
    """
    Get the global pattern cache instance.
    
    Returns:
        LRUPatternCache: The global cache instance
    """
    return _PATTERN_CACHE

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

# Enhanced condition caching API
def get_cached_condition(condition_text: str) -> Optional[CompiledCondition]:
    """Get a cached compiled condition."""
    return _CONDITION_CACHE.get(condition_text)

def cache_condition(condition_text: str, condition: CompiledCondition) -> None:
    """Cache a compiled condition."""
    _CONDITION_CACHE.put(condition_text, condition)

def get_condition_cache_stats() -> Dict[str, Any]:
    """Get condition cache statistics."""
    return _CONDITION_CACHE.stats.copy()

# Enhanced tokenization optimization API
def get_cached_tokens(pattern: str) -> Optional[TokenCache]:
    """Get cached tokenization result."""
    return _TOKENIZATION_OPTIMIZER.get_tokens(pattern)

def cache_tokenization(pattern: str, tokens: List[str], token_types: List[str]) -> None:
    """Cache tokenization result."""
    _TOKENIZATION_OPTIMIZER.cache_tokens(pattern, tokens, token_types)

def get_tokenization_stats() -> Dict[str, Any]:
    """Get tokenization cache statistics."""
    return _TOKENIZATION_OPTIMIZER.stats.copy()

def get_all_cache_stats() -> Dict[str, Any]:
    """Get comprehensive cache statistics for all caching systems."""
    return {
        'pattern_cache': get_cache_stats(),
        'condition_cache': get_condition_cache_stats(),
        'tokenization_cache': get_tokenization_stats()
    }
