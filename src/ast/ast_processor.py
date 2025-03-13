# src/ast/ast_processor.py

from typing import Dict, Any, List, Optional
import json
from src.parser.pattern_parser import parse_pattern

class ASTProcessor:
    """
    Encapsulates AST processing between parsing and automaton conversion.
    
    This class handles:
    1. Building AST from parse tree
    2. Validating AST structure
    3. Optimizing AST
    4. Preparing AST for automaton conversion
    """
    
    def __init__(self):
        """Initialize the AST processor."""
        # Import here to avoid circular imports
        from src.parser.error_handler import ErrorHandler
        self.error_handler = ErrorHandler()
        
    def process_parse_tree(self, parse_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process parse tree into validated and optimized AST.
        
        Args:
            parse_result: Parse result from SQL parser
            
        Returns:
            Dictionary containing:
            - ast: The processed AST
            - pattern: Extracted pattern information for automaton
            - errors: Any processing errors
            - warnings: Any processing warnings
        """
        # Import here to avoid circular imports
        from src.ast.ast_builder import build_ast_from_parse_tree
        
        try:
            # Step 1: Build initial AST
            ast_result = build_ast_from_parse_tree(parse_result)
            
            if not ast_result or ast_result.get("errors"):
                return {
                    "ast": None,
                    "pattern": None,
                    "errors": ast_result.get("errors", ["Unknown AST building error"]),
                    "warnings": []
                }
                
            # Step 2: Extract pattern information for automaton conversion
            pattern_info = self._extract_pattern_info(ast_result["ast"])
            
            return {
                "ast": ast_result["ast"],
                "pattern": pattern_info,
                "errors": [],
                "warnings": []
            }
            
        except Exception as e:
            import traceback
            return {
                "ast": None,
                "pattern": None,
                "errors": [f"Error processing AST: {str(e)}\n{traceback.format_exc()}"],
                "warnings": []
            }
    
    def _extract_pattern_info(self, ast: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract pattern information needed for automaton conversion.
        
        Args:
            ast: The optimized AST
            
        Returns:
            Dictionary containing pattern information for automaton conversion
        """
        if not ast or "match_recognize" not in ast or not ast["match_recognize"]:
            return None
            
        # Get the first MATCH_RECOGNIZE clause
        mr = ast["match_recognize"][0]
        
        # Extract pattern structure
        pattern_structure = None
        pattern_text = None
        
        # Find the pattern text in the query
        if isinstance(mr, dict):
            # For dictionary-style AST
            if "pattern" in mr:
                pattern_obj = mr["pattern"]
                if isinstance(pattern_obj, dict):
                    if "raw" in pattern_obj:
                        pattern_text = pattern_obj["raw"]
                    if "ast" in pattern_obj:
                        pattern_structure = pattern_obj["ast"]
        else:
            # For object-style AST
            if hasattr(mr, 'pattern'):
                pattern_obj = mr.pattern
                if hasattr(pattern_obj, 'raw'):
                    pattern_text = pattern_obj.raw
                if hasattr(pattern_obj, 'ast'):
                    pattern_structure = pattern_obj.ast
        
        # If we have pattern text but no structure, parse it
        if pattern_text and not pattern_structure:
            try:
                # Extract the actual pattern from the text (remove parentheses)
                if pattern_text.startswith('(') and pattern_text.endswith(')'):
                    pattern_text = pattern_text[1:-1].strip()
                pattern_structure = parse_pattern(pattern_text)
            except Exception as e:
                self.error_handler.add_error(f"Error parsing pattern: {str(e)}", 0, 0)
        
        # Extract variable definitions
        variables = {}
        if isinstance(mr, dict) and "define" in mr:
            for var_def in mr["define"]:
                var_name = var_def.get("variable")
                condition = var_def.get("condition", {})
                if var_name:
                    variables[var_name] = condition
        elif hasattr(mr, 'define'):
            for var_def in mr.define:
                var_name = getattr(var_def, "variable", None)
                condition = getattr(var_def, "condition", {})
                if var_name:
                    variables[var_name] = condition
        
        # Extract other relevant information
        pattern_info = {
            "pattern_structure": pattern_structure,
            "pattern_text": pattern_text,
            "variables": variables,
            "is_greedy": True  # Default to greedy matching
        }
        
        # Extract additional properties based on object type
        if isinstance(mr, dict):
            pattern_info.update({
                "skip_behavior": mr.get("after_match_skip"),
                "rows_per_match": mr.get("rows_per_match"),
                "partition_by": mr.get("partition_by", []),
                "order_by": mr.get("order_by", []),
                "measures": mr.get("measures", [])
            })
        else:
            # Handle case where mr is an object with attributes
            pattern_info.update({
                "skip_behavior": getattr(mr, 'after_match_skip', None),
                "rows_per_match": getattr(mr, 'rows_per_match', None),
                "partition_by": getattr(mr, 'partition_by', []),
                "order_by": getattr(mr, 'order_by', []),
                "measures": getattr(mr, 'measures', [])
            })
        
        return pattern_info
