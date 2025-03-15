# src/parser/pattern_parser.py

from typing import Dict, Any, Optional, List, Set, Tuple
from src.parser.parse_tree import ParseTreeNode
from .parser_util import ErrorHandler, ParserContext
from .tokenizer import Token, TokenStream, Tokenizer

class PatternParser:
    """
    A recursive descent parser for pattern expressions in MATCH_RECOGNIZE.
    Produces a parse tree.
    """
    
    def __init__(self, pattern_text: str, context: Optional[ParserContext] = None):
        self.pattern_text = pattern_text
        self.context = context if context else ParserContext(ErrorHandler())
        # Use a punctuation set that includes additional characters for patterns.
        pattern_punctuation = ['(', ')', ',', '+', '-', '*', '/', '.', '=', '>', '<', '!', '|', '?']
        self.tokens: TokenStream = Tokenizer.create_token_stream(pattern_text, self._determine_token_type, punctuation=pattern_punctuation)
        self.current_token = self.tokens.consume()
        self.pattern_variables: Set[str] = set()
    
    def _determine_token_type(self, token: str) -> str:
        if token in ['(', ')', '{', '}', '[', ']', '^', '$']:
            return 'SPECIAL'
        elif token in ['*', '+', '?']:
            return 'QUANTIFIER'
        elif token == '|':
            return 'ALTERNATION'
        elif token == ',':
            return 'OPERATOR'
        elif token.isalnum():
            return 'VARIABLE'
        else:
            return 'UNKNOWN'
    
    def _eat(self, token_value: str):
        if self.current_token and self.current_token.value == token_value:
            self.current_token = self.tokens.consume()
        else:
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.column if self.current_token else 0
            self.context.error_handler.add_error(
                f"Expected token '{token_value}' but got '{self.current_token.value if self.current_token else 'EOF'}'",
                line, col
            )
    
    def parse(self) -> ParseTreeNode:
        return self._parse_pattern()
    
    def _parse_pattern(self) -> ParseTreeNode:
        return self._parse_alternation()
    
    def _parse_alternation(self) -> ParseTreeNode:
        left = self._parse_concatenation()
        while self.current_token and self.current_token.type == 'ALTERNATION':
            self._eat('|')
            right = self._parse_concatenation()
            left = ParseTreeNode("alternation", token={"value": "|"}, children=[left, right])
        return left
    
    def _parse_concatenation(self) -> ParseTreeNode:
        nodes = []
        while self.current_token and self.current_token.value != ')' and self.current_token.type != 'ALTERNATION' and self.current_token.type != 'EOF':
            term = self._parse_term()
            if term:
                nodes.append(term)
        if not nodes:
            return ParseTreeNode("empty")
        if len(nodes) == 1:
            return nodes[0]
        return ParseTreeNode("concatenation", token={"value": "concatenation"}, children=nodes)
    
    def _parse_term(self) -> ParseTreeNode:
        factor = self._parse_factor()
        if self.current_token and self.current_token.type == 'QUANTIFIER':
            quant = self.current_token.value
            self._eat(quant)
            return ParseTreeNode("quantifier", token={"quantifier": quant}, children=[factor])
        return factor
    
    def _parse_factor(self) -> ParseTreeNode:
        if self.current_token and self.current_token.type == 'QUANTIFIER':
            token = self.current_token
            self._eat(token.value)
            self.context.error_handler.add_error(f"Invalid quantifier placement in pattern: '{token.value}'", token.line, token.column)
            return ParseTreeNode("error", token={"value": token.value})
        
        if self.current_token and self.current_token.value == '(':
            self._eat('(')
            node = self._parse_pattern()
            if self.current_token and self.current_token.value == ')':
                self._eat(')')
            else:
                line = self.current_token.line if self.current_token else 0
                col = self.current_token.column if self.current_token else 0
                self.context.error_handler.add_error("Expected ')' after group", line, col)
            return ParseTreeNode("group", token={"value": "group"}, children=[node])
        elif self.current_token and self.current_token.type == 'VARIABLE':
            token = self.current_token
            self._eat(token.value)
            self.pattern_variables.add(token.value)
            return ParseTreeNode("literal", token={"value": token.value, "line": token.line, "column": token.column})
        else:
            if self.current_token:
                token = self.current_token
                self._eat(token.value)
                self.context.error_handler.add_error(f"Unknown token in pattern: '{token.value}'", token.line, token.column)
                return ParseTreeNode("error", token={"value": token.value})
            return ParseTreeNode("empty")
            
def parse_pattern(pattern_text: str, context: Optional[ParserContext] = None) -> ParseTreeNode:
    parser = PatternParser(pattern_text, context)
    return parser.parse()

def parse_pattern_full(pattern_text: str, subset_mapping=None, context: Optional[ParserContext] = None) -> Dict[str, Any]:
    if context is None:
        from .parser_util import ErrorHandler, ParserContext
        context = ParserContext(ErrorHandler())
        
    if subset_mapping:
        for subset_name, members in subset_mapping.items():
            context.add_subset_definition(subset_name, set(members))
            
    parser = PatternParser(pattern_text, context)
    tree = parser.parse()
    
    for var in parser.pattern_variables:
        context.add_pattern_variable(var)
        
    return {
        "raw": pattern_text,
        "parse_tree": tree,
        "errors": context.error_handler.get_formatted_errors(),
        "warnings": context.error_handler.get_formatted_warnings(),
        "pattern_variables": parser.pattern_variables
    }
