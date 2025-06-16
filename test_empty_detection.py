#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.matcher.pattern_tokenizer import tokenize_pattern
from src.matcher.automata import NFABuilder

def test_empty_pattern_detection():
    """Test if empty patterns are correctly detected in alternations."""
    
    # Test pattern: (() | A)
    pattern = "(() | A)"
    print(f"Testing pattern: {pattern}")
    
    try:
        # Tokenize the pattern
        tokens = tokenize_pattern(pattern)
        print("Tokens:")
        for i, token in enumerate(tokens):
            print(f"  {i}: {token.type.value} = '{token.value}'")
        
        # Build NFA
        nfa_builder = NFABuilder()
        nfa = nfa_builder.build(tokens, {"A": "true"})
        
        print(f"\nNFA metadata: {nfa.metadata}")
        print(f"Allows empty: {nfa.metadata.get('allows_empty', False)}")
        print(f"Has empty group: {nfa.metadata.get('has_empty_group', False)}")
        
        # Check NFA structure
        print(f"\nNFA structure:")
        print(f"  Start state: {nfa.start}")
        print(f"  Accept state: {nfa.accept}")
        print(f"  Total states: {len(nfa.states)}")
        
        # Check for direct epsilon path from start to accept (empty match)
        has_direct_path = nfa.accept in nfa.states[nfa.start].epsilon
        print(f"  Direct epsilon path from start to accept: {has_direct_path}")
        
        return nfa.metadata.get('allows_empty', False)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_empty_pattern_detection()
