# src/parser/unified_parser.py

from typing import Dict, Any, Optional
from src.parser.config import ParserConfig
from src.parser.context import ParserContext
from src.parser.error_handler import ErrorHandler
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full
from src.ast.validator import UnifiedValidator
from src.ast.ast_builder import build_enhanced_match_recognize_ast

class UnifiedParser:
    """Unified interface for all parsing operations"""
    
    def __init__(self, config: Optional[ParserConfig] = None):
        self.config = config or ParserConfig()
        self.error_handler = ErrorHandler()
        self.context = ParserContext(self.error_handler)
        self.validator = UnifiedValidator()
        
    def parse_expression(self, expr_text: str, in_measures_clause: bool = True) -> Dict[str, Any]:
        """Parse an expression with full validation"""
        self.context.in_measures_clause = in_measures_clause
        result = parse_expression_full(expr_text, in_measures_clause, self.context)
        return result
        
    def parse_pattern(self, pattern_text: str, subset_mapping=None) -> Dict[str, Any]:
        """Parse a pattern with full validation"""
        result = parse_pattern_full(pattern_text, subset_mapping, self.context)
        return result
        
    def parse_match_recognize(self, query: str) -> Dict[str, Any]:
        """Parse a complete MATCH_RECOGNIZE clause"""
        ast, errors = build_enhanced_match_recognize_ast(query)
        
        if errors:
            return {
                "ast": None,
                "errors": errors,
                "warnings": []
            }
            
        # Perform additional validation
        validation_result = self.validator.validate_match_recognize(ast)
        
        return {
            "ast": ast,
            "errors": validation_result["errors"],
            "warnings": validation_result["warnings"]
        }
