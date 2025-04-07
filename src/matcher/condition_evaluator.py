# src/matcher/condition_evaluator.py

import ast
import operator
import re
from typing import Dict, Any, Optional, Callable, List
from src.matcher.row_context import RowContext

class ConditionEvaluator(ast.NodeVisitor):
    def __init__(self, context: RowContext):
        self.context = context

    def visit_Compare(self, node: ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("Only simple comparisons are supported")
        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
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
        return func(left, right)

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
            return self.context.classifier()
        elif node.id.upper() == "MATCH_NUMBER":
            return self.context.match_number
            
        # Regular variable - get from current row
        return self.context.rows[self.context.current_idx].get(node.id)

    def visit_Call(self, node: ast.Call):
        """Handle function calls (PREV, NEXT, etc.)"""
        func = self.visit(node.func)
        if callable(func):
            args = [self.visit(arg) for arg in node.args]
            return func(*args)
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

    def visit_BoolOp(self, node: ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(self.visit(v) for v in node.values)
        elif isinstance(node.op, ast.Or):
            return any(self.visit(v) for v in node.values)
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
            
        return func(left, right)
    
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
    
    def visit_Str(self, node: ast.Str):
        """Handle string literals for Python < 3.8"""
        return node.s
    
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
        """Handle subscript expressions like a[b]"""
        value = self.visit(node.value)
        if isinstance(node.slice, ast.Index):
            # Python < 3.9
            idx = self.visit(node.slice.value)
        else:
            # Python >= 3.9
            idx = self.visit(node.slice)
        
        if value is None:
            return None
            
        try:
            return value[idx]
        except (TypeError, KeyError, IndexError):
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
        """Implementation of PREV function."""
        row = self.context.prev(steps)
        return row.get(column) if row else None

    def _get_next_value(self, column: str, steps: int = 1) -> Any:
        """Implementation of NEXT function."""
        row = self.context.next(steps)
        return row.get(column) if row else None

    def _get_first_value(self, variable: str, column: str, occurrence: int = 0) -> Any:
        """Implementation of FIRST function."""
        row = self.context.first(variable, occurrence)
        return row.get(column) if row else None

    def _get_last_value(self, variable: str, column: str, occurrence: int = 0) -> Any:
        """Implementation of LAST function."""
        row = self.context.last(variable, occurrence)
        return row.get(column) if row else None

def compile_condition(expr: str) -> Callable[[Dict[str, Any], RowContext], bool]:
    """Compile a condition expression into a function."""
    tree = ast.parse(expr, mode='eval')
    
    def evaluator(row: Dict[str, Any], context: RowContext) -> bool:
        context.rows.append(row)
        context.current_idx = len(context.rows) - 1
        try:
            result = ConditionEvaluator(context).visit(tree.body)
            return bool(result) if result is not None else False
        except Exception as e:
            print(f"Error evaluating condition '{expr}': {e}")
            return False
        finally:
            context.rows.pop()
            context.current_idx = len(context.rows) - 1 if context.rows else 0
            
    return evaluator
