# Row Pattern Matching Navigation Function Fix

This repository contains a fix for the `PREV` and `NEXT` navigation functions in the row pattern matching library. The fix enables correct pattern matching with queries that use these navigation functions.

## Problem Overview

The pattern matching engine had an issue with navigation functions like `PREV` and `NEXT`. For example, patterns like:

```sql
DEFINE
    DOWN AS price < PREV(price),
    UP AS price > PREV(price)
```

Weren't finding matches in data that should clearly have matching patterns.

## Fix Implementation

The fix introduces a simplified `evaluate_navigation_function` method that:

1. Uses direct row index arithmetic (current_idx - steps for PREV, current_idx + steps for NEXT)
2. Properly handles edge cases (index bounds, partition boundaries)
3. Eliminates the complexity of the original timeline-based implementation

The fix has been permanently applied to the `src/matcher/condition_evaluator.py` file.

## Testing the Fix

Several test scripts and notebooks are available to verify the fix:

### Test Scripts

- `test_navigation_functions.py`: Automated test suite for navigation functions
- `validate_navigation_realworld.py`: Real-world validation of navigation functions
- `run_navigation_tests.py`: Script to run all test notebooks and collect results

Run the test scripts:

```bash
python3 test_navigation_functions.py
python3 validate_navigation_realworld.py
python3 run_navigation_tests.py
```

### Test Notebooks

- `Navigation_Function_Debug.ipynb`: Diagnostic notebook used to identify the issue
- `Navigation_Function_Comprehensive_Tests.ipynb`: Comprehensive tests for the fix
- `Query_Validation_Test.ipynb`: Validation of specific queries using the fix

## Best Practices for Navigation Functions

### 1. Direct Variable References (Preferred Approach)

Whenever possible, use direct variable references instead of navigation functions:

```sql
DEFINE
    B AS price < A.price,   -- Instead of price < PREV(price)
    C AS price > B.price    -- Instead of price > PREV(price)
```

This approach is more reliable and often more intuitive.

### 2. Fixed Navigation Functions

If you need to use `PREV` or `NEXT`:

```sql
DEFINE
    DOWN AS price < PREV(price),
    UP AS price > PREV(price)
```

The fix we implemented makes these navigation functions work correctly.

### 3. Mixed Approach for Complex Patterns

For complex patterns, you can combine direct variable references with navigation functions:

```sql
DEFINE
    PEAK AS value > NEXT(value),
    DOWN AS value < PREV(value),
    VALLEY AS value < PREV(value) AND value < NEXT(value),
    RECOVERY AS value > PREV(value)
```

### 4. Handle Boundary Conditions

Remember that navigation functions return `None` at boundaries:
- `PREV` returns `None` at the first row
- `NEXT` returns `None` at the last row
- Both return `None` when crossing partition boundaries

### 5. Multiple Steps Navigation

You can navigate multiple steps by providing a second argument:
- `PREV(price, 2)` gets the price from two rows back
- `NEXT(price, 3)` gets the price from three rows ahead

## Documentation

For more details on the navigation function fix, see:
- `/docs/navigation_function_fix.md`
