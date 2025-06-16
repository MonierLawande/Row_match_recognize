# src/executor/match_recognize.py

import pandas as pd
import re
import time
import itertools
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
from src.utils.pattern_cache import (
    get_cache_key, get_cached_pattern, cache_pattern, CACHE_STATS,
    get_cache_stats, is_caching_enabled
)
from src.config.production_config import MatchRecognizeConfig

# Module logger
logger = get_logger(__name__)

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
        non_none_values = [v for v in values if v is not None]
        
        if has_none:
            # If column has None values, use object dtype to preserve them
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
    Process an empty match according to SQL standard, preserving original row data.
    
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
    
    # Create context for empty match
    context = RowContext()
    context.rows = rows
    context.variables = {}
    context.match_number = match_number
    context.current_idx = start_idx
    
    # Set all measures to NULL values
    for alias, expr in measures.items():
        # Special handling for MATCH_NUMBER()
        if expr.upper() == "MATCH_NUMBER()":
            result[alias] = match_number
        else:
            # All other measures are NULL for empty matches
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
        measure_semantics = {}
        
        if mr_clause.measures:
            for m in mr_clause.measures.measures:
                expr = m.expression
                alias = m.alias if m.alias else expr
                
                # Determine semantics based on measure type and rows_per_match
                if m.is_classifier:
                    measures[alias] = expr
                    measure_semantics[alias] = "FINAL" if rows_per_match == RowsPerMatch.ONE_ROW else "RUNNING"
                elif expr.upper() == "MATCH_NUMBER()":
                    measures[alias] = "MATCH_NUMBER()"
                    measure_semantics[alias] = "FINAL" if rows_per_match == RowsPerMatch.ONE_ROW else "RUNNING"
                else:
                    # Handle explicit semantics prefixes
                    if expr.upper().startswith("RUNNING "):
                        measures[alias] = expr[8:].strip()
                        measure_semantics[alias] = "RUNNING"
                    elif expr.upper().startswith("FINAL "):
                        measures[alias] = expr[6:].strip()
                        measure_semantics[alias] = "FINAL"
                    elif m.metadata and 'semantics' in m.metadata:
                        measures[alias] = expr
                        measure_semantics[alias] = m.metadata['semantics']
                    else:
                        # Default semantics based on rows_per_match
                        measures[alias] = expr
                        measure_semantics[alias] = "RUNNING" if rows_per_match != RowsPerMatch.ONE_ROW else "FINAL"
        
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
        
        # Try to load configuration
        try:
            app_config = MatchRecognizeConfig.from_env()
            caching_enabled = app_config.performance.enable_caching
        except Exception:
            caching_enabled = is_caching_enabled()
        
        # Generate cache key using centralized utility
        cache_key = get_cache_key(pattern_text, define, subset_dict)
        
        try:
            # Try to get compiled pattern from cache first
            cached_pattern = get_cached_pattern(cache_key) if caching_enabled else None
            if cached_pattern:
                # Cache hit - use cached DFA and NFA
                dfa, nfa, cached_time = cached_pattern
                logger.info(f"Pattern compilation cache HIT for pattern: {pattern_text}")
                
                # Log cache statistics for monitoring
                cache_stats = get_cache_stats()
                logger.debug(f"Cache efficiency: {cache_stats.get('cache_efficiency', 0):.2f}%, "
                           f"Memory used: {cache_stats.get('memory_used_mb', 0):.2f} MB, "
                           f"Cache size: {cache_stats.get('size', 0)}/{cache_stats.get('max_size', 0)}")
                
                # Create matcher with cached automata
                matcher = EnhancedMatcher(
                    dfa=dfa,
                    measures=measures,
                    measure_semantics=measure_semantics,
                    exclusion_ranges=nfa.exclusion_ranges,
                    after_match_skip=skip_mode,
                    subsets=subset_dict,
                    original_pattern=pattern_text
                )
            else:
                # Cache miss - compile pattern and cache the result
                logger.info(f"Pattern compilation cache MISS for pattern: {pattern_text}")
                compilation_start = time.time()
                
                # Build pattern matching automata
                pattern_tokens = tokenize_pattern(pattern_text)
                nfa_builder = NFABuilder()
                nfa = nfa_builder.build(pattern_tokens, define, subset_dict)
                dfa_builder = DFABuilder(nfa)
                dfa = dfa_builder.build()
                
                compilation_time = time.time() - compilation_start
                
                # Cache the compiled pattern using centralized utility if caching is enabled
                if caching_enabled:
                    cache_pattern(cache_key, dfa, nfa, compilation_time)
                    
                    # Log cache statistics for monitoring
                    cache_stats = get_cache_stats()
                    logger.debug(f"Cache size after adding new pattern: {cache_stats.get('size', 0)}")
                
                # Create matcher with newly compiled automata
                matcher = EnhancedMatcher(
                    dfa=dfa,
                    measures=measures,
                    measure_semantics=measure_semantics,
                    exclusion_ranges=nfa.exclusion_ranges,
                    after_match_skip=skip_mode,
                    subsets=subset_dict,
                    original_pattern=pattern_text
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
            
            # Create partitions
            partitions = [group for _, group in df.groupby(partition_by, sort=False)] if partition_by else [df]
            metrics["partition_count"] = len(partitions)
            
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
                
                results.extend(partition_results)
            
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
        except Exception as e:
            raise RuntimeError(f"Error during pattern matching: {str(e)}")
        metrics["matching_time"] = time.time() - matching_start
        
        # --- PROCESS RESULTS ---
        
        processing_start = time.time()
        try:
            # Handle empty results case
            if not results and not all_matches:
                # Create empty DataFrame with appropriate columns
                columns = []
                columns.extend(partition_by)
                if measures:
                    columns.extend(measures.keys())
                metrics["result_processing_time"] = time.time() - processing_start
                metrics["total_time"] = time.time() - start_time
                return pd.DataFrame(columns=columns)
            
            # Handle ONE ROW PER MATCH mode
            if rows_per_match == RowsPerMatch.ONE_ROW:
                # Create a list to hold the final result rows
                final_results = []
                
                # Process each match
                for match in all_matches:
                    match_num = match.get("match_number")
                    
                    # Handle empty match case
                    if match.get("is_empty", False) or (match["start"] > match["end"]):
                        if match["start"] < len(all_rows):
                            empty_row = _process_empty_match(match["start"], all_rows, measures, match_num, partition_by)
                            if empty_row:
                                final_results.append(empty_row)
                        continue
                    
                    # Create a new result row
                    result_row = {}
                    
                    # Add partition columns
                    if match["start"] < len(all_rows):
                        start_row = all_rows[match["start"]]
                        for col in partition_by:
                            if col in start_row:
                                result_row[col] = start_row[col]
                    
                    # Create context for measure evaluation
                    context = RowContext()
                    context.rows = all_rows
                    context.variables = match.get("variables", {})
                    context.match_number = match_num
                    context.current_idx = match["end"]  # Use the last row for FINAL semantics
                    context.subsets = subset_dict.copy() if subset_dict else {}
                    
                    # Set pattern_variables for PERMUTE patterns
                    if isinstance(pattern_text, str) and 'PERMUTE' in pattern_text:
                        permute_match = re.search(r'PERMUTE\s*\(\s*([^)]+)\s*\)', pattern_text, re.IGNORECASE)
                        if permute_match:
                            context.pattern_variables = [v.strip() for v in permute_match.group(1).split(',')]
                    elif hasattr(mr_clause.pattern, 'metadata'):
                        context.pattern_variables = mr_clause.pattern.metadata.get('base_variables', [])
                    
                    # Create evaluator and process measures
                    evaluator = MeasureEvaluator(context, final=True)
                    for alias, expr in measures.items():
                        try:
                            semantics = measure_semantics.get(alias, "FINAL")
                            result_row[alias] = evaluator.evaluate(expr, semantics)
                            logger.debug(f"Setting {alias} to {result_row[alias]} from evaluator")
                        except Exception as e:
                            logger.warning(f"Error evaluating measure {alias}: {e}")
                            result_row[alias] = None
                    
                    final_results.append(result_row)
                
                # Create DataFrame with the final results
                result_df = pd.DataFrame(final_results)
                
                # Handle empty result case
                if result_df.empty:
                    # Create empty DataFrame with appropriate columns
                    columns = []
                    columns.extend(partition_by)
                    if measures:
                        columns.extend(measures.keys())
                    metrics["result_processing_time"] = time.time() - processing_start
                    metrics["total_time"] = time.time() - start_time
                    return pd.DataFrame(columns=columns)
                
                # Ensure columns are in the correct order
                ordered_cols = []
                ordered_cols.extend(partition_by)  # Partition columns first
                if mr_clause.measures:
                    ordered_cols.extend([m.alias for m in mr_clause.measures.measures if m.alias])
                
                # Include columns specified in the SELECT clause
                if ast.select_clause and ast.select_clause.items:
                    select_items = [item.expression.split('.')[-1] if '.' in item.expression else item.expression 
                                   for item in ast.select_clause.items]
                    for col in select_items:
                        if col not in ordered_cols and col in result_df.columns:
                            ordered_cols.append(col)
                
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
                        for idx in range(match["start"], match["end"] + 1):
                            if idx >= len(all_rows):
                                continue
                                
                            # Create result row from original data
                            result = dict(all_rows[idx])
                            
                            # Create context for measure evaluation
                            context = RowContext()
                            context.rows = all_rows
                            context.variables = match.get("variables", {})
                            context.match_number = match_num
                            context.current_idx = idx
                            context.subsets = subset_dict.copy() if subset_dict else {}
                            
                            # Create evaluator and process measures
                            evaluator = MeasureEvaluator(context, final=False)  # RUNNING semantics
                            for alias, expr in measures.items():
                                try:
                                    semantics = measure_semantics.get(alias, "RUNNING")
                                    # Standard evaluation for all expressions - no special case handling
                                    result[alias] = evaluator.evaluate(expr, semantics)
                                    logger.debug(f"DEBUG: Set {alias}={result[alias]} for row {idx}")
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
                    
                    # Otherwise, sort by match number then original order
                    match_num = r.get('match', r.get('MATCH_NUMBER', 0))
                    if match_num is None:
                        match_num = 0
                    original_order = r.get('_original_order', 0)
                    if original_order is None:
                        original_order = 0
                    return (match_num, original_order)
                
                sorted_results = sorted(results, key=safe_sort_key)
                
                # Remove the temporary ordering field
                for result in sorted_results:
                    result.pop('_original_order', None)
                
                result_df = _create_dataframe_with_preserved_types(sorted_results)
                
                # Reset the DataFrame index to be sequential
                result_df.reset_index(drop=True, inplace=True)
                
                # Debug the measure columns
                logger.debug("Checking measure columns in final DataFrame:")
                for alias in measures.keys():
                    if alias in result_df.columns:
                        logger.debug(f"  Measure '{alias}' exists with values: {result_df[alias].head(3).tolist()}")
                    else:
                        logger.debug(f"  Measure '{alias}' is MISSING from result DataFrame")
                
                # Ensure measure columns are properly preserved
                for alias in measures.keys():
                    if alias in result_df.columns:
                        # Check if the column has all None values when it shouldn't
                        if result_df[alias].isna().all():
                            logger.warning(f"Measure column '{alias}' has all None values!")
                            
                            # Try to recover values from raw results if possible
                            for i, row in enumerate(results):
                                if alias in row and row[alias] is not None:
                                    result_df.at[i, alias] = row[alias]
                                    logger.info(f"  Fixed value at row {i}: {row[alias]}")
                
                # Handle empty result case
                if result_df.empty:
                    # Create empty DataFrame with appropriate columns
                    columns = []
                    columns.extend(partition_by)
                    if measures:
                        columns.extend(measures.keys())
                    metrics["result_processing_time"] = time.time() - processing_start
                    metrics["total_time"] = time.time() - start_time
                    return pd.DataFrame(columns=columns)
                
                # Define ordered columns - match Trino's output format
                ordered_cols = []
                
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
                
                # Only include columns specified in the SELECT clause
                if ast.select_clause and ast.select_clause.items:
                    select_items = [item.expression.split('.')[-1] if '.' in item.expression else item.expression 
                                   for item in ast.select_clause.items]
                    for col in select_items:
                        if col not in ordered_cols and col in result_df.columns:
                            ordered_cols.append(col)
                
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
                    
                    # Then add partition columns
                    if partition_by:
                        sort_columns.extend([col for col in partition_by if col not in sort_columns])
                    
                    # Then add order columns, but only if they don't break match grouping
                    # For SKIP TO NEXT ROW, we want to maintain match order, not reorder by id within matches
                    if order_by and not any('SKIP TO NEXT ROW' in query.upper() for _ in [1]):
                        sort_columns.extend([col for col in order_by if col not in sort_columns])
                
                if sort_columns:
                    # Reset DataFrame index before final sort to ensure proper ordering
                    result_df.reset_index(drop=True, inplace=True)
                    result_df = result_df.sort_values(by=sort_columns)
                    # Reset index again after sort
                    result_df.reset_index(drop=True, inplace=True)
                
                # Remove temporary sorting columns
                if '_original_row_idx' in result_df.columns:
                    result_df = result_df.drop('_original_row_idx', axis=1)
                
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
        
        # Display cache statistics
        total_requests = CACHE_STATS['hits'] + CACHE_STATS['misses']
        cache_stats = {
            'total_hits': CACHE_STATS['hits'],
            'total_misses': CACHE_STATS['misses'], 
            'total_compilation_time_saved': CACHE_STATS['compilation_time_saved'],
            'memory_used_mb': CACHE_STATS['memory_used_mb']
        }
        logger.info(f"Pattern cache statistics: {cache_stats}")
        
        # Calculate cache effectiveness
        if total_requests > 0:
            hit_rate = (CACHE_STATS['hits'] / total_requests) * 100
            logger.info(f"Cache hit rate: {hit_rate:.1f}% ({CACHE_STATS['hits']}/{total_requests})")
            
            if CACHE_STATS['compilation_time_saved'] > 0:
                logger.info(f"Compilation time saved: {CACHE_STATS['compilation_time_saved']:.3f}s")
        
        # Display memory usage
        if cache_stats['memory_used_mb'] > 0:
            memory_mb = cache_stats['memory_used_mb']
            logger.info(f"Cache memory usage: {memory_mb:.2f} MB")


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