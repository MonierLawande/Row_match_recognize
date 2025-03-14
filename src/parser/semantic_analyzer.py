# src/parser/semantic_analyzer.py

from typing import Optional, List, Dict, Set
from src.ast.expression_ast import ExpressionAST
from .error_handler import ErrorHandler
from .symbol_table import SymbolTable, SymbolType

class SemanticAnalyzer:
    """
    Semantic analyzer for SQL expressions in MATCH_RECOGNIZE context.
    Performs type checking, validation of aggregate functions, etc.
    """
    
    def __init__(self, error_handler: Optional[ErrorHandler] = None):
        self.error_handler = error_handler or ErrorHandler()
        self.symbol_table = SymbolTable()
        
    def analyze_expression(self, expr_ast: ExpressionAST, context: str = "expression"):
        """
        Analyze an expression AST for semantic errors.
        
        Args:
            expr_ast: The expression AST to analyze
            context: Context string for error messages
        """
        # Validate aggregate functions
        self.validate_aggregate_functions(expr_ast, context)
        
        # Additional semantic checks could be added here
        
    def validate_aggregate_functions(self, expr_ast: ExpressionAST, context: str):
        """
        Validate aggregate function usage.
        Only direct nested aggregates (i.e. an aggregate function immediately inside another aggregate)
        are disallowed.
        """
        def check_nested(node: ExpressionAST, parent_is_aggregate: bool = False):
            if node.type == "aggregate":
                if parent_is_aggregate:
                    self.error_handler.add_error(
                        "Nested aggregate functions are not allowed",
                        getattr(node, 'line', 0),
                        getattr(node, 'column_pos', 0)
                    )
                current_parent = True
            else:
                current_parent = False
            for child in node.children:
                check_nested(child, current_parent)
        check_nested(expr_ast)
