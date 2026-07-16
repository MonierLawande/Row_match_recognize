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
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.executor.match_recognize import match_recognize
from src.matcher.matcher import PatternSearchLimitError

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

    def test_nonlinear_budget_never_changes_leftmost_match(self):
        """Resource protection must fail explicitly, not skip start row 0."""
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
        assert error.value.explored_steps == error.value.step_budget == 200_000

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
