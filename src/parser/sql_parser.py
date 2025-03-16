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
        
        return {
            "parse_tree": tree_info,
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
    