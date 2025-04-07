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
        # Check for RUNNING/FINAL keywords
        is_running = not self.final
        if expr.upper().startswith("RUNNING "):
            is_running = True
            expr = expr[8:].strip()
        elif expr.upper().startswith("FINAL "):
            is_running = False
            expr = expr[6:].strip()
            
        # Check for aggregate functions
        agg_match = re.match(r'(\w+)\((.*)\)', expr)
        if agg_match:
            func_name = agg_match.group(1).lower()
            args_str = agg_match.group(2)
            
            return self._evaluate_aggregate(func_name, args_str, is_running)
            
        # Check for pattern variable references
        var_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', expr)
        if var_match:
            var = var_match.group(1)
            col = var_match.group(2)
            
            if is_running:
                # Return value from the most recently matched row for this variable
                rows = self.context.var_rows(var)
                for idx in sorted(self.context.variables.get(var, []), reverse=True):
                    if idx <= self.context.current_idx:
                        return self.context.rows[idx].get(col)
                return None
            else:
                # Return value from the last row matched to this variable
                rows = self.context.var_rows(var)
                return rows[-1].get(col) if rows else None
                
        # Check for navigation functions
        if expr.upper().startswith(("FIRST(", "LAST(", "PREV(", "NEXT(")):
            return self._evaluate_navigation(expr, is_running)
            
        # Direct column reference - from current row
        if self.context.rows:
            return self.context.rows[self.context.current_idx].get(expr)
        
        return None
        
    def _evaluate_aggregate(self, func_name: str, args_str: str, is_running: bool) -> Any:
        """Evaluate aggregate functions like avg, sum, count, etc."""
        # Parse arguments and determine variable scope
        var_scope = None
        count_all = False
        
        # Handle special COUNT(*) syntax
        if func_name.lower() == "count" and args_str.strip() in ("*", ""):
            count_all = True
            args = []
        else:
            # Check for variable-prefixed arguments
            var_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z0-9_*]+)', args_str)
            if var_match:
                var_scope = var_match.group(1)
                args_str = var_match.group(2)
                
                # Handle COUNT(A.*) special syntax
                if func_name.lower() == "count" and args_str == "*":
                    count_all = True
                    args = []
                else:
                    args = [args_str]
            else:
                # No variable scope - use all rows
                args = [arg.strip() for arg in args_str.split(',')]
        
        # Get rows to aggregate over
        rows_to_use = []
        if var_scope:
            # Get only rows matched to the specified variable
            indices = []
            if var_scope in self.context.variables:
                indices = self.context.variables[var_scope]
            elif var_scope in self.context.subsets:
                for comp in self.context.subsets[var_scope]:
                    indices.extend(self.context.variables.get(comp, []))
                    
            # For running semantics, only use rows up to current position
            if is_running:
                indices = [idx for idx in indices if idx <= self.context.current_idx]
                
            rows_to_use = [self.context.rows[idx] for idx in sorted(indices)]
        else:
            # Use all rows in the match up to current position if running
            if is_running:
                rows_to_use = self.context.rows[:self.context.current_idx + 1]
            else:
                rows_to_use = self.context.rows
        
        # Perform the aggregation
        if count_all:
            return len(rows_to_use)
            
        # Extract values for the arguments
        values = []
        for row in rows_to_use:
            if len(args) == 1:  # Simple case: single column
                values.append(row.get(args[0]))
            else:
                # Multiple arguments not fully implemented yet
                pass
        
        # Remove None values (NULL handling)
        values = [v for v in values if v is not None]
        
        # Compute the aggregate
        if not values:
            return None
            
        if func_name.lower() == "count":
            return len(values)
        elif func_name.lower() == "sum":
            return sum(values)
        elif func_name.lower() == "avg":
            return sum(values) / len(values) if values else None
        elif func_name.lower() == "min":
            return min(values)
        elif func_name.lower() == "max":
            return max(values)
        elif func_name.lower() == "stddev":
            return statistics.stdev(values) if len(values) > 1 else 0
        
        return None
        
    def _evaluate_navigation(self, expr: str, is_running: bool) -> Any:
        """Evaluate navigation functions like FIRST(), LAST(), PREV(), NEXT()"""
        func_match = re.match(r'([A-Z]+)\((.*)\)', expr, re.IGNORECASE)
        if not func_match:
            return None
            
        func_name = func_match.group(1).upper()
        args_str = func_match.group(2)
        
        # Parse arguments
        args = [arg.strip() for arg in args_str.split(',')]
        
        if func_name == "PREV":
            col = args[0]
            steps = int(args[1]) if len(args) > 1 else 1
            row = self.context.prev(steps)
            return row.get(col) if row else None
            
        elif func_name == "NEXT":
            col = args[0]
            steps = int(args[1]) if len(args) > 1 else 1
            row = self.context.next(steps)
            return row.get(col) if row else None
            
        elif func_name == "FIRST":
            # Parse variable.column format
            var_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', args[0])
            if var_match:
                var = var_match.group(1)
                col = var_match.group(2)
                occurrence = int(args[1]) if len(args) > 1 else 0
                row = self.context.first(var, occurrence)
                return row.get(col) if row else None
                
        elif func_name == "LAST":
            # Parse variable.column format
            var_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', args[0])
            if var_match:
                var = var_match.group(1)
                col = var_match.group(2)
                occurrence = int(args[1]) if len(args) > 1 else 0
                
                if is_running:
                    # For running semantics, only consider rows up to current position
                    indices = [idx for idx in self.context.variables.get(var, []) 
                              if idx <= self.context.current_idx]
                    if occurrence < len(indices):
                        return self.context.rows[indices[-(occurrence+1)]].get(col)
                    return None
                else:
                    row = self.context.last(var, occurrence)
                    return row.get(col) if row else None
        
        return None
