import unittest
from src.parser.expression_parser import parse_expression_full

class TestExpressionParser(unittest.TestCase):
    def test_literal_expression(self):
        expr = "42"
        result = parse_expression_full(expr)
        self.assertEqual(result["ast"].type, "literal")
        self.assertEqual(result["ast"].value, "42")
    def test_navigation_expression(self):
        expr = "PREV(A.totalprice, 2)"
        result = parse_expression_full(expr)
        self.assertEqual(result["ast"].type, "navigation")
        self.assertEqual(result["ast"].navigation_type, "PREV")
        self.assertEqual(result["ast"].offset, 2)
    def test_semantics_expression(self):
        expr = "FINAL FIRST(A.totalprice, 3)"
        result = parse_expression_full(expr)
        self.assertEqual(result["ast"].semantics, "FINAL")
        self.assertEqual(result["ast"].type, "navigation")
        self.assertEqual(result["ast"].navigation_type, "FIRST")

if __name__ == '__main__':
    unittest.main()
