#!/usr/bin/env python3

"""
Fix for the missing validate_navigation_conditions function in condition_evaluator.py.

This script adds the missing validate_navigation_conditions function that's imported by other modules.
"""

import re
from pathlib import Path

def fix_missing_function():
    """Add the missing validate_navigation_conditions function to condition_evaluator.py."""
    # Get the source file path
    file_path = Path(__file__).resolve().parent / "src" / "matcher" / "condition_evaluator.py"
    
    if not file_path.exists():
        print(f"Error: {file_path} not found!")
        return False
    
    # The missing function to add
    missing_function = '''
def validate_navigation_conditions(pattern_variables, define_clauses):
    """
    Validate that navigation function calls in conditions are valid for the pattern.
    
    For example, navigation calls that reference pattern variables that don't appear
    in the pattern or haven't been matched yet are invalid.
    
    Args:
        pattern_variables: List of pattern variables from the pattern definition
        define_clauses: Dict mapping variable names to their conditions
        
    Returns:
        True if all navigation conditions are valid, False otherwise
    """
    # Validate each condition for each variable
    for var, condition in define_clauses.items():
        if var not in pattern_variables:
            logger.warning(f"Variable {var} in DEFINE clause not found in pattern")
            continue
            
        # Validate navigation references to other variables
        for ref_var in pattern_variables:
            # Skip self-references (always valid)
            if ref_var == var:
                continue
                
            # Find PREV(var) references
            if f"PREV({ref_var}" in condition:
                # Ensure the referenced variable appears before this one in the pattern
                var_idx = pattern_variables.index(var)
                ref_idx = pattern_variables.index(ref_var)
                
                if ref_idx >= var_idx:
                    logger.error(f"Invalid PREV({ref_var}) reference in condition for {var}: "
                               f"{ref_var} does not appear before {var} in the pattern")
                    return False
            
            # Find NEXT(var) references
            if f"NEXT({ref_var}" in condition:
                # Ensure the referenced variable appears after this one in the pattern
                var_idx = pattern_variables.index(var)
                ref_idx = pattern_variables.index(ref_var)
                
                if ref_idx <= var_idx:
                    logger.error(f"Invalid NEXT({ref_var}) reference in condition for {var}: "
                               f"{ref_var} does not appear after {var} in the pattern")
                    return False
    
    # If all checks pass
    return True
'''

    # Read the file content
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Check if a backup already exists and create one if not
    backup_path = Path(f"{file_path}.bak")
    if not backup_path.exists():
        with open(backup_path, 'w') as f:
            f.write(content)
        print(f"Backup saved at {backup_path}")
    
    # Add the missing function after the compile_condition function
    pattern = r"(def compile_condition.*?return lambda row, ctx: False\n)"
    replacement = r"\1\n" + missing_function
    
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Check if any replacement was made
    if new_content == content:
        print("No changes were made. The pattern wasn't found.")
        return False
    
    # Write the changes back
    with open(file_path, 'w') as f:
        f.write(new_content)
    
    print(f"Successfully updated {file_path}")
    return True

if __name__ == "__main__":
    success = fix_missing_function()
    print(f"Fix applied: {success}")
