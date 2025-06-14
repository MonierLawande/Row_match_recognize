# Row Match Recognize Stress Testing System

This comprehensive stress testing system evaluates the performance characteristics of the Row Match Recognize SQL pattern matching implementation. The system generates synthetic test data, executes various pattern matching scenarios, and produces detailed visualizations and recommendations.

## Features

- **Data Generation**: Creates synthetic time series data with controllable characteristics
- **Performance Scaling**: Tests how the system scales with increasing data sizes
- **Pattern Complexity**: Evaluates impact of different pattern types on performance
- **Memory Usage**: Monitors memory consumption during matching operations
- **Cache Efficiency**: Analyzes effectiveness of pattern caching mechanisms
- **Partition Scaling**: Measures performance with varying numbers of partitions
- **Concurrency Testing**: Evaluates behavior under parallel execution
- **CPU Profiling**: Identifies performance hotspots at function level
- **Interactive Dashboards**: Generates web-based interactive visualizations

## Getting Started

### Prerequisites

- Python 3.6+
- Required Python packages (install with `pip install -r requirements.txt`):
  - pandas
  - numpy
  - matplotlib
  - seaborn
  - plotly
  - psutil

### Configuration

Adjust the testing parameters in `stress_test_config.json`:

```json
{
  "testing": {
    "data_sizes": [100, 500, 1000, 5000, 10000, 20000],
    "partition_counts": [1, 5, 10, 50, 100, 500],
    "cache_sizes": [0, 100, 1000, 10000],
    "pattern_complexities": ["simple", "medium", "complex"],
    "thread_counts": [1, 2, 4, 8],
    "memory_leak_iterations": 10
  },
  "visualization": {
    "color_palette": "viridis",
    "chart_style": "ggplot",
    "dpi": 300,
    "dashboard_size": [24, 18],
    "include_annotations": true
  },
  ...
}
```

### Running Tests

#### Complete Test Suite

To run the complete stress test suite:

```bash
./run_stress_test_suite.sh
```

This will:
1. Run basic scaling tests
2. Run enhanced memory and concurrency tests
3. Analyze CPU profiling data
4. Generate a consolidated performance report
5. Create an interactive dashboard

#### Individual Testing Components

Run specific tests:

1. Basic scaling tests:
   ```bash
   python run_stress_tests.py --output-dir stress_test_results/basic --test-type all
   ```

2. Enhanced performance analyzer:
   ```bash
   python performance_analyzer.py --output-dir stress_test_results/enhanced --test-type all --threads 4
   ```

3. CPU profiling analysis:
   ```bash
   python analyze_profiling.py --profile-data profile_data.prof --output-dir profiling_analysis
   ```

4. Generate interactive dashboard:
   ```bash
   python generate_interactive_dashboard.py --input-dir stress_test_results --output-file dashboard.html
   ```

## Understanding Results

### Test Output Structure

```
stress_test_results/
├── basic/
│   ├── charts/
│   ├── data/
│   └── performance_recommendations.txt
├── enhanced/
│   ├── charts/
│   ├── data/
│   └── recommendations/
├── cache_optimizations/
│   ├── charts/
│   ├── data/
│   └── recommendations/
├── concurrency_scaling/
│   ├── charts/
│   ├── data/
│   └── recommendations/
├── profiling_analysis/
│   ├── function_hotspots.png
│   ├── module_hotspots.png
│   └── optimization_recommendations.md
└── consolidated_report/
    ├── charts/
    ├── CONSOLIDATED_PERFORMANCE_REPORT.md
    └── interactive_performance_dashboard.html
```

### Key Visualizations

1. **Performance Scaling Dashboard**: Shows how execution time and memory usage scale with data size
2. **Pattern Complexity Analysis**: Compares performance across different pattern types
3. **Cache Efficiency Analysis**: Evaluates the effectiveness of pattern caching
4. **Partition Scaling Analysis**: Shows how performance scales with number of partitions
5. **Function Hotspots**: Identifies CPU-intensive functions from profiling data
6. **Interactive Dashboard**: Web-based dashboard for exploring all performance metrics

### Optimization Recommendations

The system generates performance recommendations in several categories:

1. **Memory Management**: Identifies potential memory leaks and optimization opportunities
2. **Cache Configuration**: Recommends optimal cache settings
3. **Concurrency Handling**: Suggests improvements for parallel execution
4. **Pattern Complexity**: Identifies problematic pattern types
5. **CPU Hotspots**: Recommends optimizations for CPU-intensive functions

## Extending the System

### Adding New Tests

To add a new test type:

1. Create a new test function in `performance_analyzer.py`
2. Update the argument parser to include your new test type
3. Add your test to the main function's execution flow

### Adding New Visualizations

To add new visualizations:

1. Create a visualization function in the appropriate script
2. Ensure it saves output to the charts directory
3. Update the dashboard generation code to include your visualization

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- This stress testing system was developed to evaluate and improve the Row Match Recognize implementation
- Inspired by database benchmarking methodologies and visualization best practices
