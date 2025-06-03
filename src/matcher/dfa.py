# enhanced/dfa.py

from typing import List, Dict, FrozenSet, Set, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from src.matcher.automata import NFA, NFAState, Transition, NFABuilder
from src.matcher.pattern_tokenizer import PatternTokenType, PermuteHandler

FAIL_STATE = -1

@dataclass
class DFAState:
    """
    Enhanced DFA state with comprehensive pattern matching support.
    
    Attributes:
        nfa_states: Set of NFA states represented by this DFA state
        is_accept: Whether this is an accepting state
        transitions: List of transitions from this state
        variables: Set of pattern variables associated with this state
        excluded_variables: Set of variables marked for exclusion
        is_anchor: Whether this state represents an anchor (^ or $)
        anchor_type: Type of anchor (START or END)
        is_empty_match: Whether this state allows empty matches
        permute_data: Optional metadata for PERMUTE patterns
        subset_vars: Set of subset variables defined for this state
    """
    nfa_states: FrozenSet[int]
    is_accept: bool = False
    transitions: List[Transition] = field(default_factory=list)
    variables: Set[str] = field(default_factory=set)
    excluded_variables: Set[str] = field(default_factory=set)
    is_anchor: bool = False
    anchor_type: Optional[PatternTokenType] = None
    is_empty_match: bool = False
    permute_data: Optional[Dict[str, Any]] = None
    subset_vars: Set[str] = field(default_factory=set)

    def add_transition(self, condition: Any, target: int, variable: Optional[str] = None):
        """Add a transition with enhanced validation."""
        # Allow transitions for excluded variables - they should be available for matching
        # but will be filtered from output during result processing
        self.transitions.append(Transition(condition, target, variable))

    def allows_empty_match(self) -> bool:
        """Check if this state allows empty matches."""
        return self.is_empty_match or (self.is_accept and not self.transitions)

@dataclass
class DFA:
    """
    Enhanced DFA implementation for pattern matching.
    
    Attributes:
        start: Start state index
        states: List of DFA states
        exclusion_ranges: Ranges of excluded pattern components
        metadata: Additional pattern metadata
    """
    start: int
    states: List[DFAState]
    exclusion_ranges: List[Tuple[int, int]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate_pattern(self) -> bool:
        """
        Validate pattern structure and constraints.
        
        Returns:
            bool: True if pattern is valid, False otherwise
        """
        # Check for infinite loops in skip patterns
        if self.metadata.get('skip_to_first'):
            skip_var = self.metadata['skip_to_first']
            if skip_var in self.get_first_variables():
                return False

        # Validate anchor constraints
        has_start_anchor = any(s.is_anchor and s.anchor_type == PatternTokenType.ANCHOR_START 
                             for s in self.states)
        has_end_anchor = any(s.is_anchor and s.anchor_type == PatternTokenType.ANCHOR_END 
                           for s in self.states)

        if has_start_anchor and has_end_anchor:
            self.metadata['spans_partition'] = True

        # Validate exclusions with unmatched rows
        if self.metadata.get('with_unmatched') and self.exclusion_ranges:
            return False

        return True

    def get_first_variables(self) -> Set[str]:
        """Get variables that can match first in pattern."""
        first_vars = set()
        visited = {self.start}
        queue = [self.start]

        while queue:
            state_idx = queue.pop(0)
            state = self.states[state_idx]

            # Add variables from this state
            first_vars.update(state.variables)

            # Follow epsilon transitions
            for trans in state.transitions:
                if trans.target not in visited:
                    visited.add(trans.target)
                    queue.append(trans.target)

                    # If we reach an accepting state, stop following this path
                    if self.states[trans.target].is_accept:
                        break

        return first_vars

    def optimize(self):
        """Apply optimizations to the DFA."""
        self._remove_unreachable_states()
        self._merge_equivalent_states()
        self._optimize_transitions()

    def _remove_unreachable_states(self):
        """Remove states that cannot be reached from start state."""
        reachable = set()
        queue = [self.start]

        while queue:
            state_idx = queue.pop(0)
            if state_idx not in reachable:
                reachable.add(state_idx)
                for trans in self.states[state_idx].transitions:
                    queue.append(trans.target)

        # Keep only reachable states
        new_states = []
        state_map = {}
        for idx in sorted(reachable):
            state_map[idx] = len(new_states)
            new_states.append(self.states[idx])

        # Update transitions
        for state in new_states:
            for trans in state.transitions:
                trans.target = state_map[trans.target]

        self.states = new_states

    def _merge_equivalent_states(self):
        """Merge states that are functionally equivalent."""
        while True:
            merged = False
            for i in range(len(self.states)):
                for j in range(i + 1, len(self.states)):
                    if self._are_equivalent(i, j):
                        self._merge_states(i, j)
                        merged = True
                        break
                if merged:
                    break
            if not merged:
                break

    def _are_equivalent(self, state1: int, state2: int) -> bool:
        """Check if two states are equivalent."""
        s1, s2 = self.states[state1], self.states[state2]
        
        # States must have same acceptance, variables, and anchors
        if (s1.is_accept != s2.is_accept or
            s1.variables != s2.variables or
            s1.is_anchor != s2.is_anchor or
            s1.anchor_type != s2.anchor_type):
            return False

        # Must have same number of transitions
        if len(s1.transitions) != len(s2.transitions):
            return False

        # Check transitions
        for t1 in s1.transitions:
            found_match = False
            for t2 in s2.transitions:
                if (t1.variable == t2.variable and
                    t1.condition == t2.condition):
                    found_match = True
                    break
            if not found_match:
                return False

        return True

    def _merge_states(self, state1: int, state2: int):
        """Merge two equivalent states."""
        # Redirect all transitions to state2 to state1
        for state in self.states:
            for trans in state.transitions:
                if trans.target == state2:
                    trans.target = state1

        # Remove state2 and update all higher indices
        self.states.pop(state2)
        for state in self.states:
            for trans in state.transitions:
                if trans.target > state2:
                    trans.target -= 1

    def _optimize_transitions(self):
        """Optimize transitions for better performance."""
        for state in self.states:
            # Group transitions by variable
            var_transitions: Dict[str, List[Transition]] = {}
            for trans in state.transitions:
                if trans.variable not in var_transitions:
                    var_transitions[trans.variable] = []
                var_transitions[trans.variable].append(trans)

            # Combine transitions with same variable and target
            new_transitions = []
            for var_trans in var_transitions.values():
                by_target: Dict[int, List[Transition]] = {}
                for trans in var_trans:
                    if trans.target not in by_target:
                        by_target[trans.target] = []
                    by_target[trans.target].append(trans)

                # Combine conditions for same target
                for target_trans in by_target.values():
                    if len(target_trans) == 1:
                        new_transitions.append(target_trans[0])
                    else:
                        # Create combined condition
                        conditions = [t.condition for t in target_trans]
                        combined_condition = lambda row, ctx, conds=conditions: any(c(row, ctx) for c in conds)
                        new_transitions.append(Transition(
                            combined_condition,
                            target_trans[0].target,
                            target_trans[0].variable
                        ))

            state.transitions = new_transitions

class DFABuilder:
    """Enhanced DFA builder with comprehensive pattern support."""

    def __init__(self, nfa: NFA):
        self.nfa = nfa
        self.subset_cache: Dict[FrozenSet[int], int] = {}
        # Copy metadata from NFA to preserve anchor information
        self.metadata: Dict[str, Any] = nfa.metadata.copy() if hasattr(nfa, 'metadata') and nfa.metadata else {}

    def build(self) -> DFA:
        """Build optimized DFA from NFA with enhanced features."""
        dfa_states: List[DFAState] = []
        state_map: Dict[FrozenSet[int], int] = {}

        # Create initial state
        start_set = frozenset(self.nfa.epsilon_closure([self.nfa.start]))
        start_dfa = self._create_dfa_state(start_set)
        dfa_states.append(start_dfa)
        state_map[start_set] = 0

        # Process state queue
        queue = [start_set]
        while queue:
            current_set = queue.pop(0)
            current_idx = state_map[current_set]

            # Group transitions by variable for optimization
            var_transitions = self._group_transitions(current_set)

            # Process transitions
            for var, transitions in var_transitions.items():
                target_set = self._compute_target_set(transitions)
                target_idx = self._get_target_state(target_set, state_map, dfa_states, queue)
                
                # Create optimized transition
                condition = self._create_combined_condition(transitions)
                dfa_states[current_idx].add_transition(condition, target_idx, var)

        # Build final DFA
        dfa = DFA(0, dfa_states, self.nfa.exclusion_ranges, self.metadata)
        
        # Apply optimizations
        dfa.optimize()
        
        return dfa

    def _create_dfa_state(self, nfa_states: FrozenSet[int]) -> DFAState:
        """Create a DFA state from NFA states with enhanced metadata."""
        is_accept = self.nfa.accept in nfa_states
        state = DFAState(nfa_states, is_accept)

        # Process state properties
        for nfa_state in nfa_states:
            nfa_info = self.nfa.states[nfa_state]

            # Copy variables
            if hasattr(nfa_info, 'variable') and nfa_info.variable:
                state.variables.add(nfa_info.variable)
                if hasattr(nfa_info, 'is_excluded') and nfa_info.is_excluded:
                    state.excluded_variables.add(nfa_info.variable)

            # Copy anchor information
            if hasattr(nfa_info, 'is_anchor') and nfa_info.is_anchor:
                state.is_anchor = True
                state.anchor_type = nfa_info.anchor_type

            # Handle subset variables
            if hasattr(nfa_info, 'subset_vars'):
                state.subset_vars.update(nfa_info.subset_vars)

            # Handle PERMUTE metadata
            if hasattr(nfa_info, 'permute_data'):
                if state.permute_data is None:
                    state.permute_data = {}
                state.permute_data.update(nfa_info.permute_data)

        return state

    def _group_transitions(self, nfa_states: FrozenSet[int]) -> Dict[str, List[Transition]]:
        """Group NFA transitions by variable for optimization."""
        transitions: Dict[str, List[Transition]] = {}
        
        for state_idx in nfa_states:
            for trans in self.nfa.states[state_idx].transitions:
                if trans.variable not in transitions:
                    transitions[trans.variable] = []
                transitions[trans.variable].append(trans)
                
        return transitions

    def _compute_target_set(self, transitions: List[Transition]) -> FrozenSet[int]:
        """Compute target state set for transitions."""
        target_states = set()
        for trans in transitions:
            target_states.update(self.nfa.epsilon_closure([trans.target]))
        return frozenset(target_states)

    def _get_target_state(
        self,
        target_set: FrozenSet[int],
        state_map: Dict[FrozenSet[int], int],
        dfa_states: List[DFAState],
        queue: List[FrozenSet[int]]
    ) -> int:
        """Get or create target DFA state."""
        if target_set in state_map:
            return state_map[target_set]

        # Create new state
        target_idx = len(dfa_states)
        state_map[target_set] = target_idx
        dfa_states.append(self._create_dfa_state(target_set))
        queue.append(target_set)

        return target_idx

    def _create_combined_condition(self, transitions: List[Transition]) -> Any:
        """Create optimized combined condition function."""
        conditions = [t.condition for t in transitions]
        return lambda row, ctx: any(c(row, ctx) for c in conditions)