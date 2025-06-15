# MATCH_RECOGNIZE Testing Suite

This project contains a comprehensive testing suite for a pandas-based implementation of SQL MATCH_RECOGNIZE functionality, following the structure and approach in TestRowPatternMatching.java from Trino. The goal is to improve and enhance the existing pandas implementation by ensuring it complies with the SQL:2016 standard and matches Trino's behavior.

## Structure

The testing suite is organized into several components:

- `tests/test_match_recognize.py`: Core tests mirroring Trino's TestRowPatternMatching.java
- `tests/test_pattern_tokenizer.py`: Tests for pattern tokenization functionality
- `tests/test_navigation_and_conditions.py`: Tests for navigation functions and condition evaluation
- `tests/test_sql_parser.py`: Tests for SQL parsing functionality
- `tests/test_sql2016_compliance.py`: Tests specifically for SQL:2016 standard compliance

## Running Tests

### Running All Tests

To run all tests and generate a detailed report:

```bash
./run_tests.py -v -o test_report.txt
```

### Running Specific Tests

To run a specific test file:

```bash
./run_tests.py -f tests/test_match_recognize.py
```

### Generating Test Coverage Report

To analyze the test coverage and identify potential gaps:

```bash
./generate_test_coverage.py -o test_coverage.txt
```

## Features Tested

The test suite covers the following aspects of MATCH_RECOGNIZE:

1. **Pattern Syntax**
   - Pattern concatenation
   - Pattern alternation (`|`)
   - Pattern permutation (`PERMUTE`)
   - Grouping (`()`)
   - Pattern quantifiers (`*`, `+`, `?`, `{n,m}`)
   - Greedy vs. reluctant quantifiers
   - Anchor patterns (`^` and `$`)
   - Exclusion syntax (`{- pattern -}`)

2. **Output Handling**
   - `ONE ROW PER MATCH`
   - `ALL ROWS PER MATCH`
   - `ALL ROWS PER MATCH WITH UNMATCHED ROWS`
   - `ALL ROWS PER MATCH OMIT EMPTY MATCHES`

3. **AFTER MATCH SKIP Modes**
   - `PAST LAST ROW`
   - `TO NEXT ROW`
   - `TO FIRST/LAST <pattern_variable>`

4. **Navigation Functions**
   - `PREV`
   - `NEXT`
   - `FIRST`
   - `LAST`
   - `RUNNING` and `FINAL` semantics

5. **Special Functions**
   - `CLASSIFIER()`
   - `MATCH_NUMBER()`

6. **Other Features**
   - `PARTITION BY` and `ORDER BY`
   - `SUBSET` functionality
   - Pattern variable references
   - Empty matches and cycles

## Trino Reference

The test suite is designed to mirror the behavior of Trino's TestRowPatternMatching.java, ensuring compatibility and standard compliance. The original Java test file is included in the repository for reference.

## Future Work

Areas for potential improvement:

1. Expand tests for edge cases and error conditions
2. Add performance testing for large datasets
3. Add benchmarks to compare with Trino's implementation
4. Create specific test cases for identified bugs or issues

## Contributing

To contribute additional tests:

1. Identify a feature or aspect that needs testing
2. Add a new test method to the appropriate test file
3. Run the tests to verify your changes
4. Submit a pull request with your changes
