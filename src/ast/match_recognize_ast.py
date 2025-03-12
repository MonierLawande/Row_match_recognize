# src/ast/match_recognize_ast.py

from dataclasses import dataclass, field
from enum import Enum

class RowsPerMatchType(Enum):
    ONE_ROW_PER_MATCH = "ONE ROW PER MATCH"
    ALL_ROWS_PER_MATCH = "ALL ROWS PER MATCH"
    ALL_ROWS_PER_MATCH_SHOW_EMPTY = "ALL ROWS PER MATCH SHOW EMPTY MATCHES"
    ALL_ROWS_PER_MATCH_OMIT_EMPTY = "ALL ROWS PER MATCH OMIT EMPTY MATCHES"
    ALL_ROWS_PER_MATCH_WITH_UNMATCHED = "ALL ROWS PER MATCH WITH UNMATCHED ROWS"

class AfterMatchSkipType(Enum):
    SKIP_PAST_LAST_ROW = "SKIP PAST LAST ROW"
    SKIP_TO_NEXT_ROW = "SKIP TO NEXT ROW"
    SKIP_TO_FIRST = "SKIP TO FIRST"
    SKIP_TO_LAST = "SKIP TO LAST"

@dataclass
class MatchRecognizeAST:
    partition_by: list = field(default_factory=list)
    order_by: list = field(default_factory=list)
    measures: list = field(default_factory=list)    # List of dicts e.g., {"expression": <expr_ast>, "alias": str}
    rows_per_match: str = "ONE ROW PER MATCH"       # Raw string representation
    after_match_skip: str = "SKIP PAST LAST ROW"    # Raw string representation
    pattern: dict = field(default_factory=dict)     # {"raw": str, "ast": <PatternAST>}
    subset: dict = field(default_factory=dict)
    define: list = field(default_factory=list)      # List of dicts e.g., {"variable": str, "condition": <expr_ast>}
    is_empty_match: bool = False                    # Flag indicating an empty match
    
    # Enhanced properties for semantic analysis
    rows_per_match_type: RowsPerMatchType = None    # Parsed enum value
    after_match_skip_type: AfterMatchSkipType = None  # Parsed enum value
    skip_to_variable: str = None                    # Variable name for SKIP TO FIRST/LAST
    has_unmatched_rows: bool = False                # Whether unmatched rows are included in output
    has_exclusion: bool = False                     # Whether pattern contains exclusion syntax
    
    def __post_init__(self):
        """Parse the rows_per_match and after_match_skip strings into structured representations"""
        self._parse_rows_per_match()
        self._parse_after_match_skip()
        self._check_pattern_exclusion()
    
    def _parse_rows_per_match(self):
        """Parse the rows_per_match string into a structured representation"""
        if not self.rows_per_match:
            self.rows_per_match_type = RowsPerMatchType.ONE_ROW_PER_MATCH
            return
            
        rpm = self.rows_per_match.upper()
        
        if "ONE ROW PER MATCH" in rpm:
            self.rows_per_match_type = RowsPerMatchType.ONE_ROW_PER_MATCH
        elif "WITH UNMATCHED ROWS" in rpm:
            self.rows_per_match_type = RowsPerMatchType.ALL_ROWS_PER_MATCH_WITH_UNMATCHED
            self.has_unmatched_rows = True
        elif "OMIT EMPTY MATCHES" in rpm:
            self.rows_per_match_type = RowsPerMatchType.ALL_ROWS_PER_MATCH_OMIT_EMPTY
        elif "SHOW EMPTY MATCHES" in rpm:
            self.rows_per_match_type = RowsPerMatchType.ALL_ROWS_PER_MATCH_SHOW_EMPTY
        elif "ALL ROWS PER MATCH" in rpm:
            self.rows_per_match_type = RowsPerMatchType.ALL_ROWS_PER_MATCH
    
    def _parse_after_match_skip(self):
        """Parse the after_match_skip string into a structured representation"""
        if not self.after_match_skip:
            self.after_match_skip_type = AfterMatchSkipType.SKIP_PAST_LAST_ROW
            return
            
        skip = self.after_match_skip.upper()
        
        if "SKIP PAST LAST ROW" in skip:
            self.after_match_skip_type = AfterMatchSkipType.SKIP_PAST_LAST_ROW
        elif "SKIP TO NEXT ROW" in skip:
            self.after_match_skip_type = AfterMatchSkipType.SKIP_TO_NEXT_ROW
        elif "SKIP TO FIRST" in skip:
            self.after_match_skip_type = AfterMatchSkipType.SKIP_TO_FIRST
            # Extract variable name
            import re
            match = re.search(r"SKIP TO FIRST (\w+)", skip)
            if match:
                self.skip_to_variable = match.group(1)
        elif "SKIP TO LAST" in skip:
            self.after_match_skip_type = AfterMatchSkipType.SKIP_TO_LAST
            # Extract variable name
            import re
            match = re.search(r"SKIP TO LAST (\w+)", skip)
            if match:
                self.skip_to_variable = match.group(1)
    
    def _check_pattern_exclusion(self):
        """Check if the pattern contains exclusion syntax"""
        if self.pattern and "ast" in self.pattern:
            self.has_exclusion = self._has_exclusion_node(self.pattern["ast"])
    
    def _has_exclusion_node(self, ast):
        """Check if an AST contains an exclusion node"""
        if ast.type == "exclusion":
            return True
        
        for child in ast.children:
            if self._has_exclusion_node(child):
                return True
        
        return False
