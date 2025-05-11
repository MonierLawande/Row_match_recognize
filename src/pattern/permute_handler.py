class PermuteHandler:
    """Handles PERMUTE patterns with lexicographical ordering and optimizations"""
    
    def __init__(self):
        self.permute_cache = {}
        
    def expand_permutation(self, variables):
        """
        Expands a PERMUTE pattern into all possible permutations
        in lexicographical order based on original variable order
        
        Args:
            variables: List of pattern variables in the PERMUTE clause
        
        Returns:
            List of permutations in lexicographical order
        """
        # Use tuple as key for cache lookup
        cache_key = tuple(variables)
        if cache_key in self.permute_cache:
            return self.permute_cache[cache_key]
        
        # Generate all permutations
        result = self._generate_permutations(variables)
        
        # Sort permutations based on original variable positions
        # This ensures lexicographical ordering per Trino spec
        var_priority = {var: idx for idx, var in enumerate(variables)}
        
        def permutation_key(perm):
            # Create a key for sorting based on original variable positions
            return [var_priority[var] for var in perm]
        
        result.sort(key=permutation_key)
        
        # Cache result
        self.permute_cache[cache_key] = result
        return result
    
    def _generate_permutations(self, variables):
        """Generate all permutations of the variables"""
        if len(variables) <= 1:
            return [variables]
        
        result = []
        for i in range(len(variables)):
            # Get current variable
            current = variables[i]
            # Generate permutations of remaining variables
            remaining = variables[:i] + variables[i+1:]
            for p in self._generate_permutations(remaining):
                result.append([current] + p)
        
        return result
    
    def expand_nested_permute(self, pattern):
        """
        Handles nested PERMUTE patterns like PERMUTE(A, PERMUTE(B, C))
        
        Args:
            pattern: Pattern object with potentially nested PERMUTE
            
        Returns:
            Expanded pattern with all permutations properly resolved
        """
        # Implementation would depend on your pattern representation
        # This is a placeholder for the logic
        if not self._has_nested_permute(pattern):
            return self.expand_permutation(pattern['variables'])
            
        # Process nested permutations first, then outer permutation
        expanded_variables = []
        for component in pattern['components']:
            if component.get('permute', False):
                # Recursively expand nested permute
                expanded = self.expand_nested_permute(component)
                expanded_variables.append(expanded)
            else:
                expanded_variables.append([component['variable']])
        
        # Flatten the expanded variables
        flat_variables = [var for sublist in expanded_variables for var in sublist]
        return self.expand_permutation(flat_variables)
        
    def _has_nested_permute(self, pattern):
        """Check if pattern has nested PERMUTE"""
        if not pattern.get('permute', False):
            return False
            
        for component in pattern.get('components', []):
            if component.get('permute', False):
                return True
                
        return False 