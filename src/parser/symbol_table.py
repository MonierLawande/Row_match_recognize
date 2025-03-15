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
    defined_at: Tuple[int, int]
    references: List[Tuple[int, int]] = field(default_factory=list)
    properties: dict = field(default_factory=dict)

class SymbolTable:
    """Manages symbols for pattern matching."""
    def __init__(self):
        self.symbols: Dict[str, Symbol] = {}
        self.scopes: List[Set[str]] = [set()]
        
    def enter_scope(self):
        self.scopes.append(set())
        
    def exit_scope(self):
        if self.scopes:
            scope = self.scopes.pop()
            for name in scope:
                if name in self.symbols:
                    del self.symbols[name]
                    
    def add_symbol(self, name: str, type: SymbolType, line: int, column: int, properties: dict = None):
        if self.scopes:
            self.scopes[-1].add(name)
        self.symbols[name] = Symbol(name=name, type=type, defined_at=(line, column), properties=properties or {})
        
    def add_reference(self, name: str, line: int, column: int):
        if name in self.symbols:
            self.symbols[name].references.append((line, column))
            
    def get_symbol(self, name: str) -> Optional[Symbol]:
        return self.symbols.get(name)
        
    def get_undefined_references(self) -> List[Tuple[str, int, int]]:
        undefined = []
        for symbol in self.symbols.values():
            for ref in symbol.references:
                if symbol.defined_at is None:
                    undefined.append((symbol.name, ref[0], ref[1]))
        return undefined
