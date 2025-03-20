import re
from typing import Dict, List

def tokenize_pattern(pattern: str) -> Dict[str, List[str]]:
    """
    Tokenizes a row pattern string into a list of tokens (the full tokens with quantifiers)
    and a list of base tokens (identifiers without trailing quantifiers).

    This function supports patterns written with explicit whitespace or with no whitespace.
    For example:
      - "A b+ c*"  → variables: ["A", "b+", "c*"], base_variables: ["A", "b", "c"]
      - "AB+C"     → tokens: ["A", "B+", "C"] (using a lookahead to split when a new token begins)
      - "PERMUTE(A,B,C)" → tokens: ["A", "B", "C"]

    Note: For patterns without whitespace, we assume that a new token starts whenever an
    alphabetic character appears after the previous token’s (optional) quantifier.
    """
    original = pattern.strip()

    # If the pattern starts with PERMUTE( ... ), remove the wrapper.
    if original.upper().startswith("PERMUTE(") and original.endswith(")"):
        # Remove the PERMUTE( prefix and trailing ')'
        inner = original[len("PERMUTE("):-1]
        pattern_text = inner.strip()
    else:
        pattern_text = original

    # Optionally remove outer grouping parentheses, if they span the entire pattern.
    if pattern_text.startswith("(") and pattern_text.endswith(")") and balanced_parentheses(pattern_text):
        # Check that these are truly outer grouping parens (balanced when removed)
        pattern_text = pattern_text[1:-1].strip()

    # If there is any whitespace, split on whitespace.
    if re.search(r'\s', pattern_text):
        tokens = pattern_text.split()
    else:
        # Use a regex to detect token boundaries in a string with no whitespace.
        # We assume a token is an identifier followed by optional quantifier symbols.
        # The lookahead (?=[A-Za-z]|$) ensures we cut before the next letter or at the end.
        tokens = re.findall(r'([A-Za-z][A-Za-z0-9_]*[\*\+\?\{\}0-9]*)(?=[A-Za-z]|$)', pattern_text)

    # Clean tokens: remove commas if present.
    tokens = [token.replace(",", "") for token in tokens]

    # Derive base tokens by stripping off trailing quantifiers.
    base_tokens = [re.sub(r'[\*\+\?\{\}0-9]+$', '', token) for token in tokens]

    return {"variables": tokens, "base_variables": base_tokens}

def balanced_parentheses(s: str) -> bool:
    """Simple check to verify that parentheses in s are balanced."""
    count = 0
    for ch in s:
        if ch == '(':
            count += 1
        elif ch == ')':
            count -= 1
            if count < 0:
                return False
    return count == 0

# --- For manual testing ---
if __name__ == "__main__":
    examples = [
        "A b+ c*",
        "AB+C",
        "PERMUTE(A,B,C)",
        "(A B C)",
        "A{2,4}",
        "A{2,4}?",
        "X|Y|Z",
    ]
    for ex in examples:
        tokens = tokenize_pattern(ex)
        print(f"Pattern: {ex}\nTokens: {tokens}\n")
