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
        # Add PERMUTE-specific metadata initialization
        if self.type == PatternTokenType.PERMUTE:
            if "variables" not in self.metadata:
                self.metadata["variables"] = []
            if "nested" not in self.metadata:
                self.metadata["nested"] = False
            if "original" not in self.metadata:
                self.metadata["original"] = ""


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


def extract_exclusion_variables(pattern: str) -> Set[str]:
    """
    Extract variables from exclusion patterns.
    
    Args:
        pattern: The pattern string
        
    Returns:
        Set of excluded variable names
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
            print(f"Warning: Unbalanced exclusion markers in pattern: {pattern}")
            break
        
        # Extract excluded content
        excluded_content = pattern[start_marker + 2:end_marker].strip()
        
        # Extract excluded variables
        var_pattern = r'([A-Za-z_][A-Za-z0-9_]*)(?:[+*?]|\{[0-9,]*\})?'
        excluded_vars.update(re.findall(var_pattern, excluded_content))
        
        start = end_marker + 2
    
    return excluded_vars

def tokenize_pattern(pattern: str) -> List[PatternToken]:
    """Enhanced tokenizer with comprehensive support for all pattern syntax features including nested PERMUTE."""
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
            
        # Enhanced PERMUTE handling with recursive nesting and quantifiers
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
                        nested_paren_depth = 0
                        
                        # Skip to the opening parenthesis of nested PERMUTE
                        j = i + 7  # After "PERMUTE"
                        while j < len(pattern) and pattern[j] != '(':
                            if not pattern[j].isspace():
                                # Found non-whitespace before opening parenthesis
                                print(f"Warning: Unexpected character '{pattern[j]}' after PERMUTE")
                            j += 1
                        
                        if j < len(pattern) and pattern[j] == '(':
                            # Found opening parenthesis for nested PERMUTE
                            nested_paren_start = j
                            nested_paren_depth = 1
                            j += 1
                            
                            # Find matching closing parenthesis
                            while j < len(pattern) and nested_paren_depth > 0:
                                if pattern[j] == '(':
                                    nested_paren_depth += 1
                                elif pattern[j] == ')':
                                    nested_paren_depth -= 1
                                j += 1
                            
                            if nested_paren_depth == 0:
                                # Successfully found the end of nested PERMUTE
                                nested_permute_text = pattern[nested_permute_start:j]
                                nested_tokens = tokenize_pattern(nested_permute_text)
                                
                                if nested_tokens:
                                    # Add the nested PERMUTE token to our variables
                                    nested_tokens[0].metadata["nested"] = True
                                    variables.append(nested_tokens[0])
                                
                                # Update the outer loop position
                                i = j
                                var_start = j
                                
                                # Check for quantifiers after the nested PERMUTE
                                quantifier = None
                                if i < len(pattern) and pattern[i] in '*+?':
                                    quantifier = pattern[i]
                                    i += 1
                                    
                                    # Check for non-greedy marker
                                    greedy = True
                                    if i < len(pattern) and pattern[i] == '?':
                                        greedy = False
                                        i += 1
                                        
                                    # Apply quantifier to the last nested token
                                    if nested_tokens and isinstance(variables[-1], PatternToken):
                                        variables[-1].quantifier = quantifier
                                        variables[-1].greedy = greedy
                                elif i < len(pattern) and pattern[i] == '{':
                                    # Complex quantifier like {n}, {n,m}, etc.
                                    quant_start = i
                                    brace_depth = 1
                                    i += 1
                                    
                                    while i < len(pattern) and brace_depth > 0:
                                        if pattern[i] == '{':
                                            brace_depth += 1
                                        elif pattern[i] == '}':
                                            brace_depth -= 1
                                        i += 1
                                    
                                    quantifier = pattern[quant_start:i]
                                    
                                    # Check for non-greedy marker
                                    greedy = True
                                    if i < len(pattern) and pattern[i] == '?':
                                        greedy = False
                                        i += 1
                                        
                                    # Apply quantifier to the last nested token
                                    if nested_tokens and isinstance(variables[-1], PatternToken):
                                        variables[-1].quantifier = quantifier
                                        variables[-1].greedy = greedy
                                
                                # If we're at a comma, skip it
                                if i < len(pattern) and pattern[i] == ',':
                                    i += 1
                                    var_start = i
                            else:
                                # Unbalanced parentheses in nested PERMUTE
                                print(f"Warning: Unbalanced parentheses in nested PERMUTE: {pattern[nested_permute_start:]}")
                                # Try to continue anyway
                                i += 1
                        else:
                            # Expected opening parenthesis not found
                            print(f"Warning: Missing opening parenthesis after PERMUTE keyword")
                            i += 1
                    elif pattern[i] == '(':
                        nested_depth += 1
                        i += 1
                    elif pattern[i] == ')':
                        nested_depth -= 1
                        if nested_depth > 0:
                            i += 1
                        else:
                            # Before closing, extract any last variable
                            if i > var_start:
                                var_text = pattern[var_start:i].strip()
                                if var_text:
                                    if var_text.endswith(','):
                                        var_text = var_text[:-1].strip()
                                    if var_text:
                                        variables.append(var_text)
                            i += 1  # Skip closing parenthesis
                    elif pattern[i] == ',':
                        # Extract variable and skip comma
                        if i > var_start:
                            var_text = pattern[var_start:i].strip()
                            if var_text:
                                variables.append(var_text)
                        i += 1
                        var_start = i
                    else:
                        i += 1
                
                # Check for quantifiers after the PERMUTE construct
                quantifier = None
                greedy = True
                
                if i < len(pattern) and pattern[i] in '*+?':
                    quantifier = pattern[i]
                    i += 1
                    
                    # Check for non-greedy marker
                    if i < len(pattern) and pattern[i] == '?':
                        greedy = False
                        i += 1
                elif i < len(pattern) and pattern[i] == '{':
                    # Complex quantifier like {n}, {n,m}, etc.
                    quant_start = i
                    brace_depth = 1
                    i += 1
                    
                    while i < len(pattern) and brace_depth > 0:
                        if pattern[i] == '{':
                            brace_depth += 1
                        elif pattern[i] == '}':
                            brace_depth -= 1
                        i += 1
                    
                    quantifier = pattern[quant_start:i]
                    
                    # Check for non-greedy marker
                    if i < len(pattern) and pattern[i] == '?':
                        greedy = False
                        i += 1
                
                # Create token with metadata about the PERMUTE variables
                permute_token = PatternToken(
                    PatternTokenType.PERMUTE,
                    f"PERMUTE({','.join(str(v) for v in variables)})",
                    quantifier=quantifier,
                    greedy=greedy,
                    metadata={
                        "variables": variables,
                        "base_variables": [v for v in variables if not isinstance(v, PatternToken)],
                        "permute": True,
                        "nested_permute": any(isinstance(v, PatternToken) and v.type == PatternTokenType.PERMUTE for v in variables),
                        "original": pattern[permute_start:i]
                    }
                )
                
                tokens.append(permute_token)
            else:
                # Invalid PERMUTE - missing opening parenthesis
                print(f"Warning: Invalid PERMUTE syntax at position {i}")
                tokens.append(PatternToken(PatternTokenType.LITERAL, "PERMUTE"))
                i += 7
        
        # Handle pattern exclusion
        elif char == '{' and i + 1 < len(pattern) and pattern[i + 1] == '-':
            tokens.append(PatternToken(PatternTokenType.EXCLUSION_START, "{-"))
            i += 2
        elif char == '-' and i + 1 < len(pattern) and pattern[i + 1] == '}':
            tokens.append(PatternToken(PatternTokenType.EXCLUSION_END, "-}"))
            i += 2
        
        # Handle anchors
        elif char == '^':
            tokens.append(PatternToken(PatternTokenType.ANCHOR_START, "^"))
            i += 1
        elif char == '$':
            tokens.append(PatternToken(PatternTokenType.ANCHOR_END, "$"))
            i += 1
        
        # Handle alternation
        elif char == '|':
            tokens.append(PatternToken(PatternTokenType.ALTERNATION, "|"))
            i += 1
        
        # Handle grouping
        elif char == '(':
            tokens.append(PatternToken(PatternTokenType.GROUP_START, "("))
            paren_depth += 1
            i += 1
        elif char == ')':
            paren_depth -= 1
            
            # Check for quantifiers
            quantifier = None
            is_greedy = True
            
            # Look ahead for quantifiers
            if i + 1 < len(pattern) and pattern[i + 1] in "*+?{":
                j = i + 1
                
                # Extended quantifier like {n,m}
                if pattern[j] == '{':
                    quant_start = j
                    j += 1
                    while j < len(pattern) and pattern[j] != '}':
                        j += 1
                    if j < len(pattern) and pattern[j] == '}':
                        quantifier = pattern[quant_start:j+1]
                        j += 1
                else:
                    # Simple quantifier
                    quantifier = pattern[j]
                    j += 1
                
                # Check for reluctant quantifier
                if j < len(pattern) and pattern[j] == '?':
                    is_greedy = False
                    quantifier += '?'
                    j += 1
                
                i = j  # Update position past quantifier
            else:
                i += 1
            
            # Add token with optional quantifier
            tokens.append(PatternToken(
                PatternTokenType.GROUP_END, 
                ")", 
                quantifier, 
                is_greedy
            ))
            
        # Handle literal with quantifier
        else:
            # Extract literal variable name
            var_start = i
            while i < len(pattern) and pattern[i] not in "|()*+?{}^$ \t\n\r":
                i += 1
            
            if i > var_start:
                var_name = pattern[var_start:i]
                
                # Check for quantifiers
                quantifier = None
                is_greedy = True
                
                if i < len(pattern) and pattern[i] in "*+?{":
                    j = i
                    
                    # Extended quantifier like {n,m}
                    if pattern[j] == '{':
                        quant_start = j
                        j += 1
                        while j < len(pattern) and pattern[j] != '}':
                            j += 1
                        if j < len(pattern) and pattern[j] == '}':
                            quantifier = pattern[quant_start:j+1]
                            j += 1
                    else:
                        # Simple quantifier
                        quantifier = pattern[j]
                        j += 1
                    
                    # Check for reluctant quantifier
                    if j < len(pattern) and pattern[j] == '?':
                        is_greedy = False
                        quantifier += '?'
                        j += 1
                    
                    i = j  # Update position past quantifier
                
                # Add token with optional quantifier
                tokens.append(PatternToken(
                    PatternTokenType.LITERAL, 
                    var_name, 
                    quantifier, 
                    is_greedy
                ))
    
    # Handle end anchor if present
    if pattern.endswith('$'):
        # If we already processed the $, don't add it again
        if len(tokens) == 0 or tokens[-1].type != PatternTokenType.ANCHOR_END:
            tokens.append(PatternToken(PatternTokenType.ANCHOR_END, "$"))
    
    # Return the list of tokens
    return tokens

class PermuteHandler:
    """Handles PERMUTE patterns with lexicographical ordering and optimizations"""
    
    def __init__(self):
        self.permute_cache = {}
        
    def expand_permutation(self, variables):
        """
        Expands a PERMUTE pattern into all possible permutations
        in lexicographical order based on original variable order
        
        Args:
            variables: List of pattern variables in the PERMUTE clause
        
        Returns:
            List of permutations in lexicographical order
        """
        # Use tuple as key for cache lookup
        cache_key = tuple(variables)
        if cache_key in self.permute_cache:
            return self.permute_cache[cache_key]
        
        # Generate all permutations
        result = self._generate_permutations(variables)
        
        # Sort permutations based on original variable positions
        # This ensures lexicographical ordering per Trino spec
        var_priority = {var: idx for idx, var in enumerate(variables)}
        
        def permutation_key(perm):
            # Create a key for sorting based on original variable positions
            return [var_priority[var] for var in perm]
        
        result.sort(key=permutation_key)
        
        # Cache result
        self.permute_cache[cache_key] = result
        return result
    
    def _generate_permutations(self, variables):
        """Generate all permutations of the variables"""
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
        Handles nested PERMUTE patterns like PERMUTE(A, PERMUTE(B, C))
        
        Args:
            pattern: Pattern object with potentially nested PERMUTE
            
        Returns:
            Expanded pattern with all permutations properly resolved
        """
        # Implementation would depend on your pattern representation
        if not self._has_nested_permute(pattern):
            return self.expand_permutation(pattern['variables'])
            
        # Process nested permutations first, then outer permutation
        expanded_variables = []
        for component in pattern.get('components', []):
            if component.get('permute', False):
                # Recursively expand nested permute
                expanded = self.expand_nested_permute(component)
                expanded_variables.append(expanded)
            else:
                expanded_variables.append([component.get('variable')])
        
        # Flatten the expanded variables
        flat_variables = [var for sublist in expanded_variables for var in sublist]
        return self.expand_permutation(flat_variables)
        
    def _has_nested_permute(self, pattern):
        """Check if pattern has nested PERMUTE"""
        if not pattern.get('permute', False):
            return False
            
        for component in pattern.get('components', []):
            if component.get('permute', False):
                return True
                
        return False

