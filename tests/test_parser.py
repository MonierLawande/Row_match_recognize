# tests/test_parser_edge_cases.py

import unittest
from hypothesis import given, strategies as st
from src.parser.expression_parser import parse_expression_full, parse_expression
from src.parser.pattern_parser import parse_pattern_full, parse_pattern
from src.parser.parser_util import ErrorHandler, ParserContext

class TestExpressionParserEdgeCases(unittest.TestCase):
    def setUp(self):
        self.error_handler = ErrorHandler()
        self.context = ParserContext(self.error_handler)
    
    def test_empty_expression(self):
        expr = ""
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Empty expression" in err for err in result["errors"]))
    
    def test_whitespace_only_expression(self):
        expr = "   \t\n   "
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Empty expression" in err for err in result["errors"]))
    
    def test_missing_closing_parenthesis(self):
        expr = "A + (B * 2"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Expected" in err and ")" in err for err in result["errors"]))
    
    def test_extra_closing_parenthesis(self):
        expr = "A + B) + C"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Unexpected token" in err for err in result["errors"]))
    
    def test_invalid_character_in_expression(self):
        expr = "A + # + C"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Unexpected token" in err for err in result["errors"]))
    
    def test_deeply_nested_expression(self):
        expr = "A"
        for _ in range(11):  # default max nesting is 10
            expr = "(" + expr + ")"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Maximum nesting level" in err for err in result["errors"]))
    
    def test_trailing_unexpected_tokens(self):
        expr = "A + B extra"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Unexpected token" in err for err in result["errors"]))
    
    def test_valid_function_call(self):
        expr = "avg(A.totalprice)"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertFalse(result["errors"], f"Errors found: {result['errors']}")
        self.assertIn(result["parse_tree"].node_type, ["aggregate", "function"],
                      "Expected function call node type")
    
    def test_function_call_missing_parenthesis(self):
        expr = "avg(A.totalprice"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Expected" in err for err in result["errors"]),
                        f"Expected error for missing ')' but got: {result['errors']}")
    
    def test_valid_navigation_function(self):
        expr = "PREV(A.totalprice, 2)"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertFalse(result["errors"], f"Errors found: {result['errors']}")
        self.assertEqual(result["parse_tree"].node_type, "navigation",
                         "Expected navigation function node")
    
    def test_navigation_negative_offset(self):
        expr = "PREV(A.totalprice, -1)"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Navigation offset must be a positive integer literal" in err for err in result["errors"]),
                        f"Expected error for negative offset, got: {result['errors']}")
    
    def test_function_call_with_extra_tokens(self):
        expr = "sum(A.totalprice) extra"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Unexpected token" in err for err in result["errors"]),
                        f"Expected error for extra tokens, got: {result['errors']}")
    
    def test_decimal_literal(self):
        expr = "3.14 + 2.71"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")
        literals = [node for node in self._collect_nodes(result["parse_tree"]) if node.node_type == "literal"]
        self.assertGreaterEqual(len(literals), 2, "Expected at least two literal nodes for decimals")
    
    def test_expression_caching(self):
        expr = "A + B"
        result1 = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        result2 = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertIs(result1, result2, "Expected cached result to be reused")
    
    @given(st.text(min_size=1, max_size=50))
    def test_expression_fuzzing(self, random_expr):
        result = parse_expression_full(random_expr, in_measures_clause=True, context=self.context)
        self.assertIn("parse_tree", result)
    
    def _collect_nodes(self, node):
        """Recursively collect all nodes from the parse tree."""
        nodes = [node]
        for child in node.children:
            nodes.extend(self._collect_nodes(child))
        return nodes

class TestPatternParserEdgeCases(unittest.TestCase):
    def setUp(self):
        self.error_handler = ErrorHandler()
        self.context = ParserContext(self.error_handler)
    
    def test_empty_pattern(self):
        pattern = ""
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertEqual(result["parse_tree"].node_type, "empty")
    
    def test_whitespace_only_pattern(self):
        pattern = "   "
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertEqual(result["parse_tree"].node_type, "empty")
    
    def test_invalid_pattern_quantifier(self):
        pattern = "+ A"
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertTrue(any("Invalid quantifier placement" in err for err in result["errors"]))
    
    def test_pattern_with_unknown_token(self):
        pattern = "A @ B"
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertTrue(any("Unknown token" in err for err in result["errors"]))
    
    def test_pattern_with_extra_parentheses(self):
        pattern = "((A+ B*))"
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertNotEqual(result["parse_tree"].node_type, "empty")
    
    def test_valid_pattern_concatenation(self):
        pattern = "A+ B? C"
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertFalse(result["errors"], f"Errors found: {result['errors']}")
        self.assertEqual(result["parse_tree"].node_type, "concatenation")
        self.assertEqual(result["pattern_variables"], {"A", "B", "C"})
    
    def test_pattern_with_subset_definition(self):
        pattern = "A B"
        subset_mapping = {"X": ["A", "B"]}
        result = parse_pattern_full(pattern, subset_mapping=subset_mapping, context=self.context)
        self.assertIn("X", self.context.subset_variables)
    
    @given(st.text(min_size=1, max_size=20))
    def test_pattern_fuzzing(self, random_pattern):
        result = parse_pattern_full(random_pattern, subset_mapping=None, context=self.context)
        self.assertIn("parse_tree", result)

if __name__ == '__main__':
    unittest.main()
