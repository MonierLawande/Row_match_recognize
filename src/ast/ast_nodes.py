from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional,Tuple
# Base AST node
class ASTNode:
    """Base class for all AST nodes."""
    pass

# --- MATCH_RECOGNIZE Clause AST Nodes ---

@dataclass
class PartitionByClause(ASTNode):
    columns: List[str]

@dataclass
class SortItem(ASTNode):
    column: str
    ordering: str = "ASC"
    nulls_ordering: Optional[str] = None

    def __post_init__(self):
        self.ordering = self.ordering.upper()
        if self.nulls_ordering:
            self.nulls_ordering = self.nulls_ordering.upper()

@dataclass
class OrderByClause(ASTNode):
    sort_items: List[SortItem]

@dataclass
class Measure(ASTNode):
    expression: str
    alias: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    is_classifier: bool = field(init=False)
    is_match_number: bool = field(init=False)

    def __post_init__(self):
        self.is_classifier = re.match(r'CLASSIFIER\(\s*([A-Za-z][A-Za-z0-9_]*)?\s*\)', self.expression) is not None
        self.is_match_number = re.match(r'MATCH_NUMBER\(\s*\)', self.expression) is not None

@dataclass
class MeasuresClause(ASTNode):
    measures: List[Measure]

@dataclass
class RowsPerMatchClause(ASTNode):
    raw_mode: str
    show_empty: Optional[bool] = None
    with_unmatched: Optional[bool] = None
    mode: str = field(init=False)

    def __post_init__(self):
        self.raw_mode = self.raw_mode.strip()
        self.mode = self.raw_mode.replace(" ", "").upper()

    @staticmethod
    def one_row_per_match():
        return RowsPerMatchClause("ONE ROW PER MATCH")

    @staticmethod
    def all_rows_per_match_show_empty():
        return RowsPerMatchClause("ALL ROWS PER MATCH", show_empty=True, with_unmatched=False)

    @staticmethod
    def all_rows_per_match_omit_empty():
        return RowsPerMatchClause("ALL ROWS PER MATCH", show_empty=False, with_unmatched=False)

    @staticmethod
    def all_rows_per_match_with_unmatched():
        return RowsPerMatchClause("ALL ROWS PER MATCH", show_empty=True, with_unmatched=True)

    def __str__(self):
        if self.mode == "ONEROWPERMATCH":
            return "ONE ROW PER MATCH"
        elif self.mode.startswith("ALLROWSPERMATCH"):
            base = "ALL ROWS PER MATCH"
            modifiers = []
            if self.show_empty is False or "OMITEMPTYMATCHES" in self.mode:
                modifiers.append("OMIT EMPTY MATCHES")
            elif self.show_empty is True or "SHOWEMPTYMATCHES" in self.mode:
                modifiers.append("SHOW EMPTY MATCHES")
            if self.with_unmatched or "WITHUNMATCHEDROWS" in self.mode:
                modifiers.append("WITH UNMATCHED ROWS")
            return f"{base} {' '.join(modifiers)}".strip()
        else:
            return self.raw_mode

    def __repr__(self):
        return f"RowsPerMatchClause(raw_mode='{self.__str__()}')"

# First, update the AfterMatchSkipClause class in src/ast/ast_nodes.py
@dataclass
class AfterMatchSkipClause(ASTNode):
    """
    Represents the AFTER MATCH SKIP clause in MATCH_RECOGNIZE.
    
    The options are:
    - AFTER MATCH SKIP PAST LAST ROW (default)
    - AFTER MATCH SKIP TO NEXT ROW 
    - AFTER MATCH SKIP TO FIRST pattern_variable
    - AFTER MATCH SKIP TO LAST pattern_variable
    """
    mode: str  # 'PAST LAST ROW', 'TO NEXT ROW', 'TO FIRST', 'TO LAST'
    target_variable: Optional[str] = None  # Used with 'TO FIRST' and 'TO LAST' modes
    raw_value: Optional[str] = None  # Original text (for debugging/display)
    
    def __post_init__(self):
        # Store original text if not provided
        if self.raw_value is None:
            if self.mode == 'PAST LAST ROW':
                self.raw_value = "AFTER MATCH SKIP PAST LAST ROW"
            elif self.mode == 'TO NEXT ROW':
                self.raw_value = "AFTER MATCH SKIP TO NEXT ROW"
            elif self.mode in ['TO FIRST', 'TO LAST']:
                position = "FIRST" if self.mode == 'TO FIRST' else "LAST"
                self.raw_value = f"AFTER MATCH SKIP TO {position} {self.target_variable}"
            else:
                # Custom mode
                self.raw_value = f"AFTER MATCH SKIP {self.mode}"
    
    @property
    def value(self):
        """Get the full text representation (for backward compatibility)"""
        return self.raw_value
    
    @staticmethod
    def past_last_row():
        """Create an AFTER MATCH SKIP PAST LAST ROW clause (default)"""
        return AfterMatchSkipClause('PAST LAST ROW')
    
    @staticmethod
    def to_next_row():
        """Create an AFTER MATCH SKIP TO NEXT ROW clause"""
        return AfterMatchSkipClause('TO NEXT ROW')
    
    @staticmethod
    def to_first(variable):
        """Create an AFTER MATCH SKIP TO FIRST variable clause"""
        return AfterMatchSkipClause('TO FIRST', variable)
    
    @staticmethod
    def to_last(variable):
        """Create an AFTER MATCH SKIP TO LAST variable clause"""
        return AfterMatchSkipClause('TO LAST', variable)
    
    def __str__(self):
        return self.raw_value
    
    def __repr__(self):
        return f"AfterMatchSkipClause(mode='{self.mode}', target_variable={repr(self.target_variable)})"











def balanced_parentheses(s: str) -> bool:
    """Simple check to verify that parentheses in s are balanced."""
    count = 0
    for ch in s:
        if ch == '(':
            count += 1
        elif ch == ')':
            count -= 1
            if count < 0:
                return False
    return count == 0

def remove_commas_outside_curly(pattern: str) -> str:
    """
    Remove commas that are not inside curly braces.
    """
    result = []
    in_curly = False
    for ch in pattern:
        if ch == '{':
            in_curly = True
            result.append(ch)
        elif ch == '}':
            in_curly = False
            result.append(ch)
        elif ch == ',' and not in_curly:
            continue
        else:
            result.append(ch)
    return ''.join(result)
@dataclass
class PatternClause:
    """
    Represents the PATTERN clause in MATCH_RECOGNIZE.
    """
    RESERVED_KEYWORDS = {"PERMUTE", "AND", "OR", "NOT"}
    pattern: str
    metadata: Dict = field(default_factory=dict)
    
    def __init__(self, pattern: str):
        # Store the original pattern exactly as entered
        self.pattern = pattern
        self.metadata = {}
        self._tokenize_initial()
    
    def _clean_pattern(self, pattern: str) -> str:
        """Clean the pattern string for tokenization purposes only."""
        pattern = pattern.strip()
        # Remove outer parentheses if they wrap the entire pattern
        if pattern.startswith('(') and pattern.endswith(')') and balanced_parentheses(pattern):
            pattern = pattern[1:-1].strip()
        # Handle PERMUTE patterns
        if pattern.upper().startswith("PERMUTE("):
            pattern = re.sub(r',', '', pattern)
            pattern = re.sub(r'PERMUTE\s*\((.*?)\)', r'\1', pattern, flags=re.IGNORECASE)
        else:
            pattern = remove_commas_outside_curly(pattern)
        # Don't remove spaces here to preserve the original pattern format
        return pattern
    
    def _tokenize_pattern(self, pattern: str, defined_vars: List[str] = None) -> List[Tuple[str, str]]:
        """
        Tokenize a pattern string into a list of (variable, quantifier) tuples.
        If defined_vars is provided, use it to guide tokenization.
        """
        tokens = []
        i = 0
        pattern = pattern.strip()
        
        # If we have defined variables, sort them by length (longest first)
        # to prioritize matching longer variable names
        if defined_vars:
            sorted_vars = sorted(defined_vars, key=len, reverse=True)
        else:
            sorted_vars = None
        
        while i < len(pattern):
            # Skip special characters but preserve spaces in the original pattern
            if pattern[i] in {'|', '&', '!', '(', ')', ','}:
                i += 1
                continue
            elif pattern[i].isspace():
                i += 1
                continue
            
            # Try to match defined variables first (if available)
            matched = False
            if sorted_vars:
                for var in sorted_vars:
                    if pattern[i:].startswith(var) and (i + len(var) >= len(pattern) or 
                                                       not pattern[i + len(var)].isalnum() and 
                                                       pattern[i + len(var)] != '_'):
                        var_name = var
                        i += len(var)
                        matched = True
                        break
            
            # If no defined variable matched, try to match a single character variable
            if not matched and pattern[i].isalpha():
                var_name = pattern[i]
                i += 1
                matched = True
            
            # If we matched a variable, look for a quantifier
            if matched:
                quant = ""
                if i < len(pattern):
                    if pattern[i] in {'*', '+', '?'}:
                        quant = pattern[i]
                        i += 1
                        # Check for reluctant quantifier
                        if i < len(pattern) and pattern[i] == '?':
                            quant += '?'
                            i += 1
                    elif pattern[i] == '{':
                        # Handle range quantifier
                        j = pattern.find('}', i)
                        if j != -1:
                            quant = pattern[i:j+1]
                            if j+1 < len(pattern) and pattern[j+1] == '?':
                                quant += '?'
                                j += 1
                            i = j + 1
                
                # Add token if it's not a reserved keyword
                if var_name.upper() not in self.RESERVED_KEYWORDS:
                    tokens.append((var_name, quant))
            else:
                # Skip any character we couldn't match
                i += 1
        
        return tokens

    def _tokenize_initial(self):
        """Initial tokenization of the pattern."""
        # Use the original pattern for metadata extraction
        cleaned = self._clean_pattern(self.pattern)
        # For initial tokenization, we don't have defined variables yet
        # So we tokenize character by character
        tokens = []
        i = 0
        while i < len(cleaned):
            if cleaned[i] in {'|', '&', '!', '(', ')', ','}:
                i += 1
                continue
            elif cleaned[i].isspace():
                i += 1
                continue
            
            if cleaned[i].isalpha():
                var_name = cleaned[i]
                i += 1
                
                # Look for quantifier
                quant = ""
                if i < len(cleaned):
                    if cleaned[i] in {'*', '+', '?'}:
                        quant = cleaned[i]
                        i += 1
                        if i < len(cleaned) and cleaned[i] == '?':
                            quant += '?'
                            i += 1
                    elif cleaned[i] == '{':
                        j = cleaned.find('}', i)
                        if j != -1:
                            quant = cleaned[i:j+1]
                            if j+1 < len(cleaned) and cleaned[j+1] == '?':
                                quant += '?'
                                j += 1
                            i = j + 1
                
                if var_name.upper() not in self.RESERVED_KEYWORDS:
                    tokens.append((var_name, quant))
            else:
                i += 1
        
        # Extract base variables and full variables
        base_variables = []
        full_variables = []
        
        for var, quant in tokens:
            if var not in base_variables:
                base_variables.append(var)
            full_token = var + quant
            if full_token not in full_variables:
                full_variables.append(full_token)
        
        self.metadata = {
            "variables": full_variables,
            "base_variables": base_variables
        }

    def update_from_defined(self, defined_vars: List[str], subset_vars: Dict[str, List[str]] = None):
        """Update pattern metadata based on defined variables."""
        # Re-tokenize with defined variables as guidance
        cleaned = self._clean_pattern(self.pattern)
        tokens = self._tokenize_pattern(cleaned, defined_vars)
        
        # Extract base variables and full variables
        base_variables = []
        full_variables = []
        
        for var, quant in tokens:
            if var not in base_variables and var.upper() not in self.RESERVED_KEYWORDS:
                base_variables.append(var)
            full_token = var + quant
            if full_token not in full_variables:
                full_variables.append(full_token)
        
        # Verify defined variables exist in pattern or in a subset
        defined_set = set(defined_vars)
        current_base_vars = set(base_variables)
        
        # Add subset components to valid variables if their union variable is in the pattern
        if subset_vars:
            for subset_name, components in subset_vars.items():
                if subset_name in current_base_vars:  # If the union variable is in the pattern
                    # Add the subset name and its components to valid variables
                    current_base_vars.update(components)
                    # Also add the subset name itself if it's defined
                    if subset_name in defined_set:
                        current_base_vars.add(subset_name)
        
        # Check for undefined variables
        if not defined_set.issubset(current_base_vars):
            extra_vars = defined_set - current_base_vars
            raise ValueError(f"Defined variables {extra_vars} not found in pattern or subsets")
        
        self.metadata = {
            "variables": full_variables,
            "base_variables": base_variables
        }

        
    def __repr__(self):
        return f"PatternClause(pattern='{self.pattern}', metadata={self.metadata})"
@dataclass
class SubsetClause(ASTNode):
    subset_text: str

@dataclass
class Define(ASTNode):
    variable: str
    condition: str

@dataclass
class DefineClause(ASTNode):
    definitions: List[Define]

@dataclass
class MatchRecognizeClause(ASTNode):
    partition_by: Optional[PartitionByClause] = None
    order_by: Optional[OrderByClause] = None
    measures: Optional[MeasuresClause] = None
    rows_per_match: Optional[RowsPerMatchClause] = None
    after_match_skip: Optional[AfterMatchSkipClause] = None
    pattern: Optional[PatternClause] = None
    subset: List[SubsetClause] = field(default_factory=list)
    define: Optional[DefineClause] = None


    def __repr__(self):
        return (f"MatchRecognizeClause(\n"
                f"  partition_by={self.partition_by},\n"
                f"  order_by={self.order_by},\n"
                f"  measures={self.measures},\n"
                f"  rows_per_match={str(self.rows_per_match) if self.rows_per_match else None},\n"
                f"  after_match_skip={self.after_match_skip},\n"
                f"  pattern={self.pattern},\n"
                f"  subset={self.subset},\n"
                f"  define={self.define}\n)")

# --- Full Query AST Nodes ---
@dataclass
class SelectItem(ASTNode):
    expression: str
    alias: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def __repr__(self):
        if self.alias:
            return f"SelectItem(expression={self.expression}, alias={self.alias}, metadata={self.metadata})"
        return f"SelectItem(expression={self.expression}, metadata={self.metadata})"

@dataclass
class SelectClause(ASTNode):
    items: List[SelectItem]

@dataclass
class FromClause(ASTNode):
    table: str

@dataclass
class FullQueryAST(ASTNode):
    select_clause: Optional[SelectClause]
    from_clause: Optional[FromClause]
    match_recognize: Optional[MatchRecognizeClause]
    metadata: Dict = field(default_factory=dict)

    def __repr__(self):
        return (f"FullQueryAST(\n"
                f"  select_clause={self.select_clause},\n"
                f"  from_clause={self.from_clause},\n"
                f"  match_recognize={self.match_recognize},\n"
                f"  metadata={self.metadata}\n)")
