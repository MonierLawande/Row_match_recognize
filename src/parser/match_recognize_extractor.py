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
from src.parser.error_listeners import ParserError, CustomErrorListener

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from typing import List, Optional, Dict


def smart_split(raw_text):
    parts = None
    if ")" in raw_text:
        parts = re.split(r'(?<=\))\s*AS\s*', raw_text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return parts
    parts = re.split(r'\s*AS\s*', raw_text, maxsplit=1, flags=re.IGNORECASE)
    return parts





def post_process_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return text
    return re.sub(r'\s+', ' ', text).strip()


def robust_split_select_items(select_text: str) -> List[str]:
    items = []
    current = []
    depth = 0
    in_single_quote = False
    in_double_quote = False
    escape_next = False
    for char in select_text:
        if escape_next:
            current.append(char)
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            current.append(char)
            continue
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
            continue
        if not in_single_quote and not in_double_quote:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
        if char == ',' and depth == 0 and not in_single_quote and not in_double_quote:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        items.append("".join(current).strip())
    return items


def parse_select_clause(full_text: str) -> SelectClause:
    select_match = re.search(r'(?i)^SELECT\s+(.+?)\s+FROM\s', full_text)
    if not select_match:
        raise ParserError("SELECT clause not found or malformed in the query.", snippet=full_text)
    select_text = select_match.group(1)
    items_raw = robust_split_select_items(select_text)
    items = []
    for item in items_raw:
        item = post_process_text(item)
        alias_match = re.search(r'(?i)^(.+?)\s+AS\s+(.+)$', item)
        if alias_match:
            expr = post_process_text(alias_match.group(1))
            alias = post_process_text(alias_match.group(2))
            items.append(SelectItem(expr, alias))
        else:
            items.append(SelectItem(item))
    return SelectClause(items)


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
        if self.ast.define and self.ast.pattern:
            defined_vars = [d.variable for d in self.ast.define.definitions]
            self.ast.pattern.update_from_defined(defined_vars)
            logger.debug(f"Updated Pattern tokens: {self.ast.pattern.metadata}")
           
            
        self.validate_clauses(ctx)
        self.validate_identifiers(ctx)
        self.validate_pattern_variables_defined(ctx)
        self.validate_function_usage(ctx)
        return self.ast
    
    def extract_partition_by(self, ctx):
        return PartitionByClause([post_process_text(expr.getText()) for expr in ctx.partition])

    def extract_order_by(self, ctx):
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
                    next_tok = child_tokens[null_index + 1].upper()
                    if next_tok == "FIRST":
                        nulls_ordering = "NULLS FIRST"
                    elif next_tok == "LAST":
                        nulls_ordering = "NULLS LAST"
            sort_items.append(SortItem(column, ordering, nulls_ordering))
        return OrderByClause(sort_items)

    def extract_measures(self, ctx):
        measures = []
        for md in ctx.measureDefinition():
            raw_text = md.getText()
            semantics = "RUNNING"
            raw_expr = raw_text.strip()
            if raw_expr.upper().startswith("RUNNING "):
                raw_expr = raw_expr[len("RUNNING "):].strip()
            elif raw_expr.upper().startswith("FINAL "):
                semantics = "FINAL"
                raw_expr = raw_expr[len("FINAL "):].strip()

            parts = smart_split(raw_expr)
            if len(parts) == 2:
                expr, alias = post_process_text(parts[0]), post_process_text(parts[1])
            else:
                expr, alias = post_process_text(raw_expr), None

            measure_metadata = {"semantics": semantics}
            measures.append(Measure(expr, alias, measure_metadata))
        return MeasuresClause(measures)

    def extract_rows_per_match(self, ctx):
        """Extract the ROWS PER MATCH clause."""
        # ctx is already a RowsPerMatchContext, so we don't need to call ctx.rowsPerMatch()
        
        # Get the raw text
        raw_mode = self.get_text(ctx)
        logger.debug(f"Extracted ROWS PER MATCH: {raw_mode}")
        
        # Create the appropriate RowsPerMatchClause object based on the mode
        if "ONE ROW PER MATCH" in raw_mode.upper():
            return RowsPerMatchClause.one_row_per_match()
        elif "ALL ROWS PER MATCH" in raw_mode.upper():
            with_unmatched = "WITH UNMATCHED ROWS" in raw_mode.upper()
            if "OMIT EMPTY MATCHES" in raw_mode.upper():
                return RowsPerMatchClause("ALL ROWS PER MATCH", show_empty=False, with_unmatched=with_unmatched)
            else:  # Default is SHOW EMPTY MATCHES
                return RowsPerMatchClause("ALL ROWS PER MATCH", show_empty=True, with_unmatched=with_unmatched)
        else:
            # Fallback to raw mode if we can't determine the specific type
            return RowsPerMatchClause(raw_mode)
    def get_text(self, ctx):
        """Get the text representation of a parse tree node."""
        if ctx is None:
            return ""
        if hasattr(ctx, 'getText'):
            return ctx.getText()
        start = ctx.start.start
        stop = ctx.stop.stop
        return ctx.start.getInputStream().getText(start, stop)

    def extract_after_match_skip(self, ctx):
        return AfterMatchSkipClause(post_process_text(" ".join(child.getText() for child in ctx.skipTo().getChildren())))

    def extract_pattern(self, ctx: TrinoParser.PatternRecognitionContext) -> PatternClause:
        """
        Extract the pattern from the pattern recognition context.
        This method gets the raw pattern text and creates a PatternClause object.
        """
        # Get the raw pattern text
        pattern_text = None
        if ctx.rowPattern():
            # Get the text between parentheses
            pattern_text = ctx.rowPattern().getText()
            if pattern_text.startswith('(') and pattern_text.endswith(')'):
                pattern_text = pattern_text[1:-1].strip()
            
            # Create the pattern clause with the cleaned pattern text
            pattern_clause = PatternClause(pattern_text)
            
            # If we have a DEFINE clause, use it to guide tokenization
            if ctx.DEFINE_():
                defined_vars = []
                for vd in ctx.variableDefinition():
                    var_name = vd.identifier().getText()
                    defined_vars.append(var_name)
                
                # Update pattern tokenization with defined variables
                if defined_vars:
                    pattern_clause.update_from_defined(defined_vars)
                    logger.debug(f"Updated Pattern tokens: {pattern_clause.metadata}")
                    logger.debug(f"PATTERN clause validated successfully: {pattern_text}")
            
            return pattern_clause
        return PatternClause("")  # Return empty pattern clause if no pattern found


    def extract_subset(self, ctx):
        return [SubsetClause(post_process_text(sd.getText())) for sd in ctx.subsetDefinition()]

    def extract_define(self, ctx):
        definitions = []
        for vd in ctx.variableDefinition():
            raw_text = vd.getText()
            parts = smart_split(raw_text)
            if len(parts) == 2:
                definitions.append(Define(post_process_text(parts[0]), post_process_text(parts[1])))
            else:
                definitions.append(Define(post_process_text(raw_text), ""))
        return DefineClause(definitions)

    def validate_clauses(self, ctx):
        if self.ast.define and not self.ast.pattern:
            raise ParserError("PATTERN clause is required when DEFINE is used.", line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        if self.ast.after_match_skip:
            skip_value = self.ast.after_match_skip.value.upper().split()
            if "TO" in skip_value:
                target_var = skip_value[-1]
                pattern_vars = self.ast.pattern.metadata.get("base_variables", [])
                if target_var not in pattern_vars:
                    raise ParserError(f"AFTER MATCH SKIP target '{target_var}' not found in pattern variables {pattern_vars}.", line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
                if pattern_vars and target_var == pattern_vars[0]:
                    raise ParserError(f"AFTER MATCH SKIP target '{target_var}' cannot be the first element (infinite loop).", line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        self.validate_pattern_clause(ctx)

    def validate_pattern_clause(self, ctx):
        if not self.ast.pattern:
            return
        pattern_text = self.ast.pattern.pattern.strip()
        if pattern_text == "()":
            return
        if pattern_text.count("(") != pattern_text.count(")"):
            raise ParserError("Unbalanced parentheses in PATTERN clause.", line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        if self.ast.rows_per_match and "WITH UNMATCHED ROWS" in self.ast.rows_per_match.mode.upper():
            if "{-" in pattern_text and "-}" in pattern_text:
                raise ParserError("Pattern exclusions are not allowed with ALL ROWS PER MATCH WITH UNMATCHED ROWS.", line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        logger.debug(f"PATTERN clause validated successfully: {pattern_text}")

    def validate_function_usage(self, ctx):
        allowed_functions = {
            "COUNT": r"(?:FINAL|RUNNING)?\s*COUNT\(\s*(\*|[\w.]+\*?)\s*\)",
            "FIRST": r"(?:FINAL|RUNNING)?\s*FIRST\(\s*[\w.]+(?:\s*,\s*\d+)?\s*\)",
            "LAST":  r"(?:FINAL|RUNNING)?\s*LAST\(\s*[\w.]+(?:\s*,\s*\d+)?\s*\)",
            "PREV":  r"(?:FINAL|RUNNING)?\s*PREV\(\s*.+?(?:,\s*\d+)?\s*\)",
            "NEXT":  r"(?:FINAL|RUNNING)?\s*NEXT\(\s*.+?(?:,\s*\d+)?\s*\)",
        }
        for measure in self.ast.measures.measures if self.ast.measures else []:
            for func, pattern in allowed_functions.items():
                if re.search(func, measure.expression, flags=re.IGNORECASE):
                    if not re.search(pattern, measure.expression, flags=re.IGNORECASE):
                        raise ParserError(f"Invalid usage of {func} in measure: {measure.expression}", line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
            logger.debug(f"Validated function usage for measure: {measure.expression}")

    def validate_identifiers(self, ctx):
        pattern_vars = set(self.ast.pattern.metadata.get("base_variables", [])) if self.ast.pattern else set()
        for definition in self.ast.define.definitions if self.ast.define else []:
            if definition.variable not in pattern_vars:
                raise ParserError(f"Define variable '{definition.variable}' not found in pattern base variables {pattern_vars}.", line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
    
    def validate_pattern_variables_defined(self, ctx):
        if not self.ast.pattern:
            return
        
        # Get pattern variables and defined variables
        pattern_vars = set(self.ast.pattern.metadata.get("base_variables", []))
        defined_vars = {d.variable for d in self.ast.define.definitions} if self.ast.define else set()
        
        # Get subset variables and their mappings
        subset_vars = {}
        if self.ast.subset:
            for subset_clause in self.ast.subset:
                subset_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\((.*?)\)', subset_clause.subset_text)
                if subset_match:
                    subset_name = subset_match.group(1)
                    subset_elements = [v.strip() for v in subset_match.group(2).split(',')]
                    subset_vars[subset_name] = subset_elements
                    logger.debug(f"Extracted subset mapping: {subset_name} -> {subset_elements}")
        
        # Track all referenced variables
        referenced_vars = set()
        
        # 1. Check variables used in MEASURES
        if self.ast.measures:
            for measure in self.ast.measures.measures:
                # Extract variables from column references like A.totalprice
                column_refs = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*', measure.expression)
                referenced_vars.update(column_refs)
                
                # Extract variables from functions like FIRST(A), LAST(A), etc.
                # Only match standalone variables, not those in column references
                func_pattern = r'(?:FIRST|LAST|PREV|NEXT)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)(?:\s*(?:,|\))\s*)'
                func_refs = re.findall(func_pattern, measure.expression, re.IGNORECASE)
                # Filter out variables that are part of column references
                func_refs = [v for v in func_refs if not re.search(f'{v}\\.[A-Za-z_]', measure.expression)]
                referenced_vars.update(func_refs)
                
                # Extract variables from CLASSIFIER function
                classifier_refs = re.findall(r'CLASSIFIER\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)', 
                                        measure.expression, re.IGNORECASE)
                referenced_vars.update(classifier_refs)
                
                logger.debug(f"Extracted variables from measure '{measure.expression}': {list(set(column_refs + func_refs + classifier_refs))}")
        
        # 2. Check variables used in SUBSET
        if self.ast.subset:
            for subset_clause in self.ast.subset:
                # Extract the subset elements
                subset_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\((.*?)\)', subset_clause.subset_text)
                if subset_match:
                    subset_elements = [v.strip() for v in subset_match.group(2).split(',')]
                    referenced_vars.update(subset_elements)
                    logger.debug(f"Extracted variables from subset '{subset_clause.subset_text}': {subset_elements}")
        
        # 3. Check variables used in AFTER MATCH SKIP
        if self.ast.after_match_skip:
            skip_text = self.ast.after_match_skip.value.upper()
            if "TO" in skip_text:
                # Extract variable after "TO"
                skip_match = re.search(r'TO\s+([A-Za-z_][A-Za-z0-9_]*)', skip_text)
                if skip_match:
                    target_var = skip_match.group(1)
                    referenced_vars.add(target_var)
                    logger.debug(f"Extracted variable from AFTER MATCH SKIP: {target_var}")
        
        # 4. Check variables used in DEFINE conditions
        if self.ast.define:
            for define in self.ast.define.definitions:
                # Extract variables from column references in conditions (pattern variables)
                column_refs = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*', define.condition)
                referenced_vars.update(column_refs)
                
                # Extract variables from functions in conditions
                # Only match pattern variables in functions, not column names
                func_pattern = r'(?:FIRST|LAST|PREV|NEXT)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*\s*\)'
                func_refs = re.findall(func_pattern, define.condition, re.IGNORECASE)
                referenced_vars.update(func_refs)
                
                # For PREV/NEXT without explicit variable, the current row variable is implied
                # We don't need to add anything to referenced_vars in this case
                
                extracted_vars = list(set(column_refs + func_refs))
                logger.debug(f"Extracted variables from define condition '{define.condition}': {extracted_vars}")
        
        # Check for missing definitions and extra definitions
        # Subset variables should be considered as valid references
        missing = referenced_vars - pattern_vars - set(subset_vars.keys())
        extra = defined_vars - pattern_vars
        
        # Also verify that all subset elements are valid pattern variables
        for subset_name, elements in subset_vars.items():
            invalid_elements = set(elements) - pattern_vars
            if invalid_elements:
                raise ParserError(f"Subset '{subset_name}' contains undefined pattern variables: {invalid_elements}", 
                                line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        
        if missing:
            raise ParserError(f"Referenced variable(s) {missing} not found in the PATTERN clause or SUBSET definitions.", 
                            line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        
        if extra:
            raise ParserError(f"Defined variable(s) {extra} not found in the PATTERN clause.", 
                            line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        
        # Log the validation results
        logger.debug(f"Pattern variables: {pattern_vars}")
        logger.debug(f"Referenced variables: {referenced_vars}")
        logger.debug(f"Defined variables: {defined_vars}")
        logger.debug(f"Subset variables: {subset_vars}")



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
        try:
            self.select_clause = parse_select_clause(full_text)
            logger.debug(f"Extracted SELECT clause: {self.select_clause}")
        except ParserError as pe:
            logger.error(f"Error parsing SELECT clause: {pe}")
            raise
        from_match = re.search(r'(?i)FROM\s+(\w+)', full_text)
        if from_match:
            self.from_clause = FromClause(from_match.group(1))
            logger.debug(f"Extracted FROM clause: {self.from_clause}")
        else:
            logger.warning("No FROM clause found via regex.")
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
            if result:
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
