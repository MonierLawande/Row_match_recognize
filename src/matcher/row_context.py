# src/matcher/row_context.py

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Tuple, Union

@dataclass
class RowContext:
    """
    Maintains context for row pattern matching and navigation functions.
    
    Attributes:
        rows: The input rows
        variables: Mapping from variables to row indices
        subsets: Mapping from subset variable to component variables
        current_idx: Current row index being processed
        match_number: Sequential match number
    """
    rows: List[Dict[str, Any]] = field(default_factory=list)
    variables: Dict[str, List[int]] = field(default_factory=dict)  # Variable -> row indices
    subsets: Dict[str, List[str]] = field(default_factory=dict)    # Subset -> component vars
    current_idx: int = 0
    match_number: int = 1
    
    def classifier(self, variable: Optional[str] = None) -> str:
        """
        Return pattern variable for current row or specified set.
        
        Args:
            variable: Optional variable name to check against
            
        Returns:
            String containing the pattern variable name or empty string if not matched
            
        Examples:
            >>> context.classifier()  # Returns variable for current row
            'A'
            >>> context.classifier('A')  # Check if row matches 'A'
            'A'  # or '' if not matched
        """
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

    def var_rows(self, variable: str) -> List[Dict[str, Any]]:
        """
        Get all rows matched to a variable or subset.
        
        Args:
            variable: Variable name
            
        Returns:
            List of rows matched to the variable
        """
        indices = self.var_row_indices(variable)
        return [self.rows[idx] for idx in indices if 0 <= idx < len(self.rows)]

    def var_row_indices(self, variable: str) -> List[int]:
        """
        Get indices of rows matched to a variable or subset.
        
        Args:
            variable: Variable name
            
        Returns:
            List of row indices matched to the variable
        """
        indices = []
        
        # Check direct variable
        if variable in self.variables:
            indices = self.variables[variable]
        
        # Check subset variable
        elif variable in self.subsets:
            for comp in self.subsets[variable]:
                if comp in self.variables:
                    indices.extend(self.variables[comp])
        
        return sorted(indices)
    
    def prev(self, steps: int = 1) -> Optional[Dict[str, Any]]:
        """
        Get previous row within partition with robust boundary handling.
        
        Args:
            steps: Number of rows to look backwards
            
        Returns:
            Previous row or None if out of bounds
        """
        if self.current_idx - steps >= 0 and self.current_idx - steps < len(self.rows):
            return self.rows[self.current_idx - steps]
        return None

    def next(self, steps: int = 1) -> Optional[Dict[str, Any]]:
        """
        Get next row within partition with robust boundary handling.
        
        Args:
            steps: Number of rows to look forwards
            
        Returns:
            Next row or None if out of bounds
        """
        if self.current_idx + steps >= 0 and self.current_idx + steps < len(self.rows):
            return self.rows[self.current_idx + steps]
        return None
        
    def first(self, variable: str, occurrence: int = 0) -> Optional[Dict[str, Any]]:
        """
        Get first occurrence of a pattern variable with robust handling.
        
        Args:
            variable: Variable name
            occurrence: Which occurrence to retrieve (0-based index)
            
        Returns:
            Row of the specified occurrence or None
        """
        indices = self.var_row_indices(variable)
        if indices and occurrence >= 0 and occurrence < len(indices):
            return self.rows[indices[occurrence]]
        return None
        
    def last(self, variable: str, occurrence: int = 0) -> Optional[Dict[str, Any]]:
        """
        Get last occurrence of a pattern variable with robust handling.
        
        Args:
            variable: Variable name
            occurrence: Which occurrence from the end to retrieve (0-based index)
            
        Returns:
            Row of the specified occurrence or None
        """
        indices = self.var_row_indices(variable)
        if indices and occurrence >= 0 and occurrence < len(indices):
            return self.rows[indices[-(occurrence+1)]]
        return None
