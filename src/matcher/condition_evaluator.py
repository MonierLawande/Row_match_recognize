# src/matcher/condition_evaluator.py
"""
Production-ready condition evaluator for SQL:2016 row pattern matching.

This module implements comprehensive condition evaluation with full support for:
- SQL:2016 pattern matching semantics
- Enhanced navigation functions (FIRST, LAST, PREV, NEXT)
- Pattern variable references and subset variables
- Mathematical and utility functions
- Advanced error handling and validation
- Performance optimization with caching

Refactored to eliminate duplication and improve maintainability.

Author: Pattern Matching Engine Team
Version: 2.0.0
"""

import ast
import operator
import re
import time
import threading
from typing import Dict, Any, Optional, Callable, List, Union, Tuple, Set
from dataclasses import dataclass

from src.matcher.row_context import RowContext
from src.matcher.evaluation_utils import (
    EvaluationMode, ValidationError, ExpressionValidationError,
    validate_expression_length, validate_recursion_depth,
    is_null, safe_compare, is_table_prefix, MATH_FUNCTIONS, 
    evaluate_math_function, get_evaluation_metrics
)
from src.utils.logging_config import get_logger, PerformanceTimer

# Module logger
logger = get_logger(__name__)

# Define the type for condition functions
ConditionFn = Callable[[Dict[str, Any], RowContext], bool]

# Enhanced Navigation Function Info for better structured parsing
@dataclass
class NavigationFunctionInfo:
    """Information about a navigation function call."""
    function_type: str  # PREV, NEXT, FIRST, LAST
    variable: Optional[str]
    column: Optional[str]
    offset: int
    is_nested: bool
    inner_functions: List['NavigationFunctionInfo']
    raw_expression: str

class ConditionEvaluator(ast.NodeVisitor):
    """
    Production-ready condition evaluator with comprehensive SQL:2016 support.
    
    This class provides enhanced condition evaluation with:
    - Context-aware navigation (physical for DEFINE, logical for MEASURES)
    - Pattern variable reference resolution
    - Mathematical and utility function evaluation
    - Comprehensive error handling and validation
    - Performance optimization with caching
    
    Refactored to eliminate duplication and improve maintainability.
    """
    
    def __init__(self, context: RowContext, evaluation_mode='DEFINE', recursion_depth=0):
        """
        Initialize condition evaluator with context-aware navigation.
        
        Args:
            context: RowContext for pattern matching
            evaluation_mode: 'DEFINE' for physical navigation, 'MEASURES' for logical navigation
            recursion_depth: Current recursion depth to prevent infinite recursion
        """
        # Input validation
        if not isinstance(context, RowContext):
            raise ValueError(f"Expected RowContext, got {type(context)}")
        
        self.context = context
        self.current_row = None
        self.evaluation_mode = evaluation_mode
        self.recursion_depth = recursion_depth
        self.max_recursion_depth = 20  # Increased for complex patterns
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Performance tracking
        self.stats = {
            "evaluations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "navigation_calls": 0,
            "math_function_calls": 0
        }
        
        # Initialize visit stack for recursion tracking
        self.visit_stack = set()
        
        # CLASSIFIER lookup is the only condition operation that needs this
        # row-to-variable index.  Keep it lazy: rebuilding it for every
        # running-aggregate comparison makes long matches quadratic even when
        # the expression never reads CLASSIFIER.
        self._row_var_index = {}
        self._evaluation_indices_ready = False

    def reset(
        self,
        context: RowContext,
        evaluation_mode='DEFINE',
        recursion_depth=0,
    ) -> "ConditionEvaluator":
        """
        Reuse this evaluator for another row/context evaluation.

        Compiled conditions are evaluated many times while the DFA scans rows.
        Reusing the evaluator avoids repeated object allocation while preserving
        the same public semantics.  Variable assignments may change as a match
        grows, so the optional classifier index is marked dirty and rebuilt
        only if an expression requests it.
        """
        if not isinstance(context, RowContext):
            raise ValueError(f"Expected RowContext, got {type(context)}")

        self.context = context
        self.current_row = None
        self.evaluation_mode = evaluation_mode
        self.recursion_depth = recursion_depth
        self.visit_stack.clear()
        self.stats = {
            "evaluations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "navigation_calls": 0,
            "math_function_calls": 0
        }
        self._evaluation_indices_ready = False
        return self

    
    def _build_evaluation_indices(self) -> None:
        """Build optimized indices for fast evaluation."""
        try:
            with self._lock:
                # Build row-to-variable mapping for fast lookups
                self._row_var_index = {}
                for var_name, indices in self.context.variables.items():
                    for idx in indices:
                        if isinstance(idx, int) and 0 <= idx < len(self.context.rows):
                            if idx not in self._row_var_index:
                                self._row_var_index[idx] = set()
                            self._row_var_index[idx].add(var_name)
                
                # Build subset memberships
                if hasattr(self.context, 'subsets') and self.context.subsets:
                    for subset_name, components in self.context.subsets.items():
                        for comp in components:
                            if comp in self.context.variables:
                                for idx in self.context.variables[comp]:
                                    if idx not in self._row_var_index:
                                        self._row_var_index[idx] = set()
                                    self._row_var_index[idx].add(subset_name)
                self._evaluation_indices_ready = True
        except Exception as e:
            logger.warning(f"Error building evaluation indices: {e}")
            self._row_var_index = {}
            self._evaluation_indices_ready = True

    def _ensure_evaluation_indices(self) -> None:
        """Build classifier indices only when a condition needs them."""
        if not self._evaluation_indices_ready:
            self._build_evaluation_indices()

    def _safe_compare(self, left: Any, right: Any, op: Union[Callable, ast.operator]) -> Any:
        """Perform SQL-style comparison with NULL handling."""
        self.stats["evaluations"] += 1
        return safe_compare(left, right, op)

    def visit_Compare(self, node: ast.Compare):
        """Handle comparison operations with SQL semantics."""
        # Handle chained comparisons like (20 <= value <= 30) for BETWEEN
        if len(node.ops) > 1:
            # Handle chained comparisons by evaluating them step by step
            left = self.visit(node.left)
            
            for i, (op, comparator) in enumerate(zip(node.ops, node.comparators)):
                right = self.visit(comparator)
                
                # Evaluate the current comparison
                result = self._safe_compare(left, right, op)
                
                # If any comparison in the chain is False, return False
                if not result:
                    return False
                
                # For the next iteration, the right becomes the new left
                left = right
            
            # If all comparisons passed, return True
            return True
            
        left = self.visit(node.left)
        op = node.ops[0]
        
        # Debug logging for DEFINE mode comparisons
        if self.evaluation_mode == 'DEFINE':
            logger.debug(f"[DEBUG] COMPARE: left={left} ({type(left)}), op={op.__class__.__name__}")
        
        # Handle IN operator specially
        if isinstance(op, ast.In):
            # For IN operator, we need to check if left is in any of the comparators
            if len(node.comparators) != 1:
                raise ValueError("IN operator requires exactly one comparator (list/tuple)")
            
            right = self.visit(node.comparators[0])
            
            # Handle different types of right-hand side for IN
            if isinstance(right, (list, tuple)):
                # Handle special empty IN placeholders
                if len(right) == 1:
                    if right[0] == '__EMPTY_IN_FALSE__':
                        result = False  # Empty IN should always be false
                    elif right[0] == '__EMPTY_IN_TRUE__':
                        result = True   # Used for NOT IN () preprocessing
                    else:
                        result = left in right
                else:
                    # Direct list/tuple comparison
                    result = left in right
            elif hasattr(right, '__iter__') and not isinstance(right, str):
                # Iterable but not string
                try:
                    result = left in right
                except TypeError:
                    # If comparison fails, return False
                    result = False
            else:
                # Single value - handle special placeholders
                if right == '__EMPTY_IN_FALSE__':
                    result = False  # Empty IN should always be false
                elif right == '__EMPTY_IN_TRUE__':
                    result = True   # Used for NOT IN () preprocessing
                else:
                    # Single value - treat as membership test
                    result = left == right
                
            if self.evaluation_mode == 'DEFINE':
                logger.debug(f"[DEBUG] IN RESULT: {left} IN {right} = {result}")
            
            return result
            
        elif isinstance(op, ast.NotIn):
            # Handle NOT IN operator
            if len(node.comparators) != 1:
                raise ValueError("NOT IN operator requires exactly one comparator (list/tuple)")
            
            right = self.visit(node.comparators[0])
            
            # Handle different types of right-hand side for NOT IN
            if isinstance(right, (list, tuple)):
                # Handle special empty IN placeholders
                if len(right) == 1:
                    if right[0] == '__EMPTY_IN_FALSE__':
                        result = False  # NOT IN with empty false placeholder
                    elif right[0] == '__EMPTY_IN_TRUE__':
                        result = True   # NOT IN () should always be true
                    else:
                        result = left not in right
                else:
                    # Direct list/tuple comparison
                    result = left not in right
            elif hasattr(right, '__iter__') and not isinstance(right, str):
                # Iterable but not string
                try:
                    result = left not in right
                except TypeError:
                    # If comparison fails, return True (not in)
                    result = True
            else:
                # Single value - handle special placeholders
                if right == '__EMPTY_IN_FALSE__':
                    result = False  # NOT IN with empty false placeholder
                elif right == '__EMPTY_IN_TRUE__':
                    result = True   # NOT IN () should always be true
                else:
                    # Single value - treat as membership test
                    result = left != right
                
            if self.evaluation_mode == 'DEFINE':
                logger.debug(f"[DEBUG] NOT IN RESULT: {left} NOT IN {right} = {result}")
            
            return result
        
        # Handle standard comparison operators
        if len(node.comparators) != 1:
            raise ValueError("Standard comparison operators require exactly one comparator")
            
        right = self.visit(node.comparators[0])
        
        if self.evaluation_mode == 'DEFINE':
            logger.debug(f"[DEBUG] COMPARE: left={left} ({type(left)}), right={right} ({type(right)})")
        
        # Use the safer comparison method
        result = self._safe_compare(left, right, op)
        
        # Enhanced debug logging for result
        if self.evaluation_mode == 'DEFINE':
            current_var = getattr(self.context, 'current_var', None)
            logger.debug(f"[DEBUG] COMPARE RESULT: {left} {op.__class__.__name__} {right} = {result} (evaluating for var={current_var})")
        
        return result

    def visit_Name(self, node: ast.Name):
        # Check for special functions
        if node.id.upper() == "PREV":
            return lambda col, steps=1: self.evaluate_navigation_function('PREV', col, steps)
        elif node.id.upper() == "NEXT":
            return lambda col, steps=1: self.evaluate_navigation_function('NEXT', col, steps)
        elif node.id.upper() == "FIRST":
            def first_lambda(var, col, occ=0):
                logger = get_logger(__name__)
                logger.debug(f"🔍 [FIRST_LAMBDA] Called with var={var}, col={col}, occ={occ}")
                return self._handle_first_last_navigation('FIRST', col, occ, var)
            return first_lambda
        elif node.id.upper() == "LAST":
            def last_lambda(var, col, occ=0):
                logger = get_logger(__name__)
                logger.debug(f"🔍 [LAST_LAMBDA] Called with var={var}, col={col}, occ={occ}")
                return self._handle_first_last_navigation('LAST', col, occ, var)
            return last_lambda
        elif node.id.upper() == "CLASSIFIER":
            return lambda var=None: self._get_classifier(var)
        elif node.id.upper() == "MATCH_NUMBER":
            return self.context.match_number
        elif node.id == "row":
            # Special handling for 'row' references in keyword substitution
            return {}  # Return an empty dict that will be used in visit_Subscript
        elif node.id == "get_var_value":
            # Special function for pattern variable access
            return self._get_variable_column_value
                
        # Regular variable - handle as universal pattern variable
        # First check if this might be a universal pattern variable (non-prefixed column)
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', node.id):
            # Check if this conflicts with defined pattern variables
            if hasattr(self.context, 'pattern_variables') and node.id in self.context.pattern_variables:
                logger.warning(f"Column name '{node.id}' conflicts with pattern variable name")
                return None
            
            # Universal pattern variable: get from current row
            value = None
            if self.current_row is not None:
                value = self.current_row.get(node.id)
            elif self.context.current_idx >= 0 and self.context.current_idx < len(self.context.rows):
                value = self.context.rows[self.context.current_idx].get(node.id)
            
            if value is not None:
                logger.debug(f"Universal pattern variable '{node.id}' resolved to: {value}")
            
            return value
        
        # Fallback for non-standard identifiers
        value = None
        if self.current_row is not None:
            value = self.current_row.get(node.id)
        elif self.context.current_idx >= 0 and self.context.current_idx < len(self.context.rows):
            value = self.context.rows[self.context.current_idx].get(node.id)
        
        return value

    def _extract_navigation_args(self, node: ast.Call):
        """Extract arguments from a navigation function call with support for nesting."""
        args = []
        
        for arg in node.args:
            if isinstance(arg, ast.Name):
                # For navigation functions, Name nodes should be treated as column names
                args.append(arg.id)
            elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                # Handle pattern variable references like A.value -> split to var and column
                var_name = arg.value.id
                col_name = arg.attr
                # For navigation functions like FIRST(A.value), we need both parts
                args.extend([var_name, col_name])
            elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Constant):
                # Handle quoted variable references like "b".value -> split to var and column
                var_name = f'"{arg.value.value}"'  # Preserve quotes for consistency
                col_name = arg.attr
                # For navigation functions like FIRST("b".value), we need both parts
                args.extend([var_name, col_name])
            elif isinstance(arg, ast.Constant):
                # Constant values (numbers, strings)
                args.append(arg.value)
            else:
                # For complex expressions, evaluate them
                value = self.visit(arg)
                # Handle nested navigation functions
                if callable(value):
                    value = value()
                args.append(value)
            
        return args

    def visit_Call(self, node: ast.Call):
        """Handle function calls (navigation functions, mathematical functions, etc.)"""
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.upper()
            
            # Handle null checking helper function
            if func_name == "_IS_NULL":
                args = [self.visit(arg) for arg in node.args]
                if len(args) == 1:
                    return is_null(args[0])
                else:
                    raise ValueError("_is_null function requires exactly one argument")
            
            # Handle LAG and LEAD window functions
            if func_name in ("LAG", "LEAD"):
                return self._handle_window_function(node, func_name)
            
            # Handle mathematical and utility functions using shared utilities
            if func_name in MATH_FUNCTIONS:
                args = [self.visit(arg) for arg in node.args]
                self.stats["math_function_calls"] += 1
                try:
                    return evaluate_math_function(func_name, *args)
                except Exception as e:
                    raise ValueError(f"Error in {func_name} function: {e}")
            
            # Special handling for pattern variable access
            if func_name == "GET_VAR_VALUE":
                args = [self.visit(arg) for arg in node.args]
                if len(args) == 3:
                    var_name, col_name, ctx = args
                    return self._get_variable_column_value(var_name, col_name, ctx)
            
            # Special handling for CLASSIFIER function
            if func_name == "CLASSIFIER":
                # For CLASSIFIER, we need the literal variable name, not its evaluated value
                if len(node.args) == 0:
                    return self._get_classifier(None)
                elif len(node.args) == 1:
                    arg = node.args[0]
                    if isinstance(arg, ast.Name):
                        # Pass the literal variable name
                        return self._get_classifier(arg.id)
                    else:
                        raise ValueError("CLASSIFIER function requires a variable name argument")
                else:
                    raise ValueError("CLASSIFIER function takes at most one argument")
            
            # Enhanced navigation function handling
            if func_name in ("PREV", "NEXT", "FIRST", "LAST"):
                return self._handle_navigation_function(node, func_name)

            # MATCH_NUMBER() of the match candidate being evaluated
            if func_name == "MATCH_NUMBER":
                return getattr(self.context, 'match_number', None)

            # Aggregate functions in DEFINE (running semantics over the rows
            # matched so far, current row included under its tentative label)
            if func_name in ("SUM", "AVG", "MIN", "MAX", "COUNT", "ARBITRARY", "ARRAY_AGG",
                             "MAX_BY", "MIN_BY"):
                return self._handle_define_aggregate(node, func_name)

        func = self.visit(node.func)
        if callable(func):
            args = [self.visit(arg) for arg in node.args]
            try:
                return func(*args)
            except Exception as e:
                # More descriptive error
                raise ValueError(f"Error calling {func_name or 'function'}: {e}")
        raise ValueError(f"Function {func_name or func} not callable")
    
    def _handle_define_aggregate(self, node: ast.Call, func_name: str) -> Any:
        """Evaluate an aggregate function inside a DEFINE condition.

        SQL:2016 running semantics: the aggregate runs over the rows matched
        so far in the current match attempt, with the current row included
        under its tentative label.  A label-qualified argument (``B.value``)
        restricts the scope to that variable's rows (or a SUBSET union);
        an unqualified argument aggregates over the universal row variable.
        The argument may be an arbitrary expression: it is re-evaluated for
        every aggregated row with the evaluator positioned at that row, so
        CLASSIFIER()/MATCH_NUMBER()-dependent arguments work.
        """
        # The AST is immutable after condition compilation.  Resolve its
        # argument shape once instead of repeating multiple ``isinstance``
        # walks for every candidate row in the exact searcher.
        aggregate_plan = getattr(node, "_rowmatch_define_aggregate_plan", None)
        if aggregate_plan is None:
            expected_args = 2 if func_name in ("MAX_BY", "MIN_BY") else 1
            if len(node.args) != expected_args or node.keywords:
                raise ValueError(
                    f"{func_name} in DEFINE requires {expected_args} argument(s)"
                )
            arg = node.args[0]
            key_arg = node.args[1] if expected_args == 2 else None
            simple_field = (
                arg.attr
                if key_arg is None
                and isinstance(arg, ast.Attribute)
                and isinstance(arg.value, ast.Name)
                else None
            )
            scope_var = (
                arg.value.id
                if isinstance(arg, ast.Attribute)
                and isinstance(arg.value, ast.Name)
                else None
            )
            scope_upper = scope_var.upper() if scope_var is not None else None
            aggregate_plan = (
                arg,
                key_arg,
                simple_field,
                scope_var,
                scope_upper,
                frozenset((scope_upper,)) if scope_upper is not None else None,
            )
            node._rowmatch_define_aggregate_plan = aggregate_plan
        (
            arg,
            key_arg,
            simple_field,
            scope_var,
            scope_upper,
            single_member_set,
        ) = aggregate_plan

        context = self.context
        variables = getattr(context, "variables", {}) or {}
        rows = getattr(context, "rows", None) or []
        current_idx = getattr(context, "current_idx", -1)
        current_var = getattr(context, "current_var", None)

        member_set = None
        if scope_var is not None:
            subsets = getattr(context, "subsets", {}) or {}
            if not subsets:
                member_set = single_member_set
            else:
                members = [scope_var]
                for subset_name, subset_members in subsets.items():
                    if str(subset_name).upper() == scope_upper:
                        members = list(subset_members)
                        break
                member_set = {str(m).upper() for m in members}

        matching_lists = None
        if simple_field is not None and member_set is not None and len(member_set) == 1:
            matching_lists = [
                var_indices
                for var_name, var_indices in variables.items()
                if str(var_name).upper() in member_set
            ]

        # The exact backtracking searcher supplies per-variable assignment
        # revisions.  Aggregates scoped to A, for example, do not change while
        # rows are tentatively added to B.  Cache against only the revisions
        # that can affect this aggregate, plus the current tentative row when
        # it belongs to the aggregate scope.  Assignment and rollback both
        # advance revisions, which makes stale reuse impossible.
        aggregate_cache = getattr(context, "_define_aggregate_cache", None)
        assignment_versions = (
            getattr(context, "_define_assignment_versions", None)
            if aggregate_cache is not None
            else None
        )
        aggregate_cache_key = None
        if aggregate_cache is not None and assignment_versions is not None:
            tentative_in_scope = (
                current_idx is not None
                and 0 <= current_idx < len(rows)
                and (
                    member_set is None
                    or (
                        current_var
                        and str(current_var).upper() in member_set
                    )
                )
            )
            # Memoization only pays when the aggregate scope is unchanged by
            # the tentative row and contains enough rows to make rescanning
            # materially more expensive than key construction.  If the
            # tentative row belongs to the scope, every input position has a
            # distinct value and the cache would add overhead without reuse.
            # Universal aggregates always include the tentative row, so the
            # cheap gate also avoids constructing member sets for them.
            if not tentative_in_scope and member_set is not None:
                if matching_lists is not None:
                    scope_cardinality = sum(map(len, matching_lists))
                else:
                    scope_cardinality = 0
                    for var_name, var_indices in variables.items():
                        if str(var_name).upper() in member_set:
                            scope_cardinality += len(var_indices)
                # Below this point a direct scan is cheaper on CPython.  This
                # threshold is a cost-model decision, independent of any
                # pattern or column name; long unchanged scopes still obtain
                # linear rather than repeated-scan behavior.
                if scope_cardinality < 16:
                    relevant_members = None
                else:
                    relevant_members = member_set
            else:
                relevant_members = None
            if relevant_members is not None:
                if len(relevant_members) == 1:
                    member = next(iter(relevant_members))
                    revision_key = ((member, assignment_versions.get(member, 0)),)
                else:
                    revision_key = tuple(
                        (member, assignment_versions.get(member, 0))
                        for member in sorted(relevant_members)
                    )
                aggregate_cache_key = (id(node), func_name, revision_key)
                if aggregate_cache_key in aggregate_cache:
                    return aggregate_cache[aggregate_cache_key]

        def finish(value):
            if aggregate_cache_key is not None:
                # Bound pathological ambiguous searches.  Clearing affects
                # performance only; revision keys preserve correctness.
                if len(aggregate_cache) >= 4096:
                    aggregate_cache.clear()
                aggregate_cache[aggregate_cache_key] = value
            return value

        # A single qualified field over one primary variable already has an
        # ordered assignment list.  Stream it directly instead of creating a
        # set, sorting indices, building classifier labels, and materializing
        # all values.  Subsets/multiple case variants and expression-valued
        # arguments retain the generic implementation below.
        if simple_field is not None and member_set is not None and len(member_set) == 1:
            if len(matching_lists) <= 1:
                assigned_indices = matching_lists[0] if matching_lists else []
                include_current = (
                    current_idx is not None
                    and 0 <= current_idx < len(rows)
                    and current_var
                    and str(current_var).upper() in member_set
                    and current_idx not in assigned_indices
                )

                count = 0
                total = 0
                minimum = None
                maximum = None
                first = None
                array_values = [] if func_name == "ARRAY_AGG" else None
                column_cache = context._input_column_cache
                if simple_field in column_cache:
                    column_values = column_cache[simple_field]
                else:
                    exact_column_at = getattr(rows, "column_array_exact", None)
                    column_values = (
                        exact_column_at(simple_field)
                        if exact_column_at is not None
                        else None
                    )
                    column_cache[simple_field] = column_values

                def consume(row_index):
                    nonlocal count, total, minimum, maximum, first
                    value = (
                        column_values[row_index]
                        if column_values is not None
                        else rows[row_index].get(simple_field)
                    )
                    if value is None or value != value:  # SQL NULL/NaN
                        return
                    count += 1
                    if first is None:
                        first = value
                    if func_name in ("SUM", "AVG"):
                        total += value
                    elif func_name == "MIN":
                        minimum = value if minimum is None else min(minimum, value)
                    elif func_name == "MAX":
                        maximum = value if maximum is None else max(maximum, value)
                    elif array_values is not None:
                        array_values.append(value)

                for row_index in assigned_indices:
                    if 0 <= row_index < len(rows):
                        consume(row_index)
                if include_current:
                    consume(current_idx)

                if func_name == "COUNT":
                    return finish(count)
                if count == 0:
                    return finish(None)
                if func_name == "SUM":
                    return finish(total)
                if func_name == "AVG":
                    return finish(total / count)
                if func_name == "MIN":
                    return finish(minimum)
                if func_name == "MAX":
                    return finish(maximum)
                if func_name == "ARRAY_AGG":
                    return finish(array_values)
                if func_name == "ARBITRARY":
                    return finish(first)

        indices = set()
        for var_name, var_indices in variables.items():
            if member_set is None or str(var_name).upper() in member_set:
                indices.update(var_indices)
        indices = sorted(i for i in indices if 0 <= i < len(rows))
        if (
            current_idx is not None and 0 <= current_idx < len(rows)
            and current_idx not in indices
            and (member_set is None
                 or (current_var and str(current_var).upper() in member_set))
        ):
            indices.append(current_idx)
            indices.sort()

        # Per-row labels so CLASSIFIER() inside the argument sees each row's
        # own label; the current row keeps its tentative label.
        index_labels = {}
        for var_name, var_indices in variables.items():
            for row_index in var_indices:
                index_labels.setdefault(row_index, var_name)
        if current_idx is not None and current_idx >= 0:
            index_labels.setdefault(current_idx, current_var)

        values = []
        keys = []
        saved_row = self.current_row
        saved_idx = context.current_idx
        saved_var = getattr(context, "current_var", None)
        try:
            for row_index in indices:
                if simple_field is not None:
                    value = rows[row_index].get(simple_field)
                else:
                    self.current_row = rows[row_index]
                    context.current_idx = row_index
                    context.current_var = index_labels.get(row_index, saved_var)
                    value = self.visit(arg)
                if key_arg is not None:
                    key = self.visit(key_arg)
                    if (value is not None and value == value
                            and key is not None and key == key):
                        values.append(value)
                        keys.append(key)
                elif value is not None and value == value:  # skip NULL/NaN
                    values.append(value)
        finally:
            self.current_row = saved_row
            context.current_idx = saved_idx
            context.current_var = saved_var

        if func_name == "COUNT":
            return finish(len(values))
        if not values:
            return finish(None)
        if func_name in ("MAX_BY", "MIN_BY"):
            pick = max if func_name == "MAX_BY" else min
            best_index = pick(range(len(keys)), key=lambda i: keys[i])
            return finish(values[best_index])
        if func_name == "SUM":
            return finish(sum(values))
        if func_name == "AVG":
            return finish(sum(values) / len(values))
        if func_name == "MIN":
            return finish(min(values))
        if func_name == "MAX":
            return finish(max(values))
        if func_name == "ARRAY_AGG":
            return finish(values)
        return finish(values[0])  # ARBITRARY

    def _handle_navigation_function(self, node: ast.Call, func_name: str) -> Any:
        """Handle navigation function calls with comprehensive support."""
        self.stats["navigation_calls"] += 1
        
        # Check if this might be a nested navigation call
        is_nested = False
        if len(node.args) > 0:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Call) and hasattr(first_arg, 'func') and isinstance(first_arg.func, ast.Name):
                inner_func_name = first_arg.func.id.upper()
                if inner_func_name in ("PREV", "NEXT", "FIRST", "LAST"):
                    is_nested = True
        
        if is_nested:
            # For nested navigation, convert to string representation and use evaluate_nested_navigation
            navigation_expr = self._build_navigation_expr(node)
            # Store current evaluator in context for nested navigation
            original_active_evaluator = getattr(self.context, '_active_evaluator', None)
            self.context._active_evaluator = self
            try:
                result = evaluate_nested_navigation(
                    navigation_expr, 
                    self.context, 
                    self.context.current_idx, 
                    getattr(self.context, 'current_var', None),
                    self.recursion_depth + 1
                )
                return result
            finally:
                # Restore original active evaluator
                if original_active_evaluator is not None:
                    self.context._active_evaluator = original_active_evaluator
                else:
                    if hasattr(self.context, '_active_evaluator'):
                        delattr(self.context, '_active_evaluator')
        else:
            # Handle standard navigation function calls
            if len(node.args) == 0:
                raise ValueError(f"{func_name} function requires at least one argument")
            
            # Get the first argument which should be either ast.Name or ast.Attribute
            first_arg = node.args[0]
            
            # Get optional steps argument
            steps = 0 if func_name in ("FIRST", "LAST") else 1
            if len(node.args) > 1:
                steps_arg = node.args[1]
                if isinstance(steps_arg, ast.Constant):
                    steps = steps_arg.value
            
            if isinstance(first_arg, ast.Attribute) and isinstance(first_arg.value, ast.Name):
                # Pattern: NEXT(A.value) - variable.column format
                var_name = first_arg.value.id
                column = first_arg.attr
                
                # Table prefix validation
                if self._is_table_prefix_in_context(var_name):
                    raise ValueError(f"Forbidden table prefix reference: '{var_name}.{column}'. "
                                   f"In MATCH_RECOGNIZE, use pattern variable references instead of table references")
                
                if func_name in ("PREV", "NEXT"):
                    # In DEFINE mode, PREV(A.price) means "get A.price from the previous physical row"
                    # not "get price from the previous A-matched row"
                    # The variable prefix is just specifying which column to access
                    if self.evaluation_mode == 'DEFINE':
                        # Physical navigation: use direct row indexing
                        return self.evaluate_physical_navigation(func_name, column, steps)
                    else:
                        # Logical navigation: use pattern match timeline
                        return self.evaluate_navigation_function(func_name, column, steps)
                else:
                    # Use new navigation handler for FIRST/LAST
                    return self._handle_first_last_navigation(func_name, column, steps, var_name)
                    
            elif isinstance(first_arg, ast.Attribute) and isinstance(first_arg.value, ast.Constant):
                # Pattern: NEXT("b".value) - quoted variable.column format
                var_name = f'"{first_arg.value.value}"'  # Preserve quotes for consistency
                column = first_arg.attr
                
                if func_name in ("PREV", "NEXT"):
                    # Context-aware navigation: physical for DEFINE, logical for MEASURES
                    if self.evaluation_mode == 'DEFINE':
                        return self.evaluate_physical_navigation(func_name, column, steps)
                    else:
                        return self.evaluate_navigation_function(func_name, column, steps)
                else:
                    # Use new navigation handler for FIRST/LAST
                    return self._handle_first_last_navigation(func_name, column, steps, var_name)
                    
            elif isinstance(first_arg, ast.Name):
                # Pattern: NEXT(column) - simple column format
                column = first_arg.id
                
                if func_name in ("PREV", "NEXT"):
                    # Context-aware navigation: physical for DEFINE, logical for MEASURES
                    if self.evaluation_mode == 'DEFINE':
                        return self.evaluate_physical_navigation(func_name, column, steps)
                    else:
                        return self.evaluate_navigation_function(func_name, column, steps)
                else:
                    # Use new navigation handler for FIRST/LAST with simple column format
                    return self._handle_first_last_navigation(func_name, column, steps, None)
                    
            elif isinstance(first_arg, ast.Call):
                # Handle nested function calls like NEXT(CLASSIFIER()) and PREV(CLASSIFIER(U))
                if isinstance(first_arg.func, ast.Name) and first_arg.func.id.upper() == "CLASSIFIER":
                    # Extract subset variable if present
                    subset_var = None
                    if len(first_arg.args) > 0 and isinstance(first_arg.args[0], ast.Name):
                        subset_var = first_arg.args[0].id
                    
                    # Special case: Navigation with CLASSIFIER
                    classifier_steps = steps if len(node.args) > 1 else (
                        0 if func_name in ("FIRST", "LAST") else 1
                    )
                    return self._handle_classifier_navigation(
                        func_name, subset_var, classifier_steps
                    )
                else:
                    # For other nested calls, evaluate the argument first
                    evaluated_arg = self.visit(first_arg)
                    if evaluated_arg is not None:
                        # Use the evaluated result as a column name
                        column = str(evaluated_arg)
                        if func_name in ("PREV", "NEXT"):
                            if self.evaluation_mode == 'DEFINE':
                                return self.evaluate_physical_navigation(func_name, column, steps)
                            else:
                                return self.evaluate_navigation_function(func_name, column, steps)
                        else:
                            # Use new navigation handler for FIRST/LAST with nested calls
                            return self._handle_first_last_navigation(func_name, column, steps, None)
                    else:
                        return None
            elif func_name in ("FIRST", "LAST"):
                # SQL logical navigation accepts a value expression, not only
                # a bare column.  Evaluate that expression at the selected
                # matched row (e.g. FIRST(A.x > 0 OR EXISTS(...))).
                variables = getattr(self.context, "_full_match_variables", None) or getattr(
                    self.context, "variables", {}
                )
                indices = sorted({idx for values in variables.values() for idx in values})
                current_idx = self.context.current_idx
                if self.evaluation_mode == "DEFINE":
                    indices = [idx for idx in indices if idx <= current_idx]
                    if current_idx not in indices:
                        indices.append(current_idx)
                        indices.sort()
                if not indices:
                    return None
                occurrence = int(steps or 0)
                target_pos = occurrence if func_name == "FIRST" else len(indices) - 1 - occurrence
                if not 0 <= target_pos < len(indices):
                    return None
                target_idx = indices[target_pos]
                old_idx = self.context.current_idx
                old_row = self.current_row
                old_context_row = getattr(self.context, "current_row", None)
                try:
                    self.context.current_idx = target_idx
                    self.current_row = self.context.rows[target_idx]
                    self.context.current_row = self.current_row
                    return self.visit(first_arg)
                finally:
                    self.context.current_idx = old_idx
                    self.current_row = old_row
                    self.context.current_row = old_context_row
            else:
                raise ValueError(f"Unsupported argument type for {func_name}: {type(first_arg)}")
    
    def _handle_classifier_navigation(self, func_name: str, subset_var: Optional[str], steps: int) -> Any:
        """Handle navigation functions with CLASSIFIER arguments."""
        if func_name in ("PREV", "NEXT"):
            # For PREV/NEXT with CLASSIFIER, navigate through classifier values
            if subset_var and subset_var in self.context.subsets:
                # Direct subset navigation without recursion
                subset_components = self.context.subsets[subset_var]
                all_subset_indices = []
                for comp_var in subset_components:
                    if comp_var in self.context.variables:
                        all_subset_indices.extend(self.context.variables[comp_var])
                
                if all_subset_indices:
                    all_subset_indices = sorted(set(all_subset_indices))
                    current_idx = self.context.current_idx
                    
                    # Enhanced logic: navigate from current position even if not in subset
                    if func_name == "PREV":
                        # Find the most recent subset position before current_idx
                        target_indices = [idx for idx in all_subset_indices if idx < current_idx]
                        if target_indices and steps <= len(target_indices):
                            target_idx = target_indices[-steps]  # steps positions back
                            return self._get_direct_classifier_at_index(target_idx, subset_var)
                        else:
                            return None
                    else:  # NEXT
                        # Find the next subset position after current_idx
                        target_indices = [idx for idx in all_subset_indices if idx > current_idx]
                        if target_indices and steps <= len(target_indices):
                            target_idx = target_indices[steps - 1]  # steps positions forward
                            return self._get_direct_classifier_at_index(target_idx, subset_var)
                        else:
                            return None
                else:
                    return None
            else:
                # Regular CLASSIFIER() without subset - use timeline navigation
                current_idx = self.context.current_idx
                target_idx = current_idx + steps if func_name == "NEXT" else current_idx - steps
                
                # Check bounds
                if target_idx < 0 or target_idx >= len(self.context.rows):
                    return None
                
                return self._get_direct_classifier_at_index(target_idx, None)
                
        elif func_name in ("FIRST", "LAST"):
            # Handle FIRST/LAST with CLASSIFIER
            return self._handle_first_last_classifier(func_name, subset_var, steps)
        else:
            logger.error(f"{func_name}(CLASSIFIER()) not yet supported")
            return None
    
    def _handle_first_last_classifier(self, func_name: str, subset_var: Optional[str], steps: int) -> Any:
        """Handle FIRST/LAST with CLASSIFIER arguments."""
        if func_name.upper() == 'LAST':
            if subset_var and subset_var in self.context.subsets:
                # Get the last classifier in the subset
                subset_components = self.context.subsets[subset_var]
                all_subset_indices = []
                for comp_var in subset_components:
                    if comp_var in self.context.variables:
                        all_subset_indices.extend(self.context.variables[comp_var])
                
                if all_subset_indices:
                    all_subset_indices = sorted(set(all_subset_indices))
                    
                    # Handle steps parameter for LAST function - relative to current position
                    if steps > 0:
                        # LAST(CLASSIFIER(subset), N) means N positions back from current
                        current_idx = self.context.current_idx
                        target_idx = current_idx - steps
                        if target_idx < 0 or target_idx not in all_subset_indices:
                            return None
                        return self._get_direct_classifier_at_index(target_idx, subset_var)
                    else:
                        # LAST(CLASSIFIER(subset)) means the most recent position in subset
                        target_idx = all_subset_indices[-1]
                        return self._get_direct_classifier_at_index(target_idx, subset_var)
            else:
                # Get the last classifier in the overall match
                if hasattr(self.context, 'variables') and self.context.variables:
                    # Handle steps parameter for LAST function - relative to current position
                    if steps > 0:
                        # LAST(CLASSIFIER(), N) means N positions back from current
                        current_idx = self.context.current_idx
                        target_idx = current_idx - steps
                        logger.debug(f"[LAST_DEBUG] LAST(CLASSIFIER(), {steps}): current_idx={current_idx}, target_idx={target_idx}")
                        if target_idx < 0:
                            logger.debug(f"[LAST_DEBUG] target_idx={target_idx} < 0, returning None")
                            return None
                        result = self._get_direct_classifier_at_index(target_idx, None)
                        logger.debug(f"[LAST_DEBUG] _get_direct_classifier_at_index({target_idx}) returned: {result}")
                        return result
                    else:
                        # LAST(CLASSIFIER()) means the most recent position in match
                        # Find all row indices across all variables in current match
                        all_indices = []
                        for var, indices in self.context.variables.items():
                            all_indices.extend(indices)
                        
                        if all_indices:
                            all_indices = sorted(set(all_indices))
                            target_idx = all_indices[-1]
                            return self._get_direct_classifier_at_index(target_idx, None)
                        else:
                            return None
                else:
                    return None
        
        elif func_name.upper() == 'FIRST':
            if subset_var and subset_var in self.context.subsets:
                # Get the first classifier in the subset
                subset_components = self.context.subsets[subset_var]
                all_subset_indices = []
                for comp_var in subset_components:
                    if comp_var in self.context.variables:
                        all_subset_indices.extend(self.context.variables[comp_var])
                
                if all_subset_indices:
                    all_subset_indices = sorted(set(all_subset_indices))
                    
                    # Handle steps parameter for FIRST function  
                    if steps > len(all_subset_indices):
                        return None
                    target_idx = all_subset_indices[steps - 1] if steps > 0 else all_subset_indices[0]
                    
                    return self._get_direct_classifier_at_index(target_idx, subset_var)
            else:
                # Get the first classifier in the overall match
                if hasattr(self.context, 'variables') and self.context.variables:
                    # Find all row indices across all variables in current match
                    all_indices = []
                    for var, indices in self.context.variables.items():
                        all_indices.extend(indices)
                    
                    if all_indices:
                        all_indices = sorted(set(all_indices))
                        # Handle steps parameter for FIRST function
                        if steps > len(all_indices):
                            return None
                        target_idx = all_indices[steps - 1] if steps > 0 else all_indices[0]
                        
                        return self._get_direct_classifier_at_index(target_idx, None)
                    else:
                        return None
                else:
                    return None
        
        return None

    def visit_Attribute(self, node: ast.Attribute):
        """Handle pattern variable references (A.price or "b".price) with table prefix validation"""
        if isinstance(node.value, ast.Name):
            var = node.value.id
            col = node.attr
            
            # Table prefix validation: prevent forbidden table.column references
            if self._is_table_prefix_in_context(var):
                raise ValueError(f"Forbidden table prefix reference: '{var}.{col}'. "
                               f"In MATCH_RECOGNIZE, use pattern variable references instead of table references")
            
            # Handle pattern variable references
            result = self._get_variable_column_value(var, col, self.context)
            
            return result
        elif isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            # Handle quoted identifiers like "b".value
            var = f'"{node.value.value}"'  # Preserve quotes for consistency with context storage
            col = node.attr
            
            # Handle pattern variable references for quoted identifiers
            result = self._get_variable_column_value(var, col, self.context)
            
            return result
        
        # If we can't extract a pattern var reference, try regular attribute access
        obj = self.visit(node.value)
        if obj is not None:
            return getattr(obj, node.attr, None)
        
        return None

    def visit_BinOp(self, node: ast.BinOp):
        """Handle binary operations (addition, subtraction, multiplication, etc.)"""
        import operator
        
        # Map AST operators to Python operators
        op_map = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.LShift: operator.lshift,
            ast.RShift: operator.rshift,
            ast.BitOr: operator.or_,
            ast.BitXor: operator.xor,
            ast.BitAnd: operator.and_,
        }
        
        try:
            left = self.visit(node.left)
            right = self.visit(node.right)
            op = op_map.get(type(node.op))
            
            if op is None:
                raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
            
            # Handle None values - if either operand is None, result is None (SQL semantics)
            if left is None or right is None:
                return None
                
            result = op(left, right)
                
            logger.debug(f"[DEBUG] BinOp: {left} {type(node.op).__name__} {right} = {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in binary operation: {e}")
            return None

    def visit_UnaryOp(self, node: ast.UnaryOp):
        """Handle unary operations (not, -, +, ~)"""
        import operator
        
        # Map AST unary operators to Python operators
        op_map = {
            ast.Not: operator.not_,
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
            ast.Invert: operator.invert,
        }
        
        try:
            operand = self.visit(node.operand)
            op = op_map.get(type(node.op))
            
            if op is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
            
            # Handle None values - SQL semantics
            if operand is None:
                return None
                
            result = op(operand)
            logger.debug(f"[DEBUG] UnaryOp: {type(node.op).__name__} {operand} = {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in unary operation: {e}")
            return None

    def _is_table_prefix_in_context(self, var_name: str) -> bool:
        """
        Check if a variable name looks like a table prefix in the current context.
        
        Args:
            var_name: The variable name to check
            
        Returns:
            True if this looks like a forbidden table prefix, False otherwise
        """
        # If it's a defined pattern variable, it's not a table prefix
        if hasattr(self.context, 'variables') and var_name in self.context.variables:
            return False
        if hasattr(self.context, 'subsets') and self.context.subsets and var_name in self.context.subsets:
            return False
        
        # Use the shared utility function
        return is_table_prefix(var_name, 
                              getattr(self.context, 'variables', {}),
                              getattr(self.context, 'subsets', {}))

    def _handle_window_function(self, node: ast.Call, func_name: str):
        """Handle LAG and LEAD window functions"""
        if not hasattr(self.context, 'rows') or not self.context.rows or not self.current_row:
            return None
            
        args = [self.visit(arg) for arg in node.args]
        
        if len(args) == 0:
            # No arguments - not valid for LAG/LEAD
            raise ValueError(f"{func_name} function requires at least one argument (column name)")
        
        # First argument should be the column name/expression
        column_expr = args[0]
        
        # Second argument is offset (default 1)
        offset = args[1] if len(args) > 1 else 1
        
        # Third argument is default value (default None)
        default = args[2] if len(args) > 2 else None
        
        # Get current row index using context
        current_idx = self.context.current_idx
        if current_idx < 0 or current_idx >= len(self.context.rows):
            return default
            
        # Calculate target index
        if func_name == "LAG":
            target_idx = current_idx - offset
        else:  # LEAD
            target_idx = current_idx + offset
            
        # Check bounds
        if target_idx < 0 or target_idx >= len(self.context.rows):
            return default
            
        # Get value from target row
        target_row = self.context.rows[target_idx]
        
        # If column_expr is a string, treat it as column name
        if isinstance(column_expr, str):
            return target_row.get(column_expr, default)
        else:
            # For more complex expressions, we'd need to evaluate them in the context of target_row
            # For now, return the expression value as-is
            return column_expr

        # Updates for src/matcher/condition_evaluator.py
    def _get_variable_column_value(self, var_name: str, col_name: str, ctx: RowContext) -> Any:
        """
        Get a column value from a pattern variable's matched rows with enhanced subset support.
        
        For self-referential conditions (e.g., B.price < A.price when evaluating for B),
        use the current row's value for the variable being evaluated.
        
        Args:
            var_name: Pattern variable name
            col_name: Column name
            ctx: Row context
            
        Returns:
            Column value from the matched row or current row
        """
        # Check if we're in DEFINE evaluation mode
        is_define_mode = self.evaluation_mode == 'DEFINE'
        
        # DEBUG: Enhanced logging to trace exact values
        current_var = getattr(ctx, 'current_var', None)
        logger.debug(f"[DEBUG] _get_variable_column_value: var_name={var_name}, col_name={col_name}, is_define_mode={is_define_mode}, current_var={current_var}")
        logger.debug(f"[DEBUG] ctx.current_idx={ctx.current_idx}, ctx.variables={ctx.variables}")
        
        # CRITICAL FIX: In DEFINE mode, we need special handling for pattern variable references
        if is_define_mode:
            # CRITICAL FIX: When evaluating B's condition, B.price should use the current row
            # but A.price should use A's previously matched row
            if var_name == current_var or (current_var is None and var_name in self.visit_stack):
                # Self-reference: use current row being tested
                logger.debug(f"[DEBUG] DEFINE mode - self-reference for {var_name}.{col_name}")
                if ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                    value = ctx.rows[ctx.current_idx].get(col_name)
                    logger.debug(f"[DEBUG] Self-reference value: {var_name}.{col_name} = {value} (from row {ctx.current_idx})")
                    return value
                else:
                    logger.debug(f"[DEBUG] Self-reference: invalid current_idx {ctx.current_idx}")
                    return None
            else:
                # Cross-reference: use previously matched row for this variable
                logger.debug(f"[DEBUG] DEFINE mode - cross-reference for {var_name}.{col_name}")
                
                # Check if this is a subset variable
                if hasattr(ctx, 'subsets') and var_name in ctx.subsets:
                    # For subset variables, find the last row matched to any component variable
                    component_vars = ctx.subsets[var_name]
                    last_idx = -1
                    
                    for comp_var in component_vars:
                        if comp_var in ctx.variables:
                            var_indices = ctx.variables[comp_var]
                            if var_indices:
                                last_var_idx = max(var_indices)
                                if last_var_idx > last_idx:
                                    last_idx = last_var_idx
                    
                    if last_idx >= 0 and last_idx < len(ctx.rows):
                        value = ctx.rows[last_idx].get(col_name)
                        logger.debug(f"[DEBUG] Subset cross-reference value: {var_name}.{col_name} = {value} (from row {last_idx})")
                        return value
                
                # Get the value from the last row matched to this variable
                var_indices = ctx.variables.get(var_name, [])
                logger.debug(f"[DEBUG] Looking for {var_name} in ctx.variables: {var_indices}")
                if var_indices:
                    last_idx = max(var_indices)
                    if last_idx < len(ctx.rows):
                        value = ctx.rows[last_idx].get(col_name)
                        logger.debug(f"[DEBUG] Cross-reference value: {var_name}.{col_name} = {value} (from row {last_idx})")
                        return value
                    else:
                        logger.debug(f"[DEBUG] Cross-reference: invalid last_idx {last_idx}")
                        return None
                
                # If no rows matched yet, this variable hasn't been matched
                logger.debug(f"[DEBUG] Cross-reference: no rows matched for {var_name} yet")
                return None
        
        # For non-DEFINE modes (MEASURES mode), use standard logic
        
        # Track if we're evaluating a condition for the same variable (self-reference)
        is_self_reference = False
        
        # If we have current_var set, this is a direct check for self-reference
        if hasattr(ctx, 'current_var') and ctx.current_var == var_name:
            is_self_reference = True
        
        # Otherwise check if current row is already assigned to this variable
        if not is_self_reference and hasattr(ctx, 'current_var_assignments'):
            if var_name in ctx.current_var_assignments and ctx.current_idx in ctx.current_var_assignments[var_name]:
                is_self_reference = True
        
        # For self-references in other modes, use the current row's value
        if is_self_reference:
            if self.current_row is not None:
                return self.current_row.get(col_name)
            elif ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                return ctx.rows[ctx.current_idx].get(col_name)
        
        # Check if this is a subset variable
        if hasattr(ctx, 'subsets') and var_name in ctx.subsets:
            # For subset variables in MEASURES mode, return the value from the current row
            # if the current row matches any component of the subset
            component_vars = ctx.subsets[var_name]
            current_idx = ctx.current_idx
            
            # Check if current row matches any component of this subset
            for comp_var in component_vars:
                if comp_var in ctx.variables and current_idx in ctx.variables[comp_var]:
                    # Current row matches this component, return its value
                    if current_idx >= 0 and current_idx < len(ctx.rows):
                        return ctx.rows[current_idx].get(col_name)
            
            # If current row doesn't match any component, fall back to original logic
            # (find the last row matched to any component variable)
            last_idx = -1
            for comp_var in component_vars:
                if comp_var in ctx.variables:
                    var_indices = ctx.variables[comp_var]
                    if var_indices:
                        last_var_idx = max(var_indices)
                        if last_var_idx > last_idx:
                            last_idx = last_var_idx
            
            if last_idx >= 0 and last_idx < len(ctx.rows):
                return ctx.rows[last_idx].get(col_name)
        
        # CRITICAL FIX: For RUNNING aggregates in MEASURES mode, use current row instead of last matched row
        # This is essential for conditional aggregates like COUNT_IF, SUM_IF, AVG_IF
        if (self.evaluation_mode == 'MEASURES' and 
            hasattr(ctx, 'current_idx') and 
            ctx.current_idx >= 0 and 
            ctx.current_idx < len(ctx.rows)):
            
            # Check if the current row is within the variable's matched indices
            var_indices = ctx.variables.get(var_name, [])
            if var_indices and ctx.current_idx in var_indices:
                logger.debug(f"[DEBUG] RUNNING aggregate: using current row {ctx.current_idx} for {var_name}.{col_name}")
                value = ctx.rows[ctx.current_idx].get(col_name)
                logger.debug(f"[DEBUG] RUNNING aggregate value: {var_name}.{col_name} = {value} (from current row {ctx.current_idx})")
                return value
        
        # Otherwise, get the value from the last row matched to this variable (traditional behavior)
        var_indices = ctx.variables.get(var_name, [])
        if var_indices:
            last_idx = max(var_indices)
            if last_idx < len(ctx.rows):
                logger.debug(f"[DEBUG] Using traditional last row logic: {var_name}.{col_name} from row {last_idx}")
                return ctx.rows[last_idx].get(col_name)
        
        # If no rows matched yet, use the current row's value
        # This is important for the first evaluation of a pattern variable
        if self.current_row is not None:
            return self.current_row.get(col_name)
        elif ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
            return ctx.rows[ctx.current_idx].get(col_name)
        
        return None

    def _handle_subset_navigation(self, var_name, column, nav_type, steps, cache_key):
        """Handle navigation for subset variables with enhanced logic."""
        logger.debug(f"[NAV_ENHANCED] Processing subset variable: {var_name}")
        
        component_vars = self.context.subsets[var_name]
        all_indices = []
        
        # Collect indices from all component variables
        for comp_var in component_vars:
            if comp_var in self.context.variables:
                all_indices.extend(self.context.variables[comp_var])
        
        if not all_indices:
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Sort and deduplicate indices
        all_indices = sorted(set(all_indices))
        
        # Apply steps parameter for subset navigation
        if nav_type == 'FIRST':
            if steps > len(all_indices):
                idx = None
            else:
                idx = all_indices[steps - 1] if steps > 0 else all_indices[0]
        else:  # LAST
            if steps > len(all_indices):
                idx = None
            else:
                idx = all_indices[-steps] if steps > 0 else all_indices[-1]
        
        if idx is None or not (0 <= idx < len(self.context.rows)):
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Check partition boundaries
        if self._check_partition_boundary(self.context.current_idx, idx):
            result = self.context.rows[idx].get(column)
            self.context.navigation_cache[cache_key] = result
            return result
        
        self.context.navigation_cache[cache_key] = None
        return None

    def _build_optimized_timeline(self):
        """Build an optimized timeline of variable assignments."""
        # Use cached timeline if available and valid
        if (hasattr(self.context, '_timeline') and 
            hasattr(self.context, '_timeline_version') and
            self.context._timeline_version == id(self.context.variables)):
            return self.context._timeline
        
        logger.debug(f"[NAV_ENHANCED] Building optimized timeline from variables: {self.context.variables}")
        
        # Build timeline with improved algorithm
        timeline = []
        for var, indices in self.context.variables.items():
            for idx in indices:
                timeline.append((idx, var))
        
        # Sort by row index for consistent ordering
        timeline.sort()
        
        # Cache with version tracking
        self.context._timeline = timeline
        self.context._timeline_version = id(self.context.variables)
        
        logger.debug(f"[NAV_ENHANCED] Built timeline with {len(timeline)} entries")
        return timeline

    def _handle_logical_navigation(self, var_name, column, nav_type, steps, timeline, cache_key):
        """Handle FIRST/LAST navigation with enhanced logic."""
        logger.debug(f"[NAV_ENHANCED] Logical navigation: {nav_type}({var_name}.{column})")
        
        if var_name is None:
            # Navigate across all variables in the match
            all_indices = []
            for var, indices in self.context.variables.items():
                all_indices.extend(indices)
            
            if not all_indices:
                self.context.navigation_cache[cache_key] = None
                return None
            
            all_indices = sorted(set(all_indices))
            idx = all_indices[0] if nav_type == 'FIRST' else all_indices[-1]
            
        elif var_name not in self.context.variables or not self.context.variables[var_name]:
            logger.debug(f"[NAV_ENHANCED] Variable {var_name} not found or empty")
            self.context.navigation_cache[cache_key] = None
            return None
        else:
            # Navigate within specific variable
            var_indices = sorted(set(self.context.variables[var_name]))
            
            if not var_indices:
                self.context.navigation_cache[cache_key] = None
                return None
            
            # Apply steps parameter for logical navigation
            if nav_type == 'FIRST':
                if steps > len(var_indices):
                    idx = None
                else:
                    idx = var_indices[steps - 1] if steps > 0 else var_indices[0]
            else:  # LAST
                if steps > len(var_indices):
                    idx = None
                else:
                    idx = var_indices[-steps] if steps > 0 else var_indices[-1]
        
        if idx is None or not (0 <= idx < len(self.context.rows)):
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Enhanced boundary checking
        if self._check_partition_boundary(self.context.current_idx, idx):
            result = self.context.rows[idx].get(column)
            self.context.navigation_cache[cache_key] = result
            return result
        
        self.context.navigation_cache[cache_key] = None
        return None

    def _handle_physical_navigation_define(self, column, nav_type, steps, cache_key):
        """Handle PREV/NEXT navigation in DEFINE mode (physical navigation)."""
        logger.debug(f"[NAV_ENHANCED] Physical navigation in DEFINE mode: {nav_type}({column}, {steps})")
        
        # For DEFINE mode, navigate through physical input sequence
        curr_idx = self.context.current_idx
        
        if nav_type == 'PREV':
            target_idx = curr_idx - steps
        else:  # NEXT
            target_idx = curr_idx + steps
        
        # Enhanced bounds checking
        if target_idx < 0 or target_idx >= len(self.context.rows):
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Check partition boundaries for physical navigation
        if self._check_partition_boundary(curr_idx, target_idx):
            result = self.context.rows[target_idx].get(column)
            self.context.navigation_cache[cache_key] = result
            return result
        
        self.context.navigation_cache[cache_key] = None
        return None

    def _handle_logical_timeline_navigation(self, var_name, column, nav_type, steps, timeline, cache_key, current_var):
        """Handle PREV/NEXT navigation through pattern timeline."""
        logger.debug(f"[NAV_ENHANCED] Timeline navigation: {nav_type}({column}, {steps}) for var={var_name}")
        
        if not timeline:
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Find current position in timeline
        curr_idx = self.context.current_idx
        curr_pos = -1
        
        # Enhanced position finding with variable context
        for i, (idx, var) in enumerate(timeline):
            if idx == curr_idx and (current_var is None or var == current_var or var_name is None):
                curr_pos = i
                break
        
        if curr_pos < 0:
            # Try alternative matching strategies
            for i, (idx, var) in enumerate(timeline):
                if idx == curr_idx:
                    curr_pos = i
                    break
        
        if curr_pos < 0:
            self.context.navigation_cache[cache_key] = None
            return None
        
        # Calculate target position
        if nav_type == 'PREV':
            target_pos = curr_pos - steps
        else:  # NEXT
            target_pos = curr_pos + steps
        
        # Bounds checking for timeline
        if target_pos < 0 or target_pos >= len(timeline):
            self.context.navigation_cache[cache_key] = None
            return None
        
        target_idx, _ = timeline[target_pos]
        
        # Enhanced boundary checking
        if self._check_partition_boundary(curr_idx, target_idx):
            if 0 <= target_idx < len(self.context.rows):
                result = self.context.rows[target_idx].get(column)
                self.context.navigation_cache[cache_key] = result
                return result
        
        self.context.navigation_cache[cache_key] = None
        return None

    def _check_partition_boundary(self, curr_idx, target_idx):
        """Enhanced partition boundary checking."""
        if not hasattr(self.context, 'partition_boundaries') or not self.context.partition_boundaries:
            return True  # No partition boundaries defined
        
        try:
            curr_partition = self.context.get_partition_for_row(curr_idx)
            target_partition = self.context.get_partition_for_row(target_idx)
            
            return (curr_partition is not None and 
                   target_partition is not None and 
                   curr_partition == target_partition)
        except Exception as e:
            logger.warning(f"Error checking partition boundary: {e}")
            return True  # Default to allowing navigation on error

    def _get_classifier(self, variable: Optional[str] = None) -> str:
        """Get the classifier (pattern variable name) for the current or specified position."""
        if variable is not None:
            # Check if this is a subset variable
            if hasattr(self.context, 'subsets') and variable in self.context.subsets:
                # For subset variables, return the component variable that matches the current row
                current_idx = self.context.current_idx
                for comp in self.context.subsets[variable]:
                    if comp in self.context.variables and current_idx in self.context.variables[comp]:
                        return comp.strip('"')
                # CLASSIFIER(subset) is NULL when the current row was not
                # classified by one of that subset's primary variables.  The
                # subset name itself is never a row classifier.
                return None
            else:
                # Return the specific variable name for non-subset variables
                return variable
        
        # Get the classifier for the current row
        current_idx = self.context.current_idx
        self._ensure_evaluation_indices()
        
        # Check which variable(s) this row belongs to
        if hasattr(self, '_row_var_index') and current_idx in self._row_var_index:
            variables = self._row_var_index[current_idx]
            if len(variables) == 1:
                return next(iter(variables))
            elif len(variables) > 1:
                # Multiple variables - return the first one alphabetically for consistency
                return min(variables)
        
        # Fallback to searching through all variables
        for var_name, indices in self.context.variables.items():
            if current_idx in indices:
                return var_name

        # The row being tested in DEFINE carries its tentative label
        tentative = getattr(self.context, 'current_var', None)
        if tentative:
            return tentative

        # If no variable found, return empty string
        return ""
    
    def _get_direct_classifier_at_index(self, row_idx: int, subset_var: Optional[str] = None) -> str:
        """
        Get the classifier value directly at a specific row index without recursion.
        
        Args:
            row_idx: The row index to get the classifier for
            subset_var: Optional subset variable name
            
        Returns:
            The classifier value at the specified index
        """
        logger.debug(f"[CLASSIFIER_DEBUG] _get_direct_classifier_at_index(row_idx={row_idx}, subset_var={subset_var})")
        
        if subset_var:
            # For subset variables, return the actual component variable name that matches
            if subset_var in self.context.subsets:
                component_vars = self.context.subsets[subset_var]
                for comp_var in component_vars:
                    if comp_var in self.context.variables and row_idx in self.context.variables[comp_var]:
                        logger.debug(f"[CLASSIFIER_DEBUG] Found subset component {comp_var} for row {row_idx}")
                        return comp_var  # Return the actual component variable, not the subset name
            logger.debug(f"[CLASSIFIER_DEBUG] No subset component found for row {row_idx}, returning empty string")
            return ""
        
        # Check which variable this row belongs to
        logger.debug(f"[CLASSIFIER_DEBUG] Context variables: {self.context.variables}")
        
        if hasattr(self, '_row_var_index') and row_idx in self._row_var_index:
            variables = self._row_var_index[row_idx]
            logger.debug(f"[CLASSIFIER_DEBUG] Found in _row_var_index: {variables}")
            if len(variables) == 1:
                result = next(iter(variables))
                logger.debug(f"[CLASSIFIER_DEBUG] Single variable: {result}")
                return result
            elif len(variables) > 1:
                # Multiple variables - return the first one alphabetically for consistency
                result = min(variables)
                logger.debug(f"[CLASSIFIER_DEBUG] Multiple variables, returning: {result}")
                return result
        
        # Fallback to searching through all variables
        for var_name, indices in self.context.variables.items():
            if row_idx in indices:
                logger.debug(f"[CLASSIFIER_DEBUG] Found row {row_idx} in variable {var_name}")
                return var_name
        
        logger.debug(f"[CLASSIFIER_DEBUG] No variable found for row {row_idx}, returning empty string")
        return ""

    def _build_navigation_expr(self, node):
        """
        Convert an AST navigation function call to a string representation.
        
        This handles both simple and nested navigation functions:
        - PREV(price)
        - FIRST(A.price)
        - PREV(FIRST(A.price))
        - PREV(FIRST(A.price), 2)
        
        Args:
            node: The AST Call node representing the navigation function
            
        Returns:
            String representation of the navigation expression
        """
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.upper()
        else:
            # Can't determine function name
            return ""
            
        # Build argument list
        args = []
        for arg in node.args:
            if isinstance(arg, ast.Name):
                # Simple identifier
                args.append(arg.id)
            elif isinstance(arg, ast.Constant):
                # Literal value
                args.append(str(arg.value))
            elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                # Pattern variable reference (A.price)
                args.append(f"{arg.value.id}.{arg.attr}")
            elif isinstance(arg, ast.Call):
                # Nested navigation function
                args.append(self._build_navigation_expr(arg))
            else:
                # Complex expression
                try:
                    if hasattr(ast, 'unparse'):
                        args.append(ast.unparse(arg).strip())
                    else:
                        # For Python versions < 3.9 that don't have ast.unparse
                        import astunparse
                        args.append(astunparse.unparse(arg).strip())
                except (ImportError, AttributeError):
                    # Fallback
                    args.append(str(arg))
                
        # Combine into navigation expression
        return f"{func_name}({', '.join(args)})"

    def evaluate_physical_navigation(self, nav_type, column, steps=1):
        """
        Physical navigation for DEFINE conditions.
        
        This method implements the correct SQL:2016 semantics for navigation functions
        in DEFINE conditions, where PREV/NEXT refer to the previous/next row in the
        input sequence (ordered by ORDER BY), not in the pattern match.
        
        Args:
            nav_type: Type of navigation ('PREV' or 'NEXT')
            column: Column name to retrieve
            steps: Number of steps to navigate (default: 1)
            
        Returns:
            The value at the navigated position or None if navigation is invalid
        """
        # Debug logging
        logger = get_logger(__name__)
        logger.debug(f"PHYSICAL_NAV: {nav_type}({column}, {steps}) at current_idx={self.context.current_idx}")
        
        # Input validation
        if steps < 0:
            raise ValueError(f"Navigation steps must be non-negative: {steps}")
            
        if nav_type not in ('PREV', 'NEXT'):
            raise ValueError(f"Invalid navigation type: {nav_type}")
        
        # Get current row index in the input sequence
        curr_idx = self.context.current_idx
        
        # Bounds check for current index
        if curr_idx < 0 or curr_idx >= len(self.context.rows):
            logger.debug(f"PHYSICAL_NAV: curr_idx {curr_idx} out of bounds [0, {len(self.context.rows)})")
            return None
            
        # Special case for steps=0 (return current row's value)
        if steps == 0:
            result = self.context.rows[curr_idx].get(column)
            logger.debug(f"PHYSICAL_NAV: steps=0, returning current row value: {result}")
            return result
            
        # Calculate target index based on navigation type
        if nav_type == 'PREV':
            target_idx = curr_idx - steps
        else:  # NEXT
            target_idx = curr_idx + steps
            
        logger.debug(f"PHYSICAL_NAV: target_idx={target_idx} (curr_idx={curr_idx}, nav={nav_type}, steps={steps})")
            
        # Check index bounds
        if target_idx < 0 or target_idx >= len(self.context.rows):
            logger.debug(f"PHYSICAL_NAV: target_idx {target_idx} out of bounds [0, {len(self.context.rows)})")
            return None
            
        # Check partition boundaries if defined
        # Physical navigation respects partition boundaries
        if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
            current_partition = self.context.get_partition_for_row(curr_idx)
            target_partition = self.context.get_partition_for_row(target_idx)
            
            if (current_partition is None or target_partition is None or
                current_partition != target_partition):
                logger.debug(f"PHYSICAL_NAV: partition boundary violation")
                return None
                
        # Get the value from the target row
        result = self.context.rows[target_idx].get(column)
        logger.debug(f"PHYSICAL_NAV: returning value from row {target_idx}: {result}")
        return result

    def evaluate_variable_aware_navigation(self, nav_type, var_name, column, steps=1):
        """
        Variable-aware navigation for DEFINE conditions with pattern variable references.
        
        This method implements the correct SQL:2016 semantics for navigation functions
        like PREV(A.price) in DEFINE conditions. PREV(A.price) means "the previous row
        that was assigned to variable A", not just "the previous physical row".
        
        For example, in the condition:
            A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL
        
        When evaluating the first row for variable A, there are no previous A assignments,
        so PREV(A.price) returns NULL, making the condition TRUE.
        
        Args:
            nav_type: Type of navigation ('PREV' or 'NEXT')
            var_name: Variable name to navigate within (e.g., 'A')
            column: Column name to retrieve
            steps: Number of steps to navigate (default: 1)
            
        Returns:
            The value at the navigated position or None if navigation is invalid
        """
        logger = get_logger(__name__)
        logger.debug(f"[VAR_NAV] {nav_type}({var_name}.{column}, {steps}) at current_idx={self.context.current_idx}")
        
        # Input validation
        if steps < 0:
            raise ValueError(f"Navigation steps must be non-negative: {steps}")
            
        if nav_type not in ('PREV', 'NEXT'):
            raise ValueError(f"Invalid navigation type: {nav_type}")
        
        # Get currently assigned indices for this variable
        var_indices = self.context.variables.get(var_name, [])
        
        # If no rows assigned to this variable yet, return None
        if not var_indices:
            logger.debug(f"[VAR_NAV] No rows assigned to {var_name} yet, returning None")
            return None
        
        # Sort indices to ensure consistent ordering
        sorted_indices = sorted(var_indices)
        
        # Find the current position in the variable's assignment sequence
        curr_idx = self.context.current_idx
        
        # If current row is not yet assigned to this variable, we're evaluating
        # whether it should be assigned. In this case, look at the last assigned row.
        if curr_idx not in var_indices:
            if nav_type == 'PREV':
                # For PREV, use the last assigned row
                if sorted_indices:
                    target_idx = sorted_indices[-1]
                    result = self.context.rows[target_idx].get(column)
                    logger.debug(f"[VAR_NAV] Current row not in {var_name}, using last assigned row {target_idx}: {result}")
                    return result
                else:
                    logger.debug(f"[VAR_NAV] No previous {var_name} rows, returning None")
                    return None
            else:  # NEXT
                # For NEXT, there's no "next" row since we're at evaluation boundary
                logger.debug(f"[VAR_NAV] NEXT navigation not valid during evaluation, returning None")
                return None
        
        # Current row is in the variable's assignment, find its position
        try:
            pos = sorted_indices.index(curr_idx)
        except ValueError:
            logger.debug(f"[VAR_NAV] Current row {curr_idx} not found in {var_name} indices")
            return None
        
        # Calculate target position
        if nav_type == 'PREV':
            target_pos = pos - steps
        else:  # NEXT
            target_pos = pos + steps
        
        # Check bounds
        if target_pos < 0 or target_pos >= len(sorted_indices):
            logger.debug(f"[VAR_NAV] Target position {target_pos} out of bounds [0, {len(sorted_indices)})")
            return None
        
        # Get target row index
        target_idx = sorted_indices[target_pos]
        
        # Check partition boundaries if defined
        if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
            current_partition = self.context.get_partition_for_row(curr_idx)
            target_partition = self.context.get_partition_for_row(target_idx)
            
            if (current_partition is None or target_partition is None or
                current_partition != target_partition):
                logger.debug(f"[VAR_NAV] Partition boundary violation")
                return None
        
        # Get the value from the target row
        result = self.context.rows[target_idx].get(column)
        logger.debug(f"[VAR_NAV] Returning value from {var_name} row {target_idx}: {result}")
        return result

    def evaluate_navigation_function(self, nav_type, column, steps=1, var_name=None):
        """
        Context-aware navigation function that uses different strategies based on evaluation mode.
        
        DEFINE Mode (Physical Navigation):
        - PREV/NEXT navigate through the input table rows in ORDER BY sequence
        - Used for condition evaluation: B.price < PREV(price)
        
        MEASURES Mode (Logical Navigation):
        - PREV/NEXT navigate through pattern match results
        - Used for value extraction: FIRST(A.order_date)
        
        Args:
            nav_type: Type of navigation ('PREV' or 'NEXT')
            column: Column name to retrieve
            steps: Number of steps to navigate (default: 1)
            var_name: Optional variable name for context
            
        Returns:
            The value at the navigated position or None if navigation is invalid
        """
        logger = get_logger(__name__)
        logger.debug(f"🔍 [NAV_MAIN] evaluate_navigation_function called: nav_type={nav_type}, column={column}, steps={steps}, var_name={var_name}")
        
        # Input validation
        if steps < 0:
            raise ValueError(f"Navigation steps must be non-negative: {steps}")
            
        if nav_type not in ('PREV', 'NEXT', 'FIRST', 'LAST'):
            raise ValueError(f"Invalid navigation type: {nav_type}")
        
        # Special case for steps=0 (return current row's value)
        if steps == 0:
            if 0 <= self.context.current_idx < len(self.context.rows):
                return self.context.rows[self.context.current_idx].get(column)
            return None

        # Handle FIRST and LAST functions
        if nav_type in ('FIRST', 'LAST'):
            logger.debug(f"🔍 [NAV_MAIN] Routing {nav_type} to _handle_first_last_navigation")
            return self._handle_first_last_navigation(nav_type, column, steps, var_name)
        
        # DEFINE Mode: Physical Navigation through input sequence (PREV/NEXT)
        if self.evaluation_mode == 'DEFINE':
            return self._physical_navigation(nav_type, column, steps)
        
        # MEASURES Mode: Logical Navigation through pattern matches (PREV/NEXT)
        else:
            return self._logical_navigation(nav_type, column, steps, var_name)
    
    def _physical_navigation(self, nav_type, column, steps):
        """
        Enhanced physical navigation for DEFINE conditions with production-ready optimizations.
        
        This implementation provides:
        - Direct integration with optimized context navigation methods
        - Consistent behavior across all pattern types
        - Advanced error handling and boundary validation
        - Performance optimization with early exits
        - Enhanced null handling for proper SQL semantics
        
        Args:
            nav_type: Navigation type ('PREV' or 'NEXT')
            column: Column name to retrieve
            steps: Number of steps to navigate
            
        Returns:
            The value at the navigated position or None if navigation is invalid
        """
        start_time = time.time()
        
        try:
            # Use advanced navigation methods from context
            if nav_type == 'PREV':
                row = self.context.prev(steps)
            else:  # NEXT
                row = self.context.next(steps)
                
            # Get column value with proper null handling
            result = None if row is None else row.get(column)
            
            # Track specific navigation type metrics
            if hasattr(self.context, 'stats'):
                metric_key = f"{nav_type.lower()}_navigation_calls"
                self.context.stats[metric_key] = self.context.stats.get(metric_key, 0) + 1
            
            return result
            
        except Exception as e:
            # Enhanced error handling with logging
            logger = get_logger(__name__)
            logger.error(f"Error in physical navigation ({nav_type}): {str(e)}")
            
            # Track errors
            if hasattr(self.context, 'stats'):
                self.context.stats["navigation_errors"] = self.context.stats.get("navigation_errors", 0) + 1
                
            # Set context error flag for pattern matching to handle
            self.context._navigation_context_error = True
            
            # Return None for proper SQL NULL comparison semantics
            return None
            
        finally:
            # Track performance metrics
            if hasattr(self.context, 'timing'):
                navigation_time = time.time() - start_time
                self.context.timing['physical_navigation'] = self.context.timing.get('physical_navigation', 0) + navigation_time
    
    def _logical_navigation(self, nav_type, column, steps, var_name=None):
        """
        Logical navigation for MEASURES expressions.
        Navigate through pattern match timeline using the enhanced navigation logic.
        """
        # Use the enhanced logical navigation logic
        # Implementation moved directly here for better performance and clarity
        
        logger = get_logger(__name__)
        logger.debug(f"[LOGICAL_NAV] nav_type={nav_type}, column={column}, steps={steps}, var_name={var_name}")
        
        # For logical navigation, we need to work with the pattern match timeline
        if not hasattr(self.context, 'variables') or not self.context.variables:
            logger.debug("[LOGICAL_NAV] No variables in context")
            return None
        
        # Build timeline of variable assignments
        timeline = []
        for var, indices in self.context.variables.items():
            for idx in indices:
                timeline.append((idx, var))
        
        # Sort by row index for consistent ordering
        timeline.sort()
        
        if not timeline:
            logger.debug("[LOGICAL_NAV] Empty timeline")
            return None
        
        # Find current position in timeline
        curr_idx = self.context.current_idx
        curr_pos = -1
        current_var = getattr(self.context, 'current_var', None)
        
        # Find position in timeline
        for i, (idx, var) in enumerate(timeline):
            if idx == curr_idx and (current_var is None or var == current_var or var_name is None):
                curr_pos = i
                break
        
        if curr_pos < 0:
            # Try alternative matching
            for i, (idx, var) in enumerate(timeline):
                if idx == curr_idx:
                    curr_pos = i
                    break
        
        if curr_pos < 0:
            logger.debug(f"[LOGICAL_NAV] Could not find current position for idx {curr_idx}")
            return None
        
        # Calculate target position
        if nav_type == 'PREV':
            target_pos = curr_pos - steps
        else:  # NEXT
            target_pos = curr_pos + steps
        
        # Bounds checking
        if target_pos < 0 or target_pos >= len(timeline):
            logger.debug(f"[LOGICAL_NAV] Target position {target_pos} out of bounds [0, {len(timeline)})")
            return None
        
        target_idx, _ = timeline[target_pos]
        
        # Check partition boundaries (if defined)
        if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
            current_partition = self.context.get_partition_for_row(curr_idx)
            target_partition = self.context.get_partition_for_row(target_idx)
            
            if (current_partition is None or target_partition is None or
                current_partition != target_partition):
                logger.debug(f"[LOGICAL_NAV] Cross-partition navigation not allowed")
                return None
        
        # Get value from target row
        if 0 <= target_idx < len(self.context.rows):
            result = self.context.rows[target_idx].get(column)
            logger.debug(f"[LOGICAL_NAV] Returning {result} from row {target_idx}")
            return result
        
        logger.debug(f"[LOGICAL_NAV] Target index {target_idx} out of range")
        return None

    def _handle_first_last_navigation(self, nav_type, column, steps, var_name=None):
        """
        Handle FIRST and LAST navigation functions with mode-aware behavior.
        
        DEFINE Mode (Physical Navigation):
        - FIRST(column) - gets the first value in the current partition
        - LAST(column) - gets the last value in the current partition
        
        MEASURES Mode (Logical Navigation):
        - FIRST(column) - gets the first value in the pattern match
        - LAST(column) - gets the last value in the pattern match
        
        Args:
            nav_type: 'FIRST' or 'LAST'
            column: Column name to retrieve
            steps: Number of steps (usually 1, but could be > 1)
            var_name: Optional variable name for qualified references
            
        Returns:
            The first/last value or None if not found
        """
        logger = get_logger(__name__)
        
        try:
            if self.evaluation_mode == 'DEFINE':
                # In DEFINE mode, handle qualified vs unqualified references differently
                rows = self.context.rows
                
                if not rows:
                    return None
                
                if var_name:
                    # Qualified reference like FIRST(A.value) or LAST(A.value)
                    # Find first/last occurrence of the specific variable in the partial match
                    variable_name = var_name.strip('"')  # Remove quotes if present
                    
                    if hasattr(self.context, 'variables') and variable_name in self.context.variables:
                        var_indices = self.context.variables[variable_name]
                        if var_indices:
                            if nav_type == 'FIRST':
                                # Get the first occurrence of this variable
                                target_idx = var_indices[0]
                            else:  # LAST
                                # Get the last occurrence of this variable that's <= current position
                                current_pos = getattr(self.context, 'current_idx', len(rows) - 1)
                                valid_indices = [idx for idx in var_indices if idx <= current_pos]
                                if valid_indices:
                                    target_idx = valid_indices[-1]
                                else:
                                    return None
                            
                            if target_idx < len(rows):
                                result = rows[target_idx].get(column)
                                return result
                    
                    return None
                
                else:
                    # Unqualified reference like FIRST(value) or LAST(value)
                    # Use boundary values in the current partition (original behavior)
                    if nav_type == 'FIRST':
                        target_row = rows[0]
                    else:  # LAST
                        target_row = rows[-1]
                    
                    result = target_row.get(column)
                    return result
            
            else:
                # MEASURES mode: Use logical navigation through pattern matches
                
                if var_name:
                    # Qualified reference like FIRST(A.value) or LAST(A.value)
                    # Must respect variable qualifiers even in MEASURES mode
                    variable_name = var_name.strip('"')  # Remove quotes if present
                    
                    if hasattr(self.context, 'variables') and variable_name in self.context.variables:
                        var_indices = self.context.variables[variable_name]
                        if var_indices:
                            if nav_type == 'FIRST':
                                # Get the first occurrence of this variable
                                target_idx = var_indices[0]
                            else:  # LAST
                                # Get the last occurrence of this variable
                                target_idx = var_indices[-1]
                            
                            if target_idx < len(self.context.rows):
                                result = self.context.rows[target_idx].get(column)
                                return result
                    
                    return None
                else:
                    # Unqualified reference like FIRST(value) or LAST(value)
                    if nav_type == 'FIRST':
                        # For MEASURES, get the first value from the pattern match
                        if self.context.rows:
                            result = self.context.rows[0].get(column)
                            return result
                    else:  # LAST
                        # For MEASURES, get the last value from the pattern match
                        if self.context.rows:
                            result = self.context.rows[-1].get(column)
                            return result
                
                return None
                
        except Exception as e:
            logger.debug(f"FIRST/LAST navigation failed: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

    def visit_Constant(self, node: ast.Constant):
        """Handle all constant types (numbers, strings, booleans, None)"""
        return node.value

    def visit_BoolOp(self, node: ast.BoolOp):
        """Handle boolean operations (AND, OR) with SQL NULL semantics"""
        if isinstance(node.op, ast.And):
            # For AND with SQL semantics:
            # - If any operand is None (NULL), result is None
            # - If any operand is False, result is False
            # - If all operands are True, result is True
            has_none = False
            for value in node.values:
                result = self.visit(value)
                if result is None:
                    has_none = True
                elif not result:  # False (but not None)
                    return False
            # If we found None but no False, return None
            if has_none:
                return None
            return True
        elif isinstance(node.op, ast.Or):
            # For OR with SQL semantics:
            # - If any operand is True, result is True
            # - If any operand is None and no True found, result is None
            # - If all operands are False, result is False
            has_none = False
            for value in node.values:
                result = self.visit(value)
                # DataFrame scalar comparisons commonly produce numpy.bool_
                # rather than the singleton ``True``.  Identity comparison
                # incorrectly treated those true values as false and broke
                # OR whenever only that branch matched.
                if result is not None and bool(result):
                    return True
                elif result is None:
                    has_none = True
            # If we found None but no True, return None
            if has_none:
                return None
            return False
        else:
            raise ValueError(f"Unsupported boolean operator: {type(node.op)}")

    def visit_IfExp(self, node: ast.IfExp):
        """
        Handle Python conditional expressions (ternary operator): x if condition else y
        
        This is crucial for handling CASE WHEN expressions converted to Python conditionals.
        For example: CASE WHEN CLASSIFIER() IN ('A', 'START') THEN 1 ELSE 0 END
        becomes: (1 if 'A' in ('A', 'START') else 0)
        
        Args:
            node: AST IfExp node representing a conditional expression
            
        Returns:
            The value of either the 'then' branch or 'else' branch based on condition
        """
        try:
            # Evaluate the condition (test)
            condition = self.visit(node.test)
            
            logger.debug(f"[DEBUG] IfExp condition: {condition} (type: {type(condition)})")
            
            # Handle None condition (SQL semantics)
            if condition is None:
                logger.debug("[DEBUG] IfExp condition is None, returning else value")
                return self.visit(node.orelse)
            
            # Python truth value evaluation
            if condition:
                result = self.visit(node.body)
                logger.debug(f"[DEBUG] IfExp condition is truthy, returning then value: {result}")
                return result
            else:
                result = self.visit(node.orelse)
                logger.debug(f"[DEBUG] IfExp condition is falsy, returning else value: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Error evaluating condition '{e}'")
            # For production readiness, we should return None on errors
            return None

    def visit_Tuple(self, node: ast.Tuple):
        """
        Handle tuple literals like ('A', 'START') in expressions.
        
        This is essential for IN predicates that use tuple literals.
        For example: 'A' in ('A', 'START') needs to parse the tuple correctly.
        
        Args:
            node: AST Tuple node
            
        Returns:
            A Python tuple with evaluated elements
        """
        try:
            # Evaluate each element in the tuple
            elements = []
            for elt in node.elts:
                value = self.visit(elt)
                elements.append(value)
            
            result = tuple(elements)
            logger.debug(f"[DEBUG] Tuple evaluation: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error evaluating tuple: {e}")
            return ()

    def visit_List(self, node: ast.List):
        """
        Handle list literals like ['A', 'START'] in expressions.
        
        This supports IN predicates that use list literals.
        For example: 'A' in ['A', 'START'] needs to parse the list correctly.
        
        Args:
            node: AST List node
            
        Returns:
            A Python list with evaluated elements
        """
        try:
            # Evaluate each element in the list
            elements = []
            for elt in node.elts:
                value = self.visit(elt)
                elements.append(value)
            
            result = elements
            logger.debug(f"[DEBUG] List evaluation: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error evaluating list: {e}")
            return []

    def _get_direct_classifier_at_index(self, row_idx: int, subset_var: Optional[str] = None) -> str:
        """
        Production-ready direct classifier lookup at specific row index.
        
        This method provides direct classifier lookup without creating temporary contexts
        or evaluators, preventing infinite recursion in subset navigation scenarios.
        
        Args:
            row_idx: Row index to get classifier for
            subset_var: Optional subset variable name for validation
            
        Returns:
            Classifier name for the specified row index
        """
        try:
            # Validate row index bounds
            if row_idx < 0 or row_idx >= len(self.context.rows):
                return None
            
            # Find which variable(s) match this row index
            matching_vars = []
            for var_name, indices in self.context.variables.items():
                if row_idx in indices:
                    matching_vars.append(var_name)
            
            if not matching_vars:
                return None
            
            # If subset variable specified, validate it's a component
            if subset_var and subset_var in self.context.subsets:
                subset_components = self.context.subsets[subset_var]
                matching_vars = [var for var in matching_vars if var in subset_components]
            
            # Return the first matching variable (or the most appropriate one)
            if matching_vars:
                # Apply case sensitivity rules for classifier
                result_var = matching_vars[0]  # Take first match
                
                # Apply case sensitivity rules
                if hasattr(self.context, 'defined_variables') and self.context.defined_variables:
                    if result_var.lower() in [v.lower() for v in self.context.defined_variables]:
                        # Preserve original case for defined variables
                        return result_var
                    else:
                        # Uppercase for undefined variables
                        return result_var.upper()
                else:
                    # Default to uppercase if no defined_variables info
                    return result_var.upper()
            
            return None
            
        except Exception as e:
            logger.error(f"Error in direct classifier lookup at index {row_idx}: {e}")
            return None


# External function imports that are referenced but defined elsewhere
def evaluate_nested_navigation(expr: str, context: RowContext, current_idx: int, current_var: Optional[str] = None, recursion_depth: int = 0) -> Any:
    """
    Placeholder for nested navigation evaluation.
    This function should be implemented in a separate module to handle complex nested navigation.
    """
    # This is a placeholder - the actual implementation should be in a separate module
    logger.warning(f"evaluate_nested_navigation called but not implemented: {expr}")
    return None


class _FastConditionUnsupported(Exception):
    """Internal signal that a residual expression needs the AST evaluator."""


def _bind_fast_condition_part(part, context):
    """Return a context-bound compiled expression part when one is safe."""
    binder = getattr(part, "bind_context", None)
    return binder(context) if binder is not None else part


_UNBOUND_FAST_VALUE = object()


def _mark_fast_condition_part(
    part,
    *,
    row_dependent,
    state_scopes=(),
    vector_column=_UNBOUND_FAST_VALUE,
):
    """Publish conservative dependency metadata on compiled expression IR.

    The metadata is an optional optimization contract, not a second semantic
    evaluator.  Missing metadata always means "potentially row dependent" and
    therefore disables batch evaluation.  This lets newly supported or
    context-sensitive expressions continue through the scalar production
    evaluator without having to opt out explicitly.
    """
    part._fast_row_dependent = bool(row_dependent)
    part._fast_state_scopes = frozenset(
        str(scope).upper() for scope in state_scopes
    )
    if vector_column is not _UNBOUND_FAST_VALUE:
        part._fast_vector_column = vector_column
    return part


def _mark_composed_fast_condition_part(part, children):
    """Propagate only dependency facts proved for every child expression."""
    children = tuple(children)
    if any(
        not hasattr(child, "_fast_row_dependent") for child in children
    ):
        return part
    scopes = set()
    for child in children:
        scopes.update(getattr(child, "_fast_state_scopes", ()))
    return _mark_fast_condition_part(
        part,
        row_dependent=any(child._fast_row_dependent for child in children),
        state_scopes=scopes,
    )


class _RollbackAggregateState:
    """Prefix aggregate state maintained by exact-search append/rollback."""

    def __init__(self, func_name, column_values, rows, field_name, indices):
        self.func_name = func_name
        self.column_values = column_values
        self.rows = rows
        self.field_name = field_name
        self.snapshots = []
        self.valid = True
        for row_index in indices:
            self.append_index(row_index)
            if not self.valid:
                break

    def _read(self, row_index):
        if self.column_values is not None:
            return self.column_values[row_index]
        return self.rows[row_index].get(self.field_name)

    def _advance(self, previous, row_index):
        value = self._read(row_index)
        present = value is not None and value == value
        if self.func_name == "COUNT":
            return previous + (1 if present else 0)
        if self.func_name in {"MIN", "MAX", "ARBITRARY"}:
            has_value, current = previous
            if not present or (self.func_name == "ARBITRARY" and has_value):
                return previous
            if not has_value:
                return True, value
            if self.func_name == "MIN":
                return True, min(current, value)
            if self.func_name == "MAX":
                return True, max(current, value)
            return previous
        total, count = previous
        if present:
            total = total + value
            count += 1
        return total, count

    def append_index(self, row_index):
        if not self.valid:
            return
        previous = (
            self.snapshots[-1]
            if self.snapshots
            else (
                0
                if self.func_name == "COUNT"
                else (
                    (False, None)
                    if self.func_name in {"MIN", "MAX", "ARBITRARY"}
                    else (0, 0)
                )
            )
        )
        try:
            self.snapshots.append(self._advance(previous, row_index))
        except Exception:
            # Non-numeric SUM/AVG inputs retain the generic evaluator's error
            # behavior instead of failing during matcher-state mutation.
            self.valid = False

    def truncate(self, length):
        if len(self.snapshots) > length:
            del self.snapshots[length:]

    def value(self, include_index=None):
        if not self.valid:
            return _UNBOUND_FAST_VALUE
        current = (
            self.snapshots[-1]
            if self.snapshots
            else (
                0
                if self.func_name == "COUNT"
                else (
                    (False, None)
                    if self.func_name in {"MIN", "MAX", "ARBITRARY"}
                    else (0, 0)
                )
            )
        )
        if include_index is not None:
            try:
                current = self._advance(current, include_index)
            except Exception:
                return _UNBOUND_FAST_VALUE
        if self.func_name == "COUNT":
            return current
        if self.func_name in {"MIN", "MAX", "ARBITRARY"}:
            has_value, value = current
            return value if has_value else None
        total, count = current
        if count == 0:
            return None
        return total if self.func_name == "SUM" else total / count


def _evaluate_prepared_simple_aggregate(
    evaluator,
    node,
    func_name,
    scope_upper,
    field_name,
    context,
    exact_scope=_UNBOUND_FAST_VALUE,
    column_values=_UNBOUND_FAST_VALUE,
):
    """Compact exact-search evaluator for ``AGG(variable.field)``.

    The exact matcher publishes a scope map only for pattern variables whose
    case-folded names are unique.  Its absence, a SUBSET, or a long unchanged
    scope delegates to the complete evaluator.  This keeps one semantic
    implementation for every ambiguous case while removing repeated AST and
    scope discovery from the common short-scope path.
    """
    if exact_scope is _UNBOUND_FAST_VALUE:
        scope_map = getattr(context, "_define_direct_scope_map", None)
        exact_scope = (
            scope_map.get(scope_upper) if scope_map is not None else None
        )
    if exact_scope is None or context.subsets:
        return evaluator._handle_define_aggregate(node, func_name)

    # Exact-search binding always supplies a RowContext whose assignment
    # dictionary is cleared and reused between candidates.  Read its stable
    # containers directly: repeated defensive getattr/case-fold dispatch is
    # measurable when a short aggregate is evaluated millions of times, but
    # adds no semantic protection after direct-scope resolution has succeeded.
    variables = context.variables
    assigned = variables.get(exact_scope, ())
    assigned_count = len(assigned)
    rows = context.rows
    row_count = len(rows)
    current_idx = context.current_idx
    current_var = context.current_var
    include_current = bool(
        current_var == exact_scope
        and 0 <= current_idx < row_count
        and (not assigned or assigned[-1] != current_idx)
    )

    # The linear exact executor assigns each case-unique token as one
    # contiguous scope.  For long SUM/AVG/COUNT scopes it publishes mutable
    # prefix states that are extended on assignment and truncated on rollback.
    # Stored prefixes preserve the original left-to-right arithmetic exactly;
    # no inverse floating-point operation is used.
    incremental_states = context._define_incremental_aggregate_states
    incremental_threshold = context._define_incremental_aggregate_threshold
    if (
        incremental_states is not None
        and func_name in {
            "SUM", "AVG", "COUNT", "MIN", "MAX", "ARBITRARY"
        }
        and assigned_count >= incremental_threshold
    ):
        scope_states = incremental_states.setdefault(
            str(exact_scope).upper(), {}
        )
        state_key = (field_name, func_name)
        state = scope_states.get(state_key)
        if state is None:
            bound_column = (
                None
                if column_values is _UNBOUND_FAST_VALUE
                else column_values
            )
            if bound_column is None:
                exact_column_at = getattr(rows, "column_array_exact", None)
                bound_column = (
                    exact_column_at(field_name)
                    if exact_column_at is not None else None
                )
            state = _RollbackAggregateState(
                func_name,
                bound_column,
                rows,
                field_name,
                assigned,
            )
            scope_states[state_key] = state
        if state.valid and len(state.snapshots) == assigned_count:
            state_value = state.value(current_idx if include_current else None)
            if state_value is not _UNBOUND_FAST_VALUE:
                return state_value

    # The generic path memoizes a long scope while a different variable is
    # being tested.  Preserve that asymptotic behavior; the compact path is
    # for the overwhelmingly common short scopes where memo-key construction
    # costs more than scanning the few values.
    if assigned_count >= 16 and not include_current:
        return evaluator._handle_define_aggregate(node, func_name)

    if column_values is _UNBOUND_FAST_VALUE:
        column_cache = context._input_column_cache
        if field_name in column_cache:
            column_values = column_cache[field_name]
        else:
            exact_column_at = getattr(rows, "column_array_exact", None)
            column_values = (
                exact_column_at(field_name)
                if exact_column_at is not None
                else None
            )
            column_cache[field_name] = column_values

    scope_size = assigned_count + (1 if include_current else 0)
    if scope_size <= 1:
        if assigned:
            scalar_index = assigned[0]
        elif include_current:
            scalar_index = current_idx
        else:
            scalar_index = None
        value = (
            None
            if scalar_index is None
            else (
                column_values[scalar_index]
                if column_values is not None
                else rows[scalar_index].get(field_name)
            )
        )
        present = value is not None and value == value
        if func_name == "COUNT":
            return 1 if present else 0
        if not present:
            return None
        if func_name == "ARRAY_AGG":
            return [value]
        # SUM, AVG, MIN, MAX and ARBITRARY are all the single non-NULL
        # value for a one-row scope.
        return value

    if func_name in ("SUM", "AVG"):
        count = 0
        total = 0
        for row_index in assigned:
            value = (
                column_values[row_index]
                if column_values is not None
                else rows[row_index].get(field_name)
            )
            if value is not None and value == value:
                total += value
                count += 1
        if include_current:
            value = (
                column_values[current_idx]
                if column_values is not None
                else rows[current_idx].get(field_name)
            )
            if value is not None and value == value:
                total += value
                count += 1
        if count == 0:
            return None
        return total if func_name == "SUM" else total / count

    if func_name == "COUNT":
        count = 0
        for row_index in assigned:
            value = (
                column_values[row_index]
                if column_values is not None
                else rows[row_index].get(field_name)
            )
            if value is not None and value == value:
                count += 1
        if include_current:
            value = (
                column_values[current_idx]
                if column_values is not None
                else rows[current_idx].get(field_name)
            )
            if value is not None and value == value:
                count += 1
        return count

    values = []
    for row_index in assigned:
        value = (
            column_values[row_index]
            if column_values is not None
            else rows[row_index].get(field_name)
        )
        if value is not None and value == value:
            values.append(value)
    if include_current:
        value = (
            column_values[current_idx]
            if column_values is not None
            else rows[current_idx].get(field_name)
        )
        if value is not None and value == value:
            values.append(value)
    if not values:
        return None
    if func_name == "MIN":
        return min(values)
    if func_name == "MAX":
        return max(values)
    if func_name == "ARRAY_AGG":
        return values
    return values[0]


def _compile_fast_condition_expression(node):
    """Compile a safe DEFINE-expression subset into direct callables.

    The returned functions still use the production aggregate and comparison
    primitives; this removes only repeated ``ast.NodeVisitor`` dispatch.  Any
    node whose semantics are context-sensitive beyond this subset rejects the
    whole plan and falls back to the standard evaluator.
    """
    if isinstance(node, ast.Constant):
        value = node.value
        return _mark_fast_condition_part(
            lambda evaluator, row, context: value,
            row_dependent=False,
        )

    if isinstance(node, ast.Name):
        name = node.id
        if name.upper() in {
            "PREV", "NEXT", "FIRST", "LAST", "CLASSIFIER",
            "MATCH_NUMBER", "GET_VAR_VALUE",
        } or name == "row":
            raise _FastConditionUnsupported

        def read_current_field(evaluator, row, context):
            if name in getattr(context, "pattern_variables", ()):
                return None
            if row is not None:
                return row.get(name)
            index = getattr(context, "current_idx", -1)
            rows = getattr(context, "rows", ())
            if 0 <= index < len(rows):
                column_cache = context._input_column_cache
                if name in column_cache:
                    column_values = column_cache[name]
                else:
                    exact_column_at = getattr(rows, "column_array_exact", None)
                    column_values = (
                        exact_column_at(name)
                        if exact_column_at is not None
                        else None
                    )
                    column_cache[name] = column_values
                if column_values is not None:
                    return column_values[index]
                return rows[index].get(name)
            return None

        def bind_current_field(context):
            if name in getattr(context, "pattern_variables", ()):
                return lambda evaluator, row, context: None
            rows = getattr(context, "rows", ())
            exact_column_at = getattr(rows, "column_array_exact", None)
            column_values = (
                exact_column_at(name) if exact_column_at is not None else None
            )
            if column_values is None:
                return read_current_field

            def read_bound_field(evaluator, row, context):
                if row is not None:
                    return row.get(name)
                index = context.current_idx
                if 0 <= index < len(column_values):
                    return column_values[index]
                return None

            return _mark_fast_condition_part(
                read_bound_field,
                row_dependent=True,
                vector_column=column_values,
            )

        read_current_field.bind_context = bind_current_field

        return read_current_field

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        func_name = node.func.id.upper()
        if func_name in {
            "SUM", "AVG", "MIN", "MAX", "COUNT", "ARBITRARY",
            "ARRAY_AGG", "MAX_BY", "MIN_BY",
        }:
            if (
                func_name not in {"MAX_BY", "MIN_BY"}
                and len(node.args) == 1
                and not node.keywords
                and isinstance(node.args[0], ast.Attribute)
                and isinstance(node.args[0].value, ast.Name)
            ):
                scope_upper = node.args[0].value.id.upper()
                field_name = node.args[0].attr
                def evaluate_prepared_aggregate(evaluator, row, context):
                    return (
                    _evaluate_prepared_simple_aggregate(
                        evaluator,
                        node,
                        func_name,
                        scope_upper,
                        field_name,
                        context,
                    )
                    )

                def bind_prepared_aggregate(context):
                    scope_map = getattr(
                        context, "_define_direct_scope_map", None
                    )
                    exact_scope = (
                        scope_map.get(scope_upper)
                        if scope_map is not None else None
                    )
                    if exact_scope is None:
                        return evaluate_prepared_aggregate
                    rows = context.rows
                    exact_column_at = getattr(
                        rows, "column_array_exact", None
                    )
                    column_values = (
                        exact_column_at(field_name)
                        if exact_column_at is not None else None
                    )

                    def evaluate_bound_aggregate(evaluator, row, context):
                        return _evaluate_prepared_simple_aggregate(
                            evaluator,
                            node,
                            func_name,
                            scope_upper,
                            field_name,
                            context,
                            exact_scope,
                            column_values,
                        )

                    # The value is stable while another pattern variable is
                    # being extended.  A caller must still reject batching
                    # when ``current_var`` is this scope, because DEFINE then
                    # includes the prospective current row.
                    return _mark_fast_condition_part(
                        evaluate_bound_aggregate,
                        row_dependent=False,
                        state_scopes=(scope_upper,),
                    )

                evaluate_prepared_aggregate.bind_context = (
                    bind_prepared_aggregate
                )
                return evaluate_prepared_aggregate
            return lambda evaluator, row, context: (
                evaluator._handle_define_aggregate(node, func_name)
            )
        if func_name == "_IS_NULL" and len(node.args) == 1 and not node.keywords:
            argument = _compile_fast_condition_expression(node.args[0])
            evaluate_is_null = lambda evaluator, row, context: is_null(
                argument(evaluator, row, context)
            )

            def bind_is_null(context):
                bound_argument = _bind_fast_condition_part(argument, context)
                evaluate_bound_is_null = lambda evaluator, row, context: is_null(
                    bound_argument(evaluator, row, context)
                )
                return _mark_composed_fast_condition_part(
                    evaluate_bound_is_null, (bound_argument,)
                )

            evaluate_is_null.bind_context = bind_is_null
            return evaluate_is_null
        if func_name in MATH_FUNCTIONS and not node.keywords:
            arguments = tuple(
                _compile_fast_condition_expression(arg) for arg in node.args
            )

            def evaluate_math(evaluator, row, context):
                values = [part(evaluator, row, context) for part in arguments]
                evaluator.stats["math_function_calls"] += 1
                return evaluate_math_function(func_name, *values)

            def bind_math(context):
                bound_arguments = tuple(
                    _bind_fast_condition_part(part, context)
                    for part in arguments
                )

                def evaluate_bound_math(evaluator, row, context):
                    values = [
                        part(evaluator, row, context)
                        for part in bound_arguments
                    ]
                    evaluator.stats["math_function_calls"] += 1
                    return evaluate_math_function(func_name, *values)

                return _mark_composed_fast_condition_part(
                    evaluate_bound_math, bound_arguments
                )

            evaluate_math.bind_context = bind_math

            return evaluate_math
        raise _FastConditionUnsupported

    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise _FastConditionUnsupported
        op_node = node.ops[0]
        if isinstance(op_node, (ast.In, ast.NotIn)):
            raise _FastConditionUnsupported
        comparison = {
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
            ast.Is: operator.is_,
            ast.IsNot: operator.is_not,
        }.get(type(op_node))
        if comparison is None:
            raise _FastConditionUnsupported
        left = _compile_fast_condition_expression(node.left)
        right = _compile_fast_condition_expression(node.comparators[0])
        def evaluate_compare(evaluator, row, context):
            return safe_compare(
                left(evaluator, row, context),
                right(evaluator, row, context),
                comparison,
            )

        def bind_compare(context):
            bound_left = _bind_fast_condition_part(left, context)
            bound_right = _bind_fast_condition_part(right, context)

            def evaluate_bound_compare(evaluator, row, context):
                return safe_compare(
                bound_left(evaluator, row, context),
                bound_right(evaluator, row, context),
                comparison,
            )

            # A quantified token can consume a contiguous run in one NumPy
            # operation when (and only when) one operand is an exact numeric
            # input column and the other is proved independent of the current
            # input row.  The scalar operand may depend on already assigned
            # pattern scopes, but not on the variable currently being grown.
            # SQL NULL behavior is reproduced explicitly below.  Returning
            # None means "unsupported" and tells the matcher to use the
            # ordinary scalar predicate without changing semantics.
            left_column = getattr(bound_left, "_fast_vector_column", None)
            right_column = getattr(bound_right, "_fast_vector_column", None)
            if (
                not isinstance(op_node, (ast.Is, ast.IsNot))
                and (left_column is None) != (right_column is None)
            ):
                scalar_part = bound_right if left_column is not None else bound_left
                vector_column = (
                    left_column if left_column is not None else right_column
                )
                scalar_is_proved_stable = (
                    hasattr(scalar_part, "_fast_row_dependent")
                    and not scalar_part._fast_row_dependent
                )
                scalar_scopes = frozenset(
                    getattr(scalar_part, "_fast_state_scopes", ())
                )

                if scalar_is_proved_stable:
                    # The bound exact-search evaluator normally receives no
                    # row dictionary: its current row is the numeric column at
                    # ``context.current_idx``.  Fuse that proved representation
                    # with the stable scalar expression so the hottest scalar
                    # comparison avoids two closure calls plus the fully
                    # defensive ``safe_compare`` dispatcher.  NULL/NaN and
                    # exceptional comparisons retain exactly the shared SQL
                    # semantics by falling back to ``safe_compare``.
                    try:
                        import numpy as np

                        numeric_values = np.asarray(vector_column)
                        numeric_vector = (
                            numeric_values.ndim == 1
                            and numeric_values.dtype.kind in "biuf"
                        )
                    except (ImportError, TypeError, ValueError):
                        numeric_values = None
                        numeric_vector = False

                    if numeric_vector:
                        generic_bound_compare = evaluate_bound_compare

                        def evaluate_bound_numeric_compare(
                            evaluator, row, context
                        ):
                            if row is not None:
                                return generic_bound_compare(
                                    evaluator, row, context
                                )
                            index = context.current_idx
                            if index < 0 or index >= len(numeric_values):
                                return None
                            scalar_value = scalar_part(
                                evaluator, None, context
                            )
                            if scalar_value is None:
                                return None
                            vector_value = numeric_values[index]
                            try:
                                if (
                                    bool(vector_value != vector_value)
                                    or bool(scalar_value != scalar_value)
                                ):
                                    return None
                                return (
                                    comparison(vector_value, scalar_value)
                                    if left_column is not None
                                    else comparison(scalar_value, vector_value)
                                )
                            except Exception:
                                return (
                                    safe_compare(
                                        vector_value,
                                        scalar_value,
                                        comparison,
                                    )
                                    if left_column is not None
                                    else safe_compare(
                                        scalar_value,
                                        vector_value,
                                        comparison,
                                    )
                                )

                        evaluate_bound_compare = (
                            evaluate_bound_numeric_compare
                        )

                        def prepare_linear_token(evaluator, current_var):
                            """Bind the state-only operand once for one token.

                            The exact linear matcher mutates only the current
                            pattern variable while it consumes a token.  If
                            the scalar side of this comparison is proved to
                            depend exclusively on other scopes, its value is
                            invariant for that token attempt.  Returning a
                            row-index predicate avoids re-running aggregates
                            such as ``AVG(A.price)`` for every row of ``B+``.

                            This is deliberately an optional compiler
                            contract.  SUBSET scopes, self-dependent
                            expressions, non-numeric columns, and evaluation
                            failures return None and retain the complete
                            scalar evaluator.
                            """
                            if context.subsets:
                                return None
                            current_upper = str(current_var or "").upper()
                            if current_upper in scalar_scopes:
                                return None
                            try:
                                scalar_value = scalar_part(
                                    evaluator, None, context
                                )
                            except Exception:
                                return None

                            if is_null(scalar_value):
                                # SQL UNKNOWN is false in DEFINE.  A closure
                                # keeps the same contract as the ordinary
                                # compiled expression while avoiding repeated
                                # aggregate evaluation for the remaining run.
                                return lambda _index: None

                            def evaluate_token_index(index):
                                if index < 0 or index >= len(numeric_values):
                                    return None
                                vector_value = numeric_values[index]
                                try:
                                    if bool(vector_value != vector_value):
                                        return None
                                    return (
                                        comparison(
                                            vector_value, scalar_value
                                        )
                                        if left_column is not None
                                        else comparison(
                                            scalar_value, vector_value
                                        )
                                    )
                                except Exception:
                                    return (
                                        safe_compare(
                                            vector_value,
                                            scalar_value,
                                            comparison,
                                        )
                                        if left_column is not None
                                        else safe_compare(
                                            scalar_value,
                                            vector_value,
                                            comparison,
                                        )
                                    )

                            return evaluate_token_index

                        evaluate_bound_compare.prepare_linear_token = (
                            prepare_linear_token
                        )

                    suffix_extrema = {}

                    def prepared_vector_operands(evaluator, start, stop):
                        """Return a safe numeric window and stable scalar."""
                        current_var = str(
                            getattr(context, "current_var", "") or ""
                        ).upper()
                        if current_var in scalar_scopes:
                            return None
                        try:
                            import numpy as np

                            values = np.asarray(vector_column)
                            if values.ndim != 1 or values.dtype.kind not in "biuf":
                                return None
                            start_index = max(0, int(start))
                            stop_index = min(len(values), int(stop))
                            scalar_value = scalar_part(evaluator, None, context)
                            if is_null(scalar_value):
                                return values, start_index, stop_index, None
                            return (
                                values,
                                start_index,
                                stop_index,
                                scalar_value,
                            )
                        except Exception:
                            return None

                    def true_run_length(evaluator, start, stop):
                        prepared = prepared_vector_operands(
                            evaluator, start, stop
                        )
                        if prepared is None:
                            return None
                        try:
                            import numpy as np

                            (
                                values,
                                start_index,
                                stop_index,
                                scalar_value,
                            ) = prepared
                            if stop_index <= start_index:
                                return 0
                            if scalar_value is None:
                                return 0
                            window = values[start_index:stop_index]
                            compared = (
                                comparison(window, scalar_value)
                                if left_column is not None
                                else comparison(scalar_value, window)
                            )
                            accepted = np.asarray(compared, dtype=bool)
                            if accepted.shape != window.shape:
                                return None
                            if values.dtype.kind == "f":
                                accepted = accepted & ~np.isnan(window)
                            rejected = np.flatnonzero(~accepted)
                            return (
                                len(window)
                                if len(rejected) == 0
                                else int(rejected[0])
                            )
                        except Exception:
                            return None

                    true_run_length.minimum_size = 32
                    evaluate_bound_compare.true_run_length = true_run_length

                    def entire_range_is_true(evaluator, start, stop):
                        """Prove a complete numeric suffix without row scans.

                        The terminal-anchor executor only asks about the whole
                        remaining suffix.  Ordered and equality comparisons can
                        answer that question from suffix minima/maxima and a
                        suffix non-NULL flag.  ``!=`` cannot be proved by
                        extrema alone and deliberately retains a vector scan.
                        """
                        prepared = prepared_vector_operands(
                            evaluator, start, stop
                        )
                        if prepared is None:
                            return None
                        try:
                            import numpy as np

                            (
                                values,
                                start_index,
                                stop_index,
                                scalar_value,
                            ) = prepared
                            if stop_index <= start_index:
                                return True
                            if scalar_value is None:
                                return False
                            window = values[start_index:stop_index]

                            if (
                                stop_index == len(values)
                                and not isinstance(op_node, ast.NotEq)
                            ):
                                if not suffix_extrema:
                                    valid = (
                                        ~np.isnan(values)
                                        if values.dtype.kind == "f"
                                        else np.ones(len(values), dtype=bool)
                                    )
                                    suffix_extrema["all_valid"] = (
                                        np.logical_and.accumulate(
                                            valid[::-1]
                                        )[::-1].copy()
                                    )
                                    needs_minimum = (
                                        isinstance(op_node, ast.Eq)
                                        or (
                                            left_column is not None
                                            and isinstance(
                                                op_node, (ast.Gt, ast.GtE)
                                            )
                                        )
                                        or (
                                            left_column is None
                                            and isinstance(
                                                op_node, (ast.Lt, ast.LtE)
                                            )
                                        )
                                    )
                                    needs_maximum = (
                                        isinstance(op_node, ast.Eq)
                                        or (
                                            left_column is not None
                                            and isinstance(
                                                op_node, (ast.Lt, ast.LtE)
                                            )
                                        )
                                        or (
                                            left_column is None
                                            and isinstance(
                                                op_node, (ast.Gt, ast.GtE)
                                            )
                                        )
                                    )
                                    if needs_minimum:
                                        minimum_values = np.where(
                                            valid, values, np.inf
                                        )
                                        suffix_extrema["minimum"] = (
                                            np.minimum.accumulate(
                                                minimum_values[::-1]
                                            )[::-1].copy()
                                        )
                                    if needs_maximum:
                                        maximum_values = np.where(
                                            valid, values, -np.inf
                                        )
                                        suffix_extrema["maximum"] = (
                                            np.maximum.accumulate(
                                                maximum_values[::-1]
                                            )[::-1].copy()
                                        )
                                if not bool(
                                    suffix_extrema["all_valid"][start_index]
                                ):
                                    return False
                                if isinstance(op_node, ast.Eq):
                                    minimum = suffix_extrema[
                                        "minimum"
                                    ][start_index]
                                    maximum = suffix_extrema[
                                        "maximum"
                                    ][start_index]
                                    return bool(
                                        minimum == scalar_value
                                        and maximum == scalar_value
                                    )
                                if left_column is not None:
                                    if isinstance(op_node, ast.Gt):
                                        return bool(
                                            suffix_extrema["minimum"][start_index]
                                            > scalar_value
                                        )
                                    if isinstance(op_node, ast.GtE):
                                        return bool(
                                            suffix_extrema["minimum"][start_index]
                                            >= scalar_value
                                        )
                                    if isinstance(op_node, ast.Lt):
                                        return bool(
                                            suffix_extrema["maximum"][start_index]
                                            < scalar_value
                                        )
                                    if isinstance(op_node, ast.LtE):
                                        return bool(
                                            suffix_extrema["maximum"][start_index]
                                            <= scalar_value
                                        )
                                else:
                                    if isinstance(op_node, ast.Gt):
                                        return bool(
                                            suffix_extrema["maximum"][start_index]
                                            < scalar_value
                                        )
                                    if isinstance(op_node, ast.GtE):
                                        return bool(
                                            suffix_extrema["maximum"][start_index]
                                            <= scalar_value
                                        )
                                    if isinstance(op_node, ast.Lt):
                                        return bool(
                                            suffix_extrema["minimum"][start_index]
                                            > scalar_value
                                        )
                                    if isinstance(op_node, ast.LtE):
                                        return bool(
                                            suffix_extrema["minimum"][start_index]
                                            >= scalar_value
                                        )

                            compared = (
                                comparison(window, scalar_value)
                                if left_column is not None
                                else comparison(scalar_value, window)
                            )
                            accepted = np.asarray(compared, dtype=bool)
                            if accepted.shape != window.shape:
                                return None
                            if values.dtype.kind == "f":
                                accepted = accepted & ~np.isnan(window)
                            return bool(np.all(accepted))
                        except Exception:
                            return None

                    entire_range_is_true.minimum_size = 32
                    evaluate_bound_compare.entire_range_is_true = (
                        entire_range_is_true
                    )

            return _mark_composed_fast_condition_part(
                evaluate_bound_compare, (bound_left, bound_right)
            )

        evaluate_compare.bind_context = bind_compare
        return evaluate_compare

    if isinstance(node, ast.BoolOp):
        parts = tuple(
            _compile_fast_condition_expression(value) for value in node.values
        )
        if isinstance(node.op, ast.And):
            def evaluate_and(evaluator, row, context):
                has_null = False
                for part in parts:
                    result = part(evaluator, row, context)
                    if result is None:
                        has_null = True
                    elif not bool(result):
                        return False
                return None if has_null else True

            def bind_and(context):
                bound_parts = tuple(
                    _bind_fast_condition_part(part, context)
                    for part in parts
                )

                def evaluate_bound_and(evaluator, row, context):
                    has_null = False
                    for part in bound_parts:
                        result = part(evaluator, row, context)
                        if result is None:
                            has_null = True
                        elif not bool(result):
                            return False
                    return None if has_null else True

                return _mark_composed_fast_condition_part(
                    evaluate_bound_and, bound_parts
                )

            evaluate_and.bind_context = bind_and

            return evaluate_and
        if isinstance(node.op, ast.Or):
            def evaluate_or(evaluator, row, context):
                has_null = False
                for part in parts:
                    result = part(evaluator, row, context)
                    if result is None:
                        has_null = True
                    elif bool(result):
                        return True
                return None if has_null else False

            def bind_or(context):
                bound_parts = tuple(
                    _bind_fast_condition_part(part, context)
                    for part in parts
                )

                def evaluate_bound_or(evaluator, row, context):
                    has_null = False
                    for part in bound_parts:
                        result = part(evaluator, row, context)
                        if result is None:
                            has_null = True
                        elif bool(result):
                            return True
                    return None if has_null else False

                return _mark_composed_fast_condition_part(
                    evaluate_bound_or, bound_parts
                )

            evaluate_or.bind_context = bind_or

            return evaluate_or
        raise _FastConditionUnsupported

    if isinstance(node, ast.BinOp):
        operation = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.LShift: operator.lshift,
            ast.RShift: operator.rshift,
            ast.BitOr: operator.or_,
            ast.BitXor: operator.xor,
            ast.BitAnd: operator.and_,
        }.get(type(node.op))
        if operation is None:
            raise _FastConditionUnsupported
        left = _compile_fast_condition_expression(node.left)
        right = _compile_fast_condition_expression(node.right)

        def evaluate_binary(evaluator, row, context):
            try:
                left_value = left(evaluator, row, context)
                right_value = right(evaluator, row, context)
                if left_value is None or right_value is None:
                    return None
                return operation(left_value, right_value)
            except Exception:
                return None

        def bind_binary(context):
            bound_left = _bind_fast_condition_part(left, context)
            bound_right = _bind_fast_condition_part(right, context)

            def evaluate_bound_binary(evaluator, row, context):
                try:
                    left_value = bound_left(evaluator, row, context)
                    right_value = bound_right(evaluator, row, context)
                    if left_value is None or right_value is None:
                        return None
                    return operation(left_value, right_value)
                except Exception:
                    return None

            return _mark_composed_fast_condition_part(
                evaluate_bound_binary, (bound_left, bound_right)
            )

        evaluate_binary.bind_context = bind_binary

        return evaluate_binary

    if isinstance(node, ast.UnaryOp):
        operation = {
            ast.Not: operator.not_,
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
            ast.Invert: operator.invert,
        }.get(type(node.op))
        if operation is None:
            raise _FastConditionUnsupported
        operand = _compile_fast_condition_expression(node.operand)

        def evaluate_unary(evaluator, row, context):
            try:
                value = operand(evaluator, row, context)
                return None if value is None else operation(value)
            except Exception:
                return None

        def bind_unary(context):
            bound_operand = _bind_fast_condition_part(operand, context)

            def evaluate_bound_unary(evaluator, row, context):
                try:
                    value = bound_operand(evaluator, row, context)
                    return None if value is None else operation(value)
                except Exception:
                    return None

            return _mark_composed_fast_condition_part(
                evaluate_bound_unary, (bound_operand,)
            )

        evaluate_unary.bind_context = bind_unary

        return evaluate_unary

    raise _FastConditionUnsupported


def _compile_condition_node(
    condition_node,
    *,
    source_condition: str,
    python_condition: str,
    evaluation_mode: str,
    compiled_expression=None,
):
    """Compile an already parsed condition AST node.

    The matcher planner uses this entry point after it has proved some
    top-level AND conjuncts with a vectorized row-local guard.  Evaluating the
    remaining node is exactly equivalent on rows where that guard is true,
    and avoids converting/parsing the residual expression again.  Keeping the
    evaluator construction here also ensures planned and unplanned predicates
    share one implementation and identical SQL semantics.
    """
    is_boolean_expression = _is_boolean_expression(condition_node)
    thread_state = threading.local()

    def evaluate_condition(row, ctx):
        # Reuse one evaluator per compiled condition and thread.  If the same
        # condition is re-entered recursively, use a temporary evaluator so
        # the active evaluation state is not corrupted.
        in_use = getattr(thread_state, "in_use", False)
        if in_use:
            evaluator = ConditionEvaluator(ctx, evaluation_mode)
        else:
            evaluator = getattr(thread_state, "evaluator", None)
            if evaluator is None:
                evaluator = ConditionEvaluator(ctx, evaluation_mode)
                thread_state.evaluator = evaluator
            else:
                evaluator.reset(ctx, evaluation_mode)

        thread_state.in_use = True
        try:
            evaluator.current_row = row
            if compiled_expression is None:
                result = evaluator.visit(condition_node)
            else:
                result = compiled_expression(evaluator, row, ctx)
            if is_boolean_expression:
                return bool(result)
            return result
        except Exception as exc:
            logger.error(
                f"Error evaluating condition '{source_condition}': {exc}"
            )
            return False
        finally:
            thread_state.in_use = False

    def bind_context(ctx):
        """Bind compiled expression evaluation to one matching context.

        Exact matching mutates one :class:`RowContext` while it explores a
        candidate and then resets that same object for the next candidate.
        Entering the public thread-local wrapper for every tentative row would
        repeatedly look up and reset an evaluator even though its context
        object has not changed.  A context-bound evaluator is safe here
        because RowContext mutation is already single-threaded and the
        compiled IR does not use the visitor's re-entrant navigation state.

        Conditions that could not be compiled never expose this binder and
        continue through ``evaluate_condition`` with the complete AST
        evaluator.  This keeps navigation, classifier, ambiguous scope, and
        all unsupported expressions on their existing semantic path.
        """
        if compiled_expression is None:
            return None
        evaluator = ConditionEvaluator(ctx, evaluation_mode)
        bound_expression = _bind_fast_condition_part(compiled_expression, ctx)

        def evaluate_bound(row=None):
            try:
                evaluator.current_row = row
                result = bound_expression(evaluator, row, ctx)
                if is_boolean_expression:
                    return bool(result)
                return result
            except Exception as exc:
                logger.error(
                    f"Error evaluating condition '{source_condition}': {exc}"
                )
                return False

        expression_true_run = getattr(
            bound_expression, "true_run_length", None
        )
        if expression_true_run is not None:
            def true_run_length(start, stop):
                return expression_true_run(evaluator, start, stop)

            true_run_length.minimum_size = getattr(
                expression_true_run, "minimum_size", 32
            )
            evaluate_bound.true_run_length = true_run_length
        expression_entire_range = getattr(
            bound_expression, "entire_range_is_true", None
        )
        if expression_entire_range is not None:
            def entire_range_is_true(start, stop):
                return expression_entire_range(evaluator, start, stop)

            entire_range_is_true.minimum_size = getattr(
                expression_entire_range, "minimum_size", 32
            )
            evaluate_bound.entire_range_is_true = entire_range_is_true

        expression_prepare_token = getattr(
            bound_expression, "prepare_linear_token", None
        )
        if expression_prepare_token is not None:
            def prepare_linear_token(current_var):
                return expression_prepare_token(evaluator, current_var)

            evaluate_bound.prepare_linear_token = prepare_linear_token

        return evaluate_bound

    evaluate_condition.original_condition = source_condition
    evaluate_condition.python_condition = python_condition
    evaluate_condition.is_boolean_expression = is_boolean_expression
    evaluate_condition.uses_compiled_expression = compiled_expression is not None
    # A compiled expression resolves current fields from ``context.current_idx``
    # when no row dictionary is supplied.  Exact-search callers can therefore
    # avoid materializing a whole DataFrame row for a scalar residual.  AST
    # fallbacks keep receiving the full row.
    evaluate_condition.accepts_context_row = compiled_expression is not None
    evaluate_condition.bind_context = (
        bind_context if compiled_expression is not None else None
    )
    # Aggregates read accumulated match state, so results for the same input
    # position can differ between tentative match assignments.
    evaluate_condition.uses_match_state = bool(
        re.search(
            r'\b(?:sum|avg|min|max|count|arbitrary|array_agg)\s*\(',
            source_condition,
            re.IGNORECASE,
        )
    )
    return evaluate_condition


def compile_condition_ast(condition_node, source_condition, evaluation_mode='DEFINE'):
    """Compile a trusted normalized AST node using the standard evaluator.

    This is deliberately a narrow internal planning API: callers must obtain
    the node from the normal SQL-to-Python parser, rather than constructing a
    separate expression language.
    """
    python_condition = ast.unparse(condition_node)
    try:
        compiled_expression = _compile_fast_condition_expression(condition_node)
    except _FastConditionUnsupported:
        compiled_expression = None
    return _compile_condition_node(
        condition_node,
        source_condition=source_condition,
        python_condition=python_condition,
        evaluation_mode=evaluation_mode,
        compiled_expression=compiled_expression,
    )


def compile_condition(condition_str, evaluation_mode='DEFINE'):
    """
    Compile a condition string into a callable function.
    
    Args:
        condition_str: SQL condition string
        evaluation_mode: 'DEFINE' for pattern definitions, 'MEASURES' for measures
        
    Returns:
        A callable function that takes a row and context and returns a boolean
    """
    if not condition_str or condition_str.strip().upper() == 'TRUE':
        # Optimization for true condition
        return lambda row, ctx: True
        
    if condition_str.strip().upper() == 'FALSE':
        # Optimization for false condition
        return lambda row, ctx: False
    
    try:
        # Convert SQL syntax to Python syntax
        python_condition = _sql_to_python_condition(condition_str)
        
        # Parse the condition
        tree = ast.parse(python_condition, mode='eval')
        try:
            compiled_expression = _compile_fast_condition_expression(
                tree.body
            )
        except _FastConditionUnsupported:
            compiled_expression = None
        return _compile_condition_node(
            tree.body,
            source_condition=condition_str,
            python_condition=python_condition,
            evaluation_mode=evaluation_mode,
            compiled_expression=compiled_expression,
        )
    except SyntaxError as e:
        # Log the error and return a function that always returns False
        logger.error(f"Syntax error in condition '{condition_str}': {e}")
        return lambda row, ctx: False
    except Exception as e:
        # Log the error and return a function that always returns False
        logger.error(f"Error compiling condition '{condition_str}': {e}")
        return lambda row, ctx: False


def validate_navigation_conditions(pattern_variables, define_clauses):
    """
    Validate that navigation function calls in conditions are valid for the pattern.
    
    For example, navigation calls that reference pattern variables that don't appear
    in the pattern or haven't been matched yet are invalid.
    
    Args:
        pattern_variables: List of pattern variables from the pattern definition
        define_clauses: Dict mapping variable names to their conditions
        
    Returns:
        True if all navigation conditions are valid, False otherwise
    """
    # Validate each condition for each variable
    for var, condition in define_clauses.items():
        if var not in pattern_variables:
            logger.warning(f"Variable {var} in DEFINE clause not found in pattern")
            continue
            
        # Validate navigation references to other variables
        for ref_var in pattern_variables:
            # Skip self-references (always valid)
            if ref_var == var:
                continue
                
            # Find PREV(var) references - must be exact variable references, not column references
            if f"PREV({ref_var})" in condition:
                # Ensure the referenced variable appears before this one in the pattern
                var_idx = pattern_variables.index(var)
                ref_idx = pattern_variables.index(ref_var)
                
                if ref_idx >= var_idx:
                    logger.error(f"Invalid PREV({ref_var}) reference in condition for {var}: "
                               f"{ref_var} does not appear before {var} in the pattern")
                    return False
            
            # Find NEXT(var) references - must be exact variable references, not column references  
            if f"NEXT({ref_var})" in condition:
                # Ensure the referenced variable appears after this one in the pattern
                var_idx = pattern_variables.index(var)
                ref_idx = pattern_variables.index(ref_var)
                
                if ref_idx <= var_idx:
                    logger.error(f"Invalid NEXT({ref_var}) reference in condition for {var}: "
                               f"{ref_var} does not appear after {var} in the pattern")
                    return False
        
        # SQL:2016 Standard Compliance: Check for NEXT() usage in DEFINE clauses
        # NEXT() function usage should be restricted, but allow self-references
        if "NEXT(" in condition:
            var_idx = pattern_variables.index(var)
            is_final_variable = var_idx == len(pattern_variables) - 1
            
            # Allow NEXT() in final variables or when referencing the same variable
            # Pattern: NEXT(current_var.column) or NEXT(column) should be allowed
            import re
            next_calls = re.findall(r'NEXT\(([^)]+)\)', condition)
            
            for next_arg in next_calls:
                # Extract variable name if qualified (e.g., "A.price" -> "A")
                if '.' in next_arg:
                    referenced_var = next_arg.split('.')[0]
                    # Allow self-references (A.price in condition for A)
                    if referenced_var == var:
                        continue
                    # For cross-variable references, check if target appears later
                    if referenced_var in pattern_variables:
                        ref_idx = pattern_variables.index(referenced_var)
                        if ref_idx <= var_idx:
                            logger.error(f"Invalid NEXT({next_arg}) reference in condition for {var}: "
                                       f"{referenced_var} does not appear after {var} in the pattern")
                            return False
                else:
                    # Unqualified NEXT(column) - allow for any variable in practical implementation
                    # This is a column reference, not a variable reference
                    continue
            
            # Additional SQL:2016 compliance can be added here if needed
            # For now, we allow NEXT() with proper variable ordering validation
        
        # Similar validation for FIRST() and LAST() functions
        for nav_func in ['FIRST', 'LAST']:
            if f"{nav_func}(" in condition:
                import re
                nav_calls = re.findall(f'{nav_func}\\(([^)]+)\\)', condition)
                
                for nav_arg in nav_calls:
                    # Extract variable name if qualified (e.g., "A.value" -> "A")
                    if '.' in nav_arg:
                        referenced_var = nav_arg.split('.')[0]
                        # For FIRST/LAST, the referenced variable should exist in pattern
                        if referenced_var in pattern_variables:
                            # FIRST/LAST can reference any variable in the pattern
                            # This is generally allowed as they refer to boundary values
                            continue
                        else:
                            logger.warning(f"{nav_func}({nav_arg}) references unknown variable {referenced_var}")
                    else:
                        # Unqualified FIRST/LAST(column) - allow for any variable
                        continue
    
    # If all checks pass
    return True


def evaluate_nested_navigation(expr: str, context: RowContext, current_idx: int, current_var: Optional[str] = None, recursion_depth: int = 0) -> Any:
    """
    Enhanced nested navigation evaluation with comprehensive pattern support.
    
    Key improvements:
    - Advanced recursion protection with depth tracking
    - Enhanced parser for complex navigation expressions
    - Better error handling and recovery mechanisms
    - Improved performance with smart caching
    - Support for more complex nested patterns
    - Thread-safe evaluation with proper context management
    
    This function handles complex navigation expressions that may contain nested function calls
    like NEXT(PREV(value)), FIRST(CLASSIFIER()), PREV(LAST(A.value), 3), and SQL-specific 
    constructs like PREV(RUNNING LAST(value)).
    
    Args:
        expr: The navigation expression string to evaluate
        context: The row context for evaluation
        current_idx: Current row index
        current_var: Current pattern variable (optional)
        recursion_depth: Current recursion depth for protection
        
    Returns:
        The evaluated result or None if evaluation fails
    """
    
    try:
        import re
        import ast
        
        # Enhanced recursion protection
        max_recursion_depth = 15
        if recursion_depth >= max_recursion_depth:
            logger.warning(f"[NESTED_NAV] Maximum recursion depth {max_recursion_depth} reached for: '{expr}'")
            return None
        
        # Enhanced expression validation and cleanup
        if not expr or not isinstance(expr, str):
            logger.warning(f"[NESTED_NAV] Invalid expression: {expr}")
            return None
        
        processed_expr = expr.strip()
        if not processed_expr:
            return None
        
        # Set up evaluation context with recursion protection
        original_evaluator = getattr(context, '_active_evaluator', None)
        
        logger.debug(f"[NESTED_NAV] Evaluating: '{processed_expr}' at depth {recursion_depth}")
        
        # Enhanced pattern matching for complex navigation structures
        
        # Pattern 1: Complex arithmetic with multiple navigation functions
        # Example: PREV(LAST(A.value), 3) + FIRST(A.value) + PREV(LAST(B.value), 2)
        complex_arithmetic_pattern = r'.*(?:PREV|NEXT|FIRST|LAST)\s*\(.*[\+\-\*\/].*(?:PREV|NEXT|FIRST|LAST)\s*\('
        if re.search(complex_arithmetic_pattern, processed_expr, re.IGNORECASE):
            logger.debug(f"[NESTED_NAV] Complex arithmetic navigation detected")
            return _evaluate_complex_arithmetic_navigation(processed_expr, context, current_idx, current_var, recursion_depth)
        
        # Pattern 2: Nested navigation functions like PREV(FIRST(A.value), 3)
        nested_nav_pattern = r'(PREV|NEXT)\s*\(\s*(FIRST|LAST)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*\)\s*(?:,\s*(\d+))?\s*\)'
        nested_nav_match = re.match(nested_nav_pattern, processed_expr, re.IGNORECASE)
        
        if nested_nav_match:
            return _evaluate_nested_navigation_pattern(nested_nav_match, context, current_idx, recursion_depth)
        
        # Pattern 3: CLASSIFIER navigation functions
        classifier_nav_pattern = r'(FIRST|LAST|PREV|NEXT)\s*\(\s*CLASSIFIER\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)?\s*\)\s*(?:,\s*(\d+))?\s*\)'
        classifier_nav_match = re.match(classifier_nav_pattern, processed_expr, re.IGNORECASE)
        
        if classifier_nav_match:
            return _evaluate_classifier_navigation(classifier_nav_match, context, current_idx, recursion_depth)
        
        # Pattern 4: Enhanced function call patterns with better variable references
        enhanced_func_pattern = r'(PREV|NEXT|FIRST|LAST)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*(?:,\s*(\d+))?\s*\)'
        enhanced_func_match = re.match(enhanced_func_pattern, processed_expr, re.IGNORECASE)
        
        if enhanced_func_match:
            return _evaluate_enhanced_function_call(enhanced_func_match, context, current_idx, recursion_depth)
        
        # Pattern 5: SQL-specific constructs (RUNNING, FINAL keywords)
        sql_construct_pattern = r'(PREV|NEXT)\s*\(\s*(RUNNING|FINAL)\s+(FIRST|LAST)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*\)\s*(?:,\s*(\d+))?\s*\)'
        sql_construct_match = re.match(sql_construct_pattern, processed_expr, re.IGNORECASE)
        
        if sql_construct_match:
            return _evaluate_sql_construct_navigation(sql_construct_match, context, current_idx, recursion_depth)
        
        # Fallback: Try AST evaluation with enhanced error handling
        try:
            return _evaluate_ast_navigation(processed_expr, context, current_idx, current_var, recursion_depth)
        except Exception as e:
            logger.debug(f"[NESTED_NAV] AST evaluation failed: {e}")
            return None
            
    except Exception as e:
        logger.error(f"[NESTED_NAV] Evaluation error for '{expr}': {e}")
        return None
    finally:
        # Restore original evaluator context
        if original_evaluator is not None:
            context._active_evaluator = original_evaluator


def _evaluate_complex_arithmetic_navigation(expr: str, context: RowContext, current_idx: int, current_var: Optional[str], recursion_depth: int) -> Any:
    """Evaluate complex arithmetic expressions with multiple navigation functions."""
    try:
        # Use AST parsing for complex arithmetic
        tree = ast.parse(expr, mode='eval')
        
        # Create or reuse evaluator with recursion protection
        if hasattr(context, '_active_evaluator') and context._active_evaluator is not None:
            evaluator = context._active_evaluator
            evaluator.current_row = context.rows[current_idx] if 0 <= current_idx < len(context.rows) else None
        else:
            # Default to MEASURES mode for complex arithmetic in result calculation
            evaluation_mode = 'MEASURES'
            evaluator = ConditionEvaluator(context, evaluation_mode, recursion_depth + 1)
            evaluator.current_row = context.rows[current_idx] if 0 <= current_idx < len(context.rows) else None
            context._active_evaluator = evaluator
        
        result = evaluator.visit(tree.body)
        logger.debug(f"[NESTED_NAV] Complex arithmetic result: {result}")
        return result
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Complex arithmetic evaluation failed: {e}")
        return None


def _evaluate_nested_navigation_pattern(match, context: RowContext, current_idx: int, recursion_depth: int) -> Any:
    """Evaluate nested navigation patterns like PREV(FIRST(A.value), 3)."""
    try:
        outer_func = match.group(1).upper()  # PREV or NEXT
        inner_func = match.group(2).upper()  # FIRST or LAST
        column_ref = match.group(3)          # A.value or just column
        steps = int(match.group(4)) if match.group(4) else 1
        
        logger.debug(f"[NESTED_NAV] Nested pattern: {outer_func}({inner_func}({column_ref}), {steps})")
        
        # Parse column reference
        if '.' in column_ref:
            var_name, col_name = column_ref.split('.', 1)
        else:
            var_name = None
            col_name = column_ref
        
        # Find the FIRST/LAST row index for the variable
        if var_name and hasattr(context, 'variables') and var_name in context.variables:
            var_indices = context.variables[var_name]
            logger.debug(f"[NESTED_NAV] Variable {var_name} indices: {var_indices}")
            
            if var_indices:
                if inner_func == 'FIRST':
                    target_base_idx = min(var_indices)
                else:  # LAST
                    target_base_idx = max(var_indices)
                
                logger.debug(f"[NESTED_NAV] {inner_func} index: {target_base_idx}")
                
                # Apply PREV/NEXT with steps
                if outer_func == 'PREV':
                    final_idx = target_base_idx - steps
                else:  # NEXT
                    final_idx = target_base_idx + steps
                
                logger.debug(f"[NESTED_NAV] Final index: {final_idx}")
                
                # Get value with bounds checking
                if 0 <= final_idx < len(context.rows):
                    result = context.rows[final_idx].get(col_name)
                    logger.debug(f"[NESTED_NAV] Result: {result}")
                    return result
                else:
                    logger.debug(f"[NESTED_NAV] Index {final_idx} out of bounds")
                    return None
            else:
                logger.debug(f"[NESTED_NAV] No indices for variable {var_name}")
                return None
        else:
            # Handle case where var_name is None (column-only reference)
            logger.debug(f"[NESTED_NAV] Column-only reference: {col_name}")
            
            # Find all indices in current match
            all_indices = []
            if hasattr(context, 'variables'):
                for var, indices in context.variables.items():
                    all_indices.extend(indices)
            
            if all_indices:
                all_indices = sorted(set(all_indices))
                
                if inner_func == 'FIRST':
                    target_base_idx = all_indices[0]
                else:  # LAST
                    target_base_idx = all_indices[-1]
                
                # Apply PREV/NEXT
                if outer_func == 'PREV':
                    final_idx = target_base_idx - steps
                else:  # NEXT
                    final_idx = target_base_idx + steps
                
                if 0 <= final_idx < len(context.rows):
                    result = context.rows[final_idx].get(col_name)
                    return result
            
            return None
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Nested pattern evaluation failed: {e}")
        return None


def _evaluate_classifier_navigation(match, context: RowContext, current_idx: int, recursion_depth: int) -> Any:
    """Evaluate CLASSIFIER navigation functions."""
    try:
        nav_func = match.group(1).upper()     # FIRST, LAST, PREV, NEXT
        classifier_var = match.group(2)       # Optional variable name
        steps = int(match.group(3)) if match.group(3) else 1
        
        logger.debug(f"[NESTED_NAV] Classifier navigation: {nav_func}(CLASSIFIER({classifier_var}), {steps})")
        
        if nav_func in ('FIRST', 'LAST'):
            # Handle FIRST/LAST CLASSIFIER
            return _handle_first_last_classifier_navigation(nav_func, classifier_var, steps, context)
        elif nav_func in ('PREV', 'NEXT'):
            # Handle PREV/NEXT CLASSIFIER
            return _handle_prev_next_classifier_navigation(nav_func, classifier_var, steps, context, current_idx)
        else:
            logger.warning(f"[NESTED_NAV] Unsupported classifier navigation: {nav_func}")
            return None
            
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Classifier navigation failed: {e}")
        return None


def _handle_first_last_classifier_navigation(nav_func: str, classifier_var: Optional[str], steps: int, context: RowContext) -> Any:
    """Handle FIRST/LAST CLASSIFIER navigation."""
    try:
        # Check if we're in FINAL semantics mode
        # For FINAL semantics, LAST should return the absolute last classifier, not relative to current position
        is_final_semantics = False
        
        # Try to detect FINAL semantics from evaluator or context
        if hasattr(context, '_active_evaluator'):
            evaluator = context._active_evaluator
            # Check if evaluator is in MEASURES mode, which typically indicates FINAL semantics for LAST
            if hasattr(evaluator, 'evaluation_mode') and evaluator.evaluation_mode == 'MEASURES':
                is_final_semantics = True
        
        # Alternative: Check if context has semantics information
        if hasattr(context, '_current_semantics'):
            is_final_semantics = context._current_semantics == 'FINAL'
            
        logger.debug(f"[CLASSIFIER_NAV] {nav_func}(CLASSIFIER({classifier_var}), {steps}) - FINAL semantics: {is_final_semantics}")
        
        if classifier_var and hasattr(context, 'subsets') and classifier_var in context.subsets:
            # Subset variable navigation
            component_vars = context.subsets[classifier_var]
            all_indices = []
            
            for comp_var in component_vars:
                if comp_var in context.variables:
                    all_indices.extend(context.variables[comp_var])
            
            if all_indices:
                all_indices = sorted(set(all_indices))
                
                if nav_func == 'FIRST':
                    if steps > len(all_indices):
                        return None
                    target_idx = all_indices[steps - 1] if steps > 0 else all_indices[0]
                else:  # LAST
                    if is_final_semantics:
                        # FINAL semantics: always return classifier from the absolute last row
                        target_idx = all_indices[-1] if all_indices else None
                        if target_idx is None:
                            return None
                    else:
                        # RUNNING semantics: relative to current position
                        if not hasattr(context, 'current_idx'):
                            return None
                        current_idx = context.current_idx
                        target_idx = current_idx - steps
                        if target_idx < 0 or target_idx not in all_indices:
                            return None
                
                logger.debug(f"[CLASSIFIER_NAV] Subset navigation target_idx: {target_idx}")
                return _get_classifier_at_index(target_idx, classifier_var, context)
        else:
            # General CLASSIFIER navigation
            all_indices = []
            if hasattr(context, 'variables'):
                for var, indices in context.variables.items():
                    all_indices.extend(indices)
            
            if all_indices:
                all_indices = sorted(set(all_indices))
                
                if nav_func == 'FIRST':
                    if steps > len(all_indices):
                        return None
                    target_idx = all_indices[steps - 1] if steps > 0 else all_indices[0]
                else:  # LAST
                    if is_final_semantics:
                        # FINAL semantics: always return classifier from the absolute last row in the match
                        target_idx = all_indices[-1] if all_indices else None
                        if target_idx is None:
                            return None
                        logger.debug(f"[CLASSIFIER_NAV] FINAL LAST: using absolute last index {target_idx}")
                    else:
                        # RUNNING semantics: relative to current position
                        if not hasattr(context, 'current_idx'):
                            return None
                        current_idx = context.current_idx
                        target_idx = current_idx - steps
                        if target_idx < 0:
                            return None
                        logger.debug(f"[CLASSIFIER_NAV] RUNNING LAST: using relative index {target_idx} (current={current_idx} - steps={steps})")
                
                logger.debug(f"[CLASSIFIER_NAV] General navigation target_idx: {target_idx}")
                return _get_classifier_at_index(target_idx, None, context)
        
        return None
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] FIRST/LAST classifier navigation failed: {e}")
        return None


def _handle_prev_next_classifier_navigation(nav_func: str, classifier_var: Optional[str], steps: int, context: RowContext, current_idx: int) -> Any:
    """Handle PREV/NEXT CLASSIFIER navigation."""
    try:
        if nav_func == 'PREV':
            target_idx = current_idx - steps
        else:  # NEXT
            target_idx = current_idx + steps
        
        # Check bounds
        if target_idx < 0 or target_idx >= len(context.rows):
            return None
        
        return _get_classifier_at_index(target_idx, classifier_var, context)
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] PREV/NEXT classifier navigation failed: {e}")
        return None


def _get_classifier_at_index(row_idx: int, subset_var: Optional[str], context: RowContext) -> str:
    """Get classifier value at specific index."""
    try:
        if row_idx < 0 or row_idx >= len(context.rows):
            return ""
        
        # Find which variable(s) this row belongs to
        matching_vars = []
        
        # Use full variables for forward navigation if available
        variables_to_search = getattr(context, '_full_match_variables', None) or getattr(context, 'variables', {})
        
        if variables_to_search:
            for var_name, indices in variables_to_search.items():
                if row_idx in indices:
                    matching_vars.append(var_name)
        
        if not matching_vars:
            return ""
        
        # If subset variable specified, validate
        if subset_var and hasattr(context, 'subsets') and subset_var in context.subsets:
            subset_components = context.subsets[subset_var]
            matching_vars = [var for var in matching_vars if var in subset_components]
            if matching_vars:
                # Return the actual component variable, not the subset name
                result_var = matching_vars[0]
                if hasattr(context, 'defined_variables') and context.defined_variables:
                    if result_var.lower() in [v.lower() for v in context.defined_variables]:
                        return result_var
                    else:
                        return result_var.upper()
                else:
                    return result_var.upper()
        
        if matching_vars:
            # Apply case sensitivity rules for classifier
            result_var = matching_vars[0]
            if hasattr(context, 'defined_variables') and context.defined_variables:
                if result_var.lower() in [v.lower() for v in context.defined_variables]:
                    return result_var
                else:
                    return result_var.upper()
            else:
                return result_var.upper()
        
        return ""
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Get classifier at index failed: {e}")
        return ""


def _evaluate_enhanced_function_call(match, context: RowContext, current_idx: int, recursion_depth: int) -> Any:
    """Evaluate enhanced function calls with better variable handling."""
    try:
        func_name = match.group(1).upper()
        column_ref = match.group(2)
        steps = int(match.group(3)) if match.group(3) else 1
        
        logger.debug(f"[NESTED_NAV] Enhanced function call: {func_name}({column_ref}, {steps})")
        
        # Parse column reference
        if '.' in column_ref:
            var_name, col_name = column_ref.split('.', 1)
        else:
            var_name = None
            col_name = column_ref
        
        # Create evaluator for navigation
        evaluator = ConditionEvaluator(context, 'MEASURES', recursion_depth + 1)
        evaluator.current_row = context.rows[current_idx] if 0 <= current_idx < len(context.rows) else None
        
        # Use the appropriate navigation function based on type
        if func_name in ('FIRST', 'LAST'):
            result = evaluator._handle_first_last_navigation(func_name, col_name, steps, var_name)
        else:  # PREV, NEXT
            result = evaluator.evaluate_navigation_function(func_name, col_name, steps, var_name)
        logger.debug(f"[NESTED_NAV] Enhanced function result: {result}")
        return result
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Enhanced function call failed: {e}")
        return None


def _evaluate_sql_construct_navigation(match, context: RowContext, current_idx: int, recursion_depth: int) -> Any:
    """Evaluate SQL construct navigation (RUNNING/FINAL keywords)."""
    try:
        outer_func = match.group(1).upper()     # PREV or NEXT
        sql_keyword = match.group(2).upper()   # RUNNING or FINAL
        inner_func = match.group(3).upper()    # FIRST or LAST
        column_ref = match.group(4)
        steps = int(match.group(5)) if match.group(5) else 1
        
        logger.debug(f"[NESTED_NAV] SQL construct: {outer_func}({sql_keyword} {inner_func}({column_ref}), {steps})")
        
        # Parse column reference
        if '.' in column_ref:
            var_name, col_name = column_ref.split('.', 1)
        else:
            var_name = None
            col_name = column_ref
        
        # Handle RUNNING vs FINAL semantics
        if sql_keyword == 'RUNNING':
            # RUNNING semantics: consider only rows up to current_idx in the match
            # Find the appropriate base row index using RUNNING semantics
            target_base_idx = _find_running_base_index(inner_func, var_name, col_name, context, current_idx)
        else:  # FINAL
            # FINAL semantics: consider all rows in the complete match
            target_base_idx = _find_final_base_index(inner_func, var_name, col_name, context)
        
        if target_base_idx is None:
            logger.debug(f"[NESTED_NAV] Could not find base index for {sql_keyword} {inner_func}")
            return None
        
        logger.debug(f"[NESTED_NAV] {sql_keyword} {inner_func} base index: {target_base_idx}")
        
        # Apply PREV/NEXT with steps
        if outer_func == 'PREV':
            final_idx = target_base_idx - steps
        else:  # NEXT
            final_idx = target_base_idx + steps
        
        logger.debug(f"[NESTED_NAV] Final index after {outer_func}({steps}): {final_idx}")
        
        # Get value with bounds checking
        if 0 <= final_idx < len(context.rows):
            result = context.rows[final_idx].get(col_name)
            logger.debug(f"[NESTED_NAV] Result: {result}")
            return result
        else:
            logger.debug(f"[NESTED_NAV] Index {final_idx} out of bounds [0, {len(context.rows)})")
            return None
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] SQL construct navigation failed: {e}")
        return None


def _find_running_base_index(inner_func: str, var_name: Optional[str], col_name: str, context: RowContext, current_idx: int) -> Optional[int]:
    """Find base index for RUNNING semantics (considering only rows up to current_idx)."""
    try:
        if var_name and hasattr(context, 'variables') and var_name in context.variables:
            # Variable-specific running semantics
            var_indices = [idx for idx in context.variables[var_name] if idx <= current_idx]
            if var_indices:
                if inner_func == 'FIRST':
                    return min(var_indices)
                else:  # LAST
                    return max(var_indices)
        else:
            # Column-only reference: consider all rows up to current_idx
            if inner_func == 'FIRST':
                return 0 if current_idx >= 0 else None
            else:  # LAST
                return current_idx if current_idx >= 0 else None
        
        return None
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Error finding running base index: {e}")
        return None


def _find_final_base_index(inner_func: str, var_name: Optional[str], col_name: str, context: RowContext) -> Optional[int]:
    """Find base index for FINAL semantics (considering all rows in match)."""
    try:
        if var_name and hasattr(context, 'variables') and var_name in context.variables:
            # Variable-specific final semantics
            var_indices = context.variables[var_name]
            if var_indices:
                if inner_func == 'FIRST':
                    return min(var_indices)
                else:  # LAST
                    return max(var_indices)
        else:
            # Column-only reference: consider all rows in context
            if inner_func == 'FIRST':
                return 0 if context.rows else None
            else:  # LAST
                return len(context.rows) - 1 if context.rows else None
        
        return None
    except Exception as e:
        logger.debug(f"[NESTED_NAV] Error finding final base index: {e}")
        return None


def _evaluate_ast_navigation(expr: str, context: RowContext, current_idx: int, current_var: Optional[str], recursion_depth: int) -> Any:
    """Fallback AST evaluation for navigation expressions."""
    try:
        logger.debug(f"[NESTED_NAV] AST fallback evaluation: {expr}")
        
        tree = ast.parse(expr, mode='eval')
        
        # Create evaluator with recursion protection
        evaluator = ConditionEvaluator(context, 'MEASURES', recursion_depth + 1)
        evaluator.current_row = context.rows[current_idx] if 0 <= current_idx < len(context.rows) else None
        
        # Set active evaluator to prevent further nesting
        original_evaluator = getattr(context, '_active_evaluator', None)
        context._active_evaluator = evaluator
        
        try:
            result = evaluator.visit(tree.body)
            logger.debug(f"[NESTED_NAV] AST result: {result}")
            return result
        finally:
            context._active_evaluator = original_evaluator
        
    except Exception as e:
        logger.debug(f"[NESTED_NAV] AST evaluation failed: {e}")
        return None


def _sql_to_python_condition(condition: str) -> str:
    """
    Convert SQL condition syntax to Python expression syntax.
    
    Args:
        condition: SQL condition string
        
    Returns:
        Python expression string
    """
    if not condition:
        return condition

    from src.matcher.evaluation_utils import inline_scalar_subqueries
    condition = inline_scalar_subqueries(condition)
    
    import re
    
    # Clean up whitespace and newlines to make valid Python expression
    # Replace newlines and multiple spaces with single spaces
    condition = re.sub(r'\s+', ' ', condition.strip())

    # SQL ARRAY[...] literals become Python list literals
    condition = re.sub(r'\bARRAY\s*\[', '[', condition, flags=re.IGNORECASE)
    
    # Convert SQL equality to Python equality
    # Handle cases like 'value = 10' -> 'value == 10'
    # But avoid changing '==' to '===='
    
    # First, preserve quoted strings to avoid corrupting them during regex replacements
    # Find all quoted strings and replace them with placeholders
    quote_patterns = [
        (r"'([^']*)'", "SINGLE_QUOTE_"),  # Single quotes
        (r'"([^"]*)"', "DOUBLE_QUOTE_"),  # Double quotes
    ]
    
    preserved_strings = {}
    placeholder_counter = 0
    
    for pattern, prefix in quote_patterns:
        matches = re.finditer(pattern, condition)
        for match in matches:
            placeholder = f"{prefix}{placeholder_counter}"
            preserved_strings[placeholder] = match.group(0)
            condition = condition.replace(match.group(0), placeholder, 1)
            placeholder_counter += 1
    
    # Convert SQL CASE expressions to Python conditional expressions
    # Pattern: CASE WHEN condition1 THEN result1 WHEN condition2 THEN result2 ... ELSE default END
    case_pattern = r'\bCASE\s+(.*?)\s+END\b'
    
    def convert_case(match):
        case_content = match.group(1)
        
        # Find all WHEN...THEN pairs
        when_pattern = r'\bWHEN\s+(.*?)\s+THEN\s+(.*?)(?=\s+WHEN|\s+ELSE|$)'
        when_matches = re.findall(when_pattern, case_content, re.IGNORECASE | re.DOTALL)
        
        # Find ELSE clause
        else_match = re.search(r'\bELSE\s+(.*?)$', case_content, re.IGNORECASE | re.DOTALL)
        else_clause = else_match.group(1).strip() if else_match else 'None'
        
        if not when_matches:
            return match.group(0)  # Return original if can't parse
        
        # Build nested conditional expression from right to left
        result = else_clause
        
        # Process WHEN clauses in reverse order to build nested conditionals
        for when_condition, then_result in reversed(when_matches):
            when_condition = when_condition.strip()
            then_result = then_result.strip()
            
            # Recursively convert the condition (but avoid infinite recursion)
            # Don't recursively call _sql_to_python_condition here as it can cause issues
            # Just handle basic operators in the when_condition
            when_condition = re.sub(r'(?<![=!<>])\s*=\s*(?!=)', ' == ', when_condition)
            when_condition = re.sub(r'\bAND\b', 'and', when_condition, flags=re.IGNORECASE)
            when_condition = re.sub(r'\bOR\b', 'or', when_condition, flags=re.IGNORECASE)
            when_condition = re.sub(r'\bNOT\b', 'not', when_condition, flags=re.IGNORECASE)
            
            result = f'({then_result} if {when_condition} else {result})'
        
        return result
    
    # Apply CASE conversion
    condition = re.sub(case_pattern, convert_case, condition, flags=re.IGNORECASE | re.DOTALL)
    
    # Replace single = with == but avoid changing already existing ==
    condition = re.sub(r'(?<![=!<>])\s*=\s*(?!=)', ' == ', condition)
    
    # Convert SQL logical operators to Python operators
    # Use word boundaries to avoid replacing parts of words
    condition = re.sub(r'\bAND\b', 'and', condition, flags=re.IGNORECASE)
    condition = re.sub(r'\bOR\b', 'or', condition, flags=re.IGNORECASE)
    condition = re.sub(r'\bNOT\b', 'not', condition, flags=re.IGNORECASE)
    
    # Convert SQL BETWEEN to Python range check
    # BETWEEN pattern: column BETWEEN value1 AND value2
    between_pattern = r'(\w+)\s+BETWEEN\s+([^A]+?)\s+AND\s+([^A]+?)(?=\s|$)'
    condition = re.sub(between_pattern, r'(\2 <= \1 <= \3)', condition, flags=re.IGNORECASE)
    
    # Handle IS NULL and IS NOT NULL
    # Use a helper function for null checking that handles both None and NaN
    # Enhanced to support function calls like PREV(A.price) IS NULL
    # Uses a callback function to properly handle nested parentheses
    def convert_is_null(match):
        """Convert IS NULL with proper handling of nested function calls."""
        expr = match.group(1).strip()
        return f'_is_null({expr})'
    
    def convert_is_not_null(match):
        """Convert IS NOT NULL with proper handling of nested function calls."""
        expr = match.group(1).strip()
        return f'(not _is_null({expr}))'
    
    # Pattern explanation:
    # - Matches simple identifiers: column_name
    # - Matches dot-notation: table.column or A.price
    # - Matches function calls with balanced parentheses: FUNC(args)
    # The pattern uses a non-greedy approach to find the expression before IS NULL
    # Step 1: Try to match function calls first (most specific)
    # Match: FUNCTION_NAME(...) where ... can contain nested parentheses
    # We use a helper to find balanced parentheses
    def find_expression_before_is_null(text, is_not_null=False):
        """
        Find and replace expressions before IS [NOT] NULL with proper parenthesis balancing.
        
        This handles complex cases like:
        - PREV(A.price) IS NULL
        - FUNC1(FUNC2(col)) IS NULL
        - table.column IS NULL
        - simple_column IS NULL
        - PREV(A.price)IS NULL (no space before IS)
        """
        # Allow optional whitespace before IS NULL for better robustness
        keyword = r'\s*IS\s+NOT\s+NULL\b' if is_not_null else r'\s*IS\s+NULL\b'
        result = text
        
        # Find all IS NULL occurrences
        pattern = re.compile(keyword, re.IGNORECASE)
        matches = list(pattern.finditer(result))
        
        # Process from right to left to maintain correct positions
        for match in reversed(matches):
            is_null_start = match.start()
            
            # Work backwards from IS NULL to find the complete expression
            pos = is_null_start - 1
            paren_count = 0
            expr_start = 0
            found_function = False
            
            # Skip trailing whitespace
            while pos >= 0 and result[pos].isspace():
                pos -= 1
            
            if pos < 0:
                continue
                
            # If we find a closing paren, we need to find its matching opening paren
            if result[pos] == ')':
                paren_count = 1
                found_function = True
                pos -= 1
                
                # Find the matching opening parenthesis
                while pos >= 0 and paren_count > 0:
                    if result[pos] == ')':
                        paren_count += 1
                    elif result[pos] == '(':
                        paren_count -= 1
                    pos -= 1
                
                # Now find the function name
                while pos >= 0 and (result[pos].isalnum() or result[pos] == '_'):
                    pos -= 1
                
                expr_start = pos + 1
            else:
                # Not a function call, find identifier with optional dot-notation
                while pos >= 0 and (result[pos].isalnum() or result[pos] in '_.'):
                    pos -= 1
                expr_start = pos + 1
            
            # Extract the expression
            expr = result[expr_start:is_null_start].strip()
            
            if not expr:
                continue
            
            # Create replacement
            if is_not_null:
                replacement = f'(not _is_null({expr}))'
            else:
                replacement = f'_is_null({expr})'
            
            # Replace in result
            result = result[:expr_start] + replacement + result[match.end():]
        
        return result
    
    # Process IS NOT NULL first (more specific)
    condition = find_expression_before_is_null(condition, is_not_null=True)
    # Then process IS NULL
    condition = find_expression_before_is_null(condition, is_not_null=False)
    
    # Handle IN predicates - convert SQL IN to Python in
    # Pattern: expression IN (value1, value2, ...) -> expression in [value1, value2, ...]
    # Enhanced to support function calls like LOWER(column) IN (...)
    def convert_in_predicate(match):
        full_match = match.group(0)
        left_expr = match.group(1).strip()
        in_values = match.group(2).strip()
        
        # If empty, return special handling
        if not in_values:
            return f'{left_expr} in []'
        
        # Convert parentheses to square brackets for Python list syntax
        python_list = f'[{in_values}]'
        return f'{left_expr} in {python_list}'
    
    # Enhanced IN predicates pattern to handle various expressions
    # This pattern matches multiple cases:
    # 1. Simple identifiers: column
    # 2. Dotted expressions: table.column
    # 3. Function calls: FUNCTION(args)
    # 4. Parenthesized expressions: (expression)
    # 5. Complex expressions: (value + 10), (column * 2), etc.
    
    # First try to match parenthesized expressions like (value + 10) IN (...)
    parenthesized_in_pattern = r'(\([^)]+\))\s+IN\s*\(([^)]*)\)'
    condition = re.sub(parenthesized_in_pattern, convert_in_predicate, condition, flags=re.IGNORECASE)

    # Literal left operands are common after inlining a scalar subquery, e.g.
    # `1 IN (SELECT 1)` -> `1 IN (1)`.
    literal_in_pattern = r"((?:'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|-?\d+(?:\.\d+)?))\s+IN\s*\(([^)]*)\)"
    condition = re.sub(literal_in_pattern, convert_in_predicate, condition, flags=re.IGNORECASE)
    
    # Then match function calls like SUBSTR(column, 1, 1) IN (...)
    complex_in_pattern = r'([A-Za-z_][A-Za-z0-9_]*\([^)]*(?:\([^)]*\)[^)]*)*\))\s+IN\s*\(([^)]*)\)'
    condition = re.sub(complex_in_pattern, convert_in_predicate, condition, flags=re.IGNORECASE)
    
    # Finally match simple expressions: column IN (...), table.column IN (...)
    simple_in_pattern = r'([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s+IN\s*\(([^)]*)\)'
    condition = re.sub(simple_in_pattern, convert_in_predicate, condition, flags=re.IGNORECASE)
    
    # Handle NOT IN predicates
    def convert_not_in_predicate(match):
        full_match = match.group(0)
        left_expr = match.group(1).strip()
        in_values = match.group(2).strip()
        
        # If empty, return special handling
        if not in_values:
            return f'{left_expr} not in []'
        
        # Convert parentheses to square brackets for Python list syntax
        python_list = f'[{in_values}]'
        return f'{left_expr} not in {python_list}'
    
    # Enhanced NOT IN predicates pattern to handle various expressions
    # First try to match parenthesized expressions like (value + 10) NOT IN (...)
    parenthesized_not_in_pattern = r'(\([^)]+\))\s+NOT\s+IN\s*\(([^)]*)\)'
    condition = re.sub(parenthesized_not_in_pattern, convert_not_in_predicate, condition, flags=re.IGNORECASE)
    
    # Then match function calls like SUBSTR(column, 1, 1) NOT IN (...)
    complex_not_in_pattern = r'([A-Za-z_][A-Za-z0-9_]*\([^)]*(?:\([^)]*\)[^)]*)*\))\s+NOT\s+IN\s*\(([^)]*)\)'
    condition = re.sub(complex_not_in_pattern, convert_not_in_predicate, condition, flags=re.IGNORECASE)
    
    # Finally match simple expressions: column NOT IN (...), table.column NOT IN (...)
    simple_not_in_pattern = r'([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s+NOT\s+IN\s*\(([^)]*)\)'
    condition = re.sub(simple_not_in_pattern, convert_not_in_predicate, condition, flags=re.IGNORECASE)
    
    # Handle empty IN predicates - convert to always false/true
    condition = re.sub(r'\bIN\s*\(\s*\)', 'in []', condition, flags=re.IGNORECASE)
    condition = re.sub(r'\bNOT\s+IN\s*\(\s*\)', 'not in []', condition, flags=re.IGNORECASE)
    
    # Restore preserved quoted strings
    for placeholder, original_string in preserved_strings.items():
        condition = condition.replace(placeholder, original_string)
    
    return condition

def _is_boolean_expression(node):
    """
    Determine if an AST node represents a boolean expression that should return True/False
    vs a value expression that should return the actual value.
    
    Args:
        node: AST node to analyze
        
    Returns:
        True if the expression should return a boolean, False if it should return actual value
    """
    if isinstance(node, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
        # Comparison operations (=, <, >, IN, etc.), boolean operations (AND, OR), 
        # or unary operations (NOT) should return boolean
        return True
    elif isinstance(node, ast.IfExp):
        # Conditional expressions (CASE WHEN) should return boolean if both branches are boolean
        return _is_boolean_expression(node.body) and _is_boolean_expression(node.orelse)
    elif isinstance(node, ast.Call):
        # Function calls - need to check the function name
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.upper()
            # Navigation functions and CLASSIFIER should return actual values
            if func_name in ('CLASSIFIER', 'PREV', 'NEXT', 'FIRST', 'LAST'):
                return False
            # Boolean functions should return boolean
            elif func_name in ('EXISTS', 'IS_NULL', 'IS_NOT_NULL'):
                return True
        # Default for unknown functions: return boolean for safety
        return True
    elif isinstance(node, (ast.Name, ast.Attribute, ast.Constant)):
        # Simple values should return their actual value
        return False
    else:
        # For unknown node types, default to boolean for safety
        return True
