# MATCH_RECOGNIZE Test Suite

This directory contains a comprehensive test suite for the pandas-based SQL MATCH_RECOGNIZE implementation. The tests aim to validate compliance with the SQL:2016 standard and compatibility with Trino's implementation.

## Test Structure

The test suite is organized into several files, each focusing on specific aspects of the MATCH_RECOGNIZE functionality:

- `test_match_recognize.py`: Core tests for the match_recognize function, mirroring Trino's TestRowPatternMatching.java
- `test_pattern_tokenizer.py`: Tests for pattern tokenization functionality
- `test_navigation_and_conditions.py`: Tests for navigation functions and condition evaluation
- `test_sql_parser.py`: Tests for SQL parsing functionality

## Running Tests

You can run all tests using the provided `run_tests.py` script:

```bash
./run_tests.py
```

For verbose output:

```bash
./run_tests.py -v
```

To run a specific test file:

```bash
./run_tests.py -f tests/test_match_recognize.py
```

To generate a report:

```bash
./run_tests.py -o test_report.txt
```

## Test Coverage

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

## Adding New Tests

To add new tests:

1. Determine which test file is most appropriate for your test
2. Add a new test method following the existing patterns
3. Ensure your test includes appropriate assertions
4. Run the tests to verify your changes

## Debugging Failed Tests

When a test fails, the test runner will provide detailed output including:
- The test that failed
- The expected output
- The actual output
- Any error messages

Use this information to debug the implementation and fix any issues.
