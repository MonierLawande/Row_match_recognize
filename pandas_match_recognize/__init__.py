"""
SQL MATCH_RECOGNIZE for Pandas DataFrames

This package provides SQL:2016 MATCH_RECOGNIZE functionality for pandas DataFrames,
bringing powerful pattern matching capabilities to Python data science workflows.

🚀 Features:
- Complete SQL:2016 MATCH_RECOGNIZE support
- High-performance finite automata engine  
- Advanced pattern constructs (quantifiers, alternation, PERMUTE)
- Comprehensive measure evaluation

Usage:
    from pandas_match_recognize import match_recognize
    
    result = match_recognize(sql_query, dataframe)

Features:
- Complete SQL:2016 MATCH_RECOGNIZE support  
- Finite automata-based pattern matching
- Advanced pattern constructs (quantifiers, alternation, PERMUTE)
- High-performance execution engine
- Comprehensive measure evaluation

Example:
    import pandas as pd
    from pandas_match_recognize import match_recognize
    
    # Sample data
    df = pd.DataFrame({
        'customer_id': [1, 1, 1],
        'order_date': ['2023-01-01', '2023-01-02', '2023-01-03'],
        'price': [100, 80, 60]
    })
    
    # Pattern matching query
    sql = '''
        SELECT * FROM df 
        MATCH_RECOGNIZE (
            PARTITION BY customer_id 
            ORDER BY order_date
            PATTERN (A B+ C)
            DEFINE 
                B AS B.price < A.price,
                C AS C.price < B.price
        )
    '''
    
    result = match_recognize(sql, df)
    print(result)
"""

# Import the main function
try:
    # Try to import from the sibling src package (when properly packaged)
    import sys
    import os
    
    # Add the project root to Python path so we can import src
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_current_dir)
    
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    
    from src.executor.match_recognize import match_recognize
    
except ImportError as e:
    # Fallback error message
    raise ImportError(
        f"Could not import match_recognize function. "
        f"This usually means the package wasn't installed correctly. "
        f"Original error: {e}\n\n"
        f"Try:\n"
        f"1. Reinstall: pip uninstall pandas-match-recognize && pip install pandas-match-recognize\n"
        f"2. Or use development install: pip install -e .\n"
        f"3. Or import directly: from match_recognize import match_recognize"
    )

# Package metadata
# Version information
__version__ = "0.1.5"
__author__ = "MonierAshraf"
__description__ = "SQL MATCH_RECOGNIZE for Pandas DataFrames"

# Export the main function
__all__ = ['match_recognize']