#!/usr/bin/env python
"""
Main entry point for the MATCH_RECOGNIZE project.
Demonstrates parsing a SQL query with MATCH_RECOGNIZE and extended expression features.
"""

import logging
from src.ast_nodes.ast_builder import build_enhanced_match_recognize_ast
from ast.expression_optimizer import visualize_expression_ast
from src.ast.pattern_ast import visualize_pattern
from src.parser.expression_parser import parse_expression_full

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

def main():
    # Sample SQL query with MATCH_RECOGNIZE clause
    query = (
        "SELECT * FROM orders "
        "MATCH_RECOGNIZE ("
        "  PARTITION BY custkey "
        "  ORDER BY orderdate "
        "  MEASURES "
        "         A.totalprice AS starting_price, "
        "         LAST(B.totalprice) AS bottom_price, "
        "         LAST(U.totalprice) AS top_price, "
        "         match_number() AS match_no "
        "  ONE ROW PER MATCH "
        "  AFTER MATCH SKIP PAST LAST ROW "
        "  PATTERN (A B+ C+ D+) "
        "  SUBSET U = (C, D) "
        "  DEFINE "
        "         B AS totalprice < PREV(totalprice), "
        "         C AS totalprice > PREV(totalprice) AND totalprice <= A.totalprice, "
        "         D AS totalprice > PREV(totalprice) "
        ");"
    )
    
    # Build the enhanced AST from the query
    ast, errors = build_enhanced_match_recognize_ast(query)
    
    if errors:
        print("Validation Errors:")
        for err in errors:
            print(" -", err)
    else:
        print("Generated AST for MATCH_RECOGNIZE clause:")
        print(ast)
    
    # Visualize the row pattern if available
    if ast.pattern and "ast" in ast.pattern:
        print("\nPattern Visualization:")
        print(visualize_pattern(ast.pattern["ast"]))
    
    # Example: Parsing an independent expression with nested navigation and semantics
    expression = "RUNNING PREV(FIRST(A.totalprice, 3), 2) + 5"
    expr_result = parse_expression_full(expression)
    print("\nParsed Expression AST:")
    print(visualize_expression_ast(expr_result["ast"]))

if __name__ == "__main__":
    main()
