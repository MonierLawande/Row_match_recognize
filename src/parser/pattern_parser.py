# src/parser/pattern_parser.py

import re
from src.ast.pattern_ast import PatternAST

class PatternParser:
    """
    Tokenizes and parses a row pattern string into a preliminary parse tree.
    
    Supports:
      - Nested quantifiers (including reluctant quantifiers)
      - Proper exclusion syntax using {- ... -}
      - Grouping, alternation, permutation, and concatenation
      - Partition anchors (^ and $)
    """
    def __init__(self, pattern_text: str, subset_mapping=None):
        self.pattern_text = pattern_text
        self.subset_mapping = subset_mapping or {}
        self.tokens = self.tokenize(pattern_text)
        self.pos = 0
        self.nesting_level = 0
        self.MAX_NESTING = 10  # Maximum allowed nesting depth
        self.has_exclusion = False
        self.has_anchor = False

    def tokenize(self, pattern: str):
        """
        Tokenizes the pattern string with special handling for exclusion syntax.
        """
        # First, replace exclusion delimiters with special markers
        pattern = pattern.replace("{-", " EXCL_START ")
        pattern = pattern.replace("-}", " EXCL_END ")
        
        # Insert spaces around other symbols
        for sym in ['(', ')', '|', '+', '*', '?', '{', '}', ',', '^', '$']:
            pattern = pattern.replace(sym, f' {sym} ')
            
        # Split tokens and then restore exclusion tokens
        tokens = [t for t in pattern.split() if t]
        tokens = ['{-' if t == "EXCL_START" else t for t in tokens]
        tokens = [t if t != "EXCL_END" else "-}" for t in tokens]
        
        return tokens

    def next_token(self):
        """Consume and return the next token"""
        if self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            self.pos += 1
            return token
        return None

    def peek(self):
        """Look at the next token without consuming it"""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None
        
    def expect(self, expected_token):
        """Consume next token and verify it matches expected_token"""
        token = self.next_token()
        if token != expected_token:
            raise ValueError(f"Expected '{expected_token}', got '{token or 'end of pattern'}'")
        return token

    def parse(self):
        """Parse the pattern and return the AST"""
        # Check for empty pattern
        if not self.tokens:
            return PatternAST(type="empty")
            
        # Check for partition start anchor
        if self.peek() == '^':
            self.next_token()
            self.has_anchor = True
            
        result = self.parse_concatenation()
        
        # Check for partition end anchor
        if self.peek() == '$':
            self.next_token()
            self.has_anchor = True
            
        if self.peek() is not None:
            raise ValueError(f"Unexpected token '{self.peek()}' after pattern")
            
        return result

    def parse_concatenation(self):
        """Parse a concatenation of elements"""
        elements = []
        
        while self.pos < len(self.tokens) and self.peek() not in [')', '-}', None]:
            # Check for alternation
            if self.peek() == '|':
                break
                
            element = self.parse_alternation()
            elements.append(element)
            
        if not elements:
            return PatternAST(type="empty")
        if len(elements) == 1:
            return elements[0]
        return PatternAST(type="concatenation", children=elements)

    def parse_alternation(self):
        """Parse alternation (|)"""
        left = self.parse_quantified_element()
        
        if self.peek() == '|':
            alternatives = [left]
            while self.peek() == '|':
                self.next_token()  # Consume '|'
                right = self.parse_quantified_element()
                alternatives.append(right)
            return PatternAST(type="alternation", children=alternatives)
        
        return left

    def parse_quantified_element(self):
        """Parse an element with optional quantifier"""
        # Check for exclusion syntax
        if self.peek() == "{-":
            return self.parse_exclusion()

        # Parse a single element
        element = self.parse_element()

        # Check for quantifiers (greedy or reluctant)
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
                
                # Parse minimum value
                token = self.next_token()
                if token and token.isdigit():
                    min_val = int(token)
                else:
                    raise ValueError("Expected a number in quantifier")
                    
                # Check for range quantifier
                if self.peek() == ',':
                    self.next_token()  # consume ','
                    token = self.peek()
                    if token and token.isdigit():
                        max_val = int(self.next_token())
                    else:
                        max_val = None  # unbounded
                else:
                    max_val = min_val
                    
                self.expect('}')
                
                # Check for reluctant marker
                if self.peek() == '?':
                    self.next_token()
                    reluctant = True
                    
                # Validate quantifier values
                if min_val < 0:
                    raise ValueError("Quantifier minimum cannot be negative")
                if max_val is not None and max_val < min_val:
                    raise ValueError("Quantifier maximum cannot be less than minimum")
                
                element = PatternAST(
                    type="quantifier",
                    quantifier="{n,m}" + ("?" if reluctant else ""),
                    quantifier_min=min_val,
                    quantifier_max=max_val,
                    children=[element]
                )
            else:
                break
                
        return element

    def parse_exclusion(self):
        """Parse an exclusion pattern {- row_pattern -}"""
        self.has_exclusion = True
        
        # Consume the exclusion start token
        self.expect("{-")
        
        # Parse the inner row pattern
        inner_pattern = self.parse_concatenation()
        
        # Expect the exclusion end token
        self.expect("-}")
        
        # Return a PatternAST node for exclusion
        return PatternAST(type="exclusion", children=[inner_pattern])

    def parse_element(self):
        """Parse a pattern element (literal, group, or permutation)"""
        self.nesting_level += 1
        if self.nesting_level > self.MAX_NESTING:
            raise ValueError(f"Pattern nesting too deep (max {self.MAX_NESTING} levels)")
            
        token = self.next_token()
        if token is None:
            raise ValueError("Unexpected end of pattern")
            
        # Handle empty pattern
        if token == '(' and self.peek() == ')':
            self.next_token()  # Consume ')'
            self.nesting_level -= 1
            return PatternAST(type="empty")
            
        # Handle group
        if token == '(':
            inner = self.parse_concatenation()
            self.expect(")")
            self.nesting_level -= 1
            return PatternAST(type="group", children=[inner])
            
        # Handle PERMUTE syntax
        if token.upper() == "PERMUTE":
            self.expect("(")
            elements = []
            
            # Parse comma-separated list of elements
            while self.peek() != ')':
                if self.peek() == ',':
                    self.next_token()  # Skip comma
                    continue
                    
                elem = self.next_token()
                if not elem or elem in ['(', ')', '+', '*', '?', '{', '}']:
                    raise ValueError(f"Invalid element '{elem}' in PERMUTE")
                    
                elements.append(PatternAST(type="literal", value=elem))
            
            if not elements:
                raise ValueError("PERMUTE requires at least one element")
                
            self.expect(")")
            self.nesting_level -= 1
            return PatternAST(type="permutation", children=elements)
            
        # Handle subset expansion
        if token in self.subset_mapping:
            alternatives = [PatternAST(type="literal", value=v) for v in self.subset_mapping[token]]
            if not alternatives:
                raise ValueError(f"Subset '{token}' has no elements")
            self.nesting_level -= 1
            return PatternAST(type="alternation", children=alternatives)
            
        # Handle anchors (should only appear at start/end)
        if token in ['^', '$'] and self.nesting_level > 1:
            raise ValueError(f"Anchor '{token}' can only appear at the start or end of the pattern")
            
        # Otherwise, treat as a literal
        self.nesting_level -= 1
        return PatternAST(type="literal", value=token)

    def validate_pattern(self):
        """Validate the overall pattern structure"""
        errors = []
        
        # Check for exclusion with ALL ROWS PER MATCH WITH UNMATCHED ROWS
        if self.has_exclusion and self.has_rows_per_match_with_unmatched():
            errors.append("Pattern exclusions cannot be used with ALL ROWS PER MATCH WITH UNMATCHED ROWS")
            
        return errors
        
    def has_rows_per_match_with_unmatched(self):
        """Check if the pattern is used with ALL ROWS PER MATCH WITH UNMATCHED ROWS"""
        # This would need to be set from outside based on the full MATCH_RECOGNIZE clause
        # For now, we'll assume it's not used
        return False

def parse_pattern(pattern_text: str, subset_mapping=None):
    """Parse a pattern and return the AST"""
    parser = PatternParser(pattern_text, subset_mapping)
    ast = parser.parse()
    return ast

def parse_pattern_full(pattern_text: str, subset_mapping=None):
    """Parse a pattern and return both raw text and AST"""
    parser = PatternParser(pattern_text, subset_mapping)
    ast = parser.parse()
    errors = parser.validate_pattern()
    return {"raw": pattern_text.strip(), "ast": ast, "errors": errors}
