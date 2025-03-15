# src/parser/parser_util.py

from dataclasses import dataclass, field
from typing import Dict, Set, List, Tuple

class ParseError(Exception):
    """Custom exception for parsing errors."""
    def __init__(self, message: str, line: int = 0, column: int = 0):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Parse error at {line}:{column}: {message}")

class ErrorHandler:
    """
    Centralized error handling for parsing and validation.
    """
    def __init__(self):
        self.errors: List[Tuple[str, int, int]] = []
        self.warnings: List[Tuple[str, int, int]] = []
        
    def add_error(self, message: str, line: int = 0, column: int = 0) -> None:
        self.errors.append((message, line, column))
        
    def add_warning(self, message: str, line: int = 0, column: int = 0) -> None:
        self.warnings.append((message, line, column))
        
    def has_errors(self) -> bool:
        return len(self.errors) > 0
        
    def get_formatted_errors(self) -> List[str]:
        return [f"Error at line {line}, column {col}: {msg}" for msg, line, col in self.errors]
        
    def get_formatted_warnings(self) -> List[str]:
        return [f"Warning at line {line}, column {col}: {msg}" for msg, line, col in self.warnings]
        
    def clear(self) -> None:
        self.errors = []
        self.warnings = []

@dataclass
class ParserContext:
    """
    Shared context for parsing operations.
    """
    error_handler: ErrorHandler
    in_measures_clause: bool = False
    in_define_clause: bool = False
    pattern_variables: Set[str] = field(default_factory=set)
    subset_variables: Dict[str, Set[str]] = field(default_factory=dict)
    nesting_level: int = 0
    max_nesting: int = 10
    
    def enter_scope(self):
        """Enter a new nesting level; add an error if maximum nesting is exceeded."""
        self.nesting_level += 1
        if self.nesting_level > self.max_nesting:
            self.error_handler.add_error(
                f"Maximum nesting level ({self.max_nesting}) exceeded",
                0, 0
            )
            
    def exit_scope(self):
        """Exit the current nesting level."""
        self.nesting_level -= 1
        
    def add_pattern_variable(self, variable: str):
        """Register a pattern variable."""
        self.pattern_variables.add(variable)
        
    def add_subset_definition(self, name: str, variables: Set[str]):
        """Register a subset definition."""
        self.subset_variables[name] = variables
