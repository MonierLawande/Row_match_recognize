# src/matcher/row_context.py

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

@dataclass
class RowContext:
    """Maintains context for row pattern matching and navigation functions."""
    rows: List[Dict[str, Any]] = field(default_factory=list)
    variables: Dict[str, List[int]] = field(default_factory=dict)  # Variable -> row indices
    subsets: Dict[str, List[str]] = field(default_factory=dict)    # Subset -> component vars
    current_idx: int = 0
    match_number: int = 1
    
    def add_row(self, row: Dict[str, Any], variable: Optional[str] = None) -> None:
        """Add a row to the context, optionally assigning to a pattern variable."""
        self.rows.append(row)
        if variable:
            if variable not in self.variables:
                self.variables[variable] = []
            self.variables[variable].append(len(self.rows) - 1)
    
    def var_rows(self, variable: str) -> List[Dict[str, Any]]:
        """Get all rows matched to a variable."""
        print(f"Getting rows for variable: {variable}")
        print(f"Available variables: {self.variables}")
        print(f"Total rows: {len(self.rows)}")
        
        if variable in self.variables:
            indices = sorted(self.variables[variable])
            print(f"Found indices: {indices}")
            return [self.rows[idx] for idx in indices]
        return []
    
    def var_row_indices(self, variable: str) -> List[int]:
        """Get indices of rows matched to a variable or subset."""
        indices = []
        if variable in self.variables:
            indices = self.variables[variable]
        elif variable in self.subsets:
            for comp in self.subsets[variable]:
                if comp in self.variables:
                    indices.extend(self.variables.get(comp, []))
        return sorted(indices)
    
    def prev(self, steps: int = 1) -> Optional[Dict[str, Any]]:
        """Get previous row within partition."""
        if self.current_idx - steps >= 0:
            return self.rows[self.current_idx - steps]
        return None
    
    def next(self, steps: int = 1) -> Optional[Dict[str, Any]]:
        """Get next row within partition."""
        if self.current_idx + steps < len(self.rows):
            return self.rows[self.current_idx + steps]
        return None
        
    def first(self, variable: str, occurrence: int = 0) -> Optional[Dict[str, Any]]:
        """Get first occurrence of a pattern variable."""
        indices = self.var_row_indices(variable)
        if occurrence < len(indices):
            return self.rows[indices[occurrence]]
        return None
        
    def last(self, variable: str, occurrence: int = 0) -> Optional[Dict[str, Any]]:
        """Get last occurrence of a pattern variable."""
        indices = self.var_row_indices(variable)
        if occurrence < len(indices):
            return self.rows[indices[-(occurrence+1)]]
        return None

    def classifier(self, variable: Optional[str] = None) -> str:
        """Return pattern variable for current row or specified set."""
        if variable:
            # Check if current row is in the specified variable's rows
            indices = []
            if variable in self.variables:
                indices = self.variables[variable]
            elif variable in self.subsets:
                for comp in self.subsets[variable]:
                    indices.extend(self.variables.get(comp, []))
            
            if self.current_idx in indices:
                # For subsets, need to determine which component variable matched
                if variable in self.subsets:
                    for comp in self.subsets[variable]:
                        if self.current_idx in self.variables.get(comp, []):
                            return comp
                return variable
            return ""
        
        # No variable specified - return the matching variable for current row
        for var, indices in self.variables.items():
            if self.current_idx in indices:
                return var
        return ""
