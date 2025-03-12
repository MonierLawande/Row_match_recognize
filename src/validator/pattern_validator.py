# src/validator/pattern_validator.py

from typing import List, Dict, Any, Tuple, Set

class PatternValidator:
    """
    Specialized validator for pattern syntax with focus on:
    - Quantifiers (including reluctant quantifiers)
    - Exclusions
    - Subsets
    - Pattern structure and nesting
    """
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.pattern_variables = set()
        self.subset_variables = {}
        self.max_nesting_level = 0
        self.has_exclusion = False
        self.has_empty_match = False
    
    def validate_pattern(self, pattern_ast, subset_mapping=None) -> Tuple[List[str], List[str]]:
        """
        Validate a pattern AST with detailed error messages.
        
        Args:
            pattern_ast: The pattern AST to validate
            subset_mapping: Optional mapping of subset variables to their components
            
        Returns:
            Tuple of (errors, warnings)
        """
        self.errors = []
        self.warnings = []
        self.pattern_variables = set()
        self.subset_variables = subset_mapping or {}
        self.max_nesting_level = 0
        self.has_exclusion = False
        self.has_empty_match = False
        
        # Validate pattern structure
        self._validate_pattern_structure(pattern_ast)
        
        # Check for empty pattern
        if pattern_ast.type == "empty":
            self.has_empty_match = True
            self.warnings.append("Empty pattern '()' will match zero-length sequences")
        
        # Check for excessive nesting
        if self.max_nesting_level > 10:
            self.warnings.append(
                f"Pattern has deep nesting (level {self.max_nesting_level}), "
                "which may impact performance"
            )
        
        # Validate subsets if provided
        if subset_mapping:
            self._validate_subsets(subset_mapping)
        
        return self.errors, self.warnings
    
    def _validate_pattern_structure(self, ast, nesting_level=0):
        """Recursively validate pattern structure with detailed path information"""
        # Track maximum nesting level
        self.max_nesting_level = max(self.max_nesting_level, nesting_level)
        
        # Track pattern variables
        if ast.type == "literal":
            self.pattern_variables.add(ast.value)
        
        # Track exclusions
        if ast.type == "exclusion":
            self.has_exclusion = True
        
        # Validate quantifiers
        if ast.type == "quantifier":
            self._validate_quantifier(ast)
        
        # Validate permutation
        elif ast.type == "permutation":
            self._validate_permutation(ast)
        
        # Validate alternation
        elif ast.type == "alternation":
            self._validate_alternation(ast)
        
        # Validate exclusion
        elif ast.type == "exclusion":
            self._validate_exclusion(ast)
        
        # Recursively validate children
        for child in ast.children:
            self._validate_pattern_structure(child, nesting_level + 1)
    
    def _validate_quantifier(self, ast):
        """Validate a quantifier node"""
        if not ast.children:
            self.errors.append("Quantifier has no target")
            return
            
        # Get quantifier details for better error messages
        quant_str = ast.quantifier or ""
        reluctant = quant_str.endswith("?")
        
        # Validate quantifier values
        if ast.quantifier_min is not None:
            if ast.quantifier_min < 0:
                self.errors.append(f"Quantifier minimum cannot be negative: {ast.quantifier_min}")
            
            if ast.quantifier_min == 0:
                # Check for potentially problematic zero-minimum quantifiers
                if ast.children[0].type == "group" and self.has_complex_group(ast.children[0]):
                    self.warnings.append(
                        f"Quantifier {quant_str} with minimum=0 on complex group may lead to "
                        "unexpected matching behavior"
                    )
        
        if ast.quantifier_max is not None and ast.quantifier_min is not None:
            if ast.quantifier_max < ast.quantifier_min:
                self.errors.append(
                    f"Quantifier maximum cannot be less than minimum: "
                    f"{ast.quantifier_max} < {ast.quantifier_min}"
                )
            
            if ast.quantifier_min == ast.quantifier_max:
                # Fixed repetition with reluctant marker has no effect
                if reluctant:
                    self.warnings.append(
                        f"Reluctant marker '?' on fixed repetition quantifier {{{ast.quantifier_min}}} "
                        "has no effect"
                    )
        
        # Check for quantifier on empty pattern
        if ast.children[0].type == "empty":
            self.warnings.append(
                f"Quantifier {quant_str} applied to empty pattern has no effect"
            )
        
        # Check for nested reluctant quantifiers
        if reluctant and self.has_reluctant_quantifier(ast.children[0]):
            self.warnings.append(
                "Nested reluctant quantifiers may lead to complex matching behavior"
            )
        
        # Check for quantifier applied to alternation with empty branch
        if ast.children[0].type == "alternation" and self.has_empty_branch(ast.children[0]):
            self.warnings.append(
                f"Quantifier {quant_str} applied to alternation with empty branch "
                "may lead to unexpected matching behavior"
            )
    
    def _validate_permutation(self, ast):
        """Validate a permutation node"""
        if len(ast.children) < 2:
            self.errors.append(
                f"PERMUTE requires at least two elements, found {len(ast.children)}"
            )
        
        # Check for duplicates in permutation
        values = [child.value for child in ast.children if child.type == "literal"]
        duplicates = {val for val in values if values.count(val) > 1}
        if duplicates:
            self.errors.append(
                f"PERMUTE contains duplicate elements: {', '.join(duplicates)}"
            )
        
        # Check for non-literal elements in permutation
        for child in ast.children:
            if child.type != "literal":
                self.warnings.append(
                    f"PERMUTE contains a non-literal element of type '{child.type}', "
                    "which may lead to unexpected behavior"
                )
    
    def _validate_alternation(self, ast):
        """Validate an alternation node"""
        if len(ast.children) < 2:
            self.errors.append(
                f"Alternation requires at least two alternatives, found {len(ast.children)}"
            )
        
        # Check for duplicate branches
        branch_strs = []
        for child in ast.children:
            branch_str = self.pattern_to_string(child)
            branch_strs.append(branch_str)
        
        duplicates = {val for val in branch_strs if branch_strs.count(val) > 1}
        if duplicates:
            self.warnings.append(
                f"Alternation contains duplicate branches: {', '.join(duplicates)}"
            )
        
        # Check for empty branches
        if self.has_empty_branch(ast):
            self.warnings.append(
                "Alternation contains an empty branch, which may match zero-length sequences"
            )
    
    def _validate_exclusion(self, ast):
        """Validate an exclusion node"""
        if not ast.children:
            self.errors.append("Exclusion has no content")
            return
        
        # Check for nested exclusions
        for child in ast.children:
            if self.has_exclusion_node(child):
                self.warnings.append(
                    "Nested exclusions may lead to complex matching behavior"
                )
    
    def _validate_subsets(self, subset_mapping):
        """Validate subset definitions"""
        for subset_var, components in subset_mapping.items():
            # Check that subset variable doesn't conflict with pattern variables
            if subset_var in self.pattern_variables:
                self.errors.append(
                    f"Subset variable '{subset_var}' conflicts with a pattern variable of the same name"
                )
            
            # Check that subset components exist in pattern
            for component in components:
                if component not in self.pattern_variables:
                    self.errors.append(
                        f"Subset '{subset_var}' references undefined pattern variable '{component}'"
                    )
            
            # Check for empty subsets
            if not components:
                self.errors.append(f"Subset '{subset_var}' is empty")
                
            # Check for single-element subsets (usually not useful)
            if len(components) == 1:
                self.warnings.append(
                    f"Subset '{subset_var}' contains only one element '{components[0]}', "
                    "which may be unnecessary"
                )
            
            # Check for subsets that include all pattern variables
            if set(components) == self.pattern_variables:
                self.warnings.append(
                    f"Subset '{subset_var}' includes all pattern variables, "
                    "which is equivalent to not using a pattern variable prefix"
                )
    
    def has_complex_group(self, ast):
        """Check if a group contains complex pattern elements"""
        if not ast.children:
            return False
        
        child = ast.children[0]
        return child.type in ["alternation", "concatenation", "permutation"]
    
    def has_reluctant_quantifier(self, ast):
        """Check if an AST contains a reluctant quantifier"""
        if ast.type == "quantifier" and ast.quantifier and ast.quantifier.endswith("?"):
            return True
        
        for child in ast.children:
            if self.has_reluctant_quantifier(child):
                return True
        
        return False
    
    def has_empty_branch(self, ast):
        """Check if an alternation has an empty branch"""
        for child in ast.children:
            if child.type == "empty":
                return True
        return False
    
    def has_exclusion_node(self, ast):
        """Check if an AST contains an exclusion node"""
        if ast.type == "exclusion":
            return True
        
        for child in ast.children:
            if self.has_exclusion_node(child):
                return True
        
        return False
    
    def pattern_to_string(self, ast):
        """Convert a pattern AST to a string representation for comparison"""
        if ast.type == "literal":
            return ast.value
        elif ast.type == "empty":
            return "()"
        elif ast.type == "concatenation":
            return "".join(self.pattern_to_string(child) for child in ast.children)
        elif ast.type == "alternation":
            return "(" + "|".join(self.pattern_to_string(child) for child in ast.children) + ")"
        elif ast.type == "group":
            return "(" + self.pattern_to_string(ast.children[0]) + ")"
        elif ast.type == "quantifier":
            return self.pattern_to_string(ast.children[0]) + (ast.quantifier or "")
        elif ast.type == "permutation":
            return "PERMUTE(" + ",".join(self.pattern_to_string(child) for child in ast.children) + ")"
        elif ast.type == "exclusion":
            return "{-" + self.pattern_to_string(ast.children[0]) + "-}"
        return ""
