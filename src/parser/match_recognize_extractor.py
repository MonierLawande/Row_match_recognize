# src/parser/match_recognize_extractor.py

import re
import logging
from antlr4 import InputStream, CommonTokenStream
from src.grammar.TrinoLexer import TrinoLexer
from src.grammar.TrinoParser import TrinoParser
from src.grammar.TrinoParserVisitor import TrinoParserVisitor

# Configure logging.
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
    
    If the raw_text contains a closing parenthesis, first try splitting on an "AS"
    that immediately follows a ')'. If that does not yield two parts, fall back to
    a literal split on "AS". This prevents splitting inside function names like LAST.
    """
    parts = None
    if ")" in raw_text:
        parts = re.split(r'(?<=\))AS', raw_text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return parts
    # Fallback: simple split on "AS"
    parts = re.split(r'AS', raw_text, maxsplit=1, flags=re.IGNORECASE)
    return parts

class MatchRecognizeExtractor(TrinoParserVisitor):
    def __init__(self):
        # Store components in a structured dictionary.
        self.components = {
            "partition_by": [],
            "order_by": [],
            "measures": [],
            "pattern": None,
            "subset": [],
            "define": [],
            "after_match_skip": None
        }

    def visitPatternRecognition(self, ctx:TrinoParser.PatternRecognitionContext):
        logger.debug("Visiting PatternRecognition context")
        
        # --- PARTITION BY Clause ---
        if ctx.PARTITION_():
            partitions = ctx.partition  # list of ExpressionContext
            self.components["partition_by"] = [post_process_text(expr.getText()) for expr in partitions]
            logger.debug(f"Extracted PARTITION BY: {self.components['partition_by']}")
        
        # --- ORDER BY Clause ---
        if ctx.ORDER_():
            sort_items = ctx.sortItem()  # list of SortItemContext
            self.components["order_by"] = [post_process_text(si.getText()) for si in sort_items]
            logger.debug(f"Extracted ORDER BY: {self.components['order_by']}")
        
        # --- MEASURES Clause ---
        if ctx.MEASURES_():
            measure_defs = ctx.measureDefinition()
            measures = []
            if isinstance(measure_defs, list):
                for md in measure_defs:
                    raw_text = md.getText()
                    logger.debug(f"Raw measure text: {raw_text}")
                    parts = smart_split(raw_text)
                    if len(parts) == 2:
                        measure_expr = post_process_text(parts[0])
                        alias = post_process_text(parts[1])
                        measures.append({"expression": measure_expr, "alias": alias})
                    else:
                        measures.append({"expression": post_process_text(raw_text), "alias": None})
            elif measure_defs is not None:
                raw_text = measure_defs.getText()
                logger.debug(f"Raw measure text: {raw_text}")
                parts = smart_split(raw_text)
                if len(parts) == 2:
                    measure_expr = post_process_text(parts[0])
                    alias = post_process_text(parts[1])
                    measures.append({"expression": measure_expr, "alias": alias})
                else:
                    measures.append({"expression": post_process_text(raw_text), "alias": None})
            self.components["measures"] = measures
            logger.debug(f"Extracted MEASURES: {self.components['measures']}")
        
        # --- PATTERN Clause ---
        if ctx.PATTERN_():
            row_pattern = ctx.rowPattern()
            if row_pattern:
                self.components["pattern"] = post_process_text(row_pattern.getText())
            logger.debug(f"Extracted PATTERN: {self.components['pattern']}")
        
        # --- SUBSET Clause ---
        if ctx.SUBSET_():
            subset_defs = ctx.subsetDefinition()
            subsets = []
            if isinstance(subset_defs, list):
                for sd in subset_defs:
                    subsets.append(post_process_text(sd.getText()))
            elif subset_defs is not None:
                subsets.append(post_process_text(subset_defs.getText()))
            self.components["subset"] = subsets
            logger.debug(f"Extracted SUBSET: {self.components['subset']}")
        
        # --- DEFINE Clause ---
        if ctx.DEFINE_():
            var_defs = ctx.variableDefinition()
            defines = []
            if isinstance(var_defs, list):
                for vd in var_defs:
                    raw_text = vd.getText()
                    logger.debug(f"Raw define text: {raw_text}")
                    parts = smart_split(raw_text)
                    if len(parts) == 2:
                        variable = post_process_text(parts[0])
                        condition = post_process_text(parts[1])
                        defines.append({"variable": variable, "condition": condition})
                    else:
                        defines.append({"variable": post_process_text(raw_text), "condition": None})
            elif var_defs is not None:
                raw_text = var_defs.getText()
                logger.debug(f"Raw define text: {raw_text}")
                parts = smart_split(raw_text)
                if len(parts) == 2:
                    variable = post_process_text(parts[0])
                    condition = post_process_text(parts[1])
                    defines.append({"variable": variable, "condition": condition})
                else:
                    defines.append({"variable": post_process_text(raw_text), "condition": None})
            self.components["define"] = defines
            logger.debug(f"Extracted DEFINE: {self.components['define']}")
        
        # --- AFTER MATCH SKIP Clause ---
        if ctx.AFTER_():
            skip_to = ctx.skipTo()
            if skip_to:
                self.components["after_match_skip"] = post_process_text(join_children_text(skip_to))
            logger.debug(f"Extracted AFTER MATCH SKIP: {self.components['after_match_skip']}")
        
        return self.components

def parse_match_recognize_query(query: str):
    """
    Parse a SQL query containing a MATCH_RECOGNIZE clause and extract its components.
    
    Enhancements:
      • Appends a semicolon if missing.
      • Structured extraction.
      • Uses smart_split() to split measure and define texts on 'AS'.
      • Reassembles AFTER MATCH SKIP clause from child tokens.
      • Debug logging.
    
    Args:
        query (str): SQL query string.
    
    Returns:
        dict: Dictionary of extracted MATCH_RECOGNIZE components.
    """
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

