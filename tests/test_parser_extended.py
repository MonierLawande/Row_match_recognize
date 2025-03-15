# tests/test_parser_additional.py

import unittest
from hypothesis import given, strategies as st
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full
from src.parser.parser_util import ErrorHandler, ParserContext

class TestExpressionParserAdditional(unittest.TestCase):
    def setUp(self):
        self.error_handler = ErrorHandler()
        self.context = ParserContext(self.error_handler)

    def test_valid_function_call(self):
        # Test a valid aggregate function call.
        expr = "sum(A.total)"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        # Expect the outer node to be of type "aggregate" (or similar, per your implementation)
        self.assertEqual(result["parse_tree"].node_type, "aggregate")
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")

    def test_function_call_missing_parenthesis(self):
        # Test a function call missing a closing parenthesis.
        expr = "avg(A.total"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Expected" in err for err in result["errors"]),
                        f"Expected an error for missing ')' but got: {result['errors']}")

    def test_navigation_function_negative_offset(self):
        # Navigation function with a negative offset should produce an error.
        expr = "PREV(A.total, -1)"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Navigation offset" in err for err in result["errors"]),
                        f"Expected error for negative offset, got: {result['errors']}")

    def test_complex_arithmetic_expression(self):
        # Test an expression with multiple operators and grouping.
        expr = "((A + B) * (C - D)) / (E + F - G)"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertEqual(result["parse_tree"].node_type, "binary")
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")

    def test_decimal_expression(self):
        # Test expressions involving decimals.
        expr = "3.14 * 2.0 + 0.001"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertEqual(result["parse_tree"].node_type, "binary")
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")

    def test_unexpected_character_in_expression(self):
        # Test an expression with an unexpected character.
        expr = "A + @ + B"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        self.assertTrue(any("Unexpected token" in err for err in result["errors"]),
                        f"Expected an error for unexpected token, got: {result['errors']}")

class TestPatternParserAdditional(unittest.TestCase):
    def setUp(self):
        self.error_handler = ErrorHandler()
        self.context = ParserContext(self.error_handler)

    def test_valid_simple_pattern(self):
        # A simple valid pattern with multiple tokens.
        pattern = "A B C"
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertEqual(result["parse_tree"].node_type, "concatenation")
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")
        self.assertEqual(result["pattern_variables"], {"A", "B", "C"})

    def test_pattern_with_quantifiers(self):
        # Pattern using valid quantifiers.
        pattern = "A+ B* C?"
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertEqual(result["parse_tree"].node_type, "concatenation")
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")
        self.assertEqual(result["pattern_variables"], {"A", "B", "C"})

    def test_invalid_pattern_unknown_char(self):
        # Pattern with an unknown character (here '@').
        pattern = "A @ B"
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertTrue(any("Unknown token" in err for err in result["errors"]),
                        f"Expected an error for unknown token, got: {result['errors']}")

    def test_pattern_with_extra_parentheses(self):
        # Pattern with extra outer parentheses; expect them to be stripped.
        pattern = "((A+ B*))"
        result = parse_pattern_full(pattern, subset_mapping=None, context=self.context)
        self.assertNotEqual(result["parse_tree"].node_type, "empty",
                            "Expected a non-empty parse tree after stripping parentheses")
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")

    @given(st.text(min_size=1, max_size=30))
    def test_pattern_fuzzing(self, random_pattern):
        # Use Hypothesis to generate random patterns and ensure we always get a parse tree.
        result = parse_pattern_full(random_pattern, subset_mapping=None, context=self.context)
        self.assertIn("parse_tree", result)

if __name__ == '__main__':
    unittest.main()
