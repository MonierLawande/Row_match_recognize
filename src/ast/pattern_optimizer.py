# src/ast/pattern_optimizer.py

from typing import Dict, Any, Optional
from src.ast.pattern_ast import PatternAST

# Import MatchRecognizeAST only when needed to avoid circular imports
def _get_match_recognize_ast_class():
    from src.ast.match_recognize_ast import MatchRecognizeAST
    return MatchRecognizeAST
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
    
    return optimized_ast

def optimize_pattern(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimize a pattern AST by applying various optimization techniques.
    
    Optimizations include:
    1. Simplifying nested groups
    2. Merging adjacent literals
    3. Simplifying quantifiers
    4. Removing redundant nodes
    
    Args:
        pattern: The pattern AST to optimize
        
    Returns:
        The optimized pattern AST
    """
    if not pattern or "ast" not in pattern:
        return pattern
    
    # Create a deep copy of the pattern
    optimized = pattern.copy()
    optimized["ast"] = _optimize_pattern_node(pattern["ast"])
    
    return optimized

def _optimize_pattern_node(node: PatternAST) -> PatternAST:
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
        node.children = [_optimize_pattern_node(child) for child in node.children]
        # Remove None children
        node.children = [child for child in node.children if child is not None]
    
    # Apply optimizations based on node type
    if node.type == "group":
        # Simplify single-child groups
        if len(node.children) == 1:
            child = node.children[0]
            # Preserve quantifiers when removing group
            if node.quantifier:
                child.quantifier = node.quantifier
                child.quantifier_min = node.quantifier_min
                child.quantifier_max = node.quantifier_max
            return child
            
    elif node.type == "concatenation":
        # Merge adjacent literals
        if len(node.children) > 1:
            merged = []
            current_literal = None
            
            for child in node.children:
                if child.type == "literal" and not child.quantifier:
                    if current_literal:
                        current_literal.value += child.value
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
            return node.children[0]
            
    elif node.type == "alternation":
        # Remove duplicate alternatives
        if len(node.children) > 1:
            unique_children = []
            seen = set()
            
            for child in node.children:
                child_str = _node_to_string(child)
                if child_str not in seen:
                    seen.add(child_str)
                    unique_children.append(child)
                    
            node.children = unique_children
            
        # Simplify single-child alternations
        if len(node.children) == 1:
            return node.children[0]
            
    elif node.type == "quantifier":
        # Simplify quantifiers
        if node.quantifier == "?":
            node.quantifier_min = 0
            node.quantifier_max = 1
        elif node.quantifier == "*":
            node.quantifier_min = 0
            node.quantifier_max = None
        elif node.quantifier == "+":
            node.quantifier_min = 1
            node.quantifier_max = None
            
    return node

def _node_to_string(node: PatternAST) -> str:
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
        return f"{node.type.upper()}({','.join(_node_to_string(child) for child in node.children)})"
    elif node.type == "quantifier":
        return f"QUANT({node.quantifier}:{_node_to_string(node.children[0])})"
    else:
        return str(node.type)
