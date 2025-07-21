#!/usr/bin/env python3
"""
Enhanced Visualization Generator for Pattern Benchmark Results
Creates additional specialized diagrams and charts
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import json
import os
from datetime import datetime

class EnhancedVisualizationGenerator:
    """Generate additional specialized visualizations"""
    
    def __init__(self):
        self.load_latest_data()
        self.setup_plotting()
    
    def load_latest_data(self):
        """Load the latest benchmark data"""
        json_files = [f for f in os.listdir('.') if f.startswith('enhanced_pattern_benchmark_') and f.endswith('.json')]
        
        if not json_files:
            raise FileNotFoundError("No enhanced pattern benchmark results found!")
        
        latest_file = max(json_files)
        print(f"Loading data from: {latest_file}")
        
        with open(latest_file, 'r') as f:
            data = json.load(f)
        
        self.df = pd.DataFrame(data['results'])
        self.successful_df = self.df[self.df['success'] == True]
        self.metadata = data['metadata']
        
        print(f"Loaded {len(self.successful_df)} successful results")
    
    def setup_plotting(self):
        """Setup plotting parameters"""
        plt.style.use('default')
        sns.set_palette("husl")
        self.colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']
        
    def create_performance_heatmap(self):
        """Create performance heatmap across dataset sizes and patterns"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # Execution time heatmap
        pivot_time = self.successful_df.pivot(index='pattern_type', 
                                             columns='dataset_size', 
                                             values='execution_time_seconds')
        
        sns.heatmap(np.log10(pivot_time + 1), annot=False, cmap='YlOrRd', ax=ax1, cbar_kws={'label': 'Log10(Time + 1)'})
        ax1.set_title('Execution Time Heatmap\\n(Log Scale)', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Dataset Size', fontsize=12)
        ax1.set_ylabel('Pattern Type', fontsize=12)
        
        # Memory usage heatmap
        pivot_memory = self.successful_df.pivot(index='pattern_type',
                                               columns='dataset_size',
                                               values='memory_usage_mb')
        
        sns.heatmap(pivot_memory, annot=False, cmap='Blues', ax=ax2, cbar_kws={'label': 'Memory (MB)'})
        ax2.set_title('Memory Usage Heatmap', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Dataset Size', fontsize=12)
        ax2.set_ylabel('Pattern Type', fontsize=12)
        
        plt.tight_layout()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'enhanced_performance_heatmap_{timestamp}.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.show()
        
        print(f"✓ Saved: {filename}")
        return filename
    
    def create_cache_analysis_charts(self):
        """Create detailed cache performance analysis"""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # Cache hit rate by pattern
        cache_rates = self.successful_df.groupby('pattern_type').apply(
            lambda x: (x['cache_status'] == 'HIT').sum() / len(x) * 100
        )
        
        bars1 = ax1.bar(cache_rates.index, cache_rates.values, color=self.colors)
        ax1.set_title('Cache Hit Rate by Pattern Type', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Cache Hit Rate (%)', fontsize=12)
        ax1.tick_params(axis='x', rotation=45)
        
        # Add value labels on bars
        for bar, value in zip(bars1, cache_rates.values):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                    f'{value:.1f}%', ha='center', va='bottom', fontweight='bold')
        
        # Performance improvement from cache hits
        cache_improvement = []
        pattern_names = []
        
        for pattern in self.successful_df['pattern_type'].unique():
            pattern_data = self.successful_df[self.successful_df['pattern_type'] == pattern]
            hit_data = pattern_data[pattern_data['cache_status'] == 'HIT']
            miss_data = pattern_data[pattern_data['cache_status'] == 'MISS']
            
            if len(hit_data) > 0 and len(miss_data) > 0:
                avg_hit_time = hit_data['execution_time_seconds'].mean()
                avg_miss_time = miss_data['execution_time_seconds'].mean()
                improvement = ((avg_miss_time - avg_hit_time) / avg_miss_time) * 100
                cache_improvement.append(improvement)
                pattern_names.append(pattern)
        
        if cache_improvement:
            bars2 = ax2.bar(pattern_names, cache_improvement, color=self.colors[:len(cache_improvement)])
            ax2.set_title('Performance Improvement from Cache Hits', fontsize=14, fontweight='bold')
            ax2.set_ylabel('Time Reduction (%)', fontsize=12)
            ax2.tick_params(axis='x', rotation=45)
            
            for bar, value in zip(bars2, cache_improvement):
                ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                        f'{value:.1f}%', ha='center', va='bottom', fontweight='bold')
        
        # Cache performance over dataset sizes
        for pattern in ['Simple', 'Medium', 'Complex']:
            pattern_data = self.successful_df[self.successful_df['pattern_type'] == pattern]
            if len(pattern_data) > 0:
                cache_by_size = pattern_data.groupby('dataset_size').apply(
                    lambda x: (x['cache_status'] == 'HIT').sum() / len(x) * 100
                )
                ax3.plot(cache_by_size.index, cache_by_size.values, 
                        marker='o', linewidth=2, label=pattern)
        
        ax3.set_title('Cache Hit Rate vs Dataset Size', fontsize=14, fontweight='bold')
        ax3.set_xlabel('Dataset Size', fontsize=12)
        ax3.set_ylabel('Cache Hit Rate (%)', fontsize=12)
        ax3.set_xscale('log')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # Memory efficiency by cache status
        hit_data = self.successful_df[self.successful_df['cache_status'] == 'HIT']
        miss_data = self.successful_df[self.successful_df['cache_status'] == 'MISS']
        
        ax4.hist([hit_data['memory_efficiency'], miss_data['memory_efficiency']], 
                bins=20, alpha=0.7, label=['Cache Hits', 'Cache Misses'], color=['green', 'red'])
        ax4.set_title('Memory Efficiency Distribution by Cache Status', fontsize=14, fontweight='bold')
        ax4.set_xlabel('Memory Efficiency (hits/MB)', fontsize=12)
        ax4.set_ylabel('Frequency', fontsize=12)
        ax4.legend()
        
        plt.tight_layout()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'enhanced_cache_analysis_{timestamp}.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.show()
        
        print(f"✓ Saved: {filename}")
        return filename
    
    def create_scalability_analysis(self):
        """Create scalability analysis charts"""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # Scaling factors
        scaling_data = []
        for pattern in self.successful_df['pattern_type'].unique():
            pattern_data = self.successful_df[self.successful_df['pattern_type'] == pattern].sort_values('dataset_size')
            if len(pattern_data) >= 2:
                first_time = pattern_data.iloc[0]['execution_time_seconds']
                last_time = pattern_data.iloc[-1]['execution_time_seconds']
                first_size = pattern_data.iloc[0]['dataset_size']
                last_size = pattern_data.iloc[-1]['dataset_size']
                
                size_ratio = last_size / first_size
                time_ratio = last_time / first_time
                scaling_factor = time_ratio / size_ratio
                
                scaling_data.append({
                    'pattern': pattern,
                    'scaling_factor': scaling_factor,
                    'time_ratio': time_ratio,
                    'size_ratio': size_ratio
                })
        
        if scaling_data:
            scaling_df = pd.DataFrame(scaling_data)
            bars1 = ax1.bar(scaling_df['pattern'], scaling_df['scaling_factor'], color=self.colors)
            ax1.set_title('Scaling Factor (Time Growth vs Size Growth)', fontsize=14, fontweight='bold')
            ax1.set_ylabel('Scaling Factor', fontsize=12)
            ax1.tick_params(axis='x', rotation=45)
            ax1.axhline(y=1, color='red', linestyle='--', alpha=0.7, label='Linear Scaling')
            ax1.legend()
            
            for bar, value in zip(bars1, scaling_df['scaling_factor']):
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, 
                        f'{value:.1f}x', ha='center', va='bottom', fontweight='bold')
        
        # Throughput degradation
        for pattern in ['Simple', 'Medium', 'Complex']:
            pattern_data = self.successful_df[self.successful_df['pattern_type'] == pattern].sort_values('dataset_size')
            if len(pattern_data) > 0:
                ax2.plot(pattern_data['dataset_size'], pattern_data['throughput_rows_per_sec'], 
                        marker='o', linewidth=2, label=pattern)
        
        ax2.set_title('Throughput vs Dataset Size', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Dataset Size', fontsize=12)
        ax2.set_ylabel('Throughput (rows/sec)', fontsize=12)
        ax2.set_xscale('log')
        ax2.set_yscale('log')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Memory efficiency trends
        for pattern in ['Simple', 'Medium', 'Complex']:
            pattern_data = self.successful_df[self.successful_df['pattern_type'] == pattern].sort_values('dataset_size')
            if len(pattern_data) > 0:
                ax3.plot(pattern_data['dataset_size'], pattern_data['memory_efficiency'], 
                        marker='s', linewidth=2, label=pattern)
        
        ax3.set_title('Memory Efficiency vs Dataset Size', fontsize=14, fontweight='bold')
        ax3.set_xlabel('Dataset Size', fontsize=12)
        ax3.set_ylabel('Memory Efficiency (hits/MB)', fontsize=12)
        ax3.set_xscale('log')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # Pattern complexity impact
        complexity_scores = self.successful_df.groupby('pattern_type')['complexity_score'].first()
        avg_times = self.successful_df.groupby('pattern_type')['execution_time_seconds'].mean()
        
        scatter = ax4.scatter(complexity_scores, np.log10(avg_times), 
                            s=100, c=self.colors[:len(complexity_scores)], alpha=0.7)
        
        # Add pattern labels
        for pattern, score, time in zip(complexity_scores.index, complexity_scores.values, avg_times.values):
            ax4.annotate(pattern, (score, np.log10(time)), 
                        xytext=(5, 5), textcoords='offset points', fontsize=10)
        
        ax4.set_title('Complexity vs Performance Impact', fontsize=14, fontweight='bold')
        ax4.set_xlabel('Pattern Complexity Score', fontsize=12)
        ax4.set_ylabel('Log10(Avg Execution Time)', fontsize=12)
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'enhanced_scalability_analysis_{timestamp}.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.show()
        
        print(f"✓ Saved: {filename}")
        return filename
    
    def create_executive_dashboard(self):
        """Create executive summary dashboard"""
        fig = plt.figure(figsize=(20, 12))
        gs = fig.add_gridspec(3, 4, hspace=0.3, wspace=0.3)
        
        fig.suptitle('Enhanced Pattern Performance Executive Dashboard', 
                     fontsize=20, fontweight='bold', y=0.98)
        
        # Key metrics panel
        ax1 = fig.add_subplot(gs[0, :2])
        ax1.axis('off')
        
        total_tests = len(self.successful_df)
        total_hits = self.successful_df['hits_found'].sum()
        cache_hit_rate = (self.successful_df['cache_status'] == 'HIT').sum() / total_tests * 100
        avg_time = self.successful_df['execution_time_seconds'].mean()
        
        metrics_text = f"""
PERFORMANCE METRICS SUMMARY
{'='*50}
Total Test Executions:     {total_tests:,}
Total Matches Found:       {total_hits:,}
Average Execution Time:    {avg_time:.1f} seconds
Overall Cache Hit Rate:    {cache_hit_rate:.1f}%
Dataset Size Range:        {self.successful_df['dataset_size'].min():,} - {self.successful_df['dataset_size'].max():,} rows
Pattern Types Tested:      {self.successful_df['pattern_type'].nunique()}
        """
        
        ax1.text(0.1, 0.9, metrics_text, fontsize=12, fontfamily='monospace',
                verticalalignment='top', transform=ax1.transAxes,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))
        
        # Pattern performance comparison
        ax2 = fig.add_subplot(gs[0, 2:])
        pattern_times = self.successful_df.groupby('pattern_type')['execution_time_seconds'].mean()
        bars = ax2.bar(range(len(pattern_times)), pattern_times.values, color=self.colors)
        ax2.set_title('Average Execution Time by Pattern', fontsize=14, fontweight='bold')
        ax2.set_ylabel('Execution Time (seconds)', fontsize=12)
        ax2.set_yscale('log')
        ax2.set_xticks(range(len(pattern_times)))
        ax2.set_xticklabels(pattern_times.index, rotation=45)
        
        # Throughput analysis
        ax3 = fig.add_subplot(gs[1, :2])
        for pattern in ['Simple', 'Medium', 'Complex']:
            pattern_data = self.successful_df[self.successful_df['pattern_type'] == pattern]
            if len(pattern_data) > 0:
                ax3.plot(pattern_data['dataset_size'], pattern_data['throughput_rows_per_sec'], 
                        marker='o', linewidth=2, label=pattern)
        
        ax3.set_title('Throughput Performance', fontsize=14, fontweight='bold')
        ax3.set_xlabel('Dataset Size', fontsize=12)
        ax3.set_ylabel('Throughput (rows/sec)', fontsize=12)
        ax3.set_xscale('log')
        ax3.set_yscale('log')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # Memory analysis
        ax4 = fig.add_subplot(gs[1, 2:])
        memory_by_pattern = self.successful_df.groupby('pattern_type')['memory_efficiency'].mean()
        bars = ax4.bar(range(len(memory_by_pattern)), memory_by_pattern.values, color=self.colors)
        ax4.set_title('Memory Efficiency by Pattern', fontsize=14, fontweight='bold')
        ax4.set_ylabel('Memory Efficiency (hits/MB)', fontsize=12)
        ax4.set_xticks(range(len(memory_by_pattern)))
        ax4.set_xticklabels(memory_by_pattern.index, rotation=45)
        
        # Recommendations panel
        ax5 = fig.add_subplot(gs[2, :])
        ax5.axis('off')
        
        recommendations = f"""
PERFORMANCE RECOMMENDATIONS
{'='*80}
🚀 OPTIMAL CONFIGURATIONS:
   • Best Overall: Simple patterns for datasets < 100K rows (avg: {self.successful_df[self.successful_df['pattern_type']=='Simple']['execution_time_seconds'].mean():.1f}s)
   • Cache Hit Rate: {cache_hit_rate:.1f}% overall (Simple: {(self.successful_df[(self.successful_df['pattern_type']=='Simple') & (self.successful_df['cache_status']=='HIT')].shape[0] / self.successful_df[self.successful_df['pattern_type']=='Simple'].shape[0] * 100):.1f}%)
   • Memory Efficiency: Simple patterns show {memory_by_pattern['Simple']:.1f} hits/MB vs {memory_by_pattern['Ultra Complex']:.1f} hits/MB for Ultra Complex

⚠️  PERFORMANCE CONSIDERATIONS:
   • Complex patterns scale poorly: {pattern_times['Ultra Complex'] / pattern_times['Simple']:.0f}x slower than Simple patterns
   • Large datasets (>250K rows) require careful pattern selection
   • Consider caching strategies for production deployments
        """
        
        ax5.text(0.05, 0.9, recommendations, fontsize=11, fontfamily='sans-serif',
                verticalalignment='top', transform=ax5.transAxes,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", alpha=0.8))
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'enhanced_executive_dashboard_{timestamp}.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight', facecolor='white')
        plt.show()
        
        print(f"✓ Saved: {filename}")
        return filename
    
    def generate_all_visualizations(self):
        """Generate all enhanced visualizations"""
        print("🎨 Generating Enhanced Visualizations...")
        print("=" * 50)
        
        visualizations = []
        
        try:
            visualizations.append(self.create_performance_heatmap())
            visualizations.append(self.create_cache_analysis_charts())
            visualizations.append(self.create_scalability_analysis())
            visualizations.append(self.create_executive_dashboard())
            
            print("\\n✅ All visualizations generated successfully!")
            print(f"Generated {len(visualizations)} visualization files:")
            for viz in visualizations:
                print(f"  ✓ {viz}")
                
        except Exception as e:
            print(f"❌ Error generating visualizations: {e}")
        
        return visualizations

def main():
    """Main execution function"""
    try:
        generator = EnhancedVisualizationGenerator()
        visualizations = generator.generate_all_visualizations()
        
        print("\\n🎉 Enhanced visualization generation complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
