import re
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple, Dict, Any, Union

# Temporarily disable logging to fix hanging issue
# from src.utils.logging_config import get_logger
# logger = get_logger(__name__)
logger = None

class PatternTokenType(Enum):
    """Enum representing different types of pattern tokens."""
    LITERAL = "LITERAL"             
    ALTERNATION = "ALTERNATION"     
    PERMUTE = "PERMUTE"             
    GROUP_START = "GROUP_START"     
    GROUP_END = "GROUP_END"         
    ANCHOR_START = "ANCHOR_START"   
    ANCHOR_END = "ANCHOR_END"       
    EXCLUSION_START = "EXCL_START"  
    EXCLUSION_END = "EXCL_END"      

class PatternSyntaxError(Exception):
    """Base class for pattern syntax errors with context visualization."""
    def __init__(self, message: str, position: int, pattern: str):
        self.message = message
        self.position = position
        self.pattern = pattern
        self.context = self._get_error_context()
        super().__init__(f"{message}\nAt position {position}:\n{self.context}")
    
    def _get_error_context(self) -> str:
        """Get error context with pointer to error position."""
        start = max(0, self.position - 20)
        end = min(len(self.pattern), self.position + 20)
        context = self.pattern[start:end]
        pointer = " " * (self.position - start) + "^"
        return f"{context}\n{pointer}"

class PermutePatternError(PatternSyntaxError):
    """Error in PERMUTE pattern syntax."""
    pass

class QuantifierError(PatternSyntaxError):
    """Error in quantifier syntax."""
    pass

class UnbalancedPatternError(PatternSyntaxError):
    """Error for unbalanced pattern elements like parentheses or exclusion markers."""
    pass

@dataclass
class PatternToken:
    """Represents a token in a pattern expression."""
    type: PatternTokenType
    value: str
    quantifier: Optional[str] = None
    greedy: bool = True
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        """Initialize metadata dictionary and PERMUTE-specific fields."""
        if self.metadata is None:
            self.metadata = {}
        # Add PERMUTE-specific metadata initialization
        if self.type == PatternTokenType.PERMUTE:
            if "variables" not in self.metadata:
                self.metadata["variables"] = []
            if "nested" not in self.metadata:
                self.metadata["nested"] = False
            if "original" not in self.metadata:
                self.metadata["original"] = ""
    
    def __str__(self) -> str:
        """String representation of the token."""
        result = self.value
        if self.quantifier:
            result += self.quantifier
            if not self.greedy and self.quantifier[-1] != '?':
                result += '?'
        return result

def parse_quantifier(quant: str) -> Tuple[int, Optional[int], bool]:
    """
    Parse quantifier into (min, max, greedy) tuple.
    
    Args:
        quant: The quantifier string (e.g., '*', '+', '?', '{n}', '{n,m}')
        
    Returns:
        Tuple of (min_repetitions, max_repetitions, is_greedy)
        max_repetitions is None for unbounded quantifiers
    
    Raises:
        ValueError: If the quantifier format is invalid
    """
    # Handle single '?' first (optional quantifier) before checking for reluctant quantifiers
    if quant == '?':
        return (0, 1, True)
    
    # Check for reluctant quantifiers (ending with '?')
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
        try:
            if len(bounds) == 1:
                n = int(bounds[0])
                return (n, n, greedy)  # {n} means exactly n
            else:
                min_bound = int(bounds[0]) if bounds[0] else 0
                max_bound = int(bounds[1]) if bounds[1] else None
                
                # Validate bounds
                if max_bound is not None and min_bound > max_bound:
                    raise ValueError(f"Invalid quantifier range: minimum ({min_bound}) greater than maximum ({max_bound})")
                    
                return (min_bound, max_bound, greedy)
        except ValueError as e:
            if "greater than maximum" in str(e):
                raise
            raise ValueError(f"Invalid quantifier format: {quant}")
    return (1, 1, True)

def validate_quantifier_format(quant: str, position: int, pattern: str) -> None:
    """
    Validate the format of a quantifier.
    
    Args:
        quant: The quantifier string without the non-greedy marker
        position: Position in the pattern where the quantifier starts
        pattern: The full pattern string
        
    Raises:
        QuantifierError: If the quantifier format is invalid
    """
    if quant.startswith('{') and quant.endswith('}'):
        content = quant[1:-1]
        
        # Check for negative numbers first (these should be rejected)
        if '-' in content:
            raise QuantifierError(f"Negative values not allowed in quantifier: {quant}", position, pattern)
        
        # Check basic format - only allow positive digits and commas
        if not re.match(r'^\d+(?:,\d*)?$', content):
            raise QuantifierError(f"Invalid quantifier format: {quant}", position, pattern)
            
        # Parse and validate bounds
        parts = content.split(',')
        try:
            if len(parts) == 1:
                int(parts[0])  # Validate it's a number
            elif len(parts) == 2:
                min_val = int(parts[0]) if parts[0] else 0
                max_val = int(parts[1]) if parts[1] else None
                
                if max_val is not None and min_val > max_val:
                    raise QuantifierError(
                        f"Invalid quantifier range: minimum ({min_val}) greater than maximum ({max_val})",
                        position, pattern
                    )
            else:
                raise QuantifierError(f"Too many commas in quantifier: {quant}", position, pattern)
        except ValueError:
            raise QuantifierError(f"Non-numeric values in quantifier: {quant}", position, pattern)

def parse_quantifier_at(pattern: str, start_pos: int) -> Tuple[Optional[str], bool, int]:
    """
    Parse quantifier at given position in the pattern.
    
    Args:
        pattern: The full pattern string
        start_pos: Position to start parsing from
        
    Returns:
        Tuple of (quantifier, is_greedy, new_position)
        
    Raises:
        QuantifierError: If the quantifier format is invalid
    """
    if start_pos >= len(pattern):
        return None, True, start_pos
        
    char = pattern[start_pos]
    if char not in "*+?{":
        return None, True, start_pos
        
    if char in "*+?":
        pos = start_pos + 1
        is_greedy = True
        if pos < len(pattern) and pattern[pos] == "?":
            is_greedy = False
            pos += 1
        return char, is_greedy, pos
        
    # Handle {n,m} quantifiers
    pos = start_pos
    brace_depth = 0
    quant_start = pos
    
    while pos < len(pattern):
        if pattern[pos] == "{":
            brace_depth += 1
        elif pattern[pos] == "}":
            brace_depth -= 1
            if brace_depth == 0:
                break
        pos += 1
        
    if brace_depth > 0 or pos >= len(pattern):
        raise QuantifierError("Unclosed brace in quantifier", start_pos, pattern)
        
    pos += 1  # Move past closing brace
    quantifier = pattern[quant_start:pos]
    
    # Validate quantifier format
    validate_quantifier_format(quantifier, start_pos, pattern)
        
    # Check for non-greedy marker
    is_greedy = True
    if pos < len(pattern) and pattern[pos] == "?":
        is_greedy = False
        pos += 1
        
    return quantifier, is_greedy, pos




# src/matcher/pattern_tokenizer.py - Updated validate_pattern_structure function

def validate_pattern_structure(pattern: str) -> None:
    """
    Validate overall pattern structure before tokenization.
    
    Args:
        pattern: The pattern string to validate
        
    Raises:
        PatternSyntaxError: If pattern structure is invalid
    """
    # Check for complex nested exclusions with quantifiers
    # These are now supported with the PatternExclusionHandler
    
    def find_matching_exclusion_end(text: str, start_pos: int) -> int:
        """Find the matching -} for a {- at start_pos."""
        depth = 0
        i = start_pos
        while i < len(text) - 1:
            if text[i:i+2] == "{-":
                depth += 1
                i += 2
            elif text[i:i+2] == "-}":
                depth -= 1
                if depth == 0:
                    return i
                i += 2
            else:
                i += 1
        return -1
    
    # For now, we support all exclusion patterns
    # Complex patterns will be handled by PatternExclusionHandler
    # Only validate basic structure
    
    start = 0
    while True:
        start_marker = pattern.find("{-", start)
        if start_marker == -1:
            break
        
        end_marker = find_matching_exclusion_end(pattern, start_marker)
        if end_marker == -1:
            raise PatternSyntaxError(
                "Unmatched exclusion markers in pattern",
                start_marker, pattern
            )
        
        start = end_marker + 2
    
    # Check for balanced parentheses
    paren_stack = []
    brace_stack = []
    exclusion_stack = []
    
    i = 0
    while i < len(pattern):
        # Handle exclusion syntax {- ... -}
        if i + 1 < len(pattern) and pattern[i:i+2] == "{-":
            exclusion_stack.append(i)
            i += 2  # Skip both characters
            continue
            
        if i + 1 < len(pattern) and pattern[i:i+2] == "-}":
            if not exclusion_stack:
                raise UnbalancedPatternError("Unmatched exclusion end marker", i, pattern)
            exclusion_stack.pop()
            i += 2  # Skip both characters
            continue
            
        # Handle regular characters
        if pattern[i] == '(':
            paren_stack.append(i)
        elif pattern[i] == ')':
            if not paren_stack:
                raise UnbalancedPatternError("Unmatched closing parenthesis", i, pattern)
            paren_stack.pop()
        elif pattern[i] == '{' and (i == 0 or pattern[i-1] != '-'):  # Not part of -}
            brace_stack.append(i)
        elif pattern[i] == '}' and (i + 1 >= len(pattern) or pattern[i+1] != '-'):  # Not part of {-
            if not brace_stack:
                raise UnbalancedPatternError("Unmatched closing brace", i, pattern)
            brace_stack.pop()
            
        # Check for invalid quantifier positions
        if pattern[i] in "*+?" and (i == 0 or pattern[i-1] in "|("):
            raise QuantifierError(f"Invalid quantifier '{pattern[i]}' position", i, pattern)
            
        i += 1
    
    # Check for unmatched opening constructs
    if paren_stack:
        raise UnbalancedPatternError("Unmatched opening parenthesis", paren_stack[-1], pattern)
    if brace_stack:
        raise UnbalancedPatternError("Unmatched opening brace", brace_stack[-1], pattern)
    if exclusion_stack:
        raise UnbalancedPatternError("Unmatched exclusion start marker", exclusion_stack[-1], pattern)

def extract_exclusion_variables(pattern: str) -> Set[str]:
    """
    Extract variables from exclusion patterns.
    
    Args:
        pattern: The pattern string
        
    Returns:
        Set of excluded variable names
        
    Raises:
        UnbalancedPatternError: If exclusion markers are unbalanced
    """
    excluded_vars = set()
    
    if not pattern or "{-" not in pattern or "-}" not in pattern:
        return excluded_vars
    
    # Find all exclusion sections
    start = 0
    while True:
        start_marker = pattern.find("{-", start)
        if start_marker == -1:
            break
        end_marker = pattern.find("-}", start_marker)
        if end_marker == -1:
            raise UnbalancedPatternError("Unbalanced exclusion markers", start_marker, pattern)
        
        # Extract excluded content
        excluded_content = pattern[start_marker + 2:end_marker].strip()
        logger.debug(f"Extracted exclusion content: '{excluded_content}'")
        
        # Extract excluded variables - handle base variables without quantifiers
        var_pattern = r'([A-Za-z_][A-Za-z0-9_]*)(?:[+*?]|\{[0-9,]*\})?'
        for match in re.finditer(var_pattern, excluded_content):
            var_name = match.group(1)
            excluded_vars.add(var_name)
            logger.debug(f"Exclusion handler added variable: '{var_name}'")
        
        start = end_marker + 2
    
    return excluded_vars


def process_permute_variables(pattern: str, start_pos: int) -> Tuple[List[Union[str, PatternToken]], int]:
    """
    Process variables in a PERMUTE expression, handling nested PERMUTE patterns.
    
    Args:
        pattern: The full pattern string
        start_pos: Position to start parsing from (after opening parenthesis)
        
    Returns:
        Tuple of (variables_list, new_position)
        
    Raises:
        PermutePatternError: If PERMUTE syntax is invalid
    """
    variables = []
    pos = start_pos
    var_start = pos
    nested_permute_depth = 0
    
    while pos < len(pattern):
        # Handle nested PERMUTE
        if pos + 7 <= len(pattern) and pattern[pos:pos+7].upper() == 'PERMUTE':
            # Extract any variable before this nested PERMUTE
            if pos > var_start:
                var_text = pattern[var_start:pos].strip()
                if var_text and not var_text.endswith(','):
                    if var_text.endswith(','):
                        var_text = var_text[:-1].strip()
                    if var_text:
                        variables.append(var_text)
            
            # Process the nested PERMUTE
            nested_start = pos
            pos += 7  # Skip "PERMUTE"
            
            # Skip whitespace
            while pos < len(pattern) and pattern[pos].isspace():
                pos += 1
                
            if pos >= len(pattern) or pattern[pos] != '(':
                raise PermutePatternError("Expected '(' after nested PERMUTE", pos, pattern)
                
            # Find matching closing parenthesis for the nested PERMUTE
            nested_paren_depth = 1
            pos += 1  # Skip opening parenthesis
            nested_content_start = pos
            
            while pos < len(pattern) and nested_paren_depth > 0:
                if pattern[pos] == '(':
                    nested_paren_depth += 1
                elif pattern[pos] == ')':
                    nested_paren_depth -= 1
                pos += 1
                
            if nested_paren_depth > 0:
                raise PermutePatternError("Unmatched parenthesis in nested PERMUTE", nested_start, pattern)
                
            # Extract nested PERMUTE content
            nested_content_end = pos - 1  # Position of closing parenthesis
            nested_content = pattern[nested_start:pos]
            
            # Recursively tokenize the nested PERMUTE
            nested_tokens = tokenize_pattern(nested_content)
            
            if nested_tokens and nested_tokens[0].type == PatternTokenType.PERMUTE:
                # Mark as nested and add to variables
                nested_tokens[0].metadata["nested"] = True
                variables.append(nested_tokens[0])
                
                # Check for quantifiers on the nested PERMUTE
                if pos < len(pattern) and pattern[pos] in "*+?{":
                    quantifier, is_greedy, pos = parse_quantifier_at(pattern, pos)
                    if nested_tokens[0]:
                        nested_tokens[0].quantifier = quantifier
                        nested_tokens[0].greedy = is_greedy
            
            var_start = pos
            
        elif pattern[pos] == ',':
            # Extract variable and skip comma
            if pos > var_start:
                var_text = pattern[var_start:pos].strip()
                if var_text:
                    variables.append(var_text)
            pos += 1
            var_start = pos
            
        elif pattern[pos] == ')':
            # Extract final variable before closing parenthesis
            if pos > var_start:
                var_text = pattern[var_start:pos].strip()
                if var_text:
                    variables.append(var_text)
            return variables, pos + 1  # Return position after closing parenthesis
            
        else:
            pos += 1
            
    # If we get here, we didn't find the closing parenthesis
    raise PermutePatternError("Unterminated PERMUTE expression", start_pos - 1, pattern)

def tokenize_pattern(pattern: str) -> List[PatternToken]:
    """
    Enhanced tokenizer with comprehensive support for all pattern syntax features.
    
    This tokenizer handles:
    - Basic pattern elements (literals, alternation, grouping)
    - Quantifiers (*, +, ?, {n}, {n,m})
    - Anchors (^ and $)
    - Pattern exclusions ({- ... -})
    - PERMUTE expressions with nested PERMUTE support
    - Subset variables
    """
    # First validate overall pattern structure
    validate_pattern_structure(pattern)
    
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
            
        # Handle exclusion syntax {- ... -}
        if i + 1 < len(pattern) and pattern[i:i+2] == "{-":
            tokens.append(PatternToken(PatternTokenType.EXCLUSION_START, "{-"))
            i += 2
            continue
            
        if i + 1 < len(pattern) and pattern[i:i+2] == "-}":
            # Handle exclusion end with potential quantifier
            exclusion_end_pos = i + 2
            
            # Check for quantifiers after the exclusion pattern
            quantifier = None
            is_greedy = True
            
            if exclusion_end_pos < len(pattern) and pattern[exclusion_end_pos] in "*+?{":
                quantifier, is_greedy, exclusion_end_pos = parse_quantifier_at(pattern, exclusion_end_pos)
            
            # Create exclusion end token with quantifier information
            tokens.append(PatternToken(
                PatternTokenType.EXCLUSION_END, 
                "-}", 
                quantifier=quantifier, 
                greedy=is_greedy
            ))
            i = exclusion_end_pos
            continue
            
        # Enhanced PERMUTE handling with recursive nesting and quantifiers
        if i+7 <= len(pattern) and pattern[i:i+7].upper() == 'PERMUTE':
            permute_start = i
            i += 7  # Move past "PERMUTE"
            
            # Skip whitespace after PERMUTE
            while i < len(pattern) and pattern[i].isspace():
                i += 1
                
            # Handle opening parenthesis
            if i >= len(pattern) or pattern[i] != '(':
                raise ValueError(f"Expected '(' after PERMUTE at position {i}")
            
            i += 1  # Skip opening parenthesis
            
            # Process PERMUTE variables
            variables, i = process_permute_variables(pattern, i)
            
            if not variables:
                raise ValueError(f"Empty PERMUTE not allowed at position {permute_start}")
            
            # Check for duplicate variables
            var_names = [v for v in variables if isinstance(v, str)]
            if len(var_names) != len(set(var_names)):
                raise ValueError(f"Duplicate variables in PERMUTE at position {permute_start}")
            
            # Check for quantifiers after the PERMUTE construct
            quantifier, is_greedy, i = parse_quantifier_at(pattern, i)
            
            # Create token with metadata about the PERMUTE variables
            permute_token = PatternToken(
                PatternTokenType.PERMUTE,
                f"PERMUTE({','.join(str(v) for v in variables)})",
                quantifier=quantifier,
                greedy=is_greedy,
                metadata={
                    "variables": variables,
                    "base_variables": [v for v in variables if isinstance(v, str)],
                    "permute": True,
                    "nested_permute": any(isinstance(v, PatternToken) and v.type == PatternTokenType.PERMUTE for v in variables),
                    "original": pattern[permute_start:i]
                }
            )
            
            tokens.append(permute_token)
            continue
        
        # Handle anchors
        elif char == '^':
            # Production-ready fix: Allow all anchor positions during parsing
            # Semantic validation will be handled during matching phase
            # This follows SQL:2016 standard and matches Trino/Java behavior
            tokens.append(PatternToken(
                PatternTokenType.ANCHOR_START, 
                "^",
                metadata={
                    "position": i,
                    "context": pattern[max(0, i-2):i+3] if len(pattern) > i+2 else pattern[max(0, i-2):],
                    "valid_position": i == 0 or (i > 1 and pattern[i-1] == '(' and pattern[i-2] == '|')
                }
            ))
            i += 1
        elif char == '$':
            # Production-ready fix: Allow all anchor positions during parsing
            # Semantic validation will be handled during matching phase
            tokens.append(PatternToken(
                PatternTokenType.ANCHOR_END, 
                "$",
                metadata={
                    "position": i,
                    "context": pattern[max(0, i-2):i+3] if len(pattern) > i+2 else pattern[max(0, i-2):],
                    "valid_position": i == len(pattern) - 1 or pattern[i+1] == ')' or pattern[i+1] == '|'
                }
            ))
            i += 1
        
        # Handle alternation
        elif char == '|':
            tokens.append(PatternToken(PatternTokenType.ALTERNATION, "|"))
            i += 1
        
        # Handle grouping
        elif char == '(':
            tokens.append(PatternToken(PatternTokenType.GROUP_START, "("))
            i += 1
        elif char == ')':
            # Parse quantifier if present
            next_pos = i + 1
            quantifier = None
            is_greedy = True
            
            if next_pos < len(pattern) and pattern[next_pos] in "*+?{":
                quantifier, is_greedy, next_pos = parse_quantifier_at(pattern, next_pos)
            
            # Add token with optional quantifier
            tokens.append(PatternToken(
                PatternTokenType.GROUP_END, 
                ")", 
                quantifier, 
                is_greedy
            ))
            
            i = next_pos
            
        # Handle isolated quantifiers (not attached to variables) - this is an error
        elif char == '{':
            # Check if this is an isolated quantifier
            temp_i = i
            brace_depth = 0
            while temp_i < len(pattern):
                if pattern[temp_i] == '{':
                    brace_depth += 1
                elif pattern[temp_i] == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        break
                temp_i += 1
            
            if temp_i < len(pattern) and brace_depth == 0:
                # This is a complete quantifier pattern
                quantifier_text = pattern[i:temp_i+1]
                raise QuantifierError(f"Isolated quantifier '{quantifier_text}' not attached to any variable", i, pattern)
            else:
                # Unclosed brace - let it fall through to be caught later
                i += 1
        
        # Handle literal with quantifier
        else:
            # Extract literal variable name
            var_start = i
            while i < len(pattern) and pattern[i] not in "|()*+?{}^$ \t\n\r" and not (i + 1 < len(pattern) and (pattern[i:i+2] == "{-" or pattern[i:i+2] == "-}")):
                i += 1
            
            if i > var_start:
                var_name = pattern[var_start:i]
                
                # Check for quantifiers
                quantifier, is_greedy, i = parse_quantifier_at(pattern, i)
                
                # Add token with optional quantifier
                tokens.append(PatternToken(
                    PatternTokenType.LITERAL, 
                    var_name, 
                    quantifier, 
                    is_greedy
                ))
            else:
                i += 1
    
    # Handle end anchor if present
    if pattern.endswith('$'):
        # If we already processed the $, don't add it again
        if len(tokens) == 0 or tokens[-1].type != PatternTokenType.ANCHOR_END:
            tokens.append(PatternToken(PatternTokenType.ANCHOR_END, "$"))
    
    return tokens


class PermuteHandler:
    """Handles PERMUTE patterns with lexicographical ordering and optimizations."""
    
    def __init__(self):
        """Initialize the permutation handler with cache."""
        self.permute_cache = {}
        
    def expand_permutation(self, variables):
        """
        Expands a PERMUTE pattern into all possible permutations
        in lexicographical order based on original variable order.
        
        Args:
            variables: List of pattern variables in the PERMUTE clause
        
        Returns:
            List of permutations in lexicographical order
        """
        # Use tuple as key for cache lookup
        if not variables:
            return []
            
        try:
            cache_key = tuple(str(v) for v in variables)
            if cache_key in self.permute_cache:
                return self.permute_cache[cache_key]
        except TypeError:
            # If variables can't be hashed, skip caching
            pass
        
        # Generate all permutations
        result = self._generate_permutations(variables)
        
        # Sort permutations based on original variable positions
        # This ensures lexicographical ordering per Trino spec
        var_priority = {str(var): idx for idx, var in enumerate(variables)}
        
        def permutation_key(perm):
            # Create a key for sorting based on original variable positions
            return [var_priority.get(str(var), len(variables)) for var in perm]
        
        result.sort(key=permutation_key)
        
        # Cache result if possible
        try:
            self.permute_cache[cache_key] = result
        except (TypeError, UnboundLocalError):
            # Skip caching if variables can't be hashed
            pass
            
        return result
    
    def _generate_permutations(self, variables):
        """
        Generate all permutations of the variables.
        
        Args:
            variables: List of variables to permute
            
        Returns:
            List of all permutations
        """
        if len(variables) <= 1:
            return [variables]
        
        result = []
        for i in range(len(variables)):
            # Get current variable
            current = variables[i]
            # Generate permutations of remaining variables
            remaining = variables[:i] + variables[i+1:]
            for p in self._generate_permutations(remaining):
                result.append([current] + p)
        
        return result
    
    def expand_nested_permute(self, pattern):
        """
        Handles nested PERMUTE patterns like PERMUTE(A, PERMUTE(B, C)).
        
        Args:
            pattern: Pattern object or metadata with potentially nested PERMUTE
            
        Returns:
            Expanded pattern with all permutations properly resolved
        """
        import itertools
        
        # Extract pattern text for parsing
        pattern_text = ""
        if hasattr(pattern, 'pattern'):
            pattern_text = pattern.pattern
        elif hasattr(pattern, 'metadata') and pattern.metadata.get('original_pattern'):
            pattern_text = pattern.metadata.get('original_pattern')
        elif isinstance(pattern, dict) and pattern.get('original_pattern'):
            pattern_text = pattern.get('original_pattern')
        else:
            pattern_text = str(pattern)
        
        # If we have a pattern with nested PERMUTE, parse it directly
        if 'PERMUTE' in pattern_text.upper():
            # First, handle the outer PERMUTE
            outer_match = re.search(r'PERMUTE\s*\(\s*(.*?)\s*\)', pattern_text, re.IGNORECASE | re.DOTALL)
            if outer_match:
                outer_content = outer_match.group(1)
                
                # Split the outer content by commas, but respect nested PERMUTE
                outer_vars = []
                var_start = 0
                paren_depth = 0
                in_nested = False
                
                i = 0
                while i < len(outer_content):
                    # Check for nested PERMUTE
                    if i + 7 <= len(outer_content) and outer_content[i:i+7].upper() == 'PERMUTE':
                        in_nested = True
                        nested_start = i
                        i += 7  # Skip "PERMUTE"
                        
                        # Skip whitespace
                        while i < len(outer_content) and outer_content[i].isspace():
                            i += 1
                        
                        # Find the matching parenthesis for this PERMUTE
                        if i < len(outer_content) and outer_content[i] == '(':
                            paren_depth = 1
                            i += 1  # Skip opening parenthesis
                            
                            while i < len(outer_content) and paren_depth > 0:
                                if outer_content[i] == '(':
                                    paren_depth += 1
                                elif outer_content[i] == ')':
                                    paren_depth -= 1
                                i += 1
                            
                            # Extract the entire nested PERMUTE expression
                            nested_expr = outer_content[nested_start:i]
                            
                            # Add any previous variable if exists
                            if var_start < nested_start:
                                prefix = outer_content[var_start:nested_start].strip()
                                if prefix and prefix != ',':
                                    if prefix.endswith(','):
                                        prefix = prefix[:-1].strip()
                                    if prefix:
                                        outer_vars.append(prefix)
                            
                            # Add the nested PERMUTE as a single variable
                            outer_vars.append(nested_expr)
                            
                            # Reset for next variable
                            var_start = i
                            in_nested = False
                            
                            # Skip any comma after the nested PERMUTE
                            if i < len(outer_content) and outer_content[i] == ',':
                                var_start = i + 1
                                i += 1
                            continue
                    
                    # Handle regular variable separation
                    if outer_content[i] == ',' and not in_nested and paren_depth == 0:
                        # Extract variable before comma
                        var = outer_content[var_start:i].strip()
                        if var:
                            outer_vars.append(var)
                        var_start = i + 1
                    
                    i += 1
                
                # Add the last variable if any
                if var_start < len(outer_content):
                    var = outer_content[var_start:].strip()
                    if var:
                        outer_vars.append(var)
                
                # Process each variable from the outer PERMUTE
                expanded_variables = []
                for var in outer_vars:
                    if isinstance(var, str) and 'PERMUTE' in var.upper():
                        # This is a nested PERMUTE - extract its variables
                        nested_match = re.search(r'PERMUTE\s*\(\s*(.*?)\s*\)', var, re.IGNORECASE | re.DOTALL)
                        if nested_match:
                            nested_content = nested_match.group(1)
                            nested_vars = [v.strip() for v in nested_content.split(',')]
                            # Expand the nested permutation
                            expanded = self.expand_permutation(nested_vars)
                            expanded_variables.append(expanded)
                        else:
                            # If we couldn't extract nested vars, treat as regular variable
                            expanded_variables.append([var])
                    else:
                        # Regular variable
                        expanded_variables.append([var])
                
                # Generate all combinations of the expanded variables
                result = []
                for combo in itertools.product(*expanded_variables):
                    result.append(list(itertools.chain.from_iterable(
                        [item] if isinstance(item, str) else item 
                        for item in combo
                    )))
                
                return result
        
        # Fallback to simple permutation if we couldn't parse the nested structure
        if hasattr(pattern, 'metadata'):
            variables = pattern.metadata.get('variables', [])
        elif isinstance(pattern, dict):
            variables = pattern.get('variables', [])
        else:
            variables = []
        
        if not variables:
            # Try to extract variables from the pattern text
            if pattern_text and 'PERMUTE' in pattern_text.upper():
                match = re.search(r'PERMUTE\s*\(\s*(.*?)\s*\)', pattern_text, re.IGNORECASE | re.DOTALL)
                if match:
                    content = match.group(1)
                    variables = [v.strip() for v in content.split(',')]
        
        if not variables:
            raise ValueError("No variables found in pattern")
        
        # Clean up variables - remove any PERMUTE prefixes
        clean_variables = []
        for var in variables:
            if isinstance(var, str) and 'PERMUTE' in var.upper():
                # Extract variables from this PERMUTE string
                match = re.search(r'PERMUTE\s*\(\s*(.*?)\s*\)', var, re.IGNORECASE | re.DOTALL)
                if match:
                    nested_vars = [v.strip() for v in match.group(1).split(',')]
                    clean_variables.extend(nested_vars)
                else:
                    clean_variables.append(var)
            else:
                clean_variables.append(var)
        
        return self.expand_permutation(clean_variables)


    def _parse_permute_content(self, content):
        """
        Parse PERMUTE content with proper handling of nested PERMUTE expressions.
        
        Args:
            content: The content inside a PERMUTE(...) expression
            
        Returns:
            List of variables, with nested PERMUTE expressions preserved
        """
        variables = []
        start = 0
        paren_depth = 0
        in_nested_permute = False
        nested_start = -1
        
        for i, char in enumerate(content):
            if char == '(' and not in_nested_permute and content[max(0, i-7):i].upper().endswith('PERMUTE'):
                in_nested_permute = True
                nested_start = max(0, i-7)
                paren_depth = 1
            elif in_nested_permute:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
                    if paren_depth == 0:
                        # End of nested PERMUTE
                        nested_expr = content[nested_start:i+1]
                        if start < nested_start:
                            # Add any content before the nested PERMUTE
                            prefix = content[start:nested_start].strip()
                            if prefix and prefix != ',':
                                if prefix.endswith(','):
                                    prefix = prefix[:-1].strip()
                                if prefix:
                                    variables.append(prefix)
                        variables.append(nested_expr)
                        in_nested_permute = False
                        start = i + 1
            elif char == ',' and not in_nested_permute:
                # Regular variable separator
                var = content[start:i].strip()
                if var:
                    variables.append(var)
                start = i + 1
        
        # Add the last variable if any
        if start < len(content) and not in_nested_permute:
            var = content[start:].strip()
            if var:
                variables.append(var)
        
        return variables
    
    def _extract_pattern_metadata(self, pattern):
        """
        Extract pattern metadata from various input types.
        
        Args:
            pattern: Pattern object, dict, or other object with metadata
            
        Returns:
            Dict containing pattern metadata
        """
        if hasattr(pattern, 'metadata'):
            return pattern.metadata
        elif isinstance(pattern, dict):
            return pattern
        elif hasattr(pattern, 'get'):
            return pattern
        else:
            # Try to extract from string representation
            if isinstance(pattern, str) and 'PERMUTE' in pattern.upper():
                return {'variables': self._extract_nested_permute_vars(pattern)}
            return {}
    
    def _extract_nested_permute_vars(self, permute_str):
        """
        Extract variables from a nested PERMUTE string.
        
        Args:
            permute_str: String containing PERMUTE expression
            
        Returns:
            List of variables in the PERMUTE expression
        """
        import re
        match = re.search(r'PERMUTE\s*\(\s*([^)]+)\s*\)', permute_str, re.IGNORECASE)
        if match:
            content = match.group(1)
            # Parse with proper handling of nested PERMUTE
            return self._parse_permute_content(content)
        return []
    
    def analyze_pattern_hierarchy(self, pattern_text):
        """
        Analyze a pattern to determine variable hierarchy for lexicographical ordering.
        
        For nested PERMUTE patterns, Trino applies these rules:
        1. Variables in outer PERMUTE have higher priority than inner PERMUTE variables
        2. Within each PERMUTE level, earlier variables have higher priority
        3. For sequences ending with the same variable, lexicographical ordering is applied
        """
        def parse_permute(text, level=0):
            """Recursively parse PERMUTE expressions."""
            match = re.search(r'PERMUTE\s*\((.+)\)', text, re.IGNORECASE)
            if not match:
                return []
            
            content = match.group(1)
            variables = []
            
            # Parse with proper handling of nested PERMUTE
            parsed_vars = self._parse_permute_content(content)
            
            for var in parsed_vars:
                if isinstance(var, str) and 'PERMUTE' in var.upper():
                    # Recursive parsing of nested PERMUTE
                    nested_vars = parse_permute(var, level + 1)
                    variables.extend(nested_vars)
                else:
                    # Regular variable
                    variables.append((var, level))
            
            return variables
        
        # Parse the pattern and create hierarchy
        variables = parse_permute(pattern_text)
        
        # Create priority map based on level and position
        # Lower priority number means higher priority
        priority = {}
        for idx, (var, level) in enumerate(variables):
            # Priority formula: level * 1000 + position
            # This ensures outer PERMUTE variables have higher priority
            priority[var] = level * 1000 + idx
        
        return priority