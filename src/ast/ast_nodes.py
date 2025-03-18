from typing import List, Optional, Dict
import re

# Base AST node
class ASTNode:
    """Base class for all AST nodes."""
    pass

# --- MATCH_RECOGNIZE Clause AST Nodes ---
class PartitionByClause(ASTNode):
    def __init__(self, columns: List[str]):
        self.columns = columns

    def __repr__(self):
        return f"PartitionByClause(columns={self.columns})"


class SortItem(ASTNode):
    """Represents an individual sorting item in ORDER BY clause."""
    def __init__(self, column: str, ordering: str = "ASC", nulls_ordering: Optional[str] = None):
        self.column = column
        self.ordering = ordering.upper()  # "ASC" or "DESC"
        self.nulls_ordering = nulls_ordering.upper() if nulls_ordering else None  # "NULLS FIRST" or "NULLS LAST"

    def __repr__(self):
        return f"SortItem(column={self.column}, ordering={self.ordering}, nulls_ordering={self.nulls_ordering})"

class OrderByClause(ASTNode):
    def __init__(self, sort_items: List[SortItem]):
        self.sort_items = sort_items

    def __repr__(self):
        return f"OrderByClause(sort_items={self.sort_items})"


class Measure(ASTNode):
    def __init__(self, expression: str, alias: Optional[str] = None, metadata: Optional[Dict] = None):
        self.expression = expression
        self.alias = alias
        self.metadata = metadata or {}

    def __repr__(self):
        if self.alias:
            return f"Measure(expression={self.expression}, alias={self.alias}, metadata={self.metadata})"
        return f"Measure(expression={self.expression}, metadata={self.metadata})"

class MeasuresClause(ASTNode):
    def __init__(self, measures: List[Measure]):
        self.measures = measures

    def __repr__(self):
        return f"MeasuresClause(measures={self.measures})"
# Update the RowsPerMatchClause class in src/ast/ast_nodes.py

class RowsPerMatchClause(ASTNode):
    def __init__(self, mode: str, show_empty: Optional[bool] = None, with_unmatched: Optional[bool] = None):
        self.mode = mode  # Store original mode string
        self.show_empty = show_empty
        self.with_unmatched = with_unmatched

    def __repr__(self):
        # Normalize the mode by removing spaces for comparison
        normalized_mode = self.mode.replace(" ", "").upper()
        
        if normalized_mode == "ONEROWPERMATCH":
            return "RowsPerMatchClause(mode=ONE ROW PER MATCH)"
        elif normalized_mode.startswith("ALLROWSPERMATCH"):
            base = "ALL ROWS PER MATCH"
            modifiers = []
            
            # Use boolean flags as the source of truth for modifiers when available
            if self.show_empty is False or "OMITEMPTYMATCHES" in normalized_mode:
                modifiers.append("OMIT EMPTY MATCHES")
            elif self.show_empty is True or "SHOWEMPTYMATCHES" in normalized_mode:
                modifiers.append("SHOW EMPTY MATCHES")
                
            if self.with_unmatched or "WITHUNMATCHEDROWS" in normalized_mode:
                modifiers.append("WITH UNMATCHED ROWS")
                
            if modifiers:
                return f"RowsPerMatchClause(mode={base}, {', '.join(modifiers)})"
            else:
                return f"RowsPerMatchClause(mode={base})"
                
        # For any other mode, add spaces between CamelCase or UPPERCASE words
        pretty_mode = re.sub(r'([a-z])([A-Z])', r'\1 \2', self.mode)
        pretty_mode = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', pretty_mode)
        return f"RowsPerMatchClause(mode={pretty_mode})"


class AfterMatchSkipClause(ASTNode):
    def __init__(self, value: str):
        self.value = value

    def __repr__(self):
        return f"AfterMatchSkipClause(value={self.value})"


import re

class PatternClause(ASTNode):
    """Represents the PATTERN clause in MATCH_RECOGNIZE"""

    # Reserved keywords that should not be extracted as variables
    RESERVED_KEYWORDS = {"PERMUTE", "AND", "OR", "NOT"}

    def __init__(self, pattern: str):
        self.pattern = pattern

        # Step 1: Remove function-like calls for reserved keywords.
        # For example, "PERMUTE(A, B, C)" becomes "A, B, C"
        pattern_no_func = re.sub(
            r'\b(?:' + '|'.join(self.RESERVED_KEYWORDS) + r')\s*\((.*?)\)',
            r'\1',
            pattern
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

    def __repr__(self):
        return f"PatternClause(pattern={self.pattern}, metadata={self.metadata})"


class SubsetClause(ASTNode):
    def __init__(self, subset_text: str):
        self.subset_text = subset_text

    def __repr__(self):
        return f"SubsetClause(subset_text={self.subset_text})"

class Define(ASTNode):
    def __init__(self, variable: str, condition: str):
        self.variable = variable
        self.condition = condition

    def __repr__(self):
        return f"Define(variable={self.variable}, condition={self.condition})"

class DefineClause(ASTNode):
    def __init__(self, definitions: List[Define]):
        self.definitions = definitions

    def __repr__(self):
        return f"DefineClause(definitions={self.definitions})"

class MatchRecognizeClause(ASTNode):
    def __init__(self,
                 partition_by: Optional[PartitionByClause] = None,
                 order_by: Optional[OrderByClause] = None,
                 measures: Optional[MeasuresClause] = None,
                 rows_per_match: Optional[RowsPerMatchClause] = None,
                 after_match_skip: Optional[AfterMatchSkipClause] = None,
                 pattern: Optional[PatternClause] = None,
                 subset: Optional[List[SubsetClause]] = None,
                 define: Optional[DefineClause] = None):
        self.partition_by = partition_by
        self.order_by = order_by
        self.measures = measures
        self.rows_per_match = rows_per_match
        self.after_match_skip = after_match_skip
        self.pattern = pattern
        self.subset = subset or []
        self.define = define

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
class SelectItem(ASTNode):
    """Represents an individual item (column or expression with an optional alias) in the SELECT clause."""
    def __init__(self, expression: str, alias: Optional[str] = None, metadata: Optional[Dict] = None):
        self.expression = expression
        self.alias = alias
        self.metadata = metadata or {}

    def __repr__(self):
        if self.alias:
            return f"SelectItem(expression={self.expression}, alias={self.alias}, metadata={self.metadata})"
        return f"SelectItem(expression={self.expression}, metadata={self.metadata})"

class SelectClause(ASTNode):
    """Represents the SELECT clause as a list of SelectItem nodes."""
    def __init__(self, items: List[SelectItem]):
        self.items = items

    def __repr__(self):
        return f"SelectClause(items={self.items})"

class FromClause(ASTNode):
    """Represents the FROM clause with the table name."""
    def __init__(self, table: str):
        self.table = table

    def __repr__(self):
        return f"FromClause(table={self.table})"

class FullQueryAST(ASTNode):
    """Aggregates the SELECT clause, FROM clause, and the MATCH_RECOGNIZE clause."""
    def __init__(self,
                 select_clause: Optional[SelectClause],
                 from_clause: Optional[FromClause],
                 match_recognize: Optional[MatchRecognizeClause],
                 metadata: Optional[Dict] = None):
        self.select_clause = select_clause
        self.from_clause = from_clause
        self.match_recognize = match_recognize
        self.metadata = metadata or {}

    def __repr__(self):
        return (f"FullQueryAST(\n"
                f"  select_clause={self.select_clause},\n"
                f"  from_clause={self.from_clause},\n"
                f"  match_recognize={self.match_recognize},\n"
                f"  metadata={self.metadata}\n)")
