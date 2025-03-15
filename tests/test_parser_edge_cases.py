import unittest
from src.parser.match_recognize_parser import MatchRecognizeParser

class TestMatchRecognizeParser(unittest.TestCase):
    def setUp(self):
        self.parser = MatchRecognizeParser()
    
    def test_valid_match_recognize(self):
        query = """
        MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY timestamp
            MEASURES A.price AS start_price, LAST(B.price) AS end_price
            PATTERN (A B+)
            DEFINE B AS B.price > A.price
        )
        """
        result = self.parser.parse_query(query)
        self.assertFalse(result["errors"], f"Unexpected errors: {result['errors']}")
        self.assertEqual(result["match_recognize"]["pattern"], "A B+")
        self.assertEqual(len(result["define_expressions"]), 1)
    
    def test_query_without_match_recognize(self):
        query = "SELECT * FROM sales"
        result = self.parser.parse_query(query)
        self.assertIn("Query does not contain a MATCH_RECOGNIZE clause", result["errors"])
    
    def test_missing_pattern(self):
        query = """
        MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY timestamp
            MEASURES A.price AS start_price
            DEFINE B AS B.price > A.price
        )
        """
        result = self.parser.parse_query(query)
        self.assertTrue(any("PATTERN clause is required" in err for err in result["errors"]))

    def test_invalid_pattern_syntax(self):
        query = """
        MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY timestamp
            MEASURES A.price AS start_price
            PATTERN (A @ B)
            DEFINE B AS B.price > A.price
        )
        """
        result = self.parser.parse_query(query)
        self.assertTrue(any("Unknown token '@'" in err for err in result["errors"]))

    def test_multiple_define_clauses(self):
        query = """
        MATCH_RECOGNIZE (
            PARTITION BY category
            ORDER BY timestamp
            MEASURES A.price AS start_price, LAST(B.price) AS end_price
            PATTERN (A B+)
            DEFINE B AS B.price > A.price, C AS C.volume < 100
        )
        """
        result = self.parser.parse_query(query)
        self.assertEqual(len(result["define_expressions"]), 2)

if __name__ == '__main__':
    unittest.main()
