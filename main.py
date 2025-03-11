#!/usr/bin/env python
"""
Main entry point for the MATCH_RECOGNIZE project.
"""

import logging
from src.ast.ast_builder import build_enhanced_match_recognize_ast
from src.ast.expression_ast import visualize_expression_ast  # (if you want to visualize an expression)
from src.ast.pattern_ast import visualize_pattern
from src.parser.expression_parser import parse_expression_full

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

def main():
    # Sample SQL query with MATCH_RECOGNIZE clause
    query = (
        "SELECT * FROM orders "
        "MATCH_RECOGNIZE ("
        "  PARTITION BY custkey "
        "  ORDER BY orderdate "
        "  PATTERN (A+ B) "
        "  DEFINE A AS price > 10, "
        "         B AS price < 20"
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
    
    # Example: Parsing an independent expression
    expression = "price * 1.1 + 5"
    expr_ast = parse_expression_full(expression)
    print("\nParsed Expression AST:")
    print(expr_ast)

if __name__ == "__main__":
    main()
