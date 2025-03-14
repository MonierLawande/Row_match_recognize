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
    """Cache for parsed expressions to avoid redundant parsing."""
    def __init__(self):
        self.cache = {}
    
    def get(self, expr_text: str, in_measures_clause: bool = True) -> Optional[Dict[str, Any]]:
        key = (expr_text, in_measures_clause)
        return self.cache.get(key)
        
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
        self.context = context if context else ParserContext(ErrorHandler())
        self.tokens: TokenStream = self._create_token_stream(expr_text)
        self.in_aggregate = False
        self.in_navigation = False

    def _create_token_stream(self, text: str) -> TokenStream:
        return Tokenizer.create_token_stream(text, self._determine_token_type)
        
    def _determine_token_type(self, token: str) -> str:
        if token in ['(', ')']:
            return 'PAREN'
        elif token == '?':
            return 'UNKNOWN'
        elif token in ['>=', '<=', '<>', '!=', '=', '>', '<', '+', '-', '*', '/']:
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
        if self.expr_text.strip() == "":
            self.context.error_handler.add_error("Empty expression", 0, 0)
            return ExpressionAST(type="error", value="Empty expression")
        try:
            result = self.parse_logical_expression()
            if not self.context.in_measures_clause and result.semantics and result.semantics.upper() == "FINAL":
                self.context.error_handler.add_error(
                    "FINAL semantics are not allowed outside of the MEASURES clause",
                    result.line, result.column_pos
                )
            if self.tokens.has_more:
                token = self.tokens.peek()
                if token.type == 'UNKNOWN':
                    self.context.error_handler.add_error(
                        f"Unexpected token '{token.value}'", token.line, token.column
                    )
                elif token.type != 'EOF':
                    self.context.error_handler.add_error(
                        f"Unexpected token '{token.value}' after expression",
                        token.line, token.column
                    )
            return result
        except Exception as e:
            if not self.context.error_handler.has_errors():
                self.context.error_handler.add_error(f"Error parsing expression: {str(e)}", 0, 0)
            return ExpressionAST(type="error", value=str(e))

    def parse_logical_expression(self) -> ExpressionAST:
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
        left = self.parse_unary()
        while self.tokens.has_more and self.tokens.peek().type == 'OPERATOR' and self.tokens.peek().value in ['*', '/']:
            op_token = self.tokens.consume()
            right = self.parse_unary()
            left = ExpressionAST(
                type="binary",
                operator=op_token.value,
                children=[left, right],
                line=op_token.line,
                column_pos=op_token.column
            )
        return left

    def parse_unary(self) -> ExpressionAST:
        if self.tokens.has_more and self.tokens.peek().type == 'OPERATOR' and self.tokens.peek().value == '-':
            op_token = self.tokens.consume()
            factor = self.parse_unary()
            zero_ast = ExpressionAST(
                type="literal",
                value="0",
                line=op_token.line,
                column_pos=op_token.column
            )
            return ExpressionAST(
                type="binary",
                operator='-',
                children=[zero_ast, factor],
                line=op_token.line,
                column_pos=op_token.column
            )
        else:
            return self.parse_primary()

    def parse_primary(self) -> ExpressionAST:
        # First, check for an unexpected token of type UNKNOWN.
        if self.tokens.has_more and self.tokens.peek().type == 'UNKNOWN':
            token = self.tokens.consume()
            self.context.error_handler.add_error(
                f"Unexpected token '{token.value}'", token.line, token.column
            )
            return ExpressionAST(type="error", value=f"Unexpected token '{token.value}'")

        semantics = None
        if self.tokens.has_more and self.tokens.peek().type == 'SEMANTICS':
            semantics_token = self.tokens.consume()
            semantics = semantics_token.value.upper()

        if self.tokens.has_more and self.tokens.peek().value == '(':
            paren_token = self.tokens.consume()
            expr = self.parse_logical_expression()
            self._expect(')', paren_token)
            return expr

        if self.tokens.has_more and self.tokens.peek().type in ['IDENTIFIER', 'AGGREGATE', 'NAVIGATION']:
            token = self.tokens.consume()
            if '(' in token.value and token.value != '(':
                parts = token.value.split('(', 1)
                token.value = parts[0]
                new_token = Token(value='(', type='PAREN', line=token.line, column=token.column + len(parts[0]))
                self.tokens.prepend(new_token)
            # If function call is expected, ensure '(' follows.
            if token.value.lower() in AGGREGATE_FUNCTIONS or token.value.upper() in NAVIGATION_FUNCTIONS or token.value.upper() in ['CLASSIFIER', 'MATCH_NUMBER']:
                if not (self.tokens.has_more and self.tokens.peek().type == 'PAREN' and self.tokens.peek().value == '('):
                    self.context.error_handler.add_error(
                        f"Function call '{token.value}' must be followed by '('",
                        token.line, token.column
                    )
                    return ExpressionAST(type="error", value=f"Missing '(' after {token.value}")
            if self.tokens.has_more and self.tokens.peek().value == '.':
                # Pattern variable reference.
                pattern_var = token.value
                if not self._is_valid_pattern_variable(pattern_var):
                    self.context.error_handler.add_warning(
                        f"Pattern variable '{pattern_var}' not defined in PATTERN clause",
                        token.line, token.column
                    )
                self.tokens.consume()  # Consume dot.
                if not self.tokens.has_more or self.tokens.peek().type == 'EOF':
                    self.context.error_handler.add_error(
                        f"Expected column name after '{pattern_var}.'",
                        token.line, token.column
                    )
                    return ExpressionAST(type="error", value=f"Missing column name after {pattern_var}.")
                column_token = self.tokens.consume()
                column = column_token.value
                full_ref = f"{pattern_var}.{column}"
                return ExpressionAST(
                    type="pattern_variable_reference",
                    value=full_ref,
                    pattern_variable=pattern_var,
                    column=column,
                    semantics=semantics,
                    line=token.line,
                    column_pos=token.column
                )
            else:
                if self.tokens.has_more and self.tokens.peek().type == 'PAREN' and self.tokens.peek().value == '(':
                    func_name = token.value
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
                else:
                    return ExpressionAST(
                        type="identifier",
                        value=token.value,
                        semantics=semantics,
                        line=token.line,
                        column_pos=token.column
                    )
        token = self.tokens.consume()
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

    # -------------------------
    # Function Call Helpers
    # -------------------------
    def _parse_classifier_function(self, semantics: Optional[str], token: Token) -> ExpressionAST:
        self._expect('(', token)
        pattern_var = None
        if self.tokens.has_more and self.tokens.peek().value != ')':
            var_token = self.tokens.consume()
            pattern_var = var_token.value
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
        self._expect('(', token)
        self._expect(')', token)
        return ExpressionAST(
            type="match_number",
            semantics=semantics,
            line=token.line,
            column_pos=token.column
        )

    def _parse_count_function(self, semantics: Optional[str], token: Token) -> ExpressionAST:
        self.in_aggregate = True
        self._expect('(', token)
        if self.tokens.has_more and self.tokens.peek().value == '*':
            self.tokens.consume()
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
        if self.tokens.has_more and self.tokens.peek().value == ')':
            self.tokens.consume()
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
        if (self.tokens.has_more and 
                self.tokens.peek(2) and 
                self.tokens.peek(3) and 
                self.tokens.peek(2).value == '.' and 
                self.tokens.peek(3).value == '*'):
            var_token = self.tokens.consume()
            pattern_var = var_token.value
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
        self.context.enter_scope()
        self.in_navigation = True
        self._expect('(', token)
        target_expr = self.parse_logical_expression()
        # Require that target_expr is a qualified column reference.
        if target_expr.type != "pattern_variable_reference":
            self.context.error_handler.add_error(
                f"Navigation function {func_name} requires at least one column reference",
                token.line, token.column
            )
        offset = 0
        if self.tokens.has_more and self.tokens.peek().value == ',':
            self.tokens.consume()
            marker = self.tokens.mark()
            offset_expr = self.parse_logical_expression()
            offset_val = self._eval_offset(offset_expr)
            if offset_val is None:
                self.context.error_handler.add_error(
                    "Navigation offset must be a positive integer literal",
                    token.line, token.column
                )
                self.tokens.reset(marker)
            else:
                if offset_val < 0:
                    self.context.error_handler.add_error(
                        "Navigation offset cannot be negative",
                        token.line, token.column
                    )
                else:
                    offset = offset_val
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

    def _eval_offset(self, expr: ExpressionAST) -> Optional[int]:
        if expr.type == "literal":
            try:
                return int(expr.value)
            except Exception:
                return None
        if expr.type == "binary" and expr.operator == '-' and len(expr.children) == 2:
            left, right = expr.children
            if left.type == "literal" and left.value == "0" and right.type == "literal":
                try:
                    return -int(right.value)
                except Exception:
                    return None
        return None

    def _parse_function_call(self, func_name: str, semantics: Optional[str], token: Token) -> ExpressionAST:
        is_aggregate = func_name.lower() in AGGREGATE_FUNCTIONS
        # Removed immediate nested aggregate check.
        self._expect('(', token)
        arguments = []
        if self.tokens.has_more and self.tokens.peek().value != ')':
            while True:
                arg = self.parse_logical_expression()
                arguments.append(arg)
                if not self.tokens.has_more or self.tokens.peek().value != ',':
                    break
                self.tokens.consume()
        self._expect(')', token)
        if is_aggregate:
            self._validate_aggregate_arguments(arguments, token)
        return ExpressionAST(
            type="aggregate" if is_aggregate else "function",
            value=func_name,
            children=arguments,
            semantics=semantics,
            line=token.line,
            column_pos=token.column
        )

    def _validate_aggregate_arguments(self, arguments: List[ExpressionAST], token: Token) -> None:
        """Validate that aggregate function arguments are consistent."""
        pattern_vars = set()
        for arg in arguments:
            if hasattr(arg, 'pattern_variable') and arg.pattern_variable:
                pattern_vars.add(arg.pattern_variable)
            if arg.type == "classifier":
                self.context.error_handler.add_error(
                    "Aggregate function arguments cannot contain classifier functions",
                    token.line, token.column
                )
        direct_refs = [arg.pattern_variable for arg in arguments if hasattr(arg, 'pattern_variable') and arg.pattern_variable]
        explicit_vars = {v for v in direct_refs if v != "universal"}
        if explicit_vars and len(explicit_vars) > 1:
            self.context.error_handler.add_error(
                "All direct arguments in an aggregate function must refer to the same pattern variable",
                token.line, token.column
            )
        if explicit_vars and len(explicit_vars) != len(direct_refs):
            self.context.error_handler.add_error(
                "Mixed explicit and universal aggregate arguments are not allowed",
                token.line, token.column
            )

    def _contains_column_reference(self, expr: ExpressionAST) -> bool:
        if expr.type in ["identifier", "pattern_variable_reference"]:
            return True
        for child in expr.children:
            if self._contains_column_reference(child):
                return True
        return False

    def _contains_navigation_function(self, expr: ExpressionAST) -> bool:
        if expr.type == "navigation":
            return True
        for child in expr.children:
            if self._contains_navigation_function(child):
                return True
        return False

    def _is_decimal(self, token: str) -> bool:
        try:
            float(token)
            return True
        except ValueError:
            return False
            
    def _is_valid_pattern_variable(self, variable: str) -> bool:
        if self.context.pattern_variables:
            return variable in self.context.pattern_variables
        if variable in self.context.subset_variables:
            return True
        return True
        
    def _expect(self, expected: str, context_token: Optional[Token]) -> None:
        if not self.tokens.has_more or self.tokens.peek().type == 'EOF':
            if context_token:
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
    if context is None:
        context = ParserContext(ErrorHandler())
    context.in_measures_clause = in_measures_clause
    parser = ExpressionParser(expr_text, context)
    return parser.parse()

def parse_expression_full(expr_text: str, in_measures_clause: bool = True, context: Optional[ParserContext] = None) -> Dict[str, Any]:
    cached = _expression_cache.get(expr_text, in_measures_clause)
    if cached:
        return cached
    
    if context is None:
        from src.parser.error_handler import ErrorHandler
        from src.parser.context import ParserContext
        context = ParserContext(ErrorHandler())
    context.in_measures_clause = in_measures_clause
    
    parser = ExpressionParser(expr_text, context)
    ast = parser.parse()
    
    from .semantic_analyzer import SemanticAnalyzer  # Avoid circular imports
    analyzer = SemanticAnalyzer(context.error_handler)
    analyzer.analyze_expression(ast, "expression")
    
    result = {
        "raw": expr_text,
        "ast": ast,
        "errors": context.error_handler.get_formatted_errors(),
        "warnings": context.error_handler.get_formatted_warnings(),
        "symbol_table": analyzer.symbol_table
    }
    
    _expression_cache.put(expr_text, result, in_measures_clause)
    return result
