# src/matcher/matcher.py

from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
from dataclasses import dataclass
from src.matcher.dfa import DFA, FAIL_STATE
from src.matcher.row_context import RowContext
from src.matcher.measure_evaluator import MeasureEvaluator
from src.matcher.pattern_tokenizer import PatternTokenType

class SkipMode(Enum):
    PAST_LAST_ROW = "PAST_LAST_ROW"
    TO_NEXT_ROW = "TO_NEXT_ROW"
    TO_FIRST = "TO_FIRST"
    TO_LAST = "TO_LAST"

class RowsPerMatch(Enum):
    ONE_ROW = "ONE_ROW"
    ALL_ROWS = "ALL_ROWS"
    ALL_ROWS_SHOW_EMPTY = "ALL_ROWS_SHOW_EMPTY"
    ALL_ROWS_WITH_UNMATCHED = "ALL_ROWS_WITH_UNMATCHED"

@dataclass
class MatchConfig:
    """Configuration for pattern matching behavior."""
    def __init__(self, rows_per_match, skip_mode, skip_var=None, show_empty=True, include_unmatched=False):
        self.rows_per_match = rows_per_match
        self.skip_mode = skip_mode
        self.skip_var = skip_var
        self.show_empty = show_empty
        self.include_unmatched = include_unmatched
        
        # Map to dictionary for compatibility
        self._config_dict = {
            "all_rows": rows_per_match != RowsPerMatch.ONE_ROW,
            "show_empty": show_empty,
            "with_unmatched": include_unmatched,
            "skip_mode": skip_mode,
            "skip_var": skip_var
        }
    
    def get(self, key, default=None):
        """Dictionary-like get method for compatibility."""
        return self._config_dict.get(key, default)

class EnhancedMatcher:
    def __init__(self, dfa, measures=None, measure_semantics=None, exclusion_ranges=None, 
             after_match_skip="PAST LAST ROW", subsets=None, original_pattern=None):
        """Initialize the enhanced matcher."""
        self.dfa = dfa
        self.start_state = dfa.start
        self.measures = measures or {}
        self.measure_semantics = measure_semantics or {}
        self.exclusion_ranges = exclusion_ranges or []
        self.after_match_skip = after_match_skip
        self.subsets = subsets or {}
        self.original_pattern = original_pattern or ""
    
    def find_matches(self, rows, config=None, measures=None):
        """Find all matches with proper ALL ROWS PER MATCH handling."""
        results = []
        match_number = 1
        start_idx = 0
        unmatched_indices = set(range(len(rows)))  # Track unmatched rows
        
        # Get configuration
        all_rows = False
        show_empty = True
        include_unmatched = False  # Initialize the variable
        
        if config:
            all_rows = config.rows_per_match != RowsPerMatch.ONE_ROW
            show_empty = config.show_empty
            include_unmatched = config.include_unmatched  # Extract from config
        
        print(f"Find matches with all_rows={all_rows}, show_empty={show_empty}, include_unmatched={include_unmatched}")
        
        while start_idx < len(rows):
            # Create context for pattern matching
            context = RowContext()
            context.rows = rows
            
            # Find next match
            match = self._find_single_match(rows, start_idx, context)
            if not match:
                start_idx += 1
                continue
                
            # Process the match
            if all_rows:
                print(f"Processing match {match_number} with ALL ROWS PER MATCH")
                # Process ALL rows in the match
                match_rows = self._process_all_rows_match(match, rows, measures, match_number)
                results.extend(match_rows)
                
                # Remove matched indices from unmatched set
                if match.get("variables"):
                    for indices in match["variables"].values():
                        unmatched_indices -= set(indices)
            else:
                print(f"Processing match {match_number} with ONE ROW PER MATCH")
                # Process just one row per match
                match_row = self._process_one_row_match(match, rows, measures, match_number)
                if match_row:
                    results.append(match_row)
                    
                    # Remove matched indices from unmatched set
                    if match.get("variables"):
                        for indices in match["variables"].values():
                            unmatched_indices -= set(indices)
            
            # Update start index based on after match skip mode
            if match.get("is_empty", False):
                start_idx = match["start"] + 1
            else:
                # Use the appropriate skip mode
                if config and config.skip_mode:
                    start_idx = self._get_skip_position(config.skip_mode, config.skip_var, match)
                else:
                    start_idx = match["end"] + 1
                
            match_number += 1
        
        # Add unmatched rows if requested
        if include_unmatched:  # Now this variable is defined
            for idx in sorted(unmatched_indices):
                unmatched_row = self._handle_unmatched_row(rows[idx], measures or {})
                results.append(unmatched_row)
            
        return results

    def _process_all_rows_match(self, match, rows, measures, match_number):
        """Process ALL rows in a match with proper handling for multiple rows and exclusions."""
        results = []
        
        # Get all matched row indices
        matched_indices = []
        excluded_indices = set()
        
        # Create a mapping of pattern variables to excluded status
        excluded_vars = set()
        
        # First, identify excluded variables based on pattern exclusions
        pattern_text = None
        for var_name in match["variables"].keys():
            # Check if this variable appears in an exclusion range in the pattern
            if "{-" in self.original_pattern and "-}" in self.original_pattern:
                # Simple check: if the variable is between {- and -}
                # For a more robust implementation, use the exclusion_ranges from NFA
                exclusion_parts = self.original_pattern.split("{-")
                for part in exclusion_parts[1:]:  # Skip the first part (before any {-)
                    if "-}" in part:
                        excluded_pattern = part.split("-}")[0].strip()
                        # Check if var_name is in the excluded pattern
                        if var_name in excluded_pattern:
                            excluded_vars.add(var_name)
        
        print(f"Variables in exclusion pattern: {excluded_vars}")
        
        # Now separate matched indices from excluded indices
        for var, indices in match["variables"].items():
            if var in excluded_vars:
                excluded_indices.update(indices)
            else:
                matched_indices.extend(indices)
        
        matched_indices = sorted(set(matched_indices))  # Use set to remove duplicates
        excluded_indices = sorted(excluded_indices)
        
        print(f"Processing match {match_number}, included indices: {matched_indices}")
        if excluded_indices:
            print(f"Excluded indices: {excluded_indices}")
        
        # Create context for the match - includes ALL rows for measure calculation
        context = RowContext()
        context.rows = rows
        context.variables = match["variables"]
        context.match_number = match_number
        
        # Add subset information if available
        if hasattr(self, "subsets") and self.subsets:
            for subset_name, component_vars in self.subsets.items():
                context.subsets[subset_name] = component_vars
        
        # Process each matched row individually (excluding excluded rows)
        for idx in matched_indices:
            if idx >= len(rows):
                continue
                
            # Create result row from original data
            result = rows[idx].copy()
            
            # Set context position for measure calculation
            context.current_idx = idx
            
            # Calculate measures for this specific row
            for alias, expr in measures.items():
                try:
                    # Create new evaluator for each row
                    evaluator = MeasureEvaluator(context)
                    
                    # Get measure semantics - ALWAYS use RUNNING for ALL ROWS PER MATCH
                    semantics = "RUNNING"
                    
                    # Evaluate measure
                    result[alias] = evaluator.evaluate(expr, semantics)
                    print(f"Evaluated measure {alias} for row {idx} with RUNNING semantics: {result[alias]}")
                except Exception as e:
                    print(f"Error evaluating measure {alias} for row {idx}: {e}")
                    result[alias] = None
            
            # Add match metadata
            result["MATCH_NUMBER"] = match_number
            result["IS_EMPTY_MATCH"] = match.get("is_empty", False)
            
            results.append(result)
            print(f"Added row {idx} to results")
        
        return results

    
    def _is_excluded(self, row_idx: int, match_start: int, exclude_ranges: List[Tuple[int, int]]) -> bool:
        """Check if a row is in an excluded range."""
        if not exclude_ranges:
            return False
            
        rel_idx = row_idx - match_start
        return any(start <= rel_idx <= end for start, end in exclude_ranges)


    def _process_one_row_match(self, match, rows, measures, match_number):
        """Process one row per match."""
        if match["start"] >= len(rows):
            return None
        
        # Handle empty match case
        if match.get("is_empty", False):
            return self._process_empty_match(match["start"], rows, measures, match_number)
            
        # Use first row of match
        result = rows[match["start"]].copy()
        
        # Create context
        context = RowContext()
        context.rows = rows
        context.variables = match["variables"]
        context.match_number = match_number
        
        # Add subset information if available
        if hasattr(self, "subsets") and self.subsets:
            for subset_name, component_vars in self.subsets.items():
                context.subsets[subset_name] = component_vars
        
        # Add measures with FINAL semantics
        evaluator = MeasureEvaluator(context, final=True)
        for alias, expr in measures.items():
            try:
                semantics = "FINAL"  # Always use FINAL for ONE ROW PER MATCH
                result[alias] = evaluator.evaluate(expr, semantics)
            except Exception as e:
                print(f"Error evaluating measure {alias}: {e}")
                result[alias] = None
        
        # Add match metadata
        result["MATCH_NUMBER"] = match_number
        result["IS_EMPTY_MATCH"] = match.get("is_empty", False)
        
        return result

    def _find_single_match(self, rows: List[Dict[str, Any]], start_idx: int, context: RowContext) -> Optional[Dict[str, Any]]:
        """Find a single match starting from the given index with enhanced debugging."""
        state = self.start_state
        current_idx = start_idx
        var_assignments = {}
        
        print(f"Starting match at index {start_idx}, state: {state}")
        
        # Check if start state is accepting - this would be an empty match
        if self.dfa.states[state].is_accept:
            print(f"Found empty match at index {start_idx} - start state is accepting")
            empty_match = {
                "start": start_idx,
                "end": start_idx - 1,  # Empty match ends before it starts
                "variables": {},        # Empty match has no variable assignments
                "state": state,
                "is_empty": True
            }
            return empty_match
        
        longest_match = None
        
        while current_idx < len(rows):
            row = rows[current_idx]
            context.current_idx = current_idx
            
            # Debug output before evaluating transitions
            print(f"Testing row {current_idx}, data: {row}")
            
            # Debug transitions available
            transitions = self.dfa.states[state].transitions
            if transitions:
                print(f"  Available transitions: {[t.variable for t in transitions]}")
            else:
                print(f"  No transitions available from state {state}")
                break
            
            next_state = None
            matched_var = None
            
            for transition in transitions:
                try:
                    print(f"  Evaluating condition for var: {transition.variable}")
                    result = transition.condition(row, context)
                    print(f"    Condition {'passed' if result else 'failed'} for {transition.variable}")
                    if result:
                        next_state = transition.target
                        matched_var = transition.variable
                        break
                except Exception as e:
                    print(f"  Error evaluating condition for {transition.variable}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            if next_state is None:
                print(f"No valid transition from state {state} at row {current_idx}")
                break
                
            # Record variable assignment
            if matched_var:
                if matched_var not in var_assignments:
                    var_assignments[matched_var] = []
                var_assignments[matched_var].append(current_idx)
                print(f"  Assigned row {current_idx} to variable {matched_var}")
            
            state = next_state
            current_idx += 1
            
            # If we've reached an accepting state, update the longest match
            if self.dfa.states[state].is_accept:
                print(f"Reached accepting state {state} at row {current_idx-1}")
                longest_match = {
                    "start": start_idx,
                    "end": current_idx - 1,
                    "variables": {k: v[:] for k, v in var_assignments.items()},
                    "state": state,
                    "is_empty": False
                }
                print(f"  Current longest match: {start_idx}-{current_idx-1}, vars: {list(var_assignments.keys())}")
        
        if longest_match:
            print(f"Found match: {longest_match}")
        else:
            print(f"No match found starting at index {start_idx}")
        
        return longest_match
    
    def _process_empty_match(self,
                           start_idx: int,
                           rows: List[Dict[str, Any]],
                           measures: Dict[str, str],
                           match_number: int) -> Dict[str, Any]:
        """Process an empty match."""
        # Start with the starting row's values
        if start_idx >= len(rows):
            return None
            
        result = rows[start_idx].copy()
        
        # Create context for empty match
        context = RowContext()
        context.rows = rows
        context.variables = {}
        context.match_number = match_number
        context.current_idx = start_idx
        
        # Add measures as NULL values or evaluate them if possible
        for alias, expr in measures.items():
            try:
                # For special measures like MATCH_NUMBER(), try to evaluate
                if expr.upper() == "MATCH_NUMBER()":
                    result[alias] = match_number
                else:
                    # For other measures, use NULL
                    result[alias] = None
            except Exception:
                result[alias] = None
            
        # Add match metadata
        result["MATCH_NUMBER"] = match_number
        result["IS_EMPTY_MATCH"] = True
        
        return result

    def _validate_skip_target(self, 
                            skip_var: str, 
                            match: Dict[str, Any]) -> bool:
        """
        Validate that skipping to the specified variable is allowed.
        Prevents infinite loops and invalid skip targets.
        """
        if not skip_var:
            return True
            
        # Get indices for the skip target variable
        var_indices = match["variables"].get(skip_var, [])
        if not var_indices:
            return False  # Variable not present in match
            
        # Check if skipping would create an infinite loop
        start_idx = match["start"]
        skip_idx = min(var_indices)  # For TO_FIRST
        
        # Can't skip to or before the start of current match
        return skip_idx > start_idx

    def _get_skip_position(self,
                          skip_mode: SkipMode,
                          skip_var: Optional[str],
                          match: Dict[str, Any]) -> int:
        """
        Determine the next position to start matching based on skip mode.
        """
        start_idx = match["start"]
        end_idx = match["end"]
        
        if skip_mode == SkipMode.PAST_LAST_ROW:
            return end_idx + 1
            
        elif skip_mode == SkipMode.TO_NEXT_ROW:
            return start_idx + 1
            
        elif skip_mode in (SkipMode.TO_FIRST, SkipMode.TO_LAST) and skip_var:
            if skip_var in match["variables"]:
                var_indices = match["variables"][skip_var]
                if skip_mode == SkipMode.TO_FIRST:
                    return min(var_indices) + 1
                else:  # TO_LAST
                    return max(var_indices) + 1
                    
        # Default: move to next position
        return start_idx + 1

    def _is_excluded(self, 
                    row_idx: int, 
                    match_start: int,
                    exclude_ranges: List[Tuple[int, int]]) -> bool:
        """Check if a row is in an excluded range."""
        if not exclude_ranges:
            return False
            
        rel_idx = row_idx - match_start
        return any(start <= rel_idx <= end for start, end in exclude_ranges)

    def _get_match_variables(self, 
                           match: Dict[str, Any], 
                           context: RowContext) -> Set[str]:
        """Get all variables (primary and union) present in the match."""
        variables = set(match["variables"].keys())
        
        # Add union variables that are present
        for subset_name, components in context.subsets.items():
            if any(comp in variables for comp in components):
                variables.add(subset_name)
                
        return variables

    def _evaluate_running_measure(self,
                                expr: str,
                                context: RowContext,
                                current_idx: int) -> Any:
        """
        Evaluate a measure with running semantics from the perspective
        of the row at current_idx.
        """
        # Save current context state
        original_idx = context.current_idx
        
        try:
            # Set context to evaluate from current row's perspective
            context.current_idx = current_idx
            
            evaluator = MeasureEvaluator(context, final=False)
            return evaluator.evaluate(expr)
            
        finally:
            # Restore original context state
            context.current_idx = original_idx

    def _evaluate_final_measure(self,
                              expr: str,
                              context: RowContext) -> Any:
        """
        Evaluate a measure with final semantics using the complete match.
        """
        evaluator = MeasureEvaluator(context, final=True)
        return evaluator.evaluate(expr)

    def _create_empty_measures(self,
                             measures: Dict[str, str]) -> Dict[str, None]:
        """Create NULL values for all measures."""
        return {alias: None for alias in measures}

    def _handle_unmatched_row(self,
                             row: Dict[str, Any],
                             measures: Dict[str, str]) -> Dict[str, Any]:
        """Create output row for unmatched input row."""
        result = row.copy()
        result.update({
            "MATCH_NUMBER": None,
            "IS_EMPTY_MATCH": False,
            **self._create_empty_measures(measures)
        })
        return result

    def _check_anchors(self, state: int, row_idx: int, total_rows: int) -> bool:
        """Check if anchor conditions are satisfied."""
        state_info = self.dfa.states[state]
        
        if state_info.is_anchor:
            if state_info.anchor_type == PatternTokenType.ANCHOR_START:
                # ^ anchor must match at partition start
                return row_idx == 0
            elif state_info.anchor_type == PatternTokenType.ANCHOR_END:
                # $ anchor must match at partition end
                return row_idx == total_rows - 1
        return True
