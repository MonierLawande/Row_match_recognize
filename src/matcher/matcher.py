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
    def __init__(self, dfa, measures=None, exclusion_ranges=None, after_match_skip="PAST LAST ROW", subsets=None):
        """Initialize the enhanced matcher."""
        self.dfa = dfa
        self.start_state = dfa.start
        self.measures = measures or {}
        self.exclusion_ranges = exclusion_ranges or []
        self.after_match_skip = after_match_skip
        self.subsets = subsets or {}

    def find_matches(self, rows, config=None, measures=None):
        """Find all matches in the input rows."""
        # Use provided measures or fall back to instance measures
        measures = measures or self.measures
        
        # Extract configuration options from MatchConfig object
        if config:
            if hasattr(config, 'rows_per_match'):
                # It's a MatchConfig object
                all_rows = config.rows_per_match != RowsPerMatch.ONE_ROW
                show_empty = config.show_empty
                with_unmatched = config.include_unmatched
            else:
                # It's a dictionary
                all_rows = config.get("all_rows", False)
                show_empty = config.get("show_empty", True)
                with_unmatched = config.get("with_unmatched", False)
        else:
            # Default configuration
            all_rows = False
            show_empty = True
            with_unmatched = False
        
        results = []
        context = RowContext()
        context.rows = rows
        
        # Track which rows have been matched
        matched_rows = set()
        match_number = 1
        
        start_idx = 0
        while start_idx < len(rows):
            match = self._find_single_match(rows, start_idx, context)
            
            # Process match if found
            if match:
                if all_rows:
                    # ALL ROWS PER MATCH mode
                    match_rows = self._process_all_rows_match(
                        match, 
                        rows, 
                        measures,
                        match_number,
                        self.exclusion_ranges,
                        show_empty
                    )
                else:
                    # ONE ROW PER MATCH mode
                    match_row = self._process_one_row_match(
                        match, 
                        rows, 
                        measures,
                        match_number
                    )
                    match_rows = [match_row] if match_row else []
                
                # Add match rows to results
                results.extend(match_rows)
                
                # Add matched rows to the set
                if not match.get("is_empty", False):
                    for i in range(match["start"], match["end"] + 1):
                        matched_rows.add(i)
                
                # Determine where to continue search
                if match.get("is_empty", False):
                    # Always advance by at least one position for empty matches
                    start_idx = match["start"] + 1
                elif self.after_match_skip == "PAST LAST ROW":
                    start_idx = match["end"] + 1
                elif self.after_match_skip == "TO NEXT ROW":
                    start_idx = match["start"] + 1
                else:
                    # Skip to specific position based on variable
                    start_idx = match["end"] + 1  # Default to PAST LAST ROW
                
                match_number += 1
            else:
                # No match found, move to next row
                start_idx += 1
        
        # Handle unmatched rows if requested
        if all_rows and with_unmatched:
            for i in range(len(rows)):
                if i not in matched_rows:
                    unmatched_row = rows[i].copy()
                    
                    # Add NULL measures for unmatched rows
                    for alias in measures:
                        unmatched_row[alias] = None
                    
                    # Add unmatched metadata
                    unmatched_row["MATCH_NUMBER"] = None
                    unmatched_row["IS_UNMATCHED"] = True
                    
                    results.append(unmatched_row)
        
        return results

    def _find_single_match(self, rows: List[Dict[str, Any]], start_idx: int, context: RowContext) -> Optional[Dict[str, Any]]:
        """Find a single match starting at the given index."""
        state = self.start_state
        current_idx = start_idx
        var_assignments = {}
        
        # Debug output 
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
        
        # Keep track of the longest match found so far
        longest_match = None
        
        while current_idx < len(rows):
            row = rows[current_idx]
            context.current_idx = current_idx - start_idx  # Relative to match start
            
            # Try transitions from current state
            next_state = None
            matched_var = None
            
            for transition in self.dfa.states[state].transitions:
                try:
                    print(f"Testing row {current_idx}, evaluating condition for var: {transition.variable}")
                    if transition.condition(row, context):
                        print(f"  Condition passed for {transition.variable}")
                        next_state = transition.target
                        matched_var = transition.variable
                        break
                    else:
                        print(f"  Condition failed for {transition.variable}")
                except Exception as e:
                    print(f"Error evaluating condition: {e}")
                    continue
            
            if next_state is None:
                print(f"No valid transition from state {state} at row {current_idx}, breaking")
                break
                
            # Record variable assignment
            if matched_var:
                if matched_var not in var_assignments:
                    var_assignments[matched_var] = []
                var_assignments[matched_var].append(current_idx)
            
            state = next_state
            current_idx += 1
            
            # If we've reached an accepting state, update the longest match
            if self.dfa.states[state].is_accept:
                print(f"Reached accepting state {state} at row {current_idx-1}")
                longest_match = {
                    "start": start_idx,
                    "end": current_idx - 1,
                    "variables": {k: v[:] for k, v in var_assignments.items()},  # Deep copy
                    "state": state,
                    "is_empty": False
                }
        
        return longest_match

    def _process_one_row_match(self, match: Dict[str, Any], rows: List[Dict[str, Any]], measures: Dict[str, str], match_number: int) -> Dict[str, Any]:
        """Process a match in ONE ROW PER MATCH mode."""
        start_idx = match["start"]
        end_idx = match["end"]
        
        # Handle empty match specially
        is_empty_match = match.get("is_empty", False) or not match["variables"]
        
        # Create context with ALL rows
        context = RowContext()
        context.rows = rows  # Use the entire dataset for navigation
        
        # Use the original indices from the match
        context.variables = match["variables"]
        context.match_number = match_number
        
        # For empty matches, position at starting row
        # For regular matches, position at final row
        if is_empty_match:
            context.current_idx = start_idx
        else:
            context.current_idx = end_idx
        
        # Start with appropriate row values
        result = rows[start_idx].copy() if start_idx < len(rows) else {}
        
        # Add measures
        if is_empty_match:
            # For empty matches, follow empty match semantics
            for alias, expr in measures.items():
                if "COUNT(*)" in expr or "COUNT()" in expr:
                    result[alias] = 0  # COUNT(*) = 0 for empty matches
                else:
                    result[alias] = None  # All other measures are NULL
        else:
            # Regular match processing with FINAL semantics
            evaluator = MeasureEvaluator(context, final=True)
            for alias, expr in measures.items():
                try:
                    result[alias] = evaluator.evaluate(expr)
                except Exception as e:
                    print(f"Error evaluating measure {alias}: {e}")
                    result[alias] = None
        
        # Add match metadata
        result["MATCH_NUMBER"] = match_number
        result["IS_EMPTY_MATCH"] = is_empty_match
        
        return result

    def _process_all_rows_match(self, match: Dict[str, Any], rows: List[Dict[str, Any]], measures: Dict[str, str], 
                              match_number: int, exclude_ranges: List = None, show_empty: bool = True) -> List[Dict[str, Any]]:
        """Process a match in ALL ROWS PER MATCH mode."""
        start_idx = match["start"]
        end_idx = match["end"]
        
        # Handle empty match specially
        is_empty_match = match.get("is_empty", False) or not match["variables"]
        
        # Check if we should skip this empty match
        if is_empty_match and not show_empty:
            return []
        
        # For empty matches, create a single row with NULL measures
        if is_empty_match:
            if start_idx < len(rows):
                result = [rows[start_idx].copy()]
                
                # Create empty match context
                context = RowContext()
                context.rows = rows
                context.variables = {}
                context.match_number = match_number
                context.current_idx = start_idx
                
                # Add measures according to empty match semantics
                for alias, expr in measures.items():
                    if "COUNT(*)" in expr or "COUNT()" in expr:
                        result[0][alias] = 0
                    else:
                        result[0][alias] = None
                
                # Add match metadata
                result[0]["MATCH_NUMBER"] = match_number
                result[0]["IS_EMPTY_MATCH"] = True
                
                return result
            return []
        
        # Regular non-empty match processing
        results = []
        
        # Create base context
        context = RowContext()
        context.rows = rows
        context.variables = match["variables"]
        context.match_number = match_number
        
        # Process each row in the match
        for i in range(start_idx, end_idx + 1):
            # Skip excluded rows
            if exclude_ranges and any(start <= i - start_idx <= end for start, end in exclude_ranges):
                continue
            
            # Update context for current row
            context.current_idx = i
            
            # Start with the current row's values
            result = rows[i].copy()
            
            # Add measures with RUNNING semantics
            evaluator = MeasureEvaluator(context, final=False)
            for alias, expr in measures.items():
                try:
                    result[alias] = evaluator.evaluate(expr)
                except Exception as e:
                    print(f"Error evaluating measure {alias}: {e}")
                    result[alias] = None
            
            # Add match metadata
            result["MATCH_NUMBER"] = match_number
            result["IS_EMPTY_MATCH"] = False
            
            results.append(result)
        
        return results



    def _find_single_match(self, 
                        rows: List[Dict[str, Any]], 
                        start_idx: int,
                        context: RowContext) -> Optional[Dict[str, Any]]:
        """Find a single match starting at the given index."""
        state = self.start_state
        current_idx = start_idx
        var_assignments = {}
        
        # Debug output 
        print(f"Starting match at index {start_idx}, state: {state}")
        
        # Check if start state is accepting - this would be an empty match
        # This is the critical change for empty match detection
        if self.dfa.states[state].is_accept:
            print(f"Found empty match at index {start_idx} - start state is accepting")
            empty_match = {
                "start": start_idx,
                "end": start_idx - 1,  # Empty match ends before it starts
                "variables": {},        # Empty match has no variable assignments
                "state": state,
                "is_empty": True
            }
            return empty_match  # Immediately return the empty match
        
        # Keep track of the longest match found so far
        longest_match = None
        
        while current_idx < len(rows):
            row = rows[current_idx]
            context.current_idx = current_idx - start_idx  # Relative to match start
            
            # Try transitions from current state
            next_state = None
            matched_var = None
            
            for transition in self.dfa.states[state].transitions:
                try:
                    print(f"Testing row {current_idx}, evaluating condition for var: {transition.variable}")
                    if transition.condition(row, context):
                        print(f"  Condition passed for {transition.variable}")
                        next_state = transition.target
                        matched_var = transition.variable
                        break
                    else:
                        print(f"  Condition failed for {transition.variable}")
                except Exception as e:
                    print(f"Error evaluating condition: {e}")
                    continue
            
            if next_state is None:
                print(f"No valid transition from state {state} at row {current_idx}, breaking")
                break
                
            # Record variable assignment
            if matched_var:
                if matched_var not in var_assignments:
                    var_assignments[matched_var] = []
                var_assignments[matched_var].append(current_idx)
            
            state = next_state
            current_idx += 1
            
            # If we've reached an accepting state, update the longest match
            if self.dfa.states[state].is_accept:
                print(f"Reached accepting state {state} at row {current_idx-1}")
                longest_match = {
                    "start": start_idx,
                    "end": current_idx - 1,
                    "variables": {k: v[:] for k, v in var_assignments.items()},  # Deep copy
                    "state": state,
                    "is_empty": False
                }
        
        # Return the longest match found
        if longest_match:
            print(f"Found match: {longest_match}")
        else:
            print(f"No match found starting at index {start_idx}")
        return longest_match


    def _process_one_row_match(self,
                            match: Dict[str, Any],
                            rows: List[Dict[str, Any]],
                            measures: Dict[str, str],
                            match_number: int) -> Dict[str, Any]:
        """Process a match in ONE ROW PER MATCH mode."""
        start_idx = match["start"]
        end_idx = match["end"]
        
        # Handle empty match specially
        is_empty_match = match.get("is_empty", False) or not match["variables"]
        
        # Create context with ALL rows, not just matched rows
        context = RowContext()
        context.rows = rows  # Use the entire dataset for navigation
        
        # Use the original indices from the match
        context.variables = match["variables"]
        context.match_number = match_number
        
        # For empty matches, position at starting row
        # For regular matches, position at final row
        if is_empty_match:
            context.current_idx = start_idx
        else:
            context.current_idx = end_idx
        
        # Start with the appropriate row values
        # For empty matches, use the starting row
        # For regular matches, use the first matched row
        if start_idx < len(rows):
            result = rows[start_idx].copy()
        else:
            result = {}  # Fallback empty dict if out of bounds
        
        # Add measures
        if is_empty_match:
            # For empty matches, follow empty match semantics:
            # - All column references return NULL
            # - CLASSIFIER returns NULL 
            # - Navigation operations return NULL
            # - COUNT(*) = 0
            # - Other aggregates return NULL
            for alias, expr in measures.items():
                if "COUNT(*)" in expr or "COUNT()" in expr:
                    result[alias] = 0  # COUNT(*) = 0 for empty matches
                else:
                    result[alias] = None  # All other measures are NULL
        else:
            # Regular match processing with FINAL semantics
            evaluator = MeasureEvaluator(context, final=True)
            for alias, expr in measures.items():
                try:
                    result[alias] = evaluator.evaluate(expr)
                except Exception as e:
                    print(f"Error evaluating measure {alias}: {e}")
                    result[alias] = None
        
        # Add match metadata
        result["MATCH_NUMBER"] = match_number
        result["IS_EMPTY_MATCH"] = is_empty_match
        
        return result


    def _process_all_rows_match(self,
                            match: Dict[str, Any],
                            rows: List[Dict[str, Any]],
                            measures: Dict[str, str],
                            match_number: int,
                            exclude_ranges: List = None,
                            show_empty: bool = True) -> List[Dict[str, Any]]:
        """
        Process a match in ALL ROWS PER MATCH mode.
        
        Args:
            match: Match information including start/end indices and variables
            rows: The full list of input rows
            measures: Measure expressions to evaluate
            match_number: The sequential match number
            exclude_ranges: List of (start, end) tuples for excluded segments
            show_empty: Whether to include empty matches in output (true for SHOW EMPTY MATCHES)
            
        Returns:
            List of result rows for this match
        """
        start_idx = match["start"]
        end_idx = match["end"]
        
        # Handle empty match specially
        is_empty_match = match.get("is_empty", False) or not match["variables"]
        
        # Check if we should skip this empty match
        if is_empty_match and not show_empty:
            return []  # Skip empty match if OMIT EMPTY MATCHES is specified
        
        # For empty matches, create a single row with NULL measures
        if is_empty_match:
            if start_idx < len(rows):
                result = [rows[start_idx].copy()]
                
                # Create empty match context
                context = RowContext()
                context.rows = rows
                context.variables = {}
                context.match_number = match_number
                context.current_idx = start_idx
                
                # Add measures according to empty match semantics
                for alias, expr in measures.items():
                    # COUNT(*) is 0, everything else is NULL
                    if "COUNT(*)" in expr or "COUNT()" in expr:
                        result[0][alias] = 0
                    else:
                        result[0][alias] = None
                
                # Add match metadata
                result[0]["MATCH_NUMBER"] = match_number
                result[0]["IS_EMPTY_MATCH"] = True
                
                return result
            return []  # No rows if start_idx is out of bounds
        
        # Regular non-empty match processing
        results = []
        
        # Create base context
        context = RowContext()
        context.rows = rows  # Use entire dataset
        context.variables = match["variables"]
        context.match_number = match_number
        
        # Process SUBSET info if available
        if hasattr(self, "subsets") and self.subsets:
            for subset_name, component_vars in self.subsets.items():
                context.subsets[subset_name] = component_vars
        
        # Track excluded indices based on pattern exclusion
        excluded_indices = set()
        if exclude_ranges:
            for start, end in exclude_ranges:
                excluded_indices.update(range(start_idx + start, start_idx + end + 1))
        
        # Pre-compute FINAL measure values
        final_measures = {}
        final_evaluator = MeasureEvaluator(context, final=True)
        for alias, expr in measures.items():
            if expr.upper().startswith("FINAL "):
                try:
                    final_measures[alias] = final_evaluator.evaluate(expr)
                except Exception as e:
                    print(f"Error evaluating FINAL measure {alias}: {e}")
                    final_measures[alias] = None
        
        # Process each row in the match
        for i in range(start_idx, end_idx + 1):
            # Skip excluded rows
            if i in excluded_indices:
                continue
            
            # Update context for current row
            rel_idx = i - start_idx  # Relative index within match
            context.current_idx = i  # Absolute index in dataset
            
            # Start with the current row's values
            if i < len(rows):
                result = rows[i].copy()
            else:
                continue  # Skip if row index is out of bounds
            
            # Add measures with appropriate semantics
            evaluator = MeasureEvaluator(context, final=False)  # RUNNING semantics by default
            for alias, expr in measures.items():
                try:
                    if alias in final_measures:
                        # Use pre-computed FINAL value
                        result[alias] = final_measures[alias]
                    else:
                        # Evaluate with RUNNING semantics
                        result[alias] = evaluator.evaluate(expr)
                except Exception as e:
                    print(f"Error evaluating measure {alias}: {e}")
                    result[alias] = None
            
            # Add pattern variable classification for current row
            for var, indices in context.variables.items():
                if i in indices:
                    result["__PATTERN_VAR"] = var
                    break
            
            # Add match metadata
            result["MATCH_NUMBER"] = match_number
            result["IS_EMPTY_MATCH"] = False
            
            results.append(result)
        
        return results

    
    def _process_empty_match(self,
                           start_idx: int,
                           rows: List[Dict[str, Any]],
                           measures: Dict[str, str],
                           match_number: int) -> Dict[str, Any]:
        """Process an empty match."""
        # Start with the starting row's values
        result = rows[start_idx].copy()
        
        # Create context for empty match
        context = RowContext()
        context.rows = []
        context.variables = {}
        context.match_number = match_number
        
        # Add measures as NULL values
        evaluator = MeasureEvaluator(context, final=True)
        for alias in measures:
            result[alias] = None
            
        # Add match metadata
        result["MATCH_NUMBER"] = match_number
        
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
