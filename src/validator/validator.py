# src/validator/validator.py

from typing import Dict, Any, List
from src.validator.semantic_validator import validate_semantics
from src.validator.pattern_validator import validate_pattern
from src.ast.match_recognize_ast import MatchRecognizeAST

def validate_ast(ast: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the AST for correctness.
    
    This function applies various validation techniques:
    1. Semantic validation (variable definitions, pattern variables)
    2. Pattern validation (pattern syntax, quantifiers)
    3. Type validation (expression types, compatibility)
    
    Args:
        ast: The AST to validate
        
    Returns:
        Dictionary containing:
        - valid: Boolean indicating if the AST is valid
        - errors: List of validation errors
        - warnings: List of validation warnings
    """
    all_errors = []
    all_warnings = []
    
    # Step 1: Semantic validation
    semantic_result = validate_semantics(ast)
    all_errors.extend(semantic_result.get("errors", []))
    all_warnings.extend(semantic_result.get("warnings", []))
    
    # Step 2: Pattern validation
    if "match_recognize" in ast:
        for mr_ast in ast["match_recognize"]:
            # Handle both dictionary and MatchRecognizeAST objects
            if isinstance(mr_ast, MatchRecognizeAST):
                if hasattr(mr_ast, 'pattern') and mr_ast.pattern:
                    pattern_result = validate_pattern(mr_ast.pattern)
                    all_errors.extend(pattern_result.get("errors", []))
                    all_warnings.extend(pattern_result.get("warnings", []))
            elif isinstance(mr_ast, dict):
                if "pattern" in mr_ast:
                    pattern_result = validate_pattern(mr_ast["pattern"])
                    all_errors.extend(pattern_result.get("errors", []))
                    all_warnings.extend(pattern_result.get("warnings", []))
    
    # Step 3: Type validation (future enhancement)
    # type_result = validate_types(ast)
    # all_errors.extend(type_result.get("errors", []))
    # all_warnings.extend(type_result.get("warnings", []))
    
    return {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "warnings": all_warnings
    }
