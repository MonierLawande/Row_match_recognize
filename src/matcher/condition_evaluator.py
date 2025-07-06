# src/matcher/condition_evaluator.py
"""
Production-ready condition evaluator for SQL:2016 row pattern matching.

This module implements comprehensive condition evaluation with full support for:
- SQL:2016 pattern matching semantics
- Navigation functions using centralized navigation engine (FIRST, LAST, PREV, NEXT)
- Pattern variable references and subset variables
- Mathematical and utility functions
- Advanced error handling and validation
- Performance optimization with caching

Navigation Functions:
- All navigation function implementations have been moved to the centralized 
  src.matcher.navigation_functions engine for better maintainability.
- This module now delegates navigation calls to the centralized engine.

Refactored to eliminate duplication and improve maintainability.

Author: Pattern Matching Engine Team
Version: 3.0.0
"""

import ast
import operator
import re
import time
import threading
import pandas as pd
from typing import Dict, Any, Optional, Callable, List, Union, Tuple, Set
from dataclasses import dataclass

from src.matcher.row_context import RowContext
from src.matcher.evaluation_utils import (
    EvaluationMode, ValidationError, ExpressionValidationError,
    validate_expression_length, validate_recursion_depth,
    is_null, safe_compare, is_table_prefix, MATH_FUNCTIONS, 
    evaluate_math_function, get_evaluation_metrics
)
from src.matcher.navigation_functions import get_navigation_engine
from src.utils.logging_config import get_logger, PerformanceTimer

# Module logger
logger = get_logger(__name__)

# Define the type for condition functions
ConditionFn = Callable[[Dict[str, Any], RowContext], bool]

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
        
        # Initialize navigation engine
        from src.matcher.navigation_functions import get_navigation_engine
        self.navigation_engine = get_navigation_engine()
        
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
            return lambda col, steps=1: self._get_navigation_value(node.id, col, 'PREV', steps)
        elif node.id.upper() == "NEXT":
            return lambda col, steps=1: self._get_navigation_value(node.id, col, 'NEXT', steps)
        elif node.id.upper() == "FIRST":
            return lambda var, col, occ=0: self._get_navigation_value(var, col, 'FIRST', occ)
        elif node.id.upper() == "LAST":
            return lambda var, col, occ=0: self._get_navigation_value(var, col, 'LAST', occ)
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
            if func_name == "__IS_NULL":
                args = [self.visit(arg) for arg in node.args]
                if len(args) == 1:
                    return is_null(args[0])
                else:
                    raise ValueError("__is_null function requires exactly one argument")
            
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
        raise ValueError(f"Function {func} not callable")
    
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
            # For nested navigation, use the centralized nested navigation evaluator
            navigation_expr = self._build_navigation_expr(node)
            
            # Use the new centralized nested navigation function
            from .navigation_functions import evaluate_nested_navigation
            result = evaluate_nested_navigation(
                navigation_expr, 
                self.context, 
                self.context.current_idx
            )
            
            return result
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
                        return self._get_navigation_value(None, column, func_name, steps)
                    else:
                        # Logical navigation: use pattern match timeline
                        return self._get_navigation_value(None, column, func_name, steps)
                else:
                    # Use variable-aware navigation for FIRST/LAST
                    return self._get_navigation_value(var_name, column, func_name, steps)
                    
            elif isinstance(first_arg, ast.Attribute) and isinstance(first_arg.value, ast.Constant):
                # Pattern: NEXT("b".value) - quoted variable.column format
                var_name = f'"{first_arg.value.value}"'  # Preserve quotes for consistency
                column = first_arg.attr
                
                if func_name in ("PREV", "NEXT"):
                    # Context-aware navigation: physical for DEFINE, logical for MEASURES
                    if self.evaluation_mode == 'DEFINE':
                        return self._get_navigation_value(None, column, func_name, steps)
                    else:
                        return self._get_navigation_value(None, column, func_name, steps)
                else:
                    return self._get_navigation_value(var_name, column, func_name, steps)
                    
            elif isinstance(first_arg, ast.Name):
                # Pattern: NEXT(column) - simple column format
                column = first_arg.id
                
                if func_name in ("PREV", "NEXT"):
                    # Context-aware navigation: physical for DEFINE, logical for MEASURES
                    if self.evaluation_mode == 'DEFINE':
                        return self._get_navigation_value(None, column, func_name, steps)
                    else:
                        return self._get_navigation_value(None, column, func_name, steps)
                else:
                    return self._get_navigation_value(None, column, func_name, steps)
                    
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
                                return self._get_navigation_value(None, column, func_name, steps)
                            else:
                                return self._get_navigation_value(None, column, func_name, steps)
                        else:
                            return self._get_navigation_value(None, column, func_name, steps)
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
        from .navigation_functions import NavigationResult
        
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
            
            # Extract values from NavigationResult objects
            if isinstance(left, NavigationResult):
                if not left.success:
                    logger.warning(f"Left operand navigation failed: {left.error}")
                    return None
                left = left.value
            
            if isinstance(right, NavigationResult):
                if not right.success:
                    logger.warning(f"Right operand navigation failed: {right.error}")
                    return None
                right = right.value
            
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



    def _get_navigation_value(self, var_name, column, nav_type, steps=1):
        """
        Wrapper for centralized navigation engine.
        
        Args:
            var_name: Variable name or function name
            column: Column name to retrieve
            nav_type: Navigation type ('PREV', 'NEXT', 'FIRST', 'LAST')
            steps: Number of steps to navigate (for PREV/NEXT)
            
        Returns:
            The value at the navigated position or None if navigation is invalid
        """
        try:
            # Create navigation expression
            if var_name:
                expr = f"{nav_type}({var_name}.{column}{', ' + str(steps) if steps != 1 else ''})"
            else:
                expr = f"{nav_type}({column}{', ' + str(steps) if steps != 1 else ''})"
            
            # Determine navigation mode based on function type and evaluation context
            from .navigation_functions import NavigationMode
            
            # CRITICAL FIX: For FIRST/LAST functions with pattern variables, always use logical navigation
            # For PREV/NEXT, use physical navigation in DEFINE mode, logical in MEASURES mode
            if nav_type in ('FIRST', 'LAST') and var_name:
                # FIRST/LAST with pattern variables always use logical navigation
                mode = NavigationMode.LOGICAL
            elif nav_type in ('PREV', 'NEXT'):
                # PREV/NEXT use mode based on evaluation context
                if self.evaluation_mode == 'DEFINE':
                    mode = NavigationMode.PHYSICAL
                else:  # MEASURES
                    mode = NavigationMode.LOGICAL
            else:
                # Default fallback
                if self.evaluation_mode == 'DEFINE':
                    mode = NavigationMode.PHYSICAL
                else:  # MEASURES
                    mode = NavigationMode.LOGICAL
            
            # Use the centralized navigation engine
            result = self.navigation_engine.evaluate_navigation_expression(
                expr, self.context, self.context.current_idx, mode
            )
            
            # Extract the value from NavigationResult
            if result and result.success:
                return result.value
            else:
                return None
            
        except Exception as e:
            logger.error(f"Navigation function evaluation error: {e}")
            return None

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
            node: AST Tuple node representing a tuple literal
            
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
            node: AST List node representing a list literal
            
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


# Note: All navigation function evaluation is now handled by the centralized
# navigation engine in src.matcher.navigation_functions


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
        
        # CRITICAL FIX: Clean up multiline conditions for Python parsing
        # Remove line breaks and normalize whitespace that can cause syntax errors
        python_condition = ' '.join(python_condition.split())
        
        # Debug logging
        if "AND" in condition_str.upper():
            logger.debug(f"[CONDITION_DEBUG] Original: '{condition_str}' -> Python: '{python_condition}'")
        
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
        # Log the error with the converted Python condition for better debugging
        logger.error(f"Syntax error in converted Python condition '{python_condition}': {e}")
        logger.error(f"Original SQL condition was: '{condition_str}'")
        return lambda row, ctx: False
    except Exception as e:
        # Log the error and return a function that always returns False
        logger.error(f"Error compiling condition '{condition_str}': {e}")
        return lambda row, ctx: False


def _sql_to_python_condition(condition_str: str) -> str:
    """
    Convert SQL syntax to Python syntax for condition evaluation.
    
    This function handles common SQL-to-Python conversions needed for 
    row pattern matching conditions.
    
    Args:
        condition_str: SQL condition string
        
    Returns:
        Python-compatible condition string
    """
    if not condition_str:
        return ""
    
    # Basic SQL to Python conversions
    python_condition = condition_str
    
    # Handle SQL NULL comparisons first - convert to function calls
    # For pandas compatibility, we need to handle both None and NaN
    # Convert IS NULL to a special function call that checks for both None and NaN
    python_condition = re.sub(r'(\w+(?:\.\w+)?)\s+IS\s+NOT\s+NULL\b', r'not __is_null(\1)', python_condition, flags=re.IGNORECASE)
    python_condition = re.sub(r'(\w+(?:\.\w+)?)\s+IS\s+NULL\b', r'__is_null(\1)', python_condition, flags=re.IGNORECASE)
    
    # Handle SQL BETWEEN first (before AND/OR replacement)
    # value BETWEEN a AND b -> (value >= a and value <= b)
    between_pattern = r'(\w+(?:\.\w+)?)\s+BETWEEN\s+(\d+(?:\.\d+)?)\s+AND\s+(\d+(?:\.\d+)?)'
    python_condition = re.sub(between_pattern, r'(\1 >= \2 and \1 <= \3)', python_condition, flags=re.IGNORECASE)
    
    # Handle SQL CASE statements - support multiple WHEN clauses
    python_condition = _convert_case_expression(python_condition)
    
    # Handle SQL IN and NOT IN predicates - convert to Python syntax
    # Convert "column IN ('a', 'b', 'c')" to "column in ('a', 'b', 'c')"
    # Convert "column NOT IN ('a', 'b', 'c')" to "column not in ('a', 'b', 'c')"
    python_condition = re.sub(r'\bNOT\s+IN\b', ' not in ', python_condition, flags=re.IGNORECASE)
    python_condition = re.sub(r'\bIN\b', ' in ', python_condition, flags=re.IGNORECASE)
    
    # Replace SQL inequality operators first (more specific patterns)
    python_condition = re.sub(r'\s*<>\s*', ' != ', python_condition)
    python_condition = re.sub(r'(?<![<>=!])\s*!=\s*', ' != ', python_condition)  # Don't match if already part of another operator
    
    # Replace SQL equality operator (be careful not to affect >=, <=, !=, <>)
    python_condition = re.sub(r'(?<![<>=!])\s*=\s*(?![=])', ' == ', python_condition)
    
    # Handle SQL AND/OR - ensure we don't break existing 'and' keywords
    python_condition = re.sub(r'\bAND\b', ' and ', python_condition, flags=re.IGNORECASE)
    python_condition = re.sub(r'\bOR\b', ' or ', python_condition, flags=re.IGNORECASE)  
    python_condition = re.sub(r'\bNOT\b', ' not ', python_condition, flags=re.IGNORECASE)
    
    # CRITICAL FIX: Handle string literal quote consistency - ensure we use double quotes to avoid conflicts
    # Convert single-quoted string literals to double-quoted ones to avoid syntax issues
    # This prevents syntax errors when the condition is embedded in Python eval() calls
    python_condition = re.sub(r"'([^']*)'", r'"\1"', python_condition)
    
    # ADDITIONAL FIX: Clean up any remaining whitespace issues that could cause parsing errors
    # Normalize whitespace around operators and keywords
    python_condition = re.sub(r'\s+', ' ', python_condition).strip()
    
    return python_condition


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
                
            # Find PREV(var) references
            if f"PREV({ref_var}" in condition:
                # Ensure the referenced variable appears before this one in the pattern
                var_idx = pattern_variables.index(var)
                ref_idx = pattern_variables.index(ref_var)
                
                if ref_idx >= var_idx:
                    logger.error(f"Invalid PREV({ref_var}) reference in condition for {var}: "
                               f"{ref_var} does not appear before {var} in the pattern")
                    return False
            
            # Find NEXT(var) references
            if f"NEXT({ref_var}" in condition:
                # Ensure the referenced variable appears after this one in the pattern
                var_idx = pattern_variables.index(var)
                ref_idx = pattern_variables.index(ref_var)
                
                if ref_idx <= var_idx:
                    logger.error(f"Invalid NEXT({ref_var}) reference in condition for {var}: "
                               f"{ref_var} does not appear after {var} in the pattern")
                    return False
    
    # If all checks pass
    return True

def _is_boolean_expression(node: ast.AST) -> bool:
    """
    Determine if an AST node represents a boolean expression.
    
    Args:
        node: AST node to check
        
    Returns:
        True if the node represents a boolean expression, False otherwise
    """
    # Comparison operators always return boolean
    if isinstance(node, ast.Compare):
        return True
    
    # Boolean operations always return boolean
    if isinstance(node, ast.BoolOp):
        return True
    
    # Unary not operation returns boolean
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return True
    
    # Function calls that typically return boolean
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        func_name = node.func.id.upper()
        # Mathematical comparison functions
        if func_name in ('ISNAN', 'ISINF', 'ISFINITE'):
            return True
        # NULL checking functions
        elif func_name in ('IS_NULL', '_IS_NULL', 'ISNULL'):
            return True
        elif func_name in ('EXISTS', 'IS_NULL', 'IS_NOT_NULL'):
            return True
    
    # For unknown node types, default to boolean for safety
    return True

def _convert_case_expression(condition_str: str) -> str:
    """
    Convert SQL CASE expressions to Python syntax with support for multiple WHEN clauses.
    
    Handles both simple and complex CASE expressions:
    - CASE WHEN condition THEN value ELSE value END
    - CASE WHEN condition1 THEN value1 WHEN condition2 THEN value2 ELSE value3 END
    
    Args:
        condition_str: SQL condition string that may contain CASE expressions
        
    Returns:
        Python-compatible condition string
    """
    # Pattern to match CASE expressions with multiple WHEN clauses
    case_pattern = r'CASE\s+(.*?)\s+END'
    
    def convert_single_case(match):
        case_body = match.group(1).strip()
        
        # Split the case body into WHEN/THEN pairs and ELSE clause
        parts = []
        current_part = ""
        in_when = False
        paren_count = 0
        
        tokens = case_body.split()
        i = 0
        
        while i < len(tokens):
            token = tokens[i].upper()
            
            if token == 'WHEN':
                if current_part.strip():
                    parts.append(current_part.strip())
                current_part = ""
                in_when = True
                i += 1
                continue
            elif token == 'THEN':
                if in_when:
                    # Find the condition (everything between WHEN and THEN)
                    condition_tokens = []
                    j = i + 1
                    while j < len(tokens) and tokens[j].upper() != 'WHEN' and tokens[j].upper() != 'ELSE':
                        condition_tokens.append(tokens[j])
                        j += 1
                    
                    condition = " ".join(condition_tokens) if condition_tokens else ""
                    parts.append(f"WHEN {current_part} THEN {condition}")
                    current_part = ""
                    in_when = False
                    i = j - 1
                i += 1
                continue
            elif token == 'ELSE':
                if current_part.strip():
                    parts.append(current_part.strip())
                # Get everything after ELSE
                else_tokens = tokens[i + 1:]
                parts.append(f"ELSE {' '.join(else_tokens)}")
                break
            else:
                current_part += " " + tokens[i]
                i += 1
        
        if current_part.strip():
            parts.append(current_part.strip())
        
        # Now convert the parts to Python syntax
        if len(parts) == 0:
            return "None"
        
        # Build the Python expression from right to left
        result = None
        
        # Find the ELSE clause first
        else_value = "None"
        when_clauses = []
        
        for part in parts:
            if part.startswith('ELSE '):
                else_value = part[5:].strip()
            elif part.startswith('WHEN '):
                # Parse "WHEN condition THEN value"
                when_part = part[5:].strip()  # Remove "WHEN "
                if ' THEN ' in when_part:
                    condition, value = when_part.split(' THEN ', 1)
                    when_clauses.append((condition.strip(), value.strip()))
        
        # Build the nested conditional expression
        if not when_clauses:
            return else_value
        
        # Build from right to left: (value1 if condition1 else (value2 if condition2 else else_value))
        result = else_value
        for condition, value in reversed(when_clauses):
            result = f"({value} if {condition} else {result})"
        
        return result
    
    # Apply the conversion to all CASE expressions in the string
    return re.sub(case_pattern, convert_single_case, condition_str, flags=re.IGNORECASE | re.DOTALL)
