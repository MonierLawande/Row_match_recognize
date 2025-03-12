import re
from src.ast.expression_ast import ExpressionAST

class ExpressionParser:
    """
    A recursive descent parser for SQL expressions.
    
    This parser supports:
      - Binary operations (+, -, *, /)
      - Parenthesized expressions
      - Navigation functions (PREV, NEXT, FIRST, LAST) with optional offsets
      - Nested navigation (i.e. navigation functions within navigation function arguments)
      - Semantics keywords (RUNNING, FINAL) that set a semantics field on the AST node
    """
    def __init__(self, expr_text: str):
        self.tokens = self.tokenize(expr_text)
        self.pos = 0

    def tokenize(self, expr: str):
        # Insert spaces around special symbols for easier tokenization.
        for sym in ['(', ')', ',', '+', '-', '*', '/']:
            expr = expr.replace(sym, f' {sym} ')
        return [t for t in expr.split() if t]

    def next_token(self):
        if self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            self.pos += 1
            return token
        return None

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def parse(self):
        return self.parse_expression()

    def parse_expression(self):
        # Parse an expression with binary operators + and -.
        left = self.parse_term()
        while self.peek() in ['+', '-']:
            op = self.next_token()
            right = self.parse_term()
            left = ExpressionAST(type="binary", operator=op, children=[left, right])
        return left

    def parse_term(self):
        # Parse an expression with binary operators * and /.
        left = self.parse_factor()
        while self.peek() in ['*', '/']:
            op = self.next_token()
            right = self.parse_factor()
            left = ExpressionAST(type="binary", operator=op, children=[left, right])
        return left

    def parse_factor(self):
        # For this example, factor is the same as primary.
        return self.parse_primary()

    def parse_primary(self):
        """
        Parses a primary expression.
        
        It checks for optional semantics keywords ("RUNNING" or "FINAL") first.
        Then it supports:
          - Parenthesized expressions
          - Navigation functions (which may be nested)
          - Literals and identifiers
        """
        semantics = None
        token = self.peek()
        if token and token.upper() in ['RUNNING', 'FINAL']:
            semantics = self.next_token().upper()

        token = self.peek()
        # Parenthesized expression
        if token == '(':
            self.next_token()  # Consume '('
            expr = self.parse_expression()
            if self.next_token() != ')':
                raise ValueError("Expected closing parenthesis")
            if semantics:
                expr.semantics = semantics
            return expr

        # Navigation functions: PREV, NEXT, FIRST, LAST
        if token and token.upper() in ['PREV', 'NEXT', 'FIRST', 'LAST']:
            func_name = self.next_token().upper()
            if self.next_token() != '(':
                raise ValueError(f"Expected '(' after {func_name}")
            # Parse the target expression; this call allows nesting
            target_expr = self.parse_expression()
            offset = 0
            if self.peek() == ',':
                self.next_token()  # Consume comma
                offset_expr = self.parse_expression()
                try:
                    offset = int(offset_expr.value)
                except Exception:
                    raise ValueError("Navigation function offset must be an integer literal")
            if self.next_token() != ')':
                raise ValueError(f"Expected ')' after {func_name} call")
            nav_ast = ExpressionAST(
                type="navigation",
                navigation_type=func_name,
                children=[target_expr],
                offset=offset,
                semantics=semantics
            )
            return nav_ast

        # Handle numeric literals
        token = self.next_token()
        if token is None:
            raise ValueError("Unexpected end of expression")
        if token.isdigit() or self.is_decimal(token):
            lit_ast = ExpressionAST(type="literal", value=token, semantics=semantics)
            return lit_ast

        # Otherwise, treat as an identifier
        ident_ast = ExpressionAST(type="identifier", value=token, semantics=semantics)
        return ident_ast

    def is_decimal(self, token: str):
        try:
            float(token)
            return True
        except ValueError:
            return False

def parse_expression_full(expr_text: str):
    parser = ExpressionParser(expr_text)
    ast = parser.parse()
    return {"raw": expr_text, "ast": ast}
