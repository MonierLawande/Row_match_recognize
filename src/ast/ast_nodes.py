from dataclasses import dataclass, field
from typing import List, Optional, Dict
import re

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
        self.ordering = self.ordering.upper()  # "ASC" or "DESC"
        if self.nulls_ordering:
            self.nulls_ordering = self.nulls_ordering.upper()  # "NULLS FIRST" or "NULLS LAST"

@dataclass
class OrderByClause(ASTNode):
    sort_items: List[SortItem]

@dataclass
class Measure(ASTNode):
    expression: str
    alias: Optional[str] = None
    metadata: Optional[Dict] = field(default_factory=dict)
    # These fields are computed post-initialization:
    is_classifier: bool = field(init=False)
    is_match_number: bool = field(init=False)

    def __post_init__(self):
        self.is_classifier = re.match(r'CLASSIFIER\(\s*([A-Z][A-Z0-9_]*)?\s*\)', self.expression, re.IGNORECASE) is not None
        self.is_match_number = re.match(r'MATCH_NUMBER\(\s*\)', self.expression, re.IGNORECASE) is not None

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
        self.mode = self.raw_mode.replace(" ", "").upper()  # For comparison

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
            # For any other mode, return the raw mode as provided
            return f"RowsPerMatchClause(mode={self.raw_mode})"

@dataclass
class AfterMatchSkipClause(ASTNode):
    value: str

@dataclass
class PatternClause(ASTNode):
    """Represents the PATTERN clause in MATCH_RECOGNIZE"""
    pattern: str
    metadata: Dict = field(init=False)

    # Reserved keywords that should not be extracted as variables
    RESERVED_KEYWORDS = {"PERMUTE", "AND", "OR", "NOT"}

    def __post_init__(self):
        # Step 1: Remove function-like calls for reserved keywords.
        # For example, "PERMUTE(A, B, C)" becomes "A, B, C"
        pattern_no_func = re.sub(
            r'\b(?:' + '|'.join(self.RESERVED_KEYWORDS) + r')\s*\((.*?)\)',
            r'\1',
            self.pattern
        )
        # Step 2: Remove punctuation and quantifier symbols.
        # This converts "A, B, C" (or with braces, etc.) into a space-separated string.
        cleaned_pattern = re.sub(r'[\{\}\,\+\*\?\(\)]', ' ', pattern_no_func)
        cleaned_pattern = re.sub(r'\s+', ' ', cleaned_pattern).strip()
        # Step 3: Extract valid pattern variables from the cleaned string.
        seen = set()
        variables = []
        for match in re.finditer(r'\b([A-Z][A-Z0-9_]*)\b', cleaned_pattern):
            var_name = match.group(1)
            if var_name not in seen:
                variables.append(var_name)
                seen.add(var_name)
        self.metadata = {"variables": variables}

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
    """Represents an individual item (column or expression with an optional alias) in the SELECT clause."""
    expression: str
    alias: Optional[str] = None
    metadata: Optional[Dict] = field(default_factory=dict)

    def __repr__(self):
        if self.alias:
            return f"SelectItem(expression={self.expression}, alias={self.alias}, metadata={self.metadata})"
        return f"SelectItem(expression={self.expression}, metadata={self.metadata})"

@dataclass
class SelectClause(ASTNode):
    """Represents the SELECT clause as a list of SelectItem nodes."""
    items: List[SelectItem]

@dataclass
class FromClause(ASTNode):
    """Represents the FROM clause with the table name."""
    table: str

@dataclass
class FullQueryAST(ASTNode):
    """Aggregates the SELECT clause, FROM clause, and the MATCH_RECOGNIZE clause."""
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
