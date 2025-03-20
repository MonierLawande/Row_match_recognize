from antlr4 import *
import re
import logging
from antlr4.error.ErrorListener import ErrorListener
from antlr4 import InputStream, CommonTokenStream
from src.grammar.TrinoParser import TrinoParser
from src.grammar.TrinoParserVisitor import TrinoParserVisitor
from src.grammar.TrinoLexer import TrinoLexer
from src.ast.ast_nodes import (
    PartitionByClause,
    OrderByClause,   SortItem, 
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

# Ensure that ParserError is defined before it is used.
class ParserError(Exception):
    def __init__(self, message, line=None, column=None, snippet=None):
        details = message
        if line is not None and column is not None:
            details += f" (Line: {line}, Column: {column})"
        if snippet:
            details += f"\nSnippet: {snippet}"
        super().__init__(details)
        self.line = line
        self.column = column
        self.snippet = snippet

class CustomErrorListener(ErrorListener):
    def __init__(self):
        super().__init__()

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        custom_msg = (f"Syntax error at line {line}, column {column}: {msg}. "
                      "Please verify your MATCH_RECOGNIZE clause syntax according to the specification.")
        raise ParserError(custom_msg, line=line, column=column,
                          snippet=recognizer.getInputStream().getText())

from typing import List, Optional, Dict

def post_process_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return text
    return re.sub(r'\s+', ' ', text).strip()

def smart_split(raw_text):
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
    This function tracks parentheses and quotes to avoid splitting on commas that
    occur inside expressions.
    """
    items = []
    current = []
    depth = 0
    in_single_quote = False
    in_double_quote = False
    i = 0
    while i < len(select_text):
        char = select_text[i]
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
        elif not in_single_quote and not in_double_quote:
            if char == '(':
                depth += 1
                current.append(char)
            elif char == ')':
                depth -= 1
                current.append(char)
            elif char == ',' and depth == 0:
                # End of current select item.
                item = "".join(current).strip()
                if item:
                    items.append(item)
                current = []
            else:
                current.append(char)
        else:
            current.append(char)
        i += 1
    # Append the last item
    if current:
        item = "".join(current).strip()
        if item:
            items.append(item)
    return items
def parse_select_expression(item: str) -> SelectItem:
    """
    Parse a select item into its expression and alias.
    This function uses a regex to split by 'AS' at the top level.
    If no alias is found, the entire item is taken as the expression.
    """
    # This regex splits on top-level 'AS' (case-insensitive)
    # We use a simple approach assuming that the alias is not within parentheses.
    parts = re.split(r'\s+AS\s+', item, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        expr = parts[0].strip()
        alias = parts[1].strip()
    else:
        expr = item.strip()
        alias = None
    return SelectItem(expression=expr, alias=alias)
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
            logger.debug(f"Extracted Pattern: {self.ast.pattern}")

        if ctx.SUBSET_():
            self.ast.subset = self.extract_subset(ctx)
            logger.debug(f"Extracted SUBSET: {self.ast.subset}")
        if ctx.DEFINE_():
            self.ast.define = self.extract_define(ctx)
            logger.debug(f"Extracted DEFINE: {self.ast.define}")
        
        self.validate_clauses(ctx)
        self.validate_identifiers(ctx)
        self.validate_pattern_variables_defined(ctx)
        self.validate_function_usage(ctx)
        return self.ast

    def extract_partition_by(self, ctx: TrinoParser.PatternRecognitionContext) -> PartitionByClause:
        columns = [post_process_text(expr.getText()) for expr in ctx.partition]
        return PartitionByClause(columns)

    def visitRowPattern(self, ctx: TrinoParser.RowPatternContext):
        if isinstance(ctx, TrinoParser.PatternAlternationContext):
            return self.visitPatternAlternation(ctx)
        elif isinstance(ctx, TrinoParser.PatternConcatenationContext):
            return self.visitPatternConcatenation(ctx)
        elif isinstance(ctx, TrinoParser.QuantifiedPrimaryContext):
            return self.visitQuantifiedPrimary(ctx)
        return None

    def visitPatternAlternation(self, ctx: TrinoParser.PatternAlternationContext):
        patterns = [self.visit(p) for p in ctx.rowPattern()]
        return {"type": "alternation", "patterns": patterns}

    def visitQuantifiedPrimary(self, ctx: TrinoParser.QuantifiedPrimaryContext):
        pattern = self.visit(ctx.patternPrimary())
        quantifier = ctx.patternQuantifier().getText() if ctx.patternQuantifier() else None
        return {"type": "quantified", "pattern": pattern, "quantifier": quantifier}

    def visitPatternVariable(self, ctx: TrinoParser.PatternVariableContext):
        return {"type": "variable", "name": ctx.identifier().getText()}

    def extract_order_by(self, ctx: TrinoParser.PatternRecognitionContext) -> OrderByClause:
        sort_items = []
        for si in ctx.sortItem():
            column = post_process_text(si.getChild(0).getText())
            ordering = "ASC"
            nulls_ordering = None
            child_tokens = [si.getChild(i).getText() for i in range(1, si.getChildCount())]
            if "DESC" in child_tokens:
                ordering = "DESC"
            elif "ASC" in child_tokens:
                ordering = "ASC"
            if "NULLS" in child_tokens:
                null_index = child_tokens.index("NULLS")
                if null_index + 1 < len(child_tokens):
                    next_tok = child_tokens[null_index + 1]
                    if next_tok.upper() == "FIRST":
                        nulls_ordering = "NULLS FIRST"
                    elif next_tok.upper() == "LAST":
                        nulls_ordering = "NULLS LAST"
            sort_items.append(SortItem(column, ordering, nulls_ordering))
        return OrderByClause(sort_items)

    def extract_measures(self, ctx: TrinoParser.PatternRecognitionContext) -> MeasuresClause:
        measures = []
        for md in ctx.measureDefinition():
            raw_text = md.getText()
            parts = smart_split(raw_text)
            if len(parts) == 2:
                expr = post_process_text(parts[0])
                alias = post_process_text(parts[1])
            else:
                expr = post_process_text(raw_text)
                alias = None
            semantics = "RUNNING"
            if expr.upper().startswith("RUNNING "):
                semantics = "RUNNING"
                expr = expr[len("RUNNING "):].strip()
            elif expr.upper().startswith("FINAL "):
                semantics = "FINAL"
                expr = expr[len("FINAL "):].strip()
            measure_metadata = {"semantics": semantics}
            measure = Measure(expr, alias, measure_metadata)
            measures.append(measure)
        return MeasuresClause(measures)

    def extract_rows_per_match(self, ctx: TrinoParser.RowsPerMatchContext) -> RowsPerMatchClause:
        text = post_process_text(ctx.getText()).upper()
        normalized_text = text.replace(" ", "")
        if "ONEROWPERMATCH" in normalized_text:
            return RowsPerMatchClause("ONE ROW PER MATCH")
        elif "ALLROWSPERMATCH" in normalized_text:
            show_empty = True
            with_unmatched = False
            if "OMITEMPTYMATCHES" in normalized_text:
                show_empty = False
            if "WITHUNMATCHEDROWS" in normalized_text:
                with_unmatched = True
            return RowsPerMatchClause("ALL ROWS PER MATCH", show_empty, with_unmatched)
        else:
            spaced_text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
            spaced_text = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', spaced_text)
            return RowsPerMatchClause(spaced_text)

    def extract_after_match_skip(self, ctx: TrinoParser.PatternRecognitionContext) -> AfterMatchSkipClause:
        text = post_process_text(" ".join(child.getText() for child in ctx.skipTo().getChildren()))
        return AfterMatchSkipClause(text)

    def extract_pattern(self, ctx: TrinoParser.PatternRecognitionContext) -> PatternClause:
        start_index = ctx.rowPattern().start.start
        stop_index = ctx.rowPattern().stop.stop
        pattern_text = ctx.start.getInputStream().getText(start_index, stop_index)
        pattern_text = re.sub(r'\s+', ' ', pattern_text.strip())
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
        if self.ast.after_match_skip:
            skip_value = self.ast.after_match_skip.value.upper()
            tokens = skip_value.split()
            if "TO" in tokens:
                target_var = tokens[-1]
                pattern_vars = self.ast.pattern.metadata.get("base_variables", [])
                if target_var not in pattern_vars:
                    raise ParserError(f"AFTER MATCH SKIP target '{target_var}' not found in pattern variables {pattern_vars}.",
                                      line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
                if pattern_vars and target_var == pattern_vars[0]:
                    raise ParserError(f"AFTER MATCH SKIP target '{target_var}' cannot be the first element (infinite loop).",
                                      line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        self.validate_pattern_clause(ctx)

  
    def validate_function_usage(self, ctx):
        allowed_functions = {
            "COUNT": r"(?:FINAL|RUNNING)?\s*COUNT\(\s*(\*|[A-Za-z_][A-Za-z0-9_]*(?:\.\*)?(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*\)",
            "FIRST": r"(?:FINAL|RUNNING)?\s*FIRST\(\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)(?:\s*,\s*\d+)?\s*\)",
            "LAST":  r"(?:FINAL|RUNNING)?\s*LAST\(\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)(?:\s*,\s*\d+)?\s*\)",
            "PREV":  r"(?:FINAL|RUNNING)?\s*PREV\(\s*((?:(?:FIRST|LAST)\([^()]+\))|(?:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?))\s*(?:,\s*\d+)?\s*\)",
            "NEXT":  r"(?:FINAL|RUNNING)?\s*NEXT\(\s*((?:(?:FIRST|LAST)\([^()]+\))|(?:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?))\s*(?:,\s*\d+)?\s*\)",
        }
        if self.ast.measures:
            for measure in self.ast.measures.measures:
                expr_upper = measure.expression.upper()
                for func, pattern in allowed_functions.items():
                    if func in expr_upper:
                        m = re.search(pattern, expr_upper)
                        if not m:
                            raise ParserError(
                                f"Invalid usage of {func} in measure: {measure.expression}",
                                line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText()
                            )
                logger.debug(f"Validated function usage for measure: {measure.expression}")

    def validate_pattern_clause(self, ctx):
        """Additional checks for the PATTERN clause syntax."""
        if self.ast.pattern:
            pattern_text = self.ast.pattern.pattern.strip()
            # Check for an empty pattern.
            if pattern_text == "()":
                # Empty match is allowed, but later evaluation should produce null values.
                pass

            # Additional Validation: Ensure balanced parentheses.
            open_parens = pattern_text.count("(")
            close_parens = pattern_text.count(")")
            if open_parens != close_parens:
                raise ParserError(
                    "Unbalanced parentheses in PATTERN clause.",
                    line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText()
                )

            # Example: if exclusion syntax is used with WITH UNMATCHED ROWS, raise an error.
            if self.ast.rows_per_match and "WITH UNMATCHED ROWS" in self.ast.rows_per_match.mode.upper():
                if "{-" in pattern_text and "-}" in pattern_text:
                    raise ParserError(
                        "Pattern exclusions are not allowed with ALL ROWS PER MATCH WITH UNMATCHED ROWS.",
                        line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText()
                    )
            # (Optional) Additional checks on quantifiers and grouping could be added here.
            logger.debug(f"PATTERN clause validated successfully: {pattern_text}")

    def validate_identifiers(self, ctx):
        # Compare the base variables (from PATTERN) with variables defined in DEFINE.
        if self.ast.pattern:
            pattern_vars = set(self.ast.pattern.metadata.get("base_variables", []))
        else:
            pattern_vars = set()
        
        if self.ast.define:
            for definition in self.ast.define.definitions:
                # Do a case-sensitive check.
                if definition.variable not in pattern_vars:
                    raise ParserError(
                        f"Define variable '{definition.variable}' not found in pattern base variables {pattern_vars}. "
                        "Hint: Ensure that each variable defined in the DEFINE clause appears exactly (case-sensitively) in the PATTERN clause.",
                        line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText()
                    )

    def validate_pattern_variables_defined(self, ctx):
        """
        Validate that every base variable in the PATTERN clause is defined in the DEFINE clause,
        and that there are no extra definitions.
        """
        if self.ast.pattern:
            pattern_vars = set(self.ast.pattern.metadata.get("base_variables", []))
        else:
            pattern_vars = set()
        
        defined_vars = set()
        if self.ast.define:
            for definition in self.ast.define.definitions:
                defined_vars.add(definition.variable)
        
        missing = pattern_vars - defined_vars
        extra = defined_vars - pattern_vars
        
        if missing:
            raise ParserError(
                f"All pattern variables must be explicitly defined. Missing definitions for: {missing}",
                line=ctx.start.line,
                column=ctx.start.column,
                snippet=ctx.getText()
            )
        if extra:
            raise ParserError(
                f"Defined variable(s) {extra} not found in the PATTERN clause.",
                line=ctx.start.line,
                column=ctx.start.column,
                snippet=ctx.getText()
            )

###############################################
# Full Query extractor visitor for SELECT/FROM/MATCH_RECOGNIZE
###############################################
class FullQueryExtractor(TrinoParserVisitor):
    def __init__(self, original_query: str):
        self.original_query = original_query
        self.select_clause = None
        self.from_clause = None
        self.match_recognize = None

    def visitParse(self, ctx: TrinoParser.ParseContext):
        return self.visitChildren(ctx)

    def visitSingleStatement(self, ctx: TrinoParser.SingleStatementContext):
            full_text = post_process_text(self.original_query)
            logger.debug(f"Full statement text: {full_text}")

            # Extract SELECT clause by finding text between SELECT and FROM
            select_match = re.search(r'(?i)^SELECT\s+(.+?)\s+FROM', full_text, re.DOTALL)
            if select_match:
                select_text = select_match.group(1)
                items_raw = split_select_items(select_text)
                items = [parse_select_expression(item) for item in items_raw]
                self.select_clause = SelectClause(items)
                logger.debug(f"Extracted SELECT clause via robust splitting: {self.select_clause}")
            else:
                logger.warning("No SELECT clause found via regex.")

            # (The rest of the extraction for FROM and MATCH_RECOGNIZE remains as before)
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
    parser.removeErrorListeners()
    parser.addErrorListener(CustomErrorListener())
    tree = parser.parse()
    extractor = FullQueryExtractor(query)
    extractor.visit(tree)
    return FullQueryAST(extractor.select_clause, extractor.from_clause, extractor.match_recognize)