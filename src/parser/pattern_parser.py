# src/parser/pattern_parser.py

from typing import Dict, Any, Optional, List, Set, Tuple
from src.parser.parse_tree import ParseTreeNode
from .parser_util import ErrorHandler, ParserContext
from .tokenizer import Token, TokenStream, Tokenizer

class PatternParser:
    """
    A recursive descent parser for pattern expressions in MATCH_RECOGNIZE.
    Produces a parse tree with improved error handling.
    """
    
    def __init__(self, pattern_text: str, context: Optional[ParserContext] = None):
        self.pattern_text = pattern_text.strip()
        self.context = context if context else ParserContext(ErrorHandler())
        
        # Define allowed punctuation in pattern expressions.
        pattern_punctuation = ['(', ')', '|', '+', '*', '?']
        self.tokens: TokenStream = Tokenizer.create_token_stream(
            pattern_text, self._determine_token_type, punctuation=pattern_punctuation
        )
        self.current_token = self.tokens.consume()  # Start with the first token
        self.pattern_variables: Set[str] = set()
    
    def _determine_token_type(self, token: str) -> str:
        """
        Determines the token type based on the input token.
        """
        if token in ['(', ')']:
            return 'PAREN'
        elif token in ['*', '+', '?']:
            return 'QUANTIFIER'
        elif token == '|':
            return 'ALTERNATION'
        elif token.isalnum():
            return 'VARIABLE'
        else:
            return 'UNKNOWN'

    def _eat(self, expected_value: str):
        """
        Consumes the current token if it matches the expected value.
        Otherwise, records an error.
        """
        if self.current_token and self.current_token.value == expected_value:
            self.current_token = self.tokens.consume()
        else:
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.column if self.current_token else 0
            error_msg = f"Expected '{expected_value}', but got '{self.current_token.value if self.current_token else 'EOF'}'"
            self.context.error_handler.add_error(error_msg, line, col)
    
    def parse(self) -> ParseTreeNode:
        """
        Parses the pattern and returns a parse tree.
        """
        if not self.pattern_text:
            self.context.error_handler.add_error("Pattern is empty")
            return ParseTreeNode("error", token={"value": "Empty pattern"})

        return self._parse_pattern()
    
    def _parse_pattern(self) -> ParseTreeNode:
        """
        Entry point for parsing the pattern, handling alternations (`|`).
        """
        return self._parse_alternation()
    
    def _parse_alternation(self) -> ParseTreeNode:
        """
        Handles alternations (`A | B`).
        """
        left = self._parse_concatenation()
        while self.current_token and self.current_token.type == 'ALTERNATION':
            self._eat('|')
            right = self._parse_concatenation()
            left = ParseTreeNode("alternation", token={"value": "|"}, children=[left, right])
        return left
    
    def _parse_concatenation(self) -> ParseTreeNode:
        """
        Parses concatenated patterns (e.g., `A B C`).
        """
        nodes = []
        while self.current_token and self.current_token.value not in [')', '|', 'EOF']:
            term = self._parse_term()
            if term:
                nodes.append(term)

        if not nodes:
            return ParseTreeNode("empty")

        return nodes[0] if len(nodes) == 1 else ParseTreeNode("concatenation", children=nodes)
    
    def _parse_term(self) -> ParseTreeNode:
        """
        Parses individual pattern elements (e.g., `A+`, `B*`, `C?`).
        """
        factor = self._parse_factor()
        if self.current_token and self.current_token.type == 'QUANTIFIER':
            quant = self.current_token.value
            self._eat(quant)
            return ParseTreeNode("quantifier", token={"quantifier": quant}, children=[factor])
        return factor
    
    def _parse_factor(self) -> ParseTreeNode:
        """
        Parses atomic units of the pattern, handling quantifiers and groups.
        """
        if self.current_token and self.current_token.type == 'QUANTIFIER':
            # Invalid placement of a quantifier
            self.context.error_handler.add_error(
                f"Unexpected quantifier '{self.current_token.value}' at start of expression",
                self.current_token.line, self.current_token.column
            )
            return ParseTreeNode("error", token={"value": self.current_token.value})

        if self.current_token and self.current_token.value == '(':
            self._eat('(')
            node = self._parse_pattern()
            if self.current_token and self.current_token.value == ')':
                self._eat(')')
            else:
                self.context.error_handler.add_error("Unmatched '('", self.current_token.line, self.current_token.column)
            return ParseTreeNode("group", children=[node])

        elif self.current_token and self.current_token.type == 'VARIABLE':
            token = self.current_token
            self._eat(token.value)
            self.pattern_variables.add(token.value)
            return ParseTreeNode("literal", token={"value": token.value})

        # Handle unexpected tokens
        if self.current_token:
            self.context.error_handler.add_error(f"Unknown token '{self.current_token.value}' in pattern", 
                                                 self.current_token.line, self.current_token.column)
            return ParseTreeNode("error", token={"value": self.current_token.value})

        return ParseTreeNode("empty")

def parse_pattern(pattern_text: str, context: Optional[ParserContext] = None) -> ParseTreeNode:
    """
    Parses a pattern expression and returns its parse tree.
    """
    parser = PatternParser(pattern_text, context)
    return parser.parse()

def parse_pattern_full(pattern_text: str, subset_mapping=None, context: Optional[ParserContext] = None) -> Dict[str, Any]:
    """
    Parses a pattern expression with optional subset mappings.
    """
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
