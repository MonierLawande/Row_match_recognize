# src/parser/unified_parser.py
from typing import Dict, Any, Optional, List
from src.parser.config import ParserConfig
from src.parser.parser_util import ErrorHandler, ParserContext
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full
from src.parser.antlr_parser import parse_input, extract_match_recognize_details

class UnifiedParser:
    """Provides a single interface to parse expressions and patterns."""
    def __init__(self, config: Optional[ParserConfig] = None):
        self.config = config or ParserConfig()
        self.error_handler = ErrorHandler()
        self.context = ParserContext(self.error_handler)
        
    def parse_expression(self, expr_text: str, in_measures_clause: bool = True) -> Dict[str, Any]:
        self.context.in_measures_clause = in_measures_clause
        return parse_expression_full(expr_text, in_measures_clause, self.context)
        
    def parse_pattern(self, pattern_text: str, subset_mapping=None) -> Dict[str, Any]:
        return parse_pattern_full(pattern_text, subset_mapping, self.context)
        
    def parse_match_recognize(self, query: str) -> Dict[str, Any]:
        """
        Parse a SQL query with a MATCH_RECOGNIZE clause and return detailed information.
        
        Args:
            query (str): The SQL query containing a MATCH_RECOGNIZE clause
            
        Returns:
            Dict[str, Any]: A dictionary containing:
                - sql_parse_tree: The full SQL parse tree
                - errors: Any parsing errors
                - match_recognize: Details of the MATCH_RECOGNIZE clause
                - pattern_analysis: Analysis of the pattern
                - define_expressions: Analysis of the DEFINE expressions
                - measure_expressions: Analysis of the MEASURE expressions
        """
        # Parse the SQL query
        parse_tree, parser, errors = parse_input(query)
        
        if errors:
            return {
                "sql_parse_tree": None,
                "errors": errors,
                "match_recognize": None,
                "pattern_analysis": None,
                "define_expressions": None,
                "measure_expressions": None
            }
        
        # Extract MATCH_RECOGNIZE details
        match_recognize_details = extract_match_recognize_details(parse_tree)
        
        if not match_recognize_details or 'error' in match_recognize_details:
            error_msg = match_recognize_details.get('error', "Failed to extract MATCH_RECOGNIZE clause") if match_recognize_details else "No MATCH_RECOGNIZE clause found"
            return {
                "sql_parse_tree": parse_tree,
                "errors": [error_msg],
                "match_recognize": None,
                "pattern_analysis": None,
                "define_expressions": None,
                "measure_expressions": None
            }
        
        # Parse the pattern
        pattern_text = match_recognize_details['pattern']
        pattern_result = self.parse_pattern(pattern_text)
        
        # Parse expressions from the DEFINE clause
        define_expressions = []
        for define in match_recognize_details['define_clauses']:
            expr_result = self.parse_expression(define['expression'], in_measures_clause=False)
            define_expressions.append({
                'variable': define['variable'],
                'expression': define['expression'],
                'analysis': expr_result
            })
        
        # Parse expressions from the MEASURES clause
        measure_expressions = []
        for measure in match_recognize_details['measures']:
            expr_result = self.parse_expression(measure['expression'], in_measures_clause=True)
            measure_expressions.append({
                'expression': measure['expression'],
                'alias': measure['alias'],
                'analysis': expr_result
            })
        
        # Collect all errors
        all_errors = errors.copy()
        if pattern_result.get("errors"):
            all_errors.extend([f"Pattern error: {err}" for err in pattern_result["errors"]])
        
        for define_expr in define_expressions:
            if define_expr['analysis'].get("errors"):
                all_errors.extend([f"Define error ({define_expr['variable']}): {err}" for err in define_expr['analysis']["errors"]])
        
        for measure_expr in measure_expressions:
            if measure_expr['analysis'].get("errors"):
                all_errors.extend([f"Measure error ({measure_expr['alias']}): {err}" for err in measure_expr['analysis']["errors"]])
        
        return {
            "sql_parse_tree": parse_tree,
            "errors": all_errors,
            "match_recognize": match_recognize_details,
            "pattern_analysis": pattern_result,
            "define_expressions": define_expressions,
            "measure_expressions": measure_expressions
        }
