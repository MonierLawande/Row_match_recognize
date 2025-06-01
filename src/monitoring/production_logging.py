"""
Production-ready logging system for Row Match Recognize.

This module provides structured logging, performance tracking,
and monitoring capabilities for production environments.
"""

import logging
import time
import json
import traceback
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import contextmanager
from functools import wraps
import threading
from collections import defaultdict, deque


@dataclass
class LogContext:
    """Context information for structured logging."""
    query_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    partition_id: Optional[str] = None
    pattern: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring."""
    operation: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    input_rows: Optional[int] = None
    output_rows: Optional[int] = None
    memory_used_mb: Optional[float] = None
    cache_hits: int = 0
    cache_misses: int = 0
    error_count: int = 0
    
    def complete(self, end_time: Optional[float] = None) -> None:
        """Mark the operation as complete."""
        self.end_time = end_time or time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'operation': self.operation,
            'duration_ms': self.duration_ms,
            'input_rows': self.input_rows,
            'output_rows': self.output_rows,
            'memory_used_mb': self.memory_used_mb,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'error_count': self.error_count,
            'timestamp': self.start_time,
        }


class StructuredLogger:
    """Structured logger with context support."""
    
    def __init__(self, name: str, context: Optional[LogContext] = None):
        self.logger = logging.getLogger(name)
        self.context = context or LogContext()
        self._local = threading.local()
    
    def _format_message(self, message: str, **kwargs) -> str:
        """Format message with context and additional fields."""
        log_data = {
            'message': message,
            'timestamp': datetime.utcnow().isoformat(),
            **self.context.to_dict(),
            **kwargs
        }
        return json.dumps(log_data, default=str)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(self._format_message(message, **kwargs))
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(self._format_message(message, **kwargs))
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(self._format_message(message, **kwargs))
    
    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """Log error message."""
        if exc_info:
            kwargs['traceback'] = traceback.format_exc()
        self.logger.error(self._format_message(message, **kwargs))
    
    def critical(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """Log critical message."""
        if exc_info:
            kwargs['traceback'] = traceback.format_exc()
        self.logger.critical(self._format_message(message, **kwargs))
    
    def with_context(self, **context_updates) -> 'StructuredLogger':
        """Create a new logger with updated context."""
        new_context = LogContext(**{**self.context.to_dict(), **context_updates})
        return StructuredLogger(self.logger.name, new_context)


class PerformanceTracker:
    """Thread-safe performance tracking system."""
    
    def __init__(self, max_metrics: int = 10000):
        self.max_metrics = max_metrics
        self.metrics: deque = deque(maxlen=max_metrics)
        self.operation_stats = defaultdict(list)
        self.lock = threading.Lock()
        self.logger = StructuredLogger(__name__)
    
    def start_operation(self, operation: str, **context) -> PerformanceMetrics:
        """Start tracking an operation."""
        metrics = PerformanceMetrics(
            operation=operation,
            start_time=time.time()
        )
        
        # Add context information
        for key, value in context.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)
        
        return metrics
    
    def complete_operation(self, metrics: PerformanceMetrics) -> None:
        """Complete operation tracking."""
        metrics.complete()
        
        with self.lock:
            self.metrics.append(metrics)
            self.operation_stats[metrics.operation].append(metrics.duration_ms)
        
        # Log slow operations
        if metrics.duration_ms and metrics.duration_ms > 5000:  # 5 seconds
            self.logger.warning(
                "Slow operation detected",
                operation=metrics.operation,
                duration_ms=metrics.duration_ms,
                **metrics.to_dict()
            )
    
    def get_stats(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """Get performance statistics."""
        with self.lock:
            if operation:
                durations = self.operation_stats.get(operation, [])
                if not durations:
                    return {}
                
                return {
                    'operation': operation,
                    'count': len(durations),
                    'avg_duration_ms': sum(durations) / len(durations),
                    'min_duration_ms': min(durations),
                    'max_duration_ms': max(durations),
                    'total_duration_ms': sum(durations),
                }
            
            # Overall stats
            all_metrics = list(self.metrics)
            if not all_metrics:
                return {}
            
            operations = defaultdict(list)
            for metric in all_metrics:
                if metric.duration_ms:
                    operations[metric.operation].append(metric.duration_ms)
            
            return {
                'total_operations': len(all_metrics),
                'operations': {
                    op: {
                        'count': len(durations),
                        'avg_duration_ms': sum(durations) / len(durations),
                        'min_duration_ms': min(durations),
                        'max_duration_ms': max(durations),
                    }
                    for op, durations in operations.items()
                    if durations
                }
            }
    
    def get_recent_metrics(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent performance metrics."""
        with self.lock:
            recent = list(self.metrics)[-limit:]
            return [metric.to_dict() for metric in recent]


# Global instances
_performance_tracker: Optional[PerformanceTracker] = None
_logger_cache: Dict[str, StructuredLogger] = {}


def get_logger(name: str, context: Optional[LogContext] = None) -> StructuredLogger:
    """Get or create a structured logger."""
    cache_key = f"{name}:{id(context) if context else 'default'}"
    
    if cache_key not in _logger_cache:
        _logger_cache[cache_key] = StructuredLogger(name, context)
    
    return _logger_cache[cache_key]


def get_performance_tracker() -> PerformanceTracker:
    """Get the global performance tracker."""
    global _performance_tracker
    if _performance_tracker is None:
        _performance_tracker = PerformanceTracker()
    return _performance_tracker


@contextmanager
def track_performance(operation: str, logger: Optional[StructuredLogger] = None, **context):
    """Context manager for tracking operation performance."""
    tracker = get_performance_tracker()
    metrics = tracker.start_operation(operation, **context)
    
    if logger:
        logger.debug(f"Starting operation: {operation}", **context)
    
    try:
        yield metrics
    except Exception as e:
        metrics.error_count += 1
        if logger:
            logger.error(f"Operation failed: {operation}", exc_info=True, **context)
        raise
    finally:
        tracker.complete_operation(metrics)
        
        if logger:
            logger.debug(
                f"Completed operation: {operation}",
                duration_ms=metrics.duration_ms,
                **context
            )


def log_performance(operation: str, logger: Optional[StructuredLogger] = None):
    """Decorator for tracking function performance."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or get_logger(func.__module__)
            
            with track_performance(
                operation,
                func_logger,
                function=func.__name__,
                module=func.__module__
            ) as metrics:
                try:
                    result = func(*args, **kwargs)
                    
                    # Try to extract metrics from result if it's a DataFrame
                    if hasattr(result, '__len__'):
                        try:
                            metrics.output_rows = len(result)
                        except:
                            pass
                    
                    return result
                    
                except Exception as e:
                    func_logger.error(
                        f"Function {func.__name__} failed",
                        exc_info=True,
                        function=func.__name__,
                        error_type=type(e).__name__,
                        error_message=str(e)
                    )
                    raise
        
        return wrapper
    return decorator


def setup_production_logging(config) -> None:
    """Setup production logging configuration."""
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper()),
        format=config.logging.format
    )
    
    # Add file handler if specified
    if config.logging.log_file:
        from logging.handlers import RotatingFileHandler
        
        handler = RotatingFileHandler(
            config.logging.log_file,
            maxBytes=config.logging.max_log_size_mb * 1024 * 1024,
            backupCount=config.logging.backup_count
        )
        
        if config.logging.enable_structured_logging:
            # Custom formatter for structured logs
            class StructuredFormatter(logging.Formatter):
                def format(self, record):
                    # Try to parse as JSON, fall back to standard formatting
                    try:
                        data = json.loads(record.getMessage())
                        return json.dumps(data, ensure_ascii=False)
                    except:
                        return super().format(record)
            
            handler.setFormatter(StructuredFormatter())
        else:
            handler.setFormatter(logging.Formatter(config.logging.format))
        
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)


# Health check functions
def get_system_health() -> Dict[str, Any]:
    """Get system health information."""
    tracker = get_performance_tracker()
    stats = tracker.get_stats()
    
    # Basic health indicators
    health_status = "healthy"
    issues = []
    
    # Check for high error rates
    total_ops = stats.get('total_operations', 0)
    if total_ops > 100:  # Only check if we have sufficient data
        error_rate = sum(
            len([m for m in tracker.metrics if m.error_count > 0])
        ) / total_ops
        
        if error_rate > 0.05:  # 5% error rate threshold
            health_status = "degraded"
            issues.append(f"High error rate: {error_rate:.2%}")
    
    # Check for slow operations
    operations = stats.get('operations', {})
    for op, op_stats in operations.items():
        if op_stats.get('avg_duration_ms', 0) > 10000:  # 10 second threshold
            health_status = "degraded"
            issues.append(f"Slow operation {op}: {op_stats['avg_duration_ms']:.0f}ms avg")
    
    return {
        'status': health_status,
        'timestamp': datetime.utcnow().isoformat(),
        'performance_stats': stats,
        'issues': issues,
        'uptime_seconds': time.time() - (tracker.metrics[0].start_time if tracker.metrics else time.time()),
    }


# Export commonly used items
__all__ = [
    'LogContext',
    'PerformanceMetrics',
    'StructuredLogger',
    'PerformanceTracker',
    'get_logger',
    'get_performance_tracker',
    'track_performance',
    'log_performance',
    'setup_production_logging',
    'get_system_health',
]
