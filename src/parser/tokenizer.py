from dataclasses import dataclass
from typing import List, Callable, Optional

@dataclass
class Token:
    type: str
    value: str
    line: int
    column: int

class TokenStream:
    """Enhanced token stream with lookahead and backtracking support."""
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.position = 0
        self.markers = []
        
    def peek(self, lookahead: int = 1) -> Optional[Token]:
        if self.position + lookahead - 1 < len(self.tokens):
            return self.tokens[self.position + lookahead - 1]
        return None
        
    def consume(self) -> Optional[Token]:
        if self.position < len(self.tokens):
            token = self.tokens[self.position]
            self.position += 1
            return token
        return None
        
    def mark(self) -> int:
        self.markers.append(self.position)
        return len(self.markers) - 1
        
    def reset(self, marker: int):
        if marker < len(self.markers):
            self.position = self.markers[marker]
            self.markers = self.markers[:marker]
            
    def release(self, marker: int):
        if marker < len(self.markers):
            self.markers = self.markers[:marker]
            
    @property
    def has_more(self) -> bool:
        return self.position < len(self.tokens)

class Tokenizer:
    """Tokenizer for SQL expressions and patterns."""
    @staticmethod
    def create_token_stream(text: str, token_type_determiner: Callable[[str], str]) -> TokenStream:
        lines = text.split('\n')
        tokens: List[Token] = []
        
        for line_num, line in enumerate(lines, 1):
            pos = 0
            while pos < len(line):
                while pos < len(line) and line[pos].isspace():
                    pos += 1
                if pos >= len(line):
                    continue
                if line[pos] in ['(', ')', ',', '+', '-', '*', '/', '.', '=', '>', '<', '!']:
                    if pos + 1 < len(line) and line[pos:pos+2] in ['>=', '<=', '!=', '<>']:
                        token_type = token_type_determiner(line[pos:pos+2])
                        tokens.append(Token(
                            type=token_type,
                            value=line[pos:pos+2],
                            line=line_num,
                            column=pos + 1
                        ))
                        pos += 2
                        continue
                    token_type = token_type_determiner(line[pos])
                    tokens.append(Token(
                        type=token_type,
                        value=line[pos],
                        line=line_num,
                        column=pos + 1
                    ))
                    pos += 1
                else:
                    start = pos
                    if line[pos] == "'":
                        pos += 1
                        while pos < len(line) and line[pos] != "'":
                            if line[pos] == '\\' and pos + 1 < len(line):
                                pos += 2
                            else:
                                pos += 1
                        if pos < len(line):
                            pos += 1
                        token_value = line[start:pos]
                        token_type = 'LITERAL'
                    elif line[pos].isdigit():
                        while pos < len(line) and (line[pos].isdigit() or line[pos] == '.'):
                            pos += 1
                        token_value = line[start:pos]
                        token_type = 'LITERAL'
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
        tokens.append(Token(
            type='EOF',
            value='',
            line=len(lines),
            column=1
        ))
        return TokenStream(tokens)
