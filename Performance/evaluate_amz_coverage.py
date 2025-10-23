#!/usr/bin/env python3
"""
Amazon UK Dataset Coverage Evaluation

This script evaluates the match_recognize implementation using the amz_uk_processed_data
dataset to determine:
1. Whether the implementation is working correctly
2. How many rows can be covered/matched by different patterns
3. Performance metrics for the real-world dataset
"""

import time
import pandas as pd
import sys
import os
import psutil
from typing import Dict, Any, List
import traceback
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def get_memory_usage():
    """Get current memory usage in MB."""
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024

def load_amazon_dataset(sample_size: int = None) -> pd.DataFrame:
    """Load Amazon UK dataset with optional sampling."""
    
    dataset_path = "amz_uk_processed_data.csv"
    
    if not os.path.exists(dataset_path):
        print(f"❌ Dataset not found: {dataset_path}")
        return None
    
    print(f"📊 Loading Amazon UK dataset...")
    
    try:
        if sample_size:
            df = pd.read_csv(dataset_path, nrows=sample_size)
            print(f"✅ Loaded {len(df):,} rows (sampled from dataset)")
        else:
            # First check the size
            with open(dataset_path, 'r') as f:
                total_lines = sum(1 for line in f) - 1  # Subtract header
            print(f"📏 Total dataset size: {total_lines:,} rows")
            
            df = pd.read_csv(dataset_path)
            print(f"✅ Loaded full dataset: {len(df):,} rows")
        
        print(f"   Columns: {', '.join(df.columns.tolist())}")
        print(f"   Memory usage: {df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")
        print(f"   Data types:")
        for col in df.columns:
            print(f"      {col}: {df[col].dtype}")
        
        return df
        
    except Exception as e:
        print(f"❌ Error loading dataset: {e}")
        traceback.print_exc()
        return None

def prepare_data_for_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare the dataset for pattern matching by adding necessary columns."""
    
    print(f"\n🔧 Preparing data for pattern matching...")
    
    # Add ROWNUM for ordering
    if 'ROWNUM' not in df.columns:
        df['ROWNUM'] = range(len(df))
    
    # Analyze available columns
    categorical_columns = df.select_dtypes(include=['object']).columns.tolist()
    numeric_columns = df.select_dtypes(include=['int64', 'float64']).columns.tolist()
    
    print(f"   Categorical columns: {categorical_columns}")
    print(f"   Numeric columns: {numeric_columns}")
    
    # Create category column for pattern matching if needed
    if 'category' not in df.columns:
        print(f"   Creating 'category' column for pattern testing...")
        
        # Try to use price or rating columns if available
        if 'price' in df.columns:
            # Create categories based on price ranges
            df['category'] = pd.cut(df['price'], 
                                   bins=[-float('inf'), 10, 25, 50, 100, float('inf')], 
                                   labels=['A', 'B', 'C', 'D', 'E'])
        elif 'rating' in df.columns:
            # Create categories based on rating
            df['category'] = pd.cut(df['rating'], 
                                   bins=[0, 2, 3, 4, 4.5, 5], 
                                   labels=['A', 'B', 'C', 'D', 'E'])
        elif len(numeric_columns) > 0:
            # Use first numeric column
            col = numeric_columns[0]
            df['category'] = pd.cut(df[col], 
                                   bins=5, 
                                   labels=['A', 'B', 'C', 'D', 'E'])
        else:
            # Create based on row index
            df['category'] = df.index.map(lambda x: ['A', 'B', 'C', 'D', 'E'][x % 5])
        
        print(f"   ✓ Created 'category' column")
    
    # Show category distribution
    print(f"   Category distribution:")
    print(df['category'].value_counts().to_string())
    
    return df

def create_test_patterns() -> Dict[str, Dict[str, Any]]:
    """Create test patterns with queries for evaluation."""
    
    patterns = {
        'simple_sequence': {
            'pattern': 'A+ B+',
            'description': 'Simple sequence: A followed by B',
            'query': """
                SELECT *
                FROM data
                MATCH_RECOGNIZE (
                    ORDER BY ROWNUM
                    MEASURES 
                        FIRST(A.ROWNUM) as start_row,
                        LAST(B.ROWNUM) as end_row,
                        COUNT(*) as match_length,
                        COUNT(A.*) as a_count,
                        COUNT(B.*) as b_count
                    ONE ROW PER MATCH
                    PATTERN (A+ B+)
                    DEFINE
                        A AS category = 'A',
                        B AS category = 'B'
                )
            """
        },
        'alternation': {
            'pattern': 'A (B|C)+ D',
            'description': 'Alternation: A followed by (B or C) followed by D',
            'query': """
                SELECT *
                FROM data
                MATCH_RECOGNIZE (
                    ORDER BY ROWNUM
                    MEASURES 
                        FIRST(A.ROWNUM) as start_row,
                        LAST(D.ROWNUM) as end_row,
                        COUNT(*) as match_length
                    ONE ROW PER MATCH
                    PATTERN (A (B|C)+ D)
                    DEFINE
                        A AS category = 'A',
                        B AS category = 'B',
                        C AS category = 'C',
                        D AS category = 'D'
                )
            """
        },
        'quantified': {
            'pattern': 'A{2,5} B* C+',
            'description': 'Quantified: 2-5 A\'s, optional B\'s, one or more C\'s',
            'query': """
                SELECT *
                FROM data
                MATCH_RECOGNIZE (
                    ORDER BY ROWNUM
                    MEASURES 
                        FIRST(A.ROWNUM) as start_row,
                        LAST(C.ROWNUM) as end_row,
                        COUNT(*) as match_length,
                        COUNT(A.*) as a_count,
                        COUNT(B.*) as b_count,
                        COUNT(C.*) as c_count
                    ONE ROW PER MATCH
                    PATTERN (A{2,5} B* C+)
                    DEFINE
                        A AS category = 'A',
                        B AS category = 'B',
                        C AS category = 'C'
                )
            """
        },
        'optional_pattern': {
            'pattern': 'A+ B? C*',
            'description': 'Optional patterns: A\'s, optional B, optional C\'s',
            'query': """
                SELECT *
                FROM data
                MATCH_RECOGNIZE (
                    ORDER BY ROWNUM
                    MEASURES 
                        FIRST(A.ROWNUM) as start_row,
                        COUNT(*) as match_length
                    ONE ROW PER MATCH
                    PATTERN (A+ B? C*)
                    DEFINE
                        A AS category = 'A',
                        B AS category = 'B',
                        C AS category = 'C'
                )
            """
        },
        'complex_nested': {
            'pattern': '(A|B)+ (C{1,3} D*)+',
            'description': 'Complex nested: (A or B)+ followed by (1-3 C\'s, optional D\'s)+',
            'query': """
                SELECT *
                FROM data
                MATCH_RECOGNIZE (
                    ORDER BY ROWNUM
                    MEASURES 
                        FIRST(A.ROWNUM) as start_row,
                        COUNT(*) as match_length
                    ONE ROW PER MATCH
                    PATTERN ((A|B)+ (C{1,3} D*)+)
                    DEFINE
                        A AS category = 'A',
                        B AS category = 'B',
                        C AS category = 'C',
                        D AS category = 'D'
                )
            """
        }
    }
    
    return patterns

def evaluate_pattern(query: str, df: pd.DataFrame, pattern_name: str, pattern_info: Dict) -> Dict[str, Any]:
    """Evaluate a single pattern on the dataset."""
    
    from src.executor.match_recognize import match_recognize
    
    print(f"\n{'='*80}")
    print(f"🔍 Testing Pattern: {pattern_name}")
    print(f"   Pattern: {pattern_info['pattern']}")
    print(f"   Description: {pattern_info['description']}")
    print(f"{'='*80}")
    
    result = {
        'pattern_name': pattern_name,
        'pattern': pattern_info['pattern'],
        'description': pattern_info['description'],
        'dataset_size': len(df),
        'success': False,
        'error': None
    }
    
    try:
        # Measure memory and time
        memory_before = get_memory_usage()
        start_time = time.time()
        
        # Execute match_recognize
        matches_df = match_recognize(query, df)
        
        end_time = time.time()
        memory_after = get_memory_usage()
        
        # Calculate metrics
        execution_time = end_time - start_time
        memory_used = memory_after - memory_before
        num_matches = len(matches_df)
        throughput = len(df) / execution_time if execution_time > 0 else 0
        
        # Calculate coverage
        total_matched_rows = 0
        if 'match_length' in matches_df.columns:
            total_matched_rows = matches_df['match_length'].sum()
        elif 'start_row' in matches_df.columns and 'end_row' in matches_df.columns:
            total_matched_rows = (matches_df['end_row'] - matches_df['start_row'] + 1).sum()
        
        coverage_percentage = (total_matched_rows / len(df)) * 100 if len(df) > 0 else 0
        
        # Update result
        result.update({
            'success': True,
            'num_matches': num_matches,
            'total_matched_rows': total_matched_rows,
            'coverage_percentage': coverage_percentage,
            'execution_time_seconds': execution_time,
            'throughput_rows_per_sec': throughput,
            'memory_used_mb': memory_used,
            'result_columns': list(matches_df.columns),
            'sample_results': matches_df.head(5).to_dict('records') if num_matches > 0 else []
        })
        
        # Print results
        print(f"\n✅ Pattern executed successfully!")
        print(f"   Execution Time: {execution_time:.3f} seconds")
        print(f"   Number of Matches: {num_matches:,}")
        print(f"   Total Matched Rows: {total_matched_rows:,}")
        print(f"   Coverage: {coverage_percentage:.2f}% of dataset")
        print(f"   Throughput: {throughput:,.0f} rows/sec")
        print(f"   Memory Used: {memory_used:.1f} MB")
        
        if num_matches > 0:
            print(f"\n   Sample Matches (first 5):")
            print(matches_df.head(5).to_string(index=False))
        else:
            print(f"\n   ⚠️  No matches found")
        
    except Exception as e:
        result['success'] = False
        result['error'] = str(e)
        print(f"\n❌ Error executing pattern: {e}")
        traceback.print_exc()
    
    return result

def run_comprehensive_evaluation(dataset_sizes: List[int] = None):
    """Run comprehensive evaluation on the dataset."""
    
    print("="*80)
    print("🎯 Amazon UK Dataset Coverage Evaluation")
    print("="*80)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Default dataset sizes if not provided
    if dataset_sizes is None:
        dataset_sizes = [1000, 5000, 10000, 25000, 50000, 100000]
    
    # Load full dataset info first
    print("📏 Checking full dataset size...")
    dataset_path = "amz_uk_processed_data.csv"
    if os.path.exists(dataset_path):
        with open(dataset_path, 'r') as f:
            total_lines = sum(1 for line in f) - 1
        print(f"   Total available rows: {total_lines:,}")
        
        # Adjust dataset sizes based on available data
        dataset_sizes = [size for size in dataset_sizes if size <= total_lines]
        if total_lines not in dataset_sizes and total_lines <= 100000:
            dataset_sizes.append(total_lines)
    
    # Get test patterns
    patterns = create_test_patterns()
    
    # Results storage
    all_results = []
    
    # Test each dataset size
    for size in dataset_sizes:
        print(f"\n{'#'*80}")
        print(f"📊 Testing with {size:,} rows")
        print(f"{'#'*80}")
        
        # Load dataset
        df = load_amazon_dataset(sample_size=size)
        if df is None:
            print(f"❌ Could not load dataset, skipping size {size}")
            continue
        
        # Prepare data
        df = prepare_data_for_patterns(df)
        
        # Test each pattern
        for pattern_name, pattern_info in patterns.items():
            result = evaluate_pattern(
                pattern_info['query'],
                df,
                pattern_name,
                pattern_info
            )
            result['dataset_size'] = size
            all_results.append(result)
            
            # Brief pause between patterns
            time.sleep(0.5)
    
    # Generate summary report
    generate_summary_report(all_results)
    
    return all_results

def generate_summary_report(results: List[Dict]):
    """Generate a comprehensive summary report."""
    
    print("\n" + "="*80)
    print("📊 EVALUATION SUMMARY REPORT")
    print("="*80)
    
    # Overall statistics
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r['success'])
    failed_tests = total_tests - successful_tests
    
    print(f"\n🎯 Overall Statistics:")
    print(f"   Total Tests: {total_tests}")
    print(f"   Successful: {successful_tests} ({successful_tests/total_tests*100:.1f}%)")
    print(f"   Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
    
    # Success by pattern
    successful_results = [r for r in results if r['success']]
    
    if successful_results:
        print(f"\n📈 Coverage Analysis:")
        
        # Group by pattern
        by_pattern = {}
        for r in successful_results:
            pattern = r['pattern_name']
            if pattern not in by_pattern:
                by_pattern[pattern] = []
            by_pattern[pattern].append(r)
        
        for pattern, pattern_results in by_pattern.items():
            avg_coverage = sum(r['coverage_percentage'] for r in pattern_results) / len(pattern_results)
            avg_matches = sum(r['num_matches'] for r in pattern_results) / len(pattern_results)
            avg_time = sum(r['execution_time_seconds'] for r in pattern_results) / len(pattern_results)
            
            print(f"\n   Pattern: {pattern}")
            print(f"      Average Coverage: {avg_coverage:.2f}%")
            print(f"      Average Matches: {avg_matches:.0f}")
            print(f"      Average Execution Time: {avg_time:.3f}s")
        
        # Best performing pattern
        best_coverage = max(successful_results, key=lambda x: x['coverage_percentage'])
        print(f"\n🏆 Best Coverage:")
        print(f"   Pattern: {best_coverage['pattern_name']}")
        print(f"   Coverage: {best_coverage['coverage_percentage']:.2f}%")
        print(f"   Matches: {best_coverage['num_matches']:,}")
        print(f"   Dataset Size: {best_coverage['dataset_size']:,} rows")
        
        # Fastest pattern
        fastest = min(successful_results, key=lambda x: x['execution_time_seconds'])
        print(f"\n⚡ Fastest Execution:")
        print(f"   Pattern: {fastest['pattern_name']}")
        print(f"   Time: {fastest['execution_time_seconds']:.3f}s")
        print(f"   Throughput: {fastest['throughput_rows_per_sec']:,.0f} rows/sec")
        
        # Performance trends
        print(f"\n📊 Performance vs Dataset Size:")
        dataset_sizes = sorted(set(r['dataset_size'] for r in successful_results))
        for size in dataset_sizes:
            size_results = [r for r in successful_results if r['dataset_size'] == size]
            avg_time = sum(r['execution_time_seconds'] for r in size_results) / len(size_results)
            avg_throughput = sum(r['throughput_rows_per_sec'] for r in size_results) / len(size_results)
            print(f"   {size:>7,} rows: {avg_time:>7.3f}s | {avg_throughput:>10,.0f} rows/sec")
    
    # Failed patterns
    if failed_tests > 0:
        print(f"\n❌ Failed Tests:")
        failed_results = [r for r in results if not r['success']]
        for r in failed_results:
            print(f"   Pattern: {r['pattern_name']} (Size: {r['dataset_size']:,})")
            print(f"      Error: {r['error']}")
    
    print("\n" + "="*80)
    print(f"✅ Evaluation Complete!")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

def main():
    """Main execution function."""
    
    try:
        # Run comprehensive evaluation with EXTENDED dataset sizes for maximum evidence
        # Testing progression: 1K -> 2.5K -> 5K -> 7.5K -> 10K -> 15K -> 20K -> 25K 
        # -> 35K -> 50K -> 75K -> 100K -> 150K -> 200K -> 300K -> 500K -> 750K -> 1M -> 2M
        # Total: 19 sizes × 5 patterns = 95 tests
        results = run_comprehensive_evaluation(
            dataset_sizes=[
                1000, 2500, 5000, 7500, 10000, 15000, 20000, 25000, 35000, 50000, 
                75000, 100000, 150000, 200000, 300000, 500000, 750000, 1000000, 2000000
            ]
        )
        
        print(f"\n🎊 Evaluation completed successfully!")
        print(f"   Total tests run: {len(results)}")
        print(f"   Successful tests: {sum(1 for r in results if r['success'])}")
        
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
