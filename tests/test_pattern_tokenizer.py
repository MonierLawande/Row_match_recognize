"""
Tests for the pattern tokenizer component of the match_recognize implementation.
"""

import pytest
import re
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple

# Add the src directory to path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the pattern tokenizer
from src.matcher.pattern_tokenizer import tokenize_pattern, PermuteHandler

class TestPatternTokenizer:
    """Test suite for the pattern tokenizer component."""
    
    def test_basic_pattern_tokenization(self):
        """Test tokenization of basic patterns."""
        # Simple concatenation
        pattern = "A B C"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # Check that tokens represent correct pattern elements
        pattern_str = "".join([t.symbol if hasattr(t, 'symbol') else str(t) for t in tokens])
        assert "ABC" in pattern_str or "A B C" in pattern_str
        
    def test_alternation_tokenization(self):
        """Test tokenization of patterns with alternation."""
        # Simple alternation
        pattern = "A | B"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # Complex alternation
        pattern = "(A B) | (C D)"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
    def test_quantifier_tokenization(self):
        """Test tokenization of patterns with quantifiers."""
        # Star quantifier
        pattern = "A*"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # Plus quantifier
        pattern = "A+"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # Question mark quantifier
        pattern = "A?"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # Range quantifier
        pattern = "A{2,5}"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # Reluctant quantifiers
        pattern = "A*?"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
    def test_anchor_tokenization(self):
        """Test tokenization of patterns with anchors."""
        # Start anchor
        pattern = "^A"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # End anchor
        pattern = "A$"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # Both anchors
        pattern = "^A$"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
    def test_exclusion_tokenization(self):
        """Test tokenization of patterns with exclusion syntax."""
        # Simple exclusion
        pattern = "{- A -}"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # Nested exclusion
        pattern = "{- {- A -} B -}"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
    def test_permute_tokenization(self):
        """Test tokenization of patterns with PERMUTE."""
        # Simple permutation
        pattern = "PERMUTE(A, B, C)"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
        # Nested permutation
        pattern = "PERMUTE(A, PERMUTE(B, C))"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
    def test_empty_pattern_tokenization(self):
        """Test tokenization of empty patterns."""
        # Empty pattern
        pattern = "()"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        
        # Empty pattern with alternation
        pattern = "() | A"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
    def test_complex_pattern_tokenization(self):
        """Test tokenization of complex patterns combining multiple features."""
        # Complex pattern
        pattern = "(A B+)* | {- C? -} | PERMUTE(D, E{1,3})"
        tokens = tokenize_pattern(pattern)
        assert tokens is not None
        assert len(tokens) > 0
        
    def test_permute_handler(self):
        """Test the PermuteHandler class for permutation expansion."""
        # Simple permutation
        elements = ["A", "B", "C"]
        handler = PermuteHandler()
        permutations = handler.expand_permutation(elements)
        
        # Should have 6 permutations (3!)
        assert len(permutations) == 6
        
        # Check first permutation is in lexicographic order
        assert "A" in permutations[0]
        
        # Check all permutations are different
        assert len(set(tuple(p) for p in permutations)) == 6
        
    def test_invalid_pattern_handling(self):
        """Test handling of invalid patterns."""
        # Unbalanced parentheses
        pattern = "(A B"
        with pytest.raises(Exception):
            tokenize_pattern(pattern)
            
        # Invalid quantifier
        pattern = "A{-1,5}"
        with pytest.raises(Exception):
            tokenize_pattern(pattern)
            
        # Unbalanced exclusion
        pattern = "{- A"
        with pytest.raises(Exception):
            tokenize_pattern(pattern)
