"""
SQL MATCH_RECOGNIZE for Pandas DataFrames

This package provides SQL:2016 MATCH_RECOGNIZE functionality for pandas DataFrames,
bringing powerful pattern matching capabilities to Python data science workflows.

Usage:
    from match_recognize import match_recognize
    
    result = match_recognize(sql_query, dataframe)

Features:
- Complete SQL:2016 MATCH_RECOGNIZE support
- Finite automata-based pattern matching
- Advanced pattern constructs (quantifiers, alternation, PERMUTE)
- High-performance execution engine
- Comprehensive measure evaluation
"""

from src.executor.match_recognize import match_recognize

# Package metadata
__version__ = "0.1.0"
__author__ = "MonierAshraf"
__email__ = "your.email@example.com"
__description__ = "SQL MATCH_RECOGNIZE for Pandas DataFrames"

# Export the main function
__all__ = ['match_recognize']