# src/ast/pattern_optimizer.py

def simplify_groups(ast):
    """
    Recursively simplifies unnecessary nested groups.
    For example, ((A)) is simplified to A.
    """
    if ast.type == "group" and len(ast.children) == 1 and ast.children[0].type == "group":
        return simplify_groups(ast.children[0])
    new_children = [simplify_groups(child) for child in ast.children]
    ast.children = new_children
    return ast

def merge_adjacent_literals(ast):
    """
    Merges adjacent literal nodes in a concatenation.
    This helps reduce redundancy in the pattern AST.
    """
    if ast.type != "concatenation":
        ast.children = [merge_adjacent_literals(child) for child in ast.children]
        return ast

    new_children = []
    i = 0
    while i < len(ast.children):
        current = ast.children[i]
        # If the next node is also a literal, merge them.
        if (i + 1 < len(ast.children) and current.type == "literal" and
                ast.children[i + 1].type == "literal"):
            merged_value = current.value + ast.children[i + 1].value
            merged_node = current
            merged_node.value = merged_value
            new_children.append(merged_node)
            i += 2
        else:
            new_children.append(merge_adjacent_literals(current))
            i += 1
    ast.children = new_children
    return ast

def reorder_alternations(ast):
    """
    Reorders branches in alternation nodes so that more complex patterns come first.
    This heuristic can improve performance during pattern matching.
    """
    if ast.type != "alternation":
        ast.children = [reorder_alternations(child) for child in ast.children]
        return ast

    def complexity(node):
        if node.type == "literal":
            return 1
        return 1 + sum(complexity(child) for child in node.children)
    
    ast.children.sort(key=lambda x: complexity(x), reverse=True)
    ast.children = [reorder_alternations(child) for child in ast.children]
    return ast

def optimize_pattern(pattern_ast):
    """
    Applies a series of optimizations to the pattern AST.
    It simplifies nested groups, merges adjacent literals, and reorders alternation branches.
    """
    if "ast" not in pattern_ast:
        return pattern_ast
    ast = pattern_ast["ast"]
    ast = simplify_groups(ast)
    ast = merge_adjacent_literals(ast)
    ast = reorder_alternations(ast)
    return {"raw": pattern_ast["raw"], "ast": ast}
