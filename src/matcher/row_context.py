# src/matcher/row_context.py

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

# src/matcher/row_context.py

@dataclass
class RowContext:
    """Maintains context for row pattern matching and navigation functions."""
    rows: List[Dict[str, Any]] = field(default_factory=list)
    variables: Dict[str, List[int]] = field(default_factory=dict)  # Variable -> row indices
    subsets: Dict[str, List[str]] = field(default_factory=dict)    # Subset -> component vars
    current_idx: int = 0
    match_number: int = 1
    
    def var_rows(self, variable: str) -> List[Dict[str, Any]]:
        """Get all rows matched to a variable or subset."""
        print(f"Getting rows for variable: {variable}")
        
        # Get indices for the variable
        indices = self.var_row_indices(variable)
        print(f"Found indices: {indices}")
        
        # Return rows at those indices
        return [self.rows[idx] for idx in indices if 0 <= idx < len(self.rows)]

    def var_row_indices(self, variable: str) -> List[int]:
        """Get indices of rows matched to a variable or subset with better error handling."""
        indices = []
        
        # Check if this is a direct variable
        if variable in self.variables:
            indices = self.variables[variable]
        
        # Check if this is a subset variable
        elif variable in self.subsets:
            for comp in self.subsets[variable]:
                if comp in self.variables:
                    indices.extend(self.variables.get(comp, []))
        
        # Return sorted indices (ensures correct navigation order)
        return sorted(indices)
    
    def classifier(self, variable: Optional[str] = None) -> str:
        """Return pattern variable for current row or specified set."""
        if variable:
            # Check if current row is in the specified variable's rows
            indices = self.var_row_indices(variable)
            
            if self.current_idx in indices:
                # For subsets, need to determine which component variable matched
                if variable in self.subsets:
                    for comp in self.subsets[variable]:
                        if comp in self.variables and self.current_idx in self.variables[comp]:
                            return comp
                return variable
            return ""
        
        # No variable specified - return the matching variable for current row
        for var, indices in self.variables.items():
            if self.current_idx in indices:
                return var
        return ""

    
    def add_row(self, row: Dict[str, Any], variable: Optional[str] = None) -> None:
        """Add a row to the context, optionally assigning to a pattern variable."""
        self.rows.append(row)
        if variable:
            if variable not in self.variables:
                self.variables[variable] = []
            self.variables[variable].append(len(self.rows) - 1)
    
    

    def prev(self, steps: int = 1) -> Optional[Dict[str, Any]]:
        """Get previous row within partition with robust boundary handling."""
        if self.current_idx - steps >= 0 and self.current_idx - steps < len(self.rows):
            return self.rows[self.current_idx - steps]
        return None

    def next(self, steps: int = 1) -> Optional[Dict[str, Any]]:
        """Get next row within partition with robust boundary handling."""
        if self.current_idx + steps >= 0 and self.current_idx + steps < len(self.rows):
            return self.rows[self.current_idx + steps]
        return None
        
    def first(self, variable: str, occurrence: int = 0) -> Optional[Dict[str, Any]]:
        """Get first occurrence of a pattern variable with robust handling."""
        indices = self.var_row_indices(variable)
        if indices and occurrence >= 0 and occurrence < len(indices):
            return self.rows[indices[occurrence]]
        return None
        
    def last(self, variable: str, occurrence: int = 0) -> Optional[Dict[str, Any]]:
        """Get last occurrence of a pattern variable with robust handling."""
        indices = self.var_row_indices(variable)
        if indices and occurrence >= 0 and occurrence < len(indices):
            return self.rows[indices[-(occurrence+1)]]
        return None
        
    


    