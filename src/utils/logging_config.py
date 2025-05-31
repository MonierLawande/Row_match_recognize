# src/utils/logging_config.py

import logging
import logging.config
import os
from pathlib import Path
from typing import Optional

def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_performance: bool = False
) -> None:
    """
    Set up logging configuration for the Row Match Recognize system.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        enable_console: Whether to enable console logging
        enable_performance: Whether to enable detailed performance logging
    """
    
    # Create logs directory if it doesn't exist
    if log_file:
        log_dir = Path(log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
    
    # Base configuration
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
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
            }
        },
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


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the specified module.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(f"row_match_recognize.{name}")


def get_performance_logger() -> logging.Logger:
    """
    Get a logger instance for performance metrics.
    
    Returns:
        Performance logger instance
    """
    return logging.getLogger("row_match_recognize.performance")


# Context manager for performance timing
class PerformanceTimer:
    """Context manager for timing operations and logging performance metrics."""
    
    def __init__(self, operation_name: str, logger: Optional[logging.Logger] = None):
        self.operation_name = operation_name
        self.logger = logger or get_performance_logger()
        self.start_time = None
        
    def __enter__(self):
        import time
        self.start_time = time.perf_counter()
        self.logger.debug(f"Starting {self.operation_name}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        end_time = time.perf_counter()
        duration = end_time - self.start_time
        
        if exc_type is None:
            self.logger.info(f"{self.operation_name} completed in {duration:.4f}s")
        else:
            self.logger.warning(f"{self.operation_name} failed after {duration:.4f}s: {exc_val}")


# Initialize default logging if not already configured
def init_default_logging():
    """Initialize default logging configuration if not already set up."""
    if not logging.getLogger().handlers:
        # Determine log level from environment
        log_level = os.getenv('ROW_MATCH_LOG_LEVEL', 'INFO').upper()
        
        # Determine if we should enable performance logging
        enable_perf = os.getenv('ROW_MATCH_ENABLE_PERFORMANCE_LOGGING', 'false').lower() == 'true'
        
        # Set up basic logging
        setup_logging(
            log_level=log_level,
            enable_console=True,
            enable_performance=enable_perf
        )


# Auto-initialize on import
init_default_logging()
