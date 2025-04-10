# src/executor/match_recognize.py

import pandas as pd
from typing import List, Dict, Any, Optional, Set

from src.parser.match_recognize_extractor import parse_full_query
from src.matcher.pattern_tokenizer import tokenize_pattern
from src.matcher.automata import NFABuilder
from src.matcher.dfa import DFABuilder
from src.matcher.matcher import EnhancedMatcher, MatchConfig, SkipMode, RowsPerMatch
from src.matcher.row_context import RowContext
from src.matcher.condition_evaluator import compile_condition

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

def match_recognize(query: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Execute a MATCH_RECOGNIZE query against a Pandas DataFrame.
    Enhanced with support for all MATCH_RECOGNIZE features, including empty matches.
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
        rows_per_match_text = mr_clause.rows_per_match.raw_mode.upper()
        if "ALL ROWS PER MATCH" in rows_per_match_text:
            if "WITH UNMATCHED ROWS" in rows_per_match_text:
                rows_per_match = RowsPerMatch.ALL_ROWS_WITH_UNMATCHED
            elif "OMIT EMPTY MATCHES" in rows_per_match_text:
                rows_per_match = RowsPerMatch.ALL_ROWS
            else:
                rows_per_match = RowsPerMatch.ALL_ROWS_SHOW_EMPTY

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
    if mr_clause.measures:
        for m in mr_clause.measures.measures:
            # Handle special functions
            if m.expression.upper() == "CLASSIFIER()":
                measures[m.alias] = "CLASSIFIER()"
            elif m.expression.upper() == "MATCH_NUMBER()":
                measures[m.alias] = "MATCH_NUMBER()"
            else:
                # Handle RUNNING/FINAL prefixes
                if m.metadata and 'semantics' in m.metadata:
                    if m.metadata['semantics'] == 'RUNNING':
                        measures[m.alias] = f"RUNNING {m.expression}"
                    elif m.metadata['semantics'] == 'FINAL':
                        measures[m.alias] = f"FINAL {m.expression}"
                    else:
                        measures[m.alias] = m.expression
                else:
                    measures[m.alias] = m.expression

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
        include_unmatched=(rows_per_match == RowsPerMatch.ALL_ROWS_WITH_UNMATCHED)
    )
    
    # Process partitions
    results = []
    
    # Partition the DataFrame
    if partition_by:
        partitions = [group for _, group in df.groupby(partition_by)]
    else:
        partitions = [df]
    
    for partition in partitions:
        # Order the partition
        if order_by:
            partition = partition.sort_values(by=order_by)
            
        # Convert to rows
        rows = partition.to_dict('records')
        
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
            exclusion_ranges=nfa.exclusion_ranges,
            after_match_skip=skip_mode,
            subsets=subset_dict
        )
        
        # Find matches
        partition_results = matcher.find_matches(
            rows=rows,
            config=config,
            measures=measures  # Pass measures explicitly
        )
        
        # Add partition columns if needed
        if partition_by and rows:
            for result in partition_results:
                for col in partition_by:
                    result[col] = rows[0][col]  # Use values from first row of partition
                    
        results.extend(partition_results)

    # Create output DataFrame
    if not results:
        # Create empty DataFrame with appropriate columns
        columns = list(df.columns)  # Include original columns
        if measures:
            columns.extend(measures.keys())  # Add measure columns
        columns.extend(['MATCH_NUMBER', 'IS_EMPTY_MATCH'])  # Add metadata columns
        return pd.DataFrame(columns=columns)
    
    return pd.DataFrame(results)
