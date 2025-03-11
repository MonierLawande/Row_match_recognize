from dataclasses import dataclass, field

@dataclass
class ExpressionAST:
    type: str           # e.g., "literal", "identifier", "binary"
    value: str = None   # literal value or identifier name
    operator: str = None
    children: list = field(default_factory=list)

def visualize_expression_ast(ast: ExpressionAST, indent=0) -> str:
    spacing = " " * indent
    if ast is None:
        return spacing + "None"
    result = f"{spacing}{ast.type}: {ast.value if ast.value else ''}"
    for child in ast.children:
        result += "\n" + visualize_expression_ast(child, indent + 2)
    return result
