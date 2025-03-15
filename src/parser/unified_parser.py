from typing import Dict, Any, Optional
from src.parser.config import ParserConfig
from src.parser.parser_util import ErrorHandler, ParserContext
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full

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
        # Stub: implement MATCH_RECOGNIZE parsing as needed.
        return {
            "parse_tree": None,
            "errors": ["MATCH_RECOGNIZE parsing not yet implemented in unified parser"]
        }
