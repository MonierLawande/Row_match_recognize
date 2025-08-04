# Production Debugging Guide for Row Match Recognize

## Overview

This guide provides comprehensive debugging capabilities for troubleshooting Row Match Recognize in production environments. The debugging system is designed to be safe, configurable, and non-intrusive while providing deep insights into system behavior.

## Quick Start

### 1. Enable Basic Debugging

```bash
# Set environment variables
export ROW_MATCH_DEBUG_ENABLED=true
export ROW_MATCH_DEBUG_LEVEL=standard
export ROW_MATCH_DEBUG_SCOPE=all
```

```python
# In your Python code
from src.utils.debug_config import safe_debug_log, safe_performance_log

# Log debug information safely
safe_debug_log("Query execution started", query_id="q123", data_rows=1000)

# Log performance metrics
safe_performance_log("pattern_matching", duration_ms=250.5, matches_found=42)
```

### 2. Use CLI Tool for Troubleshooting

```bash
# Check current debugging status
python debug_tool.py status

# Enable debugging temporarily
python debug_tool.py enable --level verbose

# Generate comprehensive debug report
python debug_tool.py report --output production_debug.json

# Analyze recent performance
python debug_tool.py performance --hours 2

# Check for errors
python debug_tool.py errors --count 20
```

## Debugging Levels

### DISABLED
- No debugging information collected
- Minimal performance impact
- **Use in production by default**

### MINIMAL
- Error logging only
- Basic performance metrics
- Security events
- **Safe for production**

### STANDARD
- Info, warning, and error logging
- Query execution tracking
- Performance monitoring
- Cache statistics
- **Recommended for staging**

### VERBOSE
- Debug level logging
- Detailed execution stages
- Function call tracking
- Memory and CPU monitoring
- **Use for development/troubleshooting**

### TRACE
- Full function tracing
- Complete state capture
- Maximum detail
- **Heavy performance impact - debug only**

## Debugging Scopes

### ALL
- Debug all components
- Complete system visibility

### PARSER
- SQL parsing and AST generation
- Query validation
- Pattern extraction

### MATCHER
- Pattern matching engine
- Automata construction and execution
- Match finding algorithms

### EXECUTOR
- Query execution coordination
- Result processing
- Integration components

### PERFORMANCE
- Performance metrics only
- Memory and CPU monitoring
- Cache statistics

### ERRORS
- Error conditions only
- Exception handling
- Failure analysis

## Environment Variables

| Variable | Description | Default | Examples |
|----------|-------------|---------|----------|
| `ROW_MATCH_DEBUG_ENABLED` | Enable/disable debugging | `false` | `true`, `false` |
| `ROW_MATCH_DEBUG_LEVEL` | Debug detail level | `minimal` | `disabled`, `minimal`, `standard`, `verbose`, `trace` |
| `ROW_MATCH_DEBUG_SCOPE` | Component scope | `all` | `all`, `parser`, `matcher`, `executor`, `performance`, `errors` |
| `ROW_MATCH_DEBUG_MAX_FRAMES` | Max debug frames to keep | `1000` | `500`, `2000` |
| `ROW_MATCH_DEBUG_MAX_QUERIES` | Max query debug info | `100` | `50`, `200` |
| `ROW_MATCH_DEBUG_TRACER` | Enable Python tracer | `false` | `true`, `false` |
| `ROW_MATCH_DEBUG_OUTPUT_DIR` | Debug output directory | `debug_output` | `/var/log/debug`, `./logs` |
| `ROW_MATCH_DEBUG_PERF_THRESHOLD` | Performance alert threshold (ms) | `100.0` | `50.0`, `500.0` |
| `ROW_MATCH_DEBUG_SENSITIVE` | Capture sensitive data | `false` | `true`, `false` |
| `ROW_MATCH_ENVIRONMENT` | Environment name | `production` | `development`, `staging`, `production` |

## Production Safety Features

### 1. Non-Intrusive Design
- Debugging never blocks main execution
- Automatic fallback on debugging failures
- Performance impact minimization

### 2. Data Security
- Sensitive data masking by default
- Configurable data capture limits
- Anonymous data collection options

### 3. Resource Management
- Automatic cleanup of old debug data
- Memory usage limits
- CPU impact monitoring

### 4. Error Isolation
- Debugging errors never crash the application
- Safe exception handling
- Graceful degradation

## CLI Tool Reference

### Status Commands

```bash
# Show current debugging status
python debug_tool.py status

# Output example:
# {
#   "enabled": true,
#   "level": "standard",
#   "scope": "all",
#   "environment": "production",
#   "performance_threshold_ms": 100.0
# }
```

### Control Commands

```bash
# Enable debugging
python debug_tool.py enable --level standard --scope matcher

# Disable debugging
python debug_tool.py disable
```

### Analysis Commands

```bash
# Generate comprehensive report
python debug_tool.py report --output debug_report.json

# Analyze performance trends
python debug_tool.py performance --hours 6

# Check query performance
python debug_tool.py query-performance --query-id q123

# Diagnose errors
python debug_tool.py errors --count 25
```

### Testing Commands

```bash
# Test query with debugging
python debug_tool.py test-query "SELECT ..." test_data.csv
```

## Programming Interface

### Safe Logging Functions

```python
from src.utils.debug_config import safe_debug_log, safe_performance_log

# Safe debug logging (never throws exceptions)
safe_debug_log(
    "Pattern compilation started",
    pattern="A+ B* C+",
    complexity="moderate",
    level="DEBUG"  # Optional, defaults to DEBUG
)

# Safe performance logging
safe_performance_log(
    "dfa_construction",
    duration_ms=45.2,
    nfa_states=25,
    dfa_states=12,
    optimization_ratio=0.48
)
```

### Debug Context Managers

```python
from src.utils.debug_manager import debug_query

# Query-level debugging
with debug_query(sql_query, dataframe) as query_info:
    result = match_recognize(sql_query, dataframe)
    
    # query_info is automatically populated with:
    # - Execution stages and timing
    # - Automata construction info
    # - Performance metrics
    # - Error information
```

### Function Decorators

```python
from src.utils.debug_integration import debug_function, monitor_performance

# Add debugging to any function
@debug_function(location="custom.my_function", capture_args=True)
def my_function(data, pattern):
    # Function implementation
    pass

# Monitor performance with threshold
@monitor_performance(threshold_ms=50.0)
def performance_critical_function():
    # Function implementation
    pass
```

## Debug Report Structure

Debug reports contain comprehensive system information:

```json
{
  "report_metadata": {
    "generated_at": "2025-08-04T10:30:00",
    "debug_enabled": true,
    "environment": "production"
  },
  "summary": {
    "total_frames": 1000,
    "total_queries": 25,
    "recent_errors": 3
  },
  "recent_activity": {
    "frames": [...],
    "queries": {...},
    "performance": [...]
  },
  "analysis": {
    "most_active_functions": {...},
    "error_patterns": {...},
    "performance_trends": {...}
  }
}
```

## Performance Analysis

### Query Performance Metrics

- **Execution time breakdown** by stage
- **Automata construction time** (NFA/DFA)
- **Pattern matching time**
- **Result processing time**
- **Memory usage** during execution

### System Performance Trends

- **Memory usage over time**
- **CPU utilization patterns**
- **Cache hit rates**
- **Query throughput**

### Performance Alerts

Automatic alerts for:
- Queries exceeding time thresholds
- Memory usage spikes
- High CPU utilization
- Cache performance degradation

## Error Diagnosis

### Error Categories

1. **Parsing Errors**: SQL syntax, pattern syntax
2. **Validation Errors**: Data type mismatches, invalid patterns
3. **Execution Errors**: Runtime failures, resource exhaustion
4. **Performance Errors**: Timeouts, memory limits

### Error Analysis Features

- **Pattern recognition** in error messages
- **Frequency analysis** of error types
- **Correlation** with query complexity
- **Trend analysis** over time

## Troubleshooting Common Issues

### High Memory Usage

```bash
# Check memory trends
python debug_tool.py performance --hours 4

# Look for memory leaks in report
python debug_tool.py report --output memory_analysis.json
```

**Solutions:**
- Reduce cache sizes
- Implement query result limits
- Check for data frame memory leaks

### Slow Query Performance

```bash
# Analyze query performance
python debug_tool.py query-performance

# Enable verbose debugging for specific queries
export ROW_MATCH_DEBUG_LEVEL=verbose
export ROW_MATCH_DEBUG_SCOPE=matcher
```

**Solutions:**
- Optimize pattern complexity
- Add data filtering
- Increase cache sizes
- Review automata construction

### Frequent Errors

```bash
# Diagnose error patterns
python debug_tool.py errors --count 50

# Enable error-focused debugging
export ROW_MATCH_DEBUG_SCOPE=errors
export ROW_MATCH_DEBUG_ON_ERROR=true
```

**Solutions:**
- Fix common pattern syntax errors
- Add input validation
- Improve error messages
- Update documentation

## Best Practices

### Development
- Use `VERBOSE` level with full scope
- Enable function tracing for complex debugging
- Capture sensitive data for complete analysis

### Testing
- Use `STANDARD` level with specific scopes
- Enable performance monitoring
- Test with realistic data sizes

### Staging
- Use `MINIMAL` level with error focus
- Monitor performance trends
- Validate production configurations

### Production
- Keep debugging `DISABLED` by default
- Enable temporarily for troubleshooting
- Use CLI tool for real-time analysis
- Generate reports for post-incident analysis

### Emergency Debugging

For production emergencies:

```bash
# Quick enable with minimal impact
export ROW_MATCH_DEBUG_ENABLED=true
export ROW_MATCH_DEBUG_LEVEL=minimal
export ROW_MATCH_DEBUG_SCOPE=errors

# Generate immediate report
python debug_tool.py report --output emergency_$(date +%Y%m%d_%H%M%S).json

# Check recent performance
python debug_tool.py performance --hours 1

# Disable after troubleshooting
export ROW_MATCH_DEBUG_ENABLED=false
```

## Security Considerations

### Data Protection
- Sensitive data is masked by default
- Configurable data capture limits
- Option to disable data capture entirely

### Access Control
- Debug outputs should be restricted
- CLI tool requires appropriate permissions
- Log files should be secured

### Privacy Compliance
- Anonymous mode available
- Data retention controls
- Audit trail for debug access

## Integration Examples

### With Monitoring Systems

```python
# Send debug metrics to monitoring system
def send_to_monitoring(metrics):
    # Integration with your monitoring system
    pass

# Custom performance callback
safe_performance_log(
    "query_execution",
    duration_ms=execution_time,
    callback=send_to_monitoring
)
```

### With Alerting Systems

```python
# Custom error handler for alerts
def handle_critical_error(error_info):
    # Send to alerting system
    pass

# Register error handler
debug_manager = get_debug_manager()
debug_manager.add_watch("critical_errors", handle_critical_error)
```

This debugging system provides comprehensive troubleshooting capabilities while maintaining production safety and performance. Use it to quickly identify and resolve issues in your Row Match Recognize deployment.
