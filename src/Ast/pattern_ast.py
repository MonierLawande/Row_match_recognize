from dataclasses import dataclass, field

@dataclass
class PatternAST:
    type: str   # e.g., "literal", "concatenation", "alternation", etc.
    value: str = None
    children: list = field(default_factory=list)
    excluded: bool = False

def visualize_pattern(ast: PatternAST, indent=0) -> str:
    spacing = " " * indent
    result = f"{spacing}{ast.type}"
    if ast.value:
        result += f": {ast.value}"
    if ast.excluded:
        result += " (excluded)"
    for child in ast.children:
        result += "\n" + visualize_pattern(child, indent + 2)
    return result
