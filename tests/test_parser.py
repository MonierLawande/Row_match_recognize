# tests/test_parser_edge_cases.py

import unittest
from hypothesis import given, strategies as st
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full
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
        # Expect error reporting an unexpected token ')'
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
    
    @given(st.text(min_size=1, max_size=50))
    def test_expression_fuzzing(self, random_expr):
        result = parse_expression_full(random_expr, in_measures_clause=True, context=self.context)
        self.assertIn("parse_tree", result)
    
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
        # Expect that outer parentheses are stripped and a valid pattern tree is returned.
        self.assertNotEqual(result["parse_tree"].node_type, "empty")

if __name__ == '__main__':
    unittest.main()
