# src/matcher/dfa.py

from typing import List, Dict, FrozenSet, Set, Any, Optional
from collections import deque
from src.matcher.automata import NFA, NFAState, Transition

FAIL_STATE = -1

class DFAState:
    def __init__(self, nfa_states: FrozenSet[int], is_accept: bool = False):
        self.nfa_states = nfa_states
        self.is_accept = is_accept
        self.transitions: List[Transition] = []
        self.variables: Set[str] = set()
        self.excluded_variables: Set[str] = set()
        self.is_anchor: bool = False
        self.anchor_type = None

class DFA:
    def __init__(self, start: int, states: List[DFAState], exclusion_ranges: List = None):
        self.start = start
        self.states = states
        self.exclusion_ranges = exclusion_ranges or []

class DFABuilder:
    def __init__(self, nfa: NFA):
        self.nfa = nfa
        
    def build(self) -> DFA:
        """Build DFA from NFA using subset construction algorithm."""
        dfa_states: List[DFAState] = []
        state_map: Dict[FrozenSet[int], int] = {}
        
        # Create initial state from NFA start state epsilon closure
        start_set = frozenset(self.nfa.epsilon_closure([self.nfa.start]))
        start_is_accept = self.nfa.accept in start_set
        start_dfa = DFAState(start_set, start_is_accept)
        
        # Add variables and anchors from NFA states
        for nfa_state in start_set:
            if hasattr(self.nfa.states[nfa_state], 'variable') and self.nfa.states[nfa_state].variable:
                start_dfa.variables.add(self.nfa.states[nfa_state].variable)
            
            # Check for excluded variables
            if hasattr(self.nfa.states[nfa_state], 'is_excluded') and self.nfa.states[nfa_state].is_excluded:
                if hasattr(self.nfa.states[nfa_state], 'variable') and self.nfa.states[nfa_state].variable:
                    start_dfa.excluded_variables.add(self.nfa.states[nfa_state].variable)
            
            # Check for anchors
            if hasattr(self.nfa.states[nfa_state], 'is_anchor') and self.nfa.states[nfa_state].is_anchor:
                start_dfa.is_anchor = True
                start_dfa.anchor_type = self.nfa.states[nfa_state].anchor_type
        
        dfa_states.append(start_dfa)
        state_map[start_set] = 0
        
        # Process states queue
        queue = deque([0])
        while queue:
            current_idx = queue.popleft()
            current = dfa_states[current_idx]
            
            # Get all possible transitions from current NFA states
            for nfa_state in current.nfa_states:
                for trans in self.nfa.states[nfa_state].transitions:
                    condition = trans.condition
                    target = trans.target
                    variable = trans.variable
                    
                    # Get epsilon closure of target
                    target_closure = frozenset(self.nfa.epsilon_closure([target]))
                    
                    # Create or get DFA state for target closure
                    if target_closure not in state_map:
                        is_accept = self.nfa.accept in target_closure
                        new_state = DFAState(target_closure, is_accept)
                        
                        # Add variables from NFA states
                        for ns in target_closure:
                            if hasattr(self.nfa.states[ns], 'variable') and self.nfa.states[ns].variable:
                                new_state.variables.add(self.nfa.states[ns].variable)
                            
                            # Check for excluded variables
                            if hasattr(self.nfa.states[ns], 'is_excluded') and self.nfa.states[ns].is_excluded:
                                if hasattr(self.nfa.states[ns], 'variable') and self.nfa.states[ns].variable:
                                    new_state.excluded_variables.add(self.nfa.states[ns].variable)
                            
                            # Check for anchors
                            if hasattr(self.nfa.states[ns], 'is_anchor') and self.nfa.states[ns].is_anchor:
                                new_state.is_anchor = True
                                new_state.anchor_type = self.nfa.states[ns].anchor_type
                        
                        dfa_states.append(new_state)
                        new_idx = len(dfa_states) - 1
                        state_map[target_closure] = new_idx
                        queue.append(new_idx)
                    
                    target_idx = state_map[target_closure]
                    
                    # Add transition
                    current.transitions.append(Transition(condition, target_idx, variable))
        
        return DFA(0, dfa_states, self.nfa.exclusion_ranges)
