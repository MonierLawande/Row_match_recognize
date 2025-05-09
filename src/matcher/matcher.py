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
# Add to src/matcher/matcher.py

class PatternExclusionHandler:
    """
    Handler for pattern exclusions with proper semantics.
    """
    
    def __init__(self, original_pattern: str):
        self.original_pattern = original_pattern
        self.exclusion_ranges = []
        self.excluded_vars = set()
        self._parse_exclusions()
    
    def _parse_exclusions(self):
        """
        Parse exclusion patterns from the original pattern.
        """
        if not self.original_pattern:
            return
        
        # Find all exclusion sections
        pattern = self.original_pattern
        start = 0
        while True:
            start_marker = pattern.find("{-", start)
            if start_marker == -1:
                break
            end_marker = pattern.find("-}", start_marker)
            if end_marker == -1:
                print(f"Warning: Unbalanced exclusion markers in pattern: {pattern}")
                break
            
            # Extract excluded content
            excluded_content = pattern[start_marker + 2:end_marker].strip()
            self.exclusion_ranges.append((start_marker, end_marker))
            
            # Extract excluded variables
            var_pattern = r'([A-Za-z_][A-Za-z0-9_]*)(?:[+*?]|\{[0-9,]*\})?'
            excluded_vars = re.findall(var_pattern, excluded_content)
            self.excluded_vars.update(excluded_vars)
            
            start = end_marker + 2
    
    def is_excluded(self, var_name: str) -> bool:
        """
        Check if a variable is excluded.
        
        Args:
            var_name: The variable name to check
            
        Returns:
            True if the variable is excluded, False otherwise
        """
        return var_name in self.excluded_vars
    
    def filter_excluded_rows(self, match: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter out excluded rows from a match.
        
        Args:
            match: The match to filter
            
        Returns:
            Filtered match with excluded rows removed
        """
        if not self.excluded_vars or "variables" not in match:
            return match
        
        # Create a copy of the match
        filtered_match = match.copy()
        filtered_match["variables"] = match["variables"].copy()
        
        # Remove excluded variables
        for var in self.excluded_vars:
            if var in filtered_match["variables"]:
                del filtered_match["variables"][var]
        
        # Update matched indices
        matched_indices = []
        for var, indices in filtered_match["variables"].items():
            matched_indices.extend(indices)
        filtered_match["matched_indices"] = sorted(set(matched_indices))
        
        return filtered_match
    
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
        self._matches = []  # Store matches for post-processing

        # Add performance tracking
        self.timing = defaultdict(float)
        
        # Add optimization structures
        self.transition_index = self._build_transition_index()
        self.excluded_vars = self._analyze_exclusions()
        
        # Create pattern exclusion handler
        self.exclusion_handler = PatternExclusionHandler(original_pattern) if original_pattern else None


    def find_matches(self, rows, config=None, measures=None):
        """Find all matches with optimized processing."""
        start_time = time.time()
        results = []
        match_number = 1
        start_idx = 0
        processed_indices = set()  # Track processed indices to prevent infinite loops
        unmatched_indices = set(range(len(rows)))
        self._matches = []  # Reset matches

        # Get configuration
        all_rows = config.rows_per_match != RowsPerMatch.ONE_ROW if config else False
        show_empty = config.show_empty if config else True
        include_unmatched = config.include_unmatched if config else False

        print(f"Find matches with all_rows={all_rows}, show_empty={show_empty}, include_unmatched={include_unmatched}")

        # Safety counter to prevent infinite loops
        max_iterations = len(rows) * 2  # Allow at most 2 iterations per row
        iteration_count = 0

        while start_idx < len(rows) and iteration_count < max_iterations:
            iteration_count += 1

            # Skip already processed indices
            if start_idx in processed_indices:
                start_idx += 1
                continue

            # Find next match using optimized transitions
            match = self._find_single_match(rows, start_idx, RowContext(rows=rows))
            if not match:
                # Mark this index as processed and move on
                processed_indices.add(start_idx)
                start_idx += 1
                continue

            # Store the match for post-processing
            match["match_number"] = match_number
            self._matches.append(match)

            # Process the match
            if all_rows:
                match_time_start = time.time()
                print(f"Processing match {match_number} with ALL ROWS PER MATCH")
                match_rows = self._process_all_rows_match(match, rows, measures, match_number, config)
                results.extend(match_rows)
                self.timing["process_match"] += time.time() - match_time_start

                # Update unmatched indices efficiently
                if match.get("variables"):
                    matched_indices = set(sum(match["variables"].values(), []))
                    unmatched_indices -= matched_indices
                    processed_indices.update(matched_indices)
            else:
                print("\nProcessing match with ONE ROW PER MATCH:")
                print(f"Match: {match}")
                match_row = self._process_one_row_match(match, rows, measures, match_number)
                if match_row:
                    results.append(match_row)
                    if match.get("variables"):
                        matched_indices = set(sum(match["variables"].values(), []))
                        unmatched_indices -= matched_indices
                        processed_indices.update(matched_indices)

            # Update start index based on skip mode
            if match.get("is_empty", False):
                # For empty matches, always move to the next position
                processed_indices.add(start_idx)
                start_idx += 1
            else:
                # For non-empty matches, use the skip mode
                old_start_idx = start_idx
                if config and config.skip_mode:
                    start_idx = self._get_skip_position(config.skip_mode, config.skip_var, match)
                else:
                    start_idx = match["end"] + 1

                # Mark all indices in the match as processed
                for idx in range(old_start_idx, match["end"] + 1):
                    processed_indices.add(idx)

            match_number += 1

        # Check if we hit the iteration limit
        if iteration_count >= max_iterations:
            print(f"WARNING: Reached maximum iteration count ({max_iterations}). Possible infinite loop detected.")

        # Add unmatched rows if requested
        if include_unmatched or (config and config.rows_per_match == RowsPerMatch.ALL_ROWS_WITH_UNMATCHED):
            for idx in sorted(unmatched_indices):
                if idx not in processed_indices:  # Avoid duplicates
                    unmatched_row = self._handle_unmatched_row(rows[idx], measures or {})
                    results.append(unmatched_row)
                    processed_indices.add(idx)

        self.timing["total"] = time.time() - start_time
        print(f"Find matches completed in {self.timing['total']:.6f} seconds")
        return results



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
    def _get_skip_position(self, skip_mode: SkipMode, skip_var: Optional[str], match: Dict[str, Any]) -> int:
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
        # src/matcher/matcher.py

        # src/matcher/matcher.py

    def _process_empty_match(self, start_idx: int, rows: List[Dict[str, Any]], measures: Dict[str, str], match_number: int) -> Dict[str, Any]:
        """
        Process an empty match according to SQL standard, preserving original row data.
        
        Args:
            start_idx: Starting row index for the empty match
            rows: Input rows
            measures: Measure expressions
            match_number: Sequential match number
            
        Returns:
            Result row for the empty match with original row data preserved
        """
        # Check if index is valid
        if start_idx >= len(rows):
            return None
            
        # Start with a copy of the original row to preserve all columns
        result = rows[start_idx].copy()
        
        # Create context for empty match
        context = RowContext()
        context.rows = rows
        context.variables = {}
        context.match_number = match_number
        context.current_idx = start_idx
        
        # Set all measures to NULL values
        for alias, expr in measures.items():
            # Special handling for MATCH_NUMBER()
            if expr.upper() == "MATCH_NUMBER()":
                result[alias] = match_number
            else:
                # All other measures are NULL for empty matches
                result[alias] = None
        
        # Add match metadata
        result["MATCH_NUMBER"] = match_number
        result["IS_EMPTY_MATCH"] = True
        
        return result

    def _handle_unmatched_row(self, row: Dict[str, Any], measures: Dict[str, str]) -> Dict[str, Any]:
        """
        Create output row for unmatched input row according to SQL standard.
        
        Args:
            row: The unmatched input row
            measures: Measure expressions
            
        Returns:
            Result row for the unmatched row
        """
        # For ALL ROWS PER MATCH WITH UNMATCHED ROWS, include original columns
        result = row.copy()
        
        # Add NULL values for all measures
        for alias in measures:
            result[alias] = None
        
        # Add match metadata
        result["MATCH_NUMBER"] = None
        result["IS_EMPTY_MATCH"] = False
        
        return result

    def _process_one_row_match(self, match, rows, measures, match_number):
        """Process one row per match to exactly match Trino's output format."""
        if match["start"] >= len(rows):
            return None
        
        # Handle empty match case
        if match.get("is_empty", False):
            return self._process_empty_match(match["start"], rows, measures, match_number)
        
        # Filter out excluded rows if needed
        if self.exclusion_handler and self.exclusion_handler.excluded_vars:
            match = self.exclusion_handler.filter_excluded_rows(match)
        
        # Create a new empty result row
        result = {}

        # Add partition columns if available
        start_row = rows[match["start"]]
        for col in ['department', 'region']:  # Common partition columns
            if col in start_row:
                result[col] = start_row[col]
        
        # Get variable assignments for easy access
        var_assignments = match.get("variables", {})
        
        # Create context for measure evaluation
        context = RowContext()
        context.rows = rows
        context.variables = var_assignments
        context.match_number = match_number
        context.current_idx = match["end"]  # Use the last row for FINAL semantics
        context.subsets = self.subsets.copy() if self.subsets else {}
        
        # Create evaluator with caching
        evaluator = MeasureEvaluator(context, final=True)
        
        # Process measures
        for alias, expr in measures.items():
            try:
                # Evaluate the expression with appropriate semantics
                semantics = self.measure_semantics.get(alias, "FINAL")
                result[alias] = evaluator.evaluate(expr, semantics)
                print(f"Setting {alias} to {result[alias]} from evaluator")
                
            except Exception as e:
                print(f"Error evaluating measure {alias}: {e}")
                result[alias] = None
        
        # Print debug information
        print("\nMatch information:")
        print(f"Match number: {match_number}")
        print(f"Match start: {match['start']}, end: {match['end']}")
        print(f"Variables: {var_assignments}")
        print("\nResult row:")
        for key, value in result.items():
            print(f"{key}: {value}")
        
        return result

    

    def _get_state_description(self, state_idx):
        """Get a human-readable description of a state."""
        if state_idx == FAIL_STATE:
            return "FAIL_STATE"
        
        if state_idx >= len(self.dfa.states):
            return f"Invalid state {state_idx}"
        
        state = self.dfa.states[state_idx]
        accept_str = "Accept" if state.is_accept else "Non-accept"
        vars_str = ", ".join(sorted(state.variables)) if state.variables else "None"
        
        return f"State {state_idx} ({accept_str}, Vars: {vars_str})"
        # src/matcher/matcher.py

    def _check_anchors(self, state: int, row_idx: int, total_rows: int, check_type: str = "both") -> bool:
        """
        Unified method to check anchor constraints based on context.
        
        Args:
            state: State ID to check
            row_idx: Current row index
            total_rows: Total number of rows in the partition
            check_type: Type of check to perform ("start", "end", or "both")
            
        Returns:
            True if anchor constraints are satisfied, False otherwise
        """
        # Skip check for invalid state
        if state == FAIL_STATE or state >= len(self.dfa.states):
            return True
            
        state_info = self.dfa.states[state]
        
        if not hasattr(state_info, 'is_anchor') or not state_info.is_anchor:
            return True
            
        # Check start anchor if requested
        if check_type in ("start", "both") and state_info.anchor_type == PatternTokenType.ANCHOR_START:
            if row_idx != 0:
                print(f"Start anchor failed: row_idx={row_idx} is not at partition start")
                return False
                
        # Check end anchor if requested and only for accepting states
        if check_type in ("end", "both") and state_info.anchor_type == PatternTokenType.ANCHOR_END:
            if state_info.is_accept and row_idx != total_rows - 1:
                print(f"End anchor failed: row_idx={row_idx} is not at partition end")
                return False
                    
        return True

    def _can_satisfy_anchors(self, partition_size: int) -> bool:
        """
        Quick check if a partition of given size can potentially satisfy anchor constraints.
        
        Args:
            partition_size: Size of the partition
            
        Returns:
            False if we know anchors can't be satisfied, True otherwise
        """
        # If there are no rows, we can only match empty patterns
        if partition_size == 0:
            return self.dfa.states[self.start_state].is_accept
            
        # If no anchors in pattern, all partitions can potentially match
        if not hasattr(self, "_anchor_metadata"):
            return True
            
        # For patterns with both start and end anchors (^...$), check if partition is viable
        if self._anchor_metadata.get("spans_partition", False):
            # Additional validation could be added here based on pattern needs
            pass
            
        return True

    
    def _find_single_match(self, rows: List[Dict[str, Any]], start_idx: int, context: RowContext) -> Optional[Dict[str, Any]]:
        """Find a single match using optimized transitions with proper variable handling."""
        match_start_time = time.time()
        state = self.start_state
        current_idx = start_idx
        var_assignments = {}
        
        print(f"Starting match at index {start_idx}, state: {self._get_state_description(state)}")
        
        # Optional early filtering based on anchor constraints
        if hasattr(self, '_anchor_metadata') and not self._can_satisfy_anchors(len(rows)):
            print(f"Partition cannot satisfy anchor constraints")
            self.timing["find_match"] += time.time() - match_start_time
            return None
        
        # Check start anchor constraints for the start state
        if not self._check_anchors(state, start_idx, len(rows), "start"):
            print(f"Start state anchor check failed at index {start_idx}")
            self.timing["find_match"] += time.time() - match_start_time
            return None
        
        # Check for empty match - but only use it if we can't find a non-empty match
        empty_match = None
        if self.dfa.states[state].is_accept:
            # For empty matches, also verify end anchor if present
            if self._check_anchors(state, start_idx, len(rows), "end"):
                print(f"Found potential empty match at index {start_idx} - start state is accepting")
                empty_match = {
                    "start": start_idx,
                    "end": start_idx - 1,
                    "variables": {},
                    "state": state,
                    "is_empty": True
                }
                # Don't return immediately - try to find a non-empty match first
        
        longest_match = None
        trans_index = self.transition_index[state]
        
        # Check if we have both start and end anchors in the pattern
        has_both_anchors = hasattr(self, '_anchor_metadata') and self._anchor_metadata.get("spans_partition", False)
        # Check if we have only end anchor in the pattern
        has_end_anchor = hasattr(self, '_anchor_metadata') and self._anchor_metadata.get("has_end_anchor", False)
        
        # Add pattern_variables to context for PERMUTE pattern navigation
        if hasattr(self, 'original_pattern') and 'PERMUTE' in self.original_pattern:
            # Extract A, B, C from PERMUTE(A, B, C)
            pattern_str = self.original_pattern
            permute_match = re.search(r'PERMUTE\s*\(\s*([^)]+)\s*\)', pattern_str, re.IGNORECASE)
            if permute_match:
                variables = [v.strip() for v in permute_match.group(1).split(',')]
                context.pattern_variables = variables
                # Important: Store the ORIGINAL pattern order, not the permuted order
        
        while current_idx < len(rows):
            row = rows[current_idx]
            context.current_idx = current_idx
            
            # Update context with current variable assignments for condition evaluation
            context.variables = var_assignments
            # Add tracking for current variable assignments
            context.current_var_assignments = var_assignments
            
            print(f"Testing row {current_idx}, data: {row}")
            
            # Use indexed transitions for faster lookups
            next_state = None
            matched_var = None
            
            # Try all transitions and use the first one that matches the condition
            # This is critical for correct variable assignment based on DEFINE conditions
            for var, target, condition in trans_index:
                print(f"  Evaluating condition for var: {var}")
                try:
                    # Set the current variable being evaluated for self-references
                    context.current_var = var
                    
                    # First check if target state's START anchor constraints are satisfied
                    # We don't check end anchors here, only at match acceptance time
                    if not self._check_anchors(target, current_idx, len(rows), "start"):
                        print(f"  Start anchor check failed for transition to state {target} with var {var}")
                        continue
                        
                    # Then evaluate the condition with the current row and context
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
                finally:
                    # Clear the current variable after evaluation
                    if hasattr(context, 'current_var'):
                        delattr(context, 'current_var')
            
            # For star patterns, we need to handle the case where no transition matches
            # but we're in an accepting state
            if next_state is None and self.dfa.states[state].is_accept:
                print(f"No valid transition from accepting state {state} at row {current_idx}")
                # Update longest match to include all rows up to this point
                if current_idx > start_idx:  # Only if we've matched at least one row
                    # For patterns with both start and end anchors, we need to check if we've reached the end
                    if has_both_anchors and current_idx < len(rows):
                        print(f"Pattern has both anchors but we're not at the end of partition")
                        break  # Don't accept partial matches for ^...$ patterns
                    
                    # For patterns with only end anchor, we need to check if we're at the last row
                    if has_end_anchor and not has_both_anchors:
                        # Only accept if we're at the last row
                        if current_idx - 1 == len(rows) - 1:
                            longest_match = {
                                "start": start_idx,
                                "end": current_idx - 1,
                                "variables": {k: v[:] for k, v in var_assignments.items()},
                                "state": state,
                                "is_empty": False
                            }
                        else:
                            print(f"End anchor requires match to end at last row, but we're at row {current_idx-1}")
                    else:
                        # No end anchor, accept the match
                        longest_match = {
                            "start": start_idx,
                            "end": current_idx - 1,
                            "variables": {k: v[:] for k, v in var_assignments.items()},
                            "state": state,
                            "is_empty": False
                        }
                    break
                
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
                if not self._check_anchors(state, current_idx - 1, len(rows), "end"):
                    print(f"End anchor check failed for accepting state {state} at row {current_idx-1}")
                    # Continue to next row, but don't update longest_match
                    continue
                    
                print(f"Reached accepting state {state} at row {current_idx-1}")
                
                # For patterns with both start and end anchors, we need to check if we've consumed the entire partition
                if has_both_anchors and current_idx < len(rows):
                    # If we have both anchors (^...$) and haven't reached the end of the partition,
                    # we need to continue matching to try to consume the entire partition
                    print(f"Pattern has both anchors but we're not at the end of partition yet")
                    continue
                
                # For patterns with only end anchor, we need to check if we're at the last row
                if has_end_anchor and not has_both_anchors:
                    # Only accept if we're at the last row
                    if current_idx - 1 != len(rows) - 1:
                        print(f"End anchor requires match to end at last row, but we're at row {current_idx-1}")
                        continue
                
                longest_match = {
                    "start": start_idx,
                    "end": current_idx - 1,
                    "variables": {k: v[:] for k, v in var_assignments.items()},
                    "state": state,
                    "is_empty": False
                }
                print(f"  Current longest match: {start_idx}-{current_idx-1}, vars: {list(var_assignments.keys())}")
                
                # If we have both anchors and have reached the end of the partition, we can stop
                if has_both_anchors and current_idx == len(rows):
                    print(f"Found complete match spanning entire partition")
                    break
        
        # For patterns with both anchors, verify we've consumed the entire partition
        if longest_match and has_both_anchors:
            if start_idx != 0 or longest_match["end"] != len(rows) - 1:
                print(f"Match doesn't span entire partition for ^...$ pattern, rejecting")
                longest_match = None
        
        # For patterns with only end anchor, verify the match ends at the last row
        if longest_match and has_end_anchor and not has_both_anchors:
            if longest_match["end"] != len(rows) - 1:
                print(f"Match doesn't end at last row for $ pattern, rejecting")
                longest_match = None
        
        # Prefer non-empty match over empty match
        if longest_match and longest_match["end"] >= longest_match["start"]:  # Ensure it's a valid match
            print(f"Found non-empty match: {longest_match}")
            self.timing["find_match"] += time.time() - match_start_time
            return longest_match
        elif empty_match:
            print(f"Using empty match as fallback: {empty_match}")
            self.timing["find_match"] += time.time() - match_start_time
            return empty_match
        else:
            print(f"No match found starting at index {start_idx}")
            self.timing["find_match"] += time.time() - match_start_time
            return None

    def _process_all_rows_match(self, match, rows, measures, match_number, config=None):
        """
        Process ALL rows in a match with proper handling for multiple rows and exclusions.
        """
        process_start = time.time()
        results = []
        
        # Extract excluded variables
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
        
        # Handle empty matches
        if match.get("is_empty", False):
            if config and config.show_empty:
                # For empty matches, use the original row data at the start index
                if match["start"] < len(rows):
                    empty_row = rows[match["start"]].copy()
                    
                    # Set all measures to NULL
                    for alias in measures:
                        if alias.upper() == "MATCH_NUM" or measures[alias].upper() == "MATCH_NUMBER()":
                            empty_row[alias] = match_number
                        else:
                            empty_row[alias] = None
                    
                    # Add match metadata
                    empty_row["MATCH_NUMBER"] = match_number
                    empty_row["IS_EMPTY_MATCH"] = True
                    
                    results.append(empty_row)
                    print(f"Added empty match row for index {match['start']}")
        else:
            # Process each matched row (excluding excluded rows)
            for idx in matched_indices:
                if idx >= len(rows) or idx in excluded_indices:
                    continue
                    
                # Create result row from original data
                result = dict(rows[idx])
                context.current_idx = idx
                
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
                result["IS_EMPTY_MATCH"] = False
                
                results.append(result)
                print(f"Added row {idx} to results")
        
        # Log measure timings
        if measure_timings:
            print("Measure evaluation timings:")
            for alias, duration in measure_timings.items():
                print(f"  {alias}: {duration:.6f} seconds")
        
        return results



    def _build_transition_index(self):
        """Build index of transitions with enhanced anchor metadata."""
        index = defaultdict(list)
        
        # Add anchor information to the index for faster checking
        anchor_start_states = set()
        anchor_end_accepting_states = set()
        
        # Identify states with anchors
        for i, state in enumerate(self.dfa.states):
            if hasattr(state, 'is_anchor') and state.is_anchor:
                if state.anchor_type == PatternTokenType.ANCHOR_START:
                    anchor_start_states.add(i)
                elif state.anchor_type == PatternTokenType.ANCHOR_END and state.is_accept:
                    anchor_end_accepting_states.add(i)
        
        # Build normal transition index
        for i, state in enumerate(self.dfa.states):
            for transition in state.transitions:
                index[i].append((transition.variable, transition.target, transition.condition))
        
        # Store anchor metadata for quick reference
        self._anchor_metadata = {
            "has_start_anchor": bool(anchor_start_states),
            "has_end_anchor": bool(anchor_end_accepting_states),
            "start_anchor_states": anchor_start_states,
            "end_anchor_accepting_states": anchor_end_accepting_states,
            "spans_partition": bool(anchor_start_states and anchor_end_accepting_states)
        }
        
        return index
