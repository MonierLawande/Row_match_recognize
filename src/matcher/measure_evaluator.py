# src/matcher/measure_evaluator.py

import re
import statistics
import time
from collections import defaultdict
from typing import Dict, Any, List, Optional, Set, Union, Tuple
from src.matcher.row_context import RowContext
# src/matcher/measure_evaluator.py

import re
import statistics
import time
from collections import defaultdict
from functools import lru_cache
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
        # Add cache for classifier lookups with LRU cache policy
        self._classifier_cache = {}
        self.timing = defaultdict(float)
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "total_evaluations": 0
        }
        
        # Create row-to-variable index for fast lookup
        self._build_row_variable_index()
        
    def _build_row_variable_index(self):
        """Build an index of which variables each row belongs to for faster lookup."""
        self._row_to_vars = defaultdict(set)
        for var, indices in self.context.variables.items():
            for idx in indices:
                self._row_to_vars[idx].add(var)
        
        # Pre-compute subset memberships too
        if hasattr(self.context, 'subsets') and self.context.subsets:
            for subset_name, components in self.context.subsets.items():
                for comp in components:
                    if comp in self.context.variables:
                        for idx in self.context.variables[comp]:
                            self._row_to_vars[idx].add(subset_name)

        # src/matcher/measure_evaluator.py

    def evaluate(self, expr: str, semantics: str = None) -> Any:
        """
        Evaluate a measure expression with proper RUNNING/FINAL semantics.
        
        Args:
            expr: The expression to evaluate
            semantics: Optional semantics override ('RUNNING' or 'FINAL')
            
        Returns:
            The result of the expression evaluation
        """
        # Use passed semantics or instance default
        is_running = (semantics == 'RUNNING') if semantics else not self.final
        
        print(f"Evaluating expression: {expr} with {('FINAL' if not is_running else 'RUNNING')} semantics")
        print(f"Context variables: {self.context.variables}")
        print(f"Number of rows: {len(self.context.rows)}")
        print(f"Current index: {self.context.current_idx}")
        
        # Store original expression for reference
        self.original_expr = expr
        
        # Check for explicit RUNNING/FINAL prefix
        running_match = re.match(r'RUNNING\s+(.+)', expr, re.IGNORECASE)
        final_match = re.match(r'FINAL\s+(.+)', expr, re.IGNORECASE)
        
        if running_match:
            expr = running_match.group(1)
            is_running = True
        elif final_match:
            expr = final_match.group(1)
            is_running = False
        
        # Ensure current_idx is always defined and valid
        if not hasattr(self.context, 'current_idx') or self.context.current_idx is None:
            self.context.current_idx = 0
        
        if len(self.context.rows) > 0 and self.context.current_idx >= len(self.context.rows):
            self.context.current_idx = len(self.context.rows) - 1
        
        # Special handling for pattern variable references like A.salary
        var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\\.([A-Za-z_][A-Za-z0-9_]*)', expr)
        if var_col_match:
            var_name = var_col_match.group(1)
            col_name = var_col_match.group(2)
            
            # Get the row matched to this variable
            var_indices = self._get_var_indices(var_name)
            if var_indices:
                if is_running:
                    # For RUNNING semantics, use the first occurrence
                    idx = var_indices[0]
                else:
                    # For FINAL semantics, use the last occurrence
                    idx = var_indices[-1]
                    
                if idx < len(self.context.rows):
                    return self.context.rows[idx].get(col_name)
        
        # Enhanced CLASSIFIER handling with caching
        classifier_pattern = r'CLASSIFIER\(\s*([A-Za-z][A-Za-z0-9_]*)?\s*\)'
        classifier_match = re.match(classifier_pattern, expr, re.IGNORECASE)
        if classifier_match:
            var_name = classifier_match.group(1)
            return self.evaluate_classifier(var_name, running=is_running)
                    
        # Special handling for MATCH_NUMBER
        if expr.upper().strip() == "MATCH_NUMBER()":
            return self.context.match_number

        # Handle navigation functions like FIRST, LAST, PREV, NEXT
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

        # src/matcher/measure_evaluator.py

    def evaluate_classifier(self, 
                        var_name: Optional[str] = None, 
                        *, 
                        running: bool = True) -> Optional[str]:
        """
        Evaluate CLASSIFIER function according to SQL standard.
        
        The CLASSIFIER function returns the name of the pattern variable that matched
        the current row. It can be used in two forms:
        
        1. CLASSIFIER() - Returns the pattern variable for the current row
        2. CLASSIFIER(var) - Returns var if the current row is matched to var, otherwise NULL
        
        Args:
            var_name: Optional variable name to check against
            running: Whether to use RUNNING semantics (default: True)
            
        Returns:
            String containing the pattern variable name or None if not matched
            
        Examples:
            >>> # With current row matched to variable 'A':
            >>> evaluator.evaluate_classifier()  
            'A'
            >>> evaluator.evaluate_classifier('A')  
            'A'
            >>> evaluator.evaluate_classifier('B')  
            None
            
            >>> # With subset U = (A, B):
            >>> evaluator.evaluate_classifier('U')
            'A'  # Returns the component variable that matched
            
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
                raise ClassifierError(
                    f"CLASSIFIER argument must be a string, got {type(var_name).__name__}"
                )
                
            if not var_name.isidentifier():
                raise ClassifierError(
                    f"Invalid CLASSIFIER argument: '{var_name}' is not a valid identifier"
                )
                
            # Only check if variable exists in pattern if we have variables
            if self.context.variables and var_name not in self.context.variables and (
                not hasattr(self.context, 'subsets') or 
                var_name not in self.context.subsets
            ):
                available_vars = list(self.context.variables.keys())
                subset_vars = []
                if hasattr(self.context, 'subsets'):
                    subset_vars = list(self.context.subsets.keys())
                    
                raise ClassifierError(
                    f"Variable '{var_name}' not found in pattern. "
                    f"Available variables: {available_vars}. "
                    f"Available subset variables: {subset_vars}."
                )

    def _evaluate_classifier_impl(self, 
                                var_name: Optional[str] = None,
                                running: bool = True) -> Optional[str]:
        """
        Internal implementation of CLASSIFIER evaluation with optimizations.
        
        Args:
            var_name: Optional variable name to check against
            running: Whether to use RUNNING semantics
            
        Returns:
            String containing the pattern variable name or None if not matched
        """
        current_idx = self.context.current_idx
        
        # Fast path using row-to-variable index
        if hasattr(self, '_row_to_vars') and current_idx in self._row_to_vars:
            matched_vars = self._row_to_vars[current_idx]
            
            # Handle CLASSIFIER() without arguments - use first matched variable
            if var_name is None:
                # First check primary variables for this row
                for var in self.context.variables:
                    if var in matched_vars:
                        return var
                        
                # Then check subset variable components
                if hasattr(self.context, 'subsets'):
                    for subset_name, components in self.context.subsets.items():
                        for comp in components:
                            if comp in matched_vars:
                                return comp
                
                return None
            
            # Handle CLASSIFIER(var) - direct lookup in matched vars
            elif var_name in matched_vars:
                return var_name
                
            # Handle subset variable
            elif hasattr(self.context, 'subsets') and var_name in self.context.subsets:
                for comp in self.context.subsets[var_name]:
                    if comp in matched_vars:
                        return comp
        
        # Fallback path (should rarely be needed with index)
        if var_name is None:
            # First check primary variables
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    return var
                    
            # Then check subset variables
            if hasattr(self.context, 'subsets') and self.context.subsets:
                for subset_name, components in self.context.subsets.items():
                    for comp in components:
                        if comp in self.context.variables and current_idx in self.context.variables[comp]:
                            return comp
        else:
            # Check specific variable
            if var_name in self.context.variables and current_idx in self.context.variables[var_name]:
                return var_name
                
            # Check subset variable
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

    

        
    # src/matcher/measure_evaluator.py

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
        Get indices of rows matched to a variable or subset with improved handling.
        
        Args:
            var: The variable name
            
        Returns:
            List of row indices that match the variable
        """
        # Direct variable
        if var in self.context.variables:
            return sorted(self.context.variables[var])
        
        # Check for subset variable with improved handling
        if hasattr(self.context, 'subsets') and var in self.context.subsets:
            indices = []
            for comp_var in self.context.subsets[var]:
                if comp_var in self.context.variables:
                    indices.extend(self.context.variables[comp_var])
            return sorted(set(indices))  # Ensure we don't have duplicates
        
        # Try to handle variable name with quantifier (var?)
        base_var = None
        if var.endswith('?'):
            base_var = var[:-1]
        elif var.endswith('*') or var.endswith('+'):
            base_var = var[:-1]
        elif '{' in var and var.endswith('}'):
            base_var = var[:var.find('{')]
            
        if base_var and base_var in self.context.variables:
            return sorted(self.context.variables[base_var])
        
        return []

        # src/matcher/measure_evaluator.py

    def _evaluate_aggregate(self, func_name: str, args_str: str, is_running: bool) -> Any:
        """
        Evaluate aggregate functions like SUM, COUNT, etc. with enhanced pattern variable support.
        
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
        
        # Handle pattern variable COUNT(A.*) special case
        pattern_count_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.\*', args_str)
        if func_name.lower() == 'count' and pattern_count_match:
            var_name = pattern_count_match.group(1)
            var_indices = self._get_var_indices(var_name)
            if is_running:
                var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
            return len(var_indices)
        
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
            indices = self._get_var_indices(var_scope)
            if is_running:
                # For RUNNING semantics, only consider rows up to current_idx
                indices = [idx for idx in indices if idx <= self.context.current_idx]
            rows_to_use = [self.context.rows[idx] for idx in sorted(indices) if idx < len(self.context.rows)]
        else:
            # Use all rows up to current position if running
            if is_running:
                # For RUNNING semantics with no variable scope, use only the current match
                # Get all matched rows in the current match
                matched_indices = []
                for var, indices in self.context.variables.items():
                    matched_indices.extend(indices)
                matched_indices = sorted(matched_indices)
                
                # Only include rows up to current_idx
                matched_indices = [idx for idx in matched_indices if idx <= self.context.current_idx]
                rows_to_use = [self.context.rows[idx] for idx in matched_indices if idx < len(self.context.rows)]
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
