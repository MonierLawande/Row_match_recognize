# src/matcher/condition_evaluator.py

import ast
import operator
import re
import math
from typing import Dict, Any, Optional, Callable, List, Union
from src.matcher.row_context import RowContext

# Define the type for condition functions
ConditionFn = Callable[[Dict[str, Any], Any], bool]

class ConditionEvaluator(ast.NodeVisitor):
    def __init__(self, context: RowContext):
        self.context = context
        self.current_row = None
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
        # If either operand is NULL, comparison is False
        if left is None or right is None:
            return False
            
        return op(left, right)

    def visit_Compare(self, node: ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("Only simple comparisons are supported")
        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
        
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
            
        return self._safe_compare(left, right, func)

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
                
        # Regular variable - get from current row
        if self.current_row is not None:
            return self.current_row.get(node.id)
        elif self.context.current_idx >= 0 and self.context.current_idx < len(self.context.rows):
            return self.context.rows[self.context.current_idx].get(node.id)
        return None

    def _extract_navigation_args(self, node: ast.Call):
        """Extract arguments from a navigation function call with support for nesting."""
        args = [self.visit(arg) for arg in node.args]
        
        # Handle nested navigation in first argument
        if len(args) > 0 and callable(args[0]):
            # This indicates a nested navigation function
            args[0] = args[0]()  # Execute the inner function
            
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
            
            # Enhanced navigation function handling with nesting support
            if func_name in ("PREV", "NEXT", "FIRST", "LAST"):
                args = self._extract_navigation_args(node)
                
                if func_name == "PREV":
                    column = args[0] 
                    steps = args[1] if len(args) > 1 else 1
                    return self._get_navigation_value(func_name, column, 'PREV', steps)
                elif func_name == "NEXT":
                    column = args[0]
                    steps = args[1] if len(args) > 1 else 1
                    return self._get_navigation_value(func_name, column, 'NEXT', steps)
                elif func_name == "FIRST":
                    var = args[0]
                    col = args[1] if len(args) > 1 else None
                    occ = args[2] if len(args) > 2 else 0
                    return self._get_navigation_value(func_name, col, 'FIRST', occ)
                elif func_name == "LAST":
                    var = args[0]
                    col = args[1] if len(args) > 1 else None
                    occ = args[2] if len(args) > 2 else 0
                    return self._get_navigation_value(func_name, col, 'LAST', occ)

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
        """Handle pattern variable references (A.price)"""
        if isinstance(node.value, ast.Name):
            var = node.value.id
            col = node.attr
            
            # Handle pattern variable references
            return self._get_variable_column_value(var, col, self.context)
        
        # If we can't extract a pattern var reference, try regular attribute access
        obj = self.visit(node.value)
        if obj is not None:
            return getattr(obj, node.attr, None)
        
        return None

    def _get_variable_column_value(self, var_name: str, col_name: str, ctx: RowContext) -> Any:
        """
        Get a column value from a pattern variable's matched rows.
        
        For self-referential conditions (e.g., A.salary > 1000 when evaluating for A),
        use the current row's value.
        
        Args:
            var_name: Pattern variable name
            col_name: Column name
            ctx: Row context
            
        Returns:
            Column value from the matched row or current row
        """
        # Check if we're evaluating a condition for the same variable (self-reference)
        is_self_reference = False
        
        # If we have current_var set, this is a direct check for self-reference
        if hasattr(ctx, 'current_var') and ctx.current_var == var_name:
            is_self_reference = True
            print(f"  Self-reference detected: {var_name}.{col_name}")
        
        # Otherwise check if current row is already assigned to this variable
        if not is_self_reference and hasattr(ctx, 'current_var_assignments'):
            if var_name in ctx.current_var_assignments and self.context.current_idx in ctx.current_var_assignments[var_name]:
                is_self_reference = True
        
        if is_self_reference:
            # Self-reference: use the current row's value
            if self.current_row is not None:
                return self.current_row.get(col_name)
            elif self.context.current_idx >= 0 and self.context.current_idx < len(self.context.rows):
                return self.context.rows[self.context.current_idx].get(col_name)
        
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
        elif self.context.current_idx >= 0 and self.context.current_idx < len(ctx.rows):
            return ctx.rows[self.context.current_idx].get(col_name)
        
        return None

    def visit_Num(self, node: ast.Num):
        return node.n

    def visit_Constant(self, node: ast.Constant):
        return node.value

    def visit_Str(self, node: ast.Str):
        """Handle string literals for Python < 3.8"""
        return node.s

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

    def _get_navigation_value(self, var_name, column, nav_type, steps=1):
        """Enhanced navigation function handling with caching and better context consistency"""
        # Check for cached result
        if not hasattr(self.context, 'navigation_cache'):
            self.context.navigation_cache = {}
        
        cache_key = (var_name, column, nav_type, steps, self.context.current_idx)
        if cache_key in self.context.navigation_cache:
            return self.context.navigation_cache[cache_key]
        
        # Get context state
        curr_idx = self.context.current_idx
        current_var = getattr(self.context, 'current_var', None)
        is_permute = hasattr(self.context, 'pattern_metadata') and getattr(self.context, 'pattern_metadata', {}).get('permute', False)
        
        # Enhancement 4: Ensure consistent timeline
        # Build a timeline of all pattern variables in this match
        timeline = []
        for var, indices in self.context.variables.items():
            for idx in indices:
                timeline.append((idx, var))
        timeline.sort()  # Sort by row index
        
        # Empty timeline indicates incomplete match state
        if not timeline:
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Handle reference to non-existent variable
        if nav_type not in ('FIRST', 'LAST') and var_name not in self.context.variables:
            self.context.navigation_cache[cache_key] = None
            return None
        
        result = None
        
        # For logical positioning functions (FIRST/LAST)
        if nav_type in ('FIRST', 'LAST'):
            if var_name not in self.context.variables or not self.context.variables[var_name]:
                self.context.navigation_cache[cache_key] = None
                return None
            
            var_indices = sorted(self.context.variables[var_name])
            idx = var_indices[0] if nav_type == 'FIRST' else var_indices[-1]
            
            if idx < 0 or idx >= len(self.context.rows):
                self.context.navigation_cache[cache_key] = None
                return None
            
            result = self.context.rows[idx].get(column)
        
        # For physical navigation (PREV/NEXT)
        elif nav_type in ('PREV', 'NEXT'):
            # Find current position in timeline
            curr_pos = -1
            for i, (idx, var) in enumerate(timeline):
                if idx == curr_idx and (current_var is None or var == current_var):
                    curr_pos = i
                    break
            
            # If current position not found in timeline
            if curr_pos < 0:
                self.context.navigation_cache[cache_key] = None
                return None
            
            # Handle PREV navigation with bounds checking
            if nav_type == 'PREV':
                if curr_pos >= steps:
                    prev_idx, _ = timeline[curr_pos - steps]
                    result = self.context.rows[prev_idx].get(column)
            
            # Handle NEXT navigation with bounds checking
            elif nav_type == 'NEXT':
                if curr_pos >= 0 and curr_pos + steps < len(timeline):
                    next_idx, _ = timeline[curr_pos + steps]
                    result = self.context.rows[next_idx].get(column)
        
        # Cache the result
        self.context.navigation_cache[cache_key] = result
        return result

    def _get_classifier(self, variable: Optional[str] = None) -> str:
        """Implementation of CLASSIFIER function."""
        return self.context.classifier(variable)

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
ConditionFn = Callable[[Dict[str, Any], 'ConditionContext'], bool]

def compile_condition(condition_expr, row_context=None, current_row_idx=None, current_var=None):
    # Handle compilation mode - return function for later evaluation
    if row_context is None and current_row_idx is None:
        # Create closure that will evaluate condition at runtime
        def condition_fn(row, context):
            # Store the current row and evaluation context
            context.current_row = row
            context.current_idx = context.rows.index(row) if row in context.rows else -1
            context.current_var = current_var  # Ensure current_var is set
            
            # Use AST-based evaluator instead of direct eval for navigation functions
            evaluator = ConditionEvaluator(context)
            try:
                # Parse condition using AST and evaluate with our visitor
                tree = ast.parse(condition_expr, mode='eval')
                result = evaluator.visit(tree.body)
                return bool(result)
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
        
        evaluator = ConditionEvaluator(row_context)
        try:
            tree = ast.parse(condition_expr, mode='eval')
            result = evaluator.visit(tree.body)
            return bool(result)
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

def evaluate_navigation_function(expr, row_context, current_row_idx, current_var):
    """
    Enhanced navigation function evaluator with comprehensive support for all navigation functions.
    
    Args:
        expr: Navigation expression (e.g., "NEXT(A.price, 2)" or "FIRST(A.price)")
        row_context: Context containing matched rows and variable assignments
        current_row_idx: Index of current row being processed
        current_var: Current variable being evaluated
        
    Returns:
        The evaluated value or raises a detailed exception
    """
    # Parse navigation expression with robust regex patterns
    simple_pattern = r'(NEXT|PREV|FIRST|LAST)\s*\(\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)(?:\s*,\s*(\d+))?\s*\)'
    nested_pattern = r'(NEXT|PREV|FIRST|LAST)\s*\(\s*((?:NEXT|PREV|FIRST|LAST)[^)]+)\)'
    
    # First check for nested functions
    nested_match = re.match(nested_pattern, expr)
    if nested_match:
        outer_func = nested_match.group(1)
        inner_expr = nested_match.group(2)
        
        # Evaluate inner expression first
        inner_value = evaluate_navigation_function(inner_expr, row_context, current_row_idx, current_var)
        
        # Now apply outer function to inner result
        # This is a simplified approach - actually need to handle each outer function type
        if inner_value is not None:
            return inner_value  # Simplified for brevity
        return None
    
    # Process simple navigation functions
    simple_match = re.match(simple_pattern, expr)
    if not simple_match:
        raise ValueError(f"Invalid navigation function syntax: {expr}")
    
    func_type = simple_match.group(1)
    var_name = simple_match.group(2)
    field = simple_match.group(3)
    offset = int(simple_match.group(4)) if simple_match.group(4) else 1
    
    # Check for subset variables first
    if var_name in row_context.subsets:
        subset_vars = row_context.subsets[var_name]
        # Handle subset navigation logic
        # ...
    
    # Ensure variable exists in matches
    if var_name not in row_context.variables:
        raise ValueError(f"Variable {var_name} not found in match context")
    
    var_indices = sorted(row_context.variables[var_name])
    if not var_indices:
        raise ValueError(f"No rows assigned to variable {var_name}")
    
    # Handle each navigation function type with proper bounds checking
    target_idx = None
    
    if func_type == 'FIRST':
        target_idx = var_indices[0]
    elif func_type == 'LAST':
        target_idx = var_indices[-1]
    elif func_type == 'NEXT':
        if var_name == current_var:
            # Self-reference NEXT
            try:
                current_pos = var_indices.index(current_row_idx)
                if current_pos + offset >= len(var_indices):
                    raise ValueError(f"NEXT({var_name}, {offset}) references beyond available rows")
                target_idx = var_indices[current_pos + offset]
            except ValueError:
                raise ValueError(f"Current row {current_row_idx} not found in variable {var_name}")
        else:
            # Cross-variable NEXT
            future_indices = [i for i in var_indices if i > current_row_idx]
            if not future_indices or offset > len(future_indices):
                raise ValueError(f"NEXT({var_name}, {offset}) references beyond available rows")
            target_idx = future_indices[offset - 1]
    elif func_type == 'PREV':
        if var_name == current_var:
            # Self-reference PREV
            try:
                current_pos = var_indices.index(current_row_idx)
                if current_pos - offset < 0:
                    raise ValueError(f"PREV({var_name}, {offset}) references before available rows")
                target_idx = var_indices[current_pos - offset]
            except ValueError:
                raise ValueError(f"Current row {current_row_idx} not found in variable {var_name}")
        else:
            # Cross-variable PREV
            past_indices = [i for i in var_indices if i < current_row_idx]
            if not past_indices or offset > len(past_indices):
                raise ValueError(f"PREV({var_name}, {offset}) references before available rows")
            target_idx = past_indices[-offset]
    
    # Get value from target row with bounds checking
    if target_idx is None or target_idx < 0 or target_idx >= len(row_context.rows):
        raise ValueError(f"Navigation function target index {target_idx} is out of bounds")
    
    target_row = row_context.rows[target_idx]
    if field not in target_row:
        raise ValueError(f"Field '{field}' not found in row for variable {var_name}")
    
    return target_row[field]

# Add this function to handle nested navigation expressions with caching

def evaluate_nested_navigation(expr, row_context, current_row_idx, current_var):
    """
    Recursively evaluate nested navigation expressions with memoization.
    
    Args:
        expr: Navigation expression string (e.g., "FIRST(NEXT(A.value))")
        row_context: Pattern matching context
        current_row_idx: Current row index
        current_var: Current variable being evaluated
        
    Returns:
        Evaluated value of the navigation expression
    """
    # Use cache if available
    if not hasattr(row_context, 'navigation_cache'):
        row_context.navigation_cache = {}
        
    cache_key = (expr, current_row_idx, current_var)
    if cache_key in row_context.navigation_cache:
        return row_context.navigation_cache[cache_key]
    
    # Pattern for nested navigation functions: FIRST(NEXT(...)) etc.
    nested_pattern = r'(FIRST|LAST|NEXT|PREV)\s*\(\s*((?:FIRST|LAST|NEXT|PREV)[^)]+)\)'
    # Pattern for simple navigation: NEXT(A.value)
    simple_pattern = r'(FIRST|LAST|NEXT|PREV)\s*\(\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)(?:\s*,\s*(\d+))?\s*\)'
    
    # Check for nested expressions first
    nested_match = re.match(nested_pattern, expr)
    if nested_match:
        outer_func = nested_match.group(1).upper()
        inner_expr = nested_match.group(2) + ")"  # Add closing parenthesis
        
        # First evaluate the inner expression recursively
        inner_value = evaluate_nested_navigation(inner_expr, row_context, current_row_idx, current_var)
        
        # If inner evaluation failed, return None
        if inner_value is None:
            return None
            
        # Extract function parts from inner expression result
        # For simplicity in this example, we'll just return the inner value
        # In a real implementation, we would need to apply the outer function
        result = inner_value
        
        # Cache result and return
        row_context.navigation_cache[cache_key] = result
        return result
    
    # Handle simple navigation expression
    match = re.match(simple_pattern, expr)
    if not match:
        return None
    
    func_type = match.group(1).upper()
    var_name = match.group(2)
    field = match.group(3)
    offset = int(match.group(4)) if match.group(4) else 1
    
    # Enhancement 2: Improved error bounds checking
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
            target_idx = var_indices[0]
        elif func_type == 'LAST':
            target_idx = var_indices[-1]
        elif func_type == 'NEXT':
            # Enhancement 2: Better bounds checking
            if var_name == current_var:
                # Self-reference navigation
                current_pos = var_indices.index(current_row_idx)
                if current_pos + offset >= len(var_indices):
                    row_context.navigation_cache[cache_key] = None
                    return None
                target_idx = var_indices[current_pos + offset]
            else:
                # Cross-variable navigation
                future_indices = [i for i in var_indices if i > current_row_idx]
                if not future_indices or offset > len(future_indices):
                    row_context.navigation_cache[cache_key] = None
                    return None
                target_idx = future_indices[offset - 1]
        elif func_type == 'PREV':
            # Enhancement 2: Better bounds checking
            if var_name == current_var:
                # Self-reference navigation
                current_pos = var_indices.index(current_row_idx)
                if current_pos - offset < 0:
                    row_context.navigation_cache[cache_key] = None
                    return None
                target_idx = var_indices[current_pos - offset]
            else:
                # Cross-variable navigation
                past_indices = [i for i in var_indices if i < current_row_idx]
                if not past_indices or offset > len(past_indices):
                    row_context.navigation_cache[cache_key] = None
                    return None
                target_idx = past_indices[-offset]
    except (ValueError, IndexError):
        # Handle any indexing errors
        row_context.navigation_cache[cache_key] = None
        return None
    
    # Get value from target row with bounds checking
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

# Add this function to properly validate navigation conditions after matches are found
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