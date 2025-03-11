import unittest
from src.ast.match_recognize_ast import MatchRecognizeAST
from src.validator.match_recognize_validator import validate_match_recognize_ast

class TestValidator(unittest.TestCase):
    def test_missing_clauses(self):
        ast = MatchRecognizeAST()
        errors = validate_match_recognize_ast(ast)
        self.assertTrue(len(errors) >= 3)  # Expecting errors for missing PARTITION BY, ORDER BY, etc.

if __name__ == '__main__':
    unittest.main()
