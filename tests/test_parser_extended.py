# tests/test_parser_comprehensive.py

import unittest
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full
from src.parser.context import ParserContext
from src.parser.error_handler import ErrorHandler

class ComprehensiveExpressionTests(unittest.TestCase):
    def setUp(self):
        self.context = ParserContext(ErrorHandler())

    def test_identifier(self):
        result = parse_expression_full("A", context=self.context)
        self.assertEqual(result["ast"].type, "identifier")
        self.assertEqual(result["ast"].value, "A")

    def test_number_literal(self):
        result = parse_expression_full("12345", context=self.context)
        self.assertEqual(result["ast"].type, "literal")
        self.assertEqual(result["ast"].value, "12345")

    def test_string_literal(self):
        result = parse_expression_full("'test'", context=self.context)
        self.assertEqual(result["ast"].type, "literal")
        self.assertEqual(result["ast"].value, "'test'")

    def test_simple_arithmetic(self):
        result = parse_expression_full("A + 5", context=self.context)
        self.assertEqual(result["ast"].type, "binary")
        self.assertEqual(result["ast"].operator, "+")

    def test_operator_precedence(self):
        result = parse_expression_full("A + B * C", context=self.context)
        # Expect multiplication to be performed before addition.
        self.assertEqual(result["ast"].children[1].operator, "*")

    def test_nested_parentheses(self):
        result = parse_expression_full("(A + (B * C))", context=self.context)
        self.assertEqual(result["ast"].type, "binary")
        self.assertEqual(len(result["errors"]), 0)

    def test_missing_parenthesis(self):
        result = parse_expression_full("A + (B * C", context=self.context)
        self.assertTrue(any("Expected ')'" in e for e in result["errors"]))

    def test_unexpected_token(self):
        result = parse_expression_full("A + ?", context=self.context)
        self.assertTrue(any("Unexpected token" in e for e in result["errors"]))

    def test_function_call_valid(self):
        result = parse_expression_full("sum(A.totalprice)", context=self.context)
        self.assertEqual(result["ast"].type, "aggregate")
        self.assertEqual(result["ast"].value.lower(), "sum")

    def test_function_call_without_parenthesis(self):
        result = parse_expression_full("sum A.totalprice", context=self.context)
        self.assertTrue(any("must be followed by '('" in e for e in result["errors"]))

    def test_direct_nested_aggregate(self):
        result = parse_expression_full("avg(sum(A.totalprice))", context=self.context)
        self.assertTrue(any("Nested aggregate functions are not allowed" in e for e in result["errors"]))

    def test_aggregate_inside_arithmetic(self):
        result = parse_expression_full("avg(A.totalprice) + sum(B.discount)", context=self.context)
        # Aggregates nested within arithmetic operations are allowed.
        self.assertEqual(result["errors"], [])

    def test_navigation_function_valid(self):
        result = parse_expression_full("PREV(A.totalprice, 1)", context=self.context)
        self.assertEqual(result["ast"].type, "navigation")

    def test_navigation_function_invalid_reference(self):
        result = parse_expression_full("PREV(123, 1)", context=self.context)
        self.assertTrue(any("requires at least one column reference" in e for e in result["errors"]))

    def test_classifier_function(self):
        result = parse_expression_full("CLASSIFIER(A)", context=self.context)
        self.assertEqual(result["ast"].type, "classifier")

    def test_match_number_function(self):
        result = parse_expression_full("MATCH_NUMBER()", context=self.context)
        self.assertEqual(result["ast"].type, "match_number")

    def test_semantics_final_outside_measures(self):
        # FINAL semantics are only allowed in a MEASURES clause.
        result = parse_expression_full("FINAL (A + 5)", in_measures_clause=False, context=self.context)
        self.assertTrue(any("FINAL semantics are not allowed" in e for e in result["errors"]))

class ComprehensivePatternTests(unittest.TestCase):
    def setUp(self):
        self.context = ParserContext(ErrorHandler())

    def test_empty_pattern(self):
        result = parse_pattern_full("", context=self.context)
        self.assertEqual(result["ast"].type, "empty")

    def test_literal_pattern(self):
        result = parse_pattern_full("A", context=self.context)
        self.assertEqual(result["ast"].type, "literal")
        self.assertEqual(result["ast"].value, "A")

    def test_quantifier_plus(self):
        result = parse_pattern_full("A+", context=self.context)
        self.assertEqual(result["ast"].type, "quantifier")
        self.assertEqual(result["ast"].quantifier, "+")

    def test_quantifier_star(self):
        result = parse_pattern_full("B*", context=self.context)
        self.assertEqual(result["ast"].type, "quantifier")
        self.assertEqual(result["ast"].quantifier, "*")

    def test_quantifier_question(self):
        result = parse_pattern_full("C?", context=self.context)
        self.assertEqual(result["ast"].type, "quantifier")
        self.assertEqual(result["ast"].quantifier, "?")

    def test_concatenation(self):
        result = parse_pattern_full("A B C", context=self.context)
        self.assertEqual(result["ast"].type, "concatenation")
        self.assertEqual(len(result["ast"].children), 3)

    def test_pattern_with_parentheses(self):
        result = parse_pattern_full("(A+ B?)", context=self.context)
        self.assertIn(result["ast"].type, ["concatenation", "literal", "quantifier"])

class ComprehensiveMatchRecognizeTests(unittest.TestCase):
    def setUp(self):
        self.context = ParserContext(ErrorHandler())

    def test_full_match_recognize_scenario(self):
        # Simulate a full MATCH_RECOGNIZE clause by parsing an expression and a pattern.
        expression = "avg(A.totalprice) + sum(B.discount)"
        pattern = "A+ B*"
        expr_result = parse_expression_full(expression, context=self.context)
        pat_result = parse_pattern_full(pattern, context=self.context)
        self.assertNotEqual(expr_result["ast"].type, "error", "Expression parsing failed")
        self.assertNotEqual(pat_result["ast"].type, "empty", "Pattern parsing failed")
        self.assertEqual(expr_result["errors"], [])
        self.assertEqual(pat_result["errors"], [])

    def test_match_recognize_with_subset(self):
        # Test pattern parsing with subset definitions provided in context.
        subset_mapping = {"grp": ["A", "B"]}
        result = parse_pattern_full("A B", subset_mapping=subset_mapping, context=self.context)
        self.assertIn("A", result["pattern_variables"])
        self.assertIn("B", result["pattern_variables"])

if __name__ == '__main__':
    unittest.main()
