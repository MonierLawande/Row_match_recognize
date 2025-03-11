import re
from src.ast.pattern_ast import PatternAST

class PatternParser:
    """
    Tokenizes and parses a row pattern string into a preliminary tree.
    """
    def __init__(self, pattern_text: str, subset_mapping=None):
        self.pattern_text = pattern_text
        self.subset_mapping = subset_mapping or {}
        self.tokens = self.tokenize(pattern_text)
        self.pos = 0
    def tokenize(self, pattern: str):
        # Simple tokenizer for patterns
        pattern = pattern.replace('(', ' ( ').replace(')', ' ) ')
        pattern = pattern.replace('|', ' | ')
        pattern = pattern.replace('+', ' + ').replace('*', ' * ').replace('?', ' ? ')
        return [t for t in pattern.split() if t]
    def parse(self):
        # For demonstration, parse a concatenation of literals
        elements = []
        while self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            self.pos += 1
            elements.append(PatternAST(type="literal", value=token))
        if len(elements) == 1:
            return elements[0]
        return PatternAST(type="concatenation", children=elements)

def parse_pattern_full(pattern_text: str, subset_mapping=None):
    parser = PatternParser(pattern_text, subset_mapping)
    ast = parser.parse()
    return {"raw": pattern_text.strip(), "ast": ast}
