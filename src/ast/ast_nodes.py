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
    """Represents an individual sorting item in ORDER BY clause."""
    column: str
    ordering: str = "ASC"
    nulls_ordering: Optional[str] = None

    def __post_init__(self):
        # Preserve the ordering as provided (but you might still want to standardize if needed).
        self.ordering = self.ordering  # case-sensitive; do not force upper case.
        if self.nulls_ordering:
            self.nulls_ordering = self.nulls_ordering

@dataclass
class OrderByClause(ASTNode):
    sort_items: List[SortItem]

@dataclass
class Measure(ASTNode):
    expression: str
    alias: Optional[str] = None
    metadata: Optional[Dict] = field(default_factory=dict)
    is_classifier: bool = field(init=False)
    is_match_number: bool = field(init=False)

    def __post_init__(self):
        self.is_classifier = re.match(r'CLASSIFIER\(\s*([A-Za-z_][A-Za-z0-9_]*)?\s*\)', self.expression) is not None
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
        self.mode = self.raw_mode.replace(" ", "")

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

@dataclass
class PatternClause(ASTNode):
    """Represents the PATTERN clause in MATCH_RECOGNIZE.

    This implementation extracts two lists:
      - "variables": the tokens as they appear (e.g. ["A", "b+", "c"])
      - "base_variables": the base identifiers with any trailing quantifiers removed (e.g. ["A", "b", "c"])
    The comparison in validation is case‑sensitive.
    """
    pattern: str
    metadata: Dict = field(init=False)

    # Reserved keywords that should not be treated as pattern variables.
    RESERVED_KEYWORDS = {"PERMUTE", "AND", "OR", "NOT"}

    def __post_init__(self):
        # Split the raw pattern by whitespace.
        tokens = self.pattern.split()
        variables: List[str] = []
        base_variables: List[str] = []
        for token in tokens:
            token = token.strip()
            if token in self.RESERVED_KEYWORDS:
                continue
            # Use a regex to capture an identifier optionally followed by a quantifier.
            # For example, "b+" will capture "b" as the base.
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)([\*\+\?\{].*)?$', token)
            if m:
                ident = m.group(1)              # the base identifier (case preserved)
                quantifier = m.group(2) if m.group(2) else ""
                full_token = ident + quantifier  # preserve original token (e.g., "b+")
                variables.append(full_token)
                base_variables.append(ident)
            else:
                # If token doesn't match the expected pattern, include it as-is.
                variables.append(token)
                base_variables.append(token)
        self.metadata = {"variables": variables, "base_variables": base_variables}

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
    metadata: Optional[Dict] = field(default_factory=dict)

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
    metadata: Optional[Dict] = field(default_factory=dict)

    def __repr__(self):
        return (f"FullQueryAST(\n"
                f"  select_clause={self.select_clause},\n"
                f"  from_clause={self.from_clause},\n"
                f"  match_recognize={self.match_recognize},\n"
                f"  metadata={self.metadata}\n)")
