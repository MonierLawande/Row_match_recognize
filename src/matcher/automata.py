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
    Enhanced NFA state with comprehensive pattern matching support.
    
    Attributes:
        transitions: List of outgoing transitions
        epsilon: List of epsilon transition target states
        variable: Pattern variable associated with this state
        is_excluded: Whether this state is part of an excluded pattern
        is_anchor: Whether this state represents an anchor (^ or $)
        anchor_type: Type of anchor (START or END)
        subset_vars: Set of subset variables defined for this state
        permute_data: Optional metadata for PERMUTE patterns
        is_empty_match: Whether this state allows empty matches
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
    
    def add_transition(self, condition: ConditionFn, target: int, variable: Optional[str] = None, 
                      priority: int = 0, metadata: Dict[str, Any] = None):
        """Add a transition with enhanced metadata support."""
        self.transitions.append(Transition(
            condition, 
            target, 
            variable, 
            priority,
            metadata or {}
        ))
        
    def add_epsilon(self, target: int):
        """Add an epsilon transition to target state."""
        if target not in self.epsilon:
            self.epsilon.append(target)

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
        Compute epsilon closure for given states with cycle detection.
        
        Args:
            state_indices: List of state indices to compute closure for
            
        Returns:
            List of state indices in the epsilon closure
        """
        closure = set(state_indices)
        stack = list(state_indices)
        visited_pairs = set()  # Track (state, target) pairs to detect cycles
        
        while stack:
            s = stack.pop()
            for t in self.states[s].epsilon:
                # Skip if we've already processed this epsilon transition
                if (s, t) in visited_pairs:
                    continue
                    
                visited_pairs.add((s, t))
                if t not in closure:
                    closure.add(t)
                    stack.append(t)
                    
        return sorted(closure)  # Sort for deterministic behavior
        
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
        # For each state, compute its epsilon closure
        for i, state in enumerate(self.states):
            # Skip accept state
            if i == self.accept:
                continue
                
            # Get epsilon closure for this state
            closure = self.epsilon_closure([i])
            
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
                            existing.variable == trans.variable):
                            duplicate = True
                            break
                            
                    if not duplicate:
                        state.add_transition(
                            trans.condition,
                            trans.target,
                            trans.variable,
                            trans.priority,
                            trans.metadata
                        )
                        
            # If accept state is in closure, make this state accepting too
            if self.accept in closure:
                # Add epsilon to accept state
                state.add_epsilon(self.accept)

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
        Build NFA from pattern tokens with enhanced features.
        
        Args:
            tokens: List of pattern tokens
            define: Dictionary of variable definitions
            subset_vars: Dictionary of subset variable definitions
            
        Returns:
            NFA: The constructed NFA
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
        
        # Handle empty pattern
        if not tokens:
            self.add_epsilon(start, accept)
            return NFA(start, accept, self.states, [], {"empty_pattern": True})
        
        # Process pattern with optional components (like Z?)
        pattern_start, pattern_end = self._process_sequence(tokens, [0], define)
        
        # Connect pattern to start and accept states
        self.add_epsilon(start, pattern_start)
        self.add_epsilon(pattern_end, accept)
        
        # Check for patterns that allow empty matches
        allows_empty = False
        for token in tokens:
            if token.quantifier in ['?', '*', '{0}', '{0,}']:
                allows_empty = True
                break
            
        # For patterns like Z?, add direct path to allow empty matches
        if allows_empty:
            print("Pattern allows empty matches - adding epsilon transition")
            self.add_epsilon(start, accept)  # Critical change for empty match support
            self.metadata["allows_empty"] = True
        
        # Add metadata about pattern structure
        self._analyze_pattern_structure(tokens)
        
        # Create and return the NFA
        nfa = NFA(start, accept, self.states, self.exclusion_ranges, self.metadata)
        
        # Apply optimizations
        nfa.optimize()
        
        return nfa

    def _analyze_pattern_structure(self, tokens: List[PatternToken]):
        """Analyze pattern structure and store metadata."""
        # Check for anchors
        has_start_anchor = any(t.type == PatternTokenType.ANCHOR_START for t in tokens)
        has_end_anchor = any(t.type == PatternTokenType.ANCHOR_END for t in tokens)
        
        if has_start_anchor:
            self.metadata["has_start_anchor"] = True
        if has_end_anchor:
            self.metadata["has_end_anchor"] = True
        if has_start_anchor and has_end_anchor:
            self.metadata["spans_partition"] = True
            
        # Check for PERMUTE patterns
        has_permute = any(t.type == PatternTokenType.PERMUTE for t in tokens)
        if has_permute:
            self.metadata["has_permute"] = True
            
            # Extract PERMUTE variables
            permute_vars = []
            for token in tokens:
                if token.type == PatternTokenType.PERMUTE:
                    if "variables" in token.metadata:
                        permute_vars.extend(token.metadata["variables"])
                        
            if permute_vars:
                self.metadata["permute_variables"] = permute_vars
                
        # Check for exclusions
        has_exclusion = any(t.type == PatternTokenType.EXCLUSION_START for t in tokens)
        if has_exclusion:
            self.metadata["has_exclusion"] = True
            
        # Extract all pattern variables
        all_vars = set()
        for token in tokens:
            if token.type == PatternTokenType.LITERAL:
                all_vars.add(token.value)
                
        if all_vars:
            self.metadata["pattern_variables"] = list(all_vars)

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
        """Process an exclusion pattern fragment."""
        # Remember exclusion start position
        exclusion_start_idx = len(self.states)
        
        # Track original exclusion state and set current to true
        previous_exclusion_state = self.current_exclusion
        self.current_exclusion = True
        
        # Skip exclusion start token
        idx[0] += 1
        
        # Process tokens inside exclusion normally (don't create bypass)
        excl_start, excl_end = self._process_sequence(tokens, idx, define)
        
        # Mark exclusion end
        exclusion_end_idx = len(self.states) - 1
        self.exclusion_ranges.append((exclusion_start_idx, exclusion_end_idx))
        
        # Mark all states in this range as excluded
        for i in range(exclusion_start_idx, exclusion_end_idx + 1):
            self.states[i].is_excluded = True
        
        # Restore previous exclusion state
        self.current_exclusion = previous_exclusion_state
        
        # Skip exclusion end token if present
        if idx[0] < len(tokens) and tokens[idx[0]].type == PatternTokenType.EXCLUSION_END:
            idx[0] += 1
        
        # Return the exclusion states directly without bypass
        # This makes excluded variables available as normal transitions
        # but they will be filtered from output during result processing
        return excl_start, excl_end

    def create_var_states(self, var: Union[str, PatternToken], define: Dict[str, str]) -> Tuple[int, int]:
        """Create states for a pattern variable with support for subset variables and PatternToken objects."""
        start = self.new_state()
        end = self.new_state()
        
        # Handle PatternToken objects (for nested PERMUTE patterns)
        if hasattr(var, 'type') and hasattr(var, 'value'):
            # This is a PatternToken object
            if var.type == PatternTokenType.PERMUTE:
                # Process nested PERMUTE token
                nested_start, nested_end = self._process_permute(var, define)
                self.add_epsilon(start, nested_start)
                self.add_epsilon(nested_end, end)
                return start, end
            else:
                # Use the value from the token
                var_base = var.value
                quantifier = var.quantifier
        else:
            # Extract any quantifier from the variable name for string variables
            var_base = var
            quantifier = None
            
            # Handle quantifiers
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
        
        # Get condition from DEFINE clause or use TRUE
        condition = define.get(var_base, "TRUE")
        print(f"Creating transition for variable '{var_base}' with condition: '{condition}'")
        condition_fn = compile_condition(condition)
        
        # Create transition with condition
        self.states[start].add_transition(condition_fn, end, var_base)
        self.states[start].variable = var_base  # Mark state with variable name
        
        # Handle subset variables
        if var_base in self.subset_vars:
            # Add subset components to the state
            self.states[start].subset_vars = set(self.subset_vars[var_base])
            self.states[end].subset_vars = set(self.subset_vars[var_base])
        
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
        
        # Handle nested PERMUTE patterns
        processed_vars = []
        for var in variables:
            if isinstance(var, PatternToken) and var.type == PatternTokenType.PERMUTE:
                # Recursively process nested PERMUTE
                nested_start, nested_end = self._process_permute(var, define)
                processed_vars.append((nested_start, nested_end))
            else:
                # Check for quantifiers on variables
                if isinstance(var, str) and (var.endswith('*') or var.endswith('+') or 
                                            var.endswith('?') or 
                                            ('{' in var and var.endswith('}'))):
                    # Extract quantifier from the variable
                    var_base = var
                    quantifier = None

                    
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
                    
                    # Create state for base variable
                    var_start, var_end = self.create_var_states(var_base, define)
                    
                    # Apply quantifier if present
                    if quantifier:
                        min_rep, max_rep, greedy = parse_quantifier(quantifier)
                        var_start, var_end = self._apply_quantifier(
                            var_start, var_end, min_rep, max_rep, greedy)
                    
                    processed_vars.append((var_start, var_end))
                else:
                    # Regular variable without quantifier
                    var_start, var_end = self.create_var_states(var, define)
                    processed_vars.append((var_start, var_end))
        
        # Generate all permutations explicitly - this is the only correct approach
        # CRITICAL FIX: Create fresh states for each permutation to avoid cross-contamination
        all_perms = list(itertools.permutations(range(len(processed_vars))))
        
        # Process each permutation as a separate sequential path
        for perm in all_perms:
            branch_start = self.new_state()
            branch_current = branch_start
            
            # Build the permutation branch as a sequential chain with FRESH states
            for var_idx in perm:
                # CRITICAL: Create fresh states for this variable in this permutation
                # Do NOT reuse processed_vars states to avoid epsilon contamination
                original_var = variables[var_idx]
                fresh_var_start, fresh_var_end = self.create_var_states(original_var, define)
                
                self.add_epsilon(branch_current, fresh_var_start)
                branch_current = fresh_var_end
            
            # Connect this permutation branch to the main flow
            self.add_epsilon(perm_start, branch_start)
            self.add_epsilon(branch_current, perm_end)
        
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
        """Apply quantifier to a subpattern with improved optional handling."""
        new_start = self.new_state()
        new_end = self.new_state()
        
        # Handle {n,n} case (exactly n repetitions)
        if min_rep == max_rep and min_rep > 0:
            # Create a chain of exactly min_rep copies
            current = new_start
            for _ in range(min_rep):
                next_state = self.new_state()
                # Copy the original transition
                for trans in self.states[start].transitions:
                    self.states[current].add_transition(
                        trans.condition,
                        next_state if trans.target == end else trans.target,
                        trans.variable,
                        trans.priority,
                        trans.metadata
                    )
                current = next_state
            # Connect the last state to new_end
            self.add_epsilon(current, new_end)
            return new_start, new_end
        
        # Handle different quantifier types
        if min_rep == 0 and max_rep is None:  # *
            # Allow empty matches
            self.add_epsilon(new_start, new_end)
            
            if greedy:
                # Try to match (greedy)
                self.add_epsilon(new_start, start)
                self.add_epsilon(end, start)  # Loop back
                self.add_epsilon(end, new_end)  # Or finish
            else:
                # Try to skip (reluctant)
                self.add_epsilon(new_start, new_end)  # Skip first
                self.add_epsilon(new_start, start)    # Or try to match
                self.add_epsilon(end, new_end)        # Finish after match
                self.add_epsilon(end, start)          # Or loop back
            
        elif min_rep == 1 and max_rep is None:  # +
            self.add_epsilon(new_start, start)  # Must match once
            
            if greedy:
                # Try to match more (greedy)
                self.add_epsilon(end, start)  # Loop back
                self.add_epsilon(end, new_end)  # Or finish
            else:
                # Try to finish (reluctant)
                self.add_epsilon(end, new_end)  # Finish
                self.add_epsilon(end, start)  # Or loop back
            
        elif min_rep == 0 and max_rep == 1:  # ?
            # Must have this for optional elements (var?)
            if greedy:
                # Try to match (greedy)
                self.add_epsilon(new_start, start)    # Try to match
                self.add_epsilon(new_start, new_end)  # Or skip
                self.add_epsilon(end, new_end)        # End after match
            else:
                # Try to skip (reluctant)
                self.add_epsilon(new_start, new_end)  # Skip first
                self.add_epsilon(new_start, start)    # Or try to match
                self.add_epsilon(end, new_end)        # End after match
            
        else:  # {m,n} bounds
            # Create chain for minimum repetitions
            current = new_start
            
            # Handle empty match case for {0,n}
            if min_rep == 0:
                # Direct path for empty match
                self.add_epsilon(new_start, new_end)
            
            # Create states for minimum required repetitions
            prev_end = None
            for i in range(min_rep):
                rep_start = self.new_state()
                rep_end = self.new_state()
                
                # Connect to previous state
                self.add_epsilon(current, rep_start)
                
                # Copy transitions from original pattern
                for trans in self.states[start].transitions:
                    self.states[rep_start].add_transition(
                        trans.condition,
                        rep_end if trans.target == end else trans.target,
                        trans.variable,
                        trans.priority,
                        trans.metadata
                    )
                
                current = rep_end
                if i == min_rep - 1:
                    prev_end = rep_end
            
            # Add optional repetitions up to max
            if max_rep is not None and max_rep > min_rep:
                # Create states for optional repetitions
                for i in range(min_rep, max_rep):
                    opt_start = self.new_state()
                    opt_end = self.new_state()
                    
                    # Connect based on greediness
                    if greedy:
                        # Try to match more (greedy)
                        self.add_epsilon(current, opt_start)  # Try another repetition
                        self.add_epsilon(current, new_end)    # Or finish
                    else:
                        # Try to finish (reluctant)
                        self.add_epsilon(current, new_end)    # Try to finish
                        self.add_epsilon(current, opt_start)  # Or match more
                    
                    # Copy transitions from original pattern
                    for trans in self.states[start].transitions:
                        self.states[opt_start].add_transition(
                            trans.condition,
                            opt_end if trans.target == end else trans.target,
                            trans.variable,
                            trans.priority,
                            trans.metadata
                        )
                    
                    current = opt_end
                
                # Connect final state
                self.add_epsilon(current, new_end)
            elif max_rep is None and min_rep > 0:
                # Unbounded upper limit {m,}
                # Connect to allow more repetitions or finish
                if greedy:
                    self.add_epsilon(current, start)   # Try more repetitions
                    self.add_epsilon(current, new_end) # Or finish
                else:
                    self.add_epsilon(current, new_end) # Try to finish
                    self.add_epsilon(current, start)   # Or more repetitions
            else:
                # Exact number of repetitions {m,m}
                self.add_epsilon(current, new_end)
        
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