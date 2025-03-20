import pytest
from src.parser.match_recognize_extractor import parse_match_recognize_query, parse_full_query
from src.ast.ast_nodes import FullQueryAST, MatchRecognizeClause

# Example queries for testing

def test_alternation():
    query = """
    SELECT * FROM orders MATCH_RECOGNIZE(
        PARTITION BY custkey
        ORDER BY orderdate
        MEASURES A.totalprice AS starting_price
        PATTERN (A | B | C)
        DEFINE A AS totalprice > 100, B AS totalprice < 50, C AS totalprice BETWEEN 50 AND 100
    );
    """
    ast = parse_match_recognize_query(query)
    # Check that pattern variables are parsed correctly.
    assert isinstance(ast, MatchRecognizeClause)
    pattern_vars = ast.pattern.metadata["variables"]
    assert pattern_vars == ['A', 'B', 'C']

def test_grouping():
    query = """
    SELECT * FROM orders MATCH_RECOGNIZE(
        PARTITION BY custkey
        ORDER BY orderdate
        MEASURES A.totalprice AS starting_price
        PATTERN ((A B C))
        DEFINE A AS totalprice > 0, B AS totalprice < PREV(totalprice), C AS totalprice < 100
    );
    """
    ast = parse_match_recognize_query(query)
    # Grouping should remove extra parentheses.
    assert ast.pattern.metadata["base_variables"] == ['A', 'B', 'C']

def test_permutation():
    query = """
    SELECT * FROM orders MATCH_RECOGNIZE(
        PARTITION BY custkey
        ORDER BY orderdate
        MEASURES LAST(U.totalprice) AS top_price
        PATTERN (PERMUTE(A, B, C))
        SUBSET U = (A, B, C)
        DEFINE A AS totalprice > 0, B AS totalprice < PREV(totalprice), C AS totalprice < 100
    );
    """
    ast = parse_match_recognize_query(query)
    # For permutation, metadata should list base variables without commas.
    assert ast.pattern.metadata["base_variables"] == ['A', 'B', 'C']

def test_quantifiers_greedy():
    query = """
    SELECT * FROM orders MATCH_RECOGNIZE(
        PARTITION BY custkey
        ORDER BY orderdate
        MEASURES A.totalprice AS starting_price, LAST(A.totalprice) AS ending_price
        PATTERN (A{2,4})
        DEFINE A AS totalprice > 0
    );
    """
    ast = parse_match_recognize_query(query)
    assert ast.pattern.metadata["variables"] == ['A{2,4}']
    assert ast.pattern.metadata["base_variables"] == ['A']

def test_quantifiers_reluctant():
    query = """
    SELECT * FROM orders MATCH_RECOGNIZE(
        PARTITION BY custkey
        ORDER BY orderdate
        MEASURES A.totalprice AS starting_price, LAST(A.totalprice) AS ending_price
        PATTERN (A{2,4}?)
        DEFINE A AS totalprice > 0
    );
    """
    ast = parse_match_recognize_query(query)
    assert ast.pattern.metadata["variables"] == ['A{2,4}?']
    assert ast.pattern.metadata["base_variables"] == ['A']

def test_navigation_invalid():
    query = """
    SELECT * FROM orders MATCH_RECOGNIZE(
        PARTITION BY custkey
        ORDER BY orderdate
        MEASURES LAST(1) AS invalid_nav
        PATTERN (A+)
        DEFINE A AS totalprice > 0
    );
    """
    with pytest.raises(Exception) as excinfo:
        parse_match_recognize_query(query)
    assert "Invalid usage of LAST" in str(excinfo.value)

def test_nested_aggregate_invalid():
    query = """
    SELECT * FROM orders MATCH_RECOGNIZE(
        PARTITION BY custkey
        ORDER BY orderdate
        MEASURES FIRST(avg(A.totalprice),2) AS invalid_agg_nav
        PATTERN (A+)
        DEFINE A AS totalprice > 0
    );
    """
    with pytest.raises(Exception) as excinfo:
        parse_match_recognize_query(query)
    assert "Invalid usage of FIRST" in str(excinfo.value)

# You can add additional tests for complex SELECT clause parsing as needed.
