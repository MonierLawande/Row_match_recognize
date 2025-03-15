# src/parser/expression_parser.py

import re
import logging
from typing import List, Dict, Any, Optional, Set
from .parse_tree import ParseTreeNode
from .tokenizer import Tokenizer, Token, TokenStream
from .parser_util import ErrorHandler, ParserContext

# Constants for token categorization.
AGGREGATE_FUNCTIONS = ['avg', 'min', 'max', 'count', 'sum', 'max_by', 'min_by', 'array_agg']
NAVIGATION_FUNCTIONS = ['PREV', 'NEXT', 'FIRST', 'LAST']
SEMANTICS_KEYWORDS = ['RUNNING', 'FINAL']

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Adjust as needed or drive from a config flag.

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

_expression_cache = ExpressionCache()

class ExpressionParser:
    """
    A recursive descent parser for SQL expressions in MATCH_RECOGNIZE context.
    Produces a parse tree and includes enhancements for error recovery,
    detailed logging, and caching.
    """
    def __init__(self, expr_text: str, context: Optional[ParserContext] = None):
        self.expr_text = expr_text
        self.context = context if context else ParserContext(ErrorHandler())
        self.tokens: TokenStream = Tokenizer.create_token_stream(expr_text, self._determine_token_type)
        self.in_aggregate = False
        self.in_navigation = False
        self.subexpr_cache = {}
    
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
            # If token is not purely alphanumeric, classify as UNKNOWN.
            if not token.isalnum():
                return 'UNKNOWN'
            return 'IDENTIFIER'
    
    def _is_decimal(self, token: str) -> bool:
        try:
            float(token)
            return True
        except ValueError:
            return False
    
    def recover(self, sync_tokens: List[str]):
        """Skip tokens until one of the sync_tokens is encountered."""
        logger.debug("Recovering from error; sync tokens: %s", sync_tokens)
        while self.tokens.has_more:
            token = self.tokens.peek()
            if token.value in sync_tokens:
                logger.debug("Found sync token: %s", token.value)
                return
            self.tokens.consume()
    
    def get_context(self, lookaround: int = 3) -> str:
        """Return a string with up to 'lookaround' tokens for context."""
        tokens = []
        for i in range(1, lookaround + 1):
            token = self.tokens.peek(i)
            if token:
                tokens.append(token.value)
        return " ".join(tokens)
    
    def parse(self) -> ParseTreeNode:
        if self.expr_text.strip() == "":
            self.context.error_handler.add_error("Empty expression", 0, 0)
            return ParseTreeNode("error", token={"value": "Empty expression"})
        try:
            logger.debug("Starting parse for: %s", self.expr_text)
            result = self.parse_logical_expression()
            if not self.context.in_measures_clause and result.token and result.token.get("semantics", "").upper() == "FINAL":
                self.context.error_handler.add_error(
                    "FINAL semantics are not allowed outside of the MEASURES clause",
                    result.token.get("line", 0),
                    result.token.get("column", 0)
                )
            if self.tokens.has_more:
                token = self.tokens.peek()
                if token.type != 'EOF':
                    self.context.error_handler.add_error(
                        f"Unexpected token '{token.value}' after expression",
                        token.line, token.column
                    )
            logger.debug("Completed parse: %s", result)
            return result
        except Exception as e:
            if not self.context.error_handler.has_errors():
                self.context.error_handler.add_error(f"Error parsing expression: {str(e)}", 0, 0)
            return ParseTreeNode("error", token={"value": str(e)})
    
    def parse_logical_expression(self) -> ParseTreeNode:
        left = self.parse_comparison()
        while self.tokens.has_more and self.tokens.peek().type == 'LOGICAL':
            op_token = self.tokens.consume()
            right = self.parse_comparison()
            left = ParseTreeNode(
                "binary",
                token={"operator": op_token.value.upper(), "line": op_token.line, "column": op_token.column},
                children=[left, right]
            )
            logger.debug("Parsed logical expression: %s", left)
        return left
    
    def parse_comparison(self) -> ParseTreeNode:
        left = self.parse_additive_expression()
        if self.tokens.has_more and self.tokens.peek().type == 'OPERATOR' and self.tokens.peek().value in ['>', '<', '=', '>=', '<=', '!=', '<>']:
            op_token = self.tokens.consume()
            right = self.parse_additive_expression()
            left = ParseTreeNode(
                "binary",
                token={"operator": op_token.value, "line": op_token.line, "column": op_token.column},
                children=[left, right]
            )
            logger.debug("Parsed comparison: %s", left)
        return left
    
    def parse_additive_expression(self) -> ParseTreeNode:
        pos = self.tokens.position
        if pos in self.subexpr_cache:
            logger.debug("Using cached additive expression at pos %s", pos)
            return self.subexpr_cache[pos]
        left = self.parse_term()
        while self.tokens.has_more and self.tokens.peek().type == 'OPERATOR' and self.tokens.peek().value in ['+', '-']:
            op_token = self.tokens.consume()
            right = self.parse_term()
            left = ParseTreeNode(
                "binary",
                token={"operator": op_token.value, "line": op_token.line, "column": op_token.column},
                children=[left, right]
            )
            logger.debug("Parsed additive expression: %s", left)
        self.subexpr_cache[pos] = left
        return left
    
    def parse_term(self) -> ParseTreeNode:
        left = self.parse_unary()
        while self.tokens.has_more and self.tokens.peek().type == 'OPERATOR' and self.tokens.peek().value in ['*', '/']:
            op_token = self.tokens.consume()
            right = self.parse_unary()
            left = ParseTreeNode(
                "binary",
                token={"operator": op_token.value, "line": op_token.line, "column": op_token.column},
                children=[left, right]
            )
            logger.debug("Parsed term: %s", left)
        return left
    
    def parse_unary(self) -> ParseTreeNode:
        if self.tokens.has_more and self.tokens.peek().type == 'OPERATOR' and self.tokens.peek().value == '-':
            op_token = self.tokens.consume()
            factor = self.parse_unary()
            zero_node = ParseTreeNode(
                "literal",
                token={"value": "0", "line": op_token.line, "column": op_token.column}
            )
            node = ParseTreeNode(
                "binary",
                token={"operator": "-", "line": op_token.line, "column": op_token.column},
                children=[zero_node, factor]
            )
            logger.debug("Parsed unary minus: %s", node)
            return node
        else:
            return self.parse_primary()
    
    def parse_primary(self) -> ParseTreeNode:
        if self.tokens.has_more and self.tokens.peek().type == 'UNKNOWN':
            token = self.tokens.consume()
            context_str = self.get_context()
            self.context.error_handler.add_error(
                f"Unexpected token '{token.value}'. Context: {context_str}",
                token.line, token.column
            )
            self.recover(sync_tokens=[',', ')', ';'])
            return ParseTreeNode("error", token={"value": token.value})
        
        semantics = None
        if self.tokens.has_more and self.tokens.peek().type == 'SEMANTICS':
            semantics_token = self.tokens.consume()
            semantics = semantics_token.value.upper()
        
        if self.tokens.has_more and self.tokens.peek().value == '(':
            paren_token = self.tokens.consume()
            self.context.enter_scope()
            expr = self.parse_logical_expression()
            self.context.exit_scope()
            self._expect(')', paren_token)
            if semantics:
                if expr.token is None:
                    expr.token = {}
                expr.token["semantics"] = semantics
            logger.debug("Parsed parenthesized expression: %s", expr)
            return expr
        
        if self.tokens.has_more and self.tokens.peek().type in ['IDENTIFIER', 'AGGREGATE', 'NAVIGATION']:
            token = self.tokens.consume()
            if '(' in token.value and token.value != '(':
                parts = token.value.split('(', 1)
                token.value = parts[0]
                new_token = Token(value='(', type='PAREN', line=token.line, column=token.column + len(parts[0]))
                self.tokens.prepend(new_token)
            if token.value.lower() in AGGREGATE_FUNCTIONS or token.value.upper() in NAVIGATION_FUNCTIONS or token.value.upper() in ['CLASSIFIER', 'MATCH_NUMBER']:
                if not (self.tokens.has_more and self.tokens.peek().type == 'PAREN' and self.tokens.peek().value == '('):
                    self.context.error_handler.add_error(
                        f"Function call '{token.value}' must be followed by '('",
                        token.line, token.column
                    )
                    return ParseTreeNode("error", token={"value": f"Missing '(' after {token.value}"})
            if self.tokens.has_more and self.tokens.peek().value == '.':
                pattern_var = token.value
                self.tokens.consume()  # Consume the dot.
                if not self.tokens.has_more or self.tokens.peek().type == 'EOF':
                    self.context.error_handler.add_error(
                        f"Expected column name after '{pattern_var}.'",
                        token.line, token.column
                    )
                    return ParseTreeNode("error", token={"value": f"Missing column name after {pattern_var}."})
                column_token = self.tokens.consume()
                full_ref = f"{pattern_var}.{column_token.value}"
                node = ParseTreeNode("pattern_variable_reference", token={"value": full_ref, "line": token.line, "column": token.column, "semantics": semantics}, children=[])
                logger.debug("Parsed pattern variable reference: %s", node)
                return node
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
                    node = ParseTreeNode("identifier", token={"value": token.value, "line": token.line, "column": token.column, "semantics": semantics}, children=[])
                    logger.debug("Parsed identifier: %s", node)
                    return node
        token = self.tokens.consume()
        if token.type == 'LITERAL':
            node = ParseTreeNode("literal", token={"value": token.value, "line": token.line, "column": token.column, "semantics": semantics}, children=[])
            logger.debug("Parsed literal: %s", node)
            return node
        else:
            node = ParseTreeNode("identifier", token={"value": token.value, "line": token.line, "column": token.column, "semantics": semantics}, children=[])
            logger.debug("Parsed identifier (fallback): %s", node)
            return node
    
    def _parse_classifier_function(self, semantics: Optional[str], token: Token) -> ParseTreeNode:
        self._expect('(', token)
        pattern_var = None
        if self.tokens.has_more and self.tokens.peek().value != ')':
            var_token = self.tokens.consume()
            pattern_var = var_token.value
        self._expect(')', token)
        node = ParseTreeNode("classifier", token={"value": token.value, "line": token.line, "column": token.column, "semantics": semantics, "pattern_variable": pattern_var}, children=[])
        logger.debug("Parsed classifier function: %s", node)
        return node
        
    def _parse_match_number_function(self, semantics: Optional[str], token: Token) -> ParseTreeNode:
        self._expect('(', token)
        self._expect(')', token)
        node = ParseTreeNode("match_number", token={"value": token.value, "line": token.line, "column": token.column, "semantics": semantics}, children=[])
        logger.debug("Parsed match_number function: %s", node)
        return node
    
    def _parse_count_function(self, semantics: Optional[str], token: Token) -> ParseTreeNode:
        self.in_aggregate = True
        self._expect('(', token)
        if self.tokens.has_more and self.tokens.peek().value == '*':
            self.tokens.consume()
            self._expect(')', token)
            self.in_aggregate = False
            node = ParseTreeNode("aggregate", token={"value": "count", "line": token.line, "column": token.column, "semantics": semantics, "count_star": True}, children=[])
            logger.debug("Parsed count(*) function: %s", node)
            return node
        if self.tokens.has_more and self.tokens.peek().value == ')':
            self.tokens.consume()
            self.in_aggregate = False
            node = ParseTreeNode("aggregate", token={"value": "count", "line": token.line, "column": token.column, "semantics": semantics, "count_star": True}, children=[])
            logger.debug("Parsed count() function: %s", node)
            return node
        if (self.tokens.has_more and 
                self.tokens.peek(2) and 
                self.tokens.peek(3) and 
                self.tokens.peek(2).value == '.' and 
                self.tokens.peek(3).value == '*'):
            var_token = self.tokens.consume()
            pattern_var = var_token.value
            self.tokens.consume()  # Consume '.'
            self.tokens.consume()  # Consume '*'
            self._expect(')', token)
            self.in_aggregate = False
            node = ParseTreeNode("aggregate", token={"value": "count", "line": token.line, "column": token.column, "semantics": semantics, "pattern_variable": pattern_var, "count_star": True}, children=[])
            logger.debug("Parsed count(pattern.*) function: %s", node)
            return node
        arg = self.parse_logical_expression()
        self._expect(')', token)
        self.in_aggregate = False
        node = ParseTreeNode("aggregate", token={"value": "count", "line": token.line, "column": token.column, "semantics": semantics}, children=[arg])
        logger.debug("Parsed count() function with argument: %s", node)
        return node
    
    def _parse_navigation_function(self, func_name: str, semantics: Optional[str], token: Token) -> ParseTreeNode:
        self.context.enter_scope()
        self.in_navigation = True
        self._expect('(', token)
        target_expr = self.parse_logical_expression()
        if target_expr.node_type != "pattern_variable_reference":
            self.context.error_handler.add_error(
                f"Navigation function {func_name} requires at least one column reference",
                token.line, token.column
            )
        offset = 0
        if self.tokens.has_more and self.tokens.peek().value == ',':
            self.tokens.consume()
            marker = self.tokens.mark()
            offset_expr = self.parse_logical_expression()
            try:
                offset_val = int(offset_expr.token.get("value", "0"))
            except Exception:
                offset_val = None
            if offset_val is None or offset_val < 0:
                self.context.error_handler.add_error(
                    "Navigation offset must be a positive integer literal",
                    token.line, token.column
                )
                self.tokens.reset(marker)
            else:
                offset = offset_val
        self._expect(')', token)
        self.context.exit_scope()
        self.in_navigation = False
        node = ParseTreeNode("navigation", token={"navigation_type": func_name.upper(), "line": token.line, "column": token.column, "semantics": semantics, "offset": offset}, children=[target_expr])
        logger.debug("Parsed navigation function: %s", node)
        return node
    
    def _parse_function_call(self, func_name: str, semantics: Optional[str], token: Token) -> ParseTreeNode:
        is_aggregate = func_name.lower() in AGGREGATE_FUNCTIONS
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
            pass  # Optionally validate aggregate arguments.
        node = ParseTreeNode("aggregate" if is_aggregate else "function", token={"value": func_name, "line": token.line, "column": token.column, "semantics": semantics}, children=arguments)
        logger.debug("Parsed function call: %s", node)
        return node
    
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

def parse_expression(expr_text: str, in_measures_clause: bool = True, context: Optional[ParserContext] = None) -> ParseTreeNode:
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
        context = ParserContext(ErrorHandler())
    context.in_measures_clause = in_measures_clause
    parser = ExpressionParser(expr_text, context)
    parse_tree = parser.parse()
    result = {
        "raw": expr_text,
        "parse_tree": parse_tree,
        "errors": context.error_handler.get_formatted_errors(),
        "warnings": []  # You can similarly add warnings if desired.
    }
    _expression_cache.put(expr_text, result, in_measures_clause)
    return result
