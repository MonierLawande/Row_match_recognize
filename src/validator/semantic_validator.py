# src/validator/semantic_validator.py

import re
from typing import List, Dict, Any, Tuple, Optional, Set

class SemanticValidator:
    """
    Enhanced semantic validator for MATCH_RECOGNIZE clauses.
    
    Provides detailed validation with clear error messages for:
    - Pattern syntax and semantics
    - Variable definitions
    - Measure expressions
    - Subset definitions
    - Navigation and aggregate function usage
    """
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.pattern_variables = set()
        self.subset_variables = {}
        self.defined_variables = set()
        self.rows_per_match_with_unmatched = False
    
    def validate_match_recognize(self, ast) -> Tuple[List[str], List[str]]:
        """
        Validate the entire MATCH_RECOGNIZE AST.
        Returns a tuple of (errors, warnings).
        """
        self.errors = []
        self.warnings = []
        
        # Extract pattern variables first for reference in other validations
        if ast.pattern and "ast" in ast.pattern:
            self.extract_pattern_variables(ast.pattern["ast"])
        
        # Check if using ALL ROWS PER MATCH WITH UNMATCHED ROWS
        if ast.rows_per_match and "WITH UNMATCHED ROWS" in ast.rows_per_match.upper():
            self.rows_per_match_with_unmatched = True
        
        # Validate each component
        self.validate_pattern(ast.pattern)
        self.validate_subset(ast.subset)
        self.validate_define(ast.define)
        self.validate_measures(ast.measures)
        self.validate_after_match_skip(ast.after_match_skip)
        self.validate_rows_per_match(ast.rows_per_match)
        
        # Cross-component validations
        self.validate_cross_components(ast)
        
        return self.errors, self.warnings
    
    def extract_pattern_variables(self, pattern_ast):
        """Extract all pattern variables from the pattern AST"""
        if pattern_ast.type == "literal":
            self.pattern_variables.add(pattern_ast.value)
        elif pattern_ast.type in ["concatenation", "alternation", "group", "quantifier", "permutation", "exclusion"]:
            for child in pattern_ast.children:
                self.extract_pattern_variables(child)
    
    def validate_pattern(self, pattern):
        """Validate the pattern clause"""
        if not pattern:
            self.errors.append("PATTERN clause is required in MATCH_RECOGNIZE")
            return
        
        if "ast" not in pattern:
            self.errors.append("Invalid pattern structure: missing AST")
            return
            
        pattern_ast = pattern["ast"]
        
        # Check for empty pattern
        if pattern_ast.type == "empty":
            self.warnings.append("Empty pattern '()' will match zero-length sequences")
        
        # Validate pattern structure
        self.validate_pattern_structure(pattern_ast)
        
        # Check for exclusion with ALL ROWS PER MATCH WITH UNMATCHED ROWS
        if self.has_exclusion(pattern_ast) and self.rows_per_match_with_unmatched:
            self.errors.append(
                "Pattern exclusions '{- ... -}' cannot be used with ALL ROWS PER MATCH WITH UNMATCHED ROWS"
            )
    
    def validate_pattern_structure(self, ast, path=""):
        """Recursively validate pattern structure with detailed path information"""
        current_path = f"{path}/{ast.type}"
        
        # Validate quantifiers
        if ast.type == "quantifier":
            if not ast.children:
                self.errors.append(f"Quantifier at {current_path} has no target")
                return
                
            # Validate quantifier values
            if ast.quantifier_min is not None and ast.quantifier_min < 0:
                self.errors.append(
                    f"Quantifier minimum at {current_path} cannot be negative: {ast.quantifier_min}"
                )
                
            if (ast.quantifier_max is not None and ast.quantifier_min is not None and 
                    ast.quantifier_max < ast.quantifier_min):
                self.errors.append(
                    f"Quantifier maximum at {current_path} cannot be less than minimum: "
                    f"{ast.quantifier_max} < {ast.quantifier_min}"
                )
                
            # Check for quantifier on empty pattern
            if ast.children[0].type == "empty":
                self.warnings.append(
                    f"Quantifier {ast.quantifier} applied to empty pattern at {current_path} "
                    "has no effect"
                )
        
        # Validate permutation
        elif ast.type == "permutation":
            if len(ast.children) < 2:
                self.errors.append(
                    f"PERMUTE at {current_path} requires at least two elements, found {len(ast.children)}"
                )
            
            # Check for duplicates in permutation
            values = [child.value for child in ast.children if child.type == "literal"]
            duplicates = {val for val in values if values.count(val) > 1}
            if duplicates:
                self.errors.append(
                    f"PERMUTE at {current_path} contains duplicate elements: {', '.join(duplicates)}"
                )
        
        # Validate alternation
        elif ast.type == "alternation":
            if len(ast.children) < 2:
                self.errors.append(
                    f"Alternation at {current_path} requires at least two alternatives, found {len(ast.children)}"
                )
        
        # Recursively validate children
        for i, child in enumerate(ast.children):
            self.validate_pattern_structure(child, f"{current_path}[{i}]")
    
    def has_exclusion(self, ast) -> bool:
        """Check if pattern contains exclusion syntax"""
        if ast.type == "exclusion":
            return True
        for child in ast.children:
            if self.has_exclusion(child):
                return True
        return False
    
    def validate_subset(self, subset_mapping):
        """Validate SUBSET definitions"""
        if not subset_mapping:
            return
            
        self.subset_variables = subset_mapping
        
        for subset_var, components in subset_mapping.items():
            # Check that subset variable doesn't conflict with pattern variables
            if subset_var in self.pattern_variables:
                self.errors.append(
                    f"Subset variable '{subset_var}' conflicts with a pattern variable of the same name"
                )
            
            # Check that subset components exist in pattern
            for component in components:
                if component not in self.pattern_variables:
                    self.errors.append(
                        f"Subset '{subset_var}' references undefined pattern variable '{component}'"
                    )
            
            # Check for empty subsets
            if not components:
                self.errors.append(f"Subset '{subset_var}' is empty")
                
            # Check for single-element subsets (usually not useful)
            if len(components) == 1:
                self.warnings.append(
                    f"Subset '{subset_var}' contains only one element '{components[0]}', "
                    "which may be unnecessary"
                )
    
    def validate_define(self, define_clauses):
        """Validate DEFINE clauses"""
        if not define_clauses:
            # If pattern has variables but no DEFINE clause, warn
            if self.pattern_variables:
                self.warnings.append(
                    "No DEFINE clause provided. All pattern variables will match any row."
                )
            return
            
        defined_vars = set()
        
        for define in define_clauses:
            var_name = define.get("variable")
            condition = define.get("condition")
            
            if not var_name:
                self.errors.append("DEFINE clause missing variable name")
                continue
                
            # Track defined variables
            defined_vars.add(var_name)
            
            # Check that defined variable exists in pattern
            if var_name not in self.pattern_variables:
                self.errors.append(
                    f"DEFINE clause for '{var_name}' references a variable not used in the pattern"
                )
            
            # Check for duplicate definitions
            if var_name in self.defined_variables:
                self.errors.append(f"Duplicate definition for variable '{var_name}'")
            else:
                self.defined_variables.add(var_name)
            
            # Validate condition expression
            if not condition:
                self.errors.append(f"DEFINE clause for '{var_name}' is missing a condition")
                continue
                
            if "ast" not in condition:
                self.errors.append(f"Invalid condition structure for '{var_name}'")
                continue
                
            # Validate navigation and aggregate functions in condition
            self.validate_expression(condition["ast"], f"DEFINE {var_name}", allow_final=False)
        
        # Check for undefined pattern variables
        undefined_vars = self.pattern_variables - defined_vars
        if undefined_vars:
            self.warnings.append(
                f"Pattern variables not defined in DEFINE clause will match any row: "
                f"{', '.join(undefined_vars)}"
            )
    
    def validate_measures(self, measures):
        """Validate MEASURES clause"""
        if not measures:
            return
            
        measure_aliases = set()
        
        for measure in measures:
            alias = measure.get("alias")
            expr = measure.get("expression")
            
            if not alias:
                self.errors.append("MEASURE is missing an alias")
                continue
                
            # Check for duplicate aliases
            if alias in measure_aliases:
                self.errors.append(f"Duplicate measure alias '{alias}'")
            else:
                measure_aliases.add(alias)
            
            # Validate measure expression
            if not expr:
                self.errors.append(f"MEASURE '{alias}' is missing an expression")
                continue
                
            if "ast" not in expr:
                self.errors.append(f"Invalid expression structure for measure '{alias}'")
                continue
                
            # Validate navigation and aggregate functions in measure
            self.validate_expression(expr["ast"], f"MEASURE {alias}", allow_final=True)
    
    def validate_after_match_skip(self, skip_clause):
        """Validate AFTER MATCH SKIP clause"""
        if not skip_clause:
            return
            
        skip_clause = skip_clause.upper()
        
        # Check for valid skip options
        if "TO FIRST" in skip_clause or "TO LAST" in skip_clause:
            # Extract variable name
            match = re.search(r"TO (FIRST|LAST) (\w+)", skip_clause)
            if match:
                var_name = match.group(2)
                
                # Check that variable exists in pattern or subset
                if (var_name not in self.pattern_variables and 
                        var_name not in self.subset_variables):
                    self.errors.append(
                        f"AFTER MATCH SKIP TO {match.group(1)} {var_name} references undefined variable"
                    )
                    
                # Check for skipping to first variable in pattern (potential infinite loop)
                if match.group(1) == "FIRST" and self.is_first_variable(var_name):
                    self.errors.append(
                        f"AFTER MATCH SKIP TO FIRST {var_name} may cause infinite loop as "
                        f"'{var_name}' is the first variable in the pattern"
                    )
    
    def is_first_variable(self, var_name):
        """
        Check if a variable is the first one in the pattern.
        This is a simplified implementation - in a real system,
        you would need to analyze the pattern structure more carefully.
        """
        # For now, just assume the first variable in our set is the first in the pattern
        # A more accurate implementation would analyze the pattern structure
        if self.pattern_variables and list(self.pattern_variables)[0] == var_name:
            return True
        return False
    
    def validate_rows_per_match(self, rows_clause):
        """Validate ROWS PER MATCH clause"""
        if not rows_clause:
            return
            
        rows_clause = rows_clause.upper()
        
        # Check for exclusion with ALL ROWS PER MATCH WITH UNMATCHED ROWS
        if "WITH UNMATCHED ROWS" in rows_clause:
            self.rows_per_match_with_unmatched = True
    
    def validate_cross_components(self, ast):
        """Validate relationships between different components"""
        # Check for pattern exclusions with ALL ROWS PER MATCH WITH UNMATCHED ROWS
        if self.rows_per_match_with_unmatched and ast.pattern and "ast" in ast.pattern:
            if self.has_exclusion(ast.pattern["ast"]):
                self.errors.append(
                    "Pattern exclusions '{- ... -}' cannot be used with ALL ROWS PER MATCH WITH UNMATCHED ROWS"
                )
    
    def validate_expression(self, expr_ast, context="", allow_final=True):
        """
        Validate an expression AST for semantic correctness.
        
        Args:
            expr_ast: The expression AST to validate
            context: String describing where this expression is used (for error messages)
            allow_final: Whether FINAL semantics are allowed in this context
        """
        # Check for FINAL semantics in DEFINE clause
        if not allow_final and expr_ast.semantics == "FINAL":
            self.errors.append(f"FINAL semantics not allowed in {context}")
        
        # Validate navigation functions
        if expr_ast.type == "navigation":
            # Check navigation function arguments
            if not expr_ast.children:
                self.errors.append(f"Navigation function in {context} is missing arguments")
            
            # Check for negative offset
            if hasattr(expr_ast, "offset") and expr_ast.offset < 0:
                self.errors.append(f"Navigation offset in {context} cannot be negative: {expr_ast.offset}")
            
            # Check for navigation inside aggregate
            if self.is_inside_aggregate(expr_ast):
                self.errors.append(f"Navigation function in {context} cannot be used inside aggregate function")
        
        # Validate aggregate functions
        elif expr_ast.type == "aggregate":
            # Check for nested aggregates
            for child in expr_ast.children:
                if self.has_aggregate(child):
                    self.errors.append(f"Nested aggregate functions not allowed in {context}")
            
            # Check for consistent pattern variables in arguments
            pattern_vars = self.get_pattern_variables_in_expr(expr_ast)
            if len(pattern_vars) > 1:
                self.errors.append(
                    f"Aggregate function in {context} references multiple pattern variables: "
                    f"{', '.join(pattern_vars)}"
                )
        
        # Validate pattern variable references
        elif expr_ast.type == "pattern_variable_reference":
            var = expr_ast.pattern_variable
            
            # Check that variable exists in pattern or subset
            if var not in self.pattern_variables and var not in self.subset_variables:
                self.errors.append(
                    f"Expression in {context} references undefined pattern variable '{var}'"
                )
        
        # Recursively validate children
        for child in expr_ast.children:
            self.validate_expression(child, context, allow_final)
    
    def is_inside_aggregate(self, expr_ast):
        """Check if an expression is inside an aggregate function"""
        parent = getattr(expr_ast, "_parent", None)
        while parent:
            if parent.type == "aggregate":
                return True
            parent = getattr(parent, "_parent", None)
        return False
    
    def has_aggregate(self, expr_ast):
        """Check if an expression contains an aggregate function"""
        if expr_ast.type == "aggregate":
            return True
        for child in expr_ast.children:
            if self.has_aggregate(child):
                return True
        return False
    
    def get_pattern_variables_in_expr(self, expr_ast):
        """Get all pattern variables referenced in an expression"""
        vars = set()
        
        if hasattr(expr_ast, "pattern_variable") and expr_ast.pattern_variable:
            vars.add(expr_ast.pattern_variable)
            
        for child in expr_ast.children:
            vars.update(self.get_pattern_variables_in_expr(child))
            
        return vars
