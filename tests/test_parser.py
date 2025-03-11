import unittest
from src.parser.expression_parser import parse_expression_full

class TestExpressionParser(unittest.TestCase):
    def test_literal(self):
        expr = "42"
        result = parse_expression_full(expr)
        self.assertEqual(result["ast"].type, "literal")
        self.assertEqual(result["ast"].value, "42")

if __name__ == '__main__':
    unittest.main()
