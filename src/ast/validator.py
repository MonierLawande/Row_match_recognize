# src/ast/validator.py

from src.parser.error_handler import ErrorHandler
from src.parser.symbol_table import SymbolTable
from src.ast.visitor import PatternVisitor, ExpressionVisitor
from src.ast.pattern_ast import PatternAST
from src.ast.expression_ast import ExpressionAST
from src.ast.match_recognize_ast import MatchRecognizeAST

class UnifiedValidator:
    """Unified validator for all AST components"""
    
    def __init__(self):
        self.error_handler = ErrorHandler()
        self.symbol_table = SymbolTable()
        self.pattern_validator = PatternValidator(self.error_handler, self.symbol_table)
        self.expression_validator = ExpressionValidator(self.error_handler, self.symbol_table)
        
    def validate_match_recognize(self, ast: MatchRecognizeAST):
        """Validate a complete MATCH_RECOGNIZE clause"""
        # First validate pattern to collect pattern variables
        if ast.pattern and "ast" in ast.pattern:
            self.pattern_validator.visit_pattern_ast(ast.pattern["ast"])
            
        # Then validate measures
        for measure in ast.measures:
            if "expression" in measure and "ast" in measure["expression"]:
                self.expression_validator.visit_expression_ast(
                    measure["expression"]["ast"], 
                    context="MEASURES",
                    in_measures=True
                )
                
        # Then validate define conditions
        for define in ast.define:
            if "condition" in define and "ast" in define["condition"]:
                self.expression_validator.visit_expression_ast(
                    define["condition"]["ast"],
                    context=f"DEFINE {define['variable']}",
                    in_measures=False
                )
                
        # Cross-validate between clauses
        self._cross_validate_clauses(ast)
        
        return {
            "errors": self.error_handler.get_formatted_errors(),
            "warnings": self.error_handler.get_formatted_warnings()
        }
        
    def _cross_validate_clauses(self, ast: MatchRecognizeAST):
        """Perform cross-clause validations"""
        # Check that all pattern variables are defined
        pattern_vars = set(self.symbol_table.get_symbols_by_type("pattern_variable"))
        defined_vars = {define["variable"] for define in ast.define}
        undefined_vars = pattern_vars - defined_vars
        
        if undefined_vars:
            self.error_handler.add_warning(
                f"Pattern variables not defined in DEFINE clause: {', '.join(undefined_vars)}",
                0, 0
            )
            
        # Check that SKIP TO variable exists in pattern
        if ast.skip_to_variable and ast.skip_to_variable not in pattern_vars:
            self.error_handler.add_error(
                f"SKIP TO variable '{ast.skip_to_variable}' not defined in pattern",
                0, 0
            )

class PatternValidator(PatternVisitor):
    """Validator for pattern AST nodes"""
    
    def __init__(self, error_handler, symbol_table):
        self.error_handler = error_handler
        self.symbol_table = symbol_table
        self.nesting_level = 0
        
    def pre_visit(self, ast: PatternAST):
        self.nesting_level += 1
        
    def post_visit(self, ast: PatternAST):
        self.nesting_level -= 1
        
    def visit_literal(self, ast: PatternAST):
        # Register pattern variable
        self.symbol_table.add_symbol(
            ast.value, 
            "pattern_variable",
            ast.line, 
            ast.column
        )
        
    def visit_quantifier(self, ast: PatternAST):
        # Validate quantifier values
        if ast.quantifier_min is not None and ast.quantifier_min < 0:
            self.error_handler.add_error(
                f"Negative quantifier minimum {ast.quantifier_min}",
                ast.line, ast.column
            )
            
        if (ast.quantifier_max is not None and 
                ast.quantifier_min is not None and 
                ast.quantifier_max < ast.quantifier_min):
            self.error_handler.add_error(
                f"Quantifier maximum less than minimum",
                ast.line, ast.column
            )
            
        # Visit children
        for child in ast.children:
            self.visit_pattern_ast(child)

class ExpressionValidator(ExpressionVisitor):
    """Validator for expression AST nodes"""
    
    def __init__(self, error_handler, symbol_table):
        self.error_handler = error_handler
        self.symbol_table = symbol_table
        self.in_aggregate = False
        self.in_navigation = False
        self.context = "expression"
        self.in_measures = True
        
    def visit_expression_ast(self, ast: ExpressionAST, context=None, in_measures=True):
        """Visit with context information"""
        if context:
            self.context = context
        self.in_measures = in_measures
        return super().visit_expression_ast(ast)
        
    def visit_aggregate(self, ast: ExpressionAST):
        # Check for nested aggregates
        if self.in_aggregate:
            self.error_handler.add_error(
                f"In {self.context}: Nested aggregate functions are not allowed",
                ast.line, ast.column
            )
            
        # Track aggregate state
        old_in_aggregate = self.in_aggregate
        self.in_aggregate = True
        
        # Visit children
        for child in ast.children:
            self.visit_expression_ast(child)
            
        # Restore state
        self.in_aggregate = old_in_aggregate
        
    def visit_navigation(self, ast: ExpressionAST):
        # Check for navigation inside aggregate
        if self.in_aggregate:
            self.error_handler.add_error(
                f"In {self.context}: Navigation functions cannot be used inside aggregate functions",
                ast.line, ast.column
            )
            
        # Track navigation state
        old_in_navigation = self.in_navigation
        self.in_navigation = True
        
        # Visit children
        for child in ast.children:
            self.visit_expression_ast(child)
            
        # Restore state
        self.in_navigation = old_in_navigation
        
    def visit_pattern_variable_reference(self, ast: ExpressionAST):
        # Check that pattern variable exists
        if not self.symbol_table.has_symbol(ast.pattern_variable, "pattern_variable"):
            self.error_handler.add_warning(
                f"In {self.context}: Reference to undefined pattern variable '{ast.pattern_variable}'",
                ast.line, ast.column
            )
