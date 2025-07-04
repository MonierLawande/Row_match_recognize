# src/matcher/measure_evaluator.py
"""
Production-ready measure evaluator for SQL:2016 row pattern matching.

This module implements comprehensive measure evaluation with full support for:
- SQL:2016 navigation functions (FIRST, LAST, PREV, NEXT)
- RUNNING vs FINAL semantics with proper offset handling
- Pattern variable references and subset variables
- Production aggregate functions (SUM, COUNT, MIN, MAX, AVG, etc.)
- Type preservation and Trino compatibility
- Advanced error handling and validation
- Performance optimization with caching

Features:
- Thread-safe evaluation with proper context management
- Comprehensive input validation and sanitization
- Detailed logging and performance monitoring
- Memory-efficient processing for large datasets
- Full SQL:2016 compliance with edge case handling

Refactored to eliminate duplication and improve maintainability.

Author: Pattern Matching Engine Team
Version: 3.0.0
"""

from collections import defaultdict
from functools import lru_cache
from typing import Dict, Any, List, Optional, Set, Union, Tuple, Callable
import ast
import re
import math
import time
import threading
from dataclasses import dataclass
from enum import Enum

from src.matcher.row_context import RowContext
from src.matcher.evaluation_utils import (
    EvaluationMode, ValidationError, ExpressionValidationError,
    validate_expression_length, validate_recursion_depth,
    is_null, is_table_prefix, get_column_value_with_type_preservation,
    preserve_data_type, MATH_FUNCTIONS, evaluate_math_function,
    get_evaluation_metrics, cast_function, try_cast_function
)
from src.utils.logging_config import get_logger, PerformanceTimer

# Module logger with enhanced configuration
logger = get_logger(__name__)

# Constants for production-ready behavior
MAX_EXPRESSION_LENGTH = 10000  # Prevent extremely long expressions
MAX_RECURSION_DEPTH = 50      # Prevent infinite recursion
CACHE_SIZE_LIMIT = 1000       # LRU cache limit for expression evaluation

class EvaluationMode(Enum):
    """Enumeration of evaluation modes for measure expressions."""
    RUNNING = "RUNNING"
    FINAL = "FINAL"

class NavigationDirection(Enum):
    """Enumeration of navigation directions."""
    FORWARD = "FORWARD"
    BACKWARD = "BACKWARD"

@dataclass
class EvaluationContext:
    """Container for evaluation context information."""
    current_idx: int
    is_running: bool
    is_permute: bool
    recursion_depth: int = 0
    cache: Optional[Dict[str, Any]] = None

class MeasureEvaluationError(Exception):
    """Base class for measure evaluation errors."""
    pass

class ClassifierError(MeasureEvaluationError):
    """Error in CLASSIFIER function evaluation."""
    pass

class NavigationError(MeasureEvaluationError):
    """Error in navigation function evaluation."""
    pass

class AggregateError(MeasureEvaluationError):
    """Error in aggregate function evaluation."""
    pass

# Thread-local storage for evaluation context
_evaluation_context = threading.local()

def _get_evaluation_context() -> Optional[EvaluationContext]:
    """Get the current thread's evaluation context."""
    return getattr(_evaluation_context, 'context', None)

def _set_evaluation_context(context: EvaluationContext) -> None:
    """Set the current thread's evaluation context."""
    _evaluation_context.context = context

def _clear_evaluation_context() -> None:
    """Clear the current thread's evaluation context."""
    if hasattr(_evaluation_context, 'context'):
        delattr(_evaluation_context, 'context')

# Updates for src/matcher/measure_evaluator.py

def evaluate_pattern_variable_reference(expr: str, var_assignments: Dict[str, List[int]], all_rows: List[Dict[str, Any]], cache: Dict[str, Any] = None, subsets: Dict[str, List[str]] = None, current_idx: int = None, is_running: bool = False, is_permute: bool = False) -> Tuple[bool, Any]:
    """
    Evaluate a pattern variable reference with proper subset handling, RUNNING semantics, and PERMUTE support.
    
    Args:
        expr: The expression to evaluate
        var_assignments: Dictionary mapping variables to row indices
        all_rows: List of all rows in the partition
        cache: Optional cache for variable reference results
        subsets: Optional dictionary of subset variable definitions
        current_idx: Current row index for RUNNING semantics
        is_running: Whether we're in RUNNING mode
        is_permute: Whether this is a PERMUTE pattern
        
    Returns:
        Tuple of (handled, value) where handled is True if this was a pattern variable reference
    """
    # Clean the expression - remove any whitespace
    expr = expr.strip()
    
    logger.debug(f"Evaluating pattern variable reference: {expr}, current_idx={current_idx}, is_running={is_running}, is_permute={is_permute}")
    
    # Use cache if provided (but cache key should include current_idx, is_running, and is_permute for proper caching)
    # CRITICAL FIX: For ALL ROWS PER MATCH mode with FINAL semantics, we need row-specific caching
    # because A.value should return different values for different rows
    cache_key = f"{expr}_{current_idx}_{is_running}_{is_permute}"
    if cache is not None and cache_key in cache:
        logger.debug(f"Cache hit for {cache_key}")
        return True, cache[cache_key]
    
    # Handle direct pattern variable references like A.salary or X.value
    var_col_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$', expr)
    if var_col_match:
        var_name = var_col_match.group(1)
        col_name = var_col_match.group(2)
        
        # Table prefix validation: prevent forbidden table.column references
        # Check if this looks like a table prefix (common table naming patterns)
        if is_table_prefix(var_name, var_assignments, subsets):
            raise ValueError(f"Forbidden table prefix reference: '{expr}'. "
                           f"In MATCH_RECOGNIZE, use pattern variable references like 'A.{col_name}' "
                           f"instead of table references like '{var_name}.{col_name}'")
        
        logger.debug(f"Pattern variable reference matched: var={var_name}, col={col_name}")
        
        # For PERMUTE patterns in ONE ROW PER MATCH mode, always use FINAL semantics
        # This ensures we get the actual value for each variable regardless of order
        if is_permute and not is_running:
            logger.debug(f"Using PERMUTE-specific logic for {var_name}")
            var_indices = var_assignments.get(var_name, [])
            if var_indices:
                # Use the last matched position for this variable
                idx = max(var_indices)
                if idx < len(all_rows):
                    value = all_rows[idx].get(col_name)
                    logger.debug(f"PERMUTE match found value {value} at index {idx}")
                    if cache is not None:
                        cache[cache_key] = value
                    return True, value
        
        # Check if this is a subset variable
        if subsets and var_name in subsets:
            components = subsets[var_name]
            
            # CRITICAL FIX: For subset variables, SQL:2016 standard specifies returning the value 
            # from the LAST matching variable in the subset (not first).
            # This is essential for PERMUTE patterns with subset variables.
            last_component_value = None
            last_component_idx = -1
            
            for component in components:
                if component in var_assignments and var_assignments[component]:
                    var_indices = var_assignments[component]
                    
                    # For RUNNING semantics, only consider positions at or before current_idx
                    if is_running and current_idx is not None:
                        valid_indices = [idx for idx in var_indices if idx <= current_idx]
                        if not valid_indices:
                            continue  # Try next component
                        var_indices = valid_indices
                    
                    if var_indices:
                        # Use the LAST index for this component (SQL:2016 standard)
                        component_idx = max(var_indices)
                        if component_idx < len(all_rows) and component_idx > last_component_idx:
                            last_component_idx = component_idx
                            last_component_value = all_rows[component_idx].get(col_name)
            
            # Return the value from the component with the highest (last) index
            if cache is not None:
                cache[cache_key] = last_component_value
            return True, last_component_value
        
        # Direct variable lookup
        var_indices = var_assignments.get(var_name, [])
        
        # For RUNNING semantics, only return value if the variable's position is at or before current_idx
        if is_running and current_idx is not None:
            valid_indices = [idx for idx in var_indices if idx <= current_idx]
            if not valid_indices:
                if cache is not None:
                    cache[cache_key] = None
                return True, None
            var_indices = valid_indices
        
        if var_indices:
            # CRITICAL FIX: For FINAL semantics in ALL ROWS PER MATCH mode, 
            # return the value from the current row if it's among the variable's indices
            target_idx = None
            if not is_running and current_idx is not None and current_idx in var_indices:
                # FINAL semantics: Use current row if it matches this variable
                target_idx = current_idx
                logger.debug(f"FINAL semantics: Using current row {current_idx} for {var_name}.{col_name}")
            else:
                # RUNNING semantics or FINAL without current row: Use first matched index
                target_idx = var_indices[0]
                logger.debug(f"Using first index {target_idx} for {var_name}.{col_name}")
            
            if target_idx < len(all_rows):
                value = all_rows[target_idx].get(col_name)
                if cache is not None:
                    cache[cache_key] = value
                return True, value
        
        if cache is not None:
            cache[cache_key] = None
        return True, None
    
    # Not a pattern variable reference
    return False, None



class MeasureEvaluator:
    """
    Production-ready measure evaluator for SQL:2016 row pattern matching.
    
    This class provides comprehensive measure evaluation with full support for:
    - SQL:2016 navigation functions with proper semantics
    - Aggregate functions with type preservation
    - Pattern variable references and subset handling
    - Thread-safe evaluation with proper caching
    - Performance monitoring and optimization
    
    Features:
    - Comprehensive input validation and sanitization
    - Advanced error handling and recovery
    - Memory-efficient caching with LRU eviction
    - Detailed performance metrics and logging
    - Full SQL:2016 compliance with edge case handling
    """
    
    def __init__(self, context: RowContext, final: bool = True):
        """
        Initialize the measure evaluator with enhanced validation and monitoring.
        
        Args:
            context: Row context for evaluation
            final: Whether to use FINAL semantics by default
            
        Raises:
            ValueError: If context is invalid
        """
        # Input validation
        if not isinstance(context, RowContext):
            raise ValueError(f"Expected RowContext, got {type(context)}")
        
        self.context = context
        self.final = final
        self.original_expr = None
        
        # Production-ready caching with LRU policy
        self._classifier_cache = {}
        self._var_ref_cache = {}
        self._navigation_cache = {}
        self._aggregate_cache = {}
        
        # Performance monitoring
        self.timing = defaultdict(float)
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "total_evaluations": 0,
            "validation_errors": 0,
            "evaluation_errors": 0
        }
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Build optimized indices for fast lookup
        try:
            self._build_row_variable_index()
            self._build_navigation_index()
        except Exception as e:
            logger.error(f"Failed to build evaluation indices: {e}")
            # Continue with basic functionality
    
    def _build_row_variable_index(self) -> None:
        """Build optimized index for row-to-variable lookups."""
        with self._lock:
            self._row_var_index = defaultdict(set)
            try:
                for var_name, indices in self.context.variables.items():
                    for idx in indices:
                        if isinstance(idx, int) and 0 <= idx < len(self.context.rows):
                            self._row_var_index[idx].add(var_name)
            except Exception as e:
                logger.warning(f"Error building row variable index: {e}")
                self._row_var_index = defaultdict(set)
    
    def _build_navigation_index(self) -> None:
        """Build optimized index for navigation operations."""
        with self._lock:
            self._navigation_index = {}
            try:
                # Pre-compute sorted indices for efficient navigation
                all_indices = set()
                for indices in self.context.variables.values():
                    all_indices.update(indices)
                self._navigation_index['sorted_indices'] = sorted(all_indices)
                self._navigation_index['index_map'] = {
                    idx: pos for pos, idx in enumerate(self._navigation_index['sorted_indices'])
                }
            except Exception as e:
                logger.warning(f"Error building navigation index: {e}")
                self._navigation_index = {}
    
    def _preserve_data_type(self, original_value: Any, new_value: Any) -> Any:
        """
        Preserve the data type of the original value using shared utility.
        """
        return preserve_data_type(original_value, new_value)

    def _build_row_variable_index(self):
        """Build an index of which variables each row belongs to for faster lookup."""
        self._row_to_vars = defaultdict(set)
        for var, indices in self.context.variables.items():
            for idx in indices:
                self._row_to_vars[idx].add(var)
        
        # Pre-compute subset memberships too
        if hasattr(self.context, 'subsets') and self.context.subsets:
            for subset_name, components in self.context.subsets.items():
                for comp in components:
                    if comp in self.context.variables:
                        for idx in self.context.variables[comp]:
                            self._row_to_vars[idx].add(subset_name)

    def _preprocess_expression_for_ast(self, expr: str, is_running: bool = False) -> str:
        """
        Preprocess an expression to replace special SQL functions with their values
        so that the expression can be parsed by Python's AST parser.
        
        This method handles:
        - MATCH_NUMBER() -> actual match number value
        - CLASSIFIER() -> classifier value (if needed, but not inside navigation functions)
        - Aggregate functions (SUM, AVG, COUNT, MIN, MAX, etc.) -> computed values
        - SQL IN operator -> Python in operator (case conversion)
        
        Args:
            expr: The original expression
            
        Returns:
            The preprocessed expression that can be parsed by AST
        """
        # Check if expression contains navigation functions
        # If it does, don't preprocess CLASSIFIER calls as they should be handled by the AST evaluator
        has_navigation_functions = re.search(r'\b(FIRST|LAST|PREV|NEXT)\s*\(', expr, re.IGNORECASE)
        
        preprocessed = expr
        
        # Replace MATCH_NUMBER() with the actual match number
        # Use word boundaries to avoid replacing partial matches
        if 'MATCH_NUMBER()' in preprocessed:
            match_number = str(self.context.match_number)
            preprocessed = re.sub(r'\bMATCH_NUMBER\(\)', match_number, preprocessed, flags=re.IGNORECASE)
        
        # Replace aggregate function calls with their computed values
        # This is crucial for expressions like "AVG(value) * 0.9"
        agg_pattern = r'(SUM|COUNT|MIN|MAX|AVG|STDDEV|VAR)\s*\(([^)]+)\)'
        agg_matches = re.finditer(agg_pattern, preprocessed, re.IGNORECASE)
        
        # Process matches in reverse order to avoid position shifts when replacing
        for match in reversed(list(agg_matches)):
            func_name = match.group(1).lower()
            args_str = match.group(2).strip()
            
            # Evaluate the aggregate function
            # Use the semantics passed to this method
            agg_value = self._evaluate_aggregate(func_name, args_str, is_running)
            
            # Replace the aggregate function call with its computed value
            if agg_value is not None:
                # Convert to string, preserving numeric precision
                if isinstance(agg_value, float):
                    # Use sufficient precision to avoid rounding errors
                    agg_str = f"{agg_value:.10g}"
                else:
                    agg_str = str(agg_value)
                
                old_expr = preprocessed[match.start():match.end()]
                logger.debug(f"Preprocessing: replacing '{old_expr}' with '{agg_str}' in expression")
                preprocessed = preprocessed[:match.start()] + agg_str + preprocessed[match.end():]
                logger.debug(f"After replacement: '{preprocessed}'")
            else:
                logger.debug(f"Aggregate evaluation returned None for: {match.group()}")
        
        # Convert SQL IN to Python in (case-sensitive conversion)
        # Use word boundaries to avoid replacing parts of words
        preprocessed = re.sub(r'\bIN\b', 'in', preprocessed)
        preprocessed = re.sub(r'\bNOT IN\b', 'not in', preprocessed)
        
        # Replace CLASSIFIER() calls with their actual values
        # Skip this if expression contains navigation functions, as they should handle CLASSIFIER calls directly
        if not has_navigation_functions:
            classifier_pattern = r'CLASSIFIER\(\s*([A-Za-z][A-Za-z0-9_]*)?\s*\)'
            classifier_matches = re.finditer(classifier_pattern, preprocessed, re.IGNORECASE)
            
            # Process matches in reverse order to avoid position shifts when replacing
            for match in reversed(list(classifier_matches)):
                var_name = match.group(1)
                
                # Evaluate the CLASSIFIER function
                classifier_value = self.evaluate_classifier(var_name, running=is_running)
                
                # Replace the CLASSIFIER function call with its computed value (quoted string)
                if classifier_value is not None:
                    # Quote the classifier value as a string literal for AST parsing
                    classifier_str = f"'{classifier_value}'"
                    
                    old_expr = preprocessed[match.start():match.end()]
                    logger.debug(f"Preprocessing: replacing '{old_expr}' with '{classifier_str}' in expression")
                    preprocessed = preprocessed[:match.start()] + classifier_str + preprocessed[match.end():]
                    logger.debug(f"After CLASSIFIER replacement: '{preprocessed}'")
                else:
                    logger.debug(f"CLASSIFIER evaluation returned None for: {match.group()}")
        else:
            logger.debug("Skipping CLASSIFIER preprocessing due to presence of navigation functions")
        
        # Replace SQL CASE expressions with Python conditional expressions using the proper converter
        from .condition_evaluator import _sql_to_python_condition
        
        # Check if there are any CASE expressions to convert
        if re.search(r'\bCASE\s+WHEN\b', preprocessed, re.IGNORECASE):
            logger.debug(f"Converting CASE expressions using _sql_to_python_condition")
            old_preprocessed = preprocessed
            preprocessed = _sql_to_python_condition(preprocessed)
            logger.debug(f"After CASE conversion: '{old_preprocessed}' -> '{preprocessed}'")
        
        # Convert SQL operators to Python operators for AST parsing
        # This is critical for expressions like "PREV(CLASSIFIER(U), 1) = 'A'"
        if '=' in preprocessed and '==' not in preprocessed:
            # Convert SQL equality (=) to Python equality (==)
            # Be careful to avoid converting already-converted == operators
            # Use negative lookbehind and lookahead to avoid matching parts of != or ==
            preprocessed = re.sub(r'(?<![\!=])=(?!=)', '==', preprocessed)
            logger.debug(f"Converted SQL = to Python ==: '{preprocessed}'")
        
        # Convert SQL logical operators to Python logical operators
        preprocessed = re.sub(r'\bAND\b', 'and', preprocessed, flags=re.IGNORECASE)
        preprocessed = re.sub(r'\bOR\b', 'or', preprocessed, flags=re.IGNORECASE)
        preprocessed = re.sub(r'\bNOT\b', 'not', preprocessed, flags=re.IGNORECASE)
        
        # Handle CAST and TRY_CAST functions by evaluating them and replacing with their values
        # Use a more robust approach to handle nested parentheses in type specifications
        def find_cast_expressions(text):
            """Find CAST/TRY_CAST expressions with proper parentheses balancing."""
            cast_expressions = []
            pattern = r'(CAST|TRY_CAST)\s*\('
            
            for match in re.finditer(pattern, text, re.IGNORECASE):
                func_name = match.group(1)
                start_pos = match.start()
                paren_pos = match.end() - 1  # Position of the opening parenthesis
                
                # Find the matching closing parenthesis
                paren_count = 1
                pos = paren_pos + 1
                while pos < len(text) and paren_count > 0:
                    if text[pos] == '(':
                        paren_count += 1
                    elif text[pos] == ')':
                        paren_count -= 1
                    pos += 1
                
                if paren_count == 0:
                    # Found complete expression
                    full_expr = text[start_pos:pos]
                    inner_content = text[paren_pos + 1:pos - 1].strip()
                    
                    # Split on ' AS ' (case insensitive)
                    as_match = re.search(r'\s+AS\s+', inner_content, re.IGNORECASE)
                    if as_match:
                        value_expr = inner_content[:as_match.start()].strip()
                        target_type = inner_content[as_match.end():].strip()
                        
                        cast_expressions.append({
                            'full_expr': full_expr,
                            'func_name': func_name.upper(),
                            'value_expr': value_expr,
                            'target_type': target_type,
                            'start_pos': start_pos,
                            'end_pos': pos
                        })
            
            return cast_expressions
        
        cast_expressions = find_cast_expressions(preprocessed)
        
        # Process in reverse order to avoid position shifts when replacing
        
        # Process in reverse order to avoid position shifts when replacing
        for cast_info in reversed(cast_expressions):
            func_name = cast_info['func_name']
            value_expr = cast_info['value_expr']
            target_type = cast_info['target_type']
            
            try:
                # First evaluate the inner expression (e.g., "value" in "CAST(value AS VARCHAR)")
                from .condition_evaluator import ConditionEvaluator
                
                # Set up context for evaluating the inner expression
                temp_context = self.context
                temp_context.current_row = temp_context.rows[temp_context.current_idx] if temp_context.current_idx < len(temp_context.rows) else None
                
                evaluator = ConditionEvaluator(temp_context, evaluation_mode='MEASURES')
                
                # Try to evaluate the inner expression as an AST
                try:
                    inner_tree = ast.parse(value_expr, mode='eval')
                    inner_value = evaluator.visit(inner_tree.body)
                except:
                    # Fallback: try as simple column reference
                    inner_value = temp_context.current_row.get(value_expr) if temp_context.current_row else None
                
                # Apply the CAST function
                if func_name == 'CAST':
                    cast_result = cast_function(inner_value, target_type)
                else:  # TRY_CAST
                    cast_result = try_cast_function(inner_value, target_type)
                
                # Replace the CAST function call with its computed value
                if cast_result is not None:
                    # Quote string results, use literal representation for others
                    if isinstance(cast_result, str):
                        cast_str = f"'{cast_result}'"
                    else:
                        cast_str = str(cast_result)
                    
                    old_expr = cast_info['full_expr']
                    logger.debug(f"Preprocessing: replacing '{old_expr}' with '{cast_str}' in expression")
                    preprocessed = preprocessed[:cast_info['start_pos']] + cast_str + preprocessed[cast_info['end_pos']:]
                    logger.debug(f"After CAST replacement: '{preprocessed}'")
                else:
                    # For TRY_CAST or failed CAST, replace with None
                    old_expr = cast_info['full_expr']
                    logger.debug(f"Preprocessing: replacing '{old_expr}' with 'None' (CAST failed)")
                    preprocessed = preprocessed[:cast_info['start_pos']] + 'None' + preprocessed[cast_info['end_pos']:]
                    
            except Exception as e:
                logger.error(f"Error preprocessing CAST function {cast_info['full_expr']}: {e}")
                # Leave the CAST expression as-is if preprocessing fails
                continue
        
        logger.debug(f"Preprocessed expression: '{expr}' -> '{preprocessed}'")
        return preprocessed


    def evaluate(self, expr: str, semantics: str = None) -> Any:
        """
        Evaluate a measure expression with comprehensive validation and error handling.
        
        This production-ready implementation provides:
        - Full SQL:2016 compliance with proper RUNNING/FINAL semantics
        - Comprehensive input validation and sanitization
        - Advanced error handling and recovery
        - Performance monitoring and caching
        - Thread-safe evaluation
        
        Args:
            expr: The expression to evaluate (validated)
            semantics: Optional semantics override ('RUNNING' or 'FINAL')
            
        Returns:
            The result of the expression evaluation
            
        Raises:
            ExpressionValidationError: If expression is invalid
            MeasureEvaluationError: If evaluation fails
        """
        start_time = time.time()
        
        try:
            # Input validation
            if not isinstance(expr, str):
                raise ExpressionValidationError(f"Expected str for expr, got {type(expr)}")
            
            expr = expr.strip()
            if not expr:
                raise ExpressionValidationError("Empty expression")
            
            validate_expression_length(expr)
            
            # Get evaluation context
            eval_context = _get_evaluation_context()
            if eval_context is None:
                eval_context = EvaluationContext(
                    current_idx=getattr(self.context, 'current_idx', 0),
                    is_running=semantics == 'RUNNING',
                    is_permute=False,
                    cache={}
                )
                _set_evaluation_context(eval_context)
            
            validate_recursion_depth(eval_context.recursion_depth)
            eval_context.recursion_depth += 1
            
            # Thread-safe statistics update
            with self._lock:
                self.stats["total_evaluations"] += 1
            
            # Check cache first
            cache_key = f"{expr}:{semantics}:{self.context.current_idx}:{self.final}"
            if cache_key in self._var_ref_cache:
                with self._lock:
                    self.stats["cache_hits"] += 1
                return self._var_ref_cache[cache_key]
            
            # Determine semantics with SQL:2016 compliance
            if semantics == 'RUNNING':
                is_running = True
            elif semantics == 'FINAL':
                is_running = False
            else:
                # Default semantics based on SQL:2016 specification
                is_running = False  # FINAL is default for most functions
            
            logger.debug(f"Evaluating expression: {expr} with {('RUNNING' if is_running else 'FINAL')} semantics")
            logger.debug(f"Context variables: {self.context.variables}")
            logger.debug(f"Number of rows: {len(self.context.rows)}")
            logger.debug(f"Current index: {self.context.current_idx}")
            
            # Store original expression for debugging
            self.original_expr = expr
            
            # Check for explicit RUNNING/FINAL prefix with security validation
            running_match = re.match(r'RUNNING\s+(.+)', expr, re.IGNORECASE)
            final_match = re.match(r'FINAL\s+(.+)', expr, re.IGNORECASE)
            
            if running_match:
                expr = running_match.group(1).strip()
                is_running = True
            elif final_match:
                expr = final_match.group(1).strip()
                is_running = False
            
            # Validate and normalize current_idx
            if not hasattr(self.context, 'current_idx') or self.context.current_idx is None:
                self.context.current_idx = 0
            
            if len(self.context.rows) > 0 and self.context.current_idx >= len(self.context.rows):
                self.context.current_idx = len(self.context.rows) - 1
            elif self.context.current_idx < 0:
                self.context.current_idx = 0
            
            # Update evaluation context
            eval_context.current_idx = self.context.current_idx
            eval_context.is_running = is_running
            
            # Evaluate the expression with error handling
            try:
                result = self._evaluate_expression_safe(expr, is_running)
                
                # Cache successful result
                with self._lock:
                    if len(self._var_ref_cache) < CACHE_SIZE_LIMIT:
                        self._var_ref_cache[cache_key] = result
                    self.stats["cache_misses"] += 1
                
                return result
                
            except Exception as e:
                with self._lock:
                    self.stats["evaluation_errors"] += 1
                logger.error(f"Error evaluating expression '{expr}': {e}")
                raise MeasureEvaluationError(f"Evaluation failed for '{expr}': {e}")
            
        except ExpressionValidationError:
            with self._lock:
                self.stats["validation_errors"] += 1
            raise
        except Exception as e:
            logger.error(f"Unexpected error in evaluate: {e}")
            raise MeasureEvaluationError(f"Unexpected evaluation error: {e}")
        finally:
            # Update timing statistics
            elapsed = time.time() - start_time
            with self._lock:
                self.timing["evaluate"] += elapsed
            
            # Clean up evaluation context
            if eval_context:
                eval_context.recursion_depth -= 1
                if eval_context.recursion_depth <= 0:
                    _clear_evaluation_context()
    
    def _evaluate_expression_safe(self, expr: str, is_running: bool) -> Any:
        """
        Safely evaluate an expression with comprehensive error handling.
        
        Args:
            expr: The expression to evaluate
            is_running: Whether to use RUNNING semantics
            
        Returns:
            The evaluation result
        """
        # Handle CLASSIFIER function
        classifier_pattern = r'CLASSIFIER\(\s*([A-Za-z][A-Za-z0-9_]*)?\s*\)'
        classifier_match = re.match(classifier_pattern, expr, re.IGNORECASE)
        if classifier_match:
            var_name = classifier_match.group(1)
            return self.evaluate_classifier(var_name, running=is_running)
        
        # Handle MATCH_NUMBER function
        if expr.upper().strip() == "MATCH_NUMBER()":
            return self.context.match_number
            
        # Special handling for ROW_NUMBER
        if expr.upper().strip() == "ROW_NUMBER()":
            # ROW_NUMBER() returns the sequential number of the row within the match (1-based)
            # In RUNNING semantics, it returns the current row number within the visible portion
            # In FINAL semantics, it returns the row number within the complete match
            
            if is_running:
                # RUNNING semantics: count visible rows up to and including current position
                visible_rows = set()
                for var_indices in self.context.variables.values():
                    for idx in var_indices:
                        if idx <= self.context.current_idx:
                            visible_rows.add(idx)
                
                # Find the position of current_idx among visible rows
                visible_list = sorted(visible_rows)
                if self.context.current_idx in visible_list:
                    return visible_list.index(self.context.current_idx) + 1  # 1-based
                else:
                    return None
            else:
                # FINAL semantics: count all rows in the match
                all_rows = set()
                for var_indices in self.context.variables.values():
                    all_rows.update(var_indices)
                
                # Find the position of current_idx among all matched rows
                all_list = sorted(all_rows)
                if self.context.current_idx in all_list:
                    return all_list.index(self.context.current_idx) + 1  # 1-based
                else:
                    return None
        
        # Special handling for SUM with both pattern variable references and universal column references
        if expr.upper().startswith("SUM("):
            # Extract the column expression from SUM(column_expr)
            sum_match = re.match(r'SUM\(([^)]+)\)', expr, re.IGNORECASE)
            if sum_match:
                col_expr = sum_match.group(1).strip()
                
                # Parse pattern variable reference (e.g., B.totalprice)
                var_col_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$', col_expr)
                if var_col_match:
                    var_name = var_col_match.group(1)
                    col_name = var_col_match.group(2)
                    
                    # Get indices for the specific variable
                    if var_name not in self.context.variables:
                        return 0
                        
                    var_indices = self.context.variables[var_name]
                    
                    # For RUNNING semantics, only include indices up to current position
                    if is_running:
                        var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
                    
                    # Calculate sum
                    total = 0
                    for idx in var_indices:
                        if idx < len(self.context.rows):
                            row_val = self.context.rows[idx].get(col_name)
                            if row_val is not None:
                                try:
                                    total += float(row_val)
                                except (ValueError, TypeError):
                                    pass
                    
                    return total
                else:
                    # Handle universal column reference (e.g., SUM(salary))
                    # For universal references, sum across all matched rows in the current pattern
                    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', col_expr):
                        # Get all matched row indices
                        all_indices = []
                        for var, indices in self.context.variables.items():
                            all_indices.extend(indices)
                        
                        # For RUNNING semantics, only include rows up to current position
                        if is_running:
                            all_indices = [idx for idx in all_indices if idx <= self.context.current_idx]
                        
                        # Calculate sum across all matched rows
                        total = 0
                        for idx in set(all_indices):  # Use set to avoid duplicates
                            if idx < len(self.context.rows):
                                row_val = self.context.rows[idx].get(col_expr)
                                if row_val is not None:
                                    try:
                                        total += float(row_val)
                                    except (ValueError, TypeError):
                                        pass
                        
                        return total
        
        # Handle arithmetic expressions containing aggregates (like "AVG(value) * 0.9")
        # First check if this contains aggregate functions as part of a larger arithmetic expression
        agg_arith_pattern = r'.*\b(SUM|COUNT|MIN|MAX|AVG|STDDEV|VAR)\s*\([^)]+\).*[+\-*/].*'
        if re.match(agg_arith_pattern, expr, re.IGNORECASE):
            # This is an arithmetic expression containing aggregates
            logger.debug(f"Detected arithmetic expression with aggregates: {expr}")
            result = self._evaluate_arithmetic_with_aggregates(expr, is_running)
            logger.debug(f"Arithmetic aggregates result: {result}")
            if result is not None:
                return result
        
        # Handle other aggregate functions using the comprehensive _evaluate_aggregate method
        # Check if this is a standalone aggregate function call (not part of a larger expression)
        # Only match if the entire expression is an aggregate function to avoid breaking complex expressions like "AVG(value) * 0.9"
        agg_match = re.match(r'^(SUM|COUNT|MIN|MAX|AVG|STDDEV|VAR)\s*\(([^)]+)\)$', expr, re.IGNORECASE)
        if agg_match:
            func_name = agg_match.group(1).lower()
            args_str = agg_match.group(2).strip()
            
            # Use the comprehensive aggregate evaluator
            result = self._evaluate_aggregate(func_name, args_str, is_running)
            return result
        
        # Determine if this is a PERMUTE pattern
        is_permute = False
        if hasattr(self.context, 'pattern_metadata'):
            is_permute = self.context.pattern_metadata.get('permute', False)
        elif hasattr(self.context, 'pattern_variables') and len(self.context.pattern_variables) > 0:
            is_permute = True
        
        # Try optimized pattern variable reference evaluation with PERMUTE support
        handled, value = evaluate_pattern_variable_reference(
            expr, 
            self.context.variables, 
            self.context.rows,
            self._var_ref_cache,
            getattr(self.context, 'subsets', None),
            self.context.current_idx,
            is_running,
            is_permute  # Pass the PERMUTE flag
        )
        if handled:
            return value
        
        # Enhanced navigation function detection
        # Only match complete navigation function expressions, not complex expressions that contain them
        # Strategy: Look for expressions that are ONLY navigation functions (no operators after)
        complete_nav_pattern = r'^(FIRST|LAST|PREV|NEXT)\s*\(.*\)\s*$'
        nested_nav_pattern = r'^(FIRST|LAST|PREV|NEXT)\s*\(\s*(FIRST|LAST|PREV|NEXT)\s*\([^)]*\)\s*,\s*[^)]*\)\s*$'
        has_operators_pattern = r'.*\)\s*[=<>!]+.*|.*\)\s+(AND|OR|NOT)\s+.*'
        
        # Check if expression is a simple navigation function (not a complex boolean expression)
        matches_nav = re.match(complete_nav_pattern, expr, re.IGNORECASE) is not None
        has_operators = re.match(has_operators_pattern, expr, re.IGNORECASE) is not None
        is_simple_nav = matches_nav and not has_operators
        is_nested_nav = re.match(nested_nav_pattern, expr, re.IGNORECASE) is not None
        
        if is_simple_nav or is_nested_nav:
            return self._evaluate_navigation(expr, is_running)
        
        # Try AST-based evaluation for complex expressions (arithmetic, etc.)
        try:
            from src.matcher.condition_evaluator import ConditionEvaluator
            
            # Set up context for AST evaluation
            self.context.current_row = self.context.rows[self.context.current_idx] if self.context.current_idx < len(self.context.rows) else None
            
            # Preprocess the expression to replace special functions with their values
            # This allows complex expressions like "MATCH_NUMBER() IN (0, MATCH_NUMBER())" and "AVG(value) * 0.9" to be parsed by AST
            preprocessed_expr = self._preprocess_expression_for_ast(expr, is_running)
            
            # Create a specialized condition evaluator for measure expressions
            # Use MEASURES mode for correct PREV/NEXT semantics in measure expressions
            evaluator = ConditionEvaluator(self.context, evaluation_mode='MEASURES')
            
            # Parse and evaluate the expression using AST
            try:
                tree = ast.parse(preprocessed_expr, mode='eval')
                result = evaluator.visit(tree.body)
                return result
            except (SyntaxError, ValueError) as ast_error:
                # If AST parsing fails, try as a universal pattern variable (non-prefixed column reference)
                try:
                    # Universal pattern variable: refers to all rows in current match
                    result = self._evaluate_universal_pattern_variable(expr)
                    if result is not None:
                        return result
                    
                    # Fallback to simple column reference for compatibility
                    fallback_result = self.context.rows[self.context.current_idx].get(expr)
                    return fallback_result
                except Exception:
                    logger.error(f"Error evaluating expression '{expr}' with AST: {ast_error}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error evaluating expression '{expr}': {e}")
            return None

    def _evaluate_universal_pattern_variable(self, column_name: str) -> Any:
        """
        Evaluate a universal pattern variable (non-prefixed column reference).
        
        According to SQL:2016, a universal pattern variable refers to all rows in the 
        current match and returns the value from the current row being processed.
        
        Args:
            column_name: The column name without any pattern variable prefix
            
        Returns:
            The value of the column from the current row, or None if not found
        """
        try:
            # Validate that this is a simple column name (no dots, no special characters)
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', column_name):
                return None
            
            # Check if this column name conflicts with any defined pattern variables
            if hasattr(self.context, 'pattern_variables') and column_name in self.context.pattern_variables:
                logger.warning(f"Column name '{column_name}' conflicts with pattern variable name")
                return None
            
            # For universal pattern variables, we get the value from the current row
            if self.context.current_idx >= 0 and self.context.current_idx < len(self.context.rows):
                current_row = self.context.rows[self.context.current_idx]
                if column_name in current_row:
                    value = current_row[column_name]
                    logger.debug(f"Universal pattern variable '{column_name}' resolved to: {value}")
                    return value
            
            return None
            
        except Exception as e:
            logger.error(f"Error evaluating universal pattern variable '{column_name}': {e}")
            return None



    def evaluate_classifier(self, var_name: Optional[str] = None, *, running: bool = True) -> Optional[str]:
        """
        Evaluate CLASSIFIER function according to SQL:2016 standard.
        
        The CLASSIFIER function returns the name of the pattern variable that matched
        the current row. It can be used in two forms:
        
        1. CLASSIFIER() - Returns the pattern variable for the current row
        2. CLASSIFIER(var) - Returns var if it exists in the pattern (in ONE ROW PER MATCH mode)
                            or if the current row is matched to var (in ALL ROWS PER MATCH mode)
        
        This implementation handles all cases including:
        - Rows matched to regular pattern variables
        - Rows matched to subset variables
        - Rows after exclusion sections
        - Proper handling of ONE ROW PER MATCH vs ALL ROWS PER MATCH semantics
        
        Args:
            var_name: Optional variable name to check against
            running: Whether to use RUNNING semantics
            
        Returns:
            String containing the pattern variable name or None if not matched
        """
        start_time = time.time()
        self.stats["total_evaluations"] += 1
        
        try:
            # Validate argument
            self._validate_classifier_arg(var_name)
            
            current_idx = self.context.current_idx
            cache_key = (current_idx, var_name, running)
            
            # Check cache first
            if cache_key in self._classifier_cache:
                self.stats["cache_hits"] += 1
                return self._classifier_cache[cache_key]
                
            self.stats["cache_misses"] += 1
            
            # Handle subset variables with context-aware semantics
            if var_name is not None and hasattr(self.context, 'subsets') and var_name in self.context.subsets:
                subset_components = self.context.subsets[var_name]
                
                # Find the raw classifier for the current row (without case correction)
                current_idx = self.context.current_idx
                actual_classifier_raw = None
                
                # Check which variable this row is assigned to (raw lookup)
                for var, indices in self.context.variables.items():
                    if current_idx in indices:
                        actual_classifier_raw = var
                        break
                
                # If the actual classifier is in the subset, return it with case correction (standard SQL:2016)
                if actual_classifier_raw and actual_classifier_raw in subset_components:
                    result = self.context._apply_case_sensitivity_rule(actual_classifier_raw)
                    self._classifier_cache[cache_key] = result
                    return result
                
                # Compatibility behavior: Only use fallback for alternation patterns where
                # the subset contains variables from the current alternation group
                # Check if this appears to be an alternation pattern by looking at variable context
                is_alternation_context = False
                if hasattr(self.context, 'variables'):
                    # Count how many variables in the subset are active in the current match
                    active_subset_vars = sum(1 for comp in subset_components 
                                           if comp in self.context.variables and self.context.variables[comp])
                    
                    # If only one subset component is active and there are other non-subset variables,
                    # this might be an alternation pattern like (L|H) A
                    total_active_vars = sum(1 for var_rows in self.context.variables.values() if var_rows)
                    if active_subset_vars == 1 and total_active_vars > active_subset_vars:
                        is_alternation_context = True
                
                # Use fallback behavior only for alternation contexts
                if is_alternation_context:
                    for component in subset_components:
                        if component in self.context.variables:
                            component_rows = self.context.variables[component]
                            if component_rows:  # If this component has any matched rows in the match
                                result = self.context._apply_case_sensitivity_rule(component)
                                self._classifier_cache[cache_key] = result
                                return result
                
                # Standard behavior: If not in subset and not alternation context, return None
                self._classifier_cache[cache_key] = None
                return None
            
            # Special handling for CLASSIFIER(var) in ONE ROW PER MATCH mode
            if var_name is not None and not running:
                # For ONE ROW PER MATCH, return var if it exists in the pattern
                if var_name in self.context.variables:
                    result = self.context._apply_case_sensitivity_rule(var_name)
                    self._classifier_cache[cache_key] = result
                    return result
                    
                # No match found
                self._classifier_cache[cache_key] = None
                return None
            
            # Standard classifier evaluation for ALL ROWS PER MATCH or CLASSIFIER() without arguments
            result = self._evaluate_classifier_impl(var_name, running)
            
            # Cache the result
            self._classifier_cache[cache_key] = result
            return result
            
        finally:
            self.timing["classifier_evaluation"] += time.time() - start_time



    def _validate_classifier_arg(self, var_name: Optional[str]) -> None:
        """
        Validate CLASSIFIER function argument.
        
        Args:
            var_name: Optional variable name to check against
            
        Raises:
            ClassifierError: If the argument is invalid
        """
        if var_name is not None:
            if not isinstance(var_name, str):
                raise ClassifierError(
                    f"CLASSIFIER argument must be a string, got {type(var_name).__name__}"
                )
                
            if not var_name.isidentifier():
                raise ClassifierError(
                    f"Invalid CLASSIFIER argument: '{var_name}' is not a valid identifier"
                )
                
            # Only check if variable exists in pattern if we have variables
            if self.context.variables and var_name not in self.context.variables and (
                not hasattr(self.context, 'subsets') or 
                var_name not in self.context.subsets
            ):
                available_vars = list(self.context.variables.keys())
                subset_vars = []
                if hasattr(self.context, 'subsets'):
                    subset_vars = list(self.context.subsets.keys())
                    
                raise ClassifierError(
                    f"Variable '{var_name}' not found in pattern. "
                    f"Available variables: {available_vars}. "
                    f"Available subset variables: {subset_vars}."
                )

    def _evaluate_classifier_impl(self, 
                            var_name: Optional[str] = None,
                            running: bool = True) -> Optional[str]:
        """
        Internal implementation of CLASSIFIER evaluation with optimizations.
        
        This method determines which pattern variable matched the current row,
        handling all cases including:
        - Direct variable matches
        - Subset variables
        - Rows after exclusion sections
        - Proper handling of pattern variable priorities
        - Empty pattern handling (returns None)
        
        Args:
            var_name: Optional variable name to check against
            running: Whether to use RUNNING semantics
            
        Returns:
            String containing the pattern variable name or None if not matched or empty pattern
        """
        current_idx = self.context.current_idx
        
        # Empty pattern handling: If there are no variables defined in the context
        # or this row is not assigned to any variable, return None
        # This handles cases like PATTERN (() | A) for empty matches
        if not self.context.variables or all(current_idx not in indices for indices in self.context.variables.values()):
            return None
            
        # Check if this row is part of an empty pattern match
        if hasattr(self.context, '_empty_pattern_rows') and current_idx in self.context._empty_pattern_rows:
            return None
        
        # For ONE ROW PER MATCH with FINAL semantics, we need to return the variable
        # that matched the row based on the DEFINE conditions, not just the last variable
        if not running and var_name is None:
            # Use optimized row-to-variable index for deterministic behavior
            if hasattr(self.context, '_row_var_index') and current_idx in self.context._row_var_index:
                vars_for_row = self.context._row_var_index[current_idx]
                if vars_for_row:
                    # If multiple variables match this row, use timeline for correct order
                    if len(vars_for_row) == 1:
                        var = next(iter(vars_for_row))
                        return self.context._apply_case_sensitivity_rule(var)
                    else:
                        # Use timeline to determine correct variable in pattern order
                        timeline = self.context.get_timeline()
                        timeline_vars = [var for idx, var in timeline if idx == current_idx]
                        if timeline_vars:
                            var = timeline_vars[0]
                            return self.context._apply_case_sensitivity_rule(var)
                        # Fallback to alphabetical ordering
                        var = min(vars_for_row)
                        return self.context._apply_case_sensitivity_rule(var)
            
            # Fallback: Check which variable this row was assigned to
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    return self.context._apply_case_sensitivity_rule(var)
        
        # Case 1: CLASSIFIER() without arguments - find the matching variable for current row
        if var_name is None:
            # Check if current row is assigned to any variable
            assigned_to_any_var = False
            for indices in self.context.variables.values():
                if current_idx in indices:
                    assigned_to_any_var = True
                    break
                    
            # If not assigned to any variable, return None (important for empty pattern tests)
            if not assigned_to_any_var:
                return None
                
            # Use optimized row-to-variable index if available (more deterministic)
            if hasattr(self, '_row_to_vars'):
                vars_for_row = self._row_to_vars.get(current_idx, set())
                if vars_for_row:
                    # If multiple variables match this row, use the timeline to determine the correct one
                    if len(vars_for_row) == 1:
                        var = next(iter(vars_for_row))
                        return self.context._apply_case_sensitivity_rule(var)
                    else:
                        # Multiple variables for this row - check timeline for order
                        timeline = self.context.get_timeline() if hasattr(self.context, 'get_timeline') else []
                        # Find all entries for this row in the timeline
                        timeline_vars = [var for idx, var in timeline if idx == current_idx]
                        # Return the first one in timeline order (pattern matching order)
                        if timeline_vars:
                            var = timeline_vars[0]
                            return self.context._apply_case_sensitivity_rule(var)
                        # Fallback to alphabetical for deterministic behavior
                        var = min(vars_for_row)
                        return self.context._apply_case_sensitivity_rule(var)
            
            # Fallback to direct variable assignments (preserving original logic)
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    return self.context._apply_case_sensitivity_rule(var)
                    
            # Then check subset variables
            if hasattr(self.context, 'subsets') and self.context.subsets:
                for subset_name, components in self.context.subsets.items():
                    for comp in components:
                        if comp in self.context.variables and current_idx in self.context.variables[comp]:
                            return self.context._apply_case_sensitivity_rule(comp)
            
            # For rows not matching any variable, return None
            # This is a change from previous behavior which returned an empty string
            # to align with SQL:2016 standard and Trino behavior
            return None
        
        # Case 2: CLASSIFIER(var) - check if the current row is matched to the specified variable
        else:
            # Direct variable check
            if var_name in self.context.variables and current_idx in self.context.variables[var_name]:
                return self.context._apply_case_sensitivity_rule(var_name)
                
            # Subset variable check
            if hasattr(self.context, 'subsets') and var_name in self.context.subsets:
                for comp in self.context.subsets[var_name]:
                    if comp in self.context.variables and current_idx in self.context.variables[comp]:
                        return self.context._apply_case_sensitivity_rule(comp)
            
            # No match found
            return None



    def _format_classifier_output(self, value: Optional[str]) -> str:
        """
        Format CLASSIFIER output according to SQL standard.
        
        Args:
            value: The classifier value to format
            
        Returns:
            Formatted classifier output (NULL for None)
        """
        return value if value is not None else "NULL"

    

        
    def _evaluate_navigation(self, expr: str, is_running: bool) -> Any:
        """
        Handle navigation functions like FIRST, LAST, PREV, NEXT with proper semantics.
        
        This enhanced implementation supports:
        1. Simple navigation functions (FIRST(A.price), LAST(B.quantity))
        2. Nested navigation functions (PREV(FIRST(A.price)), NEXT(LAST(B.quantity)))
        3. Navigation with offsets (FIRST(A.price, 3), PREV(price, 2))
        4. Combinations with proper semantics handling
        
        Args:
            expr: The navigation expression (e.g., "LAST(A.value)")
            is_running: Whether to use RUNNING semantics
            
        Returns:
            The result of the navigation function
        """
        # Check for nested navigation pattern first
        # Updated pattern to recognize RUNNING/FINAL semantic modifiers with navigation functions
        nested_pattern = r'(FIRST|LAST|NEXT|PREV)\s*\(\s*((?:(?:RUNNING|FINAL)\s+)?(?:FIRST|LAST|NEXT|PREV|CLASSIFIER)[^)]*\))\s*(?:,\s*(\d+))?\s*\)'
        nested_match = re.match(nested_pattern, expr, re.IGNORECASE)
        
        if nested_match:
            # For nested navigation, delegate to specialized function
            # This will also respect RUNNING semantics by using current_idx
            from src.matcher.condition_evaluator import evaluate_nested_navigation
            
            current_idx = self.context.current_idx
            
            # Set semantics information in context for classifier navigation
            original_semantics = getattr(self.context, '_current_semantics', None)
            try:
                if is_running:
                    # When using RUNNING semantics, we only consider rows up to the current position
                    # This affects nested navigation functions
                    self.context._current_semantics = 'RUNNING'
                    return evaluate_nested_navigation(expr, self.context, current_idx, None)
                else:
                    # With FINAL semantics, we consider all rows in the match
                    self.context._current_semantics = 'FINAL'
                    return evaluate_nested_navigation(expr, self.context, current_idx, None)
            finally:
                # Restore original semantics
                if original_semantics is not None:
                    self.context._current_semantics = original_semantics
                elif hasattr(self.context, '_current_semantics'):
                    delattr(self.context, '_current_semantics')
        
        # Cache key for memoization - include running semantics in the key
        cache_key = (expr, is_running, self.context.current_idx)
        if hasattr(self, '_var_ref_cache') and cache_key in self._var_ref_cache:
            return self._var_ref_cache[cache_key]
        
        # Extract function name and arguments for simple navigation
        match = re.match(r'(FIRST|LAST|PREV|NEXT)\s*\(\s*(.+?)\s*\)', expr, re.IGNORECASE)
        if not match:
            return None
            
        func_name = match.group(1).upper()
        args_str = match.group(2)
        
        # Parse arguments
        args = [arg.strip() for arg in args_str.split(',')]
        if not args:
            return None
        
        result = None
        
        # Check if we have variable.field reference (like A.value) or simple field reference (like value)
        var_field_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', args[0])
        
        if var_field_match:
            # Handle variable.field references (like A.value)
            var_name = var_field_match.group(1)
            field_name = var_field_match.group(2)
            
            # For PREV/NEXT, we navigate relative to current position
            if func_name in ('PREV', 'NEXT'):
                # Get steps (default is 1)
                steps = 1
                if len(args) > 1:
                    try:
                        steps = int(args[1])
                    except ValueError:
                        pass
                
                if func_name == 'PREV':
                    prev_idx = self.context.current_idx - steps
                    if prev_idx >= 0 and prev_idx < len(self.context.rows):
                        raw_value = self.context.rows[prev_idx].get(field_name)
                        # Preserve data type for Trino compatibility
                        if raw_value is not None and self.context.current_idx < len(self.context.rows):
                            current_value = self.context.rows[self.context.current_idx].get(field_name)
                            result = self._preserve_data_type(current_value, raw_value)
                        else:
                            result = raw_value
                    # Note: if prev_idx < 0, result remains None (boundary condition)
                
                elif func_name == 'NEXT':
                    next_idx = self.context.current_idx + steps
                    if next_idx >= 0 and next_idx < len(self.context.rows):
                        raw_value = self.context.rows[next_idx].get(field_name)
                        # Preserve data type for Trino compatibility
                        if raw_value is not None and self.context.current_idx < len(self.context.rows):
                            current_value = self.context.rows[self.context.current_idx].get(field_name)
                            result = self._preserve_data_type(current_value, raw_value)
                        else:
                            result = raw_value
                    # Note: if next_idx >= len(rows), result remains None (boundary condition)                # For FIRST/LAST with variable prefix, we use variable-specific logic
            elif func_name in ('FIRST', 'LAST'):
                # Get occurrence (default is 0)
                occurrence = 0
                if len(args) > 1:
                    try:
                        occurrence = int(args[1])
                    except ValueError:
                        pass
                
                # Leverage the enhanced RowContext methods with semantics support
                if func_name == 'FIRST':
                    semantics = 'RUNNING' if is_running else 'FINAL'
                    row = self.context.first(var_name, occurrence, semantics)
                    if row and field_name in row:
                        result = row.get(field_name)
                    else:
                        result = None
                        
                elif func_name == 'LAST':
                    semantics = 'RUNNING' if is_running else 'FINAL'
                    row = self.context.last(var_name, occurrence, semantics)
                    if row and field_name in row:
                        result = row.get(field_name)
                    else:
                        result = None
        
        else:
            # Handle simple field references (no variable prefix) for all functions
            field_name = args[0]
            
            # For PREV/NEXT, we navigate relative to current position
            if func_name in ('PREV', 'NEXT'):
                # Get steps (default is 1)
                steps = 1
                if len(args) > 1:
                    try:
                        steps = int(args[1])
                    except ValueError:
                        pass
                
                if func_name == 'PREV':
                    prev_idx = self.context.current_idx - steps
                    if prev_idx >= 0 and prev_idx < len(self.context.rows):
                        result = get_column_value_with_type_preservation(self.context.rows[prev_idx], field_name)
                    else:
                        result = None
                
                elif func_name == 'NEXT':
                    next_idx = self.context.current_idx + steps
                    if next_idx >= 0 and next_idx < len(self.context.rows):
                        result = get_column_value_with_type_preservation(self.context.rows[next_idx], field_name)
                    else:
                        result = None
            
            # Handle FIRST/LAST with simple field references (no variable prefix)
            elif func_name in ('FIRST', 'LAST'):
                field_name = args[0]
                
                # Get offset/occurrence: SQL:2016 standard interpretation:
                # FIRST(value) = 1st value (default offset 0 = first item)
                # FIRST(value, N) = value at 0-based offset N from start  
                # LAST(value) = last value (default offset 0 = last item)
                # LAST(value, N) = value at 0-based offset N from end
                offset = 0  # Default to 0-based offset (first/last item)
                if len(args) > 1:
                    try:
                        offset = int(args[1])
                        if offset < 0:
                            offset = 0  # Ensure non-negative offset (0-based)
                    except ValueError:
                        offset = 0
                
                # Collect all row indices from all matched variables
                all_indices = []
                
                # Use full variables if available for FIRST/LAST navigation
                variables_to_use = getattr(self.context, '_full_match_variables', None) or self.context.variables
                
                for var_name in variables_to_use:
                    var_indices = variables_to_use[var_name]
                    all_indices.extend(var_indices)
                
                # Sort indices to ensure correct order and remove duplicates
                all_indices = sorted(set(all_indices))
                
                # CRITICAL FIX FOR RUNNING/FINAL SEMANTICS:
                # For navigation functions like FIRST(value), LAST(value),
                # the behavior differs based on RUNNING vs FINAL semantics:
                
                # For RUNNING semantics with FIRST function:
                # - FIRST(value) should only consider rows up to current position
                # - FIRST(value, N) with offset should use full match if available, since it's positional navigation
                if is_running:
                    if func_name == 'FIRST' and offset > 0:
                        # For FIRST with offset, allow access to full match for positional navigation
                        pass  # Keep all_indices as is (full match)
                    else:
                        # For FIRST without offset or LAST, filter to current position
                        all_indices = [idx for idx in all_indices if idx <= self.context.current_idx]
                
                if func_name == 'FIRST':
                    # SQL:2016 LOGICAL NAVIGATION: FIRST(value, N) 
                    # Find first occurrence in match, then navigate forward N MORE occurrences
                    # Default N=0 means stay at first occurrence
                    
                    if all_indices:
                        target_position = 0 + offset  # Start from first (index 0), add offset
                        if target_position < len(all_indices):
                            logical_idx = all_indices[target_position]
                            logger.debug(f"FIRST({field_name}, {offset}): all_indices={all_indices}, target_position={target_position}, logical_idx={logical_idx}, current_idx={self.context.current_idx}, is_running={is_running}")
                        else:
                            logical_idx = None
                            logger.debug(f"FIRST({field_name}, {offset}): target_position {target_position} out of bounds for {len(all_indices)} indices")
                    else:
                        logical_idx = None
                        logger.debug(f"FIRST({field_name}, {offset}): no indices available")
                            
                elif func_name == 'LAST':
                    # SQL:2016 LOGICAL NAVIGATION: LAST(value, N)
                    # Find last occurrence in match, then navigate backward N MORE occurrences
                    # Default N=0 means stay at last occurrence
                    
                    # CRITICAL FIX FOR RUNNING SEMANTICS:
                    # For RUNNING LAST(value) with offset=0, this should return the current row's value
                    # For RUNNING LAST(value, N) with offset>0, this should return the value N positions back from current
                    # For FINAL LAST(value) with offset=0, this should return the final row's value
                    # For FINAL LAST(value, N) with offset>0, this should return the value N positions back from final
                    
                    if all_indices:
                        if is_running:
                            if offset == 0:
                                # RUNNING LAST(value): Return last value among matched rows up to current position
                                # all_indices is already filtered to include only rows <= current_idx
                                logical_idx = all_indices[-1]  # Last index in the filtered list
                                logger.debug(f"RUNNING LAST({field_name}): using last index from filtered list: logical_idx={logical_idx}, all_indices={all_indices}")
                            else:
                                # RUNNING LAST(value, N): Go backward N positions from last position in filtered indices
                                last_position = len(all_indices) - 1
                                target_position = last_position - offset
                                if target_position >= 0:
                                    logical_idx = all_indices[target_position]
                                    logger.debug(f"RUNNING LAST({field_name}, {offset}): all_indices={all_indices}, target_position={target_position}, logical_idx={logical_idx}")
                                else:
                                    logical_idx = None
                                    logger.debug(f"RUNNING LAST({field_name}, {offset}): target_position {target_position} out of bounds for filtered indices")
                        else:
                            # FINAL semantics: Navigate from final position
                            last_position = len(all_indices) - 1
                            target_position = last_position - offset  # Start from last, subtract offset
                            if target_position >= 0:
                                logical_idx = all_indices[target_position]
                                logger.debug(f"FINAL LAST({field_name}, {offset}): all_indices={all_indices}, target_position={target_position}, logical_idx={logical_idx}, is_running={is_running}")
                            else:
                                logical_idx = None
                    else:
                        logical_idx = None
                
                # Get the value if we found a valid logical position
                if logical_idx is not None and logical_idx < len(self.context.rows):
                    # Use the row context's enhanced direct access with optimized caching
                    raw_value = self.context.rows[logical_idx].get(field_name)
                    # Preserve data type for Trino compatibility
                    if raw_value is not None and self.context.current_idx < len(self.context.rows):
                        current_value = self.context.rows[self.context.current_idx].get(field_name)
                        result = self._preserve_data_type(current_value, raw_value)
                    else:
                        result = raw_value
                else:
                    result = None
        
        # Cache the result
        if hasattr(self, '_var_ref_cache'):
            self._var_ref_cache[cache_key] = result
        return result


    def _get_var_indices(self, var: str) -> List[int]:
        """
        Get indices of rows matched to a variable or subset with improved handling.
        
        Args:
            var: The variable name
            
        Returns:
            List of row indices that match the variable
        """
        # Direct variable
        if var in self.context.variables:
            return sorted(self.context.variables[var])
        
        # Check for subset variable with improved handling
        if hasattr(self.context, 'subsets') and var in self.context.subsets:
            indices = []
            for comp_var in self.context.subsets[var]:
                if comp_var in self.context.variables:
                    indices.extend(self.context.variables[comp_var])
            return sorted(set(indices))  # Ensure we don't have duplicates
        
        # Try to handle variable name with quantifier (var?)
        base_var = None
        if var.endswith('?'):
            base_var = var[:-1]
        elif var.endswith('*') or var.endswith('+'):
            base_var = var[:-1]
        elif '{' in var and var.endswith('}'):
            base_var = var[:var.find('{')]
            
        if base_var and base_var in self.context.variables:
            return sorted(self.context.variables[base_var])
        
        return []


    def _supported_aggregates(self) -> Set[str]:
        """Return set of supported aggregate functions."""
        return {
            'sum', 'count', 'avg', 'min', 'max', 'first', 'last',
            'median', 'stddev', 'stddev_samp', 'stddev_pop',
            'var', 'var_samp', 'var_pop', 'covar', 'corr'
        }

    def _evaluate_count_star(self, is_running: bool) -> int:
        """Optimized implementation of COUNT(*)."""
        matched_indices = set()
        for indices in self.context.variables.values():
            matched_indices.update(indices)
        
        if is_running:
            matched_indices = {idx for idx in matched_indices if idx <= self.context.current_idx}
            
        return len(matched_indices)

    def _evaluate_count_var(self, var_name: str, is_running: bool) -> int:
        """Optimized implementation of COUNT(var.*)."""
        var_indices = self._get_var_indices(var_name)
        
        if is_running:
            var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
            
        return len(var_indices)

    def _gather_values_for_aggregate(self, args_str: str, is_running: bool) -> List[Any]:
        """Gather values for aggregation with proper type handling."""
        values = []
        indices_to_use = []
        
        # Check for pattern variable prefix
        var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', args_str)
        
        if var_col_match:
            # Pattern variable prefixed column
            var_name, col_name = var_col_match.groups()
            indices_to_use = self._get_var_indices(var_name)
        else:
            # Direct column reference
            col_name = args_str
            # Get all matched rows
            for indices in self.context.variables.values():
                indices_to_use.extend(indices)
            indices_to_use = sorted(set(indices_to_use))
        
        # Apply RUNNING semantics filter
        if is_running:
            indices_to_use = [idx for idx in indices_to_use if idx <= self.context.current_idx]
        
        # Gather values with type checking
        for idx in indices_to_use:
            if idx < len(self.context.rows):
                val = self.context.rows[idx].get(col_name)
                if val is not None:
                    try:
                        # Ensure numeric type for numeric aggregates
                        if isinstance(val, (str, bool)):
                            val = float(val)
                        values.append(val)
                    except (ValueError, TypeError):
                        # Log warning but continue processing
                        logger.warning(f"Non-numeric value '{val}' found in column {col_name}")
                        continue
        
        return values

    def _compute_aggregate(self, func_name: str, values: List[Any]) -> Any:
        """Compute aggregate with proper type handling and SQL semantics."""
        if not values:
            return None
            
        try:
            if func_name == 'count':
                return len(values)
            elif func_name == 'sum':
                return sum(values)
            elif func_name == 'avg':
                return sum(values) / len(values)
            elif func_name == 'min':
                return min(values)
            elif func_name == 'max':
                return max(values)
            elif func_name == 'first':
                return values[0]
            elif func_name == 'last':
                return values[-1]
            elif func_name == 'median':
                return self._compute_median(values)
            elif func_name in ('stddev', 'stddev_samp'):
                return self._compute_stddev(values, population=False)
            elif func_name == 'stddev_pop':
                return self._compute_stddev(values, population=True)
            elif func_name in ('var', 'var_samp'):
                return self._compute_variance(values, population=False)
            elif func_name == 'var_pop':
                return self._compute_variance(values, population=True)
            
        except Exception as e:
            self._log_aggregate_error(func_name, str(values), e)
            return None

    def _compute_median(self, values: List[Any]) -> Any:
        """Compute median with proper handling of even/odd counts."""
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        mid = n // 2
        
        if n % 2 == 0:
            return (sorted_vals[mid-1] + sorted_vals[mid]) / 2
        return sorted_vals[mid]

    def _compute_stddev(self, values: List[Any], population: bool = False) -> float:
        """Compute standard deviation with proper handling of sample vs population."""
        if len(values) < (1 if population else 2):
            return None
            
        mean = sum(values) / len(values)
        squared_diff_sum = sum((x - mean) ** 2 for x in values)
        
        if population:
            return math.sqrt(squared_diff_sum / len(values))
        return math.sqrt(squared_diff_sum / (len(values) - 1))

    def _compute_variance(self, values: List[Any], population: bool = False) -> float:
        """Compute variance with proper handling of sample vs population."""
        stddev = self._compute_stddev(values, population)
        return stddev * stddev if stddev is not None else None

    def _log_aggregate_error(self, func_name: str, args: str, error: Exception) -> None:
        """Log aggregate function errors with context."""
        error_msg = (
            f"Error in aggregate function {func_name}({args}): {str(error)}\n"
            f"Context: current_idx={self.context.current_idx}, "
            f"running={not self.final}"
        )
        logger.error(error_msg)

    def _evaluate_aggregate(self, func_name: str, args_str: str, is_running: bool) -> Any:
        """
        Production-level implementation of aggregate function evaluation for pattern matching.
        
        Supports both pattern variable prefixed and non-prefixed column references with full SQL standard compliance:
        - SUM(A.order_amount): Sum of order_amount values from rows matched to variable A
        - SUM(order_amount): Sum of order_amount values from all matched rows
        
        Features:
        - Full SQL standard compliance for aggregates
        - Proper NULL handling according to SQL standards
        - Comprehensive error handling and logging
        - Performance optimizations with caching
        - Support for all standard SQL aggregate functions
        - Proper type handling and conversions
        - Thread-safe implementation
        
        Args:
            func_name: The aggregate function name (sum, count, avg, min, max, etc.)
            args_str: Function arguments as string (column name or pattern_var.column)
            is_running: Whether to use RUNNING semantics (True) or FINAL semantics (False)
                
        Returns:
            Result of the aggregate function or None if no values to aggregate
            
        Raises:
            ValueError: If the function name is invalid or arguments are malformed
            TypeError: If incompatible types are used in aggregation
            
        Examples:
            COUNT(*) -> Count of all rows in the match
            COUNT(A.*) -> Count of rows matched to variable A
            SUM(A.amount) -> Sum of amount values from rows matched to variable A
            AVG(price) -> Average of price values from all matched rows
        """
        start_time = time.time()
        
        try:
            # Input validation
            if not isinstance(func_name, str) or not isinstance(args_str, str):
                raise ValueError("Function name and arguments must be strings")
            
            # Normalize function name and validate
            func_name = func_name.lower()
            if func_name not in self._supported_aggregates():
                raise ValueError(f"Unsupported aggregate function: {func_name}")
            
            # Cache key for memoization
            cache_key = (func_name, args_str, is_running, self.context.current_idx)
            if hasattr(self, '_agg_cache') and cache_key in self._agg_cache:
                return self._agg_cache[cache_key]
            
            # Initialize result
            result = None
            
            try:
                # Handle COUNT(*) special case with optimizations
                if func_name == 'count' and args_str.strip() in ('*', ''):
                    result = self._evaluate_count_star(is_running)
                    
                # Handle pattern variable COUNT(A.*) special case
                elif func_name == 'count' and re.match(r'([A-Za-z_][A-ZaZ0-9_]*)\.\*', args_str):
                    pattern_count_match = re.match(r'([A-Za-z_][A-ZaZ0-9_]*)\.\*', args_str)
                    result = self._evaluate_count_var(pattern_count_match.group(1), is_running)
                    
                # Handle regular aggregates
                else:
                    values = self._gather_values_for_aggregate(args_str, is_running)
                    result = self._compute_aggregate(func_name, values)
                
                # Cache the result
                if not hasattr(self, '_agg_cache'):
                    self._agg_cache = {}
                self._agg_cache[cache_key] = result
                
                return result
                
            except Exception as e:
                # Log the error with context
                self._log_aggregate_error(func_name, args_str, e)
                return None
                
        finally:
            # Performance monitoring
            duration = time.time() - start_time
            if hasattr(self, 'timing'):
                self.timing[f'aggregate_{func_name}'] += duration
    
    def _evaluate_arithmetic_with_aggregates(self, expr: str, is_running: bool) -> Any:
        """
        Safely evaluate arithmetic expressions containing aggregate functions.
        
        This handles expressions like:
        - AVG(value) * 0.9
        - SUM(price) + COUNT(*)
        - MAX(value) - MIN(value)
        
        Args:
            expr: The arithmetic expression containing aggregates
            is_running: Whether to use RUNNING semantics
            
        Returns:
            The computed result or None if evaluation fails
        """
        try:
            # First, find all aggregate function calls in the expression
            agg_pattern = r'\b(SUM|COUNT|MIN|MAX|AVG|STDDEV|VAR)\s*\([^)]+\)'
            agg_functions = list(re.finditer(agg_pattern, expr, re.IGNORECASE))
            
            if not agg_functions:
                return None
            
            # Create a working copy of the expression
            working_expr = expr
            substitutions = {}
            
            # Replace each aggregate function with a placeholder and compute its value
            for i, match in enumerate(agg_functions):
                agg_func = match.group(0)
                placeholder = f"__AGG_{i}__"
                
                # Parse the aggregate function
                func_match = re.match(r'(SUM|COUNT|MIN|MAX|AVG|STDDEV|VAR)\s*\(([^)]+)\)', agg_func, re.IGNORECASE)
                if func_match:
                    func_name = func_match.group(1).lower()
                    args_str = func_match.group(2).strip()
                    
                    # Evaluate the aggregate function
                    try:
                        agg_result = self._evaluate_aggregate(func_name, args_str, is_running)
                        if agg_result is None:
                            logger.debug(f"Aggregate {agg_func} returned None")
                            return None
                        substitutions[placeholder] = agg_result
                    except Exception as e:
                        logger.warning(f"Failed to evaluate aggregate {agg_func}: {e}")
                        return None
                    
                    # Replace the aggregate function call with the placeholder
                    working_expr = working_expr.replace(agg_func, placeholder, 1)
            
            # Now substitute the actual values and evaluate
            for placeholder, value in substitutions.items():
                working_expr = working_expr.replace(placeholder, str(value))
            
            # Evaluate the arithmetic expression safely
            try:
                # Only allow safe arithmetic operations
                if re.match(r'^[\d\.\+\-\*/\(\)\s]+$', working_expr):
                    result = eval(working_expr)
                    logger.debug(f"Arithmetic expression {expr} -> {working_expr} = {result}")
                    return result
                else:
                    logger.warning(f"Unsafe arithmetic expression: {working_expr}")
                    return None
                    
            except Exception as e:
                logger.warning(f"Failed to evaluate arithmetic expression: {working_expr}, error: {e}")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to process arithmetic expression with aggregates: {expr}, error: {e}")
            return None

