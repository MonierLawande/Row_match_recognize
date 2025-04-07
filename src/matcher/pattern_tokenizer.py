# src/matcher/pattern_tokenizer.py

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple
import itertools

class PatternTokenType(Enum):
    LITERAL = "LITERAL"             # A, B, C
    ALTERNATION = "ALTERNATION"     # |
    PERMUTE = "PERMUTE"             # PERMUTE
    GROUP_START = "GROUP_START"     # (
    GROUP_END = "GROUP_END"         # )
    ANCHOR_START = "ANCHOR_START"   # ^
    ANCHOR_END = "ANCHOR_END"       # $
    EXCLUSION_START = "EXCL_START"  # {-
    EXCLUSION_END = "EXCL_END"      # -}

@dataclass
class PatternToken:
    type: PatternTokenType
    value: str
    quantifier: Optional[str] = None  # *, +, ?, {n}, {m,n}
    greedy: bool = True              # True for greedy, False for reluctant
    
def parse_quantifier(quant: str) -> Tuple[int, Optional[int], bool]:
    """Parse quantifier into (min, max, greedy) tuple."""
    greedy = not quant.endswith('?')
    if not greedy:
        quant = quant[:-1]
        
    if quant == '*':
        return (0, None, greedy)
    elif quant == '+':
        return (1, None, greedy)
    elif quant == '?':
        return (0, 1, greedy)
    elif quant.startswith('{') and quant.endswith('}'):
        bounds = quant[1:-1].split(',')
        if len(bounds) == 1:
            n = int(bounds[0])
            return (n, n, greedy)
        else:
            min_bound = int(bounds[0]) if bounds[0] else 0
            max_bound = int(bounds[1]) if bounds[1] else None
            return (min_bound, max_bound, greedy)
    return (1, 1, True)  # Default: exactly one occurrence

def tokenize_pattern(pattern: str) -> List[PatternToken]:
    """Tokenize pattern with full syntax support."""
    tokens = []
    i = 0
    
    # Handle start anchor
    if pattern.startswith('^'):
        tokens.append(PatternToken(PatternTokenType.ANCHOR_START, '^'))
        i += 1
        
    while i < len(pattern):
        char = pattern[i]
        
        if char.isspace():
            i += 1
            continue
            
        # Handle PERMUTE keyword
        if i+7 <= len(pattern) and pattern[i:i+7].upper() == 'PERMUTE':
            tokens.append(PatternToken(PatternTokenType.PERMUTE, 'PERMUTE'))
            i += 7  # Skip 'PERMUTE'
            continue
            
        # Handle grouping
        elif char == '(':
            tokens.append(PatternToken(PatternTokenType.GROUP_START, '('))
            i += 1
            
        elif char == ')':
            token = PatternToken(PatternTokenType.GROUP_END, ')')
            # Check for quantifiers after group
            next_pos = i + 1
            while next_pos < len(pattern) and pattern[next_pos] in '+*?{':
                next_pos += 1
            if next_pos > i + 1:
                quant = pattern[i+1:next_pos]
                min_rep, max_rep, greedy = parse_quantifier(quant)
                token.quantifier = quant
                token.greedy = greedy
                i = next_pos
            else:
                i += 1
            tokens.append(token)
            
        # Handle alternation
        elif char == '|':
            tokens.append(PatternToken(PatternTokenType.ALTERNATION, '|'))
            i += 1
            
        # Handle exclusion
        elif i+1 < len(pattern) and pattern[i:i+2] == '{-':
            tokens.append(PatternToken(PatternTokenType.EXCLUSION_START, '{-'))
            i += 2
            
        elif i+1 < len(pattern) and pattern[i:i+2] == '-}':
            tokens.append(PatternToken(PatternTokenType.EXCLUSION_END, '-}'))
            i += 2
            
        # Handle end anchor
        elif char == '$':
            tokens.append(PatternToken(PatternTokenType.ANCHOR_END, '$'))
            i += 1
            
        # Handle pattern variables
        elif char.isalpha():
            var_start = i
            while i < len(pattern) and (pattern[i].isalnum() or pattern[i] == '_'):
                i += 1
            var_name = pattern[var_start:i]
            
            # Check for quantifiers
            quant = ''
            greedy = True
            if i < len(pattern) and pattern[i] in '+*?{':
                quant_start = i
                while i < len(pattern) and pattern[i] not in ' |)':
                    i += 1
                quant = pattern[quant_start:i]
                min_rep, max_rep, greedy = parse_quantifier(quant)
            
            tokens.append(PatternToken(
                PatternTokenType.LITERAL,
                var_name,
                quantifier=quant or None,
                greedy=greedy
            ))
            
        else:
            i += 1
            
    # Handle end anchor at the end of the pattern
    if pattern.endswith('$') and tokens and tokens[-1].type != PatternTokenType.ANCHOR_END:
        tokens.append(PatternToken(PatternTokenType.ANCHOR_END, '$'))
            
    return tokens
