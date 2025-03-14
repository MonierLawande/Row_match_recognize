import unittest
import json
from src.parser.sql_parser import parse_sql_query
from src.ast.ast_processor import ASTProcessor

class TestIntegration(unittest.TestCase):
    def test_full_pipeline(self):
        test_query = """
        SELECT *
        FROM Orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_time
            MEASURES
                A.order_id AS start_order,
                B.order_id AS end_order,
                COUNT(*) AS order_count
            ONE ROW PER MATCH
            PATTERN (A B+)
            DEFINE
                A AS A.amount > 100,
                B AS B.amount > A.amount
        );
        """
        # Parse the SQL query.
        parse_result = parse_sql_query(test_query)
        self.assertFalse(parse_result.get("errors"), f"Parsing errors: {parse_result.get('errors')}")
        
        # Process the parse tree into an AST.
        ast_processor = ASTProcessor()
        ast_result = ast_processor.process_parse_tree(parse_result)
        self.assertFalse(ast_result.get("errors"), f"AST processing errors: {ast_result.get('errors')}")
        
        # Convert AST to JSON for easier inspection.
        ast_json = json.dumps(ast_result["ast"], default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o), indent=2)
        
        # Check that the AST contains expected top-level keys.
        self.assertIn("partition_by", ast_json)
        self.assertIn("order_by", ast_json)
        self.assertIn("measures", ast_json)
        self.assertIn("pattern", ast_json)
        self.assertIn("define", ast_json)
        
if __name__ == '__main__':
    unittest.main()
