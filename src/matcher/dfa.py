"""
Production-ready DFA module for SQL:2016 row pattern matching.

This module implements Deterministic Finite Automata (DFA) with comprehensive
support for complex pattern constructs. Built from NFA using subset construction
with advanced optimizations for performance and correctness.

Features:
- Efficient subset construction from NFA
- Comprehensive metadata propagation
- Advanced optimization techniques
- Thread-safe operations
- Robust error handling and validation
- Performance monitoring and debugging

Author: Pattern Matching Engine Team
Version: 2.0.0
"""

from typing import (
    List, Dict, FrozenSet, Set, Any, Optional, Tuple, Union,
    Callable, Iterator, Protocol
)
from dataclasses import dataclass, field
import time
import threading
from collections import defaultdict, deque
from abc import ABC, abstractmethod

from src.matcher.automata import NFA, NFAState, Transition, NFABuilder
from src.matcher.pattern_tokenizer import PatternTokenType, PermuteHandler
from src.utils.logging_config import get_logger, PerformanceTimer

# Module logger
logger = get_logger(__name__)

# Constants
FAIL_STATE = -1
MAX_OPTIMIZATION_ITERATIONS = 100

@dataclass
class DFAState:
    """
    Production-ready DFA state with comprehensive pattern matching support.
    
    This class represents a deterministic state constructed from a set of NFA states
    using subset construction. Includes comprehensive metadata tracking and validation.
    
    Attributes:
        nfa_states: Frozen set of NFA states represented by this DFA state
        is_accept: Whether this is an accepting state
        transitions: List of transitions from this state
        variables: Set of pattern variables associated with this state
        excluded_variables: Set of variables marked for exclusion
        is_anchor: Whether this state represents an anchor (^ or $)
        anchor_type: Type of anchor (START or END)
        is_empty_match: Whether this state allows empty matches
        permute_data: Optional metadata for PERMUTE patterns
        subset_vars: Set of subset variables defined for this state
        priority: Priority for state ordering in ambiguous cases
        state_id: Optional identifier for debugging
        
    Thread Safety:
        This class is thread-safe for read operations. Modifications should be
        synchronized externally if used across multiple threads.
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
    priority: int = 0
    state_id: Optional[int] = None
    
    def __post_init__(self):
        """Initialize additional state attributes and validation."""
        if not self.nfa_states:
            raise ValueError("DFA state must represent at least one NFA state")
        
        # Threading support
        self._lock = threading.RLock()
        self._validated = False
        
        # Optimization metadata
        self.creation_time = time.time()
        self.access_count = 0
        
        # Validate on creation
        if not self.validate():
            raise ValueError("DFA state validation failed")

    def add_transition(self, condition: Any, target: int, variable: Optional[str] = None, 
                      priority: int = 0, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a transition with enhanced validation and priority support.
        
        Args:
            condition: Condition function for the transition
            target: Target state index
            variable: Optional variable name (allows excluded variables)
            priority: Priority for transition ordering
            metadata: Additional transition metadata
            
        Raises:
            ValueError: If parameters are invalid
        """
        with self._lock:
            # Allow transitions for excluded variables - they should be available for matching
            # but will be filtered from output during result processing
            transition = Transition(
                condition=condition,
                target=target,
                variable=variable,
                priority=priority,
                metadata=metadata or {}
            )
            
            # Check for duplicate transitions
            existing = [t for t in self.transitions 
                       if t.target == target and t.variable == variable]
            if existing:
                logger.warning(f"Duplicate transition to state {target} with variable '{variable}'")
            
            self.transitions.append(transition)
            self.access_count += 1
            self._validated = False
            
            logger.debug(f"DFA state {self.state_id}: added transition to {target}, variable='{variable}'")

    def allows_empty_match(self) -> bool:
        """
        Check if this state allows empty matches with comprehensive logic.
        
        Returns:
            bool: True if this state allows empty matches
        """
        # Accept states with no outgoing transitions allow empty matches
        if self.is_accept and not self.transitions:
            return True
        
        # Explicitly marked empty match states
        if self.is_empty_match:
            return True
        
        # PERMUTE states may allow empty matches in certain conditions
        if self.permute_data and self.permute_data.get('allows_empty', False):
            return True
        
        return False
    
    def get_variables_by_priority(self) -> List[str]:
        """
        Get variables associated with this state sorted by priority.
        
        Returns:
            List[str]: Variables sorted by priority (excluded variables marked)
        """
        all_vars = list(self.variables.union(self.excluded_variables))
        
        # Sort by priority (excluded variables get higher priority numbers)
        def var_priority(var):
            base_priority = 0
            if var in self.excluded_variables:
                base_priority = 1000  # Lower priority for excluded vars
            return (base_priority, var)  # Secondary sort by name for determinism
        
        return sorted(all_vars, key=var_priority)
    
    def has_variable(self, variable: str) -> bool:
        """
        Check if this state has a specific variable (including excluded).
        
        Args:
            variable: Variable name to check
            
        Returns:
            bool: True if variable is present
        """
        return variable in self.variables or variable in self.excluded_variables
    
    def is_variable_excluded(self, variable: str) -> bool:
        """
        Check if a variable is marked as excluded in this state.
        
        Args:
            variable: Variable name to check
            
        Returns:
            bool: True if variable is excluded
        """
        return variable in self.excluded_variables
    
    def get_transitions_for_variable(self, variable: str) -> List[Transition]:
        """
        Get all transitions associated with a specific variable.
        
        Args:
            variable: Variable name to filter by
            
        Returns:
            List[Transition]: Transitions for the variable
        """
        with self._lock:
            return [t for t in self.transitions if t.variable == variable]
    
    def optimize_transitions(self) -> None:
        """
        Optimize transitions by removing duplicates and sorting by priority.
        """
        with self._lock:
            if not self.transitions:
                return
            
            # Remove duplicate transitions (same target, variable, priority)
            seen = set()
            unique_transitions = []
            
            for trans in self.transitions:
                key = (trans.target, trans.variable, trans.priority)
                if key not in seen:
                    seen.add(key)
                    unique_transitions.append(trans)
                else:
                    logger.debug(f"DFA state {self.state_id}: removed duplicate transition {key}")
            
            # Sort by priority, then by target, then by variable for determinism
            self.transitions = sorted(unique_transitions, key=lambda t: (
                t.priority,
                t.target,
                t.variable or ""
            ))
            
            self._validated = False
    
    def validate(self) -> bool:
        """
        Comprehensive validation of DFA state structure and constraints.
        
        Returns:
            bool: True if state is valid, False otherwise
        """
        with self._lock:
            if self._validated:
                return True
            
            try:
                # Validate NFA states
                if not self.nfa_states:
                    logger.error(f"DFA state {self.state_id} has no NFA states")
                    return False
                
                # Validate variables
                for var in self.variables.union(self.excluded_variables):
                    if not var or not isinstance(var, str):
                        logger.error(f"DFA state {self.state_id} has invalid variable: '{var}'")
                        return False
                
                # Validate anchor constraints
                if self.is_anchor and not self.anchor_type:
                    logger.error(f"DFA state {self.state_id} is anchor but missing anchor_type")
                    return False
                
                # Validate transitions
                for i, trans in enumerate(self.transitions):
                    if trans.target < 0:
                        logger.error(f"DFA state {self.state_id} transition {i} has negative target")
                        return False
                
                # Validate PERMUTE data consistency
                if self.permute_data:
                    required_keys = {'variables', 'combinations'}
                    if not all(key in self.permute_data for key in required_keys):
                        logger.warning(f"DFA state {self.state_id} has incomplete PERMUTE data")
                
                self._validated = True
                return True
                
            except Exception as e:
                logger.error(f"DFA state {self.state_id} validation failed: {e}")
                return False
    
    def get_debug_info(self) -> Dict[str, Any]:
        """
        Get comprehensive debug information about this DFA state.
        
        Returns:
            Dict[str, Any]: Debug information including structure and metadata
        """
        with self._lock:
            return {
                'state_id': self.state_id,
                'nfa_states': sorted(list(self.nfa_states)),
                'is_accept': self.is_accept,
                'is_anchor': self.is_anchor,
                'anchor_type': self.anchor_type.name if self.anchor_type else None,
                'is_empty_match': self.is_empty_match,
                'variables': sorted(list(self.variables)),
                'excluded_variables': sorted(list(self.excluded_variables)),
                'subset_vars': sorted(list(self.subset_vars)),
                'priority': self.priority,
                'transition_count': len(self.transitions),
                'permute_data': dict(self.permute_data) if self.permute_data else None,
                'creation_time': self.creation_time,
                'access_count': self.access_count,
                'validated': self._validated,
                'transitions': [
                    {
                        'target': t.target,
                        'variable': t.variable,
                        'priority': t.priority,
                        'metadata_keys': list(t.metadata.keys())
                    } for t in self.transitions
                ]
            }

@dataclass
class DFA:
    """
    Production-ready Deterministic Finite Automaton for SQL:2016 pattern matching.
    
    This class represents a DFA constructed from an NFA using subset construction
    with comprehensive support for complex pattern constructs and optimizations.
    
    Features:
    - Efficient subset construction from NFA
    - Comprehensive metadata propagation from NFA
    - Advanced state optimization and validation
    - Thread-safe operations with proper locking
    - Robust error handling and debugging support
    - Performance monitoring and metrics
    
    Attributes:
        start: Start state index (validated on construction)
        states: List of DFA states (optimized and validated)
        exclusion_ranges: Ranges of excluded pattern components
        metadata: Comprehensive pattern metadata including PERMUTE and alternation info
        
    Thread Safety:
        This class is thread-safe for read operations. Construction and optimization
        should be synchronized externally if used across multiple threads.
    """
    start: int
    states: List[DFAState]
    exclusion_ranges: List[Tuple[int, int]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize DFA with validation and threading support."""
        # Validate basic structure
        if not self.states:
            raise ValueError("DFA must have at least one state")
        
        if not (0 <= self.start < len(self.states)):
            raise ValueError(f"Start state index {self.start} out of range")
        
        # Threading support
        self._lock = threading.RLock()
        self._validated = False
        self._optimized = False
        
        # Performance tracking
        self.creation_time = time.time()
        self.access_count = 0
        
        # Assign state IDs if not present
        for i, state in enumerate(self.states):
            if state.state_id is None:
                state.state_id = i
        
        # Validate structure
        if not self.validate_pattern():
            raise ValueError("DFA structure validation failed")

    def validate_pattern(self) -> bool:
        """
        Comprehensive validation of DFA structure and constraints.
        
        Returns:
            bool: True if DFA is valid, False otherwise
        """
        with self._lock:
            if self._validated:
                return True
            
            try:
                # Validate each state
                for i, state in enumerate(self.states):
                    if not state.validate():
                        logger.error(f"DFA state {i} validation failed")
                        return False
                    
                    # Validate transition targets
                    for trans in state.transitions:
                        if not (0 <= trans.target < len(self.states)):
                            logger.error(f"DFA state {i} has invalid transition target {trans.target}")
                            return False
                
                # Check for infinite loops in skip patterns
                if self.metadata.get('skip_to_first'):
                    skip_var = self.metadata['skip_to_first']
                    if skip_var in self.get_first_variables():
                        logger.error(f"Infinite loop detected: skip to first variable '{skip_var}' that can match first")
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
                    logger.warning("Exclusions with unmatched rows may cause unexpected behavior")

                # Validate PERMUTE metadata consistency
                if self.metadata.get('permute'):
                    if not self._validate_permute_metadata():
                        logger.error("PERMUTE metadata validation failed")
                        return False

                self._validated = True
                return True
                
            except Exception as e:
                logger.error(f"DFA validation failed: {e}")
                return False
    
    def _validate_permute_metadata(self) -> bool:
        """Validate PERMUTE-specific metadata."""
        try:
            if self.metadata.get('has_alternations'):
                combinations = self.metadata.get('alternation_combinations', [])
                if not combinations:
                    logger.error("PERMUTE with alternations must have non-empty combinations")
                    return False
                
                # Validate combination structure
                for combo in combinations:
                    if not isinstance(combo, (list, tuple)) or len(combo) < 2:
                        logger.error(f"Invalid alternation combination: {combo}")
                        return False
            
            permute_vars = self.metadata.get('permute_variables', [])
            if permute_vars:
                # Check that permute variables exist in some state
                all_vars = set()
                for state in self.states:
                    all_vars.update(state.variables)
                    all_vars.update(state.excluded_variables)
                
                missing_vars = set(permute_vars) - all_vars
                if missing_vars:
                    logger.warning(f"PERMUTE variables not found in any state: {missing_vars}")
            
            return True
            
        except Exception as e:
            logger.error(f"PERMUTE metadata validation error: {e}")
            return False

    def get_first_variables(self) -> Set[str]:
        """
        Get variables that can match first in the pattern.
        
        Returns:
            Set[str]: Variables that can appear at the beginning of a match
        """
        first_vars = set()
        visited = {self.start}
        queue = deque([self.start])

        while queue:
            state_idx = queue.popleft()
            state = self.states[state_idx]

            # Add variables from this state (excluding excluded ones for first match)
            first_vars.update(state.variables - state.excluded_variables)

            # Follow transitions that don't consume input (epsilon-like)
            for trans in state.transitions:
                # Only follow if this is an epsilon-like transition or allows empty match
                if (trans.variable is None or 
                    state.allows_empty_match() or
                    trans.target == state_idx):  # Self-loop
                    
                    if trans.target not in visited:
                        visited.add(trans.target)
                        queue.append(trans.target)

                    # If we reach an accepting state, we might have epsilon path to end
                    if self.states[trans.target].is_accept:
                        break

        return first_vars
    
    def get_reachable_states(self, from_state: int = None) -> Set[int]:
        """
        Get all states reachable from a given state (or start state).
        
        Args:
            from_state: Starting state index (defaults to start state)
            
        Returns:
            Set[int]: Set of reachable state indices
        """
        if from_state is None:
            from_state = self.start
        
        if not (0 <= from_state < len(self.states)):
            raise ValueError(f"Invalid from_state: {from_state}")
        
        reachable = set()
        queue = deque([from_state])

        while queue:
            state_idx = queue.popleft()
            if state_idx in reachable:
                continue
            
            reachable.add(state_idx)
            
            # Add all transition targets
            for trans in self.states[state_idx].transitions:
                if trans.target not in reachable:
                    queue.append(trans.target)

        return reachable
    
    def find_accepting_states(self) -> List[int]:
        """
        Find all accepting states in the DFA.
        
        Returns:
            List[int]: List of accepting state indices
        """
        return [i for i, state in enumerate(self.states) if state.is_accept]
    
    def has_path_to_accept(self, from_state: int = None) -> bool:
        """
        Check if there's a path from given state to any accepting state.
        
        Args:
            from_state: Starting state index (defaults to start state)
            
        Returns:
            bool: True if path to accepting state exists
        """
        if from_state is None:
            from_state = self.start
        
        reachable = self.get_reachable_states(from_state)
        accepting_states = set(self.find_accepting_states())
        
        return bool(reachable.intersection(accepting_states))

    def optimize(self) -> None:
        """
        Apply comprehensive optimizations to improve DFA performance.
        """
        with self._lock:
            if self._optimized:
                return
            
            logger.info("Optimizing DFA...")
            optimization_start = time.time()
            
            # Track optimization metrics
            original_state_count = len(self.states)
            original_transition_count = sum(len(s.transitions) for s in self.states)
            
            # Step 1: Optimize individual states
            for state in self.states:
                state.optimize_transitions()
            
            # Step 2: Remove unreachable states
            self._remove_unreachable_states()
            
            # Step 3: Merge equivalent states
            self._merge_equivalent_states()
            
            # Step 4: Optimize transition structure
            self._optimize_transitions()
            
            # Update metadata with optimization results
            optimization_time = time.time() - optimization_start
            new_state_count = len(self.states)
            new_transition_count = sum(len(s.transitions) for s in self.states)
            
            self.metadata.update({
                'optimized': True,
                'optimization_time': optimization_time,
                'original_state_count': original_state_count,
                'optimized_state_count': new_state_count,
                'original_transition_count': original_transition_count,
                'optimized_transition_count': new_transition_count,
                'optimization_savings': {
                    'states_removed': original_state_count - new_state_count,
                    'transitions_removed': original_transition_count - new_transition_count
                }
            })
            
            self._optimized = True
            self._validated = False  # Need re-validation after optimization
            
            logger.info(f"DFA optimization completed in {optimization_time:.3f}s: "
                       f"{original_state_count}→{new_state_count} states, "
                       f"{original_transition_count}→{new_transition_count} transitions")

    def _remove_unreachable_states(self) -> None:
        """Remove states that cannot be reached from start state."""
        reachable = self.get_reachable_states()
        
        if len(reachable) == len(self.states):
            return  # No unreachable states
        
        logger.info(f"Removing {len(self.states) - len(reachable)} unreachable states")
        
        # Create mapping from old to new indices
        old_to_new = {}
        new_states = []
        
        for old_idx in sorted(reachable):
            old_to_new[old_idx] = len(new_states)
            new_states.append(self.states[old_idx])
        
        # Update state references
        for state in new_states:
            # Update transition targets
            valid_transitions = []
            for trans in state.transitions:
                if trans.target in old_to_new:
                    # Create new transition with updated target
                    updated_trans = Transition(
                        condition=trans.condition,
                        target=old_to_new[trans.target],
                        variable=trans.variable,
                        priority=trans.priority,
                        metadata=trans.metadata
                    )
                    valid_transitions.append(updated_trans)
                else:
                    logger.debug(f"Removed transition to unreachable state {trans.target}")
            state.transitions = valid_transitions
        
        # Update DFA references
        self.start = old_to_new[self.start]
        self.states = new_states

    def _merge_equivalent_states(self) -> None:
        """Merge states that are functionally equivalent."""
        if len(self.states) <= 1:
            return
        
        # Find equivalent state pairs
        equivalences = []
        
        for i in range(len(self.states)):
            for j in range(i + 1, len(self.states)):
                if self._are_equivalent(i, j):
                    equivalences.append((i, j))
        
        if not equivalences:
            return
        
        logger.info(f"Merging {len(equivalences)} equivalent state pairs")
        
        # Build equivalence classes
        equiv_classes = {}
        for i, j in equivalences:
            # Find existing class or create new one
            class_id = None
            for existing_id, members in equiv_classes.items():
                if i in members or j in members:
                    class_id = existing_id
                    break
            
            if class_id is None:
                class_id = min(i, j)
                equiv_classes[class_id] = set()
            
            equiv_classes[class_id].update([i, j])
        
        # Merge states within each equivalence class
        state_mapping = {}
        states_to_remove = set()
        
        for class_id, members in equiv_classes.items():
            representative = min(members)
            state_mapping[representative] = representative
            
            for member in members:
                if member != representative:
                    state_mapping[member] = representative
                    states_to_remove.add(member)
        
        # Update transitions to point to representative states
        for state in self.states:
            updated_transitions = []
            for trans in state.transitions:
                if trans.target in state_mapping:
                    # Create new transition with updated target
                    updated_trans = Transition(
                        condition=trans.condition,
                        target=state_mapping[trans.target],
                        variable=trans.variable,
                        priority=trans.priority,
                        metadata=trans.metadata
                    )
                    updated_transitions.append(updated_trans)
                else:
                    updated_transitions.append(trans)
            state.transitions = updated_transitions
        
        # Remove merged states and update indices
        if states_to_remove:
            new_states = []
            old_to_new = {}
            
            for i, state in enumerate(self.states):
                if i not in states_to_remove:
                    old_to_new[i] = len(new_states)
                    new_states.append(state)
            
            # Final index update
            for state in new_states:
                updated_transitions = []
                for trans in state.transitions:
                    new_target = old_to_new.get(trans.target, trans.target)
                    if new_target != trans.target:
                        # Create new transition with updated target
                        updated_trans = Transition(
                            condition=trans.condition,
                            target=new_target,
                            variable=trans.variable,
                            priority=trans.priority,
                            metadata=trans.metadata
                        )
                        updated_transitions.append(updated_trans)
                    else:
                        updated_transitions.append(trans)
                state.transitions = updated_transitions
            
            self.start = old_to_new[self.start]
            self.states = new_states

    def _are_equivalent(self, state1: int, state2: int) -> bool:
        """
        Check if two states are equivalent for merging purposes.
        
        Args:
            state1: First state index
            state2: Second state index
            
        Returns:
            bool: True if states are equivalent
        """
        s1, s2 = self.states[state1], self.states[state2]
        
        # Basic equivalence checks
        if (s1.is_accept != s2.is_accept or
            s1.is_anchor != s2.is_anchor or
            s1.anchor_type != s2.anchor_type or
            s1.variables != s2.variables or
            s1.excluded_variables != s2.excluded_variables):
            return False
        
        # Check transition structure (simplified check)
        if len(s1.transitions) != len(s2.transitions):
            return False
        
        # More sophisticated equivalence checking could be added here
        # For now, we use a conservative approach
        
        return True

    def _optimize_transitions(self) -> None:
        """Optimize transition structure for better performance."""
        for state in self.states:
            if not state.transitions:
                continue
            
            # Group transitions by target for potential combination
            target_groups = defaultdict(list)
            for trans in state.transitions:
                target_groups[trans.target].append(trans)
            
            # Look for optimization opportunities
            optimized_transitions = []
            
            for target, trans_list in target_groups.items():
                if len(trans_list) == 1:
                    optimized_transitions.extend(trans_list)
                else:
                    # Multiple transitions to same target - could be optimized
                    # For now, keep all transitions but sort by priority
                    trans_list.sort(key=lambda t: (t.priority, t.variable or ""))
                    optimized_transitions.extend(trans_list)
            
            state.transitions = optimized_transitions
    
    def get_transition_graph(self) -> Dict[int, List[Tuple[int, str]]]:
        """
        Get a simplified transition graph for visualization/debugging.
        
        Returns:
            Dict mapping state indices to list of (target, variable) tuples
        """
        graph = {}
        
        for i, state in enumerate(self.states):
            graph[i] = []
            for trans in state.transitions:
                graph[i].append((trans.target, trans.variable or "ε"))
        
        return graph
    
    def get_debug_info(self) -> Dict[str, Any]:
        """
        Get comprehensive debug information about the DFA.
        
        Returns:
            Dict[str, Any]: Debug information including structure, metadata, and statistics
        """
        with self._lock:
            accepting_states = self.find_accepting_states()
            reachable_states = self.get_reachable_states()
            
            return {
                'structure': {
                    'start': self.start,
                    'state_count': len(self.states),
                    'accepting_states': accepting_states,
                    'reachable_states': sorted(list(reachable_states)),
                    'validated': self._validated,
                    'optimized': self._optimized
                },
                'metadata': dict(self.metadata),
                'exclusion_ranges': list(self.exclusion_ranges),
                'statistics': {
                    'total_transitions': sum(len(s.transitions) for s in self.states),
                    'variable_states_count': len([s for s in self.states if s.variables]),
                    'anchor_states_count': len([s for s in self.states if s.is_anchor]),
                    'has_path_to_accept': self.has_path_to_accept(),
                    'creation_time': self.creation_time,
                    'access_count': self.access_count
                },
                'transition_graph': self.get_transition_graph(),
                'states': [state.get_debug_info() for state in self.states]
            }
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
            updated_transitions = []
            for trans in state.transitions:
                if trans.target == state2:
                    # Create new transition with updated target
                    updated_trans = Transition(
                        condition=trans.condition,
                        target=state1,
                        variable=trans.variable,
                        priority=trans.priority,
                        metadata=trans.metadata
                    )
                    updated_transitions.append(updated_trans)
                else:
                    updated_transitions.append(trans)
            state.transitions = updated_transitions

        # Remove state2 and update all higher indices
        self.states.pop(state2)
        for state in self.states:
            updated_transitions = []
            for trans in state.transitions:
                new_target = trans.target - 1 if trans.target > state2 else trans.target
                if new_target != trans.target:
                    # Create new transition with updated target
                    updated_trans = Transition(
                        condition=trans.condition,
                        target=new_target,
                        variable=trans.variable,
                        priority=trans.priority,
                        metadata=trans.metadata
                    )
                    updated_transitions.append(updated_trans)
                else:
                    updated_transitions.append(trans)
            state.transitions = updated_transitions

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
    """
    Production-ready DFA builder with comprehensive pattern support and optimizations.
    
    This class implements subset construction algorithm to convert NFA to DFA with
    comprehensive support for complex pattern constructs and advanced optimizations.
    
    Features:
    - Efficient subset construction with caching
    - Comprehensive metadata propagation from NFA
    - Priority-based transition ordering
    - Advanced state optimization techniques
    - Robust error handling and validation
    - Performance monitoring and debugging
    
    Thread Safety:
        This class is thread-safe. Multiple threads can safely build DFAs
        from different NFAs simultaneously.
    """

    def __init__(self, nfa: NFA):
        """
        Initialize DFA builder with comprehensive validation.
        
        Args:
            nfa: Source NFA to convert to DFA
            
        Raises:
            ValueError: If NFA is invalid or malformed
            TypeError: If NFA is not of correct type
        """
        if not isinstance(nfa, NFA):
            raise TypeError(f"Expected NFA instance, got {type(nfa)}")
        
        if not nfa.validate():
            raise ValueError("Source NFA failed validation")
        
        self.nfa = nfa
        self.subset_cache: Dict[FrozenSet[int], int] = {}
        
        # Copy and enhance metadata from NFA
        self.metadata: Dict[str, Any] = nfa.metadata.copy() if nfa.metadata else {}
        
        # Add builder-specific metadata
        self.metadata.update({
            'builder_version': '2.0.0',
            'source_nfa_states': len(nfa.states),
            'build_timestamp': time.time()
        })
        
        # Performance tracking
        self.build_stats = {
            'states_created': 0,
            'transitions_created': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'build_time': 0.0
        }
        
        # Threading support
        self._lock = threading.RLock()
        
        logger.debug(f"DFABuilder initialized for NFA with {len(nfa.states)} states")

    def build(self) -> DFA:
        """
        Build optimized DFA from NFA with comprehensive error handling and monitoring.
        
        Returns:
            DFA: Optimized deterministic finite automaton
            
        Raises:
            RuntimeError: If DFA construction fails
            ValueError: If resulting DFA is invalid
        """
        build_start = time.time()
        
        try:
            with PerformanceTimer("dfa_build"):
                logger.info("Starting DFA construction from NFA")
                
                # Initialize data structures
                dfa_states: List[DFAState] = []
                state_map: Dict[FrozenSet[int], int] = {}
                
                # Create initial state from epsilon closure of NFA start state
                start_closure = self.nfa.epsilon_closure([self.nfa.start])
                start_set = frozenset(start_closure)
                
                logger.debug(f"Start state epsilon closure: {sorted(start_closure)}")
                
                start_dfa = self._create_dfa_state(start_set)
                dfa_states.append(start_dfa)
                state_map[start_set] = 0
                self.build_stats['states_created'] += 1

                # Process state queue using breadth-first approach
                queue = deque([start_set])
                processed_states = set()
                
                while queue:
                    current_set = queue.popleft()
                    
                    # Skip if already processed (shouldn't happen but safety check)
                    if current_set in processed_states:
                        continue
                    processed_states.add(current_set)
                    
                    current_idx = state_map[current_set]
                    current_dfa_state = dfa_states[current_idx]

                    # Group transitions by variable for optimization
                    var_transitions = self._group_transitions(current_set)

                    # Process each variable's transitions
                    for var, transitions in var_transitions.items():
                        try:
                            target_set = self._compute_target_set(transitions)
                            
                            if not target_set:
                                continue  # Skip empty target sets
                            
                            target_idx = self._get_target_state(target_set, state_map, dfa_states, queue)
                            
                            # Create optimized transition with metadata
                            condition = self._create_combined_condition(transitions)
                            priority = self._compute_combined_priority(transitions)
                            metadata = self._create_combined_metadata(transitions)
                            
                            current_dfa_state.add_transition(
                                condition=condition,
                                target=target_idx,
                                variable=var,
                                priority=priority,
                                metadata=metadata
                            )
                            
                            self.build_stats['transitions_created'] += 1
                            
                        except Exception as e:
                            logger.error(f"Error processing transitions for variable '{var}': {e}")
                            raise RuntimeError(f"Transition processing failed: {e}") from e

                # Record build time
                self.build_stats['build_time'] = time.time() - build_start

                # Build final DFA with comprehensive metadata
                final_metadata = self._create_final_metadata()
                
                dfa = DFA(
                    start=0,
                    states=dfa_states,
                    exclusion_ranges=self.nfa.exclusion_ranges.copy(),
                    metadata=final_metadata
                )
                
                # Validate resulting DFA
                if not dfa.validate_pattern():
                    raise ValueError("Constructed DFA failed validation")
                
                # Apply optimizations
                logger.info("Applying DFA optimizations...")
                dfa.optimize()
                
                logger.info(f"DFA construction completed: {len(dfa_states)} states, "
                           f"{self.build_stats['transitions_created']} transitions, "
                           f"{self.build_stats['build_time']:.3f}s")
                
                return dfa
                
        except Exception as e:
            logger.error(f"DFA construction failed: {e}")
            raise RuntimeError(f"DFA build failed: {e}") from e

    def _create_dfa_state(self, nfa_states: FrozenSet[int]) -> DFAState:
        """
        Create a DFA state from NFA states with comprehensive metadata handling.
        
        Args:
            nfa_states: Frozen set of NFA state indices
            
        Returns:
            DFAState: Newly created DFA state with full metadata
            
        Raises:
            ValueError: If NFA states are invalid
        """
        if not nfa_states:
            raise ValueError("Cannot create DFA state from empty NFA state set")
        
        # Validate NFA state indices
        for state_idx in nfa_states:
            if not (0 <= state_idx < len(self.nfa.states)):
                raise ValueError(f"Invalid NFA state index: {state_idx}")
        
        # Check if this is an accepting state
        is_accept = self.nfa.accept in nfa_states
        
        # Create DFA state with state ID for debugging
        state = DFAState(
            nfa_states=nfa_states,
            is_accept=is_accept,
            state_id=self.build_stats['states_created']
        )

        # Aggregate properties from all constituent NFA states
        all_variables = set()
        excluded_variables = set()
        subset_vars = set()
        anchor_states = []
        permute_data_merged = {}
        
        for nfa_state_idx in nfa_states:
            nfa_state = self.nfa.states[nfa_state_idx]

            # Collect variables
            if hasattr(nfa_state, 'variable') and nfa_state.variable:
                all_variables.add(nfa_state.variable)
                
                # Check if variable is excluded
                if hasattr(nfa_state, 'is_excluded') and nfa_state.is_excluded:
                    excluded_variables.add(nfa_state.variable)

            # Collect anchor information
            if hasattr(nfa_state, 'is_anchor') and nfa_state.is_anchor:
                anchor_states.append((nfa_state_idx, nfa_state.anchor_type))

            # Collect subset variables
            if hasattr(nfa_state, 'subset_vars') and nfa_state.subset_vars:
                subset_vars.update(nfa_state.subset_vars)

            # Merge PERMUTE metadata
            if hasattr(nfa_state, 'permute_data') and nfa_state.permute_data:
                for key, value in nfa_state.permute_data.items():
                    if key in permute_data_merged:
                        # Handle conflicts by preferring more specific data
                        if isinstance(value, list) and isinstance(permute_data_merged[key], list):
                            permute_data_merged[key].extend(value)
                        elif value != permute_data_merged[key]:
                            logger.warning(f"PERMUTE metadata conflict for key '{key}': "
                                         f"{permute_data_merged[key]} vs {value}")
                    else:
                        permute_data_merged[key] = value

            # Check for empty match capability
            if hasattr(nfa_state, 'allows_empty_match') and nfa_state.allows_empty_match():
                state.is_empty_match = True

        # Assign aggregated properties
        state.variables = all_variables
        state.excluded_variables = excluded_variables
        state.subset_vars = subset_vars
        
        # Handle anchor states (prefer START anchors over END if both present)
        if anchor_states:
            state.is_anchor = True
            # Prioritize START anchor over END anchor
            start_anchors = [a for a in anchor_states if a[1] == PatternTokenType.ANCHOR_START]
            if start_anchors:
                state.anchor_type = PatternTokenType.ANCHOR_START
            else:
                state.anchor_type = anchor_states[0][1]
        
        # Assign PERMUTE data if any
        if permute_data_merged:
            state.permute_data = permute_data_merged
        
        # Calculate state priority based on constituent NFA states
        state.priority = min(self.nfa.states[idx].priority for idx in nfa_states)
        
        logger.debug(f"Created DFA state {state.state_id} from NFA states {sorted(nfa_states)}: "
                    f"accept={is_accept}, variables={all_variables}, anchor={state.is_anchor}")
        
        return state

    def _group_transitions(self, nfa_states: FrozenSet[int]) -> Dict[Optional[str], List[Transition]]:
        """
        Group NFA transitions by variable, preserving priorities and handling conflicts.
        
        Args:
            nfa_states: Set of NFA state indices to process
            
        Returns:
            Dict mapping variable names to lists of transitions
        """
        transitions: Dict[Optional[str], List[Transition]] = defaultdict(list)
        
        for state_idx in nfa_states:
            nfa_state = self.nfa.states[state_idx]
            
            for trans in nfa_state.transitions:
                variable = trans.variable
                transitions[variable].append(trans)
        
        # Sort transitions within each group by priority
        for var, trans_list in transitions.items():
            trans_list.sort(key=lambda t: (t.priority, t.target))
        
        return dict(transitions)
        """Group NFA transitions by variable for optimization, preserving priorities."""
        transitions: Dict[str, List[Transition]] = {}
        
        for state_idx in nfa_states:
            for trans in self.nfa.states[state_idx].transitions:
                if trans.variable not in transitions:
                    transitions[trans.variable] = []
                transitions[trans.variable].append(trans)
        
        # Sort transitions within each variable group by priority (lower = higher priority)
        for var, trans_list in transitions.items():
            trans_list.sort(key=lambda t: t.priority)
                
        return transitions

    def _compute_target_set(self, transitions: List[Transition]) -> FrozenSet[int]:
        """
        Compute the target set of states reachable through given transitions.
        
        Args:
            transitions: List of transitions to follow
            
        Returns:
            FrozenSet[int]: Set of reachable state indices
        """
        target_states = set()
        
        for trans in transitions:
            # Add direct target
            target_states.add(trans.target)
        
        # Compute epsilon closure of all targets
        if target_states:
            epsilon_closure = self.nfa.epsilon_closure(list(target_states))
            return frozenset(epsilon_closure)
        
        return frozenset()

    def _get_target_state(
        self,
        target_set: FrozenSet[int],
        state_map: Dict[FrozenSet[int], int],
        dfa_states: List[DFAState],
        queue: deque
    ) -> int:
        """
        Get or create target state for given NFA state set.
        
        Args:
            target_set: Set of NFA states
            state_map: Mapping from state sets to DFA state indices
            dfa_states: List of existing DFA states
            queue: Queue for processing new states
            
        Returns:
            int: Index of target DFA state
        """
        if target_set in state_map:
            self.build_stats['cache_hits'] += 1
            return state_map[target_set]
        
        # Create new DFA state
        self.build_stats['cache_misses'] += 1
        new_state = self._create_dfa_state(target_set)
        new_idx = len(dfa_states)
        
        dfa_states.append(new_state)
        state_map[target_set] = new_idx
        queue.append(target_set)
        
        self.build_stats['states_created'] += 1
        
        return new_idx

    def _create_combined_condition(self, transitions: List[Transition]) -> Callable:
        """
        Create a combined condition function for multiple transitions.
        
        Args:
            transitions: List of transitions to combine
            
        Returns:
            Callable: Combined condition function
        """
        if len(transitions) == 1:
            return transitions[0].condition
        
        # Create OR combination of all conditions
        def combined_condition(row_data, context):
            for trans in transitions:
                try:
                    if trans.condition(row_data, context):
                        return True
                except Exception as e:
                    logger.warning(f"Condition evaluation failed: {e}")
                    continue
            return False
        
        return combined_condition
    
    def _compute_combined_priority(self, transitions: List[Transition]) -> int:
        """
        Compute combined priority for multiple transitions.
        
        Args:
            transitions: List of transitions
            
        Returns:
            int: Combined priority (minimum for highest precedence)
        """
        if not transitions:
            return 0
        
        return min(trans.priority for trans in transitions)
    
    def _create_combined_metadata(self, transitions: List[Transition]) -> Dict[str, Any]:
        """
        Create combined metadata from multiple transitions.
        
        Args:
            transitions: List of transitions
            
        Returns:
            Dict[str, Any]: Combined metadata
        """
        combined = {}
        
        for trans in transitions:
            if trans.metadata:
                for key, value in trans.metadata.items():
                    if key in combined:
                        # Handle conflicts - prefer more specific/recent data
                        if isinstance(value, list) and isinstance(combined[key], list):
                            combined[key].extend(value)
                        else:
                            combined[key] = value
                    else:
                        combined[key] = value
        
        return combined
    
    def _create_final_metadata(self) -> Dict[str, Any]:
        """
        Create final metadata for the completed DFA.
        
        Returns:
            Dict[str, Any]: Comprehensive metadata
        """
        final_metadata = self.metadata.copy()
        
        # Add build statistics
        final_metadata.update({
            'build_stats': self.build_stats.copy(),
            'dfa_construction_time': self.build_stats['build_time'],
            'cache_hit_rate': (
                self.build_stats['cache_hits'] / 
                max(1, self.build_stats['cache_hits'] + self.build_stats['cache_misses'])
            ),
            'construction_efficiency': {
                'states_per_second': self.build_stats['states_created'] / max(0.001, self.build_stats['build_time']),
                'transitions_per_second': self.build_stats['transitions_created'] / max(0.001, self.build_stats['build_time'])
            }
        })
        
        return final_metadata
    
    def get_build_statistics(self) -> Dict[str, Any]:
        """
        Get detailed build statistics for monitoring and debugging.
        
        Returns:
            Dict[str, Any]: Build statistics and performance metrics
        """
        return {
            'states_created': self.build_stats['states_created'],
            'transitions_created': self.build_stats['transitions_created'],
            'cache_hits': self.build_stats['cache_hits'],
            'cache_misses': self.build_stats['cache_misses'],
            'cache_hit_rate': (
                self.build_stats['cache_hits'] / 
                max(1, self.build_stats['cache_hits'] + self.build_stats['cache_misses'])
            ),
            'build_time': self.build_stats['build_time'],
            'source_nfa_states': len(self.nfa.states),
            'subset_cache_size': len(self.subset_cache)
        }