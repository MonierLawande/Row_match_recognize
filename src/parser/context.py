# src/parser/context.py

from dataclasses import dataclass, field
from typing import Dict, Set, Optional
from .error_handler import ErrorHandler

@dataclass
class ParserContext:
    """Shared context for parsing operations"""
    
    error_handler: ErrorHandler
    in_measures_clause: bool = False
    in_define_clause: bool = False
    pattern_variables: Set[str] = field(default_factory=set)
    subset_variables: Dict[str, Set[str]] = field(default_factory=dict)
    nesting_level: int = 0
    max_nesting: int = 10
    
    def enter_scope(self):
        """Enter a new nesting level"""
        self.nesting_level += 1
        if self.nesting_level > self.max_nesting:
            self.error_handler.add_error(
                f"Maximum nesting level ({self.max_nesting}) exceeded",
                0, 0  # Line and column would come from actual token
            )
            
    def exit_scope(self):
        """Exit current nesting level"""
        self.nesting_level -= 1
        
    def add_pattern_variable(self, variable: str):
        """Register a pattern variable"""
        self.pattern_variables.add(variable)
        
    def add_subset_definition(self, name: str, variables: Set[str]):
        """Register a subset definition"""
        self.subset_variables[name] = variables
        
    def is_valid_pattern_variable(self, variable: str) -> bool:
        """Check if a pattern variable is valid"""
        return variable in self.pattern_variables
        
    def is_valid_subset_variable(self, variable: str) -> bool:
        """Check if a subset variable is valid"""
        return variable in self.subset_variables
