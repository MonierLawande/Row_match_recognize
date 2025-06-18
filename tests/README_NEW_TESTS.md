# MATCH_RECOGNIZE Test Suite - Java Reference Implementation Coverage

This directory contains comprehensive tests that validate the Python MATCH_RECOGNIZE implementation against Trino's Java `TestRowPatternMatching.java` reference.

## 🆕 New Test Files Created

### Core Missing Functionality Tests

| Java Method | Python Test File | Status | Priority |
|-------------|------------------|--------|----------|
| `testCaseSensitiveLabels` | `test_case_sensitivity.py` | 🆕 NEW | HIGH |
| `testScalarFunctions` | `test_scalar_functions.py` | 🆕 NEW | HIGH |
| `testOutputLayout` | `test_output_layout.py` | 🆕 NEW | HIGH |
| `testMultipleMatchRecognize` | `test_multiple_match_recognize.py` | 🆕 NEW | MEDIUM |
| `testSubqueries` | `test_subqueries.py` | 🆕 NEW | MEDIUM |
| `testInPredicateWithoutSubquery` | `test_in_predicate.py` | 🆕 NEW | HIGH |
| `testPotentiallyExponentialMatch` | `test_exponential_protection.py` | 🆕 NEW | 🚨 CRITICAL |
| `testExponentialMatch` | `test_exponential_protection.py` | 🆕 NEW | 🚨 CRITICAL |

## 🎯 Test File Descriptions

### `test_case_sensitivity.py` 
**Tests case-sensitive pattern variable handling**
- Pattern variables: `(a b+ C+)` → should produce labels `['A', 'b', 'b', 'C']`
- Quoted identifiers: `"b"` preserves exact case
- Mixed case handling and SQL keyword case insensitivity

### `test_scalar_functions.py`
**Tests scalar functions in MEASURES and DEFINE clauses**
- String functions: `CONCAT()`, `UPPER()`, `LENGTH()`
- Arithmetic: `+`, `-`, `*`, `/`, `ABS()`
- Conditional: `CASE WHEN ... THEN ... ELSE`
- Type conversion: `CAST(value AS VARCHAR)`

### `test_output_layout.py`
**Tests column ordering and layout**
- Required order: `[partition_columns, order_columns, measures, original_columns]`
- Duplicate column handling
- Column aliasing and selection

### `test_multiple_match_recognize.py`
**Tests nested and multiple MATCH_RECOGNIZE clauses**
- Nested queries: `SELECT ... FROM (... MATCH_RECOGNIZE ...) MATCH_RECOGNIZE ...`
- Multiple MATCH_RECOGNIZE in same query level
- UNION with MATCH_RECOGNIZE

### `test_subqueries.py`
**Tests subqueries in DEFINE and MEASURES**
- DEFINE subqueries: `B AS B.value > (SELECT AVG(value) FROM ref WHERE cat = B.cat)`
- MEASURES subqueries: `(SELECT COUNT(*) FROM reference) AS ref_count`
- Correlated subqueries and EXISTS patterns

### `test_in_predicate.py`
**Tests IN predicate functionality**
- String literals: `A.category IN ('high', 'medium', 'low')`
- Numeric literals: `A.value IN (90, 85, 80)`
- Function results: `CLASSIFIER() IN ('A', 'START')`
- NOT IN predicate and NULL handling

### `test_exponential_protection.py` 🚨 **CRITICAL**
**Tests protection against exponential pattern complexity**
- Exponential patterns: `((A+)+ B)` that could cause infinite loops
- Performance limits: All patterns must complete in <5 seconds
- Memory protection: Prevent exponential memory usage
- Backtracking complexity limits

## 🚀 Running the Tests

### Full Validation Suite
```bash
# Run comprehensive validation
python validate_test_coverage.py --verbose

# Output: Detailed report comparing Python vs Java behavior
```

### Individual Test Categories
```bash
# Case sensitivity
pytest tests/test_case_sensitivity.py -v

# Scalar functions  
pytest tests/test_scalar_functions.py -v

# Exponential protection (CRITICAL)
pytest tests/test_exponential_protection.py -v

# Output layout
pytest tests/test_output_layout.py -v

# IN predicate
pytest tests/test_in_predicate.py -v

# Subqueries
pytest tests/test_subqueries.py -v

# Multiple MATCH_RECOGNIZE
pytest tests/test_multiple_match_recognize.py -v
```

## 📊 Expected Test Results

Currently, most new tests will **FAIL** or **SKIP** because the features are not yet implemented. This is expected and correct behavior.

### Example Test Output:
```
test_case_sensitivity.py::test_case_sensitive_labels_basic FAILED
# Expected: ['A', 'b', 'b', 'C'] 
# Actual:   ['a', 'b', 'b', 'C']
# Issue: Case conversion not implemented

test_exponential_protection.py::test_potentially_exponential_pattern_basic FAILED  
# Issue: Pattern ((A+)+ B) needs optimization to prevent hanging
```

## 🎯 Implementation Priority

### 🚨 CRITICAL - Implement Immediately
1. **Exponential Pattern Protection** (`test_exponential_protection.py`)
   - **Risk:** System can hang on complex patterns
   - **Solution:** Implement equivalent state detection

### ⚠️ HIGH PRIORITY  
2. **Case Sensitivity** (`test_case_sensitivity.py`)
   - **Issue:** Pattern variables not normalized correctly
   
3. **Scalar Functions** (`test_scalar_functions.py`)
   - **Issue:** No support for CONCAT, UPPER, arithmetic in MEASURES/DEFINE

4. **Column Layout** (`test_output_layout.py`)
   - **Issue:** Column ordering doesn't match Trino spec

5. **IN Predicate** (`test_in_predicate.py`)
   - **Issue:** No support for `A.cat IN ('high', 'low')`

## 📋 Test Data Standards

All tests use data that matches the Java reference exactly:

```python
# Primary test data from Java testSimpleQuery()
simple_data = pd.DataFrame({
    'id': [1, 2, 3, 4, 5, 6, 7, 8],
    'value': [90, 80, 70, 80, 90, 50, 40, 60]
})

# Basic test data from Java testRowPattern()  
basic_data = pd.DataFrame({
    'id': [1, 2, 3, 4],
    'value': [90, 80, 70, 70]
})
```

## 🔧 Test Infrastructure

### `validate_test_coverage.py`
Comprehensive validation script that:
- Maps all Java test methods to Python implementations
- Runs tests with timeout protection (30s per test)
- Generates detailed coverage reports
- Identifies missing functionality gaps

### Coverage Report Output
- **Implementation Coverage:** Percentage of Python tests passing
- **Java Reference Coverage:** Percentage of Java methods covered
- **Priority Recommendations:** Critical/High/Medium priority fixes
- **Detailed Breakdown:** Status of each test method

## 📈 Success Metrics

- **Test Coverage:** 100% of Java methods have Python equivalents ✅
- **Behavioral Accuracy:** Python output matches Java exactly
- **Performance Safety:** No pattern hangs system (exponential protection)
- **Production Readiness:** All critical features implemented and tested

## 🎯 Next Steps

1. **Implement exponential protection** (security critical)
2. **Fix case sensitivity** for pattern variables  
3. **Add scalar function support** in parser/evaluator
4. **Standardize column ordering** in output formatter
5. **Add IN predicate parsing** in condition evaluator

Each implementation should be validated against the corresponding test file to ensure exact Trino behavioral matching.
