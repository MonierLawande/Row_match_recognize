# src/parser/pattern_parser.py

from typing import Dict, Any, Optional, List, Set, Tuple
from src.ast.pattern_ast import PatternAST
from .token_stream import Token, TokenStream
from .error_handler import ErrorHandler
from .context import ParserContext
from .tokenizer import Tokenizer

class PatternParser:
    """
    A recursive descent parser for pattern expressions in MATCH_RECOGNIZE.
    """
    
    def __init__(self, pattern_text: str, context: Optional[ParserContext] = None):
        self.pattern_text = pattern_text
        
        # Use provided context or create a new one
        if context:
            self.context = context
        else:
            self.context = ParserContext(ErrorHandler())
            
        # Create token stream
        self.tokens = self._create_token_stream(pattern_text)
        
        # Track pattern variables
        self.pattern_variables = set()
        
    def _create_token_stream(self, text: str) -> TokenStream:
        return Tokenizer.create_token_stream(text, self._determine_token_type)
        
    def _determine_token_type(self, token: str) -> str:
        """Determine the type of a token in pattern syntax"""
        if token in ['(', ')', '{', '}', '[', ']', '^', '$', '-']:
            return 'SPECIAL'
        elif token in ['*', '+', '?']:
            return 'QUANTIFIER'
        elif token in ['|', ',']:
            return 'OPERATOR'
        elif token.isalnum():  # Pattern variables are alphanumeric
            return 'VARIABLE'
        else:
            return 'UNKNOWN'
            
    def parse(self) -> PatternAST:
        """Parse the pattern and return the AST"""
        try:
            # Remove outer parentheses if present
            pattern_text = self.pattern_text.strip()
            if pattern_text.startswith('(') and pattern_text.endswith(')'):
                pattern_text = pattern_text[1:-1].strip()
                
            # Parse the pattern
            parts = pattern_text.split()
            if not parts:
                return PatternAST(type="empty")
                
            # Create a concatenation node for multiple parts
            if len(parts) > 1:
                children = []
                for part in parts:
                    children.append(self._parse_part(part))
                return PatternAST(
                    type="concatenation",
                    children=children,
                    line=1,
                    column=1
                )
            else:
                # Single part pattern
                return self._parse_part(parts[0])
                
        except Exception as e:
            # Add error to error handler if not already added
            if not self.context.error_handler.has_errors():
                self.context.error_handler.add_error(
                    f"Error parsing pattern: {str(e)}",
                    0, 0
                )
            # Return a minimal valid AST to allow processing to continue
            return PatternAST(type="empty")
            
    def _parse_part(self, part: str) -> PatternAST:
        """Parse a single part of the pattern"""
        # Check for quantifiers
        if part.endswith('+'):
            var_name = part[:-1]
            self.pattern_variables.add(var_name)
            return PatternAST(
                type="quantifier",
                quantifier="+",
                children=[PatternAST(
                    type="literal",
                    value=var_name,
                    line=1,
                    column=1
                )],
                line=1,
                column=1
            )
        elif part.endswith('*'):
            var_name = part[:-1]
            self.pattern_variables.add(var_name)
            return PatternAST(
                type="quantifier",
                quantifier="*",
                children=[PatternAST(
                    type="literal",
                    value=var_name,
                    line=1,
                    column=1
                )],
                line=1,
                column=1
            )
        elif part.endswith('?'):
            var_name = part[:-1]
            self.pattern_variables.add(var_name)
            return PatternAST(
                type="quantifier",
                quantifier="?",
                children=[PatternAST(
                    type="literal",
                    value=var_name,
                    line=1,
                    column=1
                )],
                line=1,
                column=1
            )
        else:
            # Regular pattern variable
            self.pattern_variables.add(part)
            return PatternAST(
                type="literal",
                value=part,
                line=1,
                column=1
            )
            
    def get_pattern_variables(self) -> Set[str]:
        """Get the set of pattern variables found during parsing"""
        return self.pattern_variables

def parse_pattern(pattern_text: str, context: Optional[ParserContext] = None) -> PatternAST:
    """Parse a pattern and return the AST"""
    parser = PatternParser(pattern_text, context)
    return parser.parse()

def parse_pattern_full(pattern_text: str, subset_mapping=None, context: Optional[ParserContext] = None) -> Dict[str, Any]:
    """Parse a pattern and return both raw text and AST"""
    if context is None:
        context = ParserContext(ErrorHandler())
        
    # Add subset mappings to context if provided
    if subset_mapping:
        for subset_name, members in subset_mapping.items():
            context.add_subset_definition(subset_name, set(members))
            
    parser = PatternParser(pattern_text, context)
    ast = parser.parse()
    
    # Add pattern variables to context
    for var in parser.get_pattern_variables():
        context.add_pattern_variable(var)
        
    return {
        "raw": pattern_text,
        "ast": ast,
        "errors": context.error_handler.get_formatted_errors(),
        "warnings": context.error_handler.get_formatted_warnings(),
        "pattern_variables": parser.get_pattern_variables()
    }
