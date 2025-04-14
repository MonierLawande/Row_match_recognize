# src/matcher/pattern_tokenizer.py

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

class PatternTokenType(Enum):
    LITERAL = "LITERAL"             
    ALTERNATION = "ALTERNATION"     
    PERMUTE = "PERMUTE"             
    GROUP_START = "GROUP_START"     
    GROUP_END = "GROUP_END"         
    ANCHOR_START = "ANCHOR_START"   
    ANCHOR_END = "ANCHOR_END"       
    EXCLUSION_START = "EXCL_START"  
    EXCLUSION_END = "EXCL_END"      

@dataclass
class PatternToken:
    type: PatternTokenType
    value: str
    quantifier: Optional[str] = None
    greedy: bool = True

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
            return (n, n, greedy)  # {n} means exactly n
        else:
            min_bound = int(bounds[0]) if bounds[0] else 0
            max_bound = int(bounds[1]) if bounds[1] else None
            return (min_bound, max_bound, greedy)
    return (1, 1, True)


# src/matcher/pattern_tokenizer.py

def tokenize_pattern(pattern: str) -> List[PatternToken]:
    """Enhanced tokenizer with full syntax support and better handling of nested structures."""
    tokens = []
    i = 0
    paren_depth = 0  # Track parenthesis depth for proper nesting
    
    # Handle start anchor
    if pattern.startswith('^'):
        tokens.append(PatternToken(PatternTokenType.ANCHOR_START, '^'))
        i += 1
        
    while i < len(pattern):
        char = pattern[i]
        
        if char.isspace():
            i += 1
            continue
            
        # Enhanced PERMUTE handling
        if i+7 <= len(pattern) and pattern[i:i+7].upper() == 'PERMUTE':
            tokens.append(PatternToken(PatternTokenType.PERMUTE, 'PERMUTE'))
            i += 7
            
            # Skip whitespace after PERMUTE
            while i < len(pattern) and pattern[i].isspace():
                i += 1
                
            # Collect variables in permutation
            if i < len(pattern) and pattern[i] == '(':
                paren_depth += 1  # Track opening paren
                i += 1  # Skip opening parenthesis
                variables = []
                
                while i < len(pattern):
                    # Skip whitespace
                    while i < len(pattern) and pattern[i].isspace():
                        i += 1
                    
                    if i >= len(pattern):
                        raise ValueError("Unterminated PERMUTE expression in pattern")
                        
                    if pattern[i] == ')':
                        paren_depth -= 1  # Track closing paren
                        i += 1  # Move past the closing parenthesis
                        break
                        
                    # Collect variable name
                    var_start = i
                    while i < len(pattern) and (pattern[i].isalnum() or pattern[i] == '_'):
                        i += 1
                    
                    if i > var_start:
                        variables.append(pattern[var_start:i])
                    
                    # Skip comma and whitespace
                    while i < len(pattern) and (pattern[i].isspace() or pattern[i] == ','):
                        i += 1
                
                # Add variables as LITERAL tokens
                for var in variables:
                    tokens.append(PatternToken(PatternTokenType.LITERAL, var))
            continue
            
        # Handle pattern exclusions
        elif i+1 < len(pattern) and pattern[i:i+2] == '{-':
            tokens.append(PatternToken(PatternTokenType.EXCLUSION_START, '{-'))
            i += 2
            
        elif i+1 < len(pattern) and pattern[i:i+2] == '-}':
            tokens.append(PatternToken(PatternTokenType.EXCLUSION_END, '-}'))
            i += 2
            
        # Handle grouping
        elif char == '(':
            tokens.append(PatternToken(PatternTokenType.GROUP_START, '('))
            paren_depth += 1
            i += 1
            
        elif char == ')':
            if paren_depth <= 0:
                raise ValueError(f"Unbalanced parentheses in pattern: unexpected closing parenthesis at position {i}")
                
            paren_depth -= 1
            token = PatternToken(PatternTokenType.GROUP_END, ')')
            
            # Check for quantifiers after group
            next_pos = i + 1
            while next_pos < len(pattern) and pattern[next_pos] in '+*?{':
                next_pos += 1
                
                # If we encounter a '{', we need to find the matching '}'
                if pattern[next_pos-1] == '{':
                    brace_pos = pattern.find('}', next_pos)
                    if brace_pos == -1:
                        raise ValueError(f"Unterminated quantifier at position {next_pos-1}")
                    next_pos = brace_pos + 1
                    
                # Check for reluctant quantifier
                if next_pos < len(pattern) and pattern[next_pos] == '?':
                    next_pos += 1
                    
            if next_pos > i + 1:
                quant = pattern[i+1:next_pos]
                token.quantifier = quant
                token.greedy = not quant.endswith('?')
                i = next_pos
            else:
                i += 1
            tokens.append(token)
            
        # Handle alternation
        elif char == '|':
            tokens.append(PatternToken(PatternTokenType.ALTERNATION, '|'))
            i += 1
            
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
                
                # Parse the quantifier
                if pattern[i] in '+*?':
                    i += 1
                    # Check for reluctant quantifier
                    if i < len(pattern) and pattern[i] == '?':
                        greedy = False
                        i += 1
                elif pattern[i] == '{':
                    # Find matching closing brace
                    brace_pos = pattern.find('}', i)
                    if brace_pos == -1:
                        raise ValueError(f"Unterminated quantifier at position {i}")
                    i = brace_pos + 1
                    
                    # Check for reluctant quantifier after brace
                    if i < len(pattern) and pattern[i] == '?':
                        greedy = False
                        i += 1
                
                quant = pattern[quant_start:i]
            
            tokens.append(PatternToken(
                PatternTokenType.LITERAL,
                var_name,
                quantifier=quant or None,
                greedy=greedy
            ))
            
        else:
            # Skip characters we don't recognize
            i += 1
            
    # Check for unbalanced parentheses at the end
    if paren_depth > 0:
        raise ValueError(f"Unbalanced parentheses in pattern: missing {paren_depth} closing parentheses")
            
    # Handle end anchor at the end of the pattern
    if pattern.endswith('$') and tokens and tokens[-1].type != PatternTokenType.ANCHOR_END:
        tokens.append(PatternToken(PatternTokenType.ANCHOR_END, '$'))
            
    return tokens
