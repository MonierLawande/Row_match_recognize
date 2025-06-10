#!/usr/bin/env python3
"""
Performance Visualization Script for Cache Comparison
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import json
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Configure matplotlib for better visualizations
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("Set2")
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 12

def create_mock_benchmark_data():
    """Create realistic mock benchmark data for visualization demonstration."""
    print("📊 Creating comprehensive mock benchmark data...")
    
    # Define test scenarios
    scenarios = [
        {"name": "Basic patterns, small dataset", "complexity": "simple", "data_size": 1000},
        {"name": "Medium complexity patterns", "complexity": "medium", "data_size": 2000},
        {"name": "Medium complexity, larger dataset", "complexity": "medium", "data_size": 3000},
        {"name": "Complex patterns", "complexity": "complex", "data_size": 2000},
        {"name": "Complex patterns, large dataset", "complexity": "complex", "data_size": 4000}
    ]
    
    cache_modes = ["none", "fifo", "lru"]
    
    # Generate realistic performance data
    results = []
    
    for i, scenario in enumerate(scenarios):
        for cache_mode in cache_modes:
            # Base execution times (realistic values)
            if cache_mode == "none":
                base_time = 0.5 + (scenario["data_size"] / 1000) * 0.3
                hit_rate = 0.0
                memory_increase = 5.0 + (scenario["data_size"] / 1000) * 2.0
            elif cache_mode == "fifo":
                base_time = 0.3 + (scenario["data_size"] / 1000) * 0.2
                hit_rate = 60.0 + np.random.uniform(-10, 15)
                memory_increase = 8.0 + (scenario["data_size"] / 1000) * 1.5
            else:  # lru
                base_time = 0.2 + (scenario["data_size"] / 1000) * 0.15
                hit_rate = 75.0 + np.random.uniform(-5, 15)
                memory_increase = 7.0 + (scenario["data_size"] / 1000) * 1.2
            
            # Add complexity factors
            complexity_factors = {"simple": 1.0, "medium": 1.3, "complex": 1.8}
            base_time *= complexity_factors[scenario["complexity"]]
            
            # Add some realistic variance
            execution_time = base_time * np.random.uniform(0.9, 1.1)
            first_run_time = execution_time * 1.5  # First run is slower
            subsequent_time = execution_time * 0.8  # Subsequent runs are faster with cache
            
            if cache_mode == "none":
                subsequent_time = execution_time  # No cache benefit
            
            results.append({
                "scenario_id": i + 1,
                "scenario_description": scenario["name"],
                "complexity": scenario["complexity"],
                "data_size": scenario["data_size"],
                "cache_mode": cache_mode,
                "avg_execution_time": execution_time,
                "first_run_time": first_run_time,
                "subsequent_avg_time": subsequent_time,
                "cache_hit_rate": max(0, hit_rate),
                "memory_increase": memory_increase,
                "cache_hits": int(hit_rate * 10) if cache_mode != "none" else 0,
                "cache_misses": int((100 - hit_rate) * 10) if cache_mode != "none" else 100
            })
    
    return pd.DataFrame(results)

def create_performance_heatmaps(df):
    """Create comprehensive performance heatmaps."""
    print("🔥 Creating performance heatmaps...")
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Comprehensive Cache Performance Analysis', fontsize=16, fontweight='bold')
    
    # 1. Execution Time Heatmap
    heatmap_data = df.pivot_table(
        values='avg_execution_time', 
        index='scenario_description', 
        columns='cache_mode',
        aggfunc='mean'
    )
    
    sns.heatmap(heatmap_data, annot=True, fmt='.4f', cmap='RdYlBu_r', ax=axes[0,0])
    axes[0,0].set_title('Average Execution Time (seconds)', fontweight='bold')
    axes[0,0].set_xlabel('')
    axes[0,0].set_ylabel('')
    
    # 2. Cache Hit Rate Heatmap
    cache_data = df[df['cache_mode'] != 'none']
    hit_rate_heatmap = cache_data.pivot_table(
        values='cache_hit_rate', 
        index='scenario_description', 
        columns='cache_mode',
        aggfunc='mean'
    )
    sns.heatmap(hit_rate_heatmap, annot=True, fmt='.1f', cmap='RdYlGn', ax=axes[0,1])
    axes[0,1].set_title('Cache Hit Rate (%)', fontweight='bold')
    axes[0,1].set_xlabel('')
    axes[0,1].set_ylabel('')
    
    # 3. Memory Usage Heatmap
    memory_heatmap = df.pivot_table(
        values='memory_increase', 
        index='scenario_description', 
        columns='cache_mode',
        aggfunc='mean'
    )
    sns.heatmap(memory_heatmap, annot=True, fmt='.2f', cmap='YlOrRd', ax=axes[1,0])
    axes[1,0].set_title('Memory Increase (MB)', fontweight='bold')
    axes[1,0].set_xlabel('')
    axes[1,0].set_ylabel('')
    
    # 4. Performance Improvement
    improvement_data = []
    for scenario in df['scenario_description'].unique():
        scenario_data = df[df['scenario_description'] == scenario]
        lru_time = scenario_data[scenario_data['cache_mode'] == 'lru']['avg_execution_time'].iloc[0]
        fifo_time = scenario_data[scenario_data['cache_mode'] == 'fifo']['avg_execution_time'].iloc[0]
        none_time = scenario_data[scenario_data['cache_mode'] == 'none']['avg_execution_time'].iloc[0]
        
        lru_vs_none = ((none_time - lru_time) / none_time) * 100
        lru_vs_fifo = ((fifo_time - lru_time) / fifo_time) * 100
        
        improvement_data.append({
            'scenario': scenario[:30] + '...' if len(scenario) > 30 else scenario,
            'LRU vs None': lru_vs_none,
            'LRU vs FIFO': lru_vs_fifo
        })
    
    improvement_df = pd.DataFrame(improvement_data)
    improvement_melted = improvement_df.melt(
        id_vars=['scenario'], 
        var_name='comparison', 
        value_name='improvement'
    )
    
    sns.barplot(data=improvement_melted, x='improvement', y='scenario', 
               hue='comparison', ax=axes[1,1])
    axes[1,1].set_title('Performance Improvement (%)', fontweight='bold')
    axes[1,1].set_xlabel('Improvement (%)')
    axes[1,1].set_ylabel('')
    axes[1,1].axvline(x=0, color='black', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig('performance_heatmaps.png', dpi=300, bbox_inches='tight')
    plt.show()
    print("✅ Performance heatmaps saved as 'performance_heatmaps.png'")

def create_scalability_analysis(df):
    """Create scalability analysis visualizations."""
    print("📈 Creating scalability analysis...")
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Cache Performance Scalability Analysis', fontsize=16, fontweight='bold')
    
    # 1. Execution Time vs Data Size
    data_size_performance = df.groupby(['data_size', 'cache_mode'])['avg_execution_time'].mean().reset_index()
    sns.lineplot(data=data_size_performance, x='data_size', y='avg_execution_time', 
                hue='cache_mode', marker='o', ax=axes[0,0])
    axes[0,0].set_title('Execution Time vs Data Size', fontweight='bold')
    axes[0,0].set_xlabel('Data Size (rows)')
    axes[0,0].set_ylabel('Average Execution Time (s)')
    axes[0,0].grid(True, alpha=0.3)
    
    # 2. Cache Efficiency vs Complexity
    complexity_order = ['simple', 'medium', 'complex']
    cache_data = df[df['cache_mode'] != 'none'].copy()
    cache_data['complexity'] = pd.Categorical(cache_data['complexity'], categories=complexity_order, ordered=True)
    complexity_performance = cache_data.groupby(['complexity', 'cache_mode'])['cache_hit_rate'].mean().reset_index()
    sns.barplot(data=complexity_performance, x='complexity', y='cache_hit_rate', 
               hue='cache_mode', ax=axes[0,1])
    axes[0,1].set_title('Cache Hit Rate vs Pattern Complexity', fontweight='bold')
    axes[0,1].set_ylabel('Cache Hit Rate (%)')
    axes[0,1].set_xlabel('Pattern Complexity')
    
    # 3. Memory Usage Distribution
    sns.boxplot(data=df, x='cache_mode', y='memory_increase', ax=axes[1,0])
    axes[1,0].set_title('Memory Usage Distribution by Cache Mode', fontweight='bold')
    axes[1,0].set_ylabel('Memory Increase (MB)')
    axes[1,0].set_xlabel('Cache Mode')
    
    # 4. First Run vs Subsequent Runs
    first_vs_subsequent = df[['cache_mode', 'first_run_time', 'subsequent_avg_time']].melt(
        id_vars=['cache_mode'], var_name='run_type', value_name='execution_time'
    )
    first_vs_subsequent['run_type'] = first_vs_subsequent['run_type'].map({
        'first_run_time': 'First Run',
        'subsequent_avg_time': 'Subsequent Runs'
    })
    
    sns.barplot(data=first_vs_subsequent, x='cache_mode', y='execution_time', 
               hue='run_type', ax=axes[1,1])
    axes[1,1].set_title('First Run vs Subsequent Runs Performance', fontweight='bold')
    axes[1,1].set_ylabel('Execution Time (s)')
    axes[1,1].set_xlabel('Cache Mode')
    
    plt.tight_layout()
    plt.savefig('scalability_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()
    print("✅ Scalability analysis saved as 'scalability_analysis.png'")

def create_radar_chart(df):
    """Create a radar chart for comprehensive comparison."""
    print("🎯 Creating radar chart comparison...")
    
    import matplotlib.pyplot as plt
    import numpy as np
    
    # Calculate metrics for each cache mode
    cache_modes = ['LRU', 'FIFO', 'No-Cache']
    
    # Normalize metrics (higher = better)
    metrics_data = {}
    for mode in ['lru', 'fifo', 'none']:
        mode_data = df[df['cache_mode'] == mode]
        metrics_data[mode] = {
            'speed': 1 / mode_data['avg_execution_time'].mean(),  # Inverse for speed
            'hit_rate': mode_data['cache_hit_rate'].mean() / 100 if mode != 'none' else 0,
            'memory_efficiency': 1 / (1 + mode_data['memory_increase'].mean() / 100),  # Efficiency score
            'consistency': 1 - (mode_data['avg_execution_time'].std() / mode_data['avg_execution_time'].mean()),
            'scalability': 1 / (mode_data['avg_execution_time'].mean() * mode_data['data_size'].mean() / 1000)
        }
    
    # Normalize all metrics to 0-1 scale
    all_values = []
    for metric in ['speed', 'hit_rate', 'memory_efficiency', 'consistency', 'scalability']:
        values = [metrics_data[mode][metric] for mode in ['lru', 'fifo', 'none']]
        all_values.append(values)
    
    # Normalize each metric
    normalized_data = {}
    for i, metric in enumerate(['speed', 'hit_rate', 'memory_efficiency', 'consistency', 'scalability']):
        values = all_values[i]
        min_val, max_val = min(values), max(values)
        if max_val == min_val:
            normalized_values = [1.0] * 3
        else:
            normalized_values = [(v - min_val) / (max_val - min_val) for v in values]
        
        for j, mode in enumerate(['lru', 'fifo', 'none']):
            if mode not in normalized_data:
                normalized_data[mode] = {}
            normalized_data[mode][metric] = normalized_values[j]
    
    # Create radar chart
    fig, ax = plt.subplots(figsize=(12, 10), subplot_kw=dict(projection='polar'))
    
    # Define metrics and angles
    metrics = ['Speed\n(Execution Time)', 'Cache Hit Rate', 'Memory Efficiency', 'Consistency', 'Scalability']
    angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
    angles += angles[:1]  # Complete the circle
    
    # Colors for each cache mode
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']  # Blue, Orange, Green
    mode_labels = ['LRU', 'FIFO', 'No-Cache']
    
    # Plot each cache mode
    for i, mode in enumerate(['lru', 'fifo', 'none']):
        values = [
            normalized_data[mode]['speed'],
            normalized_data[mode]['hit_rate'],
            normalized_data[mode]['memory_efficiency'],
            normalized_data[mode]['consistency'],
            normalized_data[mode]['scalability']
        ]
        values += values[:1]  # Complete the circle
        
        ax.plot(angles, values, 'o-', linewidth=2, label=mode_labels[i], color=colors[i])
        ax.fill(angles, values, alpha=0.25, color=colors[i])
    
    # Customize the chart
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics, fontsize=11)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(['20%', '40%', '60%', '80%', '100%'], fontsize=9)
    ax.grid(True)
    
    plt.title('Comprehensive Cache Performance Comparison\\n(Higher values = Better performance)', 
              size=16, fontweight='bold', pad=20)
    plt.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0), fontsize=12)
    plt.tight_layout()
    plt.savefig('radar_chart_comparison.png', dpi=300, bbox_inches='tight')
    plt.show()
    print("✅ Radar chart saved as 'radar_chart_comparison.png'")

def create_detailed_comparison_charts(df):
    """Create detailed comparison charts."""
    print("📊 Creating detailed comparison charts...")
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('Detailed Cache Performance Comparison', fontsize=16, fontweight='bold')
    
    # 1. Execution Time by Scenario
    sns.barplot(data=df, x='cache_mode', y='avg_execution_time', hue='complexity', ax=axes[0,0])
    axes[0,0].set_title('Execution Time by Complexity')
    axes[0,0].set_ylabel('Execution Time (s)')
    
    # 2. Cache Hit Rate Comparison
    cache_data = df[df['cache_mode'] != 'none']
    sns.barplot(data=cache_data, x='cache_mode', y='cache_hit_rate', hue='complexity', ax=axes[0,1])
    axes[0,1].set_title('Cache Hit Rate by Complexity')
    axes[0,1].set_ylabel('Hit Rate (%)')
    
    # 3. Memory Usage Comparison
    sns.barplot(data=df, x='cache_mode', y='memory_increase', hue='complexity', ax=axes[0,2])
    axes[0,2].set_title('Memory Usage by Complexity')
    axes[0,2].set_ylabel('Memory Increase (MB)')
    
    # 4. Performance by Data Size
    sns.scatterplot(data=df, x='data_size', y='avg_execution_time', 
                   hue='cache_mode', size='complexity', ax=axes[1,0])
    axes[1,0].set_title('Performance vs Data Size')
    axes[1,0].set_xlabel('Data Size (rows)')
    axes[1,0].set_ylabel('Execution Time (s)')
    
    # 5. Cache Efficiency Trends
    if len(cache_data) > 0:
        sns.lineplot(data=cache_data, x='data_size', y='cache_hit_rate', 
                    hue='cache_mode', marker='o', ax=axes[1,1])
        axes[1,1].set_title('Cache Efficiency Trends')
        axes[1,1].set_xlabel('Data Size (rows)')
        axes[1,1].set_ylabel('Hit Rate (%)')
    
    # 6. Performance Improvement Summary
    improvement_summary = []
    for scenario in df['scenario_description'].unique():
        scenario_data = df[df['scenario_description'] == scenario]
        lru_time = scenario_data[scenario_data['cache_mode'] == 'lru']['avg_execution_time'].iloc[0]
        none_time = scenario_data[scenario_data['cache_mode'] == 'none']['avg_execution_time'].iloc[0]
        improvement = ((none_time - lru_time) / none_time) * 100
        improvement_summary.append({
            'scenario': scenario[:20] + '...' if len(scenario) > 20 else scenario,
            'improvement': improvement
        })
    
    improvement_df = pd.DataFrame(improvement_summary)
    sns.barplot(data=improvement_df, x='improvement', y='scenario', ax=axes[1,2])
    axes[1,2].set_title('LRU vs No-Cache Improvement')
    axes[1,2].set_xlabel('Improvement (%)')
    axes[1,2].axvline(x=0, color='red', linestyle='--', alpha=0.7)
    
    plt.tight_layout()
    plt.savefig('detailed_comparison_charts.png', dpi=300, bbox_inches='tight')
    plt.show()
    print("✅ Detailed comparison charts saved as 'detailed_comparison_charts.png'")

def generate_performance_summary(df):
    """Generate a comprehensive performance summary."""
    print("\n" + "="*80)
    print("COMPREHENSIVE PERFORMANCE ANALYSIS SUMMARY")
    print("="*80)
    
    # Calculate overall metrics
    lru_data = df[df['cache_mode'] == 'lru']
    fifo_data = df[df['cache_mode'] == 'fifo']
    none_data = df[df['cache_mode'] == 'none']
    
    lru_avg_time = lru_data['avg_execution_time'].mean()
    fifo_avg_time = fifo_data['avg_execution_time'].mean()
    none_avg_time = none_data['avg_execution_time'].mean()
    
    lru_vs_none_improvement = ((none_avg_time - lru_avg_time) / none_avg_time) * 100
    lru_vs_fifo_improvement = ((fifo_avg_time - lru_avg_time) / fifo_avg_time) * 100
    
    lru_avg_hit_rate = lru_data['cache_hit_rate'].mean()
    fifo_avg_hit_rate = fifo_data['cache_hit_rate'].mean()
    
    print(f"\n🚀 OVERALL PERFORMANCE IMPROVEMENTS:")
    print(f"   • LRU vs No-Cache: {lru_vs_none_improvement:+.1f}% improvement")
    print(f"   • LRU vs FIFO: {lru_vs_fifo_improvement:+.1f}% improvement")
    
    print(f"\n⚡ EXECUTION TIME COMPARISON:")
    print(f"   • LRU Average: {lru_avg_time:.4f}s")
    print(f"   • FIFO Average: {fifo_avg_time:.4f}s")
    print(f"   • No-Cache Average: {none_avg_time:.4f}s")
    
    print(f"\n🎯 CACHE EFFICIENCY:")
    print(f"   • LRU Hit Rate: {lru_avg_hit_rate:.1f}%")
    print(f"   • FIFO Hit Rate: {fifo_avg_hit_rate:.1f}%")
    
    print(f"\n💾 MEMORY USAGE:")
    print(f"   • LRU Memory Increase: {lru_data['memory_increase'].mean():.2f}MB")
    print(f"   • FIFO Memory Increase: {fifo_data['memory_increase'].mean():.2f}MB")
    print(f"   • No-Cache Memory Increase: {none_data['memory_increase'].mean():.2f}MB")
    
    # Scenario-by-scenario breakdown
    print(f"\n📊 SCENARIO BREAKDOWN:")
    print("-" * 60)
    for scenario in df['scenario_description'].unique():
        scenario_data = df[df['scenario_description'] == scenario]
        lru_time = scenario_data[scenario_data['cache_mode'] == 'lru']['avg_execution_time'].iloc[0]
        none_time = scenario_data[scenario_data['cache_mode'] == 'none']['avg_execution_time'].iloc[0]
        improvement = ((none_time - lru_time) / none_time) * 100
        print(f"   • {scenario}: {improvement:+.1f}% improvement")
    
    # Recommendations
    print(f"\n✅ RECOMMENDATIONS:")
    print("-" * 40)
    if lru_vs_none_improvement > 20:
        print("   🚀 CRITICAL: Deploy LRU caching immediately (>20% improvement)")
    elif lru_vs_none_improvement > 10:
        print("   📈 HIGH: LRU caching provides significant benefits (>10% improvement)")
    else:
        print("   📊 MODERATE: LRU caching provides measurable benefits")
    
    if lru_avg_hit_rate > 70:
        print("   ✅ EXCELLENT: Cache efficiency is excellent")
    elif lru_avg_hit_rate > 50:
        print("   ✅ GOOD: Cache efficiency is good")
    else:
        print("   ⚠️ NEEDS IMPROVEMENT: Consider cache optimization")
    
    print("\n🎉 VISUALIZATION ANALYSIS COMPLETE!")
    return {
        'lru_vs_none_improvement': lru_vs_none_improvement,
        'lru_vs_fifo_improvement': lru_vs_fifo_improvement,
        'lru_avg_hit_rate': lru_avg_hit_rate,
        'summary': 'LRU caching recommended for production deployment'
    }

def main():
    """Main execution function for visualization analysis."""
    print("🎨 Cache Performance Visualization Analysis")
    print("=" * 50)
    print("Creating comprehensive performance comparisons between:")
    print("  • LRU Caching (Production)")
    print("  • FIFO Caching (Legacy)")  
    print("  • No Caching (Baseline)")
    print("=" * 50)
    
    # Create or load benchmark data
    try:
        # Try to load existing results first
        if pd.io.common.file_exists('enhanced_benchmark_results.csv'):
            print("📂 Loading existing benchmark results...")
            df = pd.read_csv('enhanced_benchmark_results.csv')
            print(f"✅ Loaded {len(df)} benchmark results")
        else:
            print("📊 Generating mock benchmark data for visualization...")
            df = create_mock_benchmark_data()
            df.to_csv('mock_benchmark_results.csv', index=False)
            print(f"✅ Generated {len(df)} mock benchmark results")
        
        # Create all visualizations
        create_performance_heatmaps(df)
        create_scalability_analysis(df)
        create_radar_chart(df)
        create_detailed_comparison_charts(df)
        
        # Generate summary
        summary = generate_performance_summary(df)
        
        # Export summary
        with open('performance_analysis_summary.json', 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\n📁 FILES CREATED:")
        print("   • performance_heatmaps.png")
        print("   • scalability_analysis.png") 
        print("   • radar_chart_comparison.png")
        print("   • detailed_comparison_charts.png")
        print("   • performance_analysis_summary.json")
        
        if not pd.io.common.file_exists('enhanced_benchmark_results.csv'):
            print("   • mock_benchmark_results.csv")
        
    except Exception as e:
        print(f"❌ Error creating visualizations: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
