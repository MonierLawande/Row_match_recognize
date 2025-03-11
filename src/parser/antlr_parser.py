from antlr4 import InputStream, CommonTokenStream
from src.grammar.TrinoLexer import TrinoLexer
from src.grammar.TrinoParser import TrinoParser
from src.grammar.TrinoParserListener import TrinoParserListener

class CustomErrorListener:
    def __init__(self):
        self.errors = []
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        error_message = f"Syntax error at {line}:{column} - {msg}"
        self.errors.append(error_message)
    def get_errors(self):
        return self.errors

def parse_input(query: str):
    """
    Initializes ANTLR lexer, parser and returns the parse tree.
    """
    input_stream = InputStream(query)
    lexer = TrinoLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = TrinoParser(stream)
    tree = parser.statements()  # assuming 'statements' is the entry rule
    return tree, parser
