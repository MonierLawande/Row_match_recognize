import sys
import os
import pandas as pd
import time
import re
import logging
import itertools
from typing import List, Dict, Any, Optional, Set, Tuple, Union

# Add the parent directory to the path so we can import from src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the match_recognize function
from src.executor.match_recognize import match_recognize

# Import our modules
from src.matcher.pattern_tokenizer import tokenize_pattern, PatternTokenType
from src.matcher.automata import NFABuilder, NFA, NFAState, Transition
from src.matcher.dfa import DFABuilder
from src.matcher.condition_evaluator import compile_condition

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_permute_pattern():
    print("Testing PERMUTE pattern NFA construction...")
    
    # Define a simple PERMUTE pattern: PERMUTE(A, B, C)
    pattern_str = "PERMUTE(A, B, C)"
    tokens = tokenize_pattern(pattern_str)
    
    # Print the tokens for inspection
    print("Tokenized PERMUTE pattern:")
    for i, token in enumerate(tokens):
        print(f"  Token {i}: {token}")
    
    # Create NFA for pattern
    nfa_builder = NFABuilder()
    define = {
        'A': 'TRUE',
        'B': 'TRUE',
        'C': 'TRUE'
    }
    nfa = nfa_builder.build(tokens, define)
    
    # Print NFA structure
    print(f"\nNFA Structure for PERMUTE pattern:")
    print(f"  Start state: {nfa.start}")
    print(f"  Accept state: {nfa.accept}")
    print(f"  Number of states: {len(nfa.states)}")
    print(f"  Metadata: {nfa.metadata}")
    
    # Test with a nested PERMUTE pattern: PERMUTE(A, PERMUTE(B, C))
    nested_pattern_str = "PERMUTE(A, PERMUTE(B, C))"
    nested_tokens = tokenize_pattern(nested_pattern_str)
    
    # Print the nested tokens for inspection
    print("\nTokenized nested PERMUTE pattern:")
    for i, token in enumerate(nested_tokens):
        print(f"  Token {i}: {token}")
    
    # Create NFA for nested pattern
    nested_nfa = nfa_builder.build(nested_tokens, define)
    
    # Print nested NFA structure
    print(f"\nNFA Structure for nested PERMUTE pattern:")
    print(f"  Start state: {nested_nfa.start}")
    print(f"  Accept state: {nested_nfa.accept}")
    print(f"  Number of states: {len(nested_nfa.states)}")
    print(f"  Metadata: {nested_nfa.metadata}")
    
    return True

if __name__ == "__main__":
    success = test_permute_pattern()
    print(f"\nPermute pattern test {'succeeded' if success else 'failed'}")

    # Define sample data for testing
    df = pd.DataFrame({
        'id': range(1, 10),
        'category': ['A', 'B', 'C', 'A', 'B', 'C', 'A', 'B', 'C']
    })

    # Define a MATCH_RECOGNIZE query with PERMUTE pattern
    query = """
SELECT *
FROM df
MATCH_RECOGNIZE (
    PARTITION BY id % 4
    ORDER BY id
    MEASURES
        CLASSIFIER() AS var_match,
        MATCH_NUMBER() AS match_num
    PATTERN (PERMUTE(A, B, C))
    DEFINE
        A AS category = 'A',
        B AS category = 'B',
        C AS category = 'C'
)
"""

# Execute the query
    result = match_recognize(query, df)
    print("PERMUTE Pattern Result:")
    print(result)

# Test with a nested PERMUTE pattern
    nested_query = """
SELECT *
FROM df
MATCH_RECOGNIZE (
    PARTITION BY id % 4
    ORDER BY id
    MEASURES
        CLASSIFIER() AS var_match,
        MATCH_NUMBER() AS match_num
    PATTERN (PERMUTE(A, PERMUTE(B, C)))
    DEFINE
        A AS category = 'A',
        B AS category = 'B',
        C AS category = 'C'
)
"""

# Execute the nested query
    try:
        nested_result = match_recognize(nested_query, df)
        print("\nNested PERMUTE Pattern Result:")
        print(nested_result)
    except Exception as e:
        print(f"\nNested PERMUTE Pattern Error: {e}")
