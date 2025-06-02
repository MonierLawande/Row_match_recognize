# enhanced/automata.py - Part 1: Basic Classes

from typing import Callable, List, Optional, Dict, Any, Set, Tuple, Union
from dataclasses import dataclass, field
from src.matcher.pattern_tokenizer import PatternToken, PatternTokenType, parse_quantifier
from src.matcher.condition_evaluator import compile_condition
import itertools
import re
from typing import List, Dict, FrozenSet, Set, Any, Optional, Tuple, Union

# A condition function: given a row and current match context, return True if the row qualifies.
ConditionFn = Callable[[Dict[str, Any], Any], bool]

@dataclass
class Transition:
    """
    Enhanced transition with support for pattern variables and optimizations.
    
    Attributes:
        condition: Function that evaluates if a row matches this transition
        target: Target state index
        variable: Optional pattern variable associated with this transition
        priority: Priority for resolving ambiguous transitions (lower is higher priority)
        metadata: Additional metadata for specialized transitions
    """
    condition: ConditionFn
    target: int
    variable: Optional[str] = None
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

class NFAState:
    """
    Enhanced NFA state with comprehensive SQL:2016 pattern matching support.
    
    Attributes:
        transitions: List of outgoing transitions with conditions
        epsilon: List of epsilon transition target states
        variable: Pattern variable associated with this state
        is_excluded: Whether this state is part of an excluded pattern
        is_anchor: Whether this state represents an anchor (^ or $)
        anchor_type: Type of anchor (START or END)
        subset_vars: Set of subset variables defined for this state
        permute_data: Optional metadata for PERMUTE patterns
        is_empty_match: Whether this state allows empty matches
        can_accept: Whether this state can reach accept via epsilon transitions
        is_accept: Whether this is an accepting state
        subset_parent: Parent variable for subset variables
        priority: Priority for deterministic matching (lower is higher priority)
    """
    def __init__(self):
        self.transitions: List[Transition] = []
        self.epsilon: List[int] = []
        self.variable: Optional[str] = None
        self.is_excluded: bool = False
        self.is_anchor: bool = False
        self.anchor_type: Optional[PatternTokenType] = None
        self.subset_vars: Set[str] = set()
        self.permute_data: Dict[str, Any] = {}
        self.is_empty_match: bool = False
        self.can_accept: bool = False
        self.is_accept: bool = False
        self.subset_parent: Optional[str] = None
        self.priority: int = 0
    
    def add_transition(self, condition: ConditionFn, target: int, variable: Optional[str] = None, 
                      priority: int = 0, metadata: Dict[str, Any] = None):
        """
        Add a transition with enhanced metadata support.
        
        Args:
            condition: Function that evaluates if a row matches this transition
            target: Target state index
            variable: Optional pattern variable associated with this transition
            priority: Priority for resolving ambiguous transitions (lower is higher priority)
            metadata: Additional metadata for specialized transitions
        """
        self.transitions.append(Transition(
            condition, 
            target, 
            variable, 
            priority,
            metadata or {}
        ))
        
    def add_epsilon(self, target: int):
        """
        Add an epsilon transition to target state.
        
        Args:
            target: Target state index
        """
        if target not in self.epsilon:
            self.epsilon.append(target)
            
    def has_transition_to(self, target: int) -> bool:
        """
        Check if this state has a transition to the target state.
        
        Args:
            target: Target state index to check
            
        Returns:
            bool: True if there is a transition to target, False otherwise
        """
        # Check normal transitions
        for trans in self.transitions:
            if trans.target == target:
                return True
                
        # Check epsilon transitions
        return target in self.epsilon
        
    def allows_empty_match(self) -> bool:
        """
        Check if this state allows empty matches.
        
        Returns:
            bool: True if this state allows empty matches, False otherwise
        """
        return self.is_empty_match
        
    def is_variable_state(self) -> bool:
        """
        Check if this state represents a pattern variable.
        
        Returns:
            bool: True if this state has a variable name, False otherwise
        """
        return self.variable is not None
        
    def get_epsilon_targets(self) -> List[int]:
        """
        Get list of epsilon transition targets.
        
        Returns:
            List[int]: List of target state indices
        """
        return self.epsilon
        
    def get_transition_targets(self) -> List[int]:
        """
        Get list of all transition targets (non-epsilon).
        
        Returns:
            List[int]: List of target state indices
        """
        return [trans.target for trans in self.transitions]

# src/matcher/automata.py
# enhanced/automata.py - Part 2: NFA Class

class NFA:
    """
    Enhanced NFA implementation for pattern matching.
    
    Attributes:
        start: Start state index
        accept: Accept state index
        states: List of NFA states
        exclusion_ranges: Ranges of excluded pattern components
        metadata: Additional pattern metadata
    """
    def __init__(self, start: int, accept: int, states: List[NFAState], 
                exclusion_ranges: List[Tuple[int, int]] = None,
                metadata: Dict[str, Any] = None):
        self.start = start
        self.accept = accept
        self.states = states
        self.exclusion_ranges = exclusion_ranges or []
        self.metadata = metadata or {}
    
    def epsilon_closure(self, state_indices: List[int]) -> List[int]:
        """
        Compute epsilon closure for given states with robust cycle detection.
        
        This method computes the set of states reachable from the given states
        via epsilon transitions, including the original states themselves.
        It efficiently handles cycles in the epsilon transition graph.
        
        Args:
            state_indices: List of state indices to compute closure for
            
        Returns:
            List of state indices in the epsilon closure (sorted)
        """
        closure = set(state_indices)  # Result set
        stack = list(state_indices)   # DFS stack
        visited_pairs = set()         # Track (state, target) pairs to detect cycles
        
        while stack:
            s = stack.pop()
            
            # Get epsilon transitions for this state
            for t in self.states[s].epsilon:
                # Skip if we've already processed this epsilon transition
                if (s, t) in visited_pairs:
                    continue
                
                # Mark transition as visited
                visited_pairs.add((s, t))
                
                # Add target to closure if not already present
                if t not in closure:
                    closure.add(t)
                    stack.append(t)
                    
                    # SQL:2016 requires proper handling of epsilon loops
                    # Special handling for epsilon transitions from accept state
                    if t == self.accept and s != self.accept:
                        # If we reached accept via epsilon, mark source state
                        self.states[s].can_accept = True
        
        # Return sorted closure for deterministic behavior
        # This is important for predictable NFA-to-DFA conversion
        return sorted(closure)
        
    def validate(self) -> bool:
        """
        Validate NFA structure and constraints.
        
        Returns:
            bool: True if NFA is valid, False otherwise
        """
        # Check for unreachable states
        reachable = set()
        queue = [self.start]
        
        while queue:
            state_idx = queue.pop(0)
            if state_idx not in reachable:
                reachable.add(state_idx)
                # Add epsilon transitions
                for target in self.states[state_idx].epsilon:
                    queue.append(target)
                # Add normal transitions
                for trans in self.states[state_idx].transitions:
                    queue.append(trans.target)
        
        # Check if accept state is reachable
        if self.accept not in reachable:
            return False
            
        # Check for invalid transitions
        for i, state in enumerate(self.states):
            for trans in state.transitions:
                if trans.target < 0 or trans.target >= len(self.states):
                    return False
            for eps in state.epsilon:
                if eps < 0 or eps >= len(self.states):
                    return False
                    
        return True
        
    def optimize(self):
        """Apply optimizations to the NFA."""
        self._remove_unreachable_states()
        self._optimize_epsilon_transitions()
        
    # Fix for src/matcher/automata.py - _remove_unreachable_states method

    def _remove_unreachable_states(self):
        """Remove states that cannot be reached from start state."""
        reachable = set()
        queue = [self.start]
        
        while queue:
            state_idx = queue.pop(0)
            if state_idx not in reachable:
                reachable.add(state_idx)
                # Add epsilon transitions
                for target in self.states[state_idx].epsilon:
                    queue.append(target)
                # Add normal transitions
                current_state = self.states[state_idx]  # Get the current state object
                for trans in current_state.transitions:  # Use current_state instead of undefined state
                    queue.append(trans.target)
        
        # Keep only reachable states
        new_states = []
        state_map = {}
        for idx in sorted(reachable):
            state_map[idx] = len(new_states)
            new_states.append(self.states[idx])
            
        # Update transitions
        for state in new_states:
            # Update epsilon transitions
            state.epsilon = [state_map[t] for t in state.epsilon if t in state_map]
            # Update normal transitions
            for trans in state.transitions:
                trans.target = state_map[trans.target]
                
        # Update start and accept states
        self.start = state_map[self.start]
        if self.accept in state_map:
            self.accept = state_map[self.accept]
        else:
            # Create a new accept state if the original is unreachable
            accept_state = NFAState()
            self.accept = len(new_states)
            new_states.append(accept_state)
            
        self.states = new_states
        
    def _optimize_epsilon_transitions(self):
        """Optimize epsilon transitions by computing transitive closures."""
        # First, compute epsilon closures for all states
        epsilon_closures = {}
        for i in range(len(self.states)):
            epsilon_closures[i] = set(self.epsilon_closure([i]))
        
        # For each state, optimize its transitions
        for i, state in enumerate(self.states):
            # Skip accept state
            if i == self.accept:
                continue
                
            # Get epsilon closure for this state
            closure = epsilon_closures[i]
            
            # Skip if no epsilon transitions
            if len(closure) <= 1:
                continue
                
            # For each state in the closure, copy its transitions to this state
            for target in closure:
                if target == i:
                    continue
                    
                target_state = self.states[target]
                
                # Copy normal transitions
                for trans in target_state.transitions:
                    # Skip if this would create a duplicate transition
                    duplicate = False
                    for existing in state.transitions:
                        if (existing.target == trans.target and 
                            existing.variable == trans.variable and
                            existing.condition == trans.condition):
                            duplicate = True
                            break
                            
                    if not duplicate:
                        state.add_transition(
                            trans.condition,
                            trans.target,
                            trans.variable,
                            trans.priority,
                            trans.metadata.copy() if trans.metadata else {}
                        )
            
            # Optimize variables - if state in closure has variable, copy it
            for target in closure:
                if target == i:
                    continue
                    
                target_state = self.states[target]
                if target_state.variable and not state.variable:
                    state.variable = target_state.variable
                
                # Merge subset variables if needed
                if target_state.subset_vars:
                    state.subset_vars.update(target_state.subset_vars)
                    
                # Copy permute data if needed
                if target_state.permute_data and not state.permute_data:
                    state.permute_data = target_state.permute_data.copy()
                    
                # Copy anchor data if needed
                if target_state.is_anchor and not state.is_anchor:
                    state.is_anchor = True
                    state.anchor_type = target_state.anchor_type
            
            # If accept state is in closure, make this state accepting too
            if self.accept in closure:
                # Add epsilon to accept state
                state.add_epsilon(self.accept)
                
        # Clean up epsilon transitions that are now redundant
        # Only keep epsilon transitions to states that have unique behavior
        for i, state in enumerate(self.states):
            # Skip accept state
            if i == self.accept:
                continue
                
            new_epsilon = []
            for eps_target in state.epsilon:
                # Always keep transition to accept state
                if eps_target == self.accept:
                    if eps_target not in new_epsilon:
                        new_epsilon.append(eps_target)
                    continue
                
                # Check if target has transitions this state doesn't have
                target_state = self.states[eps_target]
                has_unique_transitions = False
                
                for trans in target_state.transitions:
                    found_match = False
                    for existing in state.transitions:
                        if (existing.target == trans.target and 
                            existing.variable == trans.variable and
                            existing.condition == trans.condition):
                            found_match = True
                            break
                    
                    if not found_match:
                        has_unique_transitions = True
                        break
                
                # Keep epsilon if target has unique transitions or other unique properties
                if (has_unique_transitions or 
                    (target_state.is_anchor and not state.is_anchor) or
                    (target_state.variable and not state.variable) or
                    (eps_target not in new_epsilon and target_state.subset_vars and 
                     not target_state.subset_vars.issubset(state.subset_vars))):
                    new_epsilon.append(eps_target)
            
            # Update epsilon transitions
            state.epsilon = new_epsilon

# enhanced/automata.py - Part 3: NFABuilder Core Methods

class NFABuilder:
    """
    Enhanced NFA builder with comprehensive pattern support.
    
    This builder creates NFAs from pattern tokens with support for:
    - All pattern quantifiers (*, +, ?, {n}, {n,m})
    - Anchors (^ and $)
    - Pattern exclusions ({- ... -})
    - PERMUTE patterns with nested PERMUTE support
    - Subset variables
    - Empty pattern matching
    """
    def __init__(self):
        self.states: List[NFAState] = []
        self.current_exclusion = False
        self.exclusion_ranges: List[Tuple[int, int]] = []
        self.metadata: Dict[str, Any] = {}
        self.subset_vars: Dict[str, List[str]] = {}
    
    def new_state(self) -> int:
        """Create a new NFA state and return its index."""
        state = NFAState()
        self.states.append(state)
        return len(self.states) - 1
    
    def add_epsilon(self, from_state: int, to_state: int):
        """Add an epsilon transition between states."""
        if to_state not in self.states[from_state].epsilon:
            self.states[from_state].epsilon.append(to_state)
 
    def build(self, tokens: List[PatternToken], define: Dict[str, str], 
             subset_vars: Dict[str, List[str]] = None) -> NFA:
        """
        Build NFA from pattern tokens with comprehensive SQL:2016 support.
        
        Args:
            tokens: List of pattern tokens
            define: Dictionary of variable definitions
            subset_vars: Dictionary of subset variable definitions
            
        Returns:
            NFA: The constructed NFA with full SQL:2016 compliance
        """
        # Store subset variables
        self.subset_vars = subset_vars or {}
        
        # Reset state
        self.states = []
        self.current_exclusion = False
        self.exclusion_ranges = []
        self.metadata = {}
        
        # Create start and accept states
        start = self.new_state()
        accept = self.new_state()
        
        # Mark accept state
        self.states[accept].is_accept = True
        
        # Handle empty pattern - SQL:2016 treats this as a match
        if not tokens:
            self.add_epsilon(start, accept)
            return NFA(start, accept, self.states, [], {"empty_pattern": True})
        
        # Process pattern with full SQL:2016 compliance
        idx = [0]  # Use mutable list for position tracking
        
        try:
            # Process sequence of tokens
            pattern_start, pattern_end = self._process_sequence(tokens, idx, define)
            
            # Connect pattern to start and accept states
            self.add_epsilon(start, pattern_start)
            self.add_epsilon(pattern_end, accept)
            
            # Check for patterns that allow empty matches - critical for SQL:2016 compliance
            allows_empty = False
            
            # Check token quantifiers for empty match possibilities
            for token in tokens:
                if token.quantifier in ['?', '*', '{0}', '{0,}']:
                    allows_empty = True
                    self.metadata["allows_empty"] = True
                    break
                    
                # Also check for empty alternatives like (A|) which allow empty matches
                if token.type == PatternTokenType.ALTERNATION:
                    # If alternation is followed by GROUP_END, it might allow empty match
                    idx_alt = tokens.index(token)
                    if idx_alt + 1 < len(tokens) and tokens[idx_alt + 1].type == PatternTokenType.GROUP_END:
                        allows_empty = True
                        self.metadata["allows_empty"] = True
                        break
            
            # For patterns like Z? that allow empty matches, add direct path
            if allows_empty:
                self.add_epsilon(start, accept)
            
            # Add metadata about pattern structure for optimization and validation
            self._analyze_pattern_structure(tokens)
            
            # Debug: Check state list before NFA creation
            print(f"DEBUG: About to create NFA with start={start}, accept={accept}, states_count={len(self.states)}")
            for i, state in enumerate(self.states):
                print(f"DEBUG: State {i} before NFA creation: transitions={len(state.transitions)}, epsilon={state.epsilon}")
            
            # Create the NFA with all metadata
            nfa = NFA(start, accept, self.states, self.exclusion_ranges, self.metadata)
            
            # Debug: Check NFA after creation
            print(f"DEBUG: NFA created with states_count={len(nfa.states)}")
            for i, state in enumerate(nfa.states):
                print(f"DEBUG: NFA State {i} after creation: transitions={len(state.transitions)}, epsilon={state.epsilon}")
            
            # Apply optimizations - temporarily disabled for debugging
            # nfa.optimize()
            
            # Validate NFA structure
            if not nfa.validate():
                # Add warning to metadata if validation fails
                nfa.metadata["validation_warning"] = "NFA validation failed, structure may be problematic"
            
            return nfa
            
        except Exception as e:
            # Debug: Print the actual error that's being caught
            print(f"ERROR in NFABuilder.build: {e}")
            print(f"ERROR type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            
            # Create a minimal valid NFA in case of error
            error_state = self.new_state()
            error_accept = self.new_state()
            
            # Add metadata about the error
            error_metadata = {
                "error": str(e),
                "error_type": type(e).__name__,
                "tokens": str(tokens)
            }
            
            # Return a minimal NFA that won't match anything - FIX the indices
            return NFA(0, 1, [NFAState(), NFAState()], [], error_metadata)

    def _analyze_pattern_structure(self, tokens: List[PatternToken]):
        """
        Analyze pattern structure and store comprehensive metadata for SQL:2016 compliance.
        
        This method analyzes the pattern tokens to extract key characteristics that are
        important for SQL:2016 pattern matching functionality, such as:
        - Presence of anchors (^ and $)
        - PERMUTE patterns and nested PERMUTE structure
        - Pattern exclusions
        - Pattern variables and their relationships
        - Quantifier usage statistics
        - Alternation structure
        - Empty match possibilities
        
        Args:
            tokens: List of pattern tokens to analyze
        """
        # Check for anchors
        has_start_anchor = any(t.type == PatternTokenType.ANCHOR_START for t in tokens)
        has_end_anchor = any(t.type == PatternTokenType.ANCHOR_END for t in tokens)
        
        if has_start_anchor:
            self.metadata["has_start_anchor"] = True
        if has_end_anchor:
            self.metadata["has_end_anchor"] = True
        if has_start_anchor and has_end_anchor:
            self.metadata["spans_partition"] = True
        
        # Check for PERMUTE patterns and extract their structure
        permute_tokens = [t for t in tokens if t.type == PatternTokenType.PERMUTE]
        has_permute = len(permute_tokens) > 0
        
        if has_permute:
            self.metadata["has_permute"] = True
            
            # Extract PERMUTE variables and structure
            permute_vars = []
            permute_structure = []
            
            for token in permute_tokens:
                if "variables" in token.metadata:
                    permute_vars.extend([
                        v.value if hasattr(v, 'value') else v 
                        for v in token.metadata["variables"]
                    ])
                    
                    # Build structure info
                    permute_info = {
                        "variables": [
                            v.value if hasattr(v, 'value') else v 
                            for v in token.metadata["variables"]
                        ],
                        "quantifier": token.quantifier,
                        "nested": token.metadata.get("nested", False)
                    }
                    permute_structure.append(permute_info)
            
            if permute_vars:
                self.metadata["permute_variables"] = permute_vars
            
            if permute_structure:
                self.metadata["permute_structure"] = permute_structure
        
        # Check for exclusions and extract their structure
        exclusion_ranges = []
        current_exclusion_start = None
        
        for i, token in enumerate(tokens):
            if token.type == PatternTokenType.EXCLUSION_START:
                current_exclusion_start = i
            elif token.type == PatternTokenType.EXCLUSION_END and current_exclusion_start is not None:
                exclusion_ranges.append((current_exclusion_start, i))
                current_exclusion_start = None
        
        if exclusion_ranges:
            self.metadata["has_exclusion"] = True
            self.metadata["exclusion_ranges"] = exclusion_ranges
        
        # Extract all pattern variables and their properties
        all_vars = set()
        vars_with_quantifiers = {}
        
        for token in tokens:
            if token.type == PatternTokenType.LITERAL:
                all_vars.add(token.value)
                
                # Track variables with quantifiers
                if token.quantifier:
                    vars_with_quantifiers[token.value] = token.quantifier
        
        if all_vars:
            self.metadata["pattern_variables"] = list(all_vars)
        
        if vars_with_quantifiers:
            self.metadata["variables_with_quantifiers"] = vars_with_quantifiers
        
        # Check for alternation (|) - important for pattern compilation strategy
        has_alternation = any(t.type == PatternTokenType.ALTERNATION for t in tokens)
        if has_alternation:
            self.metadata["has_alternation"] = True
        
        # Check for pattern structures that allow empty matches
        allows_empty = False
        
        # Empty match is possible if any token has a quantifier that allows zero occurrences
        for token in tokens:
            if token.quantifier in ['?', '*', '{0}', '{0,}']:
                allows_empty = True
                break
                
            # Also check for complex structures like (A|) which allow empty matches
            if token.type == PatternTokenType.ALTERNATION:
                # If alternation is followed by a GROUP_END, it might allow empty match
                idx = tokens.index(token)
                if idx + 1 < len(tokens) and tokens[idx + 1].type == PatternTokenType.GROUP_END:
                    allows_empty = True
                    break
        
        if allows_empty:
            self.metadata["allows_empty_match"] = True

# enhanced/automata.py - Part 4: NFABuilder Pattern Processing Methods

    def _process_sequence(self, tokens: List[PatternToken], idx: List[int], define: Dict[str, str]) -> Tuple[int, int]:
        """Process a sequence of tokens until the end or until a GROUP_END."""
        start = self.new_state()
        current = start
        
        while idx[0] < len(tokens):
            token = tokens[idx[0]]
            
            if token.type == PatternTokenType.GROUP_END:
                # End of group - return current NFA fragment
                end = self.new_state()
                self.add_epsilon(current, end)
                return start, end
                
            elif token.type == PatternTokenType.ALTERNATION:
                # Start of alternation - finish current branch
                left_end = self.new_state()
                self.add_epsilon(current, left_end)
                
                # Skip the alternation token
                idx[0] += 1
                
                # Process the right side of the alternation
                right_start, right_end = self._process_sequence(tokens, idx, define)
                
                # Create a new fragment representing the alternation
                alt_start = self.new_state()
                alt_end = self.new_state()
                
                # Connect alternation fragment
                self.add_epsilon(alt_start, start)  # To left branch
                self.add_epsilon(alt_start, right_start)  # To right branch
                self.add_epsilon(left_end, alt_end)  # From left branch
                self.add_epsilon(right_end, alt_end)  # From right branch
                
                return alt_start, alt_end
                
            elif token.type == PatternTokenType.GROUP_START:
                # Process nested group
                idx[0] += 1  # Skip GROUP_START
                group_start, group_end = self._process_sequence(tokens, idx, define)
                
                # Check if there's a GROUP_END with quantifier
                if idx[0] < len(tokens) and tokens[idx[0]].type == PatternTokenType.GROUP_END:
                    group_end_token = tokens[idx[0]]
                    idx[0] += 1  # Skip GROUP_END
                    
                    # Apply quantifiers to the group if present
                    if group_end_token.quantifier:
                        min_rep, max_rep, greedy = parse_quantifier(group_end_token.quantifier)
                        group_start, group_end = self._apply_quantifier(
                            group_start, group_end, min_rep, max_rep, greedy)
                
                # Connect group to current fragment
                self.add_epsilon(current, group_start)
                current = group_end
                
            elif token.type == PatternTokenType.PERMUTE:
                # Use the enhanced PERMUTE processing
                perm_start, perm_end = self._process_permute(token, define)
                
                # Connect permutation fragment to current NFA
                self.add_epsilon(current, perm_start)
                current = perm_end
                
                # Skip the PERMUTE token
                idx[0] += 1
                
            elif token.type == PatternTokenType.EXCLUSION_START:
                # Enhanced exclusion handling
                exclusion_start, exclusion_end = self._process_exclusion(tokens, idx, define)
                
                # Connect exclusion fragment to current NFA
                self.add_epsilon(current, exclusion_start)
                current = exclusion_end
                
            elif token.type in (PatternTokenType.ANCHOR_START, PatternTokenType.ANCHOR_END):
                # Create anchor state
                anchor_state = self.new_state()
                self.states[anchor_state].is_anchor = True
                self.states[anchor_state].anchor_type = token.type
                
                # Connect anchor to current NFA
                self.add_epsilon(current, anchor_state)
                current = anchor_state
                
                # Skip anchor token
                idx[0] += 1
                
            elif token.type == PatternTokenType.LITERAL:
                # Create states for the variable
                var_start, var_end = self.create_var_states(token.value, define)
                
                # Apply quantifiers if present
                if token.quantifier:
                    min_rep, max_rep, greedy = parse_quantifier(token.quantifier)
                    var_start, var_end = self._apply_quantifier(
                        var_start, var_end, min_rep, max_rep, greedy)
                
                # Connect to current NFA
                self.add_epsilon(current, var_start)
                current = var_end
                
                # Skip literal token
                idx[0] += 1
                
            else:
                # Skip other token types
                idx[0] += 1
        
        # End of sequence - create end state
        end = self.new_state()
        self.add_epsilon(current, end)
        
        return start, end

    def _process_exclusion(self, tokens: List[PatternToken], idx: List[int], define: Dict[str, str]) -> Tuple[int, int]:
        """
        Process an exclusion pattern fragment with SQL:2016 compliant behavior.
        
        SQL:2016 exclusion patterns use {- ... -} syntax to exclude certain patterns.
        This implementation handles them by marking states in the exclusion pattern as excluded,
        which will be filtered out during result processing.
        
        Args:
            tokens: List of all pattern tokens
            idx: Current position in the token list (mutable)
            define: Dictionary of variable definitions
            
        Returns:
            Tuple of (start_state, end_state) for the exclusion pattern
        """
        # Remember exclusion start position in the NFA
        exclusion_start_idx = len(self.states)
        
        # Track original exclusion state and set current to true
        previous_exclusion_state = self.current_exclusion
        self.current_exclusion = True
        
        # Skip exclusion start token
        idx[0] += 1
        
        # Create start and end states for the exclusion pattern
        excl_start = self.new_state()
        
        # Mark exclusion start state
        self.states[excl_start].is_excluded = True
        
        # Process tokens inside exclusion normally
        # SQL:2016 requires exclusion patterns to be fully matched but excluded from output
        sub_pattern_start, sub_pattern_end = self._process_sequence(tokens, idx, define)
        
        # Connect to sub-pattern
        self.add_epsilon(excl_start, sub_pattern_start)
        
        # Create exclusion end state
        excl_end = self.new_state()
        
        # Connect sub-pattern to exclusion end
        self.add_epsilon(sub_pattern_end, excl_end)
        
        # Mark exclusion end state
        self.states[excl_end].is_excluded = True
        
        # Mark exclusion end in NFA states
        exclusion_end_idx = len(self.states) - 1
        
        # Store exclusion range for later processing
        self.exclusion_ranges.append((exclusion_start_idx, exclusion_end_idx))
        
        # Mark all states in this range as excluded
        for i in range(exclusion_start_idx, exclusion_end_idx + 1):
            self.states[i].is_excluded = True
        
        # Restore previous exclusion state
        self.current_exclusion = previous_exclusion_state
        
        # Skip exclusion end token if present
        if idx[0] < len(tokens) and tokens[idx[0]].type == PatternTokenType.EXCLUSION_END:
            idx[0] += 1
        
        # Return the exclusion pattern states
        # Note: These will be processed normally by the automaton,
        # but will be filtered from output during result processing
        return excl_start, excl_end

    def create_var_states(self, var: Union[str, PatternToken], define: Dict[str, str]) -> Tuple[int, int]:
        """
        Create states for a pattern variable with enhanced SQL:2016 support.
        
        Args:
            var: Variable name or PatternToken object
            define: Dictionary of variable definitions
            
        Returns:
            Tuple of (start_state, end_state)
        """
        start = self.new_state()
        end = self.new_state()
        
        # Handle PatternToken objects (for nested patterns)
        if isinstance(var, PatternToken):
            # This is a PatternToken object
            if var.type == PatternTokenType.PERMUTE:
                # Process nested PERMUTE token
                nested_start, nested_end = self._process_permute(var, define)
                self.add_epsilon(start, nested_start)
                self.add_epsilon(nested_end, end)
                return start, end
            elif var.type == PatternTokenType.GROUP_START:
                # Process group token
                idx = [0]  # Use list for mutable reference
                tokens = [var]  # Create token list with this token
                group_start, group_end = self._process_sequence(tokens, idx, define)
                self.add_epsilon(start, group_start)
                self.add_epsilon(group_end, end)
                return start, end
            else:
                # Use the value from the token
                var_base = var.value
                quantifier = var.quantifier
        else:
            # String variable - extract any quantifiers
            var_base = var
            quantifier = None
            
            # Extract quantifiers from variable name
            if isinstance(var, str):
                if var.endswith('?'):
                    var_base = var[:-1]
                    quantifier = '?'
                elif var.endswith('+'):
                    var_base = var[:-1]
                    quantifier = '+'
                elif var.endswith('*'):
                    var_base = var[:-1]
                    quantifier = '*'
                elif '{' in var and var.endswith('}'):
                    open_idx = var.find('{')
                    var_base = var[:open_idx]
                    quantifier = var[open_idx:]
        
        # Get condition from DEFINE clause with improved handling
        if var_base in define:
            condition_str = define[var_base]
        else:
            # Default to TRUE if no definition exists
            condition_str = "TRUE"
            
        # Compile the condition
        condition_fn = compile_condition(condition_str)
        
        # Create transition with condition and variable tracking
        self.states[start].add_transition(condition_fn, end, var_base)
        
        # Store variable name on both states
        self.states[start].variable = var_base
        self.states[end].variable = var_base  # Also mark end state for better variable tracking
        
        # Handle subset variables - SQL:2016 compliant
        if var_base in self.subset_vars:
            # Add subset components to states
            subset_components = self.subset_vars[var_base]
            self.states[start].subset_vars = set(subset_components)
            self.states[end].subset_vars = set(subset_components)
            
            # Store metadata about subset variable relationship
            if not hasattr(self.states[start], "subset_parent"):
                self.states[start].subset_parent = var_base
                self.states[end].subset_parent = var_base
        
        # Apply quantifier if present
        if quantifier:
            min_rep, max_rep, greedy = parse_quantifier(quantifier)
            start, end = self._apply_quantifier(start, end, min_rep, max_rep, greedy)
        
        return start, end
        
        # Apply quantifier if present
        if quantifier:
            min_rep, max_rep, greedy = parse_quantifier(quantifier)
            start, end = self._apply_quantifier(start, end, min_rep, max_rep, greedy)
        
        return start, end

    def _process_permute(self, token: PatternToken, define: Dict[str, str]) -> Tuple[int, int]:
        """
        Process a PERMUTE token with comprehensive support for all cases.
        
        Args:
            token: The PERMUTE token with metadata
            define: Dictionary of variable definitions
                
        Returns:
            Tuple of (start_state, end_state)
        """
        # Extract permute variables
        variables = token.metadata.get("variables", [])
        original_pattern = token.metadata.get("original", "")
        
        # Create states for the permutation
        perm_start = self.new_state()
        perm_end = self.new_state()
        
        # Store PERMUTE metadata in the start state
        self.states[perm_start].permute_data = {
            "variables": variables,
            "original_pattern": original_pattern
        }
        
        # Handle edge cases
        if not variables:
            # Empty PERMUTE - just an epsilon transition
            self.add_epsilon(perm_start, perm_end)
            return perm_start, perm_end
        elif len(variables) == 1:
            # Single variable - equivalent to just the variable
            var = variables[0]
            if isinstance(var, PatternToken) and var.type == PatternTokenType.PERMUTE:
                # Nested single PERMUTE
                inner_start, inner_end = self._process_permute(var, define)
                self.add_epsilon(perm_start, inner_start)
                self.add_epsilon(inner_end, perm_end)
            else:
                # Regular variable
                var_start, var_end = self.create_var_states(var, define)
                self.add_epsilon(perm_start, var_start)
                self.add_epsilon(var_end, perm_end)
            return perm_start, perm_end
        
        # Special case for PERMUTE: SQL:2016 allows each variable to match only once
        # So we need to track which variables have been matched
        
        # Pre-process variables to handle nested PERMUTE and quantifiers
        processed_vars = []
        for var in variables:
            if isinstance(var, PatternToken) and var.type == PatternTokenType.PERMUTE:
                # Recursively process nested PERMUTE
                nested_start, nested_end = self._process_permute(var, define)
                processed_vars.append((var, nested_start, nested_end))
            else:
                # Extract base variable and quantifier
                var_base = var
                quantifier = None
                
                if isinstance(var, str):
                    if var.endswith('*'):
                        var_base = var[:-1]
                        quantifier = '*'
                    elif var.endswith('+'):
                        var_base = var[:-1]
                        quantifier = '+'
                    elif var.endswith('?'):
                        var_base = var[:-1]
                        quantifier = '?'
                    elif '{' in var and var.endswith('}'):
                        open_idx = var.find('{')
                        var_base = var[:open_idx]
                        quantifier = var[open_idx:]
                
                # Process as regular variable
                var_start, var_end = self.create_var_states(var_base, define)
                
                # Apply quantifier if present
                if quantifier:
                    min_rep, max_rep, greedy = parse_quantifier(quantifier)
                    var_start, var_end = self._apply_quantifier(
                        var_start, var_end, min_rep, max_rep, greedy)
                
                processed_vars.append((var_base, var_start, var_end))
        
        # SQL:2016 PERMUTE implementation requires each variable to match exactly once
        # Following Trino's approach, we generate all permutations explicitly
        all_perms = list(itertools.permutations(range(len(processed_vars))))
        
        # For each permutation, create a separate branch in the NFA
        for perm in all_perms:
            # Create a new start state for this permutation
            branch_start = self.new_state()
            current = branch_start
            
            # Create a chain of states for this permutation
            for idx in perm:
                var_info = processed_vars[idx]
                
                if isinstance(var_info[0], PatternToken) and var_info[0].type == PatternTokenType.PERMUTE:
                    # For nested PERMUTE, create fresh copy to avoid state sharing
                    var_token = var_info[0]
                    fresh_start, fresh_end = self._process_permute(var_token, define)
                    
                    # Connect to current chain
                    self.add_epsilon(current, fresh_start)
                    current = fresh_end
                else:
                    # For regular variables, create fresh copy to avoid state sharing
                    var_base = var_info[0]
                    fresh_start, fresh_end = self.create_var_states(var_base, define)
                    
                    # Connect to current chain
                    self.add_epsilon(current, fresh_start)
                    current = fresh_end
            
            # Connect this permutation branch to the main permutation end
            self.add_epsilon(current, perm_end)
            
            # Connect permutation start to this branch
            self.add_epsilon(perm_start, branch_start)
        
        # Apply quantifiers to the entire PERMUTE pattern if present
        if token.quantifier:
            min_rep, max_rep, greedy = parse_quantifier(token.quantifier)
            perm_start, perm_end = self._apply_quantifier(
                perm_start, perm_end, min_rep, max_rep, greedy)
        
        return perm_start, perm_end
# enhanced/automata.py - Part 7: NFABuilder Quantifier Handling

    def _apply_quantifier(self, 
                      start: int, 
                      end: int, 
                      min_rep: int, 
                      max_rep: Optional[int],
                      greedy: bool) -> Tuple[int, int]:
        """
        Apply quantifier to a subpattern with improved SQL:2016 compliant handling.
        
        Args:
            start: Start state of the subpattern
            end: End state of the subpattern
            min_rep: Minimum number of repetitions
            max_rep: Maximum number of repetitions (None for unbounded)
            greedy: Whether quantifier is greedy (True) or reluctant (False)
            
        Returns:
            Tuple of (new_start, new_end) states
        """
        # Create new start and end states for the quantified pattern
        new_start = self.new_state()
        new_end = self.new_state()
        
        # SQL:2016 compliance: Ensure empty match handling works correctly
        # Mark the new end state as allowing empty matches if min_rep is 0
        if min_rep == 0:
            self.states[new_end].is_empty_match = True
        
        # Special case for exact repetitions {n,n}
        if min_rep == max_rep:
            if min_rep == 0:
                # {0,0} - empty match
                self.add_epsilon(new_start, new_end)
                return new_start, new_end
            elif min_rep == 1:
                # {1,1} - exactly one match, no quantifier
                self.add_epsilon(new_start, start)
                self.add_epsilon(end, new_end)
                return new_start, new_end
            else:
                # {n,n} - exactly n repetitions
                current = new_start
                
                # Create a chain of n copies
                for i in range(min_rep):
                    # For last repetition, connect directly to new_end
                    if i == min_rep - 1:
                        self.add_epsilon(current, start)
                        self.add_epsilon(end, new_end)
                    else:
                        # Create intermediate states for this repetition
                        rep_start = self.new_state()
                        
                        # Connect to original pattern
                        self.add_epsilon(current, start)
                        self.add_epsilon(end, rep_start)
                        
                        current = rep_start
                
                return new_start, new_end
        
        # Handle standard quantifiers with min and max
        
        # * (zero or more) - {0,}
        if min_rep == 0 and max_rep is None:
            # Connect new_start to new_end for empty match
            self.add_epsilon(new_start, new_end)
            
            if greedy:
                # Greedy matching - try to match first, then finish
                self.add_epsilon(new_start, start)  # Try to match
                self.add_epsilon(end, start)        # After match, try to match again
                self.add_epsilon(end, new_end)      # Or finish
            else:
                # Reluctant matching - try to finish first, then match
                self.add_epsilon(new_start, new_end)  # Try to skip
                self.add_epsilon(new_start, start)    # Or try to match
                self.add_epsilon(end, new_end)        # After match, try to finish
                self.add_epsilon(end, start)          # Or match again
        
        # + (one or more) - {1,}
        elif min_rep == 1 and max_rep is None:
            # Must match at least once
            self.add_epsilon(new_start, start)
            
            if greedy:
                # Greedy matching - try to match more first
                self.add_epsilon(end, start)      # After match, try to match again
                self.add_epsilon(end, new_end)    # Or finish
            else:
                # Reluctant matching - try to finish first
                self.add_epsilon(end, new_end)    # After match, try to finish
                self.add_epsilon(end, start)      # Or match again
        
        # ? (optional) - {0,1}
        elif min_rep == 0 and max_rep == 1:
            if greedy:
                # Greedy - try to match first
                self.add_epsilon(new_start, start)    # Try to match
                self.add_epsilon(new_start, new_end)  # Or skip
                self.add_epsilon(end, new_end)        # After match, finish
            else:
                # Reluctant - try to skip first
                self.add_epsilon(new_start, new_end)  # Try to skip
                self.add_epsilon(new_start, start)    # Or match
                self.add_epsilon(end, new_end)        # After match, finish
        
        # General case {m,n} where m >= 0 and n > m
        else:
            # Create states for minimum required repetitions
            if min_rep == 0:
                # Allow empty match
                self.add_epsilon(new_start, new_end)
                min_chain_start = new_start
                min_chain_end = new_start
            else:
                # Create chain for minimum required matches
                min_chain_start = new_start
                current = new_start
                
                # Create min_rep-1 copies that must match
                for i in range(min_rep - 1):
                    rep_start = self.new_state()
                    
                    # Connect to original pattern
                    self.add_epsilon(current, start)
                    self.add_epsilon(end, rep_start)
                    
                    current = rep_start
                
                # Connect last required match
                self.add_epsilon(current, start)
                min_chain_end = end
            
            # Handle optional repetitions (between min_rep and max_rep)
            if max_rep is not None:
                # Limited max repetitions - {m,n} where n is finite
                opt_start = min_chain_end
                
                # Create optional chain for (max_rep - min_rep) optional matches
                for i in range(min_rep, max_rep):
                    opt_end = self.new_state()
                    
                    if greedy:
                        # Try to match more (greedy)
                        if i > 0:  # Not first optional match
                            self.add_epsilon(opt_start, start)  # Try to match
                            self.add_epsilon(opt_start, new_end)  # Or finish
                        else:
                            # First optional match
                            self.add_epsilon(opt_start, start)  # Try to match
                            self.add_epsilon(opt_start, new_end)  # Or finish
                    else:
                        # Try to finish (reluctant)
                        if i > 0:  # Not first optional match
                            self.add_epsilon(opt_start, new_end)  # Try to finish
                            self.add_epsilon(opt_start, start)  # Or match more
                        else:
                            # First optional match
                            self.add_epsilon(opt_start, new_end)  # Try to finish
                            self.add_epsilon(opt_start, start)  # Or match more
                    
                    # After match, connect to opt_end
                    self.add_epsilon(end, opt_end)
                    
                    # Update for next iteration
                    opt_start = opt_end
                
                # Connect last optional state to new_end
                self.add_epsilon(opt_start, new_end)
            else:
                # Unbounded repetitions - {m,}
                if greedy:
                    # Greedy matching - try more matches first
                    self.add_epsilon(min_chain_end, start)  # Try to match more
                    self.add_epsilon(min_chain_end, new_end)  # Or finish
                    self.add_epsilon(end, start)  # After match, try to match more
                    self.add_epsilon(end, new_end)  # Or finish
                else:
                    # Reluctant matching - try to finish first
                    self.add_epsilon(min_chain_end, new_end)  # Try to finish
                    self.add_epsilon(min_chain_end, start)  # Or match more
                    self.add_epsilon(end, new_end)  # After match, try to finish
                    self.add_epsilon(end, start)  # Or match more
        
        return new_start, new_end

    def _copy_subpattern(self, 
                        orig_start: int, 
                        orig_end: int, 
                        new_start: int, 
                        new_end: int):
        """Copy a subpattern between new states with proper variable handling."""
        # Create a mapping from original states to new states
        state_map = {orig_start: new_start, orig_end: new_end}
        
        # Queue of states to process
        queue = [(orig_start, new_start)]
        
        while queue:
            orig_state, new_state = queue.pop(0)
            
            # Copy state properties
            new_state_obj = self.states[new_state]
            orig_state_obj = self.states[orig_state]
            
            new_state_obj.variable = orig_state_obj.variable
            new_state_obj.is_excluded = orig_state_obj.is_excluded
            new_state_obj.is_anchor = orig_state_obj.is_anchor
            new_state_obj.anchor_type = orig_state_obj.anchor_type
            new_state_obj.subset_vars = set(orig_state_obj.subset_vars)
            
            # Copy transitions
            for trans in orig_state_obj.transitions:
                # Map target state
                if trans.target == orig_end:
                    target = new_end
                elif trans.target in state_map:
                    target = state_map[trans.target]
                else:
                    # Create new state
                    target = self.new_state()
                    state_map[trans.target] = target
                    queue.append((trans.target, target))
                
                # Add transition
                new_state_obj.add_transition(
                    trans.condition,
                    target,
                    trans.variable,
                    trans.priority,
                    trans.metadata.copy() if trans.metadata else None
                )
            
            # Copy epsilon transitions
            for eps_target in orig_state_obj.epsilon:
                if eps_target == orig_end:
                    new_state_obj.add_epsilon(new_end)
                elif eps_target in state_map:
                    new_state_obj.add_epsilon(state_map[eps_target])
                else:
                    # Create new state
                    new_eps_target = self.new_state()
                    state_map[eps_target] = new_eps_target
                    queue.append((eps_target, new_eps_target))
                    new_state_obj.add_epsilon(new_eps_target)
# enhanced/automata.py - Part 9: NFABuilder Utility Methods

    def optimize_nfa(self, nfa: NFA) -> NFA:
        """
        Apply advanced optimizations to an existing NFA.
        
        Args:
            nfa: The NFA to optimize
            
        Returns:
            NFA: The optimized NFA
        """
        # Store original NFA
        self.states = nfa.states
        
        # Apply optimizations
        self._remove_dead_states()
        self._merge_equivalent_states()
        self._optimize_epsilon_transitions()
        
        # Create new optimized NFA
        return NFA(nfa.start, nfa.accept, self.states, nfa.exclusion_ranges, nfa.metadata)
    
    def _remove_dead_states(self):
        """Remove states that cannot reach the accept state."""
        # Find states that can reach accept state
        can_reach_accept = set()
        queue = [len(self.states) - 1]  # Accept state is typically the last one
        
        while queue:
            state_idx = queue.pop(0)
            if state_idx in can_reach_accept:
                continue
                
            can_reach_accept.add(state_idx)
            
            # Find states that can reach this state
            for i, state in enumerate(self.states):
                # Check normal transitions
                for trans in state.transitions:
                    if trans.target == state_idx and i not in can_reach_accept:
                        queue.append(i)
                
                # Check epsilon transitions
                if state_idx in state.epsilon and i not in can_reach_accept:
                    queue.append(i)
        
        # Keep only states that are reachable from start and can reach accept
        reachable_from_start = set()
        queue = [0]  # Start state is typically the first one
        
        while queue:
            state_idx = queue.pop(0)
            if state_idx in reachable_from_start:
                continue
                
            reachable_from_start.add(state_idx)
            
            # Add states reachable from this state
            state = self.states[state_idx]
            
            # Add states reachable via normal transitions
            for trans in state.transitions:
                if trans.target not in reachable_from_start:
                    queue.append(trans.target)
            
            # Add states reachable via epsilon transitions
            for eps in state.epsilon:
                if eps not in reachable_from_start:
                    queue.append(eps)
        
        # Keep only states that are both reachable from start and can reach accept
        keep_states = reachable_from_start.intersection(can_reach_accept)
        
        # Create new states list with only kept states
        new_states = []
        state_map = {}
        
        for idx in sorted(keep_states):
            state_map[idx] = len(new_states)
            new_states.append(self.states[idx])
        
        # Update transitions
        for state in new_states:
            # Update normal transitions
            new_transitions = []
            for trans in state.transitions:
                if trans.target in state_map:
                    trans.target = state_map[trans.target]
                    new_transitions.append(trans)
            state.transitions = new_transitions
            
            # Update epsilon transitions
            state.epsilon = [state_map[eps] for eps in state.epsilon if eps in state_map]
        
        self.states = new_states
    
    def _merge_equivalent_states(self):
        """Merge states that are functionally equivalent."""
        # This is a complex optimization - simplified implementation
        # In a full implementation, we would use an algorithm like Hopcroft's algorithm
        pass
    
    def visualize_nfa(self, nfa: NFA) -> str:
        """
        Generate a DOT representation of the NFA for visualization.
        
        Args:
            nfa: The NFA to visualize
            
        Returns:
            str: DOT format representation of the NFA
        """
        dot = ["digraph NFA {", "  rankdir=LR;"]
        
        # Add states
        for i, state in enumerate(nfa.states):
            # Determine state attributes
            attrs = []
            
            if i == nfa.start:
                attrs.append("shape=diamond")
            elif i == nfa.accept:
                attrs.append("shape=doublecircle")
            else:
                attrs.append("shape=circle")
                
            if state.is_anchor:
                attrs.append("color=blue")
                
            if state.is_excluded:
                attrs.append("style=dashed")
                
            # Add variable label if present
            label = f"{i}"
            if state.variable:
                label += f"\\n{state.variable}"
                
            attrs.append(f"label=\"{label}\"")
            
            # Add state to DOT
            dot.append(f"  {i} [{', '.join(attrs)}];")
        
        # Add transitions
        for i, state in enumerate(nfa.states):
            # Add normal transitions
            for trans in state.transitions:
                label = trans.variable if trans.variable else ""
                dot.append(f"  {i} -> {trans.target} [label=\"{label}\"];")
            
            # Add epsilon transitions
            for eps in state.epsilon:
                dot.append(f"  {i} -> {eps} [label=\"ε\", style=dashed];")
        
        dot.append("}")
        return "\n".join(dot)