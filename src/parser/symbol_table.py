# src/parser/symbol_table.py

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, List, Tuple
from enum import Enum

class SymbolType(Enum):
    PATTERN_VARIABLE = "pattern_variable"
    SUBSET_VARIABLE = "subset_variable"
    MEASURE = "measure"
    COLUMN = "column"

@dataclass
class Symbol:
    name: str
    type: SymbolType
    defined_at: tuple  # (line, column)
    references: list = field(default_factory=list)
    properties: dict = field(default_factory=dict)

class SymbolTable:
    """Enhanced symbol management for pattern matching"""
    
    def __init__(self):
        self.symbols: Dict[str, Symbol] = {}
        self.scopes: List[Set[str]] = [set()]
        
    def enter_scope(self):
        """Enter a new scope"""
        self.scopes.append(set())
        
    def exit_scope(self):
        """Exit current scope"""
        if self.scopes:
            scope = self.scopes.pop()
            # Clean up symbols from this scope
            for name in scope:
                if name in self.symbols:
                    del self.symbols[name]
                    
    def add_symbol(self, name: str, type: SymbolType, line: int, column: int, properties: dict = None):
        """Add a symbol to current scope"""
        if self.scopes:
            self.scopes[-1].add(name)
        self.symbols[name] = Symbol(
            name=name,
            type=type,
            defined_at=(line, column),
            properties=properties or {}
        )
        
    def add_reference(self, name: str, line: int, column: int):
        """Add a reference to a symbol"""
        if name in self.symbols:
            self.symbols[name].references.append((line, column))
            
    def get_symbol(self, name: str) -> Optional[Symbol]:
        """Get symbol information"""
        return self.symbols.get(name)
        
    def get_undefined_references(self) -> List[Tuple[str, int, int]]:
        """Get all references to undefined symbols"""
        undefined = []
        for symbol in self.symbols.values():
            for ref in symbol.references:
                if symbol.defined_at is None:
                    undefined.append((symbol.name, ref[0], ref[1]))
        return undefined
