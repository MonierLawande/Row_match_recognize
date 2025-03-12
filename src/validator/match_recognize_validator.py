def validate_match_recognize_ast(ast):
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
    return errors
