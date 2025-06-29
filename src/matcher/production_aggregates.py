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
        'FIRST_VALUE', 'LAST_VALUE', 'COUNT_DISTINCT',
        'APPROX_DISTINCT', 'APPROX_PERCENTILE', 'GEOMETRIC_MEAN', 'HARMONIC_MEAN'
    }
    
    # Mathematical functions that can wrap aggregates
    MATHEMATICAL_FUNCTIONS = {
        'SQRT', 'ABS', 'FLOOR', 'CEIL', 'ROUND'
    }
    
    # Functions that support RUNNING semantics by default
    RUNNING_BY_DEFAULT = {
        'SUM', 'COUNT', 'MIN', 'MAX', 'AVG', 'ARRAY_AGG', 'STRING_AGG',
        'COUNT_IF', 'SUM_IF', 'AVG_IF', 'BOOL_AND', 'BOOL_OR', 'GEOMETRIC_MEAN', 'HARMONIC_MEAN'
    }
    
    # Functions that require numeric arguments
    NUMERIC_FUNCTIONS = {
        'SUM', 'AVG', 'STDDEV', 'VARIANCE', 'STDDEV_SAMP', 'STDDEV_POP',
        'VAR_SAMP', 'VAR_POP', 'SUM_IF', 'AVG_IF', 'GEOMETRIC_MEAN', 'HARMONIC_MEAN'
    }
    
    # Functions that support multiple arguments
    MULTI_ARG_FUNCTIONS = {
        'MAX_BY': 2, 'MIN_BY': 2, 'STRING_AGG': 2, 'COUNT_IF': 1, 'SUM_IF': 2, 'AVG_IF': 2,
        'APPROX_PERCENTILE': 2
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
                
                # First check if this is a mathematical function
                math_pattern = r'^\s*([A-Z_]+)\s*\('
                math_match = re.match(math_pattern, expr.strip(), re.IGNORECASE)
                if math_match:
                    func_name = math_match.group(1).upper()
                    if func_name in self.MATHEMATICAL_FUNCTIONS:
                        # Parse the function to get arguments
                        agg_info = self._parse_aggregate_function(expr)
                        if agg_info:
                            arguments = agg_info['arguments']
                            filter_condition = agg_info.get('filter')
                            is_running = semantics == "RUNNING"
                            result = self._evaluate_mathematical_functions(func_name, arguments, is_running, filter_condition)
                            logger.debug(f"PROD_AGG_FINAL: mathematical function '{expr}' evaluated to: {result}")
                            return result
                
                # First check if this is an arithmetic expression between aggregates
                arithmetic_result = self._evaluate_arithmetic_expression(expr, semantics)
                if arithmetic_result is not None:
                    logger.debug(f"PROD_AGG_FINAL: arithmetic expression '{expr}' evaluated to: {arithmetic_result}")
                    return arithmetic_result
                
                # Parse the aggregate function
                agg_info = self._parse_aggregate_function(expr)
                if not agg_info:
                    raise AggregateValidationError(
                        f"Invalid aggregate expression: {expr}",
                        None, "Check function syntax", "AGG_PARSE_001"
                    )
                
                func_name = agg_info['function'].upper()
                arguments = agg_info['arguments']
                filter_condition = agg_info.get('filter')  # Get filter condition if present
                
                # Update function call statistics
                self.stats["function_counts"][func_name] += 1
                
                # Validate the function and arguments
                self._validate_aggregate_function(func_name, arguments)
                
                # Determine evaluation mode
                is_running = semantics == "RUNNING"
                
                # Evaluate based on function type with enhanced error handling
                try:
                    if func_name == "COUNT":
                        result = self._evaluate_count(arguments, is_running, filter_condition)
                    elif func_name == "SUM":
                        result = self._evaluate_sum(arguments, is_running, filter_condition)
                    elif func_name in ("MIN", "MAX"):
                        result = self._evaluate_min_max(func_name, arguments, is_running, filter_condition)
                    elif func_name == "AVG":
                        result = self._evaluate_avg(arguments, is_running, filter_condition)
                    elif func_name == "ARRAY_AGG":
                        result = self._evaluate_array_agg(arguments, is_running, filter_condition)
                    elif func_name == "STRING_AGG":
                        result = self._evaluate_string_agg(arguments, is_running, filter_condition)
                    elif func_name in ("MAX_BY", "MIN_BY"):
                        result = self._evaluate_by_functions(func_name, arguments, is_running, filter_condition)
                    elif func_name in ("COUNT_IF", "SUM_IF", "AVG_IF"):
                        result = self._evaluate_conditional_aggregates(func_name, arguments, is_running, filter_condition)
                    elif func_name in ("BOOL_AND", "BOOL_OR"):
                        result = self._evaluate_bool_aggregates(func_name, arguments, is_running, filter_condition)
                    elif func_name in ("STDDEV", "VARIANCE", "STDDEV_SAMP", "STDDEV_POP", "VAR_SAMP", "VAR_POP"):
                        result = self._evaluate_statistical_functions(func_name, arguments, is_running, filter_condition)
                    elif func_name == "LISTAGG":
                        result = self._evaluate_listagg(arguments, is_running, filter_condition)
                    elif func_name in ("FIRST_VALUE", "LAST_VALUE"):
                        result = self._evaluate_window_functions(func_name, arguments, is_running, filter_condition)
                    elif func_name in ("APPROX_DISTINCT", "APPROX_PERCENTILE"):
                        result = self._evaluate_approximate_functions(func_name, arguments, is_running, filter_condition)
                    elif func_name in ("GEOMETRIC_MEAN", "HARMONIC_MEAN"):
                        result = self._evaluate_statistical_means(func_name, arguments, is_running, filter_condition)
                    elif func_name in self.MATHEMATICAL_FUNCTIONS:
                        result = self._evaluate_mathematical_functions(func_name, arguments, is_running, filter_condition)
                    else:
                        raise AggregateValidationError(
                            f"Unsupported aggregate function: {func_name}",
                            func_name, "Check supported functions", "AGG_UNSUPPORTED"
                        )
                    
                    # Cache the result (with size limit)
                    if len(self._result_cache) < MAX_CACHE_SIZE:
                        self._result_cache[cache_key] = result
                    
                    logger.debug(f"PROD_AGG_FINAL: evaluate_aggregate returning: {result} (type: {type(result)})")
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
        Parse an aggregate function expression into components, including FILTER clauses.
        
        Returns:
            Dict with 'function', 'arguments', and optionally 'filter' keys, or None if invalid
        """
        # Remove RUNNING/FINAL prefix if present
        clean_expr = re.sub(r'^\s*(RUNNING|FINAL)\s+', '', expr.strip(), flags=re.IGNORECASE)
        
        # Check for FILTER clause first - pattern: function(...) FILTER (WHERE condition)
        filter_pattern = r'^(.+?)\s+FILTER\s*\(\s*WHERE\s+(.+?)\s*\)$'
        filter_match = re.match(filter_pattern, clean_expr, re.IGNORECASE)
        
        filter_condition = None
        if filter_match:
            # Extract the function part and filter condition
            function_part = filter_match.group(1).strip()
            filter_condition = filter_match.group(2).strip()
            clean_expr = function_part
            logger.debug(f"Found FILTER clause: {filter_condition}")
        
        # Now parse the main aggregate function
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
        
        result = {
            'function': func_name,
            'arguments': arguments
        }
        
        # Add filter condition if present
        if filter_condition:
            result['filter'] = filter_condition
        
        logger.debug(f"Parsed aggregate function {func_name} with args: {arguments}" + 
                    (f", filter: {filter_condition}" if filter_condition else ""))
        
        return result
    
    def _parse_function_arguments(self, args_str: str) -> List[str]:
        """
        Parse function arguments handling nested parentheses, commas, and ORDER BY clauses.
        """
        if not args_str:
            return []
        
        # Check for ORDER BY clause in aggregate functions like array_agg(expr ORDER BY col)
        order_by_match = re.match(r'^(.+?)\s+ORDER\s+BY\s+(.+)$', args_str, re.IGNORECASE)
        if order_by_match:
            main_expr = order_by_match.group(1).strip()
            order_clause = order_by_match.group(2).strip()
            # Return as special format that includes ORDER BY information
            return [main_expr, f"ORDER_BY:{order_clause}"]
        
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
        
        # Handle ORDER BY clause for ARRAY_AGG and STRING_AGG
        has_order_by = len(arguments) > 1 and arguments[1].startswith("ORDER_BY:")
        effective_arg_count = len(arguments) - (1 if has_order_by else 0)
        
        # Validate argument count
        if func_name in self.MULTI_ARG_FUNCTIONS:
            expected_args = self.MULTI_ARG_FUNCTIONS[func_name]
            if effective_arg_count != expected_args:
                raise AggregateArgumentError(
                    f"{func_name} requires exactly {expected_args} arguments, got {effective_arg_count}"
                )
        elif func_name == "COUNT":
            if effective_arg_count == 0:
                raise AggregateArgumentError("COUNT requires at least one argument")
        elif func_name in ("ARRAY_AGG", "STRING_AGG") and has_order_by:
            # Special case: ARRAY_AGG and STRING_AGG can have ORDER BY as second argument
            if effective_arg_count != 1:
                raise AggregateArgumentError(f"{func_name} with ORDER BY requires exactly one expression argument")
        else:
            if effective_arg_count != 1:
                raise AggregateArgumentError(f"{func_name} requires exactly one argument")
        
        # Validate argument consistency for pattern variables
        if len(arguments) > 1 and not has_order_by:
            self._validate_argument_consistency(arguments)
        
        # Check for illegal nesting (no aggregates in navigation functions)
        for arg in arguments:
            if not arg.startswith("ORDER_BY:"):
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
    
    def _evaluate_arithmetic_expression(self, expr: str, semantics: str) -> Any:
        """
        Evaluate arithmetic expressions between aggregate functions.
        
        Handles expressions like: sum(A.x) / sum(A.y), sum(A.x) + count(B.*), etc.
        
        Args:
            expr: The arithmetic expression containing aggregates
            semantics: "RUNNING" or "FINAL"
            
        Returns:
            Result of the arithmetic operation or None if not an arithmetic expression
        """
        import re
        import ast
        import operator
        
        # Check if this contains arithmetic operators between aggregates
        # Pattern to match aggregate functions: FUNC_NAME(arguments)
        agg_pattern = r'\b([A-Z_]+)\s*\([^)]*\)'
        
        # Find all aggregate function calls in the expression
        agg_matches = list(re.finditer(agg_pattern, expr, re.IGNORECASE))
        
        # Check if there are arithmetic operators
        arithmetic_ops = ['+', '-', '*', '/', '%', '**']
        has_arithmetic = any(op in expr for op in arithmetic_ops)
        
        # If there are no aggregates or no arithmetic, this isn't an arithmetic expression
        if len(agg_matches) == 0 or not has_arithmetic:
            return None
            
        # Handle single aggregate with arithmetic (e.g., AVG(value) * 0.9)
        if len(agg_matches) == 1:
            # Check if the aggregate is part of a larger arithmetic expression
            agg_match = agg_matches[0]
            agg_start, agg_end = agg_match.span()
            
            # Check if there's arithmetic before or after the aggregate
            before_agg = expr[:agg_start].strip()
            after_agg = expr[agg_end:].strip()
            
            has_arithmetic_before = any(op in before_agg for op in arithmetic_ops)
            has_arithmetic_after = any(op in after_agg for op in arithmetic_ops)
            
            if not (has_arithmetic_before or has_arithmetic_after):
                return None
            
        logger.debug(f"Detected arithmetic expression between aggregates: {expr}")
        
        try:
            # Parse the expression into an AST to evaluate it properly
            # First, replace each aggregate function call with a placeholder
            expr_with_placeholders = expr
            agg_values = {}
            
            for i, match in enumerate(agg_matches):
                agg_expr = match.group(0)
                placeholder = f"__AGG_{i}__"
                
                # Evaluate this individual aggregate
                try:
                    agg_value = self._evaluate_single_aggregate(agg_expr, semantics)
                    agg_values[placeholder] = agg_value
                    expr_with_placeholders = expr_with_placeholders.replace(agg_expr, placeholder, 1)
                except Exception as e:
                    logger.warning(f"Failed to evaluate aggregate '{agg_expr}': {e}")
                    return None
            
            logger.debug(f"Expression with placeholders: {expr_with_placeholders}")
            logger.debug(f"Aggregate values: {agg_values}")
            
            # Parse and evaluate the arithmetic expression
            tree = ast.parse(expr_with_placeholders, mode='eval')
            result = self._eval_arithmetic_ast(tree.body, agg_values)
            
            logger.debug(f"Arithmetic expression '{expr}' evaluated to: {result}")
            return result
            
        except Exception as e:
            logger.warning(f"Failed to evaluate arithmetic expression '{expr}': {e}")
            return None
    
    def _evaluate_single_aggregate(self, agg_expr: str, semantics: str) -> Any:
        """
        Evaluate a single aggregate function call.
        
        This method handles individual aggregate functions without arithmetic operations.
        """
        # Parse the aggregate function
        agg_info = self._parse_aggregate_function(agg_expr)
        if not agg_info:
            raise AggregateValidationError(
                f"Invalid aggregate expression: {agg_expr}",
                None, "Check function syntax", "AGG_PARSE_001"
            )
        
        func_name = agg_info['function'].upper()
        arguments = agg_info['arguments']
        filter_condition = agg_info.get('filter')
        
        # Validate the function and arguments
        self._validate_aggregate_function(func_name, arguments)
        
        # Determine evaluation mode
        is_running = semantics == "RUNNING"
        
        # Evaluate based on function type
        if func_name == "COUNT":
            return self._evaluate_count(arguments, is_running, filter_condition)
        elif func_name == "SUM":
            return self._evaluate_sum(arguments, is_running, filter_condition)
        elif func_name in ("MIN", "MAX"):
            return self._evaluate_min_max(func_name, arguments, is_running, filter_condition)
        elif func_name == "AVG":
            return self._evaluate_avg(arguments, is_running, filter_condition)
        elif func_name == "ARRAY_AGG":
            return self._evaluate_array_agg(arguments, is_running, filter_condition)
        elif func_name == "STRING_AGG":
            return self._evaluate_string_agg(arguments, is_running, filter_condition)
        elif func_name in ("MAX_BY", "MIN_BY"):
            return self._evaluate_by_functions(func_name, arguments, is_running, filter_condition)
        elif func_name in ("COUNT_IF", "SUM_IF", "AVG_IF"):
            return self._evaluate_conditional_aggregates(func_name, arguments, is_running, filter_condition)
        elif func_name in ("BOOL_AND", "BOOL_OR"):
            return self._evaluate_bool_aggregates(func_name, arguments, is_running, filter_condition)
        elif func_name in ("STDDEV", "VARIANCE", "STDDEV_SAMP", "STDDEV_POP", "VAR_SAMP", "VAR_POP"):
            return self._evaluate_statistical_functions(func_name, arguments, is_running, filter_condition)
        elif func_name == "LISTAGG":
            return self._evaluate_listagg(arguments, is_running, filter_condition)
        elif func_name in ("FIRST_VALUE", "LAST_VALUE"):
            return self._evaluate_window_functions(func_name, arguments, is_running, filter_condition)
        elif func_name in ("APPROX_DISTINCT", "APPROX_PERCENTILE"):
            return self._evaluate_approximate_functions(func_name, arguments, is_running, filter_condition)
        elif func_name in ("GEOMETRIC_MEAN", "HARMONIC_MEAN"):
            return self._evaluate_statistical_means(func_name, arguments, is_running, filter_condition)
        else:
            raise AggregateValidationError(
                f"Unsupported aggregate function: {func_name}",
                func_name, "Check supported functions", "AGG_UNSUPPORTED"
            )
    
    def _eval_arithmetic_ast(self, node, agg_values):
        """
        Recursively evaluate AST nodes for arithmetic expressions with aggregate placeholders.
        """
        import ast
        import operator
        
        if isinstance(node, ast.BinOp):
            left = self._eval_arithmetic_ast(node.left, agg_values)
            right = self._eval_arithmetic_ast(node.right, agg_values)
            
            # Handle None values (SQL NULL semantics)
            if left is None or right is None:
                return None
            
            op_map = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.FloorDiv: operator.floordiv,
                ast.Mod: operator.mod,
                ast.Pow: operator.pow,
            }
            
            op = op_map.get(type(node.op))
            if op:
                try:
                    result = op(left, right)
                    return result
                except ZeroDivisionError:
                    return None  # SQL NULL for division by zero
                except Exception:
                    return None
                    
        elif isinstance(node, ast.Name):
            # This should be one of our aggregate placeholders
            placeholder = node.id
            return agg_values.get(placeholder)
            
        elif isinstance(node, ast.Constant):
            # Literal number
            return node.value
            
        elif isinstance(node, ast.Num):  # For older Python versions
            return node.n
            
        return None

    def _evaluate_count(self, arguments: List[str], is_running: bool, filter_condition: str = None) -> int:
        """Evaluate COUNT function with all SQL:2016 variants including DISTINCT and FILTER support."""
        if not arguments:
            return 0
        
        arg = arguments[0]
        
        # Get filter mask if filter condition is specified
        filter_mask = None
        if filter_condition:
            filter_mask = self._apply_filter_condition(filter_condition, is_running)
        
        # COUNT(*) - count all matched rows
        if arg == "*":
            if filter_mask:
                return sum(filter_mask)
            else:
                return self._count_all_rows(is_running)
        
        # COUNT(DISTINCT expression) - count distinct non-null values
        distinct_match = re.match(r'^\s*DISTINCT\s+(.+)$', arg, re.IGNORECASE)
        if distinct_match:
            expr = distinct_match.group(1).strip()
            values = self._get_expression_values(expr, is_running, filter_mask)
            non_null_values = [v for v in values if v is not None]
            return len(set(non_null_values))  # Use set to get distinct values
        
        # COUNT(var.*) - count rows for specific variable
        var_wildcard_match = re.match(r'^([A-Z_][A-Z0-9_]*)\.\*$', arg, re.IGNORECASE)
        if var_wildcard_match:
            var_name = var_wildcard_match.group(1).upper()
            if filter_mask:
                # Apply filter mask to variable row count
                var_rows = self._get_variable_row_indices(var_name, is_running)
                filtered_rows = [i for i, include in enumerate(filter_mask) if include and i in var_rows]
                return len(filtered_rows)
            else:
                return self._count_variable_rows(var_name, is_running)
        
        # COUNT(expression) - count non-null values
        values = self._get_expression_values(arg, is_running, filter_mask)
        # Handle both None and NaN values properly
        return len([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))])
    
    def _evaluate_sum(self, arguments: List[str], is_running: bool, filter_condition: str = None) -> Union[int, float, None]:
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
    
    def _evaluate_min_max(self, func_name: str, arguments: List[str], is_running: bool, filter_condition: str = None) -> Any:
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
    
    def _evaluate_avg(self, arguments: List[str], is_running: bool, filter_condition: str = None) -> Optional[float]:
        """Evaluate AVG function with optional FILTER support."""
        if not arguments:
            logger.debug(f"AVG: No arguments, returning None")
            return None
        
        # Get filter mask if filter condition is specified
        filter_mask = None
        if filter_condition:
            filter_mask = self._apply_filter_condition(filter_condition, is_running)
        
        values = self._get_numeric_values(arguments[0], is_running, filter_mask)
        logger.debug(f"AVG: Got numeric values: {values}")
        if not values:
            logger.info(f"AVG_DEBUG: Empty values list, returning None")
            return None
        
        result = sum(values) / len(values)
        logger.debug(f"AVG: Calculated result: {result}")
        return result
    
    def _evaluate_array_agg(self, arguments: List[str], is_running: bool, filter_condition: str = None) -> List[Any]:
        """Evaluate ARRAY_AGG function with optional ORDER BY support."""
        if not arguments:
            return []
        
        # Get filter mask if filter condition is specified  
        filter_mask = None
        if filter_condition:
            filter_mask = self._apply_filter_condition(filter_condition, is_running)
        
        # Check if there's an ORDER BY clause
        if len(arguments) > 1 and arguments[1].startswith("ORDER_BY:"):
            value_expr = arguments[0]
            order_clause = arguments[1][9:]  # Remove "ORDER_BY:" prefix
            
            # Parse ORDER BY clause (column [ASC|DESC])
            order_parts = order_clause.strip().split()
            order_column = order_parts[0]
            order_direction = order_parts[1].upper() if len(order_parts) > 1 else 'ASC'
            
            # Get matched row indices using same logic as regular aggregates
            row_indices = self._get_row_indices(value_expr, is_running)
            
            if not row_indices:
                return []
            
            # Get values and order keys for each row
            value_order_pairs = []
            for idx in row_indices:
                if idx >= len(self.context.rows):
                    continue
                
                # Temporarily set current index for expression evaluation
                old_idx = self.context.current_idx
                self.context.current_idx = idx
                
                try:
                    # Get the value to include in array
                    value_result = self._evaluate_single_expression(value_expr)
                    # Get the value to order by
                    order_result = self._evaluate_single_expression(order_column)
                    
                    if value_result is not None and order_result is not None:
                        value_order_pairs.append((value_result, order_result))
                
                except Exception as e:
                    logger.warning(f"Failed to evaluate array_agg expressions for row {idx}: {e}")
                finally:
                    self.context.current_idx = old_idx
            
            # Sort by order key
            reverse_order = (order_direction == 'DESC')
            value_order_pairs.sort(key=lambda x: x[1], reverse=reverse_order)
            
            # Return just the values in sorted order
            return [pair[0] for pair in value_order_pairs]
        
        else:
            # Standard ARRAY_AGG without ORDER BY
            values = self._get_expression_values(arguments[0], is_running)
            # Filter out nulls for array aggregation
            return [v for v in values if v is not None]
    
    def _evaluate_string_agg(self, arguments: List[str], is_running: bool, filter_condition: str = None) -> Optional[str]:
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
    
    def _evaluate_by_functions(self, func_name: str, arguments: List[str], is_running: bool, filter_condition: str = None) -> Any:
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
    
    def _evaluate_conditional_aggregates(self, func_name: str, arguments: List[str], is_running: bool, filter_condition: str = None) -> Any:
        """Evaluate COUNT_IF, SUM_IF, AVG_IF functions."""
        # COUNT_IF takes 1 argument (condition), SUM_IF and AVG_IF take 2 (value, condition)
        if func_name == "COUNT_IF":
            if len(arguments) != 1:
                raise AggregateArgumentError(f"COUNT_IF requires exactly 1 argument, got {len(arguments)}")
            condition_expr = arguments[0]
            value_expr = "1"  # COUNT_IF counts rows, so we use a constant value
        else:
            if len(arguments) != 2:
                raise AggregateArgumentError(f"{func_name} requires exactly 2 arguments, got {len(arguments)}")
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
    
    def _evaluate_bool_aggregates(self, func_name: str, arguments: List[str], is_running: bool, filter_condition: str = None) -> bool:
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
    
    def _evaluate_statistical_functions(self, func_name: str, arguments: List[str], is_running: bool, filter_condition: str = None) -> Optional[float]:
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
    
    def _get_aggregate_values(self, expr: str, is_running: bool, filter_condition: str = None) -> List[Any]:
        """Get values for an aggregate expression across all relevant rows, optionally filtered."""
        # Get filter mask if filter condition is specified
        filter_mask = None
        if filter_condition:
            filter_mask = self._apply_filter_condition(filter_condition, is_running)
        
        return self._get_expression_values(expr, is_running, filter_mask)

    def _get_expression_values(self, expr: str, is_running: bool, filter_mask: List[bool] = None) -> List[Any]:
        """Get values for an expression across all relevant rows, optionally filtered."""
        row_indices = self._get_row_indices(expr, is_running)
        values = []
        
        for i, idx in enumerate(row_indices):
            if idx >= len(self.context.rows):
                continue
            
            # Apply filter mask if provided
            if filter_mask and i < len(filter_mask) and not filter_mask[i]:
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
    
    def _get_numeric_values(self, expr: str, is_running: bool, filter_mask: List[bool] = None) -> List[Union[int, float]]:
        """Get numeric values for an expression, converting when possible, optionally filtered."""
        values = self._get_expression_values(expr, is_running, filter_mask)
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
        
        # Handle numeric literals
        try:
            # Try integer first
            if expr.isdigit() or (expr.startswith('-') and expr[1:].isdigit()):
                return int(expr)
            # Try float
            return float(expr)
        except ValueError:
            pass
        
        # Handle simple comparison expressions (var.col >= number)
        comparison_match = re.match(r'^([A-Z_][A-Z0-9_]*\.[A-Z_][A-Z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*([+-]?\d+(?:\.\d+)?)$', expr, re.IGNORECASE)
        if comparison_match:
            var_expr = comparison_match.group(1)
            operator = comparison_match.group(2)
            value_str = comparison_match.group(3)
            
            # Get the variable value
            var_match = re.match(r'^([A-Z_][A-Z0-9_]*)\.([A-Z_][A-Z0-9_]*)$', var_expr, re.IGNORECASE)
            if var_match:
                var_name = var_match.group(1)
                col_name = var_match.group(2)
                var_value = self._get_variable_column_value(var_name, col_name)
                
                # Parse the comparison value
                try:
                    compare_value = int(value_str) if '.' not in value_str else float(value_str)
                except ValueError:
                    compare_value = value_str
                
                # Perform the comparison
                if var_value is None:
                    return False
                
                try:
                    if operator == '>=':
                        return var_value >= compare_value
                    elif operator == '<=':
                        return var_value <= compare_value
                    elif operator == '==':
                        return var_value == compare_value
                    elif operator == '!=':
                        return var_value != compare_value
                    elif operator == '>':
                        return var_value > compare_value
                    elif operator == '<':
                        return var_value < compare_value
                except TypeError:
                    return False
        
        # For complex expressions, try ConditionEvaluator first with original SQL syntax
        try:
            from src.matcher.condition_evaluator import ConditionEvaluator
            import ast
            
            logger.debug(f"Production aggregates evaluating complex expression: '{expr}' at row {self.context.current_idx}")
            
            # First try to evaluate with original SQL syntax (for navigation functions)
            evaluator = ConditionEvaluator(self.context, evaluation_mode='MEASURES')
            try:
                # Try parsing and evaluating the original expression directly
                tree = ast.parse(expr, mode='eval')
                result = evaluator.visit(tree.body)
                logger.debug(f"Original expression '{expr}' evaluated to: {result}")
                return result
            except SyntaxError:
                # If direct parsing fails, try SQL-to-Python conversion
                converted_expr = self._convert_sql_to_python(expr)
                if converted_expr != expr:
                    logger.debug(f"Converted SQL expression '{expr}' to '{converted_expr}'")
                
                tree = ast.parse(converted_expr, mode='eval')
                result = evaluator.visit(tree.body)
                logger.debug(f"Converted expression '{converted_expr}' evaluated to: {result}")
                return result
        except Exception as e:
            logger.warning(f"Failed to evaluate expression '{expr}': {e}")
            # Try simpler evaluation approach for arithmetic expressions
            return self._try_simple_arithmetic_evaluation(expr)
    
    def _try_simple_arithmetic_evaluation(self, expr: str) -> Any:
        """Try simple arithmetic evaluation as fallback when ConditionEvaluator fails."""
        try:
            # Handle simple arithmetic expressions manually
            import operator
            import ast
            
            logger.debug(f"Trying simple arithmetic evaluation for: '{expr}'")
            
            tree = ast.parse(expr, mode='eval')
            result = self._eval_ast_node(tree.body, ast, operator)
            
            logger.debug(f"Simple arithmetic result for '{expr}': {result}")
            return result
        except Exception as e:
            logger.warning(f"Simple arithmetic evaluation also failed for '{expr}': {e}")
            return None
    
    def _eval_ast_node(self, node, ast, operator):
        """Recursively evaluate AST nodes for simple arithmetic expressions."""
        if isinstance(node, ast.BinOp):
            left = self._eval_ast_node(node.left, ast, operator)
            right = self._eval_ast_node(node.right, ast, operator)
            
            if left is None or right is None:
                return None
            
            op_map = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.FloorDiv: operator.floordiv,
                ast.Mod: operator.mod,
                ast.Pow: operator.pow,
            }
            
            op = op_map.get(type(node.op))
            if op:
                result = op(left, right)
                logger.debug(f"Simple BinOp: {left} {type(node.op).__name__} {right} = {result}")
                return result
                
        elif isinstance(node, ast.Name):
            # Simple column reference
            column_name = node.id
            if self.context.current_idx < len(self.context.rows):
                value = self.context.rows[self.context.current_idx].get(column_name)
                logger.debug(f"Simple column '{column_name}' resolved to: {value}")
                return value
                
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # For older Python versions
            return node.n
            
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

    def _convert_sql_to_python(self, expr: str) -> str:
        """Convert SQL function syntax to Python-compatible syntax."""
        import re
        
        # Convert CASE WHEN expressions to Python conditional expressions
        converted = self._convert_case_when_to_python(expr)
        
        # Convert SQL CAST syntax: cast(value as type) -> CAST(value, 'TYPE')
        cast_pattern = r'cast\s*\(\s*([^,)]+)\s+as\s+([^)]+)\s*\)'
        def cast_replacer(match):
            value = match.group(1).strip()
            type_name = match.group(2).strip().upper()
            return f"CAST({value}, '{type_name}')"
        
        converted = re.sub(cast_pattern, cast_replacer, converted, flags=re.IGNORECASE)
        
        # Convert SQL NULL to Python None (for both null and NULL)
        converted = re.sub(r'\bnull\b', 'None', converted, flags=re.IGNORECASE)
        
        # Convert pattern variable dot notation: A.value -> value (when evaluating for variable A)
        # For now, we'll assume the context variable is set correctly by the caller
        pattern_var_pattern = r'\b([A-Z]+)\.(\w+)'
        def var_replacer(match):
            var = match.group(1)
            column = match.group(2)
            # For production, we'll simply use the column name
            # The context evaluator will handle variable resolution
            return column
        converted = re.sub(pattern_var_pattern, var_replacer, converted)
        
        # Convert navigation functions to uppercase for consistency
        nav_functions = ['first', 'last', 'prev', 'next']
        for func in nav_functions:
            pattern = rf'\b{func}\s*\('
            replacement = f'{func.upper()}('
            converted = re.sub(pattern, replacement, converted, flags=re.IGNORECASE)
        
        # Convert SQL functions to uppercase for consistency with MATH_FUNCTIONS
        sql_functions = ['concat', 'substr', 'substring', 'trim', 'ltrim', 'rtrim', 
                        'upper', 'lower', 'length', 'replace', 'left', 'right']
        
        for func in sql_functions:
            # Use word boundaries to avoid partial matches
            pattern = rf'\b{func}\s*\('
            replacement = f'{func.upper()}('
            converted = re.sub(pattern, replacement, converted, flags=re.IGNORECASE)
        
        # Convert SQL operators to Python operators using the dedicated method
        converted = self._convert_sql_operators_to_python(converted)
        
        # Handle % modulo operator - already correct in Python
        # SQL: value % 2 = 0 -> Python: value % 2 == 0 (handled by equality conversion above)
        
        logger.debug(f"SQL conversion: '{expr}' -> '{converted}'")
        return converted

    def _convert_case_when_to_python(self, expr: str) -> str:
        """
        Convert SQL CASE WHEN expressions to Python conditional expressions.
        
        Converts:
        - CASE WHEN condition THEN value ELSE default END -> (value if condition else default)
        - CASE WHEN cond1 THEN val1 WHEN cond2 THEN val2 ELSE default END -> (val1 if cond1 else (val2 if cond2 else default))
        """
        import re
        
        # Pattern to match CASE WHEN expressions
        case_pattern = r'CASE\s+(?:WHEN\s+([^T]+?)\s+THEN\s+([^W\s]+?)(?:\s+WHEN\s+([^T]+?)\s+THEN\s+([^W\s]+?))*)?(?:\s+ELSE\s+([^E]+?))?\s+END'
        
        def case_replacer(match_obj):
            full_match = match_obj.group(0)
            logger.debug(f"Converting CASE expression: {full_match}")
            
            # Find all WHEN clauses using a more robust approach
            when_pattern = r'WHEN\s+(.+?)\s+THEN\s+(.+?)(?=\s+(?:WHEN|ELSE|END))'
            when_matches = list(re.finditer(when_pattern, full_match, re.IGNORECASE))
            
            # Find ELSE clause
            else_pattern = r'ELSE\s+(.+?)(?=\s+END)'
            else_match = re.search(else_pattern, full_match, re.IGNORECASE)
            else_value = else_match.group(1).strip() if else_match else "None"
            
            # Convert SQL NULL to Python None
            if else_value.upper() == "NULL":
                else_value = "None"
            
            if not when_matches:
                logger.warning(f"No WHEN clauses found in CASE expression: {full_match}")
                return full_match
            
            # Build nested Python conditional expression
            result = else_value
            for when_match in reversed(when_matches):
                condition = when_match.group(1).strip()
                value = when_match.group(2).strip()
                
                # Convert SQL NULL to Python None
                if value.upper() == "NULL":
                    value = "None"
                
                # Convert SQL operators to Python
                condition = self._convert_sql_operators_to_python(condition)
                
                result = f"({value} if {condition} else {result})"
            
            logger.debug(f"Converted CASE to: {result}")
            return result
        
        # Apply the conversion
        converted = re.sub(case_pattern, case_replacer, expr, flags=re.IGNORECASE | re.DOTALL)
        
        # If no CASE expressions were found, try a simpler pattern for nested cases
        if converted == expr and 'CASE' in expr.upper():
            # Simple pattern for basic CASE WHEN ... THEN ... ELSE ... END
            simple_pattern = r'CASE\s+WHEN\s+(.+?)\s+THEN\s+(.+?)\s+ELSE\s+(.+?)\s+END'
            simple_match = re.search(simple_pattern, expr, re.IGNORECASE | re.DOTALL)
            if simple_match:
                condition = simple_match.group(1).strip()
                then_value = simple_match.group(2).strip()
                else_value = simple_match.group(3).strip()
                
                # Convert SQL NULL to Python None
                if then_value.upper() == "NULL":
                    then_value = "None"
                if else_value.upper() == "NULL":
                    else_value = "None"
                
                # Convert SQL operators to Python
                condition = self._convert_sql_operators_to_python(condition)
                
                result = f"({then_value} if {condition} else {else_value})"
                converted = expr.replace(simple_match.group(0), result)
                logger.debug(f"Simple CASE conversion: {expr} -> {converted}")
        
        return converted
    
    def _convert_sql_operators_to_python(self, condition: str) -> str:
        """Convert SQL operators to Python equivalents."""
        import re
        
        # First handle SQL IN operator 
        # Convert: expression IN (value1, value2, ...) -> expression in [value1, value2, ...]
        in_pattern = r'\b(\w+(?:\(\))?)\s+IN\s*\(\s*([^)]+)\s*\)'
        def in_replacer(match):
            expr = match.group(1)
            values = match.group(2)
            # Parse the values and wrap in square brackets
            values_list = [v.strip().strip("'\"") for v in values.split(',')]
            values_python = "[" + ", ".join(f"'{v}'" for v in values_list) + "]"
            return f"{expr} in {values_python}"
        
        converted = re.sub(in_pattern, in_replacer, condition, flags=re.IGNORECASE)
        
        # Convert SQL operators to Python
        conversions = [
            (r'(?<!=)\s*=\s*(?!=)', ' == '),  # SQL equality to Python equality (not already ==)
            (r'\s*<>\s*', ' != '),      # SQL not equal to Python not equal
            (r'\s*%\s*', ' % '),        # Modulo (already Python compatible)
            (r'\bAND\b', 'and'),        # SQL AND to Python and
            (r'\bOR\b', 'or'),          # SQL OR to Python or
            (r'\bNOT\b', 'not'),        # SQL NOT to Python not
        ]
        
        for pattern, replacement in conversions:
            converted = re.sub(pattern, replacement, converted, flags=re.IGNORECASE)
        
        return converted

    def _evaluate_approximate_functions(self, func_name: str, arguments: List[str], is_running: bool, filter_condition: str = None) -> Any:
        """Evaluate approximate aggregation functions (APPROX_DISTINCT, APPROX_PERCENTILE)."""
        if func_name == "APPROX_DISTINCT":
            if len(arguments) != 1:
                raise AggregateArgumentError(f"APPROX_DISTINCT requires exactly 1 argument, got {len(arguments)}")
            
            # For simplicity, use exact distinct count (in production this would use HyperLogLog)
            values = self._get_expression_values(arguments[0], is_running)
            
            # Filter out None values and get unique values
            unique_values = set()
            for value in values:
                if value is not None:
                    unique_values.add(value)
            
            return len(unique_values)
            
        elif func_name == "APPROX_PERCENTILE":
            if len(arguments) != 2:
                raise AggregateArgumentError(f"APPROX_PERCENTILE requires exactly 2 arguments, got {len(arguments)}")
            
            # Get numeric values
            values = self._get_numeric_values(arguments[0], is_running)
            if not values:
                return None
            
            # Get percentile value (should be between 0 and 1)
            try:
                percentile_expr = arguments[1]
                percentile = self._evaluate_single_expression(percentile_expr)
                if not isinstance(percentile, (int, float)) or percentile < 0 or percentile > 1:
                    raise AggregateArgumentError(f"Percentile must be between 0 and 1, got {percentile}")
            except Exception as e:
                raise AggregateArgumentError(f"Invalid percentile expression: {arguments[1]}")
            
            # Sort values and calculate percentile using numpy's percentile function
            sorted_values = sorted(values)
            n = len(sorted_values)
            
            if n == 1:
                return sorted_values[0]
            
            # Convert percentile (0-1) to percentage (0-100) for numpy
            percentile_pct = percentile * 100
            
            # Use numpy's percentile function for accurate calculation
            try:
                import numpy as np
                result = np.percentile(sorted_values, percentile_pct)
                return float(result)
            except ImportError:
                # Fallback implementation if numpy not available
                # Linear interpolation method
                index = percentile * (n - 1)
                lower_index = int(index)
                upper_index = min(lower_index + 1, n - 1)
                weight = index - lower_index
                
                if weight == 0:
                    return sorted_values[lower_index]
                else:
                    return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight
        
        else:
            raise AggregateValidationError(f"Unsupported approximate function: {func_name}")
        
    def _evaluate_statistical_means(self, func_name: str, arguments: List[str], is_running: bool, filter_condition: str = None) -> float:
        """
        Evaluate statistical mean functions like GEOMETRIC_MEAN and HARMONIC_MEAN.
        
        Args:
            func_name: The statistical mean function name
            arguments: Function arguments
            is_running: Whether this is a RUNNING aggregate
            filter_condition: Optional FILTER WHERE condition
            
        Returns:
            The calculated statistical mean
        """
        if len(arguments) != 1:
            raise AggregateArgumentError(f"{func_name} requires exactly one argument")
        
        # Get values for the aggregate
        values = self._get_aggregate_values(arguments[0], is_running, filter_condition)
        
        # Filter out None/NaN values
        numeric_values = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v)) and v > 0]
        
        if not numeric_values:
            return None
        
        if func_name == "GEOMETRIC_MEAN":
            # Geometric mean: (x1 * x2 * ... * xn)^(1/n)
            # Using log space for numerical stability: exp(mean(log(xi)))
            try:
                log_sum = sum(math.log(v) for v in numeric_values)
                return math.exp(log_sum / len(numeric_values))
            except (ValueError, OverflowError):
                return None
                
        elif func_name == "HARMONIC_MEAN":
            # Harmonic mean: n / (1/x1 + 1/x2 + ... + 1/xn)
            try:
                reciprocal_sum = sum(1.0 / v for v in numeric_values)
                return len(numeric_values) / reciprocal_sum
            except (ZeroDivisionError, OverflowError):
                return None
        
        else:
            raise AggregateValidationError(f"Unsupported statistical mean function: {func_name}")
    
    def _evaluate_mathematical_functions(self, func_name: str, arguments: List[str], is_running: bool, filter_condition: str = None) -> float:
        """
        Evaluate mathematical functions that wrap other expressions.
        
        Args:
            func_name: The mathematical function name (e.g., 'SQRT', 'ABS', 'LOG')
            arguments: Function arguments
            is_running: Whether this is a RUNNING aggregate
            filter_condition: Optional FILTER WHERE condition
            
        Returns:
            The calculated result
        """
        if len(arguments) != 1:
            raise AggregateArgumentError(f"{func_name} requires exactly one argument")
        
        # Evaluate the inner expression (could be an aggregate or arithmetic expression)
        inner_expr = arguments[0]
        
        # If the inner expression contains aggregate functions, use the enhanced evaluator
        if any(agg in inner_expr.upper() for agg in ['AVG', 'SUM', 'COUNT', 'MIN', 'MAX', 'STDDEV', 'VARIANCE']):
            try:
                # Use enhanced evaluator for aggregate expressions
                inner_value = self.evaluate_aggregate(
                    inner_expr, 'RUNNING' if is_running else 'FINAL'
                )
            except Exception as e:
                logger.warning(f"Enhanced evaluator failed for inner expression '{inner_expr}': {e}")
                # Fallback to simple expression evaluation
                inner_value = self._evaluate_single_expression(inner_expr)
        else:
            # Use simple expression evaluation for non-aggregate expressions
            inner_value = self._evaluate_single_expression(inner_expr)
        
        if inner_value is None:
            return None
        
        try:
            if func_name == "SQRT":
                return math.sqrt(float(inner_value))
            elif func_name == "ABS":
                return abs(float(inner_value))
            elif func_name == "LOG":
                return math.log(float(inner_value))
            elif func_name == "LOG10":
                return math.log10(float(inner_value))
            elif func_name == "EXP":
                return math.exp(float(inner_value))
            elif func_name == "SIN":
                return math.sin(float(inner_value))
            elif func_name == "COS":
                return math.cos(float(inner_value))
            elif func_name == "TAN":
                return math.tan(float(inner_value))
            elif func_name == "ASIN":
                return math.asin(float(inner_value))
            elif func_name == "ACOS":
                return math.acos(float(inner_value))
            elif func_name == "ATAN":
                return math.atan(float(inner_value))
            elif func_name == "CEIL":
                return math.ceil(float(inner_value))
            elif func_name == "FLOOR":
                return math.floor(float(inner_value))
            elif func_name == "ROUND":
                return round(float(inner_value))
            else:
                raise AggregateValidationError(f"Unsupported mathematical function: {func_name}")
        except (ValueError, OverflowError, ZeroDivisionError) as e:
            logger.warning(f"Mathematical function {func_name} failed: {e}")
            return None
        
    def _apply_filter_condition(self, filter_condition: str, is_running: bool) -> List[bool]:
        """
        Apply a FILTER WHERE condition to determine which rows should be included.
        
        Args:
            filter_condition: The WHERE condition (e.g., "A.value >= FIRST(A.value)")
            is_running: Whether this is a RUNNING aggregate
            
        Returns:
            List of boolean values indicating which rows pass the filter
        """
        try:
            # Get the range of rows to consider
            if is_running:
                end_idx = self.context.current_idx + 1
            else:
                end_idx = len(self.context.rows)
            
            filter_results = []
            
            for row_idx in range(end_idx):
                # Temporarily set context to this row for condition evaluation
                original_idx = self.context.current_idx
                self.context.current_idx = row_idx
                
                try:
                    # Evaluate the filter condition for this row using the expression evaluator
                    condition_result = self._evaluate_single_expression(filter_condition)
                    filter_results.append(bool(condition_result))
                except Exception as e:
                    logger.debug(f"Filter condition evaluation failed for row {row_idx}: {e}")
                    filter_results.append(False)
                finally:
                    # Restore original context
                    self.context.current_idx = original_idx
            
            return filter_results
            
        except Exception as e:
            logger.warning(f"Failed to apply filter condition '{filter_condition}': {e}")
            # If filter evaluation fails, include all rows (safer fallback)
            if is_running:
                return [True] * (self.context.current_idx + 1)
            else:
                return [True] * len(self.context.rows)
        

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
        
        # Check if this is an aggregate function expression
        # Pattern matches: [RUNNING|FINAL] FUNC(...) - allows complex arguments including CASE WHEN
        agg_pattern = r'^\s*(?:(RUNNING|FINAL)\s+)?([A-Z_]+)\s*\('
        match = re.match(agg_pattern, expr.strip(), re.IGNORECASE)
        
        # Check if this is an aggregate function expression
        # Pattern matches: [RUNNING|FINAL] FUNC(...) - allows any arguments
        agg_pattern = r'^\s*(?:(RUNNING|FINAL)\s+)?([A-Z_]+)\s*\('
        match = re.match(agg_pattern, expr.strip(), re.IGNORECASE)
        
        logger.debug(f"Pattern match result for '{expr}': {match}")
        
        if match:
            semantics_prefix = match.group(1)
            func_name = match.group(2).upper()
            
            logger.debug(f"Matched function: {func_name}, semantics_prefix: {semantics_prefix}")
            
            # If semantics is in the expression, use that instead of parameter
            if semantics_prefix:
                semantics = semantics_prefix.upper()
            
            if func_name in ProductionAggregateEvaluator.STANDARD_AGGREGATES or func_name in ProductionAggregateEvaluator.MATHEMATICAL_FUNCTIONS:
                logger.debug(f"Using production aggregate evaluator for: {expr} -> {func_name}")
                # Create fresh production aggregate evaluator with current context
                prod_agg_evaluator = ProductionAggregateEvaluator(self.context)
                
                try:
                    result = prod_agg_evaluator.evaluate_aggregate(expr, semantics)
                    logger.info(f"ENHANCED_EVAL_DEBUG: Production aggregate result for {expr}: {result} (type: {type(result)})")
                    # Ensure we return the exact result from production aggregator
                    if result is None:
                        logger.info(f"ENHANCED_EVAL_DEBUG: Returning None from production aggregator")
                    return result
                except (AggregateValidationError, AggregateArgumentError) as e:
                    logger.warning(f"ENHANCED_EVAL: Aggregate validation error for {expr}: {e}")
                    logger.warning(f"ENHANCED_EVAL: Falling back to original evaluator")
                    return None
                except Exception as e:
                    logger.error(f"ENHANCED_EVAL: Error in production aggregate evaluator for {expr}: {e}")
                    logger.error(f"ENHANCED_EVAL: Falling back to original evaluator")
                    # Fallback to original implementation
                    pass
            else:
                logger.debug(f"Function {func_name} not in standard aggregates, using original evaluator")
        else:
            logger.debug(f"Expression doesn't match pure aggregate pattern: {expr}")
        
        # Use original implementation for complex expressions and non-aggregates
        logger.info(f"ENHANCED_EVAL_DEBUG: Falling back to original evaluator for: {expr}")
        original_result = original_evaluate(self, expr, semantics)
        logger.info(f"ENHANCED_EVAL_DEBUG: Original evaluator returned: {original_result} (type: {type(original_result)})")
        return original_result
    
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
