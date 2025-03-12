# src/parser/config.py

from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class ParserConfig:
    """Configuration for parser behavior"""
    
    # Maximum nesting level for expressions and patterns
    max_nesting_level: int = 10
    
    # Whether to allow undefined pattern variables
    allow_undefined_pattern_vars: bool = False
    
    # Whether to validate classifier function consistency
    validate_classifier: bool = True
    
    # Whether to validate RUNNING/FINAL semantics
    validate_semantics: bool = True
    
    # Whether to optimize patterns
    optimize_patterns: bool = True
    
    # Custom settings
    custom_settings: Dict[str, Any] = field(default_factory=dict)
    
    def get_setting(self, key: str, default=None):
        """Get a custom setting with fallback to default"""
        return self.custom_settings.get(key, default)
