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

    def __repr__(self):
        if self.mode == "ONEROWPERMATCH":
            return "RowsPerMatchClause(mode=ONE ROW PER MATCH)"
        elif self.mode.startswith("ALLROWSPERMATCH"):
            base = "ALL ROWS PER MATCH"
            modifiers = []
            if self.show_empty is False or "OMITEMPTYMATCHES" in self.mode:
                modifiers.append("OMIT EMPTY MATCHES")
            elif self.show_empty is True or "SHOWEMPTYMATCHES" in self.mode:
                modifiers.append("SHOW EMPTY MATCHES")
            if self.with_unmatched or "WITHUNMATCHEDROWS" in self.mode:
                modifiers.append("WITH UNMATCHED ROWS")
            if modifiers:
                return f"RowsPerMatchClause(mode={base}, {', '.join(modifiers)})"
            else:
                return f"RowsPerMatchClause(mode={base})"
        else:
            return f"RowsPerMatchClause(mode={self.raw_mode})"

@dataclass
class AfterMatchSkipClause(ASTNode):
    value: str

#
# Updated PatternClause: it extracts tokens using regex and stores both the full token (e.g. "b+")
# and the base variable (e.g. "b") in the metadata.
#


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

# --- AST Node for PatternClause ---

@dataclass
class PatternClause:
    """
    Represents the PATTERN clause in MATCH_RECOGNIZE.
    
    Initially tokenizes the raw pattern string (using a basic regex).
    Later, if variable definitions are provided (via the DEFINE clause),
    the update_from_defined method re‑tokenizes the pattern based on the
    defined variable names. This method attaches any following quantifier
    (e.g. +, *, ?, {2,4} with optional ?) without altering their original format.
    """
    pattern: str
    metadata: Dict = field(init=False)

    # Reserved keywords that should not be treated as variables.
    RESERVED_KEYWORDS = {"PERMUTE", "AND", "OR", "NOT"}

    def __post_init__(self):
        self.metadata = {}
        self._tokenize_initial()

    def _clean_pattern(self, pattern: str) -> str:
        """
        Clean the pattern string:
         - Remove outer parentheses if they wrap the entire pattern.
         - If the pattern starts with PERMUTE(...), remove commas entirely;
           otherwise, remove commas only outside of curly braces.
         - Collapse multiple whitespace characters.
        """
        pattern = pattern.strip()
        if pattern.startswith('(') and pattern.endswith(')') and balanced_parentheses(pattern):
            pattern = pattern[1:-1].strip()
        if pattern.upper().startswith("PERMUTE("):
            pattern = re.sub(r',', '', pattern)
            pattern = re.sub(r'PERMUTE\s*\((.*?)\)', r'\1', pattern, flags=re.IGNORECASE)
        else:
            pattern = remove_commas_outside_curly(pattern)
        pattern = re.sub(r'\s+', ' ', pattern).strip()
        return pattern

    def _tokenize_initial(self):
        """
        Perform an initial tokenization of the cleaned pattern.
        If whitespace is present, a simple split is used; otherwise, a regex with a lookahead is used.
        """
        cleaned = self._clean_pattern(self.pattern)
        # Allow empty patterns (empty match)
        if cleaned == "":
            self.metadata = {"variables": [], "base_variables": []}
            return
        if ' ' in cleaned:
            raw_tokens = cleaned.split()
        else:
             raw_tokens = re.findall(r'([A-Za-z][A-Za-z0-9_]*[\\*\\+\\?\\{\\}0-9]*)(?=[A-Za-z]|$)', cleaned)
        full_tokens = []
        base_tokens = []
        for token in raw_tokens:
            m = re.fullmatch(r'([A-Za-z][A-Za-z0-9_]*)([\*\+\?\{\}0-9]*)', token)
            if m:
                base, quant = m.groups()
                if base in self.RESERVED_KEYWORDS:
                    continue
                full_tokens.append(base + quant)
                base_tokens.append(base)
        self.metadata = {"variables": full_tokens, "base_variables": base_tokens}

    def update_from_defined(self, defined_vars: List[str]):
        """
        Re-tokenize the pattern string using the defined variable names.
        
        This method scans the cleaned pattern from left to right and attempts to match
        one of the defined variable names (sorted by length descending to prioritize
        multi‑letter names). If a match is found, it consumes any attached quantifier
        (such as +, *, ?, or bounded quantifiers like {2,4} possibly followed by a ?)
        and appends the token. Grouping symbols (parentheses) and whitespace are skipped.
        If no defined variable matches at the current position and the character is a quantifier,
        it is attached to the previous token. Otherwise, unexpected literals are skipped.
        """
        cleaned = self._clean_pattern(self.pattern)
        if cleaned == "":
            self.metadata = {"variables": [], "base_variables": []}
            return
        tokens = []
        i = 0
        # Sort defined variables by length descending (longest first)
        sorted_vars = sorted(defined_vars, key=len, reverse=True)
        # Define quantifier starting characters
        quant_chars = set("*+?")
        while i < len(cleaned):
            ch = cleaned[i]
            # Skip whitespace and grouping symbols
            if ch.isspace() or ch in "()":
                i += 1
                continue
            match_found = False
            for var in sorted_vars:
                if cleaned.startswith(var, i):
                    token = var
                    i += len(var)
                    quant = ""
                    # Check for bounded quantifier starting with '{'
                    if i < len(cleaned) and cleaned[i] == '{':
                        start_quant = i
                        while i < len(cleaned) and cleaned[i] != '}':
                            i += 1
                        if i < len(cleaned) and cleaned[i] == '}':
                            i += 1
                            quant = cleaned[start_quant:i]
                            if i < len(cleaned) and cleaned[i] == '?':
                                quant += '?'
                                i += 1
                    else:
                        while i < len(cleaned) and cleaned[i] in quant_chars:
                            quant += cleaned[i]
                            i += 1
                    token += quant
                    tokens.append(token)
                    match_found = True
                    break
            if not match_found:
                # If the character is a quantifier, attach it to the last token if available.
                if ch in quant_chars:
                    if tokens:
                        tokens[-1] += ch
                    i += 1
                    continue
                # Skip any unexpected literal character.
                i += 1
        base_tokens = [re.sub(r'([\*\+\?]|(\{[0-9,\s]+\})(\?)?)$', '', token) for token in tokens]
        self.metadata = {"variables": tokens, "base_variables": base_tokens}

    def __repr__(self):
        return f"PatternClause(pattern={self.pattern!r}, metadata={self.metadata})"


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
                f"  rows_per_match={self.rows_per_match},\n"
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
