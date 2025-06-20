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
    def __init__(self, context: RowContext, evaluation_mode='DEFINE', recursion_depth=0):
        """
        Initialize condition evaluator with context-aware navigation.
        
        Args:
            context: RowContext for pattern matching
            evaluation_mode: 'DEFINE' for physical navigation, 'MEASURES' for logical navigation
            recursion_depth: Current recursion depth to prevent infinite recursion (optional)
        """
        self.context = context
        self.current_row = None
        self.evaluation_mode = evaluation_mode  # 'DEFINE' or 'MEASURES'
        self.recursion_depth = recursion_depth  # Track recursion depth
        self.max_recursion_depth = 10  # Maximum allowed recursion depth
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
            'CONCAT': lambda *args: ''.join(str(arg) for arg in args if arg is not None),
            'TRIM': lambda s: str(s).strip() if s is not None else None,
            'LTRIM': lambda s: str(s).lstrip() if s is not None else None,
            'RTRIM': lambda s: str(s).rstrip() if s is not None else None,
            
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
        
        # If op is a callable, use it directly; otherwise map from AST type
        if callable(op):
            return op(left, right)
        else:
            op_func = op_map.get(type(op))
            if op_func:
                return op_func(left, right)
            else:
                raise ValueError(f"Unsupported comparison operator: {type(op)}")

    def visit_Compare(self, node: ast.Compare):
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
        logger = get_logger(__name__)
        if self.evaluation_mode == 'DEFINE':
            logger.debug(f"[DEBUG] COMPARE: left={left} ({type(left)}), op={op.__class__.__name__}")
        
        # Handle IN operator specially
        if isinstance(op, ast.In):
            # For IN operator, we need to check if left is in any of the comparators
            # IN expects a list/tuple on the right side
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
            logger.debug(f"[DEBUG] COMPARE AST: left={ast.dump(node.left)}, right={ast.dump(node.comparators[0])}")
        
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
            raise ValueError(f"Operator {op.__class__.__name__} not supported")
            
        result = self._safe_compare(left, right, func)
        
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
            elif hasattr(ast, 'Num') and isinstance(arg, ast.Num):
                # Python < 3.8 compatibility - ast.Num is deprecated in Python 3.14+
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
                        getattr(self.context, 'current_var', None),
                        self.recursion_depth + 1
                    )
                else:
                    # Fixed: Handle AST nodes directly instead of using faulty _extract_navigation_args
                    if len(node.args) == 0:
                        raise ValueError(f"{func_name} function requires at least one argument")
                    
                    # Get the first argument which should be either ast.Name or ast.Attribute
                    first_arg = node.args[0]
                    
                    # Get optional steps argument first (for all patterns)
                    steps = 1
                    if len(node.args) > 1:
                        steps_arg = node.args[1]
                        if isinstance(steps_arg, ast.Constant):
                            steps = steps_arg.value
                        elif hasattr(ast, 'Num') and isinstance(steps_arg, ast.Num):
                            steps = steps_arg.n
                    
                    if isinstance(first_arg, ast.Attribute) and isinstance(first_arg.value, ast.Name):
                        # Pattern: NEXT(A.value) - variable.column format
                        var_name = first_arg.value.id
                        column = first_arg.attr
                        
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
                            logger.debug(f"[DEBUG] Calling _get_navigation_value for {func_name}({var_name}.{column}) in visit_Call")
                            result = self._get_navigation_value(var_name, column, func_name, steps)
                            logger.debug(f"[DEBUG] _get_navigation_value returned: {result} for {func_name}({var_name}.{column})")
                            return result
                            
                    elif isinstance(first_arg, ast.Attribute) and isinstance(first_arg.value, ast.Constant):
                        # Pattern: NEXT("b".value) - quoted variable.column format
                        var_name = f'"{first_arg.value.value}"'  # Preserve quotes for consistency
                        column = first_arg.attr
                        
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
                            logger.debug(f"[DEBUG] Calling _get_navigation_value for {func_name}({var_name}.{column}) in visit_Call (quoted)")
                            result = self._get_navigation_value(var_name, column, func_name, steps)
                            logger.debug(f"[DEBUG] _get_navigation_value returned: {result} for {func_name}({var_name}.{column}) (quoted)")
                            return result
                            
                    elif isinstance(first_arg, ast.Name):
                        # Pattern: NEXT(column) - simple column format
                        column = first_arg.id
                        
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
                    elif isinstance(first_arg, ast.Call):
                        # Handle nested function calls like NEXT(CLASSIFIER())
                        if isinstance(first_arg.func, ast.Name) and first_arg.func.id.upper() == "CLASSIFIER":
                            # Special case: NEXT(CLASSIFIER()) - navigate through classifier values
                            if func_name in ("PREV", "NEXT"):
                                # For PREV/NEXT with CLASSIFIER, we need to get the classifier value at the target position
                                current_idx = self.context.current_idx
                                target_idx = current_idx + steps if func_name == "NEXT" else current_idx - steps
                                
                                # Check bounds
                                if target_idx < 0 or target_idx >= len(self.context.rows):
                                    return None
                                
                                # Create a temporary context for the target position
                                temp_context = RowContext(
                                    rows=self.context.rows,
                                    variables=self.context.variables,
                                    current_idx=target_idx,
                                    match_number=self.context.match_number
                                )
                                
                                # Get the classifier value at that position
                                temp_evaluator = ConditionEvaluator(temp_context, self.evaluation_mode)
                                return temp_evaluator._get_classifier()
                            else:
                                # For FIRST/LAST with CLASSIFIER, implement support
                                if func_name.upper() == 'LAST':
                                    # Get the last classifier in the match
                                    if self.context.current_match and len(self.context.current_match) > 0:
                                        last_row_index = self.context.current_match[-1]['row_index']
                                        temp_context = RowContext(
                                            self.context.partition,
                                            self.context.partition_index,
                                            last_row_index,
                                            self.context.pattern_variables,
                                            self.context.current_match,
                                            self.context.subset_variables
                                        )
                                        temp_evaluator = ConditionEvaluator(temp_context, self.evaluation_mode)
                                        return temp_evaluator._get_classifier()
                                    else:
                                        return None
                                else:
                                    # For FIRST(CLASSIFIER()), not yet fully supported
                                    logger.error(f"{func_name}(CLASSIFIER()) not yet supported")
                                    return None
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
                                    return self._get_navigation_value(None, column, func_name, steps)
                            else:
                                return None
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
        
        logger.debug(f"[NAV_DEBUG] _get_navigation_value: var_name={var_name}, column={column}, nav_type={nav_type}, steps={steps}")
        logger.debug(f"[NAV_DEBUG] Current context.variables: {self.context.variables}")
        logger.debug(f"[NAV_DEBUG] Current context.current_idx: {self.context.current_idx}")
        logger.debug(f"[NAV_DEBUG] Current evaluation_mode: {self.evaluation_mode}")
        
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
                logger.debug(f"[NAV_DEBUG] Fast path exit: curr_idx={curr_idx}, rows_len={len(self.context.rows) if self.context.rows else 0}")
                self.context.navigation_cache[cache_key] = None
                return None
            
            # Enhanced subset variable handling for logical navigation (FIRST/LAST)
            if nav_type in ('FIRST', 'LAST') and var_name in self.context.subsets:
                logger.debug(f"[NAV_DEBUG] Subset variable path for {var_name}")
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
            
            logger.debug(f"[NAV_DEBUG] Past subset check, checking if var_name is subset: var_name={var_name}, subsets={getattr(self.context, 'subsets', {})}")
            
            # Optimized timeline building with caching
            # Build a timeline of all pattern variables in this match
            if hasattr(self.context, '_timeline') and not getattr(self.context, '_timeline_dirty', True):
                timeline = self.context._timeline
                logger.debug(f"[NAV_DEBUG] Using cached timeline: {timeline}")
            else:
                logger.debug(f"[NAV_DEBUG] Building new timeline from variables: {self.context.variables}")
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
            
            result = None
            
            # Enhanced logical positioning functions (FIRST/LAST)
            if nav_type in ('FIRST', 'LAST'):
                logger.debug(f"[NAV_DEBUG] Processing {nav_type} navigation for var_name={var_name}")
                if var_name is None:
                    # FIRST(column) or LAST(column) - look across all variables in the match
                    all_indices = []
                    for var, indices in self.context.variables.items():
                        all_indices.extend(indices)
                    
                    if not all_indices:
                        logger.debug(f"[NAV_DEBUG] No indices found for var_name=None case")
                        self.context.navigation_cache[cache_key] = None
                        return None
                    
                    # Sort indices and select first or last
                    all_indices = sorted(set(all_indices))
                    idx = all_indices[0] if nav_type == 'FIRST' else all_indices[-1]
                    logger.debug(f"[NAV_DEBUG] var_name=None: all_indices={all_indices}, selected idx={idx}")
                    
                elif var_name not in self.context.variables or not self.context.variables[var_name]:
                    logger.debug(f"[NAV_DEBUG] Variable {var_name} not found in context.variables or empty")
                    self.context.navigation_cache[cache_key] = None
                    return None
                else:
                    # Get sorted indices with duplication handling
                    var_indices = sorted(set(self.context.variables[var_name]))
                    logger.debug(f"[NAV_DEBUG] Variable {var_name} indices: {var_indices}")
                    
                    if not var_indices:
                        logger.debug(f"[NAV_DEBUG] No indices for variable {var_name}")
                        self.context.navigation_cache[cache_key] = None
                        return None
                    
                    # Select appropriate index based on navigation type
                    idx = var_indices[0] if nav_type == 'FIRST' else var_indices[-1]
                    logger.debug(f"[NAV_DEBUG] Selected idx={idx} for {nav_type}({var_name})")
                
                # Check partition boundaries if defined
                if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
                    curr_partition = self.context.get_partition_for_row(curr_idx)
                    target_partition = self.context.get_partition_for_row(idx)
                    
                    # Enforce partition boundaries
                    if curr_partition != target_partition or curr_partition is None or target_partition is None:
                        logger.debug(f"[NAV_DEBUG] Partition boundary violation: curr={curr_partition}, target={target_partition}")
                        self.context.navigation_cache[cache_key] = None
                        return None
                
                # Bounds checking with advanced error handling
                logger.debug(f"[NAV_DEBUG] Bounds check: idx={idx}, len(self.context.rows)={len(self.context.rows)}")
                if 0 <= idx < len(self.context.rows):
                    result = self.context.rows[idx].get(column)
                    logger.debug(f"[NAV_DEBUG] Got result: {result} from row {idx}, column {column}")
                    logger.debug(f"[NAV_DEBUG] Row data at idx {idx}: {self.context.rows[idx]}")
                else:
                    result = None
                    logger.debug(f"[NAV_DEBUG] Index {idx} out of bounds (rows length: {len(self.context.rows)})")
                
                # Cache and return the result for FIRST/LAST
                logger.debug(f"[NAV_DEBUG] Caching and returning FIRST/LAST result: {result}")
                self.context.navigation_cache[cache_key] = result
                return result
            
            
            # Enhanced physical navigation (PREV/NEXT) with optimized algorithms
            elif nav_type in ('PREV', 'NEXT'):
                # Empty timeline indicates incomplete match state for PREV/NEXT navigation
                if not timeline:
                    self.context.navigation_cache[cache_key] = None
                    return None
                
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
            elif hasattr(ast, 'Num') and isinstance(arg, getattr(ast, 'Num', type(None))):
                # Numeric literal (Python < 3.8) - deprecated but handle gracefully
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
        """Handle boolean operations (AND, OR)"""
        if isinstance(node.op, ast.And):
            # For AND, all values must be True
            for value in node.values:
                result = self.visit(value)
                if not result:
                    return False
            return True
        elif isinstance(node.op, ast.Or):
            # For OR, at least one value must be True
            for value in node.values:
                result = self.visit(value)
                if result:
                    return True
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
                return bool(result)
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


def evaluate_nested_navigation(expr: str, context: RowContext, current_idx: int, current_var: Optional[str] = None, recursion_depth: int = 0) -> Any:
    """
    Evaluate nested navigation expressions.
    
    This function handles complex navigation expressions that may contain nested function calls
    like NEXT(PREV(value)) or FIRST(CLASSIFIER()), and SQL-specific constructs like 
    PREV(RUNNING LAST(value)).
    
    Args:
        expr: The navigation expression string to evaluate
        context: The row context for evaluation
        current_idx: Current row index
        current_var: Current pattern variable (optional)
        
    Returns:
        The evaluated result
    """
    try:
        import re
        
        # Check recursion depth early
        max_recursion_depth = 10
        if recursion_depth >= max_recursion_depth:
            logger.warning(f"Maximum recursion depth {max_recursion_depth} reached for expression: '{expr}', returning None")
            return None
        
        # Handle SQL-specific constructs that aren't valid Python syntax
        processed_expr = expr
        
        # Handle complex arithmetic expressions with multiple navigation functions
        # Pattern: PREV(LAST(A.value), 3) + FIRST(A.value) + PREV(LAST(B.value), 2)
        arithmetic_nav_pattern = r'.*(?:PREV|NEXT|FIRST|LAST)\s*\(.*[\+\-\*\/].*(?:PREV|NEXT|FIRST|LAST)\s*\('
        if re.search(arithmetic_nav_pattern, processed_expr, re.IGNORECASE):
            logger.debug(f"Detected complex arithmetic expression with navigation functions: {processed_expr}")
            
            # For complex arithmetic expressions, we need to parse and evaluate using AST
            # But first ensure we're in the right context for evaluation
            try:
                import ast
                tree = ast.parse(processed_expr, mode='eval')
                evaluator = ConditionEvaluator(context, 'MEASURES', recursion_depth + 1)
                evaluator.current_row = context.rows[current_idx] if 0 <= current_idx < len(context.rows) else None
                result = evaluator.visit(tree.body)
                logger.debug(f"Complex arithmetic navigation result: {result}")
                return result
            except Exception as e:
                logger.debug(f"Failed to evaluate complex arithmetic expression via AST: {e}")
                # Fall through to other methods
        
        # Handle complex nested navigation patterns like PREV(LAST(A.value), 3)
        complex_nav_pattern = r'(PREV|NEXT)\s*\(\s*(FIRST|LAST)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*(?:,\s*(\d+))?\s*\)'
        complex_nav_match = re.match(complex_nav_pattern, processed_expr, re.IGNORECASE)
        
        if complex_nav_match:
            outer_func = complex_nav_match.group(1).upper()  # PREV or NEXT
            inner_func = complex_nav_match.group(2).upper()  # FIRST or LAST
            column_ref = complex_nav_match.group(3)          # A.value
            steps = int(complex_nav_match.group(4)) if complex_nav_match.group(4) else 1
            
            logger.debug(f"Processing complex navigation: {outer_func}({inner_func}({column_ref}), {steps})")
            
            # Extract variable and column
            var_name, col_name = column_ref.split('.', 1)
            
            # First, find the FIRST/LAST row index for the variable using context.variables
            if hasattr(context, 'variables') and var_name in context.variables:
                var_indices = context.variables[var_name]
                logger.debug(f"Found variable {var_name} with indices: {var_indices}")
                
                if var_indices:
                    if inner_func == 'FIRST':
                        target_base_idx = min(var_indices)
                    else:  # LAST
                        target_base_idx = max(var_indices)
                    
                    logger.debug(f"Using {inner_func} index: {target_base_idx} for variable {var_name}")
                    
                    # Now apply PREV/NEXT with steps
                    if outer_func == 'PREV':
                        final_idx = target_base_idx - steps
                    else:  # NEXT
                        final_idx = target_base_idx + steps
                    
                    logger.debug(f"Final index after {outer_func} with steps {steps}: {final_idx}")
                    
                    # Get the value at the final index
                    if hasattr(context, 'rows') and 0 <= final_idx < len(context.rows):
                        result = context.rows[final_idx].get(col_name)
                        logger.debug(f"Complex navigation result: {result} from row {final_idx}")
                        return result
                    else:
                        logger.debug(f"Complex navigation index {final_idx} out of bounds (total rows: {len(context.rows) if hasattr(context, 'rows') else 'unknown'})")
                        return None
                else:
                    logger.debug(f"Variable {var_name} has no matched rows")
                    return None
            else:
                logger.debug(f"Variable {var_name} not found in context.variables: {getattr(context, 'variables', {})}")
                return None
        
        # Handle CLASSIFIER() inside navigation functions
        classifier_nav_pattern = r'(FIRST|LAST)\s*\(\s*CLASSIFIER\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)?\s*\)\s*\)'
        classifier_nav_match = re.match(classifier_nav_pattern, processed_expr, re.IGNORECASE)
        
        if classifier_nav_match:
            nav_func = classifier_nav_match.group(1).upper()  # FIRST or LAST
            classifier_var = classifier_nav_match.group(2)  # Optional variable name
            
            logger.debug(f"Processing {nav_func}(CLASSIFIER({classifier_var}))")
            
            # Get the match variable assignments from context
            if hasattr(context, 'variables') and context.variables:
                var_assignments = context.variables
                
                if nav_func == 'LAST':
                    # Find the last row in the match and get its classifier
                    max_idx = -1
                    last_classifier = None
                    
                    for var_name, indices in var_assignments.items():
                        if indices:
                            for idx in indices:
                                if idx > max_idx:
                                    max_idx = idx
                                    # Apply case sensitivity rules for classifier
                                    if hasattr(context, 'defined_variables') and context.defined_variables:
                                        if var_name.lower() in [v.lower() for v in context.defined_variables]:
                                            # Preserve original case for defined variables
                                            last_classifier = var_name
                                        else:
                                            # Uppercase for undefined variables
                                            last_classifier = var_name.upper()
                                    else:
                                        # Default to uppercase if no defined_variables info
                                        last_classifier = var_name.upper()
                    
                    logger.debug(f"LAST(CLASSIFIER()) -> last row index: {max_idx}, classifier: '{last_classifier}'")
                    return last_classifier
                    
                elif nav_func == 'FIRST':
                    # Find the first row in the match and get its classifier
                    min_idx = float('inf')
                    first_classifier = None
                    
                    for var_name, indices in var_assignments.items():
                        if indices:
                            for idx in indices:
                                if idx < min_idx:
                                    min_idx = idx
                                    # Apply case sensitivity rules
                                    if hasattr(context, 'defined_variables') and context.defined_variables:
                                        if var_name.lower() in [v.lower() for v in context.defined_variables]:
                                            first_classifier = var_name
                                        else:
                                            first_classifier = var_name.upper()
                                    else:
                                        first_classifier = var_name.upper()
                    
                    logger.debug(f"FIRST(CLASSIFIER()) -> first row index: {min_idx}, classifier: '{first_classifier}'")
                    return first_classifier
            
            # Fallback: return None if no variable assignments found
            logger.debug(f"{nav_func}(CLASSIFIER()) -> no variable assignments found")
            return None
        
        # Handle RUNNING/FINAL semantic modifiers with navigation functions
        # Pattern: PREV(RUNNING LAST(value)) -> PREV(value) with RUNNING semantics
        running_pattern = r'(PREV|NEXT)\s*\(\s*RUNNING\s+(LAST|FIRST)\s*\(\s*([^)]+)\s*\)\s*(?:,\s*(\d+))?\s*\)'
        running_match = re.match(running_pattern, processed_expr, re.IGNORECASE)
        
        if running_match:
            outer_func = running_match.group(1).upper()  # PREV or NEXT
            inner_func = running_match.group(2).upper()  # LAST or FIRST
            column_ref = running_match.group(3)  # value
            steps = int(running_match.group(4)) if running_match.group(4) else 1
            
            logger.debug(f"Processing {outer_func}(RUNNING {inner_func}({column_ref}))")
            
            # For RUNNING semantics, we need to:
            # 1. First get the RUNNING LAST/FIRST value at current position
            # 2. Then apply PREV/NEXT to that result
            
            if inner_func == "LAST":
                # RUNNING LAST(value): Get the last value among matched rows up to current position
                # This should be current row's value for simple cases
                if current_idx >= 0 and current_idx < len(context.rows):
                    running_value = context.rows[current_idx].get(column_ref.strip())
                    logger.debug(f"RUNNING LAST({column_ref}) at index {current_idx}: {running_value}")
                    
                    # Now apply PREV/NEXT to this position
                    if outer_func == "PREV":
                        target_idx = current_idx - steps
                    else:  # NEXT
                        target_idx = current_idx + steps
                    
                    # Check bounds and get value
                    if target_idx >= 0 and target_idx < len(context.rows):
                        result = context.rows[target_idx].get(column_ref.strip())
                        logger.debug(f"{outer_func}(RUNNING LAST({column_ref})) -> target_idx={target_idx}, result={result}")
                        return result
                    else:
                        logger.debug(f"{outer_func}(RUNNING LAST({column_ref})) -> target_idx={target_idx} out of bounds")
                        return None
                else:
                    return None
            elif inner_func == "FIRST":
                # RUNNING FIRST(value): Similar logic for FIRST
                if current_idx >= 0 and current_idx < len(context.rows):
                    # For RUNNING FIRST, we would need to find the first value in the current match sequence
                    # For simplicity, use current row's value (this may need refinement)
                    running_value = context.rows[current_idx].get(column_ref.strip())
                    
                    # Apply PREV/NEXT
                    if outer_func == "PREV":
                        target_idx = current_idx - steps
                    else:  # NEXT
                        target_idx = current_idx + steps
                    
                    if target_idx >= 0 and target_idx < len(context.rows):
                        result = context.rows[target_idx].get(column_ref.strip())
                        return result
                    else:
                        return None
                else:
                    return None
        
        # Handle FINAL semantic modifiers similarly
        final_pattern = r'(PREV|NEXT)\s*\(\s*FINAL\s+(LAST|FIRST)\s*\(\s*([^)]+)\s*\)\s*(?:,\s*(\d+))?\s*\)'
        final_match = re.match(final_pattern, processed_expr, re.IGNORECASE)
        
        if final_match:
            # Similar processing for FINAL semantics
            outer_func = final_match.group(1).upper()
            inner_func = final_match.group(2).upper()
            column_ref = final_match.group(3)
            steps = int(final_match.group(4)) if final_match.group(4) else 1
            
            if current_idx >= 0 and current_idx < len(context.rows):
                if outer_func == "PREV":
                    target_idx = current_idx - steps
                else:  # NEXT
                    target_idx = current_idx + steps
                
                if target_idx >= 0 and target_idx < len(context.rows):
                    result = context.rows[target_idx].get(column_ref.strip())
                    return result
                else:
                    return None
            else:
                return None
        
        # If no special SQL constructs, try to parse as Python AST
        tree = ast.parse(processed_expr, mode='eval')
        
        # Create a new evaluator for this expression with recursion depth check
        max_recursion_depth = 10  # Define max recursion depth at function level
        if recursion_depth >= max_recursion_depth:
            logger.warning(f"Maximum recursion depth {max_recursion_depth} reached for expression: '{expr}', returning None")
            return None
            
        evaluator = ConditionEvaluator(context, evaluation_mode='MEASURES', recursion_depth=recursion_depth + 1)
        
        # Evaluate the parsed expression
        result = evaluator.visit(tree.body)
        
        logger.debug(f"Nested navigation evaluation: '{expr}' -> {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error evaluating nested navigation '{expr}': {e}")
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
    
    # Convert SQL equality to Python equality
    # Handle cases like 'value = 10' -> 'value == 10'
    # But avoid changing '==' to '===='
    import re
    
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
    
    # Handle empty IN predicates - convert to always false/true
    condition = re.sub(r'\bIN\s*\(\s*\)', 'in []', condition, flags=re.IGNORECASE)
    condition = re.sub(r'\bNOT\s+IN\s*\(\s*\)', 'not in []', condition, flags=re.IGNORECASE)
    
    return condition