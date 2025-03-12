# src/main.py

from src.parser.sql_parser import parse_sql_query
from src.ast.ast_builder import build_ast_from_parse_tree
from src.validator.validator import validate_ast
from src.ast.pattern_optimizer import optimize_ast
from src.evaluator.evaluation_engine import evaluate_ast

def process_query(sql_query: str):
    """
    Main entry point for processing SQL queries with pattern matching.
    
    This function orchestrates the entire pipeline:
    1. Parse the SQL query into tokens and basic structure
    2. Build an abstract syntax tree (AST)
    3. Validate the AST
    4. Optimize the AST
    5. Evaluate the query
    
    Each step takes the output of the previous step as input.
    """
    # Step 1: Parse the SQL query
    parse_result = parse_sql_query(sql_query)
    if parse_result["errors"]:
        return {"status": "error", "phase": "parsing", "errors": parse_result["errors"]}
    
    # Step 2: Build the AST
    ast_result = build_ast_from_parse_tree(parse_result["parse_tree"])
    if ast_result["errors"]:
        return {"status": "error", "phase": "ast_building", "errors": ast_result["errors"]}
    
    # Step 3: Validate the AST
    validation_result = validate_ast(ast_result["ast"])
    if validation_result["errors"]:
        return {"status": "error", "phase": "validation", "errors": validation_result["errors"]}
    
    # Step 4: Optimize the AST
    optimized_ast = optimize_ast(ast_result["ast"])
    
    # Step 5: Evaluate the query
    evaluation_result = evaluate_ast(optimized_ast)
    
    return {
        "status": "success",
        "ast": optimized_ast,
        "validation": validation_result,
        "result": evaluation_result
    }
