#!/usr/bin/env python3

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_basic_imports():
    """Test just basic imports"""
    try:
        print("Testing imports...")
        from src.matcher.pattern_tokenizer import tokenize_pattern
        print("✅ Pattern tokenizer imported")
        
        from src.matcher.automata import NFABuilder
        print("✅ NFA builder imported")
        
        tokens = tokenize_pattern("() | A")
        print(f"✅ Pattern tokenized: {len(tokens)} tokens")
        
        nfa_builder = NFABuilder()
        print("✅ NFA builder created")
        
        nfa = nfa_builder.build(tokens, {"A": "value > 15"})
        print("✅ NFA built successfully")
        print(f"NFA metadata: {nfa.metadata}")
        
        from src.matcher.dfa import DFABuilder
        dfa_builder = DFABuilder(nfa)
        dfa = dfa_builder.build()
        print("✅ DFA built successfully")
        print(f"DFA metadata: {dfa.metadata}")
        
        print("✅ All basic components working!")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_basic_imports()
