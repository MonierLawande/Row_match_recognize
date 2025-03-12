# src/validator/semantic_validator.py

from typing import Dict, Any, List, Set
from src.ast.match_recognize_ast import MatchRecognizeAST

def validate_semantics(ast: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the semantics of the AST.
    
    Args:
        ast: The AST to validate
        
    Returns:
        Dictionary containing:
        - valid: Boolean indicating if the AST is semantically valid
        - errors: List of semantic errors
        - warnings: List of semantic warnings
    """
    all_errors = []
    all_warnings = []
    
    # Validate match_recognize clauses
    if "match_recognize" in ast:
        for mr_ast in ast["match_recognize"]:
            # Validate pattern variables are defined
            pattern_vars = _extract_pattern_variables(mr_ast)
            defined_vars = _extract_defined_variables(mr_ast)
            
            # Check that all pattern variables have definitions
            for var in pattern_vars:
                if var not in defined_vars:
                    all_warnings.append(f"Pattern variable '{var}' is used but not defined in DEFINE clause")
            
            # Check that all defined variables are used in pattern
            for var in defined_vars:
                if var not in pattern_vars:
                    all_warnings.append(f"Variable '{var}' is defined but not used in PATTERN clause")
    
    return {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "warnings": all_warnings
    }

def _extract_pattern_variables(mr_ast) -> Set[str]:
    """Extract all pattern variables from a match_recognize AST"""
    pattern_vars = set()

    # Handle MatchRecognizeAST objects
    if isinstance(mr_ast, MatchRecognizeAST):
        if hasattr(mr_ast, 'pattern') and isinstance(mr_ast.pattern, dict):
            if 'ast' in mr_ast.pattern:
                pattern_ast = mr_ast.pattern['ast']
                pattern_vars = _collect_pattern_variables(pattern_ast)
    # Handle dictionary representation
    elif isinstance(mr_ast, dict):
        if "pattern" in mr_ast and "ast" in mr_ast["pattern"]:
            pattern_ast = mr_ast["pattern"]["ast"]
            pattern_vars = _collect_pattern_variables(pattern_ast)

    return pattern_vars

def _extract_defined_variables(mr_ast) -> Set[str]:
    """Extract all variables with DEFINE conditions"""
    defined_vars = set()

    # Handle MatchRecognizeAST objects
    if isinstance(mr_ast, MatchRecognizeAST):
        if hasattr(mr_ast, 'define'):
            for define_item in mr_ast.define:
                if isinstance(define_item, dict) and 'variable' in define_item:
                    defined_vars.add(define_item['variable'])
    # Handle dictionary representation
    elif isinstance(mr_ast, dict):
        if "define" in mr_ast:
            for define_item in mr_ast["define"]:
                if "variable" in define_item:
                    defined_vars.add(define_item["variable"])

    return defined_vars

def _collect_pattern_variables(pattern_ast) -> Set[str]:
    """Recursively collect pattern variables from a pattern AST"""
    vars = set()
    
    if hasattr(pattern_ast, 'type'):
        if pattern_ast.type == "literal":
            vars.add(pattern_ast.value)
        elif pattern_ast.type in ["concatenation", "alternation", "group", "quantifier", "permutation", "exclusion"]:
            for child in pattern_ast.children:
                vars.update(_collect_pattern_variables(child))
    
    return vars

def validate_pattern_variables(pattern_vars: Set[str], defined_vars: Set[str]) -> List[str]:
    """
    Validate that all pattern variables are defined.
    
    Args:
        pattern_vars: Set of variables used in the pattern
        defined_vars: Set of variables defined in the DEFINE clause
        
    Returns:
        List of validation errors
    """
    errors = []
    
    for var in pattern_vars:
        if var not in defined_vars:
            errors.append(f"Pattern variable '{var}' is used but not defined in DEFINE clause")
    
    return errors

def validate_defined_variables(pattern_vars: Set[str], defined_vars: Set[str]) -> List[str]:
    """
    Validate that all defined variables are used in the pattern.
    
    Args:
        pattern_vars: Set of variables used in the pattern
        defined_vars: Set of variables defined in the DEFINE clause
        
    Returns:
        List of validation warnings
    """
    warnings = []
    
    for var in defined_vars:
        if var not in pattern_vars:
            warnings.append(f"Variable '{var}' is defined but not used in PATTERN clause")
    
    return warnings
