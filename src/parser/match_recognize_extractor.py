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
        """Extract pattern recognition components in the correct order."""
        logger.debug("Visiting PatternRecognition context")
        
        # 1. PARTITION BY (optional)
        if hasattr(ctx, 'PARTITION_') and ctx.PARTITION_():
            self.ast.partition_by = self.extract_partition_by(ctx)
            logger.debug(f"Extracted PARTITION BY: {self.ast.partition_by}")
        
        # 2. ORDER BY (optional)
        if hasattr(ctx, 'ORDER_') and ctx.ORDER_():
            self.ast.order_by = self.extract_order_by(ctx)
            logger.debug(f"Extracted ORDER BY: {self.ast.order_by}")
        
        # 3. MEASURES (optional)
        if hasattr(ctx, 'MEASURES_') and ctx.MEASURES_():
            self.ast.measures = self.extract_measures(ctx)
            logger.debug(f"Extracted MEASURES: {self.ast.measures}")
        
        # 4. ROWS PER MATCH (optional)
        if hasattr(ctx, 'rowsPerMatch') and ctx.rowsPerMatch():
            self.ast.rows_per_match = self.extract_rows_per_match(ctx.rowsPerMatch())
            logger.debug(f"Extracted ROWS PER MATCH: {self.ast.rows_per_match}")
        
        # 5. AFTER MATCH SKIP (optional)
        if hasattr(ctx, 'AFTER_') and ctx.AFTER_():
            self.ast.after_match_skip = self.extract_after_match_skip(ctx)
            logger.debug(f"Extracted AFTER MATCH SKIP: {self.ast.after_match_skip}")
        
        # 6. PATTERN (required)
        if ctx.PATTERN_():
            self.ast.pattern = self.extract_pattern(ctx)
            logger.debug(f"Extracted Pattern: {self.ast.pattern}")
        else:
            raise ParserError("PATTERN clause is required in MATCH_RECOGNIZE",
                            line=ctx.start.line, column=ctx.start.column)
        
        # 7. SUBSET (optional)
        if hasattr(ctx, 'SUBSET_') and ctx.SUBSET_():
            self.ast.subset = self.extract_subset(ctx)
            logger.debug(f"Extracted SUBSET: {self.ast.subset}")
        
        # 8. DEFINE (optional)
        if hasattr(ctx, 'DEFINE_') and ctx.DEFINE_():
            self.ast.define = self.extract_define(ctx)
            logger.debug(f"Extracted DEFINE: {self.ast.define}")
        
        # Update pattern with definitions if needed
        if self.ast.define and self.ast.pattern:
            defined_vars = [d.variable for d in self.ast.define.definitions]
            self.ast.pattern.update_from_defined(defined_vars)
            logger.debug(f"Updated Pattern tokens: {self.ast.pattern.metadata}")
        
        # Run validations
        self.validate_clauses(ctx)
        self.validate_identifiers(ctx)
        self.validate_pattern_variables_defined(ctx)
        self.validate_function_usage(ctx)
        
        return self.ast
    # Add this method to the MatchRecognizeExtractor class in src/parser/match_recognize_extractor.py

    def extract_subset(self, ctx: TrinoParser.PatternRecognitionContext) -> List[SubsetClause]:
        """Extract SUBSET clause information.
        
        The SUBSET clause defines union variables as combinations of primary pattern variables.
        For example: SUBSET X = (A, B), Y = (B, C)
        
        Args:
            ctx: The pattern recognition context
        
        Returns:
            List of SubsetClause objects
        """
        subset_clauses = []
        
        # Check if we have a SUBSET_ token and subsetDefinition contexts
        if hasattr(ctx, 'SUBSET_') and ctx.SUBSET_() and hasattr(ctx, 'subsetDefinition'):
            for subset_def in ctx.subsetDefinition():
                # Get the original text directly from the input stream
                start = subset_def.start.start
                stop = subset_def.stop.stop
                subset_text = subset_def.start.getInputStream().getText(start, stop)
                
                # Create a SubsetClause object with the raw text
                subset_clauses.append(SubsetClause(subset_text))
                
                # Debug output
                print(f"Extracted subset definition: {subset_text}")
        
        return subset_clauses

    def _parse_skip_text(self, skip_text: str) -> AfterMatchSkipClause:
        """Parse the AFTER MATCH SKIP clause text extracted from raw SQL."""
        skip_text = skip_text.strip().upper()
        
        if "PAST LAST ROW" in skip_text:
            return AfterMatchSkipClause('PAST LAST ROW', raw_value=f"AFTER MATCH SKIP {skip_text}")
        
        elif "TO NEXT ROW" in skip_text:
            return AfterMatchSkipClause('TO NEXT ROW', raw_value=f"AFTER MATCH SKIP {skip_text}")
        
        elif "TO FIRST" in skip_text:
            # Extract the variable after "TO FIRST"
            match = re.search(r'TO\s+FIRST\s+([A-Za-z_][A-Za-z0-9_]*)', skip_text)
            if match:
                target_var = match.group(1)
                return AfterMatchSkipClause('TO FIRST', target_var, raw_value=f"AFTER MATCH SKIP {skip_text}")
        
        elif "TO LAST" in skip_text:
            # Extract the variable after "TO LAST" 
            match = re.search(r'TO\s+LAST\s+([A-Za-z_][A-Za-z0-9_]*)', skip_text)
            if match:
                target_var = match.group(1)
                return AfterMatchSkipClause('TO LAST', target_var, raw_value=f"AFTER MATCH SKIP {skip_text}")
        
        # Default to PAST LAST ROW if we can't determine the mode
        return AfterMatchSkipClause('PAST LAST ROW', raw_value=f"AFTER MATCH SKIP {skip_text}")

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
            semantics = "RUNNING"  # Default semantics
            raw_expr = raw_text.strip()
            
            # Use regex to match RUNNING or FINAL with flexible whitespace
            running_match = re.match(r'(?i)RUNNING\s+', raw_expr)
            final_match = re.match(r'(?i)FINAL\s+', raw_expr)
            
            if running_match:
                raw_expr = raw_expr[running_match.end():].strip()
            elif final_match:
                semantics = "FINAL"
                raw_expr = raw_expr[final_match.end():].strip()
            
            # Alternative: If the expression is already concatenated (e.g., "FINALLAST")
            elif raw_expr.upper().startswith("RUNNING"):
                # Extract function name after "RUNNING"
                function_match = re.match(r'(?i)RUNNING([A-Z]+)', raw_expr)
                if function_match:
                    func_name = function_match.group(1)
                    raw_expr = func_name + raw_expr[len("RUNNING" + func_name):]
            elif raw_expr.upper().startswith("FINAL"):
                semantics = "FINAL"
                # Extract function name after "FINAL"
                function_match = re.match(r'(?i)FINAL([A-Z]+)', raw_expr)
                if function_match:
                    func_name = function_match.group(1)
                    raw_expr = func_name + raw_expr[len("FINAL" + func_name):]

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
        """Extract and parse the AFTER MATCH SKIP clause."""
        # Get the skipTo context
        skip_to_ctx = ctx.skipTo()
        if not skip_to_ctx:
            return None
        
        # Use direct input stream access to get text
        start = skip_to_ctx.start.start
        stop = skip_to_ctx.stop.stop
        skip_to_text = skip_to_ctx.start.getInputStream().getText(start, stop)
        skip_to_text = post_process_text(skip_to_text)
        
        # Use regex to completely remove SKIP keyword at the beginning (case-insensitive)
        skip_to_text = re.sub(r'^\s*SKIP\s+', '', skip_to_text, flags=re.IGNORECASE)
        
        # Add the prefix properly
        raw_text = f"AFTER MATCH SKIP {skip_to_text}"
        logger.debug(f"Extracting AFTER MATCH SKIP clause: {raw_text}")
        
        # Check for each type of skip clause
        lower_text = raw_text.upper()
        
        if "PAST LAST ROW" in lower_text:
            return AfterMatchSkipClause('PAST LAST ROW', raw_value=raw_text)
        
        elif "TO NEXT ROW" in lower_text:
            return AfterMatchSkipClause('TO NEXT ROW', raw_value=raw_text)
        
        elif "TO FIRST" in lower_text:
            # Extract the variable after "TO FIRST"
            match = re.search(r'TO\s+FIRST\s+([A-Za-z_][A-Za-z0-9_]*)', raw_text, re.IGNORECASE)
            if match:
                return AfterMatchSkipClause('TO FIRST', match.group(1), raw_value=raw_text)
            else:
                raise ParserError("Invalid AFTER MATCH SKIP TO FIRST clause", snippet=raw_text)
        
        elif "TO LAST" in lower_text:
            # Extract the variable after "TO LAST"
            match = re.search(r'TO\s+LAST\s+([A-Za-z_][A-Za-z0-9_]*)', raw_text, re.IGNORECASE)
            if match:
                return AfterMatchSkipClause('TO LAST', match.group(1), raw_value=raw_text)
            else:
                raise ParserError("Invalid AFTER MATCH SKIP TO LAST clause", snippet=raw_text)
        
        elif "TO" in lower_text:
            # Handle "TO" without FIRST/LAST or with NEXT ROW
            match = re.search(r'TO\s+([A-Za-z_][A-Za-z0-9_]*)', raw_text, re.IGNORECASE)
            if match:
                target_var = match.group(1)
                if target_var.upper() == "NEXT" and "ROW" in lower_text.split(target_var.upper(), 1)[1]:
                    return AfterMatchSkipClause('TO NEXT ROW', raw_value=raw_text)
                else:
                    return AfterMatchSkipClause('TO LAST', target_var, raw_value=raw_text)
            else:
                raise ParserError("Invalid AFTER MATCH SKIP TO clause", snippet=raw_text)
        
        else:
            # Custom or unrecognized mode
            logger.warning(f"Using raw AFTER MATCH SKIP value: {raw_text}")
            return AfterMatchSkipClause(raw_text, raw_value=raw_text)

    def extract_define(self, ctx: TrinoParser.PatternRecognitionContext) -> DefineClause:
        """Extract and parse the DEFINE clause from pattern recognition context."""
        definitions = []
        
        # Check if DEFINE clause exists
        if ctx.DEFINE_() and ctx.variableDefinition():
            for var_def in ctx.variableDefinition():
                # Get variable name
                variable = var_def.identifier().getText() if var_def.identifier() else None
                
                # Get condition expression
                if var_def.expression():
                    # Get the original condition text directly from the input stream
                    start = var_def.expression().start.start
                    stop = var_def.expression().stop.stop
                    condition = var_def.expression().start.getInputStream().getText(start, stop)
                    
                    # Special handling for TRUE/FALSE constants - normalize casing
                    if condition.upper() == "TRUE" or condition.upper() == "FALSE":
                        condition = condition.upper()
                    
                    # Add to definitions if both variable and condition are present
                    if variable and condition:
                        definitions.append(Define(variable, condition))
        
        return DefineClause(definitions)
  
    def extract_pattern(self, ctx: TrinoParser.PatternRecognitionContext) -> PatternClause:
        """
        Extract the pattern from the pattern recognition context.
        This method gets the raw pattern text and creates a PatternClause object.
        """
        # Get the raw pattern text
        pattern_text = None
        if ctx.rowPattern():
            # Get the original text directly from the input stream
            start = ctx.rowPattern().start.start
            stop = ctx.rowPattern().stop.stop
            original_pattern = ctx.rowPattern().start.getInputStream().getText(start, stop)
            
            # Check for empty pattern '()'
            if original_pattern.strip() == '()':
                pattern_clause = PatternClause(original_pattern)
                pattern_clause.metadata = {
                    "variables": [],
                    "base_variables": [],
                    "empty_pattern": True,
                    "allows_any_variable": True
                }
                return pattern_clause
                
            # Remove only the outer parentheses if they exist
            if original_pattern.startswith('(') and original_pattern.endswith(')'):
                pattern_text = original_pattern[1:-1]
            else:
                pattern_text = original_pattern
            
            # Create the pattern clause with the original pattern text
            pattern_clause = PatternClause(pattern_text)
            
            # Extract subset definitions
            subset_vars = {}
            if ctx.SUBSET_():
                for sd in ctx.subsetDefinition():
                    subset_text = sd.getText()
                    # Parse subset definition (e.g. "MOVE = (UP, DOWN)")
                    match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\((.*?)\)', subset_text)
                    if match:
                        subset_name = match.group(1)
                        components = [c.strip() for c in match.group(2).split(',')]
                        subset_vars[subset_name] = components
            
            # If we have a DEFINE clause, use it to guide tokenization
            if ctx.DEFINE_():
                defined_vars = []
                for vd in ctx.variableDefinition():
                    var_name = vd.identifier().getText()
                    defined_vars.append(var_name)
                
                # Update pattern tokenization with defined variables and subsets
                if defined_vars:
                    pattern_clause.update_from_defined(defined_vars, subset_vars)
                    logger.debug(f"Updated Pattern tokens: {pattern_clause.metadata}")
                    logger.debug(f"PATTERN clause validated successfully: {pattern_text}")
            
            return pattern_clause
        return PatternClause("")  # Return empty pattern clause if no pattern found


    def validate_clauses(self, ctx):
        """Validate required clauses and relationships between clauses."""
        if self.ast.define and not self.ast.pattern:
            raise ParserError("PATTERN clause is required when DEFINE is used.", 
                            line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        
        if self.ast.after_match_skip and self.ast.pattern and not self.ast.pattern.metadata.get("empty_pattern", False):
            mode = self.ast.after_match_skip.mode
            target_var = self.ast.after_match_skip.target_variable
            
            if mode in ['TO FIRST', 'TO LAST'] and target_var:
                pattern_vars = self.ast.pattern.metadata.get("base_variables", [])
                
                # Check if the target variable exists in the pattern
                if target_var not in pattern_vars:
                    raise ParserError(
                        f"AFTER MATCH SKIP target '{target_var}' not found in pattern variables {pattern_vars}.",
                        line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText()
                    )
                
                # Check for infinite loop - cannot skip to the first variable in the pattern
                if pattern_vars and target_var == pattern_vars[0]:
                    if mode == 'TO FIRST' or (mode == 'TO LAST' and len(pattern_vars) == 1):
                        raise ParserError(
                            f"AFTER MATCH SKIP {mode} {target_var} would create an infinite loop "
                            f"because {target_var} is the first pattern variable.",
                            line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText()
                        )
        
        # Skip some validations for empty patterns
        if not self.ast.pattern or self.ast.pattern.metadata.get("empty_pattern", False):
            return
            
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
        """Validate that all defined variables are found in the pattern or as subset components."""
        # Special case for empty patterns - skip validation
        if self.ast.pattern and (self.ast.pattern.metadata.get("empty_pattern", False) or 
                                self.ast.pattern.pattern.strip() == "()"):
            logger.debug("Empty pattern detected in validate_identifiers - skipping validation")
            return
            
        pattern_vars = set(self.ast.pattern.metadata.get("base_variables", [])) if self.ast.pattern else set()
        
        # Extract subset component variables
        subset_components = set()
        if self.ast.subset:
            for subset_clause in self.ast.subset:
                subset_text = subset_clause.subset_text
                match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\((.*?)\)', subset_text)
                if match:
                    subset_name = match.group(1)
                    components = [c.strip() for c in match.group(2).split(',')]
                    # If the subset union variable is in the pattern, its components are valid
                    if subset_name in pattern_vars:
                        subset_components.update(components)
        
        # All valid variables: direct pattern variables + subset components
        valid_vars = pattern_vars.union(subset_components)
        
        # Check that all defined variables are valid
        for definition in self.ast.define.definitions if self.ast.define else []:
            if definition.variable not in valid_vars:
                # Skip this check for empty pattern
                if self.ast.pattern and (self.ast.pattern.pattern.strip() == "()" or 
                                        self.ast.pattern.metadata.get("empty_pattern", False)):
                    return
                    
                raise ParserError(
                    f"Define variable '{definition.variable}' not found in pattern or subset components.", 
                    line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText()
                )


    def validate_pattern_variables_defined(self, ctx):
        """Validate pattern variable definitions and references."""
        if not self.ast.pattern:
            return
        
        # Special case for empty patterns - skip validation using robust detection
        pattern_text = self.ast.pattern.pattern.strip()
        is_empty_pattern = pattern_text == "()" or re.match(r'^\s*\(\s*\)\s*$', pattern_text)
        
        if is_empty_pattern or self.ast.pattern.metadata.get("empty_pattern", False):
            logger.debug("Empty pattern detected - skipping variable validation")
            return
            
        # Get pattern variables and defined variables (case-sensitive)
        pattern_vars = set(self.ast.pattern.metadata.get("base_variables", []))
        defined_vars = {d.variable for d in self.ast.define.definitions} if self.ast.define else set()

        # Define known functions that should NOT be considered as pattern variables
        known_functions = {'FIRST', 'LAST', 'PREV', 'NEXT', 'CLASSIFIER', 'MATCH_NUMBER', 
                        'ABS', 'ROUND', 'SQRT', 'POWER', 'CEILING', 'FLOOR', 'MOD'}
        
        # Get subset variables and their mappings
        subset_vars = {}
        subset_components = set()
        if self.ast.subset:
            for subset_clause in self.ast.subset:
                subset_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\((.*?)\)', subset_clause.subset_text)
                if subset_match:
                    subset_name = subset_match.group(1)
                    subset_elements = [v.strip() for v in subset_match.group(2).split(',')]
                    subset_vars[subset_name] = subset_elements
                    if subset_name in pattern_vars:
                        # If the union variable is in the pattern, its components are valid
                        subset_components.update(subset_elements)
                    logger.debug(f"Extracted subset mapping: {subset_name} -> {subset_elements}")
        
        # Track all referenced variables
        referenced_vars = set()
        
        # 1. Check variables used in MEASURES
        if self.ast.measures:
            for measure in self.ast.measures.measures:
                # Extract variables from column references like A.totalprice
                column_refs = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\\.([A-Za-z_][A-Za-z0-9_]*)', measure.expression)
                referenced_vars.update([ref[0] for ref in column_refs])
                
                # Extract variables from functions but exclude known function names
                func_pattern = r'(?:FIRST|LAST|PREV|NEXT)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)'
                func_refs = re.findall(func_pattern, measure.expression, re.IGNORECASE)
                referenced_vars.update(func_refs)
                
                extracted_vars = []
                if column_refs:
                    extracted_vars.extend([ref[0] for ref in column_refs])
                if func_refs:
                    extracted_vars.extend(func_refs)
                
                logger.debug(f"Extracted variables from measure '{measure.expression}': {extracted_vars}")
        
        # Filter out any known functions from referenced variables
        referenced_vars = referenced_vars - known_functions
        
        # Check for missing references
        all_valid_vars = pattern_vars.union(subset_components)
        missing = referenced_vars - all_valid_vars
        if missing:
            raise ParserError(f"Referenced variable(s) {missing} not found in the PATTERN clause or SUBSET definitions.", 
                            line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        
        # Check for extra definitions
        extra = defined_vars - pattern_vars - subset_components
        if extra:
            # Special case for empty pattern: allow any definition variables
            if self.ast.pattern and self.ast.pattern.pattern.strip() == "()":
                return
            # Otherwise raise error
            raise ParserError(f"Defined variable(s) {extra} not found in the PATTERN clause or as subset components.", 
                            line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        
        # Enhanced logging
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
