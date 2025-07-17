#!/usr/bin/env python3
"""
Test script to verify the updated dataset sizes for MATCH_RECOGNIZE performance testing.

This script validates that the new dataset sizes (1K, 2K, 4K, 5K) are correctly
configured and can generate appropriate test data.

Author: Performance Testing Team
Version: 1.0.0
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.performance.test_caching_strategies import (
    DatasetSize, SyntheticDataGenerator, CachingStrategy, PatternComplexity, TestCase
)

def test_dataset_sizes():
    """Test that all dataset sizes are correctly defined and generate appropriate data."""
    print("Testing Dataset Size Configuration")
    print("=" * 50)
    
    expected_sizes = {
        DatasetSize.SIZE_1K: 1000,
        DatasetSize.SIZE_2K: 2000,
        DatasetSize.SIZE_4K: 4000,
        DatasetSize.SIZE_5K: 5000
    }
    
    for dataset_enum, expected_rows in expected_sizes.items():
        print(f"\nTesting {dataset_enum.name}:")
        print(f"  Expected rows: {expected_rows}")
        print(f"  Enum value: {dataset_enum.value}")
        
        # Verify enum value matches expected
        assert dataset_enum.value == expected_rows, f"Enum value mismatch for {dataset_enum.name}"
        
        # Generate test data
        try:
            df = SyntheticDataGenerator.generate_dataset(dataset_enum)
            actual_rows = len(df)
            print(f"  Generated rows: {actual_rows}")
            print(f"  Columns: {list(df.columns)}")
            
            # Verify correct number of rows
            assert actual_rows == expected_rows, f"Generated {actual_rows} rows, expected {expected_rows}"
            
            # Verify required columns exist
            required_columns = ['id', 'timestamp', 'price', 'volume', 'state', 'category', 'value', 'trend']
            for col in required_columns:
                assert col in df.columns, f"Missing required column: {col}"
            
            print(f"  ✅ {dataset_enum.name} validation passed")
            
        except Exception as e:
            print(f"  ❌ {dataset_enum.name} validation failed: {e}")
            return False
    
    return True

def test_test_case_generation():
    """Test that test cases are generated correctly with new dataset sizes."""
    print("\n\nTesting Test Case Generation")
    print("=" * 50)
    
    # Generate all possible test case combinations
    test_cases = []
    for strategy in CachingStrategy:
        for size in DatasetSize:
            for complexity in PatternComplexity:
                test_cases.append(TestCase(strategy, size, complexity))
    
    expected_total = len(CachingStrategy) * len(DatasetSize) * len(PatternComplexity)
    actual_total = len(test_cases)
    
    print(f"Expected test cases: {expected_total}")
    print(f"Generated test cases: {actual_total}")
    print(f"Breakdown: {len(CachingStrategy)} strategies × {len(DatasetSize)} sizes × {len(PatternComplexity)} complexities")
    
    # Verify total count
    assert actual_total == expected_total, f"Expected {expected_total} test cases, got {actual_total}"
    
    # Verify all combinations are present
    strategy_count = {}
    size_count = {}
    complexity_count = {}
    
    for test_case in test_cases:
        strategy = test_case.caching_strategy
        size = test_case.dataset_size
        complexity = test_case.pattern_complexity
        
        strategy_count[strategy] = strategy_count.get(strategy, 0) + 1
        size_count[size] = size_count.get(size, 0) + 1
        complexity_count[complexity] = complexity_count.get(complexity, 0) + 1
    
    print(f"\nStrategy distribution:")
    for strategy, count in strategy_count.items():
        expected_count = len(DatasetSize) * len(PatternComplexity)
        print(f"  {strategy.value}: {count} (expected: {expected_count})")
        assert count == expected_count, f"Strategy {strategy.value} has {count} test cases, expected {expected_count}"
    
    print(f"\nDataset size distribution:")
    for size, count in size_count.items():
        expected_count = len(CachingStrategy) * len(PatternComplexity)
        print(f"  {size.name}: {count} (expected: {expected_count})")
        assert count == expected_count, f"Dataset size {size.name} has {count} test cases, expected {expected_count}"
    
    print(f"\nPattern complexity distribution:")
    for complexity, count in complexity_count.items():
        expected_count = len(CachingStrategy) * len(DatasetSize)
        print(f"  {complexity.value}: {count} (expected: {expected_count})")
        assert count == expected_count, f"Pattern complexity {complexity.value} has {count} test cases, expected {expected_count}"
    
    print(f"\n✅ Test case generation validation passed")
    return True

def test_sample_test_cases():
    """Test a few sample test cases to ensure they work correctly."""
    print("\n\nTesting Sample Test Cases")
    print("=" * 50)
    
    sample_cases = [
        TestCase(CachingStrategy.LRU, DatasetSize.SIZE_1K, PatternComplexity.SIMPLE),
        TestCase(CachingStrategy.FIFO, DatasetSize.SIZE_2K, PatternComplexity.MEDIUM),
        TestCase(CachingStrategy.NO_CACHE, DatasetSize.SIZE_4K, PatternComplexity.COMPLEX),
        TestCase(CachingStrategy.LRU, DatasetSize.SIZE_5K, PatternComplexity.SIMPLE)
    ]
    
    for i, test_case in enumerate(sample_cases, 1):
        print(f"\nSample {i}: {test_case.test_id}")
        print(f"  Strategy: {test_case.caching_strategy.value}")
        print(f"  Dataset Size: {test_case.dataset_size.name} ({test_case.dataset_size.value} rows)")
        print(f"  Pattern Complexity: {test_case.pattern_complexity.value}")
        
        # Verify test_id format
        expected_id = f"{test_case.caching_strategy.value}_{test_case.dataset_size.name}_{test_case.pattern_complexity.value}"
        assert test_case.test_id == expected_id, f"Test ID mismatch: {test_case.test_id} != {expected_id}"
        
        print(f"  ✅ Sample test case {i} validation passed")
    
    return True

def main():
    """Main function to run all validation tests."""
    print("MATCH_RECOGNIZE Performance Testing - Dataset Size Validation")
    print("=" * 80)
    
    try:
        # Test dataset sizes
        if not test_dataset_sizes():
            print("\n❌ Dataset size validation failed")
            return 1
        
        # Test test case generation
        if not test_test_case_generation():
            print("\n❌ Test case generation validation failed")
            return 1
        
        # Test sample test cases
        if not test_sample_test_cases():
            print("\n❌ Sample test case validation failed")
            return 1
        
        print("\n" + "=" * 80)
        print("✅ All validations passed successfully!")
        print("\nDataset Size Summary:")
        print("  - SIZE_1K: 1,000 rows")
        print("  - SIZE_2K: 2,000 rows") 
        print("  - SIZE_4K: 4,000 rows")
        print("  - SIZE_5K: 5,000 rows")
        print(f"\nTotal test combinations: {len(CachingStrategy)} × {len(DatasetSize)} × {len(PatternComplexity)} = {len(CachingStrategy) * len(DatasetSize) * len(PatternComplexity)}")
        print("=" * 80)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
