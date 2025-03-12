# src/parser/tokenizer.py

from typing import List, Callable
from .token_stream import Token, TokenStream

class Tokenizer:
    """Common tokenizer for both expression and pattern parsing"""
    
    @staticmethod
    def create_token_stream(text: str, token_type_determiner: Callable[[str], str]) -> TokenStream:
        """
        Create a token stream with accurate line and column information
        
        Args:
            text: The input text to tokenize
            token_type_determiner: A function that determines the token type from its value
            
        Returns:
            A TokenStream containing the tokens
        """
        lines = text.split('\n')
        tokens = []
        
        for line_num, line in enumerate(lines, 1):
            pos = 0
            while pos < len(line):
                # Skip whitespace
                while pos < len(line) and line[pos].isspace():
                    pos += 1
                if pos >= len(line):
                    continue
                    
                # Identify token
                if line[pos] in ['(', ')', ',', '+', '-', '*', '/', '.', '{', '}', '|', '?', '^', '$']:
                    token_type = token_type_determiner(line[pos])
                    tokens.append(Token(
                        type=token_type,
                        value=line[pos],
                        line=line_num,
                        column=pos + 1
                    ))
                    pos += 1
                elif line[pos:pos+2] in ['{-', '-}']:
                    # Handle multi-character operators
                    token_type = token_type_determiner(line[pos:pos+2])
                    tokens.append(Token(
                        type=token_type,
                        value=line[pos:pos+2],
                        line=line_num,
                        column=pos + 1
                    ))
                    pos += 2
                else:
                    # Handle identifiers, literals, etc.
                    start = pos
                    if line[pos].isdigit():
                        # Handle numbers
                        while pos < len(line) and (line[pos].isdigit() or line[pos] == '.'):
                            pos += 1
                        token_value = line[start:pos]
                        token_type = 'LITERAL'
                    else:
                        # Handle identifiers and keywords
                        while pos < len(line) and not line[pos].isspace() and line[pos] not in ['(', ')', ',', '+', '-', '*', '/', '.', '{', '}', '|', '?', '^', '$']:
                            pos += 1
                        token_value = line[start:pos]
                        token_type = token_type_determiner(token_value)
                        
                    tokens.append(Token(
                        type=token_type,
                        value=token_value,
                        line=line_num,
                        column=start + 1
                    ))
        
        return TokenStream(tokens)
