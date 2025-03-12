from dataclasses import dataclass, field

@dataclass
class PatternAST:
    type: str                   # "literal", "concatenation", "alternation", "group", "quantifier", "permutation", "empty"
    value: str = None           # For literal nodes
    children: list = field(default_factory=list)
    excluded: bool = False      # For exclusion syntax
    quantifier: str = None      # For quantifier nodes: "+", "*", "?", or "{n,m}"
    quantifier_min: int = None  # For bounded quantifiers
    quantifier_max: int = None  # For bounded quantifiers

def visualize_pattern(ast: PatternAST, indent=0) -> str:
    spacing = " " * indent
    result = f"{spacing}{ast.type}"
    if ast.value:
        result += f": {ast.value}"
    if ast.excluded:
        result += " (excluded)"
    if ast.quantifier:
        result += f" [quantifier: {ast.quantifier}"
        if ast.quantifier_min is not None:
            result += f", min: {ast.quantifier_min}"
        if ast.quantifier_max is not None:
            result += f", max: {ast.quantifier_max}"
        result += "]"
    for child in ast.children:
        result += "\n" + visualize_pattern(child, indent + 2)
    return result
