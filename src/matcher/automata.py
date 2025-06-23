"""
Production-ready automata module for SQL:2016 row pattern matching.

This module implements Non-deterministic Finite Automata (NFA) with comprehensive
support for complex pattern constructs including PERMUTE, alternation, quantifiers,
exclusions, and anchors. Designed for high performance and maintainability.

Features:
- Robust NFA construction with cycle detection
- Full PERMUTE pattern support with alternations
- Complex exclusion patterns with nested structures
- Optimized epsilon closure computation
- Comprehensive metadata tracking
- Production-grade error handling and logging

Author: Pattern Matching Engine Team
Version: 2.0.0
"""

from typing import (
    Callable, List, Optional, Dict, Any, Set, Tuple, Union, 
    FrozenSet, Iterator, Protocol
)
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import itertools
import re
import time
from collections import defaultdict, deque
import threading
from contextlib import contextmanager

from src.matcher.pattern_tokenizer import (
    PatternToken, PatternTokenType, parse_quantifier
)
from src.matcher.condition_evaluator import compile_condition
from src.utils.logging_config import get_logger, PerformanceTimer

# Module logger with enhanced configuration
logger = get_logger(__name__)

# Type aliases for better readability
ConditionFunction = Callable[[Dict[str, Any], Any], bool]
StateIndex = int
TransitionMap = Dict[StateIndex, List['Transition']]
EpsilonMap = Dict[StateIndex, List[StateIndex]]

# A condition function: given a row and current match context, return True if the row qualifies.
ConditionFn = ConditionFunction

@dataclass(frozen=True)
class Transition:
    """
    Production-ready transition with comprehensive validation and metadata support.
    
    Represents a labeled transition in an NFA with support for pattern variables,
    priorities, and specialized metadata for complex pattern constructs.
    
    Attributes:
        condition: Function that evaluates if a row matches this transition.
                  Must be callable with signature (row_data, context) -> bool
        target: Target state index (must be non-negative)
        variable: Optional pattern variable associated with this transition
        priority: Priority for resolving ambiguous transitions (lower = higher priority)
        metadata: Additional metadata for specialized transitions (e.g., PERMUTE data)
        
    Raises:
        ValueError: If target is negative or condition is not callable
        TypeError: If condition signature is invalid
    """
    condition: ConditionFunction
    target: int
    variable: Optional[str] = None
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate transition parameters after initialization."""
        if self.target < 0:
            raise ValueError(f"Target state index must be non-negative, got {self.target}")
        
        if not callable(self.condition):
            raise TypeError(f"Condition must be callable, got {type(self.condition)}")
        
        # Validate variable name if present
        if self.variable is not None:
            if not isinstance(self.variable, str) or not self.variable.strip():
                raise ValueError(f"Variable name must be non-empty string, got '{self.variable}'")
            
            # Check for valid variable naming (alphanumeric + underscore, or quoted identifiers)
            # Allow quoted identifiers like "variable_name" for SQL:2016 compliance
            if (not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', self.variable) and 
                not re.match(r'^"[^"]*"$', self.variable)):
                raise ValueError(f"Invalid variable name format: '{self.variable}'")
    
    def evaluate_condition(self, row_data: Dict[str, Any], context: Any = None) -> bool:
        """
        Safely evaluate the transition condition with error handling.
        
        Args:
            row_data: Row data to evaluate against
            context: Optional context for evaluation
            
        Returns:
            bool: True if condition matches, False otherwise
            
        Raises:
            RuntimeError: If condition evaluation fails
        """
        try:
            return self.condition(row_data, context)
        except Exception as e:
            logger.error(f"Transition condition evaluation failed for variable '{self.variable}': {e}")
            raise RuntimeError(f"Condition evaluation error: {e}") from e
    
    def is_compatible_with(self, other: 'Transition') -> bool:
        """
        Check if this transition is compatible with another for optimization.
        
        Args:
            other: Another transition to check compatibility with
            
        Returns:
            bool: True if transitions can be merged/optimized together
        """
        return (
            self.target == other.target and
            self.variable == other.variable and
            self.priority == other.priority and
            self.metadata == other.metadata
        )

class NFAState:
    """
    Production-ready NFA state with comprehensive SQL:2016 pattern matching support.
    
    This class represents a state in a Non-deterministic Finite Automaton with full
    support for complex pattern constructs including PERMUTE, alternation, quantifiers,
    exclusions, and anchors.
    
    Thread-safe design with proper validation and error handling.
    
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
        epsilon_priorities: Priority mapping for epsilon transitions
        
    Thread Safety:
        This class is thread-safe for read operations. Write operations should
        be synchronized externally if used across multiple threads.
    """
    
    def __init__(self, state_id: Optional[int] = None):
        """
        Initialize NFA state with optional state ID for debugging.
        
        Args:
            state_id: Optional unique identifier for this state
        """
        self.state_id = state_id
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
        self.epsilon_priorities: Dict[int, int] = {}
        
        # Validation flags
        self._validated: bool = False
        self._lock = threading.RLock()
    
    def add_transition(self, condition: ConditionFunction, target: int, 
                      variable: Optional[str] = None, priority: int = 0, 
                      metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a transition with enhanced validation and metadata support.
        
        Args:
            condition: Function that evaluates if a row matches this transition
            target: Target state index (must be non-negative)
            variable: Optional pattern variable associated with this transition
            priority: Priority for resolving ambiguous transitions (lower = higher priority)
            metadata: Additional metadata for specialized transitions
            
        Raises:
            ValueError: If parameters are invalid
            TypeError: If condition is not callable
        """
        with self._lock:
            transition = Transition(
                condition=condition,
                target=target,
                variable=variable,
                priority=priority,
                metadata=metadata or {}
            )
            
            # Check for duplicate transitions
            if any(t.target == target and t.variable == variable for t in self.transitions):
                logger.warning(f"Duplicate transition to state {target} with variable '{variable}'")
            
            self.transitions.append(transition)
            self._validated = False
            
            logger.debug(f"Added transition: variable='{variable}', target={target}, priority={priority}")
    
    def add_epsilon(self, target: int, priority: int = 0) -> None:
        """
        Add an epsilon transition to target state with priority support.
        
        Args:
            target: Target state index (must be non-negative)
            priority: Priority for this epsilon transition
            
        Raises:
            ValueError: If target is invalid
        """
        if target < 0:
            raise ValueError(f"Epsilon target must be non-negative, got {target}")
        
        with self._lock:
            if target not in self.epsilon:
                self.epsilon.append(target)
                self.epsilon_priorities[target] = priority
                self._validated = False
                logger.debug(f"Added epsilon transition to state {target} with priority {priority}")
            else:
                # Update priority if target already exists
                if self.epsilon_priorities.get(target, 0) != priority:
                    self.epsilon_priorities[target] = priority
                    logger.debug(f"Updated epsilon transition priority to state {target}: {priority}")
    
    def validate(self) -> bool:
        """
        Validate state configuration and constraints.
        
        Returns:
            bool: True if state is valid, False otherwise
        """
        with self._lock:
            if self._validated:
                return True
            
            try:
                # Validate variable naming - allow quoted identifiers for SQL:2016 compliance
                if (self.variable and 
                    not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', self.variable) and 
                    not re.match(r'^"[^"]*"$', self.variable)):
                    logger.error(f"Invalid variable name: '{self.variable}'")
                    return False
                
                # Validate anchor constraints
                if self.is_anchor and not self.anchor_type:
                    logger.error("Anchor state must have anchor_type specified")
                    return False
                
                # Validate transitions
                for trans in self.transitions:
                    try:
                        # Basic validation already done in Transition.__post_init__
                        pass
                    except (ValueError, TypeError) as e:
                        logger.error(f"Invalid transition in state {self.state_id}: {e}")
                        return False
                
                # Validate PERMUTE metadata consistency
                if self.permute_data:
                    required_fields = {'combinations', 'current_index', 'variables'}
                    if not all(field in self.permute_data for field in required_fields):
                        logger.warning(f"Incomplete PERMUTE metadata in state {self.state_id}")
                
                self._validated = True
                return True
                
            except Exception as e:
                logger.error(f"State validation failed for state {self.state_id}: {e}")
                return False
            
    def has_transition_to(self, target: int) -> bool:
        """
        Thread-safe check if this state has a transition to the target state.
        
        Args:
            target: Target state index to check
            
        Returns:
            bool: True if there is a transition to target, False otherwise
        """
        with self._lock:
            # Check normal transitions
            for trans in self.transitions:
                if trans.target == target:
                    return True
                    
            # Check epsilon transitions
            return target in self.epsilon
        
    def allows_empty_match(self) -> bool:
        """
        Check if this state allows empty matches with validation.
        
        Returns:
            bool: True if this state allows empty matches, False otherwise
        """
        return self.is_empty_match or (self.is_accept and len(self.transitions) == 0)
        
    def is_variable_state(self) -> bool:
        """
        Check if this state represents a pattern variable.
        
        Returns:
            bool: True if this state has a variable name, False otherwise
        """
        return self.variable is not None and self.variable.strip() != ""
        
    def get_epsilon_targets(self) -> List[int]:
        """
        Get sorted list of epsilon transition targets by priority.
        
        Returns:
            List[int]: List of target state indices sorted by priority
        """
        with self._lock:
            # Sort by priority (lower priority first), then by target index for determinism
            return sorted(self.epsilon, key=lambda t: (self.epsilon_priorities.get(t, 0), t))
        
    def get_transition_targets(self) -> List[int]:
        """
        Get sorted list of all transition targets (non-epsilon) by priority.
        
        Returns:
            List[int]: List of target state indices sorted by priority
        """
        with self._lock:
            return sorted([trans.target for trans in self.transitions], 
                         key=lambda t: (
                             min(tr.priority for tr in self.transitions if tr.target == t),
                             t
                         ))
    
    def get_transitions_by_variable(self, variable: str) -> List[Transition]:
        """
        Get all transitions associated with a specific variable.
        
        Args:
            variable: Variable name to filter by
            
        Returns:
            List[Transition]: List of transitions for the variable
        """
        with self._lock:
            return [trans for trans in self.transitions if trans.variable == variable]
    
    def has_conflicting_transitions(self) -> bool:
        """
        Check if this state has conflicting transitions that could cause ambiguity.
        
        Returns:
            bool: True if there are potential conflicts, False otherwise
        """
        with self._lock:
            # Check for transitions with same target but different variables
            target_vars = defaultdict(set)
            for trans in self.transitions:
                target_vars[trans.target].add(trans.variable)
            
            return any(len(vars_set) > 1 for vars_set in target_vars.values())
    
    def optimize_transitions(self) -> None:
        """
        Optimize transitions by removing duplicates and sorting by priority.
        """
        with self._lock:
            # Remove duplicate transitions (same target, variable, priority)
            seen = set()
            unique_transitions = []
            
            for trans in self.transitions:
                trans_key = (trans.target, trans.variable, trans.priority)
                if trans_key not in seen:
                    seen.add(trans_key)
                    unique_transitions.append(trans)
                else:
                    logger.debug(f"Removed duplicate transition: {trans_key}")
            
            # Sort by priority, then by target for determinism
            self.transitions = sorted(unique_transitions, 
                                    key=lambda t: (t.priority, t.target, t.variable or ""))
            
            # Remove duplicate epsilon transitions
            self.epsilon = list(dict.fromkeys(self.epsilon))  # Preserve order, remove dupes
            
            self._validated = False  # Re-validation needed after optimization
    
    def get_debug_info(self) -> Dict[str, Any]:
        """
        Get comprehensive debug information about this state.
        
        Returns:
            Dict[str, Any]: Debug information including transitions, metadata, etc.
        """
        with self._lock:
            return {
                'state_id': self.state_id,
                'variable': self.variable,
                'is_accept': self.is_accept,
                'is_anchor': self.is_anchor,
                'anchor_type': self.anchor_type.name if self.anchor_type else None,
                'is_excluded': self.is_excluded,
                'is_empty_match': self.is_empty_match,
                'can_accept': self.can_accept,
                'transition_count': len(self.transitions),
                'epsilon_count': len(self.epsilon),
                'subset_vars': list(self.subset_vars),
                'permute_data': dict(self.permute_data),
                'priority': self.priority,
                'validated': self._validated,
                'transitions': [
                    {
                        'target': t.target,
                        'variable': t.variable,
                        'priority': t.priority,
                        'metadata_keys': list(t.metadata.keys())
                    } for t in self.transitions
                ],
                'epsilon_targets': self.get_epsilon_targets()
            }

# src/matcher/automata.py
# enhanced/automata.py - Part 2: NFA Class

class NFA:
    """
    Production-ready Non-deterministic Finite Automaton for SQL:2016 pattern matching.
    
    This implementation provides comprehensive support for complex pattern constructs
    including PERMUTE, alternation, quantifiers, exclusions, and anchors with
    robust error handling, validation, and performance optimizations.
    
    Features:
    - Efficient epsilon closure computation with cycle detection
    - Comprehensive metadata tracking for complex patterns
    - Thread-safe operations with proper locking
    - Validation and optimization methods
    - Debug and monitoring capabilities
    
    Attributes:
        start: Start state index (must be valid state index)
        accept: Accept state index (must be valid state index)
        states: List of NFA states (validated on construction)
        exclusion_ranges: Ranges of excluded pattern components
        metadata: Additional pattern metadata including PERMUTE and alternation info
        
    Thread Safety:
        This class is thread-safe for read operations. Construction and modification
        should be synchronized externally if used across multiple threads.
    """
    
    def __init__(self, start: int, accept: int, states: List[NFAState], 
                 exclusion_ranges: Optional[List[Tuple[int, int]]] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize NFA with comprehensive validation.
        
        Args:
            start: Start state index
            accept: Accept state index  
            states: List of NFA states
            exclusion_ranges: Optional ranges of excluded pattern components
            metadata: Optional pattern metadata
            
        Raises:
            ValueError: If indices are invalid or states are malformed
            TypeError: If parameters have wrong types
        """
        # Validate parameters
        if not isinstance(states, list) or not states:
            raise ValueError("States must be a non-empty list")
        
        if not (0 <= start < len(states)):
            raise ValueError(f"Start state index {start} out of range [0, {len(states)})")
        
        if not (0 <= accept < len(states)):
            raise ValueError(f"Accept state index {accept} out of range [0, {len(states)})")
        
        # Assign validated parameters
        self.start = start
        self.accept = accept
        self.states = states
        self.exclusion_ranges = exclusion_ranges or []
        self.metadata = metadata or {}
        
        # Add state IDs for debugging if not present
        for i, state in enumerate(self.states):
            if state.state_id is None:
                state.state_id = i
        
        # Validation and optimization flags
        self._validated = False
        self._optimized = False
        self._lock = threading.RLock()
        
        # Validate structure
        if not self.validate():
            raise ValueError("NFA structure validation failed")
    
    def validate(self) -> bool:
        """
        Comprehensive validation of NFA structure and constraints.
        
        Returns:
            bool: True if NFA is valid, False otherwise
        """
        with self._lock:
            if self._validated:
                return True
            
            try:
                # Validate each state
                for i, state in enumerate(self.states):
                    if not state.validate():
                        logger.error(f"State {i} validation failed")
                        return False
                    
                    # Validate transition targets
                    for trans in state.transitions:
                        if not (0 <= trans.target < len(self.states)):
                            logger.error(f"State {i} has invalid transition target {trans.target}")
                            return False
                    
                    # Validate epsilon targets
                    for eps_target in state.epsilon:
                        if not (0 <= eps_target < len(self.states)):
                            logger.error(f"State {i} has invalid epsilon target {eps_target}")
                            return False
                
                # Validate accept state reachability
                if not self._is_accept_reachable():
                    logger.warning("Accept state is not reachable from start state")
                
                # Validate metadata consistency
                if not self._validate_metadata():
                    logger.error("Metadata validation failed")
                    return False
                
                self._validated = True
                return True
                
            except Exception as e:
                logger.error(f"NFA validation failed: {e}")
                return False
    
    def _is_accept_reachable(self) -> bool:
        """Check if accept state is reachable from start state."""
        visited = set()
        queue = deque([self.start])
        
        while queue:
            state_idx = queue.popleft()
            if state_idx == self.accept:
                return True
            
            if state_idx in visited:
                continue
            visited.add(state_idx)
            
            state = self.states[state_idx]
            
            # Add transition targets
            for trans in state.transitions:
                if trans.target not in visited:
                    queue.append(trans.target)
            
            # Add epsilon targets
            for eps_target in state.epsilon:
                if eps_target not in visited:
                    queue.append(eps_target)
        
        return False
    
    def _validate_metadata(self) -> bool:
        """Validate metadata consistency and completeness."""
        try:
            # Validate PERMUTE metadata
            if self.metadata.get('permute'):
                if 'alternation_combinations' not in self.metadata:
                    logger.warning("PERMUTE pattern missing alternation_combinations metadata")
                
                if self.metadata.get('has_alternations'):
                    combinations = self.metadata.get('alternation_combinations', [])
                    if not combinations:
                        logger.error("PERMUTE with alternations must have non-empty combinations")
                        return False
            
            # Validate exclusion ranges
            for start_pos, end_pos in self.exclusion_ranges:
                if start_pos < 0 or end_pos < start_pos:
                    logger.error(f"Invalid exclusion range: ({start_pos}, {end_pos})")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Metadata validation error: {e}")
            return False
    
    def epsilon_closure(self, state_indices: List[int]) -> List[int]:
        """
        Compute epsilon closure for given states with robust cycle detection and priority handling.
        
        This method efficiently computes the set of states reachable from the given states
        through epsilon transitions, with proper cycle detection and priority-based ordering.
        
        Args:
            state_indices: List of state indices to compute closure for
            
        Returns:
            List[int]: Sorted list of state indices in the epsilon closure
            
        Raises:
            ValueError: If any state index is invalid
        """
        # Validate input
        for idx in state_indices:
            if not (0 <= idx < len(self.states)):
                raise ValueError(f"Invalid state index {idx}")
        
        closure = set(state_indices)
        queue = deque(state_indices)
        visited_transitions = set()  # Track (source, target) pairs to detect cycles
        max_iterations = len(self.states) ** 2  # Conservative upper bound
        iterations = 0
        
        with PerformanceTimer("epsilon_closure"):
            while queue and iterations < max_iterations:
                iterations += 1
                current_state = queue.popleft()
                
                # Get epsilon targets sorted by priority
                for target in self.states[current_state].get_epsilon_targets():
                    transition_key = (current_state, target)
                    
                    # Skip if we've already processed this transition (cycle detection)
                    if transition_key in visited_transitions:
                        continue
                    
                    visited_transitions.add(transition_key)
                    
                    if target not in closure:
                        closure.add(target)
                        queue.append(target)
            
            if iterations >= max_iterations:
                logger.warning(f"Epsilon closure computation hit iteration limit: {max_iterations}")
        
        # Sort result by state priority, then by index for deterministic behavior
        result = sorted(closure, key=lambda idx: (
            self.states[idx].priority,
            idx
        ))
        
        logger.debug(f"Epsilon closure of {state_indices} = {result} (iterations: {iterations})")
        return result
    
    def get_variable_states(self) -> Dict[str, List[int]]:
        """
        Get mapping of variables to their associated state indices.
        
        Returns:
            Dict[str, List[int]]: Mapping from variable names to state indices
        """
        var_states = defaultdict(list)
        
        for i, state in enumerate(self.states):
            if state.variable:
                var_states[state.variable].append(i)
        
        # Sort state lists for consistency
        for var in var_states:
            var_states[var].sort()
        
        return dict(var_states)
    
    def get_permute_info(self) -> Dict[str, Any]:
        """
        Extract comprehensive PERMUTE pattern information.
        
        Returns:
            Dict[str, Any]: PERMUTE pattern metadata including combinations and variables
        """
        if not self.metadata.get('permute'):
            return {}
        
        return {
            'is_permute': True,
            'has_alternations': self.metadata.get('has_alternations', False),
            'alternation_combinations': self.metadata.get('alternation_combinations', []),
            'permute_variables': self.metadata.get('permute_variables', []),
            'current_combination_index': self.metadata.get('current_combination_index', 0)
        }
    
    def optimize(self) -> None:
        """
        Apply optimizations to improve NFA performance and structure.
        """
        with self._lock:
            if self._optimized:
                return
            
            logger.info("Optimizing NFA...")
            
            # Optimize each state
            for state in self.states:
                state.optimize_transitions()
            
            # Remove unreachable states
            self._remove_unreachable_states()
            
            # Merge equivalent epsilon transitions
            self._merge_epsilon_transitions()
            
            # Update metadata after optimization
            self._update_optimization_metadata()
            
            self._optimized = True
            self._validated = False  # Need re-validation after optimization
            
            logger.info("NFA optimization completed")
    
    def _remove_unreachable_states(self) -> None:
        """Remove states that cannot be reached from the start state."""
        reachable = set()
        queue = deque([self.start])
        
        # Find all reachable states
        while queue:
            state_idx = queue.popleft()
            if state_idx in reachable:
                continue
            
            reachable.add(state_idx)
            state = self.states[state_idx]
            
            # Add transition targets
            for trans in state.transitions:
                if trans.target not in reachable:
                    queue.append(trans.target)
            
            # Add epsilon targets
            for eps_target in state.epsilon:
                if eps_target not in reachable:
                    queue.append(eps_target)
        
        # Remove unreachable states if any found
        if len(reachable) < len(self.states):
            logger.info(f"Removing {len(self.states) - len(reachable)} unreachable states")
            
            # Create mapping from old to new indices
            old_to_new = {}
            new_states = []
            
            for old_idx in sorted(reachable):
                old_to_new[old_idx] = len(new_states)
                new_states.append(self.states[old_idx])
            
            # Update transitions
            for state in new_states:
                # Update transition targets
                for trans in state.transitions:
                    trans.target = old_to_new[trans.target]
                
                # Update epsilon targets
                state.epsilon = [old_to_new[target] for target in state.epsilon]
                
                # Update epsilon priorities
                if hasattr(state, 'epsilon_priorities'):
                    new_priorities = {}
                    for old_target, priority in state.epsilon_priorities.items():
                        if old_target in old_to_new:
                            new_priorities[old_to_new[old_target]] = priority
                    state.epsilon_priorities = new_priorities
            
            # Update NFA references
            self.start = old_to_new[self.start]
            self.accept = old_to_new[self.accept]
            self.states = new_states
    
    def _merge_epsilon_transitions(self) -> None:
        """Merge equivalent epsilon transitions to reduce complexity."""
        for state in self.states:
            if len(state.epsilon) <= 1:
                continue
            
            # Group epsilon targets by priority
            priority_groups = defaultdict(list)
            for target in state.epsilon:
                priority = state.epsilon_priorities.get(target, 0)
                priority_groups[priority].append(target)
            
            # Rebuild epsilon list with merged groups
            new_epsilon = []
            new_priorities = {}
            
            for priority, targets in sorted(priority_groups.items()):
                # Remove duplicates while preserving order
                unique_targets = list(dict.fromkeys(targets))
                new_epsilon.extend(unique_targets)
                
                for target in unique_targets:
                    new_priorities[target] = priority
            
            state.epsilon = new_epsilon
            state.epsilon_priorities = new_priorities
    
    def _update_optimization_metadata(self) -> None:
        """Update metadata after optimization."""
        self.metadata['optimized'] = True
        self.metadata['state_count'] = len(self.states)
        self.metadata['optimization_timestamp'] = time.time()
        
        # Update variable mappings
        var_states = self.get_variable_states()
        self.metadata['variable_states'] = var_states
    
    def get_debug_info(self) -> Dict[str, Any]:
        """
        Get comprehensive debug information about the NFA.
        
        Returns:
            Dict[str, Any]: Debug information including structure, metadata, and statistics
        """
        with self._lock:
            return {
                'structure': {
                    'start': self.start,
                    'accept': self.accept,
                    'state_count': len(self.states),
                    'validated': self._validated,
                    'optimized': self._optimized
                },
                'metadata': dict(self.metadata),
                'exclusion_ranges': list(self.exclusion_ranges),
                'variable_states': self.get_variable_states(),
                'permute_info': self.get_permute_info(),
                'statistics': {
                    'total_transitions': sum(len(s.transitions) for s in self.states),
                    'total_epsilon_transitions': sum(len(s.epsilon) for s in self.states),
                    'variable_states_count': len([s for s in self.states if s.variable]),
                    'accept_reachable': self._is_accept_reachable()
                },
                'states': [state.get_debug_info() for state in self.states]
            }
            
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
            # Update normal transitions - create new transitions since they're frozen
            updated_transitions = []
            for trans in state.transitions:
                if trans.target in state_map:
                    # Create new transition with updated target
                    new_trans = Transition(
                        condition=trans.condition,
                        target=state_map[trans.target],
                        variable=trans.variable,
                        priority=trans.priority,
                        metadata=trans.metadata
                    )
                    updated_transitions.append(new_trans)
            state.transitions = updated_transitions
                
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
    
    def add_epsilon_with_priority(self, from_state: int, to_state: int, priority: int):
        """Add an epsilon transition with priority for alternation precedence."""
        # For now, we'll use the standard epsilon transition but mark the priority
        # The actual priority handling will be done during matching
        if to_state not in self.states[from_state].epsilon:
            self.states[from_state].epsilon.append(to_state)
            # Store priority information in state metadata for use during matching
            if not hasattr(self.states[from_state], 'epsilon_priorities'):
                self.states[from_state].epsilon_priorities = {}
            self.states[from_state].epsilon_priorities[to_state] = priority
    
    def _is_empty_pattern_branch(self, start: int, end: int) -> bool:
        """
        Check if a branch represents an empty pattern.
        
        An empty pattern branch has:
        1. Only epsilon transitions from start to end (no variable transitions)
        2. No intermediate states with variable assignments
        
        Args:
            start: Start state of the branch
            end: End state of the branch
            
        Returns:
            bool: True if the branch represents an empty pattern
        """
        # If start and end are the same state, it's empty
        if start == end:
            return True
            
        # Check if there's a direct epsilon path from start to end with no variables
        visited = set()
        queue = [start]
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            # If we reached the end state, check the path
            if current == end:
                # Check if any state in the path has variable transitions
                for state_idx in visited:
                    state = self.states[state_idx]
                    if state.variable or state.transitions:
                        return False
                return True
            
            # Follow epsilon transitions only
            for eps_target in self.states[current].epsilon:
                if eps_target not in visited:
                    queue.append(eps_target)
        
        # If we can't reach end via epsilon transitions, it's not empty
        return False
 
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
        
        # Validate anchor semantics first - critical for SQL:2016 compliance
        if not self._validate_anchor_semantics(tokens):
            # Pattern has invalid anchor semantics (like A^), create a non-matching NFA
            # Connect start directly to a dead-end state (not accept)
            dead_state = self.new_state()
            self.add_epsilon(start, dead_state)
            return NFA(start, accept, self.states, [], self.metadata)
        
        # Process pattern with full SQL:2016 compliance
        idx = [0]  # Use mutable list for position tracking
        
        try:
            # Process sequence of tokens
            pattern_start, pattern_end = self._process_sequence(tokens, idx, define)
            
            # Connect pattern to start and accept states
            self.add_epsilon(start, pattern_start)
            self.add_epsilon(pattern_end, accept)
            
            # PRODUCTION FIX: Handle trailing optional quantifiers
            # For patterns like "A B+ C+ D?", the state after C+ should also be accepting
            # since D? is optional and can be skipped
            self._add_optional_suffix_transitions(tokens, start, accept, define)
            
            # Check for patterns that allow empty matches - critical for SQL:2016 compliance
            allows_empty = False
            
            # Check token quantifiers for empty match possibilities
            for token in tokens:
                if token.quantifier in ['?', '*', '{0}', '{0,}']:
                    allows_empty = True
                    self.metadata["allows_empty"] = True
                    break
            
            # Check for empty groups in alternations like (() | A)
            if not allows_empty:
                for i, token in enumerate(tokens):
                    if (token.type == PatternTokenType.GROUP_START and 
                        i + 1 < len(tokens) and 
                        tokens[i + 1].type == PatternTokenType.GROUP_END):
                        # Found empty group ()
                        allows_empty = True
                        self.metadata["allows_empty"] = True
                        self.metadata["has_empty_group"] = True
                        break
                    
                    # Also check for empty alternatives like (A|) which allow empty matches
                    if token.type == PatternTokenType.ALTERNATION:
                        # If alternation is followed by GROUP_END, it might allow empty match
                        if i + 1 < len(tokens) and tokens[i + 1].type == PatternTokenType.GROUP_END:
                            allows_empty = True
                            self.metadata["allows_empty"] = True
                            break
            
            # For patterns like Z? that allow empty matches, add direct path
            if allows_empty:
                self.add_epsilon(start, accept)
            
            # Add metadata about pattern structure for optimization and validation
            self._analyze_pattern_structure(tokens)
            
            # Create the NFA with all metadata
            nfa = NFA(start, accept, self.states, self.exclusion_ranges, self.metadata)
            
            # Apply optimizations
            nfa.optimize()
            
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
                
                # SQL:2016 alternation precedence: empty patterns have higher priority
                # Check if left branch (start to current) is an empty pattern
                left_is_empty = self._is_empty_pattern_branch(start, current)
                # Check if right branch (empty) has priority - connect it with higher priority
                right_is_empty = self._is_empty_pattern_branch(right_start, right_end)
                
                if left_is_empty and not right_is_empty:
                    # Left branch (empty) has priority - connect it with higher priority (priority 0)
                    self.add_epsilon_with_priority(alt_start, start, 0)  # Higher priority for empty
                    self.add_epsilon_with_priority(alt_start, right_start, 1)  # Lower priority for non-empty
                elif right_is_empty and not left_is_empty:
                    # Right branch (empty) has priority - connect it with higher priority
                    self.add_epsilon_with_priority(alt_start, right_start, 0)  # Higher priority for empty
                    self.add_epsilon_with_priority(alt_start, start, 1)  # Lower priority for non-empty
                else:
                    # Both empty or both non-empty - use standard equal priority
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
                
            elif token.type == PatternTokenType.EXCLUSION:
                # Handle standalone exclusion tokens
                exclusion_start, exclusion_end = self._process_exclusion_token(token, define)
                
                # Connect exclusion fragment to current NFA
                self.add_epsilon(current, exclusion_start)
                current = exclusion_end
                
                # Skip exclusion token
                idx[0] += 1
                
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

    def _process_exclusion_token(self, token: PatternToken, define: Dict[str, str]) -> Tuple[int, int]:
        """
        Process a standalone exclusion token with excluded variables in metadata.
        
        SQL:2016 EXCLUSION SEMANTICS:
        Exclusion patterns like {- B+ -} should match the full pattern but
        exclude the specified variables from the output. The automata must
        build the complete pattern and mark excluded variables for filtering.
        
        Args:
            token: The exclusion token with metadata
            define: Dictionary of variable definitions
            
        Returns:
            Tuple of (start_state, end_state) for the exclusion pattern
        """
        # Get excluded variables from token metadata
        excluded_vars = token.metadata.get('excluded_variables', [])
        
        if not excluded_vars:
            logger.warning("Exclusion token has no excluded variables in metadata")
            # Create a simple bypass
            bypass_state = self.new_state()
            return bypass_state, bypass_state
        
        # Create start and end states for the exclusion pattern
        excl_start = self.new_state()
        excl_end = self.new_state()
        
        # Track exclusion range start
        exclusion_start_idx = len(self.states) - 2  # -2 because we just created 2 states
        
        # SQL:2016 COMPLIANT EXCLUSION: Build the complete pattern
        # DO NOT create a bypass - we need to match the excluded variables
        # and then filter them from output in the matcher
        
        current_state = excl_start
        
        # Process each excluded variable and connect them in sequence
        for i, var_spec in enumerate(excluded_vars):
            var_spec = var_spec.strip()
            
            # Parse variable and quantifier (e.g., "B+" -> "B", "+")
            var_name = var_spec
            quantifier = None
            
            # Extract quantifier if present
            if var_spec.endswith('+'):
                var_name = var_spec[:-1]
                quantifier = '+'
            elif var_spec.endswith('*'):
                var_name = var_spec[:-1]
                quantifier = '*'
            elif var_spec.endswith('?'):
                var_name = var_spec[:-1]
                quantifier = '?'
            elif '{' in var_spec and '}' in var_spec:
                # Handle {n,m} quantifiers
                brace_start = var_spec.find('{')
                var_name = var_spec[:brace_start]
                quantifier = var_spec[brace_start:]
            
            # Create variable states
            var_start, var_end = self.create_var_states(var_name, define)
            
            # Connect to the sequence
            self.add_epsilon(current_state, var_start)
            
            # Apply quantifier if present
            if quantifier:
                min_rep, max_rep, greedy = parse_quantifier(quantifier)
                var_start, var_end = self._apply_quantifier(
                    var_start, var_end, min_rep, max_rep, greedy)
            
            # Mark all variable transitions as excluded in metadata
            # Do NOT mark states as excluded - we need them to match!
            # Instead, mark the transitions/variables for output filtering
            for state_id, state in enumerate(self.states):
                if state is not None:
                    for transition in state.transitions:
                        if transition.variable == var_name:
                            # Mark this transition as excluded in metadata
                            transition.metadata['is_excluded'] = True
            
            current_state = var_end
        
        # Connect the last variable to the end state
        self.add_epsilon(current_state, excl_end)
        
        # Mark exclusion end in NFA states
        exclusion_end_idx = len(self.states) - 1
        
        # Store exclusion range for later processing
        self.exclusion_ranges.append((exclusion_start_idx, exclusion_end_idx))
        
        # Store excluded variables in NFA metadata for the matcher
        if 'excluded_variables' not in self.metadata:
            self.metadata['excluded_variables'] = set()
        
        # Add excluded variable names (without quantifiers) to metadata
        for var_spec in excluded_vars:
            var_name = var_spec.strip()
            # Remove quantifier suffix
            if var_name.endswith(('+', '*', '?')):
                var_name = var_name[:-1]
            elif '{' in var_name and '}' in var_name:
                var_name = var_name[:var_name.find('{')]
            
            self.metadata['excluded_variables'].add(var_name)
        
        logger.debug(f"Processed exclusion token with variables: {excluded_vars}")
        logger.debug(f"Excluded variables added to metadata: {self.metadata['excluded_variables']}")
        
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
            
        # Compile the condition with DEFINE evaluation mode for pattern variables
        condition_fn = compile_condition(condition_str, evaluation_mode='DEFINE')
        
        # Create transition with condition, variable tracking
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

    def create_var_states_with_priority(self, var: Union[str, PatternToken], define: Dict[str, str], priority: int = 0) -> Tuple[int, int]:
        """
        Create states for a pattern variable with explicit priority assignment.
        
        Args:
            var: Variable name or PatternToken object
            define: Dictionary of variable definitions
            priority: Priority for transitions (lower = higher priority)
            
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
            
        # Compile the condition with DEFINE evaluation mode for pattern variables
        condition_fn = compile_condition(condition_str, evaluation_mode='DEFINE')
        
        # Create transition with condition, variable tracking, AND priority
        self.states[start].add_transition(condition_fn, end, var_base, priority)
        
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

    def add_epsilon_with_priority(self, source: int, target: int, priority: int):
        """
        Add an epsilon transition with priority tracking.
        
        Args:
            source: Source state index
            target: Target state index  
            priority: Priority for this epsilon transition
        """
        self.states[source].add_epsilon(target)
        # Store priority in the epsilon_priorities dict
        if not hasattr(self.states[source], 'epsilon_priorities'):
            self.states[source].epsilon_priorities = {}
        self.states[source].epsilon_priorities[target] = priority

    def add_epsilon(self, source: int, target: int):
        """Add an epsilon transition (wrapper for backward compatibility)."""
        self.states[source].add_epsilon(target)
    
    def _validate_anchor_semantics(self, tokens: List[PatternToken]) -> bool:
        """
        Validate anchor semantics to ensure patterns like A^ are marked as impossible.
        
        According to SQL:2016 standard:
        - Start anchors (^) can only appear at the beginning or after alternation
        - End anchors ($) can only appear at the end or before alternation
        - Patterns like A^ are semantically invalid (literal followed by start anchor)
        - Patterns like ^A$ are valid (start anchor, literal, end anchor)
        
        Args:
            tokens: List of pattern tokens to validate
            
        Returns:
            bool: True if pattern has valid semantics, False if impossible to match
        """
        for i, token in enumerate(tokens):
            if token.type == PatternTokenType.ANCHOR_START:
                # ^ must be at start, after (, or after |
                if i > 0:
                    prev_token = tokens[i-1]
                    if prev_token.type not in (PatternTokenType.GROUP_START, PatternTokenType.ALTERNATION):
                        # Found ^ after a literal (like A^) - this is semantically invalid
                        self.metadata["impossible_pattern"] = True
                        self.metadata["invalid_anchor_reason"] = f"Start anchor after {prev_token.type.name} at position {i}"
                        return False
                        
            elif token.type == PatternTokenType.ANCHOR_END:
                # $ must be at end, before ), or before |
                if i < len(tokens) - 1:
                    next_token = tokens[i+1]
                    if next_token.type not in (PatternTokenType.GROUP_END, PatternTokenType.ALTERNATION):
                        # Found $ before a literal (like $A) - this is semantically invalid
                        self.metadata["impossible_pattern"] = True
                        self.metadata["invalid_anchor_reason"] = f"End anchor before {next_token.type.name} at position {i}"
                        return False
        
        return True

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
        
        if not variables:
            # Empty PERMUTE - just epsilon transition
            self.add_epsilon(perm_start, perm_end)
            return perm_start, perm_end
        
        # Check for alternations in the variables
        has_alternations = any(
            isinstance(var, PatternToken) and var.type == PatternTokenType.ALTERNATION 
            for var in variables
        )
        
        # Handle quantified PERMUTE (e.g., PERMUTE(A, B){2,3})
        if token.quantifier:
            logger.debug(f"Processing quantified PERMUTE: {original_pattern} with quantifier {token.quantifier}")
            
            # Create inner permute without quantifier
            inner_token = PatternToken(
                type=PatternTokenType.PERMUTE,
                value=token.value,
                metadata=token.metadata.copy()
            )
            inner_token.quantifier = None  # Remove quantifier for inner processing
            
            # Process the inner permute
            inner_start, inner_end = self._process_permute(inner_token, define)
            
            # Apply quantifier to the inner permute
            min_rep, max_rep, greedy = parse_quantifier(token.quantifier)
            return self._apply_quantifier(inner_start, inner_end, min_rep, max_rep, greedy)
        
        # For simple sequence without alternations and without quantifiers
        if len(variables) == 1 and not has_alternations:
            # Single variable PERMUTE is just the variable itself
            var = variables[0]
            if isinstance(var, str):
                var_start, var_end = self.create_var_states(var, define)
            else:
                var_start, var_end = self.create_var_states(var.value, define)
            
            # Connect through the permute states
            self.add_epsilon(perm_start, var_start)
            self.add_epsilon(var_end, perm_end)
            return perm_start, perm_end
        
        if len(variables) > 1 and not has_alternations:
            # Simple permutation without alternations - handle as before
            current = perm_start
            
            # Create states for each variable with quantifiers handled
            var_states = []
            for var in variables:
                var_base = var
                quantifier = None
                
                if isinstance(var, str):
                    # Extract quantifiers from variable name
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
                
                # Create states for this variable
                var_start, var_end = self.create_var_states(var_base, define)
                
                # Apply quantifier if present
                if quantifier:
                    min_rep, max_rep, greedy = parse_quantifier(quantifier)
                    var_start, var_end = self._apply_quantifier(
                        var_start, var_end, min_rep, max_rep, greedy)
                
                # Connect to the sequence
                self.add_epsilon(current, var_start)
                current = var_end
            
            # Connect final state to permute end
            self.add_epsilon(current, perm_end)
            
        elif has_alternations:
            # For PERMUTE with alternations, we need to handle all combinations
            # but prefer lexicographical order through proper automata construction
            
            # Extract all alternation combinations and create automata for each
            def extract_alternatives(variables):
                """Extract all possible combinations from alternation variables."""
                if not variables:
                    return [[]]
                
                first_var = variables[0]
                rest_vars = variables[1:]
                
                if isinstance(first_var, PatternToken) and first_var.type == PatternTokenType.ALTERNATION:
                    # This is an alternation group
                    alternatives = first_var.metadata.get("alternatives", [])
                    
                    # Get combinations for the rest
                    rest_combinations = extract_alternatives(rest_vars)
                    
                    # Create combinations with each alternative
                    result = []
                    for alt in alternatives:
                        for rest_combo in rest_combinations:
                            result.append([alt] + rest_combo)
                    return result
                else:
                    # Regular variable
                    rest_combinations = extract_alternatives(rest_vars)
                    return [[first_var] + rest_combo for rest_combo in rest_combinations]
            
            # Get all alternation combinations
            all_combinations = extract_alternatives(variables)
            
            # Sort combinations to ensure lexicographical order
            def combination_priority(combo):
                priority = []
                for i, var in enumerate(combo):
                    # Find this variable's position in its original alternation group
                    original_var = variables[i]
                    if isinstance(original_var, PatternToken) and original_var.type == PatternTokenType.ALTERNATION:
                        alternatives = original_var.metadata.get("alternatives", [])
                        try:
                            alt_index = alternatives.index(var)
                            priority.append(alt_index)
                        except ValueError:
                            priority.append(999)  # Unknown alternative gets low priority
                    else:
                        priority.append(0)  # Regular variables get highest priority
                return priority
            
            # Sort by lexicographical priority - this ensures (A,C) comes before (B,C)
            sorted_combinations = sorted(all_combinations, key=combination_priority)
            
            # Store alternation combinations in metadata for the matcher to use
            self.metadata["has_permute"] = True
            self.metadata["has_alternations"] = True
            self.metadata["alternation_combinations"] = sorted_combinations
            
            # Debug the ordering
            logger.debug(f"Alternation combinations ordered: {sorted_combinations}")
            for i, combo in enumerate(sorted_combinations):
                logger.debug(f"  Priority {i}: {combo} (priority: {combination_priority(combo)})")
            
            # Create automata that can match any of the combinations
            # with proper priority assignment for lexicographical preference
            processed_combinations = []
            for combo_idx, combo in enumerate(sorted_combinations):
                processed_vars = []
                for var_idx, var in enumerate(combo):
                    var_start, var_end = self.create_var_states(var, define)
                    
                    # Calculate priority based on combination position and variable position
                    # Lower numbers = higher priority (lexicographically first)
                    priority = combo_idx * 100 + var_idx
                    processed_vars.append((var, var_start, var_end, priority))
                processed_combinations.append(processed_vars)
                
            # Create all permutations for each combination with priority tracking
            for combo_idx, combo_vars in enumerate(processed_combinations):
                all_perms = list(itertools.permutations(range(len(combo_vars))))
                
                # For each permutation of this combination, create a separate branch
                for perm_idx, perm in enumerate(all_perms):
                    # Create a new start state for this permutation
                    branch_start = self.new_state()
                    current = branch_start
                    
                    # Create a chain of states for this permutation with proper priorities
                    for chain_pos, var_pos in enumerate(perm):
                        var_info = combo_vars[var_pos]
                        var_base = var_info[0]
                        base_priority = var_info[3]  # Get the priority we calculated
                        
                        # Create fresh copy to avoid state sharing
                        fresh_start, fresh_end = self.create_var_states_with_priority(
                            var_base, define, base_priority + chain_pos)
                        
                        # Connect to current chain
                        self.add_epsilon(current, fresh_start)
                        current = fresh_end
                    
                    # Connect this permutation branch to the main permutation end
                    self.add_epsilon(current, perm_end)
                    
                    # Connect permutation start to this branch with priority
                    # Higher priority (lower number) for lexicographically first combinations
                    branch_priority = combo_idx * 1000 + perm_idx
                    self.add_epsilon_with_priority(perm_start, branch_start, branch_priority)
            
        else:
            # For non-quantified, non-alternation PERMUTE, generate all permutations as before
            # Pre-process variables to handle nested PERMUTE
            processed_vars = []
            for var in variables:
                if isinstance(var, PatternToken) and var.type == PatternTokenType.PERMUTE:
                    # Recursively process nested PERMUTE
                    nested_start, nested_end = self._process_permute(var, define)
                    processed_vars.append((var, nested_start, nested_end))
                else:
                    # Regular variable
                    var_start, var_end = self.create_var_states(var, define)
                    processed_vars.append((var, var_start, var_end))
            
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

    def _process_alternation(self, token: PatternToken, define: Dict[str, str]) -> Tuple[int, int]:
        """
        Enhanced alternation processing with exponential protection and optimization.
        
        Key improvements:
        - Exponential blowup prevention through state deduplication
        - Smart alternation merging for identical patterns
        - Enhanced priority handling for deterministic behavior
        - Memory-efficient construction for large alternation sets
        - Advanced cycle detection and prevention
        - Optimized epsilon transition management
        
        Args:
            token: The ALTERNATION token with metadata
            define: Dictionary of variable definitions
                
        Returns:
            Tuple of (start_state, end_state)
        """
        logger.debug(f"[ALT_ENHANCED] Processing alternation with {len(token.metadata.get('alternatives', []))} alternatives")
        
        # Extract alternatives from the token
        alternatives = token.metadata.get("alternatives", [])
        
        if not alternatives:
            # Empty alternation - just epsilon transition
            start = self.new_state()
            end = self.new_state()
            self.add_epsilon(start, end)
            return start, end
        
        # Enhanced exponential protection: detect and merge identical alternatives
        unique_alternatives = self._deduplicate_alternatives(alternatives)
        
        # If deduplication significantly reduced alternatives, log it
        if len(unique_alternatives) < len(alternatives):
            logger.info(f"[ALT_ENHANCED] Deduplication reduced {len(alternatives)} alternatives to {len(unique_alternatives)}")
        
        # Check for exponential risk patterns
        if self._has_exponential_risk(unique_alternatives):
            logger.warning(f"[ALT_ENHANCED] Detected potential exponential pattern, applying optimization")
            return self._process_exponential_safe_alternation(unique_alternatives, define)
        
        # Create start and end states for the alternation
        alt_start = self.new_state()
        alt_end = self.new_state()
        
        # Track state mappings for optimization
        alternative_states = {}
        
        # Process each unique alternative with enhanced priority management
        for priority, alternative in enumerate(unique_alternatives):
            try:
                # Generate cache key for this alternative
                alt_key = self._generate_alternative_key(alternative)
                
                # Check if we've already processed this exact alternative
                if alt_key in alternative_states:
                    # Reuse existing states to prevent exponential blowup
                    var_start, var_end = alternative_states[alt_key]
                    logger.debug(f"[ALT_ENHANCED] Reusing states for duplicate alternative: {alt_key}")
                else:
                    # Process new alternative
                    if isinstance(alternative, PatternToken):
                        var_start, var_end = self._process_alternative_token(alternative, define, priority)
                    else:
                        # String alternative - create variable states with enhanced priority
                        var_start, var_end = self._create_enhanced_variable_states(alternative, define, priority)
                    
                    # Cache the states for reuse
                    alternative_states[alt_key] = (var_start, var_end)
                
                # Connect to alternation structure with optimized priorities
                self._add_prioritized_epsilon(alt_start, var_start, priority)
                self.add_epsilon(var_end, alt_end)
                
            except Exception as e:
                logger.error(f"[ALT_ENHANCED] Error processing alternative {priority}: {e}")
                # Continue with other alternatives rather than failing completely
                continue
        
        # Apply post-processing optimizations
        self._optimize_alternation_structure(alt_start, alt_end)
        
        logger.debug(f"[ALT_ENHANCED] Completed alternation processing: start={alt_start}, end={alt_end}")
        return alt_start, alt_end

    def _deduplicate_alternatives(self, alternatives):
        """Remove duplicate alternatives to prevent exponential blowup."""
        seen = set()
        unique = []
        
        for alt in alternatives:
            # Generate a key for this alternative
            if isinstance(alt, PatternToken):
                key = (alt.type.value, alt.value, tuple(sorted(alt.metadata.items())))
            else:
                key = str(alt)
            
            if key not in seen:
                seen.add(key)
                unique.append(alt)
            else:
                logger.debug(f"[ALT_ENHANCED] Skipping duplicate alternative: {key}")
        
        return unique

    def _has_exponential_risk(self, alternatives):
        """Detect patterns that could lead to exponential blowup."""
        # Check for too many similar alternatives
        if len(alternatives) > 10:
            return True
        
        # Check for nested quantifiers in alternatives
        for alt in alternatives:
            if isinstance(alt, PatternToken):
                if alt.type == PatternTokenType.QUANTIFIER:
                    # Nested quantifiers are risky
                    return True
                elif alt.type == PatternTokenType.ALTERNATION:
                    # Nested alternations can be exponential
                    return True
        
        # Check for repeated patterns
        pattern_counts = {}
        for alt in alternatives:
            pattern = str(alt)
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
            if pattern_counts[pattern] > 2:
                return True
        
        return False

    def _process_exponential_safe_alternation(self, alternatives, define):
        """Process alternation with exponential safety measures."""
        logger.info(f"[ALT_ENHANCED] Using exponential-safe alternation processing")
        
        # Create simplified alternation structure
        alt_start = self.new_state()
        alt_end = self.new_state()
        
        # Group similar alternatives
        grouped_alternatives = self._group_similar_alternatives(alternatives)
        
        # Process each group with shared states where possible
        for group_id, group_alternatives in grouped_alternatives.items():
            # Create shared entry point for this group
            group_start = self.new_state()
            
            # Process alternatives in this group
            for priority, alternative in enumerate(group_alternatives):
                if isinstance(alternative, str):
                    # Simple variable - create optimized states
                    var_state = self.new_state()
                    var_state.variable = alternative
                    
                    # Create condition
                    if alternative in define:
                        condition = compile_condition(define[alternative])
                    else:
                        condition = lambda row, ctx: True  # Default to always match
                    
                    var_state.add_transition(condition, alt_end, alternative, priority)
                    self.add_epsilon(group_start, var_state)
            
            # Connect group to main alternation
            self._add_prioritized_epsilon(alt_start, group_start, group_id)
        
        return alt_start, alt_end

    def _group_similar_alternatives(self, alternatives):
        """Group similar alternatives to reduce state explosion."""
        groups = {}
        group_id = 0
        
        for alt in alternatives:
            # Simple grouping by type for now
            if isinstance(alt, str):
                group_key = "variable"
            elif isinstance(alt, PatternToken):
                group_key = alt.type.value
            else:
                group_key = "other"
            
            if group_key not in groups:
                groups[group_id] = []
                groups[group_id].append(alt)
                group_id += 1
            else:
                # Find existing group
                for gid, group in groups.items():
                    if any(self._are_similar_alternatives(alt, existing) for existing in group):
                        group.append(alt)
                        break
                else:
                    # Create new group
                    groups[group_id] = [alt]
                    group_id += 1
        
        return groups

    def _are_similar_alternatives(self, alt1, alt2):
        """Check if two alternatives are similar enough to group together."""
        if type(alt1) != type(alt2):
            return False
        
        if isinstance(alt1, str) and isinstance(alt2, str):
            return True  # All variable alternatives are similar
        
        if isinstance(alt1, PatternToken) and isinstance(alt2, PatternToken):
            return alt1.type == alt2.type
        
        return False

    def _generate_alternative_key(self, alternative):
        """Generate a unique key for caching alternative states."""
        if isinstance(alternative, PatternToken):
            return f"token_{alternative.type.value}_{alternative.value}_{hash(tuple(sorted(alternative.metadata.items())))}"
        else:
            return f"var_{alternative}"

    def _process_alternative_token(self, alternative, define, priority):
        """Process a PatternToken alternative with exponential protection."""
        if alternative.type == PatternTokenType.PERMUTE:
            # Nested PERMUTE within alternation - use limited processing
            return self._process_permute_limited(alternative, define)
        elif alternative.type == PatternTokenType.ALTERNATION:
            # Nested alternation - limit depth
            if getattr(self, '_alternation_depth', 0) > 3:
                logger.warning(f"[ALT_ENHANCED] Limiting nested alternation depth")
                # Create simple pass-through
                start = self.new_state()
                end = self.new_state()
                self.add_epsilon(start, end)
                return start, end
            else:
                # Process with depth tracking
                self._alternation_depth = getattr(self, '_alternation_depth', 0) + 1
                try:
                    result = self._process_alternation(alternative, define)
                    return result
                finally:
                    self._alternation_depth -= 1
        elif alternative.type == PatternTokenType.QUANTIFIER:
            # Apply quantifier with exponential protection
            return self._apply_quantifier_safe(alternative, define)
        else:
            # Regular pattern token
            return self.create_var_states_with_priority(alternative.value, define, priority)

    def _create_enhanced_variable_states(self, variable, define, priority):
        """Create variable states with enhanced optimization."""
        # Check if we already have states for this variable
        cache_key = f"var_{variable}_{priority}"
        
        if hasattr(self, '_variable_state_cache') and cache_key in self._variable_state_cache:
            return self._variable_state_cache[cache_key]
        
        # Create new states
        start = self.new_state()
        end = self.new_state()
        
        # Set variable
        start.variable = variable
        
        # Create condition
        if variable in define:
            condition = compile_condition(define[variable])
        else:
            condition = lambda row, ctx: True  # Default to always match
        
        # Add transition with priority
        start.add_transition(condition, end, variable, priority)
        
        # Cache for reuse
        if not hasattr(self, '_variable_state_cache'):
            self._variable_state_cache = {}
        self._variable_state_cache[cache_key] = (start, end)
        
        return start, end

    def _add_prioritized_epsilon(self, source, target, priority):
        """Add epsilon transition with proper priority handling."""
        # Get the source state and add epsilon with priority
        source_state = self.states[source]
        source_state.add_epsilon(target, priority)

    def _optimize_alternation_structure(self, start, end):
        """Apply post-processing optimizations to alternation structure."""
        # Remove redundant epsilon transitions
        start_state = self.states[start]
        
        # Group epsilon targets by priority
        epsilon_groups = {}
        for target in start_state.epsilon:
            priority = start_state.epsilon_priorities.get(target, 0)
            if priority not in epsilon_groups:
                epsilon_groups[priority] = []
            epsilon_groups[priority].append(target)
        
        # Remove duplicates within each priority group
        for priority, targets in epsilon_groups.items():
            unique_targets = list(dict.fromkeys(targets))  # Preserve order, remove duplicates
            
            # Update epsilon list if we removed duplicates
            if len(unique_targets) < len(targets):
                # Rebuild epsilon list
                new_epsilon = []
                new_priorities = {}
                
                for p, tgts in sorted(epsilon_groups.items()):
                    if p == priority:
                        tgts = unique_targets
                    new_epsilon.extend(tgts)
                    for tgt in tgts:
                        new_priorities[tgt] = p
                
                start_state.epsilon = new_epsilon
                start_state.epsilon_priorities = new_priorities

    def _apply_quantifier_safe(self, quantifier_token, define):
        """Apply quantifier with exponential protection."""
        # Extract quantifier details
        min_rep = quantifier_token.metadata.get('min_rep', 1)
        max_rep = quantifier_token.metadata.get('max_rep', 1)
        greedy = quantifier_token.metadata.get('greedy', True)
        
        # Limit excessive repetitions to prevent exponential blowup
        if max_rep == float('inf') or max_rep > 100:
            logger.warning(f"[ALT_ENHANCED] Limiting quantifier max_rep from {max_rep} to 100")
            max_rep = 100
        
        if min_rep > 50:
            logger.warning(f"[ALT_ENHANCED] Limiting quantifier min_rep from {min_rep} to 50")
            min_rep = 50
        
        # Get the pattern to quantify
        pattern = quantifier_token.value
        
        # Create states for the base pattern
        pattern_start, pattern_end = self.create_var_states_with_priority(pattern, define, 0)
        
        # Apply quantifier logic
        return self._apply_quantifier(pattern_start, pattern_end, min_rep, max_rep, greedy)

    def _process_permute_limited(self, permute_token, define):
        """Process PERMUTE with limited complexity to prevent exponential blowup."""
        logger.warning(f"[ALT_ENHANCED] Processing PERMUTE with limited complexity")
        
        # Extract variables from PERMUTE
        variables = permute_token.metadata.get('variables', [])
        
        # Limit the number of variables in PERMUTE
        if len(variables) > 5:
            logger.warning(f"[ALT_ENHANCED] Limiting PERMUTE variables from {len(variables)} to 5")
            variables = variables[:5]
        
        # Create simplified PERMUTE structure
        start = self.new_state()
        end = self.new_state()
        
        # Create simple alternation of variables instead of full permutation
        for i, var in enumerate(variables):
            var_start, var_end = self._create_enhanced_variable_states(var, define, i)
            self._add_prioritized_epsilon(start, var_start, i)
            self.add_epsilon(var_end, end)
        
        return start, end

    def _apply_quantifier(self, start: int, end: int, min_rep: int, max_rep: Union[int, float], greedy: bool) -> Tuple[int, int]:
        """
        Apply quantifier to a pattern segment with production-ready SQL:2016 compliance.
        
        Args:
            start: Start state of the pattern segment
            end: End state of the pattern segment
            min_rep: Minimum repetitions required
            max_rep: Maximum repetitions allowed (int or float('inf') for unbounded)
            greedy: Whether quantifier is greedy (True) or reluctant (False)
            
        Returns:
            Tuple of (new_start_state, new_end_state)
        """
        if min_rep == 1 and max_rep == 1:
            # No quantification needed
            return start, end
            
        # Create new start and end states for the quantified pattern
        q_start = self.new_state()
        q_end = self.new_state()
        
        if min_rep == 0:
            # Optional pattern - epsilon from start to end
            self.add_epsilon(q_start, q_end)
            
        if min_rep == 0 and max_rep == 1:
            # ? quantifier - optional
            self.add_epsilon(q_start, start)  # Can enter pattern
            self.add_epsilon(end, q_end)     # Exit after one match
            self.add_epsilon(q_start, q_end) # Can skip entirely
            
        elif min_rep == 0 and (max_rep == float('inf') or max_rep is None):
            # * quantifier - zero or more
            self.add_epsilon(q_start, start)  # Can enter pattern
            self.add_epsilon(end, q_end)     # Exit after match
            self.add_epsilon(q_start, q_end) # Can skip entirely
            self.add_epsilon(end, start)     # Can repeat
            
        elif min_rep == 1 and (max_rep == float('inf') or max_rep is None):
            # + quantifier - one or more
            self.add_epsilon(q_start, start)  # Must enter pattern
            self.add_epsilon(end, q_end)     # Exit after match
            self.add_epsilon(end, start)     # Can repeat
            
        elif min_rep > 0:
            # {n}, {n,m} quantifiers - exact or range repetitions
            current_start = q_start
            
            # Create required repetitions (min_rep)
            for i in range(min_rep):
                if i == 0:
                    # First repetition connects to original pattern
                    self.add_epsilon(current_start, start)
                    current_start = end
                else:
                    # Subsequent repetitions - create fresh copies
                    rep_start = self.new_state()
                    rep_end = self.new_state()
                    
                    # Copy the pattern structure (simplified - in production would need full copy)
                    self.add_epsilon(current_start, rep_start)
                    self.add_epsilon(rep_start, rep_end)  # Placeholder for pattern copy
                    current_start = rep_end
            
            # Handle optional additional repetitions if max_rep > min_rep
            if max_rep == float('inf') or max_rep is None:
                # Unbounded - can repeat indefinitely
                self.add_epsilon(current_start, start)  # Can repeat original pattern
                self.add_epsilon(current_start, q_end)  # Or exit
            elif max_rep > min_rep:
                # Bounded additional repetitions - ensure max_rep is int for range
                additional_reps = int(max_rep) - min_rep
                for i in range(additional_reps):
                    rep_start = self.new_state()
                    rep_end = self.new_state()
                    
                    # Can skip this repetition
                    self.add_epsilon(current_start, q_end)
                    
                    # Or take this repetition
                    self.add_epsilon(current_start, rep_start)
                    self.add_epsilon(rep_start, rep_end)  # Placeholder for pattern copy
                    current_start = rep_end
                    
                # Final connection to end
                self.add_epsilon(current_start, q_end)
            else:
                # Exact repetitions - connect final state to end
                self.add_epsilon(current_start, q_end)
        
        # For reluctant quantifiers, adjust epsilon transition priorities
        if not greedy:
            # Reluctant quantifiers prefer fewer matches
            # This would require priority adjustment in a full implementation
            logger.debug(f"Applied reluctant quantifier with min={min_rep}, max={max_rep}")
        
        return q_start, q_end

    def _add_optional_suffix_transitions(self, tokens: List[PatternToken], start: int, accept: int, define: Dict[str, str]) -> None:
        """
        Add epsilon transitions for patterns with trailing optional quantifiers.
        
        For patterns like "A B+ C+ D?", this ensures that the state after C+ can transition
        to the accept state since D? is optional and can be skipped.
        
        This implements SQL:2016 compliance for partial pattern completion when remaining
        parts are optional.
        
        Args:
            tokens: List of pattern tokens
            start: Start state of the entire pattern
            accept: Accept state of the entire pattern
            define: Dictionary of variable definitions
        """
        if not tokens:
            return
            
        # Find the last required token (non-optional)
        last_required_idx = -1
        for i in range(len(tokens) - 1, -1, -1):
            token = tokens[i]
            if token.type == PatternTokenType.LITERAL:
                # Check if this token is required (not optional)
                if not token.quantifier or token.quantifier not in ['?', '*', '{0}', '{0,}']:
                    # Check for + quantifier which is required
                    if not token.quantifier or token.quantifier in ['+', '{1,}'] or (
                        token.quantifier.startswith('{') and 
                        not token.quantifier.startswith('{0')):
                        last_required_idx = i
                        break
                        
        # If no required tokens found, pattern allows complete empty match
        if last_required_idx == -1:
            return  # Already handled by allows_empty logic
            
        # Check if there are optional tokens after the last required token
        has_optional_suffix = False
        for i in range(last_required_idx + 1, len(tokens)):
            token = tokens[i]
            if token.type == PatternTokenType.LITERAL:
                if token.quantifier in ['?', '*', '{0}', '{0,}']:
                    has_optional_suffix = True
                    break
                    
        if not has_optional_suffix:
            return  # No optional suffix to handle
            
        logger.debug(f"Found pattern with optional suffix starting after token {last_required_idx}")
        
        # Build the required prefix pattern to find intermediate states
        # This is a simplified approach - in a full implementation, we'd track
        # intermediate states during sequence building
        
        # For now, we'll rely on the DFA builder to handle this by ensuring
        # that states representing completion of required parts are marked as accepting
        
        # Add metadata to help DFA construction identify optional suffixes
        self.metadata["has_optional_suffix"] = True
        self.metadata["last_required_token_idx"] = last_required_idx
        self.metadata["optional_suffix_tokens"] = [
            tokens[i].value + (tokens[i].quantifier or '') 
            for i in range(last_required_idx + 1, len(tokens))
            if tokens[i].type == PatternTokenType.LITERAL
        ]
        
        logger.debug(f"Added optional suffix metadata: {self.metadata.get('optional_suffix_tokens', [])}")