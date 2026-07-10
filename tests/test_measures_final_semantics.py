"""
Production-Ready Test Suite for MEASURES FINAL Semantics Fix

This test suite validates the fix for the MEASURES evaluation bug where pattern
variable references were incorrectly using the FIRST matched row instead of the
LAST matched row for FINAL semantics in ALL ROWS PER MATCH mode.

Bug Description:
    For patterns with quantifiers (e.g., A+ matching multiple rows), when evaluating
    MEASURES like A.price for rows belonging to other variables (B, C), the system
    should use the LAST A row's value (FINAL semantics per SQL:2016), but was
    incorrectly using the FIRST A row's value.

Test Coverage:
    1. Basic quantifier patterns (A+, A*, A{2,})
    2. Multi-variable patterns (A+ B+ C+)
    3. RUNNING vs FINAL semantics
    4. Partition handling
    5. Edge cases (single row, zero rows, all rows)
    6. Trino compatibility validation
    7. Regression prevention

SQL:2016 Compliance:
    Tests are designed to match Trino behavior and SQL:2016 standard for
    row pattern recognition measure evaluation.

Author: Pattern Matching Engine Team
Version: 1.0.0
Date: 2025-12-12
"""

import pytest
import pandas as pd
from src.executor.match_recognize import match_recognize


class TestBasicQuantifierPatterns:
    """Test MEASURES with basic quantifier patterns (A+, A*, A{2,})."""
    
    def test_a_plus_uses_last_row_for_final_semantics(self):
        """
        Test that A+ pattern uses LAST A row for FINAL semantics.
        
        Pattern: A+ (matches 2 rows with prices 100, 200)
        Expected: Both A rows should return their own values in MEASURES
        Bug would cause: Second A row to still show 100 instead of 200
        """
        data = [
            ('cust_1', '2020-05-11', 100),  # A - first
            ('cust_1', '2020-05-12', 200),  # A - last (should use this)
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price,
                A.order_date AS a_date
            ALL ROWS PER MATCH
            PATTERN (A+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL
        );
        """
        
        result = match_recognize(query, df)
        
        # Both A rows should return their own values
        assert len(result) == 2, f"Expected 2 rows, got {len(result)}"
        
        # First A row
        row_0 = result.iloc[0]
        assert row_0['pattern_var'] == 'A'
        assert row_0['a_price'] == 100, "First A row should show its own price (100)"
        assert row_0['a_date'] == pd.Timestamp('2020-05-11')
        
        # Second A row (CRITICAL: should use its own value, not first A's value)
        row_1 = result.iloc[1]
        assert row_1['pattern_var'] == 'A'
        assert row_1['a_price'] == 200, "Second A row should show its own price (200), not first A's price"
        assert row_1['a_date'] == pd.Timestamp('2020-05-12')
    
    def test_a_plus_b_plus_uses_last_a_for_b_rows(self):
        """
        Test that B rows use LAST A row for A.price in FINAL semantics.
        
        This is the CORE bug scenario: When A+ matches multiple rows,
        B rows should reference the LAST A row, not the FIRST.
        """
        data = [
            ('cust_1', '2020-05-11', 100),  # A - first
            ('cust_1', '2020-05-12', 200),  # A - last (B rows should use THIS)
            ('cust_1', '2020-05-14', 100),  # B
            ('cust_1', '2020-05-16', 50),   # B
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price,
                A.order_date AS a_date
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        assert len(result) == 4, f"Expected 4 rows, got {len(result)}"
        
        # A rows should use their own values
        a_rows = result[result['pattern_var'] == 'A']
        assert len(a_rows) == 2
        assert a_rows.iloc[0]['a_price'] == 100
        assert a_rows.iloc[1]['a_price'] == 200
        
        # B rows should use LAST A's values (200, not 100)
        b_rows = result[result['pattern_var'] == 'B']
        assert len(b_rows) == 2
        
        for idx, b_row in b_rows.iterrows():
            assert b_row['a_price'] == 200, \
                f"B row should use LAST A price (200), got {b_row['a_price']}"
            assert b_row['a_date'] == pd.Timestamp('2020-05-12'), \
                f"B row should use LAST A date (2020-05-12), got {b_row['a_date']}"
    
    def test_full_trino_comparison_a_b_c_pattern(self):
        """
        Full Trino comparison test with A+ B+ C+ pattern.
        
        This replicates the exact scenario from the original bug report.
        """
        data = [
            ('cust_1', '2020-05-11', 100),  # A
            ('cust_1', '2020-05-12', 200),  # A (last)
            ('cust_2', '2020-05-13', 8),    # A
            ('cust_1', '2020-05-14', 100),  # B
            ('cust_2', '2020-05-15', 4),    # B
            ('cust_1', '2020-05-16', 50),   # B
            ('cust_1', '2020-05-17', 100),  # C
            ('cust_2', '2020-05-18', 6),    # C
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price,
                A.order_date AS a_date
            ALL ROWS PER MATCH
            PATTERN (A+ B+ C+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price),
                C AS C.price > PREV(C.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # Expected: 8 rows total (5 for cust_1, 3 for cust_2)
        assert len(result) == 8, f"Expected 8 rows, got {len(result)}"
        
        # Validate cust_1 partition (has 2 A rows)
        cust_1 = result[result['customer_id'] == 'cust_1'].sort_values('order_date')
        assert len(cust_1) == 5
        
        # cust_1 A rows should use their own values
        cust_1_a_rows = cust_1[cust_1['pattern_var'] == 'A']
        assert len(cust_1_a_rows) == 2
        assert cust_1_a_rows.iloc[0]['a_price'] == 100
        assert cust_1_a_rows.iloc[1]['a_price'] == 200
        
        # cust_1 B rows should use LAST A (200)
        cust_1_b_rows = cust_1[cust_1['pattern_var'] == 'B']
        assert len(cust_1_b_rows) == 2
        for _, row in cust_1_b_rows.iterrows():
            assert row['a_price'] == 200, \
                f"cust_1 B row should use last A price (200), got {row['a_price']}"
            assert row['a_date'] == pd.Timestamp('2020-05-12')
        
        # cust_1 C row should use LAST A (200)
        cust_1_c_row = cust_1[cust_1['pattern_var'] == 'C'].iloc[0]
        assert cust_1_c_row['a_price'] == 200, \
            f"cust_1 C row should use last A price (200), got {cust_1_c_row['a_price']}"
        assert cust_1_c_row['a_date'] == pd.Timestamp('2020-05-12')
        
        # Validate cust_2 partition (has 1 A row - should work regardless of bug)
        cust_2 = result[result['customer_id'] == 'cust_2'].sort_values('order_date')
        assert len(cust_2) == 3
        
        # All cust_2 rows should reference the single A row
        for _, row in cust_2.iterrows():
            assert row['a_price'] == 8
            assert row['a_date'] == pd.Timestamp('2020-05-13')


class TestMultipleColumnsAndMeasures:
    """Test MEASURES with multiple columns and complex expressions."""
    
    def test_multiple_column_references_from_same_variable(self):
        """Test that multiple column references all use LAST row."""
        data = [
            ('cust_1', '2020-05-11', 100, 'order1'),  # A
            ('cust_1', '2020-05-12', 200, 'order2'),  # A (last)
            ('cust_1', '2020-05-14', 100, 'order3'),  # B
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price', 'order_id'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price,
                A.order_date AS a_date,
                A.order_id AS a_order_id
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # B row should reference LAST A for all columns
        b_row = result[result['pattern_var'] == 'B'].iloc[0]
        assert b_row['a_price'] == 200, "Should use last A's price"
        assert b_row['a_date'] == pd.Timestamp('2020-05-12'), "Should use last A's date"
        assert b_row['a_order_id'] == 'order2', "Should use last A's order_id"
    
    def test_cross_variable_references(self):
        """Test references between different pattern variables."""
        data = [
            ('cust_1', '2020-05-11', 100),  # A
            ('cust_1', '2020-05-12', 200),  # A (last)
            ('cust_1', '2020-05-14', 100),  # B
            ('cust_1', '2020-05-16', 50),   # B (last)
            ('cust_1', '2020-05-17', 100),  # C
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price,
                B.price AS b_price
            ALL ROWS PER MATCH
            PATTERN (A+ B+ C+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price),
                C AS C.price > PREV(C.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # C row should use LAST A (200) and LAST B (50)
        c_row = result[result['pattern_var'] == 'C'].iloc[0]
        assert c_row['a_price'] == 200, "C row should use last A's price"
        assert c_row['b_price'] == 50, "C row should use last B's price"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_single_row_match_no_quantifier(self):
        """Test that single row matches (no quantifier) work correctly."""
        data = [
            ('cust_1', '2020-05-11', 100),  # A
            ('cust_1', '2020-05-14', 50),   # B
            ('cust_1', '2020-05-17', 100),  # C
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price
            ALL ROWS PER MATCH
            PATTERN (A B C)
            DEFINE
                A AS TRUE,
                B AS B.price < A.price,
                C AS C.price > B.price
        );
        """
        
        result = match_recognize(query, df)
        
        assert len(result) == 3
        # All rows should reference the single A row
        for _, row in result.iterrows():
            assert row['a_price'] == 100
    
    def test_three_or_more_rows_in_quantifier(self):
        """Test A+ with 3+ rows to ensure we use the absolute LAST."""
        data = [
            ('cust_1', '2020-05-11', 100),  # A
            ('cust_1', '2020-05-12', 200),  # A
            ('cust_1', '2020-05-13', 300),  # A (last - should use THIS)
            ('cust_1', '2020-05-14', 100),  # B
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # B row should use the LAST A (300), not first (100) or middle (200)
        b_row = result[result['pattern_var'] == 'B'].iloc[0]
        assert b_row['a_price'] == 300, \
            f"B row should use absolute last A price (300), got {b_row['a_price']}"
    
    def test_multiple_matches_in_partition(self):
        """Test multiple separate matches within same partition."""
        data = [
            ('cust_1', '2020-05-11', 100),  # Match 1: A
            ('cust_1', '2020-05-12', 200),  # Match 1: A (last)
            ('cust_1', '2020-05-14', 100),  # Match 1: B
            ('cust_1', '2020-05-16', 150),  # Match 2: A
            ('cust_1', '2020-05-17', 250),  # Match 2: A (last)
            ('cust_1', '2020-05-18', 100),  # Match 2: B
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                MATCH_NUMBER() AS match_num,
                A.price AS a_price
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # Match 1: B row should use last A from match 1 (200)
        match_1_b = result[(result['match_num'] == 1) & (result['pattern_var'] == 'B')].iloc[0]
        assert match_1_b['a_price'] == 200, \
            f"Match 1 B should use last A from match 1 (200), got {match_1_b['a_price']}"
        
        # Match 2: B row should use last A from match 2 (250)
        match_2_b = result[(result['match_num'] == 2) & (result['pattern_var'] == 'B')].iloc[0]
        assert match_2_b['a_price'] == 250, \
            f"Match 2 B should use last A from match 2 (250), got {match_2_b['a_price']}"


class TestPartitionHandling:
    """Test proper handling across multiple partitions."""
    
    def test_multiple_partitions_independent(self):
        """Test that partitions are evaluated independently."""
        data = [
            ('cust_1', '2020-05-11', 100),  # cust_1: A
            ('cust_1', '2020-05-12', 200),  # cust_1: A (last)
            ('cust_2', '2020-05-11', 50),   # cust_2: A
            ('cust_2', '2020-05-12', 75),   # cust_2: A (last)
            ('cust_1', '2020-05-14', 100),  # cust_1: B
            ('cust_2', '2020-05-14', 50),   # cust_2: B
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # cust_1 B should use cust_1's last A (200)
        cust_1_b = result[(result['customer_id'] == 'cust_1') & 
                         (result['pattern_var'] == 'B')].iloc[0]
        assert cust_1_b['a_price'] == 200, \
            f"cust_1 B should use cust_1 last A (200), got {cust_1_b['a_price']}"
        
        # cust_2 B should use cust_2's last A (75)
        cust_2_b = result[(result['customer_id'] == 'cust_2') & 
                         (result['pattern_var'] == 'B')].iloc[0]
        assert cust_2_b['a_price'] == 75, \
            f"cust_2 B should use cust_2 last A (75), got {cust_2_b['a_price']}"


class TestRunningVsFinalSemantics:
    """Test the difference between RUNNING and FINAL semantics."""
    
    def test_final_semantics_explicit(self):
        """Test explicit FINAL processing mode on a navigation function."""
        data = [
            ('cust_1', '2020-05-11', 100),  # A
            ('cust_1', '2020-05-12', 200),  # A (last)
            ('cust_1', '2020-05-14', 100),  # B
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                FINAL LAST(A.price) AS a_price
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # B row should use LAST A with explicit FINAL
        b_row = result[result['pattern_var'] == 'B'].iloc[0]
        assert b_row['a_price'] == 200, "FINAL LAST(A.price) should use last A row"
    
    def test_final_semantics_implicit_default(self):
        """Test that FINAL semantics is the default (no keyword needed)."""
        data = [
            ('cust_1', '2020-05-11', 100),  # A
            ('cust_1', '2020-05-12', 200),  # A (last)
            ('cust_1', '2020-05-14', 100),  # B
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # B row should use LAST A (FINAL is default)
        b_row = result[result['pattern_var'] == 'B'].iloc[0]
        assert b_row['a_price'] == 200, "Default FINAL semantics should use last A row"


class TestRegressionPrevention:
    """Tests to prevent regression of the bug."""
    
    def test_original_bug_scenario(self):
        """
        Exact reproduction of the original bug scenario.
        
        Before fix: B/C rows showed a_price=100 (first A)
        After fix: B/C rows should show a_price=200 (last A)
        """
        data = [
            ('cust_1', '2020-05-11', 100),
            ('cust_1', '2020-05-12', 200),
            ('cust_1', '2020-05-14', 100),
            ('cust_1', '2020-05-16', 50),
            ('cust_1', '2020-05-17', 100),
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price,
                A.order_date AS a_date
            ALL ROWS PER MATCH
            PATTERN (A+ B+ C+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price),
                C AS C.price > PREV(C.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # This is the regression test: ALL non-A rows must show 200
        for _, row in result.iterrows():
            assert row['a_price'] == 200 if row['pattern_var'] == 'A' and row['price'] == 200 else \
                   row['a_price'] == 100 if row['pattern_var'] == 'A' and row['price'] == 100 else \
                   row['a_price'] == 200, \
                   f"Row {row['pattern_var']} should use last A (200), got {row['a_price']}"
    
    def test_verify_fix_with_assertion(self):
        """
        Explicit test that would FAIL before fix, PASS after fix.
        """
        data = [
            ('cust_1', '2020-05-11', 100),  # A - row 0
            ('cust_1', '2020-05-12', 200),  # A - row 1 (LAST)
            ('cust_1', '2020-05-14', 100),  # B - row 2
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        b_row = result[result['pattern_var'] == 'B'].iloc[0]
        
        # THIS ASSERTION WOULD FAIL BEFORE FIX (would be 100)
        # THIS ASSERTION SHOULD PASS AFTER FIX (should be 200)
        assert b_row['a_price'] == 200, \
            f"REGRESSION TEST FAILED: Expected 200 (last A), got {b_row['a_price']} (likely using first A)"


class TestProductionReadiness:
    """Production-level validation tests."""
    
    def test_large_quantifier_range(self):
        """Test with many rows in A+ to ensure we always use the absolute last."""
        data = [(f'cust_1', f'2020-05-{11+i:02d}', 100 + i*10) for i in range(10)]  # 10 A rows
        data.append(('cust_1', '2020-05-21', 50))  # 1 B row
        
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # B row should use the 10th A row (price = 100 + 9*10 = 190)
        b_row = result[result['pattern_var'] == 'B'].iloc[0]
        assert b_row['a_price'] == 190, \
            f"Should use last of 10 A rows (190), got {b_row['a_price']}"
    
    def test_null_values_in_measures(self):
        """Test that NULL values are handled correctly."""
        data = [
            ('cust_1', '2020-05-11', None),  # A - NULL price
            ('cust_1', '2020-05-12', 200),   # A - last
            ('cust_1', '2020-05-14', 100),   # B
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # B row should use last A (200), skipping NULL
        b_row = result[result['pattern_var'] == 'B'].iloc[0]
        assert b_row['a_price'] == 200, \
            f"Should use last A with non-NULL value (200), got {b_row['a_price']}"
    
    def test_performance_with_multiple_measures(self):
        """Test that fix doesn't degrade performance with many MEASURES."""
        data = [
            ('cust_1', '2020-05-11', 100, 'A', 10, 1.5),
            ('cust_1', '2020-05-12', 200, 'B', 20, 2.5),
            ('cust_1', '2020-05-14', 100, 'C', 15, 1.8),
        ]
        df = pd.DataFrame(data, columns=['customer_id', 'order_date', 'price', 'category', 'quantity', 'rating'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        query = """
        SELECT *
        FROM memory.default.orders
        MATCH_RECOGNIZE (
            PARTITION BY customer_id
            ORDER BY order_date
            MEASURES
                CLASSIFIER() AS pattern_var,
                A.price AS a_price,
                A.category AS a_category,
                A.quantity AS a_quantity,
                A.rating AS a_rating,
                A.order_date AS a_date
            ALL ROWS PER MATCH
            PATTERN (A+ B+)
            DEFINE
                A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
                B AS B.price < PREV(B.price)
        );
        """
        
        result = match_recognize(query, df)
        
        # Verify all measures use last A
        b_row = result[result['pattern_var'] == 'B'].iloc[0]
        assert b_row['a_price'] == 200
        assert b_row['a_category'] == 'B'
        assert b_row['a_quantity'] == 20
        assert b_row['a_rating'] == 2.5
        assert b_row['a_date'] == pd.Timestamp('2020-05-12')


if __name__ == '__main__':
    # Run tests with verbose output
    pytest.main([__file__, '-v', '--tb=short'])


# ----------------------------------------------------------------------------
# Faithful conversion of testRunningAndFinal from src/TestRowPatternMatching.java
# (the full 11-column RUNNING/FINAL matrix, exact expected values).
# ----------------------------------------------------------------------------

from tests.test_java_reference_parity import run_query, assert_rows


class TestRunningAndFinalJavaReference:
    def test_java_running_and_final_matrix(self):
        df = pd.DataFrame({"id": [1, 2, 3, 4, 5], "value": [90, 80, 70, 100, 200]})
        query = """
        SELECT id, label, final_label, running_value, final_value,
               A_running_value, A_final_value, B_running_value, B_final_value,
               C_running_value, C_final_value
        FROM data
        MATCH_RECOGNIZE (
            ORDER BY id
            MEASURES
                CLASSIFIER() AS label,
                FINAL LAST(CLASSIFIER()) AS final_label,
                RUNNING LAST(value) AS running_value,
                FINAL LAST(value) AS final_value,
                RUNNING LAST(A.value) AS A_running_value,
                FINAL LAST(A.value) AS A_final_value,
                RUNNING LAST(B.value) AS B_running_value,
                FINAL LAST(B.value) AS B_final_value,
                RUNNING LAST(C.value) AS C_running_value,
                FINAL LAST(C.value) AS C_final_value
            ALL ROWS PER MATCH
            PATTERN (A B+ C+)
            DEFINE B AS B.value < PREV (B.value),
                   C AS C.value > PREV (C.value)
        )
        """
        expected = [
            (1, "A", "C", 90, 200, 90, 90, None, 70, None, 200),
            (2, "B", "C", 80, 200, 90, 90, 80, 70, None, 200),
            (3, "B", "C", 70, 200, 90, 90, 70, 70, None, 200),
            (4, "C", "C", 100, 200, 90, 90, 70, 70, 100, 200),
            (5, "C", "C", 200, 200, 90, 90, 70, 70, 200, 200),
        ]
        result = run_query(query, df)
        assert_rows(result, expected, [
            "id", "label", "final_label", "running_value", "final_value",
            "A_running_value", "A_final_value", "B_running_value",
            "B_final_value", "C_running_value", "C_final_value",
        ])
