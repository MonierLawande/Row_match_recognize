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

@dataclass
class SmartCacheConfig:
    """Configuration for smart caching system."""
    max_size_mb: float = 100.0  # Maximum cache size in MB
    max_entries: int = 10000  # Maximum number of cache entries
    eviction_policy: CacheEvictionPolicy = CacheEvictionPolicy.ADAPTIVE
    ttl_seconds: float = 3600.0  # Time to live for TTL policy
    hit_rate_target: float = 0.7  # Target cache hit rate (70%)
    memory_pressure_threshold: float = 0.8  # Memory pressure threshold
    enable_statistics: bool = True
    enable_persistence: bool = False  # Save cache to disk
    compression_enabled: bool = True

@dataclass
class CacheEntry:
    """Individual cache entry with metadata."""
    key: str
    value: Any
    timestamp: float
    access_count: int = 0
    last_access: float = 0.0
    size_bytes: int = 0
    ttl: Optional[float] = None
    
    def __post_init__(self):
        self.last_access = self.timestamp
        if self.size_bytes == 0:
            self.size_bytes = self._estimate_size()
    
    def _estimate_size(self) -> int:
        """Estimate memory size of the cache entry."""
        try:
            # Rough estimation using pickle
            return len(pickle.dumps(self.value))
        except:
            # Fallback estimation
            if isinstance(self.value, str):
                return len(self.value) * 2  # Unicode
            elif isinstance(self.value, (list, tuple)):
                return len(self.value) * 8
            elif isinstance(self.value, dict):
                return len(self.value) * 16
            else:
                return 64  # Default estimate

class SmartCache:
    """
    Intelligent caching system for pattern matching operations.
    
    Features:
    - Multiple eviction policies (LRU, LFU, Adaptive, TTL)
    - Memory pressure monitoring and adaptive sizing
    - Cache hit/miss rate tracking and optimization
    - Pattern-aware caching with intelligent key generation
    - Cross-instance cache sharing
    - Cache statistics and performance reporting
    """
    
    def __init__(self, config: Optional[SmartCacheConfig] = None):
        self.config = config or SmartCacheConfig()
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
        
        # Statistics tracking
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'size_bytes': 0,
            'entries_count': 0,
            'memory_pressure_events': 0,
            'policy_switches': 0
        }
        
        # Access pattern tracking for adaptive policy
        self.access_patterns = defaultdict(list)
        self.frequency_counter = defaultdict(int)
        
        # Memory monitoring
        self.memory_monitor = psutil.Process()
        self.last_memory_check = time.time()
        
        logger.info(f"SmartCache initialized with {self.config.eviction_policy.value} policy, "
                   f"max_size: {self.config.max_size_mb}MB, max_entries: {self.config.max_entries}")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        with self.lock:
            if key not in self.cache:
                self.stats['misses'] += 1
                return None
            
            entry = self.cache[key]
            
            # Check TTL expiration
            if self._is_expired(entry):
                del self.cache[key]
                self.stats['misses'] += 1
                self.stats['entries_count'] -= 1
                self.stats['size_bytes'] -= entry.size_bytes
                return None
            
            # Update access metadata
            entry.last_access = time.time()
            entry.access_count += 1
            self.frequency_counter[key] += 1
            
            # Move to end for LRU
            if self.config.eviction_policy == CacheEvictionPolicy.LRU:
                self.cache.move_to_end(key)
            
            # Track access patterns for adaptive policy
            if self.config.eviction_policy == CacheEvictionPolicy.ADAPTIVE:
                self.access_patterns[key].append(time.time())
                # Keep only recent access times (last hour)
                cutoff = time.time() - 3600
                self.access_patterns[key] = [t for t in self.access_patterns[key] if t > cutoff]
            
            self.stats['hits'] += 1
            return entry.value
    
    def put(self, key: str, value: Any, size_hint: Optional[float] = None) -> bool:
        """
        Store value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            size_hint: Optional size hint in MB
            
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
            
            # Override size if hint provided
            if size_hint:
                entry.size_bytes = int(size_hint * 1024 * 1024)
            
            # Check if we need to evict entries
            self._ensure_capacity(entry.size_bytes)
            
            # Update existing entry or add new one
            if key in self.cache:
                old_entry = self.cache[key]
                self.stats['size_bytes'] -= old_entry.size_bytes
            else:
                self.stats['entries_count'] += 1
            
            self.cache[key] = entry
            self.stats['size_bytes'] += entry.size_bytes
            
            # Move to end for LRU
            if self.config.eviction_policy == CacheEvictionPolicy.LRU:
                self.cache.move_to_end(key)
            
            return True
    
    def _ensure_capacity(self, new_entry_size: int):
        """Ensure cache has capacity for new entry."""
        # Check memory pressure
        if self._check_memory_pressure():
            self.stats['memory_pressure_events'] += 1
            self._adaptive_resize()
        
        # Evict entries based on policy
        max_size_bytes = self.config.max_size_mb * 1024 * 1024
        
        while (len(self.cache) >= self.config.max_entries or 
               self.stats['size_bytes'] + new_entry_size > max_size_bytes):
            
            if not self.cache:
                break
                
            self._evict_based_on_policy()
    
    def _evict_based_on_policy(self):
        """Evict entries based on configured policy."""
        if not self.cache:
            return
        
        evicted_key = None
        
        if self.config.eviction_policy == CacheEvictionPolicy.LRU:
            # Remove least recently used (first item in OrderedDict)
            evicted_key = next(iter(self.cache))
        
        elif self.config.eviction_policy == CacheEvictionPolicy.LFU:
            # Remove least frequently used
            evicted_key = min(self.cache.keys(), 
                            key=lambda k: self.cache[k].access_count)
        
        elif self.config.eviction_policy == CacheEvictionPolicy.TTL:
            # Remove expired entries first, then oldest
            current_time = time.time()
            expired_keys = [k for k, v in self.cache.items() 
                          if self._is_expired(v)]
            if expired_keys:
                evicted_key = expired_keys[0]
            else:
                evicted_key = min(self.cache.keys(), 
                                key=lambda k: self.cache[k].timestamp)
        
        elif self.config.eviction_policy == CacheEvictionPolicy.ADAPTIVE:
            # Adaptive policy based on access patterns
            evicted_key = self._adaptive_eviction()
        
        elif self.config.eviction_policy == CacheEvictionPolicy.SIZE_BASED:
            # Remove largest entries first
            evicted_key = max(self.cache.keys(), 
                            key=lambda k: self.cache[k].size_bytes)
        
        if evicted_key:
            entry = self.cache[evicted_key]
            del self.cache[evicted_key]
            self.stats['evictions'] += 1
            self.stats['entries_count'] -= 1
            self.stats['size_bytes'] -= entry.size_bytes
            
            # Clean up tracking data
            if evicted_key in self.access_patterns:
                del self.access_patterns[evicted_key]
            if evicted_key in self.frequency_counter:
                del self.frequency_counter[evicted_key]
    
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
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'hit_rate_percent': hit_rate,
                'total_requests': total_requests,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'evictions': self.stats['evictions'],
                'entries_count': self.stats['entries_count'],
                'size_mb': self.stats['size_bytes'] / (1024 * 1024),
                'max_size_mb': self.config.max_size_mb,
                'utilization_percent': (self.stats['entries_count'] / self.config.max_entries * 100),
                'memory_pressure_events': self.stats['memory_pressure_events'],
                'policy_switches': self.stats['policy_switches'],
                'eviction_policy': self.config.eviction_policy.value,
                'average_entry_size_kb': (self.stats['size_bytes'] / self.stats['entries_count'] / 1024) 
                                        if self.stats['entries_count'] > 0 else 0
            }
    
    def clear(self):
        """Clear all cache entries."""
        with self.lock:
            self.cache.clear()
            self.access_patterns.clear()
            self.frequency_counter.clear()
            self.stats.update({
                'entries_count': 0,
                'size_bytes': 0
            })
    
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
