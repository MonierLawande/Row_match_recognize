# src/executor/match_recognize.py

import pandas as pd
from typing import List, Dict, Any

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

def match_recognize(query: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Execute a MATCH_RECOGNIZE query against a Pandas DataFrame.
    Enhanced with support for all MATCH_RECOGNIZE features.
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
    measures = {m.alias: m.expression for m in mr_clause.measures.measures} if mr_clause.measures else {}
    define = {d.variable: d.condition for d in mr_clause.define.definitions} if mr_clause.define else {}
    subsets = mr_clause.subset if mr_clause.subset else []

    # Create match configuration
    config = MatchConfig(
        rows_per_match=rows_per_match,
        skip_mode=skip_mode,
        skip_var=skip_var,
        show_empty=True,  # Could be configured based on rows_per_match
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
        
        # Create matcher and find matches
        matcher = EnhancedMatcher(dfa)
        partition_results = matcher.find_matches(rows, config, measures)
        
        # Add partition columns if needed
        if partition_by:
            for result in partition_results:
                for col in partition_by:
                    result[col] = rows[0][col]  # Use values from first row of partition
                    
        results.extend(partition_results)

    # Create output DataFrame
    if not results:
        # Create empty DataFrame with appropriate columns
        columns = []
        if ast.select_clause:
            columns.extend(item.expression for item in ast.select_clause.items)
        if measures:
            columns.extend(measures.keys())
        return pd.DataFrame(columns=columns)
    
    return pd.DataFrame(results)

def evaluate_measure(expr: str, context: RowContext, running: bool = False) -> Any:
    """
    Evaluate a measure expression with support for RUNNING and FINAL semantics.
    """
    # Parse for RUNNING/FINAL prefix
    expr = expr.strip()
    is_running = running
    if expr.upper().startswith("RUNNING "):
        is_running = True
        expr = expr[8:].strip()
    elif expr.upper().startswith("FINAL "):
        is_running = False
        expr = expr[6:].strip()

    # Create evaluator for the expression
    evaluator = compile_condition(expr)
    
    if is_running:
        # Evaluate from current row's perspective
        return evaluator(context.rows[-1], context)
    else:
        # Evaluate with access to all rows in the match
        return evaluator(context.rows[-1], context)
