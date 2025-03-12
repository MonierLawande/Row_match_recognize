# tests/test_validator.py

import unittest
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full
from src.ast.match_recognize_ast import MatchRecognizeAST
from src.validator.match_recognize_validator import validate_match_recognize

class TestValidator(unittest.TestCase):
    
    def test_pattern_quantifier_validation(self):
        """Test validation of pattern quantifiers"""
        # Test negative minimum
        pattern = parse_pattern_full("A{-1,5}")
        ast = MatchRecognizeAST(pattern=pattern)
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("negative" in err for err in errors))
        
        # Test maximum less than minimum
        pattern = parse_pattern_full("A{5,3}")
        ast = MatchRecognizeAST(pattern=pattern)
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("maximum" in err and "minimum" in err for err in errors))
        
        # Test reluctant quantifier on fixed repetition
        pattern = parse_pattern_full("A{3}?")
        ast = MatchRecognizeAST(pattern=pattern)
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("reluctant" in warn for warn in warnings))
    
    def test_pattern_exclusion_validation(self):
        """Test validation of pattern exclusions"""
        # Test exclusion with ALL ROWS PER MATCH WITH UNMATCHED ROWS
        pattern = parse_pattern_full("A {- B+ -} C")
        ast = MatchRecognizeAST(
            pattern=pattern,
            rows_per_match="ALL ROWS PER MATCH WITH UNMATCHED ROWS"
        )
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("exclusions" in err and "UNMATCHED ROWS" in err for err in errors))
        
        # Test nested exclusions
        pattern = parse_pattern_full("A {- B {- C -} D -} E")
        ast = MatchRecognizeAST(pattern=pattern)
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("nested exclusions" in warn for warn in warnings))
    
    def test_subset_validation(self):
        """Test validation of subset definitions"""
        # Test subset with undefined pattern variable
        pattern = parse_pattern_full("A B+ C+")
        subset = {"X": ["A", "D"]}  # D is not in pattern
        ast = MatchRecognizeAST(pattern=pattern, subset=subset)
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("undefined pattern variable 'D'" in err for err in errors))
        
        # Test subset with single element
        subset = {"X": ["A"]}
        ast = MatchRecognizeAST(pattern=pattern, subset=subset)
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("only one element" in warn for warn in warnings))
        
        # Test empty subset
        subset = {"X": []}
        ast = MatchRecognizeAST(pattern=pattern, subset=subset)
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("empty" in err for err in errors))
    
    def test_navigation_function_validation(self):
        """Test validation of navigation functions"""
        # Test navigation inside aggregate
        expr = parse_expression_full("avg(PREV(A.price))")
        measure = {"expression": expr, "alias": "avg_prev"}
        ast = MatchRecognizeAST(measures=[measure])
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("navigation" in err and "inside aggregate" in err for err in errors))
        
        # Test negative offset
        expr = parse_expression_full("PREV(A.price, -1)")
        measure = {"expression": expr, "alias": "prev_neg"}
        ast = MatchRecognizeAST(measures=[measure])
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("negative offset" in err for err in errors))
        
        # Test multiple pattern variables
        expr = parse_expression_full("PREV(A.price + B.price)")
        measure = {"expression": expr, "alias": "prev_multi"}
        ast = MatchRecognizeAST(measures=[measure])
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("multiple pattern variables" in err for err in errors))
    
    def test_aggregate_function_validation(self):
        """Test validation of aggregate functions"""
        # Test nested aggregates
        expr = parse_expression_full("avg(sum(A.price))")
        measure = {"expression": expr, "alias": "avg_sum"}
        ast = MatchRecognizeAST(measures=[measure])
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("nested aggregate" in err for err in errors))
        
        # Test navigation in aggregate
        expr = parse_expression_full("sum(PREV(A.price))")
        measure = {"expression": expr, "alias": "sum_prev"}
        ast = MatchRecognizeAST(measures=[measure])
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("navigation" in err and "not allowed" in err for err in errors))
        
        # Test multiple pattern variables
        expr = parse_expression_full("sum(A.price + B.price)")
        measure = {"expression": expr, "alias": "sum_multi"}
        ast = MatchRecognizeAST(measures=[measure])
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("multiple pattern variables" in err for err in errors))
    
    def test_final_semantics_validation(self):
        """Test validation of FINAL semantics"""
        # Test FINAL in DEFINE clause
        expr = parse_expression_full("FINAL avg(A.price)")
        define = {"variable": "A", "condition": expr}
        ast = MatchRecognizeAST(define=[define])
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("FINAL semantics not allowed" in err for err in errors))
        
        # Test FINAL in MEASURES clause (should be allowed)
        expr = parse_expression_full("FINAL avg(A.price)")
        measure = {"expression": expr, "alias": "final_avg"}
        ast = MatchRecognizeAST(measures=[measure])
        errors, warnings = validate_match_recognize(ast)
        self.assertFalse(any("FINAL semantics not allowed" in err for err in errors))
    
    def test_after_match_skip_validation(self):
        """Test validation of AFTER MATCH SKIP clause"""
        # Test skip to undefined variable
        pattern = parse_pattern_full("A B+ C+")
        ast = MatchRecognizeAST(
            pattern=pattern,
            after_match_skip="AFTER MATCH SKIP TO LAST D"  # D is not in pattern
        )
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("undefined variable" in err for err in errors))
        
        # Test skip to first variable (potential infinite loop)
        ast = MatchRecognizeAST(
            pattern=pattern,
            after_match_skip="AFTER MATCH SKIP TO FIRST A"
        )
        errors, warnings = validate_match_recognize(ast)
        self.assertTrue(any("infinite loop" in err for err in errors))

if __name__ == '__main__':
    unittest.main()
