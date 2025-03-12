import unittest
from src.ast.match_recognize_ast import MatchRecognizeAST
from src.validator.match_recognize_validator import validate_match_recognize_ast

class TestValidator(unittest.TestCase):
    def test_missing_clauses(self):
        ast = MatchRecognizeAST()
        errors = validate_match_recognize_ast(ast)
        self.assertGreaterEqual(len(errors), 4)

if __name__ == '__main__':
    unittest.main()
