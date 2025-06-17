#!/usr/bin/env python3

"""
Apply production-ready fix for SQL:2016 partition handling in match_recognize.

This script permanently patches the condition_evaluator.py file to fix the
partition boundary handling issue that was causing test_sql2016_partition_handling 
to fail.
"""

import os
import sys
import re
from pathlib import Path

def apply_permanent_fix():
    """
    Apply the permanent fix to the condition_evaluator.py file.
    
    The fix changes how partition boundaries are handled to ensure the first row
    in each partition is correctly evaluated regardless of variable state.
    """
    # Get the project root directory
    script_path = Path(__file__).resolve()
    project_root = script_path.parent
    
    # Path to the file we need to patch
    condition_evaluator_path = project_root / 'src' / 'matcher' / 'condition_evaluator.py'
    
    if not condition_evaluator_path.exists():
        print(f"Error: Cannot find {condition_evaluator_path}")
        return False
    
    # Read the current file
    with open(condition_evaluator_path, 'r') as f:
        content = f.read()
    
    # Create a backup of the original file
    backup_path = condition_evaluator_path.with_suffix('.py.bak')
    with open(backup_path, 'w') as f:
        f.write(content)
    
    print(f"Created backup at {backup_path}")
    
    # Find all occurrences of the _get_variable_column_value method
    method_pattern = r'def _get_variable_column_value\(self, var_name: str, col_name: str, ctx: RowContext\) -> Any:.*?# At partition boundary, when evaluating the first pattern variable \(typically \'A\'\),.*?# we should use the current row\'s value.*?if is_partition_boundary and not ctx.variables.get\(var_name, \[\]\):'
    
    # Replace with the fixed implementation
    replacement = '''def _get_variable_column_value(self, var_name: str, col_name: str, ctx: RowContext) -> Any:
        """
        Get a column value from a pattern variable's matched rows with enhanced subset support.
        
        For self-referential conditions (e.g., B.price < A.price when evaluating for B),
        use the current row's value for the variable being evaluated.
        
        Args:
            var_name: Pattern variable name
            col_name: Column name
            ctx: Row context
            
        Returns:
            Column value from the matched row or current row
        """
        # Check if we're in DEFINE evaluation mode
        is_define_mode = self.evaluation_mode == 'DEFINE'
        
        # DEBUG: Enhanced logging to trace exact values
        current_var = getattr(ctx, 'current_var', None)
        logger.debug(f"[DEBUG] _get_variable_column_value: var_name={var_name}, col_name={col_name}, is_define_mode={is_define_mode}, current_var={current_var}")
        logger.debug(f"[DEBUG] ctx.current_idx={ctx.current_idx}, ctx.variables={ctx.variables}")
        
        # CRITICAL FIX: In DEFINE mode, we need special handling for pattern variable references
        if is_define_mode:
            # Check if this is the first row in a partition
            is_partition_boundary = False
            if ctx.partition_boundaries and ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                for start, end in ctx.partition_boundaries:
                    if ctx.current_idx == start:
                        is_partition_boundary = True
                        logger.debug(f"[DEBUG] Found partition boundary at idx={ctx.current_idx}")
                        break
            
            # CRITICAL FIX: At partition boundaries, always use current row's value
            # This ensures the first row in each partition can correctly match the pattern
            if is_partition_boundary:
                logger.debug(f"[DEBUG] PARTITION BOUNDARY: Using current row for {var_name}.{col_name} at idx={ctx.current_idx}")
                if ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                    value = ctx.rows[ctx.current_idx].get(col_name)
                    logger.debug(f"[DEBUG] Partition boundary value: {var_name}.{col_name} = {value} (from row {ctx.current_idx})")
                    return value
            
            # CRITICAL FIX: When evaluating B's condition, B.price should use the current row
            # but A.price should use A's previously matched row
            if var_name == current_var:'''
    
    # Replace the method definition and beginning of the method
    modified_content = re.sub(method_pattern, replacement, content, flags=re.DOTALL)
    
    # Check if any replacements were made
    if modified_content == content:
        print("No changes were made. Could not find the pattern to replace.")
        return False
    
    # Write the modified content back to the file
    with open(condition_evaluator_path, 'w') as f:
        f.write(modified_content)
    
    print(f"Successfully updated {condition_evaluator_path}")
    return True

if __name__ == "__main__":
    success = apply_permanent_fix()
    
    if success:
        print("\nThe fix has been applied successfully.")
        print("You can now run the test to verify that it passes:")
        print("cd tests && python -m pytest test_sql2016_compliance.py::TestSql2016Compliance::test_sql2016_partition_handling -v")
    else:
        print("\nFailed to apply the fix.")
        print("Please check the error messages above for details.")
