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
        # Mark as accepting if the NFA accept state is in the closure
        start_is_accept = self.nfa.accept in start_set
        
        # Debug output for empty match detection
        if start_is_accept:
            print(f"Start state is accepting - pattern allows empty matches")
            
        start_dfa = DFAState(start_set, start_is_accept)
        
        # Add variables and anchors from NFA states
        for nfa_state in start_set:
            if hasattr(self.nfa.states[nfa_state], 'variable') and self.nfa.states[nfa_state].variable:
                start_dfa.variables.add(self.nfa.states[nfa_state].variable)
            
            # ... rest of variables and anchors copying
        
        dfa_states.append(start_dfa)
        state_map[start_set] = 0
        
        # Process states queue - unchanged
        # ...
        
        return DFA(0, dfa_states, self.nfa.exclusion_ranges)
