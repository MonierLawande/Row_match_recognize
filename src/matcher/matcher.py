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
from src.utils.logging_config import get_logger, PerformanceTimer
import re

# Module logger
logger = get_logger(__name__)

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
    rows_per_match: RowsPerMatch
    skip_mode: SkipMode
    skip_var: Optional[str] = None
    show_empty: bool = True
    include_unmatched: bool = False
    
    def get(self, key, default=None):
        """Dictionary-like get method for compatibility."""
        config_dict = {
            "all_rows": self.rows_per_match != RowsPerMatch.ONE_ROW,
            "show_empty": self.show_empty,
            "with_unmatched": self.include_unmatched,
            "skip_mode": self.skip_mode,
            "skip_var": self.skip_var
        }
        return config_dict.get(key, default)

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
                logger.warning(f"Unbalanced exclusion markers in pattern: {pattern}")
                break
            
            # Extract excluded content
            excluded_content = pattern[start_marker + 2:end_marker].strip()
            self.exclusion_ranges.append((start_marker, end_marker))
            logger.debug(f"Exclusion handler found content: '{excluded_content}'")
            
            # Extract excluded variables - handle base variables without quantifiers
            var_pattern = r'([A-Za-z_][A-Za-z0-9_]*)(?:[+*?]|\{[0-9,]*\})?'
            for match in re.finditer(var_pattern, excluded_content):
                var_name = match.group(1)
                self.excluded_vars.add(var_name)
                logger.debug(f"Exclusion handler added variable: '{var_name}'")
            
            start = end_marker + 2
    
    def is_excluded(self, var_name: str) -> bool:
        """
        Check if a variable is excluded.
        
        Args:
            var_name: The variable name to check
            
        Returns:
            True if the variable is excluded, False otherwise
        """
        # Strip any quantifiers from the variable name
        base_var = var_name
        if var_name.endswith('+') or var_name.endswith('*') or var_name.endswith('?'):
            base_var = var_name[:-1]
        elif '{' in var_name and var_name.endswith('}'):
            base_var = var_name[:var_name.find('{')]
            
        return base_var in self.excluded_vars
    
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
        for var in list(filtered_match["variables"].keys()):
            # Strip any quantifiers for comparison
            base_var = var
            if var.endswith('+') or var.endswith('*') or var.endswith('?'):
                base_var = var[:-1]
            elif '{' in var and var.endswith('}'):
                base_var = var[:var.find('{')]
                
            if base_var in self.excluded_vars:
                logger.debug(f"Filtering out excluded variable: {var}")
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
        """Initialize the enhanced matcher with support for new DFA features."""
        self.dfa = dfa
        self.start_state = dfa.start
        self.measures = measures or {}
        self.measure_semantics = measure_semantics or {}
        # Use exclusion ranges from DFA if available
        self.exclusion_ranges = exclusion_ranges or dfa.exclusion_ranges
        self.after_match_skip = after_match_skip
        self.subsets = subsets or {}
        self.original_pattern = original_pattern
        self._matches = []  # Store matches for post-processing

        # Add performance tracking
        self.timing = defaultdict(float)
        
        # Check if pattern contains empty alternation or reluctant quantifiers - important for CLASSIFIER() function behavior
        self.has_empty_alternation = False
        self.has_reluctant_star = False  # *? quantifier (prefers zero matches)
        self.has_reluctant_plus = False  # +? quantifier (prefers minimal non-empty matches)
        if original_pattern:
            import re
            # Check for empty alternation patterns like "() |" or "| ()"
            if '()' in original_pattern and '|' in original_pattern:
                empty_alternation_patterns = [
                    r'\(\)\s*\|',  # () |
                    r'\|\s*\(\)',  # | ()
                ]
                for pattern in empty_alternation_patterns:
                    if re.search(pattern, original_pattern):
                        self.has_empty_alternation = True
                        logger.debug(f"Pattern contains empty alternation: {original_pattern}")
                        break
            
            # Check for reluctant star quantifier (*?) that prefers empty matches
            if re.search(r'\*\?', original_pattern):
                self.has_reluctant_star = True
                self.has_empty_alternation = True  # Treat *? like empty alternation for precedence
                logger.debug(f"Pattern contains reluctant star quantifier that prefers empty matches: {original_pattern}")
            
            # Check for reluctant plus quantifier (+?) that prefers minimal matches
            if re.search(r'\+\?', original_pattern):
                self.has_reluctant_plus = True
                logger.debug(f"Pattern contains reluctant plus quantifier that prefers minimal matches: {original_pattern}")
            
            # Other reluctant quantifiers (??) don't prefer empty matches over non-empty ones
            # They just prefer shorter matches among valid matches
        
        # Initialize anchor metadata before building transition index
        self._anchor_metadata = {
            "has_start_anchor": False,
            "has_end_anchor": False,
            "spans_partition": False,
            "start_anchor_states": set(),
            "end_anchor_accepting_states": set()
        }
        
        # Extract metadata from DFA for optimization
        self._extract_dfa_metadata()
        
        # Add optimization structures
        self.transition_index = self._build_transition_index()
        
        # Create pattern exclusion handler
        self.exclusion_handler = PatternExclusionHandler(original_pattern) if original_pattern else None
        
        # Extract excluded variables
        self.excluded_vars = set()
        if self.exclusion_handler:
            self.excluded_vars = self.exclusion_handler.excluded_vars
            logger.debug(f"Initialized matcher with excluded variables: {self.excluded_vars}")

    def _extract_dfa_metadata(self):
        """Extract and process metadata from the DFA for optimization."""
        # Copy metadata from DFA if available
        if hasattr(self.dfa, 'metadata'):
            self.metadata = self.dfa.metadata.copy()
            
            # Extract excluded variables from DFA states
            self.excluded_vars = set()
            for state in self.dfa.states:
                self.excluded_vars.update(state.excluded_variables)
                
            # Extract anchor information
            self._anchor_metadata = {
                "has_start_anchor": self.metadata.get("has_start_anchor", False),
                "has_end_anchor": self.metadata.get("has_end_anchor", False),
                "spans_partition": self.metadata.get("spans_partition", False)
            }
        else:
            # Fallback to legacy behavior
            self.metadata = {}
            # Use exclusion handler to get excluded variables
            if self.exclusion_handler:
                self.excluded_vars = self.exclusion_handler.excluded_vars
            else:
                self.excluded_vars = set()
            self._anchor_metadata = {
                "has_start_anchor": False,
                "has_end_anchor": False,
                "spans_partition": False
            }
    def _build_transition_index(self):
        """Build index of transitions with enhanced metadata support."""
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
        
        # Build normal transition index with priority support
        for i, state in enumerate(self.dfa.states):
            # Sort transitions by priority (lower is higher priority)
            sorted_transitions = sorted(state.transitions, key=lambda t: t.priority)
            for trans in sorted_transitions:
                index[i].append((trans.variable, trans.target, trans.condition))
        
        # Store anchor metadata for quick reference
        self._anchor_metadata.update({
            "start_anchor_states": anchor_start_states,
            "end_anchor_accepting_states": anchor_end_accepting_states,
        })
        
        return index        
    def _find_single_match(self, rows: List[Dict[str, Any]], start_idx: int, context: RowContext, config=None) -> Optional[Dict[str, Any]]:
        """Find a single match using optimized transitions with proper variable handling."""
        match_start_time = time.time()
        state = self.start_state
        current_idx = start_idx
        var_assignments = {}
        
        logger.debug(f"Starting match at index {start_idx}, state: {self._get_state_description(state)}")
        
        # Update context with subset variables from DFA metadata
        if hasattr(self.dfa, 'metadata') and 'subset_vars' in self.dfa.metadata:
            context.subsets.update(self.dfa.metadata['subset_vars'])

        # Optional early filtering based on anchor constraints
        if hasattr(self, '_anchor_metadata') and not self._can_satisfy_anchors(len(rows)):
            logger.debug(f"Partition cannot satisfy anchor constraints")
            self.timing["find_match"] += time.time() - match_start_time
            return None
        
        # Check start anchor constraints for the start state
        if not self._check_anchors(state, start_idx, len(rows), "start"):
            logger.debug(f"Start state anchor check failed at index {start_idx}")
            self.timing["find_match"] += time.time() - match_start_time
            return None
        
        # Check for empty match - but only use it if we can't find a non-empty match
        empty_match = None
        if self.dfa.states[state].is_accept:
            # For empty matches, also verify end anchor if present
            if self._check_anchors(state, start_idx, len(rows), "end"):
                logger.debug(f"Found potential empty match at index {start_idx} - start state is accepting")
                
                # Track which rows are part of empty pattern matches
                empty_pattern_rows = [start_idx]
                
                empty_match = {
                    "start": start_idx,
                    "end": start_idx - 1,
                    "variables": {},
                    "state": state,
                    "is_empty": True,
                    "excluded_vars": self.excluded_vars.copy() if hasattr(self, 'excluded_vars') else set(),
                    "excluded_rows": [],
                    "empty_pattern_rows": empty_pattern_rows  # Add tracking for empty pattern rows
                }
                # Don't return immediately - try to find a non-empty match first
        
        longest_match = None
        trans_index = self.transition_index[state]
        
        # Check if we have both start and end anchors in the pattern
        has_both_anchors = hasattr(self, '_anchor_metadata') and self._anchor_metadata.get("spans_partition", False)
        # Check if we have only end anchor in the pattern
        has_end_anchor = hasattr(self, '_anchor_metadata') and self._anchor_metadata.get("has_end_anchor", False)
        
        # Debug anchor detection
        logger.debug(f"Anchor metadata: has_end_anchor={has_end_anchor}, has_both_anchors={has_both_anchors}")
        if hasattr(self, '_anchor_metadata'):
            logger.debug(f"Full anchor metadata: {self._anchor_metadata}")
        else:
            logger.debug("No _anchor_metadata found")
        
        # Track excluded rows for proper exclusion handling
        excluded_rows = []
        
        # Track the last non-excluded state for resuming after exclusion
        last_non_excluded_state = state
        
        # Track if we're in a pattern with exclusions
        has_exclusions = hasattr(self, 'excluded_vars') and self.excluded_vars
        
        while current_idx < len(rows):
            row = rows[current_idx]
            context.current_idx = current_idx
            
            # Update context with current variable assignments for condition evaluation
            context.variables = var_assignments
            context.current_var_assignments = var_assignments
            
            logger.debug(f"Testing row {current_idx}, data: {row}")
            
            # Use indexed transitions for faster lookups
            next_state = None
            matched_var = None
            is_excluded_match = False
            
            # Try all transitions and use the first one that matches the condition
            for var, target, condition in trans_index:
                logger.debug(f"  Evaluating condition for var: {var}")
                try:
                    # Check if this is an excluded variable
                    is_excluded = var in self.excluded_vars
                    
                    # Set the current variable being evaluated for self-references
                    context.current_var = var
                    logger.debug(f"  [DEBUG] Set context.current_var = {var}")
                    
                    # First check if target state's START anchor constraints are satisfied
                    if not self._check_anchors(target, current_idx, len(rows), "start"):
                        logger.debug(f"  Start anchor check failed for transition to state {target} with var {var}")
                        continue
                        
                    # Then evaluate the condition with the current row and context
                    logger.debug(f"    DEBUG: Calling condition function with row={row}")
                    
                    # Clear any previous navigation context error flag
                    if hasattr(context, '_navigation_context_error'):
                        delattr(context, '_navigation_context_error')
                    
                    result = condition(row, context)
                    
                    # Check if condition failed due to navigation context unavailability
                    if not result and hasattr(context, '_navigation_context_error'):
                        logger.debug(f"    Condition failed for {var} due to navigation context unavailable (likely PREV() on row 0)")
                        # Skip this row for this pattern - pattern matching may need to start later
                        continue
                    
                    logger.debug(f"    Condition {'passed' if result else 'failed'} for {var}")
                    logger.debug(f"    DEBUG: condition result={result}, type={type(result)}")
                    
                    if result:
                        # If this is an excluded variable, mark for exclusion but continue matching
                        if is_excluded:
                            logger.debug(f"    Variable {var} is excluded - marking row for exclusion")
                            excluded_rows.append(current_idx)
                            is_excluded_match = True
                        
                        next_state = target
                        matched_var = var
                        break
                except Exception as e:
                    logger.error(f"  Error evaluating condition for {var}: {str(e)}")
                    logger.debug("Exception details:", exc_info=True)
                    continue
                finally:
                    # Clear the current variable after evaluation
                    logger.debug(f"  [DEBUG] Clearing context.current_var (was {getattr(context, 'current_var', 'None')})")
                    context.current_var = None
            
            # Handle exclusion matches properly - they should still advance the state
            if is_excluded_match:
                logger.debug(f"  Found excluded variable {matched_var} - will exclude row {current_idx} from output")
                # For excluded variables, we still update the state but don't assign the variable
                # This allows the pattern matching to continue correctly through exclusion sections
                state = next_state
                current_idx += 1
                trans_index = self.transition_index[state]
                
                # Check if we've reached an accepting state after the exclusion
                if self.dfa.states[state].is_accept:
                    logger.debug(f"Reached accepting state {state} after exclusion at row {current_idx-1}")
                    # Don't create a match here - continue to see if we can match more
                
                continue
            
            # For star patterns, we need to handle the case where no transition matches
            # but we're in an accepting state
            if next_state is None and self.dfa.states[state].is_accept:
                logger.debug(f"No valid transition from accepting state {state} at row {current_idx}")
                
                # Update longest match to include all rows up to this point
                if current_idx > start_idx:  # Only if we've matched at least one row
                    # For patterns with both start and end anchors, we need to check if we've reached the end
                    if has_both_anchors and current_idx < len(rows):
                        logger.debug(f"Pattern has both anchors but we're not at the end of partition")
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
                                "is_empty": False,
                                "excluded_vars": self.excluded_vars.copy() if hasattr(self, 'excluded_vars') else set(),
                                "excluded_rows": excluded_rows.copy()
                            }
                        else:
                            logger.debug(f"End anchor requires match to end at last row, but we're at row {current_idx-1}")
                    else:
                        # No end anchor, accept the match
                        longest_match = {
                            "start": start_idx,
                            "end": current_idx - 1,
                            "variables": {k: v[:] for k, v in var_assignments.items()},
                            "state": state,
                            "is_empty": False,
                            "excluded_vars": self.excluded_vars.copy() if hasattr(self, 'excluded_vars') else set(),
                            "excluded_rows": excluded_rows.copy()
                        }
                    break
                
            if next_state is None:
                logger.debug(f"No valid transition from state {state} at row {current_idx}")
                break
            
            # Record variable assignment (only for non-excluded variables)
            if matched_var and not is_excluded_match:
                if matched_var not in var_assignments:
                    var_assignments[matched_var] = []
                var_assignments[matched_var].append(current_idx)
                logger.debug(f"  Assigned row {current_idx} to variable {matched_var}")
            
            # Update state and move to next row
            state = next_state
            current_idx += 1
            trans_index = self.transition_index[state]
            
            # Update longest match if accepting state
            if self.dfa.states[state].is_accept:
                # Check end anchor constraints ONLY when we reach an accepting state
                if not self._check_anchors(state, current_idx - 1, len(rows), "end"):
                    logger.debug(f"End anchor check failed for accepting state {state} at row {current_idx-1}")
                    # Continue to next row, but don't update longest_match
                    continue
                    
                logger.debug(f"Reached accepting state {state} at row {current_idx-1}")
                
                # For patterns with both start and end anchors, we need to check if we've consumed the entire partition
                if has_both_anchors and current_idx < len(rows):
                    # If we have both anchors (^...$) and haven't reached the end of the partition,
                    # we need to continue matching to try to consume the entire partition
                    logger.debug(f"Pattern has both anchors but we're not at the end of partition yet")
                    continue
                
                # For patterns with only end anchor, we need to check if we're at the last row
                if has_end_anchor and not has_both_anchors:
                    # Only accept if we're at the last row
                    if current_idx - 1 != len(rows) - 1:
                        logger.debug(f"End anchor requires match to end at last row, but we're at row {current_idx-1}")
                        continue
                
                # For reluctant plus quantifiers, stop at the first valid match (early termination)
                if self.has_reluctant_plus:
                    logger.debug(f"Reluctant plus pattern detected - using early termination at first valid match")
                    longest_match = {
                        "start": start_idx,
                        "end": current_idx - 1,
                        "variables": {k: v[:] for k, v in var_assignments.items()},
                        "state": state,
                        "is_empty": False,
                        "excluded_vars": self.excluded_vars.copy() if hasattr(self, 'excluded_vars') else set(),
                        "excluded_rows": excluded_rows.copy()
                    }
                    logger.debug(f"  Reluctant plus match (early termination): {start_idx}-{current_idx-1}, vars: {list(var_assignments.keys())}")
                    break  # Early termination for reluctant plus
                
                # For greedy quantifiers, we should continue trying to match as long as possible
                # Only update longest_match but don't break - continue to find longer matches
                longest_match = {
                    "start": start_idx,
                    "end": current_idx - 1,
                    "variables": {k: v[:] for k, v in var_assignments.items()},
                    "state": state,
                    "is_empty": False,
                    "excluded_vars": self.excluded_vars.copy() if hasattr(self, 'excluded_vars') else set(),
                    "excluded_rows": excluded_rows.copy()
                }
                logger.debug(f"  Updated longest match: {start_idx}-{current_idx-1}, vars: {list(var_assignments.keys())}")
                
                # If we have both anchors and have reached the end of the partition, we can stop
                if has_both_anchors and current_idx == len(rows):
                    logger.debug(f"Found complete match spanning entire partition")
                    break
                
                # For greedy matching, continue to try to find longer matches
                # Don't break here - let the main loop continue until no more transitions are possible
        
        # For patterns with both anchors, verify we've consumed the entire partition
        if longest_match and has_both_anchors:
            if start_idx != 0 or longest_match["end"] != len(rows) - 1:
                logger.debug(f"Match doesn't span entire partition for ^...$ pattern, rejecting")
                longest_match = None
        
        # For patterns with only end anchor, verify the match ends at the last row
        if longest_match and has_end_anchor and not has_both_anchors:
            if longest_match["end"] != len(rows) - 1:
                logger.debug(f"Match doesn't end at last row for $ pattern, rejecting")
                longest_match = None
        
        # Special handling for patterns with exclusions
        # If we have a match and it contains excluded rows, make sure they're properly tracked
        if longest_match and excluded_rows:
            longest_match["excluded_rows"] = sorted(set(excluded_rows))
            logger.debug(f"Match contains excluded rows: {longest_match['excluded_rows']}")
        
        # Handle SQL:2016 alternation precedence for empty patterns
        # For patterns with empty alternation like () | A, prefer empty pattern
        prefer_empty = False
        if empty_match and self.has_empty_alternation:
            # For empty alternation patterns, always prefer empty match regardless of non-empty matches
            prefer_empty = True
            logger.debug(f"Empty alternation pattern detected - preferring empty match over any non-empty match")
        
        if prefer_empty:
            logger.debug(f"Applying SQL:2016 empty pattern precedence")
            logger.debug(f"Empty match: {empty_match}")
            if longest_match:
                logger.debug(f"Non-empty match (rejected): {longest_match}")
            self.timing["find_match"] += time.time() - match_start_time
            return empty_match
        
        # Standard precedence: prefer non-empty matches
        if longest_match and longest_match["end"] >= longest_match["start"]:  # Ensure it's a valid match
            logger.debug(f"Found non-empty match: {longest_match}")
            self.timing["find_match"] += time.time() - match_start_time
            return longest_match
        elif empty_match:
            # For SKIP TO NEXT ROW, TO_FIRST, TO_LAST modes, don't return empty matches when there's no valid non-empty match
            # This prevents the generation of spurious empty matches at every position
            if config and config.skip_mode in (SkipMode.TO_NEXT_ROW, SkipMode.TO_FIRST, SkipMode.TO_LAST):
                logger.debug(f"{config.skip_mode} mode: not returning empty match, will advance to next position")
                self.timing["find_match"] += time.time() - match_start_time
                return None
            else:
                logger.debug(f"Using empty match as fallback: {empty_match}")
                self.timing["find_match"] += time.time() - match_start_time
                return empty_match
        else:
            logger.debug(f"No match found starting at index {start_idx}")
            self.timing["find_match"] += time.time() - match_start_time
            return None



    def find_matches(self, rows, config=None, measures=None):
        """Find all matches with optimized processing."""
        logger.info(f"Starting find_matches with {len(rows)} rows")
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

        logger.info(f"Find matches with all_rows={all_rows}, show_empty={show_empty}, include_unmatched={include_unmatched}")

        # Safety counter to prevent infinite loops
        max_iterations = len(rows) * 3 if (config and config.skip_mode == SkipMode.TO_NEXT_ROW) else len(rows) * 2
        iteration_count = 0
        recent_starts = []  # Track recent start positions for TO_NEXT_ROW safety

        while start_idx < len(rows) and iteration_count < max_iterations:
            iteration_count += 1
            logger.debug(f"Iteration {iteration_count}, start_idx={start_idx}")

            # Additional safety for TO_NEXT_ROW to prevent infinite loops
            if config and config.skip_mode == SkipMode.TO_NEXT_ROW:
                recent_starts.append(start_idx)
                # If we've seen this start position too many times recently, break
                if recent_starts.count(start_idx) > 3:
                    logger.warning(f"Breaking TO_NEXT_ROW infinite loop at position {start_idx}")
                    break
                # Keep recent_starts manageable
                if len(recent_starts) > 20:
                    recent_starts = recent_starts[-10:]

            # Skip already processed indices (except for TO_NEXT_ROW, TO_FIRST, TO_LAST which allow overlaps)
            allow_overlap = config and config.skip_mode in (SkipMode.TO_NEXT_ROW, SkipMode.TO_FIRST, SkipMode.TO_LAST)
            if start_idx in processed_indices and not allow_overlap:
                logger.debug(f"Skipping already processed index {start_idx}")
                start_idx += 1
                continue

            # Find next match using optimized transitions
            match = self._find_single_match(rows, start_idx, RowContext(rows=rows), config)
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
                logger.info(f"Processing match {match_number} with ALL ROWS PER MATCH")
                match_rows = self._process_all_rows_match(match, rows, measures, match_number, config)
                results.extend(match_rows)
                self.timing["process_match"] += time.time() - match_time_start

                # Update unmatched indices efficiently
                if match.get("variables"):
                    matched_indices = set()
                    for var, indices in match["variables"].items():
                        matched_indices.update(indices)
                    unmatched_indices -= matched_indices
                    processed_indices.update(matched_indices)
                    
                    # Also mark excluded rows as processed
                    if match.get("excluded_rows"):
                        processed_indices.update(match["excluded_rows"])
            else:
                logger.info("\nProcessing match with ONE ROW PER MATCH:")
                logger.info(f"Match: {match}")
                match_row = self._process_one_row_match(match, rows, measures, match_number)
                if match_row:
                    results.append(match_row)
                    if match.get("variables"):
                        matched_indices = set()
                        for var, indices in match["variables"].items():
                            matched_indices.update(indices)
                        unmatched_indices -= matched_indices
                        processed_indices.update(matched_indices)
                        
                        # Also mark excluded rows as processed
                        if match.get("excluded_rows"):
                            processed_indices.update(match["excluded_rows"])

            # Update start index based on skip mode
            old_start_idx = start_idx
            if match.get("is_empty", False):
                # For empty matches, always move to the next position
                processed_indices.add(start_idx)
                start_idx += 1
                logger.debug(f"Empty match, advancing from {old_start_idx} to {start_idx}")
            else:
                # For non-empty matches, use the skip mode
                if config and config.skip_mode:
                    start_idx = self._get_skip_position(config.skip_mode, config.skip_var, match)
                else:
                    start_idx = match["end"] + 1

                logger.debug(f"Non-empty match, advancing from {old_start_idx} to {start_idx}")
                # Mark all indices in the match as processed (except for TO_NEXT_ROW which allows overlaps)
                if not (config and config.skip_mode == SkipMode.TO_NEXT_ROW):
                    for idx in range(old_start_idx, match["end"] + 1):
                        processed_indices.add(idx)
                    
                # Also mark excluded rows as processed
                if match.get("excluded_rows"):
                    processed_indices.update(match["excluded_rows"])
                    logger.debug(f"Marked excluded rows as processed: {match['excluded_rows']}")
                
                # SKIP PAST LAST ROW should continue searching for non-overlapping matches
                # The skip position is already set correctly above to start after the last row of the match
                if config and config.skip_mode == SkipMode.PAST_LAST_ROW:
                    logger.debug(f"SKIP PAST LAST ROW: continuing search from position {start_idx}")

            match_number += 1
            logger.debug(f"End of iteration {iteration_count}, match_number={match_number}")

        # Check if we hit the iteration limit
        if iteration_count >= max_iterations:
            logger.warning(f"Reached maximum iteration count ({max_iterations}). Possible infinite loop detected.")

        # Add unmatched rows if requested
        if include_unmatched or (config and config.rows_per_match == RowsPerMatch.ALL_ROWS_WITH_UNMATCHED):
            logger.debug(f"Processing unmatched rows: unmatched_indices={unmatched_indices}, processed_indices={processed_indices}")
            for idx in sorted(unmatched_indices):
                if idx not in processed_indices:  # Avoid duplicates
                    logger.debug(f"Adding unmatched row at index {idx}")
                    unmatched_row = self._handle_unmatched_row(rows[idx], measures or {})
                    results.append(unmatched_row)
                    processed_indices.add(idx)
                else:
                    logger.debug(f"Skipping unmatched row at index {idx} - already processed")
        else:
            logger.debug(f"Not processing unmatched rows: include_unmatched={include_unmatched}, config.rows_per_match={config.rows_per_match if config else None}")

        self.timing["total"] = time.time() - start_time
        logger.info(f"Find matches completed in {self.timing['total']:.6f} seconds")
        return results




    def _get_skip_position(self, skip_mode: SkipMode, skip_var: Optional[str], match: Dict[str, Any]) -> int:
        """
        Determine the next position to start matching based on skip mode.
        
        Production-ready implementation with comprehensive validation and error handling
        according to SQL:2016 specification for AFTER MATCH SKIP clause.
        """
        start_idx = match["start"]
        end_idx = match["end"]
        
        logger.debug(f"Calculating skip position: mode={skip_mode}, skip_var={skip_var}, match_range=[{start_idx}:{end_idx}]")
        
        # Empty match handling - always move to next row
        if match.get("is_empty", False):
            logger.debug(f"Empty match: skipping to position {start_idx + 1}")
            return start_idx + 1
            
        if skip_mode == SkipMode.PAST_LAST_ROW:
            # Default behavior: skip past the last row of the match
            next_pos = end_idx + 1
            logger.debug(f"PAST_LAST_ROW: skipping to position {next_pos}")
            return next_pos
            
        elif skip_mode == SkipMode.TO_NEXT_ROW:
            # Skip to the row after the first row of the match
            next_pos = start_idx + 1
            logger.debug(f"TO_NEXT_ROW: skipping to position {next_pos}")
            return next_pos
            
        elif skip_mode == SkipMode.TO_FIRST and skip_var:
            return self._get_variable_skip_position(skip_var, match, is_first=True)
            
        elif skip_mode == SkipMode.TO_LAST and skip_var:
            return self._get_variable_skip_position(skip_var, match, is_first=False)
            
        else:
            # Fallback: move to next position to avoid infinite loops
            logger.warning(f"Invalid skip configuration: mode={skip_mode}, skip_var={skip_var}. Using default.")
            return start_idx + 1

    def _get_variable_skip_position(self, skip_var: str, match: Dict[str, Any], is_first: bool) -> int:
        """
        Calculate skip position based on pattern variable position.
        
        Implements production-ready validation for TO FIRST/LAST variable skipping.
        """
        start_idx = match["start"]
        
        # Validate that the skip variable exists in the match
        if skip_var not in match["variables"]:
            logger.error(f"Skip variable '{skip_var}' not found in match variables: {list(match['variables'].keys())}")
            # Standard behavior: if variable is not present, treat as failure and skip to next row
            return start_idx + 1
            
        var_indices = match["variables"][skip_var]
        if not var_indices:
            logger.error(f"Skip variable '{skip_var}' has no matched indices")
            return start_idx + 1
            
        # Calculate target position based on FIRST or LAST
        if is_first:
            target_idx = min(var_indices)
            skip_type = "TO_FIRST"
        else:
            target_idx = max(var_indices) 
            skip_type = "TO_LAST"
            
        # Critical validation: prevent infinite loops
        # Cannot skip to the first row of the current match
        if target_idx == start_idx:
            logger.error(f"AFTER MATCH SKIP {skip_type} {skip_var} would create infinite loop: "
                        f"target position {target_idx} equals match start {start_idx}")
            # Standard mandates this should fail - skip to next row to avoid infinite loop
            return start_idx + 1
            
        # For TO FIRST/TO LAST: resume AT the variable position (SQL:2016 standard)
        # For TO FIRST: skip to the first occurrence of the variable
        # For TO LAST: skip to the last occurrence of the variable
        next_pos = target_idx
        logger.debug(f"{skip_type} {skip_var}: target_idx={target_idx}, skipping to position {next_pos}")
        
        return next_pos

    def validate_after_match_skip(self, skip_mode: SkipMode, skip_var: Optional[str], pattern_variables: Set[str]) -> bool:
        """
        Validate AFTER MATCH SKIP configuration according to SQL:2016 standard.
        
        Production-ready validation that prevents common errors and infinite loops.
        
        Args:
            skip_mode: The skip mode being used
            skip_var: The target variable for TO FIRST/LAST modes  
            pattern_variables: Set of all variables defined in the pattern
            
        Returns:
            True if configuration is valid, False otherwise
            
        Raises:
            ValueError: For invalid configurations that would cause infinite loops
        """
        logger.debug(f"Validating AFTER MATCH SKIP configuration: mode={skip_mode}, var={skip_var}")
        
        if skip_mode in (SkipMode.PAST_LAST_ROW, SkipMode.TO_NEXT_ROW):
            # These modes don't require variable validation
            return True
            
        elif skip_mode in (SkipMode.TO_FIRST, SkipMode.TO_LAST):
            if not skip_var:
                raise ValueError(f"AFTER MATCH SKIP {skip_mode.value} requires a target variable")
                
            # Validate that the target variable exists in the pattern
            if skip_var not in pattern_variables:
                raise ValueError(f"AFTER MATCH SKIP target variable '{skip_var}' not found in pattern variables: {sorted(pattern_variables)}")
                
            # Additional validation for preventing infinite loops
            # This is checked at runtime, but we can warn about potential issues here
            logger.debug(f"AFTER MATCH SKIP {skip_mode.value} {skip_var} validated successfully")
            return True
            
        else:
            raise ValueError(f"Unknown AFTER MATCH SKIP mode: {skip_mode}")

    # ...existing code...
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
        
        # Set pattern_variables from the original_pattern string
        if isinstance(self.original_pattern, str) and 'PERMUTE' in self.original_pattern:
            permute_match = re.search(r'PERMUTE\s*\(\s*([^)]+)\s*\)', self.original_pattern, re.IGNORECASE)
            if permute_match:
                context.pattern_variables = [v.strip() for v in permute_match.group(1).split(',')]
        elif hasattr(self.original_pattern, 'metadata'):
            context.pattern_variables = self.original_pattern.metadata.get('base_variables', [])
        
        # Create evaluator with caching
        evaluator = MeasureEvaluator(context, final=True)
        
        # Process measures
        for alias, expr in measures.items():
            try:
                # Evaluate the expression with appropriate semantics
                semantics = self.measure_semantics.get(alias, "FINAL")
                result[alias] = evaluator.evaluate(expr, semantics)
                logger.debug(f"Setting {alias} to {result[alias]} from evaluator")
                
            except Exception as e:
                logger.error(f"Error evaluating measure {alias}: {e}")
                result[alias] = None
        
        # Ensure we always return a meaningful result for valid matches
        # Add match metadata that indicates a match was found
        result["MATCH_NUMBER"] = match_number
        
        # If no measures were specified, add a basic match indicator
        if not measures:
            # Add original data from one of the matched rows (typically the first row of the match)
            start_row = rows[match["start"]]
            for key, value in start_row.items():
                if key not in result:  # Don't overwrite existing values
                    result[key] = value
        
        # Print debug information
        logger.info("\nMatch information:")
        logger.info(f"Match number: {match_number}")
        logger.info(f"Match start: {match['start']}, end: {match['end']}")
        logger.info(f"Variables: {var_assignments}")
        logger.info("\nResult row:")
        for key, value in result.items():
            logger.info(f"{key}: {value}")
        
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
                logger.debug(f"Start anchor failed: row_idx={row_idx} is not at partition start")
                return False
                
        # Check end anchor if requested and only for accepting states
        if check_type in ("end", "both") and state_info.anchor_type == PatternTokenType.ANCHOR_END:
            if state_info.is_accept and row_idx != total_rows - 1:
                logger.debug(f"End anchor failed: row_idx={row_idx} is not at partition end")
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
    

    def _process_permute_match(self, match, original_variables):
        """Process a match from a PERMUTE pattern with lexicographical ordering."""
        # If this is a PERMUTE pattern, ensure lexicographical ordering
        if not hasattr(self.dfa, 'metadata') or not self.dfa.metadata.get('permute', False):
            return match
            
        # Get original variable order
        if not original_variables:
            if 'original_variables' in self.dfa.metadata:
                original_variables = self.dfa.metadata['original_variables']
            elif 'permute_variables' in self.dfa.metadata:
                original_variables = self.dfa.metadata['permute_variables']
                
        if not original_variables:
            return match
            
        # Create priority map based on original variable order
        var_priority = {var: idx for idx, var in enumerate(original_variables)}
        
        # Add priority information to the match
        match['variable_priority'] = var_priority
        
        # For nested PERMUTE, we need to determine the lexicographical ordering
        # based on the actual variable sequence in the match
        if self.dfa.metadata.get('nested_permute', False):
            # Get the actual sequence of variables in this match
            var_sequence = []
            for idx in range(match['start'], match['end'] + 1):
                for var, indices in match['variables'].items():
                    if idx in indices:
                        var_sequence.append(var)
                        break
            
            # Calculate lexicographical score (lower is better)
            lex_score = 0
            for i, var in enumerate(var_sequence):
                if var in var_priority:
                    lex_score += var_priority[var] * (10 ** (len(var_sequence) - i - 1))
            
            match['lex_score'] = lex_score
        
        return match



    def _process_all_rows_match(self, match, rows, measures, match_number, config=None):
        """
        Process ALL rows in a match with proper handling for multiple rows and exclusions.
        
        Args:
            match: The match to process
            rows: Input rows
            measures: Measure expressions
            match_number: Sequential match number
            config: Match configuration
            
        Returns:
            List of result rows
        """
        process_start = time.time()
        results = []
        
        # Extract excluded variables and rows
        excluded_vars = match.get("excluded_vars", set())
        excluded_rows = match.get("excluded_rows", [])
        
        logger.debug(f"Excluded variables: {excluded_vars}")
        logger.debug(f"Excluded rows: {excluded_rows}")
        
        # Handle empty matches
        if match.get("is_empty", False) or (match["start"] > match["end"]):
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
                    
                    # Track that this is an empty pattern match
                    if "empty_pattern_rows" not in match:
                        match["empty_pattern_rows"] = [match["start"]]
                    
                    results.append(empty_row)
                    logger.debug(f"Added empty match row for index {match['start']}")
            return results
        
        # Get all matched indices, excluding excluded rows
        matched_indices = []
        for var, indices in match["variables"].items():
            matched_indices.extend(indices)
        
        # Sort indices for consistent processing
        matched_indices = sorted(set(matched_indices))
        
        logger.info(f"Processing match {match_number}, included indices: {matched_indices}")
        if excluded_rows:
            logger.debug(f"Excluded rows: {sorted(excluded_rows)}")
        
        # Create context once for all rows with optimized structures
        context = RowContext()
        context.rows = rows
        context.variables = match["variables"]
        context.match_number = match_number
        context.subsets = self.subsets.copy() if self.subsets else {}
        context.excluded_rows = excluded_rows
        
        # Add empty pattern tracking for proper CLASSIFIER() handling
        if match.get("is_empty", False) and match.get("empty_pattern_rows"):
            context._empty_pattern_rows = set(match["empty_pattern_rows"])
        
        # Create a single evaluator for better caching
        measure_evaluator = MeasureEvaluator(context)
        
        # For Trino compatibility, we need to include all rows from start to end,
        # skipping only the excluded rows
        all_indices = list(range(match["start"], match["end"] + 1))
        
        # Pre-calculate running sums for efficiency
        running_sums = {}
        for alias, expr in measures.items():
            if expr.upper().startswith("SUM("):
                # Extract column name
                col_match = re.match(r'SUM\(([^)]+)\)', expr, re.IGNORECASE)
                if col_match:
                    col_name = col_match.group(1).strip()
                    
                    # Calculate running sum for each position
                    total = 0
                    running_sums[alias] = {}
                    
                    for idx in all_indices:
                        # INCLUDE excluded rows in running sum calculation per SQL:2016
                        # (They are excluded from output but INCLUDED in RUNNING aggregations)
                        if idx < len(rows):
                            row_val = rows[idx].get(col_name)
                            if row_val is not None:
                                try:
                                    total += float(row_val)
                                except (ValueError, TypeError):
                                    pass
                        running_sums[alias][idx] = total
        
        # Process each row in the match range
        for idx in all_indices:
            # Skip excluded rows
            if idx in excluded_rows:
                continue
                
            # Skip rows outside the valid range
            if idx < 0 or idx >= len(rows):
                continue
                
            # Create result row from original data
            result = dict(rows[idx])
            context.current_idx = idx
            
            # Calculate measures
            for alias, expr in measures.items():
                try:
                    semantics = self.measure_semantics.get(alias, "RUNNING")
                    
                    # Special handling for CLASSIFIER
                    if expr.upper() == "CLASSIFIER()":
                        # Check if this is an empty pattern match
                        if match.get("is_empty", False):
                            # Empty pattern should return NULL/None for CLASSIFIER()
                            result[alias] = None
                            logger.debug(f"Empty pattern match: CLASSIFIER() returning None for row {idx}")
                        # Check if this row is explicitly marked as part of an empty pattern
                        elif match.get("empty_pattern_rows") and idx in match.get("empty_pattern_rows", []):
                            # This row was matched by an empty pattern - return None
                            result[alias] = None
                            logger.debug(f"Row {idx} is in empty_pattern_rows, CLASSIFIER() returning None")
                        # Check if the pattern has an empty alternation
                        elif match.get("has_empty_alternation", False):
                            # For patterns with () | A alternation, treat as empty
                            result[alias] = None
                            logger.debug(f"Pattern has empty alternation, CLASSIFIER() returning None for row {idx}")
                        else:
                            # Determine pattern variable for this row
                            pattern_var = None
                            for var, indices in match["variables"].items():
                                if idx in indices:
                                    pattern_var = var
                                    break
                            result[alias] = pattern_var
                            logger.debug(f"Evaluated measure {alias} for row {idx} with {semantics} semantics: {pattern_var}")
                    
                    # Special handling for running sum
                    elif expr.upper().startswith("SUM(") and semantics == "RUNNING":
                        if alias in running_sums and idx in running_sums[alias]:
                            result[alias] = running_sums[alias][idx]
                            logger.debug(f"Evaluated measure {alias} for row {idx} with {semantics} semantics: {result[alias]}")
                        else:
                            # Fallback to standard evaluation
                            result[alias] = measure_evaluator.evaluate(expr, semantics)
                            logger.debug(f"Evaluated measure {alias} for row {idx} with {semantics} semantics: {result[alias]}")
                    
                    # Standard evaluation for other measures
                    else:
                        result[alias] = measure_evaluator.evaluate(expr, semantics)
                        logger.debug(f"Evaluated measure {alias} for row {idx} with {semantics} semantics: {result[alias]}")
                        
                except Exception as e:
                    logger.error(f"Error evaluating measure {alias} for row {idx}: {e}")
                    result[alias] = None
            
            # Add match metadata
            result["MATCH_NUMBER"] = match_number
            result["IS_EMPTY_MATCH"] = False
            
            results.append(result)
            logger.debug(f"Added row {idx} to results")
        
        return results


    
    
    def _select_preferred_match(self, matches, variables):
        """
        When multiple permutation matches are found, select the one with
        highest lexicographical preference according to Trino rules.
        """
        if not matches:
            return None
        
        # Create priority map based on original variable order
        var_priority = {var: idx for idx, var in enumerate(variables)}
        
        # Sort matches by permutation preference
        def match_priority(match):
            # For each position in the pattern, get the actual variable that matched
            # Lower score is higher priority (more preferred)
            score = []
            for i in range(len(variables)):
                for var, indices in match.get('variables', {}).items():
                    if i in indices:
                        score.append(var_priority.get(var, len(variables)))
                        break
            return score
        
        # Return the most preferred match
        return sorted(matches, key=match_priority)[0]