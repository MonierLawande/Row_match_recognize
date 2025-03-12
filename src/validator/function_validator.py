# src/validator/function_validator.py

from typing import Dict, Any, List

def validate_functions(ast: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate function usage in the AST.
    
    This function checks:
    1. Aggregate function usage
    2. Navigation function usage
    3. CLASSIFIER and MATCH_NUMBER usage
    
    Args:
        ast: The AST to validate
        
    Returns:
        Dictionary containing:
        - errors: List of function errors
        - warnings: List of function warnings
    """
    errors = []
    warnings = []
    
    # Check for match_recognize section
    if "match_recognize" in ast:
        for mr_ast in ast["match_recognize"]:
            # Validate MEASURES expressions
            if "measures" in mr_ast:
                for measure in mr_ast["measures"]:
                    if "expression" in measure and "ast" in measure["expression"]:
                        expr_ast = measure["expression"]["ast"]
                        _validate_expression_functions(expr_ast, True, errors, warnings)
            
            # Validate DEFINE expressions
            if "define" in mr_ast:
                for define in mr_ast["define"]:
                    if "condition" in define and "ast" in define["condition"]:
                        expr_ast = define["condition"]["ast"]
                        _validate_expression_functions(expr_ast, False, errors, warnings)
    
    return {
        "errors": errors,
        "warnings": warnings
    }

def _validate_expression_functions(expr_ast, in_measures: bool, errors: List[str], warnings: List[str]):
    """Validate functions in an expression AST"""
    
    # Check for CLASSIFIER function
    if expr_ast.type == "classifier":
        if not in_measures:
            errors.append("CLASSIFIER function can only be used in MEASURES clause")
    
    # Check for MATCH_NUMBER function
    elif expr_ast.type == "match_number":
        if not in_measures:
            errors.append("MATCH_NUMBER function can only be used in MEASURES clause")
    
    # Check for aggregate functions
    elif expr_ast.type == "aggregate":
        if not in_measures:
            errors.append(f"Aggregate function '{expr_ast.value}' can only be used in MEASURES clause")
    
    # Check for navigation functions
    elif expr_ast.type == "navigation":
        # Check for FINAL semantics
        if hasattr(expr_ast, "semantics") and expr_ast.semantics == "FINAL" and not in_measures:
            errors.append("FINAL semantics can only be used in MEASURES clause")
    
    # Recursively check children
    for child in expr_ast.children:
        _validate_expression_functions(child, in_measures, errors, warnings)
