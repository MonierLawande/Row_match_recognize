#!/usr/bin/env python3
"""
MATCH_RECOGNIZE Combined Analysis: Performance by Pattern Complexity & Memory Usage Scaling

This script creates a combined visualization showing both performance by pattern 
complexity and memory usage scaling in a single professional image.

Author: Performance Analysis Team
Version: 1.0.0 - Combined Analysis
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Set professional style
plt.style.use('seaborn-v0_8-whitegrid')

def create_performance_data():
    """Create the performance dataset from the provided tables."""
    
    # Performance data from the detailed table
    performance_data = [
        # Dataset Size, Pattern, No Cache, FIFO, LRU
        (1000, 'SIMPLE', 46.1, 34.1, 30.6),
        (1000, 'MEDIUM', 80.7, 56.8, 53.1),
        (1000, 'COMPLEX', 134.9, 93.2, 85.4),
        (2000, 'SIMPLE', 87.3, 61.5, 58.8),
        (2000, 'MEDIUM', 146.8, 110.6, 94.6),
        (2000, 'COMPLEX', 238.1, 180.2, 169.3),
        (4000, 'SIMPLE', 157.5, 130.1, 112.7),
        (4000, 'MEDIUM', 281.8, 210.4, 190.6),
        (4000, 'COMPLEX', 471.8, 355.0, 334.7),
        (5000, 'SIMPLE', 208.8, 144.6, 137.8),
        (5000, 'MEDIUM', 344.3, 265.3, 237.3),
        (5000, 'COMPLEX', 573.0, 439.1, 419.7),
    ]
    
    # Memory data from the memory table
    memory_data = [
        # Dataset Size, Pattern, No Cache, FIFO, LRU, FIFO Hit Rate, LRU Hit Rate
        (1000, 'SIMPLE', 8.3, 27.3, 32.3, 59.1, 82.7),
        (1000, 'MEDIUM', 7.9, 28.1, 33.5, 67.2, 78.3),
        (1000, 'COMPLEX', 7.8, 27.3, 33.5, 64.1, 72.0),
        (2000, 'SIMPLE', 15.8, 56.5, 66.9, 63.6, 82.4),
        (2000, 'MEDIUM', 15.1, 56.2, 67.7, 59.7, 76.5),
        (2000, 'COMPLEX', 16.2, 56.3, 67.5, 63.0, 76.4),
        (4000, 'SIMPLE', 32.7, 111.6, 134.1, 67.8, 80.9),
        (4000, 'MEDIUM', 31.3, 112.5, 133.7, 66.0, 76.8),
        (4000, 'COMPLEX', 31.4, 111.5, 134.4, 64.4, 78.8),
        (5000, 'SIMPLE', 39.9, 140.7, 167.8, 67.4, 73.8),
        (5000, 'MEDIUM', 40.0, 140.2, 167.9, 68.0, 75.6),
        (5000, 'COMPLEX', 39.4, 140.8, 168.1, 66.1, 83.7),
    ]
    
    # Create DataFrames
    perf_df = pd.DataFrame(performance_data, 
                          columns=['Dataset_Size', 'Pattern', 'No_Cache', 'FIFO', 'LRU'])
    
    memory_df = pd.DataFrame(memory_data,
                            columns=['Dataset_Size', 'Pattern', 'No_Cache_Mem', 'FIFO_Mem', 
                                   'LRU_Mem', 'FIFO_Hit_Rate', 'LRU_Hit_Rate'])
    
    # Merge the dataframes
    df = pd.merge(perf_df, memory_df, on=['Dataset_Size', 'Pattern'])
    
    return df

def create_combined_complexity_memory_chart():
    """Create combined Performance by Pattern Complexity and Memory Usage Scaling chart."""
    
    df = create_performance_data()
    
    # Define colors for consistency
    colors = {
        'No_Cache': '#e74c3c',    # Red
        'FIFO': '#f39c12',        # Orange  
        'LRU': '#27ae60',         # Green
    }
    
    # Create the figure with two subplots side by side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    
    # 1. Performance by Pattern Complexity (left)
    complexity_order = ['SIMPLE', 'MEDIUM', 'COMPLEX']
    perf_by_complexity = df.groupby('Pattern')[['No_Cache', 'FIFO', 'LRU']].mean().reindex(complexity_order)
    
    x = np.arange(len(complexity_order))
    width = 0.25
    
    bars1 = ax1.bar(x - width, perf_by_complexity['No_Cache'], width, 
                    label='No Cache', color=colors['No_Cache'], alpha=0.8, edgecolor='white', linewidth=1.5)
    bars2 = ax1.bar(x, perf_by_complexity['FIFO'], width, 
                    label='FIFO Cache', color=colors['FIFO'], alpha=0.8, edgecolor='white', linewidth=1.5)
    bars3 = ax1.bar(x + width, perf_by_complexity['LRU'], width, 
                    label='LRU Cache', color=colors['LRU'], alpha=0.8, edgecolor='white', linewidth=1.5)
    
    # Add value labels on bars with better positioning
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height + 8,
                    f'{height:.0f}ms', ha='center', va='bottom', 
                    fontsize=11, fontweight='bold', color='black')
    
    # Add improvement percentages
    for i, complexity in enumerate(complexity_order):
        no_cache_val = perf_by_complexity.loc[complexity, 'No_Cache']
        lru_val = perf_by_complexity.loc[complexity, 'LRU']
        improvement = ((no_cache_val - lru_val) / no_cache_val) * 100
        
        # Add improvement annotation above LRU bar
        ax1.annotate(f'{improvement:.1f}%\nimprovement', 
                    xy=(i + width, lru_val), xytext=(i + width, lru_val + 40),
                    ha='center', va='bottom', fontsize=10, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=colors['LRU'], alpha=0.7),
                    arrowprops=dict(arrowstyle='->', color=colors['LRU'], lw=1.5))
    
    ax1.set_title('Performance by Pattern Complexity\nExecution Time Analysis', 
                  fontsize=16, fontweight='bold', pad=20)
    ax1.set_xlabel('Pattern Complexity Level', fontsize=13, fontweight='bold')
    ax1.set_ylabel('Average Execution Time (ms)', fontsize=13, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(complexity_order, fontsize=12)
    ax1.legend(fontsize=11, loc='upper left', frameon=True, fancybox=True, shadow=True)
    ax1.grid(True, alpha=0.3, axis='y')
    ax1.set_ylim(0, max(perf_by_complexity.max()) * 1.3)
    
    # 2. Memory Usage Scaling (right)
    sizes = sorted(df['Dataset_Size'].unique())
    memory_by_size = df.groupby('Dataset_Size')[['No_Cache_Mem', 'FIFO_Mem', 'LRU_Mem']].mean()
    
    # Plot lines with enhanced styling
    ax2.plot(sizes, memory_by_size['No_Cache_Mem'], 'o-', color=colors['No_Cache'], 
             linewidth=4, markersize=10, label='No Cache', markerfacecolor='white', 
             markeredgewidth=3, markeredgecolor=colors['No_Cache'])
    ax2.plot(sizes, memory_by_size['FIFO_Mem'], 's-', color=colors['FIFO'], 
             linewidth=4, markersize=10, label='FIFO Cache', markerfacecolor='white',
             markeredgewidth=3, markeredgecolor=colors['FIFO'])
    ax2.plot(sizes, memory_by_size['LRU_Mem'], '^-', color=colors['LRU'], 
             linewidth=4, markersize=10, label='LRU Cache', markerfacecolor='white',
             markeredgewidth=3, markeredgecolor=colors['LRU'])
    
    # Add memory overhead annotations
    for i, size in enumerate(sizes):
        no_cache_mem = memory_by_size.loc[size, 'No_Cache_Mem']
        lru_mem = memory_by_size.loc[size, 'LRU_Mem']
        overhead = lru_mem / no_cache_mem
        
        if i % 2 == 0:  # Annotate every other point to avoid crowding
            ax2.annotate(f'{overhead:.1f}×\noverhead', 
                        xy=(size, lru_mem), xytext=(size, lru_mem + 15),
                        ha='center', va='bottom', fontsize=9, fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor=colors['LRU'], alpha=0.7),
                        arrowprops=dict(arrowstyle='->', color=colors['LRU'], lw=1))
    
    ax2.set_title('Memory Usage Scaling\nMemory Consumption vs Dataset Size', 
                  fontsize=16, fontweight='bold', pad=20)
    ax2.set_xlabel('Dataset Size (records)', fontsize=13, fontweight='bold')
    ax2.set_ylabel('Memory Usage (MB)', fontsize=13, fontweight='bold')
    ax2.legend(fontsize=11, loc='upper left', frameon=True, fancybox=True, shadow=True)
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(sizes)
    ax2.set_xticklabels([f'{int(s/1000)}K' for s in sizes], fontsize=12)
    
    # Add trend line for LRU to show linear scaling
    from scipy import stats
    slope, intercept, r_value, p_value, std_err = stats.linregress(sizes, memory_by_size['LRU_Mem'])
    line_x = np.array(sizes)
    line_y = slope * line_x + intercept
    ax2.plot(line_x, line_y, '--', color=colors['LRU'], linewidth=2, alpha=0.6)
    
    # Add R² annotation for memory scaling
    ax2.text(0.05, 0.95, f'LRU Memory Scaling\nR² = {r_value**2:.4f}\nLinear: y = {slope:.2f}x + {intercept:.1f}', 
             transform=ax2.transAxes, fontsize=10, fontweight='bold',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8),
             verticalalignment='top')
    
    # Add overall title
    fig.suptitle('MATCH_RECOGNIZE Caching Strategy Analysis\nPattern Complexity Performance & Memory Usage Scaling', 
                 fontsize=18, fontweight='bold', y=0.98)
    
    # Add summary statistics box
    fig.text(0.5, 0.02, 
             'Key Findings: LRU Cache delivers 30.6% average improvement with 4.2× memory overhead • ' +
             'Performance scales consistently across complexity levels • Memory usage shows perfect linear scaling (R² > 0.99)',
             ha='center', va='bottom', fontsize=11, fontweight='bold',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='wheat', alpha=0.9))
    
    # Adjust layout
    plt.tight_layout()
    plt.subplots_adjust(top=0.88, bottom=0.15)
    
    # Save the figure
    plt.savefig('match_recognize_complexity_memory_analysis.png', dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    
    print("✅ Combined complexity and memory analysis created: match_recognize_complexity_memory_analysis.png")

def create_enhanced_combined_chart():
    """Create an enhanced version with additional insights."""
    
    df = create_performance_data()
    
    # Create figure with custom layout
    fig = plt.figure(figsize=(18, 10))
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3, height_ratios=[3, 1])
    
    # Define colors
    colors = {'No_Cache': '#e74c3c', 'FIFO': '#f39c12', 'LRU': '#27ae60'}
    
    # 1. Performance by Pattern Complexity (top left)
    ax1 = fig.add_subplot(gs[0, 0])
    
    complexity_order = ['SIMPLE', 'MEDIUM', 'COMPLEX']
    perf_by_complexity = df.groupby('Pattern')[['No_Cache', 'FIFO', 'LRU']].mean().reindex(complexity_order)
    
    x = np.arange(len(complexity_order))
    width = 0.25
    
    bars1 = ax1.bar(x - width, perf_by_complexity['No_Cache'], width, 
                    label='No Cache', color=colors['No_Cache'], alpha=0.8)
    bars2 = ax1.bar(x, perf_by_complexity['FIFO'], width, 
                    label='FIFO Cache', color=colors['FIFO'], alpha=0.8)
    bars3 = ax1.bar(x + width, perf_by_complexity['LRU'], width, 
                    label='LRU Cache', color=colors['LRU'], alpha=0.8)
    
    # Add value labels
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height + 5,
                    f'{height:.0f}ms', ha='center', va='bottom', 
                    fontsize=10, fontweight='bold')
    
    ax1.set_title('Performance by Pattern Complexity', fontsize=14, fontweight='bold')
    ax1.set_xlabel('Pattern Complexity', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Avg Execution Time (ms)', fontsize=12, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(complexity_order)
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3, axis='y')
    
    # 2. Memory Usage Scaling (top center)
    ax2 = fig.add_subplot(gs[0, 1])
    
    sizes = sorted(df['Dataset_Size'].unique())
    memory_by_size = df.groupby('Dataset_Size')[['No_Cache_Mem', 'FIFO_Mem', 'LRU_Mem']].mean()
    
    ax2.plot(sizes, memory_by_size['No_Cache_Mem'], 'o-', color=colors['No_Cache'], 
             linewidth=3, markersize=8, label='No Cache')
    ax2.plot(sizes, memory_by_size['FIFO_Mem'], 's-', color=colors['FIFO'], 
             linewidth=3, markersize=8, label='FIFO Cache')
    ax2.plot(sizes, memory_by_size['LRU_Mem'], '^-', color=colors['LRU'], 
             linewidth=3, markersize=8, label='LRU Cache')
    
    ax2.set_title('Memory Usage Scaling', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Dataset Size (records)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Memory Usage (MB)', fontsize=12, fontweight='bold')
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(sizes)
    ax2.set_xticklabels([f'{int(s/1000)}K' for s in sizes])
    
    # 3. Performance Improvement Analysis (top right)
    ax3 = fig.add_subplot(gs[0, 2])
    
    # Calculate improvements by complexity
    improvements = []
    for complexity in complexity_order:
        complexity_data = perf_by_complexity.loc[complexity]
        fifo_imp = ((complexity_data['No_Cache'] - complexity_data['FIFO']) / complexity_data['No_Cache']) * 100
        lru_imp = ((complexity_data['No_Cache'] - complexity_data['LRU']) / complexity_data['No_Cache']) * 100
        improvements.append([complexity, fifo_imp, lru_imp])
    
    imp_df = pd.DataFrame(improvements, columns=['Complexity', 'FIFO_Improvement', 'LRU_Improvement'])
    
    x = np.arange(len(complexity_order))
    width = 0.35
    
    ax3.bar(x - width/2, imp_df['FIFO_Improvement'], width, 
            label='FIFO Improvement', color=colors['FIFO'], alpha=0.8)
    ax3.bar(x + width/2, imp_df['LRU_Improvement'], width, 
            label='LRU Improvement', color=colors['LRU'], alpha=0.8)
    
    # Add value labels
    for i, (fifo_val, lru_val) in enumerate(zip(imp_df['FIFO_Improvement'], imp_df['LRU_Improvement'])):
        ax3.text(i - width/2, fifo_val + 0.5, f'{fifo_val:.1f}%', 
                ha='center', va='bottom', fontsize=9, fontweight='bold')
        ax3.text(i + width/2, lru_val + 0.5, f'{lru_val:.1f}%', 
                ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax3.set_title('Performance Improvement by Complexity', fontsize=14, fontweight='bold')
    ax3.set_xlabel('Pattern Complexity', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Improvement (%)', fontsize=12, fontweight='bold')
    ax3.set_xticks(x)
    ax3.set_xticklabels(complexity_order)
    ax3.legend(fontsize=10)
    ax3.grid(True, alpha=0.3, axis='y')
    ax3.set_ylim(0, 40)
    
    # 4. Summary Statistics (bottom, spans all columns)
    ax4 = fig.add_subplot(gs[1, :])
    ax4.axis('off')
    

    
    # Main title
    fig.suptitle('MATCH_RECOGNIZE Comprehensive Analysis: Pattern Complexity & Memory Scaling\n' +
                 'Performance Validation with Cache Effectiveness Analysis', 
                 fontsize=16, fontweight='bold', y=0.95)
    
    # Save the enhanced figure
    plt.savefig('match_recognize_enhanced_complexity_memory_analysis.png', dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    
    print("✅ Enhanced complexity and memory analysis created: match_recognize_enhanced_complexity_memory_analysis.png")

def main():
    """Create combined complexity and memory analysis charts."""
    
    print("🚀 Creating Combined Pattern Complexity & Memory Usage Analysis...")
    print("=" * 70)
    
    # Create standard combined chart
    create_combined_complexity_memory_chart()
    
    # Create enhanced version with additional insights
    create_enhanced_combined_chart()
    
    print("\n✅ Combined analysis charts created successfully!")
    print("📊 Generated files:")
    print("   • match_recognize_complexity_memory_analysis.png (focused 2-panel)")
    print("   • match_recognize_enhanced_complexity_memory_analysis.png (comprehensive 4-panel)")
    
    print("\n🎯 Key Insights:")
    print("   • LRU shows consistent performance advantages across all complexity levels")
    print("   • Memory usage scales linearly and predictably with dataset size")
    print("   • Performance improvements are maintained regardless of pattern complexity")
    print("   • Memory overhead is justified by significant performance gains")
    
    return 0

if __name__ == "__main__":
    exit(main())
