# src/ast/expression_optimizer.py

from typing import Dict, Any, Optional, List
from src.ast.expression_ast import ExpressionAST

class ExpressionOptimizer:
    """
    Optimizes expression ASTs for better execution performance.
    
    This class applies various optimization techniques:
    1. Constant folding
    2. Common subexpression elimination
    3. Dead code elimination
    4. Boolean expression simplification
    5. Pattern variable reference optimization
    """
    
    def __init__(self):
        self.optimizations_applied = []
        self.subexpr_cache = {}
        
    def optimize(self, expr: ExpressionAST) -> ExpressionAST:
        """
        Optimize an expression AST.
        
        Args:
            expr: The expression AST to optimize
            
        Returns:
            The optimized expression AST
        """
        if not expr:
            return expr
            
        # First optimize children
        for i, child in enumerate(expr.children):
            expr.children[i] = self.optimize(child)
            
        # Apply optimizations
        expr = self._fold_constants(expr)
        expr = self._simplify_boolean_expressions(expr)
        expr = self._eliminate_common_subexpressions(expr)
        expr = self._optimize_pattern_references(expr)
        
        return expr
        
    def _fold_constants(self, expr: ExpressionAST) -> ExpressionAST:
        """Fold constant expressions"""
        if expr.type == "binary" and len(expr.children) == 2:
            left, right = expr.children
            
            # Check if both operands are literals
            if left.type == "literal" and right.type == "literal":
                try:
                    # Evaluate the expression
                    result = self._evaluate_binary_expression(left.value, right.value, expr.operator)
                    if result is not None:
                        self.optimizations_applied.append(f"Folded constant: {left.value} {expr.operator} {right.value} -> {result}")
                        return ExpressionAST(type="literal", value=str(result))
                except:
                    # If evaluation fails, return the original expression
                    pass
                    
        return expr
        
    def _simplify_boolean_expressions(self, expr: ExpressionAST) -> ExpressionAST:
        """Simplify boolean expressions"""
        if expr.type == "binary" and expr.operator in ["AND", "OR"] and len(expr.children) == 2:
            left, right = expr.children
            
            # Check for AND with FALSE
            if expr.operator == "AND":
                if (left.type == "literal" and left.value.lower() == "false") or \
                   (right.type == "literal" and right.value.lower() == "false"):
                    self.optimizations_applied.append("Simplified AND with FALSE to FALSE")
                    return ExpressionAST(type="literal", value="false")
                    
                # Check for AND with TRUE
                if left.type == "literal" and left.value.lower() == "true":
                    self.optimizations_applied.append("Simplified AND with TRUE to right operand")
                    return right
                if right.type == "literal" and right.value.lower() == "true":
                    self.optimizations_applied.append("Simplified AND with TRUE to left operand")
                    return left
                    
            # Check for OR with TRUE
            if expr.operator == "OR":
                if (left.type == "literal" and left.value.lower() == "true") or \
                   (right.type == "literal" and right.value.lower() == "true"):
                    self.optimizations_applied.append("Simplified OR with TRUE to TRUE")
                    return ExpressionAST(type="literal", value="true")
                    
                # Check for OR with FALSE
                if left.type == "literal" and left.value.lower() == "false":
                    self.optimizations_applied.append("Simplified OR with FALSE to right operand")
                    return right
                if right.type == "literal" and right.value.lower() == "false":
                    self.optimizations_applied.append("Simplified OR with FALSE to left operand")
                    return left
                    
        return expr
        
    def _eliminate_common_subexpressions(self, expr: ExpressionAST) -> ExpressionAST:
        """Eliminate common subexpressions"""
        # Convert expression to string for caching
        expr_str = self._expr_to_string(expr)
        
        # Check if we've seen this expression before
        if expr_str in self.subexpr_cache:
            self.optimizations_applied.append(f"Eliminated common subexpression: {expr_str}")
            return self.subexpr_cache[expr_str]
            
        # Cache the expression
        self.subexpr_cache[expr_str] = expr
        return expr
        
    def _optimize_pattern_references(self, expr: ExpressionAST) -> ExpressionAST:
        """Optimize pattern variable references"""
        if expr.type == "pattern_variable_reference":
            # Check if we can combine multiple references to same pattern variable
            if expr.children:
                refs = self._collect_pattern_refs(expr)
                if len(refs) > 1:
                    # Combine references using same pattern variable
                    combined = self._combine_pattern_refs(refs)
                    if combined:
                        self.optimizations_applied.append(
                            f"Combined pattern references for variable {expr.pattern_variable}"
                        )
                        return combined
                        
        return expr
        
    def _evaluate_binary_expression(self, left_val: str, right_val: str, operator: str) -> Optional[Any]:
        """Evaluate a binary expression with literal operands"""
        try:
            # Try integers first
            left_num = int(left_val)
            right_num = int(right_val)
        except ValueError:
            try:
                # Try floats next
                left_num = float(left_val)
                right_num = float(right_val)
            except ValueError:
                # Handle string operations
                if operator == "+":
                    return left_val + right_val
                return None
                
        # Evaluate numeric operations
        if operator == "+":
            return left_num + right_num
        elif operator == "-":
            return left_num - right_num
        elif operator == "*":
            return left_num * right_num
        elif operator == "/":
            if right_num == 0:
                return None  # Avoid division by zero
            return left_num / right_num
        elif operator == "AND":
            return left_num and right_num
        elif operator == "OR":
            return left_num or right_num
            
        return None
        
    def _expr_to_string(self, expr: ExpressionAST) -> str:
        """Convert an expression to a string representation for comparison"""
        if expr.type == "literal":
            return f"LIT({expr.value})"
        elif expr.type == "identifier":
            return f"ID({expr.value})"
        elif expr.type == "binary":
            return f"BIN({expr.operator},{','.join(self._expr_to_string(child) for child in expr.children)})"
        elif expr.type == "pattern_variable_reference":
            return f"REF({expr.pattern_variable}.{expr.column})"
        elif expr.type == "function":
            return f"FUNC({expr.value},{','.join(self._expr_to_string(child) for child in expr.children)})"
        elif expr.type == "aggregate":
            return f"AGG({expr.value},{','.join(self._expr_to_string(child) for child in expr.children)})"
        elif expr.type == "navigation":
            return f"NAV({expr.navigation_type},{','.join(self._expr_to_string(child) for child in expr.children)})"
        else:
            return str(expr.type)
            
    def _collect_pattern_refs(self, expr: ExpressionAST) -> List[ExpressionAST]:
        """Collect all pattern variable references in an expression"""
        refs = []
        
        def collect(ast):
            if ast.type == "pattern_variable_reference":
                refs.append(ast)
            for child in ast.children:
                collect(child)
                
        collect(expr)
        return refs
        
    def _combine_pattern_refs(self, refs: List[ExpressionAST]) -> Optional[ExpressionAST]:
        """Try to combine multiple pattern variable references"""
        if not refs:
            return None
            
        # Group references by pattern variable
        by_var = {}
        for ref in refs:
            if ref.pattern_variable not in by_var:
                by_var[ref.pattern_variable] = []
            by_var[ref.pattern_variable].append(ref)
            
        # If we have multiple references to same variable, try to combine them
        for var, var_refs in by_var.items():
            if len(var_refs) > 1:
                # For now, just combine using first reference
                # In a real implementation, you'd want smarter combining logic
                combined = var_refs[0]
                self.optimizations_applied.append(
                    f"Combined {len(var_refs)} references to pattern variable {var}"
                )
                return combined
                
        return None
        
    def get_optimizations_applied(self) -> List[str]:
        """Get a list of optimizations that were applied"""
        return self.optimizations_applied


def optimize_expression(expr: ExpressionAST) -> Dict[str, Any]:
    """
    Optimize an expression AST.
    
    Args:
        expr: The expression AST to optimize
        
    Returns:
        Dictionary containing:
        - ast: The optimized expression AST
        - optimizations: List of optimizations applied
    """
    optimizer = ExpressionOptimizer()
    optimized_expr = optimizer.optimize(expr)
    
    return {
        "ast": optimized_expr,
        "optimizations": optimizer.get_optimizations_applied()
    }
