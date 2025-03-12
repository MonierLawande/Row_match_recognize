from dataclasses import dataclass, field

@dataclass
class MatchRecognizeAST:
    partition_by: list = field(default_factory=list)
    order_by: list = field(default_factory=list)
    measures: list = field(default_factory=list)    # List of dicts e.g., {"expression": <expr_ast>, "alias": str}
    rows_per_match: str = "ONE ROW PER MATCH"         # or "ALL ROWS PER MATCH", etc.
    after_match_skip: str = "SKIP PAST LAST ROW"
    pattern: dict = field(default_factory=dict)         # {"raw": str, "ast": <PatternAST>}
    subset: dict = field(default_factory=dict)
    define: list = field(default_factory=list)          # List of dicts e.g., {"variable": str, "condition": <expr_ast>}
    is_empty_match: bool = False                        # Flag indicating an empty match
