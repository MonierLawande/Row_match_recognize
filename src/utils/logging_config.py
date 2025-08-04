# src/utils/logging_config.py

import logging
import logging.config
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager

class DebugLevel(Enum):
    """Enhanced debug levels for production-ready debugging."""
    DISABLED = "DISABLED"
    MINIMAL = "MINIMAL"
    STANDARD = "STANDARD"
    VERBOSE = "VERBOSE"
    TRACE = "TRACE"


@dataclass
class DebugConfig:
    """
    Production-ready debug configuration system.
    
    Provides comprehensive debugging control with safety features,
    environment-specific presets, and performance monitoring.
    """
    level: DebugLevel = DebugLevel.DISABLED
    enable_query_debugging: bool = False
    enable_pattern_debugging: bool = False
    enable_performance_debugging: bool = False
    enable_automata_debugging: bool = False
    enable_memory_debugging: bool = False
    enable_cache_debugging: bool = False
    
    # File output settings
    debug_file: Optional[str] = None
    max_debug_file_size: int = 50 * 1024 * 1024  # 50MB
    max_debug_files: int = 5
    
    # Performance settings
    performance_threshold_ms: float = 100.0
    enable_slow_query_logging: bool = True
    
    # Safety settings
    max_debug_output_size: int = 10 * 1024 * 1024  # 10MB per operation
    enable_debug_sampling: bool = True
    debug_sample_rate: float = 0.1  # 10% sampling in production
    
    # Environment-specific settings
    environment: str = field(default_factory=lambda: os.getenv('ENVIRONMENT', 'production'))
    
    def __post_init__(self):
        """Apply environment-specific configurations and validation."""
        self._apply_environment_config()
        self._validate_config()
    
    def _apply_environment_config(self):
        """Apply environment-specific debug configurations."""
        env = self.environment.lower()
        
        if env == 'development':
            self.level = DebugLevel.STANDARD
            self.enable_query_debugging = True
            self.enable_pattern_debugging = True
            self.enable_performance_debugging = True
            self.debug_sample_rate = 1.0  # 100% sampling in dev
            
        elif env == 'testing':
            self.level = DebugLevel.VERBOSE
            self.enable_query_debugging = True
            self.enable_pattern_debugging = True
            self.enable_performance_debugging = True
            self.enable_automata_debugging = True
            self.debug_sample_rate = 1.0  # 100% sampling in testing
            
        elif env == 'staging':
            self.level = DebugLevel.MINIMAL
            self.enable_performance_debugging = True
            self.enable_slow_query_logging = True
            self.debug_sample_rate = 0.05  # 5% sampling in staging
            
        else:  # production
            self.level = DebugLevel.DISABLED
            self.enable_slow_query_logging = True
            self.debug_sample_rate = 0.01  # 1% sampling in production
            
        # Override with environment variables
        env_level = os.getenv('ROW_MATCH_DEBUG_LEVEL')
        if env_level:
            try:
                self.level = DebugLevel(env_level.upper())
            except ValueError:
                pass  # Keep default
    
    def _validate_config(self):
        """Validate configuration settings."""
        if self.debug_sample_rate < 0 or self.debug_sample_rate > 1:
            self.debug_sample_rate = 0.1
            
        if self.performance_threshold_ms < 0:
            self.performance_threshold_ms = 100.0
            
        if self.max_debug_output_size < 1024:  # Minimum 1KB
            self.max_debug_output_size = 1024
    
    def is_debug_enabled(self) -> bool:
        """Check if any debugging is enabled."""
        return self.level != DebugLevel.DISABLED
    
    def should_debug_component(self, component: str) -> bool:
        """Check if debugging is enabled for a specific component."""
        if not self.is_debug_enabled():
            return False
            
        component_map = {
            'query': self.enable_query_debugging,
            'pattern': self.enable_pattern_debugging,
            'performance': self.enable_performance_debugging,
            'automata': self.enable_automata_debugging,
            'memory': self.enable_memory_debugging,
            'cache': self.enable_cache_debugging
        }
        
        return component_map.get(component, False)


class DebugManager:
    """
    Production-ready debug manager with comprehensive debugging capabilities.
    
    Provides centralized debug management with performance monitoring,
    state inspection, and safe debug output handling.
    """
    
    def __init__(self, config: Optional[DebugConfig] = None):
        self.config = config or DebugConfig()
        self.debug_logger = get_logger("debug")
        self.performance_logger = get_performance_logger()
        self._lock = threading.RLock()
        self._debug_stats = {
            'total_debug_calls': 0,
            'total_debug_output_size': 0,
            'performance_events': 0,
            'slow_queries': 0
        }
        
    def debug_query(self, query: str, context: Dict[str, Any] = None, 
                   execution_time: Optional[float] = None) -> None:
        """Debug a query with context and performance information."""
        if not self.config.should_debug_component('query'):
            return
            
        with self._lock:
            self._debug_stats['total_debug_calls'] += 1
            
        context = context or {}
        
        # Log slow queries even if query debugging is disabled
        if (execution_time and execution_time * 1000 > self.config.performance_threshold_ms 
            and self.config.enable_slow_query_logging):
            self._debug_stats['slow_queries'] += 1
            self.performance_logger.warning(
                f"Slow query detected ({execution_time:.3f}s): {self._truncate_debug_output(query, 500)}"
            )
        
        if self.config.enable_query_debugging:
            debug_info = {
                'query': self._truncate_debug_output(query, 1000),
                'context_keys': list(context.keys()),
                'execution_time': execution_time,
                'timestamp': time.time()
            }
            
            self.debug_logger.debug(f"Query Debug: {debug_info}")
    
    def debug_pattern(self, pattern: str, tokens: List = None, metadata: Dict[str, Any] = None) -> None:
        """Debug pattern parsing and processing."""
        if not self.config.should_debug_component('pattern'):
            return
            
        debug_info = {
            'pattern': self._truncate_debug_output(str(pattern), 500),
            'token_count': len(tokens) if tokens else 0,
            'metadata_keys': list(metadata.keys()) if metadata else []
        }
        
        self.debug_logger.debug(f"Pattern Debug: {debug_info}")
    
    def debug_performance(self, operation: str, duration: float, 
                         metadata: Dict[str, Any] = None) -> None:
        """Debug performance information."""
        if not self.config.should_debug_component('performance'):
            return
            
        with self._lock:
            self._debug_stats['performance_events'] += 1
            
        perf_info = {
            'operation': operation,
            'duration_ms': duration * 1000,
            'is_slow': duration * 1000 > self.config.performance_threshold_ms,
            'metadata': metadata or {}
        }
        
        if perf_info['is_slow']:
            self.performance_logger.warning(f"Slow operation: {perf_info}")
        else:
            self.performance_logger.debug(f"Performance: {perf_info}")
    
    def debug_automata(self, nfa_info: Dict[str, Any]) -> None:
        """Debug automata construction and state information."""
        if not self.config.should_debug_component('automata'):
            return
            
        safe_info = {
            'state_count': nfa_info.get('state_count', 'unknown'),
            'start_state': nfa_info.get('start_state', 'unknown'),
            'accept_state': nfa_info.get('accept_state', 'unknown'),
            'has_exclusions': nfa_info.get('has_exclusions', False),
            'has_permute': nfa_info.get('has_permute', False)
        }
        
        self.debug_logger.debug(f"Automata Debug: {safe_info}")
    
    def debug_memory(self, component: str, memory_info: Dict[str, Any]) -> None:
        """Debug memory usage information."""
        if not self.config.should_debug_component('memory'):
            return
            
        safe_memory_info = {
            'component': component,
            'memory_mb': memory_info.get('memory_mb', 0),
            'object_count': memory_info.get('object_count', 0),
            'pool_stats': memory_info.get('pool_stats', {})
        }
        
        self.debug_logger.debug(f"Memory Debug: {safe_memory_info}")
    
    def get_debug_stats(self) -> Dict[str, Any]:
        """Get current debugging statistics."""
        with self._lock:
            return self._debug_stats.copy()
    
    def reset_debug_stats(self) -> None:
        """Reset debugging statistics."""
        with self._lock:
            self._debug_stats = {
                'total_debug_calls': 0,
                'total_debug_output_size': 0,
                'performance_events': 0,
                'slow_queries': 0
            }
    
    def _truncate_debug_output(self, output: str, max_length: int) -> str:
        """Safely truncate debug output to prevent memory issues."""
        if len(output) <= max_length:
            return output
        
        truncated = output[:max_length - 20] + "...[TRUNCATED]..."
        
        with self._lock:
            self._debug_stats['total_debug_output_size'] += len(truncated)
            
        return truncated
    
    def should_sample_debug(self) -> bool:
        """Determine if this debug call should be sampled."""
        if self.config.debug_sample_rate >= 1.0:
            return True
        
        import random
        return random.random() < self.config.debug_sample_rate


# Global debug manager instance
_debug_manager: Optional[DebugManager] = None


def get_debug_manager() -> DebugManager:
    """Get the global debug manager instance."""
    global _debug_manager
    if _debug_manager is None:
        _debug_manager = DebugManager()
    return _debug_manager


def configure_debug(config: DebugConfig) -> None:
    """Configure the global debug manager with new settings."""
    global _debug_manager
    _debug_manager = DebugManager(config)


def debug_query(query: str, context: Dict[str, Any] = None, 
               execution_time: Optional[float] = None) -> None:
    """Convenient function for query debugging."""
    get_debug_manager().debug_query(query, context, execution_time)


def debug_pattern(pattern: str, tokens: List = None, metadata: Dict[str, Any] = None) -> None:
    """Convenient function for pattern debugging."""
    get_debug_manager().debug_pattern(pattern, tokens, metadata)


def debug_performance(operation: str, duration: float, metadata: Dict[str, Any] = None) -> None:
    """Convenient function for performance debugging."""
    get_debug_manager().debug_performance(operation, duration, metadata)


def debug_automata(nfa_info: Dict[str, Any]) -> None:
    """Convenient function for automata debugging."""
    get_debug_manager().debug_automata(nfa_info)


def debug_memory(component: str, memory_info: Dict[str, Any]) -> None:
    """Convenient function for memory debugging."""
    get_debug_manager().debug_memory(component, memory_info)


@contextmanager
def debug_context(operation: str, component: str = "general"):
    """Context manager for debugging operations with automatic timing."""
    debug_manager = get_debug_manager()
    
    if not debug_manager.config.is_debug_enabled():
        yield
        return
    
    start_time = time.perf_counter()
    
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        debug_performance(f"{component}.{operation}", duration)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_performance: bool = False,
    debug_config: Optional[DebugConfig] = None
) -> None:
    """
    Set up comprehensive logging configuration for the Row Match Recognize system.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        enable_console: Whether to enable console logging
        enable_performance: Whether to enable detailed performance logging
        debug_config: Optional debug configuration for enhanced debugging
    """
    
    # Create logs directory if it doesn't exist
    if log_file:
        log_dir = Path(log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
    
    # Enhanced formatters for debugging
    formatters = {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'simple': {
            'format': '%(levelname)s - %(name)s - %(message)s'
        },
        'performance': {
            'format': '%(asctime)s - PERF - %(name)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S.%f'
        },
        'debug': {
            'format': '%(asctime)s - DEBUG - %(name)s - %(filename)s:%(lineno)d - %(funcName)s() - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S.%f'
        }
    }
    
    # Base configuration
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': formatters,
        'handlers': {},
        'loggers': {
            'row_match_recognize': {
                'level': log_level,
                'handlers': [],
                'propagate': False
            },
            'row_match_recognize.performance': {
                'level': 'DEBUG' if enable_performance else 'INFO',
                'handlers': [],
                'propagate': False
            },
            'row_match_recognize.debug': {
                'level': 'DEBUG' if debug_config and debug_config.is_debug_enabled() else 'INFO',
                'handlers': [],
                'propagate': False
            }
        },
        'root': {
            'level': log_level,
            'handlers': []
        }
    }
    
    # Add console handler if enabled
    if enable_console:
        config['handlers']['console'] = {
            'class': 'logging.StreamHandler',
            'level': log_level,
            'formatter': 'simple',
            'stream': 'ext://sys.stdout'
        }
        config['loggers']['row_match_recognize']['handlers'].append('console')
        config['root']['handlers'].append('console')
    
    # Add file handler if log file specified
    if log_file:
        config['handlers']['file'] = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'filename': log_file,
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'encoding': 'utf8'
        }
        config['loggers']['row_match_recognize']['handlers'].append('file')
        config['root']['handlers'].append('file')
    
    # Add debug handler if debug config is provided
    if debug_config and debug_config.is_debug_enabled():
        debug_formatter = 'debug' if debug_config.level in [DebugLevel.VERBOSE, DebugLevel.TRACE] else 'detailed'
        
        if debug_config.debug_file:
            config['handlers']['debug'] = {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'DEBUG',
                'formatter': debug_formatter,
                'filename': debug_config.debug_file,
                'maxBytes': debug_config.max_debug_file_size,
                'backupCount': debug_config.max_debug_files,
                'encoding': 'utf8'
            }
            config['loggers']['row_match_recognize.debug']['handlers'].append('debug')
        else:
            # Add debug to console if no file specified
            config['loggers']['row_match_recognize.debug']['handlers'].append('console')
    
    # Add performance handler if enabled
    if enable_performance:
        perf_file = log_file.replace('.log', '_performance.log') if log_file else 'performance.log'
        config['handlers']['performance'] = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'performance',
            'filename': perf_file,
            'maxBytes': 10485760,  # 10MB
            'backupCount': 3,
            'encoding': 'utf8'
        }
        config['loggers']['row_match_recognize.performance']['handlers'].append('performance')
    
    # Apply configuration
    logging.config.dictConfig(config)
    
    # Configure global debug manager if debug config provided
    if debug_config:
        configure_debug(debug_config)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the specified module with enhanced debugging support.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance with debugging capabilities
    """
    return logging.getLogger(f"row_match_recognize.{name}")


def get_debug_logger() -> logging.Logger:
    """
    Get a logger instance for debug information.
    
    Returns:
        Debug logger instance
    """
    return logging.getLogger("row_match_recognize.debug")


def get_performance_logger() -> logging.Logger:
    """
    Get a logger instance for performance metrics.
    
    Returns:
        Performance logger instance
    """
    return logging.getLogger("row_match_recognize.performance")


def set_log_level(level: str, verbose: bool = True):
    """
    Dynamically change the logging level for all row_match_recognize loggers.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        verbose: Whether to print confirmation message
    """
    level = level.upper()
    
    # Update root logger first to prevent any issues
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Update main logger
    main_logger = logging.getLogger("row_match_recognize")
    main_logger.setLevel(level)
    
    # Update performance logger  
    perf_logger = logging.getLogger("row_match_recognize.performance")
    perf_logger.setLevel(level)
    
    # Update debug logger
    debug_logger = logging.getLogger("row_match_recognize.debug")
    debug_logger.setLevel(level)
    
    # Update all handlers for main logger
    for handler in main_logger.handlers:
        handler.setLevel(level)
        
    # Update all handlers for root logger
    for handler in root_logger.handlers:
        handler.setLevel(level)
    
    # Update ALL existing loggers that start with row_match_recognize
    for logger_name in list(logging.Logger.manager.loggerDict.keys()):
        if logger_name.startswith("row_match_recognize"):
            child_logger = logging.getLogger(logger_name)
            child_logger.setLevel(level)
            for handler in child_logger.handlers:
                handler.setLevel(level)
    
    if verbose:
        print(f"Logging level set to {level} for all loggers")


def enable_debug_logging():
    """Enable detailed debug logging and configure debug manager."""
    set_log_level('DEBUG')
    
    # Configure debug manager for development
    debug_config = DebugConfig(
        level=DebugLevel.STANDARD,
        enable_query_debugging=True,
        enable_pattern_debugging=True,
        enable_performance_debugging=True,
        environment='development'
    )
    configure_debug(debug_config)


def enable_production_debug():
    """Enable production-safe debugging with sampling."""
    debug_config = DebugConfig(
        level=DebugLevel.MINIMAL,
        enable_performance_debugging=True,
        enable_slow_query_logging=True,
        debug_sample_rate=0.01,  # 1% sampling
        environment='production'
    )
    configure_debug(debug_config)


def enable_quiet_logging():
    """Enable only warnings and errors."""
    set_log_level('WARNING', verbose=False)


def enable_normal_logging():
    """Enable info, warnings and errors."""
    set_log_level('INFO')


def setup_environment_logging():
    """Set up logging based on environment variables."""
    env = os.getenv('ENVIRONMENT', 'production').lower()
    log_level = os.getenv('ROW_MATCH_LOG_LEVEL', 'WARNING' if env == 'production' else 'INFO').upper()
    
    # Create debug config based on environment
    debug_config = DebugConfig(environment=env)
    
    # Set up logging with debug config
    setup_logging(
        log_level=log_level,
        enable_console=True,
        enable_performance=debug_config.enable_performance_debugging,
        debug_config=debug_config
    )


# Enhanced Context manager for performance timing
class PerformanceTimer:
    """
    Enhanced context manager for timing operations and logging performance metrics.
    
    Integrates with the debug manager for comprehensive performance tracking.
    """
    
    def __init__(self, operation_name: str, logger: Optional[logging.Logger] = None, 
                 component: str = "general", enable_debug: bool = True):
        self.operation_name = operation_name
        self.component = component
        self.enable_debug = enable_debug
        self.logger = logger or get_performance_logger()
        self.start_time = None
        self.elapsed = 0.0
        
    def __enter__(self):
        self.start_time = time.perf_counter()
        self.logger.debug(f"Starting {self.component}.{self.operation_name}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.perf_counter()
        self.elapsed = end_time - self.start_time
        
        if exc_type is None:
            self.logger.info(f"{self.component}.{self.operation_name} completed in {self.elapsed:.4f}s")
        else:
            self.logger.warning(f"{self.component}.{self.operation_name} failed after {self.elapsed:.4f}s: {exc_val}")
        
        # Also log to debug manager if enabled
        if self.enable_debug:
            debug_performance(f"{self.component}.{self.operation_name}", self.elapsed)


# Initialize default logging if not already configured
def init_default_logging():
    """Initialize production-ready default logging configuration if not already set up."""
    if not logging.getLogger().handlers:
        # Use environment-based setup
        setup_environment_logging()
        
    # ALWAYS apply appropriate logging by default based on environment
    env = os.getenv('ENVIRONMENT', 'production').lower()
    if env == 'production':
        enable_quiet_logging()
    elif env == 'development':
        enable_debug_logging()
    else:
        enable_normal_logging()


# Convenience functions for quick debugging setup
def quick_debug_setup(enable_file_logging: bool = False, debug_file: str = "debug.log"):
    """Quickly set up debugging for development."""
    debug_config = DebugConfig(
        level=DebugLevel.VERBOSE,
        enable_query_debugging=True,
        enable_pattern_debugging=True,
        enable_performance_debugging=True,
        enable_automata_debugging=True,
        debug_file=debug_file if enable_file_logging else None,
        environment='development'
    )
    
    setup_logging(
        log_level='DEBUG',
        enable_console=True,
        enable_performance=True,
        debug_config=debug_config
    )


def production_logging_setup(log_file: str = "production.log"):
    """Set up production-ready logging with minimal overhead."""
    debug_config = DebugConfig(
        level=DebugLevel.DISABLED,
        enable_slow_query_logging=True,
        environment='production'
    )
    
    setup_logging(
        log_level='WARNING',
        log_file=log_file,
        enable_console=False,
        enable_performance=False,
        debug_config=debug_config
    )


def get_debug_status() -> Dict[str, Any]:
    """Get current debug configuration status."""
    debug_manager = get_debug_manager()
    return {
        'debug_enabled': debug_manager.config.is_debug_enabled(),
        'debug_level': debug_manager.config.level.value,
        'environment': debug_manager.config.environment,
        'components_enabled': {
            'query': debug_manager.config.enable_query_debugging,
            'pattern': debug_manager.config.enable_pattern_debugging,
            'performance': debug_manager.config.enable_performance_debugging,
            'automata': debug_manager.config.enable_automata_debugging,
            'memory': debug_manager.config.enable_memory_debugging,
            'cache': debug_manager.config.enable_cache_debugging
        },
        'debug_stats': debug_manager.get_debug_stats()
    }


# Auto-initialize on import and apply appropriate logging by default
init_default_logging()
