# src/ast/ast_builder.py

import logging
import re
from typing import Dict, Any, List, Tuple
from antlr4 import ParseTreeWalker
from src.grammar.TrinoParserListener import TrinoParserListener
from src.ast.match_recognize_ast import MatchRecognizeAST, RowsPerMatchType, AfterMatchSkipType
from src.parser.expression_parser import parse_expression_full
from src.parser.pattern_parser import parse_pattern_full
from src.ast.pattern_optimizer import optimize_pattern
from src.parser.error_handler import ErrorHandler
from src.parser.semantic_analyzer import SemanticAnalyzer

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
        self.semantic_analyzer = SemanticAnalyzer(ErrorHandler())

    def enterMatchRecognizeClause(self, ctx):
        logger.debug("Entering MATCH_RECOGNIZE clause.")

    def exitMatchRecognizeClause(self, ctx):
        try:
            # Add a more flexible context extraction method
            self._extract_from_context(ctx)
            
            # Finalize AST post-processing
            self.ast.__post_init__()
            
            # Validate unmatched rows constraints
            self._validate_unmatched_rows_constraints()
                
        except Exception as e:
            self.errors.append(str(e))
            logger.error("Error while extracting MATCH_RECOGNIZE clause: %s", e)

    def _extract_from_context(self, ctx):
        """Extract all clauses using a flexible approach that can handle different ANTLR tree structures"""
        # Extract pattern first to get pattern variables for validation
        pattern_ctx = self._get_clause_context(ctx, 'patternClause')
        if pattern_ctx:
            pattern_text = get_formatted_text(pattern_ctx)
            parsed_pattern = parse_pattern_full(pattern_text)
            pattern_vars = self._extract_pattern_variables(parsed_pattern["ast"])
            self.semantic_analyzer.set_pattern_variables(pattern_vars)
            
            # Also check for empty pattern
            if pattern_text == "()":
                self.ast.is_empty_match = True
            
            # Extract and optimize PATTERN
            optimized_pattern = optimize_pattern(parsed_pattern)
            self.ast.pattern = optimized_pattern
            logger.debug("Extracted and optimized PATTERN: %s", self.ast.pattern)
        
        # Extract PARTITION BY
        partition_ctx = self._get_clause_context(ctx, 'partitionClause')
        if partition_ctx:
            partition_exprs = self._get_expressions(partition_ctx)
            self.ast.partition_by = [get_formatted_text(expr) for expr in partition_exprs]
            logger.debug("Extracted PARTITION BY: %s", self.ast.partition_by)
        
        # Extract ORDER BY
        order_ctx = self._get_clause_context(ctx, 'orderClause')
        if order_ctx:
            sort_items = self._get_sort_items(order_ctx)
            self.ast.order_by = [get_formatted_text(item) for item in sort_items]
            logger.debug("Extracted ORDER BY: %s", self.ast.order_by)
        
        # Extract SUBSET
        subset_ctx = self._get_clause_context(ctx, 'subsetClause')
        if subset_ctx:
            subset_mapping = {}
            subset_defs = self._get_subset_definitions(subset_ctx)
            for def_ctx in subset_defs:
                text = get_formatted_text(def_ctx)
                m = re.match(r'(\w+)\s*=\s*\((.*?)\)', text)
                if m:
                    key = m.group(1).strip()
                    values = [v.strip() for v in m.group(2).split(',')]
                    subset_mapping[key] = values
                else:
                    self.errors.append("Invalid SUBSET definition: " + text)
            self.ast.subset = subset_mapping
            self.subset_variables = subset_mapping
            self.semantic_analyzer.set_subset_variables(subset_mapping)
            logger.debug("Extracted SUBSET: %s", self.ast.subset)
        
        # Extract MEASURES
        measure_ctx = self._get_clause_context(ctx, 'measureClause')
        if measure_ctx:
            measures = []
            measure_defs = self._get_measure_definitions(measure_ctx)
            for def_ctx in measure_defs:
                expr_ctx = self._get_expression(def_ctx)
                alias_ctx = self._get_alias(def_ctx)
                
                expr_text = get_formatted_text(expr_ctx) if expr_ctx else ""
                alias_text = get_formatted_text(alias_ctx) if alias_ctx else ""
                
                if not alias_text:
                    self.errors.append(f"Measure '{expr_text}' is missing an alias.")
                else:
                    expr_ast = parse_expression_full(expr_text, in_measures_clause=True)
                    self.semantic_analyzer.validate_expression(
                        expr_ast["ast"],
                        f"MEASURE {alias_text}",
                        in_measures=True
                    )
                    measures.append({
                        "expression": expr_ast,
                        "alias": alias_text
                    })
            self.ast.measures = measures
            logger.debug("Extracted MEASURES: %s", self.ast.measures)
        
        # Extract ROWS PER MATCH
        rows_ctx = self._get_clause_context(ctx, 'rowsPerMatchClause')
        if rows_ctx:
            self.ast.rows_per_match = get_formatted_text(rows_ctx)
            logger.debug("Extracted ROWS PER MATCH: %s", self.ast.rows_per_match)
        
        # Extract AFTER MATCH SKIP
        skip_ctx = self._get_clause_context(ctx, 'afterMatchSkipClause')
        if skip_ctx:
            self.ast.after_match_skip = get_formatted_text(skip_ctx)
            logger.debug("Extracted AFTER MATCH SKIP: %s", self.ast.after_match_skip)
        
        # Extract DEFINE
        define_ctx = self._get_clause_context(ctx, 'defineClause')
        if define_ctx:
            defines = []
            var_defs = self._get_variable_definitions(define_ctx)
            for def_ctx in var_defs:
                var_ctx = self._get_clause_context(def_ctx, 'variable')
                cond_ctx = self._get_clause_context(def_ctx, 'condition')
                
                var_text = get_formatted_text(var_ctx) if var_ctx else ""
                cond_text = get_formatted_text(cond_ctx) if cond_ctx else ""
                
                if not cond_text:
                    self.errors.append(f"DEFINE clause for variable '{var_text}' is missing a condition.")
                else:
                    cond_ast = parse_expression_full(cond_text, in_measures_clause=False)
                    self.semantic_analyzer.validate_expression(
                        cond_ast["ast"],
                        f"DEFINE {var_text}",
                        in_measures=False
                    )
                    defines.append({
                        "variable": var_text,
                        "condition": cond_ast
                    })
            self.ast.define = defines
            logger.debug("Extracted DEFINE: %s", self.ast.define)

    def _get_clause_context(self, ctx, name):
        """Flexibly extract a clause context from the parse tree"""
        # Try direct method access first (most reliable)
        if hasattr(ctx, name) and callable(getattr(ctx, name)):
            result = getattr(ctx, name)()
            if result:
                return result
        
        # Try attribute access
        if hasattr(ctx, name):
            result = getattr(ctx, name)
            if result:
                return result
        
        # Try searching children with similar name
        if hasattr(ctx, 'children') and ctx.children:
            # First check class names
            for child in ctx.children:
                if hasattr(child, '__class__'):
                    child_name = child.__class__.__name__.lower()
                    if name.lower() in child_name:
                        return child
            
            # Then check text content (less reliable)
            for child in ctx.children:
                if hasattr(child, 'getText'):
                    try:
                        child_text = child.getText().lower()
                        name_lower = name.lower()
                        if name_lower in child_text:
                            # For clauses like 'partitionBy', convert to 'partition by' for comparison
                            formatted_name = ''.join([' '+c.lower() if c.isupper() else c for c in name_lower]).strip()
                            if formatted_name in child_text:
                                return child
                    except:
                        pass
        
        # If not found and this is a pattern recognition context, try the root context
        if hasattr(self, 'root_context') and ctx != self.root_context:
            return self._get_clause_context(self.root_context, name)
        
        return None

    def _get_expressions(self, ctx):
        """Get expression contexts from a clause context"""
        if hasattr(ctx, 'expression') and callable(getattr(ctx, 'expression')):
            return ctx.expression()
        if hasattr(ctx, 'children'):
            return [c for c in ctx.children if hasattr(c, '__class__') and 'expression' in c.__class__.__name__.lower()]
        return []

    def _get_sort_items(self, ctx):
        """Get sortItem contexts from an ORDER BY clause"""
        if hasattr(ctx, 'sortItem') and callable(getattr(ctx, 'sortItem')):
            return ctx.sortItem()
        if hasattr(ctx, 'children'):
            return [c for c in ctx.children if hasattr(c, '__class__') and 'sortitem' in c.__class__.__name__.lower()]
        return []

    # Add similar methods for other clauses
    def _get_subset_definitions(self, ctx):
        """Get subsetDefinition contexts"""
        if hasattr(ctx, 'subsetDefinition') and callable(getattr(ctx, 'subsetDefinition')):
            return ctx.subsetDefinition()
        return []
        
    def _get_measure_definitions(self, ctx):
        """Get measureDefinition contexts"""
        if hasattr(ctx, 'measureDefinition') and callable(getattr(ctx, 'measureDefinition')):
            return ctx.measureDefinition()
        return []
        
    def _get_variable_definitions(self, ctx):
        """Get variableDefinition contexts"""
        if hasattr(ctx, 'variableDefinition') and callable(getattr(ctx, 'variableDefinition')):
            return ctx.variableDefinition()
        return []

    def _get_expression(self, ctx):
        """Get expression context from a definition context"""
        if hasattr(ctx, 'expression') and callable(getattr(ctx, 'expression')):
            return ctx.expression()
        return None
        
    def _get_alias(self, ctx):
        """Get alias context from a definition context"""
        if hasattr(ctx, 'alias') and callable(getattr(ctx, 'alias')):
            return ctx.alias()
        return None

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

def build_ast_from_parse_tree(parse_tree) -> Dict[str, Any]:
    """
    Build an AST from the ANTLR parse tree.
    
    This function identifies different SQL constructs in the parse tree
    and delegates to specialized builders for each construct.
    
    Args:
        parse_tree: ANTLR parse tree
        
    Returns:
        Dictionary containing:
        - ast: The built AST
        - errors: List of AST building errors
    """
    if parse_tree is None:
        return {"ast": None, "errors": ["No parse tree provided"]}
   
    # Find MATCH_RECOGNIZE clauses
    match_recognize_clauses = find_match_recognize_clauses(parse_tree)
    
    if match_recognize_clauses:
        # For each MATCH_RECOGNIZE clause, build its AST
        match_recognize_asts = []
        all_errors = []
        
        for clause in match_recognize_clauses:
            ast, errors = build_match_recognize_ast(clause)
            if ast:
                match_recognize_asts.append(ast)
            if errors:
                all_errors.extend(errors)
        
        return {
            "ast": {
                "type": "query",
                "match_recognize": match_recognize_asts
            },
            "errors": all_errors
        }
    else:
        # Handle other SQL constructs
        return {
            "ast": {"type": "query", "match_recognize": []},
            "errors": []
        }

# src/ast/ast_builder.py
# src/ast/ast_builder.py

def find_match_recognize_clauses(parse_tree) -> List:
    """Find all MATCH_RECOGNIZE clauses in the parse tree"""
    clauses = []
    
    class MatchRecognizeFinder(TrinoParserListener):
        def enterMatchRecognizeClause(self, ctx):
            print("Found MATCH_RECOGNIZE clause directly")
            clauses.append(ctx)
            
        def enterPatternRecognition(self, ctx):
            """Called when a PatternRecognition context is entered"""
            logger.debug("Entering PatternRecognition context")
            
            # Store this as the root context
            self.root_context = ctx
            
            # Try to extract clauses from this context too
            try:
                # This will help extract from non-standard context structures
                self._try_extract_clauses_from_pattern_recognition(ctx)
            except Exception as e:
                self.errors.append(f"Error extracting from PatternRecognition: {str(e)}")
                logger.error("Error extracting from PatternRecognition: %s", e)

        def _try_extract_clauses_from_pattern_recognition(self, ctx):
            """Try to extract clauses directly from a PatternRecognition context"""
            if hasattr(ctx, 'children') and ctx.children:
                # Process all tokens
                clause_type = None
                clause_content = []
                
                for child in ctx.children:
                    if hasattr(child, 'getText'):
                        try:
                            text = child.getText().upper()
                            
                            # Detect clause types
                            if 'PARTITION BY' in text:
                                clause_type = 'partition_by'
                                continue
                            elif 'ORDER BY' in text:
                                clause_type = 'order_by'
                                continue
                            elif 'MEASURES' in text:
                                clause_type = 'measures'
                                continue
                            elif 'PATTERN' in text:
                                clause_type = 'pattern'
                                continue
                            elif 'DEFINE' in text:
                                clause_type = 'define'
                                continue
                            elif 'ROWS PER MATCH' in text:
                                self.ast.rows_per_match = get_formatted_text(child)
                                continue
                            elif 'AFTER MATCH SKIP' in text:
                                self.ast.after_match_skip = get_formatted_text(child)
                                continue
                            
                            # Collect clause content
                            if clause_type and not text.upper() in ['(', ')', ',']:
                                clause_content.append(child)
                        
                        except:
                            pass
                        
                # Process collected content for each clause type
                if clause_type == 'pattern' and clause_content:
                    combined_text = ''.join([get_formatted_text(c) for c in clause_content])
                    if '(' in combined_text and ')' in combined_text:
                        pattern_text = combined_text[combined_text.find('('):combined_text.rfind(')')+1]
                        parsed_pattern = parse_pattern_full(pattern_text)
                        pattern_vars = self._extract_pattern_variables(parsed_pattern["ast"])
                        self.semantic_analyzer.set_pattern_variables(pattern_vars)
                        self.ast.pattern = optimize_pattern(parsed_pattern)

        def enterTableElement(self, ctx):
            if hasattr(ctx, 'matchRecognizeClause') and ctx.matchRecognizeClause():
                print("Found MATCH_RECOGNIZE clause in table element")
                clauses.append(ctx.matchRecognizeClause())
                
        def enterQuerySpecification(self, ctx):
            print("Entering query specification")
            if hasattr(ctx, 'fromClause') and ctx.fromClause():
                from_clause = ctx.fromClause()
                print("Found FROM clause")
                if hasattr(from_clause, 'relation') and from_clause.relation():
                    for relation in from_clause.relation():
                        print(f"Checking relation: {relation.__class__.__name__}")
                        if hasattr(relation, 'matchRecognizeClause') and relation.matchRecognizeClause():
                            print("Found MATCH_RECOGNIZE clause in relation")
                            clauses.append(relation.matchRecognizeClause())
        
        def enterRelation(self, ctx):
            print(f"Entering relation: {ctx.__class__.__name__}")
            if hasattr(ctx, 'matchRecognizeClause') and ctx.matchRecognizeClause():
                print("Found MATCH_RECOGNIZE clause in relation")
                clauses.append(ctx.matchRecognizeClause())
    
    walker = ParseTreeWalker()
    walker.walk(MatchRecognizeFinder(), parse_tree)
    
    print(f"Found {len(clauses)} MATCH_RECOGNIZE clauses")
    return clauses


def print_parse_tree(node, indent=0):
    """Print the structure of the parse tree for debugging"""
    if node is None:
        return
        
    # Print the current node
    node_name = node.__class__.__name__
    print(" " * indent + f"- {node_name}")
    
    # Print all methods that return something
    for method_name in dir(node):
        if method_name.startswith("get") and callable(getattr(node, method_name)):
            try:
                result = getattr(node, method_name)()
                if result is not None:
                    print(" " * (indent + 2) + f"{method_name}(): {result.__class__.__name__}")
            except:
                pass
    
    # Recursively print children
    if hasattr(node, "children") and node.children:
        for child in node.children:
            print_parse_tree(child, indent + 4)
def build_match_recognize_ast(ctx) -> Tuple[MatchRecognizeAST, List[str]]:
    """
    Build a MatchRecognizeAST from a MATCH_RECOGNIZE clause context.
    
    Args:
        ctx: ANTLR parse tree context for a MATCH_RECOGNIZE clause
        
    Returns:
        Tuple containing:
        - The built MatchRecognizeAST
        - List of errors encountered during building
    """
    builder = EnhancedMatchRecognizeASTBuilder()
    walker = ParseTreeWalker()
    
    # Handle different context types
    if hasattr(ctx, '__class__'):
        class_name = ctx.__class__.__name__
        print(f"Processing context of type: {class_name}")
        
        if class_name == 'PatternRecognitionContext':
            # For PatternRecognitionContext, extract the matchRecognize part
            if hasattr(ctx, 'matchRecognize') and ctx.matchRecognize():
                print("Found matchRecognize within PatternRecognitionContext")
                match_recognize_ctx = ctx.matchRecognize()
                walker.walk(builder, match_recognize_ctx)
            else:
                # Try to navigate directly to the correct context
                match_recognize_ctx = _extract_match_recognize_context(ctx)
                if match_recognize_ctx:
                    print(f"Extracted match recognize context: {match_recognize_ctx.__class__.__name__}")
                    walker.walk(builder, match_recognize_ctx)
                else:
                    # If we can't directly access matchRecognize, walk the entire context
                    print("Walking entire PatternRecognitionContext")
                    walker.walk(builder, ctx)
        else:
            # For other contexts, use them directly
            walker.walk(builder, ctx)
    else:
        # Fallback for non-context objects
        walker.walk(builder, ctx)
    
    return builder.get_ast(), builder.errors

def _extract_match_recognize_context(ctx):
    """Extract the actual MATCH_RECOGNIZE context from a pattern recognition context"""
    # Try searching in children
    if hasattr(ctx, 'children') and ctx.children:
        for child in ctx.children:
            if hasattr(child, '__class__'):
                child_name = child.__class__.__name__
                if 'MatchRecognize' in child_name:
                    return child
                
    # Try to find specific subclause tokens that indicate a MATCH_RECOGNIZE clause
    key_tokens = ['PARTITION', 'ORDER', 'MEASURES', 'PATTERN', 'DEFINE']
    if hasattr(ctx, 'children') and ctx.children:
        for child in ctx.children:
            if hasattr(child, 'getText'):
                try:
                    text = child.getText().upper()
                    if any(token in text for token in key_tokens):
                        return ctx  # Return the parent context if it contains key tokens
                except:
                    pass
    
    return None
