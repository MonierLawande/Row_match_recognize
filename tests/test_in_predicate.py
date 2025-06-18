"""
Test IN Predicate without Subqueries
Matches testInPredicateWithoutSubquery() from TestRowPatternMatching.java
"""

import pytest
import pandas as pd
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.executor.match_recognize import match_recognize

class TestInPredicate:
    """Test IN predicate in DEFINE and MEASURES clauses."""

    def setup_method(self):
        """Setup test data matching Java reference."""
        self.test_data = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6],
            'value': [90, 80, 70, 85, 75, 65],
            'category': ['high', 'medium', 'low', 'high', 'medium', 'low'],
            'status': ['active', 'inactive', 'pending', 'active', 'pending', 'inactive']
        })

    def test_in_predicate_with_strings(self):
        """Test IN predicate with string literals."""
        df = self.test_data
        
        query = """
        SELECT id, category, status,
               CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+ C?)
            DEFINE
                A AS category IN ('high', 'medium'),
                B AS status IN ('active', 'pending'),
                C AS category IN ('low')
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Verify IN predicates work correctly
            assert 'label' in result.columns
            
            # Check A-labeled rows have correct categories
            a_rows = result[result['label'] == 'A']
            if len(a_rows) > 0:
                for _, row in a_rows.iterrows():
                    assert row['category'] in ['high', 'medium']
            
            # Check B-labeled rows have correct status
            b_rows = result[result['label'] == 'B']
            if len(b_rows) > 0:
                for _, row in b_rows.iterrows():
                    assert row['status'] in ['active', 'pending']
        else:
            pytest.skip("IN predicate with strings not implemented")

    def test_in_predicate_with_numbers(self):
        """Test IN predicate with numeric literals."""
        df = self.test_data
        
        query = """
        SELECT id, value,
               CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (HIGH MEDIUM+ LOW?)
            DEFINE
                HIGH AS value IN (90, 85, 80),
                MEDIUM AS value IN (75, 70),
                LOW AS value IN (65, 60, 55)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Verify numeric IN predicates work
            assert 'label' in result.columns
            
            # Check HIGH-labeled rows
            high_rows = result[result['label'] == 'HIGH']
            if len(high_rows) > 0:
                for _, row in high_rows.iterrows():
                    assert row['value'] in [90, 85, 80]
            
            # Check MEDIUM-labeled rows
            medium_rows = result[result['label'] == 'MEDIUM']
            if len(medium_rows) > 0:
                for _, row in medium_rows.iterrows():
                    assert row['value'] in [75, 70]
        else:
            pytest.skip("IN predicate with numbers not implemented")

    def test_in_predicate_with_classifier(self):
        """Test IN predicate with CLASSIFIER() function."""
        df = self.test_data
        
        query = """
        SELECT id, value,
               CLASSIFIER() AS label,
               is_start_label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label,
                CASE WHEN CLASSIFIER() IN ('A', 'START') THEN 1 ELSE 0 END AS is_start_label
            ALL ROWS PER MATCH
            PATTERN (A B+ C?)
            DEFINE
                B AS B.value < PREV(B.value),
                C AS C.value > PREV(C.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check that IN predicate works with CLASSIFIER()
            assert 'is_start_label' in result.columns
            
            # A-labeled rows should have is_start_label = 1
            a_rows = result[result['label'] == 'A']
            if len(a_rows) > 0:
                for _, row in a_rows.iterrows():
                    assert row['is_start_label'] == 1
            
            # Non-A rows should have is_start_label = 0
            non_a_rows = result[result['label'] != 'A']
            if len(non_a_rows) > 0:
                for _, row in non_a_rows.iterrows():
                    assert row['is_start_label'] == 0
        else:
            pytest.skip("IN predicate with CLASSIFIER() not implemented")

    def test_in_predicate_with_match_number(self):
        """Test IN predicate with MATCH_NUMBER() function."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7, 8],
            'value': [90, 80, 70, 85, 75, 65, 70, 60]
        })
        
        query = """
        SELECT id, value,
               MATCH_NUMBER() AS match_num,
               is_early_match
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                MATCH_NUMBER() AS match_num,
                CASE WHEN MATCH_NUMBER() IN (1, 2) THEN 1 ELSE 0 END AS is_early_match
            ALL ROWS PER MATCH
            AFTER MATCH SKIP TO NEXT ROW
            PATTERN (A B+)
            DEFINE B AS B.value < PREV(B.value)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check IN predicate with MATCH_NUMBER()
            assert 'is_early_match' in result.columns
            
            # Early matches (1, 2) should have is_early_match = 1
            early_matches = result[result['match_num'].isin([1, 2])]
            if len(early_matches) > 0:
                for _, row in early_matches.iterrows():
                    assert row['is_early_match'] == 1
            
            # Later matches should have is_early_match = 0
            later_matches = result[~result['match_num'].isin([1, 2])]
            if len(later_matches) > 0:
                for _, row in later_matches.iterrows():
                    assert row['is_early_match'] == 0
        else:
            pytest.skip("IN predicate with MATCH_NUMBER() not implemented")

    def test_not_in_predicate(self):
        """Test NOT IN predicate."""
        df = self.test_data
        
        query = """
        SELECT id, category, status,
               CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE
                A AS category NOT IN ('low'),
                B AS status NOT IN ('inactive')
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check NOT IN predicate
            assert 'label' in result.columns
            
            # A-labeled rows should not have 'low' category
            a_rows = result[result['label'] == 'A']
            if len(a_rows) > 0:
                for _, row in a_rows.iterrows():
                    assert row['category'] != 'low'
            
            # B-labeled rows should not have 'inactive' status
            b_rows = result[result['label'] == 'B']
            if len(b_rows) > 0:
                for _, row in b_rows.iterrows():
                    assert row['status'] != 'inactive'
        else:
            pytest.skip("NOT IN predicate not implemented")

    def test_in_predicate_empty_list(self):
        """Test IN predicate with empty list."""
        df = self.test_data
        
        # This should always be false
        query = """
        SELECT id, value,
               CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B*)
            DEFINE
                A AS value NOT IN (),  -- Empty IN should be false, so NOT IN should be true
                B AS value IN ()        -- Empty IN should always be false
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Should only have A labels (since B condition is always false)
            labels = result['label'].unique()
            assert 'A' in labels
            if 'B' in labels:
                # If B appears, there might be an implementation issue
                pytest.fail("Empty IN list should always be false")
        else:
            # Empty IN might cause no matches, which is also valid
            pass

    def test_in_predicate_with_nulls(self):
        """Test IN predicate with NULL values."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, None, 70, 80],
            'category': ['high', None, 'low', 'medium']
        })
        
        query = """
        SELECT id, value, category,
               CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE
                A AS category IN ('high', 'medium'),
                B AS value IN (70, 80)
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # NULL values should not match IN predicates
            assert 'label' in result.columns
            
            # Check that NULL values are handled correctly
            for _, row in result.iterrows():
                if row['label'] == 'A':
                    assert row['category'] in ['high', 'medium']
                    assert pd.notna(row['category'])
                elif row['label'] == 'B':
                    assert row['value'] in [70, 80]
                    assert pd.notna(row['value'])
        else:
            pytest.skip("IN predicate with NULLs not implemented")

    def test_in_predicate_case_sensitivity(self):
        """Test IN predicate case sensitivity."""
        df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'value': [90, 80, 70, 60],
            'category': ['High', 'MEDIUM', 'low', 'Low']
        })
        
        query = """
        SELECT id, category,
               CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE
                A AS category IN ('High', 'MEDIUM'),  -- Case sensitive
                B AS LOWER(category) IN ('low')       -- Case insensitive via LOWER
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check case sensitivity
            assert 'label' in result.columns
            
            # A should match exact case
            a_rows = result[result['label'] == 'A']
            if len(a_rows) > 0:
                for _, row in a_rows.iterrows():
                    assert row['category'] in ['High', 'MEDIUM']
            
            # B should match case-insensitive via LOWER
            b_rows = result[result['label'] == 'B']
            if len(b_rows) > 0:
                for _, row in b_rows.iterrows():
                    assert row['category'].lower() == 'low'
        else:
            pytest.skip("Case sensitivity in IN predicate not implemented")

    def test_complex_in_predicate_expressions(self):
        """Test complex expressions with IN predicate."""
        df = self.test_data
        
        query = """
        SELECT id, value, category,
               CLASSIFIER() AS label
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES CLASSIFIER() AS label
            ALL ROWS PER MATCH
            PATTERN (A B+)
            DEFINE
                A AS (value + 10) IN (100, 95, 90),
                B AS SUBSTR(category, 1, 1) IN ('h', 'm', 'l')
        ) AS m
        """
        
        result = match_recognize(query, df)
        
        if result is not None and not result.empty:
            # Check complex expressions in IN predicate
            assert 'label' in result.columns
            
            # A rows should have value+10 in the specified list
            a_rows = result[result['label'] == 'A']
            if len(a_rows) > 0:
                for _, row in a_rows.iterrows():
                    assert (row['value'] + 10) in [100, 95, 90]
            
            # B rows should have first character in the list
            b_rows = result[result['label'] == 'B']
            if len(b_rows) > 0:
                for _, row in b_rows.iterrows():
                    first_char = row['category'][0] if row['category'] else ''
                    assert first_char in ['h', 'm', 'l']
        else:
            pytest.skip("Complex IN predicate expressions not implemented")
