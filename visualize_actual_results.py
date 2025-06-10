#!/usr/bin/env python3
"""
Comprehensive Performance Visualization for Row Match Recognize System
Creates detailed charts comparing LRU, FIFO, and No-caching performance
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import warnings
import ast
warnings.filterwarnings('ignore')

# Set style for professional plots
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")

def load_benchmark_data():
    """Load and process benchmark results"""
    try:
        df = pd.read_csv('enhanced_benchmark_results.csv')
        print(f"Loaded {len(df)} benchmark records")
        
        # Parse execution_times from string to list
        def safe_parse_list(x):
            try:
                if isinstance(x, str):
                    return ast.literal_eval(x)
                return x
            except:
                return []
        
        df['execution_times_parsed'] = df['execution_times'].apply(safe_parse_list)
        df['memory_usages_parsed'] = df['memory_usages'].apply(safe_parse_list)
        
        return df
    except Exception as e:
        print(f"Error loading data: {e}")
        return None

def create_execution_time_comparison(df):
    """Create execution time comparison chart"""
    plt.figure(figsize=(14, 8))
    
    # Create subplot for execution time comparison
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Performance Comparison: LRU vs FIFO vs No-Caching', fontsize=16, fontweight='bold')
    
    # 1. Average Execution Time by Cache Mode
    ax1 = axes[0, 0]
    execution_comparison = df.groupby('cache_mode')['avg_execution_time'].mean().reset_index()
    bars = ax1.bar(execution_comparison['cache_mode'], execution_comparison['avg_execution_time'], 
                   color=['#FF6B6B', '#4ECDC4', '#45B7D1'], alpha=0.8)
    ax1.set_title('Average Execution Time by Cache Mode', fontweight='bold')
    ax1.set_ylabel('Execution Time (seconds)')
    ax1.set_xlabel('Cache Mode')
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.3f}s', ha='center', va='bottom', fontweight='bold')
    
    # 2. Cache Hit Rate Comparison
    ax2 = axes[0, 1]
    cache_hit_data = df[df['cache_mode'] != 'none']['cache_hit_rate']
    cache_modes = df[df['cache_mode'] != 'none']['cache_mode']
    
    if len(cache_hit_data) > 0:
        hit_rate_comparison = df[df['cache_mode'] != 'none'].groupby('cache_mode')['cache_hit_rate'].mean()
        bars2 = ax2.bar(hit_rate_comparison.index, hit_rate_comparison.values, 
                       color=['#4ECDC4', '#45B7D1'], alpha=0.8)
        ax2.set_title('Cache Hit Rate Comparison', fontweight='bold')
        ax2.set_ylabel('Hit Rate (%)')
        ax2.set_xlabel('Cache Mode')
        
        for bar in bars2:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%', ha='center', va='bottom', fontweight='bold')
    
    # 3. Memory Usage Comparison
    ax3 = axes[1, 0]
    memory_comparison = df.groupby('cache_mode')['memory_increase'].mean().reset_index()
    bars3 = ax3.bar(memory_comparison['cache_mode'], memory_comparison['memory_increase'], 
                   color=['#FF6B6B', '#4ECDC4', '#45B7D1'], alpha=0.8)
    ax3.set_title('Average Memory Increase by Cache Mode', fontweight='bold')
    ax3.set_ylabel('Memory Increase (MB)')
    ax3.set_xlabel('Cache Mode')
    
    for bar in bars3:
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}MB', ha='center', va='bottom', fontweight='bold')
    
    # 4. Performance by Scenario Complexity
    ax4 = axes[1, 1]
    scenario_perf = df.groupby(['complexity', 'cache_mode'])['avg_execution_time'].mean().unstack()
    scenario_perf.plot(kind='bar', ax=ax4, color=['#FF6B6B', '#4ECDC4', '#45B7D1'], alpha=0.8)
    ax4.set_title('Performance by Scenario Complexity', fontweight='bold')
    ax4.set_ylabel('Execution Time (seconds)')
    ax4.set_xlabel('Complexity Level')
    ax4.legend(title='Cache Mode')
    ax4.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    plt.savefig('performance_comparison_overview.png', dpi=300, bbox_inches='tight')
    print("✓ Created performance_comparison_overview.png")
    plt.show()

def create_detailed_heatmap(df):
    """Create detailed performance heatmap"""
    plt.figure(figsize=(12, 8))
    
    # Prepare data for heatmap
    heatmap_data = df.pivot_table(
        values='avg_execution_time', 
        index='scenario_description', 
        columns='cache_mode', 
        aggfunc='mean'
    )
    
    # Create heatmap
    sns.heatmap(heatmap_data, annot=True, fmt='.3f', cmap='RdYlBu_r', 
                cbar_kws={'label': 'Execution Time (seconds)'})
    plt.title('Performance Heatmap: Execution Time by Scenario and Cache Mode', 
              fontsize=14, fontweight='bold', pad=20)
    plt.xlabel('Cache Mode', fontweight='bold')
    plt.ylabel('Test Scenario', fontweight='bold')
    plt.xticks(rotation=0)
    plt.yticks(rotation=0)
    
    plt.tight_layout()
    plt.savefig('performance_heatmap.png', dpi=300, bbox_inches='tight')
    print("✓ Created performance_heatmap.png")
    plt.show()

def create_scalability_analysis(df):
    """Create scalability analysis chart"""
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle('Scalability Analysis: Performance vs Data Size', fontsize=16, fontweight='bold')
    
    # 1. Execution Time vs Data Size
    ax1 = axes[0]
    for cache_mode in df['cache_mode'].unique():
        cache_data = df[df['cache_mode'] == cache_mode]
        ax1.plot(cache_data['data_size'], cache_data['avg_execution_time'], 
                marker='o', linewidth=2, markersize=8, label=cache_mode.upper())
    
    ax1.set_title('Execution Time vs Data Size', fontweight='bold')
    ax1.set_xlabel('Data Size (records)')
    ax1.set_ylabel('Execution Time (seconds)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. Memory Usage vs Data Size
    ax2 = axes[1]
    for cache_mode in df['cache_mode'].unique():
        cache_data = df[df['cache_mode'] == cache_mode]
        ax2.plot(cache_data['data_size'], cache_data['max_memory'], 
                marker='s', linewidth=2, markersize=8, label=cache_mode.upper())
    
    ax2.set_title('Memory Usage vs Data Size', fontweight='bold')
    ax2.set_xlabel('Data Size (records)')
    ax2.set_ylabel('Max Memory Usage (MB)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('scalability_analysis.png', dpi=300, bbox_inches='tight')
    print("✓ Created scalability_analysis.png")
    plt.show()

def create_performance_summary_table(df):
    """Create comprehensive performance summary"""
    # Calculate performance metrics
    summary_stats = []
    
    for cache_mode in df['cache_mode'].unique():
        cache_data = df[df['cache_mode'] == cache_mode]
        
        stats = {
            'Cache Mode': cache_mode.upper(),
            'Avg Execution Time (s)': f"{cache_data['avg_execution_time'].mean():.3f}",
            'Min Execution Time (s)': f"{cache_data['avg_execution_time'].min():.3f}",
            'Max Execution Time (s)': f"{cache_data['avg_execution_time'].max():.3f}",
            'Avg Memory Increase (MB)': f"{cache_data['memory_increase'].mean():.2f}",
            'Cache Hit Rate (%)': f"{cache_data['cache_hit_rate'].mean():.1f}" if cache_mode != 'none' else 'N/A'
        }
        summary_stats.append(stats)
    
    summary_df = pd.DataFrame(summary_stats)
    
    # Create table visualization
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.axis('tight')
    ax.axis('off')
    
    table = ax.table(cellText=summary_df.values, colLabels=summary_df.columns,
                    cellLoc='center', loc='center', bbox=[0, 0, 1, 1])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 2)
    
    # Style the table
    for (i, j), cell in table.get_celld().items():
        if i == 0:  # Header row
            cell.set_text_props(weight='bold')
            cell.set_facecolor('#4ECDC4')
        else:
            if j % 2 == 0:
                cell.set_facecolor('#F0F0F0')
            else:
                cell.set_facecolor('#FFFFFF')
    
    plt.title('Performance Summary Table', fontsize=16, fontweight='bold', pad=20)
    plt.savefig('performance_summary_table.png', dpi=300, bbox_inches='tight')
    print("✓ Created performance_summary_table.png")
    plt.show()
    
    return summary_df

def calculate_performance_improvements(df):
    """Calculate performance improvements"""
    print("\n" + "="*60)
    print("PERFORMANCE IMPROVEMENT ANALYSIS")
    print("="*60)
    
    # Get average performance by cache mode
    perf_by_mode = df.groupby('cache_mode')['avg_execution_time'].mean()
    
    if 'none' in perf_by_mode.index:
        baseline = perf_by_mode['none']
        
        print(f"\nBaseline (No Caching): {baseline:.3f}s")
        
        if 'fifo' in perf_by_mode.index:
            fifo_improvement = ((baseline - perf_by_mode['fifo']) / baseline) * 100
            print(f"FIFO Caching: {perf_by_mode['fifo']:.3f}s ({fifo_improvement:+.1f}%)")
        
        if 'lru' in perf_by_mode.index:
            lru_improvement = ((baseline - perf_by_mode['lru']) / baseline) * 100
            print(f"LRU Caching: {perf_by_mode['lru']:.3f}s ({lru_improvement:+.1f}%)")
            
        # Compare LRU vs FIFO
        if 'fifo' in perf_by_mode.index and 'lru' in perf_by_mode.index:
            lru_vs_fifo = ((perf_by_mode['fifo'] - perf_by_mode['lru']) / perf_by_mode['fifo']) * 100
            print(f"\nLRU vs FIFO Improvement: {lru_vs_fifo:+.1f}%")
    
    # Memory efficiency analysis
    print(f"\n{'Memory Usage Analysis:':<25}")
    memory_by_mode = df.groupby('cache_mode')['memory_increase'].mean()
    for mode, memory in memory_by_mode.items():
        print(f"{mode.upper():<12}: {memory:.2f} MB average increase")
    
    # Cache efficiency
    cache_efficiency = df[df['cache_mode'] != 'none'].groupby('cache_mode')['cache_hit_rate'].mean()
    if len(cache_efficiency) > 0:
        print(f"\n{'Cache Hit Rates:':<25}")
        for mode, hit_rate in cache_efficiency.items():
            print(f"{mode.upper():<12}: {hit_rate:.1f}%")

def main():
    """Main execution function"""
    print("🚀 Starting Comprehensive Performance Visualization")
    print("="*60)
    
    # Load data
    df = load_benchmark_data()
    if df is None:
        print("❌ Failed to load benchmark data")
        return
    
    print(f"📊 Processing {len(df)} benchmark records...")
    
    try:
        # Create all visualizations
        print("\n📈 Creating performance comparison overview...")
        create_execution_time_comparison(df)
        
        print("\n🔥 Creating performance heatmap...")
        create_detailed_heatmap(df)
        
        print("\n📏 Creating scalability analysis...")
        create_scalability_analysis(df)
        
        print("\n📋 Creating performance summary table...")
        summary_df = create_performance_summary_table(df)
        
        # Calculate improvements
        calculate_performance_improvements(df)
        
        # Save summary to CSV
        summary_df.to_csv('performance_summary.csv', index=False)
        print("\n✅ All visualizations created successfully!")
        print("📁 Files generated:")
        print("   • performance_comparison_overview.png")
        print("   • performance_heatmap.png") 
        print("   • scalability_analysis.png")
        print("   • performance_summary_table.png")
        print("   • performance_summary.csv")
        
    except Exception as e:
        print(f"❌ Error creating visualizations: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
