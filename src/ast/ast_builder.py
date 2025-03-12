# src/ast/ast_builder.py

import logging
import re
from antlr4 import ParseTreeWalker
from src.parser.antlr_parser import parse_input, CustomErrorListener
from src.grammar.TrinoParserListener import TrinoParserListener
from src.ast.match_recognize_ast import MatchRecognizeAST, RowsPerMatchType, AfterMatchSkipType
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full
from src.ast.pattern_optimizer import optimize_pattern

logger = logging.getLogger(__name__)

def get_formatted_text(ctx):
    """
    Recursively extracts text from a parse tree context.
    For simplicity, uses the getText() method if available.
    """
    try:
        return ctx.getText().strip()
    except AttributeError:
        texts = []
        if hasattr(ctx, 'children'):
            for child in ctx.children:
                texts.append(get_formatted_text(child))
        return " ".join(texts).strip()

class EnhancedMatchRecognizeASTBuilder(TrinoParserListener):
    """
    Walks the parse tree produced by the ANTLR parser and builds a full AST
    for the MATCH_RECOGNIZE clause, including subclauses for PARTITION BY,
    ORDER BY, MEASURES, ROWS PER MATCH, AFTER MATCH SKIP, PATTERN, SUBSET, and DEFINE.
    
    Enhanced with:
    - Context tracking for MEASURES vs DEFINE clauses
    - Classifier function validation
    - Unmatched row handling
    """
    def __init__(self):
        self.ast = MatchRecognizeAST()
        self.errors = []
        self.pattern_variables = set()
        self.subset_variables = {}

    def enterMatchRecognizeClause(self, ctx):
        logger.debug("Entering MATCH_RECOGNIZE clause.")

    def exitMatchRecognizeClause(self, ctx):
        try:
            # Extract PARTITION BY clause
            if hasattr(ctx, 'partitionClause') and ctx.partitionClause():
                partition_exprs = ctx.partitionClause().expression()
                self.ast.partition_by = [get_formatted_text(expr) for expr in partition_exprs]
                logger.debug("Extracted PARTITION BY: %s", self.ast.partition_by)
                
            # Extract ORDER BY clause
            if hasattr(ctx, 'orderClause') and ctx.orderClause():
                sort_items = ctx.orderClause().sortItem()
                self.ast.order_by = [get_formatted_text(item) for item in sort_items]
                logger.debug("Extracted ORDER BY: %s", self.ast.order_by)
                
            # Extract PATTERN clause and optimize the resulting AST
            # We extract pattern first to get pattern variables for validation
            if hasattr(ctx, 'patternClause') and ctx.patternClause():
                pattern_text = get_formatted_text(ctx.patternClause())
                parsed_pattern = parse_pattern_full(pattern_text)
                optimized_pattern = optimize_pattern(parsed_pattern)
                self.ast.pattern = optimized_pattern
                
                # Extract pattern variables for validation
                if "ast" in optimized_pattern:
                    self.pattern_variables = self._extract_pattern_variables(optimized_pattern["ast"])
                
                logger.debug("Extracted and optimized PATTERN: %s", self.ast.pattern)
                
            # Extract SUBSET clause
            if hasattr(ctx, 'subsetClause') and ctx.subsetClause():
                subset_mapping = {}
                for subsetDefCtx in ctx.subsetClause().subsetDefinition():
                    text = get_formatted_text(subsetDefCtx)
                    m = re.match(r'(\w+)\s*=\s*\((.*?)\)', text)
                    if m:
                        key = m.group(1).strip()
                        values = [v.strip() for v in m.group(2).split(',')]
                        subset_mapping[key] = values
                    else:
                        self.errors.append("Invalid SUBSET definition: " + text)
                self.ast.subset = subset_mapping
                self.subset_variables = subset_mapping
                logger.debug("Extracted SUBSET: %s", self.ast.subset)
                
            # Extract MEASURES clause
            if hasattr(ctx, 'measureClause') and ctx.measureClause():
                measures = []
                for measureCtx in ctx.measureClause().measureDefinition():
                    expr_ctx = measureCtx.expression()
                    alias_ctx = measureCtx.alias()
                    expr_text = get_formatted_text(expr_ctx)
                    alias_text = get_formatted_text(alias_ctx)
                    if not alias_text:
                        self.errors.append(f"Measure '{expr_text}' is missing an alias.")
                    else:
                        # Parse with in_measures_clause=True
                        expr_ast = parse_expression_full(expr_text, in_measures_clause=True)
                        
                        # Validate classifier function consistency
                        self._validate_classifier_consistency(expr_ast["ast"], f"MEASURE {alias_text}")
                        
                        # Validate RUNNING/FINAL semantics
                        self._validate_running_final_semantics(expr_ast["ast"], f"MEASURE {alias_text}", in_measures=True)
                        
                        # Validate count(*) and count(var.*) syntax
                        self._validate_count_star_syntax(expr_ast["ast"], f"MEASURE {alias_text}")
                        
                        measures.append({
                            "expression": expr_ast,
                            "alias": alias_text
                        })
                self.ast.measures = measures
                logger.debug("Extracted MEASURES: %s", self.ast.measures)
                
            # Extract ROWS PER MATCH clause
            if hasattr(ctx, 'rowsPerMatchClause') and ctx.rowsPerMatchClause():
                self.ast.rows_per_match = get_formatted_text(ctx.rowsPerMatchClause())
                logger.debug("Extracted ROWS PER MATCH: %s", self.ast.rows_per_match)
                
            # Extract AFTER MATCH SKIP clause
            if hasattr(ctx, 'afterMatchSkipClause') and ctx.afterMatchSkipClause():
                self.ast.after_match_skip = get_formatted_text(ctx.afterMatchSkipClause())
                logger.debug("Extracted AFTER MATCH SKIP: %s", self.ast.after_match_skip)
                
            # Extract DEFINE clause
            if hasattr(ctx, 'defineClause') and ctx.defineClause():
                defines = []
                for varDefCtx in ctx.defineClause().variableDefinition():
                    var_ctx = varDefCtx.variable()
                    cond_ctx = varDefCtx.condition()
                    var_text = get_formatted_text(var_ctx)
                    cond_text = get_formatted_text(cond_ctx)
                    if not cond_text:
                        self.errors.append(f"DEFINE clause for variable '{var_text}' is missing a condition.")
                    else:
                        # Parse with in_measures_clause=False
                        cond_ast = parse_expression_full(cond_text, in_measures_clause=False)
                        
                        # Validate classifier function consistency
                        self._validate_classifier_consistency(cond_ast["ast"], f"DEFINE {var_text}")
                        
                        # Validate RUNNING/FINAL semantics
                        self._validate_running_final_semantics(cond_ast["ast"], f"DEFINE {var_text}", in_measures=False)
                        
                        # Validate count(*) and count(var.*) syntax
                        self._validate_count_star_syntax(cond_ast["ast"], f"DEFINE {var_text}")
                        
                        defines.append({
                            "variable": var_text,
                            "condition": cond_ast
                        })
                self.ast.define = defines
                logger.debug("Extracted DEFINE: %s", self.ast.define)
                
            # Flag empty pattern if detected
            if hasattr(ctx, 'patternClause') and get_formatted_text(ctx.patternClause()) == "()":
                self.ast.is_empty_match = True
                logger.debug("Empty match detected.")
                
            # Finalize AST post-processing
            self.ast.__post_init__()
            
            # Validate unmatched rows constraints
            self._validate_unmatched_rows_constraints()
                
        except Exception as e:
            self.errors.append(str(e))
            logger.error("Error while extracting MATCH_RECOGNIZE clause: %s", e)

    def enterEveryRule(self, ctx):
        pass

    def exitEveryRule(self, ctx):
        pass

    def get_ast(self):
        return self.ast
        
    def _extract_pattern_variables(self, pattern_ast):
        """Extract all pattern variables from the pattern AST"""
        vars = set()
        
        if pattern_ast.type == "literal":
            vars.add(pattern_ast.value)
        elif pattern_ast.type in ["concatenation", "alternation", "group", "quantifier", "permutation", "exclusion"]:
            for child in pattern_ast.children:
                vars.update(self._extract_pattern_variables(child))
                
        return vars
        
    def _collect_variables(self, expr_ast):
        """
        Collect pattern variables and classifier variables from an expression AST.
        
        Returns:
            Tuple of (pattern_vars, classifier_vars)
        """
        pattern_vars = set()
        classifier_vars = set()
        
        if expr_ast.type == "pattern_variable_reference":
            if hasattr(expr_ast, "pattern_variable") and expr_ast.pattern_variable:
                pattern_vars.add(expr_ast.pattern_variable)
                
        elif expr_ast.type == "classifier":
            if hasattr(expr_ast, "pattern_variable") and expr_ast.pattern_variable:
                classifier_vars.add(expr_ast.pattern_variable)
                
        # Recursively collect from children
        for child in expr_ast.children:
            child_pattern_vars, child_classifier_vars = self._collect_variables(child)
            pattern_vars.update(child_pattern_vars)
            classifier_vars.update(child_classifier_vars)
            
        return pattern_vars, classifier_vars
    
    def _validate_classifier_consistency(self, expr_ast, context):
        """
        Validate that CLASSIFIER() arguments are consistent with pattern variable references.
        
        Args:
            expr_ast: The expression AST to validate
            context: String describing where this expression is used (for error messages)
        """
        # Collect all pattern variables and classifier variables
        pattern_vars, classifier_vars = self._collect_variables(expr_ast)
        
        # If there are no classifier functions, no validation needed
        if not classifier_vars:
            return
            
        # If CLASSIFIER() is used without arguments, it's always valid
        if not any(classifier_vars):
            return
            
        # If there are pattern variable references, validate that classifier variables match
        if pattern_vars:
            invalid_vars = classifier_vars - pattern_vars
            if invalid_vars:
                self.errors.append(
                    f"In {context}: CLASSIFIER() references pattern variables {invalid_vars} "
                    f"that are not used in other parts of the expression"
                )
                
        # Check for multiple different classifier variables in the same expression
        if len(classifier_vars) > 1:
            self.errors.append(
                f"In {context}: Multiple different pattern variables in CLASSIFIER() functions: "
                f"{', '.join(classifier_vars)}"
            )
    
    def _validate_running_final_semantics(self, expr_ast, context, in_measures=True):
        """
        Validate RUNNING and FINAL semantics usage.
        
        Args:
            expr_ast: The expression AST to validate
            context: String describing where this expression is used
            in_measures: Whether this expression is in the MEASURES clause
        """
        if hasattr(expr_ast, "semantics") and expr_ast.semantics:
            # FINAL can only be used in MEASURES clause
            if expr_ast.semantics == "FINAL" and not in_measures:
                self.errors.append(
                    f"In {context}: FINAL semantics can only be used in MEASURES clause"
                )
            
            # FINAL can only be used with aggregate or navigation functions
            if expr_ast.semantics == "FINAL" and expr_ast.type not in ["aggregate", "navigation"]:
                self.errors.append(
                    f"In {context}: FINAL semantics can only be applied to "
                    "aggregate or navigation functions"
                )
        
        # Recursively validate children
        for child in expr_ast.children:
            self._validate_running_final_semantics(child, context, in_measures)
    
    def _validate_count_star_syntax(self, expr_ast, context):
        """
        Validate special count(*) and count(var.*) syntax.
        
        Args:
            expr_ast: The expression AST to validate
            context: String describing where this expression is used
        """
        if expr_ast.type == "aggregate" and expr_ast.value.lower() == "count":
            # Check for count(*)
            if hasattr(expr_ast, "count_star") and expr_ast.count_star:
                if hasattr(expr_ast, "pattern_variable") and expr_ast.pattern_variable:
                    # This is count(var.*)
                    if expr_ast.pattern_variable not in self.pattern_variables and expr_ast.pattern_variable not in self.subset_variables:
                        self.errors.append(
                            f"In {context}: count({expr_ast.pattern_variable}.*) references "
                            "undefined pattern variable"
                        )
            
            # Regular count() must have exactly one argument
            elif not expr_ast.children:
                self.errors.append(
                    f"In {context}: count() requires an argument (use count(*) for counting all rows)"
                )
        
        # Recursively validate children
        for child in expr_ast.children:
            self._validate_count_star_syntax(child, context)
    
    def _validate_unmatched_rows_constraints(self):
        """Validate constraints related to unmatched rows handling"""
        if self.ast.has_unmatched_rows:
            # Check for pattern exclusions
            if self.ast.has_exclusion:
                self.errors.append(
                    "Pattern exclusions '{- ... -}' cannot be used with "
                    "ALL ROWS PER MATCH WITH UNMATCHED ROWS"
                )
            
            # Check for AFTER MATCH SKIP TO
            if (self.ast.after_match_skip_type in 
                    [AfterMatchSkipType.SKIP_TO_FIRST, AfterMatchSkipType.SKIP_TO_LAST]):
                self.errors.append(
                    "AFTER MATCH SKIP TO FIRST/LAST cannot be used with "
                    "ALL ROWS PER MATCH WITH UNMATCHED ROWS"
                )

def build_enhanced_match_recognize_ast(query: str):
    """
    Combines ANTLR parsing with AST building:
      1. Parses the query to generate a parse tree.
      2. Walks the tree with EnhancedMatchRecognizeASTBuilder.
      3. Returns the complete AST along with any collected errors.
      
    Enhanced with:
      - Classifier function validation
      - RUNNING/FINAL semantics validation
      - count(*) and count(var.*) syntax validation
      - Unmatched rows constraints validation
    """
    tree, parser, parse_errors = parse_input(query)
    if parse_errors:
        return None, parse_errors
        
    builder = EnhancedMatchRecognizeASTBuilder()
    walker = ParseTreeWalker()
    walker.walk(builder, tree)
    
    return builder.ast, builder.errors
