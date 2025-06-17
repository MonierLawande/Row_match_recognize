#!/usr/bin/env python3

"""
Test AST evaluation directly with the preprocessed expression.
"""

import sys
import os
import pandas as pd
import ast
import logging

# Add the src directory to path
sys.path.append(os.path.abspath('.'))

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG)

def test_ast_direct():
    """Test AST evaluation directly with preprocessed expressions."""
    
    from src.matcher.condition_evaluator import ConditionEvaluator
    from src.matcher.row_context import RowContext
    
    print("=== Direct AST Evaluation Test ===")
    
    # Test with preprocessed expressions
    test_cases = [
        "1 IN (0, 1)",  # Should be True
        "2 IN (0, 2)",  # Should be True
        "3 IN (0, 3)",  # Should be True
        "4 IN (0, 4)",  # Should be True
        "5 IN (0, 1, 2, 3, 4)",  # Should be False
        "1 IN [0, 1]",  # Alternative syntax with list
    ]
    
    for expr in test_cases:
        print(f"\nTesting expression: '{expr}'")
        
        try:
            # Test AST parsing
            tree = ast.parse(expr, mode='eval')
            print(f"  AST parsing: SUCCESS")
            print(f"  AST dump: {ast.dump(tree)}")
            
            # Create a mock context
            context = RowContext()
            context.match_number = 1
            context.current_idx = 0
            context.variables = {'A': [0]}
            context.rows = [{'id': 1, 'value': 100}]
            
            # Test evaluation
            evaluator = ConditionEvaluator(context, evaluation_mode='MEASURES')
            try:
                result = evaluator.visit(tree.body)
                print(f"  Evaluation result: {result} (type: {type(result)})")
            except Exception as eval_error:
                print(f"  Evaluation FAILED: {eval_error}")
                import traceback
                traceback.print_exc()
                
        except SyntaxError as parse_error:
            print(f"  AST parsing FAILED: {parse_error}")

if __name__ == "__main__":
    test_ast_direct()
