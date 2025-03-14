# tests/test_parser_extended.py

import unittest
from src.parser.expression_parser import parse_expression_full
from src.parser.context import ParserContext
from src.parser.error_handler import ErrorHandler

class TestExtendedExpressionParser(unittest.TestCase):
    
    def setUp(self):
        # Create a fresh context for each test.
        self.context = ParserContext(ErrorHandler())
    
    def test_malformed_missing_parenthesis(self):
        result = parse_expression_full("A + (B * 2", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Expected ')'" in errors or "end of expression" in errors,
                        "Should report missing closing parenthesis")
    
    def test_unexpected_token(self):
        result = parse_expression_full("A + ?", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Unexpected token" in errors,
                        "Should report unexpected token '?'")
    
    def test_semantics_running_aggregate(self):
        result = parse_expression_full("RUNNING avg(A.totalprice)", context=self.context)
        ast = result["ast"]
        self.assertEqual(ast.semantics, "RUNNING")
        self.assertEqual(ast.type, "aggregate")
    
    def test_final_semantics_in_non_measures(self):
        # Simulate non-measures context (in_measures_clause = False)
        result = parse_expression_full("FINAL count(*)", in_measures_clause=False, context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("FINAL semantics are not allowed" in errors,
                        "Should report error for FINAL semantics outside measures")
    
    def test_nested_aggregate_not_allowed(self):
        result = parse_expression_full("avg(sum(A.totalprice))", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Nested aggregate functions are not allowed" in errors,
                        "Should report nested aggregates error")
    
    def test_complex_nested_expression(self):
        result = parse_expression_full("avg(PREV(A.totalprice, 1) + (B.totalprice * 2))", context=self.context)
        ast = result["ast"]
        self.assertEqual(ast.type, "aggregate")
        binary_node = ast.children[0]
        nav_found = any(child.type == "navigation" for child in binary_node.children)
        self.assertTrue(nav_found, "Should contain a navigation function in nested expression")
    
    def test_navigation_missing_offset(self):
        # Test that if no offset is provided, offset defaults to 0.
        result = parse_expression_full("PREV(A.totalprice)", context=self.context)
        ast = result["ast"]
        self.assertEqual(ast.type, "navigation")
        self.assertEqual(ast.offset, 0, "Offset should default to 0 if not specified")
    
    def test_navigation_negative_offset(self):
        result = parse_expression_full("PREV(A.totalprice, -1)", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Navigation offset cannot be negative" in errors,
                        "Should report negative offset error")
    
    def test_navigation_missing_column_reference(self):
        # Provide an argument to a navigation function that is just 'A' (no column reference)
        result = parse_expression_full("PREV(A, 2)", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("requires at least one column reference" in errors,
                        "Should report error when navigation function lacks column reference")
    
    def test_mixing_classifier_in_aggregate(self):
        # Depending on design, mixing classifier inside aggregate might not be allowed.
        result = parse_expression_full("avg(CLASSIFIER(A))", context=self.context)
        errors = " ".join(result["errors"])
        # Expect an error related to aggregate arguments (adjust message as needed)
        self.assertTrue("Aggregate function arguments" in errors or "not allowed" in errors,
                        "Should report error for mixing classifier in aggregate")
    
    def test_empty_input(self):
        result = parse_expression_full("", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue(len(errors) > 0, "Should report error for empty input")
    
    def test_extra_tokens_after_expression(self):
        result = parse_expression_full("42 extra", context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Unexpected token" in errors,
                        "Should report error for extra tokens after expression")
    
    def test_cache_functionality(self):
        result1 = parse_expression_full("A + 5", context=self.context)
        result2 = parse_expression_full("A + 5", context=self.context)
        # Check that the AST objects are equal (or identical, if caching returns the same object)
        self.assertEqual(result1["ast"].__dict__, result2["ast"].__dict__,
                         "Cached AST should be reused for identical input")

    def test_deeply_nested_expression(self):
        # A deeply nested combination of aggregates, navigation, and arithmetic.
        expr = "avg(PREV(A.totalprice, 1) + (B.totalprice * 2) - (sum(C.discount) / 3))"
        result = parse_expression_full(expr, context=self.context)
        ast = result["ast"]
        # Ensure the outermost function is an aggregate.
        self.assertEqual(ast.type, "aggregate", "The outer function should be an aggregate")
        # Check that the error list is empty.
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")

    def test_invalid_final_semantics_on_identifier(self):
        expr = "FINAL A.totalprice"
        result = parse_expression_full(expr, in_measures_clause=True, context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("FINAL semantics can only be applied" in errors,
                        "Should report error for FINAL semantics on non-aggregate/navigation")

    def test_function_call_without_parenthesis(self):
        expr = "avg A.totalprice"
        result = parse_expression_full(expr, context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("must be followed by '('" in errors,
                        "Should report missing '(' after function name")

    def test_navigation_without_column(self):
        # Navigation without a column reference (just A, not A.column)
        expr = "PREV(A, 2)"
        result = parse_expression_full(expr, context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("requires at least one column reference" in errors,
                        "Should report error when navigation function lacks column reference")

    def test_negative_navigation_offset(self):
        expr = "PREV(A.totalprice, -5)"
        result = parse_expression_full(expr, context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Navigation offset cannot be negative" in errors,
                        "Should report error for negative navigation offset")

    def test_unexpected_token_in_expression(self):
        expr = "A + ?"
        result = parse_expression_full(expr, context=self.context)
        errors = " ".join(result["errors"])
        self.assertTrue("Unexpected token" in errors,
                        "Should report error for unexpected token '?'")

    def test_cache_reuse(self):
        expr = "A + 5"
        result1 = parse_expression_full(expr, context=self.context)
        result2 = parse_expression_full(expr, context=self.context)
        self.assertEqual(result1["ast"].__dict__, result2["ast"].__dict__,
                         "Cached AST should be reused for identical input")

   
if __name__ == '__main__':
    unittest.main()
