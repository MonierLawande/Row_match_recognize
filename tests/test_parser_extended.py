import unittest
from src.parser.expression_parser import parse_expression_full
from src.parser.context import ParserContext
from src.parser.error_handler import ErrorHandler

class TestExtendedExpressionParser(unittest.TestCase):

    def setUp(self):
        self.context = ParserContext(ErrorHandler())

    def test_basic_expression(self):
        result = parse_expression_full("A + 5", context=self.context)
        self.assertEqual(result["ast"].type, "binary")
        self.assertEqual(result["ast"].operator, "+")
        self.assertEqual(result["ast"].children[0].type, "identifier")
        self.assertEqual(result["ast"].children[1].type, "literal")

    def test_missing_parenthesis(self):
        result = parse_expression_full("A + (B * 2", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Expected ')'" in errors or "end of expression" in errors,
                        "Should report missing closing parenthesis")

    def test_unexpected_token(self):
        result = parse_expression_full("A + ?", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Unexpected token" in errors,
                        "Should report unexpected token '?'")

    def test_function_call_without_parenthesis(self):
        result = parse_expression_full("avg A.totalprice", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("must be followed by '('" in errors,
                        "Should report missing '(' after function name")

    def test_nested_aggregate_not_allowed(self):
        result = parse_expression_full("avg(sum(A.totalprice))", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Nested aggregate functions are not allowed" in errors,
                        "Should report nested aggregates error")

    def test_navigation_missing_column_reference(self):
        result = parse_expression_full("PREV(A, 2)", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("requires at least one column reference" in errors,
                        "Should report error when navigation function lacks column reference")

    def test_navigation_negative_offset(self):
        result = parse_expression_full("PREV(A.totalprice, -1)", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Navigation offset cannot be negative" in errors,
                        "Should report negative offset error")

    def test_deeply_nested_expression(self):
        expr = "avg(PREV(A.totalprice, 1) + (B.totalprice * 2) - (sum(C.discount) / 3))"
        result = parse_expression_full(expr, context=self.context)
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")
        self.assertEqual(result["ast"].type, "aggregate", "The outer function should be an aggregate")



    def test_empty_expression(self):
        result = parse_expression_full("", context=self.context)
        self.assertTrue(
            any("Empty expression" in e for e in result["errors"]),
            "Empty expression should be flagged as an error"
        )

    def test_single_identifier(self):
        result = parse_expression_full("A", context=self.context)
        self.assertEqual(result["ast"].type, "identifier")
        self.assertEqual(result["ast"].value, "A")

    def test_simple_literal(self):
        result = parse_expression_full("123", context=self.context)
        self.assertEqual(result["ast"].type, "literal")
        self.assertEqual(result["ast"].value, "123")

    def test_basic_arithmetic(self):
        result = parse_expression_full("A + 5 - 3", context=self.context)
        # The outermost operation should be subtraction
        self.assertEqual(result["ast"].type, "binary")
        self.assertEqual(result["ast"].operator, "-")
        # Left child should be a binary addition
        self.assertEqual(result["ast"].children[0].operator, "+")

    def test_nested_parentheses(self):
        expr = "((A + 5) * (B - 3))"
        result = parse_expression_full(expr, context=self.context)
        self.assertEqual(result["ast"].type, "binary")
        self.assertEqual(len(result["errors"]), 0, "No errors should be reported for valid nested parentheses")

    def test_missing_closing_parenthesis(self):
        expr = "(A + 5"
        result = parse_expression_full(expr, context=self.context)
        self.assertTrue(
            any("Expected ')'" in e for e in result["errors"]),
            "Missing closing parenthesis error not reported"
        )

    def test_unexpected_token(self):
        expr = "A + ?"
        result = parse_expression_full(expr, context=self.context)
        self.assertTrue(
            any("Unexpected token" in e for e in result["errors"]),
            "Unexpected token error not reported"
        )

    def test_function_call_without_parenthesis(self):
        expr = "sum A.totalprice"
        result = parse_expression_full(expr, context=self.context)
        self.assertTrue(
            any("must be followed by '('" in e for e in result["errors"]),
            "Missing '(' after function name error not reported"
        )

    def test_nested_aggregate_direct_error(self):
        expr = "avg(sum(A.totalprice))"
        result = parse_expression_full(expr, context=self.context)
        self.assertTrue(
            any("Nested aggregate functions are not allowed" in e for e in result["errors"]),
            "Direct nested aggregate error not reported"
        )

    def test_aggregate_inside_arithmetic(self):
        expr = "avg(A.totalprice + sum(B.discount))"
        result = parse_expression_full(expr, context=self.context)
        # The sum(B.discount) is nested inside an arithmetic expression; it should not trigger a direct nested aggregate error.
        self.assertEqual(result["errors"], [],
                         "Unexpected error for aggregate inside arithmetic expression")

    def test_navigation_function_valid(self):
        expr = "PREV(A.totalprice, 2)"
        result = parse_expression_full(expr, context=self.context)
        self.assertEqual(result["ast"].type, "navigation")
        self.assertEqual(result["ast"].offset, 2)

    def test_navigation_function_missing_column(self):
        expr = "PREV(5, 2)"
        result = parse_expression_full(expr, context=self.context)
        self.assertTrue(
            any("requires at least one column reference" in e for e in result["errors"]),
            "Navigation function missing column reference error not reported"
        )

    def test_navigation_function_negative_offset(self):
        expr = "PREV(A.totalprice, -1)"
        result = parse_expression_full(expr, context=self.context)
        self.assertTrue(
            any("Navigation offset cannot be negative" in e for e in result["errors"]),
            "Negative offset error not reported"
        )

if __name__ == '__main__':
    unittest.main()

