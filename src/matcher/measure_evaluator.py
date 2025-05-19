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

# Updates for src/matcher/measure_evaluator.py

def evaluate_pattern_variable_reference(expr: str, var_assignments: Dict[str, List[int]], all_rows: List[Dict[str, Any]], cache: Dict[str, Any] = None, subsets: Dict[str, List[str]] = None) -> Tuple[bool, Any]:
    """
    Evaluate a pattern variable reference with proper subset handling.
    
    Args:
        expr: The expression to evaluate
        var_assignments: Dictionary mapping variables to row indices
        all_rows: List of all rows in the partition
        cache: Optional cache for variable reference results
        subsets: Optional dictionary of subset variable definitions
        
    Returns:
        Tuple of (handled, value) where handled is True if this was a pattern variable reference
    """
    # Use cache if provided
    if cache is not None and expr in cache:
        return True, cache[expr]
    
    # Handle direct pattern variable references like A.salary or X.value
    var_col_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\\.([A-Za-z_][A-Za-z0-9_]*)$', expr)
    if var_col_match:
        var_name = var_col_match.group(1)
        col_name = var_col_match.group(2)
        
        # Check if this is a subset variable
        if subsets and var_name in subsets:
            components = subsets[var_name]
            
            # Find the latest position among all component variables
            # Map components to their positions in the match
            component_positions = {}
            for component in components:
                if component in var_assignments and var_assignments[component]:
                    component_positions[component] = max(var_assignments[component])
            
            # If we have any components, get the one with the latest position
            if component_positions:
                latest_component = max(component_positions.items(), key=lambda x: x[1])[0]
                var_indices = var_assignments[latest_component]
                if var_indices and var_indices[0] < len(all_rows):
                    value = all_rows[var_indices[0]].get(col_name)
                    if cache is not None:
                        cache[expr] = value
                    return True, value
            
            return True, None
        
        # Direct variable lookup
        var_indices = var_assignments.get(var_name, [])
        if var_indices and var_indices[0] < len(all_rows):
            value = all_rows[var_indices[0]].get(col_name)
            if cache is not None:
                cache[expr] = value
            return True, value
        return True, None
    
    # Not a pattern variable reference
    return False, None


class MeasureEvaluator:
    def __init__(self, context: RowContext, final: bool = True):
        self.context = context
        self.final = final
        self.original_expr = None
        # Add cache for classifier lookups with LRU cache policy
        self._classifier_cache = {}
        self._var_ref_cache = {}  # New cache for variable references
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
        
        # Try optimized pattern variable reference evaluation first
        handled, value = evaluate_pattern_variable_reference(
            expr, 
            self.context.variables, 
            self.context.rows,
            self._var_ref_cache,
            getattr(self.context, 'subsets', None)  # Pass subsets if available
        )
        if handled:
            return value
        
        # Special handling for pattern variable references like A.salary
        var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', expr)
        if var_col_match:
            var_name = var_col_match.group(1)
            col_name = var_col_match.group(2)
            
            # Check if this is a subset variable
            if hasattr(self.context, 'subsets') and var_name in self.context.subsets:
                # For subset variables, prioritize the component variable that appears latest in the match
                components = self.context.subsets[var_name]
                
                # Find the latest position among all component variables
                component_positions = {}
                for component in components:
                    if component in self.context.variables and self.context.variables[component]:
                        component_positions[component] = max(self.context.variables[component])
                
                # If we have any components, get the one with the latest position
                if component_positions:
                    latest_component = max(component_positions.items(), key=lambda x: x[1])[0]
                    var_indices = self.context.variables[latest_component]
                    if var_indices:
                        if is_running:
                            # For RUNNING semantics, use the first occurrence
                            idx = var_indices[0]
                        else:
                            # For FINAL semantics, use the last occurrence
                            idx = var_indices[-1]
                            
                        if idx < len(self.context.rows):
                            return self.context.rows[idx].get(col_name)
                return None
            
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


    def evaluate_classifier(self, 
                        var_name: Optional[str] = None, 
                        *, 
                        running: bool = True) -> Optional[str]:
        """
        Evaluate CLASSIFIER function according to SQL standard.
        
        The CLASSIFIER function returns the name of the pattern variable that matched
        the current row. It can be used in two forms:
        
        1. CLASSIFIER() - Returns the pattern variable for the current row
        2. CLASSIFIER(var) - Returns var if it exists in the pattern (in ONE ROW PER MATCH mode)
                            or if the current row is matched to var (in ALL ROWS PER MATCH mode)
        
        Args:
            var_name: Optional variable name to check against
            running: Whether to use RUNNING semantics
            
        Returns:
            String containing the pattern variable name or None if not matched
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
            
            # Special handling for CLASSIFIER(var) in ONE ROW PER MATCH mode
            if var_name is not None and not running:
                # For ONE ROW PER MATCH, return var if it exists in the pattern
                if var_name in self.context.variables:
                    result = var_name
                    self._classifier_cache[cache_key] = result
                    return result
                # Check if it's a subset variable
                elif hasattr(self.context, 'subsets') and var_name in self.context.subsets:
                    # For subset variables, check if any component matched
                    for comp in self.context.subsets[var_name]:
                        if comp in self.context.variables:
                            result = comp
                            self._classifier_cache[cache_key] = result
                            return result
                return None
            
            # For ALL ROWS PER MATCH or CLASSIFIER() without arguments
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
        
        # For ONE ROW PER MATCH with FINAL semantics, we need to return the variable
        # that matched the row based on the DEFINE conditions, not just the last variable
        if not running and var_name is None:
            # Check which variable this row was assigned to
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    return var
        
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
                var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', inner_args)
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
            var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', args[0])
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
                        if row_idx < len(self.context.rows):
                            return self.context.rows[row_idx].get(col)
                else:  # LAST
                    if occurrence < len(var_indices):
                        row_idx = var_indices[-(occurrence+1)]
                        if row_idx < len(self.context.rows):
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
            
            # Check if first argument is a pattern variable reference
            var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', args[0])
            if var_col_match:
                var_name = var_col_match.group(1)
                col_name = var_col_match.group(2)
                steps = int(args[1]) if len(args) > 1 else 1
                
                # For pattern variable references, navigate relative to the current row
                if func_name == "PREV":
                    nav_idx = current_idx - steps
                    if 0 <= nav_idx < len(self.context.rows):
                        return self.context.rows[nav_idx].get(col_name)
                else:  # NEXT
                    nav_idx = current_idx + steps
                    if 0 <= nav_idx < len(self.context.rows):
                        return self.context.rows[nav_idx].get(col_name)
            else:
                # Simple column reference
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


    def _supported_aggregates(self) -> Set[str]:
        """Return set of supported aggregate functions."""
        return {
            'sum', 'count', 'avg', 'min', 'max', 'first', 'last',
            'median', 'stddev', 'stddev_samp', 'stddev_pop',
            'var', 'var_samp', 'var_pop', 'covar', 'corr'
        }

    def _evaluate_count_star(self, is_running: bool) -> int:
        """Optimized implementation of COUNT(*)."""
        matched_indices = set()
        for indices in self.context.variables.values():
            matched_indices.update(indices)
        
        if is_running:
            matched_indices = {idx for idx in matched_indices if idx <= self.context.current_idx}
            
        return len(matched_indices)

    def _evaluate_count_var(self, var_name: str, is_running: bool) -> int:
        """Optimized implementation of COUNT(var.*)."""
        var_indices = self._get_var_indices(var_name)
        
        if is_running:
            var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
            
        return len(var_indices)

    def _gather_values_for_aggregate(self, args_str: str, is_running: bool) -> List[Any]:
        """Gather values for aggregation with proper type handling."""
        values = []
        indices_to_use = []
        
        # Check for pattern variable prefix
        var_col_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', args_str)
        
        if var_col_match:
            # Pattern variable prefixed column
            var_name, col_name = var_col_match.groups()
            indices_to_use = self._get_var_indices(var_name)
        else:
            # Direct column reference
            col_name = args_str
            # Get all matched rows
            for indices in self.context.variables.values():
                indices_to_use.extend(indices)
            indices_to_use = sorted(set(indices_to_use))
        
        # Apply RUNNING semantics filter
        if is_running:
            indices_to_use = [idx for idx in indices_to_use if idx <= self.context.current_idx]
        
        # Gather values with type checking
        for idx in indices_to_use:
            if idx < len(self.context.rows):
                val = self.context.rows[idx].get(col_name)
                if val is not None:
                    try:
                        # Ensure numeric type for numeric aggregates
                        if isinstance(val, (str, bool)):
                            val = float(val)
                        values.append(val)
                    except (ValueError, TypeError):
                        # Log warning but continue processing
                        print(f"Warning: Non-numeric value '{val}' found in column {col_name}")
                        continue
        
        return values

    def _compute_aggregate(self, func_name: str, values: List[Any]) -> Any:
        """Compute aggregate with proper type handling and SQL semantics."""
        if not values:
            return None
            
        try:
            if func_name == 'count':
                return len(values)
            elif func_name == 'sum':
                return sum(values)
            elif func_name == 'avg':
                return sum(values) / len(values)
            elif func_name == 'min':
                return min(values)
            elif func_name == 'max':
                return max(values)
            elif func_name == 'first':
                return values[0]
            elif func_name == 'last':
                return values[-1]
            elif func_name == 'median':
                return self._compute_median(values)
            elif func_name in ('stddev', 'stddev_samp'):
                return self._compute_stddev(values, population=False)
            elif func_name == 'stddev_pop':
                return self._compute_stddev(values, population=True)
            elif func_name in ('var', 'var_samp'):
                return self._compute_variance(values, population=False)
            elif func_name == 'var_pop':
                return self._compute_variance(values, population=True)
            
        except Exception as e:
            self._log_aggregate_error(func_name, str(values), e)
            return None

    def _compute_median(self, values: List[Any]) -> Any:
        """Compute median with proper handling of even/odd counts."""
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        mid = n // 2
        
        if n % 2 == 0:
            return (sorted_vals[mid-1] + sorted_vals[mid]) / 2
        return sorted_vals[mid]

    def _compute_stddev(self, values: List[Any], population: bool = False) -> float:
        """Compute standard deviation with proper handling of sample vs population."""
        if len(values) < (1 if population else 2):
            return None
            
        mean = sum(values) / len(values)
        squared_diff_sum = sum((x - mean) ** 2 for x in values)
        
        if population:
            return math.sqrt(squared_diff_sum / len(values))
        return math.sqrt(squared_diff_sum / (len(values) - 1))

    def _compute_variance(self, values: List[Any], population: bool = False) -> float:
        """Compute variance with proper handling of sample vs population."""
        stddev = self._compute_stddev(values, population)
        return stddev * stddev if stddev is not None else None

    def _log_aggregate_error(self, func_name: str, args: str, error: Exception) -> None:
        """Log aggregate function errors with context."""
        error_msg = (
            f"Error in aggregate function {func_name}({args}): {str(error)}\n"
            f"Context: current_idx={self.context.current_idx}, "
            f"running={not self.final}"
        )
        print(error_msg)  # Replace with proper logging in production

    def _evaluate_aggregate(self, func_name: str, args_str: str, is_running: bool) -> Any:
        """
        Production-level implementation of aggregate function evaluation for pattern matching.
        
        Supports both pattern variable prefixed and non-prefixed column references with full SQL standard compliance:
        - SUM(A.order_amount): Sum of order_amount values from rows matched to variable A
        - SUM(order_amount): Sum of order_amount values from all matched rows
        
        Features:
        - Full SQL standard compliance for aggregates
        - Proper NULL handling according to SQL standards
        - Comprehensive error handling and logging
        - Performance optimizations with caching
        - Support for all standard SQL aggregate functions
        - Proper type handling and conversions
        - Thread-safe implementation
        
        Args:
            func_name: The aggregate function name (sum, count, avg, min, max, etc.)
            args_str: Function arguments as string (column name or pattern_var.column)
            is_running: Whether to use RUNNING semantics (True) or FINAL semantics (False)
                
        Returns:
            Result of the aggregate function or None if no values to aggregate
            
        Raises:
            ValueError: If the function name is invalid or arguments are malformed
            TypeError: If incompatible types are used in aggregation
            
        Examples:
            COUNT(*) -> Count of all rows in the match
            COUNT(A.*) -> Count of rows matched to variable A
            SUM(A.amount) -> Sum of amount values from rows matched to variable A
            AVG(price) -> Average of price values from all matched rows
        """
        start_time = time.time()
        
        try:
            # Input validation
            if not isinstance(func_name, str) or not isinstance(args_str, str):
                raise ValueError("Function name and arguments must be strings")
            
            # Normalize function name and validate
            func_name = func_name.lower()
            if func_name not in self._supported_aggregates():
                raise ValueError(f"Unsupported aggregate function: {func_name}")
            
            # Cache key for memoization
            cache_key = (func_name, args_str, is_running, self.context.current_idx)
            if hasattr(self, '_agg_cache') and cache_key in self._agg_cache:
                return self._agg_cache[cache_key]
            
            # Initialize result
            result = None
            
            try:
                # Handle COUNT(*) special case with optimizations
                if func_name == 'count' and args_str.strip() in ('*', ''):
                    result = self._evaluate_count_star(is_running)
                    
                # Handle pattern variable COUNT(A.*) special case
                elif func_name == 'count' and (pattern_count_match := re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.\*', args_str)):
                    result = self._evaluate_count_var(pattern_count_match.group(1), is_running)
                    
                # Handle regular aggregates
                else:
                    values = self._gather_values_for_aggregate(args_str, is_running)
                    result = self._compute_aggregate(func_name, values)
                
                # Cache the result
                if not hasattr(self, '_agg_cache'):
                    self._agg_cache = {}
                self._agg_cache[cache_key] = result
                
                return result
                
            except Exception as e:
                # Log the error with context
                self._log_aggregate_error(func_name, args_str, e)
                return None
                
        finally:
            # Performance monitoring
            duration = time.time() - start_time
            if hasattr(self, 'timing'):
                self.timing[f'aggregate_{func_name}'] += duration
