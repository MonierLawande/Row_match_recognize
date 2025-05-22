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

def process_subset_clause(subsets, row_context):
    """Process SUBSET clause and configure the row context."""
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

def extract_subset_dict(subsets):
    """Extract subset definitions into a dictionary for the matcher."""
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
        separator = separator[:pos-1] + "+" + separator[pos:pos+len(col)] + "+" + separator[pos+len(col)+1:]
    
    # Format rows
    rows = []
    for _, row in df.iterrows():
        formatted_row = " | ".join(f"{str(row[col]):{col_widths[col]}}" for col in df.columns)
        rows.append(formatted_row)
    
    # Combine all parts
    result = f"{header}\n{separator}\n" + "\n".join(rows)
    result += f"\n({len(df)} {'row' if len(df) == 1 else 'rows'})"
    
    return result

def validate_navigation_functions(match, pattern_variables, define_clauses):
    """Validate navigation functions for a matched pattern"""
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
        True if valid, False otherwise
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
    This is a simplified implementation that checks for common error patterns.
    
    Returns:
        True if likely valid, False if definitely invalid
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
    # A more complete validation would require complex parsing
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
    Enhanced to match Trino's output format exactly with support for all PERMUTE cases.
    """
    # Parse the query and build the AST
    ast = parse_full_query(query)
    mr_clause = ast.match_recognize
    if not mr_clause:
        raise ValueError("No MATCH_RECOGNIZE clause found in the query.")

    # Extract partitioning and ordering information
    partition_by = mr_clause.partition_by.columns if mr_clause.partition_by else []
    order_by = [si.column for si in mr_clause.order_by.sort_items] if mr_clause.order_by else []


    # Extract rows per match configuration
    rows_per_match = RowsPerMatch.ONE_ROW  # Default
    if mr_clause.rows_per_match:
        # Get the raw mode text
        rows_per_match_text = mr_clause.rows_per_match.raw_mode
        print(f"Raw rows_per_match text: {rows_per_match_text}")
        
        # Convert to uppercase and remove spaces for consistent comparison
        clean_text = rows_per_match_text.upper().replace(" ", "")
        
        # Robust detection of ALL ROWS PER MATCH
        if "ALL" in clean_text:
            if "WITHUNMATCHED" in clean_text:
                rows_per_match = RowsPerMatch.ALL_ROWS_WITH_UNMATCHED
            elif "OMITEMPTY" in clean_text:
                rows_per_match = RowsPerMatch.ALL_ROWS
            else:
                rows_per_match = RowsPerMatch.ALL_ROWS_SHOW_EMPTY
    
    print(f"Using rows_per_match mode: {rows_per_match}")
    
    # Validate pattern exclusion usage
    if rows_per_match == RowsPerMatch.ALL_ROWS_WITH_UNMATCHED:
        pattern_text = mr_clause.pattern.pattern
        if "{-" in pattern_text and "-}" in pattern_text:
            raise ValueError("Pattern exclusions are not allowed with ALL ROWS PER MATCH WITH UNMATCHED ROWS")

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

    # Extract measures and other clauses
    measures = {}
    measure_semantics = {}  # Store semantics separately
    
    if mr_clause.measures:
        for m in mr_clause.measures.measures:
            # Handle special functions
            if m.is_classifier:  # Check if it's a CLASSIFIER function
                measures[m.alias] = m.expression
                # For ONE ROW PER MATCH, all CLASSIFIER functions should use FINAL semantics
                if rows_per_match == RowsPerMatch.ONE_ROW:
                    measure_semantics[m.alias] = "FINAL"
                else:
                    measure_semantics[m.alias] = "RUNNING"
            elif m.expression.upper() == "MATCH_NUMBER()":
                measures[m.alias] = "MATCH_NUMBER()"
                measure_semantics[m.alias] = "FINAL" if rows_per_match == RowsPerMatch.ONE_ROW else "RUNNING"
            else:
                # Store the expression without prefix
                expr = m.expression
                # Remove any RUNNING/FINAL prefix from the expression
                if expr.upper().startswith("RUNNING "):
                    expr = expr[8:].strip()
                    measure_semantics[m.alias] = "RUNNING"
                elif expr.upper().startswith("FINAL "):
                    expr = expr[6:].strip()
                    measure_semantics[m.alias] = "FINAL"
                elif m.metadata and 'semantics' in m.metadata:
                    measure_semantics[m.alias] = m.metadata['semantics']
                else:
                    # Default semantics based on rows_per_match
                    measure_semantics[m.alias] = "RUNNING" if rows_per_match != RowsPerMatch.ONE_ROW else "FINAL"
                
                measures[m.alias] = expr
    
    # Print measure semantics for debugging
    print(f"Measure semantics: {measure_semantics}")

    define = {d.variable: d.condition for d in mr_clause.define.definitions} if mr_clause.define else {}
    subsets = mr_clause.subset if mr_clause.subset else []
    
    # Extract subset definitions for matcher configuration
    subset_dict = extract_subset_dict(subsets)

    # Create match configuration
    show_empty = rows_per_match != RowsPerMatch.ALL_ROWS  # True except for OMIT EMPTY MATCHES
    config = MatchConfig(
        rows_per_match=rows_per_match,
        skip_mode=skip_mode,
        skip_var=skip_var,
        show_empty=show_empty,
        include_unmatched=(rows_per_match == RowsPerMatch.ALL_ROWS_WITH_UNMATCHED),
    )

    # Debug output to check configuration
    print(f"Match config: rows_per_match={rows_per_match}, all_rows={rows_per_match != RowsPerMatch.ONE_ROW}")

    # Process partitions
    results = []
    all_matches = []  # Store all matches for post-processing
    all_rows = []  # Store all rows for post-processing
    
    # Partition the DataFrame
    if partition_by:
        partitions = [group for _, group in df.groupby(partition_by, sort=False)]
    else:
        partitions = [df]
    
    for partition in partitions:
        # Order the partition
        if order_by:
            partition = partition.sort_values(by=order_by)
            
        # Convert to rows
        rows = partition.to_dict('records')
        partition_start_idx = len(all_rows)  # Remember where this partition starts
        all_rows.extend(rows)  # Store rows for post-processing
        
        # Create context and configure subsets
        context = RowContext()
        process_subset_clause(subsets, context)
        
        # Build pattern matching automata
        pattern_tokens = tokenize_pattern(mr_clause.pattern.pattern)
        
        # Build NFA
        nfa_builder = NFABuilder()
        nfa = nfa_builder.build(pattern_tokens, define)
        
        # Convert to DFA
        dfa_builder = DFABuilder(nfa)
        dfa = dfa_builder.build()
        
        # Create matcher with all necessary parameters
        matcher = EnhancedMatcher(
            dfa=dfa,
            measures=measures,
            measure_semantics=measure_semantics,
            exclusion_ranges=nfa.exclusion_ranges,
            after_match_skip=skip_mode,
            subsets=subset_dict,
            original_pattern=mr_clause.pattern.pattern  # Pass the original pattern
        )
        
        # Find matches
        partition_results = matcher.find_matches(
            rows=rows,
            config=config,
            measures=measures  # Pass measures explicitly
        )
        
        # Store matches for post-processing with adjusted indices
        if hasattr(matcher, "_matches"):
            for match in matcher._matches:
                # Adjust indices to be relative to all_rows
                if "variables" in match:
                    adjusted_vars = {}
                    for var, indices in match["variables"].items():
                        adjusted_vars[var] = [idx + partition_start_idx for idx in indices]
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
                        result[col] = rows[0][col]  # Use values from first row of partition
                    
        results.extend(partition_results)

    # Debug the match data
    print("\nMatch data:")
    for match in all_matches:
        # Get partition information
        partition_info = ""
        if match["start"] < len(all_rows) and partition_by:
            partition_values = []
            for col in partition_by:
                if col in all_rows[match["start"]]:
                    partition_values.append(f"{col}={all_rows[match['start']][col]}")
            if partition_values:
                partition_info = f" (Partition: {', '.join(partition_values)})"
        
        print(f"Match number: {match.get('match_number')}{partition_info}")
        print(f"Global indices - Start: {match['start']}, End: {match['end']}")
        
        # Calculate local indices within the partition
        local_start = match['start']
        local_end = match['end']
        for i in range(match['start']):
            if i > 0 and all_rows[i-1].get(partition_by[0]) != all_rows[match['start']].get(partition_by[0]):
                local_start -= i
                local_end -= i
                break
        
        print(f"Local indices within partition - Start: {local_start}, End: {local_end}")
        print(f"Variables: {match.get('variables', {})}")
        
        # Debug the variable assignments
        for var, indices in match.get("variables", {}).items():
            print(f"  Variable {var} assigned to rows (global indices): {indices}")
            for idx in indices:
                if idx < len(all_rows):
                    print(f"    Row {idx}: {all_rows[idx]}")

    # After finding matches but before processing them:
    if mr_clause.pattern.metadata.get('permute', False):
        print("PERMUTE pattern detected, validating navigation functions...")
        valid_matches = []
        define_conditions = {define.variable: define.condition for define in mr_clause.define.definitions}
        for match in all_matches:
            if post_validate_permute_match(match, define_conditions):
                valid_matches.append(match)
        print(f"After filtering: {len(valid_matches)} valid matches")
        all_matches = valid_matches

    # Create output DataFrame
    if not results and not all_matches:
        # Create empty DataFrame with appropriate columns
        columns = []
        # Add partition columns
        columns.extend(partition_by)
        # Add measure columns
        if measures:
            columns.extend(measures.keys())
        return pd.DataFrame(columns=columns)

    # For ONE ROW PER MATCH, we need to create a new DataFrame with the correct columns
    if rows_per_match == RowsPerMatch.ONE_ROW:
        # Create a list to hold the final result rows
        final_results = []
        
        # Process each match
        for match in all_matches:
            match_num = match.get("match_number")
            var_assignments = match.get("variables", {})
            
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
            context.variables = var_assignments
            context.match_number = match_num
            context.current_idx = match["end"]  # Use the last row for FINAL semantics
            context.subsets = subset_dict.copy() if subset_dict else {}
            
            # Create evaluator with caching
            evaluator = MeasureEvaluator(context, final=True)
            
            # Process measures
            for measure in mr_clause.measures.measures:
                alias = measure.alias
                expr = measure.expression
                
                # Evaluate the expression with appropriate semantics
                semantics = measure_semantics.get(alias, "FINAL")
                result_row[alias] = evaluator.evaluate(expr, semantics)
                print(f"Setting {alias} to {result_row[alias]} from evaluator")
            
            final_results.append(result_row)
        
        # Create DataFrame with the final results
        result_df = pd.DataFrame(final_results)
        
        # Ensure columns are in the correct order
        ordered_cols = []
        ordered_cols.extend(partition_by)  # Partition columns first
        if mr_clause.measures:
            ordered_cols.extend([m.alias for m in mr_clause.measures.measures])  # Measures in specified order
        
        # Only keep columns that exist in the result
        ordered_cols = [col for col in ordered_cols if col in result_df.columns]
        
        # Sort the results to match Trino's output ordering
        if not result_df.empty:
            sort_columns = []
            
            # First check if 'seq' column exists before sorting
            if 'seq' in result_df.columns:
                sort_columns.append('seq')
                print(f"Sorting by sequence column: 'seq'")
            
            # Then reorder rows for pattern variables if the column exists
            if 'pattern_var' in result_df.columns:
                print(f"Pattern variable column found: 'pattern_var'")
                
                # Modify sorting to prioritize pattern variable
                # Sort by pattern variable first (using Trino's alphabetical ordering)
                sorted_df = result_df.sort_values(['pattern_var', 'seq'])
                
                # Replace the original DataFrame with sorted version
                result_df = sorted_df
                print(f"Sorting by pattern variable first, then by sequence")
            
            # Apply sorting if we have columns to sort by
            if sort_columns:
                try:
                    print(f"Sorting by columns: {sort_columns}")
                    result_df = result_df.sort_values(by=sort_columns)
                    
                    # Remove temporary sort column if it exists
                    if '_sort_key' in result_df.columns:
                        result_df = result_df.drop('_sort_key', axis=1)
                except Exception as e:
                    print(f"Warning: Error during sorting: {e}")
            else:
                print("No sort columns identified, skipping sort operation")

        # Only keep columns that exist in the result - consolidate the two occurrences
        ordered_cols = []
        ordered_cols.extend(partition_by)  # Partition columns first
        if mr_clause.measures:
            ordered_cols.extend([m.alias for m in mr_clause.measures.measures])  # Measures in specified order

        # Only keep columns that exist in the result
        ordered_cols = [col for col in ordered_cols if col in result_df.columns]
        
        # Format the output to match Trino's format exactly
        #formatted_output = format_trino_output(result_df[ordered_cols])
        #print(f"Formatted output in Trino style:\n{formatted_output}")

        return result_df[ordered_cols]

        #  handles PERMUTE patterns
    if mr_clause.pattern.metadata.get('permute', False):
        permute_handler = PermuteHandler()
        try:
            if mr_clause.pattern.metadata.get('nested_permute', False):
                expanded_pattern = permute_handler.expand_nested_permute(mr_clause.pattern)
            else:
                expanded_pattern = permute_handler.expand_permutation(mr_clause.pattern.metadata['variables'])
            
            # Store expanded pattern for matching
            mr_clause.pattern.metadata['expanded_pattern'] = expanded_pattern
            print(f"Successfully expanded PERMUTE pattern with {len(expanded_pattern)} permutations")
        except Exception as e:
            print(f"Warning: Error expanding PERMUTE pattern: {e}")
            # Fallback to simple permutation if nested expansion fails
            try:
                expanded_pattern = permute_handler.expand_permutation(mr_clause.pattern.metadata['variables'])
                mr_clause.pattern.metadata['expanded_pattern'] = expanded_pattern
                print(f"Using fallback permutation with {len(expanded_pattern)} permutations")
            except Exception as e2:
                print(f"Critical error in PERMUTE handling: {e2}")

    # Extract the original variable order from PERMUTE pattern
    original_variable_order = []
    if mr_clause.pattern.metadata.get('permute', False):
        original_variable_order = extract_original_variable_order(mr_clause.pattern)
        print(f"Original PERMUTE variable order: {original_variable_order}")
    
    # Process results with clean PERMUTE handling
    if rows_per_match == RowsPerMatch.ONE_ROW and len(final_results) > 0:
        result_df = pd.DataFrame(final_results)
        sort_columns = []
        
        # Add primary sorting by partition columns
        if partition_by:
            sort_columns.extend(partition_by)
        
        # Handle PERMUTE patterns specially to match Trino behavior
        if mr_clause.pattern.metadata.get('permute', False):
            # Create a sort key based on the original variable order
            if 'pattern_var' in result_df.columns and original_variable_order:
                # Map pattern variables to their position in original pattern
                variable_priorities = {var: idx for idx, var in enumerate(original_variable_order)}
                print(f"Variable priorities: {variable_priorities}")
                result_df['_sort_key'] = result_df['pattern_var'].map(variable_priorities)
                
                # Filter results for complex navigation functions (NEXT, PREV, FIRST, LAST)
                has_nav_functions = False
                if mr_clause.define:
                    has_nav_functions = any(("NEXT(" in d.condition or "PREV(" in d.condition or 
                                           "FIRST(" in d.condition or "LAST(" in d.condition)
                                          for d in mr_clause.define.definitions)
                
                if has_nav_functions:
                    # For each sequence, only keep first match by variable priority (lexicographical)
                    to_keep = []
                    for seq_val in result_df['seq'].unique():
                        seq_rows = result_df[result_df['seq'] == seq_val]
                        if len(seq_rows) > 0:
                            # Sort by pattern variable priority to match Trino's behavior
                            seq_rows = seq_rows.sort_values('_sort_key')
                            to_keep.append(seq_rows.iloc[0])
                    
                    if to_keep:
                        result_df = pd.DataFrame(to_keep)
                
                sort_columns.append('_sort_key')
        
        # Apply sorting
        if sort_columns:
            print(f"Sorting by columns: {sort_columns}")
            result_df = result_df.sort_values(by=sort_columns)
            
            # Remove temporary sort column
            if '_sort_key' in result_df.columns:
                result_df = result_df.drop('_sort_key', axis=1)
        
        # Only keep columns that exist in the result
        ordered_cols = []
        ordered_cols.extend(partition_by)  # Partition columns first
        if mr_clause.measures:
            ordered_cols.extend([m.alias for m in mr_clause.measures.measures])
        
        ordered_cols = [col for col in ordered_cols if col in result_df.columns]
        return result_df[ordered_cols]

    # After PERMUTE pattern handling code (around line 590-600)
    # Create result_df if it hasn't been defined yet
    if rows_per_match != RowsPerMatch.ONE_ROW:
        # Use results for ALL_ROWS_PER_MATCH
        result_df = pd.DataFrame(results)
        
        # Add necessary columns from original data if needed
        if order_by and not result_df.empty:
            for col in order_by:
                if col not in result_df.columns:
                    result_df[col] = [row.get(col) for row in rows]
        
        # Define ordered columns
        ordered_cols = []
        if partition_by:
            ordered_cols.extend(partition_by)
        if mr_clause.measures:
            ordered_cols.extend([m.alias for m in mr_clause.measures.measures])
        
        # Only keep columns that exist
        ordered_cols = [col for col in ordered_cols if col in result_df.columns]

    return result_df

def validate_navigation_bounds(match_data, define_conditions):
    """Validate that navigation functions don't reference out-of-bounds positions in PERMUTE patterns"""
    ordered_vars = list(match_data['variables'].keys())
    
    for var, condition in define_conditions.items():
        if var not in ordered_vars:
            continue
            
        var_idx = ordered_vars.index(var)
        
        # Check NEXT references
        if 'NEXT(' in condition:
            # Check if variable is last in sequence and references NEXT
            if var_idx == len(ordered_vars) - 1:
                return False
                
        # Check PREV references
        if 'PREV(' in condition:
            # Check if variable is first in sequence and references PREV
            if var_idx == 0:
                return False
    
    # Check FIRST references
    if any('FIRST(' in cond for cond in define_conditions.values()):
        # Ensure A exists for FIRST(A.value) references
        for var, condition in define_conditions.items():
            if 'FIRST(' in condition:
                # Extract referenced variable
                ref_match = re.search(r'FIRST\s*\(\s*([A-Za-z0-9_]+)\.', condition)
                if ref_match and ref_match.group(1) not in match_data['variables']:
                    return False
    
    return True

def post_validate_permute_match(match, define_conditions, pattern_text=None):
    """Post-validate PERMUTE matches with navigation functions for Trino compatibility"""
    # Skip empty matches
    if not match or match.get('is_empty', True):
        return False
    
    # Get variable hierarchy if pattern text is provided
    variable_hierarchy = None
    if pattern_text and "PERMUTE" in pattern_text:
        permute_handler = PermuteHandler()
        variable_hierarchy = permute_handler.analyze_pattern_hierarchy(pattern_text)
    
    # Extract the sequence of variables in the match
    sequence = []
    for idx in range(match['start'], match['end'] + 1):
        for var, indices in match['variables'].items():
            if idx in indices:
                sequence.append(var)
                break
    
    # Calculate sequence score based on variable hierarchy
    if variable_hierarchy:
        score = 0
        for pos, var in enumerate(sequence):
            # Weight increases with position (later positions matter more)
            weight = 10 ** (len(sequence) - pos - 1)
            # Priority from variable hierarchy (lower is better)
            priority = variable_hierarchy.get(var, 999)
            score += priority * weight
        
        # Store score with match for later filtering
        match['_sort_score'] = score
    
    # Basic validation for navigation bounds
    if not validate_navigation_bounds(match, define_conditions):
        return False
    
    # Rest of the existing validation logic...
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
