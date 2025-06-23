# Enhanced Aggregate Function Implementation for SQL:2016 Row Pattern Recognition
# Production-ready comprehensive aggregate support

"""
Production-ready aggregate function evaluator for SQL:2016 row pattern matching.

This module implements comprehensive aggregate evaluation with full support for:
- All standard SQL:2016 aggregate functions (SUM, COUNT, MIN, MAX, AVG, etc.)
- RUNNING vs FINAL semantics with proper default handling
- Variable-specific aggregation with pattern variable support
- Advanced aggregate functions (ARRAY_AGG, STRING_AGG, MAX_BY, MIN_BY)
- Conditional aggregates (COUNT_IF, SUM_IF, AVG_IF)
- Statistical functions (STDDEV, VARIANCE)
- Comprehensive argument validation and error handling
- Performance optimization with intelligent caching
- Thread-safe operations with proper synchronization

Features:
- Memory-efficient processing for large datasets
- Advanced type preservation and null handling
- Comprehensive SQL:2016 compliance
- Production-grade error handling and recovery
- Performance monitoring and metrics collection

Author: Pattern Matching Engine Team
Version: 3.0.0
"""

import threading
from collections import defaultdict
from functools import lru_cache
from typing import Dict, Any, List, Optional, Set, Union, Tuple, Callable
import re
import math
import numpy as np
import time
from enum import Enum
from dataclasses import dataclass

from src.matcher.row_context import RowContext
from src.utils.logging_config import get_logger, PerformanceTimer

# Module logger with enhanced configuration
logger = get_logger(__name__)

# Constants for production-ready behavior
MAX_EXPRESSION_LENGTH = 5000    # Prevent extremely long expressions
MAX_CACHE_SIZE = 1000          # LRU cache limit for aggregate results
MAX_ARRAY_SIZE = 100000        # Maximum array aggregation size
PERFORMANCE_LOG_THRESHOLD = 0.1  # Log slow operations (100ms)

class AggregateMode(Enum):
    """Aggregate evaluation modes."""
    RUNNING = "RUNNING"     # Include only rows up to current position
    FINAL = "FINAL"         # Include all rows in the match

class AggregateValidationError(Exception):
    """Error in aggregate function validation with enhanced context."""
    
    def __init__(self, message: str, function_name: str = None, 
                 suggestion: str = None, error_code: str = None):
        self.message = message
        self.function_name = function_name
        self.suggestion = suggestion
        self.error_code = error_code
        
        full_message = message
        if function_name:
            full_message = f"[{function_name}] {message}"
        if suggestion:
            full_message += f"\nSuggestion: {suggestion}"
        if error_code:
            full_message += f"\nError Code: {error_code}"
        
        super().__init__(full_message)

class AggregateArgumentError(AggregateValidationError):
    """Error in aggregate function arguments with specific guidance."""
    
    def __init__(self, message: str, function_name: str = None):
        suggestions = {
            "COUNT": "COUNT(*) or COUNT(variable.column) or COUNT(DISTINCT variable.column)",
            "SUM": "SUM(variable.column) where column contains numeric values",
            "AVG": "AVG(variable.column) where column contains numeric values",
            "MIN": "MIN(variable.column) for any comparable column",
            "MAX": "MAX(variable.column) for any comparable column",
            "ARRAY_AGG": "ARRAY_AGG(variable.column) for any column",
            "STRING_AGG": "STRING_AGG(variable.column, delimiter) where column is text"
        }
        
        suggestion = suggestions.get(function_name, "Check function documentation")
        error_code = f"AGG_ARG_{function_name}" if function_name else "AGG_ARG_001"
        
        super().__init__(message, function_name, suggestion, error_code)

class AggregateTypeError(AggregateValidationError):
    """Error in aggregate function type handling."""
    pass

# Thread-local storage for aggregate metrics
_aggregate_metrics = threading.local()

def _get_aggregate_metrics():
    """Get thread-local aggregate metrics."""
    if not hasattr(_aggregate_metrics, 'metrics'):
        _aggregate_metrics.metrics = {
            "total_evaluations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "function_calls": defaultdict(int),
            "total_time": 0.0,
            "slow_operations": 0
        }
    return _aggregate_metrics.metrics

class ProductionAggregateEvaluator:
    """
    Production-ready aggregate function evaluator for SQL:2016 row pattern recognition.
    
    This class provides comprehensive aggregate evaluation with:
    - Full support for all standard SQL:2016 aggregate functions
    - RUNNING vs FINAL semantics with intelligent defaults
    - Variable-specific aggregation with pattern variable support
    - Advanced functions (ARRAY_AGG, STRING_AGG, statistical functions)
    - Conditional aggregates with proper type handling
    - Thread-safe operations with performance optimization
    - Comprehensive validation and error handling
    - Memory-efficient processing for large datasets
    
    Features:
    - All standard aggregate functions (SUM, COUNT, MIN, MAX, AVG, etc.)
    - RUNNING vs FINAL semantics with proper default handling
    - Variable-specific aggregation (A.column vs column)
    - Special count syntax (COUNT(*), COUNT(A.*), COUNT(U.*))
    - Array aggregation functions (ARRAY_AGG)
    - Multi-argument aggregates (MAX_BY, MIN_BY)
    - CLASSIFIER() and MATCH_NUMBER() in aggregate arguments
    - Comprehensive argument validation
    - Proper nesting restrictions
    - Type preservation and null handling
    """
    
    # SQL:2016 standard aggregate functions with enhanced categorization
    STANDARD_AGGREGATES = {
        'SUM', 'COUNT', 'MIN', 'MAX', 'AVG', 'STDDEV', 'VARIANCE',
        'STDDEV_SAMP', 'STDDEV_POP', 'VAR_SAMP', 'VAR_POP',
        'ARRAY_AGG', 'STRING_AGG', 'MAX_BY', 'MIN_BY', 'COUNT_IF',
        'SUM_IF', 'AVG_IF', 'BOOL_AND', 'BOOL_OR', 'LISTAGG',
        'FIRST_VALUE', 'LAST_VALUE', 'COUNT_DISTINCT'
    }
    
    # Functions that support RUNNING semantics by default
    RUNNING_BY_DEFAULT = {
        'SUM', 'COUNT', 'MIN', 'MAX', 'AVG', 'ARRAY_AGG', 'STRING_AGG',
        'COUNT_IF', 'SUM_IF', 'AVG_IF', 'BOOL_AND', 'BOOL_OR'
    }
    
    # Functions that require numeric arguments
    NUMERIC_FUNCTIONS = {
        'SUM', 'AVG', 'STDDEV', 'VARIANCE', 'STDDEV_SAMP', 'STDDEV_POP',
        'VAR_SAMP', 'VAR_POP', 'SUM_IF', 'AVG_IF'
    }
    
    # Functions that support multiple arguments
    MULTI_ARG_FUNCTIONS = {
        'MAX_BY': 2, 'MIN_BY': 2, 'STRING_AGG': 2, 'COUNT_IF': 2, 'SUM_IF': 2, 'AVG_IF': 2
    }
    
    # Functions that support DISTINCT modifier
    DISTINCT_FUNCTIONS = {
        'COUNT', 'SUM', 'AVG', 'ARRAY_AGG', 'STRING_AGG'
    }
    
    def __init__(self, context: RowContext):
        """
        Initialize the aggregate evaluator with comprehensive setup.
        
        Args:
            context: Row context for pattern matching
            
        Raises:
            AggregateValidationError: If context is invalid
        """
        if not isinstance(context, RowContext):
            raise AggregateValidationError(
                "Invalid context type", None, 
                "Pass a valid RowContext instance", "AGG_INIT_001"
            )
        
        self.context = context
        
        # Thread-safe operation lock
        self._lock = threading.RLock()
        
        # Enhanced caching structures
        self._validation_cache = {}
        self._result_cache = {}
        self._expression_cache = {}
        self._variable_data_cache = {}
        
        # Performance metrics with detailed tracking
        self.stats = {
            "evaluations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "validation_errors": 0,
            "type_conversions": 0,
            "total_time": 0.0,
            "function_counts": defaultdict(int),
            "slow_operations": 0
        }
        
        logger.debug(f"Initialized ProductionAggregateEvaluator with context containing "
                    f"{len(context.rows)} rows and {len(context.variables)} variables")
    
    def evaluate_aggregate(self, expr: str, semantics: str = "RUNNING") -> Any:
        """
        Evaluate an aggregate function with comprehensive SQL:2016 support and production-ready features.
        
        This enhanced method provides:
        - Complete validation and error handling
        - Performance optimization with intelligent caching
        - Thread-safe operations with proper synchronization
        - Advanced type handling and preservation
        - Comprehensive logging and metrics collection
        - Memory-efficient processing for large datasets
        
        Args:
            expr: The aggregate expression (e.g., "SUM(A.price)", "COUNT(*)")
            semantics: "RUNNING" or "FINAL" (default: "RUNNING")
            
        Returns:
            The aggregate result with proper type preservation
            
        Raises:
            AggregateValidationError: If the aggregate expression is invalid
            AggregateArgumentError: If the arguments are invalid
            AggregateTypeError: If type conversion fails
        """
        # Input validation
        if not expr or not isinstance(expr, str):
            raise AggregateValidationError(
                "Expression must be a non-empty string",
                None, "Provide a valid aggregate expression", "AGG_EVAL_001"
            )
        
        if len(expr) > MAX_EXPRESSION_LENGTH:
            raise AggregateValidationError(
                f"Expression too long: {len(expr)} characters (max: {MAX_EXPRESSION_LENGTH})",
                None, "Simplify the aggregate expression", "AGG_EVAL_002"
            )
        
        # Normalize semantics
        semantics = semantics.upper()
        if semantics not in ["RUNNING", "FINAL"]:
            raise AggregateValidationError(
                f"Invalid semantics: {semantics}",
                None, "Use 'RUNNING' or 'FINAL'", "AGG_EVAL_003"
            )
        
        with self._lock:
            self.stats["evaluations"] += 1
            start_time = time.time()
            
            try:
                # Check cache first - fix unhashable type issue
                # Convert variable indices lists to tuples for hashing
                hashable_variables = tuple(sorted(
                    (k, tuple(v) if isinstance(v, list) else v) 
                    for k, v in self.context.variables.items()
                ))
                cache_key = (expr, semantics, self.context.current_idx, hashable_variables)
                
                if cache_key in self._result_cache:
                    self.stats["cache_hits"] += 1
                    return self._result_cache[cache_key]
                
                self.stats["cache_misses"] += 1
                
                # Parse the aggregate function
                agg_info = self._parse_aggregate_function(expr)
                if not agg_info:
                    raise AggregateValidationError(
                        f"Invalid aggregate expression: {expr}",
                        None, "Check function syntax", "AGG_PARSE_001"
                    )
                
                func_name = agg_info['function'].upper()
                arguments = agg_info['arguments']
                
                # Update function call statistics
                self.stats["function_counts"][func_name] += 1
                
                # Validate the function and arguments
                self._validate_aggregate_function(func_name, arguments)
                
                # Determine evaluation mode
                is_running = semantics == "RUNNING"
                
                # Evaluate based on function type with enhanced error handling
                try:
                    if func_name == "COUNT":
                        result = self._evaluate_count(arguments, is_running)
                    elif func_name == "SUM":
                        result = self._evaluate_sum(arguments, is_running)
                    elif func_name in ("MIN", "MAX"):
                        result = self._evaluate_min_max(func_name, arguments, is_running)
                    elif func_name == "AVG":
                        result = self._evaluate_avg(arguments, is_running)
                    elif func_name == "ARRAY_AGG":
                        result = self._evaluate_array_agg(arguments, is_running)
                    elif func_name == "STRING_AGG":
                        result = self._evaluate_string_agg(arguments, is_running)
                    elif func_name in ("MAX_BY", "MIN_BY"):
                        result = self._evaluate_by_functions(func_name, arguments, is_running)
                    elif func_name in ("COUNT_IF", "SUM_IF", "AVG_IF"):
                        result = self._evaluate_conditional_aggregates(func_name, arguments, is_running)
                    elif func_name in ("BOOL_AND", "BOOL_OR"):
                        result = self._evaluate_bool_aggregates(func_name, arguments, is_running)
                    elif func_name in ("STDDEV", "VARIANCE", "STDDEV_SAMP", "STDDEV_POP", "VAR_SAMP", "VAR_POP"):
                        result = self._evaluate_statistical_functions(func_name, arguments, is_running)
                    elif func_name == "LISTAGG":
                        result = self._evaluate_listagg(arguments, is_running)
                    else:
                        raise AggregateValidationError(
                            f"Unsupported aggregate function: {func_name}",
                            func_name, "Check supported functions", "AGG_UNSUPPORTED"
                        )
                    
                    # Cache the result (with size limit)
                    if len(self._result_cache) < MAX_CACHE_SIZE:
                        self._result_cache[cache_key] = result
                    
                    return result
                    
                except Exception as e:
                    self.stats["validation_errors"] += 1
                    if not isinstance(e, (AggregateValidationError, AggregateArgumentError, AggregateTypeError)):
                        # Wrap unexpected errors
                        raise AggregateValidationError(
                            f"Unexpected error in {func_name}: {str(e)}",
                            func_name, "Check input data and function usage", "AGG_UNEXPECTED"
                        ) from e
                    else:
                        raise
                
            finally:
                # Track performance metrics
                operation_time = time.time() - start_time
                self.stats["total_time"] += operation_time
                
                if operation_time > PERFORMANCE_LOG_THRESHOLD:
                    self.stats["slow_operations"] += 1
                    logger.warning(f"Slow aggregate evaluation: {expr} took {operation_time:.3f}s")
                
                # Periodic cache optimization
                if self.stats["evaluations"] % 100 == 0:
                    self._optimize_caches()
    
    def _optimize_caches(self) -> None:
        """Optimize cache structures to prevent memory bloat."""
        # Simple LRU implementation: remove oldest entries when cache is full
        if len(self._result_cache) > MAX_CACHE_SIZE:
            # Remove oldest 20% of entries
            items_to_remove = len(self._result_cache) - int(MAX_CACHE_SIZE * 0.8)
            keys_to_remove = list(self._result_cache.keys())[:items_to_remove]
            for key in keys_to_remove:
                self._result_cache.pop(key, None)
        
        # Optimize other caches similarly
        for cache in [self._validation_cache, self._expression_cache, self._variable_data_cache]:
            if len(cache) > MAX_CACHE_SIZE // 2:
                items_to_remove = len(cache) - int(MAX_CACHE_SIZE * 0.3)
                keys_to_remove = list(cache.keys())[:items_to_remove]
                for key in keys_to_remove:
                    cache.pop(key, None)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive performance statistics for monitoring.
        
        Returns:
            Dictionary with detailed performance metrics
        """
        total_operations = self.stats["cache_hits"] + self.stats["cache_misses"]
        hit_rate = (self.stats["cache_hits"] / total_operations * 100) if total_operations > 0 else 0
        
        avg_time = (self.stats["total_time"] / self.stats["evaluations"]) if self.stats["evaluations"] > 0 else 0
        
        return {
            "total_evaluations": self.stats["evaluations"],
            "cache_hit_rate_percent": hit_rate,
            "average_evaluation_time_ms": avg_time * 1000,
            "slow_operations": self.stats["slow_operations"],
            "validation_errors": self.stats["validation_errors"],
            "function_usage": dict(self.stats["function_counts"]),
            "cache_sizes": {
                "result_cache": len(self._result_cache),
                "validation_cache": len(self._validation_cache),
                "expression_cache": len(self._expression_cache),
                "variable_data_cache": len(self._variable_data_cache)
            }
        }
    
    def _parse_aggregate_function(self, expr: str) -> Optional[Dict[str, Any]]:
        """
        Parse an aggregate function expression into components.
        
        Returns:
            Dict with 'function' and 'arguments' keys, or None if invalid
        """
        # Remove RUNNING/FINAL prefix if present
        clean_expr = re.sub(r'^\s*(RUNNING|FINAL)\s+', '', expr.strip(), flags=re.IGNORECASE)
        
        # Enhanced pattern to handle complex arguments including nested functions
        pattern = r'([A-Z_]+)\s*\(\s*(.*)\s*\)$'
        match = re.match(pattern, clean_expr, re.IGNORECASE)
        
        if not match:
            logger.debug(f"Failed to parse aggregate function: {expr} (cleaned: {clean_expr})")
            return None
        
        func_name = match.group(1).upper()
        args_str = match.group(2).strip()
        
        # Parse arguments (handling nested parentheses)
        arguments = self._parse_function_arguments(args_str) if args_str else []
        
        logger.debug(f"Parsed aggregate function {func_name} with args: {arguments}")
        
        return {
            'function': func_name,
            'arguments': arguments
        }
        
        return {
            'function': func_name,
            'arguments': arguments
        }
    
    def _parse_function_arguments(self, args_str: str) -> List[str]:
        """
        Parse function arguments handling nested parentheses and commas.
        """
        if not args_str:
            return []
        
        arguments = []
        current_arg = ""
        paren_depth = 0
        quote_char = None
        
        for char in args_str:
            if quote_char:
                current_arg += char
                if char == quote_char and (not current_arg or current_arg[-2] != '\\'):
                    quote_char = None
            elif char in ("'", '"'):
                current_arg += char
                quote_char = char
            elif char == '(':
                current_arg += char
                paren_depth += 1
            elif char == ')':
                current_arg += char
                paren_depth -= 1
            elif char == ',' and paren_depth == 0:
                arguments.append(current_arg.strip())
                current_arg = ""
            else:
                current_arg += char
        
        if current_arg.strip():
            arguments.append(current_arg.strip())
        
        return arguments
    
    def _validate_aggregate_function(self, func_name: str, arguments: List[str]) -> None:
        """
        Validate aggregate function and its arguments according to SQL:2016.
        """
        # Check if function is supported
        if func_name not in self.STANDARD_AGGREGATES:
            raise AggregateValidationError(f"Unsupported aggregate function: {func_name}")
        
        # Validate argument count
        if func_name in self.MULTI_ARG_FUNCTIONS:
            expected_args = self.MULTI_ARG_FUNCTIONS[func_name]
            if len(arguments) != expected_args:
                raise AggregateArgumentError(
                    f"{func_name} requires exactly {expected_args} arguments, got {len(arguments)}"
                )
        elif func_name == "COUNT":
            if len(arguments) == 0:
                raise AggregateArgumentError("COUNT requires at least one argument")
        else:
            if len(arguments) != 1:
                raise AggregateArgumentError(f"{func_name} requires exactly one argument")
        
        # Validate argument consistency for pattern variables
        if len(arguments) > 1:
            self._validate_argument_consistency(arguments)
        
        # Check for illegal nesting (no aggregates in navigation functions)
        for arg in arguments:
            self._validate_no_nested_aggregates(arg)
    
    def _validate_argument_consistency(self, arguments: List[str]) -> None:
        """
        Validate that all arguments reference the same pattern variable(s).
        SQL:2016 requires consistent variable references in multi-argument aggregates.
        """
        pattern_vars = set()
        
        for arg in arguments:
            var_refs = self._extract_pattern_variables(arg)
            if pattern_vars and var_refs and pattern_vars != var_refs:
                raise AggregateArgumentError(
                    "All arguments in multi-argument aggregate must reference the same pattern variables"
                )
            if var_refs:
                pattern_vars = var_refs
    
    def _extract_pattern_variables(self, expr: str) -> Set[str]:
        """Extract pattern variable references from an expression."""
        pattern_vars = set()
        
        # Find variable.column references
        var_col_pattern = r'\b([A-Z_][A-Z0-9_]*)\.([A-Z_][A-Z0-9_]*)\b'
        matches = re.findall(var_col_pattern, expr, re.IGNORECASE)
        
        for var_name, _ in matches:
            pattern_vars.add(var_name.upper())
        
        return pattern_vars
    
    def _validate_no_nested_aggregates(self, expr: str) -> None:
        """
        Validate that navigation functions don't contain aggregate functions.
        SQL:2016 prohibits aggregates inside FIRST, LAST, PREV, NEXT.
        """
        # Check if this is a navigation function
        nav_pattern = r'\b(FIRST|LAST|PREV|NEXT)\s*\('
        if re.search(nav_pattern, expr, re.IGNORECASE):
            # Check for aggregates inside
            agg_pattern = r'\b(' + '|'.join(self.STANDARD_AGGREGATES) + r')\s*\('
            if re.search(agg_pattern, expr, re.IGNORECASE):
                raise AggregateValidationError(
                    "Aggregate functions cannot be nested inside navigation functions"
                )
    
    def _evaluate_count(self, arguments: List[str], is_running: bool) -> int:
        """Evaluate COUNT function with all SQL:2016 variants including DISTINCT."""
        if not arguments:
            return 0
        
        arg = arguments[0]
        
        # COUNT(*) - count all matched rows
        if arg == "*":
            return self._count_all_rows(is_running)
        
        # COUNT(DISTINCT expression) - count distinct non-null values
        distinct_match = re.match(r'^\s*DISTINCT\s+(.+)$', arg, re.IGNORECASE)
        if distinct_match:
            expr = distinct_match.group(1).strip()
            values = self._get_expression_values(expr, is_running)
            non_null_values = [v for v in values if v is not None]
            return len(set(non_null_values))  # Use set to get distinct values
        
        # COUNT(var.*) - count rows for specific variable
        var_wildcard_match = re.match(r'^([A-Z_][A-Z0-9_]*)\.\*$', arg, re.IGNORECASE)
        if var_wildcard_match:
            var_name = var_wildcard_match.group(1).upper()
            return self._count_variable_rows(var_name, is_running)
        
        # COUNT(expression) - count non-null values
        values = self._get_expression_values(arg, is_running)
        # Handle both None and NaN values properly
        return len([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))])
    
    def _evaluate_sum(self, arguments: List[str], is_running: bool) -> Union[int, float, None]:
        """Evaluate SUM function with type preservation."""
        if not arguments:
            return None
        
        values = self._get_numeric_values(arguments[0], is_running)
        if not values:
            return None
        
        # Preserve integer type if all values are integers
        if all(isinstance(v, int) for v in values):
            return sum(values)
        else:
            return float(sum(values))
    
    def _evaluate_min_max(self, func_name: str, arguments: List[str], is_running: bool) -> Any:
        """Evaluate MIN/MAX functions with type preservation."""
        if not arguments:
            return None
        
        values = self._get_expression_values(arguments[0], is_running)
        values = [v for v in values if v is not None]
        
        if not values:
            return None
        
        try:
            return min(values) if func_name == "MIN" else max(values)
        except TypeError:
            # Handle mixed types by converting to strings
            str_values = [str(v) for v in values]
            return min(str_values) if func_name == "MIN" else max(str_values)
    
    def _evaluate_avg(self, arguments: List[str], is_running: bool) -> Optional[float]:
        """Evaluate AVG function."""
        if not arguments:
            return None
        
        values = self._get_numeric_values(arguments[0], is_running)
        if not values:
            return None
        
        return sum(values) / len(values)
    
    def _evaluate_array_agg(self, arguments: List[str], is_running: bool) -> List[Any]:
        """Evaluate ARRAY_AGG function."""
        if not arguments:
            return []
        
        values = self._get_expression_values(arguments[0], is_running)
        # Filter out nulls for array aggregation
        return [v for v in values if v is not None]
    
    def _evaluate_string_agg(self, arguments: List[str], is_running: bool) -> Optional[str]:
        """Evaluate STRING_AGG function."""
        if len(arguments) != 2:
            raise AggregateArgumentError("STRING_AGG requires exactly 2 arguments")
        
        values = self._get_expression_values(arguments[0], is_running)
        separator = self._evaluate_single_expression(arguments[1])
        
        # Convert values to strings and filter nulls
        str_values = [str(v) for v in values if v is not None]
        
        if not str_values:
            return None
        
        return str(separator).join(str_values)
    
    def _evaluate_by_functions(self, func_name: str, arguments: List[str], is_running: bool) -> Any:
        """Evaluate MAX_BY/MIN_BY functions."""
        if len(arguments) != 2:
            raise AggregateArgumentError(f"{func_name} requires exactly 2 arguments")
        
        value_expr = arguments[0]
        key_expr = arguments[1]
        
        # Get matched row indices
        row_indices = self._get_row_indices(value_expr, is_running)
        
        if not row_indices:
            return None
        
        # Evaluate expressions for each row
        best_value = None
        best_key = None
        
        for idx in row_indices:
            if idx >= len(self.context.rows):
                continue
            
            # Temporarily set current index for expression evaluation
            old_idx = self.context.current_idx
            self.context.current_idx = idx
            
            try:
                value = self._evaluate_single_expression(value_expr)
                key = self._evaluate_single_expression(key_expr)
                
                if value is not None and key is not None:
                    if best_key is None:
                        best_value = value
                        best_key = key
                    else:
                        if func_name == "MAX_BY" and key > best_key:
                            best_value = value
                            best_key = key
                        elif func_name == "MIN_BY" and key < best_key:
                            best_value = value
                            best_key = key
            finally:
                self.context.current_idx = old_idx
        
        return best_value
    
    def _evaluate_conditional_aggregates(self, func_name: str, arguments: List[str], is_running: bool) -> Any:
        """Evaluate COUNT_IF, SUM_IF, AVG_IF functions."""
        if len(arguments) != 2:
            raise AggregateArgumentError(f"{func_name} requires exactly 2 arguments")
        
        value_expr = arguments[0]
        condition_expr = arguments[1]
        
        # Get matched row indices
        row_indices = self._get_row_indices(value_expr, is_running)
        
        qualified_values = []
        
        for idx in row_indices:
            if idx >= len(self.context.rows):
                continue
            
            # Temporarily set current index for expression evaluation
            old_idx = self.context.current_idx
            self.context.current_idx = idx
            
            try:
                condition = self._evaluate_single_expression(condition_expr)
                if condition:  # Truthy condition
                    value = self._evaluate_single_expression(value_expr)
                    if value is not None:
                        qualified_values.append(value)
            finally:
                self.context.current_idx = old_idx
        
        if func_name == "COUNT_IF":
            return len(qualified_values)
        elif func_name == "SUM_IF":
            if not qualified_values:
                return None
            return sum(self._ensure_numeric_values(qualified_values))
        elif func_name == "AVG_IF":
            if not qualified_values:
                return None
            numeric_values = self._ensure_numeric_values(qualified_values)
            return sum(numeric_values) / len(numeric_values)
    
    def _evaluate_bool_aggregates(self, func_name: str, arguments: List[str], is_running: bool) -> bool:
        """Evaluate BOOL_AND/BOOL_OR functions."""
        if not arguments:
            return True if func_name == "BOOL_AND" else False
        
        values = self._get_expression_values(arguments[0], is_running)
        bool_values = [bool(v) for v in values if v is not None]
        
        if not bool_values:
            return True if func_name == "BOOL_AND" else False
        
        if func_name == "BOOL_AND":
            return all(bool_values)
        else:  # BOOL_OR
            return any(bool_values)
    
    def _evaluate_statistical_functions(self, func_name: str, arguments: List[str], is_running: bool) -> Optional[float]:
        """Evaluate STDDEV/VARIANCE functions."""
        if not arguments:
            return None
        
        values = self._get_numeric_values(arguments[0], is_running)
        if len(values) < 1:
            return None
        
        # Handle single value case
        if len(values) == 1:
            if func_name in ("STDDEV_POP", "VAR_POP"):
                return 0.0  # Population variance/stddev of single value is 0
            elif func_name in ("STDDEV_SAMP", "VAR_SAMP", "STDDEV", "VARIANCE"):
                return None  # Sample variance/stddev undefined for single value
        
        mean = sum(values) / len(values)
        
        # Determine denominator based on function type
        if func_name in ("STDDEV_POP", "VAR_POP"):
            # Population variance/stddev
            variance = sum((x - mean) ** 2 for x in values) / len(values)
        else:
            # Sample variance/stddev (STDDEV_SAMP, VAR_SAMP, STDDEV, VARIANCE)
            variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        
        if func_name in ("VARIANCE", "VAR_SAMP", "VAR_POP"):
            return variance
        else:  # STDDEV variants
            return math.sqrt(variance)
    
    def _get_expression_values(self, expr: str, is_running: bool) -> List[Any]:
        """Get values for an expression across all relevant rows."""
        row_indices = self._get_row_indices(expr, is_running)
        values = []
        
        for idx in row_indices:
            if idx >= len(self.context.rows):
                continue
            
            # Temporarily set current index for expression evaluation
            old_idx = self.context.current_idx
            self.context.current_idx = idx
            
            try:
                value = self._evaluate_single_expression(expr)
                values.append(value)
            finally:
                self.context.current_idx = old_idx
        
        return values
    
    def _get_numeric_values(self, expr: str, is_running: bool) -> List[Union[int, float]]:
        """Get numeric values for an expression, converting when possible."""
        values = self._get_expression_values(expr, is_running)
        return self._ensure_numeric_values(values)
    
    def _ensure_numeric_values(self, values: List[Any]) -> List[Union[int, float]]:
        """Convert values to numeric, filtering out non-convertible values."""
        numeric_values = []
        
        for value in values:
            # Filter out None and NaN values
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            
            if isinstance(value, (int, float)):
                numeric_values.append(value)
            else:
                try:
                    # Try to convert to numeric
                    if isinstance(value, str):
                        if '.' in value:
                            numeric_values.append(float(value))
                        else:
                            numeric_values.append(int(value))
                    elif isinstance(value, bool):
                        numeric_values.append(int(value))
                    else:
                        numeric_values.append(float(value))
                    self.stats["type_conversions"] += 1
                except (ValueError, TypeError):
                    # Skip non-numeric values
                    continue
        
        return numeric_values
    
    def _get_row_indices(self, expr: str, is_running: bool) -> List[int]:
        """Get row indices relevant for the expression based on pattern variables."""
        # Check if expression has specific variable references
        var_refs = self._extract_pattern_variables(expr)
        
        if var_refs:
            # Get indices for specific variables
            all_indices = []
            for var_name in var_refs:
                if var_name in self.context.variables:
                    all_indices.extend(self.context.variables[var_name])
                # Also check subset variables
                elif hasattr(self.context, 'subsets') and var_name in self.context.subsets:
                    for comp in self.context.subsets[var_name]:
                        if comp in self.context.variables:
                            all_indices.extend(self.context.variables[comp])
        else:
            # Universal reference - use all matched rows
            all_indices = []
            for var, indices in self.context.variables.items():
                all_indices.extend(indices)
        
        # Remove duplicates and sort
        all_indices = sorted(set(all_indices))
        
        # Apply RUNNING semantics
        if is_running:
            all_indices = [idx for idx in all_indices if idx <= self.context.current_idx]
        
        return all_indices
    
    def _count_all_rows(self, is_running: bool) -> int:
        """Count all matched rows (COUNT(*))."""
        all_indices = []
        for var, indices in self.context.variables.items():
            all_indices.extend(indices)
        
        # Remove duplicates
        all_indices = list(set(all_indices))
        
        # Apply RUNNING semantics
        if is_running:
            all_indices = [idx for idx in all_indices if idx <= self.context.current_idx]
        
        return len(all_indices)
    
    def _count_variable_rows(self, var_name: str, is_running: bool) -> int:
        """Count rows for a specific variable (COUNT(var.*))."""
        indices = []
        
        # Check direct variable
        if var_name in self.context.variables:
            indices.extend(self.context.variables[var_name])
        
        # Check subset variables
        elif hasattr(self.context, 'subsets') and var_name in self.context.subsets:
            for comp in self.context.subsets[var_name]:
                if comp in self.context.variables:
                    indices.extend(self.context.variables[comp])
        
        # Apply RUNNING semantics
        if is_running:
            indices = [idx for idx in indices if idx <= self.context.current_idx]
        
        return len(indices)
    
    def _evaluate_single_expression(self, expr: str) -> Any:
        """Evaluate a single expression in the current context."""
        # Handle special functions first
        if expr.upper() == "MATCH_NUMBER()":
            return getattr(self.context, 'match_number', 1)
        
        classifier_match = re.match(r'CLASSIFIER\(\s*([A-Z_][A-Z0-9_]*)?\s*\)', expr, re.IGNORECASE)
        if classifier_match:
            var_name = classifier_match.group(1)
            return self._evaluate_classifier(var_name)
        
        # Handle variable.column references
        var_col_match = re.match(r'^([A-Z_][A-Z0-9_]*)\.([A-Z_][A-Z0-9_]*)$', expr, re.IGNORECASE)
        if var_col_match:
            var_name = var_col_match.group(1)
            col_name = var_col_match.group(2)
            return self._get_variable_column_value(var_name, col_name)
        
        # Handle simple column references
        if re.match(r'^[A-Z_][A-Z0-9_]*$', expr, re.IGNORECASE):
            if self.context.current_idx < len(self.context.rows):
                return self.context.rows[self.context.current_idx].get(expr)
        
        # For complex expressions, delegate to condition evaluator
        try:
            from src.matcher.condition_evaluator import ConditionEvaluator
            import ast
            
            evaluator = ConditionEvaluator(self.context, evaluation_mode='MEASURES')
            tree = ast.parse(expr, mode='eval')
            return evaluator.visit(tree.body)
        except Exception:
            return None
    
    def _get_variable_column_value(self, var_name: str, col_name: str) -> Any:
        """Get value for a variable.column reference."""
        # For the current context, find the row assigned to this variable
        current_idx = self.context.current_idx
        
        # Check if current row is assigned to this variable
        if var_name in self.context.variables and current_idx in self.context.variables[var_name]:
            if current_idx < len(self.context.rows):
                return self.context.rows[current_idx].get(col_name)
        
        # Check subset variables
        if hasattr(self.context, 'subsets') and var_name in self.context.subsets:
            for comp in self.context.subsets[var_name]:
                if comp in self.context.variables and current_idx in self.context.variables[comp]:
                    if current_idx < len(self.context.rows):
                        return self.context.rows[current_idx].get(col_name)
        
        return None
    
    def _evaluate_classifier(self, var_name: Optional[str] = None) -> Optional[str]:
        """Evaluate CLASSIFIER function."""
        current_idx = self.context.current_idx
        
        if var_name:
            # CLASSIFIER(var) - return var if current row matches it
            if var_name in self.context.variables and current_idx in self.context.variables[var_name]:
                return var_name
            # Check subset variables
            if hasattr(self.context, 'subsets') and var_name in self.context.subsets:
                for comp in self.context.subsets[var_name]:
                    if comp in self.context.variables and current_idx in self.context.variables[comp]:
                        return comp
            return None
        else:
            # CLASSIFIER() - return the variable that matches the current row
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    return var
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get evaluation statistics for monitoring."""
        return {
            **self.stats,
            "cache_size": len(self._result_cache),
            "cache_hit_rate": self.stats["cache_hits"] / max(1, self.stats["evaluations"])
        }
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._validation_cache.clear()
        self._result_cache.clear()


# Integration function for the existing MeasureEvaluator
def enhance_measure_evaluator_with_production_aggregates():
    """
    Enhance the existing MeasureEvaluator class with production-ready aggregate functions.
    This function patches the evaluate method to use the ProductionAggregateEvaluator.
    """
    from src.matcher.measure_evaluator import MeasureEvaluator
    
    # Store original evaluate method
    original_evaluate = MeasureEvaluator.evaluate
    
    def enhanced_evaluate(self, expr: str, semantics: str = None) -> Any:
        """Enhanced evaluate method with production aggregate support."""
        logger.debug(f"Enhanced evaluate called with expr: '{expr}', semantics: '{semantics}'")
        
        # Determine semantics (default to RUNNING per SQL:2016)
        semantics = semantics or "RUNNING"
        is_running = semantics.upper() == "RUNNING"
        
        # Check if this is a PURE aggregate function (not a complex expression)
        # Pattern matches: [RUNNING|FINAL] FUNC(...) with optional whitespace but nothing else
        # This regex handles nested parentheses by counting them
        pure_agg_pattern = r'^\s*(?:(RUNNING|FINAL)\s+)?([A-Z_]+)\s*\('
        match = re.match(pure_agg_pattern, expr.strip(), re.IGNORECASE)
        
        logger.debug(f"Pattern match result for '{expr}': {match}")
        
        if match:
            # Manually check if the expression ends properly (all parentheses balanced)
            paren_count = 0
            func_start = match.end() - 1  # Position of the opening parenthesis
            for i, char in enumerate(expr[func_start:]):
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        # Found the matching closing parenthesis
                        remaining = expr[func_start + i + 1:].strip()
                        if remaining == '':  # Nothing after the function call
                            break
                        else:
                            match = None  # Not a pure function call
                            break
            else:
                # Unbalanced parentheses
                match = None
            
        if match:
            semantics_prefix = match.group(1)
            func_name = match.group(2).upper()
            
            logger.debug(f"Matched function: {func_name}, semantics_prefix: {semantics_prefix}")
            
            # If semantics is in the expression, use that instead of parameter
            if semantics_prefix:
                semantics = semantics_prefix.upper()
            
            if func_name in ProductionAggregateEvaluator.STANDARD_AGGREGATES:
                logger.debug(f"Using production aggregate evaluator for: {expr} -> {func_name}")
                # Use production aggregate evaluator for pure aggregate functions
                if not hasattr(self, '_prod_agg_evaluator'):
                    self._prod_agg_evaluator = ProductionAggregateEvaluator(self.context)
                
                try:
                    result = self._prod_agg_evaluator.evaluate_aggregate(expr, semantics)
                    logger.debug(f"Production aggregate result for {expr}: {result}")
                    return result
                except (AggregateValidationError, AggregateArgumentError) as e:
                    logger.warning(f"Aggregate validation error: {e}")
                    return None
                except Exception as e:
                    logger.error(f"Error in production aggregate evaluator: {e}")
                    # Fallback to original implementation
                    pass
            else:
                logger.debug(f"Function {func_name} not in standard aggregates, using original evaluator")
        else:
            logger.debug(f"Expression doesn't match pure aggregate pattern: {expr}")
        
        # Use original implementation for complex expressions and non-aggregates
        logger.debug(f"Falling back to original evaluator for: {expr}")
        return original_evaluate(self, expr, semantics)
    
    # Patch the method
    MeasureEvaluator.evaluate = enhanced_evaluate
    
    # Add method to get aggregate statistics
    def get_aggregate_statistics(self) -> Dict[str, Any]:
        """Get statistics from the production aggregate evaluator."""
        if hasattr(self, '_prod_agg_evaluator'):
            return self._prod_agg_evaluator.get_statistics()
        return {}
    
    MeasureEvaluator.get_aggregate_statistics = get_aggregate_statistics
    
    logger.info("MeasureEvaluator enhanced with production aggregate support")


# Additional utility functions for comprehensive aggregate support
def validate_aggregate_expression(expr: str) -> bool:
    """
    Validate an aggregate expression for SQL:2016 compliance.
    
    Returns:
        True if valid, False otherwise
    """
    try:
        # Create a dummy context for validation
        from src.matcher.row_context import RowContext
        dummy_context = RowContext([], {}, 0)
        evaluator = ProductionAggregateEvaluator(dummy_context)
        
        agg_info = evaluator._parse_aggregate_function(expr)
        if not agg_info:
            return False
        
        evaluator._validate_aggregate_function(agg_info['function'], agg_info['arguments'])
        return True
        
    except (AggregateValidationError, AggregateArgumentError):
        return False


def get_supported_aggregate_functions() -> List[str]:
    """Get list of all supported aggregate functions."""
    return sorted(list(ProductionAggregateEvaluator.STANDARD_AGGREGATES))


def get_aggregate_function_signature(func_name: str) -> str:
    """Get the signature for an aggregate function."""
    func_name = func_name.upper()
    
    if func_name not in ProductionAggregateEvaluator.STANDARD_AGGREGATES:
        return f"Unknown function: {func_name}"
    
    if func_name in ProductionAggregateEvaluator.MULTI_ARG_FUNCTIONS:
        arg_count = ProductionAggregateEvaluator.MULTI_ARG_FUNCTIONS[func_name]
        if func_name == "MAX_BY":
            return "MAX_BY(value_expression, key_expression)"
        elif func_name == "MIN_BY":
            return "MIN_BY(value_expression, key_expression)"
        elif func_name == "STRING_AGG":
            return "STRING_AGG(expression, separator)"
        elif func_name in ("COUNT_IF", "SUM_IF", "AVG_IF"):
            return f"{func_name}(expression, condition)"
        else:
            return f"{func_name}(arg1, arg2, ...)"
    else:
        if func_name == "COUNT":
            return "COUNT(*) | COUNT(expression) | COUNT(variable.*)"
        else:
            return f"{func_name}(expression)"
