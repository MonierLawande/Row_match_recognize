# src/parser/semantic_analyzer.py

from typing import Dict, Set, List, Any, Optional
from src.ast.expression_ast import ExpressionAST  # Use full path
from src.ast.pattern_ast import PatternAST  # Use full path
from .error_handler import ErrorHandler
from .symbol_table import SymbolTable, SymbolType

class SemanticAnalyzer:
    """
    Performs semantic analysis on expression and pattern ASTs.
    
    Responsibilities:
    - Validate pattern variable references
    - Validate classifier function usage
    - Validate RUNNING/FINAL semantics
    - Validate aggregate function usage
    - Validate navigation function usage
    - Build and maintain symbol table
    """
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
        self.symbol_table = SymbolTable()
        self.pattern_variables = set()
        self.subset_variables = {}
        
    def set_pattern_variables(self, pattern_vars: Set[str]):
        """Set known pattern variables for validation"""
        self.pattern_variables = set(pattern_vars)
        
    def set_subset_variables(self, subset_vars: Dict[str, List[str]]):
        """Set known subset variables for validation"""
        self.subset_variables = dict(subset_vars)
        
    def analyze_expression(self, expr_ast: ExpressionAST, context: str, in_measures: bool = True):
        """Analyze an expression AST for semantic correctness"""
        self.validate_classifier_consistency(expr_ast, context)
        self.validate_running_final_semantics(expr_ast, context, in_measures)
        self.validate_count_star_syntax(expr_ast, context)
        self.validate_aggregate_functions(expr_ast, context)
        self.validate_navigation_functions(expr_ast, context)
        
    def analyze_pattern(self, pattern_ast: PatternAST):
        """Analyze a pattern AST for semantic correctness"""
        self._collect_pattern_variables(pattern_ast)
        self._validate_pattern_structure(pattern_ast)
        
    def validate_expression(self, expr_ast: ExpressionAST, context: str, in_measures: bool = True):
        """Unified validation for expressions"""
        self.validate_classifier_consistency(expr_ast, context)
        self.validate_running_final_semantics(expr_ast, context, in_measures)
        self.validate_count_star_syntax(expr_ast, context)
        self.validate_aggregate_functions(expr_ast, context)
        self.validate_navigation_functions(expr_ast, context)
        
    def validate_classifier_consistency(self, expr_ast: ExpressionAST, context: str):
        """Validate classifier function usage"""
        pattern_vars = set()
        classifier_vars = set()
        
        def collect_vars(ast):
            if ast.type == "pattern_variable_reference":
                pattern_vars.add(ast.pattern_variable)
            elif ast.type == "classifier":
                if ast.pattern_variable:
                    classifier_vars.add(ast.pattern_variable)
            for child in ast.children:
                collect_vars(child)
                
        collect_vars(expr_ast)
        
        # Validate classifier variables
        if classifier_vars:
            # Check that classifier variables are used in pattern references
            unused_vars = classifier_vars - pattern_vars
            if unused_vars:
                self.error_handler.add_error(
                    f"In {context}: CLASSIFIER() references variables {unused_vars} "
                    f"not used in pattern references",
                    getattr(expr_ast, 'line', 0),
                    getattr(expr_ast, 'column', 0)
                )
                
            # Check for multiple different classifier variables
            if len(classifier_vars) > 1:
                self.error_handler.add_error(
                    f"In {context}: Multiple different variables in CLASSIFIER() functions: "
                    f"{', '.join(classifier_vars)}",
                    getattr(expr_ast, 'line', 0),
                    getattr(expr_ast, 'column', 0)
                )
                
    def validate_running_final_semantics(self, expr_ast: ExpressionAST, context: str, in_measures: bool = True):
        """Validate RUNNING and FINAL semantics usage"""
        if hasattr(expr_ast, "semantics") and expr_ast.semantics:
            # FINAL can only be used in MEASURES clause
            if expr_ast.semantics == "FINAL" and not in_measures:
                self.error_handler.add_error(
                    f"In {context}: FINAL semantics can only be used in MEASURES clause",
                    getattr(expr_ast, 'line', 0),
                    getattr(expr_ast, 'column', 0)
                )
            
            # FINAL can only be used with aggregate or navigation functions
            if expr_ast.semantics == "FINAL" and expr_ast.type not in ["aggregate", "navigation"]:
                self.error_handler.add_error(
                    f"In {context}: FINAL semantics can only be applied to "
                    "aggregate or navigation functions",
                    getattr(expr_ast, 'line', 0),
                    getattr(expr_ast, 'column', 0)
                )
        
        # Recursively validate children
        for child in expr_ast.children:
            self.validate_running_final_semantics(child, context, in_measures)
            
    def validate_count_star_syntax(self, expr_ast: ExpressionAST, context: str):
        """Validate special count(*) and count(var.*) syntax"""
        if expr_ast.type == "aggregate" and expr_ast.value.lower() == "count":
            # Check for count(*)
            if hasattr(expr_ast, "count_star") and expr_ast.count_star:
                if hasattr(expr_ast, "pattern_variable") and expr_ast.pattern_variable:
                    # This is count(var.*)
                    if (expr_ast.pattern_variable not in self.pattern_variables and 
                            expr_ast.pattern_variable not in self.subset_variables):
                        self.error_handler.add_error(
                            f"In {context}: count({expr_ast.pattern_variable}.*) references "
                            "undefined pattern variable",
                            getattr(expr_ast, 'line', 0),
                            getattr(expr_ast, 'column', 0)
                        )
            
            # Regular count() must have exactly one argument
            elif not expr_ast.children:
                self.error_handler.add_error(
                    f"In {context}: count() requires an argument (use count(*) for counting all rows)",
                    getattr(expr_ast, 'line', 0),
                    getattr(expr_ast, 'column', 0)
                )
        
        # Recursively validate children
        for child in expr_ast.children:
            self.validate_count_star_syntax(child, context)
            
    def validate_aggregate_functions(self, expr_ast: ExpressionAST, context: str):
        """Validate aggregate function usage"""
        in_aggregate = False
        
        def validate_agg(ast, in_agg):
            nonlocal in_aggregate
            old_in_agg = in_aggregate
            
            if ast.type == "aggregate":
                # Check for nested aggregates
                if in_agg:
                    self.error_handler.add_error(
                        f"In {context}: Nested aggregate functions are not allowed",
                        getattr(ast, 'line', 0),
                        getattr(ast, 'column', 0)
                    )
                in_aggregate = True
                
                # Check that all arguments refer to the same pattern variable
                pattern_vars = set()
                for arg in ast.children:
                    if hasattr(arg, 'pattern_variable') and arg.pattern_variable:
                        pattern_vars.add(arg.pattern_variable)
                        
                if len(pattern_vars) > 1:
                    self.error_handler.add_error(
                        f"In {context}: All arguments in an aggregate function must refer to the same pattern variable",
                        getattr(ast, 'line', 0),
                        getattr(ast, 'column', 0)
                    )
            
            # Check for navigation functions inside aggregate arguments
            if in_agg and ast.type == "navigation":
                self.error_handler.add_error(
                    f"In {context}: Aggregate function arguments cannot contain navigation functions",
                    getattr(ast, 'line', 0),
                    getattr(ast, 'column', 0)
                )
                
            # Recursively validate children
            for child in ast.children:
                validate_agg(child, in_aggregate)
                
            in_aggregate = old_in_agg
            
        validate_agg(expr_ast, False)
        
    def validate_navigation_functions(self, expr_ast: ExpressionAST, context: str):
        """Validate navigation function usage"""
        in_aggregate = False
        
        def validate_nav(ast, in_agg):
            nonlocal in_aggregate
            
            if ast.type == "aggregate":
                in_aggregate = True
                
            if ast.type == "navigation":
                # Check if we're inside an aggregate function
                if in_agg:
                    self.error_handler.add_error(
                        f"In {context}: Navigation functions cannot be used inside aggregate functions",
                        getattr(ast, 'line', 0),
                        getattr(ast, 'column', 0)
                    )
                
                # Validate that the target expression contains at least one column reference
                if not self._contains_column_reference(ast.children[0]):
                    self.error_handler.add_error(
                        f"In {context}: Navigation function {ast.navigation_type} requires at least one column reference",
                        getattr(ast, 'line', 0),
                        getattr(ast, 'column', 0)
                    )
                    
                # Validate offset if present
                if hasattr(ast, 'offset') and ast.offset < 0:
                    self.error_handler.add_error(
                        f"In {context}: Navigation offset cannot be negative",
                        getattr(ast, 'line', 0),
                        getattr(ast, 'column', 0)
                    )
            
            # Recursively validate children with updated aggregate state
            old_in_agg = in_aggregate
            for child in ast.children:
                validate_nav(child, in_aggregate)
                
            # Restore aggregate state after processing children
            in_aggregate = old_in_agg
            
        validate_nav(expr_ast, False)
        
    def _collect_pattern_variables(self, pattern_ast: PatternAST):
        """Collect pattern variables from pattern AST"""
        if pattern_ast.type == "literal":
            self.symbol_table.add_symbol(
                pattern_ast.value,
                SymbolType.PATTERN_VARIABLE,
                pattern_ast.line,
                pattern_ast.column
            )
            self.pattern_variables.add(pattern_ast.value)
            
        for child in pattern_ast.children:
            self._collect_pattern_variables(child)
            
    def _validate_pattern_structure(self, pattern_ast: PatternAST, in_exclusion: bool = False):
        """Validate pattern structure"""
        # Check for exclusion patterns
        if pattern_ast.type == "exclusion":
            if in_exclusion:
                self.error_handler.add_error(
                    "Nested exclusion patterns are not allowed",
                    pattern_ast.line,
                    pattern_ast.column
                )
            
            # Validate children with in_exclusion=True
            for child in pattern_ast.children:
                self._validate_pattern_structure(child, True)
            return
            
        # Validate quantifiers
        if pattern_ast.type == "quantifier":
            if pattern_ast.quantifier_min is not None and pattern_ast.quantifier_min < 0:
                self.error_handler.add_error(
                    f"Negative quantifier minimum {pattern_ast.quantifier_min}",
                    pattern_ast.line,
                    pattern_ast.column
                )
                
            if (pattern_ast.quantifier_max is not None and 
                    pattern_ast.quantifier_min is not None and 
                    pattern_ast.quantifier_max < pattern_ast.quantifier_min):
                self.error_handler.add_error(
                    "Quantifier maximum less than minimum",
                    pattern_ast.line,
                    pattern_ast.column
                )
                
        # Recursively validate children
        for child in pattern_ast.children:
            self._validate_pattern_structure(child, in_exclusion)
            
    def _contains_column_reference(self, expr_ast: ExpressionAST) -> bool:
        """Check if an expression contains at least one column reference"""
        if expr_ast.type in ["identifier", "pattern_variable_reference"]:
            return True
        for child in expr_ast.children:
            if self._contains_column_reference(child):
                return True
        return False
