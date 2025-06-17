#!/usr/bin/env python3

"""
Fix the compile_condition function in condition_evaluator.py to properly handle 
complex conditions like 'value = 10 OR value = 15'.
"""

import re
from pathlib import Path

def fix_compile_condition():
    """Fix the compile_condition function."""
    # Get the source file path
    file_path = Path(__file__).resolve().parent / "src" / "matcher" / "condition_evaluator.py"
    
    if not file_path.exists():
        print(f"Error: {file_path} not found!")
        return False
    
    # Read the file content
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Create a backup if one doesn't exist
    backup_path = Path(f"{file_path}.bak2")
    if not backup_path.exists():
        with open(backup_path, 'w') as f:
            f.write(content)
        print(f"Backup saved at {backup_path}")
    
    # Find the compile_condition function and fix it
    pattern = r"def compile_condition\(condition_str, evaluation_mode='DEFINE'\):.*?return lambda row, ctx: False"
    
    # The corrected implementation
    replacement = '''def compile_condition(condition_str, evaluation_mode='DEFINE'):
    """
    Compile a condition string into a callable function.
    
    Args:
        condition_str: SQL condition string
        evaluation_mode: 'DEFINE' for pattern definitions, 'MEASURES' for measures
        
    Returns:
        A callable function that takes a row and context and returns a boolean
    """
    if not condition_str or condition_str.strip().upper() == 'TRUE':
        # Optimization for true condition
        return lambda row, ctx: True
        
    if condition_str.strip().upper() == 'FALSE':
        # Optimization for false condition
        return lambda row, ctx: False
    
    try:
        # Parse the condition
        tree = ast.parse(condition_str, mode='eval')
        
        # Create a function that evaluates the condition with the given row and context
        def evaluate_condition(row, ctx):
            # Create evaluator with the given context
            evaluator = ConditionEvaluator(ctx, evaluation_mode)
            
            # Set the current row
            evaluator.current_row = row
            
            # Evaluate the condition
            try:
                result = evaluator.visit(tree.body)
                return bool(result)
            except Exception as e:
                logger.error(f"Error evaluating condition '{condition_str}': {e}")
                return False
                
        return evaluate_condition
    except SyntaxError as e:
        # Log the error and return a function that always returns False
        logger.error(f"Syntax error in condition '{condition_str}': {e}")
        return lambda row, ctx: False
    except Exception as e:
        # Log the error and return a function that always returns False
        logger.error(f"Error compiling condition '{condition_str}': {e}")
        return lambda row, ctx: False'''
    
    # Replace the function
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
    success = fix_compile_condition()
    print(f"Fix applied: {success}")
