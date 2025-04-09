# src/matcher/measure_evaluator.py

import re
import statistics
from typing import Dict, Any, List, Optional, Set
from src.matcher.row_context import RowContext

class MeasureEvaluator:
    def __init__(self, context: RowContext, final: bool = True):
        self.context = context
        self.final = final

    def evaluate(self, expr: str) -> Any:
        """Evaluate a measure expression with running/final semantics."""
        print(f"Evaluating expression: {expr}")
        print(f"Context variables: {self.context.variables}")
        print(f"Number of rows: {len(self.context.rows)}")
        
        # Check for RUNNING/FINAL keywords
        is_running = not self.final
        if expr.upper().startswith("RUNNING "):
            is_running = True
            expr = expr[8:].strip()
        elif expr.upper().startswith("FINAL "):
            is_running = False
            expr = expr[6:].strip()
        
        # Check for navigation functions first
        if any(expr.upper().startswith(f"{func}(") for func in ["FIRST", "LAST", "PREV", "NEXT"]):
            return self._evaluate_navigation(expr, is_running)
        
        # Check for nested navigation functions
        nested_pattern = r'(PREV|NEXT)\s*\(\s*(FIRST|LAST)\s*\('
        if re.match(nested_pattern, expr.upper()):
            return self._evaluate_navigation(expr, is_running)
        
        # Check for aggregate functions
        agg_match = re.match(r'([A-Z]+)\((.+)\)', expr, re.IGNORECASE)
        if agg_match:
            func_name = agg_match.group(1).lower()
            args_str = agg_match.group(2)
            return self._evaluate_aggregate(func_name, args_str, is_running)
        
        # Direct column reference from current row
        if self.context.rows:
            return self.context.rows[self.context.current_idx].get(expr)
        
        return None

    def _evaluate_navigation(self, expr: str, is_running: bool) -> Any:
        """Evaluate navigation functions like FIRST(), LAST(), PREV(), NEXT() with robust nested support"""
        print(f"Evaluating navigation function: {expr}")
        
        # Check for nested navigation pattern: PREV(FIRST(...))/NEXT(LAST(...))
        nested_pattern = r'(PREV|NEXT)\s*\(\s*(FIRST|LAST)\s*\('
        if re.match(nested_pattern, expr.upper()):
            match = re.match(r'(PREV|NEXT)\s*\(\s*(FIRST|LAST)\s*\(([^)]+)\)\s*(?:,\s*(\d+))?\s*\)', expr, re.IGNORECASE)
            if match:
                outer_func, inner_func, inner_args, steps = match.groups()
                steps = int(steps) if steps else 1
                
                print(f"Processing nested navigation: {outer_func}({inner_func}({inner_args}), {steps})")
                
                # First evaluate the inner function to get the value
                var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', inner_args)
                if var_col_match:
                    var = var_col_match.group(1)
                    col = var_col_match.group(2)
                    
                    # Get indices of rows matching the variable
                    var_indices = self.context.variables.get(var, [])
                    
                    if var_indices:
                        target_idx = None
                        if inner_func.upper() == "FIRST":
                            target_idx = min(var_indices)  # First index
                        elif inner_func.upper() == "LAST":
                            target_idx = max(var_indices)  # Last index
                        
                        if target_idx is not None:
                            # Navigate from the appropriate index
                            if outer_func.upper() == "PREV":
                                nav_idx = target_idx - steps
                                if 0 <= nav_idx < len(self.context.rows):
                                    return self.context.rows[nav_idx].get(col)
                            elif outer_func.upper() == "NEXT":
                                nav_idx = target_idx + steps
                                if 0 <= nav_idx < len(self.context.rows):
                                    return self.context.rows[nav_idx].get(col)
                    
                    # Debug info
                    print(f"  var: {var}, col: {col}, var_indices: {var_indices}")
                    if var_indices:
                        if inner_func.upper() == "FIRST":
                            target_idx = min(var_indices)
                        else:
                            target_idx = max(var_indices)
                        print(f"  target_idx: {target_idx}")
                        
                        if outer_func.upper() == "PREV":
                            nav_idx = target_idx - steps
                            print(f"  nav_idx: {nav_idx}, valid: {0 <= nav_idx < len(self.context.rows)}")
                        else:
                            nav_idx = target_idx + steps
                            print(f"  nav_idx: {nav_idx}, valid: {0 <= nav_idx < len(self.context.rows)}")
            
            # If we get here, the nested function call didn't match the expected format
            print(f"Warning: Failed to evaluate nested function: {expr}")
            return None
        
        # Regular navigation functions
        func_match = re.match(r'([A-Z]+)\((.*?)\)', expr, re.IGNORECASE)
        if not func_match:
            return None
        
        func_name = func_match.group(1).upper()
        args_str = func_match.group(2)
        args = [arg.strip() for arg in args_str.split(',')] if args_str else []
        
        print(f"Function: {func_name}, Args: {args}")

        if func_name in ("FIRST", "LAST"):
            if not args:
                return None
                
            var_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.(.*)', args[0])
            if var_match:
                var = var_match.group(1)
                col = var_match.group(2)
                occurrence = int(args[1]) if len(args) > 1 else 0
                
                if func_name == "FIRST":
                    row = self.context.first(var, occurrence)
                    return row.get(col) if row else None
                else:  # LAST
                    row = self.context.last(var, occurrence)
                    return row.get(col) if row else None
        
        elif func_name in ("PREV", "NEXT"):
            if not args:
                return None
                
            column = args[0]
            steps = int(args[1]) if len(args) > 1 else 1
            
            if func_name == "PREV":
                row = self.context.prev(steps)
                return row.get(column) if row else None
            else:  # NEXT
                row = self.context.next(steps)
                return row.get(column) if row else None
        
        return None

    def _evaluate_aggregate(self, func_name: str, args_str: str, is_running: bool) -> Any:
        """Evaluate aggregate functions like SUM, COUNT, etc."""
        print(f"Evaluating aggregate function: {func_name}({args_str})")
        
        # Handle COUNT(*) special case
        if func_name.lower() == 'count' and args_str.strip() in ('*', ''):
            return len(self.context.rows)
        
        # Parse variable and column references
        var_scope = None
        col_name = None
        
        var_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\\.([A-Za-z_][A-Za-z0-9_]*|\\*)', args_str)
        if var_match:
            var_scope = var_match.group(1)
            col_name = var_match.group(2)
        else:
            col_name = args_str
        
        # Get rows to aggregate over
        rows_to_use = []
        if var_scope:
            # Get rows matched to specific variable
            indices = self.context.variables.get(var_scope, [])
            if is_running:
                indices = [idx for idx in indices if idx <= self.context.current_idx]
            rows_to_use = [self.context.rows[idx] for idx in sorted(indices)]
        else:
            # Use all rows up to current position if running
            if is_running:
                rows_to_use = self.context.rows[:self.context.current_idx + 1]
            else:
                rows_to_use = self.context.rows
        
        # Special handling for COUNT(var.*)
        if func_name.lower() == 'count' and col_name == '*':
            return len(rows_to_use)
        
        # Get values to aggregate
        values = []
        for row in rows_to_use:
            if col_name != '*':
                val = row.get(col_name)
                if val is not None:  # Skip NULL values
                    values.append(val)
        
        # Perform aggregation
        if not values:
            return None
            
        if func_name.lower() == 'count':
            return len(values)
        elif func_name.lower() == 'sum':
            return sum(values)
        elif func_name.lower() == 'avg':
            return sum(values) / len(values)
        elif func_name.lower() == 'min':
            return min(values)
        elif func_name.lower() == 'max':
            return max(values)
        elif func_name.lower() == 'first':
            return values[0]
        elif func_name.lower() == 'last':
            return values[-1]
        
        return None
