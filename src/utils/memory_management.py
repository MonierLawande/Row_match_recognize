"""
Memory Management and Resource Pooling Module

This module provides production-ready memory management optimizations including:
1. Object pooling for frequently allocated objects
2. Memory monitoring and leak detection  
3. Garbage collection optimization
4. Resource cleanup utilities

Part of Phase 3: Memory Management and Optimization
"""

import gc
import weakref
import threading
import tracemalloc
from typing import TypeVar, Generic, Dict, List, Any, Optional, Callable
from collections import deque
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import logging
import time

logger = logging.getLogger(__name__)

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

class ObjectPool(Generic[T]):
    """
    Production-ready object pool for memory optimization.
    
    Provides efficient reuse of expensive-to-create objects like NFA states,
    transitions, and automata components.
    """
    
    def __init__(self, factory: Callable[[], T], reset_func: Optional[Callable[[T], None]] = None,
                 max_size: int = 100, enable_stats: bool = True):
        """
        Initialize object pool.
        
        Args:
            factory: Function to create new objects
            reset_func: Optional function to reset objects before reuse
            max_size: Maximum pool size to prevent memory bloat
            enable_stats: Whether to track pool statistics
        """
        self._factory = factory
        self._reset_func = reset_func
        self._max_size = max_size
        self._enable_stats = enable_stats
        
        self._pool: deque = deque()
        self._lock = threading.RLock()
        self._stats = PoolStats() if enable_stats else None
        
        # Weak references to track all created objects
        self._all_objects: weakref.WeakSet = weakref.WeakSet()
    
    def acquire(self) -> T:
        """
        Acquire an object from the pool or create new one.
        
        Returns:
            Object instance ready for use
        """
        with self._lock:
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
        self._all_objects.add(obj)
        
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
    
    def stats(self) -> Optional[PoolStats]:
        """Get pool statistics."""
        return self._stats
    
    def active_objects(self) -> int:
        """Get count of active objects (not in pool)."""
        return len(self._all_objects)

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
    """
    
    def __init__(self):
        self.object_pools: Dict[str, ObjectPool] = {}
        self.memory_monitor = MemoryMonitor()
        self.gc_optimizer = GarbageCollectionOptimizer()
        
        # Register cleanup on process exit
        import atexit
        atexit.register(self.cleanup)
    
    def get_pool(self, name: str, factory: Callable[[], T], 
                 reset_func: Optional[Callable[[T], None]] = None,
                 max_size: int = 100) -> ObjectPool[T]:
        """
        Get or create an object pool.
        
        Args:
            name: Pool identifier
            factory: Object creation function
            reset_func: Optional object reset function
            max_size: Maximum pool size
            
        Returns:
            Object pool instance
        """
        if name not in self.object_pools:
            self.object_pools[name] = ObjectPool(
                factory=factory,
                reset_func=reset_func,
                max_size=max_size
            )
        
        return self.object_pools[name]
    
    def start_monitoring(self) -> None:
        """Start comprehensive resource monitoring."""
        self.memory_monitor.start_monitoring()
        self.gc_optimizer.optimize_gc_settings()
        logger.info("Resource monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop resource monitoring."""
        self.memory_monitor.stop_monitoring()
        self.gc_optimizer.restore_gc_settings()
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
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive resource statistics."""
        stats = {
            "memory": self.memory_monitor.get_memory_stats(),
            "garbage_collection": self.gc_optimizer.get_gc_stats(),
            "object_pools": {}
        }
        
        # Add pool statistics
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
                    "active_objects": pool.active_objects()
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
