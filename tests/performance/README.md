# MATCH_RECOGNIZE Caching Strategy Performance Testing Suite

This comprehensive performance testing suite evaluates three caching strategies for the pandas MATCH_RECOGNIZE implementation across multiple scenarios and metrics.

## Overview

The test suite implements a factorial design comparing:

### Caching Strategies
- **LRU (Least Recently Used)**: Evicts least recently accessed cache entries
- **FIFO (First In, First Out)**: Evicts oldest cache entries
- **No-Caching**: Baseline with no caching enabled

### Performance Metrics
- **Cache Hit Rate**: Percentage of successful cache retrievals (0-100%)
- **Execution Time**: Total pattern matching time in milliseconds
- **Memory Usage**: Peak memory consumption in megabytes

### Test Scenarios
- **Dataset Sizes**: 1K (1,000 rows), 2K (2,000 rows), 4K (4,000 rows), 5K (5,000 rows)
- **Pattern Complexity**: Simple, Medium, Complex patterns
- **Total Combinations**: 4×3×3 = 36 test cases

## Quick Start

### Basic Usage

```bash
# Run full test suite (may take 10-30 minutes)
python tests/performance/run_performance_tests.py

# Run quick test for CI/CD (2-5 minutes)
python tests/performance/run_performance_tests.py --quick

# Run with custom iterations for higher precision
python tests/performance/run_performance_tests.py --iterations 10
```

### Regression Testing

```bash
# Save current results as baseline
python tests/performance/run_performance_tests.py --baseline

# Check for performance regressions
python tests/performance/run_performance_tests.py --regression-check

# Set custom regression threshold (default: 10%)
python tests/performance/run_performance_tests.py --regression-check --regression-threshold 5.0
```

### Selective Testing

```bash
# Test specific caching strategies
python tests/performance/run_performance_tests.py --strategies LRU FIFO

# Test specific dataset sizes
python tests/performance/run_performance_tests.py --dataset-sizes size_1k size_2k

# Test specific pattern complexities
python tests/performance/run_performance_tests.py --pattern-complexities simple medium
```

## Configuration

The test suite uses `config.yaml` for detailed configuration:

```yaml
# Test execution parameters
execution:
  iterations_per_test: 5
  timeout_seconds: 300
  warmup_iterations: 2

# Dataset configuration
datasets:
  size_1k:
    size: 1000
    patterns_to_test: ["simple", "medium", "complex"]
  size_2k:
    size: 2000
    patterns_to_test: ["simple", "medium", "complex"]
  size_4k:
    size: 4000
    patterns_to_test: ["simple", "medium", "complex"]
  size_5k:
    size: 5000
    patterns_to_test: ["simple", "medium", "complex"]

# Pattern definitions by complexity
patterns:
  simple:
    patterns:
      - "A+"
      - "A B*"
      - "A{2,5}"
  medium:
    patterns:
      - "(A | B)+ C"
      - "START (PROCESS)* END"
  complex:
    patterns:
      - "(A{2,5} | B+)* C D{1,3}"
      - "START (PROCESS{1,3} | PEAK)+ (DECLINE | STABLE)* END"
```

## Output Files

The test suite generates comprehensive results in `tests/performance/results/`:

### Core Results
- `performance_summary.json`: Aggregated performance statistics and recommendations
- `detailed_performance_results.csv`: Raw data for all test cases
- `performance_test.log`: Detailed execution log

### Visualizations
- `performance_comparison_charts.png`: Overview comparison charts
- `performance_by_dataset_size.png`: Performance breakdown by dataset size
- `performance_by_pattern_complexity.png`: Performance breakdown by pattern complexity

### Regression Testing
- `baseline_results.json`: Baseline performance data for regression detection

## Understanding Results

### Performance Summary

The summary report includes:

```json
{
  "test_summary": {
    "total_test_cases": 36,
    "strategies_tested": 3,
    "dataset_sizes": 4,
    "pattern_complexities": 3
  },
  "strategy_performance": {
    "LRU": {
      "avg_execution_time_ms": 125.3,
      "avg_memory_usage_mb": 45.2,
      "avg_cache_hit_rate": 78.5
    }
  },
  "best_strategies": {
    "execution_time": "LRU",
    "memory_usage": "FIFO", 
    "cache_hit_rate": "LRU"
  },
  "recommendations": {
    "overall_best": "LRU provides the best overall performance balance",
    "execution_speed": "For fastest execution, use LRU",
    "memory_efficiency": "For lowest memory usage, use FIFO"
  }
}
```

### Interpreting Charts

1. **Box Plots**: Show distribution of performance metrics across test cases
2. **Bar Charts**: Compare average performance by dataset size and pattern complexity
3. **Heatmaps**: Visualize performance patterns across different scenario combinations

### Statistical Analysis

The suite provides:
- **Mean and Standard Deviation**: Central tendency and variability
- **Confidence Intervals**: Statistical significance of differences
- **Regression Detection**: Automated detection of performance degradation

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Performance Tests
on: [push, pull_request]

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r tests/performance/requirements.txt
      - name: Run performance tests
        run: |
          python tests/performance/run_performance_tests.py --quick --regression-check
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: performance-results
          path: tests/performance/results/
```

### Performance Requirements

```bash
# Install additional dependencies for performance testing
pip install psutil matplotlib seaborn pyyaml
```

## Advanced Usage

### Custom Pattern Testing

Add custom patterns to `config.yaml`:

```yaml
patterns:
  custom:
    description: "Custom business logic patterns"
    patterns:
      - "ORDER (PROCESS | CANCEL)+ COMPLETE"
      - "LOGIN (ACTIVITY{1,5})* LOGOUT"
```

### Memory Profiling

For detailed memory analysis:

```bash
# Enable verbose logging for memory tracking
python tests/performance/run_performance_tests.py --verbose
```

### Benchmark Comparison

Compare against previous versions:

```bash
# Save current version as baseline
git checkout main
python tests/performance/run_performance_tests.py --baseline

# Test new version
git checkout feature-branch
python tests/performance/run_performance_tests.py --regression-check
```

## Troubleshooting

### Common Issues

1. **Out of Memory**: Reduce dataset sizes or use `--quick` mode
2. **Long Execution Time**: Use fewer iterations or selective testing
3. **Import Errors**: Ensure all dependencies are installed

### Performance Tips

- Run tests on dedicated hardware for consistent results
- Close other applications to minimize interference
- Use SSD storage for better I/O performance
- Consider running multiple iterations for statistical significance

## Contributing

When adding new caching strategies or test scenarios:

1. Update `CachingStrategy` enum in `test_caching_strategies.py`
2. Add configuration in `config.yaml`
3. Update pattern definitions if needed
4. Run full test suite to establish new baseline
5. Update documentation

## License

This performance testing suite is part of the pandas MATCH_RECOGNIZE implementation and follows the same license terms.
