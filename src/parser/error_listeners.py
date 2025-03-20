from antlr4.error.ErrorListener import ErrorListener

class ParserError(Exception):
    def __init__(self, message, line=None, column=None, snippet=None):
        details = message
        if line is not None and column is not None:
            details += f" (Line: {line}, Column: {column})"
        if snippet:
            details += f"\nSnippet: {snippet}"
        super().__init__(details)
        self.line = line
        self.column = column
        self.snippet = snippet

class CustomErrorListener(ErrorListener):
    def __init__(self):
        super().__init__()

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        custom_msg = (f"Syntax error at line {line}, column {column}: {msg}. "
                      "Please verify your MATCH_RECOGNIZE clause syntax according to the specification.")
        raise ParserError(custom_msg, line=line, column=column,
                          snippet=recognizer.getInputStream().getText())