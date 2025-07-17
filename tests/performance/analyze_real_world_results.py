#!/usr/bin/env python3
"""
Analyze Real-World Performance Benchmark Results

This script analyzes the practical real-world benchmark results and creates
comprehensive performance comparisons and visualizations.

Author: Performance Testing Team
Version: 1.0.0
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, Any

def convert_numpy_types(obj):
    """Convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    return obj

def analyze_results():
    """Analyze the practical real-world benchmark results."""
    
    # Load results
    results_dir = Path("tests/performance/real_world_results")
    df = pd.read_csv(results_dir / "practical_real_world_results.csv")
    
    print("🔍 REAL-WORLD PERFORMANCE ANALYSIS")
    print("=" * 50)
    print(f"📊 Total test cases analyzed: {len(df)}")
    print(f"📈 Dataset sizes: {sorted(df['dataset_size'].unique())}")
    print(f"🔧 Caching strategies: {list(df['cache_strategy'].unique())}")
    print(f"🎯 Pattern complexities: {list(df['pattern_complexity'].unique())}")
    print(f"📁 Data types: {list(df['data_type'].unique())}")
    
    # Calculate comprehensive summary statistics
    summary_stats = {}
    for strategy in ['NO_CACHE', 'FIFO', 'LRU']:
        strategy_data = df[df['cache_strategy'] == strategy]
        if len(strategy_data) > 0:
            summary_stats[strategy] = {
                'avg_execution_time_ms': float(strategy_data['execution_time_ms'].mean()),
                'median_execution_time_ms': float(strategy_data['execution_time_ms'].median()),
                'std_execution_time_ms': float(strategy_data['execution_time_ms'].std()),
                'min_execution_time_ms': float(strategy_data['execution_time_ms'].min()),
                'max_execution_time_ms': float(strategy_data['execution_time_ms'].max()),
                'avg_memory_usage_mb': float(strategy_data['memory_usage_mb'].mean()),
                'avg_cache_hit_rate': float(strategy_data['cache_hit_rate'].mean()),
                'total_cache_hits': int(strategy_data['cache_hits'].sum()),
                'total_cache_misses': int(strategy_data['cache_misses'].sum()),
                'test_count': int(len(strategy_data)),
                'success_rate': float(strategy_data['execution_success'].mean() * 100),
                'total_matches_found': int(strategy_data['result_count'].sum())
            }
    
    # Calculate performance improvements
    if 'NO_CACHE' in summary_stats:
        baseline_time = summary_stats['NO_CACHE']['avg_execution_time_ms']
        baseline_memory = summary_stats['NO_CACHE']['avg_memory_usage_mb']
        
        for strategy in ['FIFO', 'LRU']:
            if strategy in summary_stats:
                strategy_time = summary_stats[strategy]['avg_execution_time_ms']
                strategy_memory = summary_stats[strategy]['avg_memory_usage_mb']
                
                time_improvement = ((baseline_time - strategy_time) / baseline_time) * 100
                memory_overhead = ((strategy_memory - baseline_memory) / baseline_memory) * 100
                
                summary_stats[strategy]['performance_improvement_pct'] = float(time_improvement)
                summary_stats[strategy]['memory_overhead_pct'] = float(memory_overhead)
    
    # Save summary with proper JSON serialization
    with open(results_dir / "real_world_analysis_summary.json", 'w') as f:
        json.dump(convert_numpy_types(summary_stats), f, indent=2)
    
    # Print comprehensive results
    print("\n" + "=" * 50)
    print("📊 REAL-WORLD BENCHMARK ANALYSIS RESULTS")
    print("=" * 50)
    
    for strategy, stats in summary_stats.items():
        print(f"\n🔧 {strategy} CACHING STRATEGY:")
        print(f"   📈 Average Execution Time: {stats['avg_execution_time_ms']:.1f}ms")
        print(f"   📊 Median Execution Time: {stats['median_execution_time_ms']:.1f}ms")
        print(f"   📏 Execution Time Range: {stats['min_execution_time_ms']:.1f}ms - {stats['max_execution_time_ms']:.1f}ms")
        print(f"   📐 Standard Deviation: {stats['std_execution_time_ms']:.1f}ms")
        print(f"   💾 Average Memory Usage: {stats['avg_memory_usage_mb']:.1f}MB")
        print(f"   🎯 Average Cache Hit Rate: {stats['avg_cache_hit_rate']:.1f}%")
        print(f"   ✅ Test Cases: {stats['test_count']}")
        print(f"   🎉 Success Rate: {stats['success_rate']:.1f}%")
        print(f"   🔍 Total Matches: {stats['total_matches_found']:,}")
        
        if 'performance_improvement_pct' in stats:
            print(f"   🚀 Performance Improvement: +{stats['performance_improvement_pct']:.1f}% vs No Cache")
            print(f"   💾 Memory Overhead: +{stats['memory_overhead_pct']:.1f}% vs No Cache")
    
    # Performance comparison
    if len(summary_stats) >= 2:
        print(f"\n🏆 PERFORMANCE COMPARISON:")
        strategies = list(summary_stats.keys())
        times = [summary_stats[s]['avg_execution_time_ms'] for s in strategies]
        best_strategy = strategies[times.index(min(times))]
        print(f"   🥇 Fastest Strategy: {best_strategy} ({min(times):.1f}ms average)")
        
        if 'LRU' in summary_stats and 'FIFO' in summary_stats:
            lru_time = summary_stats['LRU']['avg_execution_time_ms']
            fifo_time = summary_stats['FIFO']['avg_execution_time_ms']
            lru_advantage = ((fifo_time - lru_time) / fifo_time) * 100
            print(f"   ⚡ LRU vs FIFO Advantage: {lru_advantage:+.1f}%")
            
            lru_hit_rate = summary_stats['LRU']['avg_cache_hit_rate']
            fifo_hit_rate = summary_stats['FIFO']['avg_cache_hit_rate']
            hit_rate_advantage = lru_hit_rate - fifo_hit_rate
            print(f"   🎯 LRU Hit Rate Advantage: +{hit_rate_advantage:.1f} percentage points")
    
    # Detailed analysis by complexity and dataset size
    print(f"\n📈 PERFORMANCE BY COMPLEXITY:")
    complexity_analysis = df.groupby(['pattern_complexity', 'cache_strategy'])['execution_time_ms'].mean().unstack()
    for complexity in ['simple', 'medium', 'complex']:
        if complexity in complexity_analysis.index:
            print(f"   {complexity.upper()}:")
            for strategy in ['NO_CACHE', 'FIFO', 'LRU']:
                if strategy in complexity_analysis.columns:
                    time = complexity_analysis.loc[complexity, strategy]
                    print(f"     {strategy}: {time:.1f}ms")
    
    print(f"\n📊 PERFORMANCE BY DATASET SIZE:")
    size_analysis = df.groupby(['dataset_size', 'cache_strategy'])['execution_time_ms'].mean().unstack()
    for size in sorted(df['dataset_size'].unique()):
        print(f"   {size:,} records:")
        for strategy in ['NO_CACHE', 'FIFO', 'LRU']:
            if strategy in size_analysis.columns:
                time = size_analysis.loc[size, strategy]
                print(f"     {strategy}: {time:.1f}ms")
    
    # Create performance comparison table
    comparison_table = []
    for _, row in df.iterrows():
        comparison_table.append({
            'Dataset_Size': f"{row['dataset_size']:,}",
            'Data_Type': row['data_type'].title(),
            'Complexity': row['pattern_complexity'].title(),
            'Strategy': row['cache_strategy'],
            'Execution_Time_ms': f"{row['execution_time_ms']:.1f}",
            'Memory_MB': f"{row['memory_usage_mb']:.1f}",
            'Cache_Hit_Rate': f"{row['cache_hit_rate']:.1f}%",
            'Matches_Found': row['result_count']
        })
    
    comparison_df = pd.DataFrame(comparison_table)
    comparison_df.to_csv(results_dir / "real_world_performance_comparison.csv", index=False)
    
    # Calculate key insights
    insights = {
        'total_tests': len(df),
        'avg_improvement_fifo': summary_stats.get('FIFO', {}).get('performance_improvement_pct', 0),
        'avg_improvement_lru': summary_stats.get('LRU', {}).get('performance_improvement_pct', 0),
        'lru_vs_fifo_advantage': lru_advantage if 'LRU' in summary_stats and 'FIFO' in summary_stats else 0,
        'lru_hit_rate': summary_stats.get('LRU', {}).get('avg_cache_hit_rate', 0),
        'fifo_hit_rate': summary_stats.get('FIFO', {}).get('avg_cache_hit_rate', 0),
        'memory_overhead_lru': summary_stats.get('LRU', {}).get('memory_overhead_pct', 0),
        'memory_overhead_fifo': summary_stats.get('FIFO', {}).get('memory_overhead_pct', 0)
    }
    
    print(f"\n🎯 KEY INSIGHTS:")
    print(f"   • FIFO Cache provides {insights['avg_improvement_fifo']:.1f}% performance improvement")
    print(f"   • LRU Cache provides {insights['avg_improvement_lru']:.1f}% performance improvement")
    print(f"   • LRU is {insights['lru_vs_fifo_advantage']:.1f}% faster than FIFO")
    print(f"   • LRU achieves {insights['lru_hit_rate']:.1f}% cache hit rate vs {insights['fifo_hit_rate']:.1f}% for FIFO")
    print(f"   • Memory overhead: FIFO +{insights['memory_overhead_fifo']:.0f}%, LRU +{insights['memory_overhead_lru']:.0f}%")
    
    print(f"\n📁 Analysis files generated:")
    print(f"   • real_world_analysis_summary.json - Comprehensive statistics")
    print(f"   • real_world_performance_comparison.csv - Detailed comparison table")
    
    return summary_stats, insights

def create_visualizations(summary_stats: Dict[str, Any]):
    """Create performance visualizations."""
    
    results_dir = Path("tests/performance/real_world_results")
    df = pd.read_csv(results_dir / "practical_real_world_results.csv")
    
    # Set style
    plt.style.use('seaborn-v0_8-whitegrid')
    
    # Create comprehensive visualization
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. Average execution time by strategy
    strategies = list(summary_stats.keys())
    times = [summary_stats[s]['avg_execution_time_ms'] for s in strategies]
    colors = ['#ff7f7f', '#7fbf7f', '#7f7fff']
    
    bars1 = ax1.bar(strategies, times, color=colors, alpha=0.8)
    ax1.set_title('Average Execution Time by Caching Strategy', fontweight='bold', fontsize=14)
    ax1.set_ylabel('Execution Time (ms)', fontsize=12)
    ax1.set_xlabel('Caching Strategy', fontsize=12)
    
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + 10,
                f'{height:.0f}ms', ha='center', va='bottom', fontweight='bold')
    
    # 2. Cache hit rates
    hit_rates = [summary_stats[s]['avg_cache_hit_rate'] for s in strategies]
    bars2 = ax2.bar(strategies, hit_rates, color=colors, alpha=0.8)
    ax2.set_title('Average Cache Hit Rate by Strategy', fontweight='bold', fontsize=14)
    ax2.set_ylabel('Cache Hit Rate (%)', fontsize=12)
    ax2.set_xlabel('Caching Strategy', fontsize=12)
    ax2.set_ylim(0, 100)
    
    for bar in bars2:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + 2,
                f'{height:.1f}%', ha='center', va='bottom', fontweight='bold')
    
    # 3. Performance by dataset size
    size_perf = df.groupby(['dataset_size', 'cache_strategy'])['execution_time_ms'].mean().unstack()
    size_perf.plot(kind='line', ax=ax3, marker='o', linewidth=2, markersize=6, color=colors)
    ax3.set_title('Performance Scaling by Dataset Size', fontweight='bold', fontsize=14)
    ax3.set_ylabel('Execution Time (ms)', fontsize=12)
    ax3.set_xlabel('Dataset Size (records)', fontsize=12)
    ax3.legend(title='Caching Strategy')
    ax3.grid(True, alpha=0.3)
    
    # 4. Memory usage comparison
    memory_usage = [summary_stats[s]['avg_memory_usage_mb'] for s in strategies]
    bars4 = ax4.bar(strategies, memory_usage, color=colors, alpha=0.8)
    ax4.set_title('Average Memory Usage by Strategy', fontweight='bold', fontsize=14)
    ax4.set_ylabel('Memory Usage (MB)', fontsize=12)
    ax4.set_xlabel('Caching Strategy', fontsize=12)
    
    for bar in bars4:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                f'{height:.1f}MB', ha='center', va='bottom', fontweight='bold')
    
    plt.suptitle('Real-World MATCH_RECOGNIZE Caching Performance Analysis', 
                 fontsize=16, fontweight='bold', y=0.98)
    plt.tight_layout()
    plt.savefig(results_dir / "real_world_performance_analysis.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"📊 Visualization saved: real_world_performance_analysis.png")

def main():
    """Main analysis function."""
    print("🚀 Starting Real-World Performance Analysis...")
    
    summary_stats, insights = analyze_results()
    create_visualizations(summary_stats)
    
    print(f"\n✅ Real-world performance analysis complete!")
    return 0

if __name__ == "__main__":
    exit(main())
