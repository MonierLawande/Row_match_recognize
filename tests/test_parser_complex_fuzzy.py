# tests/test_parser.py

import unittest
from src.parser.parser_util import ErrorHandler, ParserContext

# Example: a stub function that "parses" an expression and uses the context.
# In your real parser module, you would import the real parser.
def dummy_parse_expression(expression: str, context: ParserContext):
    # This dummy function simulates parsing.
    # For demonstration, it will add an error if the expression is empty
    # and otherwise return a dummy parse tree (e.g., a dictionary).
    if not expression.strip():
        context.error_handler.add_error("Empty expression", 1, 1)
        return None
    # Otherwise, return a dummy parse tree that includes the raw expression.
    return {"type": "dummy_expression", "raw": expression}

class TestParserIndependent(unittest.TestCase):
    def setUp(self):
        # Set up a new error handler and parser context for each test.
        self.error_handler = ErrorHandler()
        self.context = ParserContext(self.error_handler)

    def test_empty_expression(self):
        # Test that an empty expression returns an error.
        result = dummy_parse_expression("", self.context)
        self.assertIsNone(result)
        self.assertTrue(self.error_handler.has_errors())
        formatted_errors = self.error_handler.get_formatted_errors()
        self.assertIn("Empty expression", formatted_errors[0])

    def test_valid_expression(self):
        # Test that a valid expression returns a dummy parse tree and no errors.
        expression = "A + B"
        result = dummy_parse_expression(expression, self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result["raw"], expression)
        self.assertFalse(self.error_handler.has_errors())

    def test_scope_limit(self):
        # Test that entering too many scopes produces an error.
        for _ in range(self.context.max_nesting + 1):
            self.context.enter_scope()
        self.assertTrue(self.error_handler.has_errors())
        formatted_errors = self.error_handler.get_formatted_errors()
        self.assertIn("Maximum nesting level", formatted_errors[0])
        # Cleanup: exit scopes back to normal.
        while self.context.nesting_level > 0:
            self.context.exit_scope()

if __name__ == '__main__':
    unittest.main()
