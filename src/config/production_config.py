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
from src.utils.resource_profile import (
    AdaptiveResourceProfile,
    get_adaptive_resource_profile,
)


@dataclass
class PerformanceConfig:
    """Performance-related configuration settings."""
    # ``-1`` means that there is no arbitrary row-count limit.  Execution is
    # still bounded by the adaptive memory budget and by explicit structural
    # safety policies.
    max_partition_size: int = -1
    execution_timeout_seconds: float = 300.0
    # Compatibility defaults for directly constructed configurations.
    # Normal engine execution uses MatchRecognizeConfig.from_env(), which
    # replaces these values with one container-aware resource snapshot.
    max_memory_mb: int = 8192
    enable_caching: bool = True
    cache_size_limit: int = 50_000
    cache_memory_limit_mb: int = 2048
    cache_ttl_seconds: int = 3600
    cache_clear_threshold_mb: int = 1600
    cache_monitoring_interval_seconds: int = 300
    parallel_processing: bool = False
    max_workers: int = 4
    # Core algorithm controls.  Disabled capabilities are not advertised as
    # active until their execution paths provide the corresponding behavior.
    enable_streaming_processing: bool = False
    enable_early_termination: bool = True
    enable_pattern_optimization: bool = True
    enable_memory_mapping: bool = False
    progress_reporting: bool = True
    optimize_for_unlimited_size: bool = False


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
    max_pattern_length: int = 50_000
    max_nesting_depth: int = 100
    max_permute_variables: int = 50


@dataclass
class MonitoringConfig:
    """Monitoring and observability configuration."""
    enable_metrics: bool = True
    metrics_endpoint: str = "/metrics"
    metrics_interval_seconds: int = 60
    enable_health_checks: bool = True
    health_check_endpoint: str = "/health"
    health_check_interval_seconds: int = 30
    enable_profiling: bool = False
    profiling_sample_rate: float = 0.01
    enable_tracing: bool = False
    sample_rate: float = 0.1
    alert_on_high_memory: bool = True
    alert_memory_threshold_mb: int = 800
    alert_on_slow_queries: bool = True
    alert_slow_query_threshold_seconds: float = 10.0


@dataclass
class ResourceConfig:
    """Resource management configuration."""
    max_concurrent_queries: int = 10
    query_queue_size: int = 100
    enable_resource_limits: bool = True
    cpu_usage_threshold: float = 80.0
    memory_usage_threshold: float = 85.0
    disk_usage_threshold: float = 90.0
    enable_graceful_degradation: bool = True
    emergency_cache_clear_threshold: float = 95.0


@dataclass
class MatchRecognizeConfig:
    """Main configuration class for Row Match Recognize system."""
    
    # Sub-configurations
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    
    # Environment
    environment: str = "development"
    debug: bool = False
    version: str = "2.0.0"
    
    # Feature flags
    enable_advanced_patterns: bool = True
    enable_permute_functions: bool = True
    enable_experimental_features: bool = False
    enable_production_mode: bool = False

    @classmethod
    def from_env(
        cls,
        resource_profile: Optional[AdaptiveResourceProfile] = None,
    ) -> 'MatchRecognizeConfig':
        """Create configuration from environment variables."""
        config = cls()
        profile = resource_profile or get_adaptive_resource_profile()

        # Resource defaults come from the effective process/container profile.
        # Environment values remain explicit administrator ceilings.
        config.performance.max_memory_mb = int(
            profile.query_budget_bytes / (1024 ** 2)
        )
        config.performance.cache_memory_limit_mb = int(
            profile.cache_budget_bytes / (1024 ** 2)
        )
        config.performance.cache_clear_threshold_mb = int(
            config.performance.cache_memory_limit_mb * 0.8
        )
        config.performance.cache_size_limit = profile.cache_entry_limit(
            estimated_entry_bytes=64 * 1024,
            budget_share=1.0,
            minimum=128,
            maximum=500_000,
        )
        config.performance.max_workers = profile.worker_count()
        # The cache and active queries share usable memory.  Reserve the
        # optional cache pool before calculating how many full per-query
        # budgets fit; otherwise two individually safe budgets can
        # collectively overcommit a small container.
        if profile.query_budget_bytes == 0:
            config.resources.max_concurrent_queries = 0
        else:
            concurrent_query_bytes = max(
                0,
                profile.usable_available_bytes - profile.cache_budget_bytes,
            )
            concurrent_by_memory = (
                concurrent_query_bytes // profile.query_budget_bytes
            )
            config.resources.max_concurrent_queries = max(
                1,
                min(profile.cpu.effective_cpus, concurrent_by_memory),
            )
        config.resources.query_queue_size = max(
            8,
            config.resources.max_concurrent_queries * 8,
        )

        def positive_int(name: str, current: int) -> int:
            raw = os.getenv(name)
            if raw is None:
                return current
            value = int(raw)
            if value < 1:
                raise ValueError(f"{name} must be a positive integer")
            return value

        def positive_float(name: str, current: float) -> float:
            raw = os.getenv(name)
            if raw is None:
                return current
            value = float(raw)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            return value

        def nonnegative_int(name: str, current: int) -> int:
            raw = os.getenv(name)
            if raw is None:
                return current
            value = int(raw)
            if value < 0:
                raise ValueError(
                    f"{name} must be a non-negative integer"
                )
            return value

        # Performance settings
        partition_size = int(os.getenv(
            'MR_MAX_PARTITION_SIZE',
            config.performance.max_partition_size,
        ))
        if partition_size != -1 and partition_size < 1:
            raise ValueError(
                "MR_MAX_PARTITION_SIZE must be -1 or a positive integer"
            )
        config.performance.max_partition_size = partition_size
        config.performance.execution_timeout_seconds = positive_float(
            'MR_EXECUTION_TIMEOUT',
            config.performance.execution_timeout_seconds,
        )
        max_memory_override = os.getenv('MR_MAX_MEMORY_MB')
        if max_memory_override is not None:
            config.performance.max_memory_mb = min(
                config.performance.max_memory_mb,
                positive_int(
                    'MR_MAX_MEMORY_MB',
                    config.performance.max_memory_mb,
                ),
            )
        cache_requested = (
            os.getenv('MR_ENABLE_CACHING', 'true').lower() == 'true'
        )
        cache_size_override = os.getenv('MR_CACHE_SIZE_LIMIT')
        if cache_size_override is not None:
            config.performance.cache_size_limit = min(
                config.performance.cache_size_limit,
                nonnegative_int(
                    'MR_CACHE_SIZE_LIMIT',
                    config.performance.cache_size_limit,
                ),
            )
        cache_memory_override = os.getenv('MR_CACHE_MEMORY_LIMIT_MB')
        if cache_memory_override is not None:
            config.performance.cache_memory_limit_mb = min(
                config.performance.cache_memory_limit_mb,
                nonnegative_int(
                    'MR_CACHE_MEMORY_LIMIT_MB',
                    config.performance.cache_memory_limit_mb,
                ),
            )
        cache_clear_override = os.getenv('MR_CACHE_CLEAR_THRESHOLD_MB')
        if cache_clear_override is not None:
            config.performance.cache_clear_threshold_mb = min(
                config.performance.cache_memory_limit_mb,
                nonnegative_int(
                    'MR_CACHE_CLEAR_THRESHOLD_MB',
                    config.performance.cache_clear_threshold_mb,
                ),
            )
        else:
            config.performance.cache_clear_threshold_mb = min(
                config.performance.cache_clear_threshold_mb,
                config.performance.cache_memory_limit_mb,
            )
        config.performance.enable_caching = bool(
            cache_requested
            and profile.cache_budget_bytes > 0
            and config.performance.cache_memory_limit_mb > 0
            and config.performance.cache_size_limit > 0
        )
        config.performance.cache_ttl_seconds = positive_int(
            'MR_CACHE_TTL_SECONDS',
            config.performance.cache_ttl_seconds,
        )
        config.performance.parallel_processing = os.getenv(
            'MR_PARALLEL_PROCESSING',
            str(config.performance.parallel_processing).lower(),
        ).lower() == 'true'
        max_workers_override = os.getenv('MR_MAX_WORKERS')
        if max_workers_override is not None:
            config.performance.max_workers = min(
                config.performance.max_workers,
                positive_int(
                    'MR_MAX_WORKERS',
                    config.performance.max_workers,
                ),
            )
        concurrent_override = os.getenv('MR_MAX_CONCURRENT_QUERIES')
        if concurrent_override is not None:
            config.resources.max_concurrent_queries = min(
                config.resources.max_concurrent_queries,
                positive_int(
                    'MR_MAX_CONCURRENT_QUERIES',
                    config.resources.max_concurrent_queries,
                ),
            )
        queue_override = os.getenv('MR_QUERY_QUEUE_SIZE')
        if queue_override is not None:
            config.resources.query_queue_size = min(
                config.resources.query_queue_size,
                positive_int(
                    'MR_QUERY_QUEUE_SIZE',
                    config.resources.query_queue_size,
                ),
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

        if 'resources' in data:
            resource_data = data['resources']
            config.resources = ResourceConfig(**resource_data)
        
        # Main config
        for key, value in data.items():
            if key not in [
                'performance',
                'logging',
                'security',
                'monitoring',
                'resources',
            ]:
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
            'resources': {
                'max_concurrent_queries':
                    self.resources.max_concurrent_queries,
                'query_queue_size': self.resources.query_queue_size,
                'enable_resource_limits':
                    self.resources.enable_resource_limits,
                'cpu_usage_threshold':
                    self.resources.cpu_usage_threshold,
                'memory_usage_threshold':
                    self.resources.memory_usage_threshold,
                'disk_usage_threshold':
                    self.resources.disk_usage_threshold,
                'enable_graceful_degradation':
                    self.resources.enable_graceful_degradation,
                'emergency_cache_clear_threshold':
                    self.resources.emergency_cache_clear_threshold,
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
        if (
            self.performance.max_partition_size != -1
            and self.performance.max_partition_size <= 0
        ):
            errors.append("max_partition_size must be -1 or positive")
        
        if self.performance.execution_timeout_seconds <= 0:
            errors.append("execution_timeout_seconds must be positive")

        if self.performance.max_memory_mb < 0:
            errors.append("max_memory_mb cannot be negative")

        if self.performance.max_workers <= 0:
            errors.append("max_workers must be positive")

        if self.resources.max_concurrent_queries < 0:
            errors.append("max_concurrent_queries cannot be negative")

        if self.resources.query_queue_size <= 0:
            errors.append("query_queue_size must be positive")
        
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
        max_partition_size=-1,
        execution_timeout_seconds=300.0,
        enable_caching=True,
        parallel_processing=False,
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
