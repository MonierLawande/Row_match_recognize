#!/usr/bin/env python3
"""
Row Match Recognize CPU Profiler Analysis Tool

This script analyzes CPU profiling data collected during stress tests to identify
hotspots and optimization opportunities in the Row Match Recognize implementation.

Usage:
  python analyze_profiling.py --profile-data PROFILE_DATA --output-dir OUTPUT_DIR

Options:
  --profile-data PROFILE_DATA   Directory or file containing profiling data
  --output-dir OUTPUT_DIR       Directory to store analysis results (default: profiling_analysis)
"""

import os
import sys
import argparse
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from collections import defaultdict

def setup_output_directory(output_dir):
    """Create output directory if it doesn't exist."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

def load_profiling_data(profile_path):
    """Load profiling data from a file or directory."""
    if os.path.isdir(profile_path):
        # Find profiling files in the directory
        profile_files = []
        for root, _, files in os.walk(profile_path):
            for file in files:
                if file.endswith('.prof') or file.endswith('.profile') or file.endswith('.json'):
                    profile_files.append(os.path.join(root, file))
        
        if not profile_files:
            print(f"No profiling files found in {profile_path}")
            return None
        
        # Load the first profiling file (can be extended to combine multiple files)
        return parse_profile_file(profile_files[0])
    
    elif os.path.isfile(profile_path):
        return parse_profile_file(profile_path)
    
    else:
        print(f"Profile path {profile_path} does not exist")
        return None

def parse_profile_file(file_path):
    """Parse profiling data from file based on its format."""
    if file_path.endswith('.json'):
        # Assume JSON format
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error parsing JSON profile file: {e}")
            return None
    
    elif file_path.endswith('.prof') or file_path.endswith('.profile'):
        # This is a simplified example - in reality, you would use pstats or another
        # library to parse the profile file format
        print("Note: For .prof files, you should use the Python pstats module")
        print("This is a simplified placeholder implementation")
        
        # Create a mock profile data structure
        mock_data = {
            'functions': [
                {'name': 'pattern_tokenizer.tokenize_pattern', 'calls': 150, 'time': 0.25},
                {'name': 'matcher.match', 'calls': 100, 'time': 0.5},
                {'name': 'automata.NFABuilder.build_nfa', 'calls': 50, 'time': 0.15},
                {'name': 'condition_evaluator.compile_condition', 'calls': 200, 'time': 0.1}
            ],
            'total_time': 1.0
        }
        
        return mock_data
    
    else:
        print(f"Unsupported profile file format: {file_path}")
        return None

def analyze_profiling_data(profile_data):
    """Analyze profiling data to identify performance hotspots."""
    if not profile_data:
        return {}
    
    # Extract function-level metrics
    functions = profile_data.get('functions', [])
    total_time = profile_data.get('total_time', 1.0)
    
    # Calculate percentages
    for func in functions:
        func['time_percent'] = (func['time'] / total_time) * 100
    
    # Sort by time percentage
    functions_sorted = sorted(functions, key=lambda x: x['time_percent'], reverse=True)
    
    # Group by module
    modules = defaultdict(float)
    for func in functions:
        module_name = func['name'].split('.')[0] if '.' in func['name'] else 'other'
        modules[module_name] += func['time_percent']
    
    # Convert to sorted list
    modules_sorted = sorted([(k, v) for k, v in modules.items()], key=lambda x: x[1], reverse=True)
    
    return {
        'functions': functions_sorted,
        'modules': modules_sorted,
        'total_time': total_time
    }

def generate_hotspot_visualizations(analysis_data, output_dir):
    """Generate visualizations for performance hotspots."""
    if not analysis_data:
        return
    
    # Setup visualization style
    plt.style.use('ggplot')
    sns.set_palette("viridis")
    
    # 1. Function-level hotspot bar chart
    functions = analysis_data.get('functions', [])
    if functions:
        # Limit to top 10 functions for readability
        top_functions = functions[:10]
        
        plt.figure(figsize=(12, 8))
        bars = plt.barh(
            [f['name'] for f in top_functions],
            [f['time_percent'] for f in top_functions]
        )
        
        # Add percentage labels
        for bar in bars:
            width = bar.get_width()
            plt.text(
                width + 0.5, 
                bar.get_y() + bar.get_height()/2, 
                f'{width:.1f}%', 
                ha='left', 
                va='center'
            )
        
        plt.title('Top 10 Performance Hotspots (Functions)', fontsize=16)
        plt.xlabel('Percentage of Total Execution Time', fontsize=14)
        plt.ylabel('Function', fontsize=14)
        plt.tight_layout()
        
        # Save the chart
        plt.savefig(os.path.join(output_dir, 'function_hotspots.png'), dpi=300)
        plt.close()
    
    # 2. Module-level hotspot pie chart
    modules = analysis_data.get('modules', [])
    if modules:
        plt.figure(figsize=(10, 10))
        
        module_names = [m[0] for m in modules]
        module_times = [m[1] for m in modules]
        
        plt.pie(
            module_times, 
            labels=module_names,
            autopct='%1.1f%%',
            startangle=90,
            shadow=True
        )
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
        
        plt.title('Execution Time by Module', fontsize=16)
        plt.tight_layout()
        
        # Save the chart
        plt.savefig(os.path.join(output_dir, 'module_hotspots.png'), dpi=300)
        plt.close()
    
    # 3. Call frequency vs. time scatter plot
    if functions:
        plt.figure(figsize=(12, 8))
        
        plt.scatter(
            [f.get('calls', 0) for f in functions], 
            [f.get('time', 0) for f in functions],
            alpha=0.7,
            s=100
        )
        
        # Add labels for the top 5 functions
        for func in functions[:5]:
            plt.annotate(
                func['name'].split('.')[-1],
                (func.get('calls', 0), func.get('time', 0)),
                xytext=(5, 5),
                textcoords='offset points'
            )
        
        plt.title('Function Call Frequency vs. Execution Time', fontsize=16)
        plt.xlabel('Number of Calls', fontsize=14)
        plt.ylabel('Total Time (seconds)', fontsize=14)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # Save the chart
        plt.savefig(os.path.join(output_dir, 'call_frequency_vs_time.png'), dpi=300)
        plt.close()

def generate_optimization_recommendations(analysis_data, output_dir):
    """Generate optimization recommendations based on profiling analysis."""
    if not analysis_data:
        return []
    
    recommendations = []
    
    # Analyze hotspots
    functions = analysis_data.get('functions', [])
    
    # Find costly functions
    high_time_funcs = [f for f in functions if f.get('time_percent', 0) > 10]
    for func in high_time_funcs:
        func_name = func['name']
        time_percent = func['time_percent']
        
        if 'tokenize_pattern' in func_name:
            recommendations.append({
                "target": func_name,
                "impact": "High",
                "finding": f"Pattern tokenization consumes {time_percent:.1f}% of execution time",
                "recommendation": "Consider implementing a more efficient tokenization algorithm or caching tokenized patterns."
            })
        
        elif 'NFABuilder' in func_name or 'build_nfa' in func_name:
            recommendations.append({
                "target": func_name,
                "impact": "High",
                "finding": f"NFA construction consumes {time_percent:.1f}% of execution time",
                "recommendation": "Optimize NFA construction algorithm or cache NFAs for similar patterns."
            })
        
        elif 'DFABuilder' in func_name or 'build_dfa' in func_name:
            recommendations.append({
                "target": func_name,
                "impact": "High",
                "finding": f"DFA construction consumes {time_percent:.1f}% of execution time",
                "recommendation": "Optimize DFA construction algorithm or implement lazy DFA construction."
            })
        
        elif 'match' in func_name:
            recommendations.append({
                "target": func_name,
                "impact": "High",
                "finding": f"Pattern matching consumes {time_percent:.1f}% of execution time",
                "recommendation": "Review the core matching algorithm for optimization opportunities. Consider specialized algorithms for common pattern types."
            })
        
        elif 'condition_evaluator' in func_name or 'compile_condition' in func_name:
            recommendations.append({
                "target": func_name,
                "impact": "Medium",
                "finding": f"Condition evaluation consumes {time_percent:.1f}% of execution time",
                "recommendation": "Optimize condition compilation and evaluation. Consider caching compiled conditions."
            })
        
        elif 'RowContext' in func_name:
            recommendations.append({
                "target": func_name,
                "impact": "Medium",
                "finding": f"Row context management consumes {time_percent:.1f}% of execution time",
                "recommendation": "Optimize row context data structures and access patterns."
            })
        
        else:
            recommendations.append({
                "target": func_name,
                "impact": "Medium",
                "finding": f"Function consumes {time_percent:.1f}% of execution time",
                "recommendation": "Review implementation for optimization opportunities."
            })
    
    # Check for high call frequency functions
    high_call_funcs = [f for f in functions if f.get('calls', 0) > 1000 and f not in high_time_funcs]
    for func in high_call_funcs:
        func_name = func['name']
        calls = func.get('calls', 0)
        
        recommendations.append({
            "target": func_name,
            "impact": "Medium",
            "finding": f"Function called {calls} times",
            "recommendation": "Consider inlining or memoizing frequently called functions."
        })
    
    # Check module-level statistics
    modules = analysis_data.get('modules', [])
    for module_name, time_percent in modules:
        if time_percent > 30:
            recommendations.append({
                "target": module_name,
                "impact": "High",
                "finding": f"Module consumes {time_percent:.1f}% of execution time",
                "recommendation": f"Focus optimization efforts on the {module_name} module."
            })
    
    # Save recommendations to file
    with open(os.path.join(output_dir, 'optimization_recommendations.json'), 'w') as f:
        json.dump(recommendations, f, indent=2)
    
    # Create a formatted text version
    with open(os.path.join(output_dir, 'optimization_recommendations.md'), 'w') as f:
        f.write("# Row Match Recognize Performance Optimization Recommendations\n\n")
        f.write("Based on profiling analysis, the following optimizations are recommended:\n\n")
        
        # Group recommendations by impact
        impact_groups = {"High": [], "Medium": [], "Low": []}
        for rec in recommendations:
            impact_groups[rec["impact"]].append(rec)
        
        # Write recommendations by impact
        for impact in ["High", "Medium", "Low"]:
            if impact_groups[impact]:
                f.write(f"## {impact} Impact Optimizations\n\n")
                
                for rec in impact_groups[impact]:
                    f.write(f"### {rec['target']}\n\n")
                    f.write(f"**Finding:** {rec['finding']}\n\n")
                    f.write(f"**Recommendation:** {rec['recommendation']}\n\n")
    
    return recommendations

def main():
    """Main function to parse arguments and run the analysis."""
    parser = argparse.ArgumentParser(description='Analyze Row Match Recognize profiling data')
    parser.add_argument('--profile-data', type=str, required=True,
                        help='Directory or file containing profiling data')
    parser.add_argument('--output-dir', type=str, default='profiling_analysis',
                        help='Directory to store analysis results')
    
    args = parser.parse_args()
    
    # Setup output directory
    setup_output_directory(args.output_dir)
    
    # Load profiling data
    print(f"Loading profiling data from {args.profile_data}...")
    profile_data = load_profiling_data(args.profile_data)
    
    if not profile_data:
        print("No valid profiling data found. Exiting.")
        sys.exit(1)
    
    # Analyze profiling data
    print("Analyzing profiling data...")
    analysis_data = analyze_profiling_data(profile_data)
    
    # Generate visualizations
    print("Generating hotspot visualizations...")
    generate_hotspot_visualizations(analysis_data, args.output_dir)
    
    # Generate optimization recommendations
    print("Generating optimization recommendations...")
    recommendations = generate_optimization_recommendations(analysis_data, args.output_dir)
    
    print(f"Analysis complete. {len(recommendations)} optimization recommendations generated.")
    print(f"Results saved to {args.output_dir}")

if __name__ == "__main__":
    main()
