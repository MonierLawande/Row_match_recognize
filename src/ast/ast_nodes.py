from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional

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
@dataclass
class PatternClause(ASTNode):
    """Represents the PATTERN clause in MATCH_RECOGNIZE.
    
    This implementation tokenizes the pattern text in a manner similar to how a regex engine would.
    It supports alternate forms (using '|' as alternation), grouping (outer parentheses),
    and tokens with quantifiers (like A+, A*, A{2,4} or A{2,4}?).
    
    The metadata dictionary will include:
      - 'variables': a list of tokens as they appear (including quantifiers)
      - 'base_variables': a list of the base variable identifiers (without quantifiers)
    """
    pattern: str
    metadata: Dict = field(init=False)

    # Reserved keywords that should not be considered as pattern variable names.
    RESERVED_KEYWORDS = {"AND", "OR", "NOT"}

    def __post_init__(self):
        raw = self.pattern.strip()
        # If the pattern starts with PERMUTE( and ends with ), handle it separately.
        if raw.upper().startswith("PERMUTE(") and raw.endswith(")"):
            inner_text = raw[len("PERMUTE("):-1].strip()
            # Split on commas (ignore extra whitespace)
            tokens = re.split(r'\s*,\s*', inner_text)
            variables, base_variables = self._tokenize_tokens(tokens)
        else:
            # For alternate forms, replace the alternation operator '|' with whitespace.
            raw = raw.replace("|", " ")
            # Remove outer parentheses if they wrap the entire string and are balanced.
            if raw.startswith("(") and raw.endswith(")") and self._balanced_parentheses(raw[1:-1]):
                raw = raw[1:-1].strip()
            # Split by whitespace.
            tokens = raw.split()
            variables, base_variables = self._tokenize_tokens(tokens)
        self.metadata = {"variables": variables, "base_variables": base_variables}

    def _tokenize_tokens(self, tokens: List[str]) -> (List[str], List[str]):
        """
        For each token from the pattern, remove any trailing punctuation (such as commas)
        and use a regex to capture an identifier and an optional quantifier.
        Returns a tuple (variables, base_variables).
        """
        variables = []
        base_variables = []
        # Regex that matches an identifier followed by an optional quantifier.
        # The quantifier can be one of: *, +, ?, or a bounded quantifier like {2,4} or {2,4}? (with optional spaces)
        token_regex = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)(\s*\{\s*\d+(?:\s*,\s*\d*)?\s*\}\??|[\*\+\?])?$')
        for token in tokens:
            token = token.strip(",()")
            # Skip reserved keywords.
            if token.upper() in self.RESERVED_KEYWORDS:
                continue
            m = token_regex.fullmatch(token)
            if m:
                ident = m.group(1)
                quant = m.group(2)
                quant_str = quant.strip() if quant else ""
                variables.append(ident + quant_str)
                base_variables.append(ident)
            else:
                # If the token does not match the expected pattern,
                # include it as-is (this might trigger validation errors later).
                variables.append(token)
                base_variables.append(token)
        return variables, base_variables

    def _balanced_parentheses(self, s: str) -> bool:
        """Check that the string s has balanced parentheses."""
        count = 0
        for char in s:
            if char == '(':
                count += 1
            elif char == ')':
                count -= 1
                if count < 0:
                    return False
        return count == 0

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
