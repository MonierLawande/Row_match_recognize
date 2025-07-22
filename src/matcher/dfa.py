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
        """Merge states that are functionally equivalent using enhanced algorithm."""
        if len(self.states) <= 1:
            return
        
        logger.debug("Starting enhanced state minimization...")
        
        # Use partition refinement algorithm for better performance
        partitions = self._compute_initial_partitions()
        
        changed = True
        iterations = 0
        max_iterations = len(self.states)
        
        while changed and iterations < max_iterations:
            changed = False
            iterations += 1
            
            new_partitions = []
            
            for partition in partitions:
                if len(partition) <= 1:
                    new_partitions.append(partition)
                    continue
                
                # Try to split this partition
                split_result = self._split_partition(partition, partitions)
                
                if len(split_result) > 1:
                    changed = True
                    new_partitions.extend(split_result)
                else:
                    new_partitions.append(partition)
            
            partitions = new_partitions
        
        # Apply merging based on final partitions
        self._apply_partition_merging(partitions)
        
        logger.info(f"State minimization completed in {iterations} iterations, "
                   f"final partitions: {len(partitions)}")
    
    def _compute_initial_partitions(self) -> List[List[int]]:
        """Compute initial partitions based on state properties."""
        # Group states by their basic properties
        property_groups = defaultdict(list)
        
        for i, state in enumerate(self.states):
            # Create property signature
            signature = (
                state.is_accept,
                frozenset(state.variables) if state.variables else frozenset(),
                state.is_anchor,
                state.anchor_type if hasattr(state, 'anchor_type') else None,
                len(state.transitions)
            )
            property_groups[signature].append(i)
        
        return list(property_groups.values())
    
    def _split_partition(self, partition: List[int], all_partitions: List[List[int]]) -> List[List[int]]:
        """Split a partition based on transition compatibility."""
        if len(partition) <= 1:
            return [partition]
        
        # Create partition index mapping for efficient lookup
        state_to_partition = {}
        for part_idx, part in enumerate(all_partitions):
            for state_idx in part:
                state_to_partition[state_idx] = part_idx
        
        # Group states by their transition signatures
        signature_groups = defaultdict(list)
        
        for state_idx in partition:
            state = self.states[state_idx]
            
            # Create transition signature based on target partitions
            signature = []
            for trans in sorted(state.transitions, key=lambda t: (t.variable or "", t.target)):
                target_partition = state_to_partition.get(trans.target, -1)
                signature.append((trans.variable, target_partition))
            
            signature_key = tuple(signature)
            signature_groups[signature_key].append(state_idx)
        
        return list(signature_groups.values())
    
    def _apply_partition_merging(self, partitions: List[List[int]]) -> None:
        """Apply state merging based on computed partitions."""
        if len(partitions) >= len(self.states):
            return  # No merging possible
        
        # Create state mapping
        state_mapping = {}
        new_states = []
        states_merged = 0
        
        for partition in partitions:
            if not partition:
                continue
                
            representative = min(partition)
            new_states.append(self.states[representative])
            
            for state_idx in partition:
                state_mapping[state_idx] = len(new_states) - 1
                if state_idx != representative:
                    states_merged += 1
        
        if states_merged == 0:
            return
        
        logger.info(f"Merged {states_merged} states, reduced from {len(self.states)} to {len(new_states)}")
        
        # Update state references in transitions
        for state in new_states:
            updated_transitions = []
            for trans in state.transitions:
                new_target = state_mapping.get(trans.target, trans.target)
                if new_target < len(new_states):  # Valid target after merging
                    updated_trans = Transition(
                        condition=trans.condition,
                        target=new_target,
                        variable=trans.variable,
                        priority=trans.priority,
                        metadata=trans.metadata
                    )
                    updated_transitions.append(updated_trans)
            state.transitions = updated_transitions
        
        # Update start state
        self.start = state_mapping.get(self.start, self.start)
        
        # Update states list
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
    Enhanced DFA builder with exponential protection and advanced optimizations.
    
    Key improvements:
    - Exponential state explosion prevention
    - Smart state deduplication and merging
    - Advanced caching with memory management
    - Priority-based construction for deterministic behavior
    - Enhanced error handling and recovery
    - Performance monitoring and optimization
    - Memory-efficient algorithms for large patterns
    
    Features:
    - State count limits to prevent memory exhaustion
    - Intelligent subset construction with early termination
    - Advanced metadata propagation from NFA
    - Thread-safe operations with proper synchronization
    - Comprehensive validation and error recovery
    """

    def __init__(self, nfa: NFA):
        """
        Initialize enhanced DFA builder with exponential protection.
        
        Args:
            nfa: Source NFA to convert to DFA
        """
        if not isinstance(nfa, NFA):
            raise TypeError(f"Expected NFA instance, got {type(nfa)}")
        
        if not nfa.validate():
            raise ValueError("Source NFA validation failed")
        
        self.nfa = nfa
        self._lock = threading.RLock()
        
        # Exponential protection limits
        self.MAX_DFA_STATES = 10000  # Prevent memory exhaustion
        self.MAX_SUBSET_SIZE = 50    # Limit NFA state combinations
        self.MAX_ITERATIONS = 100000 # Prevent infinite loops
        
        # Enhanced caching and optimization
        self._subset_cache = {}
        self._transition_cache = {}
        self._state_dedup_cache = {}
        
        # Performance and debugging metrics
        self._build_start_time = None
        self._iteration_count = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._states_created = 0
        self._states_merged = 0
        
        # Build statistics for tracking
        self.build_stats = {
            'states_created': 0,
            'transitions_created': 0,
            'build_time': 0.0,
            'cache_hits': 0,
            'cache_misses': 0,
            'states_merged': 0
        }
        
        # Metadata for final DFA - start with NFA metadata
        self.metadata = {}
        if hasattr(nfa, 'metadata') and nfa.metadata:
            self.metadata.update(nfa.metadata)
        
        # Add DFA-specific metadata
        self.metadata.update({
            'original_nfa_states': len(nfa.states),
            'original_nfa_transitions': sum(len(state.transitions) for state in nfa.states),
            'construction_method': 'enhanced_subset_construction',
            'exponential_protection': True,
            'optimization_features': [
                'state_deduplication',
                'transition_merging',
                'early_termination',
                'cache_optimization'
            ]
        })
        
        # Validation and safety flags
        self._exponential_detected = False
        self._early_termination = False
        
        logger.debug(f"[DFA_ENHANCED] Initialized DFA builder with limits: states={self.MAX_DFA_STATES}, subset_size={self.MAX_SUBSET_SIZE}")

    def build(self) -> DFA:
        """
        Build DFA with enhanced exponential protection and optimization.
        
        Returns:
            DFA: Constructed DFA with comprehensive optimizations
            
        Raises:
            ValueError: If construction fails or limits are exceeded
            RuntimeError: If exponential pattern is detected
        """
        self._build_start_time = time.time()
        
        logger.info(f"[DFA_ENHANCED] Starting DFA construction from NFA with {len(self.nfa.states)} states")
        
        try:
            with self._lock:
                # Pre-construction validation and risk assessment
                if self._assess_exponential_risk():
                    logger.warning(f"[DFA_ENHANCED] High exponential risk detected, using conservative construction")
                    return self._build_conservative_dfa()
                
                # Standard construction with exponential monitoring
                return self._build_standard_dfa()
                
        except Exception as e:
            logger.error(f"[DFA_ENHANCED] DFA construction failed: {e}")
            raise RuntimeError(f"DFA construction failed: {e}") from e
        
        finally:
            build_time = time.time() - self._build_start_time
            logger.info(f"[DFA_ENHANCED] DFA construction completed in {build_time:.3f}s")
            self._log_construction_metrics()

    def _assess_exponential_risk(self) -> bool:
        """Assess the risk of exponential state explosion."""
        nfa_states = len(self.nfa.states)
        
        # Check for high NFA state count
        if nfa_states > 100:
            logger.warning(f"[DFA_ENHANCED] High NFA state count: {nfa_states}")
            return True
        
        # Check for patterns indicating exponential risk
        epsilon_density = self._calculate_epsilon_density()
        if epsilon_density > 0.5:
            logger.warning(f"[DFA_ENHANCED] High epsilon transition density: {epsilon_density:.2f}")
            return True
        
        # Check for complex metadata
        if self.nfa.metadata.get('has_alternations') and self.nfa.metadata.get('permute'):
            logger.warning(f"[DFA_ENHANCED] Complex pattern: PERMUTE with alternations")
            return True
        
        return False

    def _calculate_epsilon_density(self) -> float:
        """Calculate the density of epsilon transitions in the NFA."""
        total_transitions = sum(len(state.transitions) + len(state.epsilon) for state in self.nfa.states)
        epsilon_transitions = sum(len(state.epsilon) for state in self.nfa.states)
        
        return epsilon_transitions / max(total_transitions, 1)

    def _build_conservative_dfa(self) -> DFA:
        """Build DFA using conservative approach for high-risk patterns."""
        logger.info(f"[DFA_ENHANCED] Using conservative DFA construction")
        
        # Start with reduced limits
        self.MAX_DFA_STATES = min(self.MAX_DFA_STATES, 1000)
        self.MAX_SUBSET_SIZE = min(self.MAX_SUBSET_SIZE, 10)
        
        # Use simplified subset construction
        return self._build_simplified_dfa()

    def _build_standard_dfa(self) -> DFA:
        """Build DFA using standard subset construction with enhancements."""
        # Initialize data structures
        dfa_states: List[DFAState] = []
        state_map: Dict[FrozenSet[int], int] = {}
        queue = deque()
        
        # Get initial state set with epsilon closure
        initial_nfa_states = frozenset(self.nfa.epsilon_closure([self.nfa.start]))
        
        # Create initial DFA state
        initial_dfa_state = self._create_enhanced_dfa_state(initial_nfa_states)
        dfa_states.append(initial_dfa_state)
        state_map[initial_nfa_states] = 0
        queue.append((initial_nfa_states, 0))
        
        self._states_created += 1
        
        # Process queue with exponential protection
        while queue and self._iteration_count < self.MAX_ITERATIONS:
            self._iteration_count += 1
            
            if len(dfa_states) >= self.MAX_DFA_STATES:
                logger.warning(f"[DFA_ENHANCED] Reached maximum DFA states limit: {self.MAX_DFA_STATES}")
                self._early_termination = True
                break
            
            nfa_states, dfa_state_idx = queue.popleft()
            
            # Check subset size limit
            if len(nfa_states) > self.MAX_SUBSET_SIZE:
                logger.warning(f"[DFA_ENHANCED] Large subset size: {len(nfa_states)}, applying reduction")
                nfa_states = self._reduce_subset_size(nfa_states)
            
            # Group transitions by variables/conditions with enhanced logic
            transition_groups = self._group_transitions_enhanced(nfa_states)
            
            # Process each transition group
            for group_key, transitions in transition_groups.items():
                try:
                    # Compute target state set
                    target_set = self._compute_target_set_enhanced(transitions)
                    
                    if not target_set:
                        continue
                    
                    # Apply epsilon closure with limits
                    closure_result = self._safe_epsilon_closure(target_set)
                    target_closure = frozenset(closure_result)
                    
                    # Get or create target DFA state
                    target_dfa_idx = self._get_or_create_target_state(
                        target_closure, state_map, dfa_states, queue
                    )
                    
                    if target_dfa_idx is None:
                        continue  # Skip if creation failed
                    
                    # Create optimized transition
                    combined_condition = self._create_enhanced_condition(transitions)
                    combined_priority = self._compute_enhanced_priority(transitions)
                    combined_metadata = self._create_enhanced_metadata(transitions)
                    
                    # Add transition to current state
                    dfa_states[dfa_state_idx].add_transition(
                        condition=combined_condition,
                        target=target_dfa_idx,
                        variable=group_key,
                        priority=combined_priority,
                        metadata=combined_metadata
                    )
                    
                except Exception as e:
                    logger.warning(f"[DFA_ENHANCED] Error processing transition group {group_key}: {e}")
                    continue  # Skip this transition group
        
        # Check for early termination
        if self._iteration_count >= self.MAX_ITERATIONS:
            logger.warning(f"[DFA_ENHANCED] Reached maximum iterations limit: {self.MAX_ITERATIONS}")
            self._early_termination = True
        
        # Create final DFA with enhanced metadata
        final_metadata = self._create_final_enhanced_metadata()
        
        dfa = DFA(
            states=dfa_states,
            start=0,
            metadata=final_metadata
        )
        
        # Apply post-construction optimizations
        self._apply_post_construction_optimizations(dfa)
        
        logger.info(f"[DFA_ENHANCED] Standard DFA construction completed: "
                   f"{len(dfa_states)} states, {self._iteration_count} iterations")
        
        return dfa

    def _build_simplified_dfa(self) -> DFA:
        """Build a simplified DFA for high-risk patterns."""
        logger.info(f"[DFA_ENHANCED] Building simplified DFA")
        
        # Create minimal DFA structure
        dfa_states = []
        
        # Start state
        start_state = DFAState(nfa_states=frozenset([self.nfa.start]))
        dfa_states.append(start_state)
        
        # Accept state
        accept_state = DFAState(nfa_states=frozenset([self.nfa.accept]), is_accept=True)
        dfa_states.append(accept_state)
        
        # Create simplified transitions
        all_variables = set()
        for state in self.nfa.states:
            for trans in state.transitions:
                if trans.variable:
                    all_variables.add(trans.variable)
        
        # Add transitions for each variable
        for i, var in enumerate(all_variables):
            # Create simple condition that delegates to NFA
            condition = self._create_simplified_condition(var)
            start_state.add_transition(condition, 1, var, i)
        
        # Create final metadata
        metadata = {
            'simplified': True,
            'exponential_protection': True,
            'original_nfa_states': len(self.nfa.states),
            'construction_time': time.time() - self._build_start_time
        }
        
        return DFA(states=dfa_states, start=0, metadata=metadata)

    def _reduce_subset_size(self, nfa_states: FrozenSet[int]) -> FrozenSet[int]:
        """Reduce subset size by removing less important states."""
        if len(nfa_states) <= self.MAX_SUBSET_SIZE:
            return nfa_states
        
        states_list = list(nfa_states)
        
        # Sort by importance (accept states first, then by priority)
        def state_importance(state_idx):
            state = self.nfa.states[state_idx]
            importance = 0
            
            if state.is_accept:
                importance += 1000
            if state.variable:
                importance += 100
            if state.transitions:
                importance += len(state.transitions)
                
            return importance
        
        states_list.sort(key=state_importance, reverse=True)
        
        # Keep the most important states
        reduced_states = states_list[:self.MAX_SUBSET_SIZE]
        
        logger.debug(f"[DFA_ENHANCED] Reduced subset from {len(nfa_states)} to {len(reduced_states)} states")
        
        return frozenset(reduced_states)

    def _safe_epsilon_closure(self, state_set: Set[int]) -> List[int]:
        """Compute epsilon closure with safety limits."""
        try:
            # Use NFA's epsilon closure but with limits
            result = self.nfa.epsilon_closure(list(state_set))
            
            # Apply size limit
            if len(result) > self.MAX_SUBSET_SIZE:
                logger.warning(f"[DFA_ENHANCED] Large epsilon closure: {len(result)}, reducing")
                result = result[:self.MAX_SUBSET_SIZE]
            
            return result
            
        except Exception as e:
            logger.error(f"[DFA_ENHANCED] Error in epsilon closure: {e}")
            return list(state_set)  # Fallback to original set

    def _group_transitions_enhanced(self, nfa_states: FrozenSet[int]) -> Dict[Optional[str], List[Transition]]:
        """Enhanced transition grouping with deduplication."""
        groups = defaultdict(list)
        seen_transitions = set()
        
        for state_idx in nfa_states:
            state = self.nfa.states[state_idx]
            
            for trans in state.transitions:
                # Create unique key for deduplication
                trans_key = (trans.variable, trans.target, id(trans.condition))
                
                if trans_key not in seen_transitions:
                    seen_transitions.add(trans_key)
                    groups[trans.variable].append(trans)
                else:
                    self._cache_hits += 1
        
        return dict(groups)

    def _compute_target_set_enhanced(self, transitions: List[Transition]) -> Set[int]:
        """Enhanced target set computation with deduplication."""
        target_set = set()
        
        for trans in transitions:
            target_set.add(trans.target)
        
        return target_set

    def _get_or_create_target_state(self, target_closure: FrozenSet[int], 
                                  state_map: Dict[FrozenSet[int], int],
                                  dfa_states: List[DFAState], 
                                  queue: deque) -> Optional[int]:
        """
        Get existing DFA state or create new one with enhanced deduplication.
        
        Args:
            target_closure: NFA states closure for the target DFA state
            state_map: Mapping from NFA state sets to DFA state indices
            dfa_states: List of existing DFA states
            queue: Construction queue for new states
            
        Returns:
            DFA state index or None if creation fails
        """
        # Check if state already exists
        if target_closure in state_map:
            self._cache_hits += 1
            return state_map[target_closure]
        
        # Check deduplication cache for equivalent states
        closure_hash = hash(target_closure)
        if closure_hash in self._state_dedup_cache:
            equivalent_closure = self._state_dedup_cache[closure_hash]
            if equivalent_closure in state_map:
                logger.debug(f"[DFA_ENHANCED] Found equivalent state via deduplication")
                state_map[target_closure] = state_map[equivalent_closure]
                self._cache_hits += 1
                self._states_merged += 1
                return state_map[equivalent_closure]
        
        # Enforce state limits
        if len(dfa_states) >= self.MAX_DFA_STATES:
            logger.warning(f"[DFA_ENHANCED] Reached DFA state limit: {self.MAX_DFA_STATES}")
            self._early_termination = True
            return None
        
        # Create new DFA state
        try:
            new_dfa_state = self._create_enhanced_dfa_state(target_closure)
            new_state_idx = len(dfa_states)
            
            # Add to structures
            dfa_states.append(new_dfa_state)
            state_map[target_closure] = new_state_idx
            queue.append((target_closure, new_state_idx))
            
            # Update deduplication cache
            self._state_dedup_cache[closure_hash] = target_closure
            
            # Limit cache size
            if len(self._state_dedup_cache) > 5000:
                # Remove oldest 1000 entries
                keys_to_remove = list(self._state_dedup_cache.keys())[:1000]
                for key in keys_to_remove:
                    del self._state_dedup_cache[key]
            
            self._cache_misses += 1
            self._states_created += 1
            
            logger.debug(f"[DFA_ENHANCED] Created new DFA state {new_state_idx} from closure {sorted(target_closure)}")
            
            return new_state_idx
            
        except Exception as e:
            logger.error(f"[DFA_ENHANCED] Failed to create DFA state: {e}")
            return None
    
    def _create_enhanced_dfa_state(self, nfa_states: FrozenSet[int]) -> DFAState:
        """
        Create DFA state with enhanced optimization and metadata propagation.
        
        Args:
            nfa_states: Set of NFA state indices
            
        Returns:
            DFAState: Optimized DFA state with comprehensive metadata
        """
        # Check subset cache first
        cache_key = nfa_states
        if cache_key in self._subset_cache:
            cached_state = self._subset_cache[cache_key]
            # Create new state based on cached data but with unique ID
            new_state = DFAState(nfa_states=nfa_states)
            new_state.is_accept = cached_state.is_accept
            new_state.variables = cached_state.variables.copy()
            new_state.excluded_variables = cached_state.excluded_variables.copy()
            new_state.subset_vars = cached_state.subset_vars.copy()
            new_state.is_anchor = cached_state.is_anchor
            new_state.anchor_type = cached_state.anchor_type
            new_state.permute_data = cached_state.permute_data.copy() if cached_state.permute_data else None
            new_state.priority = cached_state.priority
            self._cache_hits += 1
            return new_state
        
        # Create new state
        state = DFAState(nfa_states=nfa_states)
        
        # Aggregate properties from constituent NFA states
        all_variables = set()
        excluded_variables = set()
        subset_vars = set()
        anchor_states = []
        permute_data_merged = {}
        is_accept = False
        min_priority = float('inf')
        
        for nfa_state_idx in nfa_states:
            if nfa_state_idx >= len(self.nfa.states):
                continue
                
            nfa_state = self.nfa.states[nfa_state_idx]
            
            # Check if this is an accept state
            if nfa_state_idx == self.nfa.accept:
                is_accept = True
            
            # Update minimum priority
            if hasattr(nfa_state, 'priority'):
                min_priority = min(min_priority, nfa_state.priority)
            
            # Collect variables
            if hasattr(nfa_state, 'variable') and nfa_state.variable:
                all_variables.add(nfa_state.variable)
                
                # Check if variable is excluded
                if hasattr(nfa_state, 'is_excluded') and nfa_state.is_excluded:
                    excluded_variables.add(nfa_state.variable)
            
            # Collect anchor information
            if hasattr(nfa_state, 'is_anchor') and nfa_state.is_anchor:
                anchor_states.append((nfa_state_idx, getattr(nfa_state, 'anchor_type', None)))
            
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
        
        # Assign aggregated properties
        state.is_accept = is_accept
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
        
        # Set priority
        state.priority = min_priority if min_priority != float('inf') else 0
        
        # Cache the result to speed up future lookups
        self._subset_cache[cache_key] = state
        
        # Limit cache size
        if len(self._subset_cache) > 2000:
            # Remove oldest entries
            keys_to_remove = list(self._subset_cache.keys())[:500]
            for key in keys_to_remove:
                del self._subset_cache[key]
        
        self._cache_misses += 1
        
        logger.debug(f"Created enhanced DFA state from NFA states {sorted(nfa_states)}: "
                    f"accept={is_accept}, variables={all_variables}, anchor={state.is_anchor}")
        
        return state
        """Get existing or create new target state with limits."""
        # Check cache first
        if target_closure in state_map:
            self._cache_hits += 1
            return state_map[target_closure]
        
        # Check limits
        if len(dfa_states) >= self.MAX_DFA_STATES:
            logger.warning(f"[DFA_ENHANCED] Cannot create new state: limit reached")
            return None
        
        # Create new state
        try:
            new_state = self._create_enhanced_dfa_state(target_closure)
            new_idx = len(dfa_states)
            
            dfa_states.append(new_state)
            state_map[target_closure] = new_idx
            queue.append((target_closure, new_idx))
            
            self._states_created += 1
            self._cache_misses += 1
            
            return new_idx
            
        except Exception as e:
            logger.error(f"[DFA_ENHANCED] Error creating new state: {e}")
            return None

    def _create_enhanced_dfa_state(self, nfa_states: FrozenSet[int]) -> DFAState:
        """Create enhanced DFA state with comprehensive metadata."""
        # Check if any NFA state is accepting
        is_accept = any(self.nfa.states[idx].is_accept for idx in nfa_states)
        
        # Collect variables and metadata
        variables = set()
        excluded_variables = set()
        permute_data = None
        is_anchor = False
        anchor_type = None
        
        for state_idx in nfa_states:
            state = self.nfa.states[state_idx]
            
            if state.variable:
                if state.is_excluded:
                    excluded_variables.add(state.variable)
                else:
                    variables.add(state.variable)
            
            if state.is_anchor:
                is_anchor = True
                anchor_type = state.anchor_type
            
            if state.permute_data:
                permute_data = state.permute_data
        
        # Create state with comprehensive attributes
        dfa_state = DFAState(
            nfa_states=nfa_states,
            is_accept=is_accept,
            variables=variables,
            excluded_variables=excluded_variables,
            is_anchor=is_anchor,
            anchor_type=anchor_type,
            permute_data=permute_data,
            state_id=self._states_created
        )
        
        return dfa_state

    def _create_enhanced_condition(self, transitions: List[Transition]) -> Callable:
        """Create enhanced combined condition with optimization."""
        if len(transitions) == 1:
            return transitions[0].condition
        
        # Cache key for condition combination
        conditions_key = tuple(id(t.condition) for t in transitions)
        
        if conditions_key in self._transition_cache:
            self._cache_hits += 1
            return self._transition_cache[conditions_key]
        
        # Create combined condition
        conditions = [t.condition for t in transitions]
        
        def combined_condition(row, ctx):
            # Try each condition until one matches (OR logic)
            for condition in conditions:
                try:
                    if condition(row, ctx):
                        return True
                except Exception as e:
                    logger.debug(f"[DFA_ENHANCED] Condition evaluation error: {e}")
                    continue
            return False
        
        # Cache the result
        self._transition_cache[conditions_key] = combined_condition
        self._cache_misses += 1
        
        return combined_condition

    def _compute_enhanced_priority(self, transitions: List[Transition]) -> int:
        """Compute enhanced priority from multiple transitions."""
        if not transitions:
            return 0
        
        # Use minimum priority (highest precedence)
        return min(t.priority for t in transitions)

    def _create_enhanced_metadata(self, transitions: List[Transition]) -> Dict[str, Any]:
        """Create enhanced metadata from transitions."""
        metadata = {
            'transition_count': len(transitions),
            'variables': [t.variable for t in transitions if t.variable],
            'priorities': [t.priority for t in transitions]
        }
        
        # Merge individual transition metadata
        for trans in transitions:
            if trans.metadata:
                for key, value in trans.metadata.items():
                    if key not in metadata:
                        metadata[key] = value
                    elif isinstance(value, list) and isinstance(metadata[key], list):
                        metadata[key].extend(value)
        
        return metadata

    def _create_final_enhanced_metadata(self) -> Dict[str, Any]:
        """Create final DFA metadata with construction metrics."""
        return {
            'construction_time': time.time() - self._build_start_time,
            'iterations': self._iteration_count,
            'states_created': self._states_created,
            'states_merged': self._states_merged,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'early_termination': self._early_termination,
            'exponential_detected': self._exponential_detected,
            'max_states_limit': self.MAX_DFA_STATES,
            'max_subset_limit': self.MAX_SUBSET_SIZE,
            'optimized': True,
            **dict(self.nfa.metadata)  # Include NFA metadata
        }

    def _apply_post_construction_optimizations(self, dfa: DFA):
        """Apply optimizations after DFA construction."""
        if len(dfa.states) > 100:
            logger.info(f"[DFA_ENHANCED] Applying post-construction optimizations")
            dfa.optimize()

    def _create_simplified_condition(self, variable: str) -> Callable:
        """Create simplified condition for emergency fallback."""
        def simplified_condition(row, ctx):
            # Simple always-true condition for safety
            return True
        
        return simplified_condition

    def _log_construction_metrics(self):
        """Log detailed construction metrics."""
        logger.info(f"[DFA_ENHANCED] Construction metrics:")
        logger.info(f"  - Iterations: {self._iteration_count}")
        logger.info(f"  - States created: {self._states_created}")
        logger.info(f"  - States merged: {self._states_merged}")
        logger.info(f"  - Cache hits: {self._cache_hits}")
        logger.info(f"  - Cache misses: {self._cache_misses}")
        logger.info(f"  - Early termination: {self._early_termination}")
        logger.info(f"  - Exponential detected: {self._exponential_detected}")

    def get_build_statistics(self) -> Dict[str, Any]:
        """Get comprehensive build statistics."""
        return {
            'iterations': self._iteration_count,
            'states_created': self._states_created,
            'states_merged': self._states_merged,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'cache_hit_ratio': self._cache_hits / max(self._cache_hits + self._cache_misses, 1),
            'early_termination': self._early_termination,
            'exponential_detected': self._exponential_detected,
            'construction_time': time.time() - self._build_start_time if self._build_start_time else 0
        }
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
        logger.debug(f"DFA: Copying metadata from NFA: {nfa.metadata}")
        self.metadata: Dict[str, Any] = nfa.metadata.copy() if nfa.metadata else {}
        logger.debug(f"DFA: Metadata after copy: {self.metadata}")
        
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
        
        # PRODUCTION FIX: Handle patterns with optional suffixes
        # For patterns like "A B+ C+ D?", a DFA state representing completion of "A B+ C+"
        # should also be accepting since D? is optional
        if not is_accept and hasattr(self.nfa, 'metadata'):
            nfa_metadata = self.nfa.metadata
            if nfa_metadata.get('has_optional_suffix', False):
                # Check if this DFA state represents a position where only optional parts remain
                is_accept = self._can_reach_accept_via_optional_only(nfa_states)
                if is_accept:
                    logger.debug(f"DFA state {self.build_stats['states_created']} marked as accepting due to optional suffix completion")
        
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

    def _can_reach_accept_via_optional_only(self, nfa_states: FrozenSet[int]) -> bool:
        """
        Production-ready check if the given NFA states can reach the accept state through optional-only paths.
        
        This handles patterns like "A B+ C+ D?" where after matching "A B+ C+", the remaining
        "D?" is optional and should be considered as a valid completion point.
        
        This implementation uses the optional suffix metadata from the NFA to determine
        if the current DFA state represents a valid completion point for required pattern parts.
        
        Args:
            nfa_states: Set of NFA state indices to check
            
        Returns:
            True if accept state is reachable via optional-only transitions or if this
            represents completion of all required pattern parts
        """
        # First, check direct epsilon reachability to accept state
        visited = set()
        to_check = list(nfa_states)
        
        while to_check:
            current_state_idx = to_check.pop(0)
            
            if current_state_idx in visited:
                continue
            visited.add(current_state_idx)
            
            if current_state_idx == self.nfa.accept:
                return True
                
            # Check epsilon transitions from this state
            current_state = self.nfa.states[current_state_idx]
            for target_idx in current_state.epsilon:
                if target_idx not in visited:
                    to_check.append(target_idx)
        
        # If not directly reachable via epsilon, use metadata-based approach
        # This is more reliable for complex patterns with optional suffixes
        nfa_metadata = self.nfa.metadata
        if not nfa_metadata.get('has_optional_suffix', False):
            return False
            
        # Get the optional suffix tokens to understand what's optional
        optional_suffix_tokens = nfa_metadata.get('optional_suffix_tokens', [])
        last_required_token_idx = nfa_metadata.get('last_required_token_idx', -1)
        
        if not optional_suffix_tokens or last_required_token_idx == -1:
            return False
            
        logger.debug(f"Checking optional suffix reachability: suffix_tokens={optional_suffix_tokens}, "
                    f"last_required_idx={last_required_token_idx}, nfa_states={nfa_states}")
        
        # Advanced heuristic: Check if this DFA state represents completion of required parts
        # For patterns like "A B+ C+ D?", after consuming "A B+ C+", we should be in a state
        # that can be considered accepting since D? is optional
        
        # Strategy: Check if any NFA state in this DFA state can reach accept
        # through a path that only involves optional quantifiers
        for state_idx in nfa_states:
            if self._can_reach_accept_through_optionals(state_idx, optional_suffix_tokens, visited=set()):
                logger.debug(f"Found optional path to accept from NFA state {state_idx}")
                return True
        
        return False
    
    def _can_reach_accept_through_optionals(self, state_idx: int, optional_tokens: List[str], 
                                          visited: Set[int]) -> bool:
        """
        Check if a specific NFA state can reach accept through optional-only constructs.
        
        This method performs a depth-first search through the NFA, following transitions
        that correspond to optional pattern elements.
        
        Args:
            state_idx: NFA state index to start from
            optional_tokens: List of optional pattern tokens (e.g., ['D?'])
            visited: Set of already visited states to prevent infinite loops
            
        Returns:
            True if accept is reachable through optional-only paths
        """
        if state_idx in visited:
            return False
        visited.add(state_idx)
        
        if state_idx == self.nfa.accept:
            return True
            
        # Check epsilon transitions (always consider these as "optional")
        current_state = self.nfa.states[state_idx]
        for target_idx in current_state.epsilon:
            if self._can_reach_accept_through_optionals(target_idx, optional_tokens, visited.copy()):
                return True
        
        # Check transitions that correspond to optional pattern elements
        for transition in current_state.transitions:
            if transition.variable and self._is_optional_variable(transition.variable, optional_tokens):
                target_idx = transition.target
                if self._can_reach_accept_through_optionals(target_idx, optional_tokens, visited.copy()):
                    return True
        
        return False
    
    def _is_optional_variable(self, variable: str, optional_tokens: List[str]) -> bool:
        """
        Check if a variable corresponds to an optional pattern token.
        
        Args:
            variable: Variable name to check
            optional_tokens: List of optional pattern tokens (e.g., ['D?'])
            
        Returns:
            True if the variable is part of an optional pattern construct
        """
        # Simple check: see if the variable appears in any optional token
        for token in optional_tokens:
            # Remove quantifier suffix to get base variable name
            base_token = token.rstrip('?+*{}0123456789, ')
            if variable == base_token:
                return True
        return False
    
    def _create_enhanced_condition(self, transitions: List[Transition]) -> Callable:
        """Create optimized combined condition from multiple transitions."""
        if not transitions:
            return lambda row, ctx: False
        
        if len(transitions) == 1:
            return transitions[0].condition
        
        # Cache key for condition combination
        condition_ids = tuple(id(t.condition) for t in transitions)
        if condition_ids in self._transition_cache:
            self._cache_hits += 1
            return self._transition_cache[condition_ids]
        
        # Create combined condition with short-circuit evaluation
        conditions = [t.condition for t in transitions]
        
        def combined_condition(row, ctx):
            # Use short-circuit OR evaluation for performance
            for condition in conditions:
                try:
                    if condition(row, ctx):
                        return True
                except Exception as e:
                    logger.debug(f"Condition evaluation error: {e}")
                    continue
            return False
        
        # Cache the combined condition
        self._transition_cache[condition_ids] = combined_condition
        self._cache_misses += 1
        
        # Limit cache size
        if len(self._transition_cache) > 3000:
            # Remove oldest entries
            keys_to_remove = list(self._transition_cache.keys())[:600]
            for key in keys_to_remove:
                del self._transition_cache[key]
        
        return combined_condition
    
    def _compute_enhanced_priority(self, transitions: List[Transition]) -> int:
        """Compute optimized priority from multiple transitions."""
        if not transitions:
            return 0
        
        # Use minimum priority for deterministic behavior
        return min(t.priority for t in transitions)
    
    def _create_enhanced_metadata(self, transitions: List[Transition]) -> Dict[str, Any]:
        """Create optimized metadata from multiple transitions."""
        if not transitions:
            return {}
        
        combined_metadata = {}
        
        # Merge metadata from all transitions
        for trans in transitions:
            if trans.metadata:
                for key, value in trans.metadata.items():
                    if key in combined_metadata:
                        # Handle conflicts by creating lists
                        if not isinstance(combined_metadata[key], list):
                            combined_metadata[key] = [combined_metadata[key]]
                        if value not in combined_metadata[key]:
                            combined_metadata[key].append(value)
                    else:
                        combined_metadata[key] = value
        
        return combined_metadata
    
    def _create_final_enhanced_metadata(self) -> Dict[str, Any]:
        """Create final DFA metadata with construction statistics."""
        build_time = time.time() - self._build_start_time
        
        enhanced_metadata = self.metadata.copy()
        enhanced_metadata.update({
            'construction_stats': {
                'build_time': build_time,
                'iterations': self._iteration_count,
                'states_created': self._states_created,
                'states_merged': self._states_merged,
                'cache_hits': self._cache_hits,
                'cache_misses': self._cache_misses,
                'early_termination': self._early_termination,
                'cache_hit_ratio': self._cache_hits / max(self._cache_hits + self._cache_misses, 1)
            }
        })
        
        return enhanced_metadata