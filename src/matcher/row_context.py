# src/matcher/row_context.py

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Tuple, Union
from collections import defaultdict
import time

@dataclass
class RowContext:
    """
    Maintains context for row pattern matching and navigation functions.
    
    This class provides an efficient interface for accessing matching rows,
    variables, and handling pattern variables.
    
    Attributes:
        rows: The input rows
        variables: Mapping from variables to row indices
        subsets: Mapping from subset variable to component variables
        current_idx: Current row index being processed
        match_number: Sequential match number
    """
    rows: List[Dict[str, Any]] = field(default_factory=list)
    variables: Dict[str, List[int]] = field(default_factory=dict)
    subsets: Dict[str, List[str]] = field(default_factory=dict)
    current_idx: int = 0
    match_number: int = 1
    current_var: Optional[str] = None
    navigation_cache: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Build optimized lookup structures."""
        self._build_indices()
        
    def _build_indices(self):
        """Build indices for faster variable and row lookups."""
        # Row index -> variables mapping
        self._row_var_index = defaultdict(set)
        for var, indices in self.variables.items():
            for idx in indices:
                self._row_var_index[idx].add(var)
        
        # Build subset index for faster lookups
        self._subset_index = {}
        for subset_name, components in self.subsets.items():
            for comp in components:
                if comp not in self._subset_index:
                    self._subset_index[comp] = set()
                self._subset_index[comp].add(subset_name)
        
    # Updates for src/matcher/row_context.py

    def classifier(self, variable: Optional[str] = None) -> str:
        """
        Return pattern variable for current row or specified set.
        
        This function implements the CLASSIFIER functionality of SQL:2016 standard.
        
        Args:
            variable: Optional variable name to check against
            
        Returns:
            String containing the pattern variable name or empty string if not matched
            
        Examples:
            >>> # When current row is matched to variable 'A':
            >>> context.classifier()
            'A'
            >>> context.classifier('A')
            'A'
            >>> context.classifier('B')
            ''
            
            >>> # When using subset variables:
            >>> # (with subset U = (A, B))
            >>> context.classifier('U')
            'A'  # If current row is matched to A
        """
        start_time = time.time()
        
        try:
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
            # Use the optimized index if available
            if hasattr(self, '_row_var_index') and self.current_idx in self._row_var_index:
                vars_for_row = self._row_var_index[self.current_idx]
                if vars_for_row:
                    return next(iter(vars_for_row))  # Return first variable in set
                    
            # Fallback to standard lookup
            for var, indices in self.variables.items():
                if self.current_idx in indices:
                    return var
            return ""
        finally:
            classifier_time = time.time() - start_time
            if hasattr(self, 'timing'):
                self.timing['classifier'] = classifier_time

    def var_row_indices(self, variable: str) -> List[int]:
        """
        Get indices of rows matched to a variable or subset.
        
        Args:
            variable: Variable name
            
        Returns:
            List of row indices matched to the variable
            
        Example:
            >>> # Get indices of rows matched to 'A'
            >>> context.var_row_indices('A')
            [0, 3, 5]
        """
        indices = []
        
        # Handle base variables with quantifiers (e.g., B?, C*)
        base_var = variable
        if variable.endswith('?'):
            base_var = variable[:-1]
        elif variable.endswith('+') or variable.endswith('*'):
            base_var = variable[:-1]
        elif '{' in variable and variable.endswith('}'):
            base_var = variable[:variable.find('{')]
        
        # Check direct variable (using base name)
        if base_var in self.variables:
            indices = self.variables[base_var]
        
        # Check subset variable
        elif variable in self.subsets:
            for comp in self.subsets[variable]:
                comp_base = comp
                if comp.endswith('?'):
                    comp_base = comp[:-1]
                elif comp.endswith('+') or comp.endswith('*'):
                    comp_base = comp[:-1]
                elif '{' in comp and comp.endswith('}'):
                    comp_base = comp[:comp.find('{')]
                    
                if comp_base in self.variables:
                    indices.extend(self.variables[comp_base])
        
        return sorted(indices)
        
    def var_rows(self, variable: str) -> List[Dict[str, Any]]:
        """
        Get all rows matched to a variable or subset.
        
        Args:
            variable: Variable name
            
        Returns:
            List of rows matched to the variable
            
        Example:
            >>> # Get all rows matched to variable 'A'
            >>> a_rows = context.var_rows('A')
            >>> # Get rows matched to subset 'U'
            >>> u_rows = context.var_rows('U')
        """
        indices = self.var_row_indices(variable)
        return [self.rows[idx] for idx in indices if 0 <= idx < len(self.rows)]

    
    
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

    def get_variable_positions(self, var_name):
        """Get sorted list of row positions for a variable, handling subsets."""
        if var_name in self.variables:
            return sorted(self.variables[var_name])
        elif var_name in self.subsets:
            # For subset variables, collect all rows from component variables
            subset_indices = []
            for component_var in self.subsets[var_name]:
                if component_var in self.variables:
                    subset_indices.extend(self.variables[component_var])
            return sorted(subset_indices)
        return []
    
    def get_row_value(self, row_idx, field_name):
        """Safely retrieve a value from a row."""
        if 0 <= row_idx < len(self.rows) and field_name in self.rows[row_idx]:
            return self.rows[row_idx][field_name]
        return None
    
    def reset_cache(self):
        """Clear navigation function cache between matches."""
        self.navigation_cache.clear()
