# src/executor/match_recognize.py

import pandas as pd
import re
import time
import itertools
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from src.parser.match_recognize_extractor import parse_full_query
from src.matcher.pattern_tokenizer import tokenize_pattern
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


def match_recognize(query: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Execute a MATCH_RECOGNIZE query against a Pandas DataFrame.
    Enhanced to match Trino's output format exactly.
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
        sort_columns = []
        if partition_by:
            sort_columns.extend([col for col in partition_by if col in result_df.columns])
        if order_by:
            sort_columns.extend([col for col in order_by if col in result_df.columns])
        
        if sort_columns and not result_df.empty:
            result_df = result_df.sort_values(by=sort_columns, kind='mergesort')
            
        return result_df[ordered_cols]
    else:
        # For ALL ROWS PER MATCH, keep all rows
        result_df = pd.DataFrame(results)
        
        # Determine columns to include
        output_cols = []
        # Add original columns first
        original_cols = [col for col in df.columns if col in result_df.columns]
        output_cols.extend(original_cols)
        
        # Add measure columns
        measure_cols = [col for col in measures.keys() if col in result_df.columns]
        output_cols.extend(measure_cols)
        
        # Add metadata columns if they exist
        meta_cols = ["MATCH_NUMBER", "IS_EMPTY_MATCH"]
        for col in meta_cols:
            if col in result_df.columns:
                output_cols.append(col)
        
        # Only keep columns that exist in the result
        output_cols = [col for col in output_cols if col in result_df.columns]
        
        # Sort the results to match Trino's output ordering
        sort_columns = []
        if partition_by:
            sort_columns.extend([col for col in partition_by if col in result_df.columns])
        if order_by:
            sort_columns.extend([col for col in order_by if col in result_df.columns])
        
        if sort_columns and not result_df.empty:
            result_df = result_df.sort_values(by=sort_columns, kind='mergesort')
            
        return result_df[output_cols]
