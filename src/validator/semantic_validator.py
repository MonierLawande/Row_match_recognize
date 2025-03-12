# src/validator/semantic_validator.py

def get_pattern_variable(expr_ast):
    """
    Extracts a pattern variable from an expression AST node.
    For an identifier of the form "A.totalprice", returns "A".
    Otherwise, returns "universal" if no explicit pattern variable is referenced.
    """
    if expr_ast.type == "identifier" and expr_ast.value:
        if '.' in expr_ast.value:
            return expr_ast.value.split('.')[0]
        else:
            return "universal"
    return "universal"

def contains_navigation(expr_ast):
    """
    Recursively checks whether an expression AST contains any navigation function.
    Returns True if a node of type "navigation" is found.
    """
    if expr_ast.type == "navigation":
        return True
    for child in expr_ast.children:
        if contains_navigation(child):
            return True
    return False

def validate_aggregate_consistency(expr_ast):
    """
    Recursively validates that in any aggregate function:
      - All arguments refer to the same pattern variable.
      - None of the arguments (even nested) contain a navigation function.
    Returns a list of error messages.
    """
    errors = []
    aggregate_functions = ['avg', 'min', 'max', 'count', 'sum', 'max_by', 'min_by', 'array_agg']
    
    if expr_ast.type in ["aggregate"] and expr_ast.value:
        func_name = expr_ast.value.lower()
        if func_name in aggregate_functions:
            arg_vars = []
            for arg in expr_ast.children:
                var = get_pattern_variable(arg)
                arg_vars.append(var)
                if contains_navigation(arg):
                    errors.append(
                        f"Aggregate function '{expr_ast.value}' has an argument containing navigation functions, which is not allowed."
                    )
            # If there are multiple arguments and at least one explicitly references a variable, they must all be the same.
            explicit_vars = [v for v in arg_vars if v != "universal"]
            if explicit_vars and len(set(explicit_vars)) > 1:
                errors.append(
                    f"In aggregate function '{expr_ast.value}', arguments refer to different pattern variables: {arg_vars}"
                )
            if explicit_vars and len(explicit_vars) != len(arg_vars):
                errors.append(
                    f"In aggregate function '{expr_ast.value}', mixed explicit and universal aggregate arguments are not allowed: {arg_vars}"
                )
    for child in expr_ast.children:
        errors.extend(validate_aggregate_consistency(child))
    return errors

def validate_running_final_semantics(expr_ast, context="MEASURES"):
    """
    Validates that FINAL semantics are used only in allowed contexts (typically in MEASURES).
    Returns a list of error messages.
    """
    errors = []
    if expr_ast.semantics:
        if context != "MEASURES" and expr_ast.semantics.upper() == "FINAL":
            errors.append(f"FINAL semantics are not allowed in the {context} clause: {expr_ast}")
    for child in expr_ast.children:
        errors.extend(validate_running_final_semantics(child, context))
    return errors

def validate_nested_navigation(expr_ast):
    """
    Recursively validates that nested navigation functions refer to consistent pattern variables.
    Returns a list of error messages.
    """
    errors = []
    if expr_ast.type == "navigation":
        target = expr_ast.children[0] if expr_ast.children else None
        expected_var = get_pattern_variable(target) if target else "universal"

        def traverse(node, expected_var):
            if node.type == "navigation":
                current_var = get_pattern_variable(node.children[0]) if node.children else "universal"
                if current_var != expected_var:
                    errors.append(
                        f"Inconsistent pattern variable in nested navigation: expected '{expected_var}', got '{current_var}'"
                    )
            for child in node.children:
                traverse(child, expected_var)
        if target:
            traverse(target, expected_var)
    for child in expr_ast.children:
        errors.extend(validate_nested_navigation(child))
    return errors

def extract_classifier_navigation_refs(expr_ast):
    """
    Recursively collects pattern variable references from classifier and navigation function calls.
    For a classifier function call (type "function" with value "classifier"), it extracts the reference
    from its first argument (if any). For a navigation function, it extracts the reference from its target.
    Returns a set of pattern variable names.
    """
    refs = set()
    if expr_ast.type == "function" and expr_ast.value and expr_ast.value.lower() == "classifier":
        if expr_ast.children:
            ref = get_pattern_variable(expr_ast.children[0])
            if ref:
                refs.add(ref)
    if expr_ast.type == "navigation":
        if expr_ast.children:
            ref = get_pattern_variable(expr_ast.children[0])
            if ref:
                refs.add(ref)
    for child in expr_ast.children:
        refs.update(extract_classifier_navigation_refs(child))
    return refs

def validate_classifier_navigation_consistency(expr_ast):
    """
    Validates that all classifier and navigation function calls in the expression refer to the same pattern variable.
    Returns a list of error messages if inconsistencies are found.
    """
    errors = []
    refs = extract_classifier_navigation_refs(expr_ast)
    # Exclude "universal" if that's considered the default; adjust logic as needed.
    explicit_refs = {ref for ref in refs if ref != "universal"}
    if len(explicit_refs) > 1:
        errors.append(f"Inconsistent pattern variable references in classifier/navigation functions: {explicit_refs}")
    return errors

class SemanticValidator:
    def __init__(self, schema=None):
        self.schema = schema or {}
        self.errors = []

    def validate_expression(self, expr_ast, context="MEASURES"):
        # Basic check: if an identifier, ensure it exists in the schema.
        if expr_ast.type == "identifier" and expr_ast.value:
            if expr_ast.value not in self.schema:
                self.errors.append(f"Unknown identifier: {expr_ast.value}")
        for child in expr_ast.children:
            self.validate_expression(child, context)
        # Validate aggregate function consistency.
        self.errors.extend(validate_aggregate_consistency(expr_ast))
        # Validate running/final semantics.
        self.errors.extend(validate_running_final_semantics(expr_ast, context))
        # Validate nested navigation consistency.
        self.errors.extend(validate_nested_navigation(expr_ast))
        # Validate classifier and navigation consistency.
        self.errors.extend(validate_classifier_navigation_consistency(expr_ast))

    def get_errors(self):
        return self.errors

class EnhancedSemanticValidator(SemanticValidator):
    def __init__(self, schema=None):
        super().__init__(schema)
    # Further advanced validations can be added here.
