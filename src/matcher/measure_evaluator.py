# src/matcher/measure_evaluator.py

import re
import statistics
import time
from collections import defaultdict
from typing import Dict, Any, List, Optional, Set, Union, Tuple
from src.matcher.row_context import RowContext

class ClassifierError(Exception):
    """Error in CLASSIFIER function evaluation."""
    pass

class MeasureEvaluator:
    def __init__(self, context: RowContext, final: bool = True):
        self.context = context
        self.final = final
        self.original_expr = None
        # Add cache for classifier lookups
        self._classifier_cache = {}
        self.timing = defaultdict(float)
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "total_evaluations": 0
        }

    def evaluate(self, expr: str, semantics: str = None) -> Any:
        """
        Evaluate a measure expression with proper RUNNING/FINAL semantics.
        
        Args:
            expr: The expression to evaluate
            semantics: Optional semantics override ("RUNNING" or "FINAL")
            
        Returns:
            The evaluated result of the expression
        """
        # Use passed semantics or instance default
        is_running = (semantics == 'RUNNING') if semantics else not self.final
        
        print(f"Evaluating expression: {expr} with {('FINAL' if not is_running else 'RUNNING')} semantics")
        print(f"Context variables: {self.context.variables}")
        print(f"Number of rows: {len(self.context.rows)}")
        print(f"Current index: {self.context.current_idx}")
        
        # Store original expression for reference
        self.original_expr = expr
        
        # Ensure current_idx is always defined and valid
        if not hasattr(self.context, 'current_idx') or self.context.current_idx is None:
            self.context.current_idx = 0
        
        if len(self.context.rows) > 0 and self.context.current_idx >= len(self.context.rows):
            self.context.current_idx = len(self.context.rows) - 1
            
        # Enhanced CLASSIFIER handling with caching
        classifier_pattern = r'CLASSIFIER\(\s*([A-Za-z][A-Za-z0-9_]*)?\s*\)'
        classifier_match = re.match(classifier_pattern, expr, re.IGNORECASE)
        if classifier_match:
            var_name = classifier_match.group(1)
            return self.evaluate_classifier(var_name, running=is_running)
                    
        # Special handling for MATCH_NUMBER
        if expr.upper().strip() == "MATCH_NUMBER()":
            return self.context.match_number

        # Remove RUNNING/FINAL prefix if present
        if expr.upper().startswith("RUNNING "):
            is_running = True
            expr = expr[8:].strip()
        elif expr.upper().startswith("FINAL "):
            is_running = False
            expr = expr[6:].strip()
            
        # Handle non-aggregation column references
        if not any(func in expr.upper() for func in ["COUNT", "SUM", "AVG", "MIN", "MAX", "FIRST", "LAST", "PREV", "NEXT"]):
            if not any(c in expr for c in "().*+-/"):
                if not is_running:
                    for var, indices in self.context.variables.items():
                        if indices:
                            last_idx = max(indices)
                            if last_idx < len(self.context.rows):
                                return self.context.rows[last_idx].get(expr)
                return self.context.rows[self.context.current_idx].get(expr)
        
        # Check for navigation functions
        if any(expr.upper().startswith(f"{func}(") for func in ["FIRST", "LAST", "PREV", "NEXT"]):
            return self._evaluate_navigation(expr, is_running)
            
        # Check for aggregate functions
        agg_match = re.match(r'([A-Z]+)\((.+)\)', expr, re.IGNORECASE)
        if agg_match:
            func_name = agg_match.group(1).lower()
            args_str = agg_match.group(2)
            return self._evaluate_aggregate(func_name, args_str, is_running)
            
        # Try to evaluate as a raw expression
        try:
            return self.context.rows[self.context.current_idx].get(expr)
        except Exception as e:
            print(f"Error evaluating expression '{expr}': {e}")
            return None

    def evaluate_classifier(self, 
                           var_name: Optional[str] = None, 
                           *, 
                           running: bool = True) -> Optional[str]:
        """
        Evaluate CLASSIFIER function according to SQL standard.
        
        Args:
            var_name: Optional variable name to check against
            running: Whether to use RUNNING semantics (default: True)
            
        Returns:
            String containing the pattern variable name or None if not matched
            
        Examples:
            >>> evaluator.evaluate_classifier()  # Returns current row's variable
            'A'
            >>> evaluator.evaluate_classifier('A')  # Returns 'A' if row matches A
            'A'
            >>> evaluator.evaluate_classifier('B')  # Returns None if no match
            None
            
        Raises:
            ClassifierError: If the variable name is invalid
        """
        start_time = time.time()
        self.stats["total_evaluations"] += 1
        
        try:
            # Validate argument
            self._validate_classifier_arg(var_name)
            
            current_idx = self.context.current_idx
            cache_key = (current_idx, var_name, running)
            
            # Check cache first
            if cache_key in self._classifier_cache:
                self.stats["cache_hits"] += 1
                return self._classifier_cache[cache_key]
                
            self.stats["cache_misses"] += 1
            
            result = self._evaluate_classifier_impl(var_name, running)
            
            # Cache the result
            self._classifier_cache[cache_key] = result
            return result
            
        finally:
            self.timing["classifier_evaluation"] += time.time() - start_time

    def _validate_classifier_arg(self, var_name: Optional[str]) -> None:
        """
        Validate CLASSIFIER function argument.
        
        Args:
            var_name: Optional variable name to check against
            
        Raises:
            ClassifierError: If the argument is invalid
        """
        if var_name is not None:
            if not isinstance(var_name, str):
                raise ClassifierError(f"CLASSIFIER argument must be a string, got {type(var_name)}")
                
            if not var_name.isidentifier():
                raise ClassifierError(f"Invalid variable name: {var_name}")
                
            # Only check if variable exists in pattern if we have variables
            if self.context.variables and var_name not in self.context.variables and (
                not hasattr(self.context, 'subsets') or 
                var_name not in self.context.subsets
            ):
                raise ClassifierError(f"Variable '{var_name}' not found in pattern")

    def _evaluate_classifier_impl(self, 
                                var_name: Optional[str] = None,
                                running: bool = True) -> Optional[str]:
        """
        Internal implementation of CLASSIFIER evaluation.
        
        Args:
            var_name: Optional variable name to check against
            running: Whether to use RUNNING semantics
            
        Returns:
            String containing the pattern variable name or None if not matched
        """
        current_idx = self.context.current_idx
        
        # Handle CLASSIFIER() without arguments
        if var_name is None:
            result = None
            # First check primary variables
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    result = var
                    break
                    
            # Then check subset variables if no primary match found
            if result is None and hasattr(self.context, 'subsets') and self.context.subsets:
                for subset_name, components in self.context.subsets.items():
                    for comp in components:
                        if comp in self.context.variables and current_idx in self.context.variables[comp]:
                            result = comp
                            break
                    if result:
                        break
            
            return result
        
        # Handle CLASSIFIER(var) with argument - improved NULL handling
        if var_name in self.context.variables:
            return var_name if current_idx in self.context.variables[var_name] else None
        
        # Handle subset variables
        if hasattr(self.context, 'subsets') and var_name in self.context.subsets:
            for comp in self.context.subsets[var_name]:
                if comp in self.context.variables and current_idx in self.context.variables[comp]:
                    return comp
        
        # No match found
        return None

    def _format_classifier_output(self, value: Optional[str]) -> str:
        """
        Format CLASSIFIER output according to SQL standard.
        
        Args:
            value: The classifier value to format
            
        Returns:
            Formatted classifier output (NULL for None)
        """
        return value if value is not None else "NULL"

    def _evaluate_navigation(self, expr: str, is_running: bool) -> Any:
        """
        Evaluate navigation functions with comprehensive support.
        
        Args:
            expr: The navigation expression to evaluate
            is_running: Whether to use RUNNING semantics
            
        Returns:
            The result of the navigation function
        """
        print(f"Evaluating navigation function: {expr}")
        
        # Handle nested navigation functions (e.g., PREV(FIRST(A.val)))
        nested_pattern = r'(PREV|NEXT)\s*\(\s*(FIRST|LAST)\s*\('
        if re.match(nested_pattern, expr.upper()):
            match = re.match(r'(PREV|NEXT)\s*\(\s*(FIRST|LAST)\s*\(([^)]+)\)\s*(?:,\s*(\d+))?\s*\)', expr, re.IGNORECASE)
            if match:
                outer_func, inner_func, inner_args, steps = match.groups()
                steps = int(steps) if steps else 1
                
                print(f"Processing nested navigation: {outer_func}({inner_func}({inner_args}), {steps})")
                
                # Parse the inner args - expecting pattern_var.column
                var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\\.([A-Za-z_][A-Za-z0-9_]*)', inner_args)
                if var_col_match:
                    var = var_col_match.group(1)
                    col = var_col_match.group(2)
                    
                    # Get all rows matched to the pattern variable
                    var_indices = self._get_var_indices(var)
                    
                    if var_indices:
                        target_idx = None
                        # Use first or last matched row
                        if inner_func.upper() == "FIRST":
                            target_idx = min(var_indices)
                        elif inner_func.upper() == "LAST":
                            target_idx = max(var_indices)
                        
                        if target_idx is not None:
                            # Navigate relative to the target row
                            if outer_func.upper() == "PREV":
                                nav_idx = target_idx - steps
                            else:  # NEXT
                                nav_idx = target_idx + steps
                            
                            # Check bounds
                            if 0 <= nav_idx < len(self.context.rows):
                                return self.context.rows[nav_idx].get(col)
                    
                    # Debug info for troubleshooting
                    print(f"  var: {var}, col: {col}, var_indices: {var_indices}")
        
        # Regular (non-nested) navigation functions
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
                
            # Handle both A.col and just col formats
            var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\\.([A-Za-z_][A-Za-z0-9_]*)', args[0])
            if var_col_match:
                var = var_col_match.group(1)
                col = var_col_match.group(2)
                occurrence = int(args[1]) if len(args) > 1 else 0
                
                # Get indices of rows matched to the variable
                var_indices = self._get_var_indices(var)
                if not var_indices:
                    return None
                    
                # Sort indices
                var_indices = sorted(var_indices)
                
                # For RUNNING semantics, only consider rows up to current_idx
                if is_running:
                    var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
                    if not var_indices:
                        return None
                
                if func_name == "FIRST":
                    if occurrence < len(var_indices):
                        row_idx = var_indices[occurrence]
                        return self.context.rows[row_idx].get(col)
                else:  # LAST
                    if occurrence < len(var_indices):
                        row_idx = var_indices[-(occurrence+1)]
                        return self.context.rows[row_idx].get(col)
                        
            # If not var.col format, treat as a universal column
            else:
                col = args[0]
                occurrence = int(args[1]) if len(args) > 1 else 0
                
                # Get all matched rows
                matched_indices = []
                for indices in self.context.variables.values():
                    matched_indices.extend(indices)
                
                # Sort indices
                matched_indices = sorted(matched_indices)
                
                # For RUNNING semantics, only consider rows up to current_idx
                if is_running:
                    matched_indices = [idx for idx in matched_indices if idx <= self.context.current_idx]
                    if not matched_indices:
                        return None
                
                if matched_indices:
                    if func_name == "FIRST":
                        if occurrence < len(matched_indices):
                            row_idx = matched_indices[occurrence]
                            return self.context.rows[row_idx].get(col)
                    else:  # LAST
                        if occurrence < len(matched_indices):
                            row_idx = matched_indices[-(occurrence+1)]
                            return self.context.rows[row_idx].get(col)
        
        elif func_name in ("PREV", "NEXT"):
            if not args:
                return None
            
            # Default to navigation relative to current row
            current_idx = self.context.current_idx
            column = args[0]
            steps = int(args[1]) if len(args) > 1 else 1
            
            if func_name == "PREV":
                nav_idx = current_idx - steps
                if 0 <= nav_idx < len(self.context.rows):
                    return self.context.rows[nav_idx].get(column)
            else:  # NEXT
                nav_idx = current_idx + steps
                if 0 <= nav_idx < len(self.context.rows):
                    return self.context.rows[nav_idx].get(column)
        
        return None

    def _get_var_indices(self, var: str) -> List[int]:
        """
        Get indices of rows matched to a variable or subset.
        
        Args:
            var: The variable name
            
        Returns:
            List of row indices that match the variable
        """
        # Direct variable
        if var in self.context.variables:
            return sorted(self.context.variables[var])
        
        # Check for subset variable
        if hasattr(self.context, 'subsets') and var in self.context.subsets:
            indices = []
            for comp_var in self.context.subsets[var]:
                if comp_var in self.context.variables:
                    indices.extend(self.context.variables[comp_var])
            return sorted(indices)
        
        return []

    def _evaluate_aggregate(self, func_name: str, args_str: str, is_running: bool) -> Any:
        """
        Evaluate aggregate functions like SUM, COUNT, etc.
        
        Args:
            func_name: The aggregate function name
            args_str: Function arguments as string
            is_running: Whether to use RUNNING semantics
            
        Returns:
            Result of the aggregate function
        """
        print(f"Evaluating aggregate function: {func_name}({args_str})")
        
        # Handle COUNT(*) special case
        if func_name.lower() == 'count' and args_str.strip() in ('*', ''):
            if is_running:
                # For RUNNING semantics, count rows up to current position
                return self.context.current_idx + 1
            else:
                # For FINAL semantics, count all rows
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
                # For RUNNING semantics, only consider rows up to current_idx
                indices = [idx for idx in indices if idx <= self.context.current_idx]
            rows_to_use = [self.context.rows[idx] for idx in sorted(indices) if idx < len(self.context.rows)]
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
