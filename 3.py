"""
match_recognize_pattern.py
Handles row pattern parsing and normalization.
"""
from .AST import ExpressionAST, parse_expression_full

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)
# -------------------
# Advanced Pattern Parser with Subset Expansion
# -------------------
@dataclass
class PatternAST:
    type: str  # 'literal', 'quantifier', 'alternation', 'concatenation', 'group', 'permutation', 'exclusion'
    value: Optional[str] = None
    quantifier: Optional[str] = None
    quantifier_min: Optional[int] = None
    quantifier_max: Optional[int] = None
    children: List['PatternAST'] = field(default_factory=list)
    excluded: bool = False

class PatternParser:
    """
    An advanced pattern parser that builds a structured AST for a row pattern.
    """
    def __init__(self, pattern_text: str, subset_mapping: Dict[str, List[str]] = None):
        self.pattern_text = pattern_text
        self.subset_mapping = subset_mapping or {}
        self.tokens = self.tokenize(pattern_text)
        self.pos = 0
        
    def tokenize(self, pattern: str) -> List[str]:
        pattern = re.sub(r'PERMUTE\s*\(', 'PERMUTE_START ', pattern)
        pattern = pattern.replace('(', ' ( ').replace(')', ' ) ')
        pattern = pattern.replace('|', ' | ').replace('^', ' ^ ')
        pattern = pattern.replace('{', ' { ').replace('}', ' } ')
        pattern = pattern.replace(',', ' , ')
        pattern = pattern.replace('+', ' + ').replace('*', ' * ').replace('?', ' ? ')
        return [t for t in pattern.split() if t]
        
    def parse(self) -> PatternAST:
        ast = self.parse_pattern()
        if self.pos < len(self.tokens):
            raise ValueError(f"Unexpected tokens at end of pattern: {' '.join(self.tokens[self.pos:])}")
        return ast
        
    def parse_pattern(self) -> PatternAST:
        return self.parse_alternation()
        
    def parse_alternation(self) -> PatternAST:
        left = self.parse_concatenation()
        if self.pos < len(self.tokens) and self.tokens[self.pos] == '|':
            self.pos += 1  # Consume '|'
            alternatives = [left]
            alternatives.append(self.parse_alternation())
            return PatternAST(type="alternation", children=alternatives)
        return left
        
    def parse_concatenation(self) -> PatternAST:
        elements = []
        while self.pos < len(self.tokens) and self.tokens[self.pos] not in [')', '|']:
            elements.append(self.parse_quantified_element())
        if not elements:
            return PatternAST(type="empty")
        elif len(elements) == 1:
            return elements[0]
        else:
            return PatternAST(type="concatenation", children=elements)
            
    def parse_quantified_element(self) -> PatternAST:
        excluded = False
        if self.pos < len(self.tokens) and self.tokens[self.pos] == '^':
            excluded = True
            self.pos += 1  # Consume '^'
        element = self.parse_element()
        element.excluded = excluded
        if self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            if token in ['+', '*', '?']:
                self.pos += 1
                return PatternAST(type="quantifier", quantifier=token, children=[element], excluded=excluded)
            elif token == '{':
                self.pos += 1
                if self.pos >= len(self.tokens) or not self.tokens[self.pos].isdigit():
                    raise ValueError("Expected number after '{'")
                min_val = int(self.tokens[self.pos])
                self.pos += 1
                max_val = min_val
                if self.pos < len(self.tokens) and self.tokens[self.pos] == ',':
                    self.pos += 1
                    max_val = None
                    if self.pos < len(self.tokens) and self.tokens[self.pos].isdigit():
                        max_val = int(self.tokens[self.pos])
                        self.pos += 1
                        # Validate that min <= max
                        if max_val is not None and min_val > max_val:
                            raise ValueError(f"Invalid quantifier: minimum ({min_val}) cannot be greater than maximum ({max_val})")
                if self.pos >= len(self.tokens) or self.tokens[self.pos] != '}':
                    raise ValueError("Expected '}' in quantifier")
                self.pos += 1
                return PatternAST(type="quantifier",
                                quantifier="{n,m}",
                                quantifier_min=min_val,
                                quantifier_max=max_val,
                                children=[element],
                                excluded=excluded)
        return element

        
    def parse_element(self) -> PatternAST:
        if self.pos >= len(self.tokens):
            raise ValueError("Unexpected end of pattern")
        token = self.tokens[self.pos]
        self.pos += 1
        if token == '(':
            group_content = self.parse_alternation()
            if self.pos >= len(self.tokens) or self.tokens[self.pos] != ')':
                raise ValueError("Expected closing parenthesis ')'")
            self.pos += 1
            return PatternAST(type="group", children=[group_content])
        elif token == 'PERMUTE_START':
            elements = []
            while self.pos < len(self.tokens) and self.tokens[self.pos] != ')':
                if self.tokens[self.pos] == ',':
                    self.pos += 1
                    continue
                elements.append(PatternAST(type="literal", value=self.tokens[self.pos]))
                self.pos += 1
            if self.pos >= len(self.tokens) or self.tokens[self.pos] != ')':
                raise ValueError("Expected closing parenthesis ')' after PERMUTE")
            self.pos += 1
            return PatternAST(type="permutation", children=elements)
        else:
            if token in self.subset_mapping:
                # Expand subset into alternation
                alternatives = [PatternAST(type="literal", value=v) for v in self.subset_mapping[token]]
                return PatternAST(type="alternation", children=alternatives)
            else:
                return PatternAST(type="literal", value=token)

def parse_pattern_full(pattern_text: str, subset_mapping: Dict[str, List[str]] = None) -> Dict[str, Any]:
    """
    Parses a pattern string into a structured AST with subset expansion.
    """
    try:
        if '(' in pattern_text and ')' not in pattern_text:
            raise ValueError("Unclosed parenthesis in pattern")
        if pattern_text.endswith('|'):
            raise ValueError("Trailing alternation operator")
        if pattern_text.strip().endswith('|'):
            raise ValueError("Trailing alternation operator")
        if '|' in pattern_text and pattern_text.split('|')[-1].strip() == '':
            raise ValueError("Trailing alternation operator")
        open_count = pattern_text.count('(')
        close_count = pattern_text.count(')')
        if open_count != close_count:
            raise ValueError(f"Unbalanced parentheses in pattern: {open_count} opening vs {close_count} closing")
            
        # Check for invalid quantifiers like {3,2}
        quantifier_matches = re.findall(r'\{(\d+),(\d+)\}', pattern_text)
        for min_val, max_val in quantifier_matches:
            if int(min_val) > int(max_val):
                raise ValueError(f"Invalid quantifier: minimum ({min_val}) cannot be greater than maximum ({max_val})")
                
        parser = PatternParser(pattern_text, subset_mapping)
        ast = parser.parse()
        logger.debug("Parsed pattern '%s' into AST: %s", pattern_text, ast)
        return {"raw": pattern_text.strip(), "ast": ast}
    except Exception as e:
        logger.error("Failed to parse pattern '%s': %s", pattern_text, str(e))
        raise  # Re-raise the exception to be caught by the test



def validate_pattern(pattern_ast: PatternAST, defined_variables: set) -> List[str]:
    """
    Validates a pattern AST against defined variables and pattern rules.
    
    Args:
        pattern_ast: The pattern AST to validate
        defined_variables: Set of variable names defined in the DEFINE clause
        
    Returns:
        List of validation error messages
    """
    errors = []
    used_variables = set()
    
    # Collect all variables used in the pattern
    def collect_variables(node):
        if node.type == "literal":
            used_variables.add(node.value)
        for child in node.children:
            collect_variables(child)
    
    collect_variables(pattern_ast)
    
    # Check if all used variables are defined
    undefined = used_variables - defined_variables
    if undefined:
        errors.append(f"Pattern uses undefined variables: {', '.join(undefined)}")
    
    # Check for invalid quantifiers
    def check_quantifiers(node):
        if node.type == "quantifier":
            if node.quantifier == "{n,m}" and node.quantifier_min is not None and node.quantifier_max is not None:
                if node.quantifier_min > node.quantifier_max:
                    errors.append(f"Invalid quantifier: minimum ({node.quantifier_min}) cannot be greater than maximum ({node.quantifier_max})")
        for child in node.children:
            check_quantifiers(child)
    
    check_quantifiers(pattern_ast)
    
    return errors

# -------------------
# Pattern Visitor (Alternative Implementation)
# -------------------
class PatternVisitor:
    """
    Example of a visitor-based pattern parser.
    """
    def parse(self, pattern_text: str, subset_mapping: Dict[str, List[str]] = None) -> Dict[str, Any]:
        tokens = self.tokenize(pattern_text)
        ast, _ = self.parse_concatenation(tokens, subset_mapping)
        logger.debug("Parsed pattern '%s' into AST: %s", pattern_text, ast)
        return {"raw": pattern_text.strip(), "ast": ast}

    def tokenize(self, pattern: str) -> List[str]:
        tokens = re.findall(r'\w+|\S', pattern)
        return tokens

    def parse_concatenation(self, tokens: List[str], subset_mapping: Dict[str, List[str]] = None, pos: int = 0):
        nodes = []
        while pos < len(tokens) and tokens[pos] != ')':
            token = tokens[pos]
            if token == '(':
                group_node, pos = self.parse_group(tokens, subset_mapping, pos + 1)
                nodes.append(group_node)
            elif token in ['|']:
                break
            else:
                node, pos = self.parse_element(tokens, subset_mapping, pos)
                nodes.append(node)
        return PatternAST(type="concatenation", children=nodes), pos

    def parse_group(self, tokens: List[str], subset_mapping: Dict[str, List[str]], pos: int):
        node, pos = self.parse_concatenation(tokens, subset_mapping, pos)
        if pos < len(tokens) and tokens[pos] == ')':
            pos += 1
        return PatternAST(type="group", children=[node]), pos

    def parse_element(self, tokens: List[str], subset_mapping: Dict[str, List[str]], pos: int):
        token = tokens[pos]
        pos += 1
        node = PatternAST(type="literal", value=token)
        if pos < len(tokens) and tokens[pos] in ['+', '*', '?']:
            quant = tokens[pos]
            pos += 1
            node = PatternAST(type="quantifier", value=node.value, quantifier=quant)
        if subset_mapping and node.type == "literal" and node.value in subset_mapping:
            alternatives = [PatternAST(type="literal", value=v) for v in subset_mapping[node.value]]
            node = PatternAST(type="alternation", children=alternatives)
        return node, pos

def parse_pattern_full_visitor(pattern_text: str, subset_mapping: Dict[str, List[str]] = None) -> Dict[str, Any]:
    visitor = PatternVisitor()
    return visitor.parse(pattern_text, subset_mapping)

def optimize_pattern(pattern_ast: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimizes a pattern AST for better performance.
    """
    logger.debug("Optimizing pattern AST: %s", pattern_ast)
    
    if "ast" not in pattern_ast:
        return pattern_ast
        
    ast = pattern_ast["ast"]
    
    # Apply optimizations
    optimized_ast = simplify_groups(ast)
    optimized_ast = merge_adjacent_literals(optimized_ast)
    optimized_ast = reorder_alternations(optimized_ast)
    
    return {
        "raw": pattern_ast["raw"],
        "ast": optimized_ast
    }


def simplify_groups(ast: PatternAST) -> PatternAST:
    """
    Simplifies unnecessary nested groups.
    For example: ((A)) -> (A)
    """
    # Base case: if this is a group with a single child that is also a group
    if ast.type == "group" and len(ast.children) == 1 and ast.children[0].type == "group":
        # Skip this group and return the simplified version of its child
        return simplify_groups(ast.children[0])
    
    # For all other nodes, recursively process children
    new_children = []
    for child in ast.children:
        new_children.append(simplify_groups(child))
    
    # Replace the children with simplified versions
    ast.children = new_children
    return ast



def merge_adjacent_literals(ast: PatternAST) -> PatternAST:
    """
    Merges adjacent literals with the same quantifier.
    For example: A+ A+ -> A+
    """
    if ast.type != "concatenation":
        # Recursively process children
        new_children = [merge_adjacent_literals(child) for child in ast.children]
        ast.children = new_children
        return ast
        
    # Process concatenation children
    i = 0
    new_children = []
    while i < len(ast.children):
        current = ast.children[i]
        
        # Look ahead for mergeable nodes
        if i + 1 < len(ast.children):
            next_node = ast.children[i + 1]
            if (current.type == "quantifier" and next_node.type == "quantifier" and
                current.quantifier == next_node.quantifier and
                current.children[0].type == "literal" and next_node.children[0].type == "literal" and
                current.children[0].value == next_node.children[0].value):
                # Merge and skip the next node
                i += 2
                new_children.append(current)
                continue
                
        # Process this node recursively
        new_children.append(merge_adjacent_literals(current))
        i += 1
        
    ast.children = new_children
    return ast

def reorder_alternations(ast: PatternAST) -> PatternAST:
    """
    Reorders alternations for better performance.
    For example, puts more specific patterns first.
    """
    if ast.type != "alternation":
        # Recursively process children
        new_children = [reorder_alternations(child) for child in ast.children]
        ast.children = new_children
        return ast
        
    # Sort alternation children by complexity (more complex first)
    # This is a heuristic that can be adjusted based on performance testing
    def complexity_score(node):
        if node.type == "literal":
            return 1
        elif node.type == "quantifier":
            if node.quantifier == "+":
                return complexity_score(node.children[0]) * 2
            elif node.quantifier == "*":
                return complexity_score(node.children[0]) * 1.5
            elif node.quantifier == "?":
                return complexity_score(node.children[0]) * 1.2
            else:
                return complexity_score(node.children[0]) * 2.5
        else:
            return sum(complexity_score(child) for child in node.children) + 1
            
    ast.children.sort(key=complexity_score, reverse=True)
    
    # Recursively process children
    new_children = [reorder_alternations(child) for child in ast.children]
    ast.children = new_children
    return ast


# -------------------
# Pattern Normalization Helper
# -------------------
def normalize_pattern(pattern: str) -> Dict[str, str]:
    """
    Normalize a pattern string for consistent parsing.
    Preserves spaces between pattern variables.
    """
    raw = pattern.strip()
    
    # First preserve existing spaces between variables
    normalized = " " + raw + " "  # Add sentinel spaces
    
    # Ensure spaces around operators while preserving variable boundaries
    normalized = re.sub(r'([A-Za-z0-9])([\+\*\?])', r'\1 \2', normalized)  # Add space before +*?
    normalized = re.sub(r'([\+\*\?])([A-Za-z0-9])', r'\1 \2', normalized)  # Add space after +*?
    
    # Ensure spaces around parentheses
    normalized = re.sub(r'([A-Za-z0-9])(\()', r'\1 \2', normalized)
    normalized = re.sub(r'(\))([A-Za-z0-9])', r'\1 \2', normalized)
    
    # Ensure spaces around alternation
    normalized = re.sub(r'([A-Za-z0-9])(\|)', r'\1 \2', normalized)
    normalized = re.sub(r'(\|)([A-Za-z0-9])', r'\1 \2', normalized)
    
    # Compact multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Remove sentinel spaces
    normalized = normalized.strip()
    
    logger.debug(f"Normalized pattern from '{raw}' to '{normalized}'")
    return {"raw": raw, "normalized": normalized}

def visualize_pattern(pattern_ast: PatternAST, indent: int = 0) -> str:
    """
    Creates a visual representation of the pattern AST.
    
    Args:
        pattern_ast: The pattern AST to visualize
        indent: Current indentation level
        
    Returns:
        String representation of the pattern AST
    """
    result = " " * indent
    
    if pattern_ast.type == "literal":
        result += f"LITERAL: {pattern_ast.value}"
        if pattern_ast.excluded:
            result += " (EXCLUDED)"
    elif pattern_ast.type == "quantifier":
        result += f"QUANTIFIER: {pattern_ast.quantifier}"
        if pattern_ast.quantifier_min is not None:
            result += f" min={pattern_ast.quantifier_min}"
        if pattern_ast.quantifier_max is not None:
            result += f" max={pattern_ast.quantifier_max}"
        result += "\n"
        for child in pattern_ast.children:
            result += visualize_pattern(child, indent + 2)
    elif pattern_ast.type == "alternation":
        result += "ALTERNATION:\n"
        for child in pattern_ast.children:
            result += visualize_pattern(child, indent + 2) + "\n"
    elif pattern_ast.type == "concatenation":
        result += "CONCATENATION:\n"
        for child in pattern_ast.children:
            result += visualize_pattern(child, indent + 2) + "\n"
    elif pattern_ast.type == "group":
        result += "GROUP:\n"
        for child in pattern_ast.children:
            result += visualize_pattern(child, indent + 2)
    elif pattern_ast.type == "permutation":
        result += "PERMUTATION:\n"
        for child in pattern_ast.children:
            result += visualize_pattern(child, indent + 2) + "\n"
    elif pattern_ast.type == "empty":
        result += "EMPTY"
    
    return result

def analyze_pattern_complexity(pattern_ast: PatternAST) -> Dict[str, Any]:
    """
    Analyzes a pattern AST to determine its complexity.
    
    Args:
        pattern_ast: The pattern AST to analyze
        
    Returns:
        Dictionary with complexity metrics
    """
    metrics = {
        "literal_count": 0,
        "alternation_count": 0,
        "quantifier_count": 0,
        "group_count": 0,
        "permutation_count": 0,
        "max_nesting_level": 0,
        "estimated_complexity": 0.0
    }
    
    def analyze_node(node, level=0):
        if node.type == "alternation":
            metrics["alternation_count"] += 1
        elif node.type == "group":
            metrics["group_nesting_level"] = max(metrics["group_nesting_level"], level + 1)
        elif node.type == "quantifier":
            metrics["quantifier_count"] += 1
        elif node.type == "permutation":
            metrics["permutation_count"] += 1
        elif node.type == "literal":
            metrics["literal_count"] += 1
                
        for child in node.children:
            analyze_node(child, level + 1 if node.type == "group" else level)
    
    analyze_node(pattern_ast)
    
    # Calculate complexity score for query planning
    complexity = (
        metrics["alternation_count"] * 2.0 +
        metrics["group_nesting_level"] * 1.5 +
        metrics["quantifier_count"] * 1.8 +
        metrics["permutation_count"] * 3.0 +
        metrics["literal_count"]
    )
    
    metrics["estimated_complexity"] = complexity
    return metrics

def are_patterns_equivalent(pattern1: PatternAST, pattern2: PatternAST) -> bool:
    """Determine if two pattern ASTs are semantically equivalent."""
    # Simple case: both are literals
    if pattern1.type == "literal" and pattern2.type == "literal":
        return pattern1.value == pattern2.value and pattern1.excluded == pattern2.excluded
    
    # Compare properties
    if pattern1.type != pattern2.type or pattern1.quantifier != pattern2.quantifier:
        return False
    
    if pattern1.quantifier_min != pattern2.quantifier_min or pattern1.quantifier_max != pattern2.quantifier_max:
        return False
        
    # Check children count
    if len(pattern1.children) != len(pattern2.children):
        return False
        
    # For alternation, order doesn't matter
    if pattern1.type == "alternation":
        # Try to match each child from pattern1 with one from pattern2
        matched = [False] * len(pattern2.children)
        for child1 in pattern1.children:
            found_match = False
            for i, child2 in enumerate(pattern2.children):
                if not matched[i] and are_patterns_equivalent(child1, child2):
                    matched[i] = True
                    found_match = True
                    break
            if not found_match:
                return False
        return all(matched)
    
    # For other node types, order matters
    for i in range(len(pattern1.children)):
        if not are_patterns_equivalent(pattern1.children[i], pattern2.children[i]):
            return False
            
    return True

def detect_equivalent_branches(pattern_ast: PatternAST) -> PatternAST:
    """Detect and merge equivalent branches in alternations (e.g., A|A → A)."""
    if pattern_ast.type != "alternation":
        # Process children recursively
        new_children = [detect_equivalent_branches(child) for child in pattern_ast.children]
        pattern_ast.children = new_children
        return pattern_ast
    
    # Process children first
    processed_children = [detect_equivalent_branches(child) for child in pattern_ast.children]
    unique_children = []
    
    for child in processed_children:
        # Check if this child is equivalent to any already processed
        if not any(are_patterns_equivalent(child, existing) for existing in unique_children):
            unique_children.append(child)
    
    # If reduced to a single child, return it directly
    if len(unique_children) == 1:
        return unique_children[0]
    
    # Otherwise, update the alternation with unique children
    pattern_ast.children = unique_children
    return pattern_ast

def detect_performance_risks(pattern_ast: PatternAST) -> List[str]:
    """Detect patterns that might lead to performance issues."""
    warnings = []
    
    def has_nested_quantifier(node, in_quantifier=False):
        """Recursively check for nested quantifiers in the pattern tree"""
        if node.type == "quantifier":
            if in_quantifier:
                return True
            
            # Check children with in_quantifier=True
            for child in node.children:
                if has_nested_quantifier(child, True):
                    return True
        
        # Check all children
        for child in node.children:
            if has_nested_quantifier(child, in_quantifier):
                return True
                
        return False
    
    # Check for nested quantifiers which can cause exponential backtracking
    if has_nested_quantifier(pattern_ast):
        warnings.append("Pattern has nested quantifiers which may cause excessive backtracking")
    
    # Check for unbounded repetition
    def has_unbounded_quantifier(node):
        if node.type == "quantifier" and node.quantifier == "*":
            return True
        return any(has_unbounded_quantifier(child) for child in node.children)
    
    if has_unbounded_quantifier(pattern_ast):
        warnings.append("Pattern uses unbounded repetition (*) which may consume excessive memory")
    
    # Check complexity
    complexity = analyze_pattern_complexity(pattern_ast)
    if complexity["estimated_complexity"] > 10.0:
        warnings.append(f"Pattern has high complexity ({complexity['estimated_complexity']:.1f}) which may impact performance")
    
    return warnings


def document_pattern_examples():
    """Generate examples of pattern parsing and optimization for documentation."""
    examples = [
        # Basic patterns
        {"pattern": "A B+ C?", "description": "Basic pattern with quantifiers"},
        
        # Group simplification
        {"pattern": "((A))", "description": "Nested group optimization"},
        
        # Alternation optimization
        {"pattern": "(A|A|B)", "description": "Equivalent branch elimination"},
        
        # Complex patterns
        {"pattern": "A (B|C)+ D?", "description": "Mixed quantifiers and alternation"},
        
        # Exclusion patterns
        {"pattern": "A ^B C", "description": "Pattern with exclusion"},
        
        # Permutations
        {"pattern": "PERMUTE(A,B,C)", "description": "Permutation pattern"}
    ]
    
    for example in examples:
        pattern = example["pattern"]
        print(f"\n{example['description']}:")
        print(f"Pattern: {pattern}")
        
        # Parse and optimize
        parsed = parse_pattern_full(pattern)
        print("Original AST:")
        print(visualize_pattern(parsed["ast"]))
        
        optimized = optimize_pattern(parsed)
        print("Optimized AST:")
        print(visualize_pattern(optimized["ast"]))
        
        # Show complexity analysis
        complexity = analyze_pattern_complexity(optimized["ast"])
        print(f"Complexity metrics: {complexity}")

# Add these functions to match_recognize_pattern.py

def analyze_pattern_complexity(pattern_ast: PatternAST) -> Dict[str, Any]:
    """
    Analyzes a pattern AST to determine its complexity.
    
    Args:
        pattern_ast: The pattern AST to analyze
        
    Returns:
        Dictionary with complexity metrics
    """
    metrics = {
        "literal_count": 0,
        "alternation_count": 0,
        "quantifier_count": 0,
        "group_count": 0,
        "permutation_count": 0,
        "max_nesting_level": 0,
        "estimated_complexity": 0.0
    }
    
    def analyze_node(node, nesting_level=0):
        # Update max nesting level
        metrics["max_nesting_level"] = max(metrics["max_nesting_level"], nesting_level)
        
        # Count by node type
        if node.type == "literal":
            metrics["literal_count"] += 1
        elif node.type == "alternation":
            metrics["alternation_count"] += 1
        elif node.type == "quantifier":
            metrics["quantifier_count"] += 1
        elif node.type == "group":
            metrics["group_count"] += 1
        elif node.type == "permutation":
            metrics["permutation_count"] += 1
            
        # Recursively process children
        for child in node.children:
            analyze_node(child, nesting_level + 1)
    
    # Start analysis from root
    analyze_node(pattern_ast)
    
    # Calculate estimated complexity score
    # This is a heuristic that can be tuned based on performance testing
    complexity = (
        metrics["literal_count"] * 1.0 +
        metrics["alternation_count"] * 2.5 +
        metrics["quantifier_count"] * 2.0 +
        metrics["group_count"] * 1.5 +
        metrics["permutation_count"] * 3.0 +
        metrics["max_nesting_level"] * 1.2
    )
    metrics["estimated_complexity"] = complexity
    
    return metrics

def detect_performance_risks(pattern_ast: PatternAST) -> List[str]:
    """
    Analyzes a pattern AST for performance risks.
    
    Args:
        pattern_ast: The pattern AST to analyze
        
    Returns:
        List of warning messages about potential performance issues
    """
    warnings = []
    
    # Analyze pattern complexity to warn about potentially expensive patterns
    complexity = analyze_pattern_complexity(pattern_ast)
    if complexity["estimated_complexity"] > 20:
        warnings.append(f"Pattern has high complexity ({complexity['estimated_complexity']:.1f}), which may impact performance")
    
    def check_node(node, path=""):
        # Check for unbounded repetitions (* quantifier)
        if node.type == "quantifier" and node.quantifier == "*":
            warnings.append(f"Pattern uses unbounded repetition (*) which may cause excessive backtracking")
        
        # Check for nested quantifiers (e.g., (A+)+) which can cause catastrophic backtracking
        if node.type == "quantifier":
            for child in node.children:
                if child.type == "quantifier":
                    warnings.append(f"Pattern has nested quantifiers which may cause excessive backtracking")
        
        # Check for complex alternations with quantifiers
        if node.type == "alternation":
            has_quantified_branches = False
            for child in node.children:
                # Look for quantifiers in this alternation branch
                if child.type == "quantifier" or any(grandchild.type == "quantifier" for grandchild in child.children):
                    has_quantified_branches = True
            
            if has_quantified_branches and len(node.children) > 1:
                warnings.append(f"Pattern has alternation with quantified branches which may cause backtracking issues")
        
        # Recursively check children
        for child in node.children:
            check_node(child)
    
    check_node(pattern_ast)
    return warnings

def are_patterns_equivalent(pattern1: PatternAST, pattern2: PatternAST) -> bool:
    """
    Checks if two pattern ASTs are semantically equivalent.
    
    Args:
        pattern1: First pattern AST
        pattern2: Second pattern AST
        
    Returns:
        True if patterns are equivalent, False otherwise
    """
    # Base case: patterns have different types
    if pattern1.type != pattern2.type:
        return False
        
    # Check type-specific attributes
    if pattern1.type == "literal":
        return pattern1.value == pattern2.value
    elif pattern1.type == "quantifier":
        # Check quantifier properties
        if pattern1.quantifier != pattern2.quantifier:
            return False
        if pattern1.quantifier_min != pattern2.quantifier_min:
            return False
        if pattern1.quantifier_max != pattern2.quantifier_max:
            return False
        # Check children (should be exactly one)
        if len(pattern1.children) != len(pattern2.children):
            return False
        return are_patterns_equivalent(pattern1.children[0], pattern2.children[0])
    elif pattern1.type in ["alternation", "concatenation", "group", "permutation"]:
        # Check children (order matters except for alternation)
        if len(pattern1.children) != len(pattern2.children):
            return False
            
        if pattern1.type == "alternation":
            # For alternation, order doesn't matter, so we need to check if each child
            # from pattern1 has an equivalent in pattern2
            for child1 in pattern1.children:
                matched = False
                for child2 in pattern2.children:
                    if are_patterns_equivalent(child1, child2):
                        matched = True
                        break
                if not matched:
                    return False
            return True
        else:
            # For other types, order matters
            for i in range(len(pattern1.children)):
                if not are_patterns_equivalent(pattern1.children[i], pattern2.children[i]):
                    return False
            return True
    
    # Default for unhandled cases
    return True

def detect_equivalent_branches(pattern_ast: PatternAST) -> PatternAST:
    """
    Detects and merges equivalent branches in alternation patterns.
    
    Args:
        pattern_ast: The pattern AST to optimize
        
    Returns:
        Optimized pattern AST
    """
    # Process children recursively first
    new_children = []
    for child in pattern_ast.children:
        new_children.append(detect_equivalent_branches(child))
    pattern_ast.children = new_children
    
    # Apply optimization for alternation nodes
    if pattern_ast.type == "alternation":
        # Keep track of unique branches
        unique_branches = []
        for child in pattern_ast.children:
            is_duplicate = False
            for existing in unique_branches:
                if are_patterns_equivalent(child, existing):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_branches.append(child)
        
        # If we removed duplicates, update the AST
        if len(unique_branches) < len(pattern_ast.children):
            if len(unique_branches) == 1:
                # If only one branch remains, replace alternation with the single branch
                return unique_branches[0]
            else:
                # Otherwise, update children with unique branches
                pattern_ast.children = unique_branches
    
    return pattern_ast

def print_pattern_visualization(pattern: Dict[str, Any]):
    """
    Prints a visual representation of a pattern.
    
    Args:
        pattern: Pattern dictionary with 'raw' and 'ast' keys
    """
    if "ast" in pattern:
        print(f"Pattern: {pattern['raw']}")
        print(visualize_pattern(pattern["ast"]))
    else:
        print(f"Invalid pattern: {pattern}")
