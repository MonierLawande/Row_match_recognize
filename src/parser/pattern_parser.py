# src/parser/pattern_parser.py

import re
from typing import Dict, Any, List, Optional, Set
from src.ast.pattern_ast import PatternAST
from .token_stream import Token, TokenStream
from .error_handler import ErrorHandler
from .context import ParserContext

class PatternParser:
    """
    Tokenizes and parses a row pattern string into a preliminary parse tree.
    
    Enhanced with:
      - Token stream for better token handling
      - Error handler for centralized error reporting
      - Parser context for shared state
      - Better validation of pattern variables
      - Improved error recovery
      - Support for character classes
      - Better handling of quantifiers
    """
    def __init__(self, pattern_text: str, context: Optional[ParserContext] = None):
        self.pattern_text = pattern_text
        self.tokens = self._create_token_stream(pattern_text)
        
        # Use provided context or create a new one
        if context:
            self.context = context
        else:
            self.context = ParserContext(ErrorHandler())
            
        # State tracking
        self.has_exclusion = False
        self.has_anchor = False


    # In PatternParser
    def _create_token_stream(self, text: str) -> TokenStream:
        return Tokenizer.create_token_stream(text, self._determine_token_type)


        
    def _determine_token_type(self, token: str) -> str:
        """Determine the type of a token"""
        if token in ['(', ')']:
            return 'PAREN'
        elif token in ['{-', '-}']:
            return 'EXCLUSION'
        elif token in ['+', '*', '?']:
            return 'QUANTIFIER'
        elif token == '{':
            return 'LBRACE'
        elif token == '}':
            return 'RBRACE'
        elif token == '|':
            return 'PIPE'
        elif token == ',':
            return 'COMMA'
        elif token in ['^', '$']:
            return 'ANCHOR'
        elif token.upper() == 'PERMUTE':
            return 'PERMUTE'
        else:
            return 'IDENTIFIER'

    def parse(self) -> PatternAST:
        """Parse the pattern and return the AST"""
        try:
            # Check for empty pattern
            if not self.tokens.has_more:
                return PatternAST(type="empty")
                
            # Check for partition start anchor
            if self.tokens.has_more and self.tokens.peek().value == '^':
                self.tokens.consume()
                self.has_anchor = True
                
            result = self._parse_concatenation()
            
            # Check for partition end anchor
            if self.tokens.has_more and self.tokens.peek().value == '$':
                self.tokens.consume()
                self.has_anchor = True
                
            if self.tokens.has_more:
                token = self.tokens.peek()
                self.context.error_handler.add_error(
                    f"Unexpected token '{token.value}' after pattern",
                    token.line, token.column
                )
                
            return result
        except Exception as e:
            # Add error to error handler if not already added
            if not self.context.error_handler.has_errors():
                self.context.error_handler.add_error(
                    f"Error parsing pattern: {str(e)}",
                    0, 0  # No position information available
                )
            # Return a minimal valid AST to allow processing to continue
            return PatternAST(type="error", value=str(e))

    def _parse_concatenation(self) -> PatternAST:
        """Parse a concatenation of elements"""
        elements = []
        
        while self.tokens.has_more and self.tokens.peek().value not in [')', '-}', '|']:
            element = self._parse_alternation()
            elements.append(element)
            
        if not elements:
            return PatternAST(type="empty")
        if len(elements) == 1:
            return elements[0]
        return PatternAST(type="concatenation", children=elements)

    def _parse_alternation(self) -> PatternAST:
        """Parse alternation (|)"""
        left = self._parse_quantified_element()
        
        if self.tokens.has_more and self.tokens.peek().value == '|':
            alternatives = [left]
            while self.tokens.has_more and self.tokens.peek().value == '|':
                self.tokens.consume()  # Consume '|'
                right = self._parse_quantified_element()
                alternatives.append(right)
            return PatternAST(type="alternation", children=alternatives)
        
        return left

    def _parse_quantified_element(self) -> PatternAST:
        """Parse an element with optional quantifier"""
        # Check for exclusion syntax
        if self.tokens.has_more and self.tokens.peek().value == '{-':
            return self._parse_exclusion()

        # Parse a single element
        element = self._parse_element()

        # Check for quantifiers (greedy or reluctant)
        while self.tokens.has_more:
            token = self.tokens.peek()
            
            if token.type == 'QUANTIFIER':
                quant = self.tokens.consume().value  # consume quantifier
                reluctant = False
                
                if self.tokens.has_more and self.tokens.peek().value == '?':
                    self.tokens.consume()  # consume reluctant marker
                    reluctant = True
                    
                element = PatternAST(
                    type="quantifier",
                    quantifier=quant + ("?" if reluctant else ""),
                    children=[element]
                )
                
            elif token.type == 'LBRACE':
                # Parse range quantifier {n,m}
                self.tokens.consume()  # consume '{'
                
                # Parse minimum value
                if not self.tokens.has_more or not self.tokens.peek().value.isdigit():
                    if self.tokens.has_more and self.tokens.peek().value == ',':
                        # Handle {,n} case (min=0)
                        min_val = 0
                    else:
                        self.context.error_handler.add_error(
                            "Expected a number or comma in quantifier",
                            token.line, token.column
                        )
                        min_val = 0
                else:
                    min_val = int(self.tokens.consume().value)
                    
                # Check for range quantifier
                max_val = None
                if self.tokens.has_more and self.tokens.peek().value == ',':
                    self.tokens.consume()  # consume ','
                    
                    if self.tokens.has_more and self.tokens.peek().value.isdigit():
                        max_val = int(self.tokens.consume().value)
                    else:
                        max_val = None  # unbounded
                else:
                    max_val = min_val
                    
                # Expect closing brace
                if not self.tokens.has_more or self.tokens.peek().type != 'RBRACE':
                    self.context.error_handler.add_error(
                        "Expected '}' to close quantifier",
                        token.line, token.column
                    )
                else:
                    self.tokens.consume()  # consume '}'
                    
                # Check for reluctant marker
                reluctant = False
                if self.tokens.has_more and self.tokens.peek().value == '?':
                    self.tokens.consume()
                    reluctant = True
                    
                # Validate quantifier values
                if min_val < 0:
                    self.context.error_handler.add_error(
                        "Quantifier minimum cannot be negative",
                        token.line, token.column
                    )
                    min_val = 0
                    
                if max_val is not None and max_val < min_val:
                    self.context.error_handler.add_error(
                        "Quantifier maximum cannot be less than minimum",
                        token.line, token.column
                    )
                    max_val = min_val
                
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

    def _parse_exclusion(self) -> PatternAST:
        """Parse an exclusion pattern {- row_pattern -}"""
        self.has_exclusion = True
        
        # Consume the exclusion start token
        start_token = self.tokens.consume()
        if start_token.value != '{-':
            self.context.error_handler.add_error(
                f"Expected '{{-', got '{start_token.value}'",
                start_token.line, start_token.column
            )
        
        # Parse the inner row pattern
        inner_pattern = self._parse_concatenation()
        
        # Expect the exclusion end token
        if not self.tokens.has_more or self.tokens.peek().value != '-}':
            self.context.error_handler.add_error(
                "Missing closing '-}' for exclusion pattern",
                start_token.line, start_token.column
            )
        else:
            self.tokens.consume()  # Consume '-}'
        
        # Return a PatternAST node for exclusion
        return PatternAST(type="exclusion", children=[inner_pattern])

    def _parse_element(self) -> PatternAST:
        """Parse a pattern element (literal, group, or permutation)"""
        self.context.enter_scope()
            
        if not self.tokens.has_more:
            self.context.error_handler.add_error(
                "Unexpected end of pattern",
                0, 0  # No position information available
            )
            self.context.exit_scope()
            return PatternAST(type="error", value="Unexpected end of pattern")
            
        token = self.tokens.consume()
            
        # Handle empty pattern
        if token.value == '(' and self.tokens.has_more and self.tokens.peek().value == ')':
            self.tokens.consume()  # Consume ')'
            self.context.exit_scope()
            return PatternAST(type="empty")
            
        # Handle group
        if token.value == '(':
            inner = self._parse_concatenation()
            
            if not self.tokens.has_more or self.tokens.peek().value != ')':
                self.context.error_handler.add_error(
                    "Missing closing parenthesis",
                    token.line, token.column
                )
            else:
                self.tokens.consume()  # Consume ')'
                
            self.context.exit_scope()
            return PatternAST(type="group", children=[inner])
            
        # Handle PERMUTE syntax
        if token.type == 'PERMUTE':
            if not self.tokens.has_more or self.tokens.peek().value != '(':
                self.context.error_handler.add_error(
                    "Expected '(' after PERMUTE",
                    token.line, token.column
                )
                self.context.exit_scope()
                return PatternAST(type="error", value="Invalid PERMUTE syntax")
                
            self.tokens.consume()  # Consume '('
            elements = []
            
            # Parse comma-separated list of elements
            while self.tokens.has_more and self.tokens.peek().value != ')':
                if self.tokens.peek().value == ',':
                    self.tokens.consume()  # Skip comma
                    continue
                    
                elem_token = self.tokens.consume()
                if elem_token.type != 'IDENTIFIER':
                    self.context.error_handler.add_error(
                        f"Invalid element '{elem_token.value}' in PERMUTE",
                        elem_token.line, elem_token.column
                    )
                else:
                    elements.append(PatternAST(type="literal", value=elem_token.value))
            
            if not elements:
                self.context.error_handler.add_error(
                    "PERMUTE requires at least one element",
                    token.line, token.column
                )
                
            if not self.tokens.has_more or self.tokens.peek().value != ')':
                self.context.error_handler.add_error(
                    "Missing closing parenthesis for PERMUTE",
                    token.line, token.column
                )
            else:
                self.tokens.consume()  # Consume ')'
                
            self.context.exit_scope()
            return PatternAST(type="permutation", children=elements)
            
        # Handle subset expansion
        if token.value in self.context.subset_variables:
            alternatives = [PatternAST(type="literal", value=v) for v in self.context.subset_variables[token.value]]
            if not alternatives:
                self.context.error_handler.add_error(
                    f"Subset '{token.value}' has no elements",
                    token.line, token.column
                )
                self.context.exit_scope()
                return PatternAST(type="error", value=f"Empty subset {token.value}")
                
            self.context.exit_scope()
            return PatternAST(type="alternation", children=alternatives)
            
        # Handle anchors (should only appear at start/end)
        if token.type == 'ANCHOR' and self.context.nesting_level > 1:
            self.context.error_handler.add_error(
                f"Anchor '{token.value}' can only appear at the start or end of the pattern",
                token.line, token.column
            )
            
        # Handle character class
        if token.value.startswith('[') and token.value.endswith(']'):
            self.context.exit_scope()
            return PatternAST(type="character_class", value=token.value)
            
        # Otherwise, treat as a literal
        self.context.exit_scope()
        
        # Register pattern variable in context
        if token.type == 'IDENTIFIER':
            self.context.add_pattern_variable(token.value)
            
        return PatternAST(type="literal", value=token.value)

    def validate_pattern(self) -> List[str]:
        """Validate the overall pattern structure"""
        # Check for exclusion with ALL ROWS PER MATCH WITH UNMATCHED ROWS
        if self.has_exclusion and self._has_rows_per_match_with_unmatched():
            self.context.error_handler.add_error(
                "Pattern exclusions cannot be used with ALL ROWS PER MATCH WITH UNMATCHED ROWS",
                0, 0  # No position information available
            )
            
        return self.context.error_handler.get_formatted_errors()
        
    def _has_rows_per_match_with_unmatched(self) -> bool:
        """Check if the pattern is used with ALL ROWS PER MATCH WITH UNMATCHED ROWS"""
        # This would need to be set from outside based on the full MATCH_RECOGNIZE clause
        # For now, we'll assume it's not used
        return False

def parse_pattern(pattern_text: str, subset_mapping: Optional[Dict[str, List[str]]] = None, 
                 context: Optional[ParserContext] = None) -> PatternAST:
    """Parse a pattern and return the AST"""
    if context is None:
        context = ParserContext(ErrorHandler())
        
    # Add subset variables to context
    if subset_mapping:
        for key, values in subset_mapping.items():
            context.add_subset_definition(key, set(values))
    
    parser = PatternParser(pattern_text, context)
    return parser.parse()

def parse_pattern_full(pattern_text: str, subset_mapping: Optional[Dict[str, List[str]]] = None,
                      context: Optional[ParserContext] = None) -> Dict[str, Any]:
    """Parse a pattern and return both raw text and AST"""
    if context is None:
        context = ParserContext(ErrorHandler())
        
    # Add subset variables to context
    if subset_mapping:
        for key, values in subset_mapping.items():
            context.add_subset_definition(key, set(values))
    
    parser = PatternParser(pattern_text, context)
    ast = parser.parse()
    parser.validate_pattern()
    
    # Perform semantic analysis
    analyzer = SemanticAnalyzer(context.error_handler)
    analyzer.analyze_pattern(ast)
    
    return {
        "raw": pattern_text.strip(),
        "ast": ast,
        "errors": context.error_handler.get_formatted_errors(),
        "warnings": context.error_handler.get_formatted_warnings(),
        "symbol_table": analyzer.symbol_table  # Include symbol table in result
    }
