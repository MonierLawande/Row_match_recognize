#!/usr/bin/env python3
"""
Performance Visualization Generator
Creates comprehensive charts for LRU vs FIFO vs No-caching comparison
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import ast
import warnings
import sys
import os

warnings.filterwarnings('ignore')

def main():
    print("🚀 Starting Performance Visualization Generation")
    print("=" * 60)
    
    # Set matplotlib backend for headless operation
    plt.switch_backend('Agg')
    
    # Set style for professional plots
    try:
        plt.style.use('seaborn-v0_8')
    except:
        plt.style.use('default')
    
    # Load data
    try:
        df = pd.read_csv('enhanced_benchmark_results.csv')
        print(f"✅ Loaded {len(df)} benchmark records")
        
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
        
        print(f"📋 Data Summary:")
        print(f"   • Total records: {len(df)}")
        print(f"   • Cache modes: {', '.join(df['cache_mode'].unique())}")
        print(f"   • Scenarios: {len(df['scenario_description'].unique())}")
        
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return False
    
    # 1. Performance Dashboard
    print("\n📈 Creating performance dashboard...")
    try:
        create_performance_dashboard(df)
        print("✅ Performance dashboard created")
    except Exception as e:
        print(f"❌ Error creating dashboard: {e}")
    
    # 2. Performance Heatmap
    print("\n🔥 Creating performance heatmap...")
    try:
        create_performance_heatmap(df)
        print("✅ Performance heatmap created")
    except Exception as e:
        print(f"❌ Error creating heatmap: {e}")
    
    # 3. Scalability Analysis
    print("\n📏 Creating scalability analysis...")
    try:
        create_scalability_analysis(df)
        print("✅ Scalability analysis created")
    except Exception as e:
        print(f"❌ Error creating scalability analysis: {e}")
    
    # 4. Summary Analysis
    print("\n📊 Generating performance analysis...")
    try:
        generate_performance_analysis(df)
        print("✅ Performance analysis completed")
    except Exception as e:
        print(f"❌ Error in performance analysis: {e}")
    
    print("\n🎉 Visualization generation complete!")
    return True

def create_performance_dashboard(df):
    """Create comprehensive performance dashboard"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Performance Comparison Dashboard: LRU vs FIFO vs No-Caching', 
                 fontsize=16, fontweight='bold', y=0.98)
    
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
    
    # 1. Average Execution Time by Cache Mode
    ax1 = axes[0, 0]
    execution_comparison = df.groupby('cache_mode')['avg_execution_time'].mean().reset_index()
    bars = ax1.bar(execution_comparison['cache_mode'], execution_comparison['avg_execution_time'], 
                   color=colors, alpha=0.8, edgecolor='white', linewidth=2)
    ax1.set_title('Average Execution Time by Cache Mode', fontweight='bold', pad=15)
    ax1.set_ylabel('Execution Time (seconds)')
    ax1.set_xlabel('Cache Mode')
    ax1.grid(True, alpha=0.3, axis='y')
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + 0.05,
                f'{height:.3f}s', ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    # 2. Cache Hit Rate Comparison
    ax2 = axes[0, 1]
    cache_data = df[df['cache_mode'] != 'none']
    if len(cache_data) > 0:
        hit_rate_comparison = cache_data.groupby('cache_mode')['cache_hit_rate'].mean()
        bars2 = ax2.bar(hit_rate_comparison.index, hit_rate_comparison.values, 
                       color=['#4ECDC4', '#45B7D1'], alpha=0.8, edgecolor='white', linewidth=2)
        ax2.set_title('Cache Hit Rate Comparison', fontweight='bold', pad=15)
        ax2.set_ylabel('Hit Rate (%)')
        ax2.set_xlabel('Cache Mode')
        ax2.grid(True, alpha=0.3, axis='y')
        
        for bar in bars2:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height + 1,
                    f'{height:.1f}%', ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    # 3. Memory Usage Comparison
    ax3 = axes[1, 0]
    memory_comparison = df.groupby('cache_mode')['memory_increase'].mean().reset_index()
    bars3 = ax3.bar(memory_comparison['cache_mode'], memory_comparison['memory_increase'], 
                   color=colors, alpha=0.8, edgecolor='white', linewidth=2)
    ax3.set_title('Average Memory Increase by Cache Mode', fontweight='bold', pad=15)
    ax3.set_ylabel('Memory Increase (MB)')
    ax3.set_xlabel('Cache Mode')
    ax3.grid(True, alpha=0.3, axis='y')
    
    for bar in bars3:
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height + 0.02,
                f'{height:.2f}MB', ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    # 4. Performance by Scenario Complexity
    ax4 = axes[1, 1]
    scenario_perf = df.groupby(['complexity', 'cache_mode'])['avg_execution_time'].mean().unstack()
    scenario_perf.plot(kind='bar', ax=ax4, color=colors, alpha=0.8, width=0.7)
    ax4.set_title('Performance by Scenario Complexity', fontweight='bold', pad=15)
    ax4.set_ylabel('Execution Time (seconds)')
    ax4.set_xlabel('Complexity Level')
    ax4.legend(title='Cache Mode', framealpha=0.9)
    ax4.tick_params(axis='x', rotation=45)
    ax4.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('performance_comparison_dashboard.png', dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()

def create_performance_heatmap(df):
    """Create detailed performance heatmap"""
    plt.figure(figsize=(12, 8))
    
    # Prepare data for heatmap
    heatmap_data = df.pivot_table(
        values='avg_execution_time', 
        index='scenario_description', 
        columns='cache_mode', 
        aggfunc='mean'
    )
    
    # Create heatmap with custom styling
    mask = heatmap_data.isnull()
    sns.heatmap(heatmap_data, annot=True, fmt='.3f', cmap='RdYlBu_r', 
                cbar_kws={'label': 'Execution Time (seconds)', 'shrink': 0.8},
                linewidths=1, linecolor='white', square=False, mask=mask,
                annot_kws={'fontsize': 12, 'fontweight': 'bold'})
    
    plt.title('Performance Heatmap: Execution Time by Scenario and Cache Mode', 
              fontsize=16, fontweight='bold', pad=20)
    plt.xlabel('Cache Mode', fontweight='bold', fontsize=12)
    plt.ylabel('Test Scenario', fontweight='bold', fontsize=12)
    plt.xticks(rotation=0, fontsize=11)
    plt.yticks(rotation=0, fontsize=10)
    
    plt.tight_layout()
    plt.savefig('performance_heatmap.png', dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()

def create_scalability_analysis(df):
    """Create scalability analysis charts"""
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    fig.suptitle('Scalability Analysis: Performance vs Data Size', 
                 fontsize=16, fontweight='bold', y=1.02)
    
    colors_dict = {'none': '#FF6B6B', 'fifo': '#4ECDC4', 'lru': '#45B7D1'}
    markers = {'none': 'o', 'fifo': 's', 'lru': '^'}
    
    # 1. Execution Time vs Data Size
    ax1 = axes[0]
    for cache_mode in df['cache_mode'].unique():
        cache_data = df[df['cache_mode'] == cache_mode].sort_values('data_size')
        ax1.plot(cache_data['data_size'], cache_data['avg_execution_time'], 
                marker=markers[cache_mode], linewidth=3, markersize=10, 
                label=cache_mode.upper(), color=colors_dict[cache_mode], alpha=0.8)
    
    ax1.set_title('Execution Time vs Data Size', fontweight='bold', pad=15)
    ax1.set_xlabel('Data Size (records)', fontweight='bold')
    ax1.set_ylabel('Execution Time (seconds)', fontweight='bold')
    ax1.legend(framealpha=0.9, fontsize=11)
    ax1.grid(True, alpha=0.3)
    
    # 2. Memory Usage vs Data Size
    ax2 = axes[1]
    for cache_mode in df['cache_mode'].unique():
        cache_data = df[df['cache_mode'] == cache_mode].sort_values('data_size')
        ax2.plot(cache_data['data_size'], cache_data['max_memory'], 
                marker=markers[cache_mode], linewidth=3, markersize=10, 
                label=cache_mode.upper(), color=colors_dict[cache_mode], alpha=0.8)
    
    ax2.set_title('Memory Usage vs Data Size', fontweight='bold', pad=15)
    ax2.set_xlabel('Data Size (records)', fontweight='bold')
    ax2.set_ylabel('Max Memory Usage (MB)', fontweight='bold')
    ax2.legend(framealpha=0.9, fontsize=11)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('scalability_analysis.png', dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()

def generate_performance_analysis(df):
    """Generate comprehensive performance analysis"""
    # Get performance metrics
    perf_by_mode = df.groupby('cache_mode')['avg_execution_time'].mean()
    memory_by_mode = df.groupby('cache_mode')['memory_increase'].mean()
    cache_efficiency = df[df['cache_mode'] != 'none'].groupby('cache_mode')['cache_hit_rate'].mean()
    
    # Create summary table
    summary_stats = []
    for cache_mode in df['cache_mode'].unique():
        cache_data = df[df['cache_mode'] == cache_mode]
        
        stats = {
            'Cache Mode': cache_mode.upper(),
            'Avg Execution Time (s)': f"{cache_data['avg_execution_time'].mean():.3f}",
            'Min Execution Time (s)': f"{cache_data['avg_execution_time'].min():.3f}",
            'Max Execution Time (s)': f"{cache_data['avg_execution_time'].max():.3f}",
            'Std Deviation (s)': f"{cache_data['avg_execution_time'].std():.3f}",
            'Avg Memory Increase (MB)': f"{cache_data['memory_increase'].mean():.2f}",
            'Cache Hit Rate (%)': f"{cache_data['cache_hit_rate'].mean():.1f}" if cache_mode != 'none' else 'N/A'
        }
        summary_stats.append(stats)
    
    summary_df = pd.DataFrame(summary_stats)
    
    # Create styled table visualization
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.axis('tight')
    ax.axis('off')
    
    table = ax.table(cellText=summary_df.values, colLabels=summary_df.columns,
                    cellLoc='center', loc='center', bbox=[0, 0, 1, 1])
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 2.5)
    
    # Style the table
    for (i, j), cell in table.get_celld().items():
        if i == 0:  # Header row
            cell.set_text_props(weight='bold', color='white')
            cell.set_facecolor('#2C3E50')
        else:
            if i == 1:  # NONE row
                cell.set_facecolor('#FFE5E5')
            elif i == 2:  # FIFO row
                cell.set_facecolor('#E5F7F5')
            else:  # LRU row
                cell.set_facecolor('#E5F3FF')
            
            if j == 0:  # First column
                cell.set_text_props(weight='bold')
    
    plt.title('Comprehensive Performance Summary Table', 
              fontsize=16, fontweight='bold', pad=30)
    plt.savefig('performance_summary_table.png', dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()
    
    # Save summary to CSV
    summary_df.to_csv('performance_summary.csv', index=False)
    
    # Print analysis results
    print("\n" + "="*80)
    print("PERFORMANCE IMPROVEMENT ANALYSIS")
    print("="*80)
    
    print(f"\nEXECUTION TIME COMPARISON:")
    print("-" * 40)
    
    if 'none' in perf_by_mode.index:
        baseline = perf_by_mode['none']
        print(f"Baseline (No Caching): {baseline:.3f}s")
        
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
    
    print(f"\nMEMORY USAGE ANALYSIS:")
    print("-" * 40)
    for mode, memory in memory_by_mode.items():
        print(f"{mode.upper():<12}: {memory:.2f} MB average increase")
    
    if len(cache_efficiency) > 0:
        print(f"\nCACHE HIT RATES:")
        print("-" * 40)
        for mode, hit_rate in cache_efficiency.items():
            print(f"{mode.upper():<12}: {hit_rate:.1f}%")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    success = main()
    if success:
        print("\n📁 Generated Files:")
        print("   ✅ performance_comparison_dashboard.png")
        print("   ✅ performance_heatmap.png") 
        print("   ✅ scalability_analysis.png")
        print("   ✅ performance_summary_table.png")
        print("   ✅ performance_summary.csv")
        print("\n🎉 All visualizations created successfully!")
    else:
        print("\n❌ Visualization generation failed!")
        sys.exit(1)
