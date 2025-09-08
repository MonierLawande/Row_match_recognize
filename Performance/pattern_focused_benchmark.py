#!/usr/bin/env python3
"""
Pattern-Focused Performance Analysis
Tests each pattern type (Simple, Medium, Complex) individually across all dataset sizes
Focus: Time & Memory scaling per pattern complexity
"""

import pandas as pd
import numpy as np
import time
import psutil
import os
import json
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from typing import Dict, List, Any
import warnings
warnings.filterwarnings('ignore')

# Import our implementation
import sys
sys.path.append('/home/monierashraf/Desktop/llm/Row_match_recognize')
from src.executor.match_recognize import match_recognize

class PatternFocusedBenchmark:
    """
    Individual Pattern Performance Analysis
    Tests each pattern across all dataset sizes separately
    """
    
    def __init__(self, output_dir: str = "."):
        self.output_dir = output_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Dataset sizes to test
        self.dataset_sizes = [1000, 5000, 10000, 50000, 100000]  # 1K to 100K
        
        # Individual pattern definitions with TRULY different complexities
        self.pattern_definitions = {
            'Simple_Single_Condition': {
                'description': 'Single condition match - basic price threshold',
                'complexity_level': 1,
                'sql_query': '''
                    SELECT * FROM products 
                    MATCH_RECOGNIZE (
                        PARTITION BY categoryName 
                        ORDER BY price
                        MEASURES 
                            A.price AS high_price_item
                        ONE ROW PER MATCH
                        PATTERN (A)
                        DEFINE 
                            A AS price > 100
                    )
                ''',
                'expected_performance': 'Fastest - single condition, single row match'
            },
            
            'Medium_Sequential_Pattern': {
                'description': 'Sequential multi-step pattern - price rise then fall',
                'complexity_level': 2,
                'sql_query': '''
                    SELECT * FROM products
                    MATCH_RECOGNIZE (
                        PARTITION BY categoryName 
                        ORDER BY price
                        MEASURES 
                            FIRST(A.price) AS start_price,
                            LAST(B.price) AS peak_price,
                            LAST(C.price) AS end_price,
                            COUNT(*) AS pattern_length
                        ONE ROW PER MATCH
                        PATTERN (A B+ C)
                        DEFINE 
                            A AS price > 20,
                            B AS price > PREV(price),
                            C AS price < PREV(price)
                    )
                ''',
                'expected_performance': 'Moderate - 3-step pattern with quantifier'
            },
            
            'Complex_Multi_Criteria_Pattern': {
                'description': 'Complex pattern with multiple variables and conditions',
                'complexity_level': 3,
                'sql_query': '''
                    SELECT * FROM products
                    MATCH_RECOGNIZE (
                        PARTITION BY categoryName 
                        ORDER BY boughtInLastMonth, price, stars
                        MEASURES 
                            FIRST(A.boughtInLastMonth) AS start_sales,
                            LAST(D.boughtInLastMonth) AS peak_sales,
                            COUNT(B.*) AS growth_phases,
                            COUNT(C.*) AS stability_phases,
                            AVG(A.price) AS avg_entry_price,
                            MAX(D.stars) AS peak_rating
                        ONE ROW PER MATCH
                        PATTERN (A B+ C* D)
                        DEFINE 
                            A AS boughtInLastMonth > 500 AND stars >= 3.0,
                            B AS boughtInLastMonth > PREV(boughtInLastMonth) AND price <= PREV(price) * 1.1,
                            C AS boughtInLastMonth >= PREV(boughtInLastMonth) * 0.9 AND stars >= PREV(stars),
                            D AS boughtInLastMonth > FIRST(A.boughtInLastMonth) * 2 AND stars > 4.0
                    )
                ''',
                'expected_performance': 'Slowest - complex 4-step pattern with multiple quantifiers'
            }
        }
        
        print(f"🎯 Pattern-Focused Performance Benchmark")
        print(f"📊 Focus: Individual pattern performance analysis")
        print(f"📈 Dataset Sizes: {[f'{s//1000}K' for s in self.dataset_sizes]} rows")
        print(f"🔍 Patterns: {len(self.pattern_definitions)} different complexities")
        
    def load_dataset(self) -> pd.DataFrame:
        """Load Amazon UK dataset"""
        dataset_path = os.path.join(self.output_dir, "amz_uk_processed_data.csv")
        
        if os.path.exists(dataset_path):
            df = pd.read_csv(dataset_path)
            print(f"✅ Loaded {len(df):,} records from Amazon UK dataset")
            return df
        else:
            print(f"❌ Dataset not found, creating synthetic test data...")
            return self.create_synthetic_data()
    
    def create_synthetic_data(self) -> pd.DataFrame:
        """Create synthetic dataset with realistic patterns"""
        print(f"🏗️ Creating synthetic dataset...")
        
        np.random.seed(42)  # Reproducible results
        
        categories = ['Electronics', 'Books', 'Clothing', 'Home', 'Sports', 'Beauty', 'Toys', 'Auto']
        
        data = []
        for i in range(110000):  # Enough for largest test
            category = np.random.choice(categories)
            
            # Create realistic price patterns
            base_price = np.random.uniform(20, 500)
            price_variation = np.random.uniform(0.8, 1.2)
            price = base_price * price_variation
            
            # Create realistic rating patterns  
            quality = np.random.beta(2, 1)  # Skew toward higher ratings
            stars = 1 + (quality * 4)  # 1-5 star range
            reviews = max(0, int(np.random.exponential(200 * quality)))
            
            # Create realistic sales patterns
            popularity = np.random.gamma(2, 500)  # Sales momentum
            bought_last_month = max(0, int(popularity))
            
            data.append({
                'price': round(price, 2),
                'stars': round(stars, 1),
                'reviews': reviews,
                'boughtInLastMonth': bought_last_month,
                'categoryName': category
            })
        
        df = pd.DataFrame(data)
        print(f"✅ Created {len(df):,} synthetic records")
        return df
    
    def run_pattern_benchmark(self, data: pd.DataFrame, pattern_name: str, size: int) -> Dict[str, Any]:
        """Run benchmark for specific pattern and size"""
        pattern_config = self.pattern_definitions[pattern_name]
        
        print(f"    🔍 {pattern_name} ({size:,} rows)...", end=" ")
        
        # Sample data for this test
        test_data = data.sample(n=min(size, len(data)), random_state=42).reset_index(drop=True)
        
        # Memory baseline measurement
        process = psutil.Process()
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        try:
            # Execute benchmark
            start_time = time.time()
            
            # Run our MATCH_RECOGNIZE implementation
            result_df = match_recognize(pattern_config['sql_query'], test_data)
            
            # Measure execution metrics
            execution_time = time.time() - start_time
            peak_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_used = max(0, peak_memory - baseline_memory)
            
            # Calculate performance metrics
            matches_found = len(result_df) if result_df is not None else 0
            throughput = size / execution_time if execution_time > 0 else 0
            memory_per_1k = memory_used / (size / 1000) if size > 0 else 0
            latency_per_1k = (execution_time * 1000) / (size / 1000) if size > 0 else 0
            
            print(f"✅ {execution_time:.3f}s | {memory_used:.2f}MB | {throughput:,.0f} rows/sec")
            
            return {
                'pattern_name': pattern_name,
                'pattern_description': pattern_config['description'],
                'complexity_level': pattern_config['complexity_level'],
                'dataset_size': size,
                'execution_time_seconds': execution_time,
                'memory_used_mb': memory_used,
                'matches_found': matches_found,
                'throughput_rows_per_sec': throughput,
                'memory_per_1k_rows': memory_per_1k,
                'latency_per_1k_ms': latency_per_1k,
                'success': True,
                'error': None
            }
            
        except Exception as e:
            print(f"❌ FAILED: {str(e)[:50]}...")
            return {
                'pattern_name': pattern_name,
                'pattern_description': pattern_config['description'],
                'complexity_level': pattern_config['complexity_level'],
                'dataset_size': size,
                'execution_time_seconds': 0,
                'memory_used_mb': 0,
                'matches_found': 0,
                'throughput_rows_per_sec': 0,
                'memory_per_1k_rows': 0,
                'latency_per_1k_ms': 0,
                'success': False,
                'error': str(e)
            }
    
    def run_comprehensive_pattern_analysis(self):
        """Run comprehensive analysis for each pattern across all sizes"""
        print(f"\n🚀 Starting Pattern-Focused Performance Analysis...")
        
        # Load dataset
        full_dataset = self.load_dataset()
        
        all_results = []
        
        # Test each pattern individually across all sizes
        for pattern_name, pattern_config in self.pattern_definitions.items():
            print(f"\n📊 TESTING PATTERN: {pattern_name}")
            print(f"📋 Description: {pattern_config['description']}")
            print(f"🎯 Complexity Level: {pattern_config['complexity_level']}")
            print("-" * 60)
            
            pattern_results = []
            
            for size in self.dataset_sizes:
                result = self.run_pattern_benchmark(full_dataset, pattern_name, size)
                result['test_timestamp'] = datetime.now().isoformat()
                
                all_results.append(result)
                pattern_results.append(result)
            
            # Quick pattern summary
            successful_results = [r for r in pattern_results if r['success']]
            if successful_results:
                avg_throughput = np.mean([r['throughput_rows_per_sec'] for r in successful_results])
                avg_memory = np.mean([r['memory_used_mb'] for r in successful_results])
                print(f"    📈 Pattern Summary: {avg_throughput:,.0f} avg rows/sec, {avg_memory:.2f} avg MB")
            else:
                print(f"    ❌ Pattern failed all tests")
        
        # Generate comprehensive analysis
        self.save_detailed_results(all_results)
        self.generate_pattern_report(all_results)
        self.create_pattern_visualizations(all_results)
        
        print(f"\n🎯 Pattern-Focused Analysis Complete!")
        return all_results
    
    def save_detailed_results(self, results: List[Dict]):
        """Save detailed results to files"""
        # JSON with full details
        json_file = os.path.join(self.output_dir, f"pattern_focused_analysis_{self.timestamp}.json")
        
        # Calculate metadata
        successful_results = [r for r in results if r['success']]
        
        analysis_data = {
            'metadata': {
                'analysis_type': 'Pattern-Focused Performance Analysis',
                'timestamp': self.timestamp,
                'total_tests': len(results),
                'successful_tests': len(successful_results),
                'success_rate_percent': (len(successful_results) / len(results)) * 100,
                'dataset_sizes_tested': self.dataset_sizes,
                'patterns_tested': list(self.pattern_definitions.keys())
            },
            'pattern_definitions': self.pattern_definitions,
            'detailed_results': results
        }
        
        with open(json_file, 'w') as f:
            json.dump(analysis_data, f, indent=2)
        
        # CSV for easy analysis
        csv_file = os.path.join(self.output_dir, f"pattern_focused_analysis_{self.timestamp}.csv")
        df_results = pd.DataFrame(results)
        df_results.to_csv(csv_file, index=False)
        
        print(f"💾 Detailed results saved:")
        print(f"    📄 JSON: {json_file}")
        print(f"    📊 CSV: {csv_file}")
    
    def generate_pattern_report(self, results: List[Dict]):
        """Generate comprehensive pattern analysis report"""
        successful_results = [r for r in results if r['success']]
        
        if not successful_results:
            print("❌ No successful tests to analyze")
            return
        
        report_file = os.path.join(self.output_dir, f"PATTERN_ANALYSIS_REPORT_{self.timestamp}.md")
        
        with open(report_file, 'w') as f:
            f.write("# 📊 Pattern-Focused Performance Analysis Report\\n\\n")
            f.write(f"**Analysis Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")
            f.write(f"**Dataset:** Amazon UK processed data\\n")
            f.write(f"**Focus:** Individual pattern performance across dataset sizes\\n")
            f.write(f"**Success Rate:** {len(successful_results)}/{len(results)} ({len(successful_results)/len(results)*100:.1f}%)\\n\\n")
            
            # Overall summary
            overall_avg_time = np.mean([r['execution_time_seconds'] for r in successful_results])
            overall_avg_memory = np.mean([r['memory_used_mb'] for r in successful_results])
            overall_avg_throughput = np.mean([r['throughput_rows_per_sec'] for r in successful_results])
            
            f.write("## 🎯 Overall Performance Summary\\n\\n")
            f.write(f"- **Average Execution Time:** {overall_avg_time:.3f} seconds\\n")
            f.write(f"- **Average Memory Usage:** {overall_avg_memory:.2f} MB\\n")
            f.write(f"- **Average Throughput:** {overall_avg_throughput:,.0f} rows/second\\n\\n")
            
            # Individual pattern analysis
            f.write("## 📈 Individual Pattern Performance\\n\\n")
            
            for pattern_name in self.pattern_definitions.keys():
                pattern_results = [r for r in successful_results if r['pattern_name'] == pattern_name]
                
                if pattern_results:
                    f.write(f"### 🔍 {pattern_name}\\n\\n")
                    f.write(f"**Description:** {pattern_results[0]['pattern_description']}\\n")
                    f.write(f"**Complexity Level:** {pattern_results[0]['complexity_level']}\\n\\n")
                    
                    # Pattern performance table
                    f.write("| Dataset Size | Time (s) | Memory (MB) | Throughput (rows/sec) | Memory/1K (MB) | Matches |\\n")
                    f.write("|--------------|----------|-------------|----------------------|----------------|---------|\\n")
                    
                    for size in self.dataset_sizes:
                        size_result = next((r for r in pattern_results if r['dataset_size'] == size), None)
                        if size_result:
                            f.write(f"| **{size//1000}K rows** | {size_result['execution_time_seconds']:.3f} | "
                                   f"{size_result['memory_used_mb']:.2f} | {size_result['throughput_rows_per_sec']:,.0f} | "
                                   f"{size_result['memory_per_1k_rows']:.3f} | {size_result['matches_found']} |\\n")
                    
                    # Pattern summary metrics
                    pattern_avg_time = np.mean([r['execution_time_seconds'] for r in pattern_results])
                    pattern_avg_memory = np.mean([r['memory_used_mb'] for r in pattern_results])
                    pattern_avg_throughput = np.mean([r['throughput_rows_per_sec'] for r in pattern_results])
                    
                    f.write(f"\\n**Pattern Averages:**\\n")
                    f.write(f"- Time: {pattern_avg_time:.3f}s | Memory: {pattern_avg_memory:.2f}MB | Throughput: {pattern_avg_throughput:,.0f} rows/sec\\n\\n")
            
            # Scaling analysis
            f.write("## 📊 Scaling Analysis\\n\\n")
            f.write("| Pattern | 1K→100K Scaling | Memory Efficiency | Performance Trend |\\n")
            f.write("|---------|-----------------|-------------------|--------------------|\\n")
            
            for pattern_name in self.pattern_definitions.keys():
                pattern_results = [r for r in successful_results if r['pattern_name'] == pattern_name]
                
                if len(pattern_results) >= 2:
                    # Get first and last size results
                    first_size_result = next((r for r in pattern_results if r['dataset_size'] == min(self.dataset_sizes)), None)
                    last_size_result = next((r for r in pattern_results if r['dataset_size'] == max(self.dataset_sizes)), None)
                    
                    if first_size_result and last_size_result:
                        scaling_factor = last_size_result['throughput_rows_per_sec'] / first_size_result['throughput_rows_per_sec']
                        memory_efficiency = np.mean([r['memory_per_1k_rows'] for r in pattern_results])
                        
                        trend = "📈 Improving" if scaling_factor > 1.5 else "➡️ Stable" if scaling_factor > 0.8 else "📉 Declining"
                        
                        f.write(f"| **{pattern_name}** | {scaling_factor:.1f}x | {memory_efficiency:.3f} MB/1K | {trend} |\\n")
            
            f.write("\\n## ✅ Conclusions\\n\\n")
            f.write("This analysis tested each pattern individually across all dataset sizes to understand ")
            f.write("scaling characteristics and performance profiles for different complexity levels.\\n")
        
        print(f"📋 Pattern analysis report: {report_file}")
    
    def create_pattern_visualizations(self, results: List[Dict]):
        """Create pattern-focused visualizations"""
        successful_results = [r for r in results if r['success']]
        
        if not successful_results:
            print("❌ No data for visualizations")
            return
        
        df = pd.DataFrame(successful_results)
        
        # Create comprehensive visualization
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('Pattern-Focused Performance Analysis', fontsize=16, fontweight='bold')
        
        # 1. Execution Time by Pattern and Size
        ax1 = axes[0, 0]
        for pattern in df['pattern_name'].unique():
            pattern_data = df[df['pattern_name'] == pattern].sort_values('dataset_size')
            ax1.plot(pattern_data['dataset_size'], pattern_data['execution_time_seconds'], 
                    marker='o', label=pattern.replace('_', ' '), linewidth=2)
        ax1.set_xlabel('Dataset Size (rows)')
        ax1.set_ylabel('Execution Time (seconds)')
        ax1.set_title('Execution Time vs Dataset Size')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. Memory Usage by Pattern and Size
        ax2 = axes[0, 1]
        for pattern in df['pattern_name'].unique():
            pattern_data = df[df['pattern_name'] == pattern].sort_values('dataset_size')
            ax2.plot(pattern_data['dataset_size'], pattern_data['memory_used_mb'],
                    marker='s', label=pattern.replace('_', ' '), linewidth=2)
        ax2.set_xlabel('Dataset Size (rows)')
        ax2.set_ylabel('Memory Usage (MB)')
        ax2.set_title('Memory Usage vs Dataset Size')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 3. Throughput by Pattern
        ax3 = axes[0, 2]
        throughput_by_pattern = df.groupby('pattern_name')['throughput_rows_per_sec'].mean()
        bars = ax3.bar([p.replace('_', '\\n') for p in throughput_by_pattern.index], 
                      throughput_by_pattern.values)
        ax3.set_ylabel('Throughput (rows/sec)')
        ax3.set_title('Average Throughput by Pattern')
        ax3.grid(True, alpha=0.3)
        for bar in bars:
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:,.0f}', ha='center', va='bottom')
        
        # 4. Memory Efficiency by Pattern
        ax4 = axes[1, 0]
        memory_eff_by_pattern = df.groupby('pattern_name')['memory_per_1k_rows'].mean()
        bars = ax4.bar([p.replace('_', '\\n') for p in memory_eff_by_pattern.index], 
                      memory_eff_by_pattern.values, color='orange')
        ax4.set_ylabel('Memory per 1K rows (MB)')
        ax4.set_title('Memory Efficiency by Pattern')
        ax4.grid(True, alpha=0.3)
        for bar in bars:
            height = bar.get_height()
            ax4.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.3f}', ha='center', va='bottom')
        
        # 5. Scaling Performance
        ax5 = axes[1, 1]
        for pattern in df['pattern_name'].unique():
            pattern_data = df[df['pattern_name'] == pattern].sort_values('dataset_size')
            ax5.plot(pattern_data['dataset_size'], pattern_data['throughput_rows_per_sec'],
                    marker='d', label=pattern.replace('_', ' '), linewidth=2)
        ax5.set_xlabel('Dataset Size (rows)')
        ax5.set_ylabel('Throughput (rows/sec)')
        ax5.set_title('Throughput Scaling by Pattern')
        ax5.legend()
        ax5.grid(True, alpha=0.3)
        
        # 6. Performance Heatmap
        ax6 = axes[1, 2]
        pivot_data = df.pivot(index='pattern_name', columns='dataset_size', values='throughput_rows_per_sec')
        sns.heatmap(pivot_data, annot=True, fmt='.0f', cmap='YlOrRd', ax=ax6)
        ax6.set_title('Throughput Heatmap (rows/sec)')
        ax6.set_xlabel('Dataset Size (rows)')
        ax6.set_ylabel('Pattern Type')
        
        plt.tight_layout()
        
        # Save visualization
        viz_file = os.path.join(self.output_dir, f"pattern_analysis_charts_{self.timestamp}.png")
        plt.savefig(viz_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"📊 Pattern visualizations saved: {viz_file}")

if __name__ == "__main__":
    # Run pattern-focused analysis
    analyzer = PatternFocusedBenchmark(".")
    results = analyzer.run_comprehensive_pattern_analysis()
    
    # Final summary
    successful = [r for r in results if r['success']]
    if successful:
        print(f"\\n🎯 FINAL ANALYSIS SUMMARY:")
        print(f"✅ Success Rate: {len(successful)}/{len(results)} ({len(successful)/len(results)*100:.1f}%)")
        
        # Pattern-specific summaries
        for pattern_name in set(r['pattern_name'] for r in successful):
            pattern_results = [r for r in successful if r['pattern_name'] == pattern_name]
            avg_throughput = np.mean([r['throughput_rows_per_sec'] for r in pattern_results])
            avg_memory = np.mean([r['memory_used_mb'] for r in pattern_results])
            print(f"📊 {pattern_name}: {avg_throughput:,.0f} avg rows/sec, {avg_memory:.2f} avg MB")
    else:
        print(f"❌ No successful tests completed!")
