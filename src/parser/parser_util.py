from dataclasses import dataclass, field
from typing import Dict, Set, List, Tuple

from typing import List, Tuple

class ParseError(Exception):
    """Custom exception for parsing errors"""
    def __init__(self, message: str, line: int = 0, column: int = 0):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Parse error at {line}:{column}: {message}")

class ErrorHandler:
    """
    Centralized error handling for parsing and validation.
    
    This class collects errors and warnings during parsing and validation,
    allowing for better error reporting and recovery.
    """
    def __init__(self):
        self.errors = []
        self.warnings = []
        
    def add_error(self, message: str, line: int = 0, column: int = 0) -> None:
        """Add an error with position information"""
        self.errors.append((message, line, column))
        
    def add_warning(self, message: str, line: int = 0, column: int = 0) -> None:
        """Add a warning with position information"""
        self.warnings.append((message, line, column))
        
    def has_errors(self) -> bool:
        """Check if there are any errors"""
        return len(self.errors) > 0
        
    def has_warnings(self) -> bool:
        """Check if there are any warnings"""
        return len(self.warnings) > 0
        
    def get_errors(self) -> List[Tuple[str, int, int]]:
        """Get all errors"""
        return self.errors
        
    def get_warnings(self) -> List[Tuple[str, int, int]]:
        """Get all warnings"""
        return self.warnings
        
    def get_formatted_errors(self) -> List[str]:
        """Get formatted error messages"""
        return [f"Error at line {line}, column {col}: {msg}" for msg, line, col in self.errors]
        
    def get_formatted_warnings(self) -> List[str]:
        """Get formatted warning messages"""
        return [f"Warning at line {line}, column {col}: {msg}" for msg, line, col in self.warnings]
        
    def clear(self) -> None:
        """Clear all errors and warnings"""
        self.errors = []
        self.warnings = []
        
    # ANTLR error listener interface methods
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        """Handle syntax errors from ANTLR"""
        self.add_error(f"Parsing error: {msg}", line, column)
        
    def reportAmbiguity(self, recognizer, dfa, startIndex, stopIndex, exact, ambigAlts, configs):
        """Handle ambiguity reports from ANTLR"""
        self.add_warning(f"Grammar ambiguity detected at {startIndex}:{stopIndex}", 0, startIndex)
        
    def reportAttemptingFullContext(self, recognizer, dfa, startIndex, stopIndex, conflictingAlts, configs):
        """Handle full context attempts from ANTLR"""
        # We don't need to report this, but the method must exist
        pass
        
    def reportContextSensitivity(self, recognizer, dfa, startIndex, stopIndex, prediction, configs):
        """Handle context sensitivity reports from ANTLR"""
        # We don't need to report this, but the method must exist
        pass

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
        """Enter a new nesting level; report an error if maximum nesting is exceeded."""
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
        self.pattern_variables.add(variable)
        
    def add_subset_definition(self, name: str, variables: Set[str]):
        self.subset_variables[name] = variables
