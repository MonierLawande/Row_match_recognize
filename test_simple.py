#!/usr/bin/env python3

def test_simple_case():
    """Test the simplest possible case"""
    try:
        from src.matcher.pattern_tokenizer import tokenize_pattern
        
        # Very simple test
        pattern = 'A'
        print(f"Testing pattern: {pattern}")
        
        tokens = tokenize_pattern(pattern)
        print(f"Tokens: {[(t.type.name, t.value, t.quantifier) for t in tokens]}")
        
        print("Tokenization successful!")
        
    except Exception as e:
        print(f"Error in tokenization: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_case()
