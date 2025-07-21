#!/usr/bin/env python3
"""
LaTeX Table Generator for Enhanced Pattern Benchmark Results
Generates professional LaTeX tables from the latest benchmark data
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

class EnhancedLaTeXGenerator:
    """Generate LaTeX tables from enhanced pattern benchmark results"""
    
    def __init__(self):
        self.latest_data = None
        self.load_latest_results()
    
    def load_latest_results(self):
        """Load the most recent benchmark results"""
        # Find the latest benchmark files
        json_files = [f for f in os.listdir('.') if f.startswith('enhanced_pattern_benchmark_') and f.endswith('.json')]
        
        if not json_files:
            raise FileNotFoundError("No enhanced pattern benchmark results found!")
        
        # Get the latest file
        latest_file = max(json_files)
        print(f"Loading latest results from: {latest_file}")
        
        with open(latest_file, 'r') as f:
            data = json.load(f)
        
        self.latest_data = data
        self.results_df = pd.DataFrame(data['results'])
        self.successful_df = self.results_df[self.results_df['success'] == True]
        
        print(f"Loaded {len(self.successful_df)} successful test results")
    
    def generate_performance_scaling_table(self):
        """Table 1: Performance Scaling Analysis"""
        
        # Group by dataset size and pattern type
        performance_data = []
        
        for size in sorted(self.successful_df['dataset_size'].unique()):
            row = {'Dataset Size': f"{size:,}"}
            
            for pattern in ['Simple', 'Medium', 'Complex', 'Very Complex', 'Ultra Complex']:
                pattern_data = self.successful_df[
                    (self.successful_df['dataset_size'] == size) & 
                    (self.successful_df['pattern_type'] == pattern)
                ]
                
                if len(pattern_data) > 0:
                    exec_time = pattern_data['execution_time_seconds'].iloc[0]
                    if exec_time < 1:
                        time_str = f"{exec_time*1000:.0f}ms"
                    elif exec_time < 60:
                        time_str = f"{exec_time:.2f}s"
                    elif exec_time < 3600:
                        time_str = f"{exec_time/60:.1f}m"
                    else:
                        time_str = f"{exec_time/3600:.1f}h"
                    
                    cache_status = pattern_data['cache_status'].iloc[0]
                    color = "\\textcolor{green}" if cache_status == "HIT" else "\\textcolor{red}"
                    
                    row[pattern] = f"{color}{{{time_str}}}"
                else:
                    row[pattern] = "N/A"
            
            performance_data.append(row)
        
        # Generate LaTeX table
        latex = [
            "\\begin{table}[htbp]",
            "\\centering",
            "\\caption{Performance Scaling Analysis Across Dataset Sizes and Pattern Complexity}",
            "\\label{tab:performance_scaling}",
            "\\begin{tabular}{|l|c|c|c|c|c|}",
            "\\hline",
            "\\textbf{Dataset Size} & \\textbf{Simple} & \\textbf{Medium} & \\textbf{Complex} & \\textbf{Very Complex} & \\textbf{Ultra Complex} \\\\",
            "\\hline"
        ]
        
        for row in performance_data:
            latex.append(f"{row['Dataset Size']} & {row['Simple']} & {row['Medium']} & {row['Complex']} & {row['Very Complex']} & {row['Ultra Complex']} \\\\")
            latex.append("\\hline")
        
        latex.extend([
            "\\end{tabular}",
            "\\end{table}"
        ])
        
        return "\\n".join(latex)
    
    def generate_memory_analysis_table(self):
        """Table 2: Memory Usage and Efficiency Analysis"""
        
        memory_data = []
        
        for pattern in ['Simple', 'Medium', 'Complex', 'Very Complex', 'Ultra Complex']:
            pattern_data = self.successful_df[self.successful_df['pattern_type'] == pattern]
            
            if len(pattern_data) > 0:
                avg_memory = pattern_data['memory_usage_mb'].mean()
                peak_memory = pattern_data['peak_memory_mb'].mean()
                efficiency = pattern_data['memory_efficiency'].mean()
                total_hits = pattern_data['hits_found'].sum()
                
                memory_data.append({
                    'Pattern': pattern,
                    'Avg Memory': f"{avg_memory:.1f} MB",
                    'Peak Memory': f"{peak_memory:.1f} MB", 
                    'Efficiency': f"{efficiency:.2f}",
                    'Total Hits': f"{total_hits:,}"
                })
        
        # Generate LaTeX table
        latex = [
            "\\begin{table}[htbp]",
            "\\centering", 
            "\\caption{Memory Usage and Efficiency Analysis by Pattern Type}",
            "\\label{tab:memory_analysis}",
            "\\begin{tabular}{|l|c|c|c|c|}",
            "\\hline",
            "\\textbf{Pattern Type} & \\textbf{Avg Memory} & \\textbf{Peak Memory} & \\textbf{Efficiency} & \\textbf{Total Hits} \\\\",
            "\\hline"
        ]
        
        for row in memory_data:
            latex.append(f"{row['Pattern']} & {row['Avg Memory']} & {row['Peak Memory']} & {row['Efficiency']} & {row['Total Hits']} \\\\")
            latex.append("\\hline")
        
        latex.extend([
            "\\end{tabular}",
            "\\textit{Note: Efficiency measured as hits per MB of memory used.}",
            "\\end{table}"
        ])
        
        return "\\n".join(latex)
    
    def generate_cache_performance_table(self):
        """Table 3: Cache Performance Analysis"""
        
        cache_data = []
        
        for pattern in ['Simple', 'Medium', 'Complex', 'Very Complex', 'Ultra Complex']:
            pattern_data = self.successful_df[self.successful_df['pattern_type'] == pattern]
            
            if len(pattern_data) > 0:
                total_queries = len(pattern_data)
                cache_hits = len(pattern_data[pattern_data['cache_status'] == 'HIT'])
                hit_rate = (cache_hits / total_queries) * 100
                
                # Calculate performance improvement from cache hits
                hit_data = pattern_data[pattern_data['cache_status'] == 'HIT']
                miss_data = pattern_data[pattern_data['cache_status'] == 'MISS']
                
                if len(hit_data) > 0 and len(miss_data) > 0:
                    avg_hit_time = hit_data['execution_time_seconds'].mean()
                    avg_miss_time = miss_data['execution_time_seconds'].mean()
                    improvement = ((avg_miss_time - avg_hit_time) / avg_miss_time) * 100
                    improvement_str = f"{improvement:.1f}\\%"
                else:
                    improvement_str = "N/A"
                
                cache_data.append({
                    'Pattern': pattern,
                    'Total Queries': total_queries,
                    'Cache Hits': cache_hits,
                    'Hit Rate': f"{hit_rate:.1f}\\%",
                    'Performance Improvement': improvement_str
                })
        
        # Generate LaTeX table
        latex = [
            "\\begin{table}[htbp]",
            "\\centering",
            "\\caption{Cache Performance Analysis by Pattern Type}",
            "\\label{tab:cache_performance}",
            "\\begin{tabular}{|l|c|c|c|c|}",
            "\\hline",
            "\\textbf{Pattern Type} & \\textbf{Total Queries} & \\textbf{Cache Hits} & \\textbf{Hit Rate} & \\textbf{Performance Improvement} \\\\",
            "\\hline"
        ]
        
        for row in cache_data:
            latex.append(f"{row['Pattern']} & {row['Total Queries']} & {row['Cache Hits']} & {row['Hit Rate']} & {row['Performance Improvement']} \\\\")
            latex.append("\\hline")
        
        latex.extend([
            "\\end{tabular}",
            "\\textit{Note: Performance improvement shows time reduction from cache hits vs misses.}",
            "\\end{table}"
        ])
        
        return "\\n".join(latex)
    
    def generate_throughput_analysis_table(self):
        """Table 4: Throughput and Scalability Analysis"""
        
        throughput_data = []
        
        for pattern in ['Simple', 'Medium', 'Complex', 'Very Complex', 'Ultra Complex']:
            pattern_data = self.successful_df[self.successful_df['pattern_type'] == pattern]
            
            if len(pattern_data) > 0:
                avg_throughput = pattern_data['throughput_rows_per_sec'].mean()
                max_throughput = pattern_data['throughput_rows_per_sec'].max()
                min_throughput = pattern_data['throughput_rows_per_sec'].min()
                
                # Find best and worst performing dataset sizes
                best_idx = pattern_data['throughput_rows_per_sec'].idxmax()
                worst_idx = pattern_data['throughput_rows_per_sec'].idxmin()
                
                best_size = pattern_data.loc[best_idx, 'dataset_size']
                worst_size = pattern_data.loc[worst_idx, 'dataset_size']
                
                throughput_data.append({
                    'Pattern': pattern,
                    'Avg Throughput': f"{avg_throughput:,.0f}",
                    'Best': f"{max_throughput:,.0f} ({best_size:,})",
                    'Worst': f"{min_throughput:,.0f} ({worst_size:,})",
                    'Ratio': f"{max_throughput/min_throughput:.1f}x"
                })
        
        # Generate LaTeX table
        latex = [
            "\\begin{table}[htbp]",
            "\\centering",
            "\\caption{Throughput and Scalability Analysis (rows/second)}",
            "\\label{tab:throughput_analysis}",
            "\\begin{tabular}{|l|c|c|c|c|}",
            "\\hline",
            "\\textbf{Pattern Type} & \\textbf{Avg Throughput} & \\textbf{Best (Size)} & \\textbf{Worst (Size)} & \\textbf{Ratio} \\\\",
            "\\hline"
        ]
        
        for row in throughput_data:
            latex.append(f"{row['Pattern']} & {row['Avg Throughput']} & {row['Best']} & {row['Worst']} & {row['Ratio']} \\\\")
            latex.append("\\hline")
        
        latex.extend([
            "\\end{tabular}",
            "\\textit{Note: Best/Worst shows throughput and corresponding dataset size. Ratio = Best/Worst.}",
            "\\end{table}"
        ])
        
        return "\\n".join(latex)
    
    def generate_summary_table(self):
        """Table 5: Executive Summary Statistics"""
        
        # Overall statistics
        total_tests = len(self.successful_df)
        total_hits = self.successful_df['hits_found'].sum()
        avg_time = self.successful_df['execution_time_seconds'].mean()
        
        cache_hit_rate = (len(self.successful_df[self.successful_df['cache_status'] == 'HIT']) / total_tests) * 100
        
        # Best performing configurations
        fastest = self.successful_df.loc[self.successful_df['execution_time_seconds'].idxmin()]
        most_efficient = self.successful_df.loc[self.successful_df['memory_efficiency'].idxmax()]
        highest_throughput = self.successful_df.loc[self.successful_df['throughput_rows_per_sec'].idxmax()]
        
        summary_data = [
            ['Total Test Executions', f"{total_tests}"],
            ['Total Matches Found', f"{total_hits:,}"],
            ['Average Execution Time', f"{avg_time:.1f} seconds"],
            ['Overall Cache Hit Rate', f"{cache_hit_rate:.1f}\\%"],
            ['Fastest Configuration', f"{fastest['pattern_type']} on {fastest['dataset_size']:,} rows ({fastest['execution_time_seconds']:.3f}s)"],
            ['Most Memory Efficient', f"{most_efficient['pattern_type']} ({most_efficient['memory_efficiency']:.2f} hits/MB)"],
            ['Highest Throughput', f"{highest_throughput['pattern_type']} ({highest_throughput['throughput_rows_per_sec']:,.0f} rows/sec)"]
        ]
        
        # Generate LaTeX table
        latex = [
            "\\begin{table}[htbp]",
            "\\centering",
            "\\caption{Executive Summary of Performance Analysis}",
            "\\label{tab:summary}",
            "\\begin{tabular}{|l|l|}",
            "\\hline",
            "\\textbf{Metric} & \\textbf{Value} \\\\",
            "\\hline"
        ]
        
        for row in summary_data:
            latex.append(f"{row[0]} & {row[1]} \\\\")
            latex.append("\\hline")
        
        latex.extend([
            "\\end{tabular}",
            "\\end{table}"
        ])
        
        return "\\n".join(latex)
    
    def generate_complete_document(self):
        """Generate complete LaTeX document with all tables"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        latex = [
            "\\documentclass[11pt]{article}",
            "\\usepackage[utf8]{inputenc}",
            "\\usepackage[margin=1in]{geometry}",
            "\\usepackage{booktabs}",
            "\\usepackage{xcolor}",
            "\\usepackage{graphicx}",
            "\\usepackage{float}",
            "",
            "\\title{Enhanced MATCH RECOGNIZE Pattern Performance Analysis}",
            f"\\author{{Performance Benchmarking Suite}}",
            f"\\date{{{timestamp}}}",
            "",
            "\\begin{document}",
            "",
            "\\maketitle",
            "",
            "\\section{Introduction}",
            "This document presents a comprehensive performance analysis of MATCH RECOGNIZE patterns across different dataset sizes and complexity levels. The analysis includes execution time scaling, memory usage, cache performance, and throughput characteristics.",
            "",
            "\\section{Performance Scaling Analysis}",
            self.generate_performance_scaling_table(),
            "",
            "\\section{Memory Analysis}",  
            self.generate_memory_analysis_table(),
            "",
            "\\section{Cache Performance}",
            self.generate_cache_performance_table(),
            "",
            "\\section{Throughput Analysis}",
            self.generate_throughput_analysis_table(),
            "",
            "\\section{Executive Summary}",
            self.generate_summary_table(),
            "",
            "\\section{Conclusions}",
            "The analysis demonstrates clear performance characteristics across different pattern complexities:",
            "\\begin{itemize}",
            "\\item Simple patterns show excellent scalability and high cache hit rates",
            "\\item Complex patterns require careful consideration for large datasets", 
            "\\item Caching provides significant performance benefits, especially for simpler patterns",
            "\\item Memory efficiency decreases with pattern complexity but remains predictable",
            "\\end{itemize}",
            "",
            "\\end{document}"
        ]
        
        return "\\n".join(latex)
    
    def save_all_latex_files(self):
        """Save all LaTeX tables and complete document"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        files_to_save = {
            f'enhanced_table1_performance_scaling_{timestamp}.tex': self.generate_performance_scaling_table(),
            f'enhanced_table2_memory_analysis_{timestamp}.tex': self.generate_memory_analysis_table(),
            f'enhanced_table3_cache_performance_{timestamp}.tex': self.generate_cache_performance_table(),
            f'enhanced_table4_throughput_analysis_{timestamp}.tex': self.generate_throughput_analysis_table(),
            f'enhanced_table5_summary_{timestamp}.tex': self.generate_summary_table(),
            f'enhanced_complete_analysis_{timestamp}.tex': self.generate_complete_document()
        }
        
        print("\\n📄 Generating LaTeX files...")
        
        for filename, content in files_to_save.items():
            with open(filename, 'w') as f:
                f.write(content)
            print(f"  ✓ Generated: {filename}")
        
        print(f"\\n✅ All LaTeX files generated with timestamp: {timestamp}")
        print("\\n📋 To compile the complete document:")
        print(f"   pdflatex enhanced_complete_analysis_{timestamp}.tex")
        
        return timestamp

def main():
    """Main execution function"""
    print("🔧 Enhanced LaTeX Table Generator")
    print("=" * 50)
    
    try:
        generator = EnhancedLaTeXGenerator()
        timestamp = generator.save_all_latex_files()
        
        print("\\n🎉 LaTeX generation complete!")
        print(f"Files saved with timestamp: {timestamp}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
