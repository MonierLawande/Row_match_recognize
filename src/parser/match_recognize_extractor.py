from antlr4 import *
import logging
import re
from src.grammar.TrinoParser import TrinoParser
from src.grammar.TrinoParserVisitor import TrinoParserVisitor
from src.grammar.TrinoLexer import TrinoLexer
# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Custom exception for parser errors
class ParserError(Exception):
    def __init__(self, message, position=None):
        self.message = message
        self.position = position
        super().__init__(message)

# Utility functions for text processing
def post_process_text(text):
    """
    Normalize whitespace in the text.
    """
    if text is None:
        return text
    return re.sub(r'\s+', ' ', text).strip()

def join_children_text(ctx):
    """
    Join text from all children of a context with a space.
    """
    return " ".join(child.getText() for child in ctx.getChildren())

def smart_split(raw_text):
    """
    Splits the raw text on the literal "AS" (case-insensitive) into two parts.
    """
    parts = None
    if ")" in raw_text:
        parts = re.split(r'(?<=\))\s*AS\s*', raw_text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return parts
    parts = re.split(r'\s*AS\s*', raw_text, maxsplit=1, flags=re.IGNORECASE)
    return parts

class MatchRecognizeExtractor(TrinoParserVisitor):
    def __init__(self):
        self.components = {
            "partition_by": [],
            "order_by": [],
            "measures": [],
            "rows_per_match": None,
            "after_match_skip": None,
            "pattern": None,
            "subset": [],
            "define": []
        }

    def visitPatternRecognition(self, ctx: TrinoParser.PatternRecognitionContext):
        logger.debug("Visiting PatternRecognition context")
        
        # --- PARTITION BY Clause ---
        if ctx.PARTITION_():
            self.components["partition_by"] = [post_process_text(expr.getText()) for expr in ctx.partition]
            logger.debug(f"Extracted PARTITION BY: {self.components['partition_by']}")
        
        # --- ORDER BY Clause ---
        if ctx.ORDER_():
            self.components["order_by"] = [post_process_text(si.getText()) for si in ctx.sortItem()]
            logger.debug(f"Extracted ORDER BY: {self.components['order_by']}")
        
        # --- MEASURES Clause ---
        if ctx.MEASURES_():
            for md in ctx.measureDefinition():
                raw_text = md.getText()
                parts = smart_split(raw_text)
                measure = {"expression": post_process_text(parts[0]), "alias": post_process_text(parts[1])} if len(parts) == 2 else {"expression": post_process_text(raw_text), "alias": None}
                self.components["measures"].append(measure)
            logger.debug(f"Extracted MEASURES: {self.components['measures']}")
        
        # --- ROWS PER MATCH Clause ---
        if ctx.rowsPerMatch():
            self.visitRowsPerMatch(ctx.rowsPerMatch())  # Using the visitor's method
        
        # --- AFTER MATCH SKIP Clause ---
        if ctx.AFTER_():
            self.components["after_match_skip"] = post_process_text(join_children_text(ctx.skipTo()))
            logger.debug(f"Extracted AFTER MATCH SKIP: {self.components['after_match_skip']}")
        
        # --- PATTERN Clause ---
        if ctx.PATTERN_():
            self.components["pattern"] = post_process_text(ctx.rowPattern().getText())
            logger.debug(f"Extracted PATTERN: {self.components['pattern']}")
        
        # --- SUBSET Clause ---
        if ctx.SUBSET_():
            self.components["subset"] = [post_process_text(sd.getText()) for sd in ctx.subsetDefinition()]
            logger.debug(f"Extracted SUBSET: {self.components['subset']}")
        
        # --- DEFINE Clause ---
        if ctx.DEFINE_():
            for vd in ctx.variableDefinition():
                raw_text = vd.getText()
                parts = smart_split(raw_text)
                define = {"variable": post_process_text(parts[0]), "condition": post_process_text(parts[1])} if len(parts) == 2 else {"variable": post_process_text(raw_text), "condition": None}
                self.components["define"].append(define)
            logger.debug(f"Extracted DEFINE: {self.components['define']}")
        
        # Perform cross-clause validation after all clauses have been visited
        self.validate_clauses(ctx)
        
        return self.components

    def visitRowsPerMatch(self, ctx: TrinoParser.RowsPerMatchContext):
        """
        Handles the extraction of the 'ROWS PER MATCH' clause using the visitor pattern.
        """
        rows_per_match_text = post_process_text(ctx.getText())
        
        # Directly map known values with enhanced logic
        if "ONEROWPERMATCH" in rows_per_match_text:
            self.components["rows_per_match"] = "ONE ROW PER MATCH"
        elif "ALLROWSPERMATCH" in rows_per_match_text:
            self.components["rows_per_match"] = "ALL ROWS PER MATCH"
        elif "UNLIMITED" in rows_per_match_text:
            self.components["rows_per_match"] = "UNLIMITED ROWS PER MATCH"  # Example of additional logic
        else:
            self.components["rows_per_match"] = rows_per_match_text  # In case the format is different
        logger.debug(f"Extracted ROWS PER MATCH: {self.components['rows_per_match']}")

    def validate_clauses(self, ctx):
        """
        Cross-clause validation logic to ensure clause dependencies are correct.
        """
        # Example validation: Ensure ORDER BY follows PARTITION BY
        if 'PARTITION BY' in self.components and 'ORDER BY' not in self.components:
            raise ParserError("ORDER BY clause is required when PARTITION BY is used.", position=ctx.start.line)
        
        # Example validation for DEFINE and PATTERN clauses
        if 'DEFINE' in self.components and 'PATTERN' not in self.components:
            raise ParserError("PATTERN clause is required when DEFINE is used.", position=ctx.start.line)

def parse_match_recognize_query(query: str, dialect='default'):
    """
    Parse a SQL query containing a MATCH_RECOGNIZE clause and extract its components.
    """
    # Optional dialect-based parsing
    if dialect == 'trino':
        return parse_trino_query(query)
    elif dialect == 'mysql':
        return parse_mysql_query(query)
    
    query = query.strip()
    if not query.endswith(";"):
        query += ";"
    
    input_stream = InputStream(query)
    lexer = TrinoLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = TrinoParser(token_stream)
    tree = parser.singleStatement()  # Adjust entry rule if needed.
    
    extractor = MatchRecognizeExtractor()
    extractor.visit(tree)
    return extractor.components
