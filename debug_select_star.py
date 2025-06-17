#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.parser.match_recognize_extractor import parse_full_query

def debug_select_star():
    """Debug how SELECT * is parsed."""
    
    query = """
    SELECT *
    FROM data
    MATCH_RECOGNIZE (
        ORDER BY id
        MEASURES
            MATCH_NUMBER() AS match,
            RUNNING LAST(value) AS val,
            CLASSIFIER() AS label
        ALL ROWS PER MATCH
        AFTER MATCH SKIP PAST LAST ROW
        PATTERN (A B+ C+)
        DEFINE
            B AS B.value < PREV(B.value),
            C AS C.value > PREV(C.value)
    ) AS m
    """
    
    print("Parsing SELECT * query...")
    ast = parse_full_query(query)
    
    print("=== SELECT CLAUSE ===")
    if ast.select_clause and ast.select_clause.items:
        for i, item in enumerate(ast.select_clause.items):
            print(f"Item {i}: expression='{item.expression}', alias='{item.alias}'")
            print(f"  Has '*': {'*' in item.expression}")
    
    print("\n=== MEASURES ===")
    measures = {}
    for m in ast.match_recognize.measures.measures:
        measures[m.alias] = m.expression
        print(f"'{m.alias}': '{m.expression}'")
    
    print(f"\nMeasures dict: {measures}")

if __name__ == "__main__":
    debug_select_star()
