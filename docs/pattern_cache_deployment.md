# Production Deployment Guide: Enhanced Pattern Caching

This guide provides instructions for deploying and configuring the enhanced pattern caching system in production environments. The caching system significantly improves performance by avoiding redundant pattern compilations while maintaining controlled memory usage.

## 1. Configuration Setup

### Environment Variables

Set the following environment variables to configure caching behavior:

```bash
# Enable/disable caching
export MR_ENABLE_CACHING=true

# Cache size limit (number of patterns)
export MR_CACHE_SIZE_LIMIT=10000

# Cache memory limit (MB)
export MR_CACHE_MEMORY_LIMIT_MB=500

# Cache TTL (seconds)
export MR_CACHE_TTL_SECONDS=3600

# Monitoring interval (seconds)
export MR_CACHE_MONITORING_INTERVAL_SECONDS=300
```

### Configuration File

Alternatively, you can modify the `src/config/production_config.py` file:

```python
@dataclass
class PerformanceConfig:
    # ...
    enable_caching: bool = True
    cache_size_limit: int = 10_000
    cache_memory_limit_mb: int = 500
    cache_ttl_seconds: int = 3600
    cache_clear_threshold_mb: int = 400
    cache_monitoring_interval_seconds: int = 300
    # ...
```

## 2. Deployment Strategies

### Containerized Deployment (Docker)

When deploying in Docker containers, include the environment variables in your Dockerfile or docker-compose.yml:

```dockerfile
FROM python:3.9-slim

# Set cache configuration
ENV MR_ENABLE_CACHING=true
ENV MR_CACHE_SIZE_LIMIT=10000
ENV MR_CACHE_MEMORY_LIMIT_MB=500

# Copy application
COPY . /app
WORKDIR /app

# Install dependencies
RUN pip install -r requirements.txt

# Start the application with cache monitoring
CMD ["python", "-c", "from src.monitoring.cache_monitor import start_cache_monitoring; start_cache_monitoring(); import main; main.run()"]
```

### Kubernetes Deployment

For Kubernetes deployments, include the configuration in your deployment YAML:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: row-match-recognize
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: row-match-recognize
        image: row-match-recognize:latest
        env:
        - name: MR_ENABLE_CACHING
          value: "true"
        - name: MR_CACHE_SIZE_LIMIT
          value: "10000"
        - name: MR_CACHE_MEMORY_LIMIT_MB
          value: "500"
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
```

### Serverless Deployment

For serverless environments, initialize the cache at the module level:

```python
import os
from src.utils.pattern_cache import resize_cache, set_caching_enabled

# Configure cache on module initialization
cache_size = int(os.environ.get('MR_CACHE_SIZE_LIMIT', 1000))
enable_caching = os.environ.get('MR_ENABLE_CACHING', 'true').lower() == 'true'

set_caching_enabled(enable_caching)
resize_cache(cache_size)

def handler(event, context):
    # Your serverless handler function
    # ...
```

## 3. Cache Monitoring Setup

### Starting the Monitor

To enable automatic cache monitoring and management:

```python
from src.monitoring.cache_monitor import start_cache_monitoring, stop_cache_monitoring

# At application startup
monitor = start_cache_monitoring()

# At application shutdown
stop_cache_monitoring()
```

### Custom Threshold Callbacks

Register custom callbacks for threshold events:

```python
from src.monitoring.cache_monitor import get_cache_monitor

def memory_threshold_exceeded(stats):
    """Custom callback when memory threshold is exceeded."""
    print(f"Memory usage alert: {stats.get('memory_used_mb')}MB")
    # Send alert to monitoring system
    # ...

# Get the monitor and register callback
monitor = get_cache_monitor()
if monitor:
    monitor.register_threshold_callback(memory_threshold_exceeded)
```

## 4. Monitoring Integration

### Prometheus Integration

Expose cache metrics for Prometheus:

```python
from prometheus_client import Gauge, start_http_server
from src.utils.pattern_cache import get_cache_stats

# Create Prometheus metrics
cache_size = Gauge('pattern_cache_size', 'Number of patterns in cache')
cache_memory = Gauge('pattern_cache_memory_mb', 'Memory used by pattern cache in MB')
cache_efficiency = Gauge('pattern_cache_efficiency', 'Cache hit ratio percentage')
cache_hits = Gauge('pattern_cache_hits', 'Number of cache hits')
cache_misses = Gauge('pattern_cache_misses', 'Number of cache misses')

def update_metrics():
    """Update Prometheus metrics from cache stats."""
    stats = get_cache_stats()
    cache_size.set(stats.get('size', 0))
    cache_memory.set(stats.get('memory_used_mb', 0))
    cache_efficiency.set(stats.get('cache_efficiency', 0))
    cache_hits.set(stats.get('hits', 0))
    cache_misses.set(stats.get('misses', 0))

# Start Prometheus metrics server
start_http_server(8000)

# Schedule regular updates
import threading
def metrics_updater():
    while True:
        update_metrics()
        time.sleep(15)

threading.Thread(target=metrics_updater, daemon=True).start()
```

### CloudWatch Integration (AWS)

Send cache metrics to CloudWatch:

```python
import boto3
from src.utils.pattern_cache import get_cache_stats

cloudwatch = boto3.client('cloudwatch')

def send_metrics_to_cloudwatch():
    """Send cache metrics to CloudWatch."""
    stats = get_cache_stats()
    
    cloudwatch.put_metric_data(
        Namespace='RowMatchRecognize',
        MetricData=[
            {
                'MetricName': 'CacheSize',
                'Value': stats.get('size', 0),
                'Unit': 'Count'
            },
            {
                'MetricName': 'CacheMemoryUsage',
                'Value': stats.get('memory_used_mb', 0),
                'Unit': 'Megabytes'
            },
            {
                'MetricName': 'CacheEfficiency',
                'Value': stats.get('cache_efficiency', 0),
                'Unit': 'Percent'
            }
        ]
    )
```

## 5. Performance Tuning

### Memory vs. Size Tradeoffs

Balance between cache size and memory usage:

| Scenario | Recommended Settings |
|----------|---------------------|
| Memory-constrained | `cache_size_limit=1000`, `cache_memory_limit_mb=200` |
| Balanced | `cache_size_limit=10000`, `cache_memory_limit_mb=500` |
| Performance-focused | `cache_size_limit=50000`, `cache_memory_limit_mb=2000` |

### Pattern Complexity Considerations

Adjust settings based on pattern complexity:

- **Simple patterns**: Can cache more patterns with less memory
- **Complex patterns**: Each pattern requires more memory

```python
# Example configuration for complex patterns
if complex_patterns:
    resize_cache(5000)  # Fewer patterns, but each is larger
else:
    resize_cache(20000)  # More patterns, but each is smaller
```

### Workload-Based Tuning

Tune based on usage patterns:

- **High-diversity workloads** (many unique patterns): Larger cache size
- **Repetitive workloads** (few unique patterns): Smaller cache size with longer TTL

## 6. Production Checklist

- [ ] Set appropriate environment variables for cache configuration
- [ ] Enable cache monitoring in application startup
- [ ] Integrate cache metrics with monitoring system
- [ ] Configure memory limits to prevent OOM conditions
- [ ] Implement graceful degradation if cache memory threshold is exceeded
- [ ] Add alerts for low cache efficiency (< 20%)
- [ ] Schedule periodic cache size optimization based on usage patterns
- [ ] Implement logging for cache-related events
- [ ] Add cache statistics to application health checks

## 7. Troubleshooting

### Common Issues

#### High Memory Usage

**Symptoms**: Increasing memory usage, possible OOM errors
**Solutions**:
- Reduce `cache_size_limit`
- Lower `cache_memory_limit_mb`
- Decrease `cache_ttl_seconds`
- Verify no memory leaks by checking if objects are properly released

#### Low Cache Efficiency

**Symptoms**: Low hit ratio (< 20%)
**Solutions**:
- Clear cache more frequently
- Analyze pattern usage to identify optimization opportunities
- Group similar queries together

#### Thread Safety Issues

**Symptoms**: Intermittent errors, cache corruption
**Solutions**:
- Ensure latest version of caching code
- Add additional logging around cache operations
- Verify proper thread initialization

### Diagnostic Commands

Run the cache benchmark to test performance:

```bash
python examples/pattern_cache_benchmark.py --num-patterns 100 --complexity 2 --iterations 5
```

Clear cache if needed:

```python
from src.utils.pattern_cache import clear_pattern_cache
clear_pattern_cache()
```

## 8. Conclusion

The enhanced pattern caching system provides significant performance improvements for production deployments of the Row_match_recognize project. By following this guide, you can ensure optimal configuration and monitoring of the caching system to meet your production requirements.
