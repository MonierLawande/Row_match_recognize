# src/ast/ast_builder.py

import logging
from typing import Dict, Any, List, Tuple, Optional, Set
from antlr4 import InputStream, CommonTokenStream
from src.grammar.TrinoLexer import TrinoLexer
from src.grammar.TrinoParser import TrinoParser
from src.grammar.TrinoParserVisitor import TrinoParserVisitor
from src.ast.match_recognize_ast import MatchRecognizeAST
from src.ast.pattern_ast import PatternAST
from src.ast.expression_ast import ExpressionAST
from src.parser.error_handler import ErrorHandler
from src.parser.symbol_table import SymbolTable
from src.parser.tokenizer import Tokenizer
from src.parser.expression_parser import parse_expression
from src.parser.pattern_parser import parse_pattern, parse_pattern_full
from src.parser.context import ParserContext

logger = logging.getLogger(__name__)

class ASTBuilder:
    """
    Builds an Abstract Syntax Tree (AST) from a parse tree.
    
    This class transforms the parse tree produced by the parser into a structured
    AST that can be more easily analyzed, validated, and optimized.
    """
    
    def __init__(self):
        self.error_handler = ErrorHandler()
        self.symbol_table = SymbolTable()
        self.context = ParserContext(self.error_handler)
        
    def build_ast(self, parse_tree: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build an AST from the parse tree.
        
        Args:
            parse_tree: The parse tree produced by the parser
            
        Returns:
            Dictionary containing:
            - ast: The built AST
            - errors: List of AST building errors
        """
        if not parse_tree:
            return {
                "ast": None,
                "errors": ["No parse tree provided"]
            }
            
        try:
            # Extract the actual parse tree object
            actual_tree = parse_tree.get("parse_tree")
            if not actual_tree:
                return {
                    "ast": None,
                    "errors": ["Invalid parse tree structure"]
                }
                
            # Extract match_recognize clauses from the parse tree
            match_recognize_clauses = self._extract_match_recognize_clauses(actual_tree)
            
            if match_recognize_clauses:
                # Build ASTs for each match_recognize clause
                match_recognize_asts = []
                all_errors = []
                
                for clause in match_recognize_clauses:
                    ast, errors = self._build_match_recognize_ast(clause)
                    if ast:
                        match_recognize_asts.append(ast)
                    if errors:
                        all_errors.extend(errors)
                
                if all_errors:
                    return {
                        "ast": None,
                        "errors": all_errors
                    }
                else:
                    return {
                        "ast": {
                            "type": "query",
                            "match_recognize": match_recognize_asts
                        },
                        "errors": []
                    }
            else:
                # Handle other SQL constructs or return empty AST
                return {
                    "ast": {"type": "query", "match_recognize": []},
                    "errors": []
                }
        except Exception as e:
            logger.error(f"Error building AST: {str(e)}", exc_info=True)
            return {
                "ast": None,
                "errors": [f"Error building AST: {str(e)}"]
            }
    
    def _extract_match_recognize_clauses(self, parse_tree) -> List[Any]:
        """
        Extract MATCH_RECOGNIZE clauses from the parse tree.
        
        Args:
            parse_tree: The parse tree to extract from
            
        Returns:
            List of MATCH_RECOGNIZE clause contexts
        """
        # Use a visitor to find all MATCH_RECOGNIZE clauses
        visitor = MatchRecognizeVisitor()
        clauses = visitor.visit(parse_tree)
        return clauses
    
    def _build_match_recognize_ast(self, clause) -> Tuple[MatchRecognizeAST, List[str]]:
        """
        Build a MatchRecognizeAST from a MATCH_RECOGNIZE clause context.
        
        Args:
            clause: The MATCH_RECOGNIZE clause context
            
        Returns:
            Tuple containing:
            - The built MatchRecognizeAST
            - List of errors encountered during building
        """
        ast = MatchRecognizeAST()
        errors = []
        
        try:
            # Reset context for this clause
            self.context = ParserContext(self.error_handler)
            
            # Extract PARTITION BY
            partition_by = self._extract_partition_by(clause)
            ast.partition_by = partition_by
            
            # Extract ORDER BY
            order_by = self._extract_order_by(clause)
            ast.order_by = order_by
            
            # Extract PATTERN
            pattern, pattern_errors = self._extract_pattern(clause)
            ast.pattern = pattern
            errors.extend(pattern_errors)
            
            # Extract pattern variables for validation
            if pattern and "ast" in pattern:
                pattern_vars = self._extract_pattern_variables(pattern["ast"])
                self.context.pattern_variables = pattern_vars
            
            # Extract SUBSET
            subset = self._extract_subset(clause)
            ast.subset = subset
            
            # Update context with subset variables
            for subset_name, members in subset.items():
                self.context.add_subset_definition(subset_name, set(members))
            
            # Extract DEFINE
            define, define_errors = self._extract_define(clause)
            ast.define = define
            errors.extend(define_errors)
            
            # Extract MEASURES
            measures, measure_errors = self._extract_measures(clause)
            ast.measures = measures
            errors.extend(measure_errors)
            
            # Extract ROWS PER MATCH
            rows_per_match = self._extract_rows_per_match(clause)
            ast.rows_per_match = rows_per_match
            
            # Extract AFTER MATCH SKIP
            after_match_skip = self._extract_after_match_skip(clause)
            ast.after_match_skip = after_match_skip
            
            # Initialize the AST (parse enums, etc.)
            ast.__post_init__()
            
            # Validate cross-clause constraints
            self._validate_cross_clause_constraints(ast, errors)
            
        except Exception as e:
            logger.error(f"Error building match_recognize AST: {str(e)}", exc_info=True)
            errors.append(f"Error building match_recognize AST: {str(e)}")
        
        return ast, errors
    
    def _extract_partition_by(self, clause) -> List[Dict[str, Any]]:
        """Extract PARTITION BY expressions"""
        result = []
        
        try:
            if hasattr(clause, "partitionBy") and clause.partitionBy():
                expressions = clause.partitionBy().expression()
                for expr in expressions:
                    expr_text = expr.getText()
                    expr_ast = parse_expression(expr_text, False, self.context)
                    result.append({
                        "raw": expr_text,
                        "ast": expr_ast
                    })
        except Exception as e:
            self.error_handler.add_error(f"Error extracting PARTITION BY: {str(e)}", 0, 0)
            
        return result
    
    def _extract_order_by(self, clause) -> List[Dict[str, Any]]:
        """Extract ORDER BY expressions"""
        result = []
        
        try:
            if hasattr(clause, "orderBy") and clause.orderBy():
                sort_items = clause.orderBy().sortItem()
                for item in sort_items:
                    expr = item.expression()
                    expr_text = expr.getText()
                    expr_ast = parse_expression(expr_text, False, self.context)
                    
                    # Extract ordering information
                    ordering = "ASC"
                    if hasattr(item, "DESC") and item.DESC():
                        ordering = "DESC"
                    elif hasattr(item, "ASC") and item.ASC():
                        ordering = "ASC"
                        
                    # Extract nulls ordering
                    nulls_ordering = None
                    if hasattr(item, "FIRST") and item.FIRST():
                        nulls_ordering = "NULLS FIRST"
                    elif hasattr(item, "LAST") and item.LAST():
                        nulls_ordering = "NULLS LAST"
                        
                    result.append({
                        "raw": expr_text,
                        "ast": expr_ast,
                        "ordering": ordering,
                        "nulls_ordering": nulls_ordering
                    })
        except Exception as e:
            self.error_handler.add_error(f"Error extracting ORDER BY: {str(e)}", 0, 0)
            
        return result
    
    def _extract_pattern(self, clause) -> Tuple[Dict[str, Any], List[str]]:
        """Extract PATTERN clause"""
        pattern = {}
        errors = []
        
        try:
            if hasattr(clause, "pattern") and clause.pattern():
                pattern_text = clause.pattern().getText()
                
                # Remove outer parentheses if present
                if pattern_text.startswith('(') and pattern_text.endswith(')'):
                    pattern_text = pattern_text[1:-1].strip()
                
                # Use the pattern parser to create a proper AST
                pattern_result = parse_pattern_full(pattern_text, None, self.context)
                
                if pattern_result.get("errors"):
                    errors.extend(pattern_result["errors"])
                
                pattern = {
                    "raw": pattern_text,
                    "ast": pattern_result["ast"]
                }
                
        except Exception as e:
            errors.append(f"Error extracting PATTERN: {str(e)}")
            
        return pattern, errors
    
    def _extract_subset(self, clause) -> Dict[str, List[str]]:
        """Extract SUBSET clause"""
        result = {}
        
        try:
            if hasattr(clause, "subsetDefinition") and clause.subsetDefinition():
                for subset in clause.subsetDefinition():
                    subset_name = subset.identifier().getText()
                    members = []
                    
                    if hasattr(subset, "identifierList") and subset.identifierList():
                        for member in subset.identifierList().identifier():
                            members.append(member.getText())
                            
                    result[subset_name] = members
        except Exception as e:
            self.error_handler.add_error(f"Error extracting SUBSET: {str(e)}", 0, 0)
            
        return result
       
    def _extract_define(self, clause) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Extract DEFINE clause"""
        define = []
        errors = []
        
        try:
            if hasattr(clause, "variableDefinition") and clause.variableDefinition():
                for var_def in clause.variableDefinition():
                    var_name = var_def.identifier().getText()
                    
                    # Add variable to context for validation during parsing
                    self.context.add_pattern_variable(var_name)
                    
                    # Get the condition expression text
                    condition_expr = var_def.expression().getText()
                    
                    # Parse the condition with context
                    self.context.in_define_clause = True
                    # Use parse_expression which properly uses Tokenizer
                    condition_ast = parse_expression(condition_expr, False, self.context)
                    self.context.in_define_clause = False
                    
                    define.append({
                        "variable": var_name,
                        "condition": {
                            "raw": condition_expr,
                            "ast": condition_ast
                        }
                    })
                    
                    # Check for errors in expression parsing
                    if self.error_handler.has_errors():
                        errors.extend(self.error_handler.get_formatted_errors())
                        self.error_handler.clear()
        except Exception as e:
            errors.append(f"Error extracting DEFINE: {str(e)}")
            
        return define, errors
    
    def _extract_measures(self, clause) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Extract MEASURES clause"""
        measures = []
        errors = []
        
        try:
            if hasattr(clause, "measureDefinition") and clause.measureDefinition():
                for measure in clause.measureDefinition():
                    expr = measure.expression().getText()
                    alias = measure.identifier().getText()
                    
                    # Parse the measure expression with context
                    self.context.in_measures_clause = True
                    # Use parse_expression which properly uses Tokenizer
                    expr_ast = parse_expression(expr, True, self.context)
                    self.context.in_measures_clause = False
                    
                    measures.append({
                        "expression": {
                            "raw": expr,
                            "ast": expr_ast
                        },
                        "alias": alias
                    })
                    
                    # Check for errors in expression parsing
                    if self.error_handler.has_errors():
                        errors.extend(self.error_handler.get_formatted_errors())
                        self.error_handler.clear()
        except Exception as e:
            errors.append(f"Error extracting MEASURES: {str(e)}")
            
        return measures, errors    
    
    def _extract_rows_per_match(self, clause) -> str:
        """Extract ROWS PER MATCH clause"""
        try:
            if hasattr(clause, "rowsPerMatch") and clause.rowsPerMatch():
                rpm = clause.rowsPerMatch()
                
                if hasattr(rpm, "ONE") and rpm.ONE():
                    return "ONE ROW PER MATCH"
                elif hasattr(rpm, "ALL") and rpm.ALL():
                    result = "ALL ROWS PER MATCH"
                    
                    # Check for empty match handling
                    if hasattr(rpm, "emptyMatchHandling") and rpm.emptyMatchHandling():
                        empty = rpm.emptyMatchHandling()
                        if hasattr(empty, "SHOW") and empty.SHOW():
                            result += " SHOW EMPTY MATCHES"
                        elif hasattr(empty, "OMIT") and empty.OMIT():
                            result += " OMIT EMPTY MATCHES"
                            
                    # Check for unmatched rows
                    if hasattr(rpm, "UNMATCHED") and rpm.UNMATCHED():
                        result += " WITH UNMATCHED ROWS"
                        
                    return result
        except Exception as e:
            self.error_handler.add_error(f"Error extracting ROWS PER MATCH: {str(e)}", 0, 0)
            
        # Default
        return "ONE ROW PER MATCH"
    
    def _extract_after_match_skip(self, clause) -> str:
        """Extract AFTER MATCH SKIP clause"""
        try:
            if hasattr(clause, "skipTo") and clause.skipTo():
                skip = clause.skipTo()
                
                if hasattr(skip, "PAST") and skip.PAST():
                    return "SKIP PAST LAST ROW"
                elif hasattr(skip, "TO") and skip.TO():
                    if hasattr(skip, "NEXT") and skip.NEXT():
                        return "SKIP TO NEXT ROW"
                    elif hasattr(skip, "FIRST") and skip.FIRST():
                        var = skip.identifier().getText()
                        return f"SKIP TO FIRST {var}"
                    elif hasattr(skip, "LAST") and skip.LAST():
                        var = skip.identifier().getText()
                        return f"SKIP TO LAST {var}"
        except Exception as e:
            self.error_handler.add_error(f"Error extracting AFTER MATCH SKIP: {str(e)}", 0, 0)
            
        # Default
        return "SKIP PAST LAST ROW"
    
    def _extract_pattern_variables(self, pattern_ast: PatternAST) -> Set[str]:
        """Extract all pattern variables from a pattern AST"""
        variables = set()
        
        if pattern_ast.type == "literal":
            variables.add(pattern_ast.value)
        elif pattern_ast.type in ["concatenation", "alternation", "group", "quantifier", "permutation", "exclusion"]:
            for child in pattern_ast.children:
                variables.update(self._extract_pattern_variables(child))
                
        return variables
    
    def _validate_cross_clause_constraints(self, ast: MatchRecognizeAST, errors: List[str]):
        """Validate constraints between clauses"""
        # Check that all pattern variables are defined in DEFINE clause
        if hasattr(ast, 'pattern') and 'ast' in ast.pattern:
            pattern_vars = self._extract_pattern_variables(ast.pattern['ast'])
            defined_vars = {define['variable'] for define in ast.define}
            undefined_vars = pattern_vars - defined_vars
            
            if undefined_vars:
                errors.append(f"Pattern variables not defined in DEFINE clause: {', '.join(undefined_vars)}")
        
        # Check SKIP TO variable exists in pattern
        if ast.skip_to_variable and ast.skip_to_variable not in self.context.pattern_variables:
            errors.append(f"SKIP TO variable '{ast.skip_to_variable}' not defined in pattern")


class MatchRecognizeVisitor(TrinoParserVisitor):
    """
    Visitor to extract MATCH_RECOGNIZE clauses from the parse tree.
    """
    
    def __init__(self):
        self.match_recognize_clauses = []
        
    def visitPatternRecognition(self, ctx):
        """Visit a pattern recognition clause"""
        self.match_recognize_clauses.append(ctx)
        return self.visitChildren(ctx)
        
    def visit(self, tree):
        """Visit the parse tree and return all MATCH_RECOGNIZE clauses"""
        super().visit(tree)
        return self.match_recognize_clauses


def build_ast_from_parse_tree(parse_tree: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build an AST from the parse tree.
    
    Args:
        parse_tree: The parse tree produced by the parser
        
    Returns:
        Dictionary containing:
        - ast: The built AST
        - errors: List of AST building errors
    """
    builder = ASTBuilder()
    return builder.build_ast(parse_tree)
