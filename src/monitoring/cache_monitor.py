"""
Cache monitoring utilities for production environments.

This module provides tools for monitoring cache performance, memory usage,
and automatic cache management based on configured thresholds.
"""

import time
import threading
import logging
from typing import Dict, Any, Optional, Callable
from src.utils.pattern_cache import (
    get_cache_stats, clear_pattern_cache, resize_cache, 
    is_caching_enabled, set_caching_enabled
)
from src.config.production_config import MatchRecognizeConfig

# Module logger
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

class CacheMonitor:
    """
    Production-ready cache monitor with automatic management capabilities.
    
    Features:
    - Periodic monitoring of cache statistics
    - Automatic cache cleanup based on configured thresholds
    - Memory usage tracking and alerts
    - Cache efficiency reporting
    - Customizable monitoring callback
    """
    
    def __init__(self, config: Optional[MatchRecognizeConfig] = None):
        """Initialize cache monitor with optional configuration."""
        self.config = config or MatchRecognizeConfig.from_env()
        self.monitoring_thread = None
        self.running = False
        self.last_check = time.time()
        self.monitoring_interval = self.config.performance.cache_monitoring_interval_seconds
        self.memory_threshold = self.config.performance.cache_clear_threshold_mb
        self.ttl_seconds = self.config.performance.cache_ttl_seconds
        self.cache_size_limit = self.config.performance.cache_size_limit
        self.on_threshold_exceeded_callbacks = []
        
    def start_monitoring(self) -> None:
        """Start the cache monitoring thread."""
        if self.running:
            logger.warning("Cache monitoring already running")
            return
            
        self.running = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="cache-monitor"
        )
        self.monitoring_thread.start()
        logger.info(f"Cache monitoring started with interval {self.monitoring_interval}s")
        
    def stop_monitoring(self) -> None:
        """Stop the cache monitoring thread."""
        if not self.running:
            logger.warning("Cache monitoring not running")
            return
            
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=2.0)
        logger.info("Cache monitoring stopped")
        
    def _monitoring_loop(self) -> None:
        """Main monitoring loop that runs periodically."""
        while self.running:
            try:
                self._check_cache_health()
                time.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"Error in cache monitoring: {str(e)}")
                time.sleep(5)  # Shorter sleep on error
                
    def _check_cache_health(self) -> None:
        """Check cache health and perform necessary actions."""
        stats = get_cache_stats()
        current_time = time.time()
        
        # Log current cache statistics
        logger.info(f"Cache stats: size={stats.get('size', 0)}/{self.cache_size_limit}, "
                   f"memory={stats.get('memory_used_mb', 0):.2f}MB, "
                   f"efficiency={stats.get('cache_efficiency', 0):.2f}%, "
                   f"hits={stats.get('hits', 0)}, misses={stats.get('misses', 0)}")
        
        # Check if we need to clear the cache based on age
        cache_age = current_time - stats.get('last_reset', current_time)
        if cache_age > self.ttl_seconds:
            logger.info(f"Cache age ({cache_age:.2f}s) exceeded TTL ({self.ttl_seconds}s), clearing")
            clear_pattern_cache()
            return
            
        # Check if we need to clear based on memory usage
        memory_used = stats.get('memory_used_mb', 0)
        if memory_used > self.memory_threshold:
            logger.warning(f"Cache memory usage ({memory_used:.2f}MB) exceeded threshold "
                          f"({self.memory_threshold}MB), clearing")
            clear_pattern_cache()
            
            # Execute registered callbacks
            for callback in self.on_threshold_exceeded_callbacks:
                try:
                    callback(stats)
                except Exception as e:
                    logger.error(f"Error in threshold callback: {str(e)}")
            return
            
        # Check if cache is inefficient (hit rate < 20% with significant size)
        if stats.get('size', 0) > 100 and stats.get('cache_efficiency', 0) < 20:
            logger.info(f"Cache efficiency low ({stats.get('cache_efficiency', 0):.2f}%), resizing")
            # Resize to half the current size to keep the most recently used patterns
            new_size = max(100, stats.get('size', 0) // 2)
            resize_cache(new_size)
        
    def register_threshold_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register a callback to be called when memory threshold is exceeded.
        
        Args:
            callback: Function to call with cache stats when threshold is exceeded
        """
        self.on_threshold_exceeded_callbacks.append(callback)
        
    def force_check(self) -> Dict[str, Any]:
        """
        Force an immediate cache health check.
        
        Returns:
            Current cache statistics
        """
        self._check_cache_health()
        return get_cache_stats()
        
    def resize_to_optimal(self) -> None:
        """Resize the cache to an optimal size based on hit patterns."""
        stats = get_cache_stats()
        hits = stats.get('hits', 0)
        misses = stats.get('misses', 0)
        current_size = stats.get('size', 0)
        
        # Simple heuristic for optimal size
        if hits + misses > 0:
            hit_rate = hits / (hits + misses)
            if hit_rate > 0.8 and current_size < self.cache_size_limit:
                # Cache is effective, potentially increase size
                new_size = min(self.cache_size_limit, int(current_size * 1.5))
                resize_cache(new_size)
                logger.info(f"Cache performing well, increased size to {new_size}")
            elif hit_rate < 0.3 and current_size > 100:
                # Cache is ineffective, decrease size
                new_size = max(100, int(current_size * 0.5))
                resize_cache(new_size)
                logger.info(f"Cache performing poorly, decreased size to {new_size}")

# Global cache monitor instance
_cache_monitor = None

def start_cache_monitoring(config: Optional[MatchRecognizeConfig] = None) -> CacheMonitor:
    """
    Start cache monitoring with the given configuration.
    
    Args:
        config: Optional configuration, will use default if not provided
        
    Returns:
        The CacheMonitor instance
    """
    global _cache_monitor
    if _cache_monitor is None:
        _cache_monitor = CacheMonitor(config)
        _cache_monitor.start_monitoring()
    return _cache_monitor

def stop_cache_monitoring() -> None:
    """Stop the global cache monitoring thread."""
    global _cache_monitor
    if _cache_monitor is not None:
        _cache_monitor.stop_monitoring()
        _cache_monitor = None

def get_cache_monitor() -> Optional[CacheMonitor]:
    """Get the global cache monitor instance."""
    return _cache_monitor
