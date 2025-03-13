# src/ast/expression_ast.py

from dataclasses import dataclass, field
from typing import List, Optional, Any

@dataclass
class ExpressionAST:
    type: str
    value: Optional[str] = None
    operator: Optional[str] = None
    children: List['ExpressionAST'] = field(default_factory=list)
    pattern_variable: Optional[str] = None
    column: Optional[str] = None
    navigation_type: Optional[str] = None
    offset: int = 0
    count_star: bool = False
    semantics: Optional[str] = None
    line: int = 0
    column_pos: int = 0  # Changed from column to column_pos
    
    def __str__(self) -> str:
        """String representation for debugging"""
        if self.type == "literal":
            return f"{self.value}"
        elif self.type == "identifier":
            return f"{self.value}"
        elif self.type == "binary":
            left = str(self.children[0]) if self.children else ""
            right = str(self.children[1]) if len(self.children) > 1 else ""
            return f"({left} {self.operator} {right})"
        elif self.type == "pattern_variable_reference":
            return f"{self.pattern_variable}.{self.column}"
        elif self.type == "function":
            args = ", ".join(str(child) for child in self.children)
            return f"{self.value}({args})"
        elif self.type == "aggregate":
            args = ", ".join(str(child) for child in self.children)
            prefix = f"{self.semantics} " if self.semantics else ""
            if self.count_star:
                if self.pattern_variable:
                    return f"{prefix}{self.value}({self.pattern_variable}.*)"
                else:
                    return f"{prefix}{self.value}(*)"
            return f"{prefix}{self.value}({args})"
        elif self.type == "navigation":
            target = str(self.children[0]) if self.children else ""
            prefix = f"{self.semantics} " if self.semantics else ""
            if self.offset > 0:
                return f"{prefix}{self.navigation_type}({target}, {self.offset})"
            return f"{prefix}{self.navigation_type}({target})"
        elif self.type == "classifier":
            prefix = f"{self.semantics} " if self.semantics else ""
            if self.pattern_variable:
                return f"{prefix}CLASSIFIER({self.pattern_variable})"
            return f"{prefix}CLASSIFIER()"
        elif self.type == "match_number":
            prefix = f"{self.semantics} " if self.semantics else ""
            return f"{prefix}MATCH_NUMBER()"
        else:
            return f"{self.type}({self.value})"
