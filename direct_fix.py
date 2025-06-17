#!/usr/bin/env python3

"""
Direct fix for the SQL:2016 partition handling test.

This script directly edits the source file to fix the partition boundary issue.
"""

import re
from pathlib import Path

def fix_condition_evaluator():
    """Fix the partition boundary handling in the condition evaluator."""
    # Get the source file path
    file_path = Path(__file__).resolve().parent / "src" / "matcher" / "condition_evaluator.py"
    
    if not file_path.exists():
        print(f"Error: {file_path} not found!")
        return False
    
    # Read the file content
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Create a backup
    with open(f"{file_path}.bak", 'w') as f:
        f.write(content)
    
    # Find and replace the problematic code
    pattern = r'(# At partition boundary, when evaluating the first pattern variable \(typically \'A\'\),\s*# we should use the current row\'s value\s*if is_partition_boundary and not ctx\.variables\.get\(var_name, \[\]\):)'
    replacement = r'# CRITICAL FIX: At partition boundaries, always use current row\'s value\n            # This ensures the first row in each partition can correctly match the pattern\n            if is_partition_boundary:'
    
    new_content = re.sub(pattern, replacement, content)
    
    # Check if any replacement was made
    if new_content == content:
        print("No changes were made. The pattern wasn't found.")
        return False
    
    # Write the changes back
    with open(file_path, 'w') as f:
        f.write(new_content)
    
    print(f"Successfully updated {file_path}")
    print("Backup saved at {file_path}.bak")
    return True

if __name__ == "__main__":
    success = fix_condition_evaluator()
    print(f"Fix applied: {success}")
