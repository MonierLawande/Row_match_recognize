from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class ParserConfig:
    """Configuration for parser behavior"""
    max_nesting_level: int = 10
    allow_undefined_pattern_vars: bool = False
    validate_classifier: bool = True
    validate_semantics: bool = True
    optimize_patterns: bool = True
    custom_settings: Dict[str, Any] = field(default_factory=dict)
    
    def get_setting(self, key: str, default=None):
        return self.custom_settings.get(key, default)
