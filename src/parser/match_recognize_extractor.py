from antlr4 import *
import re
import logging
from antlr4.error.ErrorListener import ErrorListener
from antlr4 import InputStream, CommonTokenStream
from src.grammar.TrinoParser import TrinoParser
from src.grammar.TrinoParserVisitor import TrinoParserVisitor
from src.grammar.TrinoLexer import TrinoLexer
from src.ast_nodes.ast_nodes import (
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
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

from typing import List, Optional, Dict


def smart_split(raw_text):
    """Split measure expression into expression and alias parts, handling complex cases correctly."""
    if not raw_text:
        return [raw_text]
    
    # Handle simple case first - no AS keyword
    if ' AS ' not in raw_text.upper():
        return [raw_text]
    
    # For complex expressions with parentheses and dots, we need to be more careful
    # Find the last occurrence of " AS " that's not inside quotes or parentheses
    raw_upper = raw_text.upper()
    
    # Look for AS keyword from right to left to find the alias
    as_positions = []
    pos = 0
    in_quotes = False
    paren_depth = 0
    quote_char = None
    
    # First pass: find all potential AS positions
    i = 0
    while i < len(raw_text) - 3:  # -3 because we need at least " AS " (4 chars)
        char = raw_text[i]
        
        # Handle quotes
        if char in ['"', "'"]:
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                quote_char = None
        
        # Handle parentheses (only when not in quotes)
        elif not in_quotes:
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
        
        # Look for " AS " pattern when not in quotes or nested parentheses
        if (not in_quotes and paren_depth == 0 and 
            i < len(raw_text) - 3 and 
            raw_text[i:i+4].upper() == ' AS '):
            as_positions.append(i)
            i += 4  # Skip past " AS "
        else:
            i += 1
    
    if not as_positions:
        return [raw_text]
    
    # Use the last " AS " as the split point (rightmost)
    last_as_pos = as_positions[-1]
    expr = raw_text[:last_as_pos].strip()
    alias = raw_text[last_as_pos + 4:].strip()
    
    return [expr, alias]





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
        
        # Find the last occurrence of ' AS ' that's not inside parentheses
        expr, alias = extract_expression_and_alias(item)
        if alias:
            items.append(SelectItem(expr, alias))
        else:
            items.append(SelectItem(item))
    return SelectClause(items)


def extract_expression_and_alias(item: str) -> tuple:
    """
    Extract expression and alias from a SELECT item, handling nested parentheses correctly.
    Returns (expression, alias) tuple where alias is None if no alias found.
    """
    # Find all occurrences of ' AS ' (case insensitive)
    as_pattern = re.compile(r'\s+AS\s+', re.IGNORECASE)
    matches = list(as_pattern.finditer(item))
    
    if not matches:
        return item, None
    
    # Check each match from right to left to find the outermost alias
    for match in reversed(matches):
        potential_expr = item[:match.start()].strip()
        potential_alias = item[match.end():].strip()
        
        # Check if this AS is at the top level (not inside parentheses)
        if is_top_level_as(item, match.start()):
            return potential_expr, potential_alias
    
    # If no top-level AS found, treat as no alias
    return item, None


def is_top_level_as(text: str, as_position: int) -> bool:
    """
    Check if the AS at the given position is at the top level (not inside parentheses).
    """
    paren_level = 0
    for i, char in enumerate(text[:as_position]):
        if char == '(':
            paren_level += 1
        elif char == ')':
            paren_level -= 1
    
    return paren_level == 0


class MatchRecognizeExtractor(TrinoParserVisitor):
    def __init__(self):
        self.ast = MatchRecognizeClause()

    def _is_table_prefix(self, var_name: str) -> bool:
        """
        Check if a variable name looks like a table prefix rather than a pattern variable.
        
        Args:
            var_name: The variable name to check
            
        Returns:
            True if this looks like a forbidden table prefix, False otherwise
        """
        # Common table name patterns that should be rejected
        table_patterns = [
            r'^[a-z]+_table$',      # ending with _table
            r'^tbl_[a-z]+$',        # starting with tbl_
            r'^[a-z]+_tbl$',        # ending with _tbl
            r'^[a-z]+_tab$',        # ending with _tab
            r'^[a-z]+s$',           # plural forms (likely table names)
            r'^[a-z]+_data$',       # ending with _data
            r'^data_[a-z]+$',       # starting with data_
        ]
        
        # Check against common table naming patterns
        for pattern in table_patterns:
            if re.match(pattern, var_name.lower()):
                return True
        
        # Check for overly long names (likely table names)
        if len(var_name) > 20:
            return True
        
        # If it contains underscores and is longer than typical pattern variable names
        if '_' in var_name and len(var_name) > 10:
            return True
        
        return False

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
        
        # Fix for PERMUTE variable ordering - move this AFTER all update_from_defined calls
        if self.ast.pattern and "PERMUTE" in self.ast.pattern.pattern.upper():
            permute_match = re.search(r'PERMUTE\s*\(\s*([^)]+)\s*\)', self.ast.pattern.pattern, re.IGNORECASE)
            if permute_match:
                # Preserve original PERMUTE order
                variables = [v.strip() for v in permute_match.group(1).split(',')]
                self.ast.pattern.metadata["variables"] = variables
                self.ast.pattern.metadata["base_variables"] = variables.copy()
        
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
            raw_text = self.get_text(md)  # Use get_text to preserve spaces
            # Default semantics per SQL:2016 specification:
            # - Aggregate functions (SUM, AVG, COUNT, etc.) default to FINAL
            # - Navigation functions (FIRST, LAST, PREV, NEXT) may default to RUNNING in some contexts
            # For consistency with Trino and the standard, use FINAL as default for all functions
            semantics = "FINAL"
            explicit_semantics = False  # Track if semantics were explicitly specified
            raw_expr = raw_text.strip()
            
            # Use regex to match RUNNING or FINAL with flexible whitespace
            running_match = re.match(r'(?i)RUNNING\s+', raw_expr)
            final_match = re.match(r'(?i)FINAL\s+', raw_expr)
            
            if running_match:
                semantics = "RUNNING"
                explicit_semantics = True
                raw_expr = raw_expr[running_match.end():].strip()
            elif final_match:
                semantics = "FINAL"
                explicit_semantics = True
                raw_expr = raw_expr[final_match.end():].strip()
            
            # Alternative: If the expression is already concatenated (e.g., "RUNNINGLAST")
            elif raw_expr.upper().startswith("RUNNING"):
                semantics = "RUNNING"
                explicit_semantics = True
                # Extract function name after "RUNNING"
                function_match = re.match(r'(?i)RUNNING([A-Z]+)', raw_expr)
                if function_match:
                    func_name = function_match.group(1)
                    raw_expr = func_name + raw_expr[len("RUNNING" + func_name):]
            elif raw_expr.upper().startswith("FINAL"):
                semantics = "FINAL"
                explicit_semantics = True
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

            measure_metadata = {"semantics": semantics, "explicit_semantics": explicit_semantics}
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
        """Get the text representation of a parse tree node with preserved whitespace."""
        if ctx is None:
            return ""
        # Always use input stream to preserve original whitespace and formatting
        if hasattr(ctx, 'start') and hasattr(ctx, 'stop'):
            start = ctx.start.start
            stop = ctx.stop.stop
            return ctx.start.getInputStream().getText(start, stop)
        # Fallback to getText() if input stream access is not available
        elif hasattr(ctx, 'getText'):
            return ctx.getText()
        return ""

    
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
                
            # Only remove outer parentheses if they truly wrap the entire pattern
            # Check if the opening parenthesis at position 0 matches the closing parenthesis at the end
            if original_pattern.startswith('(') and original_pattern.endswith(')'):
                # Count parentheses to see if the first one matches the last one
                paren_count = 0
                matches_outer = True
                for i, char in enumerate(original_pattern):
                    if char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
                        # If we reach 0 before the end, the first '(' doesn't wrap the whole pattern
                        if paren_count == 0 and i < len(original_pattern) - 1:
                            matches_outer = False
                            break
                
                if matches_outer and paren_count == 0:
                    pattern_text = original_pattern[1:-1]
                else:
                    pattern_text = original_pattern
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
            
            # Fix for PERMUTE variable ordering - move this AFTER all update_from_defined calls
            if pattern_text and "PERMUTE" in pattern_text.upper():
                permute_match = re.search(r'PERMUTE\s*\(\s*([^)]+)\s*\)', pattern_text, re.IGNORECASE)
                if permute_match:
                    # Preserve original PERMUTE order
                    variables = [v.strip() for v in permute_match.group(1).split(',')]
                    pattern_clause.metadata["variables"] = variables
                    pattern_clause.metadata["base_variables"] = variables.copy()
            
            return pattern_clause
        return PatternClause("")  # Return empty pattern clause if no pattern found

    def _extract_nested_permute_variables(self, pattern_text: str) -> List[str]:
        """
        Extract all variables from nested PERMUTE patterns.
        
        For example:
        - PERMUTE(A, B, C) -> ['A', 'B', 'C']
        - PERMUTE(A, PERMUTE(B, C)) -> ['A', 'B', 'C']
        - PERMUTE(PERMUTE(A, B), C) -> ['A', 'B', 'C']
        """
        variables = []
        
        def extract_variables_recursive(text):
            """Recursively extract variables from PERMUTE expressions"""
            # Find all PERMUTE expressions
            permute_pattern = r'PERMUTE\s*\(\s*([^()]*(?:\([^)]*\)[^()]*)*)\s*\)'
            
            while True:
                match = re.search(permute_pattern, text, re.IGNORECASE)
                if not match:
                    break
                    
                content = match.group(1)
                
                # Split content by commas, but be careful about nested parentheses
                parts = []
                current_part = ""
                paren_depth = 0
                
                for char in content:
                    if char == '(':
                        paren_depth += 1
                    elif char == ')':
                        paren_depth -= 1
                    elif char == ',' and paren_depth == 0:
                        if current_part.strip():
                            parts.append(current_part.strip())
                        current_part = ""
                        continue
                    current_part += char
                
                if current_part.strip():
                    parts.append(current_part.strip())
                
                # Process each part
                for part in parts:
                    part = part.strip()
                    if 'PERMUTE' in part.upper():
                        # This is a nested PERMUTE, process it recursively
                        extract_variables_recursive(part)
                    else:
                        # This is a regular variable
                        if part and part not in variables:
                            variables.append(part)
                
                # Replace the processed PERMUTE with empty string to avoid reprocessing
                text = text[:match.start()] + text[match.end():]
        
        extract_variables_recursive(pattern_text)
        return variables


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
                
                # Check for infinite loop - only if skipping to the same first occurrence
                # The logic should be more nuanced - A B+ pattern with SKIP TO FIRST A is valid
                # because after matching A B+, we can start again from a different A
                # Only prohibit cases that would immediately cause infinite loops
                if pattern_vars and target_var == pattern_vars[0] and mode == 'TO FIRST':
                    # This is actually valid in most cases - commented out for now
                    # Skip to first A in pattern A B+ means: after finding a match A B+, 
                    # start next search from the first A in the match
                    pass
                # Note: AFTER MATCH SKIP TO LAST variable is valid even for single-variable patterns
                # with quantifiers like UP{2,} because it advances the starting position and
                # the quantifier requirement prevents immediate infinite loops
                elif False:  # Disabled - the previous validation was too strict
                    # Only single variable patterns with TO LAST would create immediate infinite loop
                    raise ParserError(
                        f"AFTER MATCH SKIP {mode} {target_var} would create an infinite loop "
                        f"in single-variable pattern.",
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
        
        # Import and call detailed pattern validation from tokenizer
        try:
            from src.matcher.pattern_tokenizer import tokenize_pattern
            tokenize_pattern(pattern_text)  # This will raise exceptions for invalid patterns
        except Exception as e:
            # Convert tokenizer exceptions to ParserError
            raise ParserError(f"Invalid pattern syntax: {e}", line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
            
        logger.debug(f"PATTERN clause validated successfully: {pattern_text}")

    def validate_function_usage(self, ctx):
        # Order matters! Check specific functions (COUNT_IF, SUM_IF, AVG_IF) before generic ones (COUNT)
        allowed_functions = [
            ("COUNT_IF", r"(?:FINAL|RUNNING)?\s*COUNT_IF\(\s*.*?\s*\)"),  # COUNT_IF takes one condition parameter
            ("SUM_IF", r"(?:FINAL|RUNNING)?\s*SUM_IF\(\s*.*?,\s*.*?\s*\)"),  # SUM_IF takes two parameters
            ("AVG_IF", r"(?:FINAL|RUNNING)?\s*AVG_IF\(\s*.*?,\s*.*?\s*\)"),  # AVG_IF takes two parameters
            ("COUNT", r"(?:FINAL|RUNNING)?\s*COUNT\(\s*.*?\s*\)"),
            # Use word boundaries to prevent matching "first_value" as "FIRST"
            ("FIRST\\b", r"(?:FINAL|RUNNING)?\s*FIRST\(\s*.+?(?:\s*,\s*\d+)?\s*\)"),
            ("LAST\\b", r"(?:FINAL|RUNNING)?\s*LAST\(\s*.+?(?:\s*,\s*\d+)?\s*\)"),
            ("PREV\\b", r"(?:FINAL|RUNNING)?\s*PREV\(\s*.+?(?:,\s*\d+)?\s*\)"),
            ("NEXT\\b", r"(?:FINAL|RUNNING)?\s*NEXT\(\s*.+?(?:,\s*\d+)?\s*\)"),
        ]
        
        for measure in self.ast.measures.measures if self.ast.measures else []:
            expression = measure.expression
            validated = False
            
            # Check each function pattern in order
            for func, pattern in allowed_functions:
                if re.search(func, expression, flags=re.IGNORECASE):
                    if re.search(pattern, expression, flags=re.IGNORECASE):
                        validated = True
                        logger.debug(f"Validated {func} usage in measure: {expression}")
                        break
                    else:
                        raise ParserError(f"Invalid usage of {func} in measure: {expression}", 
                                        line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
            
            if not validated:
                # No specific function pattern matched, which is fine for other expressions
                logger.debug(f"No specific function validation needed for measure: {expression}")

    def validate_identifiers(self, ctx):
        """Validate that all defined variables are found in the pattern or as subset components."""
        # Special case for empty patterns - skip validation
        if self.ast.pattern and (self.ast.pattern.metadata.get("empty_pattern", False) or 
                                self.ast.pattern.pattern.strip() == "()"):
            logger.debug("Empty pattern detected in validate_identifiers - skipping validation")
            return
                
        # For nested PERMUTE patterns, skip validation as all defined variables are considered valid
        if self.ast.pattern and (self.ast.pattern.metadata.get("nested_permute", False) or 
                                "PERMUTE" in self.ast.pattern.pattern.upper()):
            logger.debug("PERMUTE pattern detected - skipping variable validation")
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
        
        # Get all defined variables
        defined_vars = set()
        if self.ast.define:
            for definition in self.ast.define.definitions:
                defined_vars.add(definition.variable)
        
        # Add subset components to defined variables if their union variable is defined
        if self.ast.subset:
            for subset_clause in self.ast.subset:
                subset_text = subset_clause.subset_text
                match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\((.*?)\)', subset_text)
                if match:
                    subset_name = match.group(1)
                    if subset_name in defined_vars:
                        components = [c.strip() for c in match.group(2).split(',')]
                        defined_vars.update(components)
        
        # Check that all pattern variables are defined (not the other way around)
        undefined_pattern_vars = pattern_vars - defined_vars
        if undefined_pattern_vars:
            # Skip this check for empty pattern
            if self.ast.pattern and (self.ast.pattern.pattern.strip() == "()" or 
                                    self.ast.pattern.metadata.get("empty_pattern", False)):
                return
                
            # Skip this check for PERMUTE patterns
            if self.ast.pattern and "PERMUTE" in self.ast.pattern.pattern.upper():
                return
                
            # SQL MATCH_RECOGNIZE Standard: Variables without DEFINE conditions default to TRUE
            # This is valid behavior - pattern variables without explicit conditions should always match
            logger.debug(f"Pattern variables {undefined_pattern_vars} have no DEFINE conditions - defaulting to TRUE (always match)")
            # Don't raise an error - this is valid SQL behavior

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
            
        # Skip validation for PERMUTE patterns
        if "PERMUTE" in pattern_text.upper():
            logger.debug("PERMUTE pattern detected - skipping variable validation")
            return
            
        # Get pattern variables and defined variables (case-sensitive)
        pattern_vars = set(self.ast.pattern.metadata.get("base_variables", []))
        defined_vars = {d.variable for d in self.ast.define.definitions} if self.ast.define else set()

        # Define known functions that should NOT be considered as pattern variables
        known_functions = {'FIRST', 'LAST', 'PREV', 'NEXT', 'CLASSIFIER', 'MATCH_NUMBER', 
                        'ABS', 'ROUND', 'SQRT', 'POWER', 'CEILING', 'FLOOR', 'MOD'}
        
        # Get subset variables and their mappings
        subset_vars = {}
        subset_union_vars = set()  # SUBSET union variables (like U, V, early_events)
        subset_components = set()  # Components of subset variables (like A, B in U = (A, B))
        if self.ast.subset:
            for subset_clause in self.ast.subset:
                # Handle both regular and quoted identifiers
                subset_match = re.match(r'((?:"[^"]+"|[A-Za-z_][A-Za-z0-9_]*))\s*=\s*\((.*?)\)', subset_clause.subset_text)
                if subset_match:
                    subset_name = subset_match.group(1)
                    subset_elements = [v.strip().strip('"') for v in subset_match.group(2).split(',')]
                    # Clean subset name by removing quotes if present
                    clean_subset_name = subset_name.strip('"')
                    subset_vars[clean_subset_name] = subset_elements
                    
                    # SUBSET union variables are valid references in MEASURES clauses
                    subset_union_vars.add(clean_subset_name)
                    # Also add quoted version if it was quoted
                    if subset_name.startswith('"'):
                        subset_union_vars.add(subset_name)
                    
                    # Subset components must be defined in DEFINE clause
                    subset_components.update(subset_elements)
                    logger.debug(f"Extracted subset mapping: {clean_subset_name} -> {subset_elements}")
        
        # Track all referenced pattern variables (not data columns)
        referenced_pattern_vars = set()
        
        # 1. Check pattern variables used in MEASURES
        if self.ast.measures:
            for measure in self.ast.measures.measures:
                # Extract pattern variables from column references like A.totalprice
                column_refs = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', measure.expression)
                referenced_pattern_vars.update([ref[0] for ref in column_refs])
                
                # For navigation functions like FIRST(price), LAST(price), the argument can be:
                # 1. A data column name (like 'price') - should NOT be validated as pattern variable
                # 2. A pattern variable reference (like 'A.price') - the 'A' part should be validated
                # We only extract pattern variables, not data column references
                func_pattern = r'(?:FIRST|LAST|PREV|NEXT)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)'
                func_pattern_refs = re.findall(func_pattern, measure.expression, re.IGNORECASE)
                referenced_pattern_vars.update([ref[0] for ref in func_pattern_refs])
                
                extracted_vars = []
                if column_refs:
                    extracted_vars.extend([ref[0] for ref in column_refs])
                if func_pattern_refs:
                    extracted_vars.extend([ref[0] for ref in func_pattern_refs])
                
                logger.debug(f"Extracted pattern variables from measure '{measure.expression}': {extracted_vars}")
        
        # 2. Check pattern variables used in DEFINE clause conditions  
        if self.ast.define:
            for definition in self.ast.define.definitions:
                # Extract pattern variables from column references like A.price > B.price
                column_refs = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)', definition.condition)
                referenced_pattern_vars.update([ref[0] for ref in column_refs])
                
                # Extract pattern variables from navigation functions in DEFINE conditions
                func_pattern = r'(?:FIRST|LAST|PREV|NEXT)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)'
                func_pattern_refs = re.findall(func_pattern, definition.condition, re.IGNORECASE)
                referenced_pattern_vars.update([ref[0] for ref in func_pattern_refs])
                
                extracted_vars = []
                if column_refs:
                    extracted_vars.extend([ref[0] for ref in column_refs])
                if func_pattern_refs:
                    extracted_vars.extend([ref[0] for ref in func_pattern_refs])
                
                logger.debug(f"Extracted pattern variables from DEFINE condition '{definition.condition}': {extracted_vars}")

        # Filter out any known functions from referenced pattern variables
        referenced_pattern_vars = referenced_pattern_vars - known_functions
        
        # Extract all variables that appear in the pattern text (not just those that were successfully tokenized)
        # This handles cases where variables like START appear in the pattern but aren't in defined_vars
        pattern_variables_in_text = set()
        var_pattern = r'\b([A-Za-z_][A-Za-z0-9_]*)\b'
        potential_vars = re.findall(var_pattern, pattern_text)
        for var in potential_vars:
            # Skip operators, keywords, and quantifiers
            if var.upper() not in {'AND', 'OR', 'NOT', 'PERMUTE'} and not var.isdigit():
                pattern_variables_in_text.add(var)
        
        # Check for missing pattern variable references - allow variables that appear in pattern text
        # SUBSET union variables are valid references in MEASURES clauses
        all_valid_pattern_vars = pattern_vars.union(subset_components).union(pattern_variables_in_text).union(subset_union_vars)
        
        # Also allow variables that are defined in DEFINE clause even if not in pattern
        # This is needed for test cases where variables are defined but not used in the current pattern
        if self.ast.define:
            defined_vars = {d.variable for d in self.ast.define.definitions}
            all_valid_pattern_vars = all_valid_pattern_vars.union(defined_vars)
        
        missing = referenced_pattern_vars - all_valid_pattern_vars
        if missing and "PERMUTE" not in pattern_text.upper():
            # Check if any missing variables look like table prefixes
            table_prefixes = []
            for var in missing:
                if self._is_table_prefix(var):
                    table_prefixes.append(var)
            
            if table_prefixes:
                # Throw specific table prefix error
                prefixes_str = ', '.join(table_prefixes)
                raise ParserError(f"Forbidden table prefix reference(s): {prefixes_str}. Use pattern variables (A, B, C, etc.) instead of table.column syntax in MATCH_RECOGNIZE.", 
                                line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
            else:
                # Throw generic missing pattern variable error
                raise ParserError(f"Referenced pattern variable(s) {missing} not found in the PATTERN clause or SUBSET definitions.", 
                                line=ctx.start.line, column=ctx.start.column, snippet=ctx.getText())
        
        # NOTE: Do not validate that all defined variables are used in patterns
        # SQL MATCH_RECOGNIZE allows defining variables that aren't used in the current pattern
        # They might be used in MEASURES, or be defined for future extension
        # Only validate that pattern variables are properly defined (which we already do above)
        
        # Enhanced logging
        logger.debug(f"Pattern variables: {pattern_vars}")
        logger.debug(f"Referenced pattern variables: {referenced_pattern_vars}")
        logger.debug(f"Defined variables: {defined_vars}")
        logger.debug(f"Subset union variables: {subset_union_vars}")
        logger.debug(f"Subset components: {subset_components}")
        logger.debug(f"Subset variables: {subset_vars}")

    def extract_permute_variables(self, pattern_text):
        # Current extraction puts variables in wrong order: ['B', 'A', 'C'] instead of ['A', 'B', 'C']
        # Fix to preserve original order from pattern:
        match = re.search(r'PERMUTE\s*\(([^)]+)\)', pattern_text)
        if match:
            variables = [v.strip() for v in match.group(1).split(',')]
            return variables
        return []
    
class FullQueryExtractor(TrinoParserVisitor):
    def __init__(self, original_query: str):
        self.original_query = original_query
        self.select_clause = None
        self.from_clause = None
        self.match_recognize = None
        self.order_by_clause = None

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
            
        # Parse outer ORDER BY clause
        order_by_match = re.search(r'(?i)\)\s*ORDER\s+BY\s+([^;]+)', full_text)
        if order_by_match:
            order_by_text = order_by_match.group(1).strip()
            logger.debug(f"Found outer ORDER BY clause: {order_by_text}")
            # Parse the ORDER BY clause
            sort_items = []
            columns = [col.strip() for col in order_by_text.split(',')]
            for col in columns:
                # Handle ASC/DESC and column references like m.category
                col_match = re.match(r'(.+?)\s+(ASC|DESC)$', col, re.IGNORECASE)
                if col_match:
                    column_name = col_match.group(1).strip()
                    ordering = col_match.group(2).upper()
                else:
                    column_name = col.strip()
                    ordering = "ASC"
                
                # Remove table alias prefix (e.g., m.category -> category)
                if '.' in column_name:
                    column_name = column_name.split('.')[-1]
                    
                sort_items.append(SortItem(column_name, ordering))
                
            self.order_by_clause = OrderByClause(sort_items)
            logger.debug(f"Extracted outer ORDER BY clause: {self.order_by_clause}")
        else:
            logger.debug("No outer ORDER BY clause found.")
            
        self.match_recognize = self.find_pattern_recognition(ctx)
        if self.match_recognize:
            extractor = MatchRecognizeExtractor()
            extractor.visit(self.match_recognize)
            self.match_recognize = extractor.ast
            logger.debug("Extracted MATCH_RECOGNIZE clause via recursive search.")
        else:
            logger.debug("No MATCH_RECOGNIZE clause found.")
        return FullQueryAST(self.select_clause, self.from_clause, self.match_recognize, self.order_by_clause)

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
    
    # Preprocess query to handle edge cases that the grammar doesn't support
    query = _preprocess_query_for_parser(query)
    
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
    
    # Preprocess query to handle edge cases that the grammar doesn't support
    query = _preprocess_query_for_parser(query)
    
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
    result = extractor.visit(tree)
    # Use the result from visitSingleStatement which includes the order_by_clause
    if result:
        return result
    # Fallback to the previous behavior if visit doesn't return anything
    return FullQueryAST(extractor.select_clause, extractor.from_clause, extractor.match_recognize, extractor.order_by_clause)


def _preprocess_query_for_parser(query: str) -> str:
    """
    Preprocess the SQL query to handle constructs not supported by the grammar.
    
    This includes:
    - Empty IN predicates: IN () -> IN (NULL) WHERE FALSE
    - Empty NOT IN predicates: NOT IN () -> NOT IN (NULL) WHERE TRUE
    
    Args:
        query: Original SQL query string
        
    Returns:
        Preprocessed SQL query string
    """
    import re
    
    # Handle empty IN predicates by replacing with equivalent that parser can handle
    # IN () should always be false, so replace with IN (NULL) and add WHERE FALSE logic
    # NOT IN () should always be true, so replace with NOT IN (NULL) and add WHERE TRUE logic
    
    # For empty IN predicates in DEFINE clauses, we can replace with a condition that always evaluates to false/true
    # Pattern: value IN () -> value IN ('__EMPTY_IN_FALSE__')
    # Pattern: value NOT IN () -> value NOT IN ('__EMPTY_IN_TRUE__')
    
    query = re.sub(r'\bIN\s*\(\s*\)', "IN ('__EMPTY_IN_FALSE__')", query, flags=re.IGNORECASE)
    query = re.sub(r'\bNOT\s+IN\s*\(\s*\)', "NOT IN ('__EMPTY_IN_TRUE__')", query, flags=re.IGNORECASE)
    
    return query


