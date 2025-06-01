"""
Health check and monitoring endpoints for Row Match Recognize.

This module provides health check endpoints and system monitoring
capabilities for production deployments.
"""

from typing import Dict, Any, Optional
import time
import psutil
import threading
from datetime import datetime
from dataclasses import asdict

from ..config.production_config import get_config
from ..monitoring.production_logging import get_system_health, get_performance_tracker


class HealthChecker:
    """System health checker for production monitoring."""
    
    def __init__(self):
        self.config = get_config()
        self.start_time = time.time()
        self.performance_tracker = get_performance_tracker()
        self._lock = threading.Lock()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        with self._lock:
            try:
                # Basic system info
                basic_info = self._get_basic_info()
                
                # Performance metrics
                performance_info = self._get_performance_info()
                
                # Resource usage
                resource_info = self._get_resource_info()
                
                # Feature status
                feature_info = self._get_feature_status()
                
                # Overall health determination
                overall_status = self._determine_overall_health(
                    performance_info, resource_info
                )
                
                return {
                    'status': overall_status['status'],
                    'timestamp': datetime.utcnow().isoformat(),
                    'uptime_seconds': time.time() - self.start_time,
                    'version': self.config.version,
                    'environment': self.config.environment,
                    'basic_info': basic_info,
                    'performance': performance_info,
                    'resources': resource_info,
                    'features': feature_info,
                    'issues': overall_status['issues'],
                    'recommendations': overall_status['recommendations'],
                }
                
            except Exception as e:
                return {
                    'status': 'unhealthy',
                    'timestamp': datetime.utcnow().isoformat(),
                    'error': str(e),
                    'error_type': type(e).__name__,
                }
    
    def _get_basic_info(self) -> Dict[str, Any]:
        """Get basic system information."""
        return {
            'service_name': 'Row Match Recognize',
            'version': self.config.version,
            'environment': self.config.environment,
            'debug_mode': self.config.debug,
            'uptime_seconds': time.time() - self.start_time,
            'started_at': datetime.fromtimestamp(self.start_time).isoformat(),
        }
    
    def _get_performance_info(self) -> Dict[str, Any]:
        """Get performance metrics."""
        stats = self.performance_tracker.get_stats()
        recent_metrics = self.performance_tracker.get_recent_metrics(50)
        
        # Calculate error rates
        total_ops = stats.get('total_operations', 0)
        error_count = sum(1 for m in recent_metrics if m.get('error_count', 0) > 0)
        error_rate = error_count / max(total_ops, 1)
        
        # Calculate average response time
        durations = [m.get('duration_ms', 0) for m in recent_metrics if m.get('duration_ms')]
        avg_response_time = sum(durations) / max(len(durations), 1) if durations else 0
        
        return {
            'total_operations': total_ops,
            'error_rate': error_rate,
            'error_count': error_count,
            'avg_response_time_ms': avg_response_time,
            'recent_operations': len(recent_metrics),
            'operations_by_type': stats.get('operations', {}),
        }
    
    def _get_resource_info(self) -> Dict[str, Any]:
        """Get system resource information."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                'memory_usage': {
                    'rss_mb': memory_info.rss / 1024 / 1024,
                    'vms_mb': memory_info.vms / 1024 / 1024,
                    'percent': process.memory_percent(),
                },
                'cpu_usage': {
                    'percent': process.cpu_percent(),
                    'num_threads': process.num_threads(),
                },
                'system': {
                    'cpu_count': psutil.cpu_count(),
                    'memory_total_gb': psutil.virtual_memory().total / 1024 / 1024 / 1024,
                    'memory_available_gb': psutil.virtual_memory().available / 1024 / 1024 / 1024,
                },
            }
        except ImportError:
            return {
                'note': 'psutil not available - install for detailed resource monitoring'
            }
        except Exception as e:
            return {
                'error': f'Failed to get resource info: {str(e)}'
            }
    
    def _get_feature_status(self) -> Dict[str, Any]:
        """Get feature status information."""
        return {
            'caching_enabled': self.config.performance.enable_caching,
            'parallel_processing': self.config.performance.parallel_processing,
            'advanced_patterns': self.config.enable_advanced_patterns,
            'permute_functions': self.config.enable_permute_functions,
            'experimental_features': self.config.enable_experimental_features,
            'metrics_enabled': self.config.monitoring.enable_metrics,
            'tracing_enabled': self.config.monitoring.enable_tracing,
        }
    
    def _determine_overall_health(
        self, 
        performance_info: Dict[str, Any], 
        resource_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Determine overall health status."""
        issues = []
        recommendations = []
        status = 'healthy'
        
        # Check error rate
        error_rate = performance_info.get('error_rate', 0)
        if error_rate > 0.1:  # 10% error rate
            status = 'unhealthy'
            issues.append(f'High error rate: {error_rate:.1%}')
        elif error_rate > 0.05:  # 5% error rate
            status = 'degraded'
            issues.append(f'Elevated error rate: {error_rate:.1%}')
        
        # Check response times
        avg_response = performance_info.get('avg_response_time_ms', 0)
        if avg_response > 30000:  # 30 seconds
            status = 'unhealthy'
            issues.append(f'Very slow response times: {avg_response:.0f}ms avg')
        elif avg_response > 10000:  # 10 seconds
            if status == 'healthy':
                status = 'degraded'
            issues.append(f'Slow response times: {avg_response:.0f}ms avg')
        
        # Check memory usage
        memory_info = resource_info.get('memory_usage', {})
        memory_percent = memory_info.get('percent', 0)
        if memory_percent > 90:
            status = 'unhealthy'
            issues.append(f'Very high memory usage: {memory_percent:.1f}%')
        elif memory_percent > 75:
            if status == 'healthy':
                status = 'degraded'
            issues.append(f'High memory usage: {memory_percent:.1f}%')
        
        # Generate recommendations
        if error_rate > 0.01:
            recommendations.append('Monitor error logs for patterns')
        
        if avg_response > 5000:
            recommendations.append('Consider optimizing query patterns')
            recommendations.append('Review partition sizes and caching settings')
        
        if memory_percent > 50:
            recommendations.append('Monitor memory usage trends')
            if not self.config.performance.enable_caching:
                recommendations.append('Consider enabling caching for better performance')
        
        return {
            'status': status,
            'issues': issues,
            'recommendations': recommendations,
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get detailed metrics for monitoring systems."""
        stats = self.performance_tracker.get_stats()
        recent_metrics = self.performance_tracker.get_recent_metrics(100)
        
        # Process metrics for monitoring
        metrics = {
            'timestamp': datetime.utcnow().isoformat(),
            'counters': {
                'total_operations': stats.get('total_operations', 0),
                'operations_last_minute': len([
                    m for m in recent_metrics 
                    if time.time() - m.get('timestamp', 0) < 60
                ]),
            },
            'gauges': {
                'uptime_seconds': time.time() - self.start_time,
                'active_threads': threading.active_count(),
            },
            'histograms': {},
        }
        
        # Add operation-specific metrics
        operations = stats.get('operations', {})
        for op_name, op_stats in operations.items():
            metrics['histograms'][f'{op_name}_duration_ms'] = {
                'count': op_stats.get('count', 0),
                'avg': op_stats.get('avg_duration_ms', 0),
                'min': op_stats.get('min_duration_ms', 0),
                'max': op_stats.get('max_duration_ms', 0),
            }
        
        # Add resource metrics if available
        try:
            resource_info = self._get_resource_info()
            if 'memory_usage' in resource_info:
                metrics['gauges']['memory_usage_mb'] = resource_info['memory_usage']['rss_mb']
                metrics['gauges']['memory_percent'] = resource_info['memory_usage']['percent']
            
            if 'cpu_usage' in resource_info:
                metrics['gauges']['cpu_percent'] = resource_info['cpu_usage']['percent']
        except:
            pass
        
        return metrics


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get the global health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


def health_check() -> Dict[str, Any]:
    """Quick health check function."""
    checker = get_health_checker()
    return checker.get_health_status()


def get_metrics() -> Dict[str, Any]:
    """Get metrics for monitoring."""
    checker = get_health_checker()
    return checker.get_metrics()


# HTTP endpoint helpers (for web frameworks)
def health_endpoint():
    """Health check endpoint for web frameworks."""
    try:
        health_data = health_check()
        
        # Determine HTTP status code based on health
        status_code = 200
        if health_data.get('status') == 'degraded':
            status_code = 200  # Still operational
        elif health_data.get('status') == 'unhealthy':
            status_code = 503  # Service unavailable
        
        return health_data, status_code
        
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat(),
        }, 503


def metrics_endpoint():
    """Metrics endpoint for monitoring systems."""
    try:
        return get_metrics(), 200
    except Exception as e:
        return {
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat(),
        }, 500
