import time
import statistics
import json
import datetime
import platform
import psutil
import os
import random
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
import sys
import traceback

# Import your actual system with proper error handling
try:
    # Try different import paths for your system
    sys.path.append('/home/monierashraf/Desktop/llm/Row_match_recognize')
    
    from src.executor.match_recognize import match_recognize
    
    # Try to import cache functions - handle missing functions gracefully
    try:
        from src.utils.pattern_cache import get_cache_stats, CACHE_STATS
        def clear_cache():
            """Clear cache function"""
            global CACHE_STATS
            CACHE_STATS['hits'] = 0
            CACHE_STATS['misses'] = 0
            CACHE_STATS['compilation_time_saved'] = 0.0
            CACHE_STATS['memory_used_mb'] = 0.0
        CACHE_AVAILABLE = True
    except ImportError:
        print("Cache functions not available, using mock functions")
        def get_cache_stats():
            return {'hits': 0, 'misses': 0, 'compilation_time_saved': 0.0, 'memory_used_mb': 0.0}
        def clear_cache():
            pass
        CACHE_AVAILABLE = False
    
    SYSTEM_AVAILABLE = True
    print("✅ Successfully imported SQL MATCH_RECOGNIZE system")
    
except ImportError as e:
    print(f"❌ Could not import actual system: {e}")
    SYSTEM_AVAILABLE = False
    CACHE_AVAILABLE = False
    
    # Mock functions for when system is not available
    def match_recognize(query, df):
        raise ImportError("System not available")
    def get_cache_stats():
        return {'hits': 0, 'misses': 0}
    def clear_cache():
        pass

@dataclass
class SystemInfo:
    os: str
    python_version: str
    cpu_count: int
    total_memory_gb: float
    timestamp: str
    system_available: bool

@dataclass
class PerformanceResult:
    name: str
    expected: Any
    actual: Any
    valid: bool
    unit: str
    details: Optional[Dict] = None

@dataclass
class ValidationResults:
    system_info: SystemInfo
    core_metrics: List[PerformanceResult]
    batch_processing: List[PerformanceResult]
    complexity: List[PerformanceResult]
    memory_usage: List[PerformanceResult]
    improvements: List[PerformanceResult]
    summary: Dict[str, Any]

class RealSystemValidator:
    def __init__(self):
        self.system_info = self._get_system_info()
        self.results = []
        self.test_queries = self._get_test_queries()
        
    def _get_system_info(self) -> SystemInfo:
        return SystemInfo(
            os=platform.system(),
            python_version=platform.python_version(),
            cpu_count=os.cpu_count(),
            total_memory_gb=psutil.virtual_memory().total / (1024**3),
            timestamp=datetime.datetime.now().isoformat(),
            system_available=SYSTEM_AVAILABLE
        )

    def _get_test_queries(self) -> Dict[str, str]:
        """Define real SQL MATCH_RECOGNIZE queries for testing"""
        return {
            "simple_sequential": """
                SELECT *
                FROM trades
                MATCH_RECOGNIZE (
                    ORDER BY id
                    MEASURES
                        A.id AS start_id,
                        B.id AS middle_id,
                        C.id AS end_id
                    PATTERN (A B C)
                    DEFINE
                        A AS A.value > 10,
                        B AS B.value > A.value,
                        C AS C.value > B.value
                )
            """,
            
            "quantified_pattern": """
                SELECT *
                FROM trades
                MATCH_RECOGNIZE (
                    ORDER BY id
                    MEASURES
                        FIRST(A.id) AS first_a,
                        LAST(A.id) AS last_a,
                        COUNT(A.*) AS count_a
                    PATTERN (A+ B*)
                    DEFINE
                        A AS A.value > 20,
                        B AS B.value < 50
                )
            """,
            
            "alternation_pattern": """
                SELECT *
                FROM trades
                MATCH_RECOGNIZE (
                    ORDER BY id
                    MEASURES
                        CLASSIFIER() AS matched_var,
                        MATCH_NUMBER() AS match_num
                    PATTERN (A | B | C)
                    DEFINE
                        A AS A.value > 80,
                        B AS B.value BETWEEN 40 AND 60,
                        C AS C.value < 20
                )
            """,
            
            "cache_test": """
                SELECT *
                FROM trades
                MATCH_RECOGNIZE (
                    ORDER BY id
                    MEASURES
                        A.value AS a_val,
                        B.value AS b_val
                    PATTERN (A B)
                    DEFINE
                        A AS A.value > 30,
                        B AS B.value > 50
                )
            """
        }

    def _generate_realistic_test_data(self, size: int, pattern_type: str = "mixed") -> pd.DataFrame:
        """Generate realistic test data that will produce matches"""
        np.random.seed(42)  # For reproducible results
        
        if pattern_type == "trending_up":
            # Data that trends upward (good for A+ patterns)
            base_values = np.linspace(10, 90, size)
            noise = np.random.normal(0, 5, size)
            values = np.maximum(1, base_values + noise)
        elif pattern_type == "alternating":
            # Alternating high/low values
            values = [80 if i % 2 == 0 else 20 for i in range(size)]
            values = np.array(values) + np.random.normal(0, 5, size)
        elif pattern_type == "mixed":
            # Mixed pattern with various ranges
            values = []
            for i in range(size):
                if i % 10 < 3:
                    values.append(np.random.uniform(80, 100))  # High values
                elif i % 10 < 6:
                    values.append(np.random.uniform(40, 60))   # Medium values
                else:
                    values.append(np.random.uniform(1, 30))    # Low values
            values = np.array(values)
        else:
            # Random values
            values = np.random.uniform(1, 100, size)
        
        data = {
            'id': range(size),
            'value': values,
            'category': [random.choice(['A', 'B', 'C']) for _ in range(size)],
            'timestamp': pd.date_range(start='2023-01-01', periods=size, freq='1min'),
            'symbol': [f'SYM{i//100}' for i in range(size)]  # For partitioning tests
        }
        
        return pd.DataFrame(data)

    def _execute_query_safely(self, query: str, data: pd.DataFrame) -> Dict[str, Any]:
        """Execute a query safely and return results with timing"""
        if not SYSTEM_AVAILABLE:
            return {
                'success': False,
                'error': 'System not available',
                'execution_time': 0,
                'result_count': 0
            }
        
        try:
            start_time = time.time()
            result = match_recognize(query, data)
            execution_time = time.time() - start_time
            
            return {
                'success': True,
                'result': result,
                'execution_time': execution_time,
                'result_count': len(result) if result is not None else 0,
                'error': None
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'execution_time': 0,
                'result_count': 0,
                'traceback': traceback.format_exc()
            }

    def _measure_real_throughput(self, size: int = 1000) -> float:
        """Measure real throughput using actual system"""
        data = self._generate_realistic_test_data(size, "mixed")
        query = self.test_queries["simple_sequential"]
        
        result = self._execute_query_safely(query, data)
        
        if result['success'] and result['execution_time'] > 0:
            return size / result['execution_time']
        else:
            print(f"Throughput test failed: {result.get('error', 'Unknown error')}")
            return 0

    def _measure_real_latency(self) -> float:
        """Measure real latency using actual system"""
        latencies = []
        
        for i in range(5):  # Reduced iterations for faster testing
            data = self._generate_realistic_test_data(100, "mixed")
            query = self.test_queries["simple_sequential"]
            
            result = self._execute_query_safely(query, data)
            
            if result['success']:
                latencies.append(result['execution_time'] * 1000)  # Convert to ms
            else:
                print(f"Latency test {i} failed: {result.get('error', 'Unknown error')}")
        
        return statistics.mean(latencies) if latencies else 0

    def _measure_real_cache_hit_rate(self) -> float:
        """Measure real cache hit rate"""
        if not SYSTEM_AVAILABLE or not CACHE_AVAILABLE:
            return 0
        
        try:
            # Clear cache first
            clear_cache()
            initial_stats = get_cache_stats()
            
            query = self.test_queries["cache_test"]
            data = self._generate_realistic_test_data(100, "mixed")
            
            # Execute same query multiple times
            for i in range(11):
                self._execute_query_safely(query, data)
            
            # Get cache statistics
            final_stats = get_cache_stats()
            total_hits = final_stats.get('hits', 0) - initial_stats.get('hits', 0)
            total_misses = final_stats.get('misses', 0) - initial_stats.get('misses', 0)
            total_requests = total_hits + total_misses
            
            if total_requests > 0:
                return (total_hits / total_requests) * 100
            else:
                return 0
                
        except Exception as e:
            print(f"Cache measurement failed: {e}")
            return 0

    def _measure_real_batch_performance(self, total_rows: int, batch_size: int) -> Dict[str, Any]:
        """Measure real batch processing performance"""
        if not SYSTEM_AVAILABLE:
            return {"cache_hit_rate": 0, "num_batches": 0, "avg_time_per_batch": 0, "total_time": 0}
        
        try:
            # Clear cache first
            clear_cache()
            initial_stats = get_cache_stats()
            
            num_batches = total_rows // batch_size
            times = []
            query = self.test_queries["cache_test"]
            
            for i in range(num_batches):
                batch_data = self._generate_realistic_test_data(batch_size, "mixed")
                result = self._execute_query_safely(query, batch_data)
                
                if result['success']:
                    times.append(result['execution_time'])
                else:
                    print(f"Batch {i} failed: {result.get('error', 'Unknown error')}")
            
            final_stats = get_cache_stats()
            
            # Calculate cache hit rate
            total_hits = final_stats.get('hits', 0) - initial_stats.get('hits', 0)
            total_requests = num_batches
            cache_hit_rate = (total_hits / total_requests) * 100 if total_requests > 0 else 0
            
            return {
                "cache_hit_rate": cache_hit_rate,
                "num_batches": num_batches,
                "avg_time_per_batch": statistics.mean(times) if times else 0,
                "total_time": sum(times)
            }
            
        except Exception as e:
            print(f"Batch performance measurement failed: {e}")
            return {"cache_hit_rate": 0, "num_batches": 0, "avg_time_per_batch": 0, "total_time": 0}

    def _measure_real_complexity(self, pattern_info: Dict) -> Dict[str, Any]:
        """Measure real computational complexity"""
        if not SYSTEM_AVAILABLE:
            return {
                "measured": "System not available",
                "matches_expected": False,
                "times": [],
                "sizes": pattern_info["sizes"],
                "growth_rate": 0
            }
        
        times = []
        sizes = pattern_info["sizes"]
        query = self.test_queries.get(pattern_info["query_key"], self.test_queries["simple_sequential"])
        
        for size in sizes:
            data = self._generate_realistic_test_data(size, pattern_info.get("data_type", "mixed"))
            result = self._execute_query_safely(query, data)
            
            if result['success']:
                times.append(result['execution_time'])
            else:
                print(f"Complexity test for size {size} failed: {result.get('error', 'Unknown error')}")
                times.append(0)
        
        # Analyze growth rate
        if len(times) >= 2 and all(t > 0 for t in times):
            growth_rates = []
            for i in range(1, len(times)):
                size_ratio = sizes[i] / sizes[i-1]
                time_ratio = times[i] / times[i-1] if times[i-1] > 0 else 1
                growth_rates.append(time_ratio / size_ratio)
            
            avg_growth = statistics.mean(growth_rates)
            
            # Determine if it matches expected complexity
            expected = pattern_info["expected"]
            if "O(n)" in expected and not ("×" in expected or "!" in expected):
                matches_expected = 0.8 <= avg_growth <= 1.5
            elif "×" in expected or "²" in expected:
                matches_expected = avg_growth >= 1.2
            elif "!" in expected:
                matches_expected = avg_growth >= 2.0
            else:
                matches_expected = True
        else:
            avg_growth = 0
            matches_expected = False
        
        return {
            "measured": f"Growth rate: {avg_growth:.2f}",
            "matches_expected": matches_expected,
            "times": times,
            "sizes": sizes,
            "growth_rate": avg_growth
        }

    def _measure_real_memory_usage(self) -> Dict[str, float]:
        """Measure real memory usage"""
        process = psutil.Process(os.getpid())
        
        # Baseline memory
        baseline_memory = process.memory_info().rss / 1024 / 1024
        
        if not SYSTEM_AVAILABLE:
            return {
                "baseline": baseline_memory,
                "cache_overhead": 0,
                "peak_usage": baseline_memory
            }
        
        try:
            # Clear cache and measure
            clear_cache()
            memory_after_clear = process.memory_info().rss / 1024 / 1024
            
            # Load cache with patterns
            for query_name, query in self.test_queries.items():
                data = self._generate_realistic_test_data(100, "mixed")
                self._execute_query_safely(query, data)
            
            memory_with_cache = process.memory_info().rss / 1024 / 1024
            cache_overhead = memory_with_cache - memory_after_clear
            
            return {
                "baseline": baseline_memory,
                "cache_overhead": max(0, cache_overhead),
                "peak_usage": memory_with_cache
            }
            
        except Exception as e:
            print(f"Memory measurement failed: {e}")
            return {
                "baseline": baseline_memory,
                "cache_overhead": 0,
                "peak_usage": baseline_memory
            }

    def _measure_real_improvement(self, size: int) -> float:
        """Measure real performance improvement with caching"""
        if not SYSTEM_AVAILABLE:
            return 0
        
        try:
            data = self._generate_realistic_test_data(size, "mixed")
            query = self.test_queries["cache_test"]
            
            # Measure without cache (clear cache before each run)
            clear_cache()
            result_no_cache = self._execute_query_safely(query, data)
            time_no_cache = result_no_cache['execution_time'] if result_no_cache['success'] else 0
            
            # Measure with cache (run twice, second run should hit cache)
            clear_cache()
            self._execute_query_safely(query, data)  # Prime the cache
            result_with_cache = self._execute_query_safely(query, data)  # This should hit cache
            time_with_cache = result_with_cache['execution_time'] if result_with_cache['success'] else 0
            
            if time_no_cache > 0 and time_with_cache > 0:
                improvement = (time_no_cache - time_with_cache) / time_no_cache
                return max(0, improvement)  # Ensure non-negative
            else:
                return 0
                
        except Exception as e:
            print(f"Improvement measurement failed: {e}")
            return 0

    def validate_all(self) -> ValidationResults:
        """Run all validations and return results"""
        if not SYSTEM_AVAILABLE:
            print("Warning: Real system not available, some tests will be skipped")
        
        core_metrics = self._validate_core_metrics()
        batch_processing = self._validate_batch_processing()
        complexity = self._validate_complexity()
        memory_usage = self._validate_memory()
        improvements = self._validate_improvements()
        
        # Collect all results for summary
        all_results = core_metrics + batch_processing + complexity + memory_usage + improvements
        self.results = all_results
        
        return ValidationResults(
            system_info=self.system_info,
            core_metrics=core_metrics,
            batch_processing=batch_processing,
            complexity=complexity,
            memory_usage=memory_usage,
            improvements=improvements,
            summary=self._generate_summary()
        )

    def _validate_core_metrics(self) -> List[PerformanceResult]:
        """Validate core performance metrics using real system"""
        results = []

        print("Testing core metrics...")
        
        # Throughput Test
        print("  - Measuring throughput...")
        throughput = self._measure_real_throughput()
        results.append(PerformanceResult(
            name="Throughput",
            expected={"min": 1000, "max": 15000},
            actual=round(throughput, 2),
            valid=1000 <= throughput <= 15000 if throughput > 0 else False,
            unit="rows/sec"
        ))

        # Latency Test
        print("  - Measuring latency...")
        latency = self._measure_real_latency()
        results.append(PerformanceResult(
            name="Latency",
            expected={"min": 1, "max": 100},
            actual=round(latency, 2),
            valid=1 <= latency <= 100 if latency > 0 else False,
            unit="ms"
        ))

        # Cache Hit Rate
        print("  - Measuring cache hit rate...")
        hit_rate = self._measure_real_cache_hit_rate()
        results.append(PerformanceResult(
            name="Cache Hit Rate",
            expected=90.9,
            actual=round(hit_rate, 1),
            valid=abs(hit_rate - 90.9) < 5,  # Allow 5% tolerance
            unit="%"
        ))

        return results

    def _validate_batch_processing(self) -> List[PerformanceResult]:
        """Validate batch processing performance using real system"""
        results = []
        
        print("Testing batch processing...")
        
        # Test with smaller batches for faster testing
        batch_metrics = self._measure_real_batch_performance(
            total_rows=4000,  # Reduced for faster testing
            batch_size=1000
        )
        
        results.append(PerformanceResult(
            name="Batch Processing",
            expected=75.0,  # 75% cache hit rate
            actual=round(batch_metrics["cache_hit_rate"], 1),
            valid=abs(batch_metrics["cache_hit_rate"] - 75.0) < 15,  # Allow 15% tolerance
            unit="%",
            details=batch_metrics
        ))

        return results

    def _validate_complexity(self) -> List[PerformanceResult]:
        """Validate computational complexity claims using real system"""
        patterns = [
            {
                "name": "Simple Sequential",
                "query_key": "simple_sequential",
                "expected": "O(n)",
                "sizes": [500, 1000, 2000],  # Smaller sizes for faster testing
                "data_type": "mixed"
            },
            {
                "name": "Quantified",
                "query_key": "quantified_pattern",
                "expected": "O(n×m)",
                "sizes": [500, 1000, 2000],
                "data_type": "trending_up"
            },
            {
                "name": "Alternation",
                "query_key": "alternation_pattern",
                "expected": "O(n×k)",
                "sizes": [500, 1000],
                "data_type": "mixed"
            }
        ]

        results = []
        print("Testing complexity...")
        
        for p in patterns:
            print(f"  - Testing {p['name']} complexity...")
            complexity_metrics = self._measure_real_complexity(p)
            results.append(PerformanceResult(
                name=p["name"],
                expected=p["expected"],
                actual=complexity_metrics["measured"],
                valid=complexity_metrics["matches_expected"],
                unit="complexity",
                details=complexity_metrics
            ))

        return results

    def _validate_memory(self) -> List[PerformanceResult]:
        """Validate memory usage claims using real system"""
        results = []
        
        print("Testing memory usage...")
        
        memory_metrics = self._measure_real_memory_usage()

        # Baseline Memory
        baseline = memory_metrics["baseline"]
        results.append(PerformanceResult(
            name="Baseline Memory",
            expected={"min": 50, "max": 300},
            actual=round(baseline, 2),
            valid=50 <= baseline <= 300,
            unit="MB"
        ))

        # Cache Overhead
        cache_overhead = memory_metrics["cache_overhead"]
        results.append(PerformanceResult(
            name="Cache Overhead",
            expected={"min": 0.1, "max": 5.0},
            actual=round(cache_overhead, 2),
            valid=0.1 <= cache_overhead <= 5.0 if cache_overhead > 0 else False,
            unit="MB"
        ))

        return results

    def _validate_improvements(self) -> List[PerformanceResult]:
        """Validate performance improvement claims using real system"""
        results = []
        
        print("Testing performance improvements...")

        # Overall Improvement
        print("  - Measuring overall improvement...")
        overall = self._measure_real_improvement(size=2000)  # Smaller size for faster testing
        results.append(PerformanceResult(
            name="Overall Improvement",
            expected={"min": 5.0, "max": 20.0},
            actual=round(overall * 100, 1),
            valid=5.0 <= (overall * 100) <= 20.0 if overall > 0 else False,
            unit="%"
        ))

        # Large Dataset Improvement
        print("  - Measuring large dataset improvement...")
        large = self._measure_real_improvement(size=4000)
        results.append(PerformanceResult(
            name="Large Dataset Improvement",
            expected={"min": 10.0, "max": 25.0},
            actual=round(large * 100, 1),
            valid=10.0 <= (large * 100) <= 25.0 if large > 0 else False,
            unit="%"
        ))

        return results

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics"""
        total_validations = len(self.results)
        passed_validations = sum(1 for r in self.results if r.valid)
        
        return {
            "total_validations": total_validations,
            "passed_validations": passed_validations,
            "success_rate": (passed_validations / total_validations) * 100 if total_validations > 0 else 0,
            "timestamp": datetime.datetime.now().isoformat(),
            "system_available": SYSTEM_AVAILABLE
        }

    def save_results(self, filename: str = "real_system_validation_results.json"):
        """Save validation results to JSON file"""
        results = self.validate_all()
        
        # Convert to dictionary
        results_dict = asdict(results)
        
        # Save to file
        with open(filename, 'w') as f:
            json.dump(results_dict, f, indent=2)
        
        return filename

    def run_diagnostic_tests(self):
        """Run diagnostic tests to check system functionality"""
        print("\n" + "="*60)
        print("DIAGNOSTIC TESTS")
        print("="*60)
        
        if not SYSTEM_AVAILABLE:
            print("❌ System not available - cannot run diagnostic tests")
            return
        
        # Test each query type
        for query_name, query in self.test_queries.items():
            print(f"\nTesting {query_name}:")
            print("-" * 40)
            
            data = self._generate_realistic_test_data(100, "mixed")
            result = self._execute_query_safely(query, data)
            
            if result['success']:
                print(f"✅ Success - {result['result_count']} results in {result['execution_time']:.3f}s")
                if result['result_count'] > 0:
                    print(f"   Sample result columns: {list(result['result'].columns) if hasattr(result['result'], 'columns') else 'N/A'}")
            else:
                print(f"❌ Failed - {result['error']}")
                if 'traceback' in result:
                    print(f"   Traceback: {result['traceback'][:200]}...")

def main():
    """Run real system validation"""
    print("="*60)
    print("REAL SQL MATCH_RECOGNIZE SYSTEM VALIDATION")
    print("="*60)
    
    validator = RealSystemValidator()
    
    # Run diagnostic tests first
    validator.run_diagnostic_tests()
    
    # Run full validation
    print("\n" + "="*60)
    print("PERFORMANCE VALIDATION")
    print("="*60)
    
    results_file = validator.save_results()
    
    print(f"\nValidation results saved to: {results_file}")
    
    # Print summary
    with open(results_file) as f:
        results = json.load(f)
        
    print("\nValidation Summary:")
    print("==================")
    print(f"System: {results['system_info']['os']}")
    print(f"Python: {results['system_info']['python_version']}")
    print(f"CPU Cores: {results['system_info']['cpu_count']}")
    print(f"Memory: {results['system_info']['total_memory_gb']:.1f} GB")
    print(f"System Available: {results['system_info']['system_available']}")
    print(f"Timestamp: {results['system_info']['timestamp']}")
    print("\nResults:")
    
    categories = ['core_metrics', 'batch_processing', 'complexity', 
                 'memory_usage', 'improvements']
    
    for category in categories:
        print(f"\n{category.upper()}:")
        for result in results[category]:
            status = "✅" if result['valid'] else "❌"
            print(f"{status} {result['name']}: {result['actual']} {result['unit']}")
            if not result['valid']:
                print(f"   Expected: {result['expected']}")
            if result.get('details'):
                print(f"   Details: {result['details']}")

    print(f"\nOverall Success Rate: {results['summary']['success_rate']:.1f}%")
    
    if not results['system_info']['system_available']:
        print("\n⚠️  WARNING: Real system was not available during testing.")
        print("   The system imports are working but there may be missing functions.")
        print("   Check the import errors above for specific issues.")

if __name__ == "__main__":
    main()
