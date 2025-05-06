from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple, Dict, Any

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
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

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
# Update the tokenize_pattern function

# src/matcher/pattern_tokenizer.py

def tokenize_pattern(pattern: str) -> List[PatternToken]:
    """Enhanced tokenizer with improved support for all pattern syntax features."""
    tokens = []
    i = 0
    paren_depth = 0  # Track parenthesis depth
    
    # Handle start anchor
    if pattern.startswith('^'):
        tokens.append(PatternToken(PatternTokenType.ANCHOR_START, '^'))
        i += 1
        
    while i < len(pattern):
        char = pattern[i]
        
        if char.isspace():
            i += 1
            continue
            
        # Enhanced PERMUTE handling with recursive nesting
        if i+7 <= len(pattern) and pattern[i:i+7].upper() == 'PERMUTE':
            permute_start = i
            i += 7  # Move past "PERMUTE"
            
            # Skip whitespace after PERMUTE
            while i < len(pattern) and pattern[i].isspace():
                i += 1
                
            # Handle opening parenthesis
            if i < len(pattern) and pattern[i] == '(':
                nested_depth = 1
                i += 1  # Move past opening parenthesis
                
                # Extract variables, handling nested PERMUTEs
                variables = []
                var_start = i
                
                while i < len(pattern) and nested_depth > 0:
                    # Check if we're starting a nested PERMUTE
                    if i+7 <= len(pattern) and pattern[i:i+7].upper() == 'PERMUTE':
                        # Get text up to this nested PERMUTE
                        if i > var_start:
                            var_text = pattern[var_start:i].strip()
                            if var_text:
                                if var_text.endswith(','):
                                    var_text = var_text[:-1].strip()
                                if var_text:
                                    variables.append(var_text)
                        
                        # Find the end of this nested PERMUTE
                        nested_permute_start = i
                        nested_permute_depth = 0
                        found_open = False
                        
                        while i < len(pattern):
                            if pattern[i] == '(' and not found_open:
                                found_open = True
                                nested_permute_depth = 1
                                i += 1
                            elif pattern[i] == '(' and found_open:
                                nested_permute_depth += 1
                                i += 1
                            elif pattern[i] == ')' and found_open:
                                nested_permute_depth -= 1
                                if nested_permute_depth == 0:
                                    # Found end of nested PERMUTE
                                    break
                                i += 1
                            else:
                                i += 1
                        
                        # Get the nested PERMUTE expression
                        if found_open:
                            nested_permute = pattern[nested_permute_start:i+1]
                            # Recursively tokenize the nested PERMUTE
                            nested_tokens = tokenize_pattern(nested_permute)
                            if nested_tokens:
                                variables.append(nested_tokens[0])
                        
                        i += 1  # Move past closing parenthesis
                        var_start = i
                        
                    elif pattern[i] == '(':
                        nested_depth += 1
                        i += 1
                    elif pattern[i] == ')':
                        nested_depth -= 1
                        if nested_depth == 0:
                            # End of PERMUTE, get the last variable
                            var_text = pattern[var_start:i].strip()
                            if var_text:
                                if var_text.endswith(','):
                                    var_text = var_text[:-1].strip()
                                if var_text:
                                    variables.append(var_text)
                        i += 1
                    elif pattern[i] == ',' and nested_depth == 1:
                        # Variable separator at top level
                        var_text = pattern[var_start:i].strip()
                        if var_text:
                            variables.append(var_text)
                        i += 1
                        var_start = i
                    else:
                        i += 1
                
                # Check for quantifiers after PERMUTE
                quant = ''
                greedy = True
                
                if i < len(pattern) and pattern[i] in '+*?{':
                    quant_start = i
                    
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
                
                # Create a PERMUTE token with metadata
                permute_token = PatternToken(
                    type=PatternTokenType.PERMUTE,
                    value='PERMUTE',
                    quantifier=quant or None,
                    greedy=greedy,
                    metadata={
                        "variables": variables,
                        "original": pattern[permute_start:i],
                        "nested": True
                    }
                )
                tokens.append(permute_token)
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

