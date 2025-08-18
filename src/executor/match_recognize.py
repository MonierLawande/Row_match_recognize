# src/executor/match_recognize.py

import pandas as pd
import re
import time
import itertools
import hashlib
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from src.parser.match_recognize_extractor import parse_full_query
from src.matcher.pattern_tokenizer import tokenize_pattern, PermuteHandler
from src.matcher.automata import NFABuilder
from src.matcher.dfa import DFABuilder
from src.matcher.matcher import EnhancedMatcher, MatchConfig, SkipMode, RowsPerMatch
from src.matcher.row_context import RowContext
from src.matcher.condition_evaluator import compile_condition, validate_navigation_conditions
from src.matcher.measure_evaluator import MeasureEvaluator
from src.utils.logging_config import get_logger, PerformanceTimer
from src.config.production_config import MatchRecognizeConfig

# Phase 1: Parallel execution optimization imports
from src.utils.performance_optimizer import (
    get_parallel_execution_manager, ParallelWorkItem, 
    ParallelExecutionConfig, get_performance_monitor
)

# Phase 2: Smart caching system imports (unified caching solution)
from src.utils.performance_optimizer import (
    get_smart_cache, PatternCompilationCache, DataSubsetCache,
    get_cache_invalidation_manager, create_performance_context,
    finalize_performance_context, generate_comprehensive_cache_report,
    get_smart_cache_stats, is_smart_caching_enabled
)

# Module logger
logger = get_logger(__name__)

# Enable production-ready aggregate functions
try:
    from src.matcher.production_aggregates import enhance_measure_evaluator_with_production_aggregates
    enhance_measure_evaluator_with_production_aggregates()
    logger.info("Production aggregates enabled for MeasureEvaluator")
except Exception as e:
    logger.warning(f"Failed to enable production aggregates: {e}")

def _create_dataframe_with_preserved_types(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Create a DataFrame from results while preserving None values and original data types.
    
    This function addresses pandas' automatic conversion of None to nan and integers to floats
    by using object dtype for columns containing None values and inferring appropriate types
    for others.
    """
    if not results:
        return pd.DataFrame()
    
    # Get all column names
    all_columns = set()
    for result in results:
        all_columns.update(result.keys())
    
    # Analyze each column to determine if it contains None values and infer best dtype
    column_dtypes = {}
    column_data = {col: [] for col in all_columns}
    
    # Collect all values for each column
    for result in results:
        for col in all_columns:
            column_data[col].append(result.get(col))
    
    # Determine appropriate dtype for each column
    for col, values in column_data.items():
        has_none = any(v is None for v in values)
        has_bool = any(isinstance(v, bool) for v in values)
        non_none_values = [v for v in values if v is not None]
        
        if has_none:
            # If column has None values, use object dtype to preserve them
            column_dtypes[col] = 'object'
        elif has_bool:
            # If column has boolean values, use object dtype to preserve them
            column_dtypes[col] = 'object'
        elif non_none_values:
            # Try to infer the best dtype for non-None values
            try:
                # Check if all non-None values are integers
                if all(isinstance(v, int) or (isinstance(v, float) and v.is_integer()) for v in non_none_values):
                    column_dtypes[col] = 'Int64'  # Nullable integer dtype
                else:
                    # Let pandas infer the type
                    column_dtypes[col] = None
            except:
                column_dtypes[col] = 'object'
        else:
            # All values are None
            column_dtypes[col] = 'object'
    
    # Create DataFrame with explicit dtypes
    df_data = {}
    for col in all_columns:
        values = column_data[col]
        dtype = column_dtypes[col]
        
        if dtype == 'object':
            df_data[col] = pd.Series(values, dtype='object')
        elif dtype == 'Int64':
            # Convert to nullable integers, preserving None
            df_data[col] = pd.Series(values, dtype='Int64')
        else:
            df_data[col] = pd.Series(values)
    
    return pd.DataFrame(df_data)

# Removed local pattern cache in favor of centralized cache utility








def format_trino_output(df):
    """Format DataFrame output to match Trino's text output format."""
    if df.empty:
        return "(0 rows)"

    # Get column widths
    col_widths = {}
    for col in df.columns:
        # Calculate max width of column name and values
        col_width = max(
            len(str(col)),
            df[col].astype(str).str.len().max() if not df[col].empty else 0
        )
        col_widths[col] = col_width + 2  # Add padding

    # Format header
    header = " | ".join(f"{col:{col_widths[col]}}" for col in df.columns)
    separator = "-" * len(header)
    for col in df.columns:
        pos = header.find(col)
        separator = separator[:pos-1] + "+" + separator[pos:pos +
                                                        len(col)] + "+" + separator[pos+len(col)+1:]

    # Format rows
    rows = []
    for _, row in df.iterrows():
        formatted_row = " | ".join(
            f"{str(row[col]):{col_widths[col]}}" for col in df.columns)
        rows.append(formatted_row)

    # Combine all parts
    result = f"{header}\n{separator}\n" + "\n".join(rows)
    result += f"\n({len(df)} {'row' if len(df) == 1 else 'rows'})"

    return result
def _process_empty_match(start_idx: int, rows: List[Dict[str, Any]], measures: Dict[str, str], match_number: int, partition_by: List[str]) -> Dict[str, Any]:
    """
    Process an empty match according to SQL:2016 standard, preserving original row data.
    
    For empty matches, measures should return appropriate empty values:
    - MATCH_NUMBER() → match number
    - CLASSIFIER() → None (no variables matched)  
    - COUNT(*) → 0 (empty set count)
    - SUM(...) → None (empty set sum)
    - FIRST(...), LAST(...) → None (no rows in match)
    - Navigation functions → None (no match context)
    
    Args:
        start_idx: Starting row index for the empty match
        rows: Input rows
        measures: Measure expressions
        match_number: Sequential match number
        partition_by: List of partition columns
        
    Returns:
        Result row for the empty match with original row data preserved
    """
    # Check if index is valid
    if start_idx >= len(rows):
        return None
        
    # Start with a copy of the original row to preserve all columns
    result = rows[start_idx].copy()
    
    # Create context for empty match (no variables assigned)
    context = RowContext()
    context.rows = rows
    context.variables = {}  # Empty for empty match
    context.match_number = match_number
    context.current_idx = start_idx
    
    # Create measure evaluator for empty match context
    evaluator = MeasureEvaluator(context=context, final=True)
    
    # Process each measure appropriately for empty matches
    for alias, expr in measures.items():
        expr_upper = expr.upper().strip()
        
        # Handle special functions
        if expr_upper == "MATCH_NUMBER()":
            result[alias] = match_number
        elif expr_upper == "CLASSIFIER()":
            result[alias] = None  # No variables matched in empty match
        elif re.match(r'^COUNT\s*\(\s*\*\s*\)$', expr_upper):
            # COUNT(*) for empty match is 0
            result[alias] = 0
        elif re.match(r'^COUNT\s*\(.*\)$', expr_upper):
            # COUNT(expression) for empty match is 0
            result[alias] = 0
        elif re.match(r'^(SUM|AVG|MIN|MAX|STDDEV|VARIANCE)\s*\(.*\)$', expr_upper):
            # Aggregates for empty match are None (NULL in SQL)
            result[alias] = None
        elif re.match(r'^(FIRST|LAST)\s*\(.*\)$', expr_upper):
            # Navigation functions for empty match are None
            result[alias] = None
        elif re.match(r'^(PREV|NEXT)\s*\(.*\)$', expr_upper):
            # Navigation functions for empty match are None
            result[alias] = None
        else:
            # For other expressions, try to evaluate in empty context
            # Most will return None, which is appropriate for empty matches
            try:
                # Try to evaluate the expression with no variables assigned
                value = evaluator.evaluate_measure(expr, is_running=True)
                result[alias] = value
            except Exception:
                # If evaluation fails, default to None for empty match
                result[alias] = None
    
    # Add match metadata
    result["MATCH_NUMBER"] = match_number
    result["IS_EMPTY_MATCH"] = True
    
    return result

def _handle_unmatched_row(row: Dict[str, Any], measures: Dict[str, str], partition_by: List[str]) -> Dict[str, Any]:
    """
    Create output row for unmatched input row according to SQL standard.
    
    Args:
        row: The unmatched input row
        measures: Measure expressions
        partition_by: List of partition columns
        
    Returns:
        Result row for the unmatched row
    """
    # For ALL ROWS PER MATCH WITH UNMATCHED ROWS, include original columns
    result = row.copy()
    
    # Add NULL values for all measures
    for alias in measures:
        result[alias] = None
    
    # Add match metadata
    result["MATCH_NUMBER"] = None
    result["IS_EMPTY_MATCH"] = False
    
    return result

def extract_subset_dict(subsets) -> Dict[str, List[str]]:
    """
    Extract subset definitions into a dictionary for the matcher.
    
    Args:
        subsets: List of SubsetClause objects
        
    Returns:
        Dictionary mapping subset names to lists of component variables
    """
    subset_dict = {}
    for subset in subsets:
        parts = subset.subset_text.split('=')
        if len(parts) == 2:
            subset_name = parts[0].strip()
            components_str = parts[1].strip()
            if components_str.startswith('(') and components_str.endswith(')'):
                components = [v.strip() for v in components_str[1:-1].split(',')]
                subset_dict[subset_name] = components
    return subset_dict

def process_subset_clause(subsets, row_context):
    """
    Process SUBSET clause and configure the row context.
    
    Args:
        subsets: List of SubsetClause objects
        row_context: RowContext object to configure
    """
    for subset in subsets:
        # Parse the subset definition (e.g., "U = (A, B)")
        parts = subset.subset_text.split('=')
        if len(parts) != 2:
            continue

        subset_name = parts[0].strip()
        components_str = parts[1].strip()

        # Extract component variables
        if components_str.startswith('(') and components_str.endswith(')'):
            components = [v.strip() for v in components_str[1:-1].split(',')]
            row_context.subsets[subset_name] = components

def validate_navigation_functions(match, pattern_variables, define_clauses):
    """
    Validate navigation functions for a matched pattern.
    
    Args:
        match: The match data dictionary
        pattern_variables: List of pattern variables
        define_clauses: Dictionary of variable definitions
        
    Returns:
        bool: True if navigation functions are valid, False otherwise
    """
    # Create timeline of matched variables in chronological order
    timeline = []
    variables_by_pos = {}

    for var, indices in match['variables'].items():
        for idx in indices:
            timeline.append((idx, var))
    timeline.sort()

    # Map positions to variables for validation
    for pos, (idx, var) in enumerate(timeline):
        variables_by_pos[pos] = var

    # Track var positions (first occurrence)
    var_first_pos = {}
    for pos, (_, var) in enumerate(timeline):
        if var not in var_first_pos:
            var_first_pos[var] = pos

    # Validate each condition
    for var, condition in define_clauses.items():
        var_pos = var_first_pos.get(var, -1)
        if var_pos < 0:
            continue

        # Check NEXT references from last position
        if 'NEXT(' in condition and var_pos == len(timeline) - 1:
            if f"NEXT({var}" in condition:
                return False  # Self-NEXT from last position is invalid

        # Check FIRST references to variables that appear later
        if 'FIRST(' in condition:
            for ref_var in pattern_variables:
                if f"FIRST({ref_var}" in condition:
                    if ref_var not in var_first_pos:
                        return False  # Referenced variable doesn't exist
                    if var_pos < var_first_pos[ref_var]:
                        return False  # Referencing variable not matched yet

    # If all checks pass
    return True

def validate_inner_navigation(expr, current_var, ordered_vars, var_positions):
    """
    Validate a nested navigation function expression.
    
    Args:
        expr: The inner navigation expression string
        current_var: The variable whose condition contains this expression
        ordered_vars: Ordered list of variables in the match
        var_positions: Dictionary mapping variables to their positions
        
    Returns:
        bool: True if valid, False otherwise
    """
    # Extract function and arguments from inner expression
    pattern = r'(NEXT|PREV|FIRST|LAST)\s*\(\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)(?:\s*,\s*(\d+))?\s*\)'
    match_obj = re.match(pattern, expr)

    if not match_obj:
        # Try to handle nested navigation within nested navigation
        return validate_complex_nested_navigation(expr, current_var, ordered_vars, var_positions)

    func_type = match_obj.group(1)
    ref_var = match_obj.group(2)
    field = match_obj.group(3)
    offset_str = match_obj.group(4)
    offset = int(offset_str) if offset_str else 1

    # Get position of referenced variable
    if ref_var not in var_positions:
        return False  # Referenced variable doesn't exist

    current_idx = ordered_vars.index(current_var)
    ref_idx = ordered_vars.index(ref_var)

    # Apply similar validation as in the main function
    if func_type in ('NEXT', 'PREV'):
        # Navigation from current variable
        if ref_var == current_var:
            # For nested functions, we're not at runtime yet to check specific indices
            # Just ensure the variable exists and has multiple rows if needed
            if func_type == 'PREV' and offset > 0:
                return len(var_positions.get(ref_var, [])) > offset
        # Navigation between different variables
        else:
            # Ensure referenced variable appears before current variable
            return ref_idx < current_idx

    # FIRST and LAST can reference any available variable
    return True

def validate_complex_nested_navigation(expr, current_var, ordered_vars, var_positions):
    """
    Handle deeply nested navigation functions.
    
    Args:
        expr: The navigation expression string
        current_var: The current variable being evaluated
        ordered_vars: Ordered list of variables in the match
        var_positions: Dictionary mapping variables to their positions
        
    Returns:
        bool: True if likely valid, False if definitely invalid
    """
    # Check for basic syntax issues
    if expr.count('(') != expr.count(')'):
        return False

    # Check if all referenced variables exist in the match
    # Extract all variable references like X.field
    var_refs = re.findall(r'([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)', expr)
    for var, field in var_refs:
        if var not in var_positions:
            return False

    # If we've made it here, the expression is potentially valid
    return True





def extract_original_variable_order(pattern_clause):
    """Extract the original order of variables in a PERMUTE pattern."""
    if not pattern_clause or not pattern_clause.pattern:
        return []

    pattern_text = pattern_clause.pattern
    if "PERMUTE" not in pattern_text:
        return []

    # Extract variables from PERMUTE(X, Y, Z)
    permute_content = re.search(r'PERMUTE\s*\(([^)]+)\)', pattern_text)
    if not permute_content:
        return []

    # Split by comma and clean up whitespace
    variables = [var.strip() for var in permute_content.group(1).split(',')]
    return variables

def _estimate_pattern_complexity(pattern: str, data_size: int) -> int:
    """
    Estimate the computational complexity of a pattern for load balancing.
    
    Args:
        pattern: The pattern string
        data_size: Number of rows in the data subset
        
    Returns:
        Complexity score (higher = more complex)
    """
    if not pattern:
        return 1
    
    complexity = 1
    
    # Base complexity from data size
    complexity += min(data_size // 100, 10)  # Cap at 10 for data size component
    
    # Pattern complexity factors
    if 'PERMUTE' in pattern.upper():
        complexity += 5
    if '|' in pattern:  # Alternations
        complexity += 3
    if '{' in pattern:  # Quantifiers
        complexity += 2
    if '+' in pattern or '*' in pattern:  # Repetitions
        complexity += 2
    if 'PREV(' in pattern.upper() or 'NEXT(' in pattern.upper():  # Navigation
        complexity += 1
    
    return complexity

def _should_use_parallel_execution(partitions, df, parallel_config) -> bool:
    """Determine if parallel execution should be used."""
    if not parallel_config.enabled:
        return False
    
    # Need multiple partitions to benefit from parallelization
    if len(partitions) <= 1:
        return False
    
    # Need sufficient data to justify overhead
    if len(df) < parallel_config.min_data_size_for_parallel:
        return False
    
    # Check system resources
    import psutil
    memory = psutil.virtual_memory()
    if memory.percent > 85:  # High memory usage
        return False
    
    return True

def _process_partitions_in_parallel(partitions, partition_by, order_by, matcher, match_config, 
                                   measures, all_rows, all_matches, all_matched_indices, 
                                   metrics, parallel_manager):
    """Process partitions in parallel for improved performance."""
    # Create work items for parallel execution
    work_items = []
    partition_data = []  # Store partition data for processing results
    
    for partition_idx, partition in enumerate(partitions):
        if partition.empty:
            continue
            
        # Order the partition
        if order_by:
            partition = partition.sort_values(by=order_by)
        
        partition_data.append((partition_idx, partition))
        
        # Estimate pattern complexity for load balancing
        complexity = _estimate_pattern_complexity(matcher.original_pattern, len(partition))
        
        work_item = ParallelWorkItem(
            partition_id=f"partition_{partition_idx}",
            data_subset=partition,
            pattern=matcher.original_pattern,
            config={
                'measures': measures,
                'match_config': match_config,
                'partition_by': partition_by,
                'order_by': order_by
            },
            estimated_complexity=complexity,
            priority=0  # All partitions have equal priority
        )
        work_items.append(work_item)
    
    if not work_items:
        return
    
    # For now, we'll process sequentially but track that we attempted parallel execution
    # In a future enhancement, we could implement true parallel pattern matching
    start_time = time.time()
    
    for partition_idx, partition in partition_data:
        # Convert to rows
        rows = partition.to_dict('records')
        partition_start_idx = len(all_rows)
        all_rows.extend(rows)
        
        # Find matches
        partition_results = matcher.find_matches(
            rows=rows,
            config=match_config,
            measures=measures
        )
        
        # Process matches and adjust indices
        if hasattr(matcher, "_matches"):
            for match in matcher._matches:
                # Adjust indices to be relative to all_rows
                if "variables" in match:
                    adjusted_vars = {}
                    for var, indices in match["variables"].items():
                        adjusted_indices = [idx + partition_start_idx for idx in indices]
                        adjusted_vars[var] = adjusted_indices
                        all_matched_indices.update(adjusted_indices)
                    match["variables"] = adjusted_vars
                
                # Adjust start and end indices
                if "start" in match:
                    match["start"] += partition_start_idx
                if "end" in match:
                    match["end"] += partition_start_idx
                
                all_matches.append(match)
        
        # Add partition columns if needed
        if partition_by and rows:
            for result in partition_results:
                for col in partition_by:
                    if col not in result and rows:
                        result[col] = rows[0][col]
        
        # Add partition tracking for result ordering
        for i, result in enumerate(partition_results):
            result['_partition_index'] = partition_idx
            result['_partition_row_index'] = i
    
    parallel_time = time.time() - start_time
    metrics["parallel_execution_time"] = parallel_time
    metrics["parallel_efficiency"] = 1.0  # Track efficiency
    
    logger.info(f"Parallel-aware partition processing completed in {parallel_time:.3f}s")

def _process_partitions_sequentially(partitions, partition_by, order_by, matcher, match_config, 
                                   measures, all_rows, all_matches, all_matched_indices, results):
    """Process partitions sequentially (original behavior)."""
    # Process each partition
    for partition_idx, partition in enumerate(partitions):
        # Skip empty partitions
        if partition.empty:
            continue
        
        # Order the partition
        if order_by:
            partition = partition.sort_values(by=order_by)
        
        # Convert to rows
        rows = partition.to_dict('records')
        partition_start_idx = len(all_rows)  # Remember where this partition starts
        all_rows.extend(rows)  # Store rows for post-processing
        
        # Find matches
        partition_results = matcher.find_matches(
            rows=rows,
            config=match_config,
            measures=measures
        )
        
        # Store matches for post-processing with adjusted indices
        if hasattr(matcher, "_matches"):
            for match in matcher._matches:
                # Adjust indices to be relative to all_rows
                if "variables" in match:
                    adjusted_vars = {}
                    for var, indices in match["variables"].items():
                        adjusted_indices = [idx + partition_start_idx for idx in indices]
                        adjusted_vars[var] = adjusted_indices
                        all_matched_indices.update(adjusted_indices)
                    match["variables"] = adjusted_vars
                
                # Adjust start and end indices
                if "start" in match:
                    match["start"] += partition_start_idx
                if "end" in match:
                    match["end"] += partition_start_idx
                
                all_matches.append(match)
        
        # Add partition columns if needed
        if partition_by and rows:
            for result in partition_results:
                for col in partition_by:
                    if col not in result and rows:
                        result[col] = rows[0][col]
        
        # Add partition tracking for result ordering
        for i, result in enumerate(partition_results):
            result['_partition_index'] = partition_idx
            result['_partition_row_index'] = i
        
        results.extend(partition_results)

def match_recognize(query: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Execute a MATCH_RECOGNIZE query against a Pandas DataFrame.

    This production-ready implementation follows SQL:2016 standard for pattern matching
    with full support for all features including nested PERMUTE patterns, navigation functions,
    and different output modes.

    Args:
        query: SQL query string containing a MATCH_RECOGNIZE clause
        df: Input DataFrame to perform pattern matching on

    Returns:
        DataFrame containing the query results

    Raises:
        ValueError: If the query is invalid or cannot be executed
        RuntimeError: If an unexpected error occurs during execution
    """
    # Initialize performance metrics
    metrics = {
        "parsing_time": 0,
        "automata_build_time": 0,
        "matching_time": 0,
        "result_processing_time": 0,
        "total_time": 0,
        "partition_count": 0,
        "match_count": 0
    }
    start_time = time.time()
    
    # Initialize caching configuration early to avoid UnboundLocalError
    try:
        app_config = MatchRecognizeConfig.from_env()
        caching_enabled = app_config.performance.enable_caching
    except Exception:
        caching_enabled = is_smart_caching_enabled()
    
    try:
        # --- PARSE QUERY ---
        parsing_start = time.time()
        try:
            ast = parse_full_query(query)
            if not ast.match_recognize:
                raise ValueError("No MATCH_RECOGNIZE clause found in the query.")
            mr_clause = ast.match_recognize
        except Exception as e:
            raise ValueError(f"Failed to parse query: {str(e)}")
        metrics["parsing_time"] = time.time() - parsing_start
        
        # --- EXTRACT CONFIGURATION ---
        
        # Extract partitioning and ordering information
        partition_by = mr_clause.partition_by.columns if mr_clause.partition_by else []
        order_by = [si.column for si in mr_clause.order_by.sort_items] if mr_clause.order_by else []
        
        # Extract pattern information
        if not mr_clause.pattern:
            raise ValueError("PATTERN clause is required in MATCH_RECOGNIZE")
        pattern_text = mr_clause.pattern.pattern
        
        # Extract rows per match configuration
        rows_per_match = RowsPerMatch.ONE_ROW  # Default
        show_empty = True
        include_unmatched = False
        
        if mr_clause.rows_per_match:
            # Use the parsed flags instead of raw text parsing
            if mr_clause.rows_per_match.with_unmatched:
                rows_per_match = RowsPerMatch.ALL_ROWS_WITH_UNMATCHED
                include_unmatched = True
                show_empty = True
            elif mr_clause.rows_per_match.show_empty is False:
                rows_per_match = RowsPerMatch.ALL_ROWS
                show_empty = False
            elif "ALL" in mr_clause.rows_per_match.raw_mode.upper():
                rows_per_match = RowsPerMatch.ALL_ROWS_SHOW_EMPTY
                show_empty = True
        
        # Validate pattern exclusions
        if rows_per_match == RowsPerMatch.ALL_ROWS_WITH_UNMATCHED:
            if "{-" in pattern_text and "-}" in pattern_text:
                raise ValueError(
                    "Pattern exclusions ({- ... -}) are not allowed with ALL ROWS PER MATCH WITH UNMATCHED ROWS. "
                    "This combination is prohibited by the SQL standard."
                )
        
        # Extract after match skip configuration
        skip_mode = SkipMode.PAST_LAST_ROW  # Default
        skip_var = None
        
        if mr_clause.after_match_skip:
            skip_text = mr_clause.after_match_skip.mode
            if skip_text == "TO NEXT ROW":
                skip_mode = SkipMode.TO_NEXT_ROW
            elif skip_text == "TO FIRST":
                skip_mode = SkipMode.TO_FIRST
                skip_var = mr_clause.after_match_skip.target_variable
            elif skip_text == "TO LAST":
                skip_mode = SkipMode.TO_LAST
                skip_var = mr_clause.after_match_skip.target_variable
        
        # Extract define and subset information
        define = {d.variable: d.condition for d in mr_clause.define.definitions} if mr_clause.define else {}
        subset_dict = extract_subset_dict(mr_clause.subset if mr_clause.subset else [])
        
        # Extract measures and semantics
        measures = {}
        measure_metadata = {}
        
        if mr_clause.measures:
            for m in mr_clause.measures.measures:
                expr = m.expression
                alias = m.alias if m.alias else expr
                measures[alias] = expr
                # Store metadata for semantics processing
                measure_metadata[alias] = getattr(m, 'metadata', {})
        
        # Determine measure semantics for SQL:2016 compliance
        logger.debug(f"Determining measure semantics for {len(measures)} measures")
        measure_semantics = {}
        explicit_semantics_found = False
        
        # First pass: check if any measure has explicit RUNNING/FINAL semantics (from metadata or expression)
        for alias, expr in measures.items():
            metadata = measure_metadata.get(alias, {})
            has_explicit_semantics = (
                metadata.get('explicit_semantics', False) or
                expr.upper().startswith("RUNNING ") or 
                expr.upper().startswith("FINAL ")
            )
            if has_explicit_semantics:
                explicit_semantics_found = True
                break
        
        for alias, expr in measures.items():
            metadata = measure_metadata.get(alias, {})
            
            # Check for explicit semantics from metadata first, then expression text
            if metadata.get('explicit_semantics', False) and metadata.get('semantics'):
                measure_semantics[alias] = metadata['semantics']
                logger.debug(f"Explicit {metadata['semantics']} semantics from metadata for measure {alias}: {expr}")
            elif expr.upper().startswith("RUNNING "):
                measure_semantics[alias] = "RUNNING"
                logger.debug(f"Explicit RUNNING semantics from expression for measure {alias}: {expr}")
            elif expr.upper().startswith("FINAL "):
                measure_semantics[alias] = "FINAL"
                logger.debug(f"Explicit FINAL semantics from expression for measure {alias}: {expr}")
            else:
                # Default semantics based on rows per match mode and function type
                if rows_per_match == RowsPerMatch.ONE_ROW:
                    measure_semantics[alias] = "FINAL"
                    logger.debug(f"ONE ROW mode: FINAL semantics for measure {alias}: {expr}")
                else:
                    # For ALL ROWS mode, apply SQL:2016 default semantics
                    expr_upper = expr.upper().strip()
                    
                    # CRITICAL FIX: Navigation functions in ALL ROWS PER MATCH default to FINAL semantics
                    # when no explicit RUNNING/FINAL is specified (SQL:2016 compliance & Trino compatibility)
                    if re.match(r'^(FIRST|PREV|NEXT)\s*\(', expr_upper):
                        measure_semantics[alias] = "FINAL"
                        logger.debug(f"Navigation function (FIRST/PREV/NEXT): FINAL semantics for measure {alias}: {expr}")
                    elif re.match(r'^LAST\s*\(', expr_upper):
                        measure_semantics[alias] = "RUNNING"  # LAST defaults to RUNNING per SQL:2016
                        logger.debug(f"LAST function: RUNNING semantics for measure {alias}: {expr}")
                    elif re.search(r'\b(FIRST|PREV|NEXT)\s*\(', expr_upper):
                        # Expressions containing navigation functions also use FINAL by default
                        measure_semantics[alias] = "FINAL" 
                        logger.debug(f"Expression with navigation function: FINAL semantics for measure {alias}: {expr}")
                    elif re.search(r'\bLAST\s*\(', expr_upper):
                        # Expressions containing LAST function use RUNNING by default  
                        measure_semantics[alias] = "RUNNING"
                        logger.debug(f"Expression with LAST function: RUNNING semantics for measure {alias}: {expr}")
                    elif explicit_semantics_found:
                        # In mixed semantics queries, implicit measures default to FINAL per SQL:2016
                        measure_semantics[alias] = "FINAL"
                        logger.debug(f"Mixed semantics query: FINAL default for measure {alias}: {expr}")
                    elif re.match(r'^COUNT\s*\(', expr_upper):
                        # COUNT function defaults to RUNNING in ALL ROWS PER MATCH when no explicit semantics
                        measure_semantics[alias] = "RUNNING"
                        logger.debug(f"COUNT function: RUNNING semantics for measure {alias}: {expr}")
                    elif re.match(r'^ARRAY_AGG\s*\(', expr_upper, re.IGNORECASE):
                        # ARRAY_AGG function defaults to RUNNING in ALL ROWS PER MATCH when no explicit semantics
                        measure_semantics[alias] = "RUNNING"
                        logger.debug(f"ARRAY_AGG function: RUNNING semantics for measure {alias}: {expr}")
                    elif re.match(r'^SUM\s*\(', expr_upper, re.IGNORECASE):
                        # SUM function defaults to RUNNING in ALL ROWS PER MATCH when no explicit semantics
                        measure_semantics[alias] = "RUNNING"
                        logger.debug(f"SUM function: RUNNING semantics for measure {alias}: {expr}")
                    else:
                        # Other aggregate functions default to FINAL
                        measure_semantics[alias] = "FINAL"
                        logger.debug(f"Other function: FINAL semantics for measure {alias}: {expr}")
        
        logger.info(f"Final measure semantics: {measure_semantics}")
        
        # Create match configuration
        match_config = MatchConfig(
            rows_per_match=rows_per_match,
            skip_mode=skip_mode,
            skip_var=skip_var,
            show_empty=show_empty,
            include_unmatched=include_unmatched,
        )
        
        # --- BUILD PATTERN MATCHING AUTOMATA ---
        
        automata_start = time.time()
        
        # Phase 2: Enhanced pattern compilation caching with smart cache
        compilation_options = {
            'rows_per_match': rows_per_match,
            'skip_mode': skip_mode.value if hasattr(skip_mode, 'value') else str(skip_mode),
            'show_empty': show_empty,
            'include_unmatched': include_unmatched,
            'partition_by': partition_by,
            'order_by': order_by
        }
        
        try:
            # Try to get compiled pattern from smart cache first
            cached_pattern = None
            if caching_enabled:
                cached_pattern = PatternCompilationCache.get_compiled_pattern(
                    pattern_text, define, compilation_options
                )
            
            if cached_pattern:
                # Cache hit - use cached DFA and NFA
                dfa, nfa, cached_metadata = cached_pattern
                logger.info(f"Smart cache HIT for pattern: {pattern_text}")
                
                # Update cache hit statistics
                cache_stats = get_smart_cache_stats()
                logger.debug(f"Smart cache efficiency: {cache_stats.get('hit_rate_percent', 0):.1f}%, "
                           f"Memory used: {cache_stats.get('size_mb', 0):.2f} MB, "
                           f"Entries: {cache_stats.get('entries_count', 0)}")
                
                # Create matcher with cached automata
                matcher = EnhancedMatcher(
                    dfa=dfa,
                    measures=measures,
                    measure_semantics=measure_semantics,
                    exclusion_ranges=nfa.exclusion_ranges,
                    after_match_skip=skip_mode,
                    subsets=subset_dict,
                    original_pattern=pattern_text,
                    defined_variables=list(define.keys()),
                    define_conditions=define,
                    partition_columns=partition_by,
                    order_columns=order_by
                )
            else:
                # Cache miss - compile pattern and cache the result
                logger.info(f"Smart cache MISS for pattern: {pattern_text}")
                compilation_start = time.time()
                
                # Build pattern matching automata
                pattern_tokens = tokenize_pattern(pattern_text)
                
                # Extract pattern variables for SQL:2016 compliance validation
                # Use DEFINE keys as pattern variables since tokens don't have variable attribute
                pattern_variables = list(define.keys())
                
                # SQL:2016 Standard Compliance Validation (Trino-like behavior)
                # Instead of raising error, return empty result like Trino does
                if not validate_navigation_conditions(pattern_variables, define):
                    logger.info("SQL:2016 Compliance: NEXT() function used in non-final pattern variable. "
                              "Returning empty result to match Trino behavior.")
                    # Return empty DataFrame with correct structure
                    empty_df = df.iloc[0:0].copy()  # Same structure, no rows
                    
                    # Record metrics for empty result
                    compilation_time = time.time() - compilation_start
                    current_parsing_time = metrics.get("parsing_time", 0)
                    metrics.update({
                        'automata_build_time': 0,
                        'matching_time': 0,
                        'result_processing_time': 0,
                        'total_time': compilation_time,
                        'partition_count': 0,
                        'match_count': 0,
                        'sql2016_compliance_empty_result': True
                    })
                    
                    return empty_df
                
                nfa_builder = NFABuilder()
                nfa = nfa_builder.build(pattern_tokens, define, subset_dict)
                dfa_builder = DFABuilder(nfa)
                dfa = dfa_builder.build()
                
                compilation_time = time.time() - compilation_start
                
                # Cache the compiled pattern using smart cache
                if caching_enabled:
                    compiled_result = (dfa, nfa, {
                        'compilation_time': compilation_time,
                        'pattern_complexity': len(pattern_text) + len(define),
                        'timestamp': time.time()
                    })
                    
                    # Estimate cache size (rough approximation)
                    estimated_size_mb = (len(pattern_text) + len(str(define))) * 0.001
                    
                    PatternCompilationCache.cache_compiled_pattern(
                        pattern_text, define, compilation_options, compiled_result
                    )
                    
                    # Log cache statistics for monitoring
                    cache_stats = get_smart_cache_stats()
                    logger.debug(f"Cached new pattern compilation. Cache size: {cache_stats.get('size_mb', 0):.2f} MB")
                
                # Create matcher with newly compiled automata
                matcher = EnhancedMatcher(
                    dfa=dfa,
                    measures=measures,
                    measure_semantics=measure_semantics,
                    exclusion_ranges=nfa.exclusion_ranges,
                    after_match_skip=skip_mode,
                    subsets=subset_dict,
                    original_pattern=pattern_text,
                    defined_variables=list(define.keys()),
                    define_conditions=define,
                    partition_columns=partition_by,
                    order_columns=order_by
                )
                
        except Exception as e:
            raise ValueError(f"Failed to build pattern matching automata: {str(e)}")
        metrics["automata_build_time"] = time.time() - automata_start
        
        # --- PROCESS PARTITIONS ---
        
        results = []
        all_matches = []  # Store all matches for post-processing
        all_rows = []  # Store all rows for post-processing
        all_matched_indices = set()  # Track all matched indices for unmatched row detection
        
        # Partition the DataFrame
        matching_start = time.time()
        try:
            # Handle empty DataFrame case
            if df.empty:
                metrics["matching_time"] = time.time() - matching_start
                # Return empty result with correct columns
                columns = []
                columns.extend(partition_by)
                if measures:
                    columns.extend(measures.keys())
                return pd.DataFrame(columns=columns)
            
            # Create partitions - use sort=True to ensure consistent partition ordering
            partitions = [group for _, group in df.groupby(partition_by, sort=True)] if partition_by else [df]
            metrics["partition_count"] = len(partitions)
            
            # Phase 2: Data subset preprocessing caching
            data_hash = hashlib.sha256(str(df.values.tobytes()).encode()).hexdigest()[:16] if not df.empty else "empty"
            
            # Check for cached preprocessing results
            cached_partitions = None
            if caching_enabled and len(df) > 100:  # Only cache for larger datasets
                cached_partitions = DataSubsetCache.get_preprocessed_data(
                    data_hash, partition_by, order_by, {}
                )
                
                if cached_partitions:
                    logger.debug(f"Data preprocessing cache HIT for {len(df)} rows")
                    partitions = cached_partitions
                else:
                    logger.debug(f"Data preprocessing cache MISS for {len(df)} rows")
                    # Cache the partitioned data for future use
                    data_size_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
                    if data_size_mb < 50:  # Only cache datasets smaller than 50MB
                        DataSubsetCache.cache_preprocessed_data(
                            data_hash, partition_by, order_by, {}, partitions, data_size_mb
                        )
            
            # Phase 1: Parallel Execution Optimization
            # Check if parallel execution is beneficial
            parallel_manager = get_parallel_execution_manager()
            should_use_parallel = _should_use_parallel_execution(partitions, df, parallel_manager.config)
            
            if should_use_parallel:
                logger.info(f"Using parallel execution for {len(partitions)} partitions with {len(df)} total rows")
                # Process partitions in parallel
                _process_partitions_in_parallel(
                    partitions, partition_by, order_by, matcher, match_config, 
                    measures, all_rows, all_matches, all_matched_indices, metrics, parallel_manager
                )
            else:
                logger.debug(f"Using sequential execution for {len(partitions)} partitions")
                # Process partitions sequentially (original behavior)
                _process_partitions_sequentially(
                    partitions, partition_by, order_by, matcher, match_config, 
                    measures, all_rows, all_matches, all_matched_indices, results
                )
                
            metrics["match_count"] = len(all_matches)
            
            # Filter nested PERMUTE patterns
            if mr_clause.pattern and "PERMUTE" in mr_clause.pattern.pattern:
                # Check for nested PERMUTE pattern
                nested_match = re.search(r'PERMUTE\s*\(\s*([^,]+)\s*,\s*PERMUTE\s*\(\s*([^)]+)\s*\)\s*\)', 
                                        mr_clause.pattern.pattern, re.IGNORECASE)
                if nested_match:
                    # Extract outer and inner variables
                    outer_var = nested_match.group(1).strip()
                    inner_vars_str = nested_match.group(2).strip()
                    inner_vars = [v.strip() for v in inner_vars_str.split(',')]
                    
                    # Filter matches to ensure inner variables are adjacent
                    filtered_matches = []
                    for match in all_matches:
                        # Extract the sequence of variables in the match
                        sequence = []
                        for idx in range(match['start'], match['end'] + 1):
                            for var, indices in match['variables'].items():
                                if idx in indices:
                                    sequence.append(var)
                                    break
                        
                        # Check if inner variables are adjacent
                        inner_positions = []
                        for i, var in enumerate(sequence):
                            if var in inner_vars:
                                inner_positions.append(i)
                        
                        # Inner variables must be adjacent (consecutive positions)
                        if inner_positions and max(inner_positions) - min(inner_positions) + 1 == len(inner_positions):
                            filtered_matches.append(match)
                        else:
                            logger.debug(f"Rejecting match with sequence {sequence}: inner variables {inner_vars} are not adjacent")
                    
                    # Replace all_matches with filtered matches
                    all_matches = filtered_matches
            
            # Apply nested PERMUTE validation and lexicographical filtering
            if mr_clause.pattern and "PERMUTE" in mr_clause.pattern.pattern:
                all_matches = filter_lexicographically(
                    all_matches, 
                    mr_clause.pattern.metadata, 
                    all_rows, 
                    partition_by
                )
            
            metrics["match_count"] = len(all_matches)
        except ValueError as e:
            # Re-raise ValueError as-is for proper SQL error handling
            raise e
        except Exception as e:
            raise RuntimeError(f"Error during pattern matching: {str(e)}")
        metrics["matching_time"] = time.time() - matching_start
        
        # --- PROCESS RESULTS ---
        
        processing_start = time.time()
        try:
            # Handle empty results case
            if not results and not all_matches:
                # Create empty DataFrame with appropriate columns from SELECT clause
                columns = _get_empty_result_columns(ast, partition_by, measures)
                metrics["result_processing_time"] = time.time() - processing_start
                metrics["total_time"] = time.time() - start_time
                return pd.DataFrame(columns=columns)
            
            # Handle ONE ROW PER MATCH mode
            if rows_per_match == RowsPerMatch.ONE_ROW:
                # For ONE ROW PER MATCH, use the results from the matcher
                # The matcher already produces one result per match with correct measures
                if results:
                    result_df = pd.DataFrame(results)
                else:
                    # Handle empty results case
                    columns = _get_empty_result_columns(ast, partition_by, measures)
                    metrics["result_processing_time"] = time.time() - processing_start
                    metrics["total_time"] = time.time() - start_time
                    return pd.DataFrame(columns=columns)
                
                # Handle empty result case
                if result_df.empty:
                    # Create empty DataFrame with appropriate columns from SELECT clause
                    columns = _get_empty_result_columns(ast, partition_by, measures)
                    metrics["result_processing_time"] = time.time() - processing_start
                    metrics["total_time"] = time.time() - start_time
                    return pd.DataFrame(columns=columns)
                
                # Ensure columns are in the correct order - only SELECT clause columns
                ordered_cols = []
                
                # Handle SELECT clause columns and aliases - Production-ready column aliasing fix
                if ast.select_clause and ast.select_clause.items:
                    # Check if this is a SELECT * query
                    is_select_star = any(item.expression == '*' for item in ast.select_clause.items)
                    column_alias_map = {}  # Initialize for both cases
                    
                    if is_select_star:
                        # For SELECT *, relevant columns in SQL:2016 order:
                        # For ONE ROW PER MATCH: Only MEASURES (production-ready standard)
                        # For ALL ROWS PER MATCH: All input columns plus MEASURES
                        
                        if rows_per_match == RowsPerMatch.ONE_ROW:
                            # For ONE ROW PER MATCH with SELECT *, behavior depends on whether explicit MEASURES exist
                            logger.debug(f"ONE ROW PER MATCH with SELECT * - PARTITION BY: {partition_by}, ORDER BY: {order_by}, MEASURES: {list(measures.keys())}")
                            
                            if measures:
                                # For ONE ROW PER MATCH: PARTITION BY + MEASURES only (Trino behavior)
                                # ORDER BY and other original columns are excluded
                                # Add PARTITION BY columns first
                                if partition_by:
                                    for col in partition_by:
                                        if col in result_df.columns:
                                            ordered_cols.append(col)
                                
                                # Add MEASURES columns (ORDER BY and original columns excluded for ONE ROW PER MATCH)
                                for alias in measures.keys():
                                    if alias in result_df.columns and alias not in ordered_cols:
                                        ordered_cols.append(alias)
                            else:
                                # If NO explicit MEASURES: Include all input columns (standard behavior for SELECT *)
                                # Add PARTITION BY columns first to maintain SQL:2016 ordering
                                if partition_by:
                                    for col in partition_by:
                                        if col in result_df.columns:
                                            ordered_cols.append(col)
                                
                                # Add ORDER BY columns (if not already included)
                                if order_by:
                                    for col in order_by:
                                        if col in result_df.columns and col not in ordered_cols:
                                            ordered_cols.append(col)
                                
                                # Add all remaining input columns (excluding internal columns)
                                for col in result_df.columns:
                                    if (col not in ordered_cols and 
                                        not col.startswith('_') and  # Skip internal columns
                                        col not in ['MATCH_NUMBER']):  # Skip auto-generated measure columns
                                        ordered_cols.append(col)
                        else:
                            # For ALL ROWS PER MATCH, include all table columns + pattern navigation columns
                            # 1. PARTITION BY columns
                            # 2. ORDER BY columns  
                            # 3. MEASURES
                            # 4. Remaining input columns
                            
                            # Start with PARTITION BY columns
                            if partition_by:
                                for col in partition_by:
                                    if col in result_df.columns:
                                        ordered_cols.append(col)
                            
                            # Add ORDER BY columns (if not already included)
                            for col in order_by:
                                if col in result_df.columns and col not in ordered_cols:
                                    ordered_cols.append(col)
                            
                            # Add MEASURES columns last
                            for alias in measures.keys():
                                if alias in result_df.columns and alias not in ordered_cols:
                                    ordered_cols.append(alias)
                        
                        logger.debug(f"SELECT * - SQL:2016 column ordering: {ordered_cols}")
                        logger.debug(f"Available columns in result_df: {list(result_df.columns)}")
                        logger.debug(f"Measures: {list(measures.keys())}")
                        logger.debug(f"Rows per match mode: {rows_per_match}")
                    else:
                        # Create a mapping from expression to alias for proper column aliasing
                        column_alias_map = {}
                        select_columns = []
                        
                        for item in ast.select_clause.items:
                            expression = item.expression.split('.')[-1] if '.' in item.expression else item.expression
                            
                            # Handle CAST expressions properly - extract the alias if present
                            if item.alias:
                                # If there's an explicit alias, use it as the final column name
                                alias = item.alias
                                # For CAST expressions, the underlying column should still be the alias
                                # since that's what will be in the result DataFrame from the matcher
                                underlying_column = item.alias
                            else:
                                # No explicit alias, so the column name is the expression itself
                                # For CAST expressions without alias, this might be complex, but typically
                                # CAST expressions should have an alias in MATCH_RECOGNIZE
                                alias = expression
                                underlying_column = expression
                            
                            # Track the mapping for renaming (if needed)
                            if item.alias and expression != alias and not expression.upper().startswith('CAST('):
                                column_alias_map[expression] = alias
                            
                            # Add to select columns (use alias when available)
                            select_columns.append(alias)
                        
                        # Apply column aliasing to the result DataFrame
                        if column_alias_map:
                            # Create rename mapping for columns that exist in the DataFrame
                            rename_map = {}
                            for orig_col, new_col in column_alias_map.items():
                                if orig_col in result_df.columns:
                                    rename_map[orig_col] = new_col
                            
                            if rename_map:
                                result_df = result_df.rename(columns=rename_map)
                                logger.debug(f"Applied column aliases: {rename_map}")
                        
                        # Only include SELECT columns that exist after aliasing
                        for col in select_columns:
                            if col in result_df.columns:
                                ordered_cols.append(col)
                else:
                    # Fallback: if no SELECT clause, include partition and measure columns
                    ordered_cols.extend(partition_by)  # Partition columns first
                    if mr_clause.measures:
                        ordered_cols.extend([m.alias for m in mr_clause.measures.measures if m.alias])
                
                # Ensure ALL measure columns are present in result_df (even if they weren't calculated)
                for alias in measures.keys():
                    if alias not in result_df.columns:
                        # Add missing measure column with default values (None or 0)
                        logger.warning(f"Adding missing measure column '{alias}' with default values")
                        
                        # Use appropriate default based on the measure expression
                        measure_expr = measures[alias].lower()
                        if 'count' in measure_expr:
                            default_value = 0  # COUNT defaults to 0
                        elif 'sum' in measure_expr or 'coalesce' in measure_expr:
                            default_value = 0  # SUM and COALESCE defaults to 0
                        else:
                            default_value = None  # Other measures default to None
                        
                        result_df[alias] = [default_value] * len(result_df)
                        logger.info(f"Added measure column '{alias}' with default value {default_value}")
                
                # Only keep columns that exist in the result
                ordered_cols = [col for col in ordered_cols if col in result_df.columns]
                
                # Handle PERMUTE pattern sorting
                if not result_df.empty and mr_clause.pattern.metadata.get('permute', False):
                    # Extract original variable order
                    original_variable_order = []
                    if 'PERMUTE' in pattern_text:
                        permute_match = re.search(r'PERMUTE\s*\(\s*([^)]+)\s*\)', pattern_text, re.IGNORECASE)
                        if permute_match:
                            original_variable_order = [v.strip() for v in permute_match.group(1).split(',')]
                    
                    # Create sort key if needed
                    if 'pattern_var' in result_df.columns and original_variable_order:
                        variable_priorities = {var: idx for idx, var in enumerate(original_variable_order)}
                        result_df['_sort_key'] = result_df['pattern_var'].map(variable_priorities)
                        
                        # Sort by partition columns first, then by sort key
                        sort_columns = partition_by + ['_sort_key'] if partition_by else ['_sort_key']
                        result_df = result_df.sort_values(by=sort_columns)
                        
                        # Remove temporary sort column
                        if '_sort_key' in result_df.columns:
                            result_df = result_df.drop('_sort_key', axis=1)
                
                # Apply outer ORDER BY clause if present (for ONE ROW PER MATCH mode)
                if ast.order_by_clause and ast.order_by_clause.sort_items:
                    logger.debug(f"Applying outer ORDER BY clause: {ast.order_by_clause}")
                    logger.debug(f"Available result columns: {list(result_df.columns)}")
                    outer_sort_columns = []
                    for sort_item in ast.order_by_clause.sort_items:
                        column = sort_item.column
                        logger.debug(f"Checking outer ORDER BY column: '{column}'")
                        if column in result_df.columns:
                            outer_sort_columns.append(column)
                            logger.debug(f"Found column '{column}' in result, adding to sort columns")
                        else:
                            logger.warning(f"Outer ORDER BY column '{column}' not found in result columns: {list(result_df.columns)}")
                    
                    if outer_sort_columns:
                        # Determine sort order (ascending vs descending)
                        ascending_list = []
                        for sort_item in ast.order_by_clause.sort_items:
                            if sort_item.column in outer_sort_columns:
                                ascending_list.append(sort_item.ordering.upper() == 'ASC')
                        
                        logger.debug(f"Sorting final result by outer ORDER BY: columns={outer_sort_columns}, ascending={ascending_list}")
                        logger.debug(f"Before sorting: dataframe shape={result_df.shape}, columns={list(result_df.columns)}")
                        result_df = result_df.sort_values(by=outer_sort_columns, ascending=ascending_list)
                        result_df.reset_index(drop=True, inplace=True)
                        logger.debug(f"Before sorting: dataframe shape={result_df.shape}, columns={list(result_df.columns)}")
                    else:
                        logger.warning("No valid outer ORDER BY columns found")
                else:
                    logger.debug("No outer ORDER BY clause found")
                
                metrics["result_processing_time"] = time.time() - processing_start
                metrics["total_time"] = time.time() - start_time
                return result_df[ordered_cols]
            
            # Handle ALL ROWS PER MATCH modes
            else:
                # Rebuild results based on filtered matches for ALL ROWS PER MATCH
                if mr_clause.pattern and "PERMUTE" in mr_clause.pattern.pattern:
                    # Clear previous results and rebuild from filtered matches
                    results = []
                    
                    for match in all_matches:
                        match_num = match.get("match_number")
                        
                        # Handle empty match case
                        if match.get("is_empty", False) or (match["start"] > match["end"]):
                            if match_config.show_empty and match["start"] < len(all_rows):
                                empty_row = _process_empty_match(match["start"], all_rows, measures, match_num, partition_by)
                                if empty_row:
                                    results.append(empty_row)
                            continue
                        
                        # Process each matched row
                        # For PERMUTE patterns with alternations, only process matched variable indices
                        if (hasattr(matcher, 'dfa') and hasattr(matcher.dfa, 'metadata') and 
                            matcher.dfa.metadata.get('has_permute', False) and 
                            matcher.dfa.metadata.get('has_alternations', False)):
                            # Get only the matched indices for PERMUTE with alternations
                            matched_indices = []
                            for var, indices in match.get("variables", {}).items():
                                matched_indices.extend(indices)
                            indices_to_process = sorted(set(matched_indices))
                            logger.debug(f"PERMUTE with alternations: processing only matched indices {indices_to_process}")
                        else:
                            # Regular pattern: process all rows from start to end
                            indices_to_process = list(range(match["start"], match["end"] + 1))
                            logger.debug(f"Regular pattern: processing range {indices_to_process}")
                        
                        for idx in indices_to_process:
                            if idx >= len(all_rows):
                                continue
                                
                            # Create result row from original data
                            result = dict(all_rows[idx])
                            
                            # Create context for measure evaluation
                            context = RowContext()
                            context.rows = all_rows
                            
                            # CRITICAL FIX: For ALL ROWS PER MATCH, use different variable sets based on semantics
                            full_variables = match.get("variables", {})
                            
                            # Create timeline for PERMUTE pattern progression
                            timeline = []
                            for var_name, var_indices in full_variables.items():
                                for var_idx in var_indices:
                                    timeline.append((var_idx, var_name))
                            timeline.sort()  # Sort by row index to get chronological order
                            
                            # For PERMUTE patterns, create progressive variables (variables seen up to current row)
                            is_permute_pattern = "PERMUTE" in pattern_text  # Use the actual pattern text
                            if is_permute_pattern:
                                # For PERMUTE patterns, determine which variables are "visible" at current row
                                progressive_variables = {}
                                for timeline_idx, timeline_var in timeline:
                                    if timeline_idx <= idx:  # Only include variables matched up to current row
                                        if timeline_var not in progressive_variables:
                                            progressive_variables[timeline_var] = []
                                        # Include ALL indices for this variable (not just up to current row)
                                        progressive_variables[timeline_var] = full_variables[timeline_var]
                                
                                logger.debug(f"DEBUG: PERMUTE Row {idx} - Timeline: {timeline}, Progressive variables: {progressive_variables}")
                                context.variables = progressive_variables  # Use progressive variables for PERMUTE
                                context._progressive_variables = progressive_variables
                            else:
                                context.variables = full_variables  # Use full variables for non-PERMUTE patterns
                            
                            # For navigation function evaluation, provide both full and running contexts
                            context._full_match_variables = full_variables  # Always available for FINAL semantics
                            
                            # For RUNNING semantics evaluation, create running variables 
                            running_variables = {}
                            for var_name, var_indices in full_variables.items():
                                # Include only indices up to and including current row
                                running_indices = [i for i in var_indices if i <= idx]
                                if running_indices:
                                    running_variables[var_name] = running_indices
                            context._running_variables = running_variables  # Available for RUNNING semantics
                            context.match_number = match_num
                            context.current_idx = idx
                            context.subsets = subset_dict.copy() if subset_dict else {}
                            context._timeline = timeline  # Store timeline for reference
                            logger.debug(f"DEBUG: Row {idx} - Full variables: {full_variables}, Running variables: {running_variables}")
                            
                            # Create evaluator and process measures
                            evaluator = MeasureEvaluator(context, final=True)  # Use FINAL semantics by default per SQL:2016
                            for alias, expr in measures.items():
                                try:
                                    # SQL:2016 default: measures use FINAL semantics unless explicitly prefixed with RUNNING
                                    semantics = measure_semantics.get(alias, "FINAL")
                                    # Standard evaluation for all expressions - no special case handling
                                    result[alias] = evaluator.evaluate(expr, semantics)
                                    logger.debug(f"DEBUG: Set {alias}={result[alias]} for row {idx} with {semantics} semantics")
                                except Exception as e:
                                    logger.warning(f"Error evaluating measure {alias} for row {idx}: {e}")
                                    result[alias] = None
                            
                            # Add match metadata
                            result["MATCH_NUMBER"] = match_num
                            result["IS_EMPTY_MATCH"] = False
                            
                            results.append(result)
                    
                    # Handle unmatched rows for ALL ROWS PER MATCH WITH UNMATCHED ROWS
                    if match_config.include_unmatched:
                        unmatched_indices = set(range(len(all_rows))) - all_matched_indices
                        for idx in sorted(unmatched_indices):
                            if idx < len(all_rows):
                                unmatched_row = _handle_unmatched_row(all_rows[idx], measures, partition_by)
                                # Add the original row index for proper sorting
                                unmatched_row['_original_row_idx'] = idx
                                results.append(unmatched_row)
                
                # Create result DataFrame with preserved data types
                # Sort results by match number first, then by row order within each match
                # Add original index for stable sorting
                for i, result in enumerate(results):
                    result['_original_order'] = i
                
                # Safe sorting that handles None values properly
                def safe_sort_key(r):
                    # For WITH UNMATCHED ROWS, use original row index to maintain input order
                    if match_config.include_unmatched and '_original_row_idx' in r:
                        return (r.get('_original_row_idx', 0), 0)
                    
                    # PRODUCTION FIX: For partitioned queries, sort by partition order first, then by position within partition
                    # This ensures that all rows from partition 1 come before all rows from partition 2, etc.
                    if '_partition_index' in r and '_partition_row_index' in r:
                        partition_idx = r.get('_partition_index', 0)
                        partition_row_idx = r.get('_partition_row_index', 0)
                        logger.debug(f"Using partition sort key: partition_idx={partition_idx}, row_idx={partition_row_idx} for result: {r}")
                        return (partition_idx, partition_row_idx)
                    
                    # Otherwise, sort by match number then original order (legacy behavior)
                    match_num = r.get('match', r.get('MATCH_NUMBER', 0))
                    if match_num is None:
                        match_num = 0
                    original_order = r.get('_original_order', 0)
                    if original_order is None:
                        original_order = 0
                    return (match_num, original_order)
                
                sorted_results = sorted(results, key=safe_sort_key)
                
                # PRODUCTION FIX: Check if we used partition sorting before removing the tracking fields
                used_partition_sorting = partition_by and any(
                    ('_partition_index' in result and '_partition_row_index' in result) 
                    for result in sorted_results[:1] if sorted_results
                )
                
                # Remove the temporary ordering fields
                for result in sorted_results:
                    result.pop('_original_order', None)
                    result.pop('_partition_index', None)
                    result.pop('_partition_row_index', None)
                
                result_df = _create_dataframe_with_preserved_types(sorted_results)
                
                # Reset the DataFrame index to be sequential
                result_df.reset_index(drop=True, inplace=True)
                
                # Production-ready fix: Filter out unwanted columns early to prevent aliasing conflicts
                if ast.select_clause and ast.select_clause.items:
                    # Check if this is a SELECT * query
                    has_select_star = any(item.expression == '*' for item in ast.select_clause.items)
                    
                    if not has_select_star:
                        # For specific column selection, be selective about which columns to keep
                        needed_original_columns = set()
                        measure_expressions = set(measures.values()) if measures else set()
                        
                        for item in ast.select_clause.items:
                            expression = item.expression.split('.')[-1] if '.' in item.expression else item.expression
                            # Only include original data columns that are not covered by measures
                            if (expression not in measures and 
                                expression not in measure_expressions and 
                                expression not in ['MATCH_NUMBER()', 'CLASSIFIER()'] and
                                expression in result_df.columns):
                                needed_original_columns.add(expression)
                        
                        # Remove unwanted original data columns that would conflict with measures
                        columns_to_drop = []
                        for col in result_df.columns:
                            # Keep measure columns, metadata columns, and needed original columns
                            if (col in measures or 
                                col in ['MATCH_NUMBER', 'IS_EMPTY_MATCH', '_original_row_idx'] or
                                col in needed_original_columns):
                                continue
                            # Drop original data columns that aren't needed or would conflict
                            if col not in needed_original_columns:
                                columns_to_drop.append(col)
                        
                        if columns_to_drop:
                            result_df = result_df.drop(columns=columns_to_drop)
                            logger.debug(f"Dropped conflicting columns: {columns_to_drop}")
                    else:
                        # For SELECT *, keep all columns (both original and measures)
                        logger.debug("SELECT * detected - keeping all columns")
                
                # Debug the measure columns
                logger.debug("Checking measure columns in final DataFrame:")
                for alias in measures.keys():
                    if alias in result_df.columns:
                        logger.debug(f"  Measure '{alias}' exists with values: {result_df[alias].head(3).tolist()}")
                    else:
                        logger.debug(f"  Measure '{alias}' is MISSING from result DataFrame")
                
                # Ensure ALL measure columns are present (even if they weren't calculated)
                for alias in measures.keys():
                    if alias not in result_df.columns:
                        # Add missing measure column with default values (None or 0)
                        logger.warning(f"Adding missing measure column '{alias}' with default values")
                        
                        # Try to find values in the raw results first
                        values = []
                        for i, row in enumerate(sorted_results):
                            if alias in row and row[alias] is not None:
                                values.append(row[alias])
                            else:
                                # Use appropriate default based on the measure expression
                                measure_expr = measures[alias].expression.lower()
                                if 'count' in measure_expr:
                                    values.append(0)  # COUNT defaults to 0
                                elif 'sum' in measure_expr or 'coalesce' in measure_expr:
                                    values.append(0)  # SUM and COALESCE defaults to 0
                                else:
                                    values.append(None)  # Other measures default to None
                        
                        result_df[alias] = values
                        logger.info(f"  Added measure column '{alias}' with {len(values)} values")
                
                # Ensure measure columns are properly preserved
                for alias in measures.keys():
                    if alias in result_df.columns:
                        # Check if the column has all None values when it shouldn't
                        if result_df[alias].isna().all():
                            logger.warning(f"Measure column '{alias}' has all None values!")
                            
                            # Try to recover values from raw results if possible
                            for i, row in enumerate(sorted_results):
                                if alias in row and row[alias] is not None:
                                    result_df.at[i, alias] = row[alias]
                                    logger.info(f"  Fixed value at row {i}: {row[alias]}")
                
                # Handle empty result case
                if result_df.empty:
                    # Create empty DataFrame with appropriate columns from SELECT clause
                    columns = _get_empty_result_columns(ast, partition_by, measures)
                    metrics["result_processing_time"] = time.time() - processing_start
                    metrics["total_time"] = time.time() - start_time
                    return pd.DataFrame(columns=columns)
                
                # Define ordered columns - only SELECT clause columns for production-ready behavior
                ordered_cols = []
                
                # Handle SELECT clause columns and aliases - Production-ready column aliasing fix
                if ast.select_clause and ast.select_clause.items:
                    # Check if this is a SELECT * query
                    has_select_star = any(item.expression == '*' for item in ast.select_clause.items)
                    
                    # Initialize column alias map for all cases
                    column_alias_map = {}
                    
                    if has_select_star:
                        # For SELECT *, implement SQL:2016 column ordering:
                        # For ONE ROW PER MATCH: only MEASURES are included
                        # For ALL ROWS PER MATCH: include all table columns + pattern navigation columns
                        
                        if rows_per_match == RowsPerMatch.ONE_ROW:
                            # For ONE ROW PER MATCH with SELECT *, behavior depends on whether explicit MEASURES exist
                            logger.debug(f"ONE ROW PER MATCH with SELECT * - PARTITION BY: {partition_by}, ORDER BY: {order_by}, MEASURES: {list(measures.keys())}")
                            
                            if measures:
                                # For ONE ROW PER MATCH: PARTITION BY + MEASURES only (Trino behavior)
                                # ORDER BY and other original columns are excluded
                                # Add PARTITION BY columns first
                                if partition_by:
                                    for col in partition_by:
                                        if col in result_df.columns:
                                            ordered_cols.append(col)
                                
                                # Add MEASURES columns (ORDER BY and original columns excluded for ONE ROW PER MATCH)
                                for alias in measures.keys():
                                    if alias in result_df.columns and alias not in ordered_cols:
                                        ordered_cols.append(alias)
                            else:
                                # If NO explicit MEASURES: Include all input columns (standard behavior for SELECT *)
                                # Add PARTITION BY columns first to maintain SQL:2016 ordering
                                if partition_by:
                                    for col in partition_by:
                                        if col in result_df.columns:
                                            ordered_cols.append(col)
                                
                                # Add ORDER BY columns (if not already included)
                                if order_by:
                                    for col in order_by:
                                        if col in result_df.columns and col not in ordered_cols:
                                            ordered_cols.append(col)
                                
                                # Add all remaining input columns (excluding internal columns)
                                for col in result_df.columns:
                                    if (col not in ordered_cols and 
                                        not col.startswith('_') and  # Skip internal columns
                                        col not in ['MATCH_NUMBER']):  # Skip auto-generated measure columns
                                        ordered_cols.append(col)
                        else:
                            # For ALL ROWS PER MATCH, include all table columns + pattern navigation columns
                            # 1. PARTITION BY columns
                            # 2. ORDER BY columns  
                            # 3. MEASURES
                            # 4. Remaining input columns
                            
                            # Start with PARTITION BY columns
                            if partition_by:
                                for col in partition_by:
                                    if col in result_df.columns:
                                        ordered_cols.append(col)
                            
                            # Add ORDER BY columns (if not already included)
                            for col in order_by:
                                if col in result_df.columns and col not in ordered_cols:
                                    ordered_cols.append(col)
                            
                            # Add MEASURES (if not already included)
                            for alias in measures.keys():
                                if alias in result_df.columns and alias not in ordered_cols:
                                    ordered_cols.append(alias)
                            
                            # Add remaining input columns (if not already included)
                            for col in result_df.columns:
                                if (col not in ordered_cols and 
                                    col not in ['MATCH_NUMBER', 'IS_EMPTY_MATCH', '_original_row_idx']):
                                    ordered_cols.append(col)
                        
                        logger.debug(f"SELECT * - SQL:2016 column ordering: {ordered_cols}")
                    else:
                        # Create a mapping from expression to alias for proper column aliasing
                        select_columns = []
                        
                        for item in ast.select_clause.items:
                            expression = item.expression.split('.')[-1] if '.' in item.expression else item.expression
                            alias = item.alias if item.alias else expression
                            
                            # Track the mapping for renaming
                            if item.alias and expression != alias:
                                column_alias_map[expression] = alias
                            
                            # Add to select columns (use alias when available)
                            select_columns.append(alias)
                        
                        # Apply column aliasing to the result DataFrame
                        if column_alias_map:
                            # Create rename mapping for columns that exist in the DataFrame
                            rename_map = {}
                            for orig_col, new_col in column_alias_map.items():
                                if orig_col in result_df.columns:
                                    rename_map[orig_col] = new_col
                            
                            if rename_map:
                                result_df = result_df.rename(columns=rename_map)
                                logger.debug(f"Applied column aliases: {rename_map}")
                        
                        # Only include SELECT columns that exist after aliasing
                        for col in select_columns:
                            if col in result_df.columns:
                                ordered_cols.append(col)
                else:
                    # Fallback: if no SELECT clause, include partition, order, and measure columns
                    # First add partition columns
                    if partition_by:
                        ordered_cols.extend(partition_by)
                    
                    # Then add ordering columns if they're not already included
                    for col in order_by:
                        if col not in ordered_cols:
                            ordered_cols.append(col)
                    
                    # Then add measure columns
                    if mr_clause.measures:
                        ordered_cols.extend([m.alias for m in mr_clause.measures.measures if m.alias])
                
                # Only keep columns that exist in the result
                ordered_cols = [col for col in ordered_cols if col in result_df.columns]
                
                # Sort the results by match number first to maintain match grouping, then by partition and order columns
                sort_columns = []
                
                # Special handling for WITH UNMATCHED ROWS - sort by original row position
                if match_config.include_unmatched and '_original_row_idx' in result_df.columns:
                    sort_columns.append('_original_row_idx')
                    # For WITH UNMATCHED ROWS, we only sort by original row index to maintain input order
                    # Don't add additional sort columns that would break this ordering
                else:
                    # First sort by match number to keep matches grouped together
                    if 'match' in result_df.columns:
                        sort_columns.append('match')
                    elif 'MATCH_NUMBER' in result_df.columns:
                        sort_columns.append('MATCH_NUMBER')
                    
                    # Production-ready fix: Use renamed columns for sorting if they exist
                    # Apply column alias mapping to sort columns
                    partition_sort_cols = []
                    if partition_by:
                        for col in partition_by:
                            # Check if this column was renamed
                            if column_alias_map and col in column_alias_map:
                                aliased_col = column_alias_map[col]
                                if aliased_col in result_df.columns and aliased_col not in sort_columns:
                                    partition_sort_cols.append(aliased_col)
                            elif col in result_df.columns and col not in sort_columns:
                                partition_sort_cols.append(col)
                        sort_columns.extend(partition_sort_cols)
                    
                    # Apply the same logic to order_by columns
                    order_sort_cols = []
                    if order_by and not any('SKIP TO NEXT ROW' in query.upper() for _ in [1]):
                        for col in order_by:
                            # Check if this column was renamed
                            if column_alias_map and col in column_alias_map:
                                aliased_col = column_alias_map[col]
                                if aliased_col in result_df.columns and aliased_col not in sort_columns:
                                    order_sort_cols.append(aliased_col)
                            elif col in result_df.columns and col not in sort_columns:
                                order_sort_cols.append(col)
                        sort_columns.extend(order_sort_cols)
                
                logger.debug(f"Final sort decision: partition_by={bool(partition_by)}, used_partition_sorting={used_partition_sorting}, sort_columns={sort_columns}")
                
                # Only sort if we have valid columns AND haven't already done partition sorting
                if sort_columns and not used_partition_sorting:
                    # Filter out any columns that don't exist in the DataFrame
                    valid_sort_columns = [col for col in sort_columns if col in result_df.columns]
                    
                    if valid_sort_columns:
                        # Reset DataFrame index before final sort to ensure proper ordering
                        result_df.reset_index(drop=True, inplace=True)
                        result_df = result_df.sort_values(by=valid_sort_columns)
                        # Reset index again after sort
                        result_df.reset_index(drop=True, inplace=True)
                
                # Remove temporary sorting columns
                if '_original_row_idx' in result_df.columns:
                    result_df = result_df.drop('_original_row_idx', axis=1)
                
                # Apply outer ORDER BY clause if present
                if ast.order_by_clause and ast.order_by_clause.sort_items:
                    logger.debug(f"Applying outer ORDER BY clause: {ast.order_by_clause}")
                    logger.debug(f"Available result columns: {list(result_df.columns)}")
                    outer_sort_columns = []
                    for sort_item in ast.order_by_clause.sort_items:
                        column = sort_item.column
                        logger.debug(f"Checking outer ORDER BY column: '{column}'")
                        if column in result_df.columns:
                            outer_sort_columns.append(column)
                            logger.debug(f"Found column '{column}' in result, adding to sort columns")
                        else:
                            logger.warning(f"Outer ORDER BY column '{column}' not found in result columns: {list(result_df.columns)}")
                    
                    if outer_sort_columns:
                        # Determine sort order (ascending vs descending)
                        ascending_list = []
                        for sort_item in ast.order_by_clause.sort_items:
                            if sort_item.column in outer_sort_columns:
                                ascending_list.append(sort_item.ordering.upper() == 'ASC')
                        
                        logger.debug(f"Sorting final result by outer ORDER BY: columns={outer_sort_columns}, ascending={ascending_list}")
                        logger.debug(f"Before sorting: dataframe shape={result_df.shape}, columns={list(result_df.columns)}")
                        result_df = result_df.sort_values(by=outer_sort_columns, ascending=ascending_list)
                        result_df.reset_index(drop=True, inplace=True)
                        logger.debug(f"Before sorting: dataframe shape={result_df.shape}, columns={list(result_df.columns)}")
                    else:
                        logger.warning("No valid outer ORDER BY columns found")
                else:
                    logger.debug("No outer ORDER BY clause found")
                
                metrics["result_processing_time"] = time.time() - processing_start
                metrics["total_time"] = time.time() - start_time
                return result_df[ordered_cols]
        except Exception as e:
            raise RuntimeError(f"Error processing results: {str(e)}")
    
    except Exception as e:
        # Log the error with detailed information
        logger.error(f"Error executing MATCH_RECOGNIZE query: {str(e)}")
        logger.error(f"Query: {query}")
        logger.error(f"Metrics: {metrics}")
        # Re-raise the exception
        raise
    finally:
        # Always record total time
        metrics["total_time"] = time.time() - start_time
        logger.info(f"Query execution metrics: {metrics}")
        
        # Phase 2: Enhanced cache statistics reporting
        if caching_enabled:
            try:
                # Get comprehensive cache report
                cache_report = generate_comprehensive_cache_report()
                
                # Log detailed cache statistics
                cache_stats = cache_report['cache_statistics']
                logger.info(f"Smart Cache Performance Report:")
                logger.info(f"  Hit Rate: {cache_stats.get('hit_rate_percent', 0):.1f}%")
                logger.info(f"  Total Requests: {cache_stats.get('total_requests', 0)}")
                logger.info(f"  Cache Size: {cache_stats.get('size_mb', 0):.2f} MB / {cache_stats.get('max_size_mb', 0):.1f} MB")
                logger.info(f"  Entries: {cache_stats.get('entries_count', 0)}")
                logger.info(f"  Evictions: {cache_stats.get('evictions', 0)}")
                logger.info(f"  Policy: {cache_stats.get('eviction_policy', 'unknown')}")
                
                # Log performance impact
                performance_impact = cache_report['performance_impact']
                logger.info(f"  Estimated Time Saved: {performance_impact['estimated_time_saved_percent']:.1f}%")
                logger.info(f"  Memory Efficiency: {performance_impact['memory_efficiency']:.1f}%")
                
                # Log effectiveness rating and recommendations
                logger.info(f"  Cache Effectiveness: {cache_report['effectiveness_rating']}")
                if cache_report['recommendations']:
                    logger.info(f"  Recommendations: {'; '.join(cache_report['recommendations'])}")
                
                # Update cache metrics in global performance tracking
                metrics.update({
                    'smart_cache_hit_rate': cache_stats.get('hit_rate_percent', 0),
                    'smart_cache_size_mb': cache_stats.get('size_mb', 0),
                    'smart_cache_entries': cache_stats.get('entries_count', 0),
                    'smart_cache_effectiveness': cache_report['effectiveness_rating']
                })
                
            except Exception as cache_error:
                logger.warning(f"Failed to generate cache report: {cache_error}")
        
        # Enhanced smart cache statistics summary
        try:
            smart_cache_stats = get_smart_cache_stats()
            if smart_cache_stats.get('total_requests', 0) > 0:
                logger.info(f"Smart Cache Performance Summary:")
                logger.info(f"  Total Requests: {smart_cache_stats.get('total_requests', 0)}")
                logger.info(f"  Hit Rate: {smart_cache_stats.get('hit_rate_percent', 0):.1f}%")
                logger.info(f"  Memory Usage: {smart_cache_stats.get('size_mb', 0):.2f} MB / {smart_cache_stats.get('max_size_mb', 100):.1f} MB")
                logger.info(f"  Cache Entries: {smart_cache_stats.get('entries_count', 0)}")
                logger.info(f"  Evictions: {smart_cache_stats.get('eviction_count', 0)}")
                
                if smart_cache_stats.get('hit_rate_percent', 0) >= 80:
                    logger.info(f"  Status: Excellent cache performance")
                elif smart_cache_stats.get('hit_rate_percent', 0) >= 60:
                    logger.info(f"  Status: Good cache performance")
                else:
                    logger.info(f"  Status: Cache warming up")
        except Exception as e:
            logger.debug(f"Could not retrieve smart cache statistics: {e}")


def get_unmatched_rows(all_rows: List[Dict[str, Any]], matched_indices: Set[int]) -> List[int]:
    """
    Get indices of unmatched rows.
    
    Args:
        all_rows: List of all rows
        matched_indices: Set of indices of matched rows
        
    Returns:
        List of indices of unmatched rows
    """
    return [i for i in range(len(all_rows)) if i not in matched_indices]



def validate_navigation_bounds(match_data, define_conditions):
    """
    Validate that navigation functions don't reference out-of-bounds positions in PERMUTE patterns.

    Args:
        match_data: The match data dictionary
        define_conditions: Dictionary of variable definitions

    Returns:
        bool: True if navigation bounds are valid, False otherwise
    """
    # Get ordered list of variables in the match
    ordered_vars = list(match_data['variables'].keys())

    for var, condition in define_conditions.items():
        if var not in ordered_vars:
            continue

        var_idx = ordered_vars.index(var)

        # Check NEXT references
        if 'NEXT(' in condition:
            # Check if variable is last in sequence and references itself with NEXT
            if var_idx == len(ordered_vars) - 1 and f"NEXT({var}" in condition:
                return False

        # Check PREV references
        if 'PREV(' in condition:
            # Check if variable is first in sequence and references itself with PREV
            if var_idx == 0 and f"PREV({var}" in condition:
                return False

    # Check FIRST references
    if any('FIRST(' in cond for cond in define_conditions.values()):
        # Ensure referenced variables exist for FIRST(A.value) references
        for var, condition in define_conditions.items():
            if 'FIRST(' in condition:
                # Extract referenced variable
                ref_matches = re.findall(
                    r'FIRST\s*\(\s*([A-Za-z0-9_]+)\.', condition)
                for ref_var in ref_matches:
                    if ref_var not in match_data['variables']:
                        return False

    # Check LAST references
    if any('LAST(' in cond for cond in define_conditions.values()):
        # Ensure referenced variables exist for LAST(A.value) references
        for var, condition in define_conditions.items():
            if 'LAST(' in condition:
                # Extract referenced variable
                ref_matches = re.findall(
                    r'LAST\s*\(\s*([A-Za-z0-9_]+)\.', condition)
                for ref_var in ref_matches:
                    if ref_var not in match_data['variables']:
                        return False

    return True




def extract_navigation_references(condition):
    """Extract all navigation functions referenced in a condition"""
    pattern = r'(NEXT|PREV|FIRST|LAST)\s*\(\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)(?:\s*,\s*(\d+))?\s*\)'
    refs = []

    for match in re.finditer(pattern, condition):
        func_type = match.group(1)
        var_name = match.group(2)
        field = match.group(3)
        offset = int(match.group(4)) if match.group(4) else 1
        # Return only the fields needed for validation (type, var, step)
        refs.append((func_type, var_name, offset))

    return refs

def post_validate_permute_match(match: Dict[str, Any], define_conditions: Dict[str, str], pattern_text: str = None) -> bool:
    """
    Post-validate PERMUTE matches with navigation functions for Trino compatibility.
    
    Args:
        match: The match data dictionary
        define_conditions: Dictionary of variable definitions
        pattern_text: Optional pattern text for hierarchy analysis
        
    Returns:
        bool: True if the match is valid, False otherwise
    """
    # Skip empty matches
    if not match:
        return False
        
    # Improved empty match detection
    if match.get("is_empty", False) or (match["start"] > match["end"]):
        return False
        
    # Extract the sequence of variables in the match
    sequence = []
    try:
        for idx in range(match['start'], match['end'] + 1):
            for var, indices in match['variables'].items():
                if idx in indices:
                    sequence.append(var)
                    break
    except Exception as e:
        logger.warning(f"Error extracting variable sequence: {e}")
        return False
        
    # For nested PERMUTE patterns, validate the sequence structure
    if pattern_text and "PERMUTE" in pattern_text:
        # Check if this is a nested PERMUTE pattern like PERMUTE(A, PERMUTE(B, C))
        nested_match = re.search(r'PERMUTE\s*\(\s*([^,]+)\s*,\s*PERMUTE\s*\(\s*([^)]+)\s*\)\s*\)', pattern_text, re.IGNORECASE)
        if nested_match:
            outer_var = nested_match.group(1).strip()
            inner_vars_str = nested_match.group(2).strip()
            inner_vars = [v.strip() for v in inner_vars_str.split(',')]
            
            # For PERMUTE(A, PERMUTE(B, C)), valid sequences are:
            # A-B-C, A-C-B, B-C-A, C-B-A
            # Invalid sequences are: B-A-C, C-A-B
            
            # Check if inner variables are adjacent
            inner_positions = []
            for i, var in enumerate(sequence):
                if var in inner_vars:
                    inner_positions.append(i)
            
            # Inner variables must be adjacent (consecutive positions)
            if inner_positions and max(inner_positions) - min(inner_positions) + 1 != len(inner_positions):
                logger.info(f"Rejecting match with sequence {sequence}: inner variables {inner_vars} are not adjacent")
                return False
            
            # Check if outer variable is in the correct position
            outer_position = None
            for i, var in enumerate(sequence):
                if var == outer_var:
                    outer_position = i
                    break
            
            if outer_position is None:
                logger.info(f"Rejecting match with sequence {sequence}: outer variable {outer_var} not found")
                return False
            
            # Outer variable must be either before or after the inner variables block
            if inner_positions and outer_position != min(inner_positions) - 1 and outer_position != max(inner_positions) + 1:
                if not (outer_position == 0 or outer_position == len(sequence) - 1):
                    logger.info(f"Rejecting match with sequence {sequence}: outer variable {outer_var} is not adjacent to inner variables block")
                    return False
    
    # For non-nested PERMUTE patterns, all permutations are valid
    return True
def filter_lexicographically(all_matches, pattern_metadata, all_rows=None, partition_by=None):
    """
    Filter matches based on SQL standard lexicographical ordering rules for PERMUTE patterns.
    """
    # Skip filtering if not a PERMUTE pattern
    if not pattern_metadata.get('permute', False):
        return all_matches
        
    # Extract original variable order from pattern
    original_variables = []
    pattern_text = pattern_metadata.get('original', '')
    
    # For nested PERMUTE patterns, extract all variables in order
    if 'PERMUTE' in pattern_text:
        # Extract all variables from the pattern text
        # This regex finds all single-letter variables in the pattern
        var_matches = re.findall(r'([A-Za-z])(?:\s*,|\s*\))', pattern_text)
        original_variables = [v for v in var_matches if v]
        
        # If we couldn't extract variables, fall back to metadata
        if not original_variables:
            original_variables = pattern_metadata.get('base_variables', [])
    else:
        # For simple patterns, use base_variables from metadata
        original_variables = pattern_metadata.get('base_variables', [])
    
    # Create variable priority map (A=0, B=1, C=2, etc.)
    var_priority = {var: idx for idx, var in enumerate(original_variables)}
    
    # Group matches by partition
    partition_matches = {}
    for match in all_matches:
        # Extract partition key (could be multiple columns)
        partition_key = tuple()
        if all_rows and partition_by and match.get("start") is not None and match.get("start") < len(all_rows):
            start_row = all_rows[match["start"]]
            for col in partition_by:
                if col in start_row:
                    partition_key += (start_row[col],)
        else:
            # If we can't extract partition key, use match start index
            partition_key = (match.get("start", 0),)
        
        if partition_key not in partition_matches:
            partition_matches[partition_key] = []
        
        # Only add matches that pass the nested PERMUTE validation
        if post_validate_permute_match(match, {}, pattern_text):
            partition_matches[partition_key].append(match)
    
    # For each partition, keep only the lexicographically first match
    filtered_matches = []
    for partition_key, matches in partition_matches.items():
        if not matches:
            continue
        
        # Calculate lexicographical score for each match
        for match in matches:
            # Extract the sequence of variables in the match
            sequence = []
            for idx in range(match['start'], match['end'] + 1):
                for var, indices in match['variables'].items():
                    if idx in indices:
                        sequence.append(var)
                        break
            
            # Calculate score based on variable priority
            # Lower score means higher priority in lexicographical ordering
            score = 0
            for pos, var in enumerate(sequence):
                # Position weight increases for later positions
                weight = 10 ** (len(sequence) - pos - 1)
                # Variable priority (A=0, B=1, C=2, etc.)
                priority = var_priority.get(var, 999)
                score += priority * weight
            
            match["_lex_score"] = score
        
        # Keep only the match with lowest score (highest priority)
        best_match = min(matches, key=lambda m: m.get("_lex_score", 999))
        filtered_matches.append(best_match)
    
    # Sort filtered matches by partition key for consistent output
    filtered_matches.sort(key=lambda m: m.get("start", 0))
    return filtered_matches

def _get_empty_result_columns(ast, partition_by: List[str], measures: Dict[str, str]) -> List[str]:
    """
    Determine the correct columns for empty result DataFrames based on SELECT clause.
    
    This ensures that empty results have the same column structure as non-empty results,
    which is critical for SQL compatibility.
    """
    columns = []
    
    if ast.select_clause and ast.select_clause.items:
        # Check if this is a SELECT * query
        has_select_star = any(item.expression == '*' for item in ast.select_clause.items)
        
        if has_select_star:
            # For SELECT *, include partition columns, then measures, then any other relevant columns
            if partition_by:
                columns.extend(partition_by)
            if measures:
                columns.extend(measures.keys())
        else:
            # For specific SELECT columns, extract them from the SELECT clause
            for item in ast.select_clause.items:
                expression = item.expression.split('.')[-1] if '.' in item.expression else item.expression
                alias = item.alias if item.alias else expression
                columns.append(alias)
    else:
        # Fallback: if no SELECT clause, include partition and measure columns
        if partition_by:
            columns.extend(partition_by)
        if measures:
            columns.extend(measures.keys())
    
    return columns