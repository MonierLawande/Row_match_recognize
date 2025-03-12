import re
from src.ast.pattern_ast import PatternAST

class PatternParser:
    """
    Tokenizes and parses a row pattern string into a preliminary parse tree.
    
    Extended to support:
      - Nested quantifiers (including reluctant quantifiers)
      - Proper exclusion syntax using {- ... -}
      - Grouping, alternation, permutation, and concatenation.
    """
    def __init__(self, pattern_text: str, subset_mapping=None):
        self.pattern_text = pattern_text
        self.subset_mapping = subset_mapping or {}
        self.tokens = self.tokenize(pattern_text)
        self.pos = 0

    def tokenize(self, pattern: str):
        """
        Tokenizes the pattern string.
        Special handling:
          - Recognize '{-' and '-}' as single tokens for exclusion syntax.
          - Insert spaces around other special symbols.
        """
        # First, replace exclusion delimiters with special markers.
        pattern = pattern.replace("{-", " EXCL_START ")
        pattern = pattern.replace("-}", " EXCL_END ")
        # Insert spaces around other symbols.
        for sym in ['(', ')', '|', '+', '*', '?', '{', '}', ',', '^']:
            pattern = pattern.replace(sym, f' {sym} ')
        # Split tokens and then restore exclusion tokens.
        tokens = [t for t in pattern.split() if t]
        # Replace tokens that are our markers.
        tokens = ['{-' if t == "EXCL_START" else t for t in tokens]
        tokens = [t if t != "EXCL_END" else "-}" for t in tokens]
        return tokens

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
        # Parse a concatenation of elements.
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
        # Check for exclusion syntax.
        if self.peek() == "{-":
            return self.parse_exclusion()

        # Parse a single element.
        element = self.parse_element()

        # Check for quantifiers (greedy or reluctant).
        while self.peek() in ['+', '*', '?'] or self.peek() == '{':
            token = self.peek()
            reluctant = False
            if token in ['+', '*', '?']:
                quant = self.next_token()  # consume quantifier
                if self.peek() == '?':
                    self.next_token()  # consume reluctant marker
                    reluctant = True
                element = PatternAST(
                    type="quantifier",
                    quantifier=quant + ("?" if reluctant else ""),
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
                # Check for reluctant marker after quantifier.
                if self.peek() == '?':
                    self.next_token()
                    reluctant = True
                quant_str = "{n,m}" + ("?" if reluctant else "")
                element = PatternAST(
                    type="quantifier",
                    quantifier=quant_str,
                    quantifier_min=min_val,
                    quantifier_max=max_val,
                    children=[element]
                )
            else:
                break
        return element

    def parse_exclusion(self):
        """
        Parses an exclusion pattern of the form:
           {- row_pattern -}
        """
        # Consume the exclusion start token.
        token = self.next_token()
        if token != "{-":
            raise ValueError("Expected '{-' for exclusion syntax")
        # Parse the inner row pattern.
        inner_pattern = self.parse()
        # Expect the exclusion end token.
        if self.next_token() != "-}":
            raise ValueError("Expected '-}' for exclusion syntax")
        # Return a PatternAST node for exclusion.
        return PatternAST(type="exclusion", children=[inner_pattern])

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
        # Otherwise, treat as a literal.
        return PatternAST(type="literal", value=token)

def parse_pattern_full(pattern_text: str, subset_mapping=None):
    parser = PatternParser(pattern_text, subset_mapping)
    ast = parser.parse()
    return {"raw": pattern_text.strip(), "ast": ast}
