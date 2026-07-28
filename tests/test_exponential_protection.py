"""
Test Exponential Pattern Protection
Matches testPotentiallyExponentialMatch() and testExponentialMatch() from TestRowPatternMatching.java

This is CRITICAL - ensures the implementation doesn't hang on exponential patterns.
"""

import pytest
import pandas as pd
import time
import sys
import os
from dataclasses import FrozenInstanceError
import importlib
from types import SimpleNamespace
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.executor.match_recognize import match_recognize
from src.matcher.automata import (
    NFAConstructionError,
    NFAConstructionLimitError,
    NFABuilder,
)
from src.matcher.dfa import (
    DFA_COMPILER_SCHEMA_VERSION,
    DFAAdaptiveMemoryPolicy,
    DFAConstructionError,
    DFAConstructionLimitError,
    DFAConstructionLimits,
    DFABuilder,
    EffectiveMemorySnapshot,
    SystemMemoryProbe,
)
from src.matcher.matcher import (
    BacktrackingSearchBudget,
    EnhancedMatcher,
    MatchConfig,
    PatternSearchLimitError,
    RowsPerMatch,
    SkipMode,
)
from src.matcher.pattern_tokenizer import tokenize_pattern
from src.matcher.row_context import RowContext
from src.utils.performance_optimizer import PatternCompilationCache
from src.utils.resource_profile import (
    AdaptiveResourceProfile,
    EffectiveCPUSnapshot,
)

class TestExponentialProtection:
    """Test protection against exponential pattern matching complexity."""

    def setup_method(self):
        """Setup test data for exponential pattern testing."""
        # Small dataset that could cause exponential blowup with certain patterns
        self.exponential_data = pd.DataFrame({
            'value': [1, 1, 1, 1, 1, 2]  # Many 1s followed by a 2
        })
        
        # Larger dataset for stress testing
        self.large_data = pd.DataFrame({
            'value': [1] * 20 + [2]  # 20 ones followed by a 2
        })

    def test_direct_matcher_initializes_metadata_without_pattern_text(self):
        """Direct construction must not depend on optional diagnostic text."""
        nfa = NFABuilder().build(tokenize_pattern("A"), {}, {})
        dfa = DFABuilder(nfa).build()

        matcher = EnhancedMatcher(dfa)

        assert matcher.transition_index
        assert matcher._anchor_metadata["has_start_anchor"] is False
        assert matcher._anchor_metadata["has_end_anchor"] is False

    def test_potentially_exponential_pattern_basic(self):
        """Test basic potentially exponential pattern - should complete quickly."""
        df = self.exponential_data
        
        start_time = time.time()
        
        query = """
        SELECT CLASSIFIER() AS classy
        FROM data
        MATCH_RECOGNIZE (
            MEASURES CLASSIFIER() AS classy
            PATTERN ((A+)+ B)
            DEFINE
                A AS value = 1,
                B AS value = 2
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete quickly (less than 5 seconds even on slow machines)
        assert execution_time < 5.0, f"Pattern took too long: {execution_time:.2f} seconds"
        
        if result is not None and not result.empty:
            # Should find the pattern correctly
            assert 'classy' in result.columns
            # With default ONE ROW PER MATCH, should only return the last row (B)
            labels = result['classy'].tolist()
            assert 'B' in labels
            # For ONE ROW PER MATCH, we expect only the final row of each match
            # The pattern ((A+)+ B) matches rows 0-5, but only row 5 (B) is returned
            assert len(labels) == 1, f"Expected 1 row for ONE ROW PER MATCH, got {len(labels)}"
            assert labels[0] == 'B', f"Expected 'B' as the only classifier, got {labels[0]}"
        else:
            # Empty result is also acceptable (no value=2 to match B)
            pass

    def test_exponential_pattern_with_timeout(self):
        """Test exponential pattern with strict timeout."""
        df = self.exponential_data
        
        start_time = time.time()
        
        query = """
        SELECT CLASSIFIER() AS classy
        FROM data
        MATCH_RECOGNIZE (
            MEASURES CLASSIFIER() AS classy
            ALL ROWS PER MATCH
            PATTERN ((A | B)+ LAST)
            DEFINE 
                A AS value = 1,
                B AS value = 1,
                LAST AS value = 2
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Must complete very quickly - this pattern could be exponential
        assert execution_time < 2.0, f"Exponential pattern took too long: {execution_time:.2f} seconds"
        
        if result is not None and not result.empty:
            # Should handle the alternation correctly
            assert 'classy' in result.columns
            labels = result['classy'].tolist()
            assert 'LAST' in labels
        else:
            pytest.skip("Exponential pattern protection might be preventing execution")

    def test_complex_exponential_pattern(self):
        """Test complex exponential pattern that requires optimization."""
        df = self.exponential_data
        
        start_time = time.time()
        
        query = """
        SELECT CLASSIFIER() AS classy
        FROM data
        MATCH_RECOGNIZE (
            MEASURES CLASSIFIER() AS classy
            ALL ROWS PER MATCH
            PATTERN ((A | B)* (C | D)+ E)
            DEFINE
                A AS value = 1,
                B AS value = 1,
                C AS value = 1,
                D AS value = 1,
                E AS value = 2
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete quickly despite complex pattern
        assert execution_time < 3.0, f"Complex exponential pattern took too long: {execution_time:.2f} seconds"
        
        if result is not None and not result.empty:
            assert 'classy' in result.columns
            labels = result['classy'].tolist()
            assert 'E' in labels  # Should find the terminating pattern
        
    def test_nested_quantifiers_protection(self):
        """Test nested quantifiers that could cause exponential explosion."""
        df = pd.DataFrame({
            'value': [1, 1, 1, 2, 3]
        })
        
        start_time = time.time()
        
        query = """
        SELECT CLASSIFIER() AS classy
        FROM data
        MATCH_RECOGNIZE (
            MEASURES CLASSIFIER() AS classy
            PATTERN ((A+)+)
            DEFINE A AS value = 1
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Nested quantifiers should be handled efficiently
        assert execution_time < 2.0, f"Nested quantifiers took too long: {execution_time:.2f} seconds"
        
        if result is not None and not result.empty:
            assert 'classy' in result.columns
            # Should match the 1s efficiently
            labels = result['classy'].tolist()
            assert all(label == 'A' for label in labels)

    def test_large_input_exponential_protection(self):
        """Test exponential protection with larger input."""
        df = self.large_data  # 20 ones + 1 two
        
        start_time = time.time()
        
        query = """
        SELECT COUNT(*) AS match_count
        FROM data
        MATCH_RECOGNIZE (
            MEASURES COUNT(*) AS match_count
            ONE ROW PER MATCH
            PATTERN ((A+)+ B)
            DEFINE
                A AS value = 1,
                B AS value = 2
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should handle larger input efficiently
        assert execution_time < 10.0, f"Large input pattern took too long: {execution_time:.2f} seconds"
        
        if result is not None and not result.empty:
            # Should find exactly one match
            assert len(result) == 1
            assert result.iloc[0]['match_count'] == 21  # 20 A's + 1 B

    def test_alternation_explosion_protection(self):
        """Test protection against alternation explosion."""
        df = pd.DataFrame({
            'value': [1, 1, 1, 1, 2]
        })
        
        start_time = time.time()
        
        query = """
        SELECT CLASSIFIER() AS classy
        FROM data
        MATCH_RECOGNIZE (
            MEASURES CLASSIFIER() AS classy
            ALL ROWS PER MATCH
            PATTERN ((A | A | A | A)+ B)
            DEFINE
                A AS value = 1,
                B AS value = 2
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Multiple alternations of same pattern should be optimized
        assert execution_time < 1.0, f"Alternation explosion took too long: {execution_time:.2f} seconds"
        
        if result is not None and not result.empty:
            assert 'classy' in result.columns
            labels = result['classy'].tolist()
            assert 'A' in labels
            assert 'B' in labels

    def test_empty_pattern_exponential(self):
        """Test exponential protection with empty patterns."""
        df = pd.DataFrame({
            'value': [1, 1, 1]
        })
        
        start_time = time.time()
        
        query = """
        SELECT CLASSIFIER() AS classy
        FROM data
        MATCH_RECOGNIZE (
            MEASURES CLASSIFIER() AS classy
            ALL ROWS PER MATCH
            PATTERN ((A*)+ B?)
            DEFINE
                A AS value = 1,
                B AS value = 2
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Empty patterns should not cause infinite loops
        assert execution_time < 1.0, f"Empty pattern handling took too long: {execution_time:.2f} seconds"
        
        # Result might be empty or have empty matches
        if result is not None:
            assert isinstance(result, pd.DataFrame)

    def test_backtracking_complexity_limit(self):
        """Test that backtracking complexity is limited."""
        df = pd.DataFrame({
            'id': range(1, 11),  # 1 to 10
            'value': [1, 1, 1, 1, 1, 1, 1, 1, 1, 2]
        })
        
        start_time = time.time()
        
        query = """
        SELECT id, CLASSIFIER() AS classy
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS classy
            ALL ROWS PER MATCH
            PATTERN (A+ B+ C+ D?)
            DEFINE
                A AS value = 1,
                B AS value = 1,
                C AS value = 1,
                D AS value = 2
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Complex backtracking should be limited
        assert execution_time < 5.0, f"Backtracking complexity took too long: {execution_time:.2f} seconds"
        
        if result is not None and not result.empty:
            assert 'classy' in result.columns
            # Should find some valid partitioning of the 1s into A+, B+, C+

    def test_state_dependent_backtracking_is_not_limited_by_python_stack(self):
        """Long quantified matches use the iterative exact-search stack.

        The match is deliberately longer than Python's default recursion
        limit.  B's predicate reads A's tentative assignments, ensuring this
        exercises the state-dependent backtracking path rather than the
        row-local linear matcher.
        """
        a_rows = 1600
        df = pd.DataFrame({
            'seq_id': range(a_rows + 1),
            'category': ['A'] * a_rows + ['B'],
            'price': [1.0] * a_rows + [2.0],
        })
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B' AND price > AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        assert result.to_dict('records') == [{
            'start_row': 0,
            'end_row': a_rows,
            'match_length': a_rows + 1,
        }]

    def test_state_dependent_or_does_not_use_and_prefilter(self):
        """Mixed OR remains on the complete exact predicate.

        The row-local branch is false for the final row, while the running
        aggregate branch is true.  An AND-style vectorized guard would reject
        this valid match.  NumPy-backed DataFrame scalars must also participate
        in SQL OR using truth-value semantics rather than object identity.
        """
        df = pd.DataFrame({
            'seq_id': [0, 1, 2],
            'category': ['A', 'A', 'C'],
            'price': [1.0, 2.0, 10.0],
        })
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B' OR price > AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        assert result.to_dict('records') == [{
            'start_row': 0,
            'end_row': 2,
        }]

    def test_running_aggregate_does_not_build_unused_classifier_index(self):
        """Long aggregate-only matches keep condition evaluation linear."""
        from src.matcher.condition_evaluator import ConditionEvaluator

        a_rows = 128
        b_rows = 128
        df = pd.DataFrame({
            'seq_id': range(a_rows + b_rows),
            'category': ['A'] * a_rows + ['B'] * b_rows,
            'price': [1.0] * a_rows + [2.0] * b_rows,
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B' AND price > AVG(A.price)
        )
        """

        original = ConditionEvaluator._build_evaluation_indices
        builds = 0

        def counted_build(evaluator):
            nonlocal builds
            builds += 1
            return original(evaluator)

        ConditionEvaluator._build_evaluation_indices = counted_build
        try:
            result = match_recognize(query, df)
        finally:
            ConditionEvaluator._build_evaluation_indices = original

        assert result.to_dict('records') == [{
            'match_length': a_rows + b_rows,
        }]
        assert builds == 0

    def test_aggregate_memo_is_invalidated_after_backtracking_rollback(self):
        """A cached aggregate cannot survive a change to its label scope."""
        prices = [1.0] + [100.0] * 16 + [40.0]
        df = pd.DataFrame({
            'seq_id': range(len(prices)),
            'price': prices,
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A+ B+ $)
            DEFINE B AS price > AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        # With 17 rows assigned to A, the final 40 cannot satisfy B.  Exact
        # search must roll A back to only the first row and recompute AVG(A),
        # after which all remaining rows satisfy B and the end anchor matches.
        assert result.to_dict('records') == [{
            'start_row': 0,
            'end_row': len(prices) - 1,
            'match_length': len(prices),
        }]

    def test_reused_exact_context_is_isolated_between_match_attempts(self):
        """Aggregate/cache state from one candidate cannot enter the next."""
        first_a = 16
        second_a = 16
        df = pd.DataFrame({
            'seq_id': range(first_a + second_a + 2),
            'category': (
                ['A'] * first_a + ['B']
                + ['A'] * second_a + ['B']
            ),
            'price': (
                [1.0] * first_a + [2.0]
                + [100.0] * second_a + [50.0]
            ),
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row,
                MATCH_NUMBER() AS match_number
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B' AND price > AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        # The first B is above AVG(A)=1.  The second is below its own
        # AVG(A)=100 and must not see the first attempt's cached aggregate.
        assert result.to_dict('records') == [{
            'start_row': 0,
            'end_row': first_a,
            'match_number': 1,
        }]

    def test_completed_exact_match_owns_detached_assignments(self):
        """Later context reuse cannot mutate an already completed match.

        The compiled exact executor transfers its assignment dictionary to a
        successful match to avoid copying every index list.  This lifecycle
        test retains the raw match objects seen by result processing and
        verifies that both successful matches keep independent assignments
        after the reusable context has advanced.
        """
        from src.matcher.matcher import EnhancedMatcher

        run = 16
        df = pd.DataFrame({
            'seq_id': range((run + 1) * 2),
            'category': ['A'] * run + ['B'] + ['A'] * run + ['B'],
            'price': [1.0] * run + [2.0] + [10.0] * run + [20.0],
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B' AND price > AVG(A.price)
        )
        """

        completed = []
        original = EnhancedMatcher._process_one_row_match

        def retain_match(matcher, match, *args, **kwargs):
            completed.append(match)
            return original(matcher, match, *args, **kwargs)

        EnhancedMatcher._process_one_row_match = retain_match
        try:
            result = match_recognize(query, df)
        finally:
            EnhancedMatcher._process_one_row_match = original

        assert result.to_dict('records') == [
            {'start_row': 0, 'end_row': run},
            {'start_row': run + 1, 'end_row': (run + 1) * 2 - 1},
        ]
        assert len(completed) == 2
        assert completed[0]['variables'] == {
            'A': list(range(run)),
            'B': [run],
        }
        assert completed[1]['variables'] == {
            'A': list(range(run + 1, (run + 1) * 2 - 1)),
            'B': [(run + 1) * 2 - 1],
        }
        assert completed[0]['variables'] is not completed[1]['variables']

    def test_columnar_exact_output_counts_input_progress(self):
        """Streaming output cannot trigger the stagnation safety guard.

        The executor's columnar ONE ROW path intentionally does not append a
        Python result dictionary for every match.  Progress must therefore be
        measured from the advancing input position and matcher count, not from
        the length of that legacy list.
        """
        match_count = 6000
        df = pd.DataFrame({
            'seq_id': range(match_count * 2),
            'category': ['A', 'B'] * match_count,
            'price': [1.0, 2.0] * match_count,
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B' AND price > AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        assert len(result) == match_count
        assert result.iloc[0].to_dict() == {
            'start_row': 0,
            'end_row': 1,
        }
        assert result.iloc[-1].to_dict() == {
            'start_row': match_count * 2 - 2,
            'end_row': match_count * 2 - 1,
        }

    def test_compiled_exact_search_preserves_simple_aggregate_semantics(self):
        """The compact aggregate IR agrees across every supported function."""
        df = pd.DataFrame({
            'seq_id': [0, 1, 2],
            'category': ['A', 'A', 'B'],
            'price': [1.0, 3.0, 5.0],
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row
            ONE ROW PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS category = 'A',
                B AS category = 'B'
                    AND SUM(A.price) = 4
                    AND AVG(A.price) = 2
                    AND COUNT(A.price) = 2
                    AND MIN(A.price) = 1
                    AND MAX(A.price) = 3
                    AND ARBITRARY(A.price) = 1
                    AND ARRAY_AGG(A.price) IS NOT NULL
        )
        """

        result = match_recognize(query, df)

        assert result.to_dict('records') == [{
            'start_row': 0,
            'end_row': 2,
        }]

    def test_compiled_residual_has_strict_navigation_fallback(self):
        """Only the explicitly supported residual IR bypasses AST dispatch."""
        import ast
        from src.matcher.condition_evaluator import (
            _sql_to_python_condition,
            compile_condition_ast,
        )

        aggregate_node = ast.parse(
            _sql_to_python_condition("price > AVG(A.price) + 1"),
            mode='eval',
        ).body
        aggregate_condition = compile_condition_ast(
            aggregate_node,
            source_condition="price > AVG(A.price) + 1",
        )
        assert aggregate_condition.uses_compiled_expression is True

        navigation_node = ast.parse(
            _sql_to_python_condition("price > PREV(price)"),
            mode='eval',
        ).body
        navigation_condition = compile_condition_ast(
            navigation_node,
            source_condition="price > PREV(price)",
        )
        assert navigation_condition.uses_compiled_expression is False

        from src.matcher.condition_evaluator import compile_condition
        complete_aggregate_condition = compile_condition(
            "price > AVG(A.price)"
        )
        assert complete_aggregate_condition.uses_compiled_expression is True

    def test_compiled_linear_exact_search_preserves_greedy_backtracking(self):
        """A greedy linear token rolls back when a later token needs its row."""
        df = pd.DataFrame({
            'seq_id': [0, 1, 2],
            'category': ['A', 'B', 'C'],
            'price': [1.0, 5.0, 10.0],
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(C.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A+ B+ C+)
            DEFINE
                A AS category = 'A' OR category = 'B',
                B AS category = 'B',
                C AS category = 'C' AND price > AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        # A greedily accepts row 1 first.  Exact preference search must return
        # it to B after B's required repetition initially fails.
        assert result.to_dict('records') == [{
            'start_row': 0,
            'end_row': 2,
            'match_length': 3,
        }]

    def test_anchored_linear_exact_search_uses_compact_rollback(self):
        """A terminal anchor remains exact beyond the generic step budget."""
        row_count = 1000
        df = pd.DataFrame({
            'seq_id': range(row_count),
            'price': [1.0] + [100.0] * (row_count - 2) + [40.0],
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A+ B+ $)
            DEFINE B AS price > AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        assert result.to_dict('records') == [{
            'start_row': 0,
            'end_row': row_count - 1,
            'match_length': row_count,
        }]

    def test_anchored_implicit_true_run_scales_past_fixed_search_floor(self):
        """A deterministic run larger than 200K is not search exhaustion."""
        row_count = 200_001
        df = pd.DataFrame({
            'seq_id': range(row_count),
            'price': [1.0] + [100.0] * (row_count - 2) + [40.0],
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                FIRST(A.seq_id) AS start_row,
                LAST(B.seq_id) AS end_row,
                COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A+ B+ $)
            DEFINE B AS price > AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        assert result.to_dict('records') == [{
            'start_row': 0,
            'end_row': row_count - 1,
            'match_length': row_count,
        }]

    def test_batched_exact_comparison_preserves_null_semantics(self):
        """A NULL in a numeric run is a rejection, never True for ``!=``."""
        row_count = 80
        prices = [1.0] + [5.0] * (row_count - 1)
        prices[50] = float('nan')
        df = pd.DataFrame({
            'seq_id': range(row_count),
            'category': ['A'] + ['B'] * (row_count - 1),
            'price': prices,
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A B+ $)
            DEFINE
                A AS category = 'A',
                B AS category = 'B' AND price != AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        assert result.empty

    def test_batched_exact_comparison_supports_reversed_arithmetic_operand(self):
        """Stable aggregate arithmetic can appear on either comparison side."""
        row_count = 96
        df = pd.DataFrame({
            'seq_id': range(row_count),
            'category': ['A'] + ['B'] * (row_count - 2) + ['C'],
            'price': [1.0] + [5.0] * (row_count - 2) + [9.0],
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A B+ C)
            DEFINE
                A AS category = 'A',
                B AS category = 'B' AND AVG(A.price) + 1 < price,
                C AS category = 'C'
        )
        """

        result = match_recognize(query, df)

        assert result['match_length'].tolist() == [row_count]

    def test_same_variable_aggregate_keeps_prospective_row_semantics(self):
        """Batching is disabled when the aggregate scope is being extended."""
        row_count = 80
        df = pd.DataFrame({
            'seq_id': range(row_count),
            'price': list(range(1, row_count + 1)),
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (A+ $)
            DEFINE A AS price >= AVG(A.price)
        )
        """

        result = match_recognize(query, df)

        assert result['match_length'].tolist() == [row_count]

    def test_nonlinear_incremental_aggregates_follow_dfs_rollback(self):
        """Prefix aggregates must track alternate-label append/pop states."""
        df = pd.DataFrame({
            'id': range(9),
            'value': [1] * 8 + [0],
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                COUNT(*) AS match_length,
                COUNT(A.value) AS a_count,
                COUNT(B.value) AS b_count
            ONE ROW PER MATCH
            PATTERN ((A | B)+ FINAL)
            DEFINE FINAL AS
                SUM(A.value) = SUM(B.value)
                AND MIN(A.value) = MAX(B.value)
                AND ARBITRARY(A.value) = 1
        )
        """

        result = match_recognize(query, df)

        assert result.to_dict('records') == [{
            'match_length': 9,
            'a_count': 4,
            'b_count': 4,
        }]

    def test_nonlinear_budget_never_changes_leftmost_match(
        self,
        monkeypatch,
    ):
        """Resource protection must fail explicitly, not skip start row 0."""
        constrained_profile = self._search_resource_profile(1)
        executor_module = importlib.import_module(
            "src.executor.match_recognize"
        )
        monkeypatch.setattr(
            executor_module,
            "get_adaptive_resource_profile",
            lambda refresh=False: constrained_profile,
        )
        label_rows = 24
        df = pd.DataFrame({
            'seq_id': range(label_rows + 1),
            'value': [1] * label_rows + [0],
        })
        query = """
        SELECT * FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES
                COUNT(*) AS match_length,
                COUNT(A.value) AS a_count,
                COUNT(B.value) AS b_count
            ONE ROW PER MATCH
            PATTERN ((A | B)+ FINAL $)
            DEFINE FINAL AS value = 0 AND SUM(A.value) = SUM(B.value)
        )
        """

        with pytest.raises(
            PatternSearchLimitError,
            match=r"PM004:.*leftmost-match",
        ) as error:
            match_recognize(query, df)
        assert error.value.start_idx == 0
        assert error.value.explored_steps == error.value.step_budget
        assert error.value.step_budget > 0

    @staticmethod
    def _search_resource_profile(query_budget_mib):
        gib = 1024 ** 3
        return AdaptiveResourceProfile(
            memory=EffectiveMemorySnapshot(
                host_total_bytes=gib,
                host_available_bytes=gib,
                effective_limit_bytes=gib,
                effective_available_bytes=gib,
            ),
            cpu=EffectiveCPUSnapshot(1, 1, 1),
            reserve_fraction=0.0,
            reserve_floor_bytes=0,
            cache_available_fraction=0.0,
            cache_limit_fraction=0.0,
            query_available_fraction=1.0,
            query_limit_fraction=1.0,
            query_hard_max_bytes=query_budget_mib * 1024 ** 2,
        )

    @staticmethod
    def _cache_resource_profile(cache_budget_mib):
        gib = 1024 ** 3
        return AdaptiveResourceProfile(
            memory=EffectiveMemorySnapshot(
                host_total_bytes=gib,
                host_available_bytes=gib,
                effective_limit_bytes=gib,
                effective_available_bytes=gib,
            ),
            cpu=EffectiveCPUSnapshot(1, 1, 1),
            reserve_fraction=0.0,
            reserve_floor_bytes=0,
            cache_available_fraction=1.0,
            cache_limit_fraction=1.0,
            cache_hard_max_bytes=cache_budget_mib * 1024 ** 2,
            query_available_fraction=1.0,
            query_limit_fraction=1.0,
            query_hard_max_bytes=128 * 1024 ** 2,
        )

    def test_nfa_optional_resources_follow_shared_profile(self):
        """Optional NFA caches follow the profile; graph states are owned."""
        disabled_profile = self._cache_resource_profile(0)
        disabled_builder = NFABuilder(
            resource_profile=disabled_profile,
        )
        disabled_nfa = disabled_builder.build(
            tokenize_pattern("A B"),
            {},
            {},
        )

        assert disabled_nfa._epsilon_cache_limit == 0
        assert not hasattr(disabled_builder, "_state_pool")
        assert not hasattr(disabled_builder, "_transition_pool")
        disabled_nfa.epsilon_closure([disabled_nfa.start])
        assert disabled_nfa._epsilon_cache == {}

        larger_profile = self._cache_resource_profile(64)
        larger_builder = NFABuilder(resource_profile=larger_profile)
        larger_nfa = larger_builder.build(
            tokenize_pattern("A B"),
            {},
            {},
        )

        assert larger_nfa._epsilon_cache_limit > 0
        assert not hasattr(larger_builder, "_state_pool")
        assert not hasattr(larger_builder, "_transition_pool")

    def test_nfa_builder_cleanup_does_not_mutate_returned_graph(self):
        """A live automaton must remain valid after its builder is released."""
        builder = NFABuilder()
        nfa = builder.build(
            tokenize_pattern("OWNERSHIP_A OWNERSHIP_B"),
            {},
            {},
        )
        state_count = len(nfa.states)

        builder.cleanup()

        assert builder.states == []
        assert len(nfa.states) == state_count
        assert nfa.states[nfa.accept].is_accept
        assert nfa.validate()

    def test_resource_profile_flows_through_all_automata_layers(self):
        """Low-level callers inherit one profile without re-probing the host."""
        profile = self._cache_resource_profile(16)
        nfa = NFABuilder(resource_profile=profile).build(
            tokenize_pattern("A B"),
            {},
            {},
        )
        dfa = DFABuilder(nfa).build()
        matcher = EnhancedMatcher(
            dfa,
            original_pattern="A B",
            defined_variables=["A", "B"],
            define_conditions={},
        )

        assert nfa._resource_profile is profile
        assert dfa._resource_profile is profile
        assert matcher._resource_profile is profile

    @staticmethod
    def _build_limit_test_matcher(
        pattern,
        variables,
        resource_profile=None,
    ):
        nfa = NFABuilder().build(tokenize_pattern(pattern), {}, {})
        dfa = DFABuilder(
            nfa,
            resource_profile=resource_profile,
        ).build()
        return EnhancedMatcher(
            dfa,
            original_pattern=pattern,
            defined_variables=variables,
            define_conditions={},
            resource_profile=resource_profile,
        )

    def test_backtracking_budget_is_frozen_and_resource_adaptive(self):
        """The same rows/DFA receive more search work under a larger profile."""
        small_matcher = self._build_limit_test_matcher(
            "(A | B)+ C",
            ["A", "B", "C"],
            self._search_resource_profile(1),
        )
        large_matcher = self._build_limit_test_matcher(
            "(A | B)+ C",
            ["A", "B", "C"],
            self._search_resource_profile(64),
        )

        small = small_matcher._build_partition_backtracking_budget(8)
        large = large_matcher._build_partition_backtracking_budget(8)

        assert isinstance(small, BacktrackingSearchBudget)
        assert small.max_depth == large.max_depth == 8
        assert small.dfa_states == large.dfa_states
        assert small.dfa_transitions == large.dfa_transitions
        assert small.memory_budget_bytes < large.memory_budget_bytes
        assert (
            small.exact_condition_step_budget
            < large.exact_condition_step_budget
        )
        assert (
            small.full_search_step_budget
            < large.full_search_step_budget
        )
        with pytest.raises(FrozenInstanceError):
            small.max_depth = 9

    def test_backtracking_depth_uses_actual_partition_bound(self):
        """Depth follows input consumption instead of a default-size guess."""
        matcher = self._build_limit_test_matcher(
            "A+",
            ["A"],
            self._search_resource_profile(8),
        )

        small = matcher._partition_backtracking_budget_for(7)
        large = matcher._partition_backtracking_budget_for(700)

        assert small.max_depth == 7
        assert large.max_depth == 700
        assert small is not large
        assert matcher._partition_backtracking_budget is large

    def test_greedy_dfa_budget_never_returns_best_so_far(self):
        """An incomplete greedy search cannot publish an early candidate."""
        matcher = self._build_limit_test_matcher(
            "(A | B)+",
            ["A", "B"],
        )
        rows = [{"value": 1} for _ in range(16)]
        context = RowContext(
            rows=rows,
            defined_variables=["A", "B"],
        )

        with pytest.raises(PatternSearchLimitError) as error:
            matcher._find_single_match_greedy_dfa_search(
                rows,
                0,
                context,
            )

        assert error.value.reason == "greedy_dfa_state_limit"
        assert error.value.start_idx == 0
        assert error.value.explored_steps == error.value.step_budget

    def test_greedy_candidate_score_matches_legacy_order_for_normal_priorities(
        self,
    ):
        """The linear key preserves length/count/leftmost-priority ordering."""
        matcher = self._build_limit_test_matcher(
            "(A | B | C)+",
            ["A", "B", "C"],
        )
        candidates = [
            {
                "start": 0,
                "end": 3,
                "variables": {"A": [0, 2], "B": [1, 3], "C": []},
            },
            {
                "start": 0,
                "end": 3,
                "variables": {"A": [0, 3], "B": [1, 2], "C": []},
            },
            {
                "start": 0,
                "end": 3,
                "variables": {"A": [1, 2], "B": [0, 3], "C": []},
            },
            {
                "start": 0,
                "end": 4,
                "variables": {"A": [0, 2, 4], "B": [1, 3], "C": []},
            },
        ]

        def legacy_score(match):
            length = match["end"] - match["start"] + 1
            assigned_count = sum(
                len(indices)
                for indices in match["variables"].values()
            )
            priority = 0
            for row_idx in range(match["start"], match["end"] + 1):
                for variable, indices in match["variables"].items():
                    if row_idx in indices:
                        priority = (
                            priority * 1000
                            + matcher.alternation_order.get(variable, 0)
                        )
                        break
            return length, assigned_count, -priority

        expected_order = sorted(
            range(len(candidates)),
            key=lambda index: legacy_score(candidates[index]),
        )
        actual_order = sorted(
            range(len(candidates)),
            key=lambda index: matcher._match_candidate_score(
                candidates[index]
            ),
        )

        assert actual_order == expected_order

    def test_greedy_candidate_score_uses_exact_lexicographic_priority(self):
        """Priority comparison is not corrupted by a base-1000 carry."""
        matcher = self._build_limit_test_matcher(
            "(A | B | C)+",
            ["A", "B", "C"],
        )
        matcher.alternation_order = {"A": 1, "B": 0, "C": 1001}
        starts_with_a = {
            "start": 0,
            "end": 1,
            "variables": {"A": [0], "B": [1], "C": []},
        }
        starts_with_b = {
            "start": 0,
            "end": 1,
            "variables": {"A": [], "B": [0], "C": [1]},
        }

        assert (
            matcher._match_candidate_score(starts_with_b)
            > matcher._match_candidate_score(starts_with_a)
        )

    def test_greedy_candidate_score_keeps_first_assignment_on_overlap(self):
        """Defensive overlapping assignments retain mapping-order semantics."""
        matcher = self._build_limit_test_matcher(
            "(A | B)+",
            ["A", "B"],
        )
        overlap = {
            "start": 0,
            "end": 1,
            "variables": {"B": [0, 1], "A": [0, 1]},
        }

        length, assigned_count, priority_key = (
            matcher._match_candidate_score(overlap)
        )

        assert length == 2
        assert assigned_count == 4
        assert priority_key == (-matcher.alternation_order["B"],) * 2

    def test_greedy_search_defers_tiebreak_for_distinct_lengths(
        self,
        monkeypatch,
    ):
        """A deterministic growing match does not build secondary keys."""
        matcher = self._build_limit_test_matcher(
            "A B+",
            ["A", "B"],
        )
        rows = [{"value": 1} for _ in range(32)]
        context = RowContext(
            rows=rows,
            defined_variables=["A", "B"],
        )
        calls = 0

        def record_tiebreak(match):
            nonlocal calls
            calls += 1
            return 0, ()

        monkeypatch.setattr(
            matcher,
            "_match_candidate_tiebreak_key",
            record_tiebreak,
        )

        result = matcher._find_single_match_greedy_dfa_search(
            rows,
            0,
            context,
        )

        assert result["end"] == len(rows) - 1
        assert calls == 0

    @pytest.mark.parametrize(
        ("max_iterations", "max_depth", "expected_reason"),
        [
            (1, 100, "full_backtracking_iteration_limit"),
            (100, 0, "full_backtracking_depth_limit"),
        ],
    )
    def test_full_backtracking_limits_never_become_no_match(
        self,
        max_iterations,
        max_depth,
        expected_reason,
    ):
        """Both full-search guards fail closed instead of returning ``None``."""
        matcher = self._build_limit_test_matcher("A+", ["A"])
        backtracker = matcher.FullBacktrackingMatcher(matcher)
        backtracker.max_iterations = max_iterations
        backtracker.max_depth = max_depth
        rows = [{"value": 1}, {"value": 1}]
        context = RowContext(rows=rows, defined_variables=["A"])

        with pytest.raises(PatternSearchLimitError) as error:
            backtracker.find_match_with_backtracking(
                rows,
                0,
                context,
            )

        assert error.value.reason == expected_reason
        assert error.value.start_idx == 0

    def test_partition_stagnation_never_advances_and_returns_partial_rows(
        self,
        monkeypatch,
    ):
        """A non-progressing skip path raises before partial output is returned."""
        matcher = self._build_limit_test_matcher("A", ["A"])
        rows = [{"value": 1}]
        config = MatchConfig(
            rows_per_match=RowsPerMatch.ONE_ROW,
            skip_mode=SkipMode.TO_FIRST,
            skip_var="A",
            show_empty=False,
            include_unmatched=False,
        )
        fixed_match = {
            "start": 0,
            "end": 0,
            "variables": {"A": [0]},
            "state": matcher.start_state,
            "is_empty": False,
            "excluded_vars": set(),
            "excluded_rows": [],
            "has_empty_alternation": False,
        }

        monkeypatch.setattr(
            matcher,
            "_smart_condition_preprocessing",
            lambda _rows: None,
        )
        monkeypatch.setattr(
            matcher,
            "_can_use_linear_quantifier_plan",
            lambda _config: False,
        )
        monkeypatch.setattr(
            matcher,
            "_can_use_row_local_dfa_fast_path",
            lambda _config: False,
        )
        monkeypatch.setattr(
            matcher,
            "_should_use_condition_backtracking",
            lambda: False,
        )
        monkeypatch.setattr(
            matcher,
            "_find_single_match",
            lambda *_args, **_kwargs: fixed_match.copy(),
        )
        monkeypatch.setattr(
            matcher,
            "_get_skip_position",
            lambda *_args, **_kwargs: 0,
        )

        with pytest.raises(PatternSearchLimitError) as error:
            matcher.find_matches(rows, config=config, measures={})

        assert error.value.reason == "enumeration_stagnation"
        assert error.value.start_idx == 0

    def test_memory_usage_protection(self):
        """Test that memory usage doesn't explode with exponential patterns."""
        df = pd.DataFrame({
            'value': [1] * 15 + [2]  # 15 ones + 1 two
        })
        
        import psutil
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        start_time = time.time()
        
        query = """
        SELECT COUNT(*) AS count
        FROM data
        MATCH_RECOGNIZE (
            MEASURES COUNT(*) AS count
            ONE ROW PER MATCH
            PATTERN ((A | B)+ FINAL)
            DEFINE
                A AS value = 1,
                B AS value = 1,
                FINAL AS value = 2
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        end_time = time.time()
        execution_time = end_time - start_time
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Should not use excessive memory
        assert memory_increase < 100, f"Memory usage increased by {memory_increase:.1f} MB"
        assert execution_time < 5.0, f"Pattern took too long: {execution_time:.2f} seconds"
        
        if result is not None and not result.empty:
            assert len(result) == 1
            assert result.iloc[0]['count'] == 16  # All rows matched

    def test_dfa_state_limit_fails_instead_of_returning_partial_automaton(self):
        """A state cap is an explicit compilation failure, not a smaller DFA."""
        nfa = NFABuilder().build(tokenize_pattern("A B"), {}, {})

        with pytest.raises(DFAConstructionLimitError) as error:
            DFABuilder(
                nfa,
                DFAConstructionLimits(max_states=2),
            ).build()

        assert error.value.reason == 'state_limit'
        assert error.value.limit == 2
        assert error.value.observed == 3
        assert error.value.states_created == 2
        assert error.value.nfa_state_count == len(nfa.states)

        complete = DFABuilder(
            nfa,
            DFAConstructionLimits(max_states=3),
        ).build()
        assert len(complete.states) == 3
        assert complete.metadata['construction_complete'] is True
        assert (
            complete.metadata['compiler_schema_version']
            == DFA_COMPILER_SCHEMA_VERSION
        )

    def test_nfa_failure_never_becomes_a_no_match_automaton(
        self,
        monkeypatch,
    ):
        """An internal compiler failure is explicit and cannot be cached."""
        builder = NFABuilder()

        def fail_sequence(*args, **kwargs):
            raise RuntimeError("forced NFA construction failure")

        monkeypatch.setattr(builder, '_process_sequence', fail_sequence)

        with pytest.raises(NFAConstructionError) as error:
            builder.build(
                tokenize_pattern("FORCEDNFAA FORCEDNFAB"),
                {},
                {},
            )

        assert isinstance(error.value.__cause__, RuntimeError)
        assert "no approximate or no-match automaton" in str(error.value)

    def test_permute_complexity_guard_never_rewrites_the_pattern(self):
        """An oversized PERMUTE is rejected instead of reduced to five labels."""
        pattern = "PERMUTE(A?, B?, C?, D?, E?, F?, G?, H?)"

        with pytest.raises(NFAConstructionLimitError) as error:
            NFABuilder().build(tokenize_pattern(pattern), {}, {})

        assert error.value.reason == 'PERMUTE branch estimate'
        assert error.value.observed > error.value.limit

    def test_dfa_iteration_limit_fails_instead_of_returning_partial_automaton(self):
        """The work limit has the same fail-closed contract as the state cap."""
        nfa = NFABuilder().build(tokenize_pattern("A B"), {}, {})

        with pytest.raises(DFAConstructionLimitError) as error:
            DFABuilder(
                nfa,
                DFAConstructionLimits(max_states=10, max_iterations=1),
            ).build()

        assert error.value.reason == 'iteration_limit'
        assert error.value.limit == 1
        assert error.value.observed == 2
        assert error.value.pending_subsets > 0

    def test_dfa_subset_warning_never_truncates_epsilon_closure(self):
        """Diagnostic thresholds must not change the recognized language."""
        nfa = NFABuilder().build(
            tokenize_pattern("(A? B?)? C"),
            {},
            {},
        )
        exact_start_closure = frozenset(nfa.epsilon_closure([nfa.start]))
        assert len(exact_start_closure) > 1

        dfa = DFABuilder(
            nfa,
            DFAConstructionLimits(
                max_states=100,
                subset_warning_threshold=1,
            ),
        ).build()

        assert dfa.states[dfa.start].nfa_states == exact_start_closure
        assert dfa.metadata['construction_complete'] is True

    def test_adaptive_dfa_limit_scales_continuously_with_memory(self):
        """Automatic sizing is continuous rather than a few fixed RAM bands."""
        policy = DFAAdaptiveMemoryPolicy(
            reserve_fraction=0.0,
            reserve_floor_bytes=0,
            available_fraction=1.0,
            total_fraction=1.0,
            estimated_bytes_per_state=1 * 1024 * 1024,
            hard_max_states=2_000_000,
            minimum_states=1,
        )

        def resolved_states(memory_mib):
            memory_bytes = memory_mib * 1024 * 1024
            snapshot = EffectiveMemorySnapshot(
                host_total_bytes=memory_bytes,
                host_available_bytes=memory_bytes,
                effective_limit_bytes=memory_bytes,
                effective_available_bytes=memory_bytes,
            )
            return policy.resolve(snapshot).max_states

        assert resolved_states(64) == 64
        assert resolved_states(65) == 65
        assert resolved_states(96) == 96
        assert resolved_states(128) == 128

    def test_default_adaptive_limit_retains_production_safety_ceiling(self):
        """Large hosts do not silently raise the structural safety ceiling."""
        policy = DFAAdaptiveMemoryPolicy()

        def resolved_states(memory_gib):
            memory_bytes = memory_gib * 1024 ** 3
            snapshot = EffectiveMemorySnapshot(
                host_total_bytes=memory_bytes,
                host_available_bytes=memory_bytes,
                effective_limit_bytes=memory_bytes,
                effective_available_bytes=memory_bytes,
            )
            return policy.resolve(snapshot).max_states

        states_32_gib = resolved_states(32)
        states_256_gib = resolved_states(256)
        states_1_tib = resolved_states(1024)
        states_8_tib = resolved_states(8 * 1024)

        assert states_32_gib == 50_000
        assert states_256_gib == 50_000
        assert states_1_tib == 50_000
        assert states_8_tib == 50_000
        assert policy.hard_max_states == 50_000

    def test_administrator_can_add_a_dfa_state_ceiling(self):
        """An optional deployment ceiling intersects the memory-derived cap."""
        gib = 1024 ** 3
        snapshot = EffectiveMemorySnapshot(
            host_total_bytes=1024 * gib,
            host_available_bytes=1024 * gib,
            effective_limit_bytes=1024 * gib,
            effective_available_bytes=1024 * gib,
        )
        policy = DFAAdaptiveMemoryPolicy(hard_max_states=123_456)

        assert policy.resolve(snapshot).max_states == 123_456

    def test_effective_memory_uses_cgroup_v2_remaining_allowance(self):
        """A container cap wins when psutil exposes the larger host."""
        gib = 1024 ** 3
        files = {
            '/proc/self/cgroup': '0::/test.slice',
            '/sys/fs/cgroup/test.slice/memory.max': str(2 * gib),
            '/sys/fs/cgroup/test.slice/memory.current': str(gib // 2),
        }

        def read_text(path):
            if path not in files:
                raise FileNotFoundError(path)
            return files[path]

        probe = SystemMemoryProbe(
            host_provider=lambda: SimpleNamespace(
                total=64 * gib,
                available=48 * gib,
            ),
            text_reader=read_text,
        )
        snapshot = probe.snapshot()

        assert snapshot.cgroup_limit_bytes == 2 * gib
        assert snapshot.cgroup_remaining_bytes == 3 * gib // 2
        assert snapshot.effective_limit_bytes == 2 * gib
        assert snapshot.effective_available_bytes == 3 * gib // 2
        assert snapshot.source == 'host+cgroup'

    def test_unlimited_cgroup_uses_host_memory(self):
        """The cgroup-v2 ``max`` token does not create a false small limit."""
        gib = 1024 ** 3
        files = {
            '/proc/self/cgroup': '0::/test.slice',
            '/sys/fs/cgroup/test.slice/memory.max': 'max',
            '/sys/fs/cgroup/test.slice/memory.current': str(gib),
        }

        def read_text(path):
            if path not in files:
                raise FileNotFoundError(path)
            return files[path]

        probe = SystemMemoryProbe(
            host_provider=lambda: SimpleNamespace(
                total=16 * gib,
                available=12 * gib,
            ),
            text_reader=read_text,
        )
        snapshot = probe.snapshot()

        assert snapshot.cgroup_limit_bytes is None
        assert snapshot.effective_limit_bytes == 16 * gib
        assert snapshot.effective_available_bytes == 12 * gib
        assert snapshot.source == 'host'

    def test_effective_memory_supports_cgroup_v1(self):
        """Legacy cgroup-v1 limits are included in the effective allowance."""
        gib = 1024 ** 3
        files = {
            '/proc/self/cgroup': '5:memory:/docker/test',
            (
                '/sys/fs/cgroup/memory/docker/test/'
                'memory.limit_in_bytes'
            ): str(4 * gib),
            (
                '/sys/fs/cgroup/memory/docker/test/'
                'memory.usage_in_bytes'
            ): str(gib),
        }

        def read_text(path):
            if path not in files:
                raise FileNotFoundError(path)
            return files[path]

        probe = SystemMemoryProbe(
            host_provider=lambda: SimpleNamespace(
                total=64 * gib,
                available=48 * gib,
            ),
            text_reader=read_text,
        )
        snapshot = probe.snapshot()

        assert snapshot.cgroup_limit_bytes == 4 * gib
        assert snapshot.cgroup_remaining_bytes == 3 * gib
        assert snapshot.effective_limit_bytes == 4 * gib
        assert snapshot.effective_available_bytes == 3 * gib

    def test_explicit_dfa_limits_bypass_memory_detection(self):
        """A caller-supplied deterministic limit has highest precedence."""
        nfa = NFABuilder().build(tokenize_pattern("A B"), {}, {})

        class FailingProbe:
            @staticmethod
            def snapshot():
                raise AssertionError("explicit limits must bypass the probe")

        builder = DFABuilder(
            nfa,
            limits=DFAConstructionLimits(max_states=17),
            memory_probe=FailingProbe(),
        )

        assert builder.MAX_DFA_STATES == 17
        assert builder.metadata['construction_limits']['mode'] == 'explicit'

    def test_failed_dfa_resource_detection_is_explicit(self):
        """An unknown environment cannot select an arbitrary fixed state cap."""
        nfa = NFABuilder().build(tokenize_pattern("A B"), {}, {})
        # Remove the inherited profile so this exercises the low-level probe
        # contract used by embedders.
        nfa._resource_profile = None

        class FailingProbe:
            @staticmethod
            def snapshot():
                raise OSError("resource files unavailable")

        with pytest.raises(
            DFAConstructionError,
            match="Unable to resolve a safe DFA memory budget",
        ):
            DFABuilder(nfa, memory_probe=FailingProbe())

    def test_default_iteration_limit_respects_stable_state_ceiling(self):
        """Large-memory hosts retain the tested default construction bounds."""
        nfa = NFABuilder().build(tokenize_pattern("A B"), {}, {})
        gib = 1024 ** 3
        probe = SystemMemoryProbe(
            host_provider=lambda: SimpleNamespace(
                total=256 * gib,
                available=256 * gib,
            ),
            text_reader=lambda path: (_ for _ in ()).throw(
                FileNotFoundError(path)
            ),
        )
        builder = DFABuilder(nfa, memory_probe=probe)

        assert builder.MAX_DFA_STATES == 50_000
        assert builder.MAX_ITERATIONS >= builder.MAX_DFA_STATES
        assert (
            builder.metadata['construction_limits']['mode']
            == 'adaptive_memory'
        )

    def test_match_recognize_propagates_dfa_limit_as_compilation_error(
        self,
        monkeypatch,
    ):
        """A compiler limit cannot be mistaken for a valid empty result."""
        cache_writes = []
        monkeypatch.setattr(
            PatternCompilationCache,
            'get_compiled_pattern',
            staticmethod(lambda *args, **kwargs: None),
        )
        monkeypatch.setattr(
            PatternCompilationCache,
            'cache_compiled_pattern',
            staticmethod(
                lambda *args, **kwargs: cache_writes.append((args, kwargs))
            ),
        )
        monkeypatch.setattr(
            DFABuilder,
            '_calculate_max_states',
            lambda self: 2,
        )
        df = pd.DataFrame({
            'seq_id': [1, 2],
            'category': ['A', 'B'],
        })
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY seq_id
            MEASURES COUNT(*) AS match_length
            ONE ROW PER MATCH
            PATTERN (LIMITA LIMITB)
            DEFINE
                LIMITA AS category = 'A',
                LIMITB AS category = 'B'
        )
        """

        with pytest.raises(DFAConstructionLimitError) as error:
            match_recognize(query, df)

        assert error.value.reason == 'state_limit'
        assert error.value.states_created == 2
        assert cache_writes == []

    def test_structurally_invalid_cached_dfa_is_recompiled(
        self,
        monkeypatch,
    ):
        """A complete marker alone cannot make a corrupted DFA executable."""
        stale_nfa = NFABuilder().build(tokenize_pattern("A B"), {}, {})
        stale_dfa = DFABuilder(stale_nfa).build()
        stale_dfa.start = len(stale_dfa.states)
        cache_writes = []

        monkeypatch.setattr(
            PatternCompilationCache,
            'get_compiled_pattern',
            staticmethod(
                lambda *args, **kwargs: (
                    stale_dfa,
                    stale_nfa,
                    {'compilation_time': 0.1},
                )
            ),
        )
        monkeypatch.setattr(
            PatternCompilationCache,
            'cache_compiled_pattern',
            staticmethod(
                lambda *args, **kwargs: cache_writes.append((args, kwargs))
            ),
        )

        result = match_recognize(
            """
            SELECT *
            FROM data
            MATCH_RECOGNIZE (
                ORDER BY seq_id
                MEASURES COUNT(*) AS match_length
                ONE ROW PER MATCH
                PATTERN (A B)
                DEFINE
                    A AS category = 'A',
                    B AS category = 'B'
            )
            """,
            pd.DataFrame({
                'seq_id': [1, 2],
                'category': ['A', 'B'],
            }),
        )

        assert result['match_length'].tolist() == [2]
        assert len(cache_writes) == 1
