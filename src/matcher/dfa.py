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
        """Build DFA from NFA using subset construction algorithm with detailed debugging."""
        dfa_states: List[DFAState] = []
        state_map: Dict[FrozenSet[int], int] = {}
        
        # Create initial state from NFA start state epsilon closure
        start_set = frozenset(self.nfa.epsilon_closure([self.nfa.start]))
        
        # Check if this is an empty pattern (start state directly goes to accept state)
        is_empty_pattern = len(start_set) == 2 and self.nfa.accept in start_set
        
        # Mark as accepting if the NFA accept state is in the closure
        start_is_accept = self.nfa.accept in start_set
        
        if start_is_accept:
            print(f"Start state is accepting - pattern allows empty matches")
                
        start_dfa = DFAState(start_set, start_is_accept)
        
        # Add variables and anchors from NFA states
        for nfa_state in start_set:
            if hasattr(self.nfa.states[nfa_state], 'variable') and self.nfa.states[nfa_state].variable:
                start_dfa.variables.add(self.nfa.states[nfa_state].variable)
            
            # Copy anchor information
            if hasattr(self.nfa.states[nfa_state], 'is_anchor') and self.nfa.states[nfa_state].is_anchor:
                start_dfa.is_anchor = True
                start_dfa.anchor_type = self.nfa.states[nfa_state].anchor_type
            
            # Copy exclusion status
            if hasattr(self.nfa.states[nfa_state], 'is_excluded') and self.nfa.states[nfa_state].is_excluded:
                start_dfa.excluded_variables.add(self.nfa.states[nfa_state].variable)
        
        dfa_states.append(start_dfa)
        state_map[start_set] = 0
        
        # Process state queue
        queue = [start_set]
        while queue:
            current_set = queue.pop(0)
            current_idx = state_map[current_set]
            
            # Group NFA states by variable
            var_transitions = {}
            for nfa_state in current_set:
                for trans in self.nfa.states[nfa_state].transitions:
                    if trans.variable not in var_transitions:
                        var_transitions[trans.variable] = []
                    var_transitions[trans.variable].append(trans)
            
            # Debug transitions
            print(f"DFA state {current_idx} has transitions for variables: {list(var_transitions.keys())}")
            
            # For each variable, create a DFA transition
            for var, transitions in var_transitions.items():
                # Create a transition function that combines all conditions using closure to avoid late binding issues
                def make_condition(transitions_list):
                    return lambda row, ctx: any(t.condition(row, ctx) for t in transitions_list)
                
                combined_condition = make_condition(transitions)
                
                # Find target states via epsilon closure
                target_states = set()
                for trans in transitions:
                    target_states.update(self.nfa.epsilon_closure([trans.target]))
                
                target_set = frozenset(target_states)
                
                # Create or get the target DFA state
                if target_set not in state_map:
                    # Check if accepting
                    is_accept = self.nfa.accept in target_set
                    
                    # Create new state
                    target_idx = len(dfa_states)
                    state_map[target_set] = target_idx
                    
                    target_dfa = DFAState(target_set, is_accept)
                    
                    # Copy variables and anchors from NFA states
                    for nfa_state in target_set:
                        if hasattr(self.nfa.states[nfa_state], 'variable') and self.nfa.states[nfa_state].variable:
                            target_dfa.variables.add(self.nfa.states[nfa_state].variable)
                        
                        # Copy anchor information
                        if hasattr(self.nfa.states[nfa_state], 'is_anchor') and self.nfa.states[nfa_state].is_anchor:
                            target_dfa.is_anchor = True
                            target_dfa.anchor_type = self.nfa.states[nfa_state].anchor_type
                        
                        # Copy exclusion information
                        if hasattr(self.nfa.states[nfa_state], 'is_excluded') and self.nfa.states[nfa_state].is_excluded:
                            target_dfa.excluded_variables.add(self.nfa.states[nfa_state].variable)
                    
                    dfa_states.append(target_dfa)
                    queue.append(target_set)
                else:
                    target_idx = state_map[target_set]
                
                # Add the transition to the DFA
                dfa_states[current_idx].transitions.append(Transition(combined_condition, target_idx, var))
                print(f"  Added transition from state {current_idx} to {target_idx} for variable {var}")
        
        # Print summary of DFA construction
        print(f"Built DFA with {len(dfa_states)} states")
        for i, state in enumerate(dfa_states):
            transitions_str = ", ".join([f"{t.variable} → {t.target}" for t in state.transitions])
            acceptance_str = "Accept" if state.is_accept else "Non-accept"
            vars_str = ", ".join(state.variables) if state.variables else "None"
            print(f"  State {i}: {acceptance_str}, Variables: {vars_str}, Transitions: {transitions_str}")
        
        return DFA(0, dfa_states, self.nfa.exclusion_ranges)
