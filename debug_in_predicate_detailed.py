#!/usr/bin/env python3

"""
Detailed debug script for IN predicate with MATCH_NUMBER issue.
This script will enable more detailed debugging to trace exactly where the issue occurs.
"""

import sys
import os
import pandas as pd
import re
import logging

# Add the src directory to path
sys.path.append(os.path.abspath('.'))

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG)

from src.executor.match_recognize import match_recognize

def test_pattern_variable_reference():
    """Test the pattern variable reference function directly."""
    
    from src.matcher.measure_evaluator import evaluate_pattern_variable_reference
    
    expr = "MATCH_NUMBER() IN (0, MATCH_NUMBER())"
    var_assignments = {'A': [0]}
    all_rows = [{'id': 1, 'value': 100}]
    
    print(f"\n=== Direct Pattern Variable Reference Test ===")
    print(f"Expression: '{expr}'")
    
    # Test the regex match directly
    var_col_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$', expr)
    print(f"Regex match result: {var_col_match}")
    
    # Test the function call
    handled, value = evaluate_pattern_variable_reference(
        expr, var_assignments, all_rows, None, None, 0, True, False
    )
    
    print(f"Function result: handled={handled}, value={value}")
    
    # Test with a simple expression that should work
    simple_expr = "A.value"
    print(f"\n=== Simple Pattern Variable Test ===")
    print(f"Expression: '{simple_expr}'")
    
    var_col_match2 = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$', simple_expr)
    print(f"Regex match result: {var_col_match2}")
    
    handled2, value2 = evaluate_pattern_variable_reference(
        simple_expr, var_assignments, all_rows, None, None, 0, True, False
    )
    
    print(f"Function result: handled={handled2}, value={value2}")

def test_ast_evaluation():
    """Test AST evaluation directly."""
    
    print(f"\n=== AST Evaluation Test ===")
    
    # Test if the expression can be parsed as AST
    import ast
    expr = "MATCH_NUMBER() IN (0, MATCH_NUMBER())"
    
    try:
        tree = ast.parse(expr, mode='eval')
        print(f"AST parsing successful: {ast.dump(tree)}")
        
        # Try to evaluate it with a mock context
        from src.matcher.condition_evaluator import ConditionEvaluator
        from src.matcher.row_context import RowContext
        
        # Create a mock context
        context = RowContext()
        context.match_number = 1
        context.current_idx = 0
        context.variables = {'A': [0]}
        context.rows = [{'id': 1, 'value': 100}]
        
        evaluator = ConditionEvaluator(context, evaluation_mode='MEASURES')
        
        try:
            result = evaluator.visit(tree.body)
            print(f"AST evaluation result: {result}")
        except Exception as e:
            print(f"AST evaluation failed: {e}")
            import traceback
            traceback.print_exc()
        
    except SyntaxError as e:
        print(f"AST parsing failed: {e}")

def debug_in_predicate():
    """Debug the IN predicate with MATCH_NUMBER issue."""
    
    print("=== Debugging IN Predicate with MATCH_NUMBER ===")
    
    # Test components first
    test_pattern_variable_reference()
    test_ast_evaluation()
    
    # Test data from the failing test
    df = pd.DataFrame({
        'id': [1, 2, 3, 4],
        'value': [100, 200, 300, 400]
    })
    
    print("Input Data:")
    print(df)
    
    query = """
    SELECT val
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES MATCH_NUMBER() IN (0, MATCH_NUMBER()) AS val
        ONE ROW PER MATCH
        AFTER MATCH SKIP TO NEXT ROW
        PATTERN (A+)
        DEFINE A AS true
    ) AS m
    """
    
    print("\nQuery:")
    print(query)
    
    print("\nRunning match_recognize...")
    result = match_recognize(query, df)
    
    print(f"\nResult shape: {result.shape}")
    print(f"Result columns: {list(result.columns)}")
    print(f"Result empty: {result.empty}")
    
    if not result.empty:
        print("\nResult DataFrame:")
        print(result)
        print(f"\nResult dtypes: {result.dtypes}")
        
        print("\n=== Detailed Analysis ===")
        print("Val column values:")
        for i, val in enumerate(result['val']):
            print(f"  Row {i}: {val} (type: {type(val)})")
        
        print("\nExpected: All values should be True")
        print(f"Actual: {list(result['val'])}")

if __name__ == "__main__":
    debug_in_predicate()
