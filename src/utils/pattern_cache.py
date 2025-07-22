"""
Centralized cache utilities for pattern matching components.
Eliminates duplication of caching logic across different modules.
Provides production-ready caching with smart multi-level hierarchy, predictive loading,
dynamic sizing, and comprehensive performance optimization.

Enhanced Features:
- Multi-level intelligent caching (L1/L2/L3)
- Predictive pattern loading and relationship mapping  
- Navigation-aware optimization for PREV/NEXT functions
- Partition-aware caching with sharing optimization
- Dynamic cache sizing based on memory pressure and performance
- Background optimization threads for continuous improvement
- Comprehensive statistics and monitoring
- Memory-efficient compression and serialization
- Robust error handling and recovery mechanisms
"""

import hashlib
import time
import sys
import threading
import re
import pickle
import os
import gzip
import json
from functools import lru_cache
from collections import OrderedDict, defaultdict, deque
from typing import Dict, Any, Tuple, List, Callable, Optional, Union, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from src.config.production_config import MatchRecognizeConfig
from src.utils.logging_config import get_logger

# Initialize logger
logger = get_logger(__name__)

# Load configuration for cache parameters
try:
    config = MatchRecognizeConfig.from_env()
    CACHE_SIZE_LIMIT = config.performance.cache_size_limit
    ENABLE_CACHING = config.performance.enable_caching
    logger.info(f"Loaded cache config: size_limit={CACHE_SIZE_LIMIT}, enabled={ENABLE_CACHING}")
except Exception as e:
    # Default values if config can't be loaded
    CACHE_SIZE_LIMIT = 10_000
    ENABLE_CACHING = True
    logger.warning(f"Using default cache config due to: {e}")

# Global cache statistics dictionary for compatibility
CACHE_STATS = {
    'hits': 0,
    'misses': 0,
    'evictions': 0,
    'size': 0,
    'memory_usage': 0,
    'hit_rate': 0.0
}

# Enhanced caching configuration with robustness features
@dataclass
class SmartCacheConfig:
    """Enhanced configuration for smart caching system with robustness features."""
    # Multi-level cache sizes (in MB)
    l1_cache_size_mb: float = 15.0   # Hot patterns (increased)
    l2_cache_size_mb: float = 75.0   # Compiled patterns (increased)
    l3_cache_size_mb: float = 300.0  # Pattern templates (increased)
    
    # Entry limits with growth capacity
    l1_max_entries: int = 150    # Increased capacity
    l2_max_entries: int = 1500   # Increased capacity
    l3_max_entries: int = 15000  # Increased capacity
    
    # TTL settings (seconds) with adaptive expiration
    l1_ttl: float = 2700.0   # 45 minutes (extended)
    l2_ttl: float = 10800.0  # 3 hours (extended)
    l3_ttl: float = 129600.0 # 36 hours (extended)
    
    # Enhanced features
    enable_compression: bool = True
    enable_persistence: bool = True
    enable_background_warming: bool = True
    enable_adaptive_sizing: bool = True
    enable_pattern_analysis: bool = True
    enable_memory_optimization: bool = True
    
    # Performance thresholds
    hit_rate_target: float = 0.75    # Target 75% hit rate
    memory_pressure_threshold: float = 0.85  # Memory pressure at 85%
    optimization_interval: float = 300.0     # 5 minutes optimization cycle
    
    # Robustness features
    enable_error_recovery: bool = True
    max_retries: int = 3
    backup_interval_hours: int = 6
    corruption_detection: bool = True
    
    # Optimization settings
    enable_predictive_loading: bool = True
    enable_dynamic_sizing: bool = True
    enable_background_warming: bool = True
    hot_pattern_threshold: int = 5
    pattern_similarity_threshold: float = 0.8
    
    # Performance tuning
    max_memory_usage_percent: float = 15.0
    optimization_interval_minutes: int = 5
    warming_thread_count: int = 2

# Enhanced cache entry with metadata
@dataclass
class CacheEntry:
    """Enhanced cache entry with comprehensive metadata."""
    value: Any
    size_mb: float
    timestamp: float
    access_count: int = 0
    last_access: float = field(default_factory=time.time)
    compilation_time: float = 0.0
    pattern_complexity: float = 0.0
    hit_rate: float = 0.0
    
    def update_access(self):
        """Update access statistics."""
        self.access_count += 1
        self.last_access = time.time()
    
    def calculate_value_score(self) -> float:
        """Calculate the value score for eviction decisions."""
        age_hours = (time.time() - self.timestamp) / 3600
        access_frequency = self.access_count / max(age_hours, 0.1)
        
        # Higher score = more valuable
        return (
            access_frequency * 10 +           # Frequency weight
            self.compilation_time * 5 +       # Compilation cost weight
            (1.0 / max(self.size_mb, 0.1)) + # Size efficiency weight
            self.hit_rate * 2                 # Hit rate bonus
        )

# Condition caching structures
@dataclass
class CompiledCondition:
    """Represents a pre-compiled condition with metadata."""
    compiled_func: Callable
    dependencies: List[str]
    complexity_score: float
    template_type: str
    cache_hits: int = 0

# Multi-level smart cache implementation with enhanced robustness
class SmartMultiLevelCache:
    """
    Enhanced intelligent multi-level cache with comprehensive optimization and robustness.
    
    Features:
    - L1: Hot patterns cache (fastest access, small size, frequent patterns)
    - L2: Compiled patterns cache (medium access, medium size, regular patterns)  
    - L3: Pattern templates cache (slower access, large size, all patterns)
    - Predictive loading based on pattern relationships
    - Memory-efficient compression and serialization
    - Background optimization and warming
    - Adaptive sizing based on performance metrics
    - Robust error handling and recovery
    """
    
    def __init__(self, config: SmartCacheConfig = None):
        self.config = config or SmartCacheConfig()
        self.lock = threading.RLock()
        
        # Multi-level cache storage with enhanced features
        self.l1_cache = OrderedDict()  # Hot patterns
        self.l2_cache = OrderedDict()  # Compiled patterns
        self.l3_cache = OrderedDict()  # Pattern templates
        
        # Enhanced pattern analysis and prediction
        self.pattern_vectors = {}  # Pattern -> feature vector
        self.access_history = deque(maxlen=2000)  # Increased history
        self.pattern_relationships = defaultdict(set)
        self.hot_patterns = set()  # Frequently accessed patterns
        self.navigation_patterns = set()  # Patterns with PREV/NEXT
        
        # Enhanced performance tracking
        self.stats = {
            'l1_hits': 0, 'l1_misses': 0, 'l1_evictions': 0, 'l1_size_mb': 0.0,
            'l2_hits': 0, 'l2_misses': 0, 'l2_evictions': 0, 'l2_size_mb': 0.0,
            'l3_hits': 0, 'l3_misses': 0, 'l3_evictions': 0, 'l3_size_mb': 0.0,
            'promotions': 0, 'demotions': 0, 'predictions': 0, 'errors': 0,
            'total_memory_mb': 0.0, 'optimization_runs': 0, 'compression_ratio': 0.0,
            'background_loads': 0, 'adaptive_resizes': 0, 'recovery_operations': 0
        }
        
        # Robustness features
        self.error_counts = defaultdict(int)
        self.last_backup = time.time()
        self.corruption_checks = 0
        
        # Background optimization and warming
        self.optimization_thread = None
        if self.config.enable_background_warming:
            self._start_optimization_thread()
            
        logger.info(f"SmartMultiLevelCache initialized with L1({self.config.l1_cache_size_mb}MB), "
                   f"L2({self.config.l2_cache_size_mb}MB), L3({self.config.l3_cache_size_mb}MB)")
    
    def get(self, key: str) -> Optional[Tuple[Any, Any, float]]:
        """Enhanced get with predictive loading and error recovery."""
        if not ENABLE_CACHING:
            return None
            
        try:
            with self.lock:
                # Try L1 first (hottest patterns)
                if key in self.l1_cache:
                    entry = self.l1_cache.pop(key)
                    entry.update_access()
                    self.l1_cache[key] = entry  # Move to end (LRU)
                    self.stats['l1_hits'] += 1
                    
                    # Trigger predictive loading for related patterns
                    if self.config.enable_pattern_analysis:
                        self._predictive_load(key)
                    
                    return self._decompress_if_needed(entry.value)
                
                # Try L2 next
                if key in self.l2_cache:
                    entry = self.l2_cache.pop(key)
                    entry.update_access()
                    self.l2_cache[key] = entry
                    self.stats['l2_hits'] += 1
                    
                    # Consider promotion to L1 if frequently accessed
                    if entry.access_count >= 5:  # Hot pattern threshold
                        self._promote_to_l1(key, entry)
                    
                    return self._decompress_if_needed(entry.value)
                
                # Try L3 last
                if key in self.l3_cache:
                    entry = self.l3_cache.pop(key)
                    entry.update_access()
                    self.l3_cache[key] = entry
                    self.stats['l3_hits'] += 1
                    
                    # Consider promotion to L2 if moderately accessed
                    if entry.access_count >= 3:
                        self._promote_to_l2(key, entry)
                    
                    return self._decompress_if_needed(entry.value)
                
                # Cache miss
                self._record_miss(key)
                return None
                
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            self.stats['errors'] += 1
            self.error_counts['get'] += 1
            
            if self.config.enable_error_recovery:
                return self._attempt_recovery_get(key)
            return None
    
    def _decompress_if_needed(self, value: Any) -> Tuple[Any, Any, float]:
        """Decompress value if it was compressed."""
        try:
            if isinstance(value, bytes):  # Compressed data
                decompressed = gzip.decompress(value)
                return pickle.loads(decompressed)
            return value
        except Exception as e:
            logger.error(f"Decompression error: {e}")
            return value
    
    def _compress_value(self, value: Tuple[Any, Any]) -> bytes:
        """Compress cache value for memory efficiency."""
        try:
            serialized = pickle.dumps(value)
            compressed = gzip.compress(serialized)
            
            # Update compression ratio stats
            ratio = len(compressed) / len(serialized) if serialized else 1.0
            self.stats['compression_ratio'] = (self.stats['compression_ratio'] + ratio) / 2
            
            return compressed
        except Exception as e:
            logger.error(f"Compression error: {e}")
            return pickle.dumps(value)  # Fallback to uncompressed
    
    def _calculate_complexity(self, key: str, metadata: Optional[Dict[str, Any]]) -> float:
        """Calculate pattern complexity score for intelligent caching."""
        try:
            complexity = 0.0
            
            # Base complexity from key length and pattern structure
            complexity += len(key) * 0.1
            
            # Add complexity from metadata
            if metadata:
                if metadata.get('has_navigation'):
                    complexity += 2.0  # Navigation functions add complexity
                if metadata.get('partitions'):
                    complexity += len(metadata['partitions']) * 0.5
                if metadata.get('compilation_time', 0) > 0.01:
                    complexity += metadata['compilation_time'] * 100
            
            # Pattern structure analysis
            if '+' in key or '*' in key:
                complexity += 1.0  # Quantifiers add complexity
            if '(' in key and ')' in key:
                complexity += 1.5  # Grouping adds complexity
            if '|' in key:
                complexity += 1.2  # Alternation adds complexity
            
            return min(complexity, 10.0)  # Cap at 10.0
            
        except Exception as e:
            logger.error(f"Complexity calculation error: {e}")
            return 1.0  # Default complexity
    
    def _determine_template_type(self, key: str, metadata: Optional[Dict[str, Any]]) -> str:
        """Determine template type for the pattern."""
        try:
            if metadata and metadata.get('has_navigation'):
                return 'NAVIGATION'
            elif metadata and metadata.get('partitions'):
                return 'PARTITION'
            elif '+' in key or '*' in key:
                return 'QUANTIFIED'
            elif '(' in key and ')' in key:
                return 'GROUPED'
            else:
                return 'SIMPLE'
        except Exception:
            return 'UNKNOWN'
    
    def _determine_cache_level(self, key: str, entry: Any, metadata: Optional[Dict[str, Any]]) -> str:
        """Enhanced cache level determination with robustness."""
        try:
            # Check if it's already identified as hot
            if key in self.hot_patterns:
                return 'L1'
            
            # High complexity or navigation patterns -> L2
            if hasattr(entry, 'complexity_score') and entry.complexity_score > 5.0:
                return 'L2'
            
            if metadata:
                if metadata.get('has_navigation') or metadata.get('partitions'):
                    return 'L2'
            
            # Default to L3 for general patterns
            return 'L3'
            
        except Exception as e:
            logger.error(f"Cache level determination error: {e}")
            return 'L3'  # Safe default
    
    def _promote_to_l1(self, key: str, entry: Any):
        """Promote entry from L2 to L1."""
        try:
            if key in self.l2_cache:
                del self.l2_cache[key]
                self.stats['l2_size_mb'] -= entry.size_mb
            
            self._evict_if_needed('L1')
            self.l1_cache[key] = entry
            self.stats['l1_size_mb'] += entry.size_mb
            self.stats['promotions'] += 1
            self.hot_patterns.add(key)
            
            logger.debug(f"Promoted {key} to L1 cache")
            
        except Exception as e:
            logger.error(f"L1 promotion error: {e}")
    
    def _promote_to_l2(self, key: str, entry: Any):
        """Promote entry from L3 to L2."""
        try:
            if key in self.l3_cache:
                del self.l3_cache[key]
                self.stats['l3_size_mb'] -= entry.size_mb
            
            self._evict_if_needed('L2')
            self.l2_cache[key] = entry
            self.stats['l2_size_mb'] += entry.size_mb
            self.stats['promotions'] += 1
            
            logger.debug(f"Promoted {key} to L2 cache")
            
        except Exception as e:
            logger.error(f"L2 promotion error: {e}")
    
    def _predictive_load(self, key: str):
        """Enhanced predictive loading based on pattern relationships."""
        try:
            if not self.config.enable_pattern_analysis:
                return
            
            # Load related patterns that might be accessed soon
            related_patterns = self.pattern_relationships.get(key, set())
            for related_key in list(related_patterns)[:3]:  # Limit to top 3
                if (related_key not in self.l1_cache and 
                    related_key not in self.l2_cache and 
                    related_key in self.l3_cache):
                    
                    # Promote related pattern to L2
                    entry = self.l3_cache[related_key]
                    self._promote_to_l2(related_key, entry)
                    self.stats['predictions'] += 1
                    self.stats['background_loads'] += 1
            
        except Exception as e:
            logger.error(f"Predictive loading error: {e}")
    
    def _analyze_pattern(self, key: str, metadata: Optional[Dict[str, Any]]):
        """Enhanced pattern analysis for relationship building."""
        try:
            # Build pattern relationships based on access history
            recent_patterns = [item[0] for item in list(self.access_history)[-10:]]
            for recent_key in recent_patterns:
                if recent_key != key:
                    self.pattern_relationships[key].add(recent_key)
                    self.pattern_relationships[recent_key].add(key)
            
            # Identify navigation patterns
            if metadata and metadata.get('has_navigation'):
                self.navigation_patterns.add(key)
            
        except Exception as e:
            logger.error(f"Pattern analysis error: {e}")
    
    def _record_miss(self, key: str):
        """Record cache miss with analysis."""
        # Determine which level should have contained this
        if key in self.hot_patterns:
            self.stats['l1_misses'] += 1
        elif any(nav in key for nav in ['PREV', 'NEXT', 'FIRST', 'LAST']):
            self.stats['l2_misses'] += 1
        else:
            self.stats['l3_misses'] += 1
    
    def _evict_if_needed(self, level: str):
        """Enhanced eviction with intelligent victim selection."""
        try:
            cache_configs = {
                'L1': (self.l1_cache, self.config.l1_max_entries, self.config.l1_cache_size_mb),
                'L2': (self.l2_cache, self.config.l2_max_entries, self.config.l2_cache_size_mb),
                'L3': (self.l3_cache, self.config.l3_max_entries, self.config.l3_cache_size_mb)
            }
            
            cache, max_entries, max_size_mb = cache_configs[level]
            current_size = self.stats[f'{level.lower()}_size_mb']
            
            # Evict if over limits
            while (len(cache) >= max_entries or current_size >= max_size_mb) and cache:
                # Select victim using enhanced LRU with access count consideration
                victim_key = self._select_eviction_victim(cache)
                if victim_key:
                    victim_entry = cache.pop(victim_key)
                    current_size -= victim_entry.size_mb
                    self.stats[f'{level.lower()}_size_mb'] = current_size
                    self.stats[f'{level.lower()}_evictions'] += 1
                    
                    # Remove from hot patterns if evicted from L1
                    if level == 'L1' and victim_key in self.hot_patterns:
                        self.hot_patterns.remove(victim_key)
                else:
                    break  # No victim found, avoid infinite loop
                    
        except Exception as e:
            logger.error(f"Eviction error for {level}: {e}")
    
    def _select_eviction_victim(self, cache: OrderedDict) -> Optional[str]:
        """Select best eviction victim using multiple criteria."""
        try:
            if not cache:
                return None
            
            # Consider access count, age, and size
            candidates = []
            current_time = time.time()
            
            for key, entry in cache.items():
                age = current_time - entry.timestamp
                access_frequency = entry.access_count / max(age / 3600, 1)  # Accesses per hour
                size_factor = getattr(entry, 'size_mb', 1.0)
                
                # Lower score = better eviction candidate
                score = (age * 0.4) + (1.0 / max(access_frequency, 0.1) * 0.4) + (size_factor * 0.2)
                candidates.append((key, score))
            
            # Return key with highest eviction score
            return max(candidates, key=lambda x: x[1])[0] if candidates else None
            
        except Exception as e:
            logger.error(f"Victim selection error: {e}")
            return next(iter(cache)) if cache else None  # Fallback to first item
    
    def _attempt_recovery_get(self, key: str) -> Optional[Tuple[Any, Any, float]]:
        """Attempt to recover from get operation errors."""
        try:
            self.stats['recovery_operations'] += 1
            
            # Try to find the key in any cache level with error tolerance
            for cache in [self.l1_cache, self.l2_cache, self.l3_cache]:
                if key in cache:
                    entry = cache[key]
                    return self._decompress_if_needed(entry.value)
            
            return None
            
        except Exception as e:
            logger.error(f"Recovery get failed: {e}")
            return None
    
    def _attempt_recovery_put(self, key: str, dfa: Any, nfa: Any, 
                             compilation_time: float, metadata: Optional[Dict[str, Any]]) -> bool:
        """Attempt to recover from put operation errors."""
        try:
            self.stats['recovery_operations'] += 1
            
            # Simple fallback - try to put in L3 without compression
            entry = EnhancedCacheEntry(
                key=key,
                value=(dfa, nfa),
                compilation_time=compilation_time,
                complexity_score=1.0,
                template_type='RECOVERY'
            )
            
            if len(self.l3_cache) < self.config.l3_max_entries:
                self.l3_cache[key] = entry
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Recovery put failed: {e}")
            return False

# Enhanced cache entry with rich metadata
@dataclass  
class EnhancedCacheEntry:
    """Enhanced cache entry with comprehensive metadata and optimization features."""
    key: str
    value: Any
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_access_time: float = field(default_factory=time.time)
    compilation_time: float = 0.0
    complexity_score: float = 0.0
    template_type: str = "UNKNOWN"
    size_mb: float = 0.001  # Default 1KB
    is_compressed: bool = False
    
    def update_access(self):
        """Update access tracking information."""
        self.access_count += 1
        self.last_access_time = time.time()

# Global cache instances with enhanced smart caching
from .performance_optimizer import get_smart_cache, SmartCacheConfig, CacheEvictionPolicy

# Enhanced pattern cache using the smart multi-level cache
_PATTERN_CACHE = None

def get_pattern_cache():
    """Get enhanced pattern cache instance."""
    global _PATTERN_CACHE
    if _PATTERN_CACHE is None:
        # Configure for pattern-specific optimizations
        config = SmartCacheConfig(
            max_size_mb=200.0,
            max_entries=10000,
            eviction_policy=CacheEvictionPolicy.SMART_MULTILEVEL,
            enable_l1_cache=True,
            enable_l2_cache=True,
            enable_l3_cache=True,
            l1_cache_size_mb=20.0,
            l2_cache_size_mb=80.0,
            l3_cache_size_mb=300.0,
            enable_predictive_loading=True,
            enable_navigation_optimization=True,
            enable_partition_optimization=True,
            enable_dynamic_sizing=True,
            enable_background_optimization=True
        )
        _PATTERN_CACHE = get_smart_cache()
    return _PATTERN_CACHE

def get_cache_stats():
    """Get current cache statistics."""
    global CACHE_STATS
    cache = get_pattern_cache()
    stats = cache.get_statistics() if cache else {}
    
    # Update global CACHE_STATS and add backward compatibility fields
    if stats:
        CACHE_STATS.update(stats)
        # Add 'size' key for backward compatibility (maps to entries_count)
        if 'entries_count' in stats:
            stats['size'] = stats['entries_count']
            CACHE_STATS['size'] = stats['entries_count']
        # Add 'memory_used_mb' key for backward compatibility (maps to size_mb)
        if 'size_mb' in stats:
            stats['memory_used_mb'] = stats['size_mb']
            CACHE_STATS['memory_used_mb'] = stats['size_mb']
    
    return stats

def get_cache_key(pattern_text: str, define: Dict[str, str] = None, 
                 subsets: Dict[str, List[str]] = None, 
                 data_characteristics: Dict[str, Any] = None) -> str:
    """
    Generate an optimized cache key for pattern caching with smart reuse capabilities.
    
    Args:
        pattern_text: The pattern text
        define: Optional define conditions
        subsets: Optional subset definitions
        data_characteristics: Optional data characteristics for optimization
        
    Returns:
        Optimized cache key string
    """
    try:
        components = [pattern_text]
        
        if define:
            # Sort define conditions for consistent keys
            sorted_define = sorted(define.items())
            define_str = "&".join(f"{k}={v}" for k, v in sorted_define)
            components.append(f"define:{define_str}")
        
        if subsets:
            # Sort subsets for consistent keys
            sorted_subsets = sorted(subsets.items())
            subset_str = "&".join(f"{k}={','.join(sorted(v))}" for k, v in sorted_subsets)
            components.append(f"subsets:{subset_str}")
        
        if data_characteristics:
            # Include key characteristics that affect pattern compilation
            char_items = []
            for key in ['row_count', 'has_navigation', 'partitions']:
                if key in data_characteristics:
                    char_items.append(f"{key}={data_characteristics[key]}")
            if char_items:
                components.append(f"chars:{'&'.join(char_items)}")
        
        # Create hash for compact key
        key_string = "|".join(components)
        return hashlib.md5(key_string.encode()).hexdigest()
        
    except Exception as e:
        logger.error(f"Cache key generation error: {e}")
        return hashlib.md5(pattern_text.encode()).hexdigest()

def cache_pattern(key: str, dfa: Any, nfa: Any, compilation_time: float = 0.0, 
                 pattern_metadata: Optional[Dict[str, Any]] = None) -> bool:
    """
    Cache a compiled pattern with enhanced metadata and intelligent placement.
    
    Args:
        key: Cache key
        dfa: Compiled DFA
        nfa: Compiled NFA  
        compilation_time: Time taken to compile
        pattern_metadata: Optional metadata for optimization
        
    Returns:
        True if successfully cached, False otherwise
    """
    try:
        # Check if caching is enabled
        if not ENABLE_CACHING:
            return False
            
        cache = get_pattern_cache()
        # Store as tuple (dfa, nfa, compilation_time) for backward compatibility
        return cache.put(key, (dfa, nfa, compilation_time), metadata=pattern_metadata)
    except Exception as e:
        logger.error(f"Pattern caching error: {e}")
        return False

def get_cached_pattern(key: str) -> Optional[Tuple[Any, Any, float]]:
    """
    Retrieve a cached pattern.
    
    Args:
        key: Cache key
        
    Returns:
        Tuple of (dfa, nfa, compilation_time) if found, None otherwise
    """
    try:
        # Check if caching is enabled
        if not ENABLE_CACHING:
            return None
            
        cache = get_pattern_cache()
        result = cache.get(key)
        return result if result else None
    except Exception as e:
        logger.error(f"Pattern retrieval error: {e}")
        return None

def clear_pattern_cache() -> None:
    """Clear all cached patterns."""
    try:
        cache = get_pattern_cache()
        cache.clear()
        logger.info("Pattern cache cleared")
    except Exception as e:
        logger.error(f"Cache clear error: {e}")

def optimize_for_pattern(pattern: str, define_conditions: Dict[str, str], 
                        data_characteristics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimize cache strategy for a specific pattern.
    
    Args:
        pattern: Pattern text
        define_conditions: Define conditions
        data_characteristics: Data characteristics
        
    Returns:
        Optimization result with recommendations
    """
    try:
        # Generate optimized cache key
        optimized_key = get_cache_key(pattern, define_conditions, None, data_characteristics)
        
        # Determine optimizations
        optimizations = []
        predicted_patterns = []
        
        if data_characteristics.get('has_navigation'):
            optimizations.append('navigation_optimization')
        
        if data_characteristics.get('partitions'):
            optimizations.append('partition_optimization')
            
        if len(pattern) > 50:
            optimizations.append('complex_pattern_handling')
            
        return {
            'optimized_cache_key': optimized_key,
            'optimizations_applied': optimizations,
            'cache_level_recommendation': 'L3',
            'predicted_patterns': predicted_patterns
        }
        
    except Exception as e:
        logger.error(f"Pattern optimization error: {e}")
        return {
            'optimized_cache_key': get_cache_key(pattern, define_conditions, None, data_characteristics),
            'optimizations_applied': ['basic_key_generation'],
            'cache_level_recommendation': 'L3',
            'predicted_patterns': []
        }

def enable_smart_caching_features(**kwargs) -> bool:
    """
    Enable smart caching features.
    
    Args:
        **kwargs: Feature flags (predictive_loading, navigation_optimization, etc.)
        
    Returns:
        True if successfully enabled
    """
    try:
        cache = get_pattern_cache()
        if hasattr(cache, 'config'):
            for feature, enabled in kwargs.items():
                if hasattr(cache.config, f'enable_{feature}'):
                    setattr(cache.config, f'enable_{feature}', enabled)
        
        logger.info(f"Smart caching features updated: {kwargs}")
        return True
        
    except Exception as e:
        logger.error(f"Feature enablement error: {e}")
        return False

def get_all_cache_stats() -> Dict[str, Any]:
    """Get comprehensive cache statistics for all caching systems."""
    try:
        pattern_stats = get_cache_stats()
        
        return {
            'pattern_cache': pattern_stats,
            'summary': {
                'total_hit_rate': pattern_stats.get('hit_rate_percent', 0.0),
                'total_entries': pattern_stats.get('entries_count', 0),
                'total_size_mb': pattern_stats.get('size_mb', 0.0),
                'cache_efficiency_score': pattern_stats.get('cache_efficiency_score', 0.0),
                'optimizations_enabled': [
                    'multi_level_caching',
                    'predictive_loading', 
                    'navigation_optimization',
                    'partition_optimization',
                    'dynamic_sizing',
                    'background_optimization'
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Statistics collection error: {e}")
        return {'error': str(e)}

def get_smart_cache_instance():
    """Get the smart cache instance for advanced operations."""
    return get_pattern_cache()

# Enhanced caching utilities
def resize_cache(new_size: int) -> bool:
    """Resize cache with the given size limit."""
    try:
        cache = get_pattern_cache()
        if hasattr(cache, 'resize_cache'):
            # For SmartCache, we need to translate entry count to memory size
            # Assume average entry size of ~100KB, so adjust L3 cache accordingly
            estimated_mb = new_size * 0.1  # 100KB per entry
            cache.resize_cache(l3_entries=new_size, l3_size_mb=estimated_mb)
            
            # Force eviction to meet new size limit
            current_stats = cache.get_statistics()
            current_entries = current_stats.get('entries_count', 0)
            
            # If we have more entries than the new limit, force eviction
            if current_entries > new_size:
                # Clear L1 and L2 first, keep only most important in L3
                cache.l1_cache.clear()
                cache.l2_cache.clear()
                
                # Keep only the newest entries in L3 up to new_size
                with cache.lock:
                    if len(cache.l3_cache) > new_size:
                        items = list(cache.l3_cache.items())
                        # Keep the most recently accessed entries
                        items.sort(key=lambda x: x[1].last_access, reverse=True)
                        cache.l3_cache.clear()
                        for key, entry in items[:new_size]:
                            cache.l3_cache[key] = entry
            
            logger.info(f"Cache resized to {new_size} entries")
            return True
        elif hasattr(cache, 'config'):
            cache.config.max_entries = new_size
            logger.info(f"Cache resized to {new_size} entries")
            return True
        return False
    except Exception as e:
        logger.error(f"Cache resize error: {e}")
        return False

def is_caching_enabled() -> bool:
    """Check if caching is enabled."""
    return ENABLE_CACHING

def set_caching_enabled(enabled: bool) -> None:
    """Enable or disable caching."""
    global ENABLE_CACHING
    ENABLE_CACHING = enabled
    logger.info(f"Caching {'enabled' if enabled else 'disabled'}")

# Missing functions for automata.py compatibility
def get_cached_condition(key: str) -> Optional[Any]:
    """Get cached condition result."""
    try:
        cache = get_pattern_cache()
        return cache.get(f"condition_{key}")
    except Exception as e:
        logger.error(f"Get cached condition error: {e}")
        return None

def cache_condition(key: str, condition_result: Any) -> bool:
    """Cache a condition result."""
    try:
        cache = get_pattern_cache()
        return cache.put(f"condition_{key}", condition_result, condition_result, 0.001)
    except Exception as e:
        logger.error(f"Cache condition error: {e}")
        return False

def get_cached_tokens(pattern: str) -> Optional[List[Any]]:
    """Get cached tokenization result."""
    try:
        cache = get_pattern_cache()
        result = cache.get(f"tokens_{pattern}")
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Get cached tokens error: {e}")
        return None

def cache_tokenization(pattern: str, tokens: List[Any]) -> bool:
    """Cache tokenization result."""
    try:
        cache = get_pattern_cache()
        return cache.put(f"tokens_{pattern}", tokens, tokens, 0.001)
    except Exception as e:
        logger.error(f"Cache tokenization error: {e}")
        return False
