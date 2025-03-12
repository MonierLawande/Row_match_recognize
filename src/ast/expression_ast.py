from dataclasses import dataclass, field

@dataclass
class ExpressionAST:
    type: str                   # "binary", "literal", "identifier", "pattern_variable_reference", etc.
    value: str = None           # For literal and identifier nodes
    operator: str = None        # For binary operation nodes
    children: list = field(default_factory=list)
    pattern_variable: str = None  # For pattern variable references
    column: str = None          # For pattern variable references
    semantics: str = None       # For RUNNING/FINAL semantics
    navigation_type: str = None  # For navigation functions
    offset: int = 0             # For navigation functions
    count_star: bool = False    # For count(*) and count(var.*)
    line: int = 0               # Line number in source
    column: int = 0             # Column number in source

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
