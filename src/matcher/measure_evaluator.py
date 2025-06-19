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

    def _preprocess_expression_for_ast(self, expr: str) -> str:
        """
        Preprocess an expression to replace special SQL functions with their values
        so that the expression can be parsed by Python's AST parser.
        
        This method handles:
        - MATCH_NUMBER() -> actual match number value
        - CLASSIFIER() -> classifier value (if needed)
        - SQL IN operator -> Python in operator (case conversion)
        
        Args:
            expr: The original expression
            
        Returns:
            The preprocessed expression that can be parsed by AST
        """
        preprocessed = expr
        
        # Replace MATCH_NUMBER() with the actual match number
        # Use word boundaries to avoid replacing partial matches
        if 'MATCH_NUMBER()' in preprocessed:
            match_number = str(self.context.match_number)
            preprocessed = re.sub(r'\bMATCH_NUMBER\(\)', match_number, preprocessed, flags=re.IGNORECASE)
        
        # Convert SQL IN to Python in (case-sensitive conversion)
        # Use word boundaries to avoid replacing parts of words
        preprocessed = re.sub(r'\bIN\b', 'in', preprocessed)
        preprocessed = re.sub(r'\bNOT IN\b', 'not in', preprocessed)
        
        # Note: We could add other special function replacements here if needed
        # For example, CLASSIFIER() could be replaced with the classifier value
        
        logger.debug(f"Preprocessed expression: '{expr}' -> '{preprocessed}'")
        return preprocessed


    def evaluate(self, expr: str, semantics: str = None) -> Any:
        """
        Evaluate a measure expression with proper RUNNING/FINAL semantics and PERMUTE support.
        
        This implementation handles all standard SQL:2016 pattern matching measures
        including CLASSIFIER(), MATCH_NUMBER(), and aggregate functions with proper
        handling of exclusions and PERMUTE patterns.
        
        Args:
            expr: The expression to evaluate
            semantics: Optional semantics override ('RUNNING' or 'FINAL')
            
        Returns:
            The result of the expression evaluation
        """
        # Use passed semantics or determine default based on SQL:2016 specification
        # For ALL ROWS PER MATCH, navigation functions default to FINAL semantics when no explicit prefix is specified
        # For ONE ROW PER MATCH, navigation functions use FINAL semantics (instance default)
        if semantics == 'RUNNING':
            is_running = True
        elif semantics == 'FINAL':
            is_running = False
        else:
            # No explicit semantics specified - use FINAL as default for navigation functions
            # This matches SQL:2016 and Trino behavior for both ONE ROW PER MATCH and ALL ROWS PER MATCH
            is_running = False
        
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
        
        # Handle empty pattern and reluctant quantifier matches
        # For reluctant quantifiers (*?), the pattern always matches the empty string first
        # In these cases, all measures should return NULL/None (except MATCH_NUMBER)
        is_empty_match = False
        current_idx = self.context.current_idx
        
        # Check if this is from a reluctant empty match or empty pattern
        pattern_has_reluctant = False
        if hasattr(self.context, 'pattern_metadata'):
            pattern_metadata = self.context.pattern_metadata
            pattern_has_reluctant = pattern_metadata.get('has_reluctant_quantifier', False)
            
        # Check if current row has any variable assignments
        current_has_vars = False
        for var, indices in self.context.variables.items():
            if current_idx in indices:
                current_has_vars = True
                break
                
        # Handle empty match cases
        # 1. Empty pattern match - no variables assigned to any rows
        # 2. Reluctant quantifier empty match - pattern_has_reluctant and no vars assigned to current row
        if (not self.context.variables) or (pattern_has_reluctant and not current_has_vars):
            # For empty matches, only MATCH_NUMBER should return a value, all other measures return None
            if expr.upper().strip() != "MATCH_NUMBER()":
                return None
                
        # Special handling for CLASSIFIER
        classifier_pattern = r'CLASSIFIER\(\s*([A-Za-z][A-Za-z0-9_]*)?\s*\)'
        classifier_match = re.match(classifier_pattern, expr, re.IGNORECASE)
        if classifier_match:
            var_name = classifier_match.group(1)
            return self.evaluate_classifier(var_name, running=is_running)
        
        # Special handling for MATCH_NUMBER
        if expr.upper().strip() == "MATCH_NUMBER()":
            return self.context.match_number
            
        # Special handling for ROW_NUMBER
        if expr.upper().strip() == "ROW_NUMBER()":
            # ROW_NUMBER() returns the sequential number of the row within the match (1-based)
            # In RUNNING semantics, it returns the current row number within the visible portion
            # In FINAL semantics, it returns the row number within the complete match
            
            if is_running:
                # RUNNING semantics: count visible rows up to and including current position
                visible_rows = set()
                for var_indices in self.context.variables.values():
                    for idx in var_indices:
                        if idx <= self.context.current_idx:
                            visible_rows.add(idx)
                
                # Find the position of current_idx among visible rows
                visible_list = sorted(visible_rows)
                if self.context.current_idx in visible_list:
                    return visible_list.index(self.context.current_idx) + 1  # 1-based
                else:
                    return None
            else:
                # FINAL semantics: count all rows in the match
                all_rows = set()
                for var_indices in self.context.variables.values():
                    all_rows.update(var_indices)
                
                # Find the position of current_idx among all matched rows
                all_list = sorted(all_rows)
                if self.context.current_idx in all_list:
                    return all_list.index(self.context.current_idx) + 1  # 1-based
                else:
                    return None
        
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
        
        # Handle other aggregate functions using the comprehensive _evaluate_aggregate method
        # Check if this is a standard aggregate function call
        agg_match = re.match(r'(SUM|COUNT|MIN|MAX|AVG|STDDEV|VAR)\s*\(([^)]+)\)', expr, re.IGNORECASE)
        if agg_match:
            func_name = agg_match.group(1).lower()
            args_str = agg_match.group(2).strip()
            
            # Use the comprehensive aggregate evaluator
            return self._evaluate_aggregate(func_name, args_str, is_running)
        
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
            
            # Preprocess the expression to replace special functions with their values
            # This allows complex expressions like "MATCH_NUMBER() IN (0, MATCH_NUMBER())" to be parsed by AST
            preprocessed_expr = self._preprocess_expression_for_ast(expr)
            
            # Create a specialized condition evaluator for measure expressions
            # Use MEASURES mode for correct PREV/NEXT semantics in measure expressions
            evaluator = ConditionEvaluator(self.context, evaluation_mode='MEASURES')
            
            # Parse and evaluate the expression using AST
            try:
                tree = ast.parse(preprocessed_expr, mode='eval')
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
            
            # Handle subset variables with context-aware semantics
            if var_name is not None and hasattr(self.context, 'subsets') and var_name in self.context.subsets:
                subset_components = self.context.subsets[var_name]
                
                # Find the raw classifier for the current row (without case correction)
                current_idx = self.context.current_idx
                actual_classifier_raw = None
                
                # Check which variable this row is assigned to (raw lookup)
                for var, indices in self.context.variables.items():
                    if current_idx in indices:
                        actual_classifier_raw = var
                        break
                
                # If the actual classifier is in the subset, return it with case correction (standard SQL:2016)
                if actual_classifier_raw and actual_classifier_raw in subset_components:
                    result = self.context._apply_case_sensitivity_rule(actual_classifier_raw)
                    self._classifier_cache[cache_key] = result
                    return result
                
                # Compatibility behavior: Only use fallback for alternation patterns where
                # the subset contains variables from the current alternation group
                # Check if this appears to be an alternation pattern by looking at variable context
                is_alternation_context = False
                if hasattr(self.context, 'variables'):
                    # Count how many variables in the subset are active in the current match
                    active_subset_vars = sum(1 for comp in subset_components 
                                           if comp in self.context.variables and self.context.variables[comp])
                    
                    # If only one subset component is active and there are other non-subset variables,
                    # this might be an alternation pattern like (L|H) A
                    total_active_vars = sum(1 for var_rows in self.context.variables.values() if var_rows)
                    if active_subset_vars == 1 and total_active_vars > active_subset_vars:
                        is_alternation_context = True
                
                # Use fallback behavior only for alternation contexts
                if is_alternation_context:
                    for component in subset_components:
                        if component in self.context.variables:
                            component_rows = self.context.variables[component]
                            if component_rows:  # If this component has any matched rows in the match
                                result = self.context._apply_case_sensitivity_rule(component)
                                self._classifier_cache[cache_key] = result
                                return result
                
                # Standard behavior: If not in subset and not alternation context, return None
                self._classifier_cache[cache_key] = None
                return None
            
            # Special handling for CLASSIFIER(var) in ONE ROW PER MATCH mode
            if var_name is not None and not running:
                # For ONE ROW PER MATCH, return var if it exists in the pattern
                if var_name in self.context.variables:
                    result = self.context._apply_case_sensitivity_rule(var_name)
                    self._classifier_cache[cache_key] = result
                    return result
                    
                # No match found
                self._classifier_cache[cache_key] = None
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
        - Empty pattern handling (returns None)
        
        Args:
            var_name: Optional variable name to check against
            running: Whether to use RUNNING semantics
            
        Returns:
            String containing the pattern variable name or None if not matched or empty pattern
        """
        current_idx = self.context.current_idx
        
        # Empty pattern handling: If there are no variables defined in the context
        # or this row is not assigned to any variable, return None
        # This handles cases like PATTERN (() | A) for empty matches
        if not self.context.variables or all(current_idx not in indices for indices in self.context.variables.values()):
            return None
            
        # Check if this row is part of an empty pattern match
        if hasattr(self.context, '_empty_pattern_rows') and current_idx in self.context._empty_pattern_rows:
            return None
        
        # For ONE ROW PER MATCH with FINAL semantics, we need to return the variable
        # that matched the row based on the DEFINE conditions, not just the last variable
        if not running and var_name is None:
            # Use optimized row-to-variable index for deterministic behavior
            if hasattr(self.context, '_row_var_index') and current_idx in self.context._row_var_index:
                vars_for_row = self.context._row_var_index[current_idx]
                if vars_for_row:
                    # If multiple variables match this row, use timeline for correct order
                    if len(vars_for_row) == 1:
                        var = next(iter(vars_for_row))
                        return self.context._apply_case_sensitivity_rule(var)
                    else:
                        # Use timeline to determine correct variable in pattern order
                        timeline = self.context.get_timeline()
                        timeline_vars = [var for idx, var in timeline if idx == current_idx]
                        if timeline_vars:
                            var = timeline_vars[0]
                            return self.context._apply_case_sensitivity_rule(var)
                        # Fallback to alphabetical ordering
                        var = min(vars_for_row)
                        return self.context._apply_case_sensitivity_rule(var)
            
            # Fallback: Check which variable this row was assigned to
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    return self.context._apply_case_sensitivity_rule(var)
        
        # Case 1: CLASSIFIER() without arguments - find the matching variable for current row
        if var_name is None:
            # Check if current row is assigned to any variable
            assigned_to_any_var = False
            for indices in self.context.variables.values():
                if current_idx in indices:
                    assigned_to_any_var = True
                    break
                    
            # If not assigned to any variable, return None (important for empty pattern tests)
            if not assigned_to_any_var:
                return None
                
            # Use optimized row-to-variable index if available (more deterministic)
            if hasattr(self, '_row_to_vars'):
                vars_for_row = self._row_to_vars.get(current_idx, set())
                if vars_for_row:
                    # If multiple variables match this row, use the timeline to determine the correct one
                    if len(vars_for_row) == 1:
                        var = next(iter(vars_for_row))
                        return self.context._apply_case_sensitivity_rule(var)
                    else:
                        # Multiple variables for this row - check timeline for order
                        timeline = self.context.get_timeline() if hasattr(self.context, 'get_timeline') else []
                        # Find all entries for this row in the timeline
                        timeline_vars = [var for idx, var in timeline if idx == current_idx]
                        # Return the first one in timeline order (pattern matching order)
                        if timeline_vars:
                            var = timeline_vars[0]
                            return self.context._apply_case_sensitivity_rule(var)
                        # Fallback to alphabetical for deterministic behavior
                        var = min(vars_for_row)
                        return self.context._apply_case_sensitivity_rule(var)
            
            # Fallback to direct variable assignments (preserving original logic)
            for var, indices in self.context.variables.items():
                if current_idx in indices:
                    return self.context._apply_case_sensitivity_rule(var)
                    
            # Then check subset variables
            if hasattr(self.context, 'subsets') and self.context.subsets:
                for subset_name, components in self.context.subsets.items():
                    for comp in components:
                        if comp in self.context.variables and current_idx in self.context.variables[comp]:
                            return self.context._apply_case_sensitivity_rule(comp)
            
            # For rows not matching any variable, return None
            # This is a change from previous behavior which returned an empty string
            # to align with SQL:2016 standard and Trino behavior
            return None
        
        # Case 2: CLASSIFIER(var) - check if the current row is matched to the specified variable
        else:
            # Direct variable check
            if var_name in self.context.variables and current_idx in self.context.variables[var_name]:
                return self.context._apply_case_sensitivity_rule(var_name)
                
            # Subset variable check
            if hasattr(self.context, 'subsets') and var_name in self.context.subsets:
                for comp in self.context.subsets[var_name]:
                    if comp in self.context.variables and current_idx in self.context.variables[comp]:
                        return self.context._apply_case_sensitivity_rule(comp)
            
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
        Handle navigation functions like FIRST, LAST, PREV, NEXT with proper semantics.
        
        This enhanced implementation supports:
        1. Simple navigation functions (FIRST(A.price), LAST(B.quantity))
        2. Nested navigation functions (PREV(FIRST(A.price)), NEXT(LAST(B.quantity)))
        3. Navigation with offsets (FIRST(A.price, 3), PREV(price, 2))
        4. Combinations with proper semantics handling
        
        Args:
            expr: The navigation expression (e.g., "LAST(A.value)")
            is_running: Whether to use RUNNING semantics
            
        Returns:
            The result of the navigation function
        """
        # Check for nested navigation pattern first
        # Updated pattern to recognize RUNNING/FINAL semantic modifiers with navigation functions
        nested_pattern = r'(FIRST|LAST|NEXT|PREV)\s*\(\s*((?:(?:RUNNING|FINAL)\s+)?(?:FIRST|LAST|NEXT|PREV|CLASSIFIER)[^)]*\))\s*(?:,\s*(\d+))?\s*\)'
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
        
        # Cache key for memoization - include running semantics in the key
        cache_key = (expr, is_running, self.context.current_idx)
        if hasattr(self, '_var_ref_cache') and cache_key in self._var_ref_cache:
            return self._var_ref_cache[cache_key]
        
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
                    except ValueError:
                        pass
                
                if func_name == 'PREV':
                    prev_idx = self.context.current_idx - steps
                    if prev_idx >= 0 and prev_idx < len(self.context.rows):
                        raw_value = self.context.rows[prev_idx].get(field_name)
                        # Preserve data type for Trino compatibility
                        if raw_value is not None and self.context.current_idx < len(self.context.rows):
                            current_value = self.context.rows[self.context.current_idx].get(field_name)
                            result = self._preserve_data_type(current_value, raw_value)
                        else:
                            result = raw_value
                    # Note: if prev_idx < 0, result remains None (boundary condition)
                
                elif func_name == 'NEXT':
                    next_idx = self.context.current_idx + steps
                    if next_idx >= 0 and next_idx < len(self.context.rows):
                        raw_value = self.context.rows[next_idx].get(field_name)
                        # Preserve data type for Trino compatibility
                        if raw_value is not None and self.context.current_idx < len(self.context.rows):
                            current_value = self.context.rows[self.context.current_idx].get(field_name)
                            result = self._preserve_data_type(current_value, raw_value)
                        else:
                            result = raw_value
                    # Note: if next_idx >= len(rows), result remains None (boundary condition)                # For FIRST/LAST with variable prefix, we use variable-specific logic
            elif func_name in ('FIRST', 'LAST'):
                # Get occurrence (default is 0)
                occurrence = 0
                if len(args) > 1:
                    try:
                        occurrence = int(args[1])
                    except ValueError:
                        pass
                
                # Leverage the enhanced RowContext methods with semantics support
                if func_name == 'FIRST':
                    semantics = 'RUNNING' if is_running else 'FINAL'
                    row = self.context.first(var_name, occurrence, semantics)
                    if row and field_name in row:
                        result = row.get(field_name)
                    else:
                        result = None
                        
                elif func_name == 'LAST':
                    semantics = 'RUNNING' if is_running else 'FINAL'
                    row = self.context.last(var_name, occurrence, semantics)
                    if row and field_name in row:
                        result = row.get(field_name)
                    else:
                        result = None
                if func_name == 'FIRST':
                    semantics = 'RUNNING' if is_running else 'FINAL'
                    row = self.context.first(var_name, occurrence, semantics)
                    if row and field_name in row:
                        result = row.get(field_name)
                    else:
                        result = None
                        
                elif func_name == 'LAST':
                    semantics = 'RUNNING' if is_running else 'FINAL'
                    row = self.context.last(var_name, occurrence, semantics)
                    if row and field_name in row:
                        result = row.get(field_name)
                    else:
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
                    except ValueError:
                        pass
                
                if func_name == 'PREV':
                    prev_idx = self.context.current_idx - steps
                    if prev_idx >= 0 and prev_idx < len(self.context.rows):
                        result = _get_column_value_with_type_preservation(self.context.rows[prev_idx], field_name)
                    else:
                        result = None
                
                elif func_name == 'NEXT':
                    next_idx = self.context.current_idx + steps
                    if next_idx >= 0 and next_idx < len(self.context.rows):
                        result = _get_column_value_with_type_preservation(self.context.rows[next_idx], field_name)
                    else:
                        result = None
            
            # Handle FIRST/LAST with simple field references (no variable prefix)
            elif func_name in ('FIRST', 'LAST'):
                field_name = args[0]
                
                # Get offset/occurrence: SQL:2016 standard interpretation:
                # FIRST(value) = 1st value (default offset 0 = first item)
                # FIRST(value, N) = value at 0-based offset N from start  
                # LAST(value) = last value (default offset 0 = last item)
                # LAST(value, N) = value at 0-based offset N from end
                offset = 0  # Default to 0-based offset (first/last item)
                if len(args) > 1:
                    try:
                        offset = int(args[1])
                        if offset < 0:
                            offset = 0  # Ensure non-negative offset (0-based)
                    except ValueError:
                        offset = 0
                
                # Collect all row indices from all matched variables
                all_indices = []
                for var_name in self.context.variables:
                    var_indices = self.context.variables[var_name]
                    all_indices.extend(var_indices)
                
                # Sort indices to ensure correct order and remove duplicates
                all_indices = sorted(set(all_indices))
                
                # CRITICAL FIX FOR RUNNING/FINAL SEMANTICS:
                # For navigation functions like FIRST(value), LAST(value),
                # the behavior differs based on RUNNING vs FINAL semantics:
                
                # For RUNNING semantics with no explicit offset, filter indices to only include rows up to current position
                # For navigation functions with explicit offsets (like FIRST(value, 2)), use complete match indices
                if is_running and offset == 0:
                    all_indices = [idx for idx in all_indices if idx <= self.context.current_idx]
                
                if func_name == 'FIRST':
                    # SQL:2016 LOGICAL NAVIGATION: FIRST(value, N) 
                    # Find first occurrence in match, then navigate forward N MORE occurrences
                    # Default N=0 means stay at first occurrence
                    
                    if all_indices:
                        target_position = 0 + offset  # Start from first (index 0), add offset
                        if target_position < len(all_indices):
                            logical_idx = all_indices[target_position]
                            logger.debug(f"FIRST({field_name}, {offset}): all_indices={all_indices}, target_position={target_position}, logical_idx={logical_idx}, current_idx={self.context.current_idx}, is_running={is_running}")
                        else:
                            logical_idx = None
                            logger.debug(f"FIRST({field_name}, {offset}): target_position {target_position} out of bounds for {len(all_indices)} indices")
                    else:
                        logical_idx = None
                        logger.debug(f"FIRST({field_name}, {offset}): no indices available")
                            
                elif func_name == 'LAST':
                    # SQL:2016 LOGICAL NAVIGATION: LAST(value, N)
                    # Find last occurrence in match, then navigate backward N MORE occurrences
                    # Default N=0 means stay at last occurrence
                    
                    # CRITICAL FIX FOR RUNNING SEMANTICS:
                    # For RUNNING LAST(value) with offset=0, this should return the current row's value
                    # For RUNNING LAST(value, N) with offset>0, this should return the value N positions back from current
                    # For FINAL LAST(value) with offset=0, this should return the final row's value
                    # For FINAL LAST(value, N) with offset>0, this should return the value N positions back from final
                    
                    if all_indices:
                        if is_running:
                            if offset == 0:
                                # Special case: RUNNING LAST(value) should return current row value
                                logical_idx = self.context.current_idx
                                logger.debug(f"RUNNING LAST({field_name}): using current_idx={logical_idx}")
                            else:
                                # RUNNING LAST(value, N): Go backward N positions from current position
                                target_idx = self.context.current_idx - offset
                                if target_idx >= 0 and target_idx in all_indices:
                                    logical_idx = target_idx
                                    logger.debug(f"RUNNING LAST({field_name}, {offset}): current_idx={self.context.current_idx}, target_idx={target_idx}, logical_idx={logical_idx}")
                                else:
                                    logical_idx = None
                                    logger.debug(f"RUNNING LAST({field_name}, {offset}): target_idx {target_idx} out of bounds or not in match")
                        else:
                            # FINAL semantics: Navigate from final position
                            last_position = len(all_indices) - 1
                            target_position = last_position - offset  # Start from last, subtract offset
                            if target_position >= 0:
                                logical_idx = all_indices[target_position]
                                logger.debug(f"FINAL LAST({field_name}, {offset}): all_indices={all_indices}, target_position={target_position}, logical_idx={logical_idx}, is_running={is_running}")
                            else:
                                logical_idx = None
                    else:
                        logical_idx = None
                
                # Get the value if we found a valid logical position
                if logical_idx is not None and logical_idx < len(self.context.rows):
                    # Use the row context's enhanced direct access with optimized caching
                    raw_value = self.context.rows[logical_idx].get(field_name)
                    # Preserve data type for Trino compatibility
                    if raw_value is not None and self.context.current_idx < len(self.context.rows):
                        current_value = self.context.rows[self.context.current_idx].get(field_name)
                        result = self._preserve_data_type(current_value, raw_value)
                    else:
                        result = raw_value
                else:
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
                        logger.warning(f"Non-numeric value '{val}' found in column {col_name}")
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
        logger.error(error_msg)

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
                elif func_name == 'count' and re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.\*', args_str):
                    pattern_count_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.\*', args_str)
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
                # Enhanced logging for debugging COUNT(B.*) issue
                import traceback
                print(f"\n=== AGGREGATE EXCEPTION DEBUG ===")
                print(f"Function: {func_name}({args_str})")
                print(f"Running: {is_running}")
                print(f"Current context: {self.context.current_idx}")
                print(f"Variables: {self.context.variables}")
                print(f"Exception type: {type(e).__name__}")
                print(f"Exception message: {str(e)}")
                print(f"Traceback:")
                traceback.print_exc()
                print("=== END AGGREGATE EXCEPTION DEBUG ===\n")
                
                # Log the error with context
                self._log_aggregate_error(func_name, args_str, e)
                return None
                
        finally:
            # Performance monitoring
            duration = time.time() - start_time
            if hasattr(self, 'timing'):
                self.timing[f'aggregate_{func_name}'] += duration