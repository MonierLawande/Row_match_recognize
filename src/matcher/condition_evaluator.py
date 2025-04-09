# src/matcher/condition_evaluator.py

import ast
import operator
import re
import math
from typing import Dict, Any, Optional, Callable, List
from src.matcher.row_context import RowContext

class ConditionEvaluator(ast.NodeVisitor):
    def __init__(self, context: RowContext):
        self.context = context
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
                
        # Regular variable - get from current row
        if self.context.current_idx >= len(self.context.rows):
            # Safer boundary handling
            return None
        return self.context.rows[self.context.current_idx].get(node.id)

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
            rows = self.context.var_rows(var)
            if rows:
                return rows[-1].get(col)
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
            if col_name is not None:
                return self.context.rows[self.context.current_idx].get(col_name)
        
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
        row = self.context.last(variable, occurrence)
        return row.get(column) if row else None
        
    def _get_classifier(self, variable: Optional[str] = None) -> str:
        """Implementation of CLASSIFIER function."""
        return self.context.classifier(variable)

def compile_condition(expr: str) -> Callable[[Dict[str, Any], RowContext], bool]:
    """Compile a condition expression into a function with improved compound expression handling."""
    import math
    
    # First handle simple condition with "return" keyword
    if "return" in expr:
        if expr == "return>0":
            return lambda row, ctx: row.get('return', 0) > 0
        elif expr == "return<0":
            return lambda row, ctx: row.get('return', 0) < 0
    
    # Handle IS NULL and IS NOT NULL conditions
    is_null_match = re.match(r'(.*?)\s+IS\s+NULL$', expr, re.IGNORECASE)
    if is_null_match:
        col = is_null_match.group(1).strip()
        return lambda row, ctx: row.get(col) is None
    
    is_not_null_match = re.match(r'(.*?)\s+IS\s+NOT\s+NULL$', expr, re.IGNORECASE)
    if is_not_null_match:
        col = is_not_null_match.group(1).strip()
        return lambda row, ctx: row.get(col) is not None
    
    # Check for compound expressions with AND
    if " AND " in expr:
        parts = expr.split(" AND ")
        left_condition = compile_condition(parts[0])
        right_condition = compile_condition(parts[1])
        return lambda row, ctx: left_condition(row, ctx) and right_condition(row, ctx)
    
    # Check for compound expressions with OR
    if " OR " in expr:
        parts = expr.split(" OR ")
        left_condition = compile_condition(parts[0])
        right_condition = compile_condition(parts[1])
        return lambda row, ctx: left_condition(row, ctx) or right_condition(row, ctx)
    
    # Special handling for common function patterns
    
    # ABS function
    abs_match = re.match(r'ABS\((.*?)\)\s*([<>=!]+)\s*([\d.]+)', expr)
    if abs_match:
        col, op, val = abs_match.groups()
        val = float(val)
        if op == ">=":
            return lambda row, ctx: abs(row.get(col.strip(), 0)) >= val
        elif op == ">":
            return lambda row, ctx: abs(row.get(col.strip(), 0)) > val
        elif op == "<=":
            return lambda row, ctx: abs(row.get(col.strip(), 0)) <= val
        elif op == "<":
            return lambda row, ctx: abs(row.get(col.strip(), 0)) < val
        elif op == "==" or op == "=":
            return lambda row, ctx: abs(row.get(col.strip(), 0)) == val
        elif op == "!=":
            return lambda row, ctx: abs(row.get(col.strip(), 0)) != val
    
    # PREV function
       # PREV function with NULL handling
    prev_match = re.match(r'(.*?)\s*([<>=!]+)\s*PREV\((.*?),?\s*(\d+)?\)', expr)
    if prev_match:
        col1, op, col2, steps = prev_match.groups()
        steps = int(steps) if steps else 1
        
        def prev_condition(row, ctx):
            left_val = row.get(col1.strip(), 0)
            prev_row = ctx.prev(steps)
            right_val = prev_row.get(col2.strip()) if prev_row else None
            
            # Handle NULL comparison
            if right_val is None:
                return False  # SQL NULL semantics
                
            if op == ">=":
                return left_val >= right_val
            elif op == ">":
                return left_val > right_val
            elif op == "<=":
                return left_val <= right_val
            elif op == "<":
                return left_val < right_val
            elif op == "==" or op == "=":
                return left_val == right_val
            elif op == "!=":
                return left_val != right_val
            return False
            
        return prev_condition
    
    # NEXT function with NULL handling
    next_match = re.match(r'(.*?)\s*([<>=!]+)\s*NEXT\((.*?),?\s*(\d+)?\)', expr)
    if next_match:
        col1, op, col2, steps = next_match.groups()
        steps = int(steps) if steps else 1
        
        def next_condition(row, ctx):
            left_val = row.get(col1.strip(), 0)
            next_row = ctx.next(steps)
            right_val = next_row.get(col2.strip()) if next_row else None
            
            # Handle NULL comparison
            if right_val is None:
                return False
                
            # Use the appropriate comparison operator
            if op == ">=":
                return left_val >= right_val
            elif op == ">":
                return left_val > right_val
            elif op == "<=":
                return left_val <= right_val
            elif op == "<":
                return left_val < right_val
            elif op == "==" or op == "=":
                return left_val == right_val
            elif op == "!=":
                return left_val != right_val
            return False
            
        return next_condition
    
    # ... rest of method ...

    # FIRST function
    first_match = re.match(r'(.*?)\s*([<>=!]+)\s*FIRST\((.*?)\)', expr)
    if first_match:
        col1, op, arg = first_match.groups()
        var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.(.*)', arg)
        if var_col_match:
            var, col2 = var_col_match.groups()
            
            def first_condition(row, ctx):
                left_val = row.get(col1.strip(), 0)
                first_row = ctx.first(var)
                right_val = first_row.get(col2) if first_row else None
                
                # Handle NULL comparison
                if right_val is None:
                    return False
                    
                if op == ">=":
                    return left_val >= right_val
                elif op == ">":
                    return left_val > right_val
                elif op == "<=":
                    return left_val <= right_val
                elif op == "<":
                    return left_val < right_val
                elif op == "==" or op == "=":
                    return left_val == right_val
                elif op == "!=":
                    return left_val != right_val
                return False
                
            return first_condition
    
    # Handle simple comparisons
    simple_comp_match = re.match(r'(.*?)\s*([<>=!]+)\s*([\d.]+)', expr)
    if simple_comp_match:
        col, op, val = simple_comp_match.groups()
        val = float(val)
        if op == ">=":
            return lambda row, ctx: row.get(col.strip(), 0) >= val
        elif op == ">":
            return lambda row, ctx: row.get(col.strip(), 0) > val
        elif op == "<=":
            return lambda row, ctx: row.get(col.strip(), 0) <= val
        elif op == "<":
            return lambda row, ctx: row.get(col.strip(), 0) < val
        elif op == "==" or op == "=":
            return lambda row, ctx: row.get(col.strip(), 0) == val
        elif op == "!=":
            return lambda row, ctx: row.get(col.strip(), 0) != val
    
    # If all else fails, try AST parsing with added support for functions
    try:
        modified_expr = expr
        
        # Replace return with row access
        if "return" in modified_expr:
            modified_expr = modified_expr.replace("return", "row.get('return', 0)")
        
        tree = ast.parse(modified_expr, mode='eval')
        
        def evaluator(row: Dict[str, Any], context: RowContext) -> bool:
            # Create globals with math functions
            import math
            
            # Helper functions with NULL handling
            def safe_prev(col, steps=1):
                prev_row = context.prev(steps)
                return prev_row.get(col) if prev_row else None
                
            def safe_next(col, steps=1):
                next_row = context.next(steps)
                return next_row.get(col) if next_row else None
                
            def safe_first(var, col):
                first_row = context.first(var)
                return first_row.get(col) if first_row else None
                
            def safe_last(var, col):
                last_row = context.last(var)
                return last_row.get(col) if last_row else None
            
            globals_dict = {
                'row': row, 
                'context': context,
                'ABS': abs,
                'ROUND': round,
                'SQRT': math.sqrt,
                'POWER': pow,
                'CEILING': math.ceil,
                'FLOOR': math.floor,
                'MOD': lambda x, y: x % y,
                'PREV': safe_prev,
                'NEXT': safe_next,
                'FIRST': safe_first,
                'LAST': safe_last
            }
            
            try:
                result = eval(modified_expr, globals_dict)
                return bool(result) if result is not None else False
            except Exception as e:
                print(f"Error evaluating expression '{modified_expr}': {e}")
                return False
                
        return evaluator
    except SyntaxError as e:
        print(f"Syntax error parsing: '{expr}'")
        print(f"Error details: {e}")
        # Fallback to TRUE
        return lambda row, ctx: True
