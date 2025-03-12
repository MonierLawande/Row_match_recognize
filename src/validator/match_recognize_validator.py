# src/validator/match_recognize_validator.py

from typing import Dict, Any, List

def validate_match_recognize(mr_ast: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the MATCH_RECOGNIZE clause.
    
    This function checks:
    1. Constraints between clauses
    2. Required clauses
    3. Compatibility between options
    
    Args:
        mr_ast: The MATCH_RECOGNIZE AST to validate
        
    Returns:
        Dictionary containing:
        - errors: List of validation errors
        - warnings: List of validation warnings
    """
    errors = []
    warnings = []
    
    # Check for required clauses
    if "pattern" not in mr_ast:
        errors.append("MATCH_RECOGNIZE requires a PATTERN clause")
    
    # Check for MEASURES clause
    if "measures" not in mr_ast or not mr_ast["measures"]:
        warnings.append("MATCH_RECOGNIZE has no MEASURES clause")
    
    # Check for DEFINE clause
    if "define" not in mr_ast or not mr_ast["define"]:
        warnings.append("MATCH_RECOGNIZE has no DEFINE clause")
    
    # Check for ROWS PER MATCH constraints
    if "rows_per_match_type" in mr_ast:
        rpm_type = mr_ast["rows_per_match_type"]
        
        # Check for unmatched rows constraints
        if hasattr(mr_ast, "has_unmatched_rows") and mr_ast.has_unmatched_rows:
            # Check for pattern exclusions
            if hasattr(mr_ast, "has_exclusion") and mr_ast.has_exclusion:
                errors.append(
                    "Pattern exclusions '{- ... -}' cannot be used with "
                    "ALL ROWS PER MATCH WITH UNMATCHED ROWS"
                )
            
            # Check for AFTER MATCH SKIP TO
            if hasattr(mr_ast, "after_match_skip_type") and mr_ast.after_match_skip_type in ["SKIP_TO_FIRST", "SKIP_TO_LAST"]:
                errors.append(
                    "AFTER MATCH SKIP TO FIRST/LAST cannot be used with "
                    "ALL ROWS PER MATCH WITH UNMATCHED ROWS"
                )
    
    return {
        "errors": errors,
        "warnings": warnings
    }
