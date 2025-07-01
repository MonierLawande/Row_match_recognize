# src/matcher/evaluation_utils.py
"""
Shared evaluation utilities for SQL:2016 row pattern matching.

This module consolidates common functionality used by both condition_evaluator.py
and measure_evaluator.py to eliminate duplication and provide a consistent API.

Features:
- Common mathematical and utility functions
- Shared type conversion and preservation utilities
- Table prefix validation and security functions
- Navigation function helpers
- Null handling and SQL semantics
- Thread-safe operations with proper validation

Author: Pattern Matching Engine Team
Version: 1.0.0
"""

import ast
import math
import re
import datetime
import decimal
import threading
from typing import Dict, Any, Optional, List, Union, Tuple, Callable
from functools import lru_cache
from dataclasses import dataclass
from enum import Enum

from src.utils.logging_config import get_logger
from src.matcher.row_context import RowContext

# Module logger
logger = get_logger(__name__)

# Constants for production-ready behavior
MAX_EXPRESSION_LENGTH = 10000  # Prevent extremely long expressions
MAX_RECURSION_DEPTH = 50      # Prevent infinite recursion

class EvaluationMode(Enum):
    """Enumeration of evaluation modes."""
    DEFINE = "DEFINE"      # Physical navigation for pattern definitions
    MEASURES = "MEASURES"  # Logical navigation for measures

class ValidationError(Exception):
    """Base class for validation errors."""
    pass

class ExpressionValidationError(ValidationError):
    """Error in expression validation."""
    pass

class SecurityValidationError(ValidationError):
    """Error in security validation."""
    pass

# Thread-local storage for evaluation metrics
_evaluation_metrics = threading.local()

def _get_evaluation_metrics():
    """Get thread-local evaluation metrics."""
    if not hasattr(_evaluation_metrics, 'metrics'):
        _evaluation_metrics.metrics = {
            "total_operations": 0,
            "validation_errors": 0,
            "type_conversions": 0,
            "security_checks": 0
        }
    return _evaluation_metrics.metrics

def validate_expression_length(expr: str) -> None:
    """
    Validate expression length to prevent resource exhaustion.
    
    Args:
        expr: Expression to validate
        
    Raises:
        ExpressionValidationError: If expression is too long
    """
    if len(expr) > MAX_EXPRESSION_LENGTH:
        raise ExpressionValidationError(
            f"Expression too long: {len(expr)} characters (max: {MAX_EXPRESSION_LENGTH})"
        )

def validate_recursion_depth(depth: int) -> None:
    """
    Validate recursion depth to prevent stack overflow.
    
    Args:
        depth: Current recursion depth
        
    Raises:
        ExpressionValidationError: If recursion depth exceeded
    """
    if depth > MAX_RECURSION_DEPTH:
        raise ExpressionValidationError(
            f"Maximum recursion depth exceeded: {depth} (max: {MAX_RECURSION_DEPTH})"
        )

def is_null(value: Any) -> bool:
    """
    Check if a value is NULL in SQL terms with comprehensive validation.
    
    Args:
        value: Value to check
        
    Returns:
        True if value is NULL/None/NaN, False otherwise
    """
    try:
        if value is None:
            return True
        
        # Handle NaN values
        if isinstance(value, float) and math.isnan(value):
            return True
        
        # Handle numpy NaN
        try:
            import numpy as np
            if hasattr(value, '__array__') and hasattr(np, 'isnan'):
                if np.isscalar(value) and np.isnan(value):
                    return True
        except (ImportError, TypeError, ValueError):
            pass
        
        # Handle pandas NA
        try:
            import pandas as pd
            if pd.isna(value):
                return True
        except (ImportError, TypeError, ValueError):
            pass
        
        return False
        
    except Exception as e:
        logger.warning(f"Error in null check for value {value}: {e}")
        return value is None

def coalesce_function(*args: Any) -> Any:
    """
    SQL COALESCE function - return the first non-null value.
    
    Args:
        *args: Values to check
        
    Returns:
        First non-null value, or None if all are null
    """
    for arg in args:
        if not is_null(arg):
            return arg
    return None

def cast_function(value: Any, target_type: str) -> Any:
    """
    SQL CAST function with comprehensive type conversion.
    
    Args:
        value: Value to cast
        target_type: Target type (BIGINT, VARCHAR, DOUBLE, etc.)
        
    Returns:
        Converted value or None if conversion fails
    """
    if is_null(value):
        return None
    
    try:
        target_type = target_type.upper()
        
        if target_type in ('BIGINT', 'INTEGER', 'INT'):
            if isinstance(value, bool):
                return int(value)
            return int(float(value))  # Handle string numbers
        elif target_type in ('DOUBLE', 'REAL', 'FLOAT'):
            return float(value)
        elif target_type in ('VARCHAR', 'CHAR', 'TEXT', 'STRING'):
            return str(value)
        elif target_type == 'BOOLEAN':
            if isinstance(value, str):
                return value.lower() in ('true', 't', '1', 'yes', 'y')
            return bool(value)
        elif target_type == 'DATE':
            if isinstance(value, str):
                return datetime.datetime.strptime(value, '%Y-%m-%d').date()
            return value
        elif target_type in ('TIMESTAMP', 'DATETIME'):
            if isinstance(value, str):
                return datetime.datetime.fromisoformat(value)
            return value
        elif target_type == 'DECIMAL':
            return decimal.Decimal(str(value))
        else:
            logger.warning(f"Unsupported cast target type: {target_type}")
            return value
            
    except (ValueError, TypeError, OverflowError) as e:
        logger.warning(f"Cast failed: {value} to {target_type}: {e}")
        return None

def try_cast_function(value: Any, target_type: str) -> Any:
    """
    SQL TRY_CAST function - like CAST but returns NULL on failure.
    
    Args:
        value: Value to cast
        target_type: Target type
        
    Returns:
        Converted value or None if conversion fails
    """
    try:
        return cast_function(value, target_type)
    except Exception:
        return None

def preserve_data_type(original_value: Any, new_value: Any) -> Any:
    """
    Preserve the data type of the original value with comprehensive type handling.
    
    This production-ready function provides robust type preservation for Trino
    compatibility and handles edge cases gracefully.
    
    Args:
        original_value: The original value whose type should be preserved
        new_value: The new value to type-cast
        
    Returns:
        The new value cast to the type of the original value, or None if conversion fails
    """
    if is_null(new_value):
        return None
    
    if is_null(original_value):
        return new_value
    
    try:
        # Handle NaN values with comprehensive checking
        if isinstance(new_value, float):
            if math.isnan(new_value):
                return None
        
        # Preserve integer types with overflow protection
        if isinstance(original_value, int):
            if isinstance(new_value, (int, float)):
                if isinstance(new_value, float):
                    if new_value.is_integer():
                        # Check for overflow
                        int_val = int(new_value)
                        if -(2**63) <= int_val <= (2**63 - 1):  # 64-bit int range
                            return int_val
                elif isinstance(new_value, int):
                    return int(new_value)
        
        # Preserve float types
        if isinstance(original_value, float):
            if isinstance(new_value, (int, float)):
                return float(new_value)
        
        # Preserve string types with encoding safety
        if isinstance(original_value, str):
            try:
                return str(new_value)
            except UnicodeEncodeError:
                logger.warning(f"Unicode encoding error converting {new_value} to string")
                return None
        
        # Handle complex types
        if isinstance(original_value, (list, tuple)):
            if isinstance(new_value, (list, tuple)):
                return type(original_value)(new_value)
        
        # For other types, return as-is with validation
        return new_value
        
    except (ValueError, TypeError, OverflowError) as e:
        logger.warning(f"Type preservation failed for {original_value} -> {new_value}: {e}")
        return new_value  # Fallback to original new_value

def is_table_prefix(var_name: str, var_assignments: Dict[str, List[int]], 
                   subsets: Dict[str, List[str]] = None) -> bool:
    """
    Check if a variable name looks like a table prefix rather than a pattern variable.
    
    This production-ready function provides comprehensive validation to prevent
    common SQL injection patterns and ensure proper variable naming.
    
    Args:
        var_name: The variable name to check (validated)
        var_assignments: Dictionary of defined pattern variables
        subsets: Dictionary of defined subset variables
        
    Returns:
        True if this looks like a forbidden table prefix, False otherwise
        
    Raises:
        ValueError: If inputs are invalid
    """
    # Input validation
    if not isinstance(var_name, str):
        raise ValueError(f"Expected str for var_name, got {type(var_name)}")
    
    if not isinstance(var_assignments, dict):
        raise ValueError(f"Expected dict for var_assignments, got {type(var_assignments)}")
    
    # Update metrics
    metrics = _get_evaluation_metrics()
    metrics["security_checks"] += 1
    
    # If it's a defined pattern variable or subset variable, it's not a table prefix
    if var_name in var_assignments:
        return False
    if subsets and var_name in subsets:
        return False
    
    # Security: Check for SQL injection patterns
    dangerous_patterns = [
        r'[;\'"\\]',              # SQL injection characters
        r'--',                    # SQL comments
        r'/\*',                   # SQL block comments
        r'\bdrop\b',              # DROP statements
        r'\bdelete\b',            # DELETE statements
        r'\bupdate\b',            # UPDATE statements
        r'\binsert\b',            # INSERT statements
        r'\bexec\b',              # EXEC statements
        r'\bunion\b',             # UNION statements
    ]
    
    var_lower = var_name.lower()
    for pattern in dangerous_patterns:
        if re.search(pattern, var_lower, re.IGNORECASE):
            logger.warning(f"Potentially dangerous pattern detected in variable name: {var_name}")
            raise SecurityValidationError(f"Forbidden pattern in variable name: {var_name}")
    
    # Common table name patterns that should be rejected
    table_patterns = [
        r'^[a-z]+_table$',      # ending with _table
        r'^tbl_[a-z]+$',        # starting with tbl_
        r'^[a-z]+_tbl$',        # ending with _tbl
        r'^[a-z]+_tab$',        # ending with _tab
        r'^[a-z]+s$',           # plural forms (likely table names)
        r'^[a-z]+_data$',       # ending with _data
        r'^data_[a-z]+$',       # starting with data_
    ]
    
    # Check against common table naming patterns
    for pattern in table_patterns:
        if re.match(pattern, var_lower):
            return True
    
    # Check for overly long names (likely table names)
    if len(var_name) > 20:
        return True
    
    # If it contains underscores and is longer than typical pattern variable names
    if '_' in var_name and len(var_name) > 10:
        return True
    
    return False

def get_column_value_with_type_preservation(row: Dict[str, Any], column_name: str) -> Any:
    """
    Get column value from row with proper type preservation and validation.
    
    This production-ready function ensures that:
    1. Original data types are preserved (int stays int, not converted to float)
    2. Missing values return None instead of NaN for Trino compatibility
    3. Proper validation and error handling
    4. Thread-safe operation
    
    Args:
        row: Dictionary representing a row (validated)
        column_name: Name of the column to retrieve (validated)
        
    Returns:
        The value with original type preserved, or None if missing
        
    Raises:
        ValueError: If inputs are invalid
    """
    # Input validation
    if row is None:
        return None
    
    if not isinstance(row, dict):
        raise ValueError(f"Expected dict for row, got {type(row)}")
    
    if not isinstance(column_name, str):
        raise ValueError(f"Expected str for column_name, got {type(column_name)}")
    
    if column_name not in row:
        return None
    
    value = row[column_name]
    
    # Handle NaN values - convert to None for Trino compatibility
    try:
        if isinstance(value, float):
            if math.isnan(value):
                return None
        elif hasattr(value, '__array__'):
            # Handle numpy values
            import numpy as np
            if np.isscalar(value) and np.isnan(value):
                return None
    except (TypeError, ValueError, ImportError):
        # If NaN check fails, continue with original value
        pass
    
    # Preserve original types - don't auto-convert
    return value

def safe_compare(left: Any, right: Any, op: Union[Callable, ast.operator]) -> Any:
    """
    Perform SQL-style comparison with NULL handling.
    
    Args:
        left: Left operand
        right: Right operand
        op: Comparison operator (function or AST operator)
        
    Returns:
        Comparison result with SQL NULL semantics (None if any operand is NULL)
    """
    # SQL NULL semantics: any comparison with NULL is NULL (None)
    if is_null(left) or is_null(right):
        return None
    
    # Map AST operators to Python functions
    import operator
    
    op_map = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }
    
    try:
        # If op is a callable, use it directly; otherwise map from AST type
        if callable(op):
            return op(left, right)
        else:
            op_func = op_map.get(type(op))
            if op_func:
                return op_func(left, right)
            else:
                raise ValueError(f"Unsupported comparison operator: {type(op)}")
    except Exception as e:
        logger.warning(f"Comparison failed: {left} {op} {right}: {e}")
        return False

# Mathematical and utility functions registry
MATH_FUNCTIONS = {
    # Basic math functions
    'ABS': abs,
    'ROUND': lambda x, digits=0: round(x, digits),
    'TRUNCATE': lambda x, digits=0: math.trunc(x * 10**digits) / 10**digits,
    'CEILING': math.ceil,
    'FLOOR': math.floor,
    
    # Statistical functions
    'SQRT': math.sqrt,
    'POWER': pow,
    'EXP': math.exp,
    'LN': math.log,
    'LOG': lambda x, base=10: math.log(x, base),
    'MOD': lambda x, y: x % y,
    
    # Trigonometric functions
    'SIN': math.sin,
    'COS': math.cos,
    'TAN': math.tan,
    'ASIN': math.asin,
    'ACOS': math.acos,
    'ATAN': math.atan,
    'ATAN2': math.atan2,
    'DEGREES': math.degrees,
    'RADIANS': math.radians,
    
    # String functions
    'LENGTH': len,
    'LOWER': str.lower,
    'UPPER': str.upper,
    'SUBSTR': lambda s, start, length=None: s[start-1:start-1+length] if length else s[start-1:],
    'SUBSTRING': lambda s, start, length=None: s[start-1:start-1+length] if length else s[start-1:],
    'CONCAT': lambda *args: ''.join(str(arg) for arg in args if arg is not None),
    'TRIM': lambda s: str(s).strip() if s is not None else None,
    'LTRIM': lambda s: str(s).lstrip() if s is not None else None,
    'RTRIM': lambda s: str(s).rstrip() if s is not None else None,
    'LEFT': lambda s, n: str(s)[:n] if s is not None else None,
    'RIGHT': lambda s, n: str(s)[-n:] if s is not None else None,
    'REPLACE': lambda s, old, new: str(s).replace(old, new) if s is not None else None,
    
    # Conditional functions
    'LEAST': min,
    'GREATEST': max,
    'COALESCE': coalesce_function,
    'NULLIF': lambda x, y: None if x == y else x,
    'IF': lambda condition, true_val, false_val: true_val if condition else false_val,
    
    # Type conversion functions
    'CAST': cast_function,
    'TRY_CAST': try_cast_function,
    
    # Date/time functions
    'NOW': lambda: datetime.datetime.now(),
    'CURRENT_DATE': lambda: datetime.date.today(),
    'CURRENT_TIME': lambda: datetime.datetime.now().time(),
    'CURRENT_TIMESTAMP': lambda: datetime.datetime.now(),
}

def evaluate_math_function(func_name: str, *args: Any) -> Any:
    """
    Evaluate a mathematical or utility function with proper error handling.
    
    Args:
        func_name: Name of the function to evaluate
        *args: Arguments to pass to the function
        
    Returns:
        Function result or None if error
        
    Raises:
        ValueError: If function not found or evaluation fails
    """
    func_name = func_name.upper()
    
    if func_name not in MATH_FUNCTIONS:
        raise ValueError(f"Unknown function: {func_name}")
    
    try:
        # Check for NULL arguments - SQL functions typically return NULL if any input is NULL
        if any(is_null(arg) for arg in args) and func_name not in ('COALESCE', 'NULLIF'):
            return None
        
        return MATH_FUNCTIONS[func_name](*args)
    except Exception as e:
        raise ValueError(f"Error in {func_name} function: {e}")

def get_evaluation_metrics() -> Dict[str, int]:
    """
    Get current evaluation metrics for monitoring.
    
    Returns:
        Dictionary of evaluation metrics
    """
    return _get_evaluation_metrics().copy()

def reset_evaluation_metrics() -> None:
    """Reset evaluation metrics."""
    metrics = _get_evaluation_metrics()
    for key in metrics:
        metrics[key] = 0

# Export key functions and classes
__all__ = [
    'EvaluationMode',
    'ValidationError', 
    'ExpressionValidationError',
    'SecurityValidationError',
    'validate_expression_length',
    'validate_recursion_depth',
    'is_null',
    'coalesce_function',
    'cast_function',
    'try_cast_function',
    'preserve_data_type',
    'is_table_prefix',
    'get_column_value_with_type_preservation',
    'safe_compare',
    'MATH_FUNCTIONS',
    'evaluate_math_function',
    'get_evaluation_metrics',
    'reset_evaluation_metrics'
]
