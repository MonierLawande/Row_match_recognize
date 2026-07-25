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
- PERMUTE pattern support with minimal matching

Author: Pattern Matching Engine Team
Version: 3.0.0 (Production Ready)
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
from functools import lru_cache

from src.matcher.automata import NFA, NFAState, Transition, NFABuilder
from src.matcher.pattern_tokenizer import PatternTokenType, PermuteHandler
from src.utils.logging_config import get_logger, PerformanceTimer
from src.utils.memory_management import get_resource_manager, MemoryMonitor
from src.utils.pattern_cache import get_pattern_cache
from src.utils.resource_profile import (
    AdaptiveResourceProfile,
    MIB,
    EffectiveMemorySnapshot,
    SystemMemoryProbe,
    get_adaptive_resource_profile,
)

# Module logger
logger = get_logger(__name__)

# Constants
FAIL_STATE = -1
MAX_OPTIMIZATION_ITERATIONS = 100
DFA_COMPILER_SCHEMA_VERSION = 2

@dataclass(frozen=True)
class DFAAdaptiveMemoryPolicy:
    """Continuously derive a safe DFA state ceiling from effective memory.

    The byte budget is intentionally conservative because a DFA state owns
    Python objects, an NFA subset, transitions, map entries, and queue entries.
    The defaults reserve host/container headroom, give compilation at most ten
    percent of effective memory, and assume 64 KiB per reachable DFA state.
    Deployments may provide a different policy after measuring their patterns.
    """

    reserve_fraction: float = 0.10
    reserve_floor_bytes: int = 512 * MIB
    available_fraction: float = 0.25
    total_fraction: float = 0.10
    estimated_bytes_per_state: int = 64 * 1024
    # An administrator may set a ceiling for multi-tenant deployments.  The
    # default is deliberately uncapped: effective memory is the physical
    # ceiling, so larger containers continue to receive a larger budget.
    hard_max_states: Optional[int] = None
    minimum_states: int = 1_000
    iteration_multiplier: int = 2

    def __post_init__(self) -> None:
        for field_name in (
            'reserve_fraction',
            'available_fraction',
            'total_fraction',
        ):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between 0 and 1")
        for field_name in (
            'estimated_bytes_per_state',
            'minimum_states',
            'iteration_multiplier',
        ):
            if getattr(self, field_name) < 1:
                raise ValueError(f"{field_name} must be at least 1")
        if self.hard_max_states is not None and self.hard_max_states < 1:
            raise ValueError("hard_max_states must be at least 1 when set")
        if self.reserve_floor_bytes < 0:
            raise ValueError("reserve_floor_bytes cannot be negative")

    def resolve(
        self,
        memory: EffectiveMemorySnapshot,
    ) -> 'ResolvedDFAStateBudget':
        available = memory.effective_available_bytes
        effective_limit = memory.effective_limit_bytes

        requested_reserve = max(
            self.reserve_floor_bytes,
            int(effective_limit * self.reserve_fraction),
        )
        # Under heavy pressure, retain at least half the current availability
        # for the application and other Python allocations.
        reserve = min(requested_reserve, available // 2)
        post_reserve = max(0, available - reserve)

        budget = min(
            int(post_reserve * self.available_fraction),
            int(effective_limit * self.total_fraction),
        )

        memory_bound_states = budget // self.estimated_bytes_per_state
        if (
            memory_bound_states < self.minimum_states
            and post_reserve
            >= self.minimum_states * self.estimated_bytes_per_state
        ):
            memory_bound_states = self.minimum_states

        max_states = max(1, memory_bound_states)
        if self.hard_max_states is not None:
            max_states = min(max_states, self.hard_max_states)
        max_iterations = max(
            100_000,
            max_states * self.iteration_multiplier,
        )
        return ResolvedDFAStateBudget(
            max_states=max_states,
            max_iterations=max_iterations,
            memory_budget_bytes=budget,
            reserved_headroom_bytes=reserve,
            estimated_bytes_per_state=self.estimated_bytes_per_state,
            memory=memory,
        )


@dataclass(frozen=True)
class ResolvedDFAStateBudget:
    """A frozen adaptive budget used for one complete DFA compilation."""

    max_states: int
    max_iterations: int
    memory_budget_bytes: int
    reserved_headroom_bytes: int
    estimated_bytes_per_state: int
    memory: EffectiveMemorySnapshot


@dataclass(frozen=True)
class DFAConstructionLimits:
    """Resource limits for complete NFA-to-DFA subset construction.

    ``max_states`` and ``max_iterations`` are fail-closed limits.  Reaching
    either limit raises :class:`DFAConstructionLimitError`; the builder never
    returns the states constructed so far.  ``subset_warning_threshold`` is
    diagnostic only.  NFA-state subsets and epsilon closures are never
    truncated because doing so changes the language recognized by the DFA.
    """

    max_states: int
    max_iterations: int = 100_000
    subset_warning_threshold: int = 50

    def __post_init__(self) -> None:
        if self.max_states < 1:
            raise ValueError("max_states must be at least 1")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if self.subset_warning_threshold < 1:
            raise ValueError("subset_warning_threshold must be at least 1")


class DFAConstructionError(ValueError):
    """Base error for DFA compilation failures.

    This is a ``ValueError`` because the requested pattern cannot be compiled
    under the configured engine resources.  Keeping a dedicated type lets API
    callers distinguish compilation failure from an empty match result.
    """


class DFAConstructionLimitError(DFAConstructionError):
    """Raised when complete determinization would exceed a configured limit."""

    def __init__(
        self,
        *,
        reason: str,
        limit: int,
        observed: int,
        states_created: int,
        iterations: int,
        pending_subsets: int,
        nfa_state_count: int,
    ) -> None:
        self.reason = reason
        self.limit = limit
        self.observed = observed
        self.states_created = states_created
        self.iterations = iterations
        self.pending_subsets = pending_subsets
        self.nfa_state_count = nfa_state_count
        super().__init__(
            "Complete DFA construction exceeded the "
            f"{reason} ({observed} > {limit}); "
            f"states_created={states_created}, iterations={iterations}, "
            f"pending_subsets={pending_subsets}, "
            f"source_nfa_states={nfa_state_count}. "
            "No partial automaton was returned or cached."
        )


@dataclass
class DFAState:
    """
    Production-ready DFA state with comprehensive pattern matching support.
    
    This class represents a deterministic state constructed from a set of NFA states
    using subset construction. Includes comprehensive metadata tracking and validation.
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
        
        self._lock = threading.RLock()
        self._validated = False
        self.creation_time = time.time()
        self.access_count = 0
        
        if not self.validate():
            raise ValueError("DFA state validation failed")

    def __del__(self):
        """Cleanup resources to prevent memory leaks"""
        try:
            if hasattr(self, 'transitions'):
                self.transitions.clear()
            if hasattr(self, 'permute_data') and self.permute_data:
                self.permute_data.clear()
            if hasattr(self, 'variables'):
                self.variables.clear()
            if hasattr(self, 'excluded_variables'):
                self.excluded_variables.clear()
            if hasattr(self, 'subset_vars'):
                self.subset_vars.clear()
        except Exception:
            pass  # Ignore errors during cleanup

    def add_transition(self, condition: Any, target: int, variable: Optional[str] = None, 
                      priority: int = 0, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a transition with enhanced validation and priority support."""
        with self._lock:
            if target < 0:
                raise ValueError(f"Invalid target state index: {target}")
            
            if not callable(condition):
                raise TypeError("Condition must be callable")
            
            # Validate condition function signature
            if not self._validate_condition_function(condition):
                logger.warning("Condition function may have invalid signature")
            
            transition = Transition(
                condition=condition,
                target=target,
                variable=variable,
                priority=priority,
                metadata=metadata or {}
            )
            
            self.transitions.append(transition)
            self.access_count += 1

    def _validate_condition_function(self, condition: Callable) -> bool:
        """Validate condition function safety"""
        import inspect
        try:
            sig = inspect.signature(condition)
            params = list(sig.parameters.keys())
            return len(params) >= 2  # At least row, context parameters
        except Exception:
            return True  # Allow if we can't validate

    def validate(self) -> bool:
        """Validate DFA state integrity."""
        try:
            if not self.nfa_states:
                return False
            
            if any(not isinstance(idx, int) or idx < 0 for idx in self.nfa_states):
                return False
            
            if not isinstance(self.transitions, list):
                return False
            
            for trans in self.transitions:
                if not isinstance(trans, Transition):
                    return False
                if trans.target < 0:
                    return False
                if not callable(trans.condition):
                    return False
            
            # Validate PERMUTE metadata if present
            if self.permute_data:
                required_fields = {'combinations', 'variables'}
                if not any(field in self.permute_data for field in required_fields):
                    logger.debug(f"PERMUTE metadata may be incomplete in state {self.state_id}")
            
            self._validated = True
            return True
            
        except Exception as e:
            logger.error(f"DFA state validation failed: {e}")
            return False

    def get_transitions_for_variable(self, variable: str) -> List[Transition]:
        """Get all transitions for a specific variable."""
        with self._lock:
            return [t for t in self.transitions if t.variable == variable]

    def has_variable(self, variable: str) -> bool:
        """Check if this state handles a specific variable."""
        return variable in self.variables

    def is_excluded_variable(self, variable: str) -> bool:
        """Check if a variable is excluded in this state."""
        return variable in self.excluded_variables

    def get_debug_info(self) -> Dict[str, Any]:
        """Get comprehensive debug information."""
        return {
            'state_id': self.state_id,
            'nfa_states': sorted(self.nfa_states),
            'is_accept': self.is_accept,
            'transition_count': len(self.transitions),
            'variables': sorted(self.variables),
            'excluded_variables': sorted(self.excluded_variables),
            'priority': self.priority,
            'is_anchor': self.is_anchor,
            'anchor_type': self.anchor_type.name if self.anchor_type else None,
            'permute_data': self.permute_data,
            'access_count': self.access_count,
            'creation_time': self.creation_time
        }


class DFA:
    """
    Production-ready Deterministic Finite Automaton for pattern matching.
    
    Supports complex SQL:2016 pattern constructs including PERMUTE patterns,
    quantifiers, anchors, and exclusions with comprehensive optimization.
    """
    
    def __init__(
        self,
        states: List[DFAState],
        start: int = 0,
        exclusion_ranges: Optional[Dict[str, Set[str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        resource_profile: Optional[AdaptiveResourceProfile] = None,
    ):
        """
        Initialize DFA with comprehensive validation.
        
        Args:
            states: List of DFA states
            start: Index of start state
            exclusion_ranges: Variable exclusion mappings
            metadata: Additional metadata
        """
        if not states:
            raise ValueError("DFA must have at least one state")
        
        if not (0 <= start < len(states)):
            raise ValueError(f"Invalid start state index: {start}")
        
        self.states = states
        self.start = start
        self.exclusion_ranges = exclusion_ranges or {}
        self.metadata = metadata or {}
        self._resource_profile = resource_profile
        
        # Performance tracking
        self._match_count = 0
        self._optimization_level = 0
        self._lock = threading.RLock()
        
        # Memory monitoring (use resource manager for proper lifecycle)
        self._resource_manager = get_resource_manager()
        self._pattern_cache = get_pattern_cache()
        
        # Validate on creation
        if not self.validate_pattern():
            raise ValueError("DFA validation failed")

    def __del__(self):
        """Cleanup DFA resources to prevent memory leaks"""
        try:
            if hasattr(self, 'states'):
                for state in self.states:
                    if hasattr(state, '__del__'):
                        del state
                self.states.clear()
            if hasattr(self, 'metadata'):
                self.metadata.clear()
            if hasattr(self, 'exclusion_ranges'):
                self.exclusion_ranges.clear()
        except Exception:
            pass  # Ignore cleanup errors

    def validate_pattern(self) -> bool:
        """Comprehensive DFA validation."""
        try:
            # Builder-produced automata explicitly mark an in-progress build
            # as incomplete.  Such an object must never become executable.
            # Metadata-free hand-built DFAs remain valid for low-level tests.
            if self.metadata.get('construction_complete') is False:
                logger.error("DFA construction is marked incomplete")
                return False

            # Basic structure validation
            if not self.states or self.start < 0 or self.start >= len(self.states):
                return False
            
            # Validate all states
            for i, state in enumerate(self.states):
                if not state.validate():
                    logger.error(f"State {i} validation failed")
                    return False
                
                # Validate transitions point to valid states
                for trans in state.transitions:
                    if trans.target >= len(self.states):
                        logger.error(f"Invalid transition target: {trans.target}")
                        return False
            
            # Check for at least one accept state
            has_accept = any(state.is_accept for state in self.states)
            if not has_accept:
                logger.warning("DFA has no accepting states")
            
            return True
            
        except Exception as e:
            logger.error(f"DFA validation error: {e}")
            return False

    def optimize(self) -> None:
        """Apply comprehensive DFA optimizations."""
        with self._lock:
            logger.info("Starting DFA optimization")
            
            # Check memory pressure before optimization
            resource_manager = get_resource_manager()
            pressure_info = resource_manager.get_memory_pressure_info()
            if pressure_info.is_under_pressure:
                logger.warning("High memory pressure detected, skipping optimization")
                return
            
            # Track optimization iterations
            iterations = 0
            max_iterations = MAX_OPTIMIZATION_ITERATIONS
            
            while iterations < max_iterations:
                initial_state_count = len(self.states)
                
                # Apply optimization passes with error handling
                try:
                    self._remove_unreachable_states()
                    self._merge_equivalent_states()
                    self._optimize_transitions()
                except Exception as e:
                    logger.warning(f"Optimization error at iteration {iterations}: {e}")
                    break
                
                # Check for convergence
                if len(self.states) == initial_state_count:
                    break
                    
                iterations += 1
                
                # Check memory pressure during optimization
                pressure_info = self._resource_manager.get_memory_pressure_info()
                if pressure_info.is_under_pressure:
                    logger.warning("Memory pressure detected during optimization, stopping early")
                    break
            
            self._optimization_level = iterations
            logger.info(f"DFA optimization completed in {iterations} iterations: "
                       f"{len(self.states)} states")

    def _remove_unreachable_states(self) -> None:
        """Remove states that cannot be reached from start state."""
        reachable = set()
        queue = deque([self.start])
        reachable.add(self.start)
        
        while queue:
            current = queue.popleft()
            for trans in self.states[current].transitions:
                if trans.target not in reachable:
                    reachable.add(trans.target)
                    queue.append(trans.target)
        
        # Create mapping from old to new indices
        old_to_new = {}
        new_states = []
        
        for old_idx in sorted(reachable):
            new_idx = len(new_states)
            old_to_new[old_idx] = new_idx
            new_states.append(self.states[old_idx])
        
        # Update transition targets by creating new transitions (since Transition is frozen)
        for state in new_states:
            new_transitions = []
            for trans in state.transitions:
                # Create new transition with updated target
                new_trans = Transition(
                    condition=trans.condition,
                    target=old_to_new[trans.target],
                    variable=trans.variable,
                    priority=trans.priority,
                    metadata=trans.metadata
                )
                new_transitions.append(new_trans)
            # Replace transitions list
            state.transitions = new_transitions
        
        # Update start state
        self.start = old_to_new[self.start]
        self.states = new_states
        
        logger.debug(f"Removed {len(self.states) - len(new_states)} unreachable states")

    def _merge_equivalent_states(self) -> None:
        """Merge states that are equivalent in behavior."""
        # Simple implementation - can be enhanced with more sophisticated algorithms
        merged_count = 0
        
        for i in range(len(self.states)):
            for j in range(i + 1, len(self.states)):
                if self._are_states_equivalent(i, j):
                    self._merge_states(i, j)
                    merged_count += 1
        
        if merged_count > 0:
            logger.debug(f"Merged {merged_count} equivalent state pairs")

    def _are_states_equivalent(self, i: int, j: int) -> bool:
        """Check if two states are equivalent."""
        state_i, state_j = self.states[i], self.states[j]
        
        # Basic equivalence check
        if (state_i.is_accept != state_j.is_accept or
            state_i.variables != state_j.variables or
            len(state_i.transitions) != len(state_j.transitions)):
            return False
        
        # Could be enhanced with more sophisticated equivalence checking
        return False

    def _merge_states(self, i: int, j: int) -> None:
        """Merge state j into state i."""
        # Update all transitions pointing to j to point to i
        for state in self.states:
            new_transitions = []
            for trans in state.transitions:
                if trans.target == j:
                    # Create new transition with updated target
                    new_trans = Transition(
                        condition=trans.condition,
                        target=i,
                        variable=trans.variable,
                        priority=trans.priority,
                        metadata=trans.metadata
                    )
                    new_transitions.append(new_trans)
                else:
                    new_transitions.append(trans)
            # Replace transitions list
            state.transitions = new_transitions

    def _optimize_transitions(self) -> None:
        """Optimize transitions within each state."""
        for state in self.states:
            # Group transitions by variable and merge compatible ones
            var_groups = defaultdict(list)
            for trans in state.transitions:
                var_groups[trans.variable].append(trans)
            
            # Rebuild transition list with optimizations
            new_transitions = []
            for var, trans_list in var_groups.items():
                if len(trans_list) == 1:
                    new_transitions.extend(trans_list)
                else:
                    # Could merge compatible transitions
                    new_transitions.extend(trans_list)
            
            state.transitions = new_transitions

    def get_debug_info(self) -> Dict[str, Any]:
        """Get comprehensive DFA debug information."""
        return {
            'state_count': len(self.states),
            'start_state': self.start,
            'accept_states': [i for i, s in enumerate(self.states) if s.is_accept],
            'total_transitions': sum(len(s.transitions) for s in self.states),
            'optimization_level': self._optimization_level,
            'match_count': self._match_count,
            'metadata': self.metadata,
            'exclusion_ranges': self.exclusion_ranges
        }


class DFABuilder:
    """
    Production-ready DFA builder with comprehensive optimizations and PERMUTE support.
    
    This builder converts NFA to DFA using subset construction with:
    - Exponential state explosion protection
    - Priority-aware construction for PERMUTE patterns
    - Advanced caching and optimization
    - Comprehensive error handling
    """

    def __init__(
        self,
        nfa: NFA,
        limits: Optional[DFAConstructionLimits] = None,
        memory_policy: Optional[DFAAdaptiveMemoryPolicy] = None,
        memory_probe: Optional[SystemMemoryProbe] = None,
        resource_profile: Optional[AdaptiveResourceProfile] = None,
    ):
        """Initialize DFA builder with validation."""
        if not isinstance(nfa, NFA):
            raise TypeError(f"Expected NFA instance, got {type(nfa)}")
        
        if not nfa.validate():
            raise ValueError("Source NFA validation failed")
        
        self.nfa = nfa
        self._resource_profile = resource_profile
        if self._resource_profile is None and memory_probe is None:
            self._resource_profile = (
                getattr(nfa, '_resource_profile', None)
                or get_adaptive_resource_profile()
            )
        if memory_policy is not None:
            self._memory_policy = memory_policy
        else:
            # The DFA remains a fraction of effective host/cgroup memory, and
            # also respects the same query ceiling used by the matcher.  An
            # injected probe is kept deterministic for low-level tests and
            # embedders; callers may pass an explicit resource profile when
            # they want both controls.
            profile = self._resource_profile
            if profile is not None:
                profile.require_query_capacity()
            hard_max_states = (
                None
                if profile is None
                else max(
                    1,
                    profile.query_budget_bytes // (64 * 1024),
                )
            )
            self._memory_policy = DFAAdaptiveMemoryPolicy(
                hard_max_states=hard_max_states,
            )
        self._memory_probe = memory_probe or SystemMemoryProbe()
        self._resolved_memory_budget: Optional[ResolvedDFAStateBudget] = None

        # Explicit limits always win.  Otherwise sample one continuous,
        # container-aware memory budget and freeze it for this compilation.
        if limits is not None:
            self.limits = limits
            limit_metadata = {
                'mode': 'explicit',
                'max_states': limits.max_states,
                'max_iterations': limits.max_iterations,
            }
        else:
            max_states = self._calculate_max_states()
            resolved = self._resolved_memory_budget
            max_iterations = (
                resolved.max_iterations
                if resolved is not None
                else max(100_000, max_states * 2)
            )
            self.limits = DFAConstructionLimits(
                max_states=max_states,
                max_iterations=max_iterations,
            )
            limit_metadata = self._adaptive_limit_metadata()

        # Keep the historical attributes for callers that inspect builder
        # statistics.  MAX_SUBSET_SIZE is now a warning threshold only.
        self.MAX_DFA_STATES = self.limits.max_states
        self.MAX_SUBSET_SIZE = self.limits.subset_warning_threshold
        self.MAX_ITERATIONS = self.limits.max_iterations
        
        # Caching and optimization with thread safety using existing utilities
        self._cache_lock = threading.RLock()
        self._pattern_cache = get_pattern_cache()
        self._subset_cache = {}
        self._transition_cache = {}
        self._state_dedup_cache = {}
        
        # Performance tracking
        self._build_start_time = None
        self._iteration_count = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._states_created = 0
        self._states_merged = 0
        
        # Memory monitoring using existing utility
        self._memory_monitor = MemoryMonitor()
        self._resource_manager = get_resource_manager()
        
        # Copy metadata from NFA
        self.metadata = self.nfa.metadata.copy() if self.nfa.metadata else {}
        self.metadata.update({
            'builder_version': '3.0.0',
            'compiler_schema_version': DFA_COMPILER_SCHEMA_VERSION,
            'source_nfa_states': len(nfa.states),
            'construction_method': 'subset_construction_with_priorities',
            'exponential_protection': True,
            'construction_complete': False,
            'construction_limits': limit_metadata,
        })
        
        # Threading support
        self._lock = threading.RLock()
        
        logger.debug(f"DFABuilder initialized for NFA with {len(nfa.states)} states")

    def _calculate_max_states(self) -> int:
        """Resolve a continuous state budget from effective available memory."""
        if self._resource_profile is not None:
            self._resolved_memory_budget = self._memory_policy.resolve(
                self._resource_profile.memory
            )
            return self._resolved_memory_budget.max_states
        try:
            memory = self._memory_probe.snapshot()
            self._resolved_memory_budget = self._memory_policy.resolve(memory)
            return self._resolved_memory_budget.max_states
        except Exception as error:
            raise DFAConstructionError(
                "Unable to resolve a safe DFA memory budget. Supply an "
                "explicit DFAConstructionLimits value when resource discovery "
                "is unavailable."
            ) from error

    def _adaptive_limit_metadata(self) -> Dict[str, Any]:
        resolved = self._resolved_memory_budget
        if resolved is None:
            return {
                'mode': 'unresolved',
            }

        memory = resolved.memory
        return {
            'mode': 'adaptive_memory',
            'policy_version': 1,
            'max_states': resolved.max_states,
            'max_iterations': resolved.max_iterations,
            'memory_budget_bytes': resolved.memory_budget_bytes,
            'reserved_headroom_bytes': resolved.reserved_headroom_bytes,
            'estimated_bytes_per_state':
                resolved.estimated_bytes_per_state,
            'effective_memory_limit_bytes':
                memory.effective_limit_bytes,
            'effective_memory_available_bytes':
                memory.effective_available_bytes,
            'memory_source': memory.source,
            'hard_max_states': self._memory_policy.hard_max_states,
        }

    def __del__(self):
        """Cleanup builder resources to prevent memory leaks"""
        try:
            if hasattr(self, '_subset_cache'):
                self._subset_cache.clear()
            if hasattr(self, '_transition_cache'):
                self._transition_cache.clear()
            if hasattr(self, '_state_dedup_cache'):
                self._state_dedup_cache.clear()
        except Exception:
            pass  # Ignore cleanup errors

    def build(self) -> DFA:
        """
        Build a complete optimized DFA from the source NFA.

        Construction is transactional from the caller's perspective.  The
        method returns only after every reachable DFA subset has been
        expanded.  Resource limits and internal compilation failures raise a
        typed error instead of returning a partial automaton.
        
        Returns:
            DFA: Optimized deterministic finite automaton
            
        Raises:
            DFAConstructionLimitError: If complete construction exceeds a
                configured resource limit
            DFAConstructionError: If construction cannot preserve semantics
            ValueError: If the resulting complete DFA is invalid
        """
        self._build_start_time = time.time()
        
        try:
            with self._lock:
                # A builder may be retried after a failed resource check.
                # Reset per-build counters so diagnostics and limits describe
                # only the current transactional construction attempt.
                self._iteration_count = 0
                self._cache_hits = 0
                self._cache_misses = 0
                self._states_created = 0
                self._states_merged = 0
                self.metadata['construction_complete'] = False

                logger.info(f"Starting DFA construction from NFA with {len(self.nfa.states)} states")
                
                # Initialize data structures
                dfa_states: List[DFAState] = []
                state_map: Dict[FrozenSet[int], int] = {}
                queue = deque()
                
                # Create initial state from epsilon closure of NFA start state
                start_closure = self.nfa.epsilon_closure([self.nfa.start])
                start_set = frozenset(start_closure)
                
                logger.debug(f"Start state epsilon closure: {sorted(start_closure)}")
                
                # Create and add initial DFA state
                initial_dfa_state = self._create_dfa_state(start_set)
                dfa_states.append(initial_dfa_state)
                state_map[start_set] = 0
                queue.append((start_set, 0))
                
                self._states_created += 1
                
                # Process every reachable subset.  A limit failure aborts the
                # build; it never converts the current prefix into a DFA.
                while queue:
                    if self._iteration_count >= self.MAX_ITERATIONS:
                        raise self._limit_error(
                            reason='iteration_limit',
                            limit=self.MAX_ITERATIONS,
                            observed=self._iteration_count + 1,
                            states_created=len(dfa_states),
                            pending_subsets=len(queue),
                        )

                    self._iteration_count += 1

                    nfa_states, dfa_state_idx = queue.popleft()
                    
                    # A large subset is valid and must remain intact.  The
                    # threshold is diagnostic only.
                    if len(nfa_states) > self.MAX_SUBSET_SIZE:
                        logger.warning(
                            "Large DFA subset contains %s NFA states "
                            "(warning threshold: %s); preserving all states",
                            len(nfa_states),
                            self.MAX_SUBSET_SIZE,
                        )
                    
                    # Group transitions by variable for optimization
                    transition_groups = self._group_transitions(nfa_states)
                    
                    # Process each transition group
                    for variable, transitions in transition_groups.items():
                        try:
                            # Compute target set
                            target_set = self._compute_target_set(transitions)
                            
                            if not target_set:
                                continue  # Skip empty target sets
                            
                            # Apply epsilon closure
                            closure_result = self._safe_epsilon_closure(target_set)
                            target_closure = frozenset(closure_result)
                            
                            # Get or create target DFA state
                            target_dfa_idx = self._get_or_create_target_state(
                                target_closure, state_map, dfa_states, queue
                            )
                            
                            # Create optimized transition
                            combined_condition = self._create_combined_condition(transitions)
                            combined_priority = self._compute_combined_priority(transitions, nfa_states)
                            combined_metadata = self._create_combined_metadata(transitions)
                            
                            # Add transition to current state
                            dfa_states[dfa_state_idx].add_transition(
                                condition=combined_condition,
                                target=target_dfa_idx,
                                variable=variable,
                                priority=combined_priority,
                                metadata=combined_metadata
                            )
                            
                        except DFAConstructionError:
                            raise
                        except Exception as e:
                            raise DFAConstructionError(
                                "Failed to compile transition group "
                                f"{variable!r} from DFA state {dfa_state_idx}; "
                                "no partial automaton was returned."
                            ) from e
                
                # Reaching this point proves every queued subset was expanded.
                final_metadata = self._create_final_metadata()
                
                dfa = DFA(
                    states=dfa_states,
                    start=0,
                    exclusion_ranges=self.nfa.exclusion_ranges.copy(),
                    metadata=final_metadata,
                    resource_profile=self._resource_profile,
                )
                
                # Validate resulting DFA
                if not dfa.validate_pattern():
                    raise ValueError("Constructed DFA failed validation")
                
                # Apply optimizations
                logger.info("Applying DFA optimizations...")
                dfa.optimize()
                
                build_time = time.time() - self._build_start_time
                logger.info(f"DFA construction completed: {len(dfa_states)} states, "
                           f"{self._iteration_count} iterations, {build_time:.3f}s")
                
                return dfa
                
        except DFAConstructionLimitError as exc:
            logger.error("DFA construction limit reached: %s", exc)
            raise
        except DFAConstructionError:
            logger.exception("DFA construction stopped before completion")
            raise
        except Exception as e:
            logger.error(f"DFA construction failed: {e}")
            raise DFAConstructionError(f"DFA build failed: {e}") from e

    def _limit_error(
        self,
        *,
        reason: str,
        limit: int,
        observed: int,
        states_created: int,
        pending_subsets: int,
    ) -> DFAConstructionLimitError:
        """Create a diagnostic-rich fail-closed determinization error."""
        return DFAConstructionLimitError(
            reason=reason,
            limit=limit,
            observed=observed,
            states_created=states_created,
            iterations=self._iteration_count,
            pending_subsets=pending_subsets,
            nfa_state_count=len(self.nfa.states),
        )

    def _create_dfa_state(self, nfa_states: FrozenSet[int]) -> DFAState:
        """
        Create DFA state from NFA states with comprehensive metadata handling.
        
        Args:
            nfa_states: Set of NFA state indices
            
        Returns:
            DFAState: Newly created DFA state with full metadata
        """
        if not nfa_states:
            raise ValueError("Cannot create DFA state from empty NFA state set")
        
        # Validate NFA state indices
        for state_idx in nfa_states:
            if not (0 <= state_idx < len(self.nfa.states)):
                raise ValueError(f"Invalid NFA state index: {state_idx}")
        
        # Check if this is an accepting state
        is_accept = self.nfa.accept in nfa_states
        
        # Handle patterns with optional suffixes
        if not is_accept and self.metadata.get('has_optional_suffix', False):
            is_accept = self._can_reach_accept_via_optional_only(nfa_states)
            if is_accept:
                logger.debug(f"DFA state marked as accepting due to optional suffix completion")
        
        # Create DFA state
        state = DFAState(
            nfa_states=nfa_states,
            is_accept=is_accept,
            state_id=self._states_created
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
                        if isinstance(value, list) and isinstance(permute_data_merged[key], list):
                            permute_data_merged[key].extend(v for v in value if v not in permute_data_merged[key])
                        elif value != permute_data_merged[key]:
                            permute_data_merged[key] = [permute_data_merged[key], value]
                    else:
                        permute_data_merged[key] = value

        # Assign aggregated properties
        state.variables = all_variables
        state.excluded_variables = excluded_variables
        state.subset_vars = subset_vars
        
        # Handle anchor states
        if anchor_states:
            state.is_anchor = True
            start_anchors = [a for a in anchor_states if a[1] == PatternTokenType.ANCHOR_START]
            if start_anchors:
                state.anchor_type = PatternTokenType.ANCHOR_START
            else:
                state.anchor_type = anchor_states[0][1]
        
        # Assign PERMUTE data
        if permute_data_merged:
            state.permute_data = permute_data_merged
        
        # Calculate state priority
        state.priority = min(self.nfa.states[idx].priority for idx in nfa_states)
        
        # Preserve PERMUTE-specific priorities for minimal matching
        self._preserve_permute_state_priorities(state, nfa_states)
        
        logger.debug(f"Created DFA state {state.state_id} from NFA states {sorted(nfa_states)}: "
                    f"accept={is_accept}, variables={all_variables}, priority={state.priority}")
        
        return state

    def _preserve_permute_state_priorities(self, dfa_state: DFAState, nfa_states: FrozenSet[int]) -> None:
        """
        Preserve PERMUTE-specific priorities in DFA states for minimal matching.
        
        This method ensures that DFA states retain the priority information needed
        for minimal matching in PERMUTE patterns with optional variables.
        """
        if not (hasattr(self.nfa, 'metadata') and self.nfa.metadata.get('has_permute', False)):
            return  # Not a PERMUTE pattern
        
        # Look for epsilon priorities in the constituent NFA states
        best_epsilon_priority = float('inf')
        permute_info = {}
        
        for nfa_state_idx in nfa_states:
            if nfa_state_idx < len(self.nfa.states):
                nfa_state = self.nfa.states[nfa_state_idx]
                
                # Collect epsilon priorities
                if hasattr(nfa_state, 'epsilon_priorities') and nfa_state.epsilon_priorities:
                    logger.debug(f"NFA state {nfa_state_idx} has epsilon priorities: {nfa_state.epsilon_priorities}")
                    
                    for target, priority in nfa_state.epsilon_priorities.items():
                        best_epsilon_priority = min(best_epsilon_priority, priority)
                        
                        # Store information about this priority path
                        if priority not in permute_info:
                            permute_info[priority] = []
                        permute_info[priority].append((nfa_state_idx, target))
        
        # Set the DFA state priority based on the best epsilon priority
        if best_epsilon_priority != float('inf'):
            dfa_state.priority = best_epsilon_priority
            
            # Store PERMUTE-specific metadata for debugging
            if not dfa_state.permute_data:
                dfa_state.permute_data = {}
            dfa_state.permute_data['epsilon_priority'] = best_epsilon_priority
            dfa_state.permute_data['permute_paths'] = permute_info
            
            logger.debug(f"Preserved PERMUTE priority {best_epsilon_priority} for DFA state with NFA states {sorted(nfa_states)}")

    def _group_transitions(self, nfa_states: FrozenSet[int]) -> Dict[Optional[str], List[Transition]]:
        """Group NFA transitions by variable with deduplication."""
        groups = defaultdict(list)
        seen_transitions = set()
        
        for state_idx in nfa_states:
            if state_idx >= len(self.nfa.states):
                continue
                
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

    def _compute_target_set(self, transitions: List[Transition]) -> Set[int]:
        """Compute target set from transitions."""
        target_set = set()
        for trans in transitions:
            target_set.add(trans.target)
        return target_set

    def _safe_epsilon_closure(self, state_set: Set[int]) -> List[int]:
        """Compute the complete epsilon closure or propagate compilation failure."""
        result = self.nfa.epsilon_closure(list(state_set))
        if len(result) > self.MAX_SUBSET_SIZE:
            logger.warning(
                "Large epsilon closure contains %s states "
                "(warning threshold: %s); preserving the complete closure",
                len(result),
                self.MAX_SUBSET_SIZE,
            )
        return result

    def _get_or_create_target_state(self, target_closure: FrozenSet[int], 
                                  state_map: Dict[FrozenSet[int], int],
                                  dfa_states: List[DFAState], 
                                  queue: deque) -> int:
        """Get existing DFA state or create new one."""
        # Check if state already exists
        if target_closure in state_map:
            self._cache_hits += 1
            return state_map[target_closure]
        
        # Check limits
        if len(dfa_states) >= self.MAX_DFA_STATES:
            raise self._limit_error(
                reason='state_limit',
                limit=self.MAX_DFA_STATES,
                observed=len(dfa_states) + 1,
                states_created=len(dfa_states),
                pending_subsets=len(queue),
            )
        
        # Create new state
        try:
            new_dfa_state = self._create_dfa_state(target_closure)
            new_state_idx = len(dfa_states)
            
            dfa_states.append(new_dfa_state)
            state_map[target_closure] = new_state_idx
            queue.append((target_closure, new_state_idx))
            
            self._states_created += 1
            self._cache_misses += 1
            
            return new_state_idx
            
        except Exception as e:
            raise DFAConstructionError(
                "Failed to create a DFA state for NFA subset "
                f"{sorted(target_closure)}; no partial automaton was returned."
            ) from e

    def _reduce_subset_size(self, nfa_states: FrozenSet[int]) -> FrozenSet[int]:
        """Compatibility helper that deliberately preserves the full subset.

        Older versions dropped lower-ranked NFA states here, which could lose
        valid matches.  The method remains for private-call compatibility but
        no longer performs a semantic reduction.
        """
        if len(nfa_states) > self.MAX_SUBSET_SIZE:
            logger.warning(
                "DFA subset reduction requested for %s states; preserving the "
                "complete subset to maintain matching semantics",
                len(nfa_states),
            )
        return nfa_states

    def _create_combined_condition(self, transitions: List[Transition]) -> Callable:
        """Create combined condition with optimization."""
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
                    logger.debug(f"Condition evaluation error: {e}")
                    continue
            return False
        
        # Cache the result
        self._transition_cache[conditions_key] = combined_condition
        self._cache_misses += 1
        
        # Limit cache size
        if len(self._transition_cache) > 3000:
            keys_to_remove = list(self._transition_cache.keys())[:600]
            for key in keys_to_remove:
                del self._transition_cache[key]
        
        return combined_condition

    def _compute_combined_priority(self, transitions: List[Transition], nfa_states: FrozenSet[int] = None) -> int:
        """
        Compute combined priority with special handling for PERMUTE patterns.
        
        For PERMUTE patterns, priority should reflect:
        1. Number of optional variables (fewer = higher priority)  
        2. Lexicographical order within same optional count
        3. Epsilon transition priorities from NFA
        """
        if not transitions:
            return 0
        
        # Check if this is a PERMUTE pattern
        if (nfa_states and hasattr(self.nfa, 'metadata') and 
            self.nfa.metadata.get('has_permute', False)):
            
            # For PERMUTE patterns, look at epsilon priorities in constituent NFA states
            min_epsilon_priority = float('inf')
            
            for nfa_state_idx in nfa_states:
                if nfa_state_idx < len(self.nfa.states):
                    nfa_state = self.nfa.states[nfa_state_idx]
                    
                    # Check epsilon priorities which encode PERMUTE combination preferences
                    if hasattr(nfa_state, 'epsilon_priorities') and nfa_state.epsilon_priorities:
                        for target, priority in nfa_state.epsilon_priorities.items():
                            min_epsilon_priority = min(min_epsilon_priority, priority)
            
            if min_epsilon_priority != float('inf'):
                logger.debug(f"Using PERMUTE epsilon priority {min_epsilon_priority} for DFA transition")
                return min_epsilon_priority
        
        # Fallback to standard behavior
        return min(t.priority for t in transitions)

    def _create_combined_metadata(self, transitions: List[Transition]) -> Dict[str, Any]:
        """Create combined metadata from transitions."""
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

    def _create_final_metadata(self) -> Dict[str, Any]:
        """Create final DFA metadata with construction metrics."""
        build_time = time.time() - self._build_start_time
        
        return {
            **self.metadata,  # Include source metadata first.
            'construction_complete': True,
            'compiler_schema_version': DFA_COMPILER_SCHEMA_VERSION,
            'construction_time': build_time,
            'iterations': self._iteration_count,
            'states_created': self._states_created,
            'states_merged': self._states_merged,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'cache_hit_rate': self._cache_hits / max(self._cache_hits + self._cache_misses, 1),
            'max_states_limit': self.MAX_DFA_STATES,
            'subset_warning_threshold': self.MAX_SUBSET_SIZE,
            'pending_subsets': 0,
            'optimized': True,
        }

    def _can_reach_accept_via_optional_only(self, nfa_states: FrozenSet[int]) -> bool:
        """
        Check if the given NFA states can reach accept through optional-only paths.
        
        This handles patterns like "A B+ C+ D?" where after matching "A B+ C+", 
        the remaining "D?" is optional and should be considered as a valid completion.
        """
        # First, check direct epsilon reachability to accept state
        visited = set()
        to_check = list(nfa_states)
        
        while to_check:
            state_idx = to_check.pop()
            if state_idx in visited or state_idx >= len(self.nfa.states):
                continue
            visited.add(state_idx)
            
            # Direct accept check
            if state_idx == self.nfa.accept:
                return True
            
            # Follow epsilon transitions
            nfa_state = self.nfa.states[state_idx]
            for epsilon_target in nfa_state.epsilon:
                if epsilon_target not in visited:
                    to_check.append(epsilon_target)
        
        # If not directly reachable via epsilon, use metadata-based approach
        nfa_metadata = self.nfa.metadata
        if not nfa_metadata.get('has_optional_suffix', False):
            return False
            
        # Get the optional suffix tokens
        optional_suffix_tokens = nfa_metadata.get('optional_suffix_tokens', [])
        
        if not optional_suffix_tokens:
            return False
            
        logger.debug(f"Checking optional suffix reachability: suffix_tokens={optional_suffix_tokens}, "
                    f"nfa_states={sorted(nfa_states)}")
        
        # Check if any NFA state can reach accept through optional paths
        for state_idx in nfa_states:
            if state_idx < len(self.nfa.states):
                if self._can_reach_accept_through_optionals(state_idx, optional_suffix_tokens, set()):
                    logger.debug(f"Found optional path to accept from NFA state {state_idx}")
                    return True
        
        return False
    
    def _can_reach_accept_through_optionals(self, state_idx: int, optional_tokens: List[str], 
                                          visited: Set[int]) -> bool:
        """Check if a specific NFA state can reach accept through optional-only constructs."""
        if state_idx in visited or state_idx >= len(self.nfa.states):
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
            if (hasattr(transition, 'variable') and transition.variable and 
                self._is_optional_variable(transition.variable, optional_tokens)):
                target_idx = transition.target
                if self._can_reach_accept_through_optionals(target_idx, optional_tokens, visited.copy()):
                    return True
        
        return False
    
    def _is_optional_variable(self, variable: str, optional_tokens: List[str]) -> bool:
        """Check if a variable corresponds to an optional pattern token."""
        for token in optional_tokens:
            # Remove quantifier suffix to get base variable name
            base_token = token.rstrip('?+*{}0123456789, ')
            if variable == base_token:
                return True
        return False

    def get_build_statistics(self) -> Dict[str, Any]:
        """Get comprehensive build statistics."""
        return {
            'iterations': self._iteration_count,
            'states_created': self._states_created,
            'states_merged': self._states_merged,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'cache_hit_ratio': self._cache_hits / max(self._cache_hits + self._cache_misses, 1),
            'construction_time': time.time() - self._build_start_time if self._build_start_time else 0
        }

    @lru_cache(maxsize=1000)
    def _cached_subset_hash(self, nfa_states_tuple: tuple) -> int:
        """Thread-safe cached subset hashing."""
        try:
            return hash(nfa_states_tuple)
        except Exception:
            return hash(str(nfa_states_tuple))


def build_dfa(nfa: NFA) -> DFA:
    """
    Convenience function to build DFA from NFA.
    
    Args:
        nfa: Source NFA
        
    Returns:
        DFA: Constructed DFA
        
    Raises:
        DFAConstructionError: If complete construction fails
    """
    try:
        builder = DFABuilder(nfa)
        return builder.build()
    except DFAConstructionError:
        raise
    except Exception as e:
        logger.error(f"DFA construction failed: {e}")
        raise DFAConstructionError(f"Failed to build DFA: {e}") from e
