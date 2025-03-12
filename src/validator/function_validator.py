# src/validator/function_validator.py

from typing import List, Dict, Any, Tuple, Set

class FunctionValidator:
    """
    Specialized validator for navigation and aggregate functions in MATCH_RECOGNIZE.
    
    Focuses on:
    - Navigation function constraints (PREV, NEXT, FIRST, LAST)
    - Aggregate function constraints
    - RUNNING and FINAL semantics
    - Pattern variable references
    """
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.pattern_variables = set()
        self.subset_variables = {}
        self.in_define_clause = False
    
    def validate_expression(self, expr_ast, context="", 
                           pattern_vars=None, subset_vars=None, 
                           in_define=False) -> Tuple[List[str], List[str]]:
        """
        Validate an expression AST for function usage correctness.
        
        Args:
            expr_ast: The expression AST to validate
            context: String describing where this expression is used (for error messages)
            pattern_vars: Set of valid pattern variables
            subset_vars: Dict mapping subset variables to their components
            in_define: Whether this expression is in a DEFINE clause
            
        Returns:
            Tuple of (errors, warnings)
        """
        self.errors = []
        self.warnings = []
        self.pattern_variables = pattern_vars or set()
        self.subset_variables = subset_vars or {}
        self.in_define_clause = in_define
        
        # Set parent references for context in validation
        self._set_parent_references(expr_ast)
        
        # Validate the expression
        self._validate_expression(expr_ast, context)
        
        return self.errors, self.warnings
    
    def _set_parent_references(self, expr_ast, parent=None):
        """Set parent references for all nodes in the expression tree"""
        expr_ast._parent = parent
        for child in expr_ast.children:
            self._set_parent_references(child, expr_ast)
    
    def _validate_expression(self, expr_ast, context=""):
        """
        Recursively validate an expression AST.
        
        Args:
            expr_ast: The expression AST to validate
            context: String describing where this expression is used (for error messages)
        """
        # Check for FINAL semantics in DEFINE clause
        if self.in_define_clause and expr_ast.semantics == "FINAL":
            self.errors.append(f"FINAL semantics not allowed in {context}")
        
        # Validate based on expression type
        if expr_ast.type == "navigation":
            self._validate_navigation_function(expr_ast, context)
        elif expr_ast.type == "aggregate":
            self._validate_aggregate_function(expr_ast, context)
        elif expr_ast.type == "pattern_variable_reference":
            self._validate_pattern_variable_reference(expr_ast, context)
        elif expr_ast.type == "classifier":
            self._validate_classifier_function(expr_ast, context)
        
        # Recursively validate children
        for child in expr_ast.children:
            self._validate_expression(child, context)
    
    def _validate_navigation_function(self, expr_ast, context):
        """Validate a navigation function"""
        nav_type = expr_ast.navigation_type
        
        # Check for navigation inside aggregate
        if self._is_inside_aggregate(expr_ast):
            self.errors.append(
                f"Navigation function {nav_type} in {context} cannot be used inside aggregate functions"
            )
        
        # Check for negative offset
        if hasattr(expr_ast, "offset") and expr_ast.offset < 0:
            self.errors.append(
                f"Navigation function {nav_type} in {context} cannot have negative offset: {expr_ast.offset}"
            )
        
        # Check for consistent pattern variables in target expression
        pattern_vars = self._get_pattern_variables_in_expr(expr_ast.children[0])
        if len(pattern_vars) > 1:
            self.errors.append(
                f"Navigation function {nav_type} in {context} references multiple pattern variables: "
                f"{', '.join(pattern_vars)}"
            )
        
        # Check for navigation function nesting
        if self._has_navigation_function(expr_ast.children[0]):
            self.warnings.append(
                f"Navigation function {nav_type} in {context} contains nested navigation functions, "
                "which may lead to complex behavior"
            )
    
    def _validate_aggregate_function(self, expr_ast, context):
        """Validate an aggregate function"""
        func_name = expr_ast.value
        
        # Check for nested aggregates
        for child in expr_ast.children:
            if self._has_aggregate_function(child):
                self.errors.append(
                    f"Aggregate function {func_name} in {context} contains nested aggregate functions, "
                    "which is not allowed"
                )
        
        # Check for navigation functions inside aggregate
        for child in expr_ast.children:
            if self._has_navigation_function(child):
                self.errors.append(
                    f"Aggregate function {func_name} in {context} contains navigation functions, "
                    "which is not allowed"
                )
        
        # Check for consistent pattern variables in arguments
        pattern_vars = set()
        for child in expr_ast.children:
            pattern_vars.update(self._get_pattern_variables_in_expr(child))
        
        if len(pattern_vars) > 1:
            self.errors.append(
                f"Aggregate function {func_name} in {context} references multiple pattern variables: "
                f"{', '.join(pattern_vars)}"
            )
        
        # Special handling for count(*) and count(var.*)
        if func_name.lower() == "count" and len(expr_ast.children) == 0:
            # This is count(*) or count() - valid
            pass
        elif func_name.lower() == "count" and len(expr_ast.children) == 1:
            child = expr_ast.children[0]
            if hasattr(child, "count_star") and child.count_star:
                # This is count(var.*) - check that var is valid
                var = child.pattern_variable
                if var and var not in self.pattern_variables and var not in self.subset_variables:
                    self.errors.append(
                        f"Count expression count({var}.*) in {context} references undefined pattern variable '{var}'"
                    )
    
    def _validate_pattern_variable_reference(self, expr_ast, context):
        """Validate a pattern variable reference"""
        var = expr_ast.pattern_variable
        
        # Check that variable exists in pattern or subset
        if var not in self.pattern_variables and var not in self.subset_variables:
            self.errors.append(
                f"Expression in {context} references undefined pattern variable '{var}'"
            )
    
    def _validate_classifier_function(self, expr_ast, context):
        """Validate a classifier function"""
        var = expr_ast.pattern_variable
        
        # If a pattern variable is specified, check that it exists
        if var and var not in self.pattern_variables and var not in self.subset_variables:
            self.errors.append(
                f"CLASSIFIER function in {context} references undefined pattern variable '{var}'"
            )
    
    def _is_inside_aggregate(self, expr_ast):
        """Check if an expression is inside an aggregate function"""
        parent = getattr(expr_ast, "_parent", None)
        while parent:
            if parent.type == "aggregate":
                return True
            parent = getattr(parent, "_parent", None)
        return False
    
    def _has_aggregate_function(self, expr_ast):
        """Check if an expression contains an aggregate function"""
        if expr_ast.type == "aggregate":
            return True
        for child in expr_ast.children:
            if self._has_aggregate_function(child):
                return True
        return False
    
    def _has_navigation_function(self, expr_ast):
        """Check if an expression contains a navigation function"""
        if expr_ast.type == "navigation":
            return True
        for child in expr_ast.children:
            if self._has_navigation_function(child):
                return True
        return False
    
    def _get_pattern_variables_in_expr(self, expr_ast):
        """Get all pattern variables referenced in an expression"""
        vars = set()
        
        if hasattr(expr_ast, "pattern_variable") and expr_ast.pattern_variable:
            vars.add(expr_ast.pattern_variable)
            
        for child in expr_ast.children:
            vars.update(self._get_pattern_variables_in_expr(child))
            
        return vars
