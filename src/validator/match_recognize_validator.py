# src/validator/match_recognize_validator.py

from typing import List, Dict, Any, Tuple, Set
from .semantic_validator import SemanticValidator
from .pattern_validator import PatternValidator
from .function_validator import FunctionValidator

class MatchRecognizeValidator:
    """
    Comprehensive validator for MATCH_RECOGNIZE clauses.
    
    Combines:
    - Semantic validation of the overall structure
    - Pattern validation for quantifiers, exclusions, and subsets
    - Function validation for navigation and aggregate functions
    
    Provides detailed error messages and warnings.
    """
    
    def __init__(self):
        self.semantic_validator = SemanticValidator()
        self.pattern_validator = PatternValidator()
        self.function_validator = FunctionValidator()
        self.errors = []
        self.warnings = []
    
    def validate(self, ast) -> Tuple[List[str], List[str]]:
        """
        Validate a MATCH_RECOGNIZE AST.
        
        Args:
            ast: The MATCH_RECOGNIZE AST to validate
            
        Returns:
            Tuple of (errors, warnings)
        """
        self.errors = []
        self.warnings = []
        
        # Extract pattern variables for reference in other validations
        pattern_vars = set()
        if ast.pattern and "ast" in ast.pattern:
            pattern_vars = self._extract_pattern_variables(ast.pattern["ast"])
        
        # 1. Validate overall semantic structure
        semantic_errors, semantic_warnings = self.semantic_validator.validate_match_recognize(ast)
        self.errors.extend(semantic_errors)
        self.warnings.extend(semantic_warnings)
        
        # 2. Validate pattern structure
        if ast.pattern and "ast" in ast.pattern:
            pattern_errors, pattern_warnings = self.pattern_validator.validate_pattern(
                ast.pattern["ast"], ast.subset
            )
            self.errors.extend(pattern_errors)
            self.warnings.extend(pattern_warnings)
        
        # 3. Validate functions in DEFINE clauses
        if ast.define:
            for define in ast.define:
                if "condition" in define and "ast" in define["condition"]:
                    func_errors, func_warnings = self.function_validator.validate_expression(
                        define["condition"]["ast"],
                        f"DEFINE {define['variable']}",
                        pattern_vars,
                        ast.subset,
                        in_define=True
                    )
                    self.errors.extend(func_errors)
                    self.warnings.extend(func_warnings)
        
        # 4. Validate functions in MEASURES clauses
        if ast.measures:
            for measure in ast.measures:
                if "expression" in measure and "ast" in measure["expression"]:
                    func_errors, func_warnings = self.function_validator.validate_expression(
                        measure["expression"]["ast"],
                        f"MEASURE {measure['alias']}",
                        pattern_vars,
                        ast.subset,
                        in_define=False
                    )
                    self.errors.extend(func_errors)
                    self.warnings.extend(func_warnings)
        
        # 5. Cross-component validations
        self._validate_cross_components(ast, pattern_vars)
        
        return self.errors, self.warnings
    
    def _extract_pattern_variables(self, pattern_ast):
        """Extract all pattern variables from the pattern AST"""
        vars = set()
        
        if pattern_ast.type == "literal":
            vars.add(pattern_ast.value)
        elif pattern_ast.type in ["concatenation", "alternation", "group", "quantifier", "permutation", "exclusion"]:
            for child in pattern_ast.children:
                vars.update(self._extract_pattern_variables(child))
                
        return vars
    
    def _validate_cross_components(self, ast, pattern_vars):
        """Validate relationships between different components"""
        # Check for exclusion with ALL ROWS PER MATCH WITH UNMATCHED ROWS
        if ast.rows_per_match and "WITH UNMATCHED ROWS" in ast.rows_per_match.upper():
            if ast.pattern and "ast" in ast.pattern and self._has_exclusion(ast.pattern["ast"]):
                self.errors.append(
                    "Pattern exclusions '{- ... -}' cannot be used with ALL ROWS PER MATCH WITH UNMATCHED ROWS"
                )
        
        # Check for AFTER MATCH SKIP TO variable that doesn't exist
        if ast.after_match_skip:
            skip = ast.after_match_skip.upper()
            if "TO FIRST" in skip or "TO LAST" in skip:
                match = re.search(r"TO (FIRST|LAST) (\w+)", skip)
                if match:
                    var_name = match.group(2)
                    if var_name not in pattern_vars and var_name not in ast.subset:
                        self.errors.append(
                            f"AFTER MATCH SKIP TO {match.group(1)} {var_name} references undefined variable"
                        )
    
    def _has_exclusion(self, ast):
        """Check if pattern contains exclusion syntax"""
        if ast.type == "exclusion":
            return True
        for child in ast.children:
            if self._has_exclusion(child):
                return True
        return False

def validate_match_recognize(ast):
    """
    Validate a MATCH_RECOGNIZE AST and return errors and warnings.
    
    Args:
        ast: The MATCH_RECOGNIZE AST to validate
        
    Returns:
        Tuple of (errors, warnings)
    """
    validator = MatchRecognizeValidator()
    return validator.validate(ast)
