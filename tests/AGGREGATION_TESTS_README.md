# Aggregation Testing Suite for Row Pattern Matching

This directory contains comprehensive test cases for validating aggregation functionality in the pandas-based row pattern matching implementation. The tests are designed to ensure production-ready quality and SQL:2016 compliance.

## 📁 Test Files Structure

```
tests/
├── test_production_aggregations.py      # Comprehensive aggregation test cases (converted from Java)
├── test_advanced_aggregation_scenarios.py  # Advanced integration and edge case tests
├── test_aggregation_performance.py      # Performance and benchmark tests
├── test_aggregation_integration.py      # Integration tests with current implementation
├── test_utils.py                       # Test utilities and mock functions
├── pytest.ini                         # Pytest configuration
└── AGGREGATION_TESTS_README.md         # This file
```

## 🚀 Quick Start

### Running Basic Tests
```bash
# Run all integration tests
python -m pytest tests/test_aggregation_integration.py -v

# Run specific test categories
python -m pytest tests/ -m "integration" -v
python -m pytest tests/ -m "unit" -v
```

### Using the Test Runner
```bash
# Run all aggregation tests
python run_aggregation_tests.py

# Run specific test types
python run_aggregation_tests.py --test-type integration
python run_aggregation_tests.py --test-type performance

# Include slow tests
python run_aggregation_tests.py --slow

# Generate coverage report
python run_aggregation_tests.py --coverage
```

## 📋 Test Categories

### 1. Production Aggregation Tests (`test_production_aggregations.py`)
**Converted from Java test cases to ensure Trino compatibility**

- ✅ **Advanced Statistical Aggregations**: STDDEV, VARIANCE, geometric means
- ✅ **Conditional Aggregations**: COUNT_IF, SUM_IF, AVG_IF functions  
- ✅ **Array/String Aggregations**: ARRAY_AGG, STRING_AGG with ordering
- ✅ **Specialized Aggregations**: MIN_BY, MAX_BY, APPROX_DISTINCT
- ✅ **Navigation Integration**: Complex FIRST, LAST, PREV, NEXT combinations
- ✅ **Subset Variables**: Aggregations with pattern variable subsets
- ✅ **NULL Handling**: Comprehensive NULL value processing
- ✅ **Percentiles**: Quantile and percentile functions

### 2. Advanced Scenario Tests (`test_advanced_aggregation_scenarios.py`)
**Complex integration and real-world scenarios**

- 🔄 **Navigation Integration**: Deep FIRST/LAST/PREV/NEXT combinations
- 🏷️ **CLASSIFIER Functions**: Integration with MATCH_NUMBER
- 🔀 **PERMUTE Patterns**: Aggregations with permutation patterns  
- 🪟 **Window Functions**: Window function style behavior
- 🎯 **Complex Filtering**: Advanced FILTER clauses
- 📊 **Real-world Scenarios**: Financial and sensor data patterns

### 3. Performance Tests (`test_aggregation_performance.py`)
**Scalability and performance validation**

- ⚡ **Large Dataset Performance**: Up to 50K+ rows
- 💾 **Memory Efficiency**: Memory usage monitoring
- 🚀 **Concurrent Patterns**: Multiple partition performance  
- 🗄️ **Cache Effectiveness**: Pattern compilation caching
- 🔥 **Stress Testing**: Production workload simulation
- 📈 **Benchmark Suite**: Standard aggregation benchmarks

### 4. Integration Tests (`test_aggregation_integration.py`)
**Works with current implementation**

- 🔧 **Basic Functionality**: SUM, AVG, COUNT validation
- 🧩 **Pattern Integration**: Aggregations with pattern matching
- 🚫 **NULL Handling**: NULL value processing
- 📊 **Partitioned Data**: PARTITION BY functionality
- 🎲 **Real Data**: Financial, sensor, categorical scenarios

## 🧪 Test Data Generators

The `test_utils.py` module provides data generators for various scenarios:

```python
from test_utils import test_data_generator

# Simple numeric data
df = test_data_generator.create_simple_numeric_data(10)

# Financial data with price trends
df = test_data_generator.create_financial_data(20)

# Sensor data with confidence scores  
df = test_data_generator.create_sensor_data(15)

# Categorical data for pattern testing
df = test_data_generator.create_categorical_data(10)

# Data with NULL values
df = test_data_generator.create_null_data(10)
```

## 🎯 Test Markers

Use pytest markers to run specific test categories:

```bash
# Run only fast tests (exclude slow ones)
pytest -m "not slow"

# Run performance tests only
pytest -m "performance"

# Run integration tests
pytest -m "integration"

# Run unit tests  
pytest -m "unit"

# Run production validation tests
pytest -m "production"
```

## 📊 Coverage and Reporting

### Generate Coverage Report
```bash
python run_aggregation_tests.py --coverage
```

This generates:
- HTML report: `htmlcov/index.html`
- Terminal summary
- XML report for CI/CD

### Performance Monitoring
```bash
# Enable stress tests
RUN_STRESS_TESTS=1 python run_aggregation_tests.py --test-type performance
```

## 🔧 Configuration

### Environment Variables
- `RUN_STRESS_TESTS=1`: Enable stress testing with large datasets
- `PYTEST_CURRENT_TEST`: Used internally by pytest

### Pytest Configuration (`pytest.ini`)
- Test discovery patterns
- Marker definitions  
- Output formatting
- Timeout settings

## 🛠️ Development Workflow

### Adding New Tests
1. **Identify Test Category**: Choose appropriate test file
2. **Create Test Method**: Follow naming convention `test_*`
3. **Use Test Utilities**: Leverage `test_utils.py` helpers
4. **Add Markers**: Tag with appropriate pytest markers
5. **Validate Structure**: Ensure proper assertions and error handling

### Test Data Strategy
```python
# Use consistent test data
df = test_data_generator.create_simple_numeric_data(5)

# Validate results structure
assert test_validator.validate_dataframe_structure(result, expected_columns)

# Check aggregation patterns
assert test_validator.validate_aggregation_results(result, "running_sum", "increasing")
```

## 🎯 Production Validation Checklist

✅ **Functional Correctness**
- [ ] All standard SQL aggregation functions
- [ ] RUNNING vs FINAL semantics
- [ ] Navigation function integration
- [ ] Pattern variable support
- [ ] Subset variable handling

✅ **Data Quality**  
- [ ] NULL value handling
- [ ] Type coercion and preservation
- [ ] Edge case handling
- [ ] Boundary condition validation

✅ **Performance**
- [ ] Large dataset handling (10K+ rows)
- [ ] Memory efficiency 
- [ ] Pattern compilation caching
- [ ] Concurrent partition processing

✅ **Compatibility**
- [ ] Trino/SQL:2016 compliance
- [ ] Pandas integration
- [ ] Error handling consistency
- [ ] Output format matching

## 🚨 Troubleshooting

### Import Errors
If you encounter import errors:
```python
# The tests include fallback implementations
# Check that your project structure matches expected paths
```

### Mock vs Real Implementation
```python
# Tests automatically detect implementation availability
# Use IMPLEMENTATION_AVAILABLE flag to check status
```

### Performance Issues
```bash
# Run with smaller datasets first
pytest tests/test_aggregation_integration.py -v

# Then scale up to performance tests
pytest tests/test_aggregation_performance.py -v -m "not slow"
```

## 📈 Next Steps

1. **Run Integration Tests**: Start with `test_aggregation_integration.py`
2. **Implement Missing Functions**: Use test failures to guide development
3. **Performance Optimization**: Use benchmark results to identify bottlenecks  
4. **Add Custom Tests**: Create project-specific test scenarios
5. **CI/CD Integration**: Add tests to your continuous integration pipeline

## 🤝 Contributing

When adding new aggregation functionality:

1. **Add Tests First**: Write failing tests for new features
2. **Implement Functionality**: Make tests pass
3. **Performance Testing**: Ensure new features scale
4. **Documentation**: Update test documentation
5. **Validation**: Run full test suite

---

These tests provide comprehensive validation for your row pattern matching aggregation implementation, ensuring production-ready quality and SQL:2016 compliance. Start with the integration tests and gradually expand to the full suite as your implementation matures.
