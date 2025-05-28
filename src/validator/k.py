# Enhanced Navigation Validation Functions (integrated from NavigationValidator)
from dataclasses import dataclass
from typing import Set, Optional, List

@dataclass
class NavigationFunctionInfo:
    """Information about a navigation function call."""
    function_type: str  # PREV, NEXT, FIRST, LAST
    variable: Optional[str]
    column: Optional[str]
    offset: int
    is_nested: bool
    inner_functions: List['NavigationFunctionInfo']
    raw_expression: str

def _parse_navigation_expression(expr: str) -> NavigationFunctionInfo:
    """
    Parse a navigation expression to extract function information.
    Supports nested expressions and arithmetic operations.
    """
    expr = expr.strip()
    
    # Pattern for nested navigation: OUTER(INNER(...))
    nested_pattern = r'(PREV|NEXT)\s*\(\s*((?:FIRST|LAST)\s*\([^)]+\))\s*(?:\+\s*(\d+))?\s*\)'
    nested_match = re.match(nested_pattern, expr, re.IGNORECASE)
    
    if nested_match:
        outer_func = nested_match.group(1).upper()
        inner_expr = nested_match.group(2)
        offset = int(nested_match.group(3)) if nested_match.group(3) else 1
        
        # Parse inner function
        inner_info = _parse_simple_navigation(inner_expr)
        
        return NavigationFunctionInfo(
            function_type=outer_func,
            variable=None,
            column=None,
            offset=offset,
            is_nested=True,
            inner_functions=[inner_info],
            raw_expression=expr
        )
    
    # Pattern for simple navigation with arithmetic: FUNC(var.col + offset)
    arithmetic_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\s*\+\s*(\d+)\s*\)'
    arith_match = re.match(arithmetic_pattern, expr, re.IGNORECASE)
    
    if arith_match:
        func_type = arith_match.group(1).upper()
        variable = arith_match.group(2)
        column = arith_match.group(3)
        offset = int(arith_match.group(4))
        
        return NavigationFunctionInfo(
            function_type=func_type,
            variable=variable,
            column=column,
            offset=offset,
            is_nested=False,
            inner_functions=[],
            raw_expression=expr
        )
    
    # Try simple navigation pattern
    return _parse_simple_navigation(expr)

def _parse_simple_navigation(expr: str) -> NavigationFunctionInfo:
    """Parse simple navigation expressions."""
    # Pattern for simple navigation: FUNC(var.col, offset) or FUNC(var.col)
    simple_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\s*(?:,\s*(\d+))?\s*\)'
    simple_match = re.match(simple_pattern, expr, re.IGNORECASE)
    
    if simple_match:
        func_type = simple_match.group(1).upper()
        variable = simple_match.group(2)
        column = simple_match.group(3)
        offset = int(simple_match.group(4)) if simple_match.group(4) else 1
        
        return NavigationFunctionInfo(
            function_type=func_type,
            variable=variable,
            column=column,
            offset=offset,
            is_nested=False,
            inner_functions=[],
            raw_expression=expr
        )
    
    # Pattern for numeric argument only: FUNC(1)
    numeric_pattern = r'(FIRST|LAST)\s*\(\s*(\d+)\s*\)'
    numeric_match = re.match(numeric_pattern, expr, re.IGNORECASE)
    
    if numeric_match:
        return NavigationFunctionInfo(
            function_type=numeric_match.group(1).upper(),
            variable=None,
            column=None,
            offset=int(numeric_match.group(2)),
            is_nested=False,
            inner_functions=[],
            raw_expression=expr
        )
    
    # Pattern for CLASSIFIER function: FUNC(CLASSIFIER())
    classifier_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*CLASSIFIER\s*\(\s*\)\s*\)'
    classifier_match = re.match(classifier_pattern, expr, re.IGNORECASE)
    
    if classifier_match:
        return NavigationFunctionInfo(
            function_type=classifier_match.group(1).upper(),
            variable=None,
            column="CLASSIFIER",
            offset=1,
            is_nested=False,
            inner_functions=[],
            raw_expression=expr
        )
    
    raise ValueError(f"Invalid navigation function syntax: {expr}")

def _validate_nested_navigation(nav_info: NavigationFunctionInfo, pattern_variables: Set[str]) -> Tuple[bool, List[str]]:
    """
    Validate nested navigation function according to SQL standard rules.
    """
    errors = []
    
    # Rule 1 & 2: Check valid nesting combinations
    if nav_info.is_nested:
        outer_func = nav_info.function_type
        if outer_func in ('PREV', 'NEXT'):
            # Physical navigation - check inner functions are logical
            for inner in nav_info.inner_functions:
                if inner.function_type not in ('FIRST', 'LAST'):
                    errors.append(f"Invalid nesting: {inner.function_type} cannot be nested within {outer_func}")
        elif outer_func in ('FIRST', 'LAST'):
            # Logical navigation cannot contain physical navigation
            for inner in nav_info.inner_functions:
                if inner.function_type in ('PREV', 'NEXT'):
                    errors.append(f"Invalid nesting: {inner.function_type} cannot be nested within {outer_func}")
    
    # Rule 3: Pattern navigation functions must have column references
    if _is_pattern_navigation_function(nav_info):
        if not _has_column_reference_or_classifier(nav_info):
            errors.append(f"Pattern navigation function {nav_info.function_type} must contain at least one column reference or CLASSIFIER function")
    
    # Rule 4: Check pattern variable consistency
    variables_used = _extract_pattern_variables(nav_info)
    if len(variables_used) > 1:
        if not _are_variables_consistent(variables_used, pattern_variables):
            errors.append(f"All column references must use the same pattern variable scope. Found: {', '.join(variables_used)}")
    
    return len(errors) == 0, errors

def _is_pattern_navigation_function(nav_info: NavigationFunctionInfo) -> bool:
    """Check if this is a pattern navigation function (used in DEFINE clause)."""
    if nav_info.variable is None and nav_info.column is None:
        return True
    
    # Check if any inner functions lack column references
    for inner in nav_info.inner_functions:
        if _is_pattern_navigation_function(inner):
            return True
    
    return False

def _has_column_reference_or_classifier(nav_info: NavigationFunctionInfo) -> bool:
    """Check if navigation function has column reference or CLASSIFIER function."""
    # Check direct column reference
    if nav_info.variable and nav_info.column:
        return True
    
    # Check for CLASSIFIER function specifically
    if nav_info.column == "CLASSIFIER":
        return True
    
    # Check for CLASSIFIER function in raw expression
    if 'CLASSIFIER(' in nav_info.raw_expression.upper():
        return True
    
    # Check inner functions
    for inner in nav_info.inner_functions:
        if _has_column_reference_or_classifier(inner):
            return True
    
    return False

def _extract_pattern_variables(nav_info: NavigationFunctionInfo) -> Set[str]:
    """Extract all pattern variables used in the navigation function."""
    variables = set()
    
    if nav_info.variable:
        variables.add(nav_info.variable)
    
    for inner in nav_info.inner_functions:
        variables.update(_extract_pattern_variables(inner))
    
    return variables

def _are_variables_consistent(variables: Set[str], pattern_variables: Set[str]) -> bool:
    """Check if all variables are consistent in pattern variable scope."""
    if len(variables) <= 1:
        return True
    
    # Check if all are primary pattern variables
    if all(var in pattern_variables for var in variables):
        return True
    
    # For now, simple consistency check - can be enhanced with subset/universal variable logic
    return False

def _extract_navigation_calls(condition: str) -> List[str]:
    """Extract all navigation function calls from a condition."""
    # Pattern to match navigation functions including nested ones
    pattern = r'((?:PREV|NEXT|FIRST|LAST)\s*\([^)]*(?:\([^)]*\)[^)]*)*\))'
    
    matches = []
    for match in re.finditer(pattern, condition, re.IGNORECASE):
        matches.append(match.group(1))
    
    return matches

def _validate_enhanced_define_conditions(define_conditions: Dict[str, str], pattern_variables: List[str]) -> Tuple[bool, List[str]]:
    """
    Validate all navigation functions in DEFINE conditions using enhanced validation.
    """
    all_errors = []
    pattern_var_set = set(pattern_variables)
    
    for var_name, condition in define_conditions.items():
        # Extract all navigation function calls
        nav_calls = _extract_navigation_calls(condition)
        
        for nav_call in nav_calls:
            try:
                nav_info = _parse_navigation_expression(nav_call)
                is_valid, errors = _validate_nested_navigation(nav_info, pattern_var_set)
                
                if not is_valid:
                    for error in errors:
                        all_errors.append(f"Variable {var_name}: {error}")
                        
            except ValueError as e:
                all_errors.append(f"Variable {var_name}: {str(e)}")
    
    return len(all_errors) == 0, all_errors