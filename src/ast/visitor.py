# src/ast/visitor.py

from abc import ABC, abstractmethod
from src.ast.pattern_ast import PatternAST
from src.ast.expression_ast import ExpressionAST

class ASTVisitor(ABC):
    """Base visitor interface for AST nodes"""
    
    @abstractmethod
    def visit_pattern_ast(self, ast: PatternAST):
        pass
        
    @abstractmethod
    def visit_expression_ast(self, ast: ExpressionAST):
        pass

class PatternVisitor(ASTVisitor):
    """Visitor for pattern AST nodes"""
    
    def visit_pattern_ast(self, ast: PatternAST):
        method_name = f"visit_{ast.type}"
        method = getattr(self, method_name, self.visit_default)
        return method(ast)
        
    def visit_default(self, ast: PatternAST):
        """Default handler for pattern nodes"""
        result = self.pre_visit(ast)
        for child in ast.children:
            self.visit_pattern_ast(child)
        self.post_visit(ast)
        return result
        
    def pre_visit(self, ast: PatternAST):
        """Called before visiting children"""
        return None
        
    def post_visit(self, ast: PatternAST):
        """Called after visiting children"""
        pass
        
    def visit_expression_ast(self, ast: ExpressionAST):
        """Delegate to an expression visitor if needed"""
        pass

class ExpressionVisitor(ASTVisitor):
    """Visitor for expression AST nodes"""
    
    def visit_expression_ast(self, ast: ExpressionAST):
        method_name = f"visit_{ast.type}"
        method = getattr(self, method_name, self.visit_default)
        return method(ast)
        
    def visit_default(self, ast: ExpressionAST):
        """Default handler for expression nodes"""
        result = self.pre_visit(ast)
        for child in ast.children:
            self.visit_expression_ast(child)
        self.post_visit(ast)
        return result
        
    def pre_visit(self, ast: ExpressionAST):
        """Called before visiting children"""
        return None
        
    def post_visit(self, ast: ExpressionAST):
        """Called after visiting children"""
        pass
        
    def visit_pattern_ast(self, ast: PatternAST):
        """Delegate to a pattern visitor if needed"""
        pass