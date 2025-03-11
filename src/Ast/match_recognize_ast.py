from dataclasses import dataclass, field

@dataclass
class MatchRecognizeAST:
    partition_by: list = field(default_factory=list)
    order_by: list = field(default_factory=list)
    measures: list = field(default_factory=list)
    rows_per_match: str = None
    after_match_skip: str = None
    pattern: dict = field(default_factory=dict)  # Expecting {"raw": str, "ast": PatternAST}
    define: list = field(default_factory=list)
