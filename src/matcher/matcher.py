# src/matcher/matcher.py

from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
from dataclasses import dataclass
from src.matcher.dfa import DFA, FAIL_STATE
from src.matcher.row_context import RowContext
from src.matcher.measure_evaluator import MeasureEvaluator

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
    rows_per_match: RowsPerMatch
    skip_mode: SkipMode
    skip_var: Optional[str] = None
    show_empty: bool = True
    include_unmatched: bool = False
    exclude_ranges: List[Any] = None  # For pattern exclusion

class EnhancedMatcher:
    def __init__(self, dfa: DFA):
        self.dfa = dfa
        self.start_state = dfa.start

    def find_matches(self, 
                    rows: List[Dict[str, Any]],
                    config: MatchConfig,
                    measures: Dict[str, str]) -> List[Dict[str, Any]]:
        """Find all pattern matches in the rows."""
        results = []
        matched_indices = set()
        i = 0
        match_number = 1
        
        while i < len(rows):
            context = RowContext()
            context.match_number = match_number
            
            match = self._find_single_match(rows, i, context)
            
            if match:
                start_idx, end_idx = match["start"], match["end"]
                
                # Process match based on ROWS PER MATCH configuration
                if config.rows_per_match == RowsPerMatch.ONE_ROW:
                    result = self._process_one_row_match(match, rows, measures, match_number)
                    results.append(result)
                else:
                    match_rows = self._process_all_rows_match(match, rows, measures, match_number, config.exclude_ranges)
                    results.extend(match_rows)
                
                # Mark matched rows
                matched_indices.update(range(start_idx, end_idx + 1))
                
                # Determine next starting position
                if not self._validate_skip_target(config.skip_var, match):
                    i += 1  # Invalid skip target - move to next row
                else:
                    i = self._get_skip_position(config.skip_mode, config.skip_var, match)
                    
                match_number += 1
            else:
                # Check for empty match if allowed by the pattern
                if self.dfa.states[self.start_state].is_accept:
                    # Empty match at this position
                    if config.show_empty:
                        if config.rows_per_match == RowsPerMatch.ONE_ROW:
                            result = self._process_empty_match(i, rows, measures, match_number)
                            results.append(result)
                        # No ALL ROWS PER MATCH for empty match (no rows)
                    
                    matched_indices.add(i)
                    match_number += 1
                
                i += 1
        
        # Handle unmatched rows if configured
        if config.include_unmatched:
            for i, row in enumerate(rows):
                if i not in matched_indices:
                    results.append(self._handle_unmatched_row(row, measures))
                    
        return results

    def _find_single_match(self, 
                          rows: List[Dict[str, Any]], 
                          start_idx: int,
                          context: RowContext) -> Optional[Dict[str, Any]]:
        """Find a single match starting at the given index."""
        state = self.start_state
        current_idx = start_idx
        var_assignments = {}
        
        while current_idx < len(rows):
            row = rows[current_idx]
            context.current_idx = current_idx - start_idx  # Relative to match start
            
            # Try transitions from current state
            next_state = None
            matched_var = None
            
            for transition in self.dfa.states[state].transitions:
                try:
                    if transition.condition(row, context):
                        next_state = transition.target
                        matched_var = transition.variable
                        break
                except Exception as e:
                    print(f"Error evaluating condition: {e}")
                    continue
            
            if next_state is None:
                break
                
            # Record variable assignment
            if matched_var:
                if matched_var not in var_assignments:
                    var_assignments[matched_var] = []
                var_assignments[matched_var].append(current_idx)
            
            state = next_state
            current_idx += 1
            
            # Check if we've reached an accepting state
            if self.dfa.states[state].is_accept:
                return {
                    "start": start_idx,
                    "end": current_idx - 1,
                    "variables": var_assignments,
                    "state": state
                }
        
        # No match found
        return None

    def _process_one_row_match(self,
                             match: Dict[str, Any],
                             rows: List[Dict[str, Any]],
                             measures: Dict[str, str],
                             match_number: int) -> Dict[str, Any]:
        """Process a match in ONE ROW PER MATCH mode."""
        start_idx = match["start"]
        end_idx = match["end"]
        
        context = RowContext()
        context.rows = rows[start_idx:end_idx+1]
        context.variables = match["variables"]
        context.match_number = match_number
        context.current_idx = len(context.rows) - 1  # Position at final row
        
        # Start with first row values
        result = rows[start_idx].copy()
        
        # Add measures using FINAL semantics
        evaluator = MeasureEvaluator(context, final=True)
        for alias, expr in measures.items():
            result[alias] = evaluator.evaluate(expr)
            
        # Add match metadata
        result["MATCH_NUMBER"] = match_number
        
        return result
    
    def _process_all_rows_match(self,
                              match: Dict[str, Any],
                              rows: List[Dict[str, Any]],
                              measures: Dict[str, str],
                              match_number: int,
                              exclude_ranges: List = None) -> List[Dict[str, Any]]:
        """Process a match in ALL ROWS PER MATCH mode."""
        start_idx = match["start"]
        end_idx = match["end"]
        results = []
        
        # Create base context
        context = RowContext()
        context.rows = rows[start_idx:end_idx+1]
        context.variables = match["variables"]
        context.match_number = match_number
        
        # Process each row in the match
        for i in range(start_idx, end_idx + 1):
            rel_idx = i - start_idx  # Relative position in match
            
            # Skip excluded rows
            if exclude_ranges and any(start <= rel_idx <= end 
                                    for start, end in exclude_ranges):
                continue
            
            # Update context for current row
            context.current_idx = rel_idx
            
            # Start with the current row's values
            result = rows[i].copy()
            
            # Add measures using RUNNING semantics
            evaluator = MeasureEvaluator(context, final=False)
            for alias, expr in measures.items():
                result[alias] = evaluator.evaluate(expr)
            
            # Add match metadata
            result["MATCH_NUMBER"] = match_number
            
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
