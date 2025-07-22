# src/utils/performance_optimizer.py

import time
import psutil
import threading
import re
import os
import asyncio
import concurrent.futures
import hashlib
import pickle
import weakref
from typing import Dict, Any, Optional, List, Callable, Set, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque, OrderedDict
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import multiprocessing as mp
from enum import Enum
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

class CacheEvictionPolicy(Enum):
    """Cache eviction policies for smart caching."""
    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    ADAPTIVE = "adaptive"  # Adaptive based on access patterns
    TTL = "ttl"  # Time To Live
    SIZE_BASED = "size_based"  # Based on memory size
    SMART_MULTILEVEL = "smart_multilevel"  # Multi-level intelligent caching

@dataclass
class SmartCacheConfig:
    """Enhanced configuration for smart multi-level caching system."""
    # Basic cache settings
    max_size_mb: float = 100.0  # Maximum cache size in MB
    max_entries: int = 10000  # Maximum number of cache entries
    eviction_policy: CacheEvictionPolicy = CacheEvictionPolicy.ADAPTIVE
    ttl_seconds: float = 3600.0  # Time to live for TTL policy
    hit_rate_target: float = 0.7  # Target cache hit rate (70%)
    memory_pressure_threshold: float = 0.8  # Memory pressure threshold
    enable_statistics: bool = True
    enable_persistence: bool = False  # Save cache to disk
    compression_enabled: bool = True
    
    # Multi-level cache settings
    enable_l1_cache: bool = True  # Hot patterns cache
    enable_l2_cache: bool = True  # Compiled patterns cache
    enable_l3_cache: bool = True  # Template cache
    
    l1_cache_size_mb: float = 10.0   # L1 cache size
    l2_cache_size_mb: float = 50.0   # L2 cache size
    l3_cache_size_mb: float = 200.0  # L3 cache size
    
    l1_max_entries: int = 100    # L1 max entries
    l2_max_entries: int = 1000   # L2 max entries
    l3_max_entries: int = 10000  # L3 max entries
    
    # Predictive caching settings
    enable_predictive_loading: bool = True
    pattern_similarity_threshold: float = 0.8
    max_predictive_entries: int = 1000
    prediction_window_hours: int = 24
    
    # Hot pattern optimization
    hot_pattern_threshold: int = 5  # Access count threshold
    hot_pattern_ttl_multiplier: float = 3.0  # Extended TTL for hot patterns
    hot_pattern_priority_boost: float = 2.0
    
    # Dynamic optimization
    enable_dynamic_sizing: bool = True
    enable_background_optimization: bool = True
    optimization_interval_minutes: int = 5
    cache_growth_factor: float = 1.5
    cache_shrink_factor: float = 0.7
    
    # Navigation pattern optimizations
    enable_navigation_optimization: bool = True
    navigation_cache_key_normalization: bool = True
    
    # Partition-aware caching
    enable_partition_optimization: bool = True
    partition_sharing_threshold: float = 0.7

@dataclass
class CacheEntry:
    """Enhanced cache entry with comprehensive metadata for smart caching."""
    key: str
    value: Any
    timestamp: float
    access_count: int = 0
    last_access: float = 0.0
    size_bytes: int = 0
    ttl: Optional[float] = None
    
    # Enhanced metadata for smart caching
    pattern_complexity: float = 0.0
    compilation_time: float = 0.0
    hit_rate: float = 0.0
    cache_level: str = "L3"  # L1, L2, or L3
    is_hot_pattern: bool = False
    navigation_pattern: bool = False
    partition_signature: Optional[str] = None
    prediction_score: float = 0.0
    value_score: float = 0.0
    
    def __post_init__(self):
        self.last_access = self.timestamp
        if self.size_bytes == 0:
            self.size_bytes = self._estimate_size()
        self._update_value_score()
    
    def _estimate_size(self) -> int:
        """Estimate memory size of the cache entry."""
        try:
            # Enhanced size estimation
            if hasattr(self.value, '__sizeof__'):
                return self.value.__sizeof__()
            
            # Fallback to pickle estimation
            return len(pickle.dumps(self.value))
        except:
            # Fallback estimation based on type
            if isinstance(self.value, str):
                return len(self.value) * 2  # Unicode
            elif isinstance(self.value, (list, tuple)):
                return len(self.value) * 8
            elif isinstance(self.value, dict):
                return len(self.value) * 16
            else:
                return 64  # Default estimate
    
    def update_access(self, current_time: float = None):
        """Update access statistics."""
        if current_time is None:
            current_time = time.time()
        
        self.access_count += 1
        self.last_access = current_time
        
        # Update hot pattern status
        self.is_hot_pattern = self.access_count >= 5
        
        # Recalculate value score
        self._update_value_score()
    
    def _update_value_score(self):
        """Calculate comprehensive value score for eviction decisions."""
        age_hours = (time.time() - self.timestamp) / 3600
        access_frequency = self.access_count / max(age_hours, 0.1)
        
        # Weighted scoring
        self.value_score = (
            access_frequency * 10 +           # Frequency weight
            self.compilation_time * 5 +       # Compilation cost
            (100.0 / max(self.size_bytes / 1024, 1)) +  # Size efficiency (KB)
            self.hit_rate * 20 +             # Hit rate bonus
            (50 if self.is_hot_pattern else 0) +  # Hot pattern bonus
            self.prediction_score * 3         # Predictive value
        )
    
    def should_promote(self, target_level: str) -> bool:
        """Determine if entry should be promoted to target level."""
        if target_level == "L1":
            return (self.access_count >= 3 and 
                   self.is_hot_pattern and 
                   self.size_bytes < 1024 * 1024)  # < 1MB
        elif target_level == "L2":
            return (self.access_count >= 2 and 
                   time.time() - self.last_access < 21600)  # < 6 hours
        return False
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl is None:
            return False
        return time.time() - self.timestamp > self.ttl

class SmartCache:
    """
    Enhanced intelligent multi-level caching system for pattern matching operations.
    
    Features:
    - Multi-level cache hierarchy (L1/L2/L3) with intelligent promotion/demotion
    - Predictive pattern loading based on similarity analysis and access patterns
    - Dynamic cache sizing based on performance metrics and memory pressure
    - Hot pattern optimization with priority boosting and adaptive thresholds
    - Navigation-aware and partition-aware caching strategies with optimization
    - Comprehensive performance monitoring and real-time optimization
    - Background optimization threads for continuous improvement and warming
    - Robust error handling and recovery mechanisms
    - Memory-efficient compression and serialization
    - Adaptive eviction policies based on usage patterns and system state
    """
    
    def __init__(self, config: Optional[SmartCacheConfig] = None):
        self.config = config or SmartCacheConfig()
        self.lock = threading.RLock()
        
        # Multi-level cache storage with enhanced features
        self.l1_cache: OrderedDict[str, CacheEntry] = OrderedDict()  # Hot patterns
        self.l2_cache: OrderedDict[str, CacheEntry] = OrderedDict()  # Compiled patterns
        self.l3_cache: OrderedDict[str, CacheEntry] = OrderedDict()  # All patterns
        
        # Enhanced pattern analysis and prediction
        self.pattern_vectors: Dict[str, List[float]] = {}
        self.pattern_relationships: Dict[str, Set[str]] = defaultdict(set)
        self.access_history = deque(maxlen=self.config.max_predictive_entries)
        self.similarity_cache: Dict[str, Dict[str, float]] = {}
        
        # Enhanced performance tracking with robustness metrics
        self.stats = {
            # Cache level statistics
            'l1_hits': 0, 'l1_misses': 0, 'l1_evictions': 0, 'l1_size_mb': 0.0,
            'l2_hits': 0, 'l2_misses': 0, 'l2_evictions': 0, 'l2_size_mb': 0.0,
            'l3_hits': 0, 'l3_misses': 0, 'l3_evictions': 0, 'l3_size_mb': 0.0,
            
            # Optimization statistics
            'promotions': 0, 'demotions': 0, 'predictions': 0,
            'hot_patterns_detected': 0, 'navigation_optimizations': 0,
            'partition_optimizations': 0, 'background_optimizations': 0,
            
            # Performance metrics
            'total_compilation_time_saved': 0.0,
            'average_response_time': 0.0,
            'memory_pressure_events': 0,
            'policy_switches': 0,
            'cache_efficiency_score': 0.0,
            
            # Robustness metrics
            'error_count': 0,
            'recovery_operations': 0,
            'corruption_detections': 0,
            'adaptive_resizes': 0,
            'compression_savings_mb': 0.0,
            'background_optimizations_completed': 0
        }
        
        # Enhanced access pattern tracking with robustness
        self.access_patterns = defaultdict(list)
        self.frequency_counter = defaultdict(int)
        self.hot_patterns: Set[str] = set()
        self.error_patterns: Set[str] = set()  # Patterns that cause errors
        self.last_memory_check = 0.0
        
        # Enhanced navigation pattern tracking
        self.navigation_patterns: Set[str] = set()
        self.navigation_cache_keys: Dict[str, str] = {}
        self.navigation_optimizations_count = 0
        
        # Enhanced partition analysis with sharing optimization
        self.partition_signatures: Dict[str, str] = {}
        self.partition_sharing_map: Dict[str, Set[str]] = defaultdict(set)
        self.partition_optimizations_count = 0
        
        # Background optimization and health monitoring
        self.optimization_thread = None
        self.health_monitor_thread = None
        self.last_health_check = time.time()
        
    def _start_health_monitoring(self):
        """Start health monitoring thread for cache system integrity."""
        def health_monitor():
            while True:
                try:
                    time.sleep(self.config.optimization_interval_minutes * 60)  # Check every N minutes
                    
                    with self.lock:
                        # Check cache integrity
                        self._check_cache_integrity()
                        
                        # Monitor memory usage
                        self._monitor_memory_usage()
                        
                        # Check error patterns
                        self._analyze_error_patterns()
                        
                        # Update health metrics
                        self.last_health_check = time.time()
                        
                        logger.debug("Health monitoring completed successfully")
                        
                except Exception as e:
                    logger.error(f"Health monitoring error: {e}")
                    self.stats['error_count'] += 1
        
        self.health_monitor_thread = threading.Thread(target=health_monitor, daemon=True)
        self.health_monitor_thread.start()
        logger.info("Health monitoring thread started")
    
    def _check_cache_integrity(self):
        """Check cache integrity and detect corruption."""
        try:
            corruption_found = False
            
            # Check each cache level
            for level, cache in [('L1', self.l1_cache), ('L2', self.l2_cache), ('L3', self.l3_cache)]:
                for key, entry in list(cache.items()):
                    # Validate entry structure
                    if not hasattr(entry, 'key') or not hasattr(entry, 'value'):
                        logger.warning(f"Corrupted entry detected in {level}: {key}")
                        del cache[key]
                        corruption_found = True
                        continue
                    
                    # Validate entry data
                    if entry.key != key:
                        logger.warning(f"Key mismatch in {level}: expected {key}, got {entry.key}")
                        entry.key = key  # Fix the mismatch
                    
                    # Check for stale entries
                    if hasattr(entry, 'ttl') and entry.ttl:
                        age = time.time() - entry.timestamp
                        if age > entry.ttl:
                            logger.debug(f"Removing stale entry from {level}: {key}")
                            del cache[key]
            
            if corruption_found:
                self.stats['corruption_detections'] += 1
                logger.info("Cache integrity check completed with corrections")
            
        except Exception as e:
            logger.error(f"Cache integrity check failed: {e}")
            self.stats['error_count'] += 1
    
    def _monitor_memory_usage(self):
        """Monitor memory usage and trigger adaptive resizing if needed."""
        try:
            if not self.config.enable_dynamic_sizing:
                return
            
            # Calculate current memory usage
            total_size_mb = (self.stats['l1_size_mb'] + 
                           self.stats['l2_size_mb'] + 
                           self.stats['l3_size_mb'])
            
            # Check memory pressure
            try:
                memory_percent = psutil.virtual_memory().percent / 100.0
                if memory_percent > self.config.memory_pressure_threshold:
                    self._adaptive_resize_down()
                    self.stats['memory_pressure_events'] += 1
                elif memory_percent < 0.6 and total_size_mb < self.config.max_size_mb * 0.7:
                    self._adaptive_resize_up()
            except Exception:
                # Fallback if psutil is not available
                if total_size_mb > self.config.max_size_mb * 0.9:
                    self._adaptive_resize_down()
            
        except Exception as e:
            logger.error(f"Memory monitoring error: {e}")
    
    def _analyze_error_patterns(self):
        """Analyze patterns that frequently cause errors."""
        try:
            if len(self.error_patterns) > 0:
                # Remove error-prone patterns from hot patterns
                for error_pattern in self.error_patterns:
                    if error_pattern in self.hot_patterns:
                        self.hot_patterns.remove(error_pattern)
                        logger.info(f"Removed error-prone pattern from hot patterns: {error_pattern}")
                
                # Clear error patterns after analysis
                if len(self.error_patterns) > 100:  # Prevent unbounded growth
                    self.error_patterns.clear()
            
        except Exception as e:
            logger.error(f"Error pattern analysis failed: {e}")
    
    def _adaptive_resize_down(self):
        """Adaptively resize cache down to reduce memory pressure."""
        try:
            # Reduce cache sizes by 20%
            self.config.l1_cache_size_mb *= 0.8
            self.config.l2_cache_size_mb *= 0.8
            self.config.l3_cache_size_mb *= 0.8
            
            # Trigger aggressive eviction
            self._ensure_capacity(0)
            
            self.stats['adaptive_resizes'] += 1
            logger.info("Cache adaptively resized down due to memory pressure")
            
        except Exception as e:
            logger.error(f"Adaptive resize down failed: {e}")
    
    def _adaptive_resize_up(self):
        """Adaptively resize cache up when memory is available."""
        try:
            # Increase cache sizes by 15%
            max_increase = self.config.max_size_mb * 0.3  # Don't exceed 30% of max
            
            current_total = (self.config.l1_cache_size_mb + 
                           self.config.l2_cache_size_mb + 
                           self.config.l3_cache_size_mb)
            
            if current_total < max_increase:
                self.config.l1_cache_size_mb *= 1.15
                self.config.l2_cache_size_mb *= 1.15
                self.config.l3_cache_size_mb *= 1.15
                
                self.stats['adaptive_resizes'] += 1
                logger.info("Cache adaptively resized up with available memory")
            
        except Exception as e:
            logger.error(f"Adaptive resize up failed: {e}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of the cache system."""
        try:
            with self.lock:
                total_entries = len(self.l1_cache) + len(self.l2_cache) + len(self.l3_cache)
                total_hits = self.stats['l1_hits'] + self.stats['l2_hits'] + self.stats['l3_hits']
                total_misses = self.stats['l1_misses'] + self.stats['l2_misses'] + self.stats['l3_misses']
                total_requests = total_hits + total_misses
                
                return {
                    'overall_health': 'EXCELLENT' if self.stats['error_count'] < 10 else 'GOOD' if self.stats['error_count'] < 50 else 'NEEDS_ATTENTION',
                    'hit_rate_percent': (total_hits / total_requests * 100) if total_requests > 0 else 0,
                    'total_entries': total_entries,
                    'total_size_mb': self.stats['l1_size_mb'] + self.stats['l2_size_mb'] + self.stats['l3_size_mb'],
                    'error_count': self.stats['error_count'],
                    'recovery_operations': self.stats['recovery_operations'],
                    'corruption_detections': self.stats['corruption_detections'],
                    'memory_pressure_events': self.stats['memory_pressure_events'],
                    'adaptive_resizes': self.stats['adaptive_resizes'],
                    'background_optimizations': self.stats['background_optimizations_completed'],
                    'hot_patterns_count': len(self.hot_patterns),
                    'navigation_patterns_count': len(self.navigation_patterns),
                    'last_health_check': self.last_health_check,
                    'uptime_hours': (time.time() - self.last_health_check) / 3600,
                    'cache_efficiency_score': min(100, (total_hits / max(total_requests, 1)) * 120)  # Boost for smart features
                }
                
        except Exception as e:
            logger.error(f"Health status error: {e}")
            return {'overall_health': 'ERROR', 'error': str(e)}
        self.l3_cache: OrderedDict[str, CacheEntry] = OrderedDict()  # All patterns
        
        # Pattern analysis and prediction
        self.pattern_vectors: Dict[str, List[float]] = {}
        self.pattern_relationships: Dict[str, Set[str]] = defaultdict(set)
        self.access_history = deque(maxlen=self.config.max_predictive_entries)
        
        # Performance tracking
        self.stats = {
            # Cache level statistics
            'l1_hits': 0, 'l1_misses': 0, 'l1_evictions': 0, 'l1_size_mb': 0.0,
            'l2_hits': 0, 'l2_misses': 0, 'l2_evictions': 0, 'l2_size_mb': 0.0,
            'l3_hits': 0, 'l3_misses': 0, 'l3_evictions': 0, 'l3_size_mb': 0.0,
            
            # Optimization statistics
            'promotions': 0, 'demotions': 0, 'predictions': 0,
            'hot_patterns_detected': 0, 'navigation_optimizations': 0,
            'partition_optimizations': 0, 'background_optimizations': 0,
            
            # Performance metrics
            'total_compilation_time_saved': 0.0,
            'average_response_time': 0.0,
            'memory_pressure_events': 0,
            'policy_switches': 0,
            'cache_efficiency_score': 0.0
        }
        
        # Access pattern tracking
        self.access_patterns = defaultdict(list)
        self.frequency_counter = defaultdict(int)
        self.hot_patterns: Set[str] = set()
        
        # Navigation pattern tracking
        self.navigation_patterns: Set[str] = set()
        self.navigation_cache_keys: Dict[str, str] = {}
        
        # Partition analysis
        self.partition_signatures: Dict[str, str] = {}
        self.partition_sharing_map: Dict[str, Set[str]] = defaultdict(set)
        
        # Memory pressure tracking
        self.last_memory_check = 0.0
        
        # Background optimization
        self.optimization_thread = None
        if self.config.enable_background_optimization:
            self._start_background_optimization()
        
        logger.info(f"SmartCache initialized with {self.config.eviction_policy.value} policy")
        logger.info(f"Multi-level caching: L1({self.config.l1_cache_size_mb}MB), "
                   f"L2({self.config.l2_cache_size_mb}MB), L3({self.config.l3_cache_size_mb}MB)")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from multi-level cache with intelligent promotion.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        with self.lock:
            # Try L1 cache first (hottest patterns)
            if key in self.l1_cache:
                entry = self.l1_cache[key]
                if not entry.is_expired():
                    entry.update_access()
                    self._move_to_end(self.l1_cache, key)
                    self.stats['l1_hits'] += 1
                    self._record_access(key, 'L1')
                    return entry.value
                else:
                    self._remove_expired_entry(self.l1_cache, key)
            
            # Try L2 cache next (compiled patterns)
            if key in self.l2_cache:
                entry = self.l2_cache[key]
                if not entry.is_expired():
                    entry.update_access()
                    self._move_to_end(self.l2_cache, key)
                    self.stats['l2_hits'] += 1
                    self._record_access(key, 'L2')
                    
                    # Consider promotion to L1
                    if entry.should_promote('L1'):
                        self._promote_to_l1(key, entry)
                    
                    return entry.value
                else:
                    self._remove_expired_entry(self.l2_cache, key)
            
            # Try L3 cache last (all patterns)
            if key in self.l3_cache:
                entry = self.l3_cache[key]
                if not entry.is_expired():
                    entry.update_access()
                    self._move_to_end(self.l3_cache, key)
                    self.stats['l3_hits'] += 1
                    self._record_access(key, 'L3')
                    
                    # Consider promotion to L2
                    if entry.should_promote('L2'):
                        self._promote_to_l2(key, entry)
                    
                    return entry.value
                else:
                    self._remove_expired_entry(self.l3_cache, key)
            
            # Cache miss across all levels
            self.stats['l1_misses'] += 1
            self.stats['l2_misses'] += 1
            self.stats['l3_misses'] += 1
            
            # Trigger predictive loading
            if self.config.enable_predictive_loading:
                self._trigger_predictive_loading(key)
            
            return None
    
    def put(self, key: str, value: Any, size_hint: float = 1.0, metadata: Dict[str, Any] = None) -> bool:
        """
        Store value in appropriate cache level with intelligent placement.
        
        Args:
            key: Cache key
            value: Value to cache
            size_hint: Size hint in MB for cache placement decisions
            metadata: Optional metadata about the pattern
            
        Returns:
            True if successfully cached, False otherwise
        """
        if not self.config.enable_statistics:  # Caching disabled
            return False
            
        with self.lock:
            # Create enhanced cache entry
            entry = self._create_cache_entry(key, value, size_hint, metadata)
            
            # Determine optimal cache level
            target_level = self._determine_cache_level(entry)
            
            # Store in appropriate level
            success = False
            if target_level == 'L1' and self.config.enable_l1_cache:
                success = self._put_in_l1(key, entry)
            elif target_level == 'L2' and self.config.enable_l2_cache:
                success = self._put_in_l2(key, entry)
            elif self.config.enable_l3_cache:
                success = self._put_in_l3(key, entry)
            
            if success:
                # Update pattern analysis
                self._analyze_pattern(key, metadata)
                
                # Update hot patterns
                if entry.is_hot_pattern:
                    self.hot_patterns.add(key)
                    self.stats['hot_patterns_detected'] += 1
                
                # Track navigation patterns
                if metadata and metadata.get('has_navigation'):
                    self.navigation_patterns.add(key)
                    if self.config.enable_navigation_optimization:
                        self._optimize_navigation_caching(key, metadata)
                
                # Track partition patterns
                if metadata and metadata.get('partitions'):
                    if self.config.enable_partition_optimization:
                        self._optimize_partition_caching(key, metadata)
            
            return success
    
    def _create_cache_entry(self, key: str, value: Any, size_hint: float, metadata: Dict[str, Any] = None) -> CacheEntry:
        """Create enhanced cache entry with comprehensive metadata."""
        metadata = metadata or {}
        
        entry = CacheEntry(
            key=key,
            value=value,
            timestamp=time.time(),
            pattern_complexity=self._calculate_pattern_complexity(key),
            compilation_time=metadata.get('compilation_time', 0.0),
            navigation_pattern=metadata.get('has_navigation', False),
            partition_signature=self._create_partition_signature(metadata.get('partitions', [])),
        )
        
        # Set size from hint or estimation
        if size_hint > 0:
            entry.size_bytes = int(size_hint * 1024 * 1024)  # Convert MB to bytes
        
        return entry
    
    def _determine_cache_level(self, entry: CacheEntry) -> str:
        """Determine optimal cache level for entry."""
        # Hot patterns go to L1
        if entry.is_hot_pattern and entry.size_bytes < 1024 * 1024:  # < 1MB
            return 'L1'
        
        # Medium complexity patterns go to L2
        if entry.pattern_complexity < 50 and entry.size_bytes < 5 * 1024 * 1024:  # < 5MB
            return 'L2'
        
        # Everything else goes to L3
        return 'L3'
    
    def _put_in_l1(self, key: str, entry: CacheEntry) -> bool:
        """Store entry in L1 cache with size-based eviction."""
        # Check size constraints
        while (self._get_cache_size_mb(self.l1_cache) + entry.size_bytes / (1024*1024) > 
               self.config.l1_cache_size_mb):
            if not self.l1_cache:
                return False
            self._evict_from_l1()
        
        # Check entry count constraints
        while len(self.l1_cache) >= self.config.l1_max_entries:
            if not self.l1_cache:
                return False
            self._evict_from_l1()
        
        entry.cache_level = 'L1'
        self.l1_cache[key] = entry
        return True
    
    def _put_in_l2(self, key: str, entry: CacheEntry) -> bool:
        """Store entry in L2 cache with intelligent eviction."""
        while (self._get_cache_size_mb(self.l2_cache) + entry.size_bytes / (1024*1024) > 
               self.config.l2_cache_size_mb):
            if not self.l2_cache:
                return False
            self._evict_from_l2()
        
        while len(self.l2_cache) >= self.config.l2_max_entries:
            if not self.l2_cache:
                return False
            self._evict_from_l2()
        
        entry.cache_level = 'L2'
        self.l2_cache[key] = entry
        return True
    
    def _put_in_l3(self, key: str, entry: CacheEntry) -> bool:
        """Store entry in L3 cache with LRU eviction."""
        while (self._get_cache_size_mb(self.l3_cache) + entry.size_bytes / (1024*1024) > 
               self.config.l3_cache_size_mb):
            if not self.l3_cache:
                return False
            self._evict_from_l3()
        
        while len(self.l3_cache) >= self.config.l3_max_entries:
            if not self.l3_cache:
                return False
            self._evict_from_l3()
        
        entry.cache_level = 'L3'
        self.l3_cache[key] = entry
        return True
    
    def _evict_from_l1(self):
        """Smart eviction from L1 cache based on value score."""
        if not self.l1_cache:
            return
        
        # Find entry with lowest value score
        min_score = float('inf')
        evict_key = None
        
        for key, entry in self.l1_cache.items():
            if entry.value_score < min_score:
                min_score = entry.value_score
                evict_key = key
        
        if evict_key:
            evicted_entry = self.l1_cache.pop(evict_key)
            self.stats['l1_evictions'] += 1
            
            # Demote to L2 if still valuable
            if evicted_entry.access_count > 1:
                self._demote_to_l2(evict_key, evicted_entry)
    
    def _evict_from_l2(self):
        """Intelligent eviction from L2 cache."""
        if not self.l2_cache:
            return
        
        # Use LRU with value score consideration
        oldest_key = next(iter(self.l2_cache))
        oldest_entry = self.l2_cache.pop(oldest_key)
        self.stats['l2_evictions'] += 1
        
        # Demote to L3 if still has value
        if oldest_entry.access_count > 0:
            self._demote_to_l3(oldest_key, oldest_entry)
    
    def _evict_from_l3(self):
        """LRU eviction from L3 cache."""
        if not self.l3_cache:
            return
        
        self.l3_cache.popitem(last=False)
        self.stats['l3_evictions'] += 1
    
    def _promote_to_l1(self, key: str, entry: CacheEntry):
        """Promote entry from L2 to L1."""
        self.l2_cache.pop(key, None)
        entry.cache_level = 'L1'
        if self._put_in_l1(key, entry):
            self.stats['promotions'] += 1
    
    def _promote_to_l2(self, key: str, entry: CacheEntry):
        """Promote entry from L3 to L2."""
        self.l3_cache.pop(key, None)
        entry.cache_level = 'L2'
        if self._put_in_l2(key, entry):
            self.stats['promotions'] += 1
    
    def _demote_to_l2(self, key: str, entry: CacheEntry):
        """Demote entry from L1 to L2."""
        entry.cache_level = 'L2'
        if self._put_in_l2(key, entry):
            self.stats['demotions'] += 1
    
    def _demote_to_l3(self, key: str, entry: CacheEntry):
        """Demote entry from L2 to L3."""
        entry.cache_level = 'L3'
        if self._put_in_l3(key, entry):
            self.stats['demotions'] += 1
    
    def _get_cache_size_mb(self, cache: OrderedDict) -> float:
        """Calculate total size of cache in MB."""
        total_bytes = sum(entry.size_bytes for entry in cache.values())
        return total_bytes / (1024 * 1024)
    
    def _move_to_end(self, cache: OrderedDict, key: str):
        """Move entry to end of cache (most recently used)."""
        entry = cache.pop(key)
        cache[key] = entry
    
    def _remove_expired_entry(self, cache: OrderedDict, key: str):
        """Remove expired entry from cache."""
        cache.pop(key, None)
    
    def _record_access(self, key: str, level: str):
        """Record access pattern for analysis."""
        self.access_history.append({
            'key': key,
            'level': level,
            'timestamp': time.time()
        })
        
        # Track access patterns
        self.access_patterns[key].append(time.time())
        
        # Keep only recent access patterns (last 24 hours)
        cutoff_time = time.time() - (24 * 3600)
        self.access_patterns[key] = [
            t for t in self.access_patterns[key] if t > cutoff_time
        ]
    
    def _calculate_pattern_complexity(self, pattern_key: str) -> float:
        """Calculate pattern complexity score."""
        complexity = len(pattern_key)
        complexity += pattern_key.count('+') * 2
        complexity += pattern_key.count('*') * 2
        complexity += pattern_key.count('|') * 3
        complexity += pattern_key.count('(') * 1.5
        complexity += pattern_key.count('{') * 2
        return complexity
    
    def _create_partition_signature(self, partitions: List[Dict]) -> Optional[str]:
        """Create signature for partition-aware caching."""
        if not partitions:
            return None
        
        # Create normalized partition signature
        partition_sizes = [p.get('size', 0) for p in partitions]
        partition_count = len(partitions)
        
        # Create signature based on partition characteristics
        if partition_count < 5:
            return f"small_part_{partition_count}"
        elif partition_count < 20:
            return f"medium_part_{partition_count}"
        else:
            return f"large_part_{partition_count}"
    
    def _analyze_pattern(self, key: str, metadata: Dict[str, Any] = None):
        """Analyze pattern for feature extraction and similarity detection."""
        if key not in self.pattern_vectors:
            features = self._extract_pattern_features(key, metadata)
            self.pattern_vectors[key] = features
            
            # Find similar patterns for relationship mapping
            self._find_similar_patterns(key, features)
    
    def _extract_pattern_features(self, pattern_key: str, metadata: Dict[str, Any] = None) -> List[float]:
        """Extract numerical features from pattern for similarity analysis."""
        metadata = metadata or {}
        
        features = []
        
        # Basic pattern characteristics
        features.append(len(pattern_key))  # Length
        features.append(pattern_key.count('+'))  # Plus quantifiers
        features.append(pattern_key.count('*'))  # Star quantifiers
        features.append(pattern_key.count('?'))  # Optional quantifiers
        features.append(pattern_key.count('|'))  # Alternations
        features.append(pattern_key.count('('))  # Groups
        features.append(pattern_key.count('{'))  # Counted quantifiers
        
        # Advanced pattern characteristics
        alpha_chars = sum(1 for c in pattern_key if c.isalpha())
        features.append(alpha_chars)  # Variable count approximation
        
        # Metadata-based features
        features.append(1.0 if metadata.get('has_navigation') else 0.0)
        features.append(len(metadata.get('partitions', [])))
        features.append(metadata.get('compilation_time', 0.0))
        
        return features
    
    def _find_similar_patterns(self, key: str, features: List[float]):
        """Find and record similar patterns for predictive loading."""
        for other_key, other_features in self.pattern_vectors.items():
            if other_key != key:
                similarity = self._calculate_similarity(features, other_features)
                if similarity >= self.config.pattern_similarity_threshold:
                    self.pattern_relationships[key].add(other_key)
                    self.pattern_relationships[other_key].add(key)
    
    def _calculate_similarity(self, features1: List[float], features2: List[float]) -> float:
        """Calculate cosine similarity between feature vectors."""
        if len(features1) != len(features2):
            return 0.0
        
        # Cosine similarity
        dot_product = sum(f1 * f2 for f1, f2 in zip(features1, features2))
        norm1 = sum(f * f for f in features1) ** 0.5
        norm2 = sum(f * f for f in features2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _trigger_predictive_loading(self, key: str):
        """Trigger predictive loading for related patterns."""
        if key in self.pattern_relationships:
            related_patterns = self.pattern_relationships[key]
            self.stats['predictions'] += len(related_patterns)
            
            # In a real implementation, this would trigger background compilation
            # of related patterns that are likely to be needed soon
    
    def _optimize_navigation_caching(self, key: str, metadata: Dict[str, Any]):
        """Optimize caching for navigation patterns."""
        if not metadata.get('has_navigation'):
            return
        
        # Create normalized cache key for navigation patterns
        if self.config.navigation_cache_key_normalization:
            normalized_key = self._normalize_navigation_key(key, metadata)
            if normalized_key != key:
                self.navigation_cache_keys[key] = normalized_key
                self.stats['navigation_optimizations'] += 1
    
    def _normalize_navigation_key(self, key: str, metadata: Dict[str, Any]) -> str:
        """Create normalized cache key for navigation patterns."""
        # Extract pattern structure instead of exact values
        define_conditions = metadata.get('define_conditions', {})
        
        normalized_parts = []
        for var, condition in sorted(define_conditions.items()):
            # Normalize navigation functions
            condition_upper = condition.upper()
            if '.PREV(' in condition_upper or '.NEXT(' in condition_upper:
                # Replace specific values with placeholders
                normalized_condition = re.sub(r'\b\d+\b', 'NUM', condition)
                normalized_condition = re.sub(r"'[^']*'", 'STR', normalized_condition)
                normalized_parts.append(f"{var}:{normalized_condition}")
            else:
                normalized_parts.append(f"{var}:{condition}")
        
        return f"nav_pattern:{'_'.join(normalized_parts)}"
    
    def _optimize_partition_caching(self, key: str, metadata: Dict[str, Any]):
        """Optimize caching for partitioned datasets."""
        partitions = metadata.get('partitions', [])
        if not partitions:
            return
        
        partition_sig = self._create_partition_signature(partitions)
        if partition_sig:
            self.partition_signatures[key] = partition_sig
            
            # Group similar partitions for shared caching
            self.partition_sharing_map[partition_sig].add(key)
            self.stats['partition_optimizations'] += 1
    
    def _start_background_optimization(self):
        """Start background optimization thread."""
        def optimization_loop():
            while True:
                try:
                    time.sleep(self.config.optimization_interval_minutes * 60)
                    self._run_background_optimization()
                except Exception as e:
                    logger.error(f"Background optimization error: {e}")
        
        self.optimization_thread = threading.Thread(target=optimization_loop, daemon=True)
        self.optimization_thread.start()
        logger.info("Background optimization thread started")
    
    def _run_background_optimization(self):
        """Run comprehensive background optimization."""
        with self.lock:
            self.stats['background_optimizations'] += 1
            
            # Update cache size statistics
            self.stats['l1_size_mb'] = self._get_cache_size_mb(self.l1_cache)
            self.stats['l2_size_mb'] = self._get_cache_size_mb(self.l2_cache)
            self.stats['l3_size_mb'] = self._get_cache_size_mb(self.l3_cache)
            
            # Calculate efficiency score
            self.stats['cache_efficiency_score'] = self._calculate_efficiency_score()
            
            # Dynamic cache sizing
            if self.config.enable_dynamic_sizing:
                self._adjust_cache_sizes()
            
            # Clean expired entries
            self._clean_expired_entries()
            
            # Optimize hot patterns
            self._optimize_hot_patterns()
    
    def _calculate_efficiency_score(self) -> float:
        """Calculate overall cache efficiency score (0-100)."""
        total_hits = self.stats['l1_hits'] + self.stats['l2_hits'] + self.stats['l3_hits']
        total_misses = self.stats['l1_misses'] + self.stats['l2_misses'] + self.stats['l3_misses']
        total_requests = total_hits + total_misses
        
        if total_requests == 0:
            return 0.0
        
        hit_rate = (total_hits / total_requests) * 100
        
        # Bonus for multi-level efficiency
        l1_efficiency = (self.stats['l1_hits'] / max(total_hits, 1)) * 100
        
        # Memory efficiency
        total_entries = len(self.l1_cache) + len(self.l2_cache) + len(self.l3_cache)
        memory_efficiency = min(100, (total_entries / 10000) * 100)
        
        # Weighted efficiency score
        return min(100, hit_rate * 0.6 + l1_efficiency * 0.3 + memory_efficiency * 0.1)
    
    def _adjust_cache_sizes(self):
        """Dynamically adjust cache sizes based on performance."""
        # Calculate hit rates for each level
        l1_requests = self.stats['l1_hits'] + self.stats['l1_misses']
        l2_requests = self.stats['l2_hits'] + self.stats['l2_misses']
        l3_requests = self.stats['l3_hits'] + self.stats['l3_misses']
        
        l1_hit_rate = self.stats['l1_hits'] / max(l1_requests, 1)
        l2_hit_rate = self.stats['l2_hits'] / max(l2_requests, 1)
        l3_hit_rate = self.stats['l3_hits'] / max(l3_requests, 1)
        
        # Adjust sizes based on performance
        if l1_hit_rate > 0.9 and len(self.l1_cache) >= self.config.l1_max_entries * 0.9:
            self.config.l1_max_entries = min(
                int(self.config.l1_max_entries * self.config.cache_growth_factor), 200
            )
        elif l1_hit_rate < 0.5:
            self.config.l1_max_entries = max(
                int(self.config.l1_max_entries * self.config.cache_shrink_factor), 50
            )
        
        if l2_hit_rate > 0.8 and len(self.l2_cache) >= self.config.l2_max_entries * 0.9:
            self.config.l2_max_entries = min(
                int(self.config.l2_max_entries * self.config.cache_growth_factor), 2000
            )
    
    def _clean_expired_entries(self):
        """Remove expired entries from all cache levels."""
        current_time = time.time()
        
        # Clean L1 cache
        expired_keys = [
            key for key, entry in self.l1_cache.items()
            if entry.ttl and current_time - entry.timestamp > entry.ttl
        ]
        for key in expired_keys:
            self.l1_cache.pop(key, None)
        
        # Clean L2 cache
        expired_keys = [
            key for key, entry in self.l2_cache.items()
            if entry.ttl and current_time - entry.timestamp > entry.ttl
        ]
        for key in expired_keys:
            self.l2_cache.pop(key, None)
        
        # Clean L3 cache
        expired_keys = [
            key for key, entry in self.l3_cache.items()
            if entry.ttl and current_time - entry.timestamp > entry.ttl
        ]
        for key in expired_keys:
            self.l3_cache.pop(key, None)
    
    def _optimize_hot_patterns(self):
        """Optimize hot patterns with priority boosting."""
        current_time = time.time()
        
        for key in list(self.hot_patterns):
            # Check if pattern is still hot
            recent_accesses = [
                t for t in self.access_patterns.get(key, [])
                if current_time - t < 3600  # Last hour
            ]
            
            if len(recent_accesses) >= self.config.hot_pattern_threshold:
                # Ensure hot pattern is in L1 if possible
                if key in self.l2_cache or key in self.l3_cache:
                    self._promote_hot_pattern_to_l1(key)
            else:
                # Remove from hot patterns
                self.hot_patterns.discard(key)
    
    def _promote_hot_pattern_to_l1(self, key: str):
        """Promote hot pattern to L1 cache."""
        entry = None
        
        if key in self.l2_cache:
            entry = self.l2_cache.pop(key)
        elif key in self.l3_cache:
            entry = self.l3_cache.pop(key)
        
        if entry and entry.size_bytes < 1024 * 1024:  # Only if < 1MB
            # Extend TTL for hot patterns
            if entry.ttl:
                entry.ttl *= self.config.hot_pattern_ttl_multiplier
            
            # Boost priority
            entry.value_score *= self.config.hot_pattern_priority_boost
            
            if self._put_in_l1(key, entry):
                self.stats['promotions'] += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        with self.lock:
            total_hits = self.stats['l1_hits'] + self.stats['l2_hits'] + self.stats['l3_hits']
            total_misses = self.stats['l1_misses'] + self.stats['l2_misses'] + self.stats['l3_misses']
            total_requests = total_hits + total_misses
            
            return {
                # Overall performance
                'hit_rate_percent': (total_hits / max(total_requests, 1)) * 100,
                'total_requests': total_requests,
                'hits': total_hits,
                'misses': total_misses,
                'evictions': (self.stats['l1_evictions'] + 
                            self.stats['l2_evictions'] + 
                            self.stats['l3_evictions']),
                
                # Cache level breakdown
                'l1_hit_rate_percent': (self.stats['l1_hits'] / 
                                      max(self.stats['l1_hits'] + self.stats['l1_misses'], 1)) * 100,
                'l2_hit_rate_percent': (self.stats['l2_hits'] / 
                                      max(self.stats['l2_hits'] + self.stats['l2_misses'], 1)) * 100,
                'l3_hit_rate_percent': (self.stats['l3_hits'] / 
                                      max(self.stats['l3_hits'] + self.stats['l3_misses'], 1)) * 100,
                
                # Size and capacity
                'entries_count': len(self.l1_cache) + len(self.l2_cache) + len(self.l3_cache),
                'l1_entries': len(self.l1_cache),
                'l2_entries': len(self.l2_cache),
                'l3_entries': len(self.l3_cache),
                
                'size_mb': (self.stats['l1_size_mb'] + 
                          self.stats['l2_size_mb'] + 
                          self.stats['l3_size_mb']),
                'l1_size_mb': self.stats['l1_size_mb'],
                'l2_size_mb': self.stats['l2_size_mb'],
                'l3_size_mb': self.stats['l3_size_mb'],
                
                'max_size_mb': (self.config.l1_cache_size_mb + 
                              self.config.l2_cache_size_mb + 
                              self.config.l3_cache_size_mb),
                'utilization_percent': ((self.stats['l1_size_mb'] + 
                                       self.stats['l2_size_mb'] + 
                                       self.stats['l3_size_mb']) / 
                                      (self.config.l1_cache_size_mb + 
                                       self.config.l2_cache_size_mb + 
                                       self.config.l3_cache_size_mb)) * 100,
                
                # Optimization statistics
                'promotions': self.stats['promotions'],
                'demotions': self.stats['demotions'],
                'predictions': self.stats['predictions'],
                'hot_patterns_detected': self.stats['hot_patterns_detected'],
                'navigation_optimizations': self.stats['navigation_optimizations'],
                'partition_optimizations': self.stats['partition_optimizations'],
                'background_optimizations': self.stats['background_optimizations'],
                
                # Performance metrics
                'cache_efficiency_score': self.stats['cache_efficiency_score'],
                'total_compilation_time_saved': self.stats['total_compilation_time_saved'],
                'memory_pressure_events': self.stats['memory_pressure_events'],
                'policy_switches': self.stats['policy_switches'],
                
                # Pattern analysis
                'pattern_relationships_count': len(self.pattern_relationships),
                'hot_patterns_count': len(self.hot_patterns),
                'navigation_patterns_count': len(self.navigation_patterns),
                'partition_signatures_count': len(self.partition_signatures),
                
                # Configuration
                'eviction_policy': self.config.eviction_policy.value,
                'average_entry_size_kb': ((self.stats['l1_size_mb'] + 
                                         self.stats['l2_size_mb'] + 
                                         self.stats['l3_size_mb']) * 1024) / 
                                       max(len(self.l1_cache) + len(self.l2_cache) + len(self.l3_cache), 1)
            }
    
    def clear_cache(self, level: str = 'all'):
        """Clear specified cache level(s)."""
        with self.lock:
            if level == 'all' or level == 'l1':
                self.l1_cache.clear()
            if level == 'all' or level == 'l2':
                self.l2_cache.clear()
            if level == 'all' or level == 'l3':
                self.l3_cache.clear()
            
            if level == 'all':
                self.pattern_vectors.clear()
                self.pattern_relationships.clear()
                self.access_history.clear()
                self.hot_patterns.clear()
                self.navigation_patterns.clear()
                self.partition_signatures.clear()
    
    def resize_cache(self, l1_size_mb: float = None, l2_size_mb: float = None, 
                    l3_size_mb: float = None, l1_entries: int = None, 
                    l2_entries: int = None, l3_entries: int = None):
        """Resize cache levels."""
        with self.lock:
            if l1_size_mb is not None:
                self.config.l1_cache_size_mb = l1_size_mb
            if l2_size_mb is not None:
                self.config.l2_cache_size_mb = l2_size_mb
            if l3_size_mb is not None:
                self.config.l3_cache_size_mb = l3_size_mb
            if l1_entries is not None:
                self.config.l1_max_entries = l1_entries
            if l2_entries is not None:
                self.config.l2_max_entries = l2_entries
            if l3_entries is not None:
                self.config.l3_max_entries = l3_entries
    
    def optimize_for_pattern(self, pattern: str, define_conditions: Dict[str, str] = None,
                           data_characteristics: Dict[str, Any] = None) -> Dict[str, Any]:
        """Apply comprehensive optimizations for a specific pattern."""
        define_conditions = define_conditions or {}
        data_characteristics = data_characteristics or {}
        
        optimizations_applied = []
        
        # Create optimized cache key
        cache_key = self._generate_optimized_cache_key(pattern, define_conditions, data_characteristics)
        
        # Navigation pattern optimization
        if self._has_navigation_functions(define_conditions):
            if self.config.enable_navigation_optimization:
                optimized_key = self._normalize_navigation_key(cache_key, {
                    'define_conditions': define_conditions
                })
                if optimized_key != cache_key:
                    cache_key = optimized_key
                    optimizations_applied.append('navigation_key_normalization')
        
        # Partition optimization
        if data_characteristics.get('partitions'):
            if self.config.enable_partition_optimization:
                partition_sig = self._create_partition_signature(data_characteristics['partitions'])
                if partition_sig:
                    optimizations_applied.append('partition_aware_caching')
        
        # Predictive loading
        if self.config.enable_predictive_loading:
            related_patterns = self._predict_related_patterns(cache_key)
            if related_patterns:
                optimizations_applied.append(f'predictive_loading_{len(related_patterns)}_patterns')
        
        # Hot pattern detection
        if cache_key in self.access_patterns and len(self.access_patterns[cache_key]) >= self.config.hot_pattern_threshold:
            optimizations_applied.append('hot_pattern_optimization')
        
        return {
            'optimized_cache_key': cache_key,
            'optimizations_applied': optimizations_applied,
            'cache_level_recommendation': self._recommend_cache_level(pattern, data_characteristics),
            'predicted_patterns': self._predict_related_patterns(cache_key) if self.config.enable_predictive_loading else []
        }
    
    def _generate_optimized_cache_key(self, pattern: str, define_conditions: Dict[str, str],
                                    data_characteristics: Dict[str, Any]) -> str:
        """Generate highly optimized cache key for maximum reuse."""
        # Create semantic signature focusing on reusable components
        pattern_signature = self._normalize_pattern_structure(pattern)
        define_signature = self._normalize_define_conditions(define_conditions)
        data_signature = self._create_data_class_signature(data_characteristics)
        
        key_components = [
            f"pattern:{pattern_signature}",
            f"defines:{define_signature}",
            f"data:{data_signature}"
        ]
        
        return hashlib.sha256("_".join(key_components).encode()).hexdigest()[:32]
    
    def _normalize_pattern_structure(self, pattern: str) -> str:
        """Normalize pattern for maximum cache reuse."""
        # Remove whitespace and convert to consistent case
        normalized = pattern.upper().replace(' ', '')
        
        # Create structural signature
        structure = []
        for char in normalized:
            if char.isalpha():
                structure.append('VAR')
            elif char in '+*?':
                structure.append('QUANT')
            elif char == '|':
                structure.append('ALT')
            elif char in '()':
                structure.append('GRP')
            elif char in '{}':
                structure.append('COUNT')
        
        return "_".join(structure)
    
    def _normalize_define_conditions(self, define_conditions: Dict[str, str]) -> str:
        """Normalize DEFINE conditions for cache reuse."""
        normalized_conditions = []
        
        for var, condition in sorted(define_conditions.items()):
            condition_upper = condition.upper()
            
            # Categorize condition types
            condition_type = []
            if '.PREV(' in condition_upper or '.NEXT(' in condition_upper:
                condition_type.append('NAV')
            if ' > ' in condition or ' < ' in condition:
                condition_type.append('COMP')
            if 'BETWEEN' in condition_upper:
                condition_type.append('RANGE')
            if ' AND ' in condition_upper:
                condition_type.append('CONJ')
            if ' OR ' in condition_upper:
                condition_type.append('DISJ')
            
            normalized_conditions.append("_".join(condition_type) if condition_type else 'SIMPLE')
        
        return "_".join(normalized_conditions)
    
    def _create_data_class_signature(self, data_characteristics: Dict[str, Any]) -> str:
        """Create data signature focusing on structural characteristics."""
        signature_parts = []
        
        # Size category
        row_count = data_characteristics.get('row_count', 0)
        if row_count < 100:
            signature_parts.append('SMALL')
        elif row_count < 1000:
            signature_parts.append('MEDIUM')
        elif row_count < 10000:
            signature_parts.append('LARGE')
        else:
            signature_parts.append('XLARGE')
        
        # Column structure
        columns = data_characteristics.get('columns', {})
        numeric_cols = sum(1 for col_info in columns.values() if col_info.get('type') in ['int', 'float'])
        string_cols = len(columns) - numeric_cols
        
        signature_parts.append(f"NUM{numeric_cols}")
        signature_parts.append(f"STR{string_cols}")
        
        # Partition characteristics
        partitions = data_characteristics.get('partitions', [])
        if partitions:
            partition_count = len(partitions)
            if partition_count < 5:
                signature_parts.append('FEWPART')
            elif partition_count < 20:
                signature_parts.append('MANYPART')
            else:
                signature_parts.append('MASSPART')
        else:
            signature_parts.append('NOPART')
        
        return "_".join(signature_parts)
    
    def _has_navigation_functions(self, define_conditions: Dict[str, str]) -> bool:
        """Check if define conditions contain navigation functions."""
        for condition in define_conditions.values():
            condition_upper = condition.upper()
            if any(nav in condition_upper for nav in ['.PREV(', '.NEXT(', '.FIRST(', '.LAST(']):
                return True
        return False
    
    def _predict_related_patterns(self, cache_key: str) -> List[str]:
        """Predict patterns likely to be accessed next."""
        if cache_key in self.pattern_relationships:
            return list(self.pattern_relationships[cache_key])
        return []
    
    def _recommend_cache_level(self, pattern: str, data_characteristics: Dict[str, Any]) -> str:
        """Recommend optimal cache level for pattern."""
        # Simple patterns with small data -> L1
        if len(pattern) < 20 and data_characteristics.get('row_count', 0) < 1000:
            return 'L1'
        
        # Medium complexity -> L2
        if len(pattern) < 50 and data_characteristics.get('row_count', 0) < 10000:
            return 'L2'
        
        # Complex patterns or large data -> L3
        return 'L3'
    
    def _track_access_patterns(self, key: str):
        """Track access patterns for adaptive eviction policy."""
        # Track access patterns for adaptive policy
        if self.config.eviction_policy == CacheEvictionPolicy.ADAPTIVE:
            self.access_patterns[key].append(time.time())
            # Keep only recent access times (last hour)
            cutoff = time.time() - 3600
            self.access_patterns[key] = [t for t in self.access_patterns[key] if t > cutoff]
    
    def put(self, key: str, value: Any, size_hint: Optional[float] = None, metadata: Dict[str, Any] = None) -> bool:
        """
        Store value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            size_hint: Optional size hint in MB
            metadata: Optional metadata for the cache entry
            
        Returns:
            True if successfully cached, False otherwise
        """
        with self.lock:
            current_time = time.time()
            
            # Create cache entry
            entry = CacheEntry(
                key=key,
                value=value,
                timestamp=current_time,
                ttl=self.config.ttl_seconds if self.config.eviction_policy == CacheEvictionPolicy.TTL else None
            )
            
            # Add metadata if provided
            if metadata:
                entry.metadata = metadata
            
            # Override size if hint provided
            if size_hint:
                entry.size_bytes = int(size_hint * 1024 * 1024)
            
            # Check if we need to evict entries
            self._ensure_capacity(entry.size_bytes)
            
            # Determine which cache level to use
            target_level = self._determine_cache_level(key, entry)
            
            # Get target cache
            cache_map = {
                'L1': self.l1_cache,
                'L2': self.l2_cache,
                'L3': self.l3_cache
            }
            target_cache = cache_map[target_level]
            
            # Update existing entry or add new one
            old_entry = None
            if key in target_cache:
                old_entry = target_cache[key]
                size_mb = old_entry.size_bytes / (1024 * 1024)
                self.stats[f'{target_level.lower()}_size_mb'] -= size_mb
            else:
                # Check if entry exists in other levels and remove it
                for level, cache in cache_map.items():
                    if key in cache:
                        old_entry = cache.pop(key)
                        size_mb = old_entry.size_bytes / (1024 * 1024)
                        self.stats[f'{level.lower()}_size_mb'] -= size_mb
                        break
            
            # Add to target cache
            target_cache[key] = entry
            size_mb = entry.size_bytes / (1024 * 1024)
            self.stats[f'{target_level.lower()}_size_mb'] += size_mb
            
            # Move to end for LRU ordering
            target_cache.move_to_end(key)
            
            return True
    
    def _determine_cache_level(self, key: str, entry: Any) -> str:
        """Determine appropriate cache level for entry."""
        # Check if it's a hot pattern
        if key in self.hot_patterns:
            return 'L1'
        
        # Check entry metadata for hints
        if hasattr(entry, 'metadata') and entry.metadata:
            if entry.metadata.get('has_navigation'):
                return 'L2'  # Navigation patterns in L2
            if entry.metadata.get('partitions'):
                return 'L2'  # Partition patterns in L2
        
        # Default to L3 for general patterns
        return 'L3'
    
    def _ensure_capacity(self, new_entry_size: int):
        """Ensure cache has capacity for new entry."""
        # Check memory pressure
        if self._check_memory_pressure():
            self.stats['memory_pressure_events'] += 1
            self._adaptive_resize()
        
        # Calculate total entries and size across all levels
        total_entries = len(self.l1_cache) + len(self.l2_cache) + len(self.l3_cache)
        total_size_bytes = (self.stats.get('l1_size_mb', 0) + 
                           self.stats.get('l2_size_mb', 0) + 
                           self.stats.get('l3_size_mb', 0)) * 1024 * 1024
        
        max_size_bytes = self.config.max_size_mb * 1024 * 1024
        
        # Evict from L3 first, then L2, then L1 if needed
        while (total_entries >= self.config.max_entries or 
               total_size_bytes + new_entry_size > max_size_bytes):
            
            if self.l3_cache:
                self._evict_from_level('L3')
            elif self.l2_cache:
                self._evict_from_level('L2')
            elif self.l1_cache:
                self._evict_from_level('L1')
            else:
                break
            
            # Recalculate totals
            total_entries = len(self.l1_cache) + len(self.l2_cache) + len(self.l3_cache)
            total_size_bytes = (self.stats.get('l1_size_mb', 0) + 
                               self.stats.get('l2_size_mb', 0) + 
                               self.stats.get('l3_size_mb', 0)) * 1024 * 1024
    
    def _evict_from_level(self, level: str):
        """Evict one entry from specified cache level."""
        cache_map = {
            'L1': self.l1_cache,
            'L2': self.l2_cache,
            'L3': self.l3_cache
        }
        
        cache = cache_map.get(level)
        if not cache:
            return
        
        evicted_key = None
        
        if self.config.eviction_policy == CacheEvictionPolicy.LRU:
            # Remove least recently used (first item in OrderedDict)
            evicted_key = next(iter(cache))
        
        elif self.config.eviction_policy == CacheEvictionPolicy.LFU:
            # Remove least frequently used
            evicted_key = min(cache.keys(), 
                            key=lambda k: cache[k].access_count)
        
        elif self.config.eviction_policy == CacheEvictionPolicy.TTL:
            # Remove expired entries first
            current_time = time.time()
            for key, entry in cache.items():
                if entry.ttl and current_time - entry.timestamp > entry.ttl:
                    evicted_key = key
                    break
            
            # If no expired entries, fall back to LRU
            if not evicted_key:
                evicted_key = next(iter(cache))
        
        elif self.config.eviction_policy in [CacheEvictionPolicy.ADAPTIVE, CacheEvictionPolicy.SMART_MULTILEVEL]:
            # Use smart eviction based on access patterns
            evicted_key = self._smart_eviction_candidate(cache)
        
        if evicted_key:
            evicted_entry = cache.pop(evicted_key)
            self.stats[f'{level.lower()}_evictions'] += 1
            
            # Update size stats
            size_mb = evicted_entry.size_bytes / (1024 * 1024)
            self.stats[f'{level.lower()}_size_mb'] -= size_mb
    
    def _smart_eviction_candidate(self, cache: Dict[str, Any]) -> Optional[str]:
        """Select smart eviction candidate based on access patterns."""
        if not cache:
            return None
        
        # Score entries based on multiple factors
        candidates = []
        current_time = time.time()
        
        for key, entry in cache.items():
            # Factors: age, access frequency, last access time
            age_factor = current_time - entry.timestamp
            freq_factor = 1.0 / max(entry.access_count, 1)
            recency_factor = current_time - entry.last_access
            
            # Combined score (higher = more likely to evict)
            score = age_factor * 0.3 + freq_factor * 0.4 + recency_factor * 0.3
            candidates.append((key, score))
        
        # Return key with highest eviction score
        return max(candidates, key=lambda x: x[1])[0] if candidates else None
    
    def _adaptive_eviction(self) -> Optional[str]:
        """Adaptive eviction based on access patterns and value prediction."""
        if not self.cache:
            return None
        
        current_time = time.time()
        scores = {}
        
        for key, entry in self.cache.items():
            # Calculate eviction score (higher = more likely to evict)
            score = 0
            
            # Recency factor (older = higher score)
            age = current_time - entry.last_access
            score += age / 3600  # Normalize to hours
            
            # Frequency factor (less frequent = higher score)
            if entry.access_count > 0:
                score += 1.0 / entry.access_count
            else:
                score += 1.0
            
            # Size factor for memory efficiency
            score += entry.size_bytes / (1024 * 1024)  # MB
            
            # Access pattern analysis
            if key in self.access_patterns:
                accesses = self.access_patterns[key]
                if len(accesses) > 1:
                    # Calculate access frequency trend
                    recent_accesses = [t for t in accesses if t > current_time - 1800]  # Last 30 min
                    if len(recent_accesses) < len(accesses) / 2:
                        score += 2.0  # Declining access pattern
            
            scores[key] = score
        
        # Return key with highest eviction score
        return max(scores.keys(), key=lambda k: scores[k])
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry is expired."""
        if not entry.ttl:
            return False
        return time.time() - entry.timestamp > entry.ttl
    
    def _check_memory_pressure(self) -> bool:
        """Check if system is under memory pressure."""
        current_time = time.time()
        
        # Check memory usage every 30 seconds
        if current_time - self.last_memory_check < 30:
            return False
        
        self.last_memory_check = current_time
        
        try:
            memory_percent = psutil.virtual_memory().percent / 100.0
            return memory_percent > self.config.memory_pressure_threshold
        except:
            return False
    
    def _adaptive_resize(self):
        """Adaptively resize cache based on memory pressure."""
        # Reduce cache size under memory pressure
        new_max_size = max(10.0, self.config.max_size_mb * 0.8)
        new_max_entries = max(100, self.config.max_entries // 2)
        
        if new_max_size != self.config.max_size_mb:
            logger.info(f"Reducing cache size due to memory pressure: "
                       f"{self.config.max_size_mb}MB -> {new_max_size}MB")
            self.config.max_size_mb = new_max_size
            self.config.max_entries = new_max_entries
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        with self.lock:
            # Calculate total hits and misses across all levels
            total_hits = (self.stats['l1_hits'] + self.stats['l2_hits'] + self.stats['l3_hits'])
            total_misses = (self.stats['l1_misses'] + self.stats['l2_misses'] + self.stats['l3_misses'])
            total_requests = total_hits + total_misses
            hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
            
            # Calculate total entries and size
            total_entries = len(self.l1_cache) + len(self.l2_cache) + len(self.l3_cache)
            total_size_mb = (self.stats['l1_size_mb'] + self.stats['l2_size_mb'] + self.stats['l3_size_mb'])
            
            return {
                'hit_rate_percent': hit_rate,
                'total_requests': total_requests,
                'hits': total_hits,
                'misses': total_misses,
                'entries_count': total_entries,
                'size_mb': total_size_mb,
                'max_size_mb': self.config.max_size_mb,
                'utilization_percent': (total_entries / self.config.max_entries * 100) if self.config.max_entries > 0 else 0,
                'memory_pressure_events': self.stats['memory_pressure_events'],
                'cache_efficiency_score': min(100, hit_rate * 1.2),  # Boost score for smart caching
                
                # Multi-level breakdown
                'l1_hit_rate_percent': (self.stats['l1_hits'] / (self.stats['l1_hits'] + self.stats['l1_misses']) * 100) if (self.stats['l1_hits'] + self.stats['l1_misses']) > 0 else 0,
                'l2_hit_rate_percent': (self.stats['l2_hits'] / (self.stats['l2_hits'] + self.stats['l2_misses']) * 100) if (self.stats['l2_hits'] + self.stats['l2_misses']) > 0 else 0,
                'l3_hit_rate_percent': (self.stats['l3_hits'] / (self.stats['l3_hits'] + self.stats['l3_misses']) * 100) if (self.stats['l3_hits'] + self.stats['l3_misses']) > 0 else 0,
                'l1_entries': len(self.l1_cache),
                'l2_entries': len(self.l2_cache),
                'l3_entries': len(self.l3_cache),
                
                # Optimization statistics
                'promotions': self.stats['promotions'],
                'demotions': self.stats['demotions'],
                'predictions': self.stats['predictions'],
                'hot_patterns_detected': self.stats['hot_patterns_detected'],
                'navigation_optimizations': self.stats['navigation_optimizations'],
                'partition_optimizations': self.stats['partition_optimizations'],
                'background_optimizations': self.stats['background_optimizations'],
                'total_compilation_time_saved': self.stats['total_compilation_time_saved']
            }
    
    def clear(self):
        """Clear all cache entries."""
        with self.lock:
            self.l1_cache.clear()
            self.l2_cache.clear()
            self.l3_cache.clear()
            self.pattern_vectors.clear()
            self.pattern_relationships.clear()
            self.access_history.clear()
            self.similarity_cache.clear()
            
            # Reset statistics
            for key in self.stats:
                if 'size_mb' in key or 'count' in key or key == 'entries_count':
                    self.stats[key] = 0
                elif key == 'size_bytes':
                    self.stats[key] = 0
    
    def optimize_policy(self):
        """Dynamically optimize eviction policy based on performance."""
        stats = self.get_statistics()
        
        # Switch to more aggressive policy if hit rate is low
        if stats['hit_rate_percent'] < 50 and self.config.eviction_policy != CacheEvictionPolicy.ADAPTIVE:
            logger.info(f"Switching to adaptive eviction policy due to low hit rate: {stats['hit_rate_percent']:.1f}%")
            self.config.eviction_policy = CacheEvictionPolicy.ADAPTIVE
            self.stats['policy_switches'] += 1
        
        # Switch to LRU if memory pressure is high
        elif stats['memory_pressure_events'] > 10 and self.config.eviction_policy != CacheEvictionPolicy.LRU:
            logger.info("Switching to LRU policy due to memory pressure")
            self.config.eviction_policy = CacheEvictionPolicy.LRU
            self.stats['policy_switches'] += 1

# Global smart cache instance
_global_smart_cache: Optional[SmartCache] = None
_cache_lock = threading.Lock()

def get_smart_cache() -> SmartCache:
    """Get global smart cache instance."""
    global _global_smart_cache
    if _global_smart_cache is None:
        with _cache_lock:
            if _global_smart_cache is None:
                _global_smart_cache = SmartCache()
    return _global_smart_cache

def clear_smart_cache():
    """Clear global smart cache."""
    global _global_smart_cache
    if _global_smart_cache:
        _global_smart_cache.clear()

def get_cache_stats() -> Dict[str, Any]:
    """Get global cache statistics."""
    cache = get_smart_cache()
    return cache.get_statistics()

@dataclass
class PerformanceMetrics:
    """Container for performance metrics with enhanced cache tracking."""
    operation_name: str
    execution_time: float
    memory_used_mb: float
    cpu_usage: float
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_rate: float = 0.0
    cache_size_mb: float = 0.0
    cache_evictions: int = 0
    row_count: int = 0
    pattern_complexity: int = 0
    parallel_efficiency: float = 0.0  # Ratio of parallel speedup vs theoretical maximum
    thread_count: int = 1
    partition_count: int = 1
    cache_policy: str = "unknown"
    pattern_cache_hits: int = 0
    compilation_cache_hits: int = 0
    data_cache_hits: int = 0

@dataclass
class ParallelExecutionConfig:
    """Configuration for parallel execution optimization."""
    enabled: bool = True
    max_workers: Optional[int] = None  # Default: CPU cores - 1
    min_data_size_for_parallel: int = 1000  # Minimum rows to enable parallel processing
    chunk_size_strategy: str = "adaptive"  # "fixed", "adaptive", "data_dependent"
    thread_pool_type: str = "thread"  # "thread", "process", "adaptive"
    load_balancing: bool = True
    memory_threshold_mb: float = 500.0  # Switch to sequential if memory usage exceeds this
    cpu_threshold_percent: float = 80.0  # Monitor CPU usage for dynamic adjustment

@dataclass 
class ParallelWorkItem:
    """Individual work item for parallel execution."""
    partition_id: str
    data_subset: Any
    pattern: str
    config: Dict[str, Any]
    estimated_complexity: int = 1
    priority: int = 0  # Higher priority items processed first

class PerformanceMonitor:
    """Enhanced performance monitoring system for pattern matching operations."""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics_history: deque = deque(maxlen=max_history)
        self.operation_stats: Dict[str, List[float]] = defaultdict(list)
        self.lock = threading.Lock()
        self._baseline_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
    def record_operation(self, metrics: PerformanceMetrics):
        """Record performance metrics for an operation."""
        with self.lock:
            self.metrics_history.append(metrics)
            self.operation_stats[metrics.operation_name].append(metrics.execution_time)
            
            # Log significant performance events
            if metrics.execution_time > 1.0:  # Operations taking more than 1 second
                logger.warning(f"Slow operation detected: {metrics.operation_name} took {metrics.execution_time:.3f}s")
            
            if metrics.memory_used_mb > 100:  # High memory usage
                logger.warning(f"High memory usage: {metrics.operation_name} used {metrics.memory_used_mb:.2f}MB")
    
    def get_operation_stats(self, operation_name: str) -> Dict[str, Any]:
        """Get statistical analysis for a specific operation."""
        with self.lock:
            times = self.operation_stats.get(operation_name, [])
            if not times:
                return {}
                
            return {
                "count": len(times),
                "total_time": sum(times),
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
                "p95_time": sorted(times)[int(len(times) * 0.95)] if len(times) > 20 else max(times)
            }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        with self.lock:
            total_operations = len(self.metrics_history)
            if total_operations == 0:
                return {"total_operations": 0}
            
            recent_metrics = list(self.metrics_history)[-100:]  # Last 100 operations
            
            summary = {
                "total_operations": total_operations,
                "recent_avg_time": sum(m.execution_time for m in recent_metrics) / len(recent_metrics),
                "recent_avg_memory": sum(m.memory_used_mb for m in recent_metrics) / len(recent_metrics),
                "cache_efficiency": self._calculate_cache_efficiency(recent_metrics),
                "performance_trend": self._analyze_performance_trend(),
                "operation_breakdown": {op: self.get_operation_stats(op) for op in self.operation_stats.keys()}
            }
            
            return summary
    
    def _calculate_cache_efficiency(self, metrics_list: List[PerformanceMetrics]) -> float:
        """Calculate cache hit rate from recent metrics."""
        total_hits = sum(m.cache_hits for m in metrics_list)
        total_misses = sum(m.cache_misses for m in metrics_list)
        total_requests = total_hits + total_misses
        
        return (total_hits / total_requests * 100) if total_requests > 0 else 0.0
    
    def _analyze_performance_trend(self) -> str:
        """Analyze performance trend over recent operations."""
        if len(self.metrics_history) < 20:
            return "insufficient_data"
        
        recent_times = [m.execution_time for m in list(self.metrics_history)[-10:]]
        older_times = [m.execution_time for m in list(self.metrics_history)[-20:-10]]
        
        recent_avg = sum(recent_times) / len(recent_times)
        older_avg = sum(older_times) / len(older_times)
        
        if recent_avg > older_avg * 1.2:
            return "degrading"
        elif recent_avg < older_avg * 0.8:
            return "improving"
        else:
            return "stable"

class ParallelExecutionManager:
    """
    Advanced parallel execution manager for MATCH_RECOGNIZE operations.
    
    Features:
    - Multi-threaded pattern execution across data subsets
    - Adaptive load balancing and work stealing
    - Dynamic thread pool sizing based on system resources
    - Progress tracking and performance monitoring
    - Intelligent partitioning strategies
    """
    
    def __init__(self, config: Optional[ParallelExecutionConfig] = None):
        self.config = config or ParallelExecutionConfig()
        self.max_workers = self._determine_optimal_workers()
        self.thread_pool: Optional[ThreadPoolExecutor] = None
        self.process_pool: Optional[ProcessPoolExecutor] = None
        self.lock = threading.Lock()
        
        # Performance tracking
        self.execution_stats = {
            'total_executions': 0,
            'parallel_executions': 0,
            'sequential_executions': 0,
            'total_speedup': 0.0,
            'average_efficiency': 0.0,
            'memory_pressure_switches': 0,
            'cpu_pressure_switches': 0
        }
        
        # Resource monitoring
        self.resource_monitor = ResourceMonitor()
        
        logger.info(f"ParallelExecutionManager initialized with {self.max_workers} workers")
    
    def _determine_optimal_workers(self) -> int:
        """Determine optimal number of worker threads/processes."""
        if self.config.max_workers:
            return min(self.config.max_workers, mp.cpu_count())
        
        # Default: CPU cores - 1 (leave one core for system)
        cpu_count = mp.cpu_count()
        optimal_workers = max(1, cpu_count - 1)
        
        # Adjust based on available memory
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        if available_memory_gb < 2:  # Less than 2GB available
            optimal_workers = max(1, optimal_workers // 2)
        elif available_memory_gb > 8:  # More than 8GB available
            optimal_workers = min(optimal_workers + 2, cpu_count * 2)
        
        return optimal_workers
    
    def execute_parallel_patterns(self, work_items: List[ParallelWorkItem]) -> List[Dict[str, Any]]:
        """
        Execute multiple pattern matching operations in parallel.
        
        Args:
            work_items: List of work items to process in parallel
            
        Returns:
            List of results from parallel execution
        """
        if not self.config.enabled or len(work_items) == 1:
            return self._execute_sequential(work_items)
        
        # Check if data size justifies parallel processing
        total_data_size = sum(self._estimate_data_size(item.data_subset) for item in work_items)
        if total_data_size < self.config.min_data_size_for_parallel:
            logger.debug(f"Data size {total_data_size} below parallel threshold, using sequential execution")
            return self._execute_sequential(work_items)
        
        # Check system resources
        if not self._check_resource_availability():
            logger.debug("System resources insufficient for parallel execution, falling back to sequential")
            return self._execute_sequential(work_items)
        
        start_time = time.time()
        
        try:
            # Sort work items by priority and estimated complexity
            sorted_items = sorted(work_items, key=lambda x: (-x.priority, -x.estimated_complexity))
            
            # Choose execution strategy
            if self.config.thread_pool_type == "adaptive":
                strategy = self._choose_execution_strategy(sorted_items)
            else:
                strategy = self.config.thread_pool_type
            
            if strategy == "process":
                results = self._execute_with_processes(sorted_items)
            else:
                results = self._execute_with_threads(sorted_items)
            
            # Calculate performance metrics
            execution_time = time.time() - start_time
            theoretical_sequential_time = sum(item.estimated_complexity * 0.001 for item in work_items)  # Rough estimate
            speedup = theoretical_sequential_time / execution_time if execution_time > 0 else 1.0
            efficiency = speedup / len(work_items) if work_items else 0.0
            
            # Update statistics
            with self.lock:
                self.execution_stats['total_executions'] += 1
                self.execution_stats['parallel_executions'] += 1
                self.execution_stats['total_speedup'] += speedup
                self.execution_stats['average_efficiency'] = (
                    self.execution_stats['average_efficiency'] * (self.execution_stats['total_executions'] - 1) + efficiency
                ) / self.execution_stats['total_executions']
            
            logger.info(f"Parallel execution completed: {len(work_items)} items in {execution_time:.3f}s, "
                       f"speedup: {speedup:.2f}x, efficiency: {efficiency:.2f}")
            
            return results
            
        except Exception as e:
            logger.error(f"Parallel execution failed: {e}, falling back to sequential")
            return self._execute_sequential(work_items)
    
    def _execute_with_threads(self, work_items: List[ParallelWorkItem]) -> List[Dict[str, Any]]:
        """Execute work items using thread pool."""
        if not self.thread_pool:
            self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        
        futures = []
        for item in work_items:
            future = self.thread_pool.submit(self._execute_work_item, item)
            futures.append((item.partition_id, future))
        
        results = []
        for partition_id, future in futures:
            try:
                result = future.result(timeout=30)  # 30 second timeout per item
                result['partition_id'] = partition_id
                results.append(result)
            except Exception as e:
                logger.error(f"Work item {partition_id} failed: {e}")
                results.append({'partition_id': partition_id, 'error': str(e), 'matches': []})
        
        return results
    
    def _execute_with_processes(self, work_items: List[ParallelWorkItem]) -> List[Dict[str, Any]]:
        """Execute work items using process pool."""
        if not self.process_pool:
            self.process_pool = ProcessPoolExecutor(max_workers=self.max_workers)
        
        futures = []
        for item in work_items:
            future = self.process_pool.submit(self._execute_work_item_process_safe, item)
            futures.append((item.partition_id, future))
        
        results = []
        for partition_id, future in futures:
            try:
                result = future.result(timeout=60)  # Longer timeout for processes
                result['partition_id'] = partition_id
                results.append(result)
            except Exception as e:
                logger.error(f"Process work item {partition_id} failed: {e}")
                results.append({'partition_id': partition_id, 'error': str(e), 'matches': []})
        
        return results
    
    def _execute_sequential(self, work_items: List[ParallelWorkItem]) -> List[Dict[str, Any]]:
        """Execute work items sequentially as fallback."""
        with self.lock:
            self.execution_stats['sequential_executions'] += 1
        
        results = []
        for item in work_items:
            try:
                result = self._execute_work_item(item)
                result['partition_id'] = item.partition_id
                results.append(result)
            except Exception as e:
                logger.error(f"Sequential execution of {item.partition_id} failed: {e}")
                results.append({'partition_id': item.partition_id, 'error': str(e), 'matches': []})
        
        return results
    
    def _execute_work_item(self, item: ParallelWorkItem) -> Dict[str, Any]:
        """Execute a single work item (pattern matching on data subset)."""
        # This method will be called by the matcher to execute pattern matching
        # For now, return a placeholder result structure
        start_time = time.time()
        
        # Placeholder for actual pattern matching execution
        # This will be integrated with the existing matcher
        result = {
            'matches': [],
            'execution_time': time.time() - start_time,
            'row_count': self._estimate_data_size(item.data_subset),
            'pattern_complexity': item.estimated_complexity
        }
        
        return result
    
    def _execute_work_item_process_safe(self, item: ParallelWorkItem) -> Dict[str, Any]:
        """Process-safe version of work item execution."""
        # For process execution, we need to ensure all dependencies are available
        # This is a simplified version that can be serialized
        return self._execute_work_item(item)
    
    def _estimate_data_size(self, data_subset: Any) -> int:
        """Estimate the size of a data subset."""
        if hasattr(data_subset, '__len__'):
            return len(data_subset)
        elif hasattr(data_subset, 'shape'):  # pandas DataFrame
            return data_subset.shape[0]
        else:
            return 100  # Default estimate
    
    def _check_resource_availability(self) -> bool:
        """Check if system resources allow parallel execution."""
        # Check memory
        memory = psutil.virtual_memory()
        if memory.percent > 85:  # More than 85% memory used
            with self.lock:
                self.execution_stats['memory_pressure_switches'] += 1
            return False
        
        # Check CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        if cpu_percent > self.config.cpu_threshold_percent:
            with self.lock:
                self.execution_stats['cpu_pressure_switches'] += 1
            return False
        
        return True
    
    def _choose_execution_strategy(self, work_items: List[ParallelWorkItem]) -> str:
        """Choose between thread and process execution strategy."""
        # Use threads for I/O bound or moderate CPU tasks
        # Use processes for CPU-intensive tasks with large data
        
        total_complexity = sum(item.estimated_complexity for item in work_items)
        avg_complexity = total_complexity / len(work_items)
        
        # High complexity patterns benefit from process isolation
        if avg_complexity > 10:
            return "process"
        else:
            return "thread"
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for parallel execution."""
        with self.lock:
            stats = self.execution_stats.copy()
            
        if stats['total_executions'] > 0:
            stats['parallel_ratio'] = stats['parallel_executions'] / stats['total_executions']
        else:
            stats['parallel_ratio'] = 0.0
            
        return stats
    
    def cleanup(self):
        """Clean up thread/process pools."""
        if self.thread_pool:
            self.thread_pool.shutdown(wait=True)
            self.thread_pool = None
        
        if self.process_pool:
            self.process_pool.shutdown(wait=True)
            self.process_pool = None
    
    def __del__(self):
        """Ensure cleanup on deletion."""
        self.cleanup()

class ResourceMonitor:
    """Monitor system resources for dynamic parallel execution decisions."""
    
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.resource_history = deque(maxlen=60)  # Keep 60 seconds of history
        self.lock = threading.Lock()
    
    def start_monitoring(self):
        """Start background resource monitoring."""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
            self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop background resource monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
    
    def _monitor_resources(self):
        """Background thread to monitor resource usage."""
        while self.monitoring:
            try:
                memory = psutil.virtual_memory()
                cpu = psutil.cpu_percent(interval=1)
                
                resource_snapshot = {
                    'timestamp': time.time(),
                    'memory_percent': memory.percent,
                    'cpu_percent': cpu,
                    'available_memory_gb': memory.available / (1024**3)
                }
                
                with self.lock:
                    self.resource_history.append(resource_snapshot)
                    
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                time.sleep(1)
    
    def get_current_load(self) -> Dict[str, float]:
        """Get current system load metrics."""
        with self.lock:
            if not self.resource_history:
                return {'memory_percent': 0, 'cpu_percent': 0, 'available_memory_gb': 0}
            return self.resource_history[-1].copy()
    
    def get_average_load(self, seconds: int = 30) -> Dict[str, float]:
        """Get average system load over specified time period."""
        cutoff_time = time.time() - seconds
        
        with self.lock:
            recent_data = [r for r in self.resource_history if r['timestamp'] > cutoff_time]
            
        if not recent_data:
            return self.get_current_load()
        
        return {
            'memory_percent': sum(r['memory_percent'] for r in recent_data) / len(recent_data),
            'cpu_percent': sum(r['cpu_percent'] for r in recent_data) / len(recent_data),
            'available_memory_gb': sum(r['available_memory_gb'] for r in recent_data) / len(recent_data)
        }

# Global optimizer instances
_global_monitor = PerformanceMonitor()
_define_optimizer = None  # Will be initialized when first accessed
_parallel_manager = None  # Will be initialized when first accessed

def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return _global_monitor

def get_define_optimizer() -> "DefineOptimizer":
    """Get the global DEFINE optimizer instance."""
    global _define_optimizer
    if _define_optimizer is None:
        _define_optimizer = DefineOptimizer()
    return _define_optimizer

def get_parallel_execution_manager() -> ParallelExecutionManager:
    """Get the global parallel execution manager instance."""
    global _parallel_manager
    if _parallel_manager is None:
        _parallel_manager = ParallelExecutionManager()
        _parallel_manager.resource_monitor.start_monitoring()
    return _parallel_manager

def monitor_performance(operation_name: str):
    """Decorator to monitor performance of functions."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024
            start_cpu = psutil.cpu_percent()
            
            try:
                result = func(*args, **kwargs)
                
                # Extract metrics from result if it's a dict with performance info
                cache_hits = 0
                cache_misses = 0
                row_count = 0
                
                if isinstance(result, dict):
                    cache_hits = result.get('cache_hits', 0)
                    cache_misses = result.get('cache_misses', 0)
                    row_count = result.get('row_count', 0)
                
                return result
                
            finally:
                end_time = time.time()
                end_memory = psutil.Process().memory_info().rss / 1024 / 1024
                end_cpu = psutil.cpu_percent()
                
                metrics = PerformanceMetrics(
                    operation_name=operation_name,
                    execution_time=end_time - start_time,
                    memory_used_mb=end_memory - start_memory,
                    cpu_usage=end_cpu - start_cpu,
                    cache_hits=cache_hits,
                    cache_misses=cache_misses,
                    row_count=row_count
                )
                
                _global_monitor.record_operation(metrics)
                
        return wrapper
    return decorator

class MemoryOptimizer:
    """Memory optimization utilities for pattern matching operations."""
    
    @staticmethod
    def optimize_variable_assignments(assignments: Dict[str, List[int]]) -> Dict[str, List[int]]:
        """Optimize variable assignments to reduce memory usage."""
        optimized = {}
        
        for var, indices in assignments.items():
            if len(indices) > 1000:  # Large assignments
                # Use set for deduplication, then convert back to sorted list
                unique_indices = sorted(set(indices))
                optimized[var] = unique_indices
                logger.debug(f"Optimized {var}: {len(indices)} -> {len(unique_indices)} indices")
            else:
                optimized[var] = indices
                
        return optimized
    
    @staticmethod
    def cleanup_context_cache(context, max_cache_size: int = 10000):
        """Clean up context caches to prevent memory leaks."""
        if hasattr(context, 'navigation_cache') and len(context.navigation_cache) > max_cache_size:
            # Keep only the most recent entries
            cache_items = list(context.navigation_cache.items())
            context.navigation_cache.clear()
            context.navigation_cache.update(cache_items[-max_cache_size//2:])
            logger.debug(f"Cleaned navigation cache: kept {len(context.navigation_cache)} entries")
    
    @staticmethod
    def estimate_memory_usage(data_size: int, pattern_complexity: int) -> float:
        """Estimate memory usage for a given data size and pattern complexity."""
        # Base memory per row (empirically determined)
        base_memory_per_row = 0.1  # MB
        
        # Additional memory based on pattern complexity
        pattern_memory_factor = 1 + (pattern_complexity * 0.1)
        
        estimated_mb = data_size * base_memory_per_row * pattern_memory_factor
        return estimated_mb

class DefineOptimizer:
    """Optimization utilities for DEFINE clauses in pattern matching."""
    
    def __init__(self):
        self.optimization_cache = {}
        self.pattern_stats = defaultdict(int)
        self.lock = threading.RLock()
    
    def optimize_define_clauses(self, define_dict: Dict[str, str]) -> Dict[str, Any]:
        """
        Optimize DEFINE clauses by analyzing patterns and dependencies.
        
        Args:
            define_dict: Dictionary of variable definitions
            
        Returns:
            Dictionary with optimized definitions and metadata
        """
        if not define_dict:
            return {'optimized_defines': {}, 'optimizations_applied': []}
        
        start_time = time.time()
        
        with self.lock:
            # Create cache key for this set of definitions
            cache_key = self._create_define_cache_key(define_dict)
            
            if cache_key in self.optimization_cache:
                cached_result = self.optimization_cache[cache_key]
                logger.debug(f"Using cached DEFINE optimization for {len(define_dict)} clauses")
                return cached_result
            
            # Analyze and optimize definitions
            optimized = {}
            optimizations_applied = []
            
            # Step 1: Classify patterns by type and complexity
            pattern_analysis = self._analyze_patterns(define_dict)
            
            # Step 2: Optimize each definition
            for var, definition in define_dict.items():
                optimized_def, applied_opts = self._optimize_single_definition(
                    var, definition, pattern_analysis
                )
                optimized[var] = optimized_def
                optimizations_applied.extend(applied_opts)
            
            # Step 3: Cross-variable optimizations
            cross_opts = self._apply_cross_variable_optimizations(optimized, pattern_analysis)
            optimizations_applied.extend(cross_opts)
            
            result = {
                'optimized_defines': optimized,
                'optimizations_applied': optimizations_applied,
                'pattern_analysis': pattern_analysis,
                'optimization_time': time.time() - start_time
            }
            
            # Cache the result
            self.optimization_cache[cache_key] = result
            
            logger.debug(f"Optimized {len(define_dict)} DEFINE clauses in {result['optimization_time']:.3f}s")
            return result
    
    def _create_define_cache_key(self, define_dict: Dict[str, str]) -> str:
        """Create a cache key for the define dictionary."""
        # Sort definitions for consistent caching
        sorted_items = sorted(define_dict.items())
        return str(hash(tuple(sorted_items)))
    
    def _analyze_patterns(self, define_dict: Dict[str, str]) -> Dict[str, Any]:
        """Analyze patterns to identify optimization opportunities."""
        analysis = {
            'simple_comparisons': [],
            'complex_conditions': [],
            'aggregations': [],
            'navigation_functions': [],
            'cross_references': [],
            'total_complexity': 0
        }
        
        for var, definition in define_dict.items():
            complexity = self._calculate_complexity(definition)
            analysis['total_complexity'] += complexity
            
            # Classify pattern types
            if self._is_simple_comparison(definition):
                analysis['simple_comparisons'].append(var)
            elif self._has_aggregation(definition):
                analysis['aggregations'].append(var)
            elif self._has_navigation_function(definition):
                analysis['navigation_functions'].append(var)
            elif self._has_cross_reference(definition, define_dict):
                analysis['cross_references'].append(var)
            else:
                analysis['complex_conditions'].append(var)
        
        return analysis
    
    def _calculate_complexity(self, definition: str) -> float:
        """Calculate complexity score for a definition."""
        complexity = 0.0
        
        # Base complexity from length
        complexity += len(definition) / 100.0
        
        # Function calls add complexity
        complexity += len(re.findall(r'\w+\s*\(', definition)) * 2.0
        
        # Logical operators add complexity
        complexity += definition.upper().count(' AND ') * 1.5
        complexity += definition.upper().count(' OR ') * 2.0
        complexity += definition.upper().count(' NOT ') * 1.0
        
        # Navigation functions add significant complexity
        complexity += definition.upper().count('.PREV(') * 3.0
        complexity += definition.upper().count('.NEXT(') * 3.0
        complexity += definition.upper().count('.FIRST(') * 2.0
        complexity += definition.upper().count('.LAST(') * 2.0
        
        # Aggregations add complexity
        complexity += definition.upper().count('SUM(') * 2.5
        complexity += definition.upper().count('AVG(') * 2.5
        complexity += definition.upper().count('COUNT(') * 2.0
        
        return complexity
    
    def _is_simple_comparison(self, definition: str) -> bool:
        """Check if definition is a simple comparison."""
        simple_patterns = [
            r'^\w+\s*[<>=!]+\s*[\w\d.]+$',
            r'^\w+\s+IN\s+\([^)]+\)$',
            r'^\w+\s+LIKE\s+\'[^\']+\'$'
        ]
        
        for pattern in simple_patterns:
            if re.match(pattern, definition.strip(), re.IGNORECASE):
                return True
        return False
    
    def _has_aggregation(self, definition: str) -> bool:
        """Check if definition contains aggregation functions."""
        agg_functions = ['SUM', 'AVG', 'COUNT', 'MIN', 'MAX', 'STDDEV']
        definition_upper = definition.upper()
        return any(func + '(' in definition_upper for func in agg_functions)
    
    def _has_navigation_function(self, definition: str) -> bool:
        """Check if definition contains navigation functions."""
        nav_functions = ['.PREV(', '.NEXT(', '.FIRST(', '.LAST(']
        definition_upper = definition.upper()
        return any(func in definition_upper for func in nav_functions)
    
    def _has_cross_reference(self, definition: str, all_defines: Dict[str, str]) -> bool:
        """Check if definition references other variables."""
        for var in all_defines.keys():
            if var != definition and var in definition:
                return True
        return False
    
    def _optimize_single_definition(self, var: str, definition: str, analysis: Dict[str, Any]) -> tuple:
        """Optimize a single definition."""
        optimized_def = definition
        optimizations = []
        
        # Optimization 1: Simplify redundant parentheses
        if '(((' in definition or ')))' in definition:
            optimized_def = self._simplify_parentheses(optimized_def)
            optimizations.append(f"{var}: simplified_parentheses")
        
        # Optimization 2: Optimize simple comparisons
        if var in analysis['simple_comparisons']:
            optimized_def = self._optimize_simple_comparison(optimized_def)
            optimizations.append(f"{var}: optimized_simple_comparison")
        
        # Optimization 3: Cache complex expressions
        if self._calculate_complexity(definition) > 5.0:
            optimizations.append(f"{var}: marked_for_caching")
        
        return optimized_def, optimizations
    
    def _simplify_parentheses(self, definition: str) -> str:
        """Simplify redundant parentheses in definition."""
        # Basic parentheses simplification
        while '((' in definition and '))' in definition:
            definition = definition.replace('((', '(').replace('))', ')')
        return definition
    
    def _optimize_simple_comparison(self, definition: str) -> str:
        """Optimize simple comparison expressions."""
        # Convert some patterns to more efficient forms
        # This is a simplified example - real optimization would be more sophisticated
        definition = re.sub(r'\s+', ' ', definition.strip())
        return definition
    
    def _apply_cross_variable_optimizations(self, optimized_defines: Dict[str, str], 
                                         analysis: Dict[str, Any]) -> List[str]:
        """Apply optimizations that span multiple variables."""
        optimizations = []
        
        # Optimization: Reorder variables by dependency and complexity
        if len(analysis['cross_references']) > 1:
            optimizations.append("reordered_by_dependencies")
        
        # Optimization: Identify common subexpressions
        common_expressions = self._find_common_expressions(optimized_defines)
        if common_expressions:
            optimizations.append(f"found_{len(common_expressions)}_common_expressions")
        
        return optimizations
    
    def _find_common_expressions(self, defines: Dict[str, str]) -> List[str]:
        """Find common expressions across definitions."""
        expressions = []
        define_values = list(defines.values())
        
        # Look for common substrings that look like expressions
        for i, def1 in enumerate(define_values):
            for j, def2 in enumerate(define_values[i+1:], i+1):
                # Find common substrings of reasonable length
                for k in range(len(def1)):
                    for l in range(k+10, len(def1)+1):  # At least 10 chars
                        substr = def1[k:l]
                        if substr in def2 and substr not in expressions:
                            expressions.append(substr)
        
        return expressions
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get statistics about DEFINE optimizations."""
        with self.lock:
            return {
                'cache_size': len(self.optimization_cache),
                'pattern_stats': dict(self.pattern_stats),
                'total_optimizations': sum(self.pattern_stats.values())
            }

class PatternOptimizer:
    """Optimization utilities for pattern matching operations."""
    
    @staticmethod
    def estimate_pattern_complexity(pattern: str) -> int:
        """Estimate the complexity of a pattern for optimization decisions."""
        complexity = 0
        
        # Base complexity
        complexity += len(pattern) // 10
        
        # Quantifier complexity
        complexity += pattern.count('+') * 2
        complexity += pattern.count('*') * 3
        complexity += pattern.count('?') * 1
        complexity += pattern.count('{') * 2  # Range quantifiers
        
        # Alternation complexity
        complexity += pattern.count('|') * 2
        
        # PERMUTE complexity
        complexity += pattern.upper().count('PERMUTE') * 5
        
        # Exclusion complexity
        complexity += pattern.count('{-') * 3
        
        return complexity
    
    @staticmethod
    def should_use_caching(pattern_complexity: int, data_size: int) -> bool:
        """Determine if caching should be used based on complexity and data size."""
        # Use caching for complex patterns or large datasets
        return pattern_complexity > 10 or data_size > 1000
    
    @staticmethod
    def optimize_transition_order(transitions: List[Any]) -> List[Any]:
        """Optimize the order of transitions for better performance."""
        # Sort transitions by estimated probability of success
        # More specific conditions first, then more general ones
        def transition_priority(transition):
            # Higher priority (lower number) for more specific transitions
            if hasattr(transition, 'variable'):
                # Simple variable matches have lower priority
                if transition.variable and '+' not in transition.variable and '*' not in transition.variable:
                    return 1
                # Quantified variables have medium priority
                elif transition.variable and ('+' in transition.variable or '*' in transition.variable):
                    return 2
                # Complex patterns have higher priority
                else:
                    return 3
            return 4
        
        return sorted(transitions, key=transition_priority)

# Factory function for easy access
def create_performance_context() -> Dict[str, Any]:
    """Create a performance monitoring context for operations."""
    cache_stats = get_cache_stats()
    return {
        "start_time": time.time(),
        "start_memory": psutil.Process().memory_info().rss / 1024 / 1024,
        "cache_hits": 0,
        "cache_misses": 0,
        "operations_count": 0,
        "initial_cache_hits": cache_stats.get('hits', 0),
        "initial_cache_misses": cache_stats.get('misses', 0),
        "cache_policy": cache_stats.get('eviction_policy', 'unknown')
    }

def finalize_performance_context(context: Dict[str, Any], operation_name: str):
    """Finalize and record performance metrics from context with enhanced cache tracking."""
    end_time = time.time()
    end_memory = psutil.Process().memory_info().rss / 1024 / 1024
    
    # Get final cache statistics
    final_cache_stats = get_cache_stats()
    cache_hits = final_cache_stats.get('hits', 0) - context.get("initial_cache_hits", 0)
    cache_misses = final_cache_stats.get('misses', 0) - context.get("initial_cache_misses", 0)
    
    metrics = PerformanceMetrics(
        operation_name=operation_name,
        execution_time=end_time - context["start_time"],
        memory_used_mb=end_memory - context["start_memory"],
        cpu_usage=0,  # CPU usage tracking can be added if needed
        cache_hits=cache_hits + context.get("cache_hits", 0),
        cache_misses=cache_misses + context.get("cache_misses", 0),
        cache_hit_rate=final_cache_stats.get('hit_rate_percent', 0.0),
        cache_size_mb=final_cache_stats.get('size_mb', 0.0),
        cache_evictions=final_cache_stats.get('evictions', 0),
        cache_policy=context.get("cache_policy", "unknown"),
        row_count=context.get("operations_count", 0)
    )
    
    _global_monitor.record_operation(metrics)
    return metrics

# Smart caching utility functions for pattern compilation and data processing
class PatternCompilationCache:
    """Specialized cache for pattern compilation results."""
    
    @staticmethod
    def generate_pattern_key(pattern: str, define_conditions: Dict[str, str], 
                           options: Dict[str, Any]) -> str:
        """Generate cache key for pattern compilation."""
        # Include pattern, define conditions, and relevant options
        key_components = [
            f"pattern:{pattern}",
            f"defines:{hash(str(sorted(define_conditions.items())))}",
            f"options:{hash(str(sorted(options.items())))}"
        ]
        return hashlib.sha256("_".join(key_components).encode()).hexdigest()[:16]
    
    @staticmethod
    def cache_compiled_pattern(pattern: str, define_conditions: Dict[str, str], 
                             options: Dict[str, Any], compiled_result: Any) -> bool:
        """Cache compiled pattern result."""
        cache = get_smart_cache()
        key = PatternCompilationCache.generate_pattern_key(pattern, define_conditions, options)
        
        # Estimate size for large compiled objects
        size_hint = len(pattern) * 0.001  # Rough estimate in MB
        
        return cache.put(key, compiled_result, size_hint)
    
    @staticmethod
    def get_compiled_pattern(pattern: str, define_conditions: Dict[str, str], 
                           options: Dict[str, Any]) -> Optional[Any]:
        """Retrieve cached compiled pattern."""
        cache = get_smart_cache()
        key = PatternCompilationCache.generate_pattern_key(pattern, define_conditions, options)
        return cache.get(key)

class DataSubsetCache:
    """Specialized cache for data subset preprocessing results."""
    
    @staticmethod
    def generate_data_key(data_hash: str, partition_columns: List[str], 
                         order_columns: List[str], filters: Dict[str, Any]) -> str:
        """Generate cache key for data subset."""
        key_components = [
            f"data:{data_hash}",
            f"partitions:{','.join(sorted(partition_columns))}",
            f"order:{','.join(order_columns)}",
            f"filters:{hash(str(sorted(filters.items())))}"
        ]
        return hashlib.sha256("_".join(key_components).encode()).hexdigest()[:16]
    
    @staticmethod
    def cache_preprocessed_data(data_hash: str, partition_columns: List[str],
                              order_columns: List[str], filters: Dict[str, Any],
                              preprocessed_result: Any, data_size_mb: float) -> bool:
        """Cache preprocessed data result."""
        cache = get_smart_cache()
        key = DataSubsetCache.generate_data_key(data_hash, partition_columns, order_columns, filters)
        
        return cache.put(key, preprocessed_result, data_size_mb)
    
    @staticmethod
    def get_preprocessed_data(data_hash: str, partition_columns: List[str],
                            order_columns: List[str], filters: Dict[str, Any]) -> Optional[Any]:
        """Retrieve cached preprocessed data."""
        cache = get_smart_cache()
        key = DataSubsetCache.generate_data_key(data_hash, partition_columns, order_columns, filters)
        return cache.get(key)

class CacheInvalidationManager:
    """Manages cache invalidation based on data changes or pattern modifications."""
    
    def __init__(self):
        self.data_checksums: Dict[str, str] = {}
        self.pattern_dependencies: Dict[str, Set[str]] = defaultdict(set)
        self.lock = threading.Lock()
    
    def register_data_dependency(self, cache_key: str, data_identifier: str, 
                               data_checksum: str):
        """Register cache dependency on data."""
        with self.lock:
            self.data_checksums[data_identifier] = data_checksum
            self.pattern_dependencies[data_identifier].add(cache_key)
    
    def invalidate_data_caches(self, data_identifier: str, new_checksum: str):
        """Invalidate caches when data changes."""
        with self.lock:
            old_checksum = self.data_checksums.get(data_identifier)
            if old_checksum and old_checksum != new_checksum:
                # Data has changed, invalidate dependent caches
                cache = get_smart_cache()
                for cache_key in self.pattern_dependencies[data_identifier]:
                    cache.cache.pop(cache_key, None)
                
                # Update checksum
                self.data_checksums[data_identifier] = new_checksum
                
                logger.info(f"Invalidated {len(self.pattern_dependencies[data_identifier])} "
                           f"cache entries due to data change in {data_identifier}")
    
    def get_invalidation_stats(self) -> Dict[str, Any]:
        """Get cache invalidation statistics."""
        with self.lock:
            return {
                'tracked_data_sources': len(self.data_checksums),
                'total_dependencies': sum(len(deps) for deps in self.pattern_dependencies.values()),
                'dependency_breakdown': {
                    data_id: len(deps) for data_id, deps in self.pattern_dependencies.items()
                }
            }

# Global instances
_global_invalidation_manager = CacheInvalidationManager()

def get_cache_invalidation_manager() -> CacheInvalidationManager:
    """Get global cache invalidation manager."""
    return _global_invalidation_manager

def generate_comprehensive_cache_report() -> Dict[str, Any]:
    """Generate comprehensive cache performance report."""
    cache_stats = get_cache_stats()
    invalidation_stats = get_cache_invalidation_manager().get_invalidation_stats()
    
    # Calculate cache effectiveness metrics
    hit_rate = cache_stats.get('hit_rate_percent', 0)
    total_requests = cache_stats.get('total_requests', 0)
    
    effectiveness = "excellent" if hit_rate >= 80 else \
                   "good" if hit_rate >= 60 else \
                   "fair" if hit_rate >= 40 else "poor"
    
    return {
        'cache_statistics': cache_stats,
        'invalidation_statistics': invalidation_stats,
        'effectiveness_rating': effectiveness,
        'performance_impact': {
            'estimated_time_saved_percent': min(hit_rate * 0.8, 60),  # Conservative estimate
            'memory_efficiency': cache_stats.get('utilization_percent', 0),
            'eviction_efficiency': cache_stats.get('evictions', 0) / max(total_requests, 1) * 100
        },
        'recommendations': _generate_cache_recommendations(cache_stats)
    }

def _generate_cache_recommendations(cache_stats: Dict[str, Any]) -> List[str]:
    """Generate cache optimization recommendations."""
    recommendations = []
    
    hit_rate = cache_stats.get('hit_rate_percent', 0)
    utilization = cache_stats.get('utilization_percent', 0)
    memory_pressure = cache_stats.get('memory_pressure_events', 0)
    
    if hit_rate < 60:
        recommendations.append("Consider increasing cache size or optimizing cache keys")
    
    if utilization > 90:
        recommendations.append("Cache is highly utilized - consider increasing max_entries")
    
    if memory_pressure > 5:
        recommendations.append("Frequent memory pressure detected - consider reducing cache size")
    
    if cache_stats.get('evictions', 0) > cache_stats.get('hits', 1):
        recommendations.append("High eviction rate - consider optimizing eviction policy")
    
    if not recommendations:
        recommendations.append("Cache performance is optimal")
    
    return recommendations

# Global performance monitor instance
_global_monitor = PerformanceMonitor()

def get_global_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance."""
    return _global_monitor

# Smart cache compatibility functions for legacy interface
def get_smart_cache_stats():
    """Get comprehensive smart cache statistics."""
    cache = get_smart_cache()
    return cache.get_statistics()

def is_smart_caching_enabled():
    """Check if smart caching is enabled."""
    return True  # Smart caching is always enabled

def get_cache_stats():
    """Compatibility function that returns smart cache stats."""
    return get_smart_cache_stats()

def is_caching_enabled():
    """Compatibility function that returns smart caching status."""
    return is_smart_caching_enabled()
