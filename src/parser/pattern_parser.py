import re
from src.ast.pattern_ast import PatternAST

class PatternParser:
    """
    Tokenizes and parses a row pattern string into a preliminary parse tree.
    Supports nested quantifiers, grouping, alternation, permutation, and exclusion.
    """
    def __init__(self, pattern_text: str, subset_mapping=None):
        self.pattern_text = pattern_text
        self.subset_mapping = subset_mapping or {}
        self.tokens = self.tokenize(pattern_text)
        self.pos = 0

    def tokenize(self, pattern: str):
        # Insert spaces around special symbols.
        for sym in ['(', ')', '|', '+', '*', '?', '{', '}', ',', '^']:
            pattern = pattern.replace(sym, f' {sym} ')
        return [t for t in pattern.split() if t]

    def next_token(self):
        if self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            self.pos += 1
            return token
        return None

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def parse(self):
        # Parse a concatenation of pattern elements.
        elements = []
        while self.pos < len(self.tokens) and self.peek() != ')':
            element = self.parse_quantified_element()
            elements.append(element)
        if not elements:
            return PatternAST(type="empty")
        if len(elements) == 1:
            return elements[0]
        return PatternAST(type="concatenation", children=elements)

    def parse_quantified_element(self):
        # Check for exclusion operator.
        excluded = False
        if self.peek() == '^':
            self.next_token()  # consume '^'
            excluded = True

        element = self.parse_element()
        element.excluded = excluded

        # Support nested quantifiers: while the next token is a quantifier, wrap the element.
        while self.peek() in ['+', '*', '?'] or self.peek() == '{':
            token = self.peek()
            if token in ['+', '*', '?']:
                quant = self.next_token()  # consume quantifier symbol
                element = PatternAST(
                    type="quantifier",
                    quantifier=quant,
                    children=[element]
                )
            elif token == '{':
                self.next_token()  # consume '{'
                min_val = None
                max_val = None
                token = self.next_token()
                if token.isdigit():
                    min_val = int(token)
                else:
                    raise ValueError("Expected a number in quantifier")
                if self.peek() == ',':
                    self.next_token()  # consume ','
                    token = self.peek()
                    if token.isdigit():
                        max_val = int(self.next_token())
                    else:
                        max_val = None  # unbounded
                else:
                    max_val = min_val
                if self.next_token() != '}':
                    raise ValueError("Expected '}' in quantifier")
                element = PatternAST(
                    type="quantifier",
                    quantifier="{n,m}",
                    quantifier_min=min_val,
                    quantifier_max=max_val,
                    children=[element]
                )
        return element

    def parse_element(self):
        token = self.next_token()
        if token is None:
            raise ValueError("Unexpected end of pattern")
        if token == '(':
            # Parse a group.
            inner = self.parse()
            if self.next_token() != ')':
                raise ValueError("Expected closing ')' for group")
            return PatternAST(type="group", children=[inner])
        # Support PERMUTE syntax.
        if token.upper() == "PERMUTE":
            if self.next_token() != '(':
                raise ValueError("Expected '(' after PERMUTE")
            elements = []
            while self.peek() != ')':
                elem = self.next_token()
                if elem == ',':
                    continue
                elements.append(PatternAST(type="literal", value=elem))
            if self.next_token() != ')':
                raise ValueError("Expected ')' after PERMUTE arguments")
            return PatternAST(type="permutation", children=elements)
        # If token is in subset mapping, expand it to an alternation.
        if token in self.subset_mapping:
            alternatives = [PatternAST(type="literal", value=v) for v in self.subset_mapping[token]]
            return PatternAST(type="alternation", children=alternatives)
        # Otherwise, return a literal node.
        return PatternAST(type="literal", value=token)

def parse_pattern_full(pattern_text: str, subset_mapping=None):
    parser = PatternParser(pattern_text, subset_mapping)
    ast = parser.parse()
    return {"raw": pattern_text.strip(), "ast": ast}
