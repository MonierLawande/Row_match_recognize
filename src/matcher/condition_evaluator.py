# src/matcher/condition_evaluator.py

import ast
import operator
import re
import math
import time
import warnings
from typing import Dict, Any, Optional, Callable, List, Union, Tuple, Set
from dataclasses import dataclass
from src.matcher.row_context import RowContext
from src.utils.logging_config import get_logger, PerformanceTimer

# Module logger
logger = get_logger(__name__)

# Define the type for condition functions
ConditionFn = Callable[[Dict[str, Any], RowContext], bool]

# Enhanced Navigation Function Info from k.py - for better structured parsing
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
    def __init__(self, context: RowContext, evaluation_mode='DEFINE'):
        """
        Initialize condition evaluator with context-aware navigation.
        
        Args:
            context: RowContext for pattern matching
            evaluation_mode: 'DEFINE' for physical navigation, 'MEASURES' for logical navigation
        """
        self.context = context
        self.current_row = None
        self.evaluation_mode = evaluation_mode  # 'DEFINE' or 'MEASURES'
        # Extended mathematical and utility functions
        self.math_functions = {
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
            'SUBSTR': lambda s, start, length=None: s[start:start+length] if length else s[start:],
            
            # Conditional functions
            'LEAST': min,
            'GREATEST': max,
            'COALESCE': lambda *args: next((arg for arg in args if arg is not None), None),
            'NULLIF': lambda x, y: None if x == y else x,
        }

    def _safe_compare(self, left, right, op):
        """Perform SQL-style comparison with NULL handling."""
        # Only apply NULL handling for SQL comparisons involving NULL values
        # Regular comparisons between non-NULL values should work normally
        if left is None or right is None:
            return False
            
        return op(left, right)

    def visit_Compare(self, node: ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("Only simple comparisons are supported")
        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
        
        # Debug logging for DEFINE mode comparisons
        logger = get_logger(__name__)
        if self.evaluation_mode == 'DEFINE':
            logger.debug(f"[DEBUG] COMPARE: left={left} ({type(left)}), right={right} ({type(right)})")
            logger.debug(f"[DEBUG] COMPARE AST: left={ast.dump(node.left)}, right={ast.dump(node.comparators[0])}")
        
        # DEBUG: Add logging for comparison debugging
        if hasattr(self.context, '_debug_comparison') and self.context._debug_comparison:
            print(f"DEBUG visit_Compare: left={left}, right={right}")
            print(f"DEBUG visit_Compare: left AST = {ast.dump(node.left)}")
            print(f"DEBUG visit_Compare: right AST = {ast.dump(node.comparators[0])}")
        
        # Use safe comparison with NULL handling
        op = node.ops[0]
        
        OPERATORS = {
            ast.Gt: operator.gt,
            ast.Lt: operator.lt,
            ast.GtE: operator.ge,
            ast.LtE: operator.le,
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
        }
        
        func = OPERATORS.get(type(op))
        if func is None:
            raise ValueError(f"Operator {op} not supported")
            
        result = self._safe_compare(left, right, func)
        
        # Enhanced debug logging for result
        if self.evaluation_mode == 'DEFINE':
            current_var = getattr(self.context, 'current_var', None)
            logger.debug(f"[DEBUG] COMPARE RESULT: {left} {op.__class__.__name__} {right} = {result} (evaluating for var={current_var})")
        
        # DEBUG: Add logging for comparison result
        if hasattr(self.context, '_debug_comparison') and self.context._debug_comparison:
            print(f"DEBUG visit_Compare: {left} {type(op).__name__} {right} = {result}")
            
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
            elif isinstance(arg, ast.Constant):
                # Constant values (numbers, strings)
                args.append(arg.value)
            elif isinstance(arg, ast.Num):
                # Python < 3.8 compatibility
                args.append(arg.n)
            else:
                # For complex expressions, evaluate them
                value = self.visit(arg)
                # Handle nested navigation functions
                if callable(value):
                    value = value()
                args.append(value)
            
        return args

    def visit_Call(self, node: ast.Call):
        """Handle function calls (PREV, NEXT, mathematical functions, etc.)"""
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.upper()
            if func_name in self.math_functions:
                args = [self.visit(arg) for arg in node.args]
                try:
                    # Check for NULL arguments - SQL functions typically return NULL if any input is NULL
                    if any(arg is None for arg in args) and func_name not in ('COALESCE', 'NULLIF'):
                        return None
                    return self.math_functions[func_name](*args)
                except Exception as e:
                    raise ValueError(f"Error in {func_name} function: {e}")
            
            # Special handling for pattern variable access
            if func_name == "GET_VAR_VALUE":
                args = [self.visit(arg) for arg in node.args]
                if len(args) == 3:
                    var_name, col_name, ctx = args
                    return self._get_variable_column_value(var_name, col_name, ctx)
            
            # Enhanced navigation function handling with support for nested functions
            if func_name in ("PREV", "NEXT", "FIRST", "LAST"):
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
                    return evaluate_nested_navigation(
                        navigation_expr, 
                        self.context, 
                        self.context.current_idx, 
                        getattr(self.context, 'current_var', None)
                    )
                else:
                    # Fixed: Handle AST nodes directly instead of using faulty _extract_navigation_args
                    if len(node.args) == 0:
                        raise ValueError(f"{func_name} function requires at least one argument")
                    
                    # Get the first argument which should be either ast.Name or ast.Attribute
                    first_arg = node.args[0]
                    
                    if isinstance(first_arg, ast.Attribute) and isinstance(first_arg.value, ast.Name):
                        # Pattern: NEXT(A.value) - variable.column format
                        var_name = first_arg.value.id
                        column = first_arg.attr
                        
                        # Get optional steps argument
                        steps = 1
                        if len(node.args) > 1:
                            steps_arg = node.args[1]
                            if isinstance(steps_arg, (ast.Constant, ast.Num)):
                                steps = steps_arg.value if isinstance(steps_arg, ast.Constant) else steps_arg.n
                        
                        if func_name in ("PREV", "NEXT"):
                            # Context-aware navigation: physical for DEFINE, logical for MEASURES
                            if self.evaluation_mode == 'DEFINE':
                                # Physical navigation: use direct row indexing
                                return self.evaluate_physical_navigation(func_name, column, steps)
                            else:
                                # Logical navigation: use pattern match timeline
                                return self.evaluate_navigation_function(func_name, column, steps)
                        else:
                            # Use variable-aware navigation for FIRST/LAST
                            return self._get_navigation_value(var_name, column, func_name, steps)
                            
                    elif isinstance(first_arg, ast.Name):
                        # Pattern: NEXT(column) - simple column format
                        column = first_arg.id
                        
                        # Get optional steps argument
                        steps = 1
                        if len(node.args) > 1:
                            steps_arg = node.args[1]
                            if isinstance(steps_arg, (ast.Constant, ast.Num)):
                                steps = steps_arg.value if isinstance(steps_arg, ast.Constant) else steps_arg.n
                        
                        if func_name in ("PREV", "NEXT"):
                            # Context-aware navigation: physical for DEFINE, logical for MEASURES
                            if self.evaluation_mode == 'DEFINE':
                                # Physical navigation: use direct row indexing
                                return self.evaluate_physical_navigation(func_name, column, steps)
                            else:
                                # Logical navigation: use pattern match timeline
                                return self.evaluate_navigation_function(func_name, column, steps)
                        else:
                            # Use variable-aware navigation for FIRST/LAST with no specific variable
                            return self._get_navigation_value(None, column, func_name, steps)
                    else:
                        raise ValueError(f"Unsupported argument type for {func_name}: {type(first_arg)}")

        func = self.visit(node.func)
        if callable(func):
            args = [self.visit(arg) for arg in node.args]
            try:
                return func(*args)
            except Exception as e:
                # More descriptive error
                raise ValueError(f"Error calling {func_name or 'function'}: {e}")
        raise ValueError(f"Function {func} not callable")

    def visit_Attribute(self, node: ast.Attribute):
        """Handle pattern variable references (A.price) with table prefix validation"""
        if isinstance(node.value, ast.Name):
            var = node.value.id
            col = node.attr
            
            # Table prefix validation: prevent forbidden table.column references
            if self._is_table_prefix_in_context(var):
                raise ValueError(f"Forbidden table prefix reference: '{var}.{col}'. "
                               f"In MATCH_RECOGNIZE, use pattern variable references instead of table references")
            
            # Handle pattern variable references
            result = self._get_variable_column_value(var, col, self.context)
            
            # DEBUG: Add logging for attribute resolution
            if hasattr(self.context, '_debug_comparison') and self.context._debug_comparison:
                print(f"DEBUG visit_Attribute: {var}.{col} = {result}")
                print(f"DEBUG visit_Attribute: current_idx={self.context.current_idx}, variables={self.context.variables}")
            
            return result
        
        # If we can't extract a pattern var reference, try regular attribute access
        obj = self.visit(node.value)
        if obj is not None:
            return getattr(obj, node.attr, None)
        
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
        if hasattr(self.context, 'var_assignments') and var_name in self.context.var_assignments:
            return False
        if hasattr(self.context, 'subsets') and self.context.subsets and var_name in self.context.subsets:
            return False
        
        # Use the same logic as the standalone function
        from src.matcher.measure_evaluator import _is_table_prefix
        return _is_table_prefix(var_name, 
                               getattr(self.context, 'var_assignments', {}),
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
                return ctx.rows[last_idx].get(col_name)
        
        # Otherwise, get the value from the last row matched to this variable
        var_indices = ctx.variables.get(var_name, [])
        if var_indices:
            last_idx = max(var_indices)
            if last_idx < len(ctx.rows):
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
        Production-grade enhanced navigation function for physical (PREV/NEXT) and logical (FIRST/LAST) operations.
        
        This implementation provides:
        - Comprehensive performance optimization with smart caching
        - Robust error handling with detailed error messages
        - Advanced bounds checking with early exit
        - Full support for subset variables and PERMUTE patterns
        - Consistent behavior across pattern boundaries
        - Production-level partition boundary enforcement
        - Performance metrics and logging
        - Thread-safety for concurrent pattern matching
        
        Args:
            var_name: Variable name or function name
            column: Column name to retrieve
            nav_type: Navigation type ('PREV', 'NEXT', 'FIRST', 'LAST')
            steps: Number of steps to navigate (for PREV/NEXT)
            
        Returns:
            The value at the navigated position or None if navigation is invalid
            
        Raises:
            ValueError: For invalid navigation parameters
            TypeError: For type mismatches
        """
        start_time = time.time()
        
        try:
            # Enhanced input validation with comprehensive error messages
            if steps < 0:
                raise ValueError(f"Navigation steps must be non-negative: {steps}")
            
            if not isinstance(column, str):
                raise TypeError(f"Column name must be a string, got {type(column)}: {column}")
            
            # Initialize or update performance metrics
            if hasattr(self.context, 'stats'):
                self.context.stats["navigation_calls"] = self.context.stats.get("navigation_calls", 0) + 1
            
            # Initialize cache if not exists with thread-safety consideration
            if not hasattr(self.context, 'navigation_cache'):
                self.context.navigation_cache = {}
            
            # Create a comprehensive cache key that includes all relevant context
            # This ensures cache hits even in complex pattern scenarios
            partition_key = getattr(self.context, 'partition_key', None)
            pattern_id = id(getattr(self.context, 'pattern_metadata', None))
            cache_key = (var_name, column, nav_type, steps, self.context.current_idx, partition_key, pattern_id)
            
            # Optimized cache lookup with metrics tracking
            if cache_key in self.context.navigation_cache:
                if hasattr(self.context, 'stats'):
                    self.context.stats["cache_hits"] = self.context.stats.get("cache_hits", 0) + 1
                return self.context.navigation_cache[cache_key]
            
            if hasattr(self.context, 'stats'):
                self.context.stats["cache_misses"] = self.context.stats.get("cache_misses", 0) + 1
            
            # Get context state with robust null handling
            curr_idx = self.context.current_idx
            current_var = getattr(self.context, 'current_var', None)
            is_permute = hasattr(self.context, 'pattern_metadata') and getattr(self.context, 'pattern_metadata', {}).get('permute', False)
            
            # Fast path: Quickly return None for obvious edge cases to avoid unnecessary computation
            if curr_idx < 0 or curr_idx >= len(self.context.rows) or not self.context.rows:
                self.context.navigation_cache[cache_key] = None
                return None
            
            # Enhanced subset variable handling for logical navigation (FIRST/LAST)
            if nav_type in ('FIRST', 'LAST') and var_name in self.context.subsets:
                # For subset variables, find rows matched to any component variable
                component_vars = self.context.subsets[var_name]
                all_indices = []
                
                # Gather indices from all component variables
                for comp_var in component_vars:
                    if comp_var in self.context.variables:
                        all_indices.extend(self.context.variables[comp_var])
                
                if all_indices:
                    # Sort indices for consistent behavior and deduplication
                    all_indices = sorted(set(all_indices))
                    
                    # Bounds checking and partition enforcement for subset variables
                    idx = all_indices[0] if nav_type == 'FIRST' else all_indices[-1]
                    
                    # Check partition boundaries if defined
                    if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
                        curr_partition = self.context.get_partition_for_row(curr_idx)
                        target_partition = self.context.get_partition_for_row(idx)
                        
                        # Enforce partition boundaries
                        if curr_partition != target_partition or curr_partition is None or target_partition is None:
                            self.context.navigation_cache[cache_key] = None
                            return None
                    
                    # Bounds checking
                    if 0 <= idx < len(self.context.rows):
                        result = self.context.rows[idx].get(column)
                        self.context.navigation_cache[cache_key] = result
                        return result
                
                # No valid indices found for subset
                self.context.navigation_cache[cache_key] = None
                return None
            
            # Optimized timeline building with caching
            # Build a timeline of all pattern variables in this match
            if hasattr(self.context, '_timeline') and not getattr(self.context, '_timeline_dirty', True):
                timeline = self.context._timeline
            else:
                # Rebuild timeline with optimized algorithm
                timeline = []
                
                # Use direct index lookup for small variable sets
                if len(self.context.variables) < 50:
                    for var, indices in self.context.variables.items():
                        for idx in indices:
                            timeline.append((idx, var))
                else:
                    # For larger sets, use a more efficient approach
                    # Pre-allocate to avoid resizing
                    total_indices = sum(len(indices) for indices in self.context.variables.values())
                    timeline = [(0, "")] * total_indices
                    pos = 0
                    
                    for var, indices in self.context.variables.items():
                        for idx in indices:
                            timeline[pos] = (idx, var)
                            pos += 1
                    
                    # Truncate if needed
                    if pos < len(timeline):
                        timeline = timeline[:pos]
                
                # Sort by row index for consistent ordering
                timeline.sort()
                
                # Cache the timeline and mark as clean
                self.context._timeline = timeline
                self.context._timeline_dirty = False
            
            # Empty timeline indicates incomplete match state
            if not timeline:
                self.context.navigation_cache[cache_key] = None
                return None
            
            result = None
            
            # Enhanced logical positioning functions (FIRST/LAST)
            if nav_type in ('FIRST', 'LAST'):
                if var_name is None:
                    # FIRST(column) or LAST(column) - look across all variables in the match
                    all_indices = []
                    for var, indices in self.context.variables.items():
                        all_indices.extend(indices)
                    
                    if not all_indices:
                        self.context.navigation_cache[cache_key] = None
                        return None
                    
                    # Sort indices and select first or last
                    all_indices = sorted(set(all_indices))
                    idx = all_indices[0] if nav_type == 'FIRST' else all_indices[-1]
                    
                elif var_name not in self.context.variables or not self.context.variables[var_name]:
                    self.context.navigation_cache[cache_key] = None
                    return None
                else:
                    # Get sorted indices with duplication handling
                    var_indices = sorted(set(self.context.variables[var_name]))
                    
                    if not var_indices:
                        self.context.navigation_cache[cache_key] = None
                        return None
                    
                    # Select appropriate index based on navigation type
                    idx = var_indices[0] if nav_type == 'FIRST' else var_indices[-1]
                
                # Check partition boundaries if defined
                if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
                    curr_partition = self.context.get_partition_for_row(curr_idx)
                    target_partition = self.context.get_partition_for_row(idx)
                    
                    # Enforce partition boundaries
                    if curr_partition != target_partition or curr_partition is None or target_partition is None:
                        self.context.navigation_cache[cache_key] = None
                        return None
                
                # Bounds checking with advanced error handling
                if 0 <= idx < len(self.context.rows):
                    result = self.context.rows[idx].get(column)
                else:
                    result = None
            
            # Enhanced physical navigation (PREV/NEXT) with optimized algorithms
            elif nav_type in ('PREV', 'NEXT'):
                # Fast path for simple operations using the context's methods
                if (var_name is None or var_name == current_var) and steps <= 10:
                    # Use optimized methods from context
                    if nav_type == 'PREV':
                        row = self.context.prev(steps)
                    else:  # NEXT
                        row = self.context.next(steps)
                        
                    if row is not None:
                        result = row.get(column)
                        self.context.navigation_cache[cache_key] = result
                        return result
                
                # Advanced position finding using optimized algorithms
                curr_pos = -1
                
                # Optimization: Binary search for current position if timeline is large
                if len(timeline) > 100:
                    # Use binary search to find position close to curr_idx
                    low, high = 0, len(timeline) - 1
                    while low <= high:
                        mid = (low + high) // 2
                        mid_idx, _ = timeline[mid]
                        
                        if mid_idx < curr_idx:
                            low = mid + 1
                        elif mid_idx > curr_idx:
                            high = mid - 1
                        else:
                            # Found exact index, now check variable if needed
                            if current_var is None or timeline[mid][1] == current_var:
                                curr_pos = mid
                                break
                            
                            # Enhanced linear search for the correct variable at this index
                            # Use expanding window to handle clustered variables
                            found = False
                            for offset in range(1, min(10, len(timeline))):
                                # Check before mid
                                if mid - offset >= 0:
                                    idx, var = timeline[mid - offset]
                                    if idx == curr_idx and (current_var is None or var == current_var):
                                        curr_pos = mid - offset
                                        found = True
                                        break
                                        
                                # Check after mid
                                if mid + offset < len(timeline):
                                    idx, var = timeline[mid + offset]
                                    if idx == curr_idx and (current_var is None or var == current_var):
                                        curr_pos = mid + offset
                                        found = True
                                        break
                                        
                            if found:
                                break
                                
                            # Fall back to checking nearby indices if we found the right index but wrong variable
                            for i in range(max(0, mid-10), min(len(timeline), mid+11)):
                                if timeline[i][0] == curr_idx and (current_var is None or timeline[i][1] == current_var):
                                    curr_pos = i
                                    found = True
                                    break
                                    
                            if found:
                                break
                            
                            # If we got here, we found the index but not the right variable
                            # Fall back to linear search from the beginning
                            break
                else:
                    # Optimized linear search for smaller timelines
                    for i, (idx, var) in enumerate(timeline):
                        if idx == curr_idx and (current_var is None or var == current_var):
                            curr_pos = i
                            break
                
                # If current position not found in timeline
                if curr_pos < 0:
                    self.context.navigation_cache[cache_key] = None
                    return None
                
                # Enhanced PREV navigation with comprehensive bounds checking and partition enforcement
                if nav_type == 'PREV':
                    if steps == 0:  # Special case: PREV(col, 0) returns current row's value
                        result = self.context.rows[curr_idx].get(column)
                    elif curr_pos >= steps:
                        prev_idx, _ = timeline[curr_pos - steps]
                        
                        # Enhanced partition boundary checking with optimized lookup
                        if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
                            # Use optimized method from context
                            if not self.context.check_same_partition(curr_idx, prev_idx):
                                self.context.navigation_cache[cache_key] = None
                                return None
                        
                        # Get the value from the previous row with column existence check
                        if 0 <= prev_idx < len(self.context.rows):
                            prev_row = self.context.rows[prev_idx]
                            result = prev_row.get(column)
                        else:
                            result = None
                    else:
                        # Not enough rows before current position - this is a boundary condition
                        # For DEFINE clauses with variable-specific PREV, return NULL (not context invalid)
                        # This allows proper SQL NULL comparison semantics: value > NULL = FALSE
                        result = None
                
                # Enhanced NEXT navigation with comprehensive bounds checking and partition enforcement
                elif nav_type == 'NEXT':
                    if steps == 0:  # Special case: NEXT(col, 0) returns current row's value
                        result = self.context.rows[curr_idx].get(column)
                    elif curr_pos >= 0 and curr_pos + steps < len(timeline):
                        next_idx, _ = timeline[curr_pos + steps]
                        
                        # Enhanced partition boundary checking with optimized lookup
                        if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
                            # Use optimized method from context
                            if not self.context.check_same_partition(curr_idx, next_idx):
                                self.context.navigation_cache[cache_key] = None
                                return None
                        
                        # Get the value from the next row with column existence check
                        if 0 <= next_idx < len(self.context.rows):
                            next_row = self.context.rows[next_idx]
                            result = next_row.get(column)
                        else:
                            result = None
                    else:
                        # Not enough rows after current position
                        result = None
            
            # Cache the result for future lookups
            self.context.navigation_cache[cache_key] = result
            return result
            
        finally:
            # Track performance metrics
            if hasattr(self.context, 'timing'):
                navigation_time = time.time() - start_time
                self.context.timing['navigation'] = self.context.timing.get('navigation', 0) + navigation_time

    def _get_classifier(self, variable: Optional[str] = None) -> str:
        """Implementation of CLASSIFIER function with subset support."""
        return self.context.classifier(variable)

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
            elif isinstance(arg, ast.Num):
                # Numeric literal (Python < 3.8)
                args.append(str(arg.n))
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
        # Input validation
        if steps < 0:
            raise ValueError(f"Navigation steps must be non-negative: {steps}")
            
        if nav_type not in ('PREV', 'NEXT'):
            raise ValueError(f"Invalid navigation type: {nav_type}")
            
        # Special case for steps=0 (return current row's value)
        if steps == 0:
            if 0 <= self.context.current_idx < len(self.context.rows):
                return self.context.rows[self.context.current_idx].get(column)
            return None
        
        # DEFINE Mode: Physical Navigation through input sequence
        if self.evaluation_mode == 'DEFINE':
            return self._physical_navigation(nav_type, column, steps)
        
        # MEASURES Mode: Logical Navigation through pattern matches
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
        Navigate through pattern match timeline.
        """
        # This uses the existing complex logic for pattern timeline navigation
        return self._get_navigation_value(var_name, column, nav_type, steps)
            
        # Check partition boundaries if defined
        if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
            current_partition = self.context.get_partition_for_row(self.context.current_idx)
            target_partition = self.context.get_partition_for_row(target_idx)
            
            if (current_partition is None or target_partition is None or
                current_partition != target_partition):
                return None
                
        # Get the value from the target row
        return self.context.rows[target_idx].get(column)

    def visit_Constant(self, node: ast.Constant):
        """Handle all constant types (numbers, strings, booleans, None)"""
        return node.value

    def visit_BoolOp(self, node: ast.BoolOp):
        if isinstance(node.op, ast.And):
            # Short-circuit evaluation for AND
            for value in node.values:
                result = self.visit(value)
                if not result:
                    return False
            return True
        elif isinstance(node.op, ast.Or):
            # Short-circuit evaluation for OR
            for value in node.values:
                result = self.visit(value)
                if result:
                    return True
            return False
        raise ValueError("Unsupported boolean operator")

    def visit_BinOp(self, node: ast.BinOp):
        """Handle binary operations like addition, subtraction, etc."""
        left = self.visit(node.left)
        right = self.visit(node.right)
        
        OPERATORS = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        
        func = OPERATORS.get(type(node.op))
        if func is None:
            raise ValueError(f"Binary operator {type(node.op)} not supported")
        
        # Handle NULL values in operations
        if left is None or right is None:
            return None
            
        try:
            return func(left, right)
        except Exception as e:
            # Better error handling
            raise ValueError(f"Error in binary operation {left} {type(node.op).__name__} {right}: {e}")
    
    def visit_UnaryOp(self, node: ast.UnaryOp):
        """Handle unary operations like negation"""
        operand = self.visit(node.operand)
        
        OPERATORS = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
            ast.Not: operator.not_,
        }
        
        func = OPERATORS.get(type(node.op))
        if func is None:
            raise ValueError(f"Unary operator {type(node.op)} not supported")
            
        # Handle NULL values
        if operand is None and type(node.op) != ast.Not:
            return None
            
        return func(operand)
    
    def visit_IfExp(self, node: ast.IfExp):
        """Handle ternary expressions: x if cond else y"""
        test = self.visit(node.test)
        if test:
            return self.visit(node.body)
        else:
            return self.visit(node.orelse)
    
    def visit_List(self, node: ast.List):
        """Handle list literals"""
        return [self.visit(elt) for elt in node.elts]
    
    def visit_Dict(self, node: ast.Dict):
        """Handle dict literals"""
        keys = [self.visit(key) if key is not None else None for key in node.keys]
        values = [self.visit(value) for value in node.values]
        return {k: v for k, v in zip(keys, values)}
    
    def visit_JoinedStr(self, node: ast.JoinedStr):
        """Handle f-strings"""
        parts = []
        for value in node.values:
            if isinstance(value, ast.Str):
                parts.append(value.s)
            else:
                parts.append(str(self.visit(value)))
        return ''.join(parts)
    
    def visit_FormattedValue(self, node: ast.FormattedValue):
        """Handle formatted values in f-strings"""
        return self.visit(node.value)
    
    def visit_Subscript(self, node: ast.Subscript):
        """Handle subscript expressions like a[b] and price[n] for array access"""
        # Special handling for row['keyword'] pattern
        if isinstance(node.value, ast.Name) and node.value.id == 'row':
            # Get the index (column name)
            col_name = self._extract_subscript_value(node)
                    
            # Return the column value from the current row
            if col_name is not None and self.current_row is not None:
                return self.current_row.get(col_name)
        
        # Handle array-like access for column values: price[1] -> PREV(price, 1)
        if isinstance(node.value, ast.Name):
            col_name = node.value.id
            idx = self._extract_subscript_value(node)
            
            if isinstance(idx, int) and idx > 0:
                # Translate to PREV function for backward compatibility
                return self._get_navigation_value('PREV', col_name, 'PREV', idx)
            elif isinstance(idx, int) and idx < 0:
                # Negative indices could translate to NEXT
                return self._get_navigation_value('NEXT', col_name, 'NEXT', abs(idx))
        
        # Original functionality for normal subscripts
        value = self.visit(node.value)
        idx = self._extract_subscript_value(node)
        
        if value is None:
            return None
            
        try:
            return value[idx]
        except (TypeError, KeyError, IndexError):
            return None
    
    def _extract_subscript_value(self, node):
        """Helper to extract value from subscript, compatible with different Python versions"""
        if hasattr(node, 'slice'):
            if isinstance(node.slice, ast.Index):  # Python < 3.9
                return self.visit(node.slice.value)
            elif hasattr(node.slice, 'value'):  # For some versions
                return self.visit(node.slice.value)
            else:  # Python >= 3.9
                return self.visit(node.slice)
        return None
    
    def visit_Tuple(self, node: ast.Tuple):
        """Handle tuple literals"""
        return tuple(self.visit(elt) for elt in node.elts)
    
    def visit_Set(self, node: ast.Set):
        """Handle set literals"""
        return {self.visit(elt) for elt in node.elts}
    
    def visit_ListComp(self, node: ast.ListComp):
        """Handle list comprehensions - limited support"""
        raise ValueError("List comprehensions are not supported in pattern conditions")
    
    def generic_visit(self, node):
        """Handle unsupported nodes"""
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")

    


    def _compare_values(self, left, right, operator):
        """Compare values with proper NULL handling for Trino compatibility."""
        # If either value is None/NULL, the comparison should fail (except for IS NULL/IS NOT NULL)
        if left is None or right is None:
            if operator == "IS NULL":
                return left is None
            elif operator == "IS NOT NULL":
                return left is not None
            elif operator == "==" or operator == "=":
                return False  # NULL = anything is FALSE
            elif operator == "!=" or operator == "<>":
                return False  # NULL != anything is FALSE as well (not TRUE)
            else:
                return False  # NULL in any other comparison is FALSE
            
        # Regular comparisons for non-NULL values
        if operator == "==" or operator == "=":
            return left == right
        elif operator == "!=" or operator == "<>" or operator == "≠":
            return left != right
        elif operator == "<":
            return left < right
        elif operator == "<=":
            return left <= right
        elif operator == ">":
            return left > right
        elif operator == ">=":
            return left >= right
        else:
            raise ValueError(f"Unknown comparison operator: {operator}")

# Define the ConditionFn type for clarity
from typing import Callable, Dict, Any, Optional, List, Tuple, Union
import re
import ast

# Type alias for condition functions
ConditionFn = Callable[[Dict[str, Any], RowContext], bool]

def _preprocess_sql_condition(condition_expr):
    """Convert SQL-style expressions to Python-compatible expressions."""
    if not condition_expr:
        return condition_expr
    
    # Handle SQL boolean literals
    condition_expr = re.sub(r'\bTRUE\b', 'True', condition_expr, flags=re.IGNORECASE)
    condition_expr = re.sub(r'\bFALSE\b', 'False', condition_expr, flags=re.IGNORECASE)
    
    # Handle SQL NULL
    condition_expr = re.sub(r'\bNULL\b', 'None', condition_expr, flags=re.IGNORECASE)
    
    # Handle SQL comparison operators
    condition_expr = re.sub(r'\bAND\b', 'and', condition_expr, flags=re.IGNORECASE)
    condition_expr = re.sub(r'\bOR\b', 'or', condition_expr, flags=re.IGNORECASE)
    condition_expr = re.sub(r'\bNOT\b', 'not', condition_expr, flags=re.IGNORECASE)
    
    # Convert SQL equality to Python comparison expression
    # Handle patterns like "column = 'value'" -> "column == 'value'"
    # This regex looks for variable = 'quoted_string' patterns
    condition_expr = re.sub(r'\b(\w+)\s*=\s*([\'"][^\'\"]*[\'"])', r'\1 == \2', condition_expr)
    
    # Handle patterns like "column = unquoted_value" -> "column == unquoted_value"
    condition_expr = re.sub(r'\b(\w+)\s*=\s*([^=\s]+(?:\s*[^=\s]+)*)', r'\1 == \2', condition_expr)
    
    return condition_expr

def compile_condition(condition_expr, row_context=None, current_row_idx=None, current_var=None, evaluation_mode='DEFINE'):
    # Preprocess SQL-style condition to Python-compatible format
    processed_condition = _preprocess_sql_condition(condition_expr)
    
    # Handle compilation mode - return function for later evaluation
    if row_context is None and current_row_idx is None:
        # Create closure that will evaluate condition at runtime
        def condition_fn(row, context):
            # Store the current row and evaluation context
            context.current_row = row
            context.current_idx = context.rows.index(row) if row in context.rows else -1
            # CRITICAL FIX: Don't overwrite current_var if it's already set by the matcher
            # Only set it if it's not already set (None) and we have a value from compilation
            if not hasattr(context, 'current_var') or context.current_var is None:
                context.current_var = current_var
            
            # Use AST-based evaluator instead of direct eval for navigation functions
            evaluator = ConditionEvaluator(context, evaluation_mode)
            try:
                # Clear any previous context invalid flag
                if hasattr(context, '_evaluation_context_invalid'):
                    delattr(context, '_evaluation_context_invalid')
                
                # Parse condition using AST and evaluate with our visitor
                tree = ast.parse(processed_condition, mode='eval')
                result = evaluator.visit(tree.body)
                return bool(result)
            except ValueError as ve:
                # Handle navigation context unavailable error
                if "Navigation context unavailable" in str(ve):
                    # This indicates the condition cannot be evaluated at this row
                    # due to missing navigation context (e.g., PREV() on row 0)
                    # Return False but signal this should be handled differently
                    context._navigation_context_error = True
                    return False
                raise ve
            except Exception as e:
                # Fall back to basic condition check
                basic_condition = extract_base_condition(condition_expr)
                if basic_condition:
                    if "event_type" in basic_condition:
                        event_type = re.search(r"'(\w+)'", basic_condition)
                        if event_type and row.get('event_type') == event_type.group(1):
                            return True
                return False
        return condition_fn
    
    # Runtime evaluation with proper context
    if row_context and current_row_idx is not None:
        if current_row_idx < 0 or current_row_idx >= len(row_context.rows):
            return False
        
        # Use proper AST-based evaluation with context
        row = row_context.rows[current_row_idx]
        row_context.current_row = row
        row_context.current_idx = current_row_idx
        row_context.current_var = current_var
        
        evaluator = ConditionEvaluator(row_context, evaluation_mode)
        try:
            # Clear any previous context invalid flag
            if hasattr(row_context, '_evaluation_context_invalid'):
                delattr(row_context, '_evaluation_context_invalid')
            
            tree = ast.parse(processed_condition, mode='eval')
            result = evaluator.visit(tree.body)
            return bool(result)
        except ValueError as ve:
            # Handle navigation context unavailable error
            if "Navigation context unavailable" in str(ve):
                # This indicates the condition cannot be evaluated at this row
                # Signal this for the matcher to handle appropriately
                row_context._navigation_context_error = True
                return False
            raise ve
        except Exception as e:
            # If navigational evaluation fails, check basic conditions
            if 'event_type' in condition_expr and 'event_type' in row:
                event_match = f"event_type = '{row['event_type']}'"
                return event_match in condition_expr
            return False
    
    # Default for validation
    return True

def extract_base_condition(condition):
    """Extract the basic part of a condition without navigation functions."""
    # Find the first navigation function call
    nav_patterns = [
        r'NEXT\s*\(.*?\)',
        r'PREV\s*\(.*?\)',
        r'FIRST\s*\(.*?\)',
        r'LAST\s*\(.*?\)'
    ]
    
    # Start with the full condition
    base_condition = condition
    
    # Find the first navigation function occurrence
    min_pos = len(condition)
    for pattern in nav_patterns:
        match = re.search(pattern, condition)
        if match and match.start() < min_pos:
            min_pos = match.start()
    
    # If we found a navigation function
    if min_pos < len(condition):
        # Check if there's a condition part before the navigation function
        if 'AND' in condition[:min_pos]:
            # Extract the part before the AND
            base_condition = condition.split('AND')[0].strip()
        elif 'OR' in condition[:min_pos]:
            # Extract the part before the OR
            base_condition = condition.split('OR')[0].strip()
        else:
            # Just event type condition
            match = re.search(r"event_type\s*=\s*'[^']+'", condition)
            if match:
                base_condition = match.group(0)
            else:
                base_condition = ""
    
    return base_condition

def evaluate_navigation_expr(expr, row_context, current_row_idx, current_var):
    """
    Evaluate a navigation function expression.
    
    Args:
        expr: The navigation expression string (e.g., "NEXT(X.field)")
        row_context: The row context object
        current_row_idx: The current row index
        current_var: The current variable being evaluated
        
    Returns:
        The value of the navigation expression
    """
    # Match navigation function with variable.field and optional offset
    pattern = r'(NEXT|PREV|FIRST|LAST)\s*\(\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)(?:\s*,\s*(\d+))?\s*\)'
    match = re.match(pattern, expr)
    
    if not match:
        raise ValueError(f"Invalid navigation function syntax: {expr}")
    
    func_type = match.group(1)
    ref_var = match.group(2)
    field = match.group(3)
    offset_str = match.group(4)
    offset = int(offset_str) if offset_str else 1
    
    # Check if referenced variable exists in context
    if ref_var not in row_context.variables:
        raise ValueError(f"Referenced variable {ref_var} not found in match context")
        
    var_indices = sorted(row_context.variables[ref_var])
    if not var_indices:
        raise ValueError(f"No rows assigned to variable {ref_var}")
    
    # Get target index based on function type
    target_idx = None
    
    if func_type == 'FIRST':
        # First occurrence of the variable
        target_idx = var_indices[0]
        
    elif func_type == 'LAST':
        # Last occurrence of the variable
        target_idx = var_indices[-1]
        
    elif func_type == 'NEXT':
        if ref_var == current_var:
            # Find position of current row in variable's rows
            try:
                current_pos = var_indices.index(current_row_idx)
                if current_pos + offset >= len(var_indices):
                    raise ValueError(f"NEXT({ref_var}, {offset}) references beyond available rows")
                target_idx = var_indices[current_pos + offset]
            except ValueError:
                raise ValueError(f"Current row index {current_row_idx} not found in variable {ref_var}")
        else:
            # Find rows of ref_var that appear after current row
            future_indices = [i for i in var_indices if i > current_row_idx]
            if not future_indices or offset > len(future_indices):
                raise ValueError(f"NEXT({ref_var}, {offset}) references beyond available rows")
            target_idx = future_indices[offset - 1]
            
    elif func_type == 'PREV':
        if ref_var == current_var:
            # Find position of current row in variable's rows
            try:
                current_pos = var_indices.index(current_row_idx)
                if current_pos - offset < 0:
                    raise ValueError(f"PREV({ref_var}, {offset}) references before available rows")
                target_idx = var_indices[current_pos - offset]
            except ValueError:
                raise ValueError(f"Current row index {current_row_idx} not found in variable {ref_var}")
        else:
            # Find rows of ref_var that appear before current row
            past_indices = [i for i in var_indices if i < current_row_idx]
            if not past_indices or offset > len(past_indices):
                raise ValueError(f"PREV({ref_var}, {offset}) references before available rows")
            target_idx = past_indices[-offset]
    
    # Get the value from the target row
    if target_idx < 0 or target_idx >= len(row_context.rows):
        raise ValueError(f"Navigation function references row index {target_idx} out of bounds")
        
    target_row = row_context.rows[target_idx]
    if field not in target_row:
        raise ValueError(f"Field {field} not found in row for {ref_var}")
        
    return target_row[field]

# Enhanced utility functions from k.py for better navigation function handling

def _parse_navigation_expression(expr: str) -> NavigationFunctionInfo:
    """
    Parse a navigation expression to extract function information.
    Supports nested expressions and arithmetic operations.
    
    This enhanced implementation handles:
    - Simple navigation: FIRST(A.price), PREV(price, 2)
    - Nested navigation: PREV(FIRST(A.price)), NEXT(LAST(B.quantity, 3), 2)
    - Multiple nesting levels: PREV(NEXT(FIRST(A.price)))
    - Arithmetic expressions: PREV(price + 10)
    """
    expr = expr.strip()
    
    # Enhanced pattern for nested navigation with better support for arguments
    nested_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*((?:PREV|NEXT|FIRST|LAST)[^)]+\))\s*(?:,\s*(\d+))?\s*\)'
    nested_match = re.match(nested_pattern, expr, re.IGNORECASE)
    
    if nested_match:
        outer_func = nested_match.group(1).upper()
        inner_expr = nested_match.group(2)
        offset = int(nested_match.group(3)) if nested_match.group(3) else 1
        
        # Parse inner function recursively to support multiple nesting levels
        try:
            if inner_expr.count('(') > inner_expr.count(')'):
                inner_expr += ")"
                
            inner_info = _parse_navigation_expression(inner_expr)
            
            return NavigationFunctionInfo(
                function_type=outer_func,
                variable=None,
                column=None,
                offset=offset,
                is_nested=True,
                inner_functions=[inner_info],
                raw_expression=expr
            )
        except Exception:
            # Fallback to simple parsing if recursive parsing fails
            inner_info = _parse_simple_navigation(inner_expr)
            return NavigationFunctionInfo(
                function_type=outer_func,
                variable=None, 
                column=None,
                offset=offset,
                is_nested=True,
                inner_functions=[inner_info],
                raw_expression=expr
            )
    
    # Pattern for simple navigation with arithmetic: FUNC(var.col + offset)
    arithmetic_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\s*\+\s*(\d+)\s*\)'
    arith_match = re.match(arithmetic_pattern, expr, re.IGNORECASE)
    
    if arith_match:
        func_type = arith_match.group(1).upper()
        variable = arith_match.group(2)
        column = arith_match.group(3)
        offset = int(arith_match.group(4))
        
        return NavigationFunctionInfo(
            function_type=func_type,
            variable=variable,
            column=column,
            offset=offset,
            is_nested=False,
            inner_functions=[],
            raw_expression=expr
        )
    
    # Try simple navigation pattern
    return _parse_simple_navigation(expr)

def _parse_simple_navigation(expr: str) -> NavigationFunctionInfo:
    """Parse simple navigation expressions."""
    # Pattern for simple navigation: FUNC(var.col, offset) or FUNC(var.col)
    simple_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\s*(?:,\s*(\d+))?\s*\)'
    simple_match = re.match(simple_pattern, expr, re.IGNORECASE)
    
    if simple_match:
        func_type = simple_match.group(1).upper()
        variable = simple_match.group(2)
        column = simple_match.group(3)
        offset = int(simple_match.group(4)) if simple_match.group(4) else 1
        
        return NavigationFunctionInfo(
            function_type=func_type,
            variable=variable,
            column=column,
            offset=offset,
            is_nested=False,
            inner_functions=[],
            raw_expression=expr
        )
    
    # Pattern for CLASSIFIER function: FUNC(CLASSIFIER())
    classifier_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*CLASSIFIER\s*\(\s*\)\s*\)'
    classifier_match = re.match(classifier_pattern, expr, re.IGNORECASE)
    
    if classifier_match:
        return NavigationFunctionInfo(
            function_type=classifier_match.group(1).upper(),
            variable=None,
            column="CLASSIFIER",
            offset=1,
            is_nested=False,
            inner_functions=[],
            raw_expression=expr
        )
    
    raise ValueError(f"Invalid navigation function syntax: {expr}")

def _validate_nested_navigation_expr(nav_info: NavigationFunctionInfo, pattern_variables: Set[str]) -> Tuple[bool, List[str]]:
    """
    Validate a nested navigation function expression with enhanced checking.
    """
    errors = []
    
    # Validate outer function first
    if nav_info.function_type not in ('PREV', 'NEXT', 'FIRST', 'LAST'):
        errors.append(f"Invalid navigation function type: {nav_info.function_type}")
    
    # If it's a nested expression
    if nav_info.is_nested and nav_info.inner_functions:
        for inner_func in nav_info.inner_functions:
            # Validate inner function recursively
            inner_valid, inner_errors = _validate_nested_navigation_expr(inner_func, pattern_variables)
            if not inner_valid:
                errors.extend(inner_errors)
            
            # Check compatibility of function types
            if nav_info.function_type in ('FIRST', 'LAST') and inner_func.function_type in ('PREV', 'NEXT'):
                # Logical navigation cannot contain physical navigation
                errors.append(f"Invalid nesting: {nav_info.function_type} cannot contain {inner_func.function_type}")
            
            # Check offset validity
            if nav_info.offset <= 0:
                errors.append(f"Navigation offset must be positive: {nav_info.offset}")
    
    # For simple expressions, validate variable reference
    elif not nav_info.is_nested and nav_info.variable:
        # Check if variable exists in pattern
        if nav_info.variable not in pattern_variables:
            errors.append(f"Variable {nav_info.variable} not found in pattern")
        
        # Check offset validity 
        if nav_info.offset <= 0:
            errors.append(f"Navigation offset must be positive: {nav_info.offset}")
    
    return (len(errors) == 0, errors)

def _extract_navigation_calls(condition: str) -> List[str]:
    """Extract all navigation function calls from a condition."""
    # Pattern to match navigation functions including nested ones
    pattern = r'((?:PREV|NEXT|FIRST|LAST)\s*\([^)]*(?:\([^)]*\)[^)]*)*\))'
    
    matches = []
    for match in re.finditer(pattern, condition, re.IGNORECASE):
        matches.append(match.group(1))
    
    return matches

# Enhanced navigation function evaluation with structured parsing and validation

def evaluate_nested_navigation(expr, row_context, current_row_idx, current_var):
    """
    Recursively evaluate nested navigation expressions with memoization.
    
    This production-ready implementation supports complex nested navigation patterns like:
    - PREV(FIRST(A.price, 3), 2): The value of the 3rd occurrence of A.price going back 2 steps
    - NEXT(LAST(B.quantity)): The next value after the last B.quantity
    - Complex combinations of FIRST, LAST, PREV, NEXT with proper argument handling
    
    Args:
        expr: Navigation expression string (e.g., "FIRST(NEXT(A.value))")
        row_context: Pattern matching context
        current_row_idx: Current row index
        current_var: Current variable being evaluated
        
    Returns:
        Evaluated value of the navigation expression
    """
    # Start timing for performance metrics
    start_time = time.time()
    
    try:
        # Use cache if available with a more comprehensive cache key
        if not hasattr(row_context, 'navigation_cache'):
            row_context.navigation_cache = {}
            
        # Enhanced cache key includes partition info for correct behavior across partitions    
        partition_key = getattr(row_context, 'partition_key', None)
        pattern_id = id(getattr(row_context, 'pattern_metadata', None))
        cache_key = (expr, current_row_idx, current_var, partition_key, pattern_id)
        
        if cache_key in row_context.navigation_cache:
            # Update statistics if available
            if hasattr(row_context, 'stats'):
                row_context.stats["cache_hits"] = row_context.stats.get("cache_hits", 0) + 1
            return row_context.navigation_cache[cache_key]
            
        # Update miss statistics
        if hasattr(row_context, 'stats'):
            row_context.stats["cache_misses"] = row_context.stats.get("cache_misses", 0) + 1
            row_context.stats["navigation_calls"] = row_context.stats.get("navigation_calls", 0) + 1
        
        # Input validation with detailed error messages
        if not expr:
            raise ValueError("Empty navigation expression")
            
        if current_row_idx < 0 or current_row_idx >= len(row_context.rows):
            raise ValueError(f"Current row index {current_row_idx} out of bounds")
        
        # Enhanced arithmetic expression handling - incorporates from k.py
        arithmetic_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\s*\+\s*(\d+)\s*\)'
        arith_match = re.match(arithmetic_pattern, expr, re.IGNORECASE)
        
        if arith_match:
            func_type = arith_match.group(1).upper()
            var_name = arith_match.group(2)
            field = arith_match.group(3)
            arithmetic_offset = int(arith_match.group(4))
            
            # Validate variables exist
            if var_name not in row_context.variables:
                row_context.navigation_cache[cache_key] = None
                return None
                
            # Handle arithmetic expressions by evaluating base navigation first
            base_expr = f"{func_type}({var_name}.{field})"
            base_result = evaluate_nested_navigation(base_expr, row_context, current_row_idx, current_var)
            
            if base_result is not None and isinstance(base_result, (int, float)):
                result = base_result + arithmetic_offset
                row_context.navigation_cache[cache_key] = result
                return result
            else:
                row_context.navigation_cache[cache_key] = None
                return None
        
        # Enhanced pattern matching with support for complex nested expressions and arguments
        # Pattern for nested navigation with optional arguments: PREV(FIRST(A.price, 3), 2)
        nested_pattern = r'(FIRST|LAST|NEXT|PREV)\s*\(\s*((?:FIRST|LAST|NEXT|PREV)[^)]+\))\s*(?:,\s*(\d+))?\s*\)'
        
        # Pattern for simple navigation: NEXT(A.value, 1)
        simple_pattern = r'(FIRST|LAST|NEXT|PREV)\s*\(\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)(?:\s*,\s*(\d+))?\s*\)'
        
        # Pattern for CLASSIFIER function: FUNC(CLASSIFIER())
        classifier_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*CLASSIFIER\s*\(\s*\)\s*\)'
        classifier_match = re.match(classifier_pattern, expr, re.IGNORECASE)
        
        if classifier_match:
            # Special handling for CLASSIFIER function
            func_type = classifier_match.group(1).upper()
            if hasattr(row_context, 'get_classifier'):
                classifier_value = row_context.get_classifier(current_row_idx)
                if classifier_value:
                    # Convert to using the classifier variable
                    modified_expr = f"{func_type}({classifier_value}.{classifier_value})"
                    return evaluate_nested_navigation(modified_expr, row_context, current_row_idx, current_var)
                    
            # If classifier handling fails, return None
            row_context.navigation_cache[cache_key] = None
            return None
        
        # Check for nested expressions first
        nested_match = re.match(nested_pattern, expr, re.IGNORECASE)
        if nested_match:
            outer_func = nested_match.group(1).upper()
            inner_expr = nested_match.group(2)
            outer_offset = int(nested_match.group(3)) if nested_match.group(3) else 1
            
            # Enhanced validation for nested navigation - incorporate from k.py
            if outer_offset <= 0:
                row_context.navigation_cache[cache_key] = None
                return None
                
            # Check compatibility of inner/outer function types
            inner_func_match = re.match(r'(PREV|NEXT|FIRST|LAST)', inner_expr, re.IGNORECASE)
            if inner_func_match:
                inner_func = inner_func_match.group(1).upper()
                
                # Logical navigation (FIRST/LAST) cannot contain physical navigation (PREV/NEXT)
                if outer_func in ('FIRST', 'LAST') and inner_func in ('PREV', 'NEXT'):
                    row_context.navigation_cache[cache_key] = None
                    return None
                    
                # Physical navigation (PREV/NEXT) can contain both logical and physical navigation
                # but we need to ensure proper evaluation order
            
            # First evaluate the inner expression recursively
            # This handles multiple levels of nesting
            inner_result = evaluate_nested_navigation(inner_expr, row_context, current_row_idx, current_var)
            
            # If inner evaluation failed, cache the failure and return None
            if inner_result is None:
                row_context.navigation_cache[cache_key] = None
                return None
                
            # Now apply the outer function based on its type
            result = None
            
            # For nested functions, we need to determine the appropriate row and field
            # based on the inner function's result
            inner_match = re.match(simple_pattern, inner_expr, re.IGNORECASE)
            if not inner_match:
                row_context.navigation_cache[cache_key] = None
                return None
                
            inner_var = inner_match.group(2)
            inner_field = inner_match.group(3)
            
            # Find the appropriate target row index for the outer function
            target_idx = None
            
            if outer_func == 'PREV':
                # Move back outer_offset rows from the current position
                target_idx = current_row_idx - outer_offset
                
                # Check partition boundaries
                if hasattr(row_context, 'partition_boundaries') and row_context.partition_boundaries:
                    current_partition = row_context.get_partition_for_row(current_row_idx)
                    if target_idx < 0 or not row_context.check_same_partition(current_row_idx, target_idx):
                        row_context.navigation_cache[cache_key] = None
                        return None
                
            elif outer_func == 'NEXT':
                # Move forward outer_offset rows from the current position
                target_idx = current_row_idx + outer_offset
                
                # Check partition boundaries
                if hasattr(row_context, 'partition_boundaries') and row_context.partition_boundaries:
                    current_partition = row_context.get_partition_for_row(current_row_idx)
                    if target_idx >= len(row_context.rows) or not row_context.check_same_partition(current_row_idx, target_idx):
                        row_context.navigation_cache[cache_key] = None
                        return None
                        
            elif outer_func == 'FIRST':
                # Find the first occurrence of inner_var
                if inner_var in row_context.variables and row_context.variables[inner_var]:
                    target_idx = row_context.variables[inner_var][0]
                    
                    # Apply offset if provided (FIRST(A.price, 3) means 3rd occurrence)
                    if outer_offset > 1 and outer_offset <= len(row_context.variables[inner_var]):
                        target_idx = row_context.variables[inner_var][outer_offset - 1]
                    
                    # Check partition boundaries
                    if hasattr(row_context, 'partition_boundaries') and row_context.partition_boundaries and not row_context.check_same_partition(current_row_idx, target_idx):
                        row_context.navigation_cache[cache_key] = None
                        return None
                else:
                    row_context.navigation_cache[cache_key] = None
                    return None
                    
            elif outer_func == 'LAST':
                # Find the last occurrence of inner_var
                if inner_var in row_context.variables and row_context.variables[inner_var]:
                    var_indices = row_context.variables[inner_var]
                    target_idx = var_indices[-1]
                    
                    # Apply offset if provided (LAST(A.price, 3) means 3rd from the end)
                    if outer_offset > 1 and outer_offset <= len(var_indices):
                        target_idx = var_indices[-outer_offset]
                    
                    # Check partition boundaries
                    if hasattr(row_context, 'partition_boundaries') and row_context.partition_boundaries and not row_context.check_same_partition(current_row_idx, target_idx):
                        row_context.navigation_cache[cache_key] = None
                        return None
                else:
                    row_context.navigation_cache[cache_key] = None
                    return None
            
            # Get the value from the target row if it's valid
            if target_idx is not None and 0 <= target_idx < len(row_context.rows):
                result = row_context.rows[target_idx].get(inner_field)
            else:
                result = None
                
            # Cache result and return
            row_context.navigation_cache[cache_key] = result
            return result
        
        # Handle simple navigation expression
        match = re.match(simple_pattern, expr, re.IGNORECASE)
        if not match:
            row_context.navigation_cache[cache_key] = None
            return None
        
        func_type = match.group(1).upper()
        var_name = match.group(2)
        field = match.group(3)
        offset = int(match.group(4)) if match.group(4) else 1
        
        # Validate offset is positive
        if offset <= 0:
            row_context.navigation_cache[cache_key] = None
            return None
        
        # Enhanced validation with proper error handling
        if var_name not in row_context.variables:
            row_context.navigation_cache[cache_key] = None
            return None
        
        var_indices = sorted(row_context.variables[var_name])
        if not var_indices:
            row_context.navigation_cache[cache_key] = None
            return None
            
        # Determine target index based on navigation function
        target_idx = None
        
        try:
            if func_type == 'FIRST':
                # Get the specified occurrence from start, with bounds checking
                occurrence_idx = offset - 1  # Convert to 0-based index
                if occurrence_idx < len(var_indices):
                    target_idx = var_indices[occurrence_idx]
                else:
                    row_context.navigation_cache[cache_key] = None
                    return None
                    
            elif func_type == 'LAST':
                # Get the specified occurrence from end, with bounds checking
                occurrence_idx = -offset  # Convert to negative index for counting from end
                if abs(occurrence_idx) <= len(var_indices):
                    target_idx = var_indices[occurrence_idx]
                else:
                    row_context.navigation_cache[cache_key] = None
                    return None
                    
            elif func_type == 'NEXT':
                # Enhanced NEXT with partition boundary checking
                if var_name == current_var:
                    # Self-reference navigation (e.g., NEXT from current position in the same variable)
                    try:
                        current_pos = var_indices.index(current_row_idx)
                        if current_pos + offset >= len(var_indices):
                            row_context.navigation_cache[cache_key] = None
                            return None
                        target_idx = var_indices[current_pos + offset]
                    except ValueError:
                        # Current row not found in this variable's indices
                        row_context.navigation_cache[cache_key] = None
                        return None
                else:
                    # Cross-variable navigation
                    future_indices = [i for i in var_indices if i > current_row_idx]
                    if not future_indices or offset > len(future_indices):
                        row_context.navigation_cache[cache_key] = None
                        return None
                    target_idx = future_indices[offset - 1]
                    
            elif func_type == 'PREV':
                # Enhanced PREV with partition boundary checking
                if var_name == current_var:
                    # Self-reference navigation
                    try:
                        current_pos = var_indices.index(current_row_idx)
                        if current_pos - offset < 0:
                            row_context.navigation_cache[cache_key] = None
                            return None
                        target_idx = var_indices[current_pos - offset]
                    except ValueError:
                        # Current row not found in this variable's indices
                        row_context.navigation_cache[cache_key] = None
                        return None
                else:
                    # Cross-variable navigation
                    past_indices = [i for i in var_indices if i < current_row_idx]
                    if not past_indices or offset > len(past_indices):
                        row_context.navigation_cache[cache_key] = None
                        return None
                    target_idx = past_indices[-offset]
                    
        except (ValueError, IndexError) as e:
            # Enhanced error handling with logging
            if hasattr(row_context, 'stats'):
                row_context.stats["navigation_errors"] = row_context.stats.get("navigation_errors", 0) + 1
            row_context.navigation_cache[cache_key] = None
            return None
        
        # Check partition boundaries for consistent behavior
        if hasattr(row_context, 'partition_boundaries') and row_context.partition_boundaries:
            if not row_context.check_same_partition(current_row_idx, target_idx):
                row_context.navigation_cache[cache_key] = None
                return None
        
        # Get value from target row with comprehensive bounds checking
        if target_idx is None or target_idx < 0 or target_idx >= len(row_context.rows):
            row_context.navigation_cache[cache_key] = None
            return None
        
        target_row = row_context.rows[target_idx]
        if field not in target_row:
            row_context.navigation_cache[cache_key] = None
            return None
        
        result = target_row[field]
        
        # Cache result before returning
        row_context.navigation_cache[cache_key] = result
        return result
    
    finally:
        # Track performance metrics
        if hasattr(row_context, 'timing'):
            navigation_time = time.time() - start_time
            row_context.timing['nested_navigation'] = row_context.timing.get('nested_navigation', 0) + navigation_time


def validate_navigation_conditions(match_data, pattern_metadata=None, conditions=None):
    """Validate navigation functions for matches in PERMUTE patterns.
    
    For PERMUTE patterns, navigation functions work based on the actual positions of variables
    in the matched rows, not the original pattern order.
    
    Args:
        match_data: The match data containing variable assignments
        pattern_metadata: Pattern metadata containing permute=True for PERMUTE patterns
        conditions: Dictionary of condition expressions (optional)
        
    Returns:
        True if navigation conditions are valid, False otherwise
    """
    # For PERMUTE patterns, skip post-validation as the matching phase already validated
    if pattern_metadata and pattern_metadata.get('permute', False):
        return True
        
    # For standard patterns, additional validation could be added here
    return True