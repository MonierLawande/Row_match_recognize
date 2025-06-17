"""
Focused debug script for nested navigation with RUNNING modifier
"""

import sys
import os
import re
sys.path.append(os.path.abspath('.'))

from src.matcher.condition_evaluator import evaluate_nested_navigation

def print_header(title):
    print(f"\n{title}")
    print("=" * 50)

def test_nested_pattern():
    """Test the nested pattern regex directly"""
    print_header("Nested Pattern Test")
    
    # Pattern for nested navigation with enhanced parenthesis matching
    nested_pattern = r'(FIRST|LAST|NEXT|PREV)\s*\(\s*((?:(?:RUNNING|FINAL)\s+)?(?:FIRST|LAST|NEXT|PREV)[^)]+\))\s*(?:,\s*(\d+))?\s*\)'
    
    # Test expressions
    expressions = [
        "PREV(RUNNING LAST(value))",
        "NEXT(RUNNING FIRST(A.value))",
        "PREV(LAST(value))",
        "NEXT(FIRST(value))"
    ]
    
    for expr in expressions:
        match = re.match(nested_pattern, expr, re.IGNORECASE)
        if match:
            groups = match.groups()
            print(f"✓ {expr} - matched: {groups}")
            print(f"  - Outer function: {groups[0]}")
            print(f"  - Inner expression: {groups[1]}")
            print(f"  - Offset: {groups[2] or 1}")
        else:
            print(f"✗ {expr} - not matched")

def test_simple_pattern():
    """Test the simple pattern regex directly"""
    print_header("Simple Pattern Test")
    
    # Pattern for simple navigation
    simple_pattern = r'(?:(RUNNING|FINAL)\s+)?(FIRST|LAST|NEXT|PREV)\s*\(\s*(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s*(?:,\s*(\d+))?\s*\)'
    
    # Test expressions
    expressions = [
        "RUNNING LAST(value)",
        "FINAL FIRST(A.value)",
        "PREV(value)",
        "LAST(A.value, 2)"
    ]
    
    for expr in expressions:
        match = re.match(simple_pattern, expr, re.IGNORECASE)
        if match:
            groups = match.groups()
            print(f"✓ {expr} - matched: {groups}")
            print(f"  - Semantic: {groups[0] or 'None'}")
            print(f"  - Function: {groups[1]}")
            print(f"  - Variable: {groups[2] or 'None'}")
            print(f"  - Field: {groups[3]}")
            print(f"  - Offset: {groups[4] or 1}")
        else:
            print(f"✗ {expr} - not matched")

def create_mock_context():
    """Create a minimal mock context for testing"""
    class MockRow(dict):
        pass
    
    class MockContext:
        def __init__(self):
            self.rows = [
                MockRow({"id": 1, "partition": "p1", "value": 100}),
                MockRow({"id": 2, "partition": "p1", "value": 200}),
                MockRow({"id": 3, "partition": "p1", "value": 300}),
                MockRow({"id": 4, "partition": "p1", "value": 400}),
                MockRow({"id": 5, "partition": "p1", "value": 500})
            ]
            self.variables = {
                'A': [0, 2],  # Rows with id 1 and 3
                'B': [1, 4]   # Rows with id 2 and 5
            }
            self.current_idx = 3  # Currently at row with id 4
            self.navigation_cache = {}
            self._is_running_context = True
        
        def check_same_partition(self, idx1, idx2):
            """Check if two indices are in the same partition"""
            if 0 <= idx1 < len(self.rows) and 0 <= idx2 < len(self.rows):
                return self.rows[idx1].get('partition') == self.rows[idx2].get('partition')
            return False
    
    return MockContext()

def debug_nested_navigation():
    """Debug the nested navigation function with print statements"""
    print_header("Nested Navigation Function Debug")
    
    context = create_mock_context()
    current_row_idx = context.current_idx
    current_var = 'A'  # Current variable
    
    # Test expressions
    expressions = [
        "PREV(value)",               # Simple navigation
        "RUNNING LAST(value)",       # With semantic modifier
        "LAST(A.value)",             # With variable
        "PREV(LAST(value))",         # Nested without semantic
        "PREV(RUNNING LAST(value))"  # Nested with semantic
    ]
    
    for expr in expressions:
        print(f"\nEvaluating: {expr}")
        print("-" * 30)
        
        # Debug regex matching
        nested_pattern = r'(FIRST|LAST|NEXT|PREV)\s*\(\s*((?:(?:RUNNING|FINAL)\s+)?(?:FIRST|LAST|NEXT|PREV)[^)]+\))\s*(?:,\s*(\d+))?\s*\)'
        nested_match = re.match(nested_pattern, expr, re.IGNORECASE)
        
        if nested_match:
            print(f"Matched nested pattern: {nested_match.groups()}")
            outer_func = nested_match.group(1).upper()
            inner_expr = nested_match.group(2)
            print(f"Outer function: {outer_func}")
            print(f"Inner expression: {inner_expr}")
            
            # Test inner expression with simple pattern
            simple_pattern = r'(?:(RUNNING|FINAL)\s+)?(FIRST|LAST|NEXT|PREV)\s*\(\s*(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s*(?:,\s*(\d+))?\s*\)'
            inner_match = re.match(simple_pattern, inner_expr, re.IGNORECASE)
            
            if inner_match:
                print(f"Inner expression matched simple pattern: {inner_match.groups()}")
                inner_semantic = inner_match.group(1)
                inner_func = inner_match.group(2).upper()
                inner_var = inner_match.group(3)
                inner_field = inner_match.group(4)
                print(f"Inner semantic: {inner_semantic or 'None'}")
                print(f"Inner function: {inner_func}")
                print(f"Inner variable: {inner_var or 'None'}")
                print(f"Inner field: {inner_field}")
                
                # For RUNNING LAST, calculate what rows would be considered
                if inner_func == 'LAST' and inner_semantic == 'RUNNING':
                    # All matched rows up to current position
                    all_indices = set()
                    for var_indices in context.variables.values():
                        all_indices.update([idx for idx in var_indices if idx <= current_row_idx])
                    
                    if all_indices:
                        all_indices = sorted(all_indices)
                        print(f"RUNNING indices up to current_idx={current_row_idx}: {all_indices}")
                        
                        # For LAST with RUNNING, it would be the last row in this set
                        inner_target_idx = all_indices[-1]
                        print(f"Inner target (RUNNING LAST): row index {inner_target_idx} with value {context.rows[inner_target_idx]['value']}")
                        
                        # For PREV of this RUNNING LAST, it would be one row before this
                        if outer_func == 'PREV':
                            outer_target_idx = inner_target_idx - 1
                            if 0 <= outer_target_idx < len(context.rows):
                                print(f"Outer target (PREV): row index {outer_target_idx} with value {context.rows[outer_target_idx]['value']}")
                            else:
                                print(f"Outer target (PREV): row index {outer_target_idx} is out of bounds")
        else:
            print(f"Not a nested expression")
        
        # Now try to evaluate the expression
        try:
            result = evaluate_nested_navigation(expr, context, current_row_idx, current_var)
            print(f"Evaluation result: {result}")
        except Exception as e:
            print(f"Evaluation error: {e}")

if __name__ == "__main__":
    test_nested_pattern()
    test_simple_pattern()
    debug_nested_navigation()
