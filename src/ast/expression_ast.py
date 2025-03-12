from dataclasses import dataclass, field

@dataclass
class ExpressionAST:
    type: str                    # "literal", "identifier", "binary", "navigation", etc.
    value: str = None            # Literal value or identifier name
    operator: str = None         # For binary operations
    children: list = field(default_factory=list)
    # Fields for navigation functions:
    navigation_type: str = None  # "PREV", "NEXT", "FIRST", "LAST"
    offset: int = 0              # Optional offset for navigation
    # Field for semantics (e.g., RUNNING, FINAL)
    semantics: str = None

def visualize_expression_ast(ast: ExpressionAST, indent=0) -> str:
    spacing = " " * indent
    result = f"{spacing}{ast.type}"
    if ast.value:
        result += f": {ast.value}"
    if ast.navigation_type:
        result += f" (nav: {ast.navigation_type}, offset: {ast.offset})"
    if ast.semantics:
        result += f" [{ast.semantics}]"
    for child in ast.children:
        result += "\n" + visualize_expression_ast(child, indent + 2)
    return result
