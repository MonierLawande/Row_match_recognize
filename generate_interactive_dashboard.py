#!/usr/bin/env python3
"""
Interactive Dashboard Generator for Row Match Recognize Stress Tests

This script generates an interactive HTML dashboard from stress test results,
allowing for dynamic exploration of performance characteristics.

Usage:
  python generate_interactive_dashboard.py --input-dir INPUT_DIR --output-file OUTPUT_FILE

Options:
  --input-dir INPUT_DIR       Directory containing stress test results (default: stress_test_results)
  --output-file OUTPUT_FILE   Output HTML dashboard file (default: row_match_dashboard.html)
"""

import os
import argparse
import json
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Generate interactive dashboard for stress test results')
    parser.add_argument('--input-dir', type=str, default='stress_test_results',
                        help='Directory containing stress test results')
    parser.add_argument('--output-file', type=str, default='row_match_dashboard.html',
                        help='Output HTML dashboard file')
    return parser.parse_args()

def load_test_results(input_dir):
    """Load and combine stress test results from different subdirectories."""
    all_results = []
    
    # Check if the directory has subdirectories
    has_subdirs = False
    for item in os.listdir(input_dir):
        if os.path.isdir(os.path.join(input_dir, item)):
            has_subdirs = True
            break
    
    if has_subdirs:
        # Process each subdirectory
        for subdir in os.listdir(input_dir):
            subdir_path = os.path.join(input_dir, subdir)
            if os.path.isdir(subdir_path):
                results = load_data_files(subdir_path, subdir)
                all_results.extend(results)
    else:
        # Process the input directory directly
        results = load_data_files(input_dir, "main")
        all_results.extend(results)
    
    # Combine all results into a DataFrame
    if all_results:
        return pd.DataFrame(all_results)
    else:
        return pd.DataFrame()

def load_data_files(directory, source_name):
    """Load CSV and JSON data files from a directory."""
    results = []
    data_dir = os.path.join(directory, 'data')
    
    if not os.path.exists(data_dir):
        data_dir = directory  # Try the directory itself if no 'data' subdirectory
    
    if not os.path.exists(data_dir):
        return results
    
    # Process CSV files
    for filename in os.listdir(data_dir):
        if filename.endswith('.csv'):
            file_path = os.path.join(data_dir, filename)
            try:
                df = pd.read_csv(file_path)
                
                # Add source information
                test_type = filename.replace('_results.csv', '').replace('.csv', '')
                df['data_source'] = source_name
                df['test_type'] = test_type
                
                # Convert to list of dictionaries
                results.extend(df.to_dict('records'))
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
    
    # Process JSON files
    for filename in os.listdir(data_dir):
        if filename.endswith('.json') and filename != 'performance_recommendations.json':
            file_path = os.path.join(data_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Handle different JSON formats
                if isinstance(data, list):
                    for item in data:
                        item['data_source'] = source_name
                        item['test_type'] = filename.replace('.json', '')
                    results.extend(data)
                elif isinstance(data, dict):
                    data['data_source'] = source_name
                    data['test_type'] = filename.replace('.json', '')
                    results.append(data)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
    
    return results

def load_recommendations(input_dir):
    """Load performance recommendations from JSON files."""
    all_recommendations = []
    
    # Check if the directory has subdirectories
    has_subdirs = False
    for item in os.listdir(input_dir):
        if os.path.isdir(os.path.join(input_dir, item)):
            has_subdirs = True
            break
    
    if has_subdirs:
        # Process each subdirectory
        for subdir in os.listdir(input_dir):
            subdir_path = os.path.join(input_dir, subdir)
            if os.path.isdir(subdir_path):
                recommendations = find_recommendation_files(subdir_path, subdir)
                all_recommendations.extend(recommendations)
    else:
        # Process the input directory directly
        recommendations = find_recommendation_files(input_dir, "main")
        all_recommendations.extend(recommendations)
    
    return all_recommendations

def find_recommendation_files(directory, source_name):
    """Find and load recommendation files in the directory structure."""
    recommendations = []
    
    # Check recommendations directory
    rec_dir = os.path.join(directory, 'recommendations')
    if os.path.exists(rec_dir):
        for filename in os.listdir(rec_dir):
            if filename == 'performance_recommendations.json':
                file_path = os.path.join(rec_dir, filename)
                try:
                    with open(file_path, 'r') as f:
                        recs = json.load(f)
                        for rec in recs:
                            rec['source'] = source_name
                        recommendations.extend(recs)
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")
    
    # Also check the main directory
    for filename in os.listdir(directory):
        if filename == 'performance_recommendations.json':
            file_path = os.path.join(directory, filename)
            try:
                with open(file_path, 'r') as f:
                    recs = json.load(f)
                    for rec in recs:
                        rec['source'] = source_name
                    recommendations.extend(recs)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
    
    return recommendations

def create_dashboard(results_df, recommendations, output_file):
    """Create an interactive HTML dashboard from the test results."""
    if results_df.empty:
        print("No test results found. Dashboard cannot be created.")
        return
    
    # Clean up and prepare the data
    # Extract pattern and test information from test_name
    if 'test_name' in results_df.columns:
        # Try to extract pattern name
        results_df['pattern_name'] = results_df['test_name'].str.extract(r'Query:(\w+)', expand=False)
        # Extract test size
        results_df['test_size'] = results_df['test_name'].str.extract(r'Size:(\d+)', expand=False)
        # Extract cache status
        results_df['cache_status'] = results_df['test_name'].str.extract(r'Cache:(\w+)', expand=False)
        # Extract pattern type
        results_df['pattern_type'] = results_df['test_name'].str.split(':').str[0]
    
    # Create plotly dashboard
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=(
            'Execution Time by Data Size', 
            'Memory Usage by Data Size',
            'Cache Efficiency', 
            'Pattern Complexity Impact',
            'Concurrency Scaling', 
            'Performance Metrics Summary'
        ),
        specs=[
            [{"type": "scatter"}, {"type": "scatter"}],
            [{"type": "scatter"}, {"type": "bar"}],
            [{"type": "scatter"}, {"type": "table"}],
        ]
    )
    
    # 1. Execution Time by Data Size
    if 'data_size' in results_df.columns and 'execution_time_seconds' in results_df.columns:
        # Filter for relevant data
        plot_data = results_df[results_df['cache_status'].notna()]
        
        # Group by pattern and cache status
        for pattern in plot_data['pattern_name'].dropna().unique():
            for cache in ['On', 'Off']:
                subset = plot_data[
                    (plot_data['pattern_name'] == pattern) & 
                    (plot_data['cache_status'] == cache)
                ]
                
                if not subset.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=subset['data_size'],
                            y=subset['execution_time_seconds'],
                            mode='lines+markers',
                            name=f"{pattern} (Cache {cache})",
                            line=dict(dash='dash' if cache == 'Off' else None)
                        ),
                        row=1, col=1
                    )
    
    # 2. Memory Usage by Data Size
    if 'data_size' in results_df.columns and 'memory_used_mb' in results_df.columns:
        # Filter for cache enabled results
        plot_data = results_df[results_df['cache_status'] == 'On']
        
        # Group by pattern
        for pattern in plot_data['pattern_name'].dropna().unique():
            subset = plot_data[plot_data['pattern_name'] == pattern]
            
            if not subset.empty:
                fig.add_trace(
                    go.Scatter(
                        x=subset['data_size'],
                        y=subset['memory_used_mb'],
                        mode='lines+markers',
                        name=f"{pattern} Memory"
                    ),
                    row=1, col=2
                )
    
    # 3. Cache Efficiency
    cache_data = results_df[results_df['cache_hit_rate'].notna()]
    if not cache_data.empty:
        # Calculate average cache hit rate by data size
        cache_summary = cache_data.groupby('data_size')['cache_hit_rate'].mean().reset_index()
        
        fig.add_trace(
            go.Scatter(
                x=cache_summary['data_size'],
                y=cache_summary['cache_hit_rate'] * 100,
                mode='lines+markers',
                name='Cache Hit Rate (%)',
                line=dict(color='green')
            ),
            row=2, col=1
        )
    
    # 4. Pattern Complexity Impact
    pattern_data = results_df[results_df['pattern_name'].notna()]
    if not pattern_data.empty:
        # Calculate average execution time by pattern
        pattern_summary = pattern_data.groupby('pattern_name')['execution_time_seconds'].mean().reset_index()
        pattern_summary = pattern_summary.sort_values('execution_time_seconds', ascending=False)
        
        fig.add_trace(
            go.Bar(
                x=pattern_summary['pattern_name'],
                y=pattern_summary['execution_time_seconds'],
                name='Avg Execution Time'
            ),
            row=2, col=2
        )
    
    # 5. Concurrency Scaling (if available)
    if 'concurrent_count' in results_df.columns:
        concurrency_data = results_df.groupby('concurrent_count')['execution_time_seconds'].mean().reset_index()
        
        fig.add_trace(
            go.Scatter(
                x=concurrency_data['concurrent_count'],
                y=concurrency_data['execution_time_seconds'],
                mode='lines+markers',
                name='Concurrency Impact',
                line=dict(color='purple')
            ),
            row=3, col=1
        )
    
    # 6. Performance Metrics Summary Table
    # Summarize key metrics
    metrics_summary = pd.DataFrame([
        {"Metric": "Avg Execution Time", "Value": f"{results_df['execution_time_seconds'].mean():.3f} s"},
        {"Metric": "Max Execution Time", "Value": f"{results_df['execution_time_seconds'].max():.3f} s"},
        {"Metric": "Avg Memory Usage", "Value": f"{results_df['memory_used_mb'].mean():.2f} MB"},
        {"Metric": "Max Memory Usage", "Value": f"{results_df['memory_used_mb'].max():.2f} MB"},
        {"Metric": "Avg Cache Hit Rate", "Value": f"{results_df['cache_hit_rate'].mean()*100:.1f}%"},
        {"Metric": "Success Rate", "Value": f"{results_df['success'].mean()*100:.1f}%"}
    ])
    
    fig.add_trace(
        go.Table(
            header=dict(
                values=["Metric", "Value"],
                fill_color='royalblue',
                align='left',
                font=dict(color='white', size=12)
            ),
            cells=dict(
                values=[metrics_summary["Metric"], metrics_summary["Value"]],
                fill_color='lavender',
                align='left'
            )
        ),
        row=3, col=2
    )
    
    # Update layout with better styling
    fig.update_layout(
        title_text="Row Match Recognize Performance Dashboard",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=900,
        width=1200,
        template="plotly_white"
    )
    
    # Add recommendations section
    recommendations_html = """
    <div style="margin-top: 30px; padding: 20px; background-color: #f5f5f5; border-radius: 10px;">
        <h2 style="color: #333;">Performance Optimization Recommendations</h2>
    """
    
    if recommendations:
        # Group recommendations by category
        categories = {}
        for rec in recommendations:
            category = rec.get('category', 'General')
            if category not in categories:
                categories[category] = []
            categories[category].append(rec)
        
        # Generate HTML for each category
        for category, recs in categories.items():
            recommendations_html += f'<h3 style="color: #555;">{category}</h3><ul>'
            
            # Sort by severity
            severity_order = {"High": 0, "Medium": 1, "Low": 2}
            sorted_recs = sorted(recs, key=lambda x: severity_order.get(x.get('severity', 'Low'), 3))
            
            for rec in sorted_recs:
                severity = rec.get('severity', 'Medium')
                severity_color = "#e74c3c" if severity == "High" else "#f39c12" if severity == "Medium" else "#2ecc71"
                
                recommendations_html += f"""
                <li style="margin-bottom: 15px;">
                    <div style="color: {severity_color}; font-weight: bold;">{rec.get('finding', 'Recommendation')}</div>
                    <div><strong>Severity:</strong> {severity}</div>
                    <div><strong>Description:</strong> {rec.get('description', 'No description provided')}</div>
                    <div><strong>Recommendation:</strong> {rec.get('recommendation', 'No specific recommendation')}</div>
                </li>
                """
            
            recommendations_html += '</ul>'
    else:
        recommendations_html += '<p>No performance recommendations available.</p>'
    
    recommendations_html += '</div>'
    
    # Create complete HTML with the dashboard and recommendations
    dashboard_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Row Match Recognize Performance Dashboard</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #fafafa;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background-color: white;
                padding: 20px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
                border-radius: 5px;
            }}
            h1 {{
                color: #2c3e50;
                text-align: center;
            }}
            .metadata {{
                text-align: center;
                color: #7f8c8d;
                margin-bottom: 30px;
            }}
            .dashboard {{
                width: 100%;
                height: 900px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Row Match Recognize Performance Dashboard</h1>
            <div class="metadata">
                Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
            <div class="dashboard" id="dashboard"></div>
            {recommendations_html}
        </div>
        
        <script>
            var dashboard = {fig.to_json()};
            Plotly.newPlot('dashboard', dashboard.data, dashboard.layout);
        </script>
    </body>
    </html>
    """
    
    # Write the HTML to file
    with open(output_file, 'w') as f:
        f.write(dashboard_html)
    
    print(f"Interactive dashboard created: {output_file}")

def main():
    """Main function to process arguments and generate the dashboard."""
    args = parse_arguments()
    
    print(f"Loading test results from {args.input_dir}...")
    results_df = load_test_results(args.input_dir)
    
    if results_df.empty:
        print("No test results found in the specified directory.")
        return
    
    print(f"Found {len(results_df)} test results.")
    
    print("Loading performance recommendations...")
    recommendations = load_recommendations(args.input_dir)
    print(f"Found {len(recommendations)} recommendations.")
    
    print(f"Generating interactive dashboard: {args.output_file}")
    create_dashboard(results_df, recommendations, args.output_file)
    
    print("Dashboard generation complete!")

if __name__ == "__main__":
    main()
