from typing import List, Optional

# Base AST node
class ASTNode:
    pass

# --- MATCH_RECOGNIZE Clause AST Nodes ---
class PartitionByClause(ASTNode):
    def __init__(self, columns: List[str]):
        self.columns = columns

    def __repr__(self):
        return f"PartitionByClause(columns={self.columns})"

class OrderByClause(ASTNode):
    def __init__(self, columns: List[str]):
        self.columns = columns

    def __repr__(self):
        return f"OrderByClause(columns={self.columns})"

class Measure(ASTNode):
    def __init__(self, expression: str, alias: Optional[str] = None):
        self.expression = expression
        self.alias = alias

    def __repr__(self):
        return f"Measure(expression={self.expression}, alias={self.alias})"

class MeasuresClause(ASTNode):
    def __init__(self, measures: List[Measure]):
        self.measures = measures

    def __repr__(self):
        return f"MeasuresClause(measures={self.measures})"

class RowsPerMatchClause(ASTNode):
    def __init__(self, value: str):
        self.value = value

    def __repr__(self):
        return f"RowsPerMatchClause(value={self.value})"

class AfterMatchSkipClause(ASTNode):
    def __init__(self, value: str):
        self.value = value

    def __repr__(self):
        return f"AfterMatchSkipClause(value={self.value})"

class PatternClause(ASTNode):
    def __init__(self, pattern: str):
        self.pattern = pattern

    def __repr__(self):
        return f"PatternClause(pattern={self.pattern})"

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
# New node to represent a single item in the SELECT clause
class SelectItem(ASTNode):
    def __init__(self, expression: str, alias: Optional[str] = None):
        self.expression = expression
        self.alias = alias

    def __repr__(self):
        if self.alias:
            return f"SelectItem(expression={self.expression}, alias={self.alias})"
        return f"SelectItem(expression={self.expression})"

# Updated SelectClause holds a list of SelectItem objects.
class SelectClause(ASTNode):
    def __init__(self, items: List[SelectItem]):
        self.items = items

    def __repr__(self):
        return f"SelectClause(items={self.items})"

class FromClause(ASTNode):
    def __init__(self, table: str):
        self.table = table

    def __repr__(self):
        return f"FromClause(table={self.table})"

class FullQueryAST(ASTNode):
    def __init__(self,
                 select_clause: Optional[SelectClause],
                 from_clause: Optional[FromClause],
                 match_recognize: Optional[MatchRecognizeClause]):
        self.select_clause = select_clause
        self.from_clause = from_clause
        self.match_recognize = match_recognize

    def __repr__(self):
        return (f"FullQueryAST(\n"
                f"  select_clause={self.select_clause},\n"
                f"  from_clause={self.from_clause},\n"
                f"  match_recognize={self.match_recognize}\n)")
