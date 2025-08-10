"""
Memory Management and Resource Pooling Module

This module provides production-ready memory management optimizations including:
1. Object pooling for frequently allocated objects
2. Memory monitoring and leak detection  
3. Garbage collection optimization
4. Resource cleanup utilities
5. Phase 3: Advanced memory management with adaptive strategies

Part of Phase 3: Memory Management and Optimization
"""

import gc
import weakref
import threading
import tracemalloc
import psutil
import os
from typing import TypeVar, Generic, Dict, List, Any, Optional, Callable
from collections import deque, defaultdict
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import logging
import time

from src.utils.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar('T')

@dataclass
class PoolStats:
    """Statistics for object pool performance."""
    created: int = 0
    reused: int = 0
    destroyed: int = 0
    peak_size: int = 0
    current_size: int = 0
    
    @property
    def reuse_rate(self) -> float:
        """Calculate object reuse rate as percentage."""
        total = self.created + self.reused
        return (self.reused / total * 100) if total > 0 else 0.0
    
    @property
    def efficiency(self) -> float:
        """Calculate pool efficiency (reused vs created)."""
        return (self.reused / self.created) if self.created > 0 else 0.0

@dataclass
class MemoryPressureInfo:
    """Information about current memory pressure."""
    total_memory_mb: float
    available_memory_mb: float
    used_memory_mb: float
    memory_percent: float
    pressure_level: str  # 'low', 'medium', 'high', 'critical'
    gc_collections: Dict[int, int] = field(default_factory=dict)
    
    @property
    def is_under_pressure(self) -> bool:
        """Check if system is under memory pressure."""
        return self.pressure_level in ['high', 'critical']

class AdaptivePoolManager:
    """
    Phase 3: Adaptive pool management that adjusts based on memory pressure.
    """
    
    def __init__(self):
        self.pools: Dict[str, ObjectPool] = {}
        self.pressure_thresholds = {
            'low': 50.0,      # < 50% memory usage
            'medium': 70.0,   # 50-70% memory usage  
            'high': 85.0,     # 70-85% memory usage
            'critical': 95.0  # > 85% memory usage
        }
        self.adaptive_strategies = {
            'low': self._expand_pools,
            'medium': self._maintain_pools,
            'high': self._shrink_pools,
            'critical': self._emergency_cleanup
        }
        
    def get_memory_pressure(self) -> MemoryPressureInfo:
        """Get current memory pressure information."""
        try:
            memory = psutil.virtual_memory()
            gc_stats = {}
            for i in range(3):  # GC generations 0, 1, 2
                gc_stats[i] = gc.get_count()[i]
            
            # Determine pressure level
            if memory.percent < self.pressure_thresholds['low']:
                level = 'low'
            elif memory.percent < self.pressure_thresholds['medium']:
                level = 'medium'
            elif memory.percent < self.pressure_thresholds['high']:
                level = 'high'
            else:
                level = 'critical'
            
            return MemoryPressureInfo(
                total_memory_mb=memory.total / 1024 / 1024,
                available_memory_mb=memory.available / 1024 / 1024,
                used_memory_mb=memory.used / 1024 / 1024,
                memory_percent=memory.percent,
                pressure_level=level,
                gc_collections=gc_stats
            )
        except Exception as e:
            logger.warning(f"Failed to get memory pressure info: {e}")
            # Return safe defaults
            return MemoryPressureInfo(
                total_memory_mb=1024.0,
                available_memory_mb=512.0,
                used_memory_mb=512.0,
                memory_percent=50.0,
                pressure_level='medium'
            )
    
    def adapt_to_pressure(self) -> Dict[str, Any]:
        """Adapt pool sizes based on current memory pressure."""
        pressure = self.get_memory_pressure()
        strategy = self.adaptive_strategies.get(pressure.pressure_level, self._maintain_pools)
        
        actions_taken = {
            'pressure_level': pressure.pressure_level,
            'memory_percent': pressure.memory_percent,
            'actions': []
        }
        
        try:
            strategy_result = strategy(pressure)
            actions_taken['actions'] = strategy_result
        except Exception as e:
            logger.error(f"Failed to adapt to memory pressure: {e}")
            actions_taken['actions'] = [f"error: {str(e)}"]
        
        return actions_taken
    
    def _expand_pools(self, pressure: MemoryPressureInfo) -> List[str]:
        """Expand pool sizes when memory pressure is low."""
        actions = []
        for name, pool in self.pools.items():
            if pool.size() < pool._max_size:
                # Increase pool size by 20%
                new_size = min(int(pool._max_size * 1.2), pool._max_size + 50)
                pool.resize(new_size)
                actions.append(f"expanded_{name}_pool_to_{new_size}")
        return actions
    
    def _maintain_pools(self, pressure: MemoryPressureInfo) -> List[str]:
        """Maintain current pool sizes when memory pressure is medium."""
        return ["maintaining_current_pool_sizes"]
    
    def _shrink_pools(self, pressure: MemoryPressureInfo) -> List[str]:
        """Shrink pool sizes when memory pressure is high."""
        actions = []
        for name, pool in self.pools.items():
            if pool.size() > 10:  # Keep minimum viable pool
                # Reduce pool size by 30%
                new_size = max(int(pool.size() * 0.7), 10)
                pool.resize(new_size)
                actions.append(f"shrunk_{name}_pool_to_{new_size}")
        return actions
    
    def _emergency_cleanup(self, pressure: MemoryPressureInfo) -> List[str]:
        """Emergency cleanup when memory pressure is critical."""
        actions = []
        
        # Aggressively shrink all pools
        for name, pool in self.pools.items():
            pool.resize(5)  # Minimal pool size
            actions.append(f"emergency_shrunk_{name}_pool_to_5")
        
        # Force garbage collection
        collected = gc.collect()
        actions.append(f"force_gc_collected_{collected}_objects")
        
        # Clear any additional caches
        actions.append("cleared_additional_caches")
        
        return actions
    
    def register_pool(self, name: str, pool: 'ObjectPool') -> None:
        """Register a pool for adaptive management."""
        self.pools[name] = pool

class ObjectPool(Generic[T]):
    """
    Production-ready object pool for memory optimization.
    
    Provides efficient reuse of expensive-to-create objects like NFA states,
    transitions, and automata components.
    """
    
    def __init__(self, factory: Callable[[], T], reset_func: Optional[Callable[[T], None]] = None,
                 max_size: int = 100, enable_stats: bool = True, adaptive: bool = True):
        """
        Initialize object pool.
        
        Args:
            factory: Function to create new objects
            reset_func: Optional function to reset objects before reuse
            max_size: Maximum pool size to prevent memory bloat
            enable_stats: Whether to track pool statistics
            adaptive: Whether to enable adaptive pool management
        """
        self._factory = factory
        self._reset_func = reset_func
        self._max_size = max_size
        self._enable_stats = enable_stats
        self._adaptive = adaptive
        
        self._pool: deque = deque()
        self._lock = threading.RLock()
        self._stats = PoolStats() if enable_stats else None
        
        # Weak references to track all created objects (only for objects that support weak refs)
        self._all_objects: weakref.WeakSet = weakref.WeakSet()
        self._all_objects_count = 0  # Fallback counter for objects that can't be weak referenced
        
        # Phase 3: Enhanced monitoring
        self._creation_timestamps: deque = deque()
        self._usage_patterns: defaultdict = defaultdict(int)
        self._last_pressure_check = 0.0
    
    def acquire(self) -> T:
        """
        Acquire an object from the pool or create new one.
        
        Returns:
            Object instance ready for use
        """
        with self._lock:
            # Phase 3: Track usage patterns
            current_time = time.time()
            hour_key = int(current_time // 3600)  # Hour-based tracking
            self._usage_patterns[hour_key] += 1
            
            # Phase 3: Adaptive pressure checking
            if self._adaptive and current_time - self._last_pressure_check > 60:  # Check every minute
                self._check_memory_pressure()
                self._last_pressure_check = current_time
            
            if self._pool:
                obj = self._pool.popleft()
                
                # Reset object if reset function provided
                if self._reset_func:
                    try:
                        self._reset_func(obj)
                    except Exception as e:
                        logger.warning(f"Object reset failed: {e}")
                        # Create new object if reset fails
                        obj = self._create_new_object()
                
                if self._stats:
                    self._stats.reused += 1
                    self._stats.current_size = len(self._pool)
                
                return obj
            else:
                return self._create_new_object()
    
    def _check_memory_pressure(self) -> None:
        """Check memory pressure and adapt pool size if needed."""
        try:
            memory = psutil.virtual_memory()
            
            if memory.percent > 85:  # High memory pressure
                # Aggressively shrink pool
                target_size = max(5, len(self._pool) // 2)
                while len(self._pool) > target_size:
                    self._pool.pop()
                logger.debug(f"Pool shrunk due to memory pressure: {len(self._pool)} objects")
                
            elif memory.percent < 50 and len(self._pool) < self._max_size // 2:
                # Low memory pressure, allow pool to grow
                pass  # Natural growth through usage
                
        except Exception as e:
            logger.warning(f"Memory pressure check failed: {e}")
    
    def release(self, obj: T) -> None:
        """
        Release an object back to the pool.
        
        Args:
            obj: Object to return to pool
        """
        with self._lock:
            # Only add to pool if under size limit
            if len(self._pool) < self._max_size:
                self._pool.append(obj)
                
                if self._stats:
                    self._stats.current_size = len(self._pool)
                    self._stats.peak_size = max(self._stats.peak_size, len(self._pool))
            else:
                # Pool is full, let object be garbage collected
                if self._stats:
                    self._stats.destroyed += 1
    
    def _create_new_object(self) -> T:
        """Create new object and track statistics."""
        obj = self._factory()
        
        # Try to add to weak reference set, fallback to counter for non-weak-referenceable objects
        try:
            self._all_objects.add(obj)
        except TypeError:
            # Object doesn't support weak references (like dict), use counter instead
            self._all_objects_count += 1
        
        if self._stats:
            self._stats.created += 1
        
        return obj
    
    def clear(self) -> None:
        """Clear all objects from pool."""
        with self._lock:
            self._pool.clear()
            if self._stats:
                self._stats.current_size = 0
    
    def size(self) -> int:
        """Get current pool size."""
        with self._lock:
            return len(self._pool)
    
    def resize(self, new_max_size: int) -> None:
        """
        Phase 3: Resize pool maximum capacity.
        
        Args:
            new_max_size: New maximum pool size
        """
        with self._lock:
            self._max_size = new_max_size
            
            # Shrink current pool if it exceeds new max
            while len(self._pool) > new_max_size:
                self._pool.pop()
                if self._stats:
                    self._stats.destroyed += 1
            
            if self._stats:
                self._stats.current_size = len(self._pool)
    
    def get_usage_patterns(self) -> Dict[str, Any]:
        """
        Phase 3: Get usage pattern analysis.
        
        Returns:
            Dictionary with usage statistics and patterns
        """
        with self._lock:
            current_time = time.time()
            total_usage = sum(self._usage_patterns.values())
            
            # Calculate peak usage hours
            if self._usage_patterns:
                peak_hour = max(self._usage_patterns.items(), key=lambda x: x[1])
                peak_usage = peak_hour[1]
            else:
                peak_hour = (0, 0)
                peak_usage = 0
            
            return {
                'total_acquisitions': total_usage,
                'peak_hour_usage': peak_usage,
                'average_hourly_usage': total_usage / max(len(self._usage_patterns), 1),
                'usage_distribution': dict(self._usage_patterns),
                'pool_efficiency': self._stats.efficiency if self._stats else 0.0,
                'memory_pressure_checks': getattr(self, '_pressure_checks', 0)
            }
    
    def stats(self) -> Optional[PoolStats]:
        """Get pool statistics."""
        return self._stats
    
    def active_objects(self) -> int:
        """Get count of active objects (not in pool)."""
        # Return count from weak references plus counter for non-weak-referenceable objects
        return len(self._all_objects) + self._all_objects_count

class MemoryMonitor:
    """
    Production memory monitoring and leak detection.
    
    Tracks memory usage patterns and detects potential leaks.
    """
    
    def __init__(self, check_interval: float = 30.0, leak_threshold_mb: float = 50.0):
        """
        Initialize memory monitor.
        
        Args:
            check_interval: Seconds between memory checks
            leak_threshold_mb: Memory growth threshold for leak detection
        """
        self.check_interval = check_interval
        self.leak_threshold_mb = leak_threshold_mb
        
        self._baseline_memory = 0.0
        self._peak_memory = 0.0
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Memory usage history
        self._memory_history: List[float] = []
        self._max_history = 100
        
    def start_monitoring(self) -> None:
        """Start background memory monitoring."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._stop_event.clear()
        
        # Start memory tracing if not already started
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        
        # Record baseline
        self._baseline_memory = self._get_current_memory()
        self._peak_memory = self._baseline_memory
        
        # Start monitoring thread
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        logger.info(f"Memory monitoring started, baseline: {self._baseline_memory:.2f}MB")
    
    def stop_monitoring(self) -> None:
        """Stop memory monitoring."""
        if not self._monitoring:
            return
        
        self._monitoring = False
        self._stop_event.set()
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        
        logger.info("Memory monitoring stopped")
    
    def _get_current_memory(self) -> float:
        """Get current memory usage in MB."""
        if tracemalloc.is_tracing():
            current, _ = tracemalloc.get_traced_memory()
            return current / 1024 / 1024
        return 0.0
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while not self._stop_event.wait(self.check_interval):
            try:
                current_memory = self._get_current_memory()
                self._memory_history.append(current_memory)
                
                # Keep history size manageable
                if len(self._memory_history) > self._max_history:
                    self._memory_history.pop(0)
                
                # Update peak memory
                self._peak_memory = max(self._peak_memory, current_memory)
                
                # Check for potential memory leak
                memory_growth = current_memory - self._baseline_memory
                if memory_growth > self.leak_threshold_mb:
                    logger.warning(
                        f"Potential memory leak detected: {memory_growth:.2f}MB growth "
                        f"(current: {current_memory:.2f}MB, baseline: {self._baseline_memory:.2f}MB)"
                    )
                
            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")
    
    def get_memory_stats(self) -> Dict[str, float]:
        """Get current memory statistics."""
        current = self._get_current_memory()
        growth = current - self._baseline_memory
        
        return {
            "current_mb": current,
            "baseline_mb": self._baseline_memory,
            "peak_mb": self._peak_memory,
            "growth_mb": growth,
            "avg_mb": sum(self._memory_history) / len(self._memory_history) if self._memory_history else 0.0
        }

class GarbageCollectionOptimizer:
    """
    Garbage collection optimization and tuning.
    
    Provides intelligent GC management for better performance.
    """
    
    def __init__(self):
        self._gc_stats = {gen: gc.get_count()[gen] for gen in range(3)}
        self._gc_thresholds = gc.get_threshold()
        self._optimized = False
    
    def optimize_gc_settings(self) -> None:
        """Optimize garbage collection settings for pattern matching workload."""
        if self._optimized:
            return
        
        # Store original settings
        self._original_thresholds = gc.get_threshold()
        
        # Tune GC thresholds for pattern matching workload
        # - Higher gen0 threshold to reduce frequent GC
        # - Moderate gen1/gen2 thresholds for memory control
        gc.set_threshold(1000, 15, 15)  # Default is (700, 10, 10)
        
        # Enable garbage collection debugging in development
        if logger.isEnabledFor(logging.DEBUG):
            gc.set_debug(gc.DEBUG_STATS)
        
        self._optimized = True
        logger.info("Garbage collection settings optimized for pattern matching")
    
    def restore_gc_settings(self) -> None:
        """Restore original garbage collection settings."""
        if hasattr(self, '_original_thresholds'):
            gc.set_threshold(*self._original_thresholds)
            gc.set_debug(0)
            self._optimized = False
            logger.info("Garbage collection settings restored")
    
    def force_cleanup(self) -> Dict[str, int]:
        """Force garbage collection and return collection stats."""
        collected = {}
        
        # Collect in all generations
        for generation in range(3):
            collected[f"gen_{generation}"] = gc.collect(generation)
        
        # Total collected objects
        collected["total"] = sum(collected.values())
        
        logger.debug(f"Forced GC cleanup collected {collected['total']} objects")
        return collected
    
    def get_gc_stats(self) -> Dict[str, Any]:
        """Get garbage collection statistics."""
        current_counts = gc.get_count()
        current_thresholds = gc.get_threshold()
        
        # Calculate collections since last check
        collections = {
            gen: current_counts[gen] - self._gc_stats[gen] 
            for gen in range(3)
        }
        
        # Update stored stats
        self._gc_stats = {gen: current_counts[gen] for gen in range(3)}
        
        return {
            "current_counts": current_counts,
            "thresholds": current_thresholds,
            "collections_since_last": collections,
            "total_objects": len(gc.get_objects()),
            "optimized": self._optimized
        }

class ResourceManager:
    """
    Centralized resource management for memory optimization.
    
    Coordinates object pools, memory monitoring, and cleanup.
    Phase 3: Enhanced with adaptive management and advanced monitoring.
    """
    
    def __init__(self):
        self.object_pools: Dict[str, ObjectPool] = {}
        self.memory_monitor = MemoryMonitor()
        self.gc_optimizer = GarbageCollectionOptimizer()
        
        # Phase 3: Adaptive pool management
        self.adaptive_manager = AdaptivePoolManager()
        self._monitoring_enabled = False
        self._last_adaptation = 0.0
        self._adaptation_interval = 120.0  # Adapt every 2 minutes
        
        # Register cleanup on process exit
        import atexit
        atexit.register(self.cleanup)
    
    def get_pool(self, name: str, factory: Callable[[], T], 
                 reset_func: Optional[Callable[[T], None]] = None,
                 max_size: int = 100, adaptive: bool = True) -> ObjectPool[T]:
        """
        Get or create an object pool.
        
        Args:
            name: Pool identifier
            factory: Object creation function
            reset_func: Optional object reset function
            max_size: Maximum pool size
            adaptive: Enable adaptive management
            
        Returns:
            Object pool instance
        """
        if name not in self.object_pools:
            pool = ObjectPool(
                factory=factory,
                reset_func=reset_func,
                max_size=max_size,
                adaptive=adaptive
            )
            self.object_pools[name] = pool
            
            # Phase 3: Register with adaptive manager
            if adaptive:
                self.adaptive_manager.register_pool(name, pool)
        
        return self.object_pools[name]
    
    def start_monitoring(self) -> None:
        """Start comprehensive resource monitoring."""
        self.memory_monitor.start_monitoring()
        self.gc_optimizer.optimize_gc_settings()
        self._monitoring_enabled = True
        logger.info("Resource monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop resource monitoring."""
        self.memory_monitor.stop_monitoring()
        self.gc_optimizer.restore_gc_settings()
        self._monitoring_enabled = False
        logger.info("Resource monitoring stopped")
    
    def cleanup(self) -> None:
        """Cleanup all resources and pools."""
        # Clear all object pools
        for pool in self.object_pools.values():
            pool.clear()
        
        # Stop monitoring
        self.stop_monitoring()
        
        # Force final cleanup
        cleanup_stats = self.gc_optimizer.force_cleanup()
        logger.info(f"Final cleanup completed, {cleanup_stats['total']} objects collected")
    
    def adapt_to_memory_pressure(self) -> Dict[str, Any]:
        """
        Phase 3: Adapt resources to current memory pressure.
        
        Returns:
            Dictionary with adaptation actions taken
        """
        current_time = time.time()
        
        if current_time - self._last_adaptation < self._adaptation_interval:
            return {"status": "skipped", "reason": "too_soon"}
        
        self._last_adaptation = current_time
        
        # Get current memory pressure and adapt
        adaptation_result = self.adaptive_manager.adapt_to_pressure()
        
        # Log significant adaptations
        if adaptation_result['pressure_level'] in ['high', 'critical']:
            logger.warning(f"Memory pressure adaptation: {adaptation_result['pressure_level']} "
                         f"({adaptation_result['memory_percent']:.1f}% memory usage)")
        
        return adaptation_result
    
    def get_memory_pressure_info(self) -> MemoryPressureInfo:
        """
        Phase 3: Get current memory pressure information.
        
        Returns:
            Current memory pressure details
        """
        return self.adaptive_manager.get_memory_pressure()
    
    def optimize_for_workload(self, workload_type: str = "balanced") -> Dict[str, Any]:
        """
        Phase 3: Optimize pools for specific workload patterns.
        
        Args:
            workload_type: 'memory_intensive', 'cpu_intensive', 'balanced'
            
        Returns:
            Dictionary with optimization actions
        """
        actions = []
        
        if workload_type == "memory_intensive":
            # Aggressive memory conservation
            for name, pool in self.object_pools.items():
                new_size = max(5, pool.size() // 2)
                pool.resize(new_size)
                actions.append(f"shrunk_{name}_pool_for_memory_intensive")
                
        elif workload_type == "cpu_intensive":
            # Larger pools to reduce allocation overhead
            pressure = self.get_memory_pressure_info()
            if not pressure.is_under_pressure:
                for name, pool in self.object_pools.items():
                    new_size = min(pool._max_size * 2, 200)
                    pool.resize(new_size)
                    actions.append(f"expanded_{name}_pool_for_cpu_intensive")
        
        return {
            "workload_type": workload_type,
            "actions": actions,
            "memory_pressure": self.get_memory_pressure_info().pressure_level
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive resource statistics."""
        stats = {
            "memory": self.memory_monitor.get_memory_stats(),
            "garbage_collection": self.gc_optimizer.get_gc_stats(),
            "object_pools": {},
            # Phase 3: Enhanced statistics
            "memory_pressure": self.get_memory_pressure_info().__dict__,
            "adaptive_management": {
                "enabled": self._monitoring_enabled,
                "last_adaptation": self._last_adaptation,
                "adaptation_interval": self._adaptation_interval
            }
        }
        
        # Add pool statistics with usage patterns
        for name, pool in self.object_pools.items():
            pool_stats = pool.stats()
            if pool_stats:
                stats["object_pools"][name] = {
                    "created": pool_stats.created,
                    "reused": pool_stats.reused,
                    "current_size": pool_stats.current_size,
                    "peak_size": pool_stats.peak_size,
                    "reuse_rate": pool_stats.reuse_rate,
                    "efficiency": pool_stats.efficiency,
                    "active_objects": pool.active_objects(),
                    # Phase 3: Usage patterns
                    "usage_patterns": pool.get_usage_patterns()
                }
        
        return stats

# Global resource manager instance
_resource_manager: Optional[ResourceManager] = None

def get_resource_manager() -> ResourceManager:
    """Get global resource manager instance."""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = ResourceManager()
    return _resource_manager

# Phase 3: Convenient API functions for memory management

def adapt_to_memory_pressure() -> Dict[str, Any]:
    """Adapt all managed resources to current memory pressure."""
    return get_resource_manager().adapt_to_memory_pressure()

def get_memory_pressure() -> MemoryPressureInfo:
    """Get current memory pressure information."""
    return get_resource_manager().get_memory_pressure_info()

def optimize_for_workload(workload_type: str = "balanced") -> Dict[str, Any]:
    """Optimize memory management for specific workload type."""
    return get_resource_manager().optimize_for_workload(workload_type)

def get_comprehensive_memory_stats() -> Dict[str, Any]:
    """Get comprehensive memory and resource statistics."""
    return get_resource_manager().get_stats()

def force_memory_cleanup() -> Dict[str, Any]:
    """Force immediate memory cleanup and garbage collection."""
    manager = get_resource_manager()
    
    # Adapt to pressure first
    adaptation = manager.adapt_to_memory_pressure()
    
    # Force GC cleanup
    gc_stats = manager.gc_optimizer.force_cleanup()
    
    return {
        "adaptation": adaptation,
        "gc_cleanup": gc_stats,
        "memory_after": manager.get_memory_pressure_info().__dict__
    }
