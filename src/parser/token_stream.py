# src/parser/token_stream.py

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Token:
    type: str
    value: str
    line: int
    column: int
    
class TokenStream:
    """Enhanced token stream with better error handling and lookahead"""
    
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.position = 0
        self.markers = []
        
    def peek(self, lookahead: int = 1) -> Optional[Token]:
        """Look ahead n tokens without consuming"""
        if self.position + lookahead - 1 < len(self.tokens):
            return self.tokens[self.position + lookahead - 1]
        return None
        
    def consume(self) -> Optional[Token]:
        """Consume and return next token"""
        if self.position < len(self.tokens):
            token = self.tokens[self.position]
            self.position += 1
            return token
        return None
        
    def mark(self) -> int:
        """Mark current position for backtracking"""
        self.markers.append(self.position)
        return len(self.markers) - 1
        
    def reset(self, marker: int):
        """Reset position to a marker"""
        if marker < len(self.markers):
            self.position = self.markers[marker]
            self.markers = self.markers[:marker]
            
    def release(self, marker: int):
        """Release a marker"""
        if marker < len(self.markers):
            self.markers = self.markers[:marker]
            
    @property
    def has_more(self) -> bool:
        """Check if more tokens are available"""
        return self.position < len(self.tokens)
