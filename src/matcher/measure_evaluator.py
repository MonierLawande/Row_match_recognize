# src/matcher/measure_evaluator.py

from collections import defaultdict
from functools import lru_cache
from typing import Dict, Any, List, Optional, Set, Union, Tuple
import re
import math
import numpy as np
import time
from src.matcher.row_context import RowContext
from src.utils.logging_config import get_logger, PerformanceTimer
from src.matcher.production_aggregates import ProductionAggregateEvaluator, AggregateValidationError, AggregateArgumentError

# Module logger
logger = get_logger(__name__)

def _get_column_value_with_type_preservation(row: Dict[str, Any], column_name: str) -> Any:
    """
    Get column value from row with proper type preservation.
    
    This function ensures that:
    1. Original data types are preserved (int stays int, not converted to float)
    2. Missing values return None instead of NaN
    3. Trino compatibility is maintained
    
    Args:
        row: Dictionary representing a row
        column_name: Name of the column to retrieve
        
    Returns:
        The value with original type preserved, or None if missing
    """
    if row is None or column_name not in row:
        return None
    
    value = row[column_name]
    
    # Handle NaN values - convert to None for Trino compatibility
    if isinstance(value, float) and (math.isnan(value) or np.isnan(value)):
        return None
    
    # Preserve original types - don't auto-convert to float
    return value



class ClassifierError(Exception):
    """Error in CLASSIFIER function evaluation."""
    pass

def _is_table_prefix(var_name: str, var_assignments: Dict[str, List[int]], subsets: Dict[str, List[str]] = None) -> bool:
    """
    Check if a variable name looks like a table prefix rather than a pattern variable.
    
    Args:
        var_name: The variable name to check
        var_assignments: Dictionary of defined pattern variables
        subsets: Dictionary of defined subset variables
        
    Returns:
        True if this looks like a forbidden table prefix, False otherwise
    """
    # If it's a defined pattern variable or subset variable, it's not a table prefix
    if var_name in var_assignments:
        return False
    if subsets and var_name in subsets:
        return False
    
    # Common table name patterns that should be rejected
    table_patterns = [
        r'^[a-z]+_table$',      # ending with _table
        r'^tbl_[a-z]+$',        # starting with tbl_
        r'^[a-z]+_tbl$',        # ending with _tbl
        r'^[a-z]+_tab$',        # ending with _tab
        r'^[a-z]+s$',           # plural forms (likely table names)
        r'^[a-z]+_data$',       # ending with _data
        r'^data_[a-z]+$',       # starting with data_
    ]
    
    # Check against common table naming patterns
    for pattern in table_patterns:
        if re.match(pattern, var_name.lower()):
            return True
    
    # Check for overly long names (likely table names)
    if len(var_name) > 20:
        return True
    
    # If it contains underscores and is longer than typical pattern variable names
    if '_' in var_name and len(var_name) > 10:
        return True
    
    return False

# Updates for src/matcher/measure_evaluator.py

def evaluate_pattern_variable_reference(expr: str, var_assignments: Dict[str, List[int]], all_rows: List[Dict[str, Any]], cache: Dict[str, Any] = None, subsets: Dict[str, List[str]] = None, current_idx: int = None, is_running: bool = False, is_permute: bool = False) -> Tuple[bool, Any]:
    """
    Evaluate a pattern variable reference with proper subset handling, RUNNING semantics, and PERMUTE support.
    
    Args:
        expr: The expression to evaluate
        var_assignments: Dictionary mapping variables to row indices
        all_rows: List of all rows in the partition
        cache: Optional cache for variable reference results
        subsets: Optional dictionary of subset variable definitions
        current_idx: Current row index for RUNNING semantics
        is_running: Whether we're in RUNNING mode
        is_permute: Whether this is a PERMUTE pattern
        
    Returns:
        Tuple of (handled, value) where handled is True if this was a pattern variable reference
    """
    # Clean the expression - remove any whitespace
    expr = expr.strip()
    
    logger.debug(f"Evaluating pattern variable reference: {expr}, current_idx={current_idx}, is_running={is_running}, is_permute={is_permute}")
    
    # Use cache if provided (but cache key should include current_idx, is_running, and is_permute for proper caching)
    cache_key = f"{expr}_{current_idx}_{is_running}_{is_permute}" if is_running or is_permute else expr
    if cache is not None and cache_key in cache:
        logger.debug(f"Cache hit for {cache_key}")
        return True, cache[cache_key]
    
    # Handle direct pattern variable references like A.salary or X.value
    var_col_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$', expr)
    if var_col_match:
        var_name = var_col_match.group(1)
        col_name = var_col_match.group(2)
        
        # Table prefix validation: prevent forbidden table.column references
        # Check if this looks like a table prefix (common table naming patterns)
        if _is_table_prefix(var_name, var_assignments, subsets):
            raise ValueError(f"Forbidden table prefix reference: '{expr}'. "
                           f"In MATCH_RECOGNIZE, use pattern variable references like 'A.{col_name}' "
                           f"instead of table references like '{var_name}.{col_name}'")
        
        logger.debug(f"Pattern variable reference matched: var={var_name}, col={col_name}")
        
        # For PERMUTE patterns in ONE ROW PER MATCH mode, always use FINAL semantics
        # This ensures we get the actual value for each variable regardless of order
        if is_permute and not is_running:
            logger.debug(f"Using PERMUTE-specific logic for {var_name}")
            var_indices = var_assignments.get(var_name, [])
            if var_indices:
                # Use the last matched position for this variable
                idx = max(var_indices)
                if idx < len(all_rows):
                    value = all_rows[idx].get(col_name)
                    logger.debug(f"PERMUTE match found value {value} at index {idx}")
                    if cache is not None:
                        cache[cache_key] = value
                    return True, value
        
        # Check if this is a subset variable
        if subsets and var_name in subsets:
            components = subsets[var_name]
            
            # Find the latest position among all component variables
            # Map components to their positions in the match
            component_positions = {}
            for component in components:
                if component in var_assignments and var_assignments[component]:
                    # For RUNNING semantics, only consider positions at or before current_idx
                    valid_positions = var_assignments[component]
                    if is_running and current_idx is not None:
                        valid_positions = [pos for pos in valid_positions if pos <= current_idx]
                    
                    if valid_positions:
                        component_positions[component] = max(valid_positions)
            
            # If we have any components, get the one with the latest position
            if component_positions:
                latest_component = max(component_positions.items(), key=lambda x: x[1])[0]
                var_indices = var_assignments[latest_component]
                
                # For RUNNING semantics, ensure the variable position is at or before current_idx
                if is_running and current_idx is not None:
                    valid_indices = [idx for idx in var_indices if idx <= current_idx]
                    if not valid_indices:
                        if cache is not None:
                            cache[cache_key] = None
                        return True, None
                    var_indices = valid_indices
                
                if var_indices and var_indices[0] < len(all_rows):
                    value = all_rows[var_indices[0]].get(col_name)
                    if cache is not None:
                        cache[cache_key] = value
                    return True, value
            
            if cache is not None:
                cache[cache_key] = None
            return True, None
        
        # Direct variable lookup
        var_indices = var_assignments.get(var_name, [])
        
        # For RUNNING semantics, only return value if the variable's position is at or before current_idx
        if is_running and current_idx is not None:
            valid_indices = [idx for idx in var_indices if idx <= current_idx]
            if not valid_indices:
                if cache is not None:
                    cache[cache_key] = None
                return True, None
            var_indices = valid_indices
        
        if var_indices and var_indices[0] < len(all_rows):
            value = all_rows[var_indices[0]].get(col_name)
            if cache is not None:
                cache[cache_key] = value
            return True, value
        
        if cache is not None:
            cache[cache_key] = None
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
        
        # Initialize production aggregate evaluator for enhanced SQL:2016 support
        self._prod_agg_evaluator = None
        self._initialize_production_aggregates()

    def _initialize_production_aggregates(self):
        """Initialize the production aggregate evaluator."""
        try:
            from src.matcher.production_aggregates import ProductionAggregateEvaluator
            self._prod_agg_evaluator = ProductionAggregateEvaluator(self.context)
            logger.debug("Production aggregate evaluator initialized successfully")
        except ImportError:
            logger.warning("Production aggregate evaluator not available, using basic implementation")
        except Exception as e:
            logger.error(f"Failed to initialize production aggregate evaluator: {e}")

    def get_aggregate_statistics(self) -> Dict[str, Any]:
        """Get statistics from the production aggregate evaluator."""
        if self._prod_agg_evaluator:
            return self._prod_agg_evaluator.get_statistics()
        return {"error": "Production aggregate evaluator not available"}

    def _preserve_data_type(self, original_value: Any, new_value: Any) -> Any:
        """
        Preserve the data type of the original value when setting a new value.
        
        This is crucial for Trino compatibility as it expects specific data types
        and doesn't handle automatic type conversions well.
        
        Args:
            original_value: The original value whose type should be preserved
            new_value: The new value to type-cast
            
        Returns:
            The new value cast to the type of the original value, or None if conversion fails
        """
        if new_value is None:
            return None
        
        if original_value is None:
            return new_value
        
        # Handle NaN values
        if isinstance(new_value, float) and (math.isnan(new_value) or np.isnan(new_value)):
            return None
        
        # Preserve integer types
        if isinstance(original_value, int) and isinstance(new_value, (int, float)):
            if isinstance(new_value, float) and new_value.is_integer():
                return int(new_value)
            elif isinstance(new_value, int):
                return new_value
        
        # Preserve float types
        if isinstance(original_value, float) and isinstance(new_value, (int, float)):
            return float(new_value)
        
        # Preserve string types
        if isinstance(original_value, str):
            return str(new_value)
        
        # For other types, return as-is
        return new_value

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


    def evaluate(self, expr: str, semantics: str = None) -> Any:
        """
        Evaluate a measure expression with proper RUNNING/FINAL semantics and production aggregate support.
        
        This implementation handles all standard SQL:2016 pattern matching measures
        including CLASSIFIER(), MATCH_NUMBER(), and aggregate functions with proper
        handling of exclusions and PERMUTE patterns.
        
        Args:
            expr: The expression to evaluate
            semantics: Optional semantics override ('RUNNING' or 'FINAL')
            
        Returns:
            The result of the expression evaluation
        """
        # Use passed semantics or instance default
        is_running = (semantics == 'RUNNING') if semantics else not self.final
        
        logger.debug(f"Evaluating expression: {expr} with {('FINAL' if not is_running else 'RUNNING')} semantics")
        logger.debug(f"Context variables: {self.context.variables}")
        logger.debug(f"Number of rows: {len(self.context.rows)}")
        logger.debug(f"Current index: {self.context.current_idx}")
        
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
        
        # Enhanced aggregate function detection and evaluation
        if self._prod_agg_evaluator:
            # Check if this is an aggregate function using production evaluator
            from src.matcher.production_aggregates import ProductionAggregateEvaluator
            agg_pattern = r'\b(' + '|'.join(ProductionAggregateEvaluator.STANDARD_AGGREGATES) + r')\s*\('
            if re.search(agg_pattern, expr, re.IGNORECASE):
                try:
                    semantics_str = "RUNNING" if is_running else "FINAL"
                    result = self._prod_agg_evaluator.evaluate_aggregate(expr, semantics_str)
                    logger.debug(f"Production aggregate evaluation result: {result}")
                    return result
                except Exception as e:
                    logger.warning(f"Production aggregate evaluation failed: {e}, falling back to basic implementation")
                    # Continue with basic implementation below
        
        # Special handling for CLASSIFIER
        classifier_pattern = r'CLASSIFIER\(\s*([A-ZaZ][A-Za-z0-9_]*)?\s*\)'
        classifier_match = re.match(classifier_pattern, expr, re.IGNORECASE)
        if classifier_match:
            var_name = classifier_match.group(1)
            return self.evaluate_classifier(var_name, running=is_running)
        
        # Special handling for MATCH_NUMBER
        if expr.upper().strip() == "MATCH_NUMBER()":
            return self.context.match_number
        
        # Special handling for SUM with both pattern variable references and universal column references
        if expr.upper().startswith("SUM("):
            # Extract the column expression from SUM(column_expr)
            sum_match = re.match(r'SUM\(([^)]+)\)', expr, re.IGNORECASE)
            if sum_match:
                col_expr = sum_match.group(1).strip()
                
                # Parse pattern variable reference (e.g., B.totalprice)
                var_col_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$', col_expr)
                if var_col_match:
                    var_name = var_col_match.group(1)
                    col_name = var_col_match.group(2)
                    
                    # Get indices for the specific variable
                    if var_name not in self.context.variables:
                        return 0
                        
                    var_indices = self.context.variables[var_name]
                    
                    # For RUNNING semantics, only include indices up to current position
                    if is_running:
                        var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
                    
                    # Calculate sum
                    total = 0
                    for idx in var_indices:
                        if idx < len(self.context.rows):
                            row_val = self.context.rows[idx].get(col_name)
                            if row_val is not None:
                                try:
                                    total += float(row_val)
                                except (ValueError, TypeError):
                                    pass
                    
                    return total
                else:
                    # Handle universal column reference (e.g., SUM(salary))
                    # For universal references, sum across all matched rows in the current pattern
                    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', col_expr):
                        # Get all matched row indices
                        all_indices = []
                        for var, indices in self.context.variables.items():
                            all_indices.extend(indices)
                        
                        # For RUNNING semantics, only include rows up to current position
                        if is_running:
                            all_indices = [idx for idx in all_indices if idx <= self.context.current_idx]
                        
                        # Calculate sum across all matched rows
                        total = 0
                        for idx in set(all_indices):  # Use set to avoid duplicates
                            if idx < len(self.context.rows):
                                row_val = self.context.rows[idx].get(col_expr)
                                if row_val is not None:
                                    try:
                                        total += float(row_val)
                                    except (ValueError, TypeError):
                                        pass
                        
                        return total
        
        # Handle other aggregate functions (MIN, MAX, AVG, COUNT, etc.)
        agg_match = re.match(r'(MIN|MAX|AVG|COUNT)\(([^)]+)\)', expr, re.IGNORECASE)
        if agg_match:
            func_name = agg_match.group(1).upper()
            col_expr = agg_match.group(2).strip()
            
            # Handle COUNT(*) special case
            if func_name == "COUNT" and col_expr == "*":
                # Get all matched indices
                matched_indices = []
                for var, indices in self.context.variables.items():
                    matched_indices.extend(indices)
                
                # For RUNNING semantics, only include rows up to current position
                if is_running:
                    matched_indices = [idx for idx in matched_indices if idx <= self.context.current_idx]
                
                return len(set(matched_indices))
            
            # Handle COUNT(var.*) special case (variable wildcard)
            count_var_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\.\*$', col_expr)
            if func_name == "COUNT" and count_var_match:
                var_name = count_var_match.group(1)
                
                # Get indices for the specific variable
                if var_name not in self.context.variables:
                    return 0
                    
                var_indices = self.context.variables[var_name]
                
                # For RUNNING semantics, only include indices up to current position
                if is_running:
                    var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
                
                return len(var_indices)
            
            # Parse pattern variable reference (e.g., B.totalprice)
            var_col_match = re.match(r'^([A-Za-z_][A-ZaZ0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$', col_expr)
            if not var_col_match:
                return None
                
            var_name = var_col_match.group(1)
            col_name = var_col_match.group(2)
            
            # Get indices for the specific variable
            if var_name not in self.context.variables:
                return None
                
            var_indices = self.context.variables[var_name]
            
            # For RUNNING semantics, only include indices up to current position
            if is_running:
                var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
            
            # Collect values for aggregation
            values = []
            for idx in var_indices:
                if idx < len(self.context.rows):
                    row_val = self.context.rows[idx].get(col_name)
                    if row_val is not None:
                        try:
                            # Convert to numeric if possible
                            if isinstance(row_val, (str, bool)):
                                row_val = float(row_val)
                            values.append(row_val)
                        except (ValueError, TypeError):
                            # Skip non-numeric values for numeric aggregates
                            if func_name in ("MIN", "MAX", "AVG"):
                                continue
                            values.append(row_val)
            
            # Calculate aggregate
            if not values:
                return None
            
            if func_name == "MIN":
                return min(values)
            elif func_name == "MAX":
                return max(values)
            elif func_name == "AVG":
                numeric_values = [v for v in values if isinstance(v, (int, float))]
                if not numeric_values:
                    return None
                return sum(numeric_values) / len(numeric_values)
            elif func_name == "COUNT":
                return len(values)
        
        # Determine if this is a PERMUTE pattern
        is_permute = False
        if hasattr(self.context, 'pattern_metadata'):
            is_permute = self.context.pattern_metadata.get('permute', False)
        elif hasattr(self.context, 'pattern_variables') and len(self.context.pattern_variables) > 0:
            is_permute = True
        
        # Try optimized pattern variable reference evaluation with PERMUTE support
        handled, value = evaluate_pattern_variable_reference(
            expr, 
            self.context.variables, 
            self.context.rows,
            self._var_ref_cache,
            getattr(self.context, 'subsets', None),
            self.context.current_idx,
            is_running,
            is_permute  # Pass the PERMUTE flag
        )
        if handled:
            return value
        
        # Enhanced navigation function detection
        # Check for both simple and nested navigation functions
        simple_nav_pattern = r'^(FIRST|LAST|PREV|NEXT)\s*\('
        nested_nav_pattern = r'^(FIRST|LAST|PREV|NEXT)\s*\(\s*(FIRST|LAST|PREV|NEXT)'
        
        is_simple_nav = re.match(simple_nav_pattern, expr, re.IGNORECASE) is not None
        is_nested_nav = re.match(nested_nav_pattern, expr, re.IGNORECASE) is not None
        
        if is_simple_nav or is_nested_nav:
            return self._evaluate_navigation(expr, is_running)
        
        # Try AST-based evaluation for complex expressions (arithmetic, etc.)
        try:
            from src.matcher.condition_evaluator import ConditionEvaluator
            import ast
            
            # Set up context for AST evaluation
            self.context.current_row = self.context.rows[self.context.current_idx] if self.context.current_idx < len(self.context.rows) else None
            
            # Create a specialized condition evaluator for measure expressions
            # Use MEASURES mode for correct PREV/NEXT semantics in measure expressions
            evaluator = ConditionEvaluator(self.context, evaluation_mode='MEASURES')
            
            # Parse and evaluate the expression using AST
            try:
                tree = ast.parse(expr, mode='eval')
                result = evaluator.visit(tree.body)
                return result
            except (SyntaxError, ValueError) as ast_error:
                # If AST parsing fails, try as a universal pattern variable (non-prefixed column reference)
                try:
                    # Universal pattern variable: refers to all rows in current match
                    result = self._evaluate_universal_pattern_variable(expr)
                    if result is not None:
                        return result
                    
                    # Fallback to simple column reference for compatibility
                    return self.context.rows[self.context.current_idx].get(expr)
                except Exception:
                    logger.error(f"Error evaluating expression '{expr}' with AST: {ast_error}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error evaluating expression '{expr}': {e}")
            return None

    def _evaluate_universal_pattern_variable(self, column_name: str) -> Any:
        """
        Evaluate a universal pattern variable (non-prefixed column reference).
        
        According to SQL:2016, a universal pattern variable refers to all rows in the 
        current match and returns the value from the current row being processed.
        
        Args:
            column_name: The column name without any pattern variable prefix
            
        Returns:
            The value of the column from the current row, or None if not found
        """
        try:
            # Validate that this is a simple column name (no dots, no special characters)
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', column_name):
                return None
            
            # Check if this column name conflicts with any defined pattern variables
            if hasattr(self.context, 'pattern_variables') and column_name in self.context.pattern_variables:
                logger.warning(f"Column name '{column_name}' conflicts with pattern variable name")
                return None
            
            # For universal pattern variables, we get the value from the current row
            if self.context.current_idx >= 0 and self.context.current_idx < len(self.context.rows):
                current_row = self.context.rows[self.context.current_idx]
                if column_name in current_row:
                    value = current_row[column_name]
                    logger.debug(f"Universal pattern variable '{column_name}' resolved to: {value}")
                    return value
            
            return None
            
        except Exception as e:
            logger.error(f"Error evaluating universal pattern variable '{column_name}': {e}")
            return None



    def evaluate_classifier(self, var_name: Optional[str] = None, *, running: bool = True) -> Optional[str]:
        """
        Evaluate CLASSIFIER function according to SQL:2016 standard.
        
        The CLASSIFIER function returns the name of the pattern variable that matched
        the current row. It can be used in two forms:
        
        1. CLASSIFIER() - Returns the pattern variable for the current row
        2. CLASSIFIER(var) - Returns var if it exists in the pattern (in ONE ROW PER MATCH mode)
                            or if the current row is matched to var (in ALL ROWS PER MATCH mode)
        
        This implementation handles all cases including:
        - Rows matched to regular pattern variables
        - Rows matched to subset variables
        - Rows after exclusion sections
        - Proper handling of ONE ROW PER MATCH vs ALL ROWS PER MATCH semantics
        
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
            
            # Standard classifier evaluation for ALL ROWS PER MATCH or CLASSIFIER() without arguments
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
        
        This method determines which pattern variable matched the current row,
        handling all cases including:
        - Direct variable matches
        - Subset variables
        - Rows after exclusion sections
        - Proper handling of pattern variable priorities
        
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
            # Use optimized row-to-variable index for deterministic behavior
            if hasattr(self.context, '_row_var_index') and current_idx in self.context._row_var_index:
                vars_for_row = self.context._row_var_index[current_idx]
                if vars_for_row:
                    # If multiple variables match this row, use timeline for correct order
                    if len(vars_for_row) == 1:
                        return next(iter(vars_for_row))
                    else:
                        # Use timeline to determine correct variable in pattern order
                        timeline = self.context.get_timeline()
                        timeline_vars = [var for idx, var in timeline if idx == current_idx]
                        if timeline_vars:
                            return timeline_vars[0]
                        # Fallback to alphabetical ordering
                        return min(vars_for_row)
            
            # Fallback: Check which variable this row was assigned to
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    return var
        
        # Case 1: CLASSIFIER() without arguments - find the matching variable for current row
        if var_name is None:
            # Use optimized row-to-variable index if available (more deterministic)
            if hasattr(self.context, '_row_var_index') and current_idx in self.context._row_var_index:
                vars_for_row = self.context._row_var_index[current_idx]
                if vars_for_row:
                    # If multiple variables match this row, use the timeline to determine the correct one
                    if len(vars_for_row) == 1:
                        return next(iter(vars_for_row))
                    else:
                        # Multiple variables for this row - check timeline for order
                        timeline = self.context.get_timeline()
                        # Find all entries for this row in the timeline
                        timeline_vars = [var for idx, var in timeline if idx == current_idx]
                        # Return the first one in timeline order (pattern matching order)
                        if timeline_vars:
                            return timeline_vars[0]
                        # Fallback to alphabetical for deterministic behavior
                        return min(vars_for_row)
            
            # Fallback to direct variable assignments (preserving original logic)
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    return var
                    
            # Then check subset variables
            if hasattr(self.context, 'subsets') and self.context.subsets:
                for subset_name, components in self.context.subsets.items():
                    for comp in components:
                        if comp in self.context.variables and current_idx in self.context.variables[comp]:
                            return comp
            
            # Special handling for rows after exclusion sections
            # This is a general solution that works for any pattern with exclusions
            if hasattr(self.context, 'excluded_rows') and self.context.excluded_rows:
                excluded_rows = sorted(self.context.excluded_rows)
                
                # Check if this row is after an exclusion section
                if excluded_rows and current_idx > excluded_rows[-1]:
                    # Find the variable that should match this row based on the pattern structure
                    # We need to look at the pattern structure to determine which variable
                    # should match rows after an exclusion section
                    
                    # First, check if this row is explicitly assigned to any variable
                    for var, indices in self.context.variables.items():
                        if current_idx in indices:
                            return var
                    
                    # If not explicitly assigned, we need to infer the variable
                    # based on the pattern structure and the surrounding matches
                    
                    # Find the last variable before the exclusion
                    last_var_before = None
                    last_idx_before = -1
                    for var, indices in self.context.variables.items():
                        for idx in indices:
                            if idx < excluded_rows[0] and idx > last_idx_before:
                                last_idx_before = idx
                                last_var_before = var
                    
                    # Find the first variable after the exclusion
                    first_var_after = None
                    first_idx_after = float('inf')
                    for var, indices in self.context.variables.items():
                        for idx in indices:
                            if idx > excluded_rows[-1] and idx < first_idx_after:
                                first_idx_after = idx
                                first_var_after = var
                    
                    # If this row is the first after the exclusion and we have a variable for it,
                    # return that variable
                    if current_idx == first_idx_after and first_var_after:
                        return first_var_after
                    
                    # Otherwise, try to infer based on pattern structure
                    # This requires knowledge of the pattern structure, which we don't have here
                    # So we'll use a heuristic: return the variable that appears after the exclusion
                    if first_var_after:
                        return first_var_after
            
            # No match found
            return None
        
        # Case 2: CLASSIFIER(var) - check if the current row is matched to the specified variable
        else:
            # Direct variable check
            if var_name in self.context.variables and current_idx in self.context.variables[var_name]:
                return var_name
                
            # Subset variable check
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
        Handle navigation functions like FIRST, LAST, PREV, NEXT with SQL:2016 compliant semantics.
        
        This enhanced implementation supports:
        1. Simple navigation functions (FIRST(A.price), LAST(B.quantity))
        2. Nested navigation functions (PREV(FIRST(A.price)), NEXT(LAST(B.quantity)))
        3. Navigation with offsets (FIRST(A.price, 3), PREV(price, 2))
        4. Universal column references (FIRST(price) vs. FIRST(A.price))
        5. RUNNING vs FINAL semantics
        6. Robust null handling and type preservation
        
        Args:
            expr: The navigation expression (e.g., "LAST(A.value)")
            is_running: Whether to use RUNNING semantics
            
        Returns:
            The result of the navigation function
        """
        # Cache key for memoization - include running semantics in the key
        cache_key = (expr, is_running, self.context.current_idx)
        if hasattr(self, '_var_ref_cache') and cache_key in self._var_ref_cache:
            return self._var_ref_cache[cache_key]
        
        # Check for nested navigation pattern first
        # Updated pattern to recognize CLASSIFIER() as a valid inner function
        nested_pattern = r'(FIRST|LAST|NEXT|PREV)\s*\(\s*((?:FIRST|LAST|NEXT|PREV|CLASSIFIER)[^)]*\))\s*(?:,\s*(\d+))?\s*\)'
        nested_match = re.match(nested_pattern, expr, re.IGNORECASE)
        
        if nested_match:
            # For nested navigation, delegate to specialized function
            # This will also respect RUNNING semantics by using current_idx
            from src.matcher.condition_evaluator import evaluate_nested_navigation
            
            current_idx = self.context.current_idx
            
            # For RUNNING semantics, limit to current row
            if is_running:
                # When using RUNNING semantics, we only consider rows up to the current position
                # This affects nested navigation functions
                return evaluate_nested_navigation(expr, self.context, current_idx, None)
            else:
                # With FINAL semantics, we consider all rows in the match
                return evaluate_nested_navigation(expr, self.context, current_idx, None)
        
        # Extract function name and arguments for simple navigation
        match = re.match(r'(FIRST|LAST|PREV|NEXT)\s*\(\s*(.+?)\s*\)', expr, re.IGNORECASE)
        if not match:
            return None
            
        func_name = match.group(1).upper()
        args_str = match.group(2)
        
        # Parse arguments
        args = [arg.strip() for arg in args_str.split(',')]
        if not args:
            return None
        
        result = None
        
        # Check if we have variable.field reference (like A.value) or simple field reference (like value)
        var_field_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', args[0])
        
        if var_field_match:
            # Handle variable.field references (like A.value)
            var_name = var_field_match.group(1)
            field_name = var_field_match.group(2)
            
            # For PREV/NEXT, we navigate relative to current position
            if func_name in ('PREV', 'NEXT'):
                # Get steps (default is 1)
                steps = 1
                if len(args) > 1:
                    try:
                        steps = int(args[1])
                        if steps < 0:
                            # SQL:2016 requires non-negative offset values
                            logger.warning(f"Negative offset {steps} in {func_name} function - using 0 instead")
                            steps = 0
                    except ValueError:
                        logger.warning(f"Invalid offset in {func_name} function - using default of 1")
                        steps = 1
                
                # Get variable indices with comprehensive handling of subset variables
                var_indices = self._get_full_var_indices(var_name)
                
                # Sort indices to ensure correct order
                var_indices = sorted(var_indices)
                
                # For RUNNING semantics, only consider rows up to current position
                if is_running:
                    var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
                
                if func_name == 'PREV':
                    # Find index in var_indices that is closest to but less than current_idx
                    current_var_idx = None
                    for i, idx in enumerate(var_indices):
                        if idx <= self.context.current_idx:
                            current_var_idx = i
                    
                    if current_var_idx is not None and current_var_idx >= steps:
                        prev_idx = var_indices[current_var_idx - steps]
                        if prev_idx >= 0 and prev_idx < len(self.context.rows):
                            raw_value = self.context.rows[prev_idx].get(field_name)
                            # Preserve data type for Trino compatibility
                            if raw_value is not None and self.context.current_idx < len(self.context.rows):
                                current_value = self.context.rows[self.context.current_idx].get(field_name)
                                result = self._preserve_data_type(current_value, raw_value)
                            else:
                                result = raw_value
                
                elif func_name == 'NEXT':
                    # Find index in var_indices that is closest to or equal to current_idx
                    current_var_idx = None
                    for i, idx in enumerate(var_indices):
                        if idx >= self.context.current_idx:
                            current_var_idx = i
                            break
                    
                    # If not found directly, use the index of the current row
                    if current_var_idx is None:
                        for i, idx in enumerate(var_indices):
                            if idx == self.context.current_idx:
                                current_var_idx = i
                                break
                    
                    # Fall back to using the first index if still not found
                    if current_var_idx is None and len(var_indices) > 0:
                        current_var_idx = 0
                    
                    if current_var_idx is not None and current_var_idx + steps < len(var_indices):
                        next_idx = var_indices[current_var_idx + steps]
                        if next_idx >= 0 and next_idx < len(self.context.rows):
                            raw_value = self.context.rows[next_idx].get(field_name)
                            # Preserve data type for Trino compatibility
                            if raw_value is not None and self.context.current_idx < len(self.context.rows):
                                current_value = self.context.rows[self.context.current_idx].get(field_name)
                                result = self._preserve_data_type(current_value, raw_value)
                            else:
                                result = raw_value
            
            # For FIRST/LAST with variable prefix, we use variable-specific logic
            elif func_name in ('FIRST', 'LAST'):
                # Get occurrence (default is 0 for SQL:2016 compliance)
                # Per SQL:2016 spec:
                # - FIRST(A.value) = first occurrence (occurrence=0)
                # - FIRST(A.value, 2) = third occurrence (occurrence=2, 0-based indexing, navigating forward)
                # - LAST(A.value) = last occurrence (occurrence=0)
                # - LAST(A.value, 2) = third from last (occurrence=2, 0-based from end, navigating backward)
                occurrence = 0
                if len(args) > 1:
                    try:
                        occurrence = int(args[1])
                        if occurrence < 0:
                            logger.warning(f"Negative offset {occurrence} in {func_name} function - using 0 instead")
                            occurrence = 0  # Ensure non-negative per SQL:2016 requirements
                    except ValueError:
                        logger.warning(f"Invalid offset in {func_name} function - using default of 0")
                        occurrence = 0
                
                # Get variable indices with comprehensive subset handling
                var_indices = self._get_full_var_indices(var_name)
                
                # Handle partition boundaries if defined
                if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
                    partition = self._get_current_partition()
                    if partition:
                        part_start, part_end = partition
                        var_indices = [idx for idx in var_indices if part_start <= idx <= part_end]
                
                # Sort indices to ensure correct order
                var_indices = sorted(var_indices)
                
                # For RUNNING semantics, only consider rows up to current position
                if is_running:
                    var_indices = [idx for idx in var_indices if idx <= self.context.current_idx]
                
                # Get logical index based on occurrence parameter
                logical_idx = None
                if var_indices:
                    if func_name == 'FIRST':
                        # Logical navigation forward from first occurrence:
                        # If occurrence is within bounds, get the corresponding index
                        # Otherwise, return null (logical_idx remains None)
                        if occurrence < len(var_indices):
                            logical_idx = var_indices[occurrence]  # 0-based indexing
                    elif func_name == 'LAST':
                        # Logical navigation backward from last occurrence:
                        # If occurrence is within bounds, get the corresponding index from the end
                        # Otherwise, return null (logical_idx remains None)
                        if occurrence < len(var_indices):
                            logical_idx = var_indices[-(occurrence + 1)]  # Search backwards from last
                    
                    # Get the value if we found a valid logical position
                    if logical_idx is not None and logical_idx < len(self.context.rows):
                        # Enhanced value retrieval with better null handling and type preservation
                        try:
                            raw_value = self.context.rows[logical_idx].get(field_name)
                            
                            # Handle nulls and type preservation properly per SQL:2016 standard
                            if raw_value is not None:
                                # Get current row's value for type context if available
                                if self.context.current_idx < len(self.context.rows):
                                    current_value = self.context.rows[self.context.current_idx].get(field_name)
                                    # Use the _preserve_data_type method to ensure consistent types
                                    result = self._preserve_data_type(current_value, raw_value)
                                else:
                                    # No current row for context, use raw value with basic type preservation
                                    result = raw_value
                            else:
                                # Explicitly handle null values (return None, not NaN)
                                result = None
                        except (KeyError, IndexError, TypeError) as e:
                            # Enhanced error handling for production reliability
                            logger.debug(f"Error retrieving {field_name} from row {logical_idx}: {str(e)}")
                            result = None
                    else:
                        # Per SQL:2016 spec, return null if no matching row is found
                        result = None
        
        else:
            # Handle simple field references (no variable prefix) for all functions
            field_name = args[0]
            
            # For PREV/NEXT, we navigate relative to current position
            if func_name in ('PREV', 'NEXT'):
                # Get steps (default is 1)
                steps = 1
                if len(args) > 1:
                    try:
                        steps = int(args[1])
                        if steps < 0:
                            logger.warning(f"Negative offset {steps} in {func_name} function - using 0 instead")
                            steps = 0
                    except ValueError:
                        logger.warning(f"Invalid offset in {func_name} function - using default of 1")
                        steps = 1
                
                # Collect all matched indices in the order they appear
                all_matched_indices = []
                for var, indices in self.context.variables.items():
                    all_matched_indices.extend(indices)
                all_matched_indices = sorted(set(all_matched_indices))
                
                # For RUNNING semantics, only consider rows up to current position
                if is_running:
                    all_matched_indices = [idx for idx in all_matched_indices if idx <= self.context.current_idx]
                
                if func_name == 'PREV':
                    # Find index in all_matched_indices that is closest to but less than current_idx
                    current_pos = None
                    for i, idx in enumerate(all_matched_indices):
                        if idx <= self.context.current_idx:
                            current_pos = i
                    
                    if current_pos is not None and current_pos >= steps:
                        prev_idx = all_matched_indices[current_pos - steps]
                        if prev_idx >= 0 and prev_idx < len(self.context.rows):
                            result = _get_column_value_with_type_preservation(self.context.rows[prev_idx], field_name)
                        else:
                            result = None
                    else:
                        result = None
                
                elif func_name == 'NEXT':
                    # Find index in all_matched_indices that is closest to or equal to current_idx
                    current_pos = None
                    for i, idx in enumerate(all_matched_indices):
                        if idx >= self.context.current_idx:
                            current_pos = i
                            break
                    
                    # If not found directly, use the index of the current row
                    if current_pos is None and len(all_matched_indices) > 0:
                        for i, idx in enumerate(all_matched_indices):
                            if i == self.context.current_idx:
                                current_pos = i
                                break
                    
                    # Fall back to using the first index if still not found
                    if current_pos is None and len(all_matched_indices) > 0:
                        current_pos = 0
                    
                    if current_pos is not None and current_pos + steps < len(all_matched_indices):
                        next_idx = all_matched_indices[current_pos + steps]
                        if next_idx >= 0 and next_idx < len(self.context.rows):
                            result = _get_column_value_with_type_preservation(self.context.rows[next_idx], field_name)
                        else:
                            result = None
                    else:
                        result = None
            
            # Handle FIRST/LAST with simple field references (no variable prefix)
            elif func_name in ('FIRST', 'LAST'):
                # Get offset/occurrence according to SQL:2016 standard requirements:
                # FIRST(value) = 1st value (default offset 0 - first occurrence)
                # FIRST(value, N) = value at N additional occurrences from first  
                # LAST(value) = last value (default offset 0 - last occurrence)
                # LAST(value, N) = value at N additional occurrences from last
                offset = 0  # Default to 0 (first/last item itself) per SQL:2016
                if len(args) > 1:
                    try:
                        offset = int(args[1])
                        if offset < 0:
                            logger.warning(f"Negative offset {offset} in {func_name} function - using 0 instead")
                            offset = 0  # Ensure non-negative offset per SQL:2016 requirements
                    except ValueError:
                        logger.warning(f"Invalid offset in {func_name} function - using default of 0")
                        offset = 0
                
                # Collect all row indices from all matched variables with comprehensive handling
                all_indices = []
                
                # Include rows from all variables
                for var_name, indices in self.context.variables.items():
                    all_indices.extend(indices)
                
                # Also check subset variables if available
                if hasattr(self.context, 'subsets') and self.context.subsets:
                    for subset_name, subset_vars in self.context.subsets.items():
                        # Skip subset variables that are already direct variables
                        if subset_name in self.context.variables:
                            continue
                        # For each component variable in the subset
                        for var in subset_vars:
                            if var in self.context.variables:
                                all_indices.extend(self.context.variables[var])
                
                # Handle partition boundaries if defined
                if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
                    partition = self._get_current_partition()
                    if partition:
                        part_start, part_end = partition
                        all_indices = [idx for idx in all_indices if part_start <= idx <= part_end]
                
                # Sort indices to ensure correct order and remove duplicates
                all_indices = sorted(set(all_indices))
                
                # Apply RUNNING/FINAL semantics according to SQL:2016 standard:
                logical_idx = None
                
                if func_name == 'FIRST':
                    # FIRST(value, N) behavior with SQL:2016 semantics:
                    # RUNNING: Consider only rows up to current position, then get value at offset N (0-based)
                    # FINAL: Consider all rows in match, then get value at offset N (0-based)
                    if is_running:
                        # For RUNNING semantics: filter to current position first
                        running_indices = [idx for idx in all_indices if idx <= self.context.current_idx]
                        if running_indices and offset < len(running_indices):
                            logical_idx = running_indices[offset]  # 0-based indexing for additional occurrences
                    else:
                        # For FINAL semantics: use all indices
                        if all_indices and offset < len(all_indices):
                            logical_idx = all_indices[offset]  # 0-based indexing for additional occurrences
                            
                elif func_name == 'LAST':
                    # LAST(value, N) behavior with SQL:2016 semantics:
                    # RUNNING: Filter to rows up to current position, then get value at offset N from end
                    # FINAL: Consider all rows in match, get value at offset N from end
                    if is_running:
                        # For RUNNING semantics: get value at offset N from end among rows up to current position
                        running_indices = [idx for idx in all_indices if idx <= self.context.current_idx]
                        if running_indices and offset < len(running_indices):
                            logical_idx = running_indices[-(offset + 1)]  # Search backwards from last
                    else:
                        # For FINAL semantics: get value at offset N from end of all rows in match
                        if all_indices and offset < len(all_indices):
                            logical_idx = all_indices[-(offset + 1)]  # Search backwards from last
                
                # Get the value if we found a valid logical position
                if logical_idx is not None and logical_idx < len(self.context.rows):
                    try:
                        # Enhanced value retrieval with robust error handling
                        raw_value = self.context.rows[logical_idx].get(field_name)
                        
                        # Handle nulls and type preservation properly per SQL:2016 standard
                        if raw_value is not None:
                            # Get current row's value for type context if available
                            if self.context.current_idx < len(self.context.rows):
                                current_value = self.context.rows[self.context.current_idx].get(field_name)
                                # Use type preservation to ensure consistent return types
                                result = self._preserve_data_type(current_value, raw_value)
                            else:
                                # No current row for context, use raw value with basic type handling
                                result = raw_value
                        else:
                            # Explicitly handle null values (return None, not NaN)
                            result = None
                    except (KeyError, IndexError, TypeError) as e:
                        # Enhanced error handling for production reliability
                        logger.debug(f"Error retrieving {field_name} from row {logical_idx}: {str(e)}")
                        result = None
                else:
                    # Per SQL:2016 spec, return null if no matching row is found
                    result = None
        
        # Cache the result
        if hasattr(self, '_var_ref_cache'):
            self._var_ref_cache[cache_key] = result
        return result


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

    def _get_full_var_indices(self, var_name: str) -> List[int]:
        """
        Get comprehensive list of indices for a variable with all edge case handling.
        
        This method provides enhanced variable resolution by handling:
        1. Direct variables (A)
        2. Subset variables (S where S := (A, B))
        3. Variables with quantifiers (A+, A*)
        4. Variables referenced via aliases
        5. Empty set handling with appropriate null return value semantics
        
        Args:
            var_name: The variable name to resolve
            
        Returns:
            Sorted list of all matched row indices for the variable
        """
        indices = []
        
        # Direct variable case - most common
        if var_name in self.context.variables:
            indices.extend(self.context.variables[var_name])
        
        # Subset variables
        if hasattr(self.context, 'subsets') and self.context.subsets:
            # If var_name is a subset variable, collect all indices from component variables
            if var_name in self.context.subsets:
                for subset_var in self.context.subsets[var_name]:
                    if subset_var in self.context.variables:
                        indices.extend(self.context.variables[subset_var])
            
            # Also check if var_name is part of any subset (for aliases)
            for subset, components in self.context.subsets.items():
                if var_name in components and subset in self.context.variables:
                    indices.extend(self.context.variables[subset])
        
        # Handle variables with quantifiers - remove quantifier and try again
        if not indices:
            base_var = None
            # Try common quantifiers
            if var_name.endswith(('*', '+', '?')):
                base_var = var_name[:-1]
            # Try range quantifiers like {n,m}
            elif '{' in var_name and var_name.endswith('}'):
                base_var = var_name[:var_name.find('{')]
                
            if base_var and base_var in self.context.variables:
                indices.extend(self.context.variables[base_var])
        
        # Remove duplicates and sort for consistent ordering
        return sorted(set(indices))
    
    def _get_current_partition(self) -> Optional[Tuple[int, int]]:
        """
        Get the current partition boundaries based on context.
        
        This method properly handles partitioning in SQL:2016 compliant way:
        1. Identifies the correct partition containing the current row
        2. Ensures navigation functions respect partition boundaries
        3. Returns appropriate boundaries for pattern navigation
        
        Returns:
            Tuple of (start_idx, end_idx) for the current partition, or None if not partitioned
        """
        if not hasattr(self.context, 'partition_boundaries') or not self.context.partition_boundaries:
            return None
            
        # Find the partition containing the current row
        current_idx = self.context.current_idx
        
        # Check if we have a specific method to get partition by row
        if hasattr(self.context, 'get_partition_for_row'):
            try:
                return self.context.get_partition_for_row(current_idx)
            except Exception:
                # Fall back to manual search if method fails
                pass
                
        # Manual search for partition containing current row
        for start_idx, end_idx in self.context.partition_boundaries:
            if start_idx <= current_idx <= end_idx:
                return (start_idx, end_idx)
                
        # If not found in any partition, return the first partition or None
        if self.context.partition_boundaries:
            return self.context.partition_boundaries[0]
        return None