#!/usr/bin/env python3
"""
Amazon UK Dataset Coverage Evaluation - Large Sizes (150K-2M)

This script evaluates the match_recognize implementation for LARGE dataset sizes:
- 150,000 rows
- 200,000 rows
- 300,000 rows
- 500,000 rows
- 750,000 rows
- 1,000,000 rows
- 2,000,000 rows (Full dataset)

Total: 7 sizes × 5 patterns = 35 tests
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
            with open(dataset_path, 'r') as f:
                total_lines = sum(1 for line in f) - 1
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
    
    if 'ROWNUM' not in df.columns:
        df['ROWNUM'] = range(len(df))
    
    categorical_columns = df.select_dtypes(include=['object']).columns.tolist()
    numeric_columns = df.select_dtypes(include=['int64', 'float64']).columns.tolist()
    
    print(f"   Categorical columns: {categorical_columns}")
    print(f"   Numeric columns: {numeric_columns}")
    
    if 'category' not in df.columns:
        print(f"   Creating 'category' column for pattern testing...")
        
        if 'price' in df.columns:
            df['category'] = pd.cut(df['price'], 
                                   bins=[-float('inf'), 10, 25, 50, 100, float('inf')], 
                                   labels=['A', 'B', 'C', 'D', 'E'])
        elif 'rating' in df.columns:
            df['category'] = pd.cut(df['rating'], 
                                   bins=[0, 2, 3, 4, 4.5, 5], 
                                   labels=['A', 'B', 'C', 'D', 'E'])
        elif len(numeric_columns) > 0:
            col = numeric_columns[0]
            df['category'] = pd.cut(df[col], 
                                   bins=5, 
                                   labels=['A', 'B', 'C', 'D', 'E'])
        else:
            df['category'] = df.index.map(lambda x: ['A', 'B', 'C', 'D', 'E'][x % 5])
        
        print(f"   ✓ Created 'category' column")
    
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
    
    mem_before = get_memory_usage()
    start_time = time.time()
    
    try:
        result_df = match_recognize(query, df)
        
        execution_time = time.time() - start_time
        mem_after = get_memory_usage()
        mem_used = mem_after - mem_before
        
        num_matches = len(result_df) if result_df is not None and not result_df.empty else 0
        
        total_matched_rows = 0
        if num_matches > 0 and 'match_length' in result_df.columns:
            total_matched_rows = result_df['match_length'].sum()
        elif num_matches > 0 and 'start_row' in result_df.columns and 'end_row' in result_df.columns:
            total_matched_rows = (result_df['end_row'] - result_df['start_row'] + 1).sum()
        else:
            total_matched_rows = num_matches
        
        coverage = (total_matched_rows / len(df)) * 100 if len(df) > 0 else 0
        throughput = len(df) / execution_time if execution_time > 0 else 0
        
        result.update({
            'success': True,
            'execution_time': execution_time,
            'num_matches': num_matches,
            'total_matched_rows': int(total_matched_rows),
            'coverage_percent': coverage,
            'throughput_rows_per_sec': throughput,
            'memory_used_mb': mem_used,
            'result_shape': result_df.shape if result_df is not None else (0, 0)
        })
        
        print(f"\n✅ Pattern executed successfully!")
        print(f"   Execution Time: {execution_time:.3f} seconds")
        print(f"   Number of Matches: {num_matches:,}")
        print(f"   Total Matched Rows: {total_matched_rows:,}")
        print(f"   Coverage: {coverage:.2f}% of dataset")
        print(f"   Throughput: {throughput:,.0f} rows/sec")
        print(f"   Memory Used: {mem_used:.1f} MB")
        
        if num_matches > 0 and result_df is not None:
            print(f"\n   Sample Matches (first 5):")
            print(result_df.head(5).to_string(index=False))
        
    except Exception as e:
        result['error'] = str(e)
        print(f"\n❌ Pattern execution failed: {e}")
        traceback.print_exc()
    
    return result

def run_comprehensive_evaluation(dataset_sizes: List[int] = None):
    """Run comprehensive evaluation across multiple dataset sizes."""
    
    if dataset_sizes is None:
        dataset_sizes = [150000, 200000, 300000, 500000, 750000, 1000000, 2000000]
    
    print(f"\n{'#'*80}")
    print(f"🚀 LARGE SIZE EVALUATION - Amazon UK Dataset")
    print(f"   Testing sizes: {', '.join([f'{s:,}' for s in dataset_sizes])}")
    print(f"   Total tests: {len(dataset_sizes)} sizes × 5 patterns = {len(dataset_sizes) * 5} tests")
    print(f"   ⚠️  This may take 1-2 hours to complete")
    print(f"{'#'*80}\n")
    
    patterns = create_test_patterns()
    all_results = []
    
    for size in dataset_sizes:
        print(f"\n{'#'*80}")
        print(f"📊 Testing with {size:,} rows")
        print(f"{'#'*80}")
        
        df = load_amazon_dataset(sample_size=size)
        if df is None:
            continue
        
        df = prepare_data_for_patterns(df)
        
        for pattern_name, pattern_info in patterns.items():
            result = evaluate_pattern(
                pattern_info['query'],
                df,
                pattern_name,
                pattern_info
            )
            all_results.append(result)
    
    # Generate summary
    print(f"\n\n{'='*80}")
    print(f"📊 EVALUATION SUMMARY - LARGE SIZES")
    print(f"{'='*80}")
    
    successful_results = [r for r in all_results if r['success']]
    failed_results = [r for r in all_results if not r['success']]
    
    print(f"\n✅ Total Tests: {len(all_results)}")
    print(f"   Successful: {len(successful_results)} ({len(successful_results)/len(all_results)*100:.1f}%)")
    print(f"   Failed: {len(failed_results)} ({len(failed_results)/len(all_results)*100:.1f}%)")
    
    if successful_results:
        print(f"\n📈 Performance Metrics:")
        avg_time = sum(r['execution_time'] for r in successful_results) / len(successful_results)
        avg_coverage = sum(r['coverage_percent'] for r in successful_results) / len(successful_results)
        avg_throughput = sum(r['throughput_rows_per_sec'] for r in successful_results) / len(successful_results)
        
        print(f"   Average Execution Time: {avg_time:.3f} seconds")
        print(f"   Average Coverage: {avg_coverage:.2f}%")
        print(f"   Average Throughput: {avg_throughput:,.0f} rows/sec")
        
        print(f"\n📊 Coverage by Pattern:")
        for pattern_name in patterns.keys():
            pattern_results = [r for r in successful_results if r['pattern_name'] == pattern_name]
            if pattern_results:
                avg_cov = sum(r['coverage_percent'] for r in pattern_results) / len(pattern_results)
                min_cov = min(r['coverage_percent'] for r in pattern_results)
                max_cov = max(r['coverage_percent'] for r in pattern_results)
                print(f"   {pattern_name}: {avg_cov:.2f}% avg (min: {min_cov:.2f}%, max: {max_cov:.2f}%)")
        
        print(f"\n📊 Coverage by Dataset Size:")
        for size in dataset_sizes:
            size_results = [r for r in successful_results if r['dataset_size'] == size]
            if size_results:
                avg_cov = sum(r['coverage_percent'] for r in size_results) / len(size_results)
                print(f"   {size:,} rows: {avg_cov:.2f}% average")
        
        print(f"\n⚡ Throughput Analysis:")
        for size in dataset_sizes:
            size_results = [r for r in successful_results if r['dataset_size'] == size]
            if size_results:
                avg_throughput = sum(r['throughput_rows_per_sec'] for r in size_results) / len(size_results)
                print(f"   {size:,} rows: {avg_throughput:,.0f} rows/sec average")
    
    if failed_results:
        print(f"\n❌ Failed Tests:")
        for r in failed_results:
            print(f"   - {r['pattern_name']} @ {r['dataset_size']:,} rows: {r['error']}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"large_sizes_results_{timestamp}.json"
    
    import json
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: {results_file}")
    
    return all_results

def main():
    """Main execution function."""
    
    try:
        print(f"\n{'='*80}")
        print(f"🎯 LARGE SIZE EVALUATION (150K - 2M rows)")
        print(f"   Target sizes: 150K, 200K, 300K, 500K, 750K, 1M, 2M")
        print(f"   Total tests: 35 (7 sizes × 5 patterns)")
        print(f"   ⏱️  Estimated duration: 1-2 hours")
        print(f"{'='*80}\n")
        
        results = run_comprehensive_evaluation(
            dataset_sizes=[150000, 200000, 300000, 500000, 750000, 1000000, 2000000]
        )
        
        print(f"\n🎊 Evaluation completed successfully!")
        print(f"   Total tests run: {len(results)}")
        print(f"   Successful tests: {sum(1 for r in results if r['success'])}")
        
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
