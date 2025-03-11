import unittest
from src.ast.expression_ast import ExpressionAST, visualize_expression_ast
from src.ast.pattern_ast import PatternAST, visualize_pattern

class TestASTVisualization(unittest.TestCase):
    def test_expression_visualization(self):
        ast = ExpressionAST(type="literal", value="42")
        visualization = visualize_expression_ast(ast)
        self.assertIn("literal", visualization)
        self.assertIn("42", visualization)
    def test_pattern_visualization(self):
        ast = PatternAST(type="literal", value="A")
        visualization = visualize_pattern(ast)
        self.assertIn("literal", visualization)
        self.assertIn("A", visualization)

if __name__ == '__main__':
    unittest.main()
