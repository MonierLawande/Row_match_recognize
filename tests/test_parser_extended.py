# tests/test_parser_full_coverage.py

import unittest
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full
from src.parser.context import ParserContext
from src.parser.error_handler import ErrorHandler

class FullCoverageExpressionTests(unittest.TestCase):
    def setUp(self):
        self.context = ParserContext(ErrorHandler())
    
    def test_unary_minus(self):
        # Testing a unary minus should produce a binary '-' operator with left child 0.
        expr = "-A"
        result = parse_expression_full(expr, context=self.context)
        self.assertEqual(result["ast"].type, "binary")
        self.assertEqual(result["ast"].operator, "-")
        self.assertEqual(result["ast"].children[0].type, "literal")
        self.assertEqual(result["ast"].children[0].value, "0")
        self.assertEqual(result["ast"].children[1].type, "identifier")
        self.assertEqual(result["ast"].children[1].value, "A")
    
    def test_decimal_numbers(self):
        # Verify that decimal numbers are correctly parsed.
        expr = "3.1415 + 2.718"
        result = parse_expression_full(expr, context=self.context)
        self.assertEqual(result["ast"].children[0].type, "literal")
        self.assertEqual(result["ast"].children[0].value, "3.1415")
        self.assertEqual(result["ast"].children[1].type, "literal")
        self.assertEqual(result["ast"].children[1].value, "2.718")
    
    def test_complex_unary_and_binary(self):
        # Testing nested unary operators with binary arithmetic.
        expr = "-(A + -B)"
        result = parse_expression_full(expr, context=self.context)
        self.assertEqual(result["ast"].type, "binary")
        self.assertEqual(result["ast"].operator, "-")
        # Left child should be the literal 0
        self.assertEqual(result["ast"].children[0].type, "literal")
        self.assertEqual(result["ast"].children[0].value, "0")
        # Right child should be a binary addition expression.
        self.assertEqual(result["ast"].children[1].type, "binary")
        self.assertEqual(result["ast"].children[1].operator, "+")
    
    def test_extra_tokens_after_expression(self):
        # Extra tokens after a valid expression should be reported as errors.
        expr = "A + 5 extra"
        result = parse_expression_full(expr, context=self.context)
        self.assertTrue(any("Unexpected token" in e for e in result["errors"]))
    
    def test_multiple_errors(self):
        # Testing an expression with several syntax issues.
        expr = "A + (B *"
        result = parse_expression_full(expr, context=self.context)
        self.assertGreater(len(result["errors"]), 0)
    
    def test_semantics_running(self):
        # RUNNING semantics should be attached and allowed in a measures clause.
        expr = "RUNNING (A + 5)"
        result = parse_expression_full(expr, context=self.context)
        self.assertEqual(result["ast"].semantics, "RUNNING")
        self.assertEqual(result["errors"], [])
    
    def test_deeply_nested_expression(self):
        # Create a deeply nested expression exceeding the allowed maximum nesting.
        expr = "A"
        # Wrap the expression in 15 pairs of parentheses.
        for i in range(15):
            expr = "(" + expr + ")"
        result = parse_expression_full(expr, context=self.context)
        self.assertTrue(any("Maximum nesting level" in e for e in result["errors"]))

class FullCoveragePatternTests(unittest.TestCase):
    def setUp(self):
        self.context = ParserContext(ErrorHandler())
    
    def test_pattern_unknown_token(self):
        # Test that an unknown token in a pattern (e.g., '@') triggers an error.
        result = parse_pattern_full("A @", context=self.context)
        self.assertTrue(len(result["errors"]) > 0)
    
    def test_pattern_complex_concatenation(self):
        # A pattern with multiple quantifiers should result in a concatenation node.
        result = parse_pattern_full("A+ B? C*", context=self.context)
        self.assertEqual(result["ast"].type, "concatenation")
        self.assertEqual(len(result["ast"].children), 3)
    
    def test_pattern_with_extra_whitespace(self):
        # Extra whitespace and outer parentheses should be handled gracefully.
        result = parse_pattern_full("  (  A+   B  )  ", context=self.context)
        self.assertNotEqual(result["ast"].type, "empty")
    
    def test_pattern_invalid_quantifier_position(self):
        # An invalid quantifier position (e.g., starting with a quantifier) should cause an error.
        result = parse_pattern_full("+ A", context=self.context)
        self.assertTrue(len(result["errors"]) > 0)

if __name__ == '__main__':
    unittest.main()
