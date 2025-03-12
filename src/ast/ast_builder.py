import logging
import re
from antlr4 import ParseTreeWalker
from src.parser.antlr_parser import parse_input, CustomErrorListener
from src.grammar.TrinoParserListener import TrinoParserListener
from src.ast.match_recognize_ast import MatchRecognizeAST
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full

logger = logging.getLogger(__name__)

def get_formatted_text(ctx):
    """
    Recursively extract text from a parse tree context.
    For demonstration, we simply call getText() if available.
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
    for the MATCH_RECOGNIZE clause.
    """
    def __init__(self):
        self.ast = MatchRecognizeAST()
        self.errors = []

    # Assuming the grammar rule is named matchRecognizeClause.
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
                        measures.append({
                            "expression": parse_expression_full(expr_text),
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
            # Extract PATTERN clause
            if hasattr(ctx, 'patternClause') and ctx.patternClause():
                pattern_text = get_formatted_text(ctx.patternClause())
                self.ast.pattern = parse_pattern_full(pattern_text)
                logger.debug("Extracted PATTERN: %s", self.ast.pattern)
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
                logger.debug("Extracted SUBSET: %s", self.ast.subset)
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
                        defines.append({
                            "variable": var_text,
                            "condition": parse_expression_full(cond_text)
                        })
                self.ast.define = defines
                logger.debug("Extracted DEFINE: %s", self.ast.define)
            # Check for an empty pattern
            if hasattr(ctx, 'patternClause') and get_formatted_text(ctx.patternClause()) == "()":
                self.ast.is_empty_match = True
                logger.debug("Empty match detected.")
        except Exception as e:
            self.errors.append(str(e))
            logger.error("Error while extracting MATCH_RECOGNIZE clause: %s", e)

    def enterEveryRule(self, ctx):
        pass
    def exitEveryRule(self, ctx):
        pass

    def get_ast(self):
        return self.ast

def build_enhanced_match_recognize_ast(query: str):
    """
    Ties together the parsing and AST building:
      1. Calls the ANTLR parser to get the parse tree.
      2. Uses a custom error listener.
      3. Walks the tree with the EnhancedMatchRecognizeASTBuilder.
      4. Returns the AST along with any errors.
    """
    tree, parser = parse_input(query)
    error_listener = CustomErrorListener()
    parser.removeErrorListeners()
    # Uncomment below if your parser supports adding custom listeners:
    # parser.addErrorListener(error_listener)

    builder = EnhancedMatchRecognizeASTBuilder()
    walker = ParseTreeWalker()
    walker.walk(builder, tree)
    errors = error_listener.get_errors() + builder.errors
    return builder.ast, errors
