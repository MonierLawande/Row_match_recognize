# src/ast/ast_builder.py

import logging
from typing import Dict, Any, List, Tuple, Optional, Set
# (Remove antlr4 imports if not needed in the new pipeline)
#from antlr4 import InputStream, CommonTokenStream
from src.ast.match_recognize_ast import MatchRecognizeAST
from src.ast.pattern_ast import PatternAST
from src.ast.expression_ast import ExpressionAST
from src.parser.error_handler import ErrorHandler
from src.parser.symbol_table import SymbolTable
#from src.parser.tokenizer import Tokenizer  # No longer needed here
from src.parser.expression_parser import parse_expression_full  # now returns parse_tree dictionary
from src.parser.pattern_parser import parse_pattern_full  # now returns parse_tree dictionary
from src.parser.context import ParserContext

# Import our conversion functions from our new conversion module (could be in this file too)
from src.ast.ast_builder_conversion import build_expression_ast, build_pattern_ast

logger = logging.getLogger(__name__)

class ASTBuilder:
    """
    Builds an Abstract Syntax Tree (AST) from a parse tree.
    
    In the new design, the parser produces a generic parse tree.
    The ASTBuilder then converts these parse trees into raw AST nodes.
    """
    
    def __init__(self):
        self.error_handler = ErrorHandler()
        self.symbol_table = SymbolTable()
        self.context = ParserContext(self.error_handler)
        
    def build_ast(self, parse_tree_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build an AST from the parse tree.
        
        Args:
            parse_tree_dict: Dictionary produced by the parser containing:
              - "parse_tree": the generic parse tree
              - "errors": any errors reported during parsing
              
        Returns:
            Dictionary containing:
              - ast: The built AST (for example, a query AST containing MATCH_RECOGNIZE clauses)
              - errors: List of AST building errors
        """
        if not parse_tree_dict:
            return {
                "ast": None,
                "errors": ["No parse tree provided"]
            }
            
        try:
            actual_tree = parse_tree_dict.get("parse_tree")
            if not actual_tree:
                return {
                    "ast": None,
                    "errors": ["Invalid parse tree structure"]
                }
                
            # Extract MATCH_RECOGNIZE clauses from the full query parse tree.
            # (If your overall parser is still producing an ANTLR tree for the full query,
            #  then you can use a visitor. Otherwise, if the full query is built using your new parser,
            #  you may need to extract the MATCH_RECOGNIZE clause(s) using your own logic.)
            match_recognize_clauses = self._extract_match_recognize_clauses(actual_tree)
            
            if match_recognize_clauses:
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
                # If no MATCH_RECOGNIZE clause is found, return an empty query AST.
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
    
    def _extract_match_recognize_clauses(self, parse_tree: Any) -> List[Any]:
        """
        Extract MATCH_RECOGNIZE clauses from the full query parse tree.
        
        (Depending on your overall grammar, this extraction logic may vary.
         For now, we assume you have a visitor class to locate such clauses.)
        """
        # Here we still use the visitor (if you are mixing ANTLR trees for full SQL)
        visitor = MatchRecognizeVisitor()
        clauses = visitor.visit(parse_tree)
        return clauses
    
    def _build_match_recognize_ast(self, clause: Any) -> Tuple[MatchRecognizeAST, List[str]]:
        """
        Build a MatchRecognizeAST from a MATCH_RECOGNIZE clause context.
        
        This method converts sub-clauses (like PARTITION BY, ORDER BY, PATTERN, DEFINE, MEASURES, etc.)
        by first using the parser to produce parse trees and then converting them with the
        dedicated conversion functions.
        
        Returns:
            Tuple of (MatchRecognizeAST, list of errors).
        """
        ast = MatchRecognizeAST()
        errors = []
        
        try:
            # Reset context for this clause.
            self.context = ParserContext(self.error_handler)
            
            # PARTITION BY: For each expression, get the parse tree then convert it.
            partition_by = self._extract_partition_by(clause)
            ast.partition_by = partition_by
            
            # ORDER BY:
            order_by = self._extract_order_by(clause)
            ast.order_by = order_by
            
            # PATTERN:
            pattern, pattern_errors = self._extract_pattern(clause)
            ast.pattern = pattern
            errors.extend(pattern_errors)
            
            # Extract and update pattern variables for later validations.
            if pattern and pattern.get("parse_tree"):
                pattern_vars = self._extract_pattern_variables(
                    build_pattern_ast(pattern["parse_tree"])
                )
                self.context.pattern_variables = pattern_vars
            
            # SUBSET:
            subset = self._extract_subset(clause)
            ast.subset = subset
            
            for subset_name, members in subset.items():
                self.context.add_subset_definition(subset_name, set(members))
            
            # DEFINE:
            define, define_errors = self._extract_define(clause)
            ast.define = define
            errors.extend(define_errors)
            
            # MEASURES:
            measures, measure_errors = self._extract_measures(clause)
            ast.measures = measures
            errors.extend(measure_errors)
            
            # ROWS PER MATCH:
            rows_per_match = self._extract_rows_per_match(clause)
            ast.rows_per_match = rows_per_match
            
            # AFTER MATCH SKIP:
            after_match_skip = self._extract_after_match_skip(clause)
            ast.after_match_skip = after_match_skip
            
            # Finalize AST initialization (e.g., process enums, etc.)
            ast.__post_init__()
            
            # Validate cross-clause constraints.
            self._validate_cross_clause_constraints(ast, errors)
            
        except Exception as e:
            logger.error(f"Error building match_recognize AST: {str(e)}", exc_info=True)
            errors.append(f"Error building match_recognize AST: {str(e)}")
        
        return ast, errors
    
    def _extract_partition_by(self, clause: Any) -> List[Dict[str, Any]]:
        result = []
        try:
            if hasattr(clause, "partitionBy") and clause.partitionBy():
                expressions = clause.partitionBy().expression()
                for expr in expressions:
                    expr_text = expr.getText()
                    # Get the parse tree for the expression.
                    expr_result = parse_expression_full(expr_text, False, self.context)
                    # Convert the parse tree to a raw AST.
                    expr_ast = build_expression_ast(expr_result.get("parse_tree"))
                    result.append({
                        "raw": expr_text,
                        "ast": expr_ast
                    })
        except Exception as e:
            self.error_handler.add_error(f"Error extracting PARTITION BY: {str(e)}", 0, 0)
        return result
    
    def _extract_order_by(self, clause: Any) -> List[Dict[str, Any]]:
        result = []
        try:
            if hasattr(clause, "orderBy") and clause.orderBy():
                sort_items = clause.orderBy().sortItem()
                for item in sort_items:
                    expr = item.expression()
                    expr_text = expr.getText()
                    expr_result = parse_expression_full(expr_text, False, self.context)
                    expr_ast = build_expression_ast(expr_result.get("parse_tree"))
                    
                    ordering = "ASC"
                    if hasattr(item, "DESC") and item.DESC():
                        ordering = "DESC"
                    elif hasattr(item, "ASC") and item.ASC():
                        ordering = "ASC"
                    
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
    
    def _extract_pattern(self, clause: Any) -> Tuple[Dict[str, Any], List[str]]:
        pattern = {}
        errors = []
        try:
            if hasattr(clause, "pattern") and clause.pattern():
                pattern_text = clause.pattern().getText()
                # Remove outer parentheses if present.
                if pattern_text.startswith('(') and pattern_text.endswith(')'):
                    pattern_text = pattern_text[1:-1].strip()
                # Get the parse tree for the pattern.
                pattern_result = parse_pattern_full(pattern_text, None, self.context)
                if pattern_result.get("errors"):
                    errors.extend(pattern_result["errors"])
                pattern = {
                    "raw": pattern_text,
                    "parse_tree": pattern_result.get("parse_tree")
                }
        except Exception as e:
            errors.append(f"Error extracting PATTERN: {str(e)}")
        return pattern, errors
    
    def _extract_subset(self, clause: Any) -> Dict[str, List[str]]:
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
       
    def _extract_define(self, clause: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
        define = []
        errors = []
        try:
            if hasattr(clause, "variableDefinition") and clause.variableDefinition():
                for var_def in clause.variableDefinition():
                    var_name = var_def.identifier().getText()
                    self.context.add_pattern_variable(var_name)
                    condition_expr = var_def.expression().getText()
                    
                    self.context.in_define_clause = True
                    condition_result = parse_expression_full(condition_expr, False, self.context)
                    self.context.in_define_clause = False
                    condition_ast = build_expression_ast(condition_result.get("parse_tree"))
                    
                    define.append({
                        "variable": var_name,
                        "condition": {
                            "raw": condition_expr,
                            "ast": condition_ast
                        }
                    })
                    
                    if self.error_handler.has_errors():
                        errors.extend(self.error_handler.get_formatted_errors())
                        self.error_handler.clear()
        except Exception as e:
            errors.append(f"Error extracting DEFINE: {str(e)}")
        return define, errors
    
    def _extract_measures(self, clause: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
        measures = []
        errors = []
        try:
            if hasattr(clause, "measureDefinition") and clause.measureDefinition():
                for measure in clause.measureDefinition():
                    expr = measure.expression().getText()
                    alias = measure.identifier().getText()
                    
                    self.context.in_measures_clause = True
                    measure_result = parse_expression_full(expr, True, self.context)
                    self.context.in_measures_clause = False
                    expr_ast = build_expression_ast(measure_result.get("parse_tree"))
                    
                    measures.append({
                        "expression": {
                            "raw": expr,
                            "ast": expr_ast
                        },
                        "alias": alias
                    })
                    
                    if self.error_handler.has_errors():
                        errors.extend(self.error_handler.get_formatted_errors())
                        self.error_handler.clear()
        except Exception as e:
            errors.append(f"Error extracting MEASURES: {str(e)}")
        return measures, errors    
    
    def _extract_rows_per_match(self, clause: Any) -> str:
        try:
            if hasattr(clause, "rowsPerMatch") and clause.rowsPerMatch():
                rpm = clause.rowsPerMatch()
                if hasattr(rpm, "ONE") and rpm.ONE():
                    return "ONE ROW PER MATCH"
                elif hasattr(rpm, "ALL") and rpm.ALL():
                    result = "ALL ROWS PER MATCH"
                    if hasattr(rpm, "emptyMatchHandling") and rpm.emptyMatchHandling():
                        empty = rpm.emptyMatchHandling()
                        if hasattr(empty, "SHOW") and empty.SHOW():
                            result += " SHOW EMPTY MATCHES"
                        elif hasattr(empty, "OMIT") and empty.OMIT():
                            result += " OMIT EMPTY MATCHES"
                    if hasattr(rpm, "UNMATCHED") and rpm.UNMATCHED():
                        result += " WITH UNMATCHED ROWS"
                    return result
        except Exception as e:
            self.error_handler.add_error(f"Error extracting ROWS PER MATCH: {str(e)}", 0, 0)
        return "ONE ROW PER MATCH"
    
    def _extract_after_match_skip(self, clause: Any) -> str:
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
        return "SKIP PAST LAST ROW"
    
    def _extract_pattern_variables(self, pattern_ast: PatternAST) -> Set[str]:
        variables = set()
        if pattern_ast.type == "literal":
            variables.add(pattern_ast.value)
        elif pattern_ast.type in ["concatenation", "alternation", "group", "quantifier", "permutation", "exclusion"]:
            for child in pattern_ast.children:
                variables.update(self._extract_pattern_variables(child))
        return variables
    
    def _validate_cross_clause_constraints(self, ast: MatchRecognizeAST, errors: List[str]):
        if hasattr(ast, 'pattern') and 'ast' in ast.pattern:
            pattern_vars = self._extract_pattern_variables(ast.pattern['ast'])
            defined_vars = {d['variable'] for d in ast.define}
            undefined_vars = pattern_vars - defined_vars
            if undefined_vars:
                errors.append(f"Pattern variables not defined in DEFINE clause: {', '.join(undefined_vars)}")
        if getattr(ast, "skip_to_variable", None) and ast.skip_to_variable not in self.context.pattern_variables:
            errors.append(f"SKIP TO variable '{ast.skip_to_variable}' not defined in pattern")

# Visitor for extracting MATCH_RECOGNIZE clauses (if full query parse tree is produced by ANTLR)
class MatchRecognizeVisitor:
    def __init__(self):
        self.match_recognize_clauses = []
        
    def visitPatternRecognition(self, ctx):
        self.match_recognize_clauses.append(ctx)
        return self.visitChildren(ctx)
        
    def visit(self, tree):
        # Traverse the tree (implementation depends on your full query parse tree structure)
        # This is a stub; you may need to implement a full visitor.
        return self.match_recognize_clauses

def build_ast_from_parse_tree(parse_tree_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build an AST from the parse tree.
    
    Args:
        parse_tree_dict: Dictionary with keys "parse_tree", "errors", etc.
        
    Returns:
        Dictionary with "ast" and "errors".
    """
    builder = ASTBuilder()
    return builder.build_ast(parse_tree_dict)
