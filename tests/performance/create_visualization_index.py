#!/usr/bin/env python3
"""
Create an HTML index page for easy viewing of all performance visualizations.

This script generates a comprehensive HTML page that displays all the performance
charts with descriptions and analysis.

Author: Performance Testing Team
Version: 1.0.0
"""

from pathlib import Path
import json

def create_html_index():
    """Create an HTML index page for all visualizations."""
    
    results_dir = Path("tests/performance/results")
    viz_dir = results_dir / "visualizations"
    
    # Load summary data for context
    try:
        with open(results_dir / "performance_summary.json", 'r') as f:
            summary = json.load(f)
    except:
        summary = {}
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MATCH_RECOGNIZE Caching Strategy Performance Visualizations</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            text-align: center;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 40px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }}
        .summary-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
            padding: 20px;
            background-color: #ecf0f1;
            border-radius: 8px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: #2980b9;
        }}
        .stat-label {{
            color: #7f8c8d;
            margin-top: 5px;
        }}
        .visualization {{
            margin: 40px 0;
            padding: 20px;
            border: 1px solid #ddd;
            border-radius: 8px;
            background-color: #fafafa;
        }}
        .viz-image {{
            width: 100%;
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            margin: 15px 0;
        }}
        .viz-description {{
            background-color: white;
            padding: 15px;
            border-radius: 5px;
            margin-top: 15px;
        }}
        .key-insights {{
            background-color: #e8f6f3;
            border-left: 4px solid #27ae60;
            padding: 15px;
            margin: 15px 0;
        }}
        .key-insights h4 {{
            color: #27ae60;
            margin-top: 0;
        }}
        .footer {{
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #7f8c8d;
        }}
        .nav-menu {{
            background-color: #34495e;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 30px;
        }}
        .nav-menu a {{
            color: white;
            text-decoration: none;
            margin: 0 15px;
            padding: 8px 15px;
            border-radius: 4px;
            transition: background-color 0.3s;
        }}
        .nav-menu a:hover {{
            background-color: #2c3e50;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 MATCH_RECOGNIZE Caching Strategy Performance Analysis</h1>
        
        <div class="nav-menu">
            <a href="#summary">📊 Summary</a>
            <a href="#execution-time">⏱️ Execution Time</a>
            <a href="#improvements">📈 Improvements</a>
            <a href="#memory">💾 Memory Usage</a>
            <a href="#cache-hits">🎯 Cache Hits</a>
            <a href="#dashboard">📋 Dashboard</a>
            <a href="#scaling">📏 Scaling</a>
        </div>

        <div id="summary">
            <h2>📊 Performance Summary</h2>
            <div class="summary-stats">
                <div class="stat-card">
                    <div class="stat-value">36</div>
                    <div class="stat-label">Test Combinations</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">30.6%</div>
                    <div class="stat-label">LRU Improvement</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">78.2%</div>
                    <div class="stat-label">LRU Hit Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">7.5%</div>
                    <div class="stat-label">LRU vs FIFO Advantage</div>
                </div>
            </div>
        </div>

        <div id="execution-time" class="visualization">
            <h2>⏱️ Execution Time Comparison</h2>
            <img src="visualizations/execution_time_comparison.png" alt="Execution Time Comparison" class="viz-image">
            <div class="viz-description">
                <p><strong>Purpose:</strong> Compare average execution times across caching strategies and dataset sizes.</p>
                <div class="key-insights">
                    <h4>🔍 Key Insights:</h4>
                    <ul>
                        <li><strong>LRU Cache:</strong> 160.4ms average (best performance)</li>
                        <li><strong>FIFO Cache:</strong> 173.4ms average (good performance)</li>
                        <li><strong>No Cache:</strong> 230.9ms average (baseline)</li>
                        <li><strong>Clear scaling patterns</strong> across dataset sizes (1K → 5K rows)</li>
                    </ul>
                </div>
            </div>
        </div>

        <div id="improvements" class="visualization">
            <h2>📈 Performance Improvement Heatmap</h2>
            <img src="visualizations/performance_improvement_heatmap.png" alt="Performance Improvement Heatmap" class="viz-image">
            <div class="viz-description">
                <p><strong>Purpose:</strong> Visualize percentage improvements over baseline across different scenarios.</p>
                <div class="key-insights">
                    <h4>🔍 Key Insights:</h4>
                    <ul>
                        <li><strong>FIFO improvements:</strong> 17.4% to 30.8% across scenarios</li>
                        <li><strong>LRU improvements:</strong> 26.8% to 36.7% across scenarios</li>
                        <li><strong>Consistent gains</strong> across all dataset sizes and pattern complexities</li>
                        <li><strong>LRU superior</strong> in every single test scenario</li>
                    </ul>
                </div>
            </div>
        </div>

        <div id="memory" class="visualization">
            <h2>💾 Memory Usage Analysis</h2>
            <img src="visualizations/memory_usage_analysis.png" alt="Memory Usage Analysis" class="viz-image">
            <div class="viz-description">
                <p><strong>Purpose:</strong> Analyze memory consumption patterns and scaling characteristics.</p>
                <div class="key-insights">
                    <h4>🔍 Key Insights:</h4>
                    <ul>
                        <li><strong>No Cache:</strong> 23.8MB baseline memory usage</li>
                        <li><strong>FIFO Cache:</strong> 84.1MB average (3.5× baseline)</li>
                        <li><strong>LRU Cache:</strong> 100.6MB average (4.2× baseline)</li>
                        <li><strong>Linear memory scaling</strong> with dataset size</li>
                    </ul>
                </div>
            </div>
        </div>

        <div id="cache-hits" class="visualization">
            <h2>🎯 Cache Hit Rate Analysis</h2>
            <img src="visualizations/cache_hit_rate_analysis.png" alt="Cache Hit Rate Analysis" class="viz-image">
            <div class="viz-description">
                <p><strong>Purpose:</strong> Compare cache effectiveness between FIFO and LRU strategies.</p>
                <div class="key-insights">
                    <h4>🔍 Key Insights:</h4>
                    <ul>
                        <li><strong>LRU Cache:</strong> 78.2% average hit rate (superior)</li>
                        <li><strong>FIFO Cache:</strong> 64.7% average hit rate (good)</li>
                        <li><strong>13.5 percentage point advantage</strong> for LRU</li>
                        <li><strong>Hit rate directly correlates</strong> with performance improvements</li>
                    </ul>
                </div>
            </div>
        </div>

        <div id="dashboard" class="visualization">
            <h2>📋 Comprehensive Performance Dashboard</h2>
            <img src="visualizations/comprehensive_performance_dashboard.png" alt="Comprehensive Performance Dashboard" class="viz-image">
            <div class="viz-description">
                <p><strong>Purpose:</strong> Single-view dashboard showing all key performance metrics.</p>
                <div class="key-insights">
                    <h4>🔍 Key Insights:</h4>
                    <ul>
                        <li><strong>Complete performance picture</strong> in one visualization</li>
                        <li><strong>LRU dominance</strong> across all metrics</li>
                        <li><strong>Scaling characteristics</strong> clearly visible</li>
                        <li><strong>Performance consistency</strong> across scenarios</li>
                    </ul>
                </div>
            </div>
        </div>

        <div id="scaling" class="visualization">
            <h2>📏 Scaling Analysis</h2>
            <img src="visualizations/scaling_analysis.png" alt="Scaling Analysis" class="viz-image">
            <div class="viz-description">
                <p><strong>Purpose:</strong> Detailed analysis of how performance scales with dataset size.</p>
                <div class="key-insights">
                    <h4>🔍 Key Insights:</h4>
                    <ul>
                        <li><strong>Linear scaling</strong> for execution time across all strategies</li>
                        <li><strong>Consistent cache effectiveness</strong> regardless of dataset size</li>
                        <li><strong>Performance efficiency</strong> maintained at scale</li>
                        <li><strong>Predictable resource requirements</strong> for capacity planning</li>
                    </ul>
                </div>
            </div>
        </div>

        <div class="footer">
            <p><strong>MATCH_RECOGNIZE Caching Strategy Performance Analysis</strong></p>
            <p>Generated from 36 comprehensive test combinations (4 dataset sizes × 3 pattern complexities × 3 caching strategies)</p>
            <p>📁 Data files: <code>detailed_performance_results.csv</code> | <code>performance_summary.json</code></p>
        </div>
    </div>
</body>
</html>
"""
    
    # Save HTML file
    html_file = results_dir / "performance_visualizations.html"
    with open(html_file, 'w') as f:
        f.write(html_content)
    
    print(f"📄 HTML index created: {html_file}")
    return html_file

if __name__ == "__main__":
    create_html_index()
