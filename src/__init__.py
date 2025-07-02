"""
Match Recognize SQL Pattern Matching Library
"""

__version__ = "0.1.0"

# Re-export match_recognize for easier access
from .executor.match_recognize import match_recognize

# Define what gets imported when someone does 'from src import *'
__all__ = ['match_recognize']