#!/usr/bin/env python3
"""
Test runner script for the match_recognize implementation.
Runs all tests and generates a comprehensive report.
"""

import os
import sys
import time
import subprocess
import argparse
import datetime
import json
from typing import Dict, List, Any

def run_tests(verbose: bool = False, test_file: str = None) -> Dict[str, Any]:
    """
    Run the pytest tests and return the results.
    
    Args:
        verbose: Whether to output verbose test logs
        test_file: Optional specific test file to run
        
    Returns:
        A dictionary with test results
    """
    start_time = time.time()
    
    # Prepare the command
    cmd = ["pytest"]
    if verbose:
        cmd.append("-v")
        
    if test_file:
        cmd.append(test_file)
    
    # Run the tests
    print(f"Running tests with command: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=False
        )
        
        output = result.stdout
        error = result.stderr
        return_code = result.returncode
    except Exception as e:
        output = ""
        error = str(e)
        return_code = 1
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Parse the output
    test_results = {
        "success": return_code == 0,
        "return_code": return_code,
        "output": output,
        "error": error,
        "duration": duration,
        "timestamp": datetime.datetime.now().isoformat(),
        "summary": {}
    }
    
    # Extract summary from output
    if output:
        # Try to parse the summary
        try:
            summary_lines = [line for line in output.split('\n') if '=' in line and 'passed' in line]
            if summary_lines:
                summary = summary_lines[-1].strip()
                # Parse the summary into components
                parts = summary.split('=')[1].strip().split()
                test_results["summary"] = {
                    "passed": int(parts[0]) if "passed" in parts[1] else 0,
                    "failed": int(parts[0]) if "failed" in parts[1] else 0,
                    "skipped": int(parts[0]) if "skipped" in parts[1] else 0,
                    "total": int(parts[0]) if "passed" in parts[1] else 0 + 
                             int(parts[0]) if "failed" in parts[1] else 0 +
                             int(parts[0]) if "skipped" in parts[1] else 0
                }
        except Exception as e:
            test_results["summary_error"] = str(e)
    
    return test_results

def generate_report(results: Dict[str, Any], output_file: str = None) -> None:
    """
    Generate a report from the test results.
    
    Args:
        results: Test results dictionary
        output_file: Optional file to write the report to
    """
    # Create the report text
    report = []
    report.append("=====================================================")
    report.append("  MATCH_RECOGNIZE Implementation Test Report")
    report.append("=====================================================")
    report.append(f"Timestamp: {results['timestamp']}")
    report.append(f"Duration: {results['duration']:.2f} seconds")
    report.append(f"Success: {'Yes' if results['success'] else 'No'}")
    report.append("")
    
    # Add summary if available
    if results['summary']:
        report.append("Test Summary:")
        report.append(f"  Passed: {results['summary'].get('passed', 'N/A')}")
        report.append(f"  Failed: {results['summary'].get('failed', 'N/A')}")
        report.append(f"  Skipped: {results['summary'].get('skipped', 'N/A')}")
        report.append(f"  Total: {results['summary'].get('total', 'N/A')}")
        report.append("")
    
    # Add output
    report.append("Test Output:")
    report.append("-----------------------------------------------------")
    report.append(results['output'])
    report.append("")
    
    # Add error if any
    if results['error']:
        report.append("Errors:")
        report.append("-----------------------------------------------------")
        report.append(results['error'])
    
    report_text = "\n".join(report)
    
    # Print the report
    print(report_text)
    
    # Write to file if specified
    if output_file:
        with open(output_file, 'w') as f:
            f.write(report_text)
        print(f"Report written to {output_file}")

def main():
    """Main function to run tests and generate a report."""
    parser = argparse.ArgumentParser(description='Run tests for match_recognize implementation.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-f', '--file', type=str, help='Specific test file to run')
    parser.add_argument('-o', '--output', type=str, help='Output file for the report')
    parser.add_argument('-j', '--json', type=str, help='Output JSON file for the test results')
    
    args = parser.parse_args()
    
    # Run the tests
    results = run_tests(verbose=args.verbose, test_file=args.file)
    
    # Generate the report
    generate_report(results, output_file=args.output)
    
    # Save JSON results if specified
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"JSON results written to {args.json}")
    
    # Return the appropriate exit code
    return 0 if results['success'] else 1

if __name__ == "__main__":
    sys.exit(main())
