#!/usr/bin/env python3
"""
Create comprehensive visualizations for MATCH_RECOGNIZE caching strategy performance analysis.

This script generates multiple types of charts and graphs to visualize the performance
comparison between No Cache, FIFO Cache, and LRU Cache strategies.

Author: Performance Testing Team
Version: 1.0.0
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import json
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# Set style for professional-looking plots
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")

def load_performance_data():
    """Load the performance data from CSV and JSON files."""
    results_dir = Path("tests/performance/results")
    
    # Load detailed results
    df = pd.read_csv(results_dir / "detailed_performance_results.csv")
    
    # Load summary statistics
    with open(results_dir / "performance_summary.json", 'r') as f:
        summary = json.load(f)
    
    return df, summary

def create_execution_time_comparison(df: pd.DataFrame, output_dir: Path):
    """Create execution time comparison charts."""
    
    # 1. Bar chart comparing average execution times by strategy
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Average execution time by strategy
    strategy_avg = df.groupby('Caching_Strategy')['Execution_Time_ms'].mean()
    colors = ['#ff7f7f', '#7fbf7f', '#7f7fff']  # Red, Green, Blue
    bars1 = ax1.bar(strategy_avg.index, strategy_avg.values, color=colors, alpha=0.8)
    ax1.set_title('Average Execution Time by Caching Strategy', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Execution Time (ms)', fontsize=12)
    ax1.set_xlabel('Caching Strategy', fontsize=12)
    
    # Add value labels on bars
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + 5,
                f'{height:.1f}ms', ha='center', va='bottom', fontweight='bold')
    
    # Execution time by dataset size and strategy
    pivot_data = df.pivot_table(values='Execution_Time_ms', 
                               index='Dataset_Size_Name', 
                               columns='Caching_Strategy', 
                               aggfunc='mean')
    
    pivot_data.plot(kind='bar', ax=ax2, color=colors, alpha=0.8)
    ax2.set_title('Execution Time by Dataset Size', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Execution Time (ms)', fontsize=12)
    ax2.set_xlabel('Dataset Size', fontsize=12)
    ax2.legend(title='Caching Strategy', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.tick_params(axis='x', rotation=0)
    
    plt.tight_layout()
    plt.savefig(output_dir / "execution_time_comparison.png", dpi=300, bbox_inches='tight')
    plt.close()

def create_performance_improvement_chart(df: pd.DataFrame, output_dir: Path):
    """Create performance improvement visualization."""
    
    # Calculate performance improvements
    baseline_data = df[df['Caching_Strategy'] == 'NO_CACHE'].set_index(['Dataset_Size_Name', 'Pattern_Complexity'])
    
    improvements = []
    for _, row in df.iterrows():
        if row['Caching_Strategy'] != 'NO_CACHE':
            baseline_time = baseline_data.loc[(row['Dataset_Size_Name'], row['Pattern_Complexity']), 'Execution_Time_ms']
            improvement = ((baseline_time - row['Execution_Time_ms']) / baseline_time) * 100
            improvements.append({
                'Dataset_Size': row['Dataset_Size_Name'],
                'Pattern_Complexity': row['Pattern_Complexity'],
                'Strategy': row['Caching_Strategy'],
                'Improvement_Percent': improvement
            })
    
    improvement_df = pd.DataFrame(improvements)
    
    # Create heatmap
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # FIFO improvements
    fifo_pivot = improvement_df[improvement_df['Strategy'] == 'FIFO'].pivot(
        index='Pattern_Complexity', columns='Dataset_Size', values='Improvement_Percent')
    sns.heatmap(fifo_pivot, annot=True, fmt='.1f', cmap='Greens', ax=ax1, 
                cbar_kws={'label': 'Performance Improvement (%)'})
    ax1.set_title('FIFO Cache Performance Improvement vs No Cache', fontsize=14, fontweight='bold')
    ax1.set_xlabel('Dataset Size', fontsize=12)
    ax1.set_ylabel('Pattern Complexity', fontsize=12)
    
    # LRU improvements
    lru_pivot = improvement_df[improvement_df['Strategy'] == 'LRU'].pivot(
        index='Pattern_Complexity', columns='Dataset_Size', values='Improvement_Percent')
    sns.heatmap(lru_pivot, annot=True, fmt='.1f', cmap='Blues', ax=ax2,
                cbar_kws={'label': 'Performance Improvement (%)'})
    ax2.set_title('LRU Cache Performance Improvement vs No Cache', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Dataset Size', fontsize=12)
    ax2.set_ylabel('Pattern Complexity', fontsize=12)
    
    plt.tight_layout()
    plt.savefig(output_dir / "performance_improvement_heatmap.png", dpi=300, bbox_inches='tight')
    plt.close()

def create_memory_usage_analysis(df: pd.DataFrame, output_dir: Path):
    """Create memory usage analysis charts."""
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Memory usage by strategy
    strategy_memory = df.groupby('Caching_Strategy')['Memory_Usage_MB'].mean()
    colors = ['#ff7f7f', '#7fbf7f', '#7f7fff']
    bars1 = ax1.bar(strategy_memory.index, strategy_memory.values, color=colors, alpha=0.8)
    ax1.set_title('Average Memory Usage by Caching Strategy', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Memory Usage (MB)', fontsize=12)
    ax1.set_xlabel('Caching Strategy', fontsize=12)
    
    # Add value labels
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + 2,
                f'{height:.1f}MB', ha='center', va='bottom', fontweight='bold')
    
    # Memory scaling by dataset size
    memory_scaling = df.groupby(['Dataset_Size_Name', 'Caching_Strategy'])['Memory_Usage_MB'].mean().unstack()
    memory_scaling.plot(kind='line', ax=ax2, marker='o', linewidth=2, markersize=8, color=colors)
    ax2.set_title('Memory Usage Scaling by Dataset Size', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Memory Usage (MB)', fontsize=12)
    ax2.set_xlabel('Dataset Size', fontsize=12)
    ax2.legend(title='Caching Strategy', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / "memory_usage_analysis.png", dpi=300, bbox_inches='tight')
    plt.close()

def create_cache_hit_rate_analysis(df: pd.DataFrame, output_dir: Path):
    """Create cache hit rate analysis charts."""
    
    # Filter out NO_CACHE strategy (has 0% hit rate)
    cache_df = df[df['Caching_Strategy'] != 'NO_CACHE']
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Average hit rates by strategy
    hit_rates = cache_df.groupby('Caching_Strategy')['Cache_Hit_Rate'].mean()
    colors = ['#7fbf7f', '#7f7fff']  # Green for FIFO, Blue for LRU
    bars1 = ax1.bar(hit_rates.index, hit_rates.values, color=colors, alpha=0.8)
    ax1.set_title('Average Cache Hit Rate by Strategy', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Cache Hit Rate (%)', fontsize=12)
    ax1.set_xlabel('Caching Strategy', fontsize=12)
    ax1.set_ylim(0, 100)
    
    # Add value labels
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + 1,
                f'{height:.1f}%', ha='center', va='bottom', fontweight='bold')
    
    # Hit rate distribution by complexity and dataset size
    sns.boxplot(data=cache_df, x='Pattern_Complexity', y='Cache_Hit_Rate', 
                hue='Caching_Strategy', ax=ax2, palette=['#7fbf7f', '#7f7fff'])
    ax2.set_title('Cache Hit Rate Distribution by Pattern Complexity', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Cache Hit Rate (%)', fontsize=12)
    ax2.set_xlabel('Pattern Complexity', fontsize=12)
    ax2.legend(title='Caching Strategy')
    
    plt.tight_layout()
    plt.savefig(output_dir / "cache_hit_rate_analysis.png", dpi=300, bbox_inches='tight')
    plt.close()

def create_comprehensive_comparison(df: pd.DataFrame, summary: Dict, output_dir: Path):
    """Create a comprehensive comparison dashboard."""
    
    fig = plt.figure(figsize=(20, 12))
    
    # Create a 3x3 grid
    gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
    
    # 1. Overall performance summary (top left)
    ax1 = fig.add_subplot(gs[0, 0])
    strategies = list(summary['strategy_performance'].keys())
    exec_times = [summary['strategy_performance'][s]['avg_execution_time_ms'] for s in strategies]
    colors = ['#ff7f7f', '#7fbf7f', '#7f7fff']
    bars = ax1.bar(strategies, exec_times, color=colors, alpha=0.8)
    ax1.set_title('Average Execution Time', fontweight='bold')
    ax1.set_ylabel('Time (ms)')
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + 5,
                f'{height:.1f}', ha='center', va='bottom', fontsize=10)
    
    # 2. Memory usage comparison (top center)
    ax2 = fig.add_subplot(gs[0, 1])
    memory_usage = [summary['strategy_performance'][s]['avg_memory_usage_mb'] for s in strategies]
    bars = ax2.bar(strategies, memory_usage, color=colors, alpha=0.8)
    ax2.set_title('Average Memory Usage', fontweight='bold')
    ax2.set_ylabel('Memory (MB)')
    for bar in bars:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + 2,
                f'{height:.1f}', ha='center', va='bottom', fontsize=10)
    
    # 3. Cache hit rates (top right)
    ax3 = fig.add_subplot(gs[0, 2])
    hit_rates = [summary['strategy_performance'][s]['avg_cache_hit_rate'] for s in strategies]
    bars = ax3.bar(strategies, hit_rates, color=colors, alpha=0.8)
    ax3.set_title('Average Cache Hit Rate', fontweight='bold')
    ax3.set_ylabel('Hit Rate (%)')
    ax3.set_ylim(0, 100)
    for bar in bars:
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height + 1,
                f'{height:.1f}%', ha='center', va='bottom', fontsize=10)
    
    # 4. Performance by dataset size (middle row, spanning 2 columns)
    ax4 = fig.add_subplot(gs[1, :2])
    pivot_data = df.pivot_table(values='Execution_Time_ms', 
                               index='Dataset_Size_Name', 
                               columns='Caching_Strategy', 
                               aggfunc='mean')
    pivot_data.plot(kind='line', ax=ax4, marker='o', linewidth=3, markersize=8, color=colors)
    ax4.set_title('Execution Time Scaling by Dataset Size', fontweight='bold')
    ax4.set_ylabel('Execution Time (ms)')
    ax4.set_xlabel('Dataset Size')
    ax4.legend(title='Strategy')
    ax4.grid(True, alpha=0.3)
    
    # 5. Performance improvement percentages (middle right)
    ax5 = fig.add_subplot(gs[1, 2])
    baseline_avg = summary['strategy_performance']['NO_CACHE']['avg_execution_time_ms']
    fifo_improvement = ((baseline_avg - summary['strategy_performance']['FIFO']['avg_execution_time_ms']) / baseline_avg) * 100
    lru_improvement = ((baseline_avg - summary['strategy_performance']['LRU']['avg_execution_time_ms']) / baseline_avg) * 100
    
    improvements = [0, fifo_improvement, lru_improvement]
    bars = ax5.bar(strategies, improvements, color=colors, alpha=0.8)
    ax5.set_title('Performance Improvement vs Baseline', fontweight='bold')
    ax5.set_ylabel('Improvement (%)')
    for i, bar in enumerate(bars):
        height = bar.get_height()
        ax5.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                f'{height:.1f}%', ha='center', va='bottom', fontsize=10)
    
    # 6. Pattern complexity analysis (bottom row, spanning all columns)
    ax6 = fig.add_subplot(gs[2, :])
    complexity_data = df.groupby(['Pattern_Complexity', 'Caching_Strategy'])['Execution_Time_ms'].mean().unstack()
    complexity_data.plot(kind='bar', ax=ax6, color=colors, alpha=0.8, width=0.8)
    ax6.set_title('Performance by Pattern Complexity', fontweight='bold')
    ax6.set_ylabel('Execution Time (ms)')
    ax6.set_xlabel('Pattern Complexity')
    ax6.legend(title='Caching Strategy', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax6.tick_params(axis='x', rotation=0)
    
    plt.suptitle('MATCH_RECOGNIZE Caching Strategy Performance Dashboard', 
                 fontsize=16, fontweight='bold', y=0.98)
    
    plt.savefig(output_dir / "comprehensive_performance_dashboard.png", dpi=300, bbox_inches='tight')
    plt.close()

def create_scaling_analysis(df: pd.DataFrame, output_dir: Path):
    """Create scaling analysis visualization."""
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. Execution time scaling
    for strategy in df['Caching_Strategy'].unique():
        strategy_data = df[df['Caching_Strategy'] == strategy]
        scaling_data = strategy_data.groupby('Dataset_Size')['Execution_Time_ms'].mean()
        ax1.plot(scaling_data.index, scaling_data.values, marker='o', linewidth=2, 
                label=strategy, markersize=8)
    
    ax1.set_title('Execution Time Scaling', fontweight='bold')
    ax1.set_xlabel('Dataset Size (rows)')
    ax1.set_ylabel('Execution Time (ms)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. Memory scaling
    for strategy in df['Caching_Strategy'].unique():
        strategy_data = df[df['Caching_Strategy'] == strategy]
        scaling_data = strategy_data.groupby('Dataset_Size')['Memory_Usage_MB'].mean()
        ax2.plot(scaling_data.index, scaling_data.values, marker='s', linewidth=2, 
                label=strategy, markersize=8)
    
    ax2.set_title('Memory Usage Scaling', fontweight='bold')
    ax2.set_xlabel('Dataset Size (rows)')
    ax2.set_ylabel('Memory Usage (MB)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. Performance efficiency (time per 1000 rows)
    df['Efficiency'] = df['Execution_Time_ms'] / (df['Dataset_Size'] / 1000)
    efficiency_data = df.groupby(['Dataset_Size_Name', 'Caching_Strategy'])['Efficiency'].mean().unstack()
    efficiency_data.plot(kind='bar', ax=ax3, alpha=0.8)
    ax3.set_title('Performance Efficiency (ms per 1K rows)', fontweight='bold')
    ax3.set_ylabel('Time per 1K rows (ms)')
    ax3.set_xlabel('Dataset Size')
    ax3.legend(title='Strategy')
    ax3.tick_params(axis='x', rotation=0)
    
    # 4. Cache effectiveness scaling
    cache_df = df[df['Caching_Strategy'] != 'NO_CACHE']
    cache_scaling = cache_df.groupby(['Dataset_Size_Name', 'Caching_Strategy'])['Cache_Hit_Rate'].mean().unstack()
    cache_scaling.plot(kind='line', ax=ax4, marker='o', linewidth=2, markersize=8)
    ax4.set_title('Cache Hit Rate Scaling', fontweight='bold')
    ax4.set_ylabel('Cache Hit Rate (%)')
    ax4.set_xlabel('Dataset Size')
    ax4.legend(title='Strategy')
    ax4.grid(True, alpha=0.3)
    ax4.set_ylim(0, 100)
    
    plt.tight_layout()
    plt.savefig(output_dir / "scaling_analysis.png", dpi=300, bbox_inches='tight')
    plt.close()

def main():
    """Generate all visualizations."""
    print("Creating MATCH_RECOGNIZE caching strategy performance visualizations...")
    
    # Create output directory
    output_dir = Path("tests/performance/results/visualizations")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    try:
        df, summary = load_performance_data()
        print(f"Loaded data: {len(df)} test cases")
    except Exception as e:
        print(f"Error loading data: {e}")
        return 1
    
    # Generate visualizations
    visualizations = [
        ("Execution Time Comparison", create_execution_time_comparison),
        ("Performance Improvement Analysis", create_performance_improvement_chart),
        ("Memory Usage Analysis", create_memory_usage_analysis),
        ("Cache Hit Rate Analysis", create_cache_hit_rate_analysis),
        ("Comprehensive Dashboard", create_comprehensive_comparison),
        ("Scaling Analysis", create_scaling_analysis)
    ]
    
    for name, func in visualizations:
        try:
            print(f"Creating {name}...")
            if func == create_comprehensive_comparison:
                func(df, summary, output_dir)
            else:
                func(df, output_dir)
            print(f"✅ {name} completed")
        except Exception as e:
            print(f"❌ Error creating {name}: {e}")
    
    print(f"\n📊 All visualizations saved to: {output_dir}")
    print("\nGenerated files:")
    for file in sorted(output_dir.glob("*.png")):
        print(f"  - {file.name}")
    
    return 0

if __name__ == "__main__":
    exit(main())
