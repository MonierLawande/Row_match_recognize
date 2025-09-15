# src/matcher/condition_evaluator.py
"""
Production-ready condition evaluator for SQL:2016 row pattern matching.

This module implements comprehensive condition evaluation with full support for:
- SQL:2016 pattern matching semantics
- Enhanced navigation functions (FIRST, LAST, PREV, NEXT)
- Pattern variable references and subset variables
- Mathematical and utility functions
- Advanced error handling and validation
- Performance optimization with caching

Refactored to eliminate duplication and improve maintainability.

Author: Pattern Matching Engine Team
Version: 2.0.0
"""

import ast
import operator
import re
import time
import threading
from typing import Dict, Any, Optional, Callable, List, Union, Tuple, Set
from dataclasses import dataclass

from src.matcher.row_context import RowContext
from src.matcher.evaluation_utils import (
    EvaluationMode, ValidationError, ExpressionValidationError,
    validate_expression_length, validate_recursion_depth,
    is_null, safe_compare, is_table_prefix, MATH_FUNCTIONS, 
    evaluate_math_function, get_evaluation_metrics
)
from src.utils.logging_config import get_logger, PerformanceTimer

# Module logger
logger = get_logger(__name__)

# Define the type for condition functions
ConditionFn = Callable[[Dict[str, Any], RowContext], bool]

# Enhanced Navigation Function Info for better structured parsing
@dataclass
class NavigationFunctionInfo:
    """Information about a navigation function call."""
    function_type: str  # PREV, NEXT, FIRST, LAST
    variable: Optional[str]
    column: Optional[str]
    offset: int
    is_nested: bool
    inner_functions: List['NavigationFunctionInfo']
    raw_expression: str

class ConditionEvaluator(ast.NodeVisitor):
    """
    Production-ready condition evaluator with comprehensive SQL:2016 support.
    
    This class provides enhanced condition evaluation with:
    - Context-aware navigation (physical for DEFINE, logical for MEASURES)
    - Pattern variable reference resolution
    - Mathematical and utility function evaluation
    - Comprehensive error handling and validation
    - Performance optimization with caching
    
    Refactored to eliminate duplication and improve maintainability.
    """
    
    def __init__(self, context: RowContext, evaluation_mode='DEFINE', recursion_depth=0):
        """
        Initialize condition evaluator with context-aware navigation.
        
        Args:
            context: RowContext for pattern matching
            evaluation_mode: 'DEFINE' for physical navigation, 'MEASURES' for logical navigation
            recursion_depth: Current recursion depth to prevent infinite recursion
        """
        # Input validation
        if not isinstance(context, RowContext):
            raise ValueError(f"Expected RowContext, got {type(context)}")
        
        self.context = context
        self.current_row = None
        self.evaluation_mode = evaluation_mode
        self.recursion_depth = recursion_depth
        self.max_recursion_depth = 20  # Increased for complex patterns
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Performance tracking
        self.stats = {
            "evaluations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "navigation_calls": 0,
            "math_function_calls": 0
        }
        
        # Initialize visit stack for recursion tracking
        self.visit_stack = set()
        
        # Build optimized indices
        self._build_evaluation_indices()

    
    def _build_evaluation_indices(self) -> None:
        """Build optimized indices for fast evaluation."""
        try:
            with self._lock:
                # Build row-to-variable mapping for fast lookups
                self._row_var_index = {}
                for var_name, indices in self.context.variables.items():
                    for idx in indices:
                        if isinstance(idx, int) and 0 <= idx < len(self.context.rows):
                            if idx not in self._row_var_index:
                                self._row_var_index[idx] = set()
                            self._row_var_index[idx].add(var_name)
                
                # Build subset memberships
                if hasattr(self.context, 'subsets') and self.context.subsets:
                    for subset_name, components in self.context.subsets.items():
                        for comp in components:
                            if comp in self.context.variables:
                                for idx in self.context.variables[comp]:
                                    if idx not in self._row_var_index:
                                        self._row_var_index[idx] = set()
                                    self._row_var_index[idx].add(subset_name)
        except Exception as e:
            logger.warning(f"Error building evaluation indices: {e}")
            self._row_var_index = {}

    def _safe_compare(self, left: Any, right: Any, op: Union[Callable, ast.operator]) -> Any:
        """Perform SQL-style comparison with NULL handling."""
        self.stats["evaluations"] += 1
        return safe_compare(left, right, op)

    def visit_Compare(self, node: ast.Compare):
        """Handle comparison operations with SQL semantics."""
        # Handle chained comparisons like (20 <= value <= 30) for BETWEEN
        if len(node.ops) > 1:
            # Handle chained comparisons by evaluating them step by step
            left = self.visit(node.left)
            
            for i, (op, comparator) in enumerate(zip(node.ops, node.comparators)):
                right = self.visit(comparator)
                
                # Evaluate the current comparison
                result = self._safe_compare(left, right, op)
                
                # If any comparison in the chain is False, return False
                if not result:
                    return False
                
                # For the next iteration, the right becomes the new left
                left = right
            
            # If all comparisons passed, return True
            return True
            
        left = self.visit(node.left)
        op = node.ops[0]
        
        # Debug logging for DEFINE mode comparisons
        if self.evaluation_mode == 'DEFINE':
            logger.debug(f"[DEBUG] COMPARE: left={left} ({type(left)}), op={op.__class__.__name__}")
        
        # Handle IN operator specially
        if isinstance(op, ast.In):
            # For IN operator, we need to check if left is in any of the comparators
            if len(node.comparators) != 1:
                raise ValueError("IN operator requires exactly one comparator (list/tuple)")
            
            right = self.visit(node.comparators[0])
            
            # Handle different types of right-hand side for IN
            if isinstance(right, (list, tuple)):
                # Handle special empty IN placeholders
                if len(right) == 1:
                    if right[0] == '__EMPTY_IN_FALSE__':
                        result = False  # Empty IN should always be false
                    elif right[0] == '__EMPTY_IN_TRUE__':
                        result = True   # Used for NOT IN () preprocessing
                    else:
                        result = left in right
                else:
                    # Direct list/tuple comparison
                    result = left in right
            elif hasattr(right, '__iter__') and not isinstance(right, str):
                # Iterable but not string
                try:
                    result = left in right
                except TypeError:
                    # If comparison fails, return False
                    result = False
            else:
                # Single value - handle special placeholders
                if right == '__EMPTY_IN_FALSE__':
                    result = False  # Empty IN should always be false
                elif right == '__EMPTY_IN_TRUE__':
                    result = True   # Used for NOT IN () preprocessing
                else:
                    # Single value - treat as membership test
                    result = left == right
                
            if self.evaluation_mode == 'DEFINE':
                logger.debug(f"[DEBUG] IN RESULT: {left} IN {right} = {result}")
            
            return result
            
        elif isinstance(op, ast.NotIn):
            # Handle NOT IN operator
            if len(node.comparators) != 1:
                raise ValueError("NOT IN operator requires exactly one comparator (list/tuple)")
            
            right = self.visit(node.comparators[0])
            
            # Handle different types of right-hand side for NOT IN
            if isinstance(right, (list, tuple)):
                # Handle special empty IN placeholders
                if len(right) == 1:
                    if right[0] == '__EMPTY_IN_FALSE__':
                        result = False  # NOT IN with empty false placeholder
                    elif right[0] == '__EMPTY_IN_TRUE__':
                        result = True   # NOT IN () should always be true
                    else:
                        result = left not in right
                else:
                    # Direct list/tuple comparison
                    result = left not in right
            elif hasattr(right, '__iter__') and not isinstance(right, str):
                # Iterable but not string
                try:
                    result = left not in right
                except TypeError:
                    # If comparison fails, return True (not in)
                    result = True
            else:
                # Single value - handle special placeholders
                if right == '__EMPTY_IN_FALSE__':
                    result = False  # NOT IN with empty false placeholder
                elif right == '__EMPTY_IN_TRUE__':
                    result = True   # NOT IN () should always be true
                else:
                    # Single value - treat as membership test
                    result = left != right
                
            if self.evaluation_mode == 'DEFINE':
                logger.debug(f"[DEBUG] NOT IN RESULT: {left} NOT IN {right} = {result}")
            
            return result
        
        # Handle standard comparison operators
        if len(node.comparators) != 1:
            raise ValueError("Standard comparison operators require exactly one comparator")
            
        right = self.visit(node.comparators[0])
        
        if self.evaluation_mode == 'DEFINE':
            logger.debug(f"[DEBUG] COMPARE: left={left} ({type(left)}), right={right} ({type(right)})")
        
        # Use the safer comparison method
        result = self._safe_compare(left, right, op)
        
        # Enhanced debug logging for result
        if self.evaluation_mode == 'DEFINE':
            current_var = getattr(self.context, 'current_var', None)
            logger.debug(f"[DEBUG] COMPARE RESULT: {left} {op.__class__.__name__} {right} = {result} (evaluating for var={current_var})")
        
        return result

    def visit_Name(self, node: ast.Name):
        # Check for special functions
        if node.id.upper() == "PREV":
            return lambda col, steps=1: self.evaluate_navigation_function('PREV', col, steps)
        elif node.id.upper() == "NEXT":
            return lambda col, steps=1: self.evaluate_navigation_function('NEXT', col, steps)
        elif node.id.upper() == "FIRST":
            def first_lambda(var, col, occ=0):
                logger = get_logger(__name__)
                logger.debug(f"🔍 [FIRST_LAMBDA] Called with var={var}, col={col}, occ={occ}")
                return self._handle_first_last_navigation('FIRST', col, occ, var)
            return first_lambda
        elif node.id.upper() == "LAST":
            def last_lambda(var, col, occ=0):
                logger = get_logger(__name__)
                logger.debug(f"🔍 [LAST_LAMBDA] Called with var={var}, col={col}, occ={occ}")
                return self._handle_first_last_navigation('LAST', col, occ, var)
            return last_lambda
        elif node.id.upper() == "CLASSIFIER":
            return lambda var=None: self._get_classifier(var)
        elif node.id.upper() == "MATCH_NUMBER":
            return self.context.match_number
        elif node.id == "row":
            # Special handling for 'row' references in keyword substitution
            return {}  # Return an empty dict that will be used in visit_Subscript
        elif node.id == "get_var_value":
            # Special function for pattern variable access
            return self._get_variable_column_value
                
        # Regular variable - handle as universal pattern variable
        # First check if this might be a universal pattern variable (non-prefixed column)
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', node.id):
            # Check if this conflicts with defined pattern variables
            if hasattr(self.context, 'pattern_variables') and node.id in self.context.pattern_variables:
                logger.warning(f"Column name '{node.id}' conflicts with pattern variable name")
                return None
            
            # Universal pattern variable: get from current row
            value = None
            if self.current_row is not None:
                value = self.current_row.get(node.id)
            elif self.context.current_idx >= 0 and self.context.current_idx < len(self.context.rows):
                value = self.context.rows[self.context.current_idx].get(node.id)
            
            if value is not None:
                logger.debug(f"Universal pattern variable '{node.id}' resolved to: {value}")
            
            return value
        
        # Fallback for non-standard identifiers
        value = None
        if self.current_row is not None:
            value = self.current_row.get(node.id)
        elif self.context.current_idx >= 0 and self.context.current_idx < len(self.context.rows):
            value = self.context.rows[self.context.current_idx].get(node.id)
        
        return value

    def _extract_navigation_args(self, node: ast.Call):
        """Extract arguments from a navigation function call with support for nesting."""
        args = []
        
        for arg in node.args:
            if isinstance(arg, ast.Name):
                # For navigation functions, Name nodes should be treated as column names
                args.append(arg.id)
            elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                # Handle pattern variable references like A.value -> split to var and column
                var_name = arg.value.id
                col_name = arg.attr
                # For navigation functions like FIRST(A.value), we need both parts
                args.extend([var_name, col_name])
            elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Constant):
                # Handle quoted variable references like "b".value -> split to var and column
                var_name = f'"{arg.value.value}"'  # Preserve quotes for consistency
                col_name = arg.attr
                # For navigation functions like FIRST("b".value), we need both parts
                args.extend([var_name, col_name])
            elif isinstance(arg, ast.Constant):
                # Constant values (numbers, strings)
                args.append(arg.value)
            else:
                # For complex expressions, evaluate them
                value = self.visit(arg)
                # Handle nested navigation functions
                if callable(value):
                    value = value()
                args.append(value)
            
        return args

    def visit_Call(self, node: ast.Call):
        """Handle function calls (navigation functions, mathematical functions, etc.)"""
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.upper()
            
            # Handle null checking helper function
            if func_name == "_IS_NULL":
                args = [self.visit(arg) for arg in node.args]
                if len(args) == 1:
                    return is_null(args[0])
                else:
                    raise ValueError("_is_null function requires exactly one argument")
            
            # Handle LAG and LEAD window functions
            if func_name in ("LAG", "LEAD"):
                return self._handle_window_function(node, func_name)
            
            # Handle mathematical and utility functions using shared utilities
            if func_name in MATH_FUNCTIONS:
                args = [self.visit(arg) for arg in node.args]
                self.stats["math_function_calls"] += 1
                try:
                    return evaluate_math_function(func_name, *args)
                except Exception as e:
                    raise ValueError(f"Error in {func_name} function: {e}")
            
            # Special handling for pattern variable access
            if func_name == "GET_VAR_VALUE":
                args = [self.visit(arg) for arg in node.args]
                if len(args) == 3:
                    var_name, col_name, ctx = args
                    return self._get_variable_column_value(var_name, col_name, ctx)
            
            # Special handling for CLASSIFIER function
            if func_name == "CLASSIFIER":
                # For CLASSIFIER, we need the literal variable name, not its evaluated value
                if len(node.args) == 0:
                    return self._get_classifier(None)
                elif len(node.args) == 1:
                    arg = node.args[0]
                    if isinstance(arg, ast.Name):
                        # Pass the literal variable name
                        return self._get_classifier(arg.id)
                    else:
                        raise ValueError("CLASSIFIER function requires a variable name argument")
                else:
                    raise ValueError("CLASSIFIER function takes at most one argument")
            
            # Enhanced navigation function handling
            if func_name in ("PREV", "NEXT", "FIRST", "LAST"):
                return self._handle_navigation_function(node, func_name)

        func = self.visit(node.func)
        if callable(func):
            args = [self.visit(arg) for arg in node.args]
            try:
                return func(*args)
            except Exception as e:
                # More descriptive error
                raise ValueError(f"Error calling {func_name or 'function'}: {e}")
        raise ValueError(f"Function {func_name or func} not callable")
    
    def _handle_navigation_function(self, node: ast.Call, func_name: str) -> Any:
        """Handle navigation function calls with comprehensive support."""
        self.stats["navigation_calls"] += 1
        
        # Check if this might be a nested navigation call
        is_nested = False
        if len(node.args) > 0:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Call) and hasattr(first_arg, 'func') and isinstance(first_arg.func, ast.Name):
                inner_func_name = first_arg.func.id.upper()
                if inner_func_name in ("PREV", "NEXT", "FIRST", "LAST"):
                    is_nested = True
        
        if is_nested:
            # For nested navigation, convert to string representation and use evaluate_nested_navigation
            navigation_expr = self._build_navigation_expr(node)
            # Store current evaluator in context for nested navigation
            original_active_evaluator = getattr(self.context, '_active_evaluator', None)
            self.context._active_evaluator = self
            # Also store as backup for mode reference
            self.context._active_evaluator_backup = self
            try:
                result = evaluate_nested_navigation(
                    navigation_expr, 
                    self.context, 
                    self.context.current_idx, 
                    getattr(self.context, 'current_var', None),
                    self.recursion_depth + 1
                )
                return result
            finally:
                # Restore original active evaluator
                if original_active_evaluator is not None:
                    self.context._active_evaluator = original_active_evaluator
                else:
                    if hasattr(self.context, '_active_evaluator'):
                        delattr(self.context, '_active_evaluator')
                # Clean up backup
                if hasattr(self.context, '_active_evaluator_backup'):
                    delattr(self.context, '_active_evaluator_backup')
        else:
            # Handle standard navigation function calls
            if len(node.args) == 0:
                raise ValueError(f"{func_name} function requires at least one argument")
            
            # Get the first argument which should be either ast.Name or ast.Attribute
            first_arg = node.args[0]
            
            # Get optional steps argument
            steps = 1
            if len(node.args) > 1:
                steps_arg = node.args[1]
                if isinstance(steps_arg, ast.Constant):
                    steps = steps_arg.value
            
            if isinstance(first_arg, ast.Attribute) and isinstance(first_arg.value, ast.Name):
                # Pattern: NEXT(A.value) - variable.column format
                var_name = first_arg.value.id
                column = first_arg.attr
                
                # Table prefix validation
                if self._is_table_prefix_in_context(var_name):
                    raise ValueError(f"Forbidden table prefix reference: '{var_name}.{column}'. "
                                   f"In MATCH_RECOGNIZE, use pattern variable references instead of table references")
                
                if func_name in ("PREV", "NEXT"):
                    # Context-aware navigation: physical for DEFINE, logical for MEASURES
                    if self.evaluation_mode == 'DEFINE':
                        # Physical navigation: use direct row indexing
                        return self.evaluate_physical_navigation(func_name, column, steps)
                    else:
                        # Logical navigation: use pattern match timeline
                        return self.evaluate_navigation_function(func_name, column, steps)
                else:
                    # Use new navigation handler for FIRST/LAST
                    return self._handle_first_last_navigation(func_name, column, steps, var_name)
                    
            elif isinstance(first_arg, ast.Attribute) and isinstance(first_arg.value, ast.Constant):
                # Pattern: NEXT("b".value) - quoted variable.column format
                var_name = f'"{first_arg.value.value}"'  # Preserve quotes for consistency
                column = first_arg.attr
                
                if func_name in ("PREV", "NEXT"):
                    # Context-aware navigation: physical for DEFINE, logical for MEASURES
                    if self.evaluation_mode == 'DEFINE':
                        return self.evaluate_physical_navigation(func_name, column, steps)
                    else:
                        return self.evaluate_navigation_function(func_name, column, steps)
                else:
                    # Use new navigation handler for FIRST/LAST
                    return self._handle_first_last_navigation(func_name, column, steps, var_name)
                    
            elif isinstance(first_arg, ast.Name):
                # Pattern: NEXT(column) - simple column format
                column = first_arg.id
                
                if func_name in ("PREV", "NEXT"):
                    # Context-aware navigation: physical for DEFINE, logical for MEASURES
                    if self.evaluation_mode == 'DEFINE':
                        return self.evaluate_physical_navigation(func_name, column, steps)
                    else:
                        return self.evaluate_navigation_function(func_name, column, steps)
                else:
                    # Use new navigation handler for FIRST/LAST with simple column format
                    return self._handle_first_last_navigation(func_name, column, steps, None)
                    
            elif isinstance(first_arg, ast.Call):
                # Handle nested function calls like NEXT(CLASSIFIER()) and PREV(CLASSIFIER(U))
                if isinstance(first_arg.func, ast.Name) and first_arg.func.id.upper() == "CLASSIFIER":
                    # Extract subset variable if present
                    subset_var = None
                    if len(first_arg.args) > 0 and isinstance(first_arg.args[0], ast.Name):
                        subset_var = first_arg.args[0].id
                    
                    # Special case: Navigation with CLASSIFIER
                    return self._handle_classifier_navigation(func_name, subset_var, steps)
                else:
                    # For other nested calls, evaluate the argument first
                    evaluated_arg = self.visit(first_arg)
                    if evaluated_arg is not None:
                        # Use the evaluated result as a column name
                        column = str(evaluated_arg)
                        if func_name in ("PREV", "NEXT"):
                            if self.evaluation_mode == 'DEFINE':
                                return self.evaluate_physical_navigation(func_name, column, steps)
                            else:
                                return self.evaluate_navigation_function(func_name, column, steps)
                        else:
                            # Use new navigation handler for FIRST/LAST with nested calls
                            return self._handle_first_last_navigation(func_name, column, steps, None)
                    else:
                        return None
            else:
                raise ValueError(f"Unsupported argument type for {func_name}: {type(first_arg)}")
    
    def _handle_classifier_navigation(self, func_name: str, subset_var: Optional[str], steps: int) -> Any:
        """Handle navigation functions with CLASSIFIER arguments."""
        if func_name in ("PREV", "NEXT"):
            # For PREV/NEXT with CLASSIFIER, navigate through classifier values
            if subset_var and subset_var in self.context.subsets:
                # Direct subset navigation without recursion
                subset_components = self.context.subsets[subset_var]
                all_subset_indices = []
                for comp_var in subset_components:
                    if comp_var in self.context.variables:
                        all_subset_indices.extend(self.context.variables[comp_var])
                
                if all_subset_indices:
                    all_subset_indices = sorted(set(all_subset_indices))
                    current_idx = self.context.current_idx
                    
                    # Enhanced logic: navigate from current position even if not in subset
                    if func_name == "PREV":
                        # Find the most recent subset position before current_idx
                        target_indices = [idx for idx in all_subset_indices if idx < current_idx]
                        if target_indices and steps <= len(target_indices):
                            target_idx = target_indices[-steps]  # steps positions back
                            return self._get_direct_classifier_at_index(target_idx, subset_var)
                        else:
                            return None
                    else:  # NEXT
                        # Find the next subset position after current_idx
                        target_indices = [idx for idx in all_subset_indices if idx > current_idx]
                        if target_indices and steps <= len(target_indices):
                            target_idx = target_indices[steps - 1]  # steps positions forward
                            return self._get_direct_classifier_at_index(target_idx, subset_var)
                        else:
                            return None
                else:
                    return None
            else:
                # Regular CLASSIFIER() without subset - use timeline navigation
                current_idx = self.context.current_idx
                target_idx = current_idx + steps if func_name == "NEXT" else current_idx - steps
                
                # Check bounds
                if target_idx < 0 or target_idx >= len(self.context.rows):
                    return None
                
                return self._get_direct_classifier_at_index(target_idx, None)
                
        elif func_name in ("FIRST", "LAST"):
            # Handle FIRST/LAST with CLASSIFIER
            return self._handle_first_last_classifier(func_name, subset_var, steps)
        else:
            logger.error(f"{func_name}(CLASSIFIER()) not yet supported")
            return None
    
    def _handle_first_last_classifier(self, func_name: str, subset_var: Optional[str], steps: int) -> Any:
        """Handle FIRST/LAST with CLASSIFIER arguments."""
        if func_name.upper() == 'LAST':
            if subset_var and subset_var in self.context.subsets:
                # Get the last classifier in the subset
                subset_components = self.context.subsets[subset_var]
                all_subset_indices = []
                for comp_var in subset_components:
                    if comp_var in self.context.variables:
                        all_subset_indices.extend(self.context.variables[comp_var])
                
                if all_subset_indices:
                    all_subset_indices = sorted(set(all_subset_indices))
                    
                    # Handle steps parameter for LAST function - relative to current position
                    if steps > 0:
                        # LAST(CLASSIFIER(subset), N) means N positions back from current
                        current_idx = self.context.current_idx
                        target_idx = current_idx - steps
                        if target_idx < 0 or target_idx not in all_subset_indices:
                            return None
                        return self._get_direct_classifier_at_index(target_idx, subset_var)
                    else:
                        # LAST(CLASSIFIER(subset)) means the most recent position in subset
                        target_idx = all_subset_indices[-1]
                        return self._get_direct_classifier_at_index(target_idx, subset_var)
            else:
                # Get the last classifier in the overall match
                if hasattr(self.context, 'variables') and self.context.variables:
                    # Handle steps parameter for LAST function - relative to current position
                    if steps > 0:
                        # LAST(CLASSIFIER(), N) means N positions back from current
                        current_idx = self.context.current_idx
                        target_idx = current_idx - steps
                        logger.debug(f"[LAST_DEBUG] LAST(CLASSIFIER(), {steps}): current_idx={current_idx}, target_idx={target_idx}")
                        if target_idx < 0:
                            logger.debug(f"[LAST_DEBUG] target_idx={target_idx} < 0, returning None")
                            return None
                        result = self._get_direct_classifier_at_index(target_idx, None)
                        logger.debug(f"[LAST_DEBUG] _get_direct_classifier_at_index({target_idx}) returned: {result}")
                        return result
                    else:
                        # LAST(CLASSIFIER()) means the most recent position in match
                        # Find all row indices across all variables in current match
                        all_indices = []
                        for var, indices in self.context.variables.items():
                            all_indices.extend(indices)
                        
                        if all_indices:
                            all_indices = sorted(set(all_indices))
                            target_idx = all_indices[-1]
                            return self._get_direct_classifier_at_index(target_idx, None)
                        else:
                            return None
                else:
                    return None
        
        elif func_name.upper() == 'FIRST':
            if subset_var and subset_var in self.context.subsets:
                # Get the first classifier in the subset
                subset_components = self.context.subsets[subset_var]
                all_subset_indices = []
                for comp_var in subset_components:
                    if comp_var in self.context.variables:
                        all_subset_indices.extend(self.context.variables[comp_var])
                
                if all_subset_indices:
                    all_subset_indices = sorted(set(all_subset_indices))
                    
                    # Handle steps parameter for FIRST function  
                    if steps > len(all_subset_indices):
                        return None
                    target_idx = all_subset_indices[steps - 1] if steps > 0 else all_subset_indices[0]
                    
                    return self._get_direct_classifier_at_index(target_idx, subset_var)
            else:
                # Get the first classifier in the overall match
                if hasattr(self.context, 'variables') and self.context.variables:
                    # Find all row indices across all variables in current match
                    all_indices = []
                    for var, indices in self.context.variables.items():
                        all_indices.extend(indices)
                    
                    if all_indices:
                        all_indices = sorted(set(all_indices))
                        # Handle steps parameter for FIRST function
                        if steps > len(all_indices):
                            return None
                        target_idx = all_indices[steps - 1] if steps > 0 else all_indices[0]
                        
                        return self._get_direct_classifier_at_index(target_idx, None)
                    else:
                        return None
                else:
                    return None
        
        return None

    def visit_Attribute(self, node: ast.Attribute):
        """Handle pattern variable references (A.price or "b".price) with table prefix validation"""
        if isinstance(node.value, ast.Name):
            var = node.value.id
            col = node.attr
            
            # Table prefix validation: prevent forbidden table.column references
            if self._is_table_prefix_in_context(var):
                raise ValueError(f"Forbidden table prefix reference: '{var}.{col}'. "
                               f"In MATCH_RECOGNIZE, use pattern variable references instead of table references")
            
            # Handle pattern variable references
            result = self._get_variable_column_value(var, col, self.context)
            
            return result
        elif isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            # Handle quoted identifiers like "b".value
            var = f'"{node.value.value}"'  # Preserve quotes for consistency with context storage
            col = node.attr
            
            # Handle pattern variable references for quoted identifiers
            result = self._get_variable_column_value(var, col, self.context)
            
            return result
        
        # If we can't extract a pattern var reference, try regular attribute access
        obj = self.visit(node.value)
        if obj is not None:
            return getattr(obj, node.attr, None)
        
        return None

    def visit_BinOp(self, node: ast.BinOp):
        """Handle binary operations (addition, subtraction, multiplication, etc.)"""
        import operator
        
        # Map AST operators to Python operators
        op_map = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.LShift: operator.lshift,
            ast.RShift: operator.rshift,
            ast.BitOr: operator.or_,
            ast.BitXor: operator.xor,
            ast.BitAnd: operator.and_,
        }
        
        try:
            left = self.visit(node.left)
            right = self.visit(node.right)
            op = op_map.get(type(node.op))
            
            if op is None:
                raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
            
            # Handle None values - if either operand is None, result is None (SQL semantics)
            if left is None or right is None:
                return None
                
            result = op(left, right)
                
            logger.debug(f"[DEBUG] BinOp: {left} {type(node.op).__name__} {right} = {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in binary operation: {e}")
            return None

    def visit_UnaryOp(self, node: ast.UnaryOp):
        """Handle unary operations (not, -, +, ~)"""
        import operator
        
        # Map AST unary operators to Python operators
        op_map = {
            ast.Not: operator.not_,
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
            ast.Invert: operator.invert,
        }
        
        try:
            operand = self.visit(node.operand)
            op = op_map.get(type(node.op))
            
            if op is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
            
            # Handle None values - SQL semantics
            if operand is None:
                return None
                
            result = op(operand)
            logger.debug(f"[DEBUG] UnaryOp: {type(node.op).__name__} {operand} = {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in unary operation: {e}")
            return None

    def _is_table_prefix_in_context(self, var_name: str) -> bool:
        """
        Check if a variable name looks like a table prefix in the current context.
        
        Args:
            var_name: The variable name to check
            
        Returns:
            True if this looks like a forbidden table prefix, False otherwise
        """
        # If it's a defined pattern variable, it's not a table prefix
        if hasattr(self.context, 'variables') and var_name in self.context.variables:
            return False
        if hasattr(self.context, 'subsets') and self.context.subsets and var_name in self.context.subsets:
            return False
        
        # Use the shared utility function
        return is_table_prefix(var_name, 
                              getattr(self.context, 'variables', {}),
                              getattr(self.context, 'subsets', {}))

    def _handle_window_function(self, node: ast.Call, func_name: str):
        """Handle LAG and LEAD window functions"""
        if not hasattr(self.context, 'rows') or not self.context.rows or not self.current_row:
            return None
            
        args = [self.visit(arg) for arg in node.args]
        
        if len(args) == 0:
            # No arguments - not valid for LAG/LEAD
            raise ValueError(f"{func_name} function requires at least one argument (column name)")
        
        # First argument should be the column name/expression
        column_expr = args[0]
        
        # Second argument is offset (default 1)
        offset = args[1] if len(args) > 1 else 1
        
        # Third argument is default value (default None)
        default = args[2] if len(args) > 2 else None
        
        # Get current row index using context
        current_idx = self.context.current_idx
        if current_idx < 0 or current_idx >= len(self.context.rows):
            return default
            
        # Calculate target index
        if func_name == "LAG":
            target_idx = current_idx - offset
        else:  # LEAD
            target_idx = current_idx + offset
            
        # Check bounds
        if target_idx < 0 or target_idx >= len(self.context.rows):
            return default
            
        # Get value from target row
        target_row = self.context.rows[target_idx]
        
        # If column_expr is a string, treat it as column name
        if isinstance(column_expr, str):
            return target_row.get(column_expr, default)
        else:
            # For more complex expressions, we'd need to evaluate them in the context of target_row
            # For now, return the expression value as-is
            return column_expr

        # Updates for src/matcher/condition_evaluator.py
    def _get_variable_column_value(self, var_name: str, col_name: str, ctx: RowContext) -> Any:
        """
        Get a column value from a pattern variable's matched rows with enhanced subset support.
        
        For self-referential conditions (e.g., B.price < A.price when evaluating for B),
        use the current row's value for the variable being evaluated.
        
        Args:
            var_name: Pattern variable name
            col_name: Column name
            ctx: Row context
            
        Returns:
            Column value from the matched row or current row
        """
        # Check if we're in DEFINE evaluation mode
        is_define_mode = self.evaluation_mode == 'DEFINE'
        
        # DEBUG: Enhanced logging to trace exact values
        current_var = getattr(ctx, 'current_var', None)
        logger.debug(f"[DEBUG] _get_variable_column_value: var_name={var_name}, col_name={col_name}, is_define_mode={is_define_mode}, current_var={current_var}")
        logger.debug(f"[DEBUG] ctx.current_idx={ctx.current_idx}, ctx.variables={ctx.variables}")
        
        # CRITICAL FIX: In DEFINE mode, we need special handling for pattern variable references
        if is_define_mode:
            # CRITICAL FIX: When evaluating B's condition, B.price should use the current row
            # but A.price should use A's previously matched row
            if var_name == current_var or (current_var is None and var_name in self.visit_stack):
                # Self-reference: use current row being tested
                logger.debug(f"[DEBUG] DEFINE mode - self-reference for {var_name}.{col_name}")
                if ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                    value = ctx.rows[ctx.current_idx].get(col_name)
                    logger.debug(f"[DEBUG] Self-reference value: {var_name}.{col_name} = {value} (from row {ctx.current_idx})")
                    return value
                else:
                    logger.debug(f"[DEBUG] Self-reference: invalid current_idx {ctx.current_idx}")
                    return None
            else:
                # Cross-reference: use previously matched row for this variable
                logger.debug(f"[DEBUG] DEFINE mode - cross-reference for {var_name}.{col_name}")
                
                # Check if this is a subset variable
                if hasattr(ctx, 'subsets') and var_name in ctx.subsets:
                    # For subset variables, find the last row matched to any component variable
                    component_vars = ctx.subsets[var_name]
                    last_idx = -1
                    
                    for comp_var in component_vars:
                        if comp_var in ctx.variables:
                            var_indices = ctx.variables[comp_var]
                            if var_indices:
                                last_var_idx = max(var_indices)
                                if last_var_idx > last_idx:
                                    last_idx = last_var_idx
                    
                    if last_idx >= 0 and last_idx < len(ctx.rows):
                        value = ctx.rows[last_idx].get(col_name)
                        logger.debug(f"[DEBUG] Subset cross-reference value: {var_name}.{col_name} = {value} (from row {last_idx})")
                        return value
                
                # Get the value from the last row matched to this variable
                var_indices = ctx.variables.get(var_name, [])
                logger.debug(f"[DEBUG] Looking for {var_name} in ctx.variables: {var_indices}")
                if var_indices:
                    last_idx = max(var_indices)
                    if last_idx < len(ctx.rows):
                        value = ctx.rows[last_idx].get(col_name)
                        logger.debug(f"[DEBUG] Cross-reference value: {var_name}.{col_name} = {value} (from row {last_idx})")
                        return value
                    else:
                        logger.debug(f"[DEBUG] Cross-reference: invalid last_idx {last_idx}")
                        return None
                
                # If no rows matched yet, this variable hasn't been matched
                logger.debug(f"[DEBUG] Cross-reference: no rows matched for {var_name} yet")
                return None
        
        # For non-DEFINE modes (MEASURES mode), use standard logic
        
        # Track if we're evaluating a condition for the same variable (self-reference)
        is_self_reference = False
        
        # If we have current_var set, this is a direct check for self-reference
        if hasattr(ctx, 'current_var') and ctx.current_var == var_name:
            is_self_reference = True
        
        # Otherwise check if current row is already assigned to this variable
        if not is_self_reference and hasattr(ctx, 'current_var_assignments'):
            if var_name in ctx.current_var_assignments and ctx.current_idx in ctx.current_var_assignments[var_name]:
                is_self_reference = True
        
        # For self-references in other modes, use the current row's value
        if is_self_reference:
            if self.current_row is not None:
                return self.current_row.get(col_name)
            elif ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                return ctx.rows[ctx.current_idx].get(col_name)
        
        # Check if this is a subset variable
        if hasattr(ctx, 'subsets') and var_name in ctx.subsets:
            # For subset variables in MEASURES mode, return the value from the current row
            # if the current row matches any component of the subset
            component_vars = ctx.subsets[var_name]
            current_idx = ctx.current_idx
            
            # Check if current row matches any component of this subset
            for comp_var in component_vars:
                if comp_var in ctx.variables and current_idx in ctx.variables[comp_var]:
                    # Current row matches this component, return its value
                    if current_idx >= 0 and current_idx < len(ctx.rows):
                        return ctx.rows[current_idx].get(col_name)
            
            # If current row doesn't match any component, fall back to original logic
            # (find the last row matched to any component variable)
            last_idx = -1
            for comp_var in component_vars:
                if comp_var in ctx.variables:
                    var_indices = ctx.variables[comp_var]
                    if var_indices:
                        last_var_idx = max(var_indices)
                        if last_var_idx > last_idx:
                            last_idx = last_var_idx
            
            if last_idx >= 0 and last_idx < len(ctx.rows):
                return ctx.rows[last_idx].get(col_name)
        
        # CRITICAL FIX: For RUNNING aggregates in MEASURES mode, use current row instead of last matched row
        # This is essential for conditional aggregates like COUNT_IF, SUM_IF, AVG_IF
        if (self.evaluation_mode == 'MEASURES' and 
            hasattr(ctx, 'current_idx') and 
            ctx.current_idx >= 0 and 
            ctx.current_idx < len(ctx.rows)):
            
            # Check if the current row is within the variable's matched indices
            var_indices = ctx.variables.get(var_name, [])
            if var_indices and ctx.current_idx in var_indices:
                logger.debug(f"[DEBUG] RUNNING aggregate: using current row {ctx.current_idx} for {var_name}.{col_name}")
                value = ctx.rows[ctx.current_idx].get(col_name)
                logger.debug(f"[DEBUG] RUNNING aggregate value: {var_name}.{col_name} = {value} (from current row {ctx.current_idx})")
                return value
        
        # Otherwise, get the value from the last row matched to this variable (traditional behavior)
        var_indices = ctx.variables.get(var_name, [])
        if var_indices:
            last_idx = max(var_indices)
            if last_idx < len(ctx.rows):
                logger.debug(f"[DEBUG] Using traditional last row logic: {var_name}.{col_name} from row {last_idx}")
                return ctx.rows[last_idx].get(col_name)
        
        # If no rows matched yet, use the current row's value
        # This is important for the first evaluation of a pattern variable
        if self.current_row is not None:
            return self.current_row.get(col_name)
        elif ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
            return ctx.rows[ctx.current_idx].get(col_name)
        
        return None

    def _handle_subset_navigation(self, var_name, column, nav_type, steps, cache_key):
        """Handle navigation for subset variables with enhanced logic."""
        logger.debug(f"[NAV_ENHANCED] Processing subset variable: {var_name}")
        
        component_vars = self.context.subsets[var_name]
        all_indices = []
        
        # Collect indices from all component variables
        for comp_var in component_vars:
            if comp_var in self.context.variables:
                all_indices.extend(self.context.variables[comp_var])
        
        if not all_indices:
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Sort and deduplicate indices
        all_indices = sorted(set(all_indices))
        
        # Apply steps parameter for subset navigation
        if nav_type == 'FIRST':
            if steps > len(all_indices):
                idx = None
            else:
                idx = all_indices[steps - 1] if steps > 0 else all_indices[0]
        else:  # LAST
            if steps > len(all_indices):
                idx = None
            else:
                idx = all_indices[-steps] if steps > 0 else all_indices[-1]
        
        if idx is None or not (0 <= idx < len(self.context.rows)):
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Check partition boundaries
        if self._check_partition_boundary(self.context.current_idx, idx):
            result = self.context.rows[idx].get(column)
            self.context.navigation_cache[cache_key] = result
            return result
        
        self.context.navigation_cache[cache_key] = None
        return None

    def _build_optimized_timeline(self):
        """Build an optimized timeline of variable assignments."""
        # Use cached timeline if available and valid
        if (hasattr(self.context, '_timeline') and 
            hasattr(self.context, '_timeline_version') and
            self.context._timeline_version == id(self.context.variables)):
            return self.context._timeline
        
        logger.debug(f"[NAV_ENHANCED] Building optimized timeline from variables: {self.context.variables}")
        
        # Build timeline with improved algorithm
        timeline = []
        for var, indices in self.context.variables.items():
            for idx in indices:
                timeline.append((idx, var))
        
        # Sort by row index for consistent ordering
        timeline.sort()
        
        # Cache with version tracking
        self.context._timeline = timeline
        self.context._timeline_version = id(self.context.variables)
        
        logger.debug(f"[NAV_ENHANCED] Built timeline with {len(timeline)} entries")
        return timeline

    def _handle_logical_navigation(self, var_name, column, nav_type, steps, timeline, cache_key):
        """Handle FIRST/LAST navigation with enhanced logic."""
        logger.debug(f"[NAV_ENHANCED] Logical navigation: {nav_type}({var_name}.{column})")
        
        if var_name is None:
            # Navigate across all variables in the match
            all_indices = []
            for var, indices in self.context.variables.items():
                all_indices.extend(indices)
            
            if not all_indices:
                self.context.navigation_cache[cache_key] = None
                return None
            
            all_indices = sorted(set(all_indices))
            idx = all_indices[0] if nav_type == 'FIRST' else all_indices[-1]
            
        elif var_name not in self.context.variables or not self.context.variables[var_name]:
            logger.debug(f"[NAV_ENHANCED] Variable {var_name} not found or empty")
            self.context.navigation_cache[cache_key] = None
            return None
        else:
            # Navigate within specific variable
            var_indices = sorted(set(self.context.variables[var_name]))
            
            if not var_indices:
                self.context.navigation_cache[cache_key] = None
                return None
            
            # Apply steps parameter for logical navigation
            if nav_type == 'FIRST':
                if steps > len(var_indices):
                    idx = None
                else:
                    idx = var_indices[steps - 1] if steps > 0 else var_indices[0]
            else:  # LAST
                if steps > len(var_indices):
                    idx = None
                else:
                    idx = var_indices[-steps] if steps > 0 else var_indices[-1]
        
        if idx is None or not (0 <= idx < len(self.context.rows)):
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Enhanced boundary checking
        if self._check_partition_boundary(self.context.current_idx, idx):
            result = self.context.rows[idx].get(column)
            self.context.navigation_cache[cache_key] = result
            return result
        
        self.context.navigation_cache[cache_key] = None
        return None

    def _handle_physical_navigation_define(self, column, nav_type, steps, cache_key):
        """Handle PREV/NEXT navigation in DEFINE mode (physical navigation)."""
        logger.debug(f"[NAV_ENHANCED] Physical navigation in DEFINE mode: {nav_type}({column}, {steps})")
        
        # For DEFINE mode, navigate through physical input sequence
        curr_idx = self.context.current_idx
        
        if nav_type == 'PREV':
            target_idx = curr_idx - steps
        else:  # NEXT
            target_idx = curr_idx + steps
        
        # Enhanced bounds checking
        if target_idx < 0 or target_idx >= len(self.context.rows):
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Check partition boundaries for physical navigation
        if self._check_partition_boundary(curr_idx, target_idx):
            result = self.context.rows[target_idx].get(column)
            self.context.navigation_cache[cache_key] = result
            return result
        
        self.context.navigation_cache[cache_key] = None
        return None

    def _handle_logical_timeline_navigation(self, var_name, column, nav_type, steps, timeline, cache_key, current_var):
        """Handle PREV/NEXT navigation through pattern timeline."""
        logger.debug(f"[NAV_ENHANCED] Timeline navigation: {nav_type}({column}, {steps}) for var={var_name}")
        
        if not timeline:
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Find current position in timeline
        curr_idx = self.context.current_idx
        curr_pos = -1
        
        # Enhanced position finding with variable context
        for i, (idx, var) in enumerate(timeline):
            if idx == curr_idx and (current_var is None or var == current_var or var_name is None):
                curr_pos = i
                break
        
        if curr_pos < 0:
            # Try alternative matching strategies
            for i, (idx, var) in enumerate(timeline):
                if idx == curr_idx:
                    curr_pos = i
                    break
        
        if curr_pos < 0:
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Calculate target position
        if nav_type == 'PREV':
            target_pos = curr_pos - steps
        else:  # NEXT
            target_pos = curr_pos + steps
        
        # Bounds checking for timeline
        if target_pos < 0 or target_pos >= len(timeline):
            self.context.navigation_cache[cache_key] = None
            return None
        
        target_idx, _ = timeline[target_pos]
        
        # Enhanced boundary checking
        if self._check_partition_boundary(curr_idx, target_idx):
            if 0 <= target_idx < len(self.context.rows):
                result = self.context.rows[target_idx].get(column)
                self.context.navigation_cache[cache_key] = result
                return result
        
        self.context.navigation_cache[cache_key] = None
        return None

    def _check_partition_boundary(self, curr_idx, target_idx):
        """Enhanced partition boundary checking."""
        if not hasattr(self.context, 'partition_boundaries') or not self.context.partition_boundaries:
            return True  # No partition boundaries defined
        
        try:
            curr_partition = self.context.get_partition_for_row(curr_idx)
            target_partition = self.context.get_partition_for_row(target_idx)
            
            return (curr_partition is not None and 
                   target_partition is not None and 
                   curr_partition == target_partition)
        except Exception as e:
            logger.warning(f"Error checking partition boundary: {e}")
            return True  # Default to allowing navigation on error

    def _get_classifier(self, variable: Optional[str] = None) -> str:
        """Get the classifier (pattern variable name) for the current or specified position."""
        if variable is not None:
            # Check if this is a subset variable
            if hasattr(self.context, 'subsets') and variable in self.context.subsets:
                # For subset variables, return the component variable that matches the current row
                current_idx = self.context.current_idx
                for comp in self.context.subsets[variable]:
                    if comp in self.context.variables and current_idx in self.context.variables[comp]:
                        return comp
                return variable  # Fallback if no component matches
            else:
                # Return the specific variable name for non-subset variables
                return variable
        
        # Get the classifier for the current row
        current_idx = self.context.current_idx
        
        # Check which variable(s) this row belongs to
        if hasattr(self, '_row_var_index') and current_idx in self._row_var_index:
            variables = self._row_var_index[current_idx]
            if len(variables) == 1:
                return next(iter(variables))
            elif len(variables) > 1:
                # Multiple variables - return the first one alphabetically for consistency
                return min(variables)
        
        # Fallback to searching through all variables
        for var_name, indices in self.context.variables.items():
            if current_idx in indices:
                return var_name
        
        # If no variable found, return empty string
        return ""
    
    def _get_direct_classifier_at_index(self, row_idx: int, subset_var: Optional[str] = None) -> str:
        """
        Get the classifier value directly at a specific row index without recursion.
        
        Args:
            row_idx: The row index to get the classifier for
            subset_var: Optional subset variable name
            
        Returns:
            The classifier value at the specified index
        """
        logger.debug(f"[CLASSIFIER_DEBUG] _get_direct_classifier_at_index(row_idx={row_idx}, subset_var={subset_var})")
        
        if subset_var:
            # For subset variables, return the actual component variable name that matches
            if subset_var in self.context.subsets:
                component_vars = self.context.subsets[subset_var]
                for comp_var in component_vars:
                    if comp_var in self.context.variables and row_idx in self.context.variables[comp_var]:
                        logger.debug(f"[CLASSIFIER_DEBUG] Found subset component {comp_var} for row {row_idx}")
                        return comp_var  # Return the actual component variable, not the subset name
            logger.debug(f"[CLASSIFIER_DEBUG] No subset component found for row {row_idx}, returning empty string")
            return ""
        
        # Check which variable this row belongs to
        logger.debug(f"[CLASSIFIER_DEBUG] Context variables: {self.context.variables}")
        
        if hasattr(self, '_row_var_index') and row_idx in self._row_var_index:
            variables = self._row_var_index[row_idx]
            logger.debug(f"[CLASSIFIER_DEBUG] Found in _row_var_index: {variables}")
            if len(variables) == 1:
                result = next(iter(variables))
                logger.debug(f"[CLASSIFIER_DEBUG] Single variable: {result}")
                return result
            elif len(variables) > 1:
                # Multiple variables - return the first one alphabetically for consistency
                result = min(variables)
                logger.debug(f"[CLASSIFIER_DEBUG] Multiple variables, returning: {result}")
                return result
        
        # Fallback to searching through all variables
        for var_name, indices in self.context.variables.items():
            if row_idx in indices:
                logger.debug(f"[CLASSIFIER_DEBUG] Found row {row_idx} in variable {var_name}")
                return var_name
        
        logger.debug(f"[CLASSIFIER_DEBUG] No variable found for row {row_idx}, returning empty string")
        return ""

    def _build_navigation_expr(self, node):
        """
        Convert an AST navigation function call to a string representation.
        
        This handles both simple and nested navigation functions:
        - PREV(price)
        - FIRST(A.price)
        - PREV(FIRST(A.price))
        - PREV(FIRST(A.price), 2)
        
        Args:
            node: The AST Call node representing the navigation function
            
        Returns:
            String representation of the navigation expression
        """
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.upper()
        else:
            # Can't determine function name
            return ""
            
        # Build argument list
        args = []
        for arg in node.args:
            if isinstance(arg, ast.Name):
                # Simple identifier
                args.append(arg.id)
            elif isinstance(arg, ast.Constant):
                # Literal value
                args.append(str(arg.value))
            elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                # Pattern variable reference (A.price)
                args.append(f"{arg.value.id}.{arg.attr}")
            elif isinstance(arg, ast.Call):
                # Nested navigation function
                args.append(self._build_navigation_expr(arg))
            else:
                # Complex expression
                try:
                    if hasattr(ast, 'unparse'):
                        args.append(ast.unparse(arg).strip())
                    else:
                        # For Python versions < 3.9 that don't have ast.unparse
                        import astunparse
                        args.append(astunparse.unparse(arg).strip())
                except (ImportError, AttributeError):
                    # Fallback
                    args.append(str(arg))
                
        # Combine into navigation expression
        return f"{func_name}({', '.join(args)})"

    def evaluate_physical_navigation(self, nav_type, column, steps=1):
        """
        Physical navigation for DEFINE conditions.
        
        This method implements the correct SQL:2016 semantics for navigation functions
        in DEFINE conditions, where PREV/NEXT refer to the previous/next row in the
        input sequence (ordered by ORDER BY), not in the pattern match.
        
        Args:
            nav_type: Type of navigation ('PREV' or 'NEXT')
            column: Column name to retrieve
            steps: Number of steps to navigate (default: 1)
            
        Returns:
            The value at the navigated position or None if navigation is invalid
        """
        # Debug logging
        logger = get_logger(__name__)
        logger.debug(f"PHYSICAL_NAV: {nav_type}({column}, {steps}) at current_idx={self.context.current_idx}")
        
        # Input validation
        if steps < 0:
            raise ValueError(f"Navigation steps must be non-negative: {steps}")
            
        if nav_type not in ('PREV', 'NEXT'):
            raise ValueError(f"Invalid navigation type: {nav_type}")
        
        # Get current row index in the input sequence
        curr_idx = self.context.current_idx
        
        # Bounds check for current index
        if curr_idx < 0 or curr_idx >= len(self.context.rows):
            logger.debug(f"PHYSICAL_NAV: curr_idx {curr_idx} out of bounds [0, {len(self.context.rows)})")
            return None
            
        # Special case for steps=0 (return current row's value)
        if steps == 0:
            result = self.context.rows[curr_idx].get(column)
            logger.debug(f"PHYSICAL_NAV: steps=0, returning current row value: {result}")
            return result
            
        # Calculate target index based on navigation type
        if nav_type == 'PREV':
            target_idx = curr_idx - steps
        else:  # NEXT
            target_idx = curr_idx + steps
            
        logger.debug(f"PHYSICAL_NAV: target_idx={target_idx} (curr_idx={curr_idx}, nav={nav_type}, steps={steps})")
            
        # Check index bounds
        if target_idx < 0 or target_idx >= len(self.context.rows):
            logger.debug(f"PHYSICAL_NAV: target_idx {target_idx} out of bounds [0, {len(self.context.rows)})")
            return None
            
        # Check partition boundaries if defined
        # Physical navigation respects partition boundaries
        if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
            current_partition = self.context.get_partition_for_row(curr_idx)
            target_partition = self.context.get_partition_for_row(target_idx)
            
            if (current_partition is None or target_partition is None or
                current_partition != target_partition):
                logger.debug(f"PHYSICAL_NAV: partition boundary violation")
                return None
                
        # Get the value from the target row
        result = self.context.rows[target_idx].get(column)
        logger.debug(f"PHYSICAL_NAV: returning value from row {target_idx}: {result}")
        return result

    def evaluate_navigation_function(self, nav_type, column, steps=1, var_name=None):
        """
        Context-aware navigation function that uses different strategies based on evaluation mode.
        
        DEFINE Mode (Physical Navigation):
        - PREV/NEXT navigate through the input table rows in ORDER BY sequence
        - Used for condition evaluation: B.price < PREV(price)
        
        MEASURES Mode (Logical Navigation):
        - PREV/NEXT navigate through pattern match results
        - Used for value extraction: FIRST(A.order_date)
        
        Args:
            nav_type: Type of navigation ('PREV' or 'NEXT')
            column: Column name to retrieve
            steps: Number of steps to navigate (default: 1)
            var_name: Optional variable name for context
            
        Returns:
            The value at the navigated position or None if navigation is invalid
        """
        logger = get_logger(__name__)
        logger.debug(f"🔍 [NAV_MAIN] evaluate_navigation_function called: nav_type={nav_type}, column={column}, steps={steps}, var_name={var_name}")
        
        # Input validation
        if steps < 0:
            raise ValueError(f"Navigation steps must be non-negative: {steps}")
            
        if nav_type not in ('PREV', 'NEXT', 'FIRST', 'LAST'):
            raise ValueError(f"Invalid navigation type: {nav_type}")
        
        # Special case for steps=0 (return current row's value)
        if steps == 0:
            if 0 <= self.context.current_idx < len(self.context.rows):
                return self.context.rows[self.context.current_idx].get(column)
            return None

        # Handle FIRST and LAST functions
        if nav_type in ('FIRST', 'LAST'):
            logger.debug(f"🔍 [NAV_MAIN] Routing {nav_type} to _handle_first_last_navigation")
            return self._handle_first_last_navigation(nav_type, column, steps, var_name)
        
        # DEFINE Mode: Physical Navigation through input sequence (PREV/NEXT)
        if self.evaluation_mode == 'DEFINE':
            return self._physical_navigation(nav_type, column, steps)
        
        # MEASURES Mode: Logical Navigation through pattern matches (PREV/NEXT)
        else:
            return self._logical_navigation(nav_type, column, steps, var_name)
    
    def _physical_navigation(self, nav_type, column, steps):
        """
        Enhanced physical navigation for DEFINE conditions with production-ready optimizations.
        
        This implementation provides:
        - Direct integration with optimized context navigation methods
        - Consistent behavior across all pattern types
        - Advanced error handling and boundary validation
        - Performance optimization with early exits
        - Enhanced null handling for proper SQL semantics
        
        Args:
            nav_type: Navigation type ('PREV' or 'NEXT')
            column: Column name to retrieve
            steps: Number of steps to navigate
            
        Returns:
            The value at the navigated position or None if navigation is invalid
        """
        start_time = time.time()
        
        try:
            # Use advanced navigation methods from context
            if nav_type == 'PREV':
                row = self.context.prev(steps)
            else:  # NEXT
                row = self.context.next(steps)
                
            # Get column value with proper null handling
            result = None if row is None else row.get(column)
            
            # Track specific navigation type metrics
            if hasattr(self.context, 'stats'):
                metric_key = f"{nav_type.lower()}_navigation_calls"
                self.context.stats[metric_key] = self.context.stats.get(metric_key, 0) + 1
            
            return result
            
        except Exception as e:
            # Enhanced error handling with logging
            logger = get_logger(__name__)
            logger.error(f"Error in physical navigation ({nav_type}): {str(e)}")
            
            # Track errors
            if hasattr(self.context, 'stats'):
                self.context.stats["navigation_errors"] = self.context.stats.get("navigation_errors", 0) + 1
                
            # Set context error flag for pattern matching to handle
            self.context._navigation_context_error = True
            
            # Return None for proper SQL NULL comparison semantics
            return None
            
        finally:
            # Track performance metrics
            if hasattr(self.context, 'timing'):
                navigation_time = time.time() - start_time
                self.context.timing['physical_navigation'] = self.context.timing.get('physical_navigation', 0) + navigation_time
    
    def _logical_navigation(self, nav_type, column, steps, var_name=None):
        """
        Logical navigation for MEASURES expressions.
        Navigate through pattern match timeline using the enhanced navigation logic.
        """
        # Use the enhanced logical navigation logic
        # Implementation moved directly here for better performance and clarity
        
        logger = get_logger(__name__)
        logger.debug(f"[LOGICAL_NAV] nav_type={nav_type}, column={column}, steps={steps}, var_name={var_name}")
        
        # For logical navigation, we need to work with the pattern match timeline
        if not hasattr(self.context, 'variables') or not self.context.variables:
            logger.debug("[LOGICAL_NAV] No variables in context")
            return None
        
        # Build timeline of variable assignments
        timeline = []
        for var, indices in self.context.variables.items():
            for idx in indices:
                timeline.append((idx, var))
        
        # Sort by row index for consistent ordering
        timeline.sort()
        
        if not timeline:
            logger.debug("[LOGICAL_NAV] Empty timeline")
            return None
        
        # Find current position in timeline
        curr_idx = self.context.current_idx
        curr_pos = -1
        current_var = getattr(self.context, 'current_var', None)
        
        # Find position in timeline
        for i, (idx, var) in enumerate(timeline):
            if idx == curr_idx and (current_var is None or var == current_var or var_name is None):
                curr_pos = i
                break
        
        if curr_pos < 0:
            # Try alternative matching
            for i, (idx, var) in enumerate(timeline):
                if idx == curr_idx:
                    curr_pos = i
                    break
        
        if curr_pos < 0:
            logger.debug(f"[LOGICAL_NAV] Could not find current position for idx {curr_idx}")
            return None
        
        # Calculate target position
        if nav_type == 'PREV':
            target_pos = curr_pos - steps
        else:  # NEXT
            target_pos = curr_pos + steps
        
        # Bounds checking
        if target_pos < 0 or target_pos >= len(timeline):
            logger.debug(f"[LOGICAL_NAV] Target position {target_pos} out of bounds [0, {len(timeline)})")
            return None
        
        target_idx, _ = timeline[target_pos]
        
        # Check partition boundaries (if defined)
        if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
            current_partition = self.context.get_partition_for_row(curr_idx)
            target_partition = self.context.get_partition_for_row(target_idx)
            
            if (current_partition is None or target_partition is None or
                current_partition != target_partition):
                logger.debug(f"[LOGICAL_NAV] Cross-partition navigation not allowed")
                return None
        
        # Get value from target row
        if 0 <= target_idx < len(self.context.rows):
            result = self.context.rows[target_idx].get(column)
            logger.debug(f"[LOGICAL_NAV] Returning {result} from row {target_idx}")
            return result
        
        logger.debug(f"[LOGICAL_NAV] Target index {target_idx} out of range")
        return None

    def _handle_first_last_navigation(self, nav_type, column, steps, var_name=None):
        """
        Handle FIRST and LAST navigation functions with mode-aware behavior.
        
        DEFINE Mode (Physical Navigation):
        - FIRST(column) - gets the first value in the current partition
        - LAST(column) - gets the last value in the current partition
        
        MEASURES Mode (Logical Navigation):
        - FIRST(column) - gets the first value in the pattern match
        - LAST(column) - gets the last value in the pattern match
        
        Args:
            nav_type: 'FIRST' or 'LAST'
            column: Column name to retrieve
            steps: Number of steps (usually 1, but could be > 1)
            var_name: Optional variable name for qualified references
            
        Returns:
            The first/last value or None if not found
        """
        logger = get_logger(__name__)
        logger.debug(f"🔍 [FIRST_LAST] {nav_type}({column}, {steps}) var_name={var_name} mode={self.evaluation_mode}")
        
        try:
            if self.evaluation_mode == 'DEFINE':
                # In DEFINE mode, handle qualified vs unqualified references differently
                rows = self.context.rows
                
                if not rows:
                    logger.debug(f"[FIRST_LAST] No rows available")
                    return None
                
                if var_name:
                    # Qualified reference like FIRST(A.value) or LAST(A.value)
                    # Find first/last occurrence of the specific variable in the partial match
                    variable_name = var_name.strip('"')  # Remove quotes if present
                    
                    if hasattr(self.context, 'variables') and variable_name in self.context.variables:
                        var_indices = self.context.variables[variable_name]
                        if var_indices:
                            if nav_type == 'FIRST':
                                # Get the first occurrence of this variable
                                target_idx = var_indices[0]
                                logger.debug(f"[FIRST_LAST] DEFINE mode - FIRST({variable_name}): using row {target_idx}")
                            else:  # LAST
                                # Get the last occurrence of this variable that's <= current position
                                current_pos = getattr(self.context, 'current_idx', len(rows) - 1)
                                valid_indices = [idx for idx in var_indices if idx <= current_pos]
                                if valid_indices:
                                    target_idx = valid_indices[-1]
                                    logger.debug(f"[FIRST_LAST] DEFINE mode - LAST({variable_name}): using row {target_idx} (current_pos={current_pos})")
                                else:
                                    logger.debug(f"[FIRST_LAST] DEFINE mode - LAST({variable_name}): no valid indices")
                                    return None
                            
                            if target_idx < len(rows):
                                result = rows[target_idx].get(column)
                                logger.debug(f"[FIRST_LAST] DEFINE mode qualified result: {result}")
                                return result
                    
                    logger.debug(f"[FIRST_LAST] DEFINE mode - variable {variable_name} not found in context")
                    return None
                
                else:
                    # Unqualified reference like FIRST(value) or LAST(value)
                    # Use boundary values in the current partition (original behavior)
                    if nav_type == 'FIRST':
                        target_row = rows[0]
                        logger.debug(f"[FIRST_LAST] DEFINE mode - unqualified FIRST: using row 0")
                    else:  # LAST
                        target_row = rows[-1]
                        logger.debug(f"[FIRST_LAST] DEFINE mode - unqualified LAST: using row {len(rows)-1}")
                    
                    result = target_row.get(column)
                    logger.debug(f"[FIRST_LAST] DEFINE mode unqualified result: {result}")
                    return result
            
            else:
                # MEASURES mode: Use logical navigation through pattern matches
                # This is similar to logical navigation for PREV/NEXT
                logger.debug(f"[FIRST_LAST] MEASURES mode - using logical navigation")
                
                if nav_type == 'FIRST':
                    # For MEASURES, get the first value from the pattern match
                    if self.context.rows:
                        result = self.context.rows[0].get(column)
                        logger.debug(f"[FIRST_LAST] MEASURES FIRST result: {result}")
                        return result
                else:  # LAST
                    # For MEASURES, get the last value from the pattern match
                    if self.context.rows:
                        result = self.context.rows[-1].get(column)
                        logger.debug(f"[FIRST_LAST] MEASURES LAST result: {result}")
                        return result
                
                logger.debug(f"[FIRST_LAST] MEASURES mode - no rows available")
                return None
                
        except Exception as e:
            logger.debug(f"FIRST/LAST navigation failed: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

    def visit_Constant(self, node: ast.Constant):
        """Handle all constant types (numbers, strings, booleans, None)"""
        return node.value

    def visit_BoolOp(self, node: ast.BoolOp):
        """Handle boolean operations (AND, OR) with SQL NULL semantics"""
        if isinstance(node.op, ast.And):
            # For AND with SQL semantics:
            # - If any operand is None (NULL), result is None
            # - If any operand is False, result is False
            # - If all operands are True, result is True
            has_none = False
            for value in node.values:
                result = self.visit(value)
                if result is None:
                    has_none = True
                elif not result:  # False (but not None)
                    return False
            # If we found None but no False, return None
            if has_none:
                return None
            return True
        elif isinstance(node.op, ast.Or):
            # For OR with SQL semantics:
            # - If any operand is True, result is True
            # - If any operand is None and no True found, result is None
            # - If all operands are False, result is False
            has_none = False
            for value in node.values:
                result = self.visit(value)
                if result is True:
                    return True
                elif result is None:
                    has_none = True
            # If we found None but no True, return None
            if has_none:
                return None
            return False
        else:
            raise ValueError(f"Unsupported boolean operator: {type(node.op)}")

    def visit_IfExp(self, node: ast.IfExp):
        """
        Handle Python conditional expressions (ternary operator): x if condition else y
        
        This is crucial for handling CASE WHEN expressions converted to Python conditionals.
        For example: CASE WHEN CLASSIFIER() IN ('A', 'START') THEN 1 ELSE 0 END
        becomes: (1 if 'A' in ('A', 'START') else 0)
        
        Args:
            node: AST IfExp node representing a conditional expression
            
        Returns:
            The value of either the 'then' branch or 'else' branch based on condition
        """
        try:
            # Evaluate the condition (test)
            condition = self.visit(node.test)
            
            logger.debug(f"[DEBUG] IfExp condition: {condition} (type: {type(condition)})")
            
            # Handle None condition (SQL semantics)
            if condition is None:
                logger.debug("[DEBUG] IfExp condition is None, returning else value")
                return self.visit(node.orelse)
            
            # Python truth value evaluation
            if condition:
                result = self.visit(node.body)
                logger.debug(f"[DEBUG] IfExp condition is truthy, returning then value: {result}")
                return result
            else:
                result = self.visit(node.orelse)
                logger.debug(f"[DEBUG] IfExp condition is falsy, returning else value: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Error evaluating condition '{e}'")
            # For production readiness, we should return None on errors
            return None

    def visit_Tuple(self, node: ast.Tuple):
        """
        Handle tuple literals like ('A', 'START') in expressions.
        
        This is essential for IN predicates that use tuple literals.
        For example: 'A' in ('A', 'START') needs to parse the tuple correctly.
        
        Args:
            node: AST Tuple node
            
        Returns:
            A Python tuple with evaluated elements
        """
        try:
            # Evaluate each element in the tuple
            elements = []
            for elt in node.elts:
                value = self.visit(elt)
                elements.append(value)
            
            result = tuple(elements)
            logger.debug(f"[DEBUG] Tuple evaluation: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error evaluating tuple: {e}")
            return ()

    def visit_List(self, node: ast.List):
        """
        Handle list literals like ['A', 'START'] in expressions.
        
        This supports IN predicates that use list literals.
        For example: 'A' in ['A', 'START'] needs to parse the list correctly.
        
        Args:
            node: AST List node
            
        Returns:
            A Python list with evaluated elements
        """
        try:
            # Evaluate each element in the list
            elements = []
            for elt in node.elts:
                value = self.visit(elt)
                elements.append(value)
            
            result = elements
            logger.debug(f"[DEBUG] List evaluation: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error evaluating list: {e}")
            return []

    def _get_direct_classifier_at_index(self, row_idx: int, subset_var: Optional[str] = None) -> str:
        """
        Production-ready direct classifier lookup at specific row index.
        
        This method provides direct classifier lookup without creating temporary contexts
        or evaluators, preventing infinite recursion in subset navigation scenarios.
        
        Args:
            row_idx: Row index to get classifier for
            subset_var: Optional subset variable name for validation
            
        Returns:
            Classifier name for the specified row index
        """
        try:
            # Validate row index bounds
            if row_idx < 0 or row_idx >= len(self.context.rows):
                return None
            
            # Find which variable(s) match this row index
            matching_vars = []
            for var_name, indices in self.context.variables.items():
                if row_idx in indices:
                    matching_vars.append(var_name)
            
            if not matching_vars:
                return None
            
            # If subset variable specified, validate it's a component
            if subset_var and subset_var in self.context.subsets:
                subset_components = self.context.subsets[subset_var]
                matching_vars = [var for var in matching_vars if var in subset_components]
            
            # Return the first matching variable (or the most appropriate one)
            if matching_vars:
                # Apply case sensitivity rules for classifier
                result_var = matching_vars[0]  # Take first match
                
                # Apply case sensitivity rules
                if hasattr(self.context, 'defined_variables') and self.context.defined_variables:
                    if result_var.lower() in [v.lower() for v in self.context.defined_variables]:
                        # Preserve original case for defined variables
                        return result_var
                    else:
                        # Uppercase for undefined variables
                        return result_var.upper()
                else:
                    # Default to uppercase if no defined_variables info
                    return result_var.upper()
            
            return None
            
        except Exception as e:
            logger.error(f"Error in direct classifier lookup at index {row_idx}: {e}")
            return None


# External function imports that are referenced but defined elsewhere
def evaluate_nested_navigation(expr: str, context: RowContext, current_idx: int, current_var: Optional[str] = None, recursion_depth: int = 0) -> Any:
    """
    Placeholder for nested navigation evaluation.
    This function should be implemented in a separate module to handle complex nested navigation.
    """
    # This is a placeholder - the actual implementation should be in a separate module
    logger.warning(f"evaluate_nested_navigation called but not implemented: {expr}")
    return None


def compile_condition(condition_str, evaluation_mode='DEFINE'):
    """
    Compile a condition string into a callable function.
    
    Args:
        condition_str: SQL condition string
        evaluation_mode: 'DEFINE' for pattern definitions, 'MEASURES' for measures
        
    Returns:
        A callable function that takes a row and context and returns a boolean
    """
    if not condition_str or condition_str.strip().upper() == 'TRUE':
        # Optimization for true condition
        return lambda row, ctx: True
        
    if condition_str.strip().upper() == 'FALSE':
        # Optimization for false condition
        return lambda row, ctx: False
    
    try:
        # Convert SQL syntax to Python syntax
        python_condition = _sql_to_python_condition(condition_str)
        
        # Parse the condition
        tree = ast.parse(python_condition, mode='eval')
        
        # Create a function that evaluates the condition with the given row and context
        def evaluate_condition(row, ctx):
            # Create evaluator with the given context
            evaluator = ConditionEvaluator(ctx, evaluation_mode)
            
            # Set the current row
            evaluator.current_row = row
            
            # Evaluate the condition
            try:
                result = evaluator.visit(tree.body)
                
                # Determine if we should return boolean or actual value based on expression structure
                # If the top-level expression is a boolean operation, comparison, etc., return boolean
                # If it's a simple value expression (like standalone CLASSIFIER(U)), return the actual value
                if _is_boolean_expression(tree.body):
                    return bool(result)
                else:
                    # For standalone value expressions, return the actual value
                    return result
                        
            except Exception as e:
                logger.error(f"Error evaluating condition '{condition_str}': {e}")
                return False
                
        return evaluate_condition
    except SyntaxError as e:
        # Log the error and return a function that always returns False
        logger.error(f"Syntax error in condition '{condition_str}': {e}")
        return lambda row, ctx: False
    except Exception as e:
        # Log the error and return a function that always returns False
        logger.error(f"Error compiling condition '{condition_str}': {e}")
        return lambda row, ctx: False


def validate_navigation_conditions(pattern_variables, define_clauses):
    """
    Validate that navigation function calls in conditions are valid for the pattern.
    
    For example, navigation calls that reference pattern variables that don't appear
    in the pattern or haven't been matched yet are invalid.
    
    Args:
        pattern_variables: List of pattern variables from the pattern definition
        define_clauses: Dict mapping variable names to their conditions
        
    Returns:
        True if all navigation conditions are valid, False otherwise
    """
    # Validate each condition for each variable
    for var, condition in define_clauses.items():
        if var not in pattern_variables:
            logger.warning(f"Variable {var} in DEFINE clause not found in pattern")
            continue
            
        # Validate navigation references to other variables
        for ref_var in pattern_variables:
            # Skip self-references (always valid)
            if ref_var == var:
                continue
                
            # Find PREV(var) references - must be exact variable references, not column references
            if f"PREV({ref_var})" in condition:
                # Ensure the referenced variable appears before this one in the pattern
                var_idx = pattern_variables.index(var)
                ref_idx = pattern_variables.index(ref_var)
                
                if ref_idx >= var_idx:
                    logger.error(f"Invalid PREV({ref_var}) reference in condition for {var}: "
                               f"{ref_var} does not appear before {var} in the pattern")
                    return False
            
            # Find NEXT(var) references - must be exact variable references, not column references  
            if f"NEXT({ref_var})" in condition:
                # Ensure the referenced variable appears after this one in the pattern
                var_idx = pattern_variables.index(var)
                ref_idx = pattern_variables.index(ref_var)
                
                if ref_idx <= var_idx:
                    logger.error(f"Invalid NEXT({ref_var}) reference in condition for {var}: "
                               f"{ref_var} does not appear after {var} in the pattern")
                    return False
        
        # SQL:2016 Standard Compliance: Check for NEXT() usage in DEFINE clauses
        # NEXT() function usage should be restricted, but allow self-references
        if "NEXT(" in condition:
            var_idx = pattern_variables.index(var)
            is_final_variable = var_idx == len(pattern_variables) - 1
            
            # Allow NEXT() in final variables or when referencing the same variable
            # Pattern: NEXT(current_var.column) or NEXT(column) should be allowed
            import re
            next_calls = re.findall(r'NEXT\(([^)]+)\)', condition)
            
            for next_arg in next_calls:
                # Extract variable name if qualified (e.g., "A.price" -> "A")
                if '.' in next_arg:
                    referenced_var = next_arg.split('.')[0]
                    # Allow self-references (A.price in condition for A)
                    if referenced_var == var:
                        continue
                    # For cross-variable references, check if target appears later
                    if referenced_var in pattern_variables:
                        ref_idx = pattern_variables.index(referenced_var)
                        if ref_idx <= var_idx:
                            logger.error(f"Invalid NEXT({next_arg}) reference in condition for {var}: "
                                       f"{referenced_var} does not appear after {var} in the pattern")
                            return False
                else:
                    # Unqualified NEXT(column) - allow for any variable in practical implementation
                    # This is a column reference, not a variable reference
                    continue
            
            # Additional SQL:2016 compliance can be added here if needed
            # For now, we allow NEXT() with proper variable ordering validation
        
        # Similar validation for FIRST() and LAST() functions
        for nav_func in ['FIRST', 'LAST']:
            if f"{nav_func}(" in condition:
                import re
                nav_calls = re.findall(f'{nav_func}\\(([^)]+)\\)', condition)
                
                for nav_arg in nav_calls:
                    # Extract variable name if qualified (e.g., "A.value" -> "A")
                    if '.' in nav_arg:
                        referenced_var = nav_arg.split('.')[0]
                        # For FIRST/LAST, the referenced variable should exist in pattern
                        if referenced_var in pattern_variables:
                            # FIRST/LAST can reference any variable in the pattern
                            # This is generally allowed as they refer to boundary values
                            continue
                        else:
                            logger.warning(f"{nav_func}({nav_arg}) references unknown variable {referenced_var}")
                    else:
                        # Unqualified FIRST/LAST(column) - allow for any variable
                        continue
    
    # If all checks pass
    return True


def evaluate_nested_navigation(expr: str, context: RowContext, current_idx: int, current_var: Optional[str] = None, recursion_depth: int = 0) -> Any:
    """
    Enhanced nested navigation evaluation with comprehensive pattern support.
    
    Key improvements:
    - Advanced recursion protection with depth tracking
    - Enhanced parser for complex navigation expressions
    - Better error handling and recovery mechanisms
    - Improved performance with smart caching
    - Support for more complex nested patterns
    - Thread-safe evaluation with proper context management
    
    This function handles complex navigation expressions that may contain nested function calls
    like NEXT(PREV(value)), FIRST(CLASSIFIER()), PREV(LAST(A.value), 3), and SQL-specific 
    constructs like PREV(RUNNING LAST(value)).
    
    Args:
        expr: The navigation expression string to evaluate
        context: The row context for evaluation
        current_idx: Current row index
        current_var: Current pattern variable (optional)
        recursion_depth: Current recursion depth for protection
        
    Returns:
        The evaluated result or None if evaluation fails
    """
    
    try:
        import re
        import ast
        
        # Enhanced recursion protection
        max_recursion_depth = 15
        if recursion_depth >= max_recursion_depth:
            logger.warning(f"[NESTED_NAV] Maximum recursion depth {max_recursion_depth} reached for: '{expr}'")
            return None
        
        # Enhanced expression validation and cleanup
        if not expr or not isinstance(expr, str):
            logger.warning(f"[NESTED_NAV] Invalid expression: {expr}")
            return None
        
        processed_expr = expr.strip()
        if not processed_expr:
            return None
        
        # Set up evaluation context with recursion protection
        original_evaluator = getattr(context, '_active_evaluator', None)
        
        logger.debug(f"[NESTED_NAV] Evaluating: '{processed_expr}' at depth {recursion_depth}")
        
        # Enhanced pattern matching for complex navigation structures
        
        # Pattern 1: Complex arithmetic with multiple navigation functions
        # Example: PREV(LAST(A.value), 3) + FIRST(A.value) + PREV(LAST(B.value), 2)
        complex_arithmetic_pattern = r'.*(?:PREV|NEXT|FIRST|LAST)\s*\(.*[\+\-\*\/].*(?:PREV|NEXT|FIRST|LAST)\s*\('
        if re.search(complex_arithmetic_pattern, processed_expr, re.IGNORECASE):
            logger.debug(f"[NESTED_NAV] Complex arithmetic navigation detected")
            return _evaluate_complex_arithmetic_navigation(processed_expr, context, current_idx, current_var, recursion_depth)
        
        # Pattern 2: Nested navigation functions like PREV(FIRST(A.value), 3)
        nested_nav_pattern = r'(PREV|NEXT)\s*\(\s*(FIRST|LAST)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*\)\s*(?:,\s*(\d+))?\s*\)'
        nested_nav_match = re.match(nested_nav_pattern, processed_expr, re.IGNORECASE)
        
        if nested_nav_match:
            return _evaluate_nested_navigation_pattern(nested_nav_match, context, current_idx, recursion_depth)
        
        # Pattern 3: CLASSIFIER navigation functions
        classifier_nav_pattern = r'(FIRST|LAST|PREV|NEXT)\s*\(\s*CLASSIFIER\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)?\s*\)\s*(?:,\s*(\d+))?\s*\)'
        classifier_nav_match = re.match(classifier_nav_pattern, processed_expr, re.IGNORECASE)
        
        if classifier_nav_match:
            return _evaluate_classifier_navigation(classifier_nav_match, context, current_idx, recursion_depth)
        
        # Pattern 4: Enhanced function call patterns with better variable references
        enhanced_func_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*(?:,\s*(\d+))?\s*\)'
        enhanced_func_match = re.match(enhanced_func_pattern, processed_expr, re.IGNORECASE)
        
        if enhanced_func_match:
            return _evaluate_enhanced_function_call(enhanced_func_match, context, current_idx, recursion_depth)
        
        # Pattern 5: SQL-specific constructs (RUNNING, FINAL keywords)
        sql_construct_pattern = r'(PREV|NEXT)\s*\(\s*(RUNNING|FINAL)\s+(FIRST|LAST)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*\)\s*(?:,\s*(\d+))?\s*\)'
        sql_construct_match = re.match(sql_construct_pattern, processed_expr, re.IGNORECASE)
        
        if sql_construct_match:
            return _evaluate_sql_construct_navigation(sql_construct_match, context, current_idx, recursion_depth)
        
        # Fallback: Try AST evaluation with enhanced error handling
        try:
            return _evaluate_ast_navigation(processed_expr, context, current_idx, current_var, recursion_depth)
        except Exception as e:
            logger.debug(f"[NESTED_NAV] AST evaluation failed: {e}")
            return None
            
    except Exception as e:
        logger.error(f"[NESTED_NAV] Evaluation error for '{expr}': {e}")
        return None
    finally:
        # Restore original evaluator context
        if original_evaluator is not None:
            context._active_evaluator = original_evaluator


def _evaluate_complex_arithmetic_navigation(expr: str, context: RowContext, current_idx: int, current_var: Optional[str], recursion_depth: int) -> Any:
    """Evaluate complex arithmetic expressions with multiple navigation functions."""
    try:
        # Use AST parsing for complex arithmetic
        tree = ast.parse(expr, mode='eval')
        
        # Create or reuse evaluator with recursion protection
        if hasattr(context, '_active_evaluator') and context._active_evaluator is not None:
            evaluator = context._active_evaluator
            evaluator.current_row = context.rows[current_idx] if 0 <= current_idx < len(context.rows) else None
        else:
            # Navigation functions should always use DEFINE mode for consistency
            # This ensures that FIRST, LAST, PREV, NEXT always operate on the matched pattern data
            evaluation_mode = 'DEFINE'
                
            evaluator = ConditionEvaluator(context, evaluation_mode, recursion_depth + 1)
            evaluator.current_row = context.rows[current_idx] if 0 <= current_idx < len(context.rows) else None
            context._active_evaluator = evaluator
        
        result = evaluator.visit(tree.body)
        logger.debug(f"[NESTED_NAV] Complex arithmetic result: {result}")
        return result
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Complex arithmetic evaluation failed: {e}")
        return None


def _evaluate_nested_navigation_pattern(match, context: RowContext, current_idx: int, recursion_depth: int) -> Any:
    """Evaluate nested navigation patterns like PREV(FIRST(A.value), 3)."""
    try:
        outer_func = match.group(1).upper()  # PREV or NEXT
        inner_func = match.group(2).upper()  # FIRST or LAST
        column_ref = match.group(3)          # A.value or just column
        steps = int(match.group(4)) if match.group(4) else 1
        
        logger.debug(f"[NESTED_NAV] Nested pattern: {outer_func}({inner_func}({column_ref}), {steps})")
        
        # Parse column reference
        if '.' in column_ref:
            var_name, col_name = column_ref.split('.', 1)
        else:
            var_name = None
            col_name = column_ref
        
        # Find the FIRST/LAST row index for the variable
        if var_name and hasattr(context, 'variables') and var_name in context.variables:
            var_indices = context.variables[var_name]
            logger.debug(f"[NESTED_NAV] Variable {var_name} indices: {var_indices}")
            
            if var_indices:
                if inner_func == 'FIRST':
                    target_base_idx = min(var_indices)
                else:  # LAST
                    target_base_idx = max(var_indices)
                
                logger.debug(f"[NESTED_NAV] {inner_func} index: {target_base_idx}")
                
                # Apply PREV/NEXT with steps
                if outer_func == 'PREV':
                    final_idx = target_base_idx - steps
                else:  # NEXT
                    final_idx = target_base_idx + steps
                
                logger.debug(f"[NESTED_NAV] Final index: {final_idx}")
                
                # Get value with bounds checking
                if 0 <= final_idx < len(context.rows):
                    result = context.rows[final_idx].get(col_name)
                    logger.debug(f"[NESTED_NAV] Result: {result}")
                    return result
                else:
                    logger.debug(f"[NESTED_NAV] Index {final_idx} out of bounds")
                    return None
            else:
                logger.debug(f"[NESTED_NAV] No indices for variable {var_name}")
                return None
        else:
            # Handle case where var_name is None (column-only reference)
            logger.debug(f"[NESTED_NAV] Column-only reference: {col_name}")
            
            # Find all indices in current match
            all_indices = []
            if hasattr(context, 'variables'):
                for var, indices in context.variables.items():
                    all_indices.extend(indices)
            
            if all_indices:
                all_indices = sorted(set(all_indices))
                
                if inner_func == 'FIRST':
                    target_base_idx = all_indices[0]
                else:  # LAST
                    target_base_idx = all_indices[-1]
                
                # Apply PREV/NEXT
                if outer_func == 'PREV':
                    final_idx = target_base_idx - steps
                else:  # NEXT
                    final_idx = target_base_idx + steps
                
                if 0 <= final_idx < len(context.rows):
                    result = context.rows[final_idx].get(col_name)
                    return result
            
            return None
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Nested pattern evaluation failed: {e}")
        return None


def _evaluate_classifier_navigation(match, context: RowContext, current_idx: int, recursion_depth: int) -> Any:
    """Evaluate CLASSIFIER navigation functions."""
    try:
        nav_func = match.group(1).upper()     # FIRST, LAST, PREV, NEXT
        classifier_var = match.group(2)       # Optional variable name
        steps = int(match.group(3)) if match.group(3) else 1
        
        logger.debug(f"[NESTED_NAV] Classifier navigation: {nav_func}(CLASSIFIER({classifier_var}), {steps})")
        
        if nav_func in ('FIRST', 'LAST'):
            # Handle FIRST/LAST CLASSIFIER
            return _handle_first_last_classifier_navigation(nav_func, classifier_var, steps, context)
        elif nav_func in ('PREV', 'NEXT'):
            # Handle PREV/NEXT CLASSIFIER
            return _handle_prev_next_classifier_navigation(nav_func, classifier_var, steps, context, current_idx)
        else:
            logger.warning(f"[NESTED_NAV] Unsupported classifier navigation: {nav_func}")
            return None
            
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Classifier navigation failed: {e}")
        return None


def _handle_first_last_classifier_navigation(nav_func: str, classifier_var: Optional[str], steps: int, context: RowContext) -> Any:
    """Handle FIRST/LAST CLASSIFIER navigation."""
    try:
        # Check if we're in FINAL semantics mode
        # For FINAL semantics, LAST should return the absolute last classifier, not relative to current position
        is_final_semantics = False
        
        # Try to detect FINAL semantics from evaluator or context
        if hasattr(context, '_active_evaluator'):
            evaluator = context._active_evaluator
            # Check if evaluator is in MEASURES mode, which typically indicates FINAL semantics for LAST
            if hasattr(evaluator, 'evaluation_mode') and evaluator.evaluation_mode == 'MEASURES':
                is_final_semantics = True
        
        # Alternative: Check if context has semantics information
        if hasattr(context, '_current_semantics'):
            is_final_semantics = context._current_semantics == 'FINAL'
            
        logger.debug(f"[CLASSIFIER_NAV] {nav_func}(CLASSIFIER({classifier_var}), {steps}) - FINAL semantics: {is_final_semantics}")
        
        if classifier_var and hasattr(context, 'subsets') and classifier_var in context.subsets:
            # Subset variable navigation
            component_vars = context.subsets[classifier_var]
            all_indices = []
            
            for comp_var in component_vars:
                if comp_var in context.variables:
                    all_indices.extend(context.variables[comp_var])
            
            if all_indices:
                all_indices = sorted(set(all_indices))
                
                if nav_func == 'FIRST':
                    if steps > len(all_indices):
                        return None
                    target_idx = all_indices[steps - 1] if steps > 0 else all_indices[0]
                else:  # LAST
                    if is_final_semantics:
                        # FINAL semantics: always return classifier from the absolute last row
                        target_idx = all_indices[-1] if all_indices else None
                        if target_idx is None:
                            return None
                    else:
                        # RUNNING semantics: relative to current position
                        if not hasattr(context, 'current_idx'):
                            return None
                        current_idx = context.current_idx
                        target_idx = current_idx - steps
                        if target_idx < 0 or target_idx not in all_indices:
                            return None
                
                logger.debug(f"[CLASSIFIER_NAV] Subset navigation target_idx: {target_idx}")
                return _get_classifier_at_index(target_idx, classifier_var, context)
        else:
            # General CLASSIFIER navigation
            all_indices = []
            if hasattr(context, 'variables'):
                for var, indices in context.variables.items():
                    all_indices.extend(indices)
            
            if all_indices:
                all_indices = sorted(set(all_indices))
                
                if nav_func == 'FIRST':
                    if steps > len(all_indices):
                        return None
                    target_idx = all_indices[steps - 1] if steps > 0 else all_indices[0]
                else:  # LAST
                    if is_final_semantics:
                        # FINAL semantics: always return classifier from the absolute last row in the match
                        target_idx = all_indices[-1] if all_indices else None
                        if target_idx is None:
                            return None
                        logger.debug(f"[CLASSIFIER_NAV] FINAL LAST: using absolute last index {target_idx}")
                    else:
                        # RUNNING semantics: relative to current position
                        if not hasattr(context, 'current_idx'):
                            return None
                        current_idx = context.current_idx
                        target_idx = current_idx - steps
                        if target_idx < 0:
                            return None
                        logger.debug(f"[CLASSIFIER_NAV] RUNNING LAST: using relative index {target_idx} (current={current_idx} - steps={steps})")
                
                logger.debug(f"[CLASSIFIER_NAV] General navigation target_idx: {target_idx}")
                return _get_classifier_at_index(target_idx, None, context)
        
        return None
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] FIRST/LAST classifier navigation failed: {e}")
        return None


def _handle_prev_next_classifier_navigation(nav_func: str, classifier_var: Optional[str], steps: int, context: RowContext, current_idx: int) -> Any:
    """Handle PREV/NEXT CLASSIFIER navigation."""
    try:
        if nav_func == 'PREV':
            target_idx = current_idx - steps
        else:  # NEXT
            target_idx = current_idx + steps
        
        # Check bounds
        if target_idx < 0 or target_idx >= len(context.rows):
            return None
        
        return _get_classifier_at_index(target_idx, classifier_var, context)
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] PREV/NEXT classifier navigation failed: {e}")
        return None


def _get_classifier_at_index(row_idx: int, subset_var: Optional[str], context: RowContext) -> str:
    """Get classifier value at specific index."""
    try:
        if row_idx < 0 or row_idx >= len(context.rows):
            return ""
        
        # Find which variable(s) this row belongs to
        matching_vars = []
        
        # Use full variables for forward navigation if available
        variables_to_search = getattr(context, '_full_match_variables', None) or getattr(context, 'variables', {})
        
        if variables_to_search:
            for var_name, indices in variables_to_search.items():
                if row_idx in indices:
                    matching_vars.append(var_name)
        
        if not matching_vars:
            return ""
        
        # If subset variable specified, validate
        if subset_var and hasattr(context, 'subsets') and subset_var in context.subsets:
            subset_components = context.subsets[subset_var]
            matching_vars = [var for var in matching_vars if var in subset_components]
            if matching_vars:
                # Return the actual component variable, not the subset name
                result_var = matching_vars[0]
                if hasattr(context, 'defined_variables') and context.defined_variables:
                    if result_var.lower() in [v.lower() for v in context.defined_variables]:
                        return result_var
                    else:
                        return result_var.upper()
                else:
                    return result_var.upper()
        
        if matching_vars:
            # Apply case sensitivity rules for classifier
            result_var = matching_vars[0]
            if hasattr(context, 'defined_variables') and context.defined_variables:
                if result_var.lower() in [v.lower() for v in context.defined_variables]:
                    return result_var
                else:
                    return result_var.upper()
            else:
                return result_var.upper()
        
        return ""
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Get classifier at index failed: {e}")
        return ""


def _evaluate_enhanced_function_call(match, context: RowContext, current_idx: int, recursion_depth: int) -> Any:
    """Evaluate enhanced function calls with better variable handling."""
    try:
        func_name = match.group(1).upper()
        column_ref = match.group(2)
        steps = int(match.group(3)) if match.group(3) else 1
        
        logger.debug(f"[NESTED_NAV] Enhanced function call: {func_name}({column_ref}, {steps})")
        
        # Parse column reference
        if '.' in column_ref:
            var_name, col_name = column_ref.split('.', 1)
        else:
            var_name = None
            col_name = column_ref
        
        # Create evaluator for navigation
        evaluator = ConditionEvaluator(context, 'MEASURES', recursion_depth + 1)
        evaluator.current_row = context.rows[current_idx] if 0 <= current_idx < len(context.rows) else None
        
        # Use the appropriate navigation function based on type
        if func_name in ('FIRST', 'LAST'):
            result = evaluator._handle_first_last_navigation(func_name, col_name, steps, var_name)
        else:  # PREV, NEXT
            result = evaluator.evaluate_navigation_function(func_name, col_name, steps, var_name)
        logger.debug(f"[NESTED_NAV] Enhanced function result: {result}")
        return result
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Enhanced function call failed: {e}")
        return None


def _evaluate_sql_construct_navigation(match, context: RowContext, current_idx: int, recursion_depth: int) -> Any:
    """Evaluate SQL construct navigation (RUNNING/FINAL keywords)."""
    try:
        outer_func = match.group(1).upper()     # PREV or NEXT
        sql_keyword = match.group(2).upper()   # RUNNING or FINAL
        inner_func = match.group(3).upper()    # FIRST or LAST
        column_ref = match.group(4)
        steps = int(match.group(5)) if match.group(5) else 1
        
        logger.debug(f"[NESTED_NAV] SQL construct: {outer_func}({sql_keyword} {inner_func}({column_ref}), {steps})")
        
        # Parse column reference
        if '.' in column_ref:
            var_name, col_name = column_ref.split('.', 1)
        else:
            var_name = None
            col_name = column_ref
        
        # Handle RUNNING vs FINAL semantics
        if sql_keyword == 'RUNNING':
            # RUNNING semantics: consider only rows up to current_idx in the match
            # Find the appropriate base row index using RUNNING semantics
            target_base_idx = _find_running_base_index(inner_func, var_name, col_name, context, current_idx)
        else:  # FINAL
            # FINAL semantics: consider all rows in the complete match
            target_base_idx = _find_final_base_index(inner_func, var_name, col_name, context)
        
        if target_base_idx is None:
            logger.debug(f"[NESTED_NAV] Could not find base index for {sql_keyword} {inner_func}")
            return None
        
        logger.debug(f"[NESTED_NAV] {sql_keyword} {inner_func} base index: {target_base_idx}")
        
        # Apply PREV/NEXT with steps
        if outer_func == 'PREV':
            final_idx = target_base_idx - steps
        else:  # NEXT
            final_idx = target_base_idx + steps
        
        logger.debug(f"[NESTED_NAV] Final index after {outer_func}({steps}): {final_idx}")
        
        # Get value with bounds checking
        if 0 <= final_idx < len(context.rows):
            result = context.rows[final_idx].get(col_name)
            logger.debug(f"[NESTED_NAV] Result: {result}")
            return result
        else:
            logger.debug(f"[NESTED_NAV] Index {final_idx} out of bounds [0, {len(context.rows)})")
            return None
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] SQL construct navigation failed: {e}")
        return None


def _find_running_base_index(inner_func: str, var_name: Optional[str], col_name: str, context: RowContext, current_idx: int) -> Optional[int]:
    """Find base index for RUNNING semantics (considering only rows up to current_idx)."""
    try:
        if var_name and hasattr(context, 'variables') and var_name in context.variables:
            # Variable-specific running semantics
            var_indices = [idx for idx in context.variables[var_name] if idx <= current_idx]
            if var_indices:
                if inner_func == 'FIRST':
                    return min(var_indices)
                else:  # LAST
                    return max(var_indices)
        else:
            # Column-only reference: consider all rows up to current_idx
            if inner_func == 'FIRST':
                return 0 if current_idx >= 0 else None
            else:  # LAST
                return current_idx if current_idx >= 0 else None
        
        return None
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Error finding running base index: {e}")
        return None


def _find_final_base_index(inner_func: str, var_name: Optional[str], col_name: str, context: RowContext) -> Optional[int]:
    """Find base index for FINAL semantics (considering all rows in match)."""
    try:
        if var_name and hasattr(context, 'variables') and var_name in context.variables:
            # Variable-specific final semantics
            var_indices = context.variables[var_name]
            if var_indices:
                if inner_func == 'FIRST':
                    return min(var_indices)
                else:  # LAST
                    return max(var_indices)
        else:
            # Column-only reference: consider all rows in context
            if inner_func == 'FIRST':
                return 0 if context.rows else None
            else:  # LAST
                return len(context.rows) - 1 if context.rows else None
        
        return None
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Error finding final base index: {e}")
        return None


def _evaluate_ast_navigation(expr: str, context: RowContext, current_idx: int, current_var: Optional[str], recursion_depth: int) -> Any:
    """Fallback AST evaluation for navigation expressions."""
    try:
        logger.debug(f"[NESTED_NAV] AST fallback evaluation: {expr}")
        
        tree = ast.parse(expr, mode='eval')
        
        # Create evaluator with recursion protection
        evaluator = ConditionEvaluator(context, 'MEASURES', recursion_depth + 1)
        evaluator.current_row = context.rows[current_idx] if 0 <= current_idx < len(context.rows) else None
        
        # Set active evaluator to prevent further nesting
        original_evaluator = getattr(context, '_active_evaluator', None)
        context._active_evaluator = evaluator
        
        try:
            result = evaluator.visit(tree.body)
            logger.debug(f"[NESTED_NAV] AST result: {result}")
            return result
        finally:
            context._active_evaluator = original_evaluator
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] AST evaluation failed: {e}")
        return None


def _sql_to_python_condition(condition: str) -> str:
    """
    Convert SQL condition syntax to Python expression syntax.
    
    Args:
        condition: SQL condition string
        
    Returns:
        Python expression string
    """
    if not condition:
        return condition
    
    import re
    
    # Clean up whitespace and newlines to make valid Python expression
    # Replace newlines and multiple spaces with single spaces
    condition = re.sub(r'\s+', ' ', condition.strip())
    
    # Convert SQL equality to Python equality
    # Handle cases like 'value = 10' -> 'value == 10'
    # But avoid changing '==' to '===='
    
    # First, preserve quoted strings to avoid corrupting them during regex replacements
    # Find all quoted strings and replace them with placeholders
    quote_patterns = [
        (r"'([^']*)'", "SINGLE_QUOTE_"),  # Single quotes
        (r'"([^"]*)"', "DOUBLE_QUOTE_"),  # Double quotes
    ]
    
    preserved_strings = {}
    placeholder_counter = 0
    
    for pattern, prefix in quote_patterns:
        matches = re.finditer(pattern, condition)
        for match in matches:
            placeholder = f"{prefix}{placeholder_counter}"
            preserved_strings[placeholder] = match.group(0)
            condition = condition.replace(match.group(0), placeholder, 1)
            placeholder_counter += 1
    
    # Convert SQL CASE expressions to Python conditional expressions
    # Pattern: CASE WHEN condition1 THEN result1 WHEN condition2 THEN result2 ... ELSE default END
    case_pattern = r'\bCASE\s+(.*?)\s+END\b'
    
    def convert_case(match):
        case_content = match.group(1)
        
        # Find all WHEN...THEN pairs
        when_pattern = r'\bWHEN\s+(.*?)\s+THEN\s+(.*?)(?=\s+WHEN|\s+ELSE|$)'
        when_matches = re.findall(when_pattern, case_content, re.IGNORECASE | re.DOTALL)
        
        # Find ELSE clause
        else_match = re.search(r'\bELSE\s+(.*?)$', case_content, re.IGNORECASE | re.DOTALL)
        else_clause = else_match.group(1).strip() if else_match else 'None'
        
        if not when_matches:
            return match.group(0)  # Return original if can't parse
        
        # Build nested conditional expression from right to left
        result = else_clause
        
        # Process WHEN clauses in reverse order to build nested conditionals
        for when_condition, then_result in reversed(when_matches):
            when_condition = when_condition.strip()
            then_result = then_result.strip()
            
            # Recursively convert the condition (but avoid infinite recursion)
            # Don't recursively call _sql_to_python_condition here as it can cause issues
            # Just handle basic operators in the when_condition
            when_condition = re.sub(r'(?<![=!<>])\s*=\s*(?!=)', ' == ', when_condition)
            when_condition = re.sub(r'\bAND\b', 'and', when_condition, flags=re.IGNORECASE)
            when_condition = re.sub(r'\bOR\b', 'or', when_condition, flags=re.IGNORECASE)
            when_condition = re.sub(r'\bNOT\b', 'not', when_condition, flags=re.IGNORECASE)
            
            result = f'({then_result} if {when_condition} else {result})'
        
        return result
    
    # Apply CASE conversion
    condition = re.sub(case_pattern, convert_case, condition, flags=re.IGNORECASE | re.DOTALL)
    
    # Replace single = with == but avoid changing already existing ==
    condition = re.sub(r'(?<![=!<>])\s*=\s*(?!=)', ' == ', condition)
    
    # Convert SQL logical operators to Python operators
    # Use word boundaries to avoid replacing parts of words
    condition = re.sub(r'\bAND\b', 'and', condition, flags=re.IGNORECASE)
    condition = re.sub(r'\bOR\b', 'or', condition, flags=re.IGNORECASE)
    condition = re.sub(r'\bNOT\b', 'not', condition, flags=re.IGNORECASE)
    
    # Convert SQL BETWEEN to Python range check
    # BETWEEN pattern: column BETWEEN value1 AND value2
    between_pattern = r'(\w+)\s+BETWEEN\s+([^A]+?)\s+AND\s+([^A]+?)(?=\s|$)'
    condition = re.sub(between_pattern, r'(\2 <= \1 <= \3)', condition, flags=re.IGNORECASE)
    
    # Handle IS NULL and IS NOT NULL
    # Use a helper function for null checking that handles both None and NaN
    condition = re.sub(r'(\w+(?:\.\w+)?)\s+IS\s+NULL\b', r'_is_null(\1)', condition, flags=re.IGNORECASE)
    condition = re.sub(r'(\w+(?:\.\w+)?)\s+IS\s+NOT\s+NULL\b', r'(not _is_null(\1))', condition, flags=re.IGNORECASE)
    
    # Handle IN predicates - convert SQL IN to Python in
    # Pattern: expression IN (value1, value2, ...) -> expression in [value1, value2, ...]
    # Enhanced to support function calls like LOWER(column) IN (...)
    def convert_in_predicate(match):
        full_match = match.group(0)
        left_expr = match.group(1).strip()
        in_values = match.group(2).strip()
        
        # If empty, return special handling
        if not in_values:
            return f'{left_expr} in []'
        
        # Convert parentheses to square brackets for Python list syntax
        python_list = f'[{in_values}]'
        return f'{left_expr} in {python_list}'
    
    # Enhanced IN predicates pattern to handle various expressions
    # This pattern matches multiple cases:
    # 1. Simple identifiers: column
    # 2. Dotted expressions: table.column
    # 3. Function calls: FUNCTION(args)
    # 4. Parenthesized expressions: (expression)
    # 5. Complex expressions: (value + 10), (column * 2), etc.
    
    # First try to match parenthesized expressions like (value + 10) IN (...)
    parenthesized_in_pattern = r'(\([^)]+\))\s+IN\s*\(([^)]*)\)'
    condition = re.sub(parenthesized_in_pattern, convert_in_predicate, condition, flags=re.IGNORECASE)
    
    # Then match function calls like SUBSTR(column, 1, 1) IN (...)
    complex_in_pattern = r'([A-Za-z_][A-Za-z0-9_]*\([^)]*(?:\([^)]*\)[^)]*)*\))\s+IN\s*\(([^)]*)\)'
    condition = re.sub(complex_in_pattern, convert_in_predicate, condition, flags=re.IGNORECASE)
    
    # Finally match simple expressions: column IN (...), table.column IN (...)
    simple_in_pattern = r'([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s+IN\s*\(([^)]*)\)'
    condition = re.sub(simple_in_pattern, convert_in_predicate, condition, flags=re.IGNORECASE)
    
    # Handle NOT IN predicates
    def convert_not_in_predicate(match):
        full_match = match.group(0)
        left_expr = match.group(1).strip()
        in_values = match.group(2).strip()
        
        # If empty, return special handling
        if not in_values:
            return f'{left_expr} not in []'
        
        # Convert parentheses to square brackets for Python list syntax
        python_list = f'[{in_values}]'
        return f'{left_expr} not in {python_list}'
    
    # Enhanced NOT IN predicates pattern to handle various expressions
    # First try to match parenthesized expressions like (value + 10) NOT IN (...)
    parenthesized_not_in_pattern = r'(\([^)]+\))\s+NOT\s+IN\s*\(([^)]*)\)'
    condition = re.sub(parenthesized_not_in_pattern, convert_not_in_predicate, condition, flags=re.IGNORECASE)
    
    # Then match function calls like SUBSTR(column, 1, 1) NOT IN (...)
    complex_not_in_pattern = r'([A-Za-z_][A-Za-z0-9_]*\([^)]*(?:\([^)]*\)[^)]*)*\))\s+NOT\s+IN\s*\(([^)]*)\)'
    condition = re.sub(complex_not_in_pattern, convert_not_in_predicate, condition, flags=re.IGNORECASE)
    
    # Finally match simple expressions: column NOT IN (...), table.column NOT IN (...)
    simple_not_in_pattern = r'([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s+NOT\s+IN\s*\(([^)]*)\)'
    condition = re.sub(simple_not_in_pattern, convert_not_in_predicate, condition, flags=re.IGNORECASE)
    
    # Handle empty IN predicates - convert to always false/true
    condition = re.sub(r'\bIN\s*\(\s*\)', 'in []', condition, flags=re.IGNORECASE)
    condition = re.sub(r'\bNOT\s+IN\s*\(\s*\)', 'not in []', condition, flags=re.IGNORECASE)
    
    # Restore preserved quoted strings
    for placeholder, original_string in preserved_strings.items():
        condition = condition.replace(placeholder, original_string)
    
    return condition

def _is_boolean_expression(node):
    """
    Determine if an AST node represents a boolean expression that should return True/False
    vs a value expression that should return the actual value.
    
    Args:
        node: AST node to analyze
        
    Returns:
        True if the expression should return a boolean, False if it should return actual value
    """
    if isinstance(node, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
        # Comparison operations (=, <, >, IN, etc.), boolean operations (AND, OR), 
        # or unary operations (NOT) should return boolean
        return True
    elif isinstance(node, ast.IfExp):
        # Conditional expressions (CASE WHEN) should return boolean if both branches are boolean
        return _is_boolean_expression(node.body) and _is_boolean_expression(node.orelse)
    elif isinstance(node, ast.Call):
        # Function calls - need to check the function name
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.upper()
            # Navigation functions and CLASSIFIER should return actual values
            if func_name in ('CLASSIFIER', 'PREV', 'NEXT', 'FIRST', 'LAST'):
                return False
            # Boolean functions should return boolean
            elif func_name in ('EXISTS', 'IS_NULL', 'IS_NOT_NULL'):
                return True
        # Default for unknown functions: return boolean for safety
        return True
    elif isinstance(node, (ast.Name, ast.Attribute, ast.Constant)):
        # Simple values should return their actual value
        return False
    else:
        # For unknown node types, default to boolean for safety
        return True