# src/semantic/type_system.py
#from src.semantic.type_system import TypeInferer

from typing import Optional
from src.ast.expression_ast import ExpressionAST

class TypeInferer:
    """Centralized type inference for expressions"""

    @staticmethod
    def infer_type(ast: ExpressionAST) -> str:
        """Infer the type of an expression"""
        if ast.type == "literal":
            # Try to infer type from literal value
            try:
                int(ast.value)
                return "integer"
            except ValueError:
                try:
                    float(ast.value)
                    return "float"
                except ValueError:
                    if ast.value.lower() in ("true", "false"):
                        return "boolean"
                    return "string"
        elif ast.type == "binary":
            # For binary operations, infer based on operator and operands
            if ast.operator in ("+", "-", "*", "/"):
                left_type = TypeInferer.infer_type(ast.children[0])
                right_type = TypeInferer.infer_type(ast.children[1])
                if left_type in ("integer", "float") and right_type in ("integer", "float"):
                    return "float" if "float" in (left_type, right_type) else "integer"
                if left_type == "string" and right_type == "string" and ast.operator == "+":
                    return "string"
            elif ast.operator in ("=", "!=", "<", ">", "<=", ">="):
                return "boolean"
        elif ast.type == "aggregate":
            # Infer type based on aggregate function
            func = ast.value.lower()
            if func in ("count", "sum"):
                return "integer"
            elif func in ("avg", "min", "max"):
                return "float"
            elif func in ("min_by", "max_by"):
                return "any"
        elif ast.type == "navigation":
            # Navigation functions return the same type as their target
            if ast.children:
                return TypeInferer.infer_type(ast.children[0])
                
        # Default type when we can't infer
        return "any"
        
    @staticmethod
    def are_types_compatible(type1: str, type2: str) -> bool:
        """Check if two types are compatible for operations"""
        if type1 == type2:
            return True
        if type1 == "any" or type2 == "any":
            return True
        if type1 in ("integer", "float") and type2 in ("integer", "float"):
            return True
        return False
