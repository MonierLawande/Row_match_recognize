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
        
        # Parse the query
        parse_tree = parser.statements()
        
        return {
            "parse_tree": parse_tree,
            "parser": parser,  # Return the parser as well
            "errors": error_handler.get_formatted_errors(),
            "tokens": token_stream.tokens
        }
    except Exception as e:
        error_handler.add_error(f"Parsing error: {str(e)}", 0, 0)
        return {
            "parse_tree": None,
            "errors": error_handler.get_formatted_errors(),
            "tokens": []
        }
    

    