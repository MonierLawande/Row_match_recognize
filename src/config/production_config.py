"""
Production configuration system for Row Match Recognize.

This module provides a comprehensive configuration management system
for production deployments with environment-specific settings.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from pathlib import Path
import json


@dataclass
class PerformanceConfig:
    """Performance-related configuration settings."""
    max_partition_size: int = 100_000
    execution_timeout_seconds: float = 30.0
    max_memory_mb: int = 1024
    enable_caching: bool = True
    cache_size_limit: int = 10_000
    cache_memory_limit_mb: int = 500
    cache_ttl_seconds: int = 3600
    cache_clear_threshold_mb: int = 400
    cache_monitoring_interval_seconds: int = 300
    parallel_processing: bool = False
    max_workers: int = 4


@dataclass
class LoggingConfig:
    """Logging configuration settings."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    enable_structured_logging: bool = True
    log_file: Optional[str] = None
    max_log_size_mb: int = 100
    backup_count: int = 5


@dataclass
class SecurityConfig:
    """Security-related configuration settings."""
    validate_input: bool = True
    max_query_complexity: int = 1000
    rate_limit_queries_per_minute: int = 60
    enable_query_sanitization: bool = True


@dataclass
class MonitoringConfig:
    """Monitoring and observability configuration."""
    enable_metrics: bool = True
    metrics_endpoint: str = "/metrics"
    health_check_endpoint: str = "/health"
    enable_tracing: bool = False
    sample_rate: float = 0.1


@dataclass
class MatchRecognizeConfig:
    """Main configuration class for Row Match Recognize system."""
    
    # Sub-configurations
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    # Environment
    environment: str = "development"
    debug: bool = False
    version: str = "1.0.0"
    
    # Feature flags
    enable_advanced_patterns: bool = True
    enable_permute_functions: bool = True
    enable_experimental_features: bool = False

    @classmethod
    def from_env(cls) -> 'MatchRecognizeConfig':
        """Create configuration from environment variables."""
        config = cls()
        
        # Performance settings
        config.performance.max_partition_size = int(
            os.getenv('MR_MAX_PARTITION_SIZE', config.performance.max_partition_size)
        )
        config.performance.execution_timeout_seconds = float(
            os.getenv('MR_EXECUTION_TIMEOUT', config.performance.execution_timeout_seconds)
        )
        config.performance.enable_caching = os.getenv('MR_ENABLE_CACHING', 'true').lower() == 'true'
        config.performance.cache_size_limit = int(
            os.getenv('MR_CACHE_SIZE_LIMIT', config.performance.cache_size_limit)
        )
        config.performance.cache_memory_limit_mb = int(
            os.getenv('MR_CACHE_MEMORY_LIMIT_MB', config.performance.cache_memory_limit_mb)
        )
        config.performance.cache_ttl_seconds = int(
            os.getenv('MR_CACHE_TTL_SECONDS', config.performance.cache_ttl_seconds)
        )
        config.performance.parallel_processing = os.getenv('MR_PARALLEL_PROCESSING', 'false').lower() == 'true'
        config.performance.max_workers = int(
            os.getenv('MR_MAX_WORKERS', config.performance.max_workers)
        )
        
        # Logging settings
        config.logging.level = os.getenv('MR_LOG_LEVEL', config.logging.level)
        config.logging.log_file = os.getenv('MR_LOG_FILE')
        
        # Environment
        config.environment = os.getenv('MR_ENVIRONMENT', config.environment)
        config.debug = os.getenv('MR_DEBUG', 'false').lower() == 'true'
        
        return config

    @classmethod
    def from_file(cls, config_path: str) -> 'MatchRecognizeConfig':
        """Load configuration from JSON file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MatchRecognizeConfig':
        """Create configuration from dictionary."""
        config = cls()
        
        # Performance
        if 'performance' in data:
            perf_data = data['performance']
            config.performance = PerformanceConfig(**perf_data)
        
        # Logging
        if 'logging' in data:
            log_data = data['logging']
            config.logging = LoggingConfig(**log_data)
        
        # Security
        if 'security' in data:
            sec_data = data['security']
            config.security = SecurityConfig(**sec_data)
        
        # Monitoring
        if 'monitoring' in data:
            mon_data = data['monitoring']
            config.monitoring = MonitoringConfig(**mon_data)
        
        # Main config
        for key, value in data.items():
            if key not in ['performance', 'logging', 'security', 'monitoring']:
                if hasattr(config, key):
                    setattr(config, key, value)
        
        return config

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'performance': {
                'max_partition_size': self.performance.max_partition_size,
                'execution_timeout_seconds': self.performance.execution_timeout_seconds,
                'max_memory_mb': self.performance.max_memory_mb,
                'enable_caching': self.performance.enable_caching,
                'cache_size_limit': self.performance.cache_size_limit,
                'parallel_processing': self.performance.parallel_processing,
                'max_workers': self.performance.max_workers,
            },
            'logging': {
                'level': self.logging.level,
                'format': self.logging.format,
                'enable_structured_logging': self.logging.enable_structured_logging,
                'log_file': self.logging.log_file,
                'max_log_size_mb': self.logging.max_log_size_mb,
                'backup_count': self.logging.backup_count,
            },
            'security': {
                'validate_input': self.security.validate_input,
                'max_query_complexity': self.security.max_query_complexity,
                'rate_limit_queries_per_minute': self.security.rate_limit_queries_per_minute,
                'enable_query_sanitization': self.security.enable_query_sanitization,
            },
            'monitoring': {
                'enable_metrics': self.monitoring.enable_metrics,
                'metrics_endpoint': self.monitoring.metrics_endpoint,
                'health_check_endpoint': self.monitoring.health_check_endpoint,
                'enable_tracing': self.monitoring.enable_tracing,
                'sample_rate': self.monitoring.sample_rate,
            },
            'environment': self.environment,
            'debug': self.debug,
            'version': self.version,
            'enable_advanced_patterns': self.enable_advanced_patterns,
            'enable_permute_functions': self.enable_permute_functions,
            'enable_experimental_features': self.enable_experimental_features,
        }

    def save_to_file(self, config_path: str) -> None:
        """Save configuration to JSON file."""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    def validate(self) -> None:
        """Validate configuration settings."""
        errors = []
        
        # Performance validation
        if self.performance.max_partition_size <= 0:
            errors.append("max_partition_size must be positive")
        
        if self.performance.execution_timeout_seconds <= 0:
            errors.append("execution_timeout_seconds must be positive")
        
        # Logging validation
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.logging.level not in valid_log_levels:
            errors.append(f"log_level must be one of {valid_log_levels}")
        
        # Security validation
        if self.security.max_query_complexity <= 0:
            errors.append("max_query_complexity must be positive")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {', '.join(errors)}")

    def setup_logging(self) -> None:
        """Setup logging based on configuration."""
        logging.basicConfig(
            level=getattr(logging, self.logging.level.upper()),
            format=self.logging.format
        )
        
        if self.logging.log_file:
            from logging.handlers import RotatingFileHandler
            
            handler = RotatingFileHandler(
                self.logging.log_file,
                maxBytes=self.logging.max_log_size_mb * 1024 * 1024,
                backupCount=self.logging.backup_count
            )
            handler.setFormatter(logging.Formatter(self.logging.format))
            
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)


# Global configuration instance
_config: Optional[MatchRecognizeConfig] = None


def get_config() -> MatchRecognizeConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = MatchRecognizeConfig.from_env()
        _config.validate()
        _config.setup_logging()
    return _config


def set_config(config: MatchRecognizeConfig) -> None:
    """Set the global configuration instance."""
    global _config
    config.validate()
    _config = config
    config.setup_logging()


def reset_config() -> None:
    """Reset configuration to default."""
    global _config
    _config = None


# Configuration presets for different environments
DEVELOPMENT_CONFIG = MatchRecognizeConfig(
    environment="development",
    debug=True,
    performance=PerformanceConfig(
        max_partition_size=10_000,
        execution_timeout_seconds=60.0,
        enable_caching=True,
    ),
    logging=LoggingConfig(
        level="DEBUG",
        enable_structured_logging=False,
    ),
    monitoring=MonitoringConfig(
        enable_metrics=False,
        enable_tracing=False,
    )
)

PRODUCTION_CONFIG = MatchRecognizeConfig(
    environment="production",
    debug=False,
    performance=PerformanceConfig(
        max_partition_size=100_000,
        execution_timeout_seconds=30.0,
        enable_caching=True,
        parallel_processing=True,
    ),
    logging=LoggingConfig(
        level="INFO",
        enable_structured_logging=True,
        log_file="/var/log/match_recognize/app.log",
    ),
    security=SecurityConfig(
        validate_input=True,
        rate_limit_queries_per_minute=100,
    ),
    monitoring=MonitoringConfig(
        enable_metrics=True,
        enable_tracing=True,
        sample_rate=0.1,
    )
)

TESTING_CONFIG = MatchRecognizeConfig(
    environment="testing",
    debug=True,
    performance=PerformanceConfig(
        max_partition_size=1_000,
        execution_timeout_seconds=10.0,
        enable_caching=False,
    ),
    logging=LoggingConfig(
        level="WARNING",
        enable_structured_logging=False,
    ),
    monitoring=MonitoringConfig(
        enable_metrics=False,
        enable_tracing=False,
    )
)
