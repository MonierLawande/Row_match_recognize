# src/parser/pattern_parser.py

from typing import Dict, Any, Optional, List, Set, Tuple
from src.parser.parse_tree import ParseTreeNode
from .parser_util import ErrorHandler, ParserContext
from .tokenizer import Token, TokenStream, Tokenizer
class PatternParser:
    """
    A recursive descent parser for pattern expressions in MATCH_RECOGNIZE.
    This parser produces a parse tree.
    """
    
    def __init__(self, pattern_text: str, context: Optional[ParserContext] = None):
        self.pattern_text = pattern_text
        
        if context:
            self.context = context
        else:
            self.context = ParserContext(ErrorHandler())
            
        self.tokens = self._create_token_stream(pattern_text)
        self.pattern_variables = set()
        
    def _create_token_stream(self, text: str) -> TokenStream:
        return Tokenizer.create_token_stream(text, self._determine_token_type)
        
    def _determine_token_type(self, token: str) -> str:
        """Determine the type of a token in pattern syntax."""
        if token in ['(', ')', '{', '}', '[', ']', '^', '$', '-']:
            return 'SPECIAL'
        elif token in ['*', '+', '?']:
            return 'QUANTIFIER'
        elif token in ['|', ',']:
            return 'OPERATOR'
        elif token.isalnum():
            return 'VARIABLE'
        else:
            return 'UNKNOWN'
            
    def parse(self) -> ParseTreeNode:
        """Parse the pattern and return the parse tree."""
        try:
            pattern_text = self.pattern_text.strip()
            if pattern_text.startswith('(') and pattern_text.endswith(')'):
                pattern_text = pattern_text[1:-1].strip()
                
            parts = pattern_text.split()
            if not parts:
                return ParseTreeNode("empty")
                
            if len(parts) > 1:
                children = []
                for part in parts:
                    children.append(self._parse_part(part))
                return ParseTreeNode(
                    node_type="concatenation",
                    token={"line": 1, "column": 1},
                    children=children
                )
            else:
                return self._parse_part(parts[0])
                
        except Exception as e:
            if not self.context.error_handler.has_errors():
                self.context.error_handler.add_error(
                    f"Error parsing pattern: {str(e)}",
                    0, 0
                )
            return ParseTreeNode("empty")
            
    def _parse_part(self, part: str) -> ParseTreeNode:
        """Parse a single part of the pattern."""
        if part.endswith('+'):
            var_name = part[:-1]
            if not var_name or not var_name.isalnum():
                self.context.error_handler.add_error(
                    f"Invalid quantifier placement in pattern: '{part}'",
                    1, 1
                )
            else:
                self.pattern_variables.add(var_name)
            return ParseTreeNode(
                node_type="quantifier",
                token={"quantifier": "+", "line": 1, "column": 1},
                children=[ParseTreeNode("literal", token={"value": var_name, "line": 1, "column": 1})]
            )
        elif part.endswith('*'):
            var_name = part[:-1]
            if not var_name or not var_name.isalnum():
                self.context.error_handler.add_error(
                    f"Invalid quantifier placement in pattern: '{part}'",
                    1, 1
                )
            else:
                self.pattern_variables.add(var_name)
            return ParseTreeNode(
                node_type="quantifier",
                token={"quantifier": "*", "line": 1, "column": 1},
                children=[ParseTreeNode("literal", token={"value": var_name, "line": 1, "column": 1})]
            )
        elif part.endswith('?'):
            var_name = part[:-1]
            if not var_name or not var_name.isalnum():
                self.context.error_handler.add_error(
                    f"Invalid quantifier placement in pattern: '{part}'",
                    1, 1
                )
            else:
                self.pattern_variables.add(var_name)
            return ParseTreeNode(
                node_type="quantifier",
                token={"quantifier": "?", "line": 1, "column": 1},
                children=[ParseTreeNode("literal", token={"value": var_name, "line": 1, "column": 1})]
            )
        else:
            if not part.isalnum():
                self.context.error_handler.add_error(
                    f"Unknown token in pattern: '{part}'",
                    1, 1
                )
            self.pattern_variables.add(part)
            return ParseTreeNode(
                node_type="literal",
                token={"value": part, "line": 1, "column": 1},
                children=[]
            )
            
    def get_pattern_variables(self) -> Set[str]:
        return self.pattern_variables

def parse_pattern(pattern_text: str, context: Optional[ParserContext] = None) -> ParseTreeNode:
    parser = PatternParser(pattern_text, context)
    return parser.parse()

def parse_pattern_full(pattern_text: str, subset_mapping=None, context: Optional[ParserContext] = None) -> Dict[str, Any]:
    if context is None:
        context = ParserContext(ErrorHandler())
        
    if subset_mapping:
        for subset_name, members in subset_mapping.items():
            context.add_subset_definition(subset_name, set(members))
            
    parser = PatternParser(pattern_text, context)
    tree = parser.parse()
    
    for var in parser.get_pattern_variables():
        context.add_pattern_variable(var)
        
    return {
        "raw": pattern_text,
        "parse_tree": tree,
        "errors": context.error_handler.get_formatted_errors(),
        "warnings": context.error_handler.get_formatted_warnings(),
        "pattern_variables": parser.get_pattern_variables()
    }
