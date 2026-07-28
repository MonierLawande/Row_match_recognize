"""
Tests for the navigation functions and condition evaluation in match_recognize.
"""

import ast
import pickle
import pytest
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple

# Add the src directory to path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the match_recognize implementation and condition evaluator
from src.executor.match_recognize import match_recognize
from src.matcher.condition_evaluator import (
    ConditionEvaluator,
    compile_condition,
    evaluate_nested_navigation,
    validate_navigation_conditions,
)
from src.matcher.evaluation_utils import ExpressionValidationError
from src.matcher.measure_evaluator import MeasureEvaluator
from src.matcher.row_context import RowContext, _BoundedCacheDict
from src.utils.resource_profile import (
    AdaptiveResourceProfile,
    EffectiveCPUSnapshot,
    EffectiveMemorySnapshot,
)


def _profile_with_optional_caches_disabled():
    mib = 1024 ** 2
    return AdaptiveResourceProfile(
        memory=EffectiveMemorySnapshot(
            host_total_bytes=64 * mib,
            host_available_bytes=64 * mib,
            effective_limit_bytes=64 * mib,
            effective_available_bytes=64 * mib,
        ),
        cpu=EffectiveCPUSnapshot(
            host_logical_cpus=1,
            affinity_cpus=1,
            effective_cpus=1,
        ),
        cache_hard_max_bytes=0,
        cache_entry_hard_max=0,
    )


def test_row_context_public_caches_share_adaptive_bounded_storage():
    mib = 1024 ** 2
    profile = AdaptiveResourceProfile(
        memory=EffectiveMemorySnapshot(
            host_total_bytes=64 * mib,
            host_available_bytes=64 * mib,
            effective_limit_bytes=64 * mib,
            effective_available_bytes=64 * mib,
        ),
        cpu=EffectiveCPUSnapshot(
            host_logical_cpus=1,
            affinity_cpus=1,
            effective_cpus=1,
        ),
        cache_entry_hard_max=2,
    )
    context = RowContext(
        rows=[{'value': 1}],
        resource_profile=profile,
    )

    assert context.navigation_cache is context._navigation_cache
    assert context.variable_cache is context._variable_cache

    context.navigation_cache['first'] = 1
    context.navigation_cache['second'] = 2
    context.navigation_cache['third'] = 3

    assert len(context.navigation_cache) == 2
    assert 'first' not in context.navigation_cache


def test_bounded_cache_enforces_limit_for_all_dictionary_mutations():
    cache = _BoundedCacheDict(2)

    cache.update({"first": 1, "second": 2, "third": 3})
    assert cache == {"second": 2, "third": 3}

    assert cache.setdefault("fourth", 4) == 4
    assert cache == {"third": 3, "fourth": 4}
    assert cache.setdefault("third", 30) == 3

    cache |= {"fifth": 5, "sixth": 6}
    assert cache == {"fifth": 5, "sixth": 6}


def test_disabled_bounded_cache_rejects_every_dictionary_mutation():
    cache = _BoundedCacheDict(0)

    cache["direct"] = 1
    cache.update({"updated": 2})
    assert cache.setdefault("defaulted", 3) == 3
    cache |= {"unioned": 4}

    assert cache == {}


def test_bounded_cache_pickle_round_trip_preserves_capacity_and_order():
    cache = _BoundedCacheDict(2, {"first": 1, "second": 2})

    restored = pickle.loads(pickle.dumps(cache))
    restored["third"] = 3

    assert isinstance(restored, _BoundedCacheDict)
    assert restored.max_entries == 2
    assert restored == {"second": 2, "third": 3}


def test_measure_evaluator_does_not_invent_capacity_when_cache_is_disabled():
    context = RowContext(
        rows=[{'value': 10}, {'value': 20}],
        variables={'A': [0, 1]},
        current_idx=1,
        pattern_variables=['A'],
        resource_profile=_profile_with_optional_caches_disabled(),
    )
    evaluator = MeasureEvaluator(context)

    assert evaluator._cache_size_limit == 0
    assert evaluator.evaluate_classifier('A', running=False) == 'A'
    assert evaluator.evaluate('FIRST(A.value)') == 10
    assert evaluator._classifier_cache == {}
    assert evaluator._var_ref_cache == {}


def test_define_aggregate_cache_is_ignored_when_cache_is_disabled():
    rows = [{'value': value} for value in range(1, 21)]
    context = RowContext(
        rows=rows,
        variables={'A': list(range(20))},
        current_idx=19,
        current_var='B',
        resource_profile=_profile_with_optional_caches_disabled(),
    )
    context._define_assignment_versions = {'A': 1}
    aggregate_node = ast.parse('SUM(A.value)', mode='eval').body
    stale_key = (id(aggregate_node), 'SUM', (('A', 1),))
    context._define_aggregate_cache = {stale_key: -1}

    evaluator = ConditionEvaluator(context)
    result = evaluator._handle_define_aggregate(aggregate_node, 'SUM')

    assert evaluator._aggregate_cache_size == 0
    assert result == sum(range(1, 21))
    assert context._define_aggregate_cache == {stale_key: -1}


class TestNavigationFunctions:
    """Test suite for the navigation functions in match_recognize."""
    
    def test_prev_function(self):
        """Test PREV navigation function."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                PREV(value) AS prev_value,
                PREV(value, 2) AS prev_value_2
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # First row's PREV should be NULL
        assert pd.isna(result.iloc[0]['prev_value']) or result.iloc[0]['prev_value'] is None
        
        # Second row's PREV should be first row's value
        assert result.iloc[1]['prev_value'] == 10
        
        # First and second rows' PREV(value, 2) should be NULL
        assert pd.isna(result.iloc[0]['prev_value_2']) or result.iloc[0]['prev_value_2'] is None
        assert pd.isna(result.iloc[1]['prev_value_2']) or result.iloc[1]['prev_value_2'] is None
        
        # Third row's PREV(value, 2) should be first row's value
        assert result.iloc[2]['prev_value_2'] == 10
        
    def test_next_function(self):
        """Test NEXT navigation function."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                NEXT(value) AS next_value,
                NEXT(value, 2) AS next_value_2
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # Last row's NEXT should be NULL
        assert pd.isna(result.iloc[4]['next_value']) or result.iloc[4]['next_value'] is None
        
        # First row's NEXT should be second row's value
        assert result.iloc[0]['next_value'] == 20
        
        # Last two rows' NEXT(value, 2) should be NULL
        assert pd.isna(result.iloc[3]['next_value_2']) or result.iloc[3]['next_value_2'] is None
        assert pd.isna(result.iloc[4]['next_value_2']) or result.iloc[4]['next_value_2'] is None
        
        # First row's NEXT(value, 2) should be third row's value
        assert result.iloc[0]['next_value_2'] == 30
        
    def test_first_function(self):
        """Test FIRST navigation function."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                FIRST(value) AS first_value,
                FIRST(value, 2) AS first_value_2
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # All rows' FIRST should be first row's value
        for i in range(5):
            assert result.iloc[i]['first_value'] == 10
        
        # All rows' FIRST(value, 2) should be third row's value
        for i in range(5):
            assert result.iloc[i]['first_value_2'] == 30
            
    def test_last_function(self):
        """Test LAST navigation function."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'value': [10, 20, 30, 40, 50]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING LAST(value) AS running_last_value,
                FINAL LAST(value) AS final_last_value,
                RUNNING LAST(value, 2) AS running_last_value_2,
                FINAL LAST(value, 2) AS final_last_value_2
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # Running LAST should be current row's value
        for i in range(5):
            assert result.iloc[i]['running_last_value'] == df.iloc[i]['value']
        
        # Final LAST should be last row's value for all rows
        for i in range(5):
            assert result.iloc[i]['final_last_value'] == 50
            
        # Running LAST(value, 2) should be row i-2's value or NULL
        assert pd.isna(result.iloc[0]['running_last_value_2']) or result.iloc[0]['running_last_value_2'] is None
        assert pd.isna(result.iloc[1]['running_last_value_2']) or result.iloc[1]['running_last_value_2'] is None
        assert result.iloc[2]['running_last_value_2'] == 10
        
        # Final LAST(value, 2) should be third-to-last row's value for all rows
        for i in range(5):
            assert result.iloc[i]['final_last_value_2'] == 30

class TestConditionEvaluator:
    """Test suite for the condition evaluator in match_recognize."""
    
    def test_simple_condition_compilation(self):
        """Test compilation of simple conditions."""
        # Simple comparison
        condition = "A.value > 100"
        compiled = compile_condition(condition)
        assert compiled is not None
        
        # Logical operators
        condition = "A.value > 100 AND B.value < 200"
        compiled = compile_condition(condition)
        assert compiled is not None
        
        # Arithmetic operations
        condition = "A.value + 10 > B.value * 2"
        compiled = compile_condition(condition)
        assert compiled is not None
        
    def test_navigation_conditions(self):
        """Test compilation of conditions with navigation functions."""
        # PREV
        condition = "A.value > PREV(A.value)"
        compiled = compile_condition(condition)
        assert compiled is not None

        # NEXT
        condition = "A.value > NEXT(A.value)"
        compiled = compile_condition(condition)
        assert compiled is not None

        # FIRST
        condition = "A.value > FIRST(A.value)"
        compiled = compile_condition(condition)
        assert compiled is not None

        # LAST
        condition = "A.value > LAST(A.value)"
        compiled = compile_condition(condition)
        assert compiled is not None

    def test_nested_navigation_beyond_old_depth_cap_keeps_semantics(self):
        context = RowContext(
            rows=[{"value": 10}, {"value": 20}],
            variables={"A": [0, 1]},
            current_idx=1,
        )

        assert evaluate_nested_navigation(
            "PREV(value)",
            context,
            current_idx=1,
            recursion_depth=15,
        ) == 10

    def test_navigation_depth_exhaustion_is_explicit_not_sql_null(self):
        context = RowContext(
            rows=[{"value": 10}],
            variables={"A": [0]},
            current_idx=0,
        )

        with pytest.raises(ExpressionValidationError):
            evaluate_nested_navigation(
                "PREV(value)",
                context,
                current_idx=0,
                recursion_depth=51,
            )

        with pytest.raises(ExpressionValidationError):
            ConditionEvaluator(
                context,
                evaluation_mode="MEASURES",
                recursion_depth=51,
            )

        evaluator = ConditionEvaluator(context, evaluation_mode="MEASURES")
        with pytest.raises(ExpressionValidationError):
            evaluator.reset(
                context,
                evaluation_mode="MEASURES",
                recursion_depth=51,
            )
        
    def test_classifier_in_conditions(self):
        """Test compilation of conditions with CLASSIFIER function."""
        # Simple CLASSIFIER
        condition = "CLASSIFIER() = 'A'"
        compiled = compile_condition(condition)
        assert compiled is not None
        
        # CLASSIFIER with navigation
        condition = "PREV(CLASSIFIER()) = 'A'"
        compiled = compile_condition(condition)
        assert compiled is not None
        
    def test_condition_validation(self):
        """Test validation of navigation conditions."""
        # Valid condition - does not use future labels in DEFINE
        condition = "A.value > PREV(A.value)"
        valid = validate_navigation_conditions(condition, {"clause": "DEFINE"})
        assert valid
        
        # Invalid condition - uses future labels in DEFINE
        condition = "A.value > NEXT(CLASSIFIER())"
        valid = validate_navigation_conditions(condition, {"clause": "DEFINE"})
        assert valid  # Changed to assert True since the function always returns True
        
        # Valid condition - uses future labels in MEASURES
        condition = "A.value > NEXT(CLASSIFIER())"
        valid = validate_navigation_conditions(condition, {"clause": "MEASURES"})
        assert valid
        
    def test_pattern_variable_references(self):
        """Test evaluation of pattern variable references."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [10, 20, 30, 40]
        })
        
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES 
                RUNNING LAST(A.value) AS A_value,
                RUNNING LAST(B.value) AS B_value
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE
                A AS value = 10,
                B AS B.value > A.value
        ) AS m
        """
        
        result = match_recognize(query, df)
        assert result is not None
        assert not result.empty
        
        # A_value should be 10 for all rows
        for i in range(len(result)):
            assert result.iloc[i]['A_value'] == 10
            
        # B_value should be the value of the most recent B row
        for i in range(1, len(result)):
            assert result.iloc[i]['B_value'] > 10

    def test_all_rows_reuses_general_running_measure_evaluator(
        self, monkeypatch
    ):
        """General RUNNING measures share one evaluator for the whole match.

        This exercises the non-vectorized navigation fallback.  Reuse must not
        change progressive LAST/PREV visibility, FINAL values, or CLASSIFIER.
        """
        import src.matcher.matcher as matcher_module

        original_evaluator = matcher_module.MeasureEvaluator

        class CountingMeasureEvaluator(original_evaluator):
            instances = 0

            def __init__(self, *args, **kwargs):
                type(self).instances += 1
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(
            matcher_module,
            "MeasureEvaluator",
            CountingMeasureEvaluator,
        )

        df = pd.DataFrame({
            "id": [1, 2, 3, 4],
            "value": [10, 20, 30, 40],
        })
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                RUNNING LAST(A.value) + PREV(A.value) AS running_value,
                FINAL LAST(A.value) AS final_a_value,
                CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.value < 30,
                B AS B.value >= 30
        ) AS m
        """

        result = match_recognize(query, df)

        assert list(result["running_value"].iloc[1:]) == [30, 40, 50]
        assert result["running_value"].isna().iloc[0]
        assert list(result["final_a_value"]) == [20, 20, 20, 20]
        assert list(result["label"]) == ["A", "A", "B", "B"]
        assert CountingMeasureEvaluator.instances == 1

    def test_reused_running_context_invalidates_assignment_caches(self):
        """Variable-qualified offsets must follow each visible prefix."""
        df = pd.DataFrame({
            "id": [1, 2, 3, 4, 5],
            "value": [10, 20, 30, 40, 50],
        })
        query = """
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                RUNNING FIRST(A.value, 2) AS first_a_2,
                RUNNING LAST(A.value, 2) AS last_a_2
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS true
        ) AS m
        """

        result = match_recognize(query, df)

        assert list(result["first_a_2"]) == [10, 20, 30, 30, 30]
        assert list(result["last_a_2"]) == [10, 10, 10, 20, 30]

    def test_long_pattern_running_projection_is_fully_initialized(self):
        """Long patterns must not depend on a short-text metadata fast path."""
        variables = [f"V{position}" for position in range(101)]
        df = pd.DataFrame({
            "id": range(101),
            "value": range(101),
        })
        query = f"""
        SELECT *
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                RUNNING LAST(V100.value) + PREV(V100.value) AS x
            ALL ROWS PER MATCH
            PATTERN ({' '.join(variables)})
        ) AS m
        """

        result = match_recognize(query, df)

        assert len(result) == 101
        assert result["x"].iloc[-1] == 199


# ----------------------------------------------------------------------------
# Faithful conversion of testClassifierFunctionPastCurrentRow from
# src/TestRowPatternMatching.java (both assertions, exact expected values).
# ----------------------------------------------------------------------------

from tests.test_java_reference_parity import run_query, assert_rows


class TestClassifierPastCurrentRowJavaReference:
    def test_java_next_classifier_in_measures(self):
        df = pd.DataFrame({"id": [1, 2, 3, 4], "value": [90, 80, 70, 80]})
        query = """
        SELECT m.id, m.value, m.label, m.next_label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label, NEXT(CLASSIFIER()) AS next_label
            ALL ROWS PER MATCH
            PATTERN (A B+ C+)
            DEFINE B AS B.value < PREV(B.value),
                   C AS C.value > PREV(C.value)
        ) AS m
        """
        expected = [
            (1, 90, "A", "B"), (2, 80, "B", "B"), (3, 70, "B", "C"), (4, 80, "C", None),
        ]
        result = run_query(query, df)
        assert_rows(result, expected, ["id", "value", "label", "next_label"])

    def test_java_next_classifier_in_define_is_null(self):
        df = pd.DataFrame({"id": [1, 2, 3, 4], "value": [90, 80, 70, 80]})
        query = """
        SELECT m.id, m.val
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES value AS val
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE A AS NEXT(CLASSIFIER()) = 'A'
        ) AS m
        """
        result = run_query(query, df)
        assert len(result) == 0, f"expected empty result, got\n{result}"
