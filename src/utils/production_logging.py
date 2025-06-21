# src/utils/production_logging.py
"""
Enhanced production logging system for Row Match Recognize.

This module provides comprehensive logging capabilities for production environments including:
- Structured logging with JSON format
- Performance tracking and metrics
- Error tracking and alerting
- Audit trail logging
- Security event logging
- Request/response logging
- Log aggregation support

Features:
- Thread-safe logging operations
- Configurable log levels and outputs
- Automatic log rotation and cleanup
- Performance monitoring integration
- Security audit trails
- Distributed tracing support
"""

import json
import logging
import logging.handlers
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
from enum import Enum

from src.config.production_config import MatchRecognizeConfig
from src.utils.logging_config import get_logger

class LogLevel(Enum):
    """Enhanced log levels for production."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    AUDIT = "AUDIT"
    SECURITY = "SECURITY"
    PERFORMANCE = "PERFORMANCE"

@dataclass
class LogEntry:
    """Structured log entry for production logging."""
    timestamp: str
    level: str
    logger_name: str
    message: str
    module: str
    function: str
    line_number: int
    thread_id: int
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    error_details: Optional[Dict[str, Any]] = None

@dataclass
class PerformanceMetrics:
    """Performance metrics for logging."""
    execution_time_ms: float
    memory_usage_mb: float
    cpu_usage_percent: float
    operation_name: str
    query_complexity: Optional[int] = None
    pattern_complexity: Optional[int] = None
    cache_hit_rate: Optional[float] = None
    rows_processed: Optional[int] = None

class ProductionLogger:
    """
    Production-grade logger with comprehensive features.
    
    Features:
    - Structured JSON logging
    - Performance metrics integration
    - Security audit trails
    - Thread-safe operations
    - Automatic log rotation
    - Multiple output destinations
    - Request correlation tracking
    """
    
    def __init__(self, config: MatchRecognizeConfig):
        self.config = config
        self.loggers: Dict[str, logging.Logger] = {}
        self.performance_data: List[PerformanceMetrics] = []
        self.audit_trail: List[LogEntry] = []
        self.security_events: List[LogEntry] = []
        
        # Thread safety
        self.lock = threading.RLock()
        self.thread_local = threading.local()
        
        # Setup logging infrastructure
        self._setup_loggers()
        self._setup_handlers()
        
        # Performance tracking
        self.start_time = time.time()
        self.operation_counters = {}
        self.error_counters = {}
        
    def _setup_loggers(self):
        """Setup specialized loggers for different purposes."""
        logger_configs = {
            'main': {'level': self.config.logging.level, 'file': 'application.log'},
            'performance': {'level': 'INFO', 'file': 'performance.log'},
            'audit': {'level': 'INFO', 'file': 'audit.log'},
            'security': {'level': 'WARNING', 'file': 'security.log'},
            'error': {'level': 'ERROR', 'file': 'error.log'}
        }
        
        for name, config in logger_configs.items():
            logger = logging.getLogger(f"rowmatch.{name}")
            logger.setLevel(getattr(logging, config['level']))
            self.loggers[name] = logger
    
    def _setup_handlers(self):
        """Setup log handlers with rotation and formatting."""
        if self.config.logging.log_file:
            log_dir = Path(self.config.logging.log_file).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            
            for name, logger in self.loggers.items():
                # File handler with rotation
                log_file = log_dir / f"{name}.log"
                handler = logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=self.config.logging.max_log_size_mb * 1024 * 1024,
                    backupCount=self.config.logging.backup_count
                )
                
                # JSON formatter for structured logging
                if self.config.logging.enable_structured_logging:
                    handler.setFormatter(StructuredFormatter())
                else:
                    handler.setFormatter(logging.Formatter(self.config.logging.format))
                
                logger.addHandler(handler)
        
        # Console handler for development
        if self.config.debug or self.config.environment == "development":
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(self.config.logging.format))
            for logger in self.loggers.values():
                logger.addHandler(console_handler)
    
    def get_context(self) -> Dict[str, Any]:
        """Get current logging context (request ID, user ID, etc.)."""
        if not hasattr(self.thread_local, 'context'):
            self.thread_local.context = {}
        return self.thread_local.context
    
    def set_context(self, **kwargs):
        """Set logging context for current thread."""
        if not hasattr(self.thread_local, 'context'):
            self.thread_local.context = {}
        self.thread_local.context.update(kwargs)
    
    def clear_context(self):
        """Clear logging context for current thread."""
        if hasattr(self.thread_local, 'context'):
            self.thread_local.context.clear()
    
    @contextmanager
    def operation_context(self, operation_name: str, **context):
        """Context manager for operation logging with automatic timing."""
        start_time = time.time()
        start_memory = self._get_memory_usage()
        
        # Set context
        old_context = self.get_context().copy()
        self.set_context(operation=operation_name, **context)
        
        try:
            self.log_info(f"Starting operation: {operation_name}", extra=context)
            yield
            
            # Log successful completion
            execution_time = (time.time() - start_time) * 1000
            memory_delta = self._get_memory_usage() - start_memory
            
            self.log_performance(
                f"Operation completed: {operation_name}",
                execution_time_ms=execution_time,
                memory_delta_mb=memory_delta,
                **context
            )
            
        except Exception as e:
            # Log error with context
            execution_time = (time.time() - start_time) * 1000
            self.log_error(
                f"Operation failed: {operation_name}",
                error=e,
                execution_time_ms=execution_time,
                **context
            )
            raise
        
        finally:
            # Restore context
            self.thread_local.context = old_context
    
    def log_info(self, message: str, **extra):
        """Log informational message."""
        self._log('main', LogLevel.INFO, message, extra)
    
    def log_warning(self, message: str, **extra):
        """Log warning message."""
        self._log('main', LogLevel.WARNING, message, extra)
    
    def log_error(self, message: str, error: Optional[Exception] = None, **extra):
        """Log error message with optional exception details."""
        error_details = None
        if error:
            error_details = {
                'error_type': type(error).__name__,
                'error_message': str(error),
                'traceback': traceback.format_exc()
            }
            extra['error_details'] = error_details
            
            # Increment error counter
            with self.lock:
                error_type = type(error).__name__
                self.error_counters[error_type] = self.error_counters.get(error_type, 0) + 1
        
        self._log('error', LogLevel.ERROR, message, extra)
    
    def log_critical(self, message: str, error: Optional[Exception] = None, **extra):
        """Log critical message."""
        if error:
            extra['error_details'] = {
                'error_type': type(error).__name__,
                'error_message': str(error),
                'traceback': traceback.format_exc()
            }
        self._log('main', LogLevel.CRITICAL, message, extra)
    
    def log_performance(self, message: str, execution_time_ms: float, **extra):
        """Log performance metrics."""
        metrics = PerformanceMetrics(
            execution_time_ms=execution_time_ms,
            memory_usage_mb=self._get_memory_usage(),
            cpu_usage_percent=self._get_cpu_usage(),
            operation_name=extra.get('operation', 'unknown'),
            query_complexity=extra.get('query_complexity'),
            pattern_complexity=extra.get('pattern_complexity'),
            cache_hit_rate=extra.get('cache_hit_rate'),
            rows_processed=extra.get('rows_processed')
        )
        
        with self.lock:
            self.performance_data.append(metrics)
            # Keep only recent data (last 1000 entries)
            if len(self.performance_data) > 1000:
                self.performance_data = self.performance_data[-1000:]
        
        extra['performance_metrics'] = asdict(metrics)
        self._log('performance', LogLevel.PERFORMANCE, message, extra)
    
    def log_audit(self, message: str, action: str, resource: str, **extra):
        """Log audit trail entry."""
        audit_data = {
            'action': action,
            'resource': resource,
            'timestamp': datetime.now().isoformat(),
            **extra
        }
        
        entry = self._create_log_entry(LogLevel.AUDIT, message, audit_data)
        with self.lock:
            self.audit_trail.append(entry)
            # Keep only recent audit entries (last 10000)
            if len(self.audit_trail) > 10000:
                self.audit_trail = self.audit_trail[-10000:]
        
        self._log('audit', LogLevel.AUDIT, message, audit_data)
    
    def log_security(self, message: str, event_type: str, severity: str = "HIGH", **extra):
        """Log security event."""
        security_data = {
            'event_type': event_type,
            'severity': severity,
            'timestamp': datetime.now().isoformat(),
            **extra
        }
        
        entry = self._create_log_entry(LogLevel.SECURITY, message, security_data)
        with self.lock:
            self.security_events.append(entry)
            # Keep only recent security events (last 1000)
            if len(self.security_events) > 1000:
                self.security_events = self.security_events[-1000:]
        
        self._log('security', LogLevel.SECURITY, message, security_data)
    
    def _log(self, logger_name: str, level: LogLevel, message: str, extra: Dict[str, Any]):
        """Internal logging method."""
        try:
            logger = self.loggers.get(logger_name, self.loggers['main'])
            
            # Add context information
            context = self.get_context()
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'thread_id': threading.get_ident(),
                'level': level.value,
                **context,
                **extra
            }
            
            # Log based on level
            if level == LogLevel.DEBUG:
                logger.debug(message, extra=log_data)
            elif level == LogLevel.INFO:
                logger.info(message, extra=log_data)
            elif level == LogLevel.WARNING:
                logger.warning(message, extra=log_data)
            elif level == LogLevel.ERROR:
                logger.error(message, extra=log_data)
            elif level == LogLevel.CRITICAL:
                logger.critical(message, extra=log_data)
            else:
                logger.info(message, extra=log_data)
                
        except Exception as e:
            # Fallback logging to prevent logging failures from breaking the application
            print(f"Logging failed: {e} - Original message: {message}")
    
    def _create_log_entry(self, level: LogLevel, message: str, extra: Dict[str, Any]) -> LogEntry:
        """Create structured log entry."""
        import inspect
        frame = inspect.currentframe().f_back.f_back
        
        return LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level.value,
            logger_name="rowmatch",
            message=message,
            module=frame.f_globals.get('__name__', 'unknown'),
            function=frame.f_code.co_name,
            line_number=frame.f_lineno,
            thread_id=threading.get_ident(),
            **self.get_context(),
            extra_data=extra
        )
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except:
            return 0.0
    
    def _get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1)
        except:
            return 0.0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get logging and performance statistics."""
        with self.lock:
            uptime = time.time() - self.start_time
            
            # Performance statistics
            recent_performance = [p for p in self.performance_data if p.execution_time_ms is not None]
            avg_execution_time = (
                sum(p.execution_time_ms for p in recent_performance) / len(recent_performance)
                if recent_performance else 0
            )
            
            return {
                'uptime_seconds': uptime,
                'total_operations': len(self.performance_data),
                'average_execution_time_ms': avg_execution_time,
                'error_counts': dict(self.error_counters),
                'audit_entries': len(self.audit_trail),
                'security_events': len(self.security_events),
                'current_memory_mb': self._get_memory_usage(),
                'current_cpu_percent': self._get_cpu_usage()
            }


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'thread_id': record.thread
        }
        
        # Add extra data if present
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, default=str)


# Global logger instance
_production_logger: Optional[ProductionLogger] = None
_logger_lock = threading.Lock()

def get_production_logger(config: Optional[MatchRecognizeConfig] = None) -> ProductionLogger:
    """Get or create global production logger instance."""
    global _production_logger
    
    with _logger_lock:
        if _production_logger is None:
            if config is None:
                config = MatchRecognizeConfig.from_env()
            _production_logger = ProductionLogger(config)
    
    return _production_logger

def setup_production_logging(config: Optional[MatchRecognizeConfig] = None):
    """Setup production logging system."""
    return get_production_logger(config)
