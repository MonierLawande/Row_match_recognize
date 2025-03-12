import re
from src.ast.expression_ast import ExpressionAST

AGGREGATE_FUNCTIONS = ['avg', 'min', 'max', 'count', 'sum', 'max_by', 'min_by', 'array_agg']

class ExpressionParser:
    """
    A recursive descent parser for SQL expressions.
    
    Supports:
      - Binary operations (+, -, *, /)
      - Parenthesized expressions
      - General function calls, including aggregate functions (avg, count, etc.),
        classifier, and match_number.
      - Navigation functions (PREV, NEXT, FIRST, LAST) with optional offsets,
        which may be nested.
      - Optional semantics keywords ("RUNNING", "FINAL") that annotate the AST node.
    """
    def __init__(self, expr_text: str):
        self.tokens = self.tokenize(expr_text)
        self.pos = 0

    def tokenize(self, expr: str):
        # Insert spaces around special symbols to ease tokenization.
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
        # Parse an expression supporting binary operators + and -
        left = self.parse_term()
        while self.peek() in ['+', '-']:
            op = self.next_token()
            right = self.parse_term()
            left = ExpressionAST(type="binary", operator=op, children=[left, right])
        return left

    def parse_term(self):
        # Parse multiplication/division.
        left = self.parse_factor()
        while self.peek() in ['*', '/']:
            op = self.next_token()
            right = self.parse_factor()
            left = ExpressionAST(type="binary", operator=op, children=[left, right])
        return left

    def parse_factor(self):
        # For simplicity, factor is the same as primary.
        return self.parse_primary()

    def parse_primary(self):
        """
        Parses a primary expression.
        
        Checks for an optional semantics keyword ("RUNNING" or "FINAL").
        Then, handles:
          - Parenthesized expressions
          - Function calls (general and aggregate)
          - Navigation functions (treated as a special function call)
          - Literals and identifiers.
        """
        semantics = None
        token = self.peek()
        if token and token.upper() in ['RUNNING', 'FINAL']:
            semantics = self.next_token().upper()

        token = self.peek()
        if token == '(':
            self.next_token()  # Consume '('
            expr = self.parse_expression()
            if self.next_token() != ')':
                raise ValueError("Expected closing parenthesis")
            if semantics:
                expr.semantics = semantics
            return expr

        # Look for a function call.
        token = self.next_token()
        if token is None:
            raise ValueError("Unexpected end of expression")

        # If the next token is '(' then this is a function call.
        if self.peek() == '(':
            func_name = token
            self.next_token()  # Consume '('
            arguments = []
            if self.peek() != ')':
                while True:
                    arg = self.parse_expression()
                    arguments.append(arg)
                    if self.peek() == ',':
                        self.next_token()  # Consume comma
                    else:
                        break
            if self.next_token() != ')':
                raise ValueError(f"Expected closing ')' in function call {func_name}")
            # Distinguish aggregate functions.
            if func_name.lower() in AGGREGATE_FUNCTIONS:
                func_type = "aggregate"
            else:
                func_type = "function"
            func_ast = ExpressionAST(
                type=func_type,
                value=func_name,
                children=arguments,
                semantics=semantics
            )
            return func_ast

        # Check for navigation function call (if the token itself is a navigation keyword)
        if token.upper() in ['PREV', 'NEXT', 'FIRST', 'LAST']:
            func_name = token.upper()
            if self.next_token() != '(':
                raise ValueError(f"Expected '(' after {func_name}")
            target_expr = self.parse_expression()  # Allow nested navigation
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

        # If token is numeric, treat as literal.
        if token.isdigit() or self.is_decimal(token):
            lit_ast = ExpressionAST(type="literal", value=token, semantics=semantics)
            return lit_ast

        # Otherwise, treat as an identifier.
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
