# src/validator/pattern_validator.py

from typing import Dict, Any, List

def validate_pattern(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the pattern structure.
    
    This function checks:
    1. Pattern syntax correctness
    2. Exclusion constraints
    3. Quantifier validity
    
    Args:
        pattern: The pattern AST to validate
        
    Returns:
        Dictionary containing:
        - errors: List of pattern errors
        - warnings: List of pattern warnings
    """
    errors = []
    warnings = []
    
    if "ast" not in pattern:
        errors.append("Pattern has no AST")
        return {"errors": errors, "warnings": warnings}
    
    pattern_ast = pattern["ast"]
    
    # Check for empty pattern
    if pattern_ast.type == "empty":
        warnings.append("Empty pattern will match nothing")
    
    # Validate pattern structure
    _validate_pattern_structure(pattern_ast, errors, warnings)
    
    return {
        "errors": errors,
        "warnings": warnings
    }

def _validate_pattern_structure(node, errors: List[str], warnings: List[str], in_exclusion: bool = False):
    """Recursively validate pattern structure"""
    
    # Check for nested exclusions
    if node.type == "exclusion" and in_exclusion:
        errors.append("Nested exclusions are not allowed")
    
    # Check for empty alternation
    if node.type == "alternation" and not node.children:
        errors.append("Empty alternation is not allowed")
    
    # Check for invalid quantifiers
    if node.type == "quantifier":
        if not node.children:
            errors.append("Quantifier must have a child element")
        elif node.children[0].type == "empty":
            errors.append("Cannot apply quantifier to empty pattern")
        
        # Check for specific quantifier issues
        if node.quantifier == "?":
            if node.children[0].type == "quantifier" and node.children[0].quantifier in ["*", "?"]:
                warnings.append(f"Redundant quantifier: {node.children[0].quantifier}{node.quantifier}")
    
    # Recursively check children
    for child in node.children:
        _validate_pattern_structure(
            child, 
            errors, 
            warnings, 
            in_exclusion=(in_exclusion or node.type == "exclusion")
        )
