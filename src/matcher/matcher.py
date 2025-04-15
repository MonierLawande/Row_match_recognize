# src/matcher/matcher.py
from collections import defaultdict
import time
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
from dataclasses import dataclass
from src.matcher.dfa import DFA, FAIL_STATE
from src.matcher.row_context import RowContext
from src.matcher.measure_evaluator import MeasureEvaluator
from src.matcher.pattern_tokenizer import PatternTokenType
import re

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
        self.original_pattern = original_pattern

        # Add performance tracking
        self.timing = defaultdict(float)
        
        # Add optimization structures
        self.transition_index = self._build_transition_index()
        self.excluded_vars = self._analyze_exclusions()

    def _build_transition_index(self):
        """Build index of transitions for faster lookups."""
        index = defaultdict(list)
        for i, state in enumerate(self.dfa.states):
            for transition in state.transitions:
                index[i].append((transition.variable, transition.target, transition.condition))
        return index

    def _analyze_exclusions(self):
        """Pre-analyze pattern for excluded variables."""
        excluded_vars = set()
        if self.original_pattern and "{-" in self.original_pattern and "-}" in self.original_pattern:
            parts = self.original_pattern.split("{-")
            for part in parts[1:]:
                if "-}" in part:
                    excluded = part.split("-}")[0].strip()
                    for var_name in self.dfa.states[0].variables:
                        if var_name in excluded:
                            excluded_vars.add(var_name)
        return excluded_vars

    def find_matches(self, rows, config=None, measures=None):
        """Find all matches with optimized processing."""
        start_time = time.time()
        results = []
        match_number = 1
        start_idx = 0
        unmatched_indices = set(range(len(rows)))
        
        # Get configuration
        all_rows = config.rows_per_match != RowsPerMatch.ONE_ROW if config else False
        show_empty = config.show_empty if config else True
        include_unmatched = config.include_unmatched if config else False
        
        print(f"Find matches with all_rows={all_rows}, show_empty={show_empty}, include_unmatched={include_unmatched}")
        
        while start_idx < len(rows):
            # Find next match using optimized transitions
            match = self._find_single_match(rows, start_idx, RowContext(rows=rows))
            if not match:
                start_idx += 1
                continue
                
            # Process the match
            if all_rows:
                match_time_start = time.time()
                print(f"Processing match {match_number} with ALL ROWS PER MATCH")
                match_rows = self._process_all_rows_match(match, rows, measures, match_number)
                results.extend(match_rows)
                self.timing["process_match"] += time.time() - match_time_start
                
                # Update unmatched indices efficiently
                if match.get("variables"):
                    unmatched_indices -= set(sum(match["variables"].values(), []))
            else:
                match_row = self._process_one_row_match(match, rows, measures, match_number)
                if match_row:
                    results.append(match_row)
                    if match.get("variables"):
                        unmatched_indices -= set(sum(match["variables"].values(), []))
            
            # Update start index based on skip mode
            if match.get("is_empty", False):
                start_idx = match["start"] + 1
            else:
                if config and config.skip_mode:
                    start_idx = self._get_skip_position(config.skip_mode, config.skip_var, match)
                else:
                    start_idx = match["end"] + 1
                
            match_number += 1
        
        # Add unmatched rows if requested
        if include_unmatched:
            for idx in sorted(unmatched_indices):
                unmatched_row = self._handle_unmatched_row(rows[idx], measures or {})
                results.append(unmatched_row)
        
        self.timing["total"] = time.time() - start_time
        print(f"Find matches completed in {self.timing['total']:.6f} seconds")
        return results

    def _process_all_rows_match(self, match, rows, measures, match_number):
        """
        Process ALL rows in a match with proper handling for multiple rows and exclusions.
        
        This method handles:
        1. Pattern exclusions (rows matched to excluded variables)
        2. CLASSIFIER functions and their arguments
        3. Performance tracking and optimization
        4. Memory-efficient processing of large datasets
        
        Args:
            match: The match information dictionary
            rows: All input rows
            measures: Dictionary of measure expressions
            match_number: The sequential match number
            
        Returns:
            List of output rows for this match
        """
        process_start = time.time()
        classifier_start = time.time()
        results = []
        
        # Check if CLASSIFIER is already requested in measures
        has_classifier_measure = any(
            re.match(r'CLASSIFIER\(\s*([A-Za-z][A-Za-z0-9_]*)?\s*\)', expr, re.IGNORECASE)
            for expr in measures.values()
        )
        
        # Direct string-based exclusion extraction with improved error handling
        excluded_vars = set()
        if self.original_pattern:
            try:
                # Look for patterns within exclusion markers
                pattern = self.original_pattern
                exclusion_sections = []
                start = 0
                while True:
                    start_marker = pattern.find("{-", start)
                    if start_marker == -1:
                        break
                    end_marker = pattern.find("-}", start_marker)
                    if end_marker == -1:
                        print(f"Warning: Unbalanced exclusion markers in pattern: {pattern}")
                        break
                    excluded_content = pattern[start_marker + 2:end_marker].strip()
                    exclusion_sections.append(excluded_content)
                    print(f"Exclusion content: '{excluded_content}'")
                    start = end_marker + 2
                    
                # Look for variables in each exclusion section
                for excluded_content in exclusion_sections:
                    for var in match["variables"].keys():
                        # More precise regex pattern to match whole words and with quantifiers
                        if re.search(r'\b' + re.escape(var) + r'\b', excluded_content):
                            excluded_vars.add(var)
                        # Match with quantifiers
                        elif re.search(r'\b' + re.escape(var) + r'[+*?]', excluded_content) or \
                            re.search(r'\b' + re.escape(var) + r'\{[0-9,]*\}', excluded_content):
                            excluded_vars.add(var)
            except Exception as e:
                print(f"Error processing pattern exclusions: {e}")
        
        print(f"Variables in exclusion pattern: {excluded_vars}")
        
        # Separate included indices from excluded indices
        matched_indices = []
        excluded_indices = set()
        for var, indices in match["variables"].items():
            if var in excluded_vars:
                excluded_indices.update(indices)
            else:
                matched_indices.extend(indices)
        
        matched_indices = sorted(set(matched_indices))
        
        print(f"Processing match {match_number}, included indices: {matched_indices}")
        if excluded_indices:
            print(f"Excluded indices: {sorted(excluded_indices)}")
        
        # Create context once for all rows with optimized structures
        context = RowContext()
        context.rows = rows
        context.variables = match["variables"]
        context.match_number = match_number
        context.subsets = self.subsets.copy() if self.subsets else {}
        
        # Create a single evaluator for better caching
        measure_evaluator = MeasureEvaluator(context)
        
        # Track individual measure timing
        measure_timings = defaultdict(float)
        
        # Process each matched row (excluding excluded rows)
        for idx in matched_indices:
            if idx >= len(rows) or idx in excluded_indices:
                continue
                
            # Create result row from original data
            result = dict(rows[idx])
            context.current_idx = idx
            
            # Store the classifier value for debugging
            if not has_classifier_measure:
                try:
                    result["_CLASSIFIER"] = context.classifier()
                except Exception as e:
                    print(f"Warning: Could not determine classifier for row {idx}: {e}")
                    result["_CLASSIFIER"] = None
            
            # Calculate measures with performance tracking
            for alias, expr in measures.items():
                measure_start = time.time()
                try:
                    result[alias] = measure_evaluator.evaluate(expr, "RUNNING")
                    print(f"Evaluated measure {alias} for row {idx} with RUNNING semantics: {result[alias]}")
                except Exception as e:
                    print(f"Error evaluating measure {alias} for row {idx}: {e}")
                    result[alias] = None
                measure_timings[alias] += time.time() - measure_start
            
            # Add match metadata
            result["MATCH_NUMBER"] = match_number
            result["IS_EMPTY_MATCH"] = match.get("is_empty", False)
            
            results.append(result)
            print(f"Added row {idx} to results")
        
        # Add timing information
        self.timing["classifier_total"] = time.time() - classifier_start
        self.timing["process_match_rows"] = time.time() - process_start
        
        # Log performance stats for debugging
        if hasattr(measure_evaluator, 'stats') and measure_evaluator.stats["total_evaluations"] > 0:
            print("CLASSIFIER performance stats:")
            print(f"  Cache hits: {measure_evaluator.stats['cache_hits']}")
            print(f"  Cache misses: {measure_evaluator.stats['cache_misses']}")
            print(f"  Hit ratio: {measure_evaluator.stats['cache_hits']/measure_evaluator.stats['total_evaluations']:.2%}")
            print(f"  Total evaluations: {measure_evaluator.stats['total_evaluations']}")
        
        # Log individual measure timings
        if measure_timings:
            print("Measure evaluation timings:")
            for alias, duration in measure_timings.items():
                print(f"  {alias}: {duration:.6f} seconds")
        
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
        """Find a single match using optimized transitions."""
        match_start_time = time.time()
        state = self.start_state
        current_idx = start_idx
        var_assignments = {}
        
        print(f"Starting match at index {start_idx}, state: {state}")
        
        # Check start anchor constraints for the start state
        # This handles the ^ anchor properly
        if not self._check_start_anchor(state, start_idx):
            print(f"Start state anchor check failed at index {start_idx}")
            self.timing["find_match"] += time.time() - match_start_time
            return None
        
        # Check for empty match
        if self.dfa.states[state].is_accept:
            # For empty matches, also verify end anchor if present
            if not self._check_end_anchor(state, start_idx, len(rows)):
                print(f"End anchor check failed for empty match at index {start_idx}")
                self.timing["find_match"] += time.time() - match_start_time
                return None
                
            print(f"Found empty match at index {start_idx} - start state is accepting")
            self.timing["find_match"] += time.time() - match_start_time
            return {
                "start": start_idx,
                "end": start_idx - 1,
                "variables": {},
                "state": state,
                "is_empty": True
            }
        
        longest_match = None
        trans_index = self.transition_index[state]
        
        while current_idx < len(rows):
            row = rows[current_idx]
            context.current_idx = current_idx
            
            print(f"Testing row {current_idx}, data: {row}")
            
            # Use indexed transitions for faster lookups
            next_state = None
            matched_var = None
            
            for var, target, condition in trans_index:
                print(f"  Evaluating condition for var: {var}")
                try:
                    # First check if target state's START anchor constraints are satisfied
                    # We don't check end anchors here, only at match acceptance time
                    if not self._check_start_anchor(target, current_idx):
                        print(f"  Start anchor check failed for transition to state {target} with var {var}")
                        continue
                        
                    # Then evaluate the condition
                    result = condition(row, context)
                    print(f"    Condition {'passed' if result else 'failed'} for {var}")
                    if result:
                        next_state = target
                        matched_var = var
                        break
                except Exception as e:
                    print(f"  Error evaluating condition for {var}: {str(e)}")
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
            trans_index = self.transition_index[state]
            
            # Update longest match if accepting state
            if self.dfa.states[state].is_accept:
                # Check end anchor constraints ONLY when we reach an accepting state
                if not self._check_end_anchor(state, current_idx - 1, len(rows)):
                    print(f"End anchor check failed for accepting state {state} at row {current_idx-1}")
                    # Continue to next row, but don't update longest_match
                    continue
                    
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
        
        self.timing["find_match"] += time.time() - match_start_time
        return longest_match

    def _check_start_anchor(self, state: int, row_idx: int) -> bool:
        """Check only start anchor constraints for a state."""
        if state == FAIL_STATE or state >= len(self.dfa.states):
            return True
            
        state_info = self.dfa.states[state]
        
        if hasattr(state_info, 'is_anchor') and state_info.is_anchor:
            if state_info.anchor_type == PatternTokenType.ANCHOR_START:
                # ^ anchor must match at partition start
                if row_idx != 0:
                    print(f"Start anchor failed: row_idx={row_idx} is not at partition start")
                    return False
        
        return True

    def _check_end_anchor(self, state: int, row_idx: int, total_rows: int) -> bool:
        """Check only end anchor constraints for a state."""
        if state == FAIL_STATE or state >= len(self.dfa.states):
            return True
            
        state_info = self.dfa.states[state]
        
        if hasattr(state_info, 'is_anchor') and state_info.is_anchor:
            if state_info.anchor_type == PatternTokenType.ANCHOR_END:
                # $ anchor must match at partition end
                if row_idx != total_rows - 1:
                    print(f"End anchor failed: row_idx={row_idx} is not at partition end")
                    return False
        
        return True


    
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
        """
        Check if anchor conditions are satisfied for the given state and row.
        """
        # Skip check for invalid state
        if state == FAIL_STATE or state >= len(self.dfa.states):
            return True
            
        state_info = self.dfa.states[state]
        
        if hasattr(state_info, 'is_anchor') and state_info.is_anchor:
            if state_info.anchor_type == PatternTokenType.ANCHOR_START:
                # ^ anchor must match at partition start
                if row_idx != 0:
                    print(f"Start anchor failed: row_idx={row_idx} is not at partition start")
                    return False
            elif state_info.anchor_type == PatternTokenType.ANCHOR_END:
                # $ anchor must match at partition end
                # BUT ONLY if this is an accepting state
                if state_info.is_accept and row_idx != total_rows - 1:
                    print(f"End anchor failed: row_idx={row_idx} is not at partition end")
                    return False
                    
        return True






    
    def _get_state_description(self, state: int) -> str:
        """
        Get a descriptive string for a state, including its anchor information.
        
        Args:
            state: State ID
            
        Returns:
            String description of the state
        """
        if state == FAIL_STATE:
            return "FAIL_STATE"
            
        if state >= len(self.dfa.states):
            return f"Invalid state {state}"
            
        state_info = self.dfa.states[state]
        desc = f"State {state}"
        
        if state_info.is_accept:
            desc += " (accepting)"
            
        if hasattr(state_info, 'is_anchor') and state_info.is_anchor:
            if state_info.anchor_type == PatternTokenType.ANCHOR_START:
                desc += " (start anchor ^)"
            elif state_info.anchor_type == PatternTokenType.ANCHOR_END:
                desc += " (end anchor $)"
                
        if state_info.variables:
            desc += f" vars: {sorted(list(state_info.variables))}"
            
        return desc
