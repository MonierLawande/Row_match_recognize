# src/parser/antlr_parser.py

from antlr4 import InputStream, CommonTokenStream, ParseTreeWalker
from src.grammar.TrinoLexer import TrinoLexer
from src.grammar.TrinoParser import TrinoParser
from src.grammar.TrinoParserListener import TrinoParserListener

# src/parser/antlr_parser.py - Fix for the error listener

class CustomErrorListener:
    def __init__(self):
        self.errors = []
        
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        error_message = f"Syntax error at {line}:{column} - {msg}"
        self.errors.append(error_message)
        
    def reportAmbiguity(self, recognizer, dfa, startIndex, stopIndex, exact, ambigAlts, configs):
        error_message = f"Ambiguity detected at {startIndex}:{stopIndex}"
        self.errors.append(error_message)
        
    def reportAttemptingFullContext(self, recognizer, dfa, startIndex, stopIndex, conflictingAlts, configs):
        # We don't need to report this, but the method must exist
        pass
        
    def reportContextSensitivity(self, recognizer, dfa, startIndex, stopIndex, prediction, configs):
        # We don't need to report this, but the method must exist
        pass
        
    def get_errors(self):
        return self.errors

def parse_input(query: str):
    """
    Initializes ANTLR lexer and parser and returns the parse tree.
    Enhanced with better error handling.
    """
    try:
        input_stream = InputStream(query)
        lexer = TrinoLexer(input_stream)
        error_listener = CustomErrorListener()
        lexer.removeErrorListeners()
        lexer.addErrorListener(error_listener)
        
        stream = CommonTokenStream(lexer)
        parser = TrinoParser(stream)
        parser.removeErrorListeners()
        parser.addErrorListener(error_listener)
        
        tree = parser.statements()  # assuming 'statements' is the entry rule
        return tree, parser, error_listener.get_errors()
    except Exception as e:
        return None, None, [f"ANTLR parsing error: {str(e)}"]

def extract_match_recognize_clause(tree):
    """
    Extract the MATCH_RECOGNIZE clause from the parse tree.
    This is a simplified implementation - in a real system,
    you would traverse the tree to find the MATCH_RECOGNIZE clause.
    """
    if hasattr(tree, 'matchRecognizeClause'):
        return tree.matchRecognizeClause()
    return None
