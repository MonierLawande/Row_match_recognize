# src/validator/match_recognize_validator.py

def validate_match_recognize_ast(ast):
    """
    Validates the overall MATCH_RECOGNIZE AST.
    Checks that mandatory subclauses are present and performs additional checks:
      - Ensures that if unmatched row semantics are specified, the pattern does not allow empty matches.
    Returns a list of error messages.
    """
    errors = []
    if not ast.partition_by:
        errors.append("Missing PARTITION BY clause.")
    if not ast.order_by:
        errors.append("Missing ORDER BY clause.")
    if not ast.measures:
        errors.append("Missing MEASURES clause.")
    if not ast.define:
        errors.append("Missing DEFINE clause.")
    if "ast" not in ast.pattern:
        errors.append("Invalid PATTERN clause.")
    # Additional unmatched row semantics check:
    # If the rows_per_match option is "ALL ROWS PER MATCH WITH UNMATCHED ROWS"
    # then the pattern must not allow empty matches.
    if ast.rows_per_match.upper() == "ALL ROWS PER MATCH WITH UNMATCHED ROWS":
        if ast.is_empty_match:
            errors.append(
                "Unmatched row semantics specified (ALL ROWS PER MATCH WITH UNMATCHED ROWS) but pattern allows empty matches."
            )
    return errors
