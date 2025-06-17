import os
import sys
from pathlib import Path

# Function to patch the file directly
def patch_file(file_path, search_pattern, replacement_pattern):
    """
    Patch a file by replacing a search pattern with a replacement pattern.
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Create a backup
    backup_path = f"{file_path}.bak"
    with open(backup_path, 'w') as f:
        f.write(content)
    
    # Replace the pattern
    modified_content = content.replace(search_pattern, replacement_pattern)
    
    # Write the modified content back
    with open(file_path, 'w') as f:
        f.write(modified_content)
    
    return modified_content != content

# Main function to fix the condition evaluator
def fix_condition_evaluator():
    """
    Fix the condition evaluator to properly handle partition boundaries.
    """
    # Find the project root
    project_root = Path(__file__).resolve().parent
    
    # Path to the condition evaluator file
    condition_evaluator_path = project_root / "src" / "matcher" / "condition_evaluator.py"
    
    if not condition_evaluator_path.exists():
        print(f"Error: Could not find {condition_evaluator_path}")
        return False
    
    # The pattern to search for - this is the problematic code
    search_pattern = """            # Critical fix for partition boundary handling
            # Check if this is the first row in a partition and we're evaluating the first variable in the pattern
            is_partition_boundary = False
            if ctx.partition_boundaries and ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                for start, end in ctx.partition_boundaries:
                    if ctx.current_idx == start:
                        is_partition_boundary = True
                        break
            
            # At partition boundary, when evaluating the first pattern variable (typically 'A'),
            # we should use the current row's value
            if is_partition_boundary and not ctx.variables.get(var_name, []):"""
    
    # The replacement pattern with the fix
    replacement_pattern = """            # Critical fix for partition boundary handling
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
            if is_partition_boundary:"""
    
    # Apply the patch
    success = patch_file(condition_evaluator_path, search_pattern, replacement_pattern)
    
    if success:
        print(f"Successfully patched {condition_evaluator_path}")
        print("The partition boundary handling has been fixed.")
    else:
        print(f"Failed to patch {condition_evaluator_path}")
        print("The search pattern was not found in the file.")
    
    return success

if __name__ == "__main__":
    fix_condition_evaluator()
