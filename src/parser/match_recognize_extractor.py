from antlr4 import *
import re
import logging
from src.grammar.TrinoParser import TrinoParser
from src.grammar.TrinoParserVisitor import TrinoParserVisitor
from src.grammar.TrinoLexer import TrinoLexer
from src.ast.ast_nodes import (
    PartitionByClause,
    OrderByClause,
    Measure,
    MeasuresClause,
    RowsPerMatchClause,
    AfterMatchSkipClause,
    PatternClause,
    SubsetClause,
    Define,
    DefineClause,
    MatchRecognizeClause,
    SelectItem,
    SelectClause,
    FromClause,
    FullQueryAST
)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class ParserError(Exception):
    def __init__(self, message, line=None, column=None, snippet=None):
        self.message = message
        self.line = line
        self.column = column
        self.snippet = snippet
        super().__init__(f"{message} (Line: {line}, Column: {column})\nSnippet: {snippet}")

def post_process_text(text):
    """Normalize whitespace in the given text."""
    if text is None:
        return text
    return re.sub(r'\s+', ' ', text).strip()

def smart_split(raw_text):
    """Splits raw_text on 'AS', trying to respect parentheses boundaries."""
    parts = None
    if ")" in raw_text:
        parts = re.split(r'(?<=\))\s*AS\s*', raw_text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return parts
    parts = re.split(r'\s*AS\s*', raw_text, maxsplit=1, flags=re.IGNORECASE)
    return parts

def split_select_items(select_text: str) -> list:
    """
    Split the SELECT clause into individual items.
    This function tracks parentheses to avoid splitting on commas that occur inside expressions.
    """
    items = []
    current = []
    depth = 0
    for char in select_text:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        if char == ',' and depth == 0:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        items.append("".join(current).strip())
    return items

###########################################
# MATCH_RECOGNIZE clause extractor visitor
###########################################
class MatchRecognizeExtractor(TrinoParserVisitor):
    def __init__(self):
        self.ast = MatchRecognizeClause()

    def visitPatternRecognition(self, ctx: TrinoParser.PatternRecognitionContext):
        logger.debug("Visiting PatternRecognition context")
        if ctx.PARTITION_():
            self.ast.partition_by = self.extract_partition_by(ctx)
            logger.debug(f"Extracted PARTITION BY: {self.ast.partition_by}")
        if ctx.ORDER_():
            self.ast.order_by = self.extract_order_by(ctx)
            logger.debug(f"Extracted ORDER BY: {self.ast.order_by}")
        if ctx.MEASURES_():
            self.ast.measures = self.extract_measures(ctx)
            logger.debug(f"Extracted MEASURES: {self.ast.measures}")
        if ctx.rowsPerMatch():
            self.ast.rows_per_match = self.extract_rows_per_match(ctx.rowsPerMatch())
            logger.debug(f"Extracted ROWS PER MATCH: {self.ast.rows_per_match}")
        if ctx.AFTER_():
            self.ast.after_match_skip = self.extract_after_match_skip(ctx)
            logger.debug(f"Extracted AFTER MATCH SKIP: {self.ast.after_match_skip}")
        if ctx.PATTERN_():
            self.ast.pattern = self.extract_pattern(ctx)
            logger.debug(f"Extracted PATTERN: {self.ast.pattern}")
        if ctx.SUBSET_():
            self.ast.subset = self.extract_subset(ctx)
            logger.debug(f"Extracted SUBSET: {self.ast.subset}")
        if ctx.DEFINE_():
            self.ast.define = self.extract_define(ctx)
            logger.debug(f"Extracted DEFINE: {self.ast.define}")
        self.validate_clauses(ctx)
        self.validate_identifiers(ctx)
        self.validate_function_usage(ctx)
        return self.ast

    def extract_partition_by(self, ctx: TrinoParser.PatternRecognitionContext) -> PartitionByClause:
        columns = [post_process_text(expr.getText()) for expr in ctx.partition]
        return PartitionByClause(columns)

    def extract_order_by(self, ctx: TrinoParser.PatternRecognitionContext) -> OrderByClause:
        columns = [post_process_text(si.getText()) for si in ctx.sortItem()]
        return OrderByClause(columns)

    def extract_measures(self, ctx: TrinoParser.PatternRecognitionContext) -> MeasuresClause:
        measures = []
        for md in ctx.measureDefinition():
            raw_text = md.getText()
            parts = smart_split(raw_text)
            if len(parts) == 2:
                measure = Measure(post_process_text(parts[0]), post_process_text(parts[1]))
            else:
                measure = Measure(post_process_text(raw_text))
            measures.append(measure)
        return MeasuresClause(measures)

    def extract_rows_per_match(self, ctx: TrinoParser.RowsPerMatchContext) -> RowsPerMatchClause:
        text = post_process_text(ctx.getText())
        if "ONEROWPERMATCH" in text.upper():
            value = "ONE ROW PER MATCH"
        elif "ALLROWSPERMATCH" in text.upper():
            value = "ALL ROWS PER MATCH"
        else:
            value = text
        return RowsPerMatchClause(value)

    def extract_after_match_skip(self, ctx: TrinoParser.PatternRecognitionContext) -> AfterMatchSkipClause:
        text = post_process_text(" ".join(child.getText() for child in ctx.skipTo().getChildren()))
        return AfterMatchSkipClause(text)

    def extract_pattern(self, ctx: TrinoParser.PatternRecognitionContext) -> PatternClause:
        pattern_text = post_process_text(ctx.rowPattern().getText())
        return PatternClause(pattern_text)

    def extract_subset(self, ctx: TrinoParser.PatternRecognitionContext) -> list:
        subsets = [SubsetClause(post_process_text(sd.getText())) for sd in ctx.subsetDefinition()]
        return subsets

    def extract_define(self, ctx: TrinoParser.PatternRecognitionContext) -> DefineClause:
        definitions = []
        for vd in ctx.variableDefinition():
            raw_text = vd.getText()
            parts = smart_split(raw_text)
            if len(parts) == 2:
                definition = Define(post_process_text(parts[0]), post_process_text(parts[1]))
            else:
                definition = Define(post_process_text(raw_text), "")
            definitions.append(definition)
        return DefineClause(definitions)

    def validate_clauses(self, ctx):
        if self.ast.partition_by and not self.ast.order_by:
            raise ParserError("ORDER BY clause is required when PARTITION BY is used.",
                              line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        if self.ast.define and not self.ast.pattern:
            raise ParserError("PATTERN clause is required when DEFINE is used.",
                              line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())

    def validate_identifiers(self, ctx):
        """Ensure that each identifier used in DEFINE is present in the pattern."""
        if self.ast.pattern:
            pattern_vars = set(re.findall(r'([A-Z])(?:\+)?', self.ast.pattern.pattern))
            logger.debug(f"Extracted pattern variables: {pattern_vars}")
            if self.ast.define:
                for definition in self.ast.define.definitions:
                    if definition.variable not in pattern_vars:
                        raise ParserError(f"Define variable '{definition.variable}' not found in pattern variables {pattern_vars}",
                                          line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())

    def validate_function_usage(self, ctx):
        """Validate aggregate and navigation functions in measures."""
        # Updated patterns to allow dot-qualified identifiers (e.g., B.totalprice).
        allowed_functions = {
            "COUNT": r"COUNT\(\s*(\*|[A-Z][A-Z0-9]*(?:\.[A-Z][A-Z0-9]*)?)\s*\)",
            "FIRST": r"FIRST\(\s*([A-Z][A-Z0-9]*(?:\.[A-Z][A-Z0-9]*)?)(?:\s*,\s*\d+)?\s*\)",
            "LAST": r"LAST\(\s*([A-Z][A-Z0-9]*(?:\.[A-Z][A-Z0-9]*)?)(?:\s*,\s*\d+)?\s*\)",
            "PREV": r"PREV\(\s*([A-Z][A-Z0-9]*(?:\.[A-Z][A-Z0-9]*)?)(?:\s*,\s*\d+)?\s*\)",
            "NEXT": r"NEXT\(\s*([A-Z][A-Z0-9]*(?:\.[A-Z][A-Z0-9]*)?)(?:\s*,\s*\d+)?\s*\)",
        }
        if self.ast.measures:
            for measure in self.ast.measures.measures:
                expr_upper = measure.expression.upper()
                for func, pattern in allowed_functions.items():
                    if func in expr_upper:
                        m = re.search(pattern, expr_upper)
                        if not m:
                            raise ParserError(f"Invalid usage of {func} in measure: {measure.expression}",
                                              line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
                        # m.group(1) should be a column name; further DataFrame validation is done later.
                logger.debug(f"Validated function usage for measure: {measure.expression}")

###############################################
# Full Query extractor visitor for SELECT/FROM/MATCH_RECOGNIZE
###############################################
class FullQueryExtractor(TrinoParserVisitor):
    def __init__(self, original_query: str):
        self.original_query = original_query  # Preserve original query formatting.
        self.select_clause = None
        self.from_clause = None
        self.match_recognize = None

    def visitParse(self, ctx: TrinoParser.ParseContext):
        return self.visitChildren(ctx)

    def visitSingleStatement(self, ctx: TrinoParser.SingleStatementContext):
        full_text = post_process_text(self.original_query)
        logger.debug(f"Full statement text: {full_text}")

        # Use robust splitting for the SELECT clause.
        select_match = re.search(r'(?i)^SELECT\s+(.+?)\s+FROM', full_text)
        if select_match:
            select_text = select_match.group(1)
            items_raw = split_select_items(select_text)
            items = []
            # Use a regex to check for simple column references (identifiers only).
            simple_column_regex = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
            for item in items_raw:
                item = post_process_text(item)
                alias_match = re.search(r'(?i)^(.+?)\s+AS\s+(.+)$', item)
                if alias_match:
                    expr = post_process_text(alias_match.group(1))
                    alias = post_process_text(alias_match.group(2))
                    items.append(SelectItem(expr, alias))
                else:
                    items.append(SelectItem(item))
            self.select_clause = SelectClause(items)
            logger.debug(f"Extracted SELECT clause via robust splitting: {self.select_clause}")
        else:
            logger.warning("No SELECT clause found via regex.")

        # Extract FROM clause: look for "FROM" followed by a table name.
        from_match = re.search(r'(?i)FROM\s+(\w+)', full_text)
        if from_match:
            table_name = from_match.group(1)
            self.from_clause = FromClause(table_name)
            logger.debug(f"Extracted FROM clause via regex: {self.from_clause}")
        else:
            logger.warning("No FROM clause found via regex.")

        # Recursively search for a PatternRecognitionContext.
        self.match_recognize = self.find_pattern_recognition(ctx)
        if self.match_recognize:
            extractor = MatchRecognizeExtractor()
            extractor.visit(self.match_recognize)
            self.match_recognize = extractor.ast
            logger.debug("Extracted MATCH_RECOGNIZE clause via recursive search.")
        else:
            logger.debug("No MATCH_RECOGNIZE clause found.")

        return FullQueryAST(self.select_clause, self.from_clause, self.match_recognize)

    def find_pattern_recognition(self, ctx):
        if not hasattr(ctx, "getChildren"):
            return None
        if isinstance(ctx, TrinoParser.PatternRecognitionContext):
            return ctx
        for child in ctx.getChildren():
            result = self.find_pattern_recognition(child)
            if result is not None:
                return result
        return None

def parse_match_recognize_query(query: str, dialect='default') -> MatchRecognizeClause:
    query = query.strip()
    if not query.endswith(";"):
        query += ";"
    input_stream = InputStream(query)
    lexer = TrinoLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = TrinoParser(token_stream)
    tree = parser.parse()
    extractor = MatchRecognizeExtractor()
    extractor.visit(tree)
    return extractor.ast

def parse_full_query(query: str, dialect='default') -> FullQueryAST:
    query = query.strip()
    if not query.endswith(";"):
        query += ";"
    input_stream = InputStream(query)
    lexer = TrinoLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = TrinoParser(token_stream)
    tree = parser.parse()
    extractor = FullQueryExtractor(query)
    extractor.visit(tree)
    return FullQueryAST(extractor.select_clause, extractor.from_clause, extractor.match_recognize)
