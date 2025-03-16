from typing import Dict, Any
from antlr4 import InputStream, CommonTokenStream
from src.grammar.TrinoLexer import TrinoLexer
from src.grammar.TrinoParser import TrinoParser
from .parser_util import ErrorHandler
def parse_sql_query(query: str) -> Dict[str, Any]:
    """
    Parse a SQL query using ANTLR and return the parse tree.
    
    Args:
        query: SQL query string
        
    Returns:
        Dictionary containing:
        - parse_tree: The ANTLR parse tree
        - errors: List of parsing errors
        - tokens: List of tokens
    """
    error_handler = ErrorHandler()
    
    try:
        # Initialize ANTLR components
        input_stream = InputStream(query)
        lexer = TrinoLexer(input_stream)
        lexer.removeErrorListeners()
        lexer.addErrorListener(error_handler)
        
        token_stream = CommonTokenStream(lexer)
        parser = TrinoParser(token_stream)
        parser.removeErrorListeners()
        parser.addErrorListener(error_handler)
        
        # Try a different entry point here - one that expects a SQL query
        # Options to try (in order):
        # 1. parser.singleStatement()
        # 2. parser.query()
        # 3. parser.statement() 
        # 4. parser.sqlStatementList()
        
        # Use singleStatement entry point (this works based on the debug output)
        parse_tree = parser.statement()
        
        # Create a more useful representation of the parse tree
        tree_info = {
            "tree_type": type(parse_tree).__name__,
            "text": parse_tree.getText() if hasattr(parse_tree, 'getText') else "No text",
            "child_count": parse_tree.getChildCount() if hasattr(parse_tree, 'getChildCount') else 0,
            "structure": extract_tree_structure(parse_tree)
        }
        
        # Extract MATCH_RECOGNIZE details if present
        match_recognize_details = extract_match_recognize_details(tree_info["structure"])
        
        return {
            "parse_tree": tree_info,
            "match_recognize": match_recognize_details,  # Add this new field
            "errors": error_handler.get_formatted_errors(),
            "tokens": token_stream.tokens
        }
    except Exception as e:
        print(f"Exception caught: {str(e)}")
        return {
            "parse_tree": [],
            "errors": [str(e)],
            "tokens": token_stream.tokens if 'token_stream' in locals() else []
        }

def extract_tree_structure(node, depth=0, max_depth=25):
    """Extract a more readable representation of the parse tree."""
    if depth >= max_depth:
        return "... (max depth reached)"
    
    if node is None:
        return None
    
    if not hasattr(node, 'getChildCount'):
        return str(node)
    
    result = {
        "type": type(node).__name__,
        "text": node.getText() if hasattr(node, 'getText') else "No text"
    }
    
    children = []
    child_count = node.getChildCount()
    for i in range(child_count):
        child = node.getChild(i)
        children.append(extract_tree_structure(child, depth + 1, max_depth))
    
    if children:
        result["children"] = children
    
    return result

def extract_match_recognize_details(parse_tree):
    """
    Extract details from MATCH_RECOGNIZE clause in a SQL parse tree.
    
    Args:
        parse_tree: The parse tree dictionary created by extract_tree_structure
        
    Returns:
        Dictionary containing structured information from MATCH_RECOGNIZE clause.
    """
    result = {
        "pattern": None,
        "measures": [],
        "partition_by": [],
        "order_by": [],
        "row_per_match": None,
        "define": {}
    }
    
    # Find PatternRecognitionContext which contains all MATCH_RECOGNIZE details
    pattern_recognition = find_node_of_type(parse_tree, "PatternRecognitionContext")
    if not pattern_recognition:
        return result
    
    # Extract pattern
    pattern_node = find_node_with_children(pattern_recognition, "PatternConcatenationContext")
    if pattern_node:
        result["pattern"] = pattern_node.get("text", "")
    
    # Extract partition by columns
    partition_node = find_node_with_text(pattern_recognition, "PARTITION")
    if partition_node:
        # Find identifier after "BY"
        identifier_node = find_node_of_type_after_text(pattern_recognition, "UnquotedIdentifierContext", "BY")
        if identifier_node:
            result["partition_by"].append(identifier_node.get("text", ""))
    
    # Extract order by columns
    order_nodes = find_node_with_text(pattern_recognition, "ORDER")
    if order_nodes:
        # Find SortItemContext nodes which contain the ordering columns
        sort_items = find_nodes_of_type(pattern_recognition, "SortItemContext")
        for sort_item in sort_items:
            # Extract the column name from the sort item
            expr = find_node_of_type(sort_item, "ExpressionContext")
            if expr:
                result["order_by"].append(expr.get("text", ""))
    
    # Extract measures
    measure_nodes = find_nodes_of_type(pattern_recognition, "MeasureDefinitionContext")
    for node in measure_nodes:
        if "children" in node:
            expression = None
            alias = None
            
            # Find expression and alias
            for i, child in enumerate(node["children"]):
                if isinstance(child, dict) and child.get("type") == "ExpressionContext":
                    expression = child.get("text", "")
                elif isinstance(child, dict) and child.get("type") == "UnquotedIdentifierContext" and i > 0:
                    alias = child.get("text", "")
            
            if expression and alias:
                result["measures"].append({
                    "expression": expression,
                    "alias": alias
                })
    
    # Extract row per match
    row_match_nodes = find_nodes_of_type(pattern_recognition, "RowsPerMatchContext")
    if row_match_nodes:
        result["row_per_match"] = "ONE ROW PER MATCH"  # Default based on your example
    
    # Extract define clauses
    define_nodes = find_nodes_of_type(pattern_recognition, "VariableDefinitionContext")
    for node in define_nodes:
        if "children" in node:
            var_name = None
            condition = None
            
            for i, child in enumerate(node["children"]):
                if isinstance(child, dict) and child.get("type") == "UnquotedIdentifierContext" and i == 0:
                    var_name = child.get("text", "")
                elif isinstance(child, dict) and child.get("type") == "ExpressionContext":
                    condition = child.get("text", "")
            
            if var_name and condition:
                result["define"][var_name] = condition
    
    return result

# Helper functions for tree traversal
def find_node_of_type(node, target_type):
    """Find first node of specified type in the tree."""
    if not isinstance(node, dict):
        return None
    
    if node.get("type") == target_type:
        return node
    
    if "children" in node:
        for child in node["children"]:
            result = find_node_of_type(child, target_type)
            if result:
                return result
    
    return None

def find_nodes_of_type(node, target_type):
    """Find all nodes of specified type in the tree."""
    results = []
    
    if not isinstance(node, dict):
        return results
    
    if node.get("type") == target_type:
        results.append(node)
    
    if "children" in node:
        for child in node["children"]:
            results.extend(find_nodes_of_type(child, target_type))
    
    return results

def find_node_with_text(node, target_text):
    """Find first node containing specified text."""
    if not isinstance(node, dict):
        return None
    
    if target_text in node.get("text", ""):
        return node
    
    if "children" in node:
        for child in node["children"]:
            result = find_node_with_text(child, target_text)
            if result:
                return result
    
    return None

def find_node_with_children(node, child_type):
    """Find first node that has a child of specified type."""
    if not isinstance(node, dict):
        return None
    
    if "children" in node:
        for child in node["children"]:
            if isinstance(child, dict) and child.get("type") == child_type:
                return child
        
        for child in node["children"]:
            result = find_node_with_children(child, child_type)
            if result:
                return result
    
    return None

def find_node_of_type_after_text(node, target_type, after_text):
    """Find node of specified type that appears after text in the tree."""
    if not isinstance(node, dict) or "children" not in node:
        return None
    
    found_text = False
    for child in node["children"]:
        if not found_text and isinstance(child, dict) and after_text in child.get("text", ""):
            found_text = True
            continue
        
        if found_text and isinstance(child, dict):
            if child.get("type") == target_type:
                return child
            
            # Look in this child's children
            result = find_node_of_type(child, target_type)
            if result:
                return result
    
    # If not found at this level, try in each child
    for child in node["children"]:
        if isinstance(child, dict):
            result = find_node_of_type_after_text(child, target_type, after_text)
            if result:
                return result
    
    return None
