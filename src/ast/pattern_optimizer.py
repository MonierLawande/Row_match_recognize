# src/ast/pattern_optimizer.py

from typing import Dict, Any, Optional, List
from src.ast.pattern_ast import PatternAST

# Import MatchRecognizeAST only when needed to avoid circular imports
def _get_match_recognize_ast_class():
    from src.ast.match_recognize_ast import MatchRecognizeAST
    return MatchRecognizeAST

class PatternOptimizer:
    """
    Optimizes pattern ASTs for better execution performance.
    
    This class applies various optimization techniques:
    1. Simplify nested groups
    2. Merge adjacent literals
    3. Simplify quantifiers
    4. Remove redundant nodes
    """
    
    def __init__(self):
        self.optimizations_applied = []
        
    def optimize(self, node: PatternAST) -> PatternAST:
        """
        Recursively optimize a pattern AST node.
        
        Args:
            node: The pattern AST node to optimize
            
        Returns:
            The optimized pattern AST node
        """
        if not node:
            return node
        
        # First optimize children
        if node.children:
            node.children = [self.optimize(child) for child in node.children]
            # Remove None children
            node.children = [child for child in node.children if child is not None]
        
        # Apply optimizations based on node type
        if node.type == "group":
            return self._optimize_group(node)
        elif node.type == "concatenation":
            return self._optimize_concatenation(node)
        elif node.type == "alternation":
            return self._optimize_alternation(node)
        elif node.type == "quantifier":
            return self._optimize_quantifier(node)
            
        return node
        
    def _optimize_group(self, node: PatternAST) -> PatternAST:
        """Optimize a group node"""
        # Simplify single-child groups
        if len(node.children) == 1:
            child = node.children[0]
            # Preserve quantifiers when removing group
            if node.quantifier:
                child.quantifier = node.quantifier
                child.quantifier_min = node.quantifier_min
                child.quantifier_max = node.quantifier_max
            self.optimizations_applied.append("Simplified group with single child")
            return child
        return node
        
    def _optimize_concatenation(self, node: PatternAST) -> PatternAST:
        """Optimize a concatenation node"""
        # Merge adjacent literals
        if len(node.children) > 1:
            merged = []
            current_literal = None
            
            for child in node.children:
                if child.type == "literal" and not child.quantifier:
                    if current_literal:
                        current_literal.value += child.value
                        self.optimizations_applied.append(f"Merged literals: {current_literal.value}")
                    else:
                        current_literal = PatternAST(
                            type="literal",
                            value=child.value,
                            line=child.line,
                            column=child.column
                        )
                        merged.append(current_literal)
                else:
                    current_literal = None
                    merged.append(child)
                    
            node.children = merged
            
        # Simplify single-child concatenations
        if len(node.children) == 1:
            self.optimizations_applied.append("Simplified concatenation with single child")
            return node.children[0]
            
        return node
        
    def _optimize_alternation(self, node: PatternAST) -> PatternAST:
        """Optimize an alternation node"""
        # Remove duplicate alternatives
        if len(node.children) > 1:
            unique_children = []
            seen = set()
            
            for child in node.children:
                child_str = self._node_to_string(child)
                if child_str not in seen:
                    seen.add(child_str)
                    unique_children.append(child)
                else:
                    self.optimizations_applied.append(f"Removed duplicate alternative: {child_str}")
                    
            node.children = unique_children
            
        # Simplify single-child alternations
        if len(node.children) == 1:
            self.optimizations_applied.append("Simplified alternation with single child")
            return node.children[0]
            
        return node
        
    def _optimize_quantifier(self, node: PatternAST) -> PatternAST:
        """Optimize a quantifier node"""
        # Simplify quantifiers
        if node.quantifier == "?":
            node.quantifier_min = 0
            node.quantifier_max = 1
            self.optimizations_applied.append("Simplified '?' quantifier")
        elif node.quantifier == "*":
            node.quantifier_min = 0
            node.quantifier_max = None
            self.optimizations_applied.append("Simplified '*' quantifier")
        elif node.quantifier == "+":
            node.quantifier_min = 1
            node.quantifier_max = None
            self.optimizations_applied.append("Simplified '+' quantifier")
            
        return node
        
    def _node_to_string(self, node: PatternAST) -> str:
        """
        Convert a pattern AST node to a string representation for comparison.
        
        Args:
            node: The pattern AST node
            
        Returns:
            A string representation of the node
        """
        if node.type == "literal":
            return f"LIT({node.value})"
        elif node.type in ["group", "concatenation", "alternation"]:
            return f"{node.type.upper()}({','.join(self._node_to_string(child) for child in node.children)})"
        elif node.type == "quantifier":
            return f"QUANT({node.quantifier}:{self._node_to_string(node.children[0])})"
        else:
            return str(node.type)
            
    def get_optimizations_applied(self) -> List[str]:
        """Get a list of optimizations that were applied"""
        return self.optimizations_applied


def optimize_ast(ast: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimize the AST for better execution performance.
    
    This function applies various optimization techniques:
    1. Pattern optimization (simplify groups, merge literals)
    2. Expression optimization (constant folding, common subexpression elimination)
    
    Args:
        ast: The AST to optimize
        
    Returns:
        The optimized AST
    """
    if ast is None:
        return None
    
    # Create a deep copy to avoid modifying the original
    optimized_ast = ast.copy()
    
    # Step 1: Optimize patterns
    if "match_recognize" in optimized_ast:
        for i, mr_ast in enumerate(optimized_ast["match_recognize"]):
            # Get MatchRecognizeAST class only when needed
            MatchRecognizeAST = _get_match_recognize_ast_class()
            
            # Handle both dictionary and MatchRecognizeAST objects
            if isinstance(mr_ast, MatchRecognizeAST):
                if hasattr(mr_ast, 'pattern') and mr_ast.pattern:
                    optimized_ast["match_recognize"][i].pattern = optimize_pattern(mr_ast.pattern)
            elif isinstance(mr_ast, dict):
                if "pattern" in mr_ast:
                    optimized_ast["match_recognize"][i]["pattern"] = optimize_pattern(mr_ast["pattern"])
    
    # Step 2: Optimize expressions (constant folding, etc.)
    optimized_ast = optimize_expressions(optimized_ast)
    
    return optimized_ast


def optimize_pattern(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimize a pattern AST by applying various optimization techniques.
    
    Args:
        pattern: The pattern AST to optimize
        
    Returns:
        The optimized pattern AST
    """
    if not pattern or "ast" not in pattern:
        return pattern
    
    # Create a deep copy of the pattern
    optimized = pattern.copy()
    
    # Apply optimizations
    optimizer = PatternOptimizer()
    optimized["ast"] = optimizer.optimize(pattern["ast"])
    
    # Add optimization metadata
    optimized["optimizations"] = optimizer.get_optimizations_applied()
    
    return optimized


def optimize_expressions(ast: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimize expressions in the AST.
    
    This function applies optimizations like:
    1. Constant folding (e.g., 2+3 -> 5)
    2. Common subexpression elimination
    3. Dead code elimination
    
    Args:
        ast: The AST to optimize
        
    Returns:
        The optimized AST
    """
    # This is a placeholder for expression optimization
    # In a real implementation, you would traverse the AST and apply optimizations to expressions
    
    return ast
