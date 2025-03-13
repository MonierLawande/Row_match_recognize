# src/parser/tokenizer.py

from typing import List, Callable, Optional
from .token_stream import Token, TokenStream

class Tokenizer:
    """Tokenizer for SQL expressions and patterns in MATCH_RECOGNIZE"""
    
    @staticmethod
    def create_token_stream(text: str, token_type_determiner: Callable[[str], str]) -> TokenStream:
        """
        Create a token stream from input text
        
        Args:
            text: The input text to tokenize
            token_type_determiner: Function to determine token type
            
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
                
                # Handle special characters (operators, parentheses, etc.)
                if line[pos] in ['(', ')', ',', '+', '-', '*', '/', '.', '=', '>', '<', '!']:
                    # Handle compound operators (>=, <=, !=, etc.)
                    if pos + 1 < len(line):
                        if line[pos:pos+2] in ['>=', '<=', '!=', '<>']:
                            token_type = token_type_determiner(line[pos:pos+2])
                            tokens.append(Token(
                                type=token_type,
                                value=line[pos:pos+2],
                                line=line_num,
                                column=pos + 1
                            ))
                            pos += 2
                            continue
                    
                    # Single character operators
                    token_type = token_type_determiner(line[pos])
                    tokens.append(Token(
                        type=token_type,
                        value=line[pos],
                        line=line_num,
                        column=pos + 1
                    ))
                    pos += 1
                else:
                    # Handle identifiers, literals, etc.
                    start = pos
                    
                    # Handle string literals
                    if line[pos] == "'":
                        pos += 1
                        while pos < len(line) and line[pos] != "'":
                            # Handle escaped quotes
                            if line[pos] == '\\' and pos + 1 < len(line):
                                pos += 2
                            else:
                                pos += 1
                        # Include closing quote
                        if pos < len(line):
                            pos += 1
                        token_value = line[start:pos]
                        token_type = 'LITERAL'
                    
                    # Handle numbers
                    elif line[pos].isdigit():
                        while pos < len(line) and (line[pos].isdigit() or line[pos] == '.'):
                            pos += 1
                        token_value = line[start:pos]
                        token_type = 'LITERAL'
                    
                    # Handle identifiers and keywords
                    else:
                        while pos < len(line) and not line[pos].isspace() and line[pos] not in ['(', ')', ',', '+', '-', '*', '/', '.', '=', '>', '<', '!']:
                            pos += 1
                        token_value = line[start:pos]
                        token_type = token_type_determiner(token_value)
                    
                    tokens.append(Token(
                        type=token_type,
                        value=token_value,
                        line=line_num,
                        column=start + 1
                    ))
        
        # Add EOF token
        tokens.append(Token(
            type='EOF',
            value='',
            line=len(lines),
            column=1
        ))
        
        return TokenStream(tokens)
