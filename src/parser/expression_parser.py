# src/parser/expression_parser.py

import re
from typing import List, Dict, Any, Optional, Set
from src.ast.expression_ast import ExpressionAST
from .token_stream import Token, TokenStream
from .error_handler import ErrorHandler
from .context import ParserContext
from .tokenizer import Tokenizer

# Define constants for better code readability
AGGREGATE_FUNCTIONS = ['avg', 'min', 'max', 'count', 'sum', 'max_by', 'min_by', 'array_agg']
NAVIGATION_FUNCTIONS = ['PREV', 'NEXT', 'FIRST', 'LAST']
SEMANTICS_KEYWORDS = ['RUNNING', 'FINAL']
ALLOWED_FINAL_FUNCTIONS = NAVIGATION_FUNCTIONS + AGGREGATE_FUNCTIONS

class ExpressionCache:
    """Cache for parsed expressions to avoid redundant parsing"""
    def __init__(self):
        self.cache = {}
    
    def get(self, expr_text: str, in_measures_clause: bool = True) -> Optional[Dict[str, Any]]:
        key = (expr_text, in_measures_clause)
        if key in self.cache:
            return self.cache[key]
        return None
        
    def put(self, expr_text: str, result: Dict[str, Any], in_measures_clause: bool = True) -> None:
        key = (expr_text, in_measures_clause)
        self.cache[key] = result

# Singleton cache instance
_expression_cache = ExpressionCache()

class ExpressionParser:
    """
    A recursive descent parser for SQL expressions in MATCH_RECOGNIZE context.
    """
    def __init__(self, expr_text: str, context: Optional[ParserContext] = None):
        self.expr_text = expr_text
        
        # Use provided context or create a new one
        if context:
            self.context = context
        else:
            self.context = ParserContext(ErrorHandler())
            
        # Create token stream
        self.tokens = self._create_token_stream(expr_text)
            
        # State tracking
        self.in_aggregate = False
        self.in_navigation = False

    def _create_token_stream(self, text: str) -> TokenStream:
        return Tokenizer.create_token_stream(text, self._determine_token_type)
        
    def _determine_token_type(self, token: str) -> str:
        """Determine the type of a token"""
        if token in ['(', ')']:
            return 'PAREN'
        elif token in ['+', '-', '*', '/', '>', '<', '=', '>=', '<=', '!=', '<>']:
            return 'OPERATOR'
        elif token.upper() in ['AND', 'OR']:
            return 'LOGICAL'
        elif token == ',':
            return 'COMMA'
        elif token == '.':
            return 'DOT'
        elif token.upper() in SEMANTICS_KEYWORDS:
            return 'SEMANTICS'
        elif token.upper() in NAVIGATION_FUNCTIONS:
            return 'NAVIGATION'
        elif token.lower() in AGGREGATE_FUNCTIONS:
            return 'AGGREGATE'
        elif token.isdigit() or self._is_decimal(token):
            return 'LITERAL'
        else:
            return 'IDENTIFIER'

    def parse(self) -> ExpressionAST:
        """Parse the expression and return the AST"""
        try:
            result = self.parse_logical_expression()
            
            # Check for unexpected tokens
            if self.tokens.has_more and self.tokens.peek().type != 'EOF':
                token = self.tokens.peek()
                self.context.error_handler.add_error(
                    f"Unexpected token '{token.value}' after expression",
                    token.line, token.column
                )
                
            return result
        except Exception as e:
            # Add error to error handler if not already added
            if not self.context.error_handler.has_errors():
                self.context.error_handler.add_error(
                    f"Error parsing expression: {str(e)}",
                    0, 0
                )
            # Return a minimal valid AST to allow processing to continue
            return ExpressionAST(type="error", value=str(e))

    def parse_logical_expression(self) -> ExpressionAST:
        """Parse logical operators (AND, OR)"""
        left = self.parse_comparison()
        
        while self.tokens.has_more and self.tokens.peek().type == 'LOGICAL':
            op_token = self.tokens.consume()
            right = self.parse_comparison()
            left = ExpressionAST(
                type="binary", 
                operator=op_token.value.upper(), 
                children=[left, right],
                line=op_token.line,
                column_pos=op_token.column
            )
            
        return left

    def parse_comparison(self) -> ExpressionAST:
        """Parse comparison operators (>, <, =, etc.)"""
        left = self.parse_additive_expression()
        
        if self.tokens.has_more and self.tokens.peek().type == 'OPERATOR' and self.tokens.peek().value in ['>', '<', '=', '>=', '<=', '!=', '<>']:
            op_token = self.tokens.consume()
            right = self.parse_additive_expression()
            left = ExpressionAST(
                type="binary", 
                operator=op_token.value, 
                children=[left, right],
                line=op_token.line,
                column_pos=op_token.column
            )
            
        return left

    def parse_additive_expression(self) -> ExpressionAST:
        """Parse an expression supporting binary operators + and -"""
        left = self.parse_term()
        
        while self.tokens.has_more and self.tokens.peek().type == 'OPERATOR' and self.tokens.peek().value in ['+', '-']:
            op_token = self.tokens.consume()
            right = self.parse_term()
            left = ExpressionAST(
                type="binary", 
                operator=op_token.value, 
                children=[left, right],
                line=op_token.line,
                column_pos=op_token.column
            )
            
        return left

    def parse_term(self) -> ExpressionAST:
        """Parse multiplication/division"""
        left = self.parse_factor()
        
        while self.tokens.has_more and self.tokens.peek().type == 'OPERATOR' and self.tokens.peek().value in ['*', '/']:
            op_token = self.tokens.consume()
            right = self.parse_factor()
            left = ExpressionAST(
                type="binary", 
                operator=op_token.value, 
                children=[left, right],
                line=op_token.line,
                column_pos=op_token.column
            )
            
        return left

    def parse_factor(self) -> ExpressionAST:
        """Parse a factor (primary expression)"""
        return self.parse_primary()

    def parse_primary(self) -> ExpressionAST:
        """Parse a primary expression with enhanced error handling."""
        # Check for semantics keyword
        semantics = None
        if self.tokens.has_more and self.tokens.peek().type == 'SEMANTICS':
            semantics_token = self.tokens.consume()
            semantics = semantics_token.value.upper()

        # Handle parenthesized expressions
        if self.tokens.has_more and self.tokens.peek().value == '(':
            paren_token = self.tokens.consume()
            expr = self.parse_logical_expression()
            self._expect(')', paren_token)
            return expr

        # Handle function calls or identifiers
        if not self.tokens.has_more or self.tokens.peek().type == 'EOF':
            self.context.error_handler.add_error(
                "Unexpected end of expression",
                0, 0
            )
            return ExpressionAST(type="error", value="Unexpected end of expression")

        token = self.tokens.consume()

        # Check for pattern variable reference (e.g., A.column)
        if self.tokens.has_more and self.tokens.peek().value == '.':
            pattern_var = token.value
            
            # Validate pattern variable
            if not self._is_valid_pattern_variable(pattern_var):
                self.context.error_handler.add_warning(
                    f"Pattern variable '{pattern_var}' not defined in PATTERN clause",
                    token.line, token.column
                )
                
            self.tokens.consume()  # Consume '.'
            
            if not self.tokens.has_more or self.tokens.peek().type == 'EOF':
                self.context.error_handler.add_error(
                    f"Expected column name after '{pattern_var}.'",
                    token.line, token.column
                )
                return ExpressionAST(type="error", value=f"Missing column name after {pattern_var}.")
                
            column_token = self.tokens.consume()
            column = column_token.value
            
            return ExpressionAST(
                type="pattern_variable_reference",
                pattern_variable=pattern_var,
                column=column,
                semantics=semantics,
                line=token.line,
                column_pos=token.column
            )

        # Handle function calls
        if self.tokens.has_more and self.tokens.peek().value == '(':
            func_name = token.value
            
            # Special handling for specific functions
            if func_name.upper() == 'CLASSIFIER':
                return self._parse_classifier_function(semantics, token)
            elif func_name.upper() == 'MATCH_NUMBER':
                return self._parse_match_number_function(semantics, token)
            elif func_name.lower() == 'count':
                return self._parse_count_function(semantics, token)
            elif func_name.upper() in NAVIGATION_FUNCTIONS:
                return self._parse_navigation_function(func_name, semantics, token)
            else:
                return self._parse_function_call(func_name, semantics, token)

        # Handle literals and identifiers
        if token.type == 'LITERAL':
            return ExpressionAST(
                type="literal", 
                value=token.value, 
                semantics=semantics,
                line=token.line,
                column_pos=token.column
            )
        else:
            return ExpressionAST(
                type="identifier", 
                value=token.value, 
                semantics=semantics,
                line=token.line,
                column_pos=token.column
            )

    # Rest of the methods remain the same...
    def _parse_classifier_function(self, semantics: Optional[str], token: Token) -> ExpressionAST:
        """Parse CLASSIFIER() function with optional pattern variable argument"""
        self._expect('(', token)
        
        pattern_var = None
        if self.tokens.has_more and self.tokens.peek().value != ')':
            var_token = self.tokens.consume()
            pattern_var = var_token.value
            
            # Validate pattern variable
            if not self._is_valid_pattern_variable(pattern_var):
                self.context.error_handler.add_warning(
                    f"Pattern variable '{pattern_var}' in CLASSIFIER() not defined in PATTERN clause",
                    var_token.line, var_token.column
                )
                
        self._expect(')', token)
        
        return ExpressionAST(
            type="classifier",
            pattern_variable=pattern_var,
            semantics=semantics,
            line=token.line,
            column_pos=token.column
        )
        
    def _parse_match_number_function(self, semantics: Optional[str], token: Token) -> ExpressionAST:
        """Parse MATCH_NUMBER() function"""
        self._expect('(', token)
        self._expect(')', token)
        
        return ExpressionAST(
            type="match_number",
            semantics=semantics,
            line=token.line,
            column_pos=token.column
        )

    def _parse_count_function(self, semantics: Optional[str], token: Token) -> ExpressionAST:
        """Parse count() function with special handling for count(*) and count(var.*)"""
        self.in_aggregate = True
        self._expect('(', token)
        
        # Handle count(*)
        if self.tokens.has_more and self.tokens.peek().value == '*':
            self.tokens.consume()  # Consume '*'
            self._expect(')', token)
            self.in_aggregate = False
            return ExpressionAST(
                type="aggregate",
                value="count",
                count_star=True,
                children=[],
                semantics=semantics,
                line=token.line,
                column_pos=token.column
            )
        
        # Handle count() with no arguments (same as count(*))
        if self.tokens.has_more and self.tokens.peek().value == ')':
            self.tokens.consume()  # Consume ')'
            self.in_aggregate = False
            return ExpressionAST(
                type="aggregate",
                value="count",
                count_star=True,
                children=[],
                semantics=semantics,
                line=token.line,
                column_pos=token.column
            )
        
        # Handle count(var.*)
        if (self.tokens.has_more and 
                self.tokens.peek(2) and 
                self.tokens.peek(3) and 
                self.tokens.peek(2).value == '.' and 
                self.tokens.peek(3).value == '*'):
            
            var_token = self.tokens.consume()
            pattern_var = var_token.value
            
            # Validate pattern variable
            if not self._is_valid_pattern_variable(pattern_var):
                self.context.error_handler.add_warning(
                    f"Pattern variable '{pattern_var}' in count({pattern_var}.*) not defined in PATTERN clause",
                    var_token.line, var_token.column
                )
                
            self.tokens.consume()  # Consume '.'
            self.tokens.consume()  # Consume '*'
            self._expect(')', token)
            self.in_aggregate = False
            
            return ExpressionAST(
                type="aggregate",
                value="count",
                pattern_variable=pattern_var,
                count_star=True,
                children=[],
                semantics=semantics,
                line=token.line,
                column_pos=token.column
            )
        
        # Handle regular count(expr)
        arg = self.parse_logical_expression()
        self._expect(')', token)
        self.in_aggregate = False
        
        return ExpressionAST(
            type="aggregate",
            value="count",
            children=[arg],
            semantics=semantics,
            line=token.line,
            column_pos=token.column
        )

    def _parse_navigation_function(self, func_name: str, semantics: Optional[str], token: Token) -> ExpressionAST:
        """Parse navigation functions with enhanced validation"""
        # Check if we're already inside an aggregate function
        if self.in_aggregate:
            self.context.error_handler.add_error(
                f"Navigation function {func_name} cannot be used inside aggregate functions",
                token.line, token.column
            )
            
        # Track nesting level for navigation functions
        self.context.enter_scope()
        self.in_navigation = True

        self._expect('(', token)
        
        # Parse the target expression
        target_expr = self.parse_logical_expression()
        
        # Validate that the target expression contains at least one column reference
        if not self._contains_column_reference(target_expr):
            self.context.error_handler.add_error(
                f"Navigation function {func_name} requires at least one column reference",
                token.line, token.column
            )
        
        # Parse optional offset
        offset = 0
        if self.tokens.has_more and self.tokens.peek().value == ',':
            self.tokens.consume()  # Consume comma
            
            # Mark position for potential backtracking
            marker = self.tokens.mark()
            
            offset_expr = self.parse_logical_expression()
            if offset_expr.type != "literal" or not str(offset_expr.value).isdigit():
                self.context.error_handler.add_error(
                    "Navigation offset must be a positive integer literal",
                    token.line, token.column
                )
                # Reset to before the offset expression
                self.tokens.reset(marker)
            else:
                offset = int(offset_expr.value)
                if offset < 0:
                    self.context.error_handler.add_error(
                        "Navigation offset cannot be negative",
                        token.line, token.column
                    )
                    offset = 0

        self._expect(')', token)

        self.context.exit_scope()
        self.in_navigation = False
        
        return ExpressionAST(
            type="navigation",
            navigation_type=func_name.upper(),
            children=[target_expr],
            offset=offset,
            semantics=semantics,
            line=token.line,
            column_pos=token.column
        )

    def _parse_function_call(self, func_name: str, semantics: Optional[str], token: Token) -> ExpressionAST:
        """Parse regular or aggregate function calls"""
        is_aggregate = func_name.lower() in AGGREGATE_FUNCTIONS
        
        # Check for nested aggregates
        if is_aggregate and self.in_aggregate:
            self.context.error_handler.add_error(
                f"Nested aggregate functions are not allowed: {func_name}",
                token.line, token.column
            )
            
        if is_aggregate:
            self.in_aggregate = True
            
        self._expect('(', token)
        
        # Parse arguments
        arguments = []
        if self.tokens.has_more and self.tokens.peek().value != ')':
            while True:
                arg = self.parse_logical_expression()
                arguments.append(arg)
                
                if not self.tokens.has_more or self.tokens.peek().value != ',':
                    break
                    
                self.tokens.consume()  # Consume comma
                    
        self._expect(')', token)
        
        # For aggregate functions, validate arguments
        if is_aggregate:
            self._validate_aggregate_arguments(arguments, token)
            self.in_aggregate = False
            
        return ExpressionAST(
            type="aggregate" if is_aggregate else "function",
            value=func_name,
            children=arguments,
            semantics=semantics,
            line=token.line,
            column_pos=token.column
        )

    def _validate_aggregate_arguments(self, arguments: List[ExpressionAST], token: Token) -> None:
        """Validate that aggregate function arguments are consistent"""
        # Check that all arguments refer to the same pattern variable
        pattern_vars = set()
        for arg in arguments:
            if hasattr(arg, 'pattern_variable') and arg.pattern_variable:
                pattern_vars.add(arg.pattern_variable)
                
        if len(pattern_vars) > 1:
            self.context.error_handler.add_error(
                "All arguments in an aggregate function must refer to the same pattern variable",
                token.line, token.column
            )
        
        # Check for navigation functions inside aggregate arguments
        for arg in arguments:
            if self._contains_navigation_function(arg):
                self.context.error_handler.add_error(
                    "Aggregate function arguments cannot contain navigation functions",
                    token.line, token.column
                )

    def _contains_column_reference(self, expr: ExpressionAST) -> bool:
        """Check if an expression contains at least one column reference"""
        if expr.type in ["identifier", "pattern_variable_reference"]:
            return True
        for child in expr.children:
            if self._contains_column_reference(child):
                return True
        return False

    def _contains_navigation_function(self, expr: ExpressionAST) -> bool:
        """Check if an expression contains a navigation function"""
        if expr.type == "navigation":
            return True
        for child in expr.children:
            if self._contains_navigation_function(child):
                return True
        return False

    def _is_decimal(self, token: str) -> bool:
        """Check if a token represents a decimal number"""
        try:
            float(token)
            return True
        except ValueError:
            return False
            
    def _is_valid_pattern_variable(self, variable: str) -> bool:
        """Check if a pattern variable is valid"""
        # If we have pattern variables in context, check against them
        if self.context.pattern_variables:
            return variable in self.context.pattern_variables
            
        # If we have subset variables in context, check against them
        if variable in self.context.subset_variables:
            return True
            
        # If we don't have pattern variables yet, assume it's valid
        return True
        
    def _expect(self, expected: str, context_token: Token) -> None:
        """Consume next token and verify it matches expected_token"""
        if not self.tokens.has_more or self.tokens.peek().type == 'EOF':
            self.context.error_handler.add_error(
                f"Expected '{expected}', got end of expression",
                context_token.line, context_token.column
            )
            return
            
        token = self.tokens.consume()
        if token.value != expected:
            self.context.error_handler.add_error(
                f"Expected '{expected}', got '{token.value}'",
                token.line, token.column
            )

def parse_expression(expr_text: str, in_measures_clause: bool = True, context: Optional[ParserContext] = None) -> ExpressionAST:
    """Parse an expression and return the AST"""
    if context is None:
        context = ParserContext(ErrorHandler())
    context.in_measures_clause = in_measures_clause
    
    parser = ExpressionParser(expr_text, context)
    return parser.parse()

def parse_expression_full(expr_text: str, in_measures_clause: bool = True, context: Optional[ParserContext] = None) -> Dict[str, Any]:
    """Parse an expression and return both raw text and AST with caching"""
    # Check cache first
    cached = _expression_cache.get(expr_text, in_measures_clause)
    if cached:
        return cached
    
    if context is None:
        context = ParserContext(ErrorHandler())
    context.in_measures_clause = in_measures_clause
    
    parser = ExpressionParser(expr_text, context)
    ast = parser.parse()
    
    # Perform semantic analysis
    from .semantic_analyzer import SemanticAnalyzer  # Import here to avoid circular imports
    analyzer = SemanticAnalyzer(context.error_handler)
    analyzer.analyze_expression(ast, "expression")
    
    result = {
        "raw": expr_text,
        "ast": ast,
        "errors": context.error_handler.get_formatted_errors(),
        "warnings": context.error_handler.get_formatted_warnings(),
        "symbol_table": analyzer.symbol_table  # Include symbol table in result
    }
    
    # Store in cache
    _expression_cache.put(expr_text, result, in_measures_clause)
    return result
