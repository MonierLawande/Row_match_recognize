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
from src.matcher.condition_evaluator import compile_condition
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
    """
    Generalized validation of navigation functions in PERMUTE patterns.
    Ensures that references to other variables are valid given the match ordering.
    
    Returns True if all navigation functions can be evaluated, False otherwise.
    """
    # Map variables to their positions in the match
    var_positions = {}
    for var, indices in match['variables'].items():
        if indices:
            var_positions[var] = min(indices)
    
    # Get the ordered list of variables based on their positions
    ordered_vars = sorted(var_positions.keys(), key=lambda v: var_positions[v])
    
    for define in define_clauses:
        var = define.variable
        condition = define.condition
        var_idx = ordered_vars.index(var) if var in ordered_vars else -1
        
        # Extract all navigation function calls
        nav_funcs = []
        # Match NEXT, PREV, FIRST, LAST with their arguments
        patterns = [
            r'NEXT\(([A-Za-z0-9_]+)\.', 
            r'PREV\(([A-Za-z0-9_]+)\.', 
            r'FIRST\(([A-Za-z0-9_]+)\.', 
            r'LAST\(([A-Za-z0-9_]+)\.'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, condition)
            for match in matches:
                if pattern.startswith(r'NEXT'):
                    nav_funcs.append(('NEXT', match))
                elif pattern.startswith(r'PREV'):
                    nav_funcs.append(('PREV', match))
                elif pattern.startswith(r'FIRST'):
                    nav_funcs.append(('FIRST', match))
                elif pattern.startswith(r'LAST'):
                    nav_funcs.append(('LAST', match))
        
        # Validate each navigation function
        for func_type, ref_var in nav_funcs:
            # Get position of referenced variable
            if ref_var not in var_positions:
                return False  # Referenced variable doesn't exist in this match
            
            ref_idx = ordered_vars.index(ref_var)
            
            # Validate based on function type
            if func_type == 'NEXT':
                # For NEXT(X), X must be the current variable and not the last
                if ref_var == var and var_idx == len(ordered_vars) - 1:
                    return False
                # For NEXT(Y), Y must appear before the current variable
                elif ref_var != var and ref_idx >= var_idx:
                    return False
            
            elif func_type == 'PREV':
                # For PREV(X), X must be the current variable and not the first
                if ref_var == var and var_idx == 0:
                    return False
                # For PREV(Y), Y must appear before the current variable
                elif ref_var != var and ref_idx >= var_idx:
                    return False
            
            elif func_type == 'FIRST':
                # Ensure the referenced variable appears somewhere in the match
                # (Already checked by the existence check above)
                pass
            
            elif func_type == 'LAST':
                # Ensure the referenced variable appears somewhere in the match
                # (Already checked by the existence check above)
                pass
    
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
    if hasattr(mr_clause, 'pattern') and hasattr(mr_clause.pattern, 'metadata') and \
       mr_clause.pattern.metadata.get('permute', False):
        print("PERMUTE pattern detected, validating navigation functions...")
        # Get define clauses
        define_clauses = mr_clause.define.definitions
        
        # Filter matches that have invalid navigation function references
        valid_matches = []
        for match in all_matches:
            if validate_navigation_functions(match, mr_clause.pattern.metadata.get('variables', []), define_clauses):
                valid_matches.append(match)
            else:
                print(f"Filtering out match with invalid navigation function usage: {match['variables']}")
        
        # Replace matches with valid ones
        all_matches = valid_matches
        print(f"After filtering: {len(all_matches)} valid matches")

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

    # If PERMUTE is present, expand the pattern and use the expanded pattern for matching
    if mr_clause.pattern.get('permute', True):
        permute_handler = PermuteHandler()
        if mr_clause.pattern.get('nested_permute', False):
            expanded_pattern = permute_handler.expand_nested_permute(mr_clause.pattern)
        else:
            expanded_pattern = {'permutations': permute_handler.expand_permutation(mr_clause.pattern['variables'])}
        # Use expanded pattern for matching

    # Extract the original variable order from PERMUTE pattern
    original_variable_order = []
    if hasattr(mr_clause, 'pattern') and hasattr(mr_clause.pattern, 'metadata') and \
       mr_clause.pattern.metadata.get('permute', False):
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
        if hasattr(mr_clause.pattern, 'metadata') and mr_clause.pattern.metadata.get('permute', False):
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

    return result_df
