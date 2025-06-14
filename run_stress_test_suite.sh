#!/usr/bin/env bash
# Row Match Recognize Stress Test Suite Runner
# This script runs a comprehensive suite of stress tests using different configurations

OUTPUT_DIR="stress_test_results"
mkdir -p $OUTPUT_DIR

# Load configuration if available
CONFIG_FILE="stress_test_config.json"
if [ -f "$CONFIG_FILE" ]; then
    echo "Using configuration from $CONFIG_FILE"
else
    echo "Configuration file not found, using defaults"
fi

echo "===================================================="
echo "   Row Match Recognize Comprehensive Stress Test"
echo "===================================================="
echo 

# Enable CPU profiling for the test run
export PYTHONPROFILENABLE=1

# Run the basic stress tests first
echo "Running basic stress tests..."
python -m cProfile -o "$OUTPUT_DIR/basic_profile.prof" run_stress_tests.py --output-dir "$OUTPUT_DIR/basic" --test-type all

# Run the enhanced performance analyzer with specialized tests
echo
echo "Running enhanced performance analyzer tests..."
python -m cProfile -o "$OUTPUT_DIR/enhanced_profile.prof" performance_analyzer.py --output-dir "$OUTPUT_DIR/enhanced" --test-type all --threads 4

# Run specialized cache configuration tests
echo
echo "Running cache optimization tests..."
python performance_analyzer.py --output-dir "$OUTPUT_DIR/cache_optimizations" --test-type memory

# Run specialized concurrency tests with higher thread count
echo
echo "Running concurrency scaling tests..."
python performance_analyzer.py --output-dir "$OUTPUT_DIR/concurrency_scaling" --test-type concurrency --threads 8

# Analyze CPU profiling data
echo
echo "Analyzing CPU profiling data..."
python analyze_profiling.py --profile-data "$OUTPUT_DIR/basic_profile.prof" --output-dir "$OUTPUT_DIR/profiling_analysis"

# Generate consolidated report
echo
echo "Generating consolidated performance report..."

# Create the consolidated directory
REPORT_DIR="$OUTPUT_DIR/consolidated_report"
mkdir -p "$REPORT_DIR/charts"

# Combine charts into a single location
cp "$OUTPUT_DIR/basic/charts/performance_dashboard.png" "$REPORT_DIR/charts/basic_performance_dashboard.png"
cp "$OUTPUT_DIR/enhanced/charts/comprehensive_performance_dashboard.png" "$REPORT_DIR/charts/enhanced_performance_dashboard.png"
cp "$OUTPUT_DIR/cache_optimizations/charts/cache_size_impact.png" "$REPORT_DIR/charts/cache_optimization.png"
cp "$OUTPUT_DIR/concurrency_scaling/charts/concurrency_performance.png" "$REPORT_DIR/charts/concurrency_scaling.png"
cp "$OUTPUT_DIR/profiling_analysis/function_hotspots.png" "$REPORT_DIR/charts/function_hotspots.png"
cp "$OUTPUT_DIR/profiling_analysis/module_hotspots.png" "$REPORT_DIR/charts/module_hotspots.png"

# Generate interactive dashboard
echo
echo "Generating interactive dashboard..."
python generate_interactive_dashboard.py --input-dir "$OUTPUT_DIR" --output-file "$REPORT_DIR/interactive_performance_dashboard.html"

# Combine recommendations
cat > "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md" << EOF
# Row Match Recognize Comprehensive Performance Analysis

## Overview
This report consolidates findings from multiple stress test suites run on the Row Match Recognize implementation.
The analysis covers:

1. **Basic Performance Characteristics**
   - Scaling with data size
   - Pattern complexity impact
   - Memory usage patterns
   
2. **Advanced Performance Analysis**
   - Memory leak detection
   - Concurrency behavior
   - Complex pattern handling
   
3. **Optimization Recommendations**
   - Cache configuration
   - Query execution
   - Resource management

## Key Performance Visualizations

### Basic Performance Dashboard
![Basic Performance Dashboard](./charts/basic_performance_dashboard.png)

### Enhanced Performance Analysis
![Enhanced Performance Dashboard](./charts/enhanced_performance_dashboard.png)

### Cache Optimization Analysis
![Cache Optimization](./charts/cache_optimization.png)

### Concurrency Scaling Analysis
![Concurrency Scaling](./charts/concurrency_scaling.png)

### CPU Profiling Analysis
![Function Hotspots](./charts/function_hotspots.png)

![Module Hotspots](./charts/module_hotspots.png)

## Interactive Dashboard
An interactive dashboard is available in the file: [interactive_performance_dashboard.html](./interactive_performance_dashboard.html)

## Consolidated Recommendations

EOF

# Append recommendations from all test runs
if [ -f "$OUTPUT_DIR/basic/performance_recommendations.txt" ]; then
    echo "### Basic Performance Recommendations" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    cat "$OUTPUT_DIR/basic/performance_recommendations.txt" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
fi

if [ -f "$OUTPUT_DIR/enhanced/recommendations/performance_recommendations.md" ]; then
    echo "### Enhanced Performance Recommendations" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    # Extract just the recommendations, not the header
    sed '1,2d' "$OUTPUT_DIR/enhanced/recommendations/performance_recommendations.md" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
fi

if [ -f "$OUTPUT_DIR/cache_optimizations/recommendations/performance_recommendations.md" ]; then
    echo "### Cache Optimization Recommendations" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    # Extract just the cache section
    sed -n '/## Cache/,/##/p' "$OUTPUT_DIR/cache_optimizations/recommendations/performance_recommendations.md" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
fi

if [ -f "$OUTPUT_DIR/concurrency_scaling/recommendations/performance_recommendations.md" ]; then
    echo "### Concurrency Optimization Recommendations" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    # Extract just the concurrency section
    sed -n '/## Concurrency/,/##/p' "$OUTPUT_DIR/concurrency_scaling/recommendations/performance_recommendations.md" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
fi

if [ -f "$OUTPUT_DIR/profiling_analysis/optimization_recommendations.md" ]; then
    echo "### CPU Profiling Optimization Recommendations" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    # Extract just the recommendations, not the header
    sed '1,2d' "$OUTPUT_DIR/profiling_analysis/optimization_recommendations.md" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
    echo "" >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
fi

# Add conclusion
cat >> "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md" << EOF
## Conclusion and Next Steps

Based on the comprehensive stress testing results, the following actions are recommended to optimize the Row Match Recognize implementation:

1. **Immediate Optimizations:**
   - Implement the cache size configuration based on the optimal values identified
   - Add timeout mechanisms to prevent runaway pattern matching operations
   - Address any memory leaks identified in the testing

2. **Medium-term Improvements:**
   - Refine the pattern matching algorithm to better handle complex patterns
   - Implement pattern complexity analysis to warn about expensive patterns
   - Optimize concurrency handling based on test results

3. **Monitoring Recommendations:**
   - Track memory usage during pattern matching operations
   - Monitor cache hit rates and effectiveness
   - Implement performance logging for pattern matching operations

4. **Architecture Improvements:**
   - Address hotspots identified in the CPU profiling analysis
   - Consider specialized optimizations for common pattern types
   - Implement adaptive runtime optimizations based on pattern characteristics

## Appendix: Test Configuration
- **Basic Tests:** Standard test suite with varying data sizes and pattern types
- **Enhanced Tests:** Specialized tests focusing on memory usage, pattern complexity, and concurrency
- **Cache Tests:** Focused evaluation of different cache configurations
- **Concurrency Tests:** Analysis of behavior under concurrent query execution
- **CPU Profiling:** Analysis of function-level performance bottlenecks
EOF

echo
echo "Stress testing complete! Consolidated report available at:"
echo "$REPORT_DIR/CONSOLIDATED_PERFORMANCE_REPORT.md"
echo
echo "Interactive dashboard available at:"
echo "$REPORT_DIR/interactive_performance_dashboard.html"
echo
