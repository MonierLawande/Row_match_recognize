# src/parser/expression_parser.py

import re
from src.ast.expression_ast import ExpressionAST

# Define constants for better code readability
AGGREGATE_FUNCTIONS = ['avg', 'min', 'max', 'count', 'sum', 'max_by', 'min_by', 'array_agg']
NAVIGATION_FUNCTIONS = ['PREV', 'NEXT', 'FIRST', 'LAST']
SEMANTICS_KEYWORDS = ['RUNNING', 'FINAL']
ALLOWED_FINAL_FUNCTIONS = NAVIGATION_FUNCTIONS + AGGREGATE_FUNCTIONS

class ExpressionParser:
    """
    A recursive descent parser for SQL expressions in MATCH_RECOGNIZE context.
    
    Supports:
      - Binary operations (+, -, *, /)
      - Parenthesized expressions
      - General function calls, including aggregate functions
      - Navigation functions (PREV, NEXT, FIRST, LAST) with optional offsets
      - RUNNING and FINAL semantics keywords
      - Pattern variable references (e.g., A.column, U.column)
      - Special functions: CLASSIFIER() and MATCH_NUMBER()
      - Special count(*) and count(var.*) syntax
    """
    def __init__(self, expr_text: str):
        self.expr_text = expr_text
        self.tokens = self.tokenize(expr_text)
        self.pos = 0
        self.nesting_level = 0
        self.in_aggregate = False
        self.in_navigation = False
        self.in_measures_clause = True  # Default to True, can be set from outside
        self.MAX_NESTING = 5  # Maximum allowed nesting depth

    def tokenize(self, expr: str):
        # Handle special count(*) and count(var.*) syntax
        expr = re.sub(r'(\w+)\.\*', r'\1 DOT_STAR', expr)
        expr = expr.replace('*', ' STAR ')
        
        # Insert spaces around special symbols to ease tokenization
        for sym in ['(', ')', ',', '+', '-', '*', '/', '.']:
            expr = expr.replace(sym, f' {sym} ')
            
        # Split into tokens and restore special tokens
        tokens = [t for t in expr.split() if t]
        tokens = [t.replace('DOT_STAR', '.*') for t in tokens]
        tokens = [t.replace('STAR', '*') for t in tokens]
        
        return tokens

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
        
    def expect(self, expected_token):
        """Consume next token and verify it matches expected_token"""
        token = self.next_token()
        if token != expected_token:
            raise ValueError(f"Expected '{expected_token}', got '{token or 'end of expression'}'")
        return token

    def parse(self):
        """Parse the expression and return the AST"""
        result = self.parse_expression()
        if self.peek() is not None:
            raise ValueError(f"Unexpected token '{self.peek()}' after expression")
        return result

    def parse_expression(self):
        """Parse an expression supporting binary operators + and -"""
        left = self.parse_term()
        while self.peek() in ['+', '-']:
            op = self.next_token()
            right = self.parse_term()
            left = ExpressionAST(type="binary", operator=op, children=[left, right])
        return left

    def parse_term(self):
        """Parse multiplication/division"""
        left = self.parse_factor()
        while self.peek() in ['*', '/']:
            op = self.next_token()
            right = self.parse_factor()
            left = ExpressionAST(type="binary", operator=op, children=[left, right])
        return left

    def parse_factor(self):
        """Parse a factor (primary expression)"""
        return self.parse_primary()

    def parse_primary(self):
        """
        Parse a primary expression with enhanced error handling.
        
        Handles:
          - Optional semantics keywords (RUNNING, FINAL)
          - Parenthesized expressions
          - Function calls (including navigation and aggregate functions)
          - Pattern variable references (e.g., A.column)
          - Literals and identifiers
        """
        # Check for semantics keyword
        semantics = None
        token = self.peek()
        if token and token.upper() in SEMANTICS_KEYWORDS:
            semantics = self.next_token().upper()
            
            # Validate FINAL semantics
            if semantics == 'FINAL':
                # FINAL can only be used in MEASURES clause
                if not self.in_measures_clause:
                    raise ValueError("FINAL semantics can only be used in MEASURES clause")
                
                # FINAL can only be applied to aggregate or navigation functions
                if not self.is_function_ahead():
                    raise ValueError("FINAL semantics can only be applied to aggregate or navigation functions")
                
                # Check if the function ahead is allowed with FINAL
                if self.pos + 1 < len(self.tokens):
                    func_name = self.tokens[self.pos].upper()
                    if func_name not in ALLOWED_FINAL_FUNCTIONS:
                        raise ValueError(f"FINAL semantics cannot be applied to function '{func_name}'")

        # Handle parenthesized expressions
        token = self.peek()
        if token == '(':
            self.nesting_level += 1
            if self.nesting_level > self.MAX_NESTING:
                raise ValueError(f"Expression nesting too deep (max {self.MAX_NESTING} levels)")
            
            self.next_token()  # Consume '('
            expr = self.parse_expression()
            if self.next_token() != ')':
                raise ValueError("Missing closing parenthesis")
            
            self.nesting_level -= 1
            if semantics:
                expr.semantics = semantics
            return expr

        # Handle function calls or identifiers
        token = self.next_token()
        if token is None:
            raise ValueError("Unexpected end of expression")

        # Check for function call
        if self.peek() == '(':
            func_name = token
            
            # Handle special functions
            if func_name.upper() == 'CLASSIFIER':
                return self.parse_classifier_function(semantics)
            elif func_name.upper() == 'MATCH_NUMBER':
                return self.parse_match_number_function(semantics)
            # Handle navigation functions
            elif func_name.upper() in NAVIGATION_FUNCTIONS:
                return self.parse_navigation_function(func_name, semantics)
            # Handle count(*) and count(var.*)
            elif func_name.lower() == 'count':
                return self.parse_count_function(semantics)
            # Handle regular and aggregate functions
            else:
                return self.parse_function_call(func_name, semantics)

        # Check for pattern variable reference (e.g., A.column)
        if self.peek() == '.':
            pattern_var = token
            self.next_token()  # Consume '.'
            column = self.next_token()
            if not column:
                raise ValueError(f"Expected column name after '{pattern_var}.'")
            
            # Check for special count(var.*) syntax
            if column == '*':
                return ExpressionAST(
                    type="pattern_variable_reference",
                    pattern_variable=pattern_var,
                    column=column,
                    count_star=True,
                    semantics=semantics
                )
            
            return ExpressionAST(
                type="pattern_variable_reference",
                pattern_variable=pattern_var,
                column=column,
                semantics=semantics
            )

        # Handle literals and identifiers
        if token.isdigit() or self.is_decimal(token):
            return ExpressionAST(type="literal", value=token, semantics=semantics)
        else:
            return ExpressionAST(type="identifier", value=token, semantics=semantics)

    def parse_classifier_function(self, semantics=None):
        """Parse CLASSIFIER() function with optional pattern variable argument"""
        self.expect('(')
        pattern_var = None
        if self.peek() != ')':
            pattern_var = self.next_token()
        self.expect(')')
        
        return ExpressionAST(
            type="classifier",
            pattern_variable=pattern_var,
            semantics=semantics
        )
        
    def parse_match_number_function(self, semantics=None):
        """Parse MATCH_NUMBER() function"""
        self.expect('(')
        self.expect(')')
        
        return ExpressionAST(
            type="match_number",
            semantics=semantics
        )

    def parse_count_function(self, semantics=None):
        """Parse count() function with special handling for count(*) and count(var.*)"""
        self.in_aggregate = True
        self.expect('(')
        
        # Handle count(*)
        if self.peek() == '*':
            self.next_token()  # Consume '*'
            self.expect(')')
            self.in_aggregate = False
            return ExpressionAST(
                type="aggregate",
                value="count",
                count_star=True,
                children=[],
                semantics=semantics
            )
        
        # Handle count() with no arguments (same as count(*))
        if self.peek() == ')':
            self.next_token()  # Consume ')'
            self.in_aggregate = False
            return ExpressionAST(
                type="aggregate",
                value="count",
                count_star=True,
                children=[],
                semantics=semantics
            )
        
        # Handle count(var.*)
        if self.peek() and self.pos + 2 < len(self.tokens) and self.tokens[self.pos + 1] == '.' and self.tokens[self.pos + 2] == '*':
            pattern_var = self.next_token()
            self.next_token()  # Consume '.'
            self.next_token()  # Consume '*'
            self.expect(')')
            self.in_aggregate = False
            return ExpressionAST(
                type="aggregate",
                value="count",
                pattern_variable=pattern_var,
                count_star=True,
                children=[],
                semantics=semantics
            )
        
        # Handle regular count(expr)
        arg = self.parse_expression()
        self.expect(')')
        self.in_aggregate = False
        
        return ExpressionAST(
            type="aggregate",
            value="count",
            children=[arg],
            semantics=semantics
        )

    def parse_navigation_function(self, func_name, semantics=None):
        """Parse navigation functions with enhanced validation"""
        # Check if we're already inside an aggregate function
        if self.in_aggregate:
            raise ValueError(f"Navigation function {func_name} cannot be used inside aggregate functions")
            
        # Track nesting level for navigation functions
        self.nesting_level += 1
        self.in_navigation = True
        
        if self.nesting_level > self.MAX_NESTING:
            raise ValueError(f"Navigation function nesting too deep (max {self.MAX_NESTING} levels)")

        self.expect('(')
        
        # Parse the target expression
        target_expr = self.parse_expression()
        
        # Validate that the target expression contains at least one column reference
        if not self.contains_column_reference(target_expr):
            raise ValueError(f"Navigation function {func_name} requires at least one column reference")
        
        # Parse optional offset
        offset = 0
        if self.peek() == ',':
            self.next_token()  # Consume comma
            offset_expr = self.parse_expression()
            if offset_expr.type != "literal" or not str(offset_expr.value).isdigit():
                raise ValueError("Navigation offset must be a positive integer literal")
            offset = int(offset_expr.value)
            if offset < 0:
                raise ValueError("Navigation offset cannot be negative")

        self.expect(')')

        self.nesting_level -= 1
        self.in_navigation = False
        
        return ExpressionAST(
            type="navigation",
            navigation_type=func_name.upper(),
            children=[target_expr],
            offset=offset,
            semantics=semantics
        )

    def parse_function_call(self, func_name, semantics=None):
        """Parse regular or aggregate function calls"""
        is_aggregate = func_name.lower() in AGGREGATE_FUNCTIONS
        
        # Check for nested aggregates
        if is_aggregate and self.in_aggregate:
            raise ValueError(f"Nested aggregate functions are not allowed: {func_name}")
            
        if is_aggregate:
            self.in_aggregate = True
            
        self.expect('(')
        
        # Parse arguments
        arguments = []
        if self.peek() != ')':
            while True:
                arg = self.parse_expression()
                arguments.append(arg)
                if self.peek() == ',':
                    self.next_token()  # Consume comma
                else:
                    break
                    
        self.expect(')')
        
        # For aggregate functions, validate arguments
        if is_aggregate:
            self.validate_aggregate_arguments(arguments)
            self.in_aggregate = False
            
        return ExpressionAST(
            type="aggregate" if is_aggregate else "function",
            value=func_name,
            children=arguments,
            semantics=semantics
        )

    def validate_aggregate_arguments(self, arguments):
        """Validate that aggregate function arguments are consistent"""
        # Check that all arguments refer to the same pattern variable
        pattern_vars = set()
        for arg in arguments:
            if hasattr(arg, 'pattern_variable') and arg.pattern_variable:
                pattern_vars.add(arg.pattern_variable)
                
        if len(pattern_vars) > 1:
            raise ValueError("All arguments in an aggregate function must refer to the same pattern variable")
        
        # Check for navigation functions inside aggregate arguments
        for arg in arguments:
            if self.contains_navigation_function(arg):
                raise ValueError("Aggregate function arguments cannot contain navigation functions")

    def contains_column_reference(self, expr):
        """Check if an expression contains at least one column reference"""
        if expr.type in ["identifier", "pattern_variable_reference"]:
            return True
        for child in expr.children:
            if self.contains_column_reference(child):
                return True
        return False

    def contains_navigation_function(self, expr):
        """Check if an expression contains a navigation function"""
        if expr.type == "navigation":
            return True
        for child in expr.children:
            if self.contains_navigation_function(child):
                return True
        return False

    def is_function_ahead(self):
        """Check if the next tokens indicate a function call"""
        if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1] == '(':
            func_name = self.tokens[self.pos].upper()
            return func_name in NAVIGATION_FUNCTIONS or func_name.lower() in AGGREGATE_FUNCTIONS
        return False

    def is_decimal(self, token: str):
        """Check if a token represents a decimal number"""
        try:
            float(token)
            return True
        except ValueError:
            return False

def parse_expression(expr_text: str, in_measures_clause=True):
    """Parse an expression and return the AST"""
    parser = ExpressionParser(expr_text)
    parser.in_measures_clause = in_measures_clause
    return parser.parse()

def parse_expression_full(expr_text: str, in_measures_clause=True):
    """Parse an expression and return both raw text and AST"""
    parser = ExpressionParser(expr_text)
    parser.in_measures_clause = in_measures_clause
    ast = parser.parse()
    return {"raw": expr_text, "ast": ast}
