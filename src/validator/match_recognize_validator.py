def validate_match_recognize_ast(ast):
    errors = []
    # Check that PARTITION BY and ORDER BY are not empty
    if not ast.partition_by:
        errors.append("Missing PARTITION BY clause.")
    if not ast.order_by:
        errors.append("Missing ORDER BY clause.")
    # Check that measures and define are provided
    if not ast.measures:
        errors.append("Missing MEASURES clause.")
    if not ast.define:
        errors.append("Missing DEFINE clause.")
    # Validate pattern (dummy check)
    if "ast" not in ast.pattern:
        errors.append("Invalid pattern in MATCH_RECOGNIZE clause.")
    return errors
