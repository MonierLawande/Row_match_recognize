# src/matcher/automata.py
from typing import Callable, List, Optional, Dict, Any, Set, Tuple
from dataclasses import dataclass
from src.matcher.pattern_tokenizer import PatternToken, PatternTokenType, parse_quantifier
from src.matcher.condition_evaluator import compile_condition
import itertools

# A condition function: given a row and current match context, return True if the row qualifies.
ConditionFn = Callable[[Dict[str, Any], Any], bool]

@dataclass
class Transition:
    condition: ConditionFn
    target: int
    variable: Optional[str] = None

# In NFAState class (src/matcher/automata.py):
class NFAState:

    def __init__(self):
        self.transitions: List[Transition] = []
        self.epsilon: List[int] = []
        self.variable: Optional[str] = None  # Initialize as None
        self.is_excluded: bool = False
        self.is_anchor: bool = False
        self.anchor_type: Optional[PatternTokenType] = None
    
    def add_transition(self, condition: ConditionFn, target: int, variable: Optional[str] = None):
        self.transitions.append(Transition(condition, target, variable))

class NFABuilder:
    def __init__(self):
        self.states: List[NFAState] = []
        self.current_exclusion = False
        self.exclusion_ranges: List[Tuple[int, int]] = []
    
    def new_state(self) -> int:
        state = NFAState()
        self.states.append(state)
        return len(self.states) - 1
    
    def add_epsilon(self, from_state: int, to_state: int):
        self.states[from_state].epsilon.append(to_state)
 
    def build(self, tokens: List[PatternToken], define: Dict[str, str]) -> 'NFA':
        """Build NFA from pattern tokens."""
        start = self.new_state()
        accept = self.new_state()
        
        # Handle empty pattern
        if not tokens:
            self.add_epsilon(start, accept)
            return NFA(start, accept, self.states, [])
        
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
        
        return NFA(start, accept, self.states, self.exclusion_ranges)

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
                # Handle PERMUTE(A,B,C)
                idx[0] += 1  # Skip PERMUTE token
                
                # Collect variables in the permutation
                variables = []
                if idx[0] < len(tokens) and tokens[idx[0]].type == PatternTokenType.GROUP_START:
                    idx[0] += 1  # Skip opening parenthesis
                    
                    # Collect all variables until GROUP_END
                    while idx[0] < len(tokens) and tokens[idx[0]].type != PatternTokenType.GROUP_END:
                        if tokens[idx[0]].type == PatternTokenType.LITERAL:
                            variables.append(tokens[idx[0]].value)
                        idx[0] += 1
                    
                    # Skip closing parenthesis
                    if idx[0] < len(tokens) and tokens[idx[0]].type == PatternTokenType.GROUP_END:
                        idx[0] += 1
                
                # Generate all permutations of variables
                perm_start = self.new_state()
                perm_end = self.new_state()
                
                for perm in itertools.permutations(variables):
                    branch_start = self.new_state()
                    branch_current = branch_start
                    
                    for var in perm:
                        var_start, var_end = self.create_var_states(var, define)
                        self.add_epsilon(branch_current, var_start)
                        branch_current = var_end
                    
                    # Connect this permutation branch
                    self.add_epsilon(perm_start, branch_start)
                    self.add_epsilon(branch_current, perm_end)
                
                # Connect permutation fragment to current NFA
                self.add_epsilon(current, perm_start)
                current = perm_end
                
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
    
    # In NFABuilder class (src/matcher/automata.py):

        # In NFABuilder._process_exclusion method
    def _process_exclusion(self, tokens: List[PatternToken], idx: List[int], define: Dict[str, str]) -> Tuple[int, int]:
        """Process an exclusion pattern fragment."""
        # Remember exclusion start position
        exclusion_start = len(self.states)
        
        # Track original exclusion state and set current to true
        previous_exclusion_state = self.current_exclusion
        self.current_exclusion = True
        
        # Skip exclusion start token
        idx[0] += 1
        
        # Process tokens inside exclusion
        excl_start, excl_end = self._process_sequence(tokens, idx, define)
        
        # Mark exclusion end
        exclusion_end = len(self.states) - 1
        self.exclusion_ranges.append((exclusion_start, exclusion_end))
        
        # Mark all states in this range as excluded
        for i in range(exclusion_start, exclusion_end + 1):
            self.states[i].is_excluded = True
        
        # Restore previous exclusion state
        self.current_exclusion = previous_exclusion_state
        
        # Skip exclusion end token if present
        if idx[0] < len(tokens) and tokens[idx[0]].type == PatternTokenType.EXCLUSION_END:
            idx[0] += 1
        
        return excl_start, excl_end

    
    # In src/matcher/automata.py
    def create_var_states(self, var: str, define: Dict[str, str]) -> Tuple[int, int]:
        """Create states for a pattern variable."""
        start = self.new_state()
        end = self.new_state()
        
        # Get condition from DEFINE clause or use TRUE
        condition = define.get(var, "TRUE")
        print(f"Creating transition for variable '{var}' with condition: '{condition}'")
        condition_fn = compile_condition(condition)
        
        # Create transition with condition
        self.states[start].add_transition(condition_fn, end, var)
        self.states[start].variable = var  # Mark state with variable name
        
        return start, end

    
    def _apply_quantifier(self, 
                        start: int, 
                        end: int, 
                        min_rep: int, 
                        max_rep: Optional[int],
                        greedy: bool) -> Tuple[int, int]:
        """Apply quantifier to a subpattern."""
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
                        trans.variable
                    )
                current = next_state
            # Connect the last state to new_end
            self.add_epsilon(current, new_end)
            return new_start, new_end
        
        # Handle different quantifier types
        if min_rep == 0 and max_rep is None:  # *
            if greedy:
                self.add_epsilon(new_start, start)  # Try to match
                self.add_epsilon(new_start, new_end)  # Or skip - allows empty match
            else:
                self.add_epsilon(new_start, new_end)  # Try to skip - allows empty match
                self.add_epsilon(new_start, start)  # Or match
            self.add_epsilon(end, start)  # Loop back
            self.add_epsilon(end, new_end)  # Or finish
            
        elif min_rep == 1 and max_rep is None:  # +
            self.add_epsilon(new_start, start)  # Must match once
            self.add_epsilon(end, start)  # Can repeat
            self.add_epsilon(end, new_end)  # Or finish
            
        elif min_rep == 0 and max_rep == 1:  # ?
            if greedy:
                self.add_epsilon(new_start, start)  # Try to match
                self.add_epsilon(new_start, new_end)  # Or skip - allows empty match
            else:
                self.add_epsilon(new_start, new_end)  # Try to skip - allows empty match
                self.add_epsilon(new_start, start)  # Or match
            self.add_epsilon(end, new_end)
            print(f"Added epsilon transition for ? quantifier - allows empty match")
            
        else:  # {m,n} bounds
            # Create chain for minimum repetitions
            current = new_start
            if min_rep == 0:
                # Direct path for empty match
                self.add_epsilon(new_start, new_end)
                print(f"Added epsilon transition for {min_rep},{max_rep} quantifier - allows empty match")
                
            for _ in range(min_rep):
                next_start = self.new_state()
                next_end = self.new_state()
                self.add_epsilon(current, next_start)
                self._copy_subpattern(start, end, next_start, next_end)
                current = next_end
            
            # Add optional repetitions up to max
            if max_rep is not None:
                for _ in range(min_rep, max_rep):
                    if greedy:
                        self.add_epsilon(current, start)  # Try to match more
                        self.add_epsilon(current, new_end)  # Or finish
                    else:
                        self.add_epsilon(current, new_end)  # Try to finish
                        self.add_epsilon(current, start)  # Or match more
                    current = end
            else:
                # No upper bound - add loop
                self.add_epsilon(current, start)  # Can repeat
                self.add_epsilon(current, new_end)  # Or finish
        
        return new_start, new_end

    
    def _copy_subpattern(self, 
                        orig_start: int, 
                        orig_end: int, 
                        new_start: int, 
                        new_end: int):
        """Copy a subpattern between new states (simplified)."""
        # Copy all transitions
        for trans in self.states[orig_start].transitions:
            self.states[new_start].add_transition(
                trans.condition,
                new_end if trans.target == orig_end else trans.target,
                trans.variable
            )

class NFA:
    def __init__(self, start: int, accept: int, states: List[NFAState], exclusion_ranges: List[Tuple[int, int]] = None):
        self.start = start
        self.accept = accept
        self.states = states
        self.exclusion_ranges = exclusion_ranges or []
    
    def epsilon_closure(self, state_indices: List[int]) -> List[int]:
        """Compute epsilon closure for given states."""
        closure = set(state_indices)
        stack = list(state_indices)
        while stack:
            s = stack.pop()
            for t in self.states[s].epsilon:
                if t not in closure:
                    closure.add(t)
                    stack.append(t)
        return list(closure)
