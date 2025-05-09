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
            return lambda col, steps=1: self._get_prev_value(col, steps)
        elif node.id.upper() == "NEXT":
            return lambda col, steps=1: self._get_next_value(col, steps)
        elif node.id.upper() == "FIRST":
            return lambda var, col, occ=0: self._get_first_value(var, col, occ)
        elif node.id.upper() == "LAST":
            return lambda var, col, occ=0: self._get_last_value(var, col, occ)
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
                    return self._get_prev_value(column, steps)
                elif func_name == "NEXT":
                    column = args[0]
                    steps = args[1] if len(args) > 1 else 1
                    return self._get_next_value(column, steps)
                elif func_name == "FIRST":
                    var = args[0]
                    col = args[1] if len(args) > 1 else None
                    occ = args[2] if len(args) > 2 else 0
                    return self._get_first_value(var, col, occ)
                elif func_name == "LAST":
                    var = args[0]
                    col = args[1] if len(args) > 1 else None
                    occ = args[2] if len(args) > 2 else 0
                    return self._get_last_value(var, col, occ)

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
            if var_name in ctx.current_var_assignments and ctx.current_idx in ctx.current_var_assignments[var_name]:
                is_self_reference = True
        
        if is_self_reference:
            # Self-reference: use the current row's value
            if self.current_row is not None:
                return self.current_row.get(col_name)
            elif ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                return ctx.rows[ctx.current_idx].get(col_name)
        
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
                return self._get_prev_value(col_name, idx)
            elif isinstance(idx, int) and idx < 0:
                # Negative indices could translate to NEXT
                return self._get_next_value(col_name, abs(idx))
        
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

    def _get_prev_value(self, column: str, steps: int = 1) -> Any:
        """Enhanced PREV function with better boundary handling."""
        # Handle the case where column is the result of a nested navigation function
        if not isinstance(column, str):
            return column  # Return the already computed value
            
        idx = self.context.current_idx - steps
        if 0 <= idx < len(self.context.rows):
            return self.context.rows[idx].get(column)
        # Handle out-of-bounds with SQL NULL semantics
        return None

    def _get_next_value(self, column: str, steps: int = 1) -> Any:
        """Enhanced NEXT function with better boundary handling."""
        # Handle the case where column is the result of a nested navigation function
        if not isinstance(column, str):
            return column  # Return the already computed value
            
        idx = self.context.current_idx + steps
        if 0 <= idx < len(self.context.rows):
            return self.context.rows[idx].get(column)
        # Handle out-of-bounds with SQL NULL semantics 
        return None

    def _get_first_value(self, variable: str, column: str, occurrence: int = 0) -> Any:
        """Implementation of FIRST function."""
        row = self.context.first(variable, occurrence)
        return row.get(column) if row else None

    def _get_last_value(self, variable: str, column: str, occurrence: int = 0) -> Any:
        """Implementation of LAST function."""
        # Check if this is a pattern variable reference (e.g., LAST(C.salary))
        var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\\.([A-Za-z_][A-Za-z0-9_]*)', column)
        if var_col_match:
            var_name = var_col_match.group(1)
            col_name = var_col_match.group(2)
            
            # Get the last row matched to this variable
            var_indices = self.context.variables.get(var_name, [])
            if var_indices:
                last_idx = var_indices[-1]
                if last_idx < len(self.context.rows):
                    return self.context.rows[last_idx].get(col_name)
            return None
        
        # Regular LAST function
        var_indices = self.context.variables.get(variable, [])
        if var_indices and occurrence < len(var_indices):
            idx = var_indices[-(occurrence+1)]
            if idx < len(self.context.rows):
                return self.context.rows[idx].get(column)
        return None

    def _get_classifier(self, variable: Optional[str] = None) -> str:
        """Implementation of CLASSIFIER function."""
        return self.context.classifier(variable)

# Define the ConditionFn type for clarity
from typing import Callable, Dict, Any, Optional, List, Tuple, Union
import re
import ast

# Type alias for condition functions
ConditionFn = Callable[[Dict[str, Any], 'ConditionContext'], bool]

def compile_condition(condition_text: str) -> ConditionFn:
    """Compile a condition string into a condition function with strict Trino-compatible navigation behaviors."""
    if not condition_text or condition_text.strip().upper() == 'TRUE':
        return lambda row, ctx: True
    
    try:
        # Special case for simple pattern: column = 'value'
        simple_eq_match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*'([^']*)'", condition_text.strip())
        if simple_eq_match:
            column = simple_eq_match.group(1)
            value = simple_eq_match.group(2)
            return lambda row, ctx: row.get(column) == value
        
        # Convert SQL string literals to Python string literals
        processed_text = ""
        i = 0
        in_string = False
        
        while i < len(condition_text):
            if not in_string and condition_text[i:i+1] == "'":
                # Start of a SQL string
                processed_text += '"'
                in_string = True
                i += 1
            elif in_string and condition_text[i:i+1] == "'":
                # Check if this is an escaped quote ('' in SQL)
                if i + 1 < len(condition_text) and condition_text[i+1:i+2] == "'":
                    # It's an escaped quote in SQL, convert to single quote in Python
                    processed_text += "'"
                    i += 2  # Skip both single quotes
                else:
                    # End of SQL string
                    processed_text += '"'
                    in_string = False
                    i += 1
            else:
                # Regular character
                if in_string and condition_text[i] == '"':
                    # Escape double quotes inside string
                    processed_text += '\\"'
                else:
                    processed_text += condition_text[i]
                i += 1
        
        # Handle SQL operators
        processed_text = re.sub(r'\bAND\b', 'and', processed_text, flags=re.IGNORECASE)
        processed_text = re.sub(r'\bOR\b', 'or', processed_text, flags=re.IGNORECASE)
        processed_text = re.sub(r'\bNOT\b', 'not', processed_text, flags=re.IGNORECASE)
        
        # Convert SQL = to Python ==
        processed_text = re.sub(r'(?<![=!<>])=(?!=)', '==', processed_text)
        
        # Handle pattern variable references
        processed_text = re.sub(
            r'([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)',
            r"get_var_value('\1', '\2')",
            processed_text
        )
        
        # Handle navigation functions
        processed_text = re.sub(
            r'PREV\s*\(\s*([^,\)]+)(?:\s*,\s*(\d+))?\s*\)',
            lambda m: f"prev('{m.group(1).strip()}', {m.group(2) if m.group(2) else 1})",
            processed_text,
            flags=re.IGNORECASE
        )
        
        processed_text = re.sub(
            r'NEXT\s*\(\s*([^,\)]+)(?:\s*,\s*(\d+))?\s*\)',
            lambda m: f"next('{m.group(1).strip()}', {m.group(2) if m.group(2) else 1})",
            processed_text,
            flags=re.IGNORECASE
        )
        
        processed_text = re.sub(
            r'FIRST\s*\(\s*([^,\)]+)(?:\s*,\s*([^,\)]+))?\s*\)',
            lambda m: f"first('{m.group(1).strip()}', '{m.group(2).strip() if m.group(2) else ''}')",
            processed_text,
            flags=re.IGNORECASE
        )
        
        processed_text = re.sub(
            r'LAST\s*\(\s*([^,\)]+)(?:\s*,\s*([^,\)]+))?\s*\)',
            lambda m: f"last('{m.group(1).strip()}', '{m.group(2).strip() if m.group(2) else ''}')",
            processed_text,
            flags=re.IGNORECASE
        )
        
        # Try compiling
        compiled_code = compile(processed_text, '<string>', 'eval')
        
        # Define condition function with all required helpers
        def condition_fn(row, ctx):
            # Helper for variable access
            def get_var_value(var, col):
                var_indices = ctx.variables.get(var, [])
                if var_indices:
                    idx = var_indices[-1]  # Use most recent match
                    if 0 <= idx < len(ctx.rows):
                        return ctx.rows[idx].get(col)
                return None
            
            # Navigation functions with Trino-compatible behavior for PERMUTE
            def prev(col, steps=1):
                # For PERMUTE patterns with fixed logical order navigation
                is_permute = hasattr(ctx, 'pattern_variables') and len(ctx.pattern_variables) > 0
                
                if is_permute and hasattr(ctx, 'current_var'):
                    # Get original pattern order (A, B, C)
                    pattern_order = ctx.pattern_variables
                    current_var = ctx.current_var
                    
                    if current_var in pattern_order:
                        current_pos = pattern_order.index(current_var)
                        
                        # In Trino's PERMUTE: PREV reference is only valid if:
                        # 1. Current var is not the first in original pattern
                        # 2. Previous var in original pattern has already been matched
                        if current_pos < steps:
                            # Cannot go back steps positions in original pattern
                            return None
                        
                        # Get previous variable in original pattern
                        prev_var = pattern_order[current_pos - steps]
                        
                        # Check if that variable has been matched yet
                        prev_indices = ctx.variables.get(prev_var, [])
                        if not prev_indices:
                            # The variable hasn't been matched yet - in Trino this means NULL
                            return None
                        
                        # Return value from most recent match of previous variable
                        prev_idx = prev_indices[-1]
                        if 0 <= prev_idx < len(ctx.rows):
                            return ctx.rows[prev_idx].get(col)
                        return None
                
                # Default implementation for normal patterns
                if ctx.current_idx < steps:
                    return None
                    
                idx = ctx.current_idx - steps
                return ctx.rows[idx].get(col)
            
            def next(col, steps=1):
                # For PERMUTE patterns with fixed logical order navigation
                is_permute = hasattr(ctx, 'pattern_variables') and len(ctx.pattern_variables) > 0
                
                if is_permute and hasattr(ctx, 'current_var'):
                    # Get original pattern order (A, B, C)
                    pattern_order = ctx.pattern_variables
                    current_var = ctx.current_var
                    
                    if current_var in pattern_order:
                        current_pos = pattern_order.index(current_var)
                        
                        # In Trino's PERMUTE: NEXT reference is only valid if:
                        # 1. Current var is not the last in original pattern
                        # 2. Next var in original pattern has already been matched
                        if current_pos + steps >= len(pattern_order):
                            # Cannot go forward steps positions in original pattern
                            return None
                        
                        # Get next variable in original pattern
                        next_var = pattern_order[current_pos + steps]
                        
                        # Check if that variable has been matched yet
                        next_indices = ctx.variables.get(next_var, [])
                        if not next_indices:
                            # The variable hasn't been matched yet - in Trino this means NULL
                            return None
                        
                        # Return value from most recent match of next variable
                        next_idx = next_indices[-1]
                        if 0 <= next_idx < len(ctx.rows):
                            return ctx.rows[next_idx].get(col)
                        return None
                
                # Default implementation for normal patterns
                if ctx.current_idx + steps >= len(ctx.rows):
                    return None
                    
                idx = ctx.current_idx + steps
                return ctx.rows[idx].get(col)
            
            def first(var, col=None):
                # FIRST requires the variable to already be matched
                if col is None and '.' in var:
                    # Handle FIRST(A.col) format
                    parts = var.split('.')
                    if len(parts) == 2:
                        var, col = parts
                
                var_indices = ctx.variables.get(var, [])
                if not var_indices:
                    # Trino behavior: FIRST returns NULL if variable not matched yet
                    return None
                
                # Get first occurrence of the variable
                idx = var_indices[0]
                if 0 <= idx < len(ctx.rows):
                    return ctx.rows[idx].get(col) if col else None
                return None
            
            def last(var, col=None):
                # LAST requires the variable to already be matched
                var_indices = ctx.variables.get(var, [])
                if not var_indices:
                    return None
                    
                if col:
                    idx = var_indices[-1]
                    return ctx.rows[idx].get(col)
                else:
                    # Handle LAST(A.col)
                    parts = var.split('.')
                    if len(parts) == 2:
                        var_name, col_name = parts
                        var_indices = ctx.variables.get(var_name, [])
                        if var_indices:
                            idx = var_indices[-1]
                            return ctx.rows[idx].get(col_name)
                return None
            
            # Set up environment
            env = {
                'row': row,
                'ctx': ctx,
                # Add direct row value access
                **{k: v for k, v in row.items()},
                # Helper functions
                'get_var_value': get_var_value,
                'prev': prev,
                'next': next,
                'first': first,
                'last': last,
            }
            
            try:
                # Execute the condition with proper NULL handling
                result = eval(compiled_code, {}, env)
                if result is None:
                    # In SQL, comparison with NULL results in FALSE
                    return False
                return bool(result)
            except Exception as e:
                print(f"Error evaluating condition '{processed_text}': {str(e)}")
                return False
                
        return condition_fn
            
    except SyntaxError as e:
        print(f"Syntax error parsing: '{condition_text}' (processed as '{processed_text}')")
        print(f"Error details: {e}")
        print(f"WARNING: Falling back to TRUE for condition: {condition_text}")
        return lambda row, ctx: True
    except Exception as e:
        print(f"Error processing condition: '{condition_text}': {str(e)}")
        print(f"WARNING: Falling back to TRUE for condition: {condition_text}")
        return lambda row, ctx: True