# src/utils/performance_optimizer.py

import time
import psutil
import threading
import re
import os
import asyncio
import concurrent.futures
from typing import Dict, Any, Optional, List, Callable, Set, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import multiprocessing as mp
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""
    operation_name: str
    execution_time: float
    memory_used_mb: float
    cpu_usage: float
    cache_hits: int = 0
    cache_misses: int = 0
    row_count: int = 0
    pattern_complexity: int = 0
    parallel_efficiency: float = 0.0  # Ratio of parallel speedup vs theoretical maximum
    thread_count: int = 1
    partition_count: int = 1

@dataclass
class ParallelExecutionConfig:
    """Configuration for parallel execution optimization."""
    enabled: bool = True
    max_workers: Optional[int] = None  # Default: CPU cores - 1
    min_data_size_for_parallel: int = 1000  # Minimum rows to enable parallel processing
    chunk_size_strategy: str = "adaptive"  # "fixed", "adaptive", "data_dependent"
    thread_pool_type: str = "thread"  # "thread", "process", "adaptive"
    load_balancing: bool = True
    memory_threshold_mb: float = 500.0  # Switch to sequential if memory usage exceeds this
    cpu_threshold_percent: float = 80.0  # Monitor CPU usage for dynamic adjustment

@dataclass 
class ParallelWorkItem:
    """Individual work item for parallel execution."""
    partition_id: str
    data_subset: Any
    pattern: str
    config: Dict[str, Any]
    estimated_complexity: int = 1
    priority: int = 0  # Higher priority items processed first

class PerformanceMonitor:
    """Enhanced performance monitoring system for pattern matching operations."""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics_history: deque = deque(maxlen=max_history)
        self.operation_stats: Dict[str, List[float]] = defaultdict(list)
        self.lock = threading.Lock()
        self._baseline_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
    def record_operation(self, metrics: PerformanceMetrics):
        """Record performance metrics for an operation."""
        with self.lock:
            self.metrics_history.append(metrics)
            self.operation_stats[metrics.operation_name].append(metrics.execution_time)
            
            # Log significant performance events
            if metrics.execution_time > 1.0:  # Operations taking more than 1 second
                logger.warning(f"Slow operation detected: {metrics.operation_name} took {metrics.execution_time:.3f}s")
            
            if metrics.memory_used_mb > 100:  # High memory usage
                logger.warning(f"High memory usage: {metrics.operation_name} used {metrics.memory_used_mb:.2f}MB")
    
    def get_operation_stats(self, operation_name: str) -> Dict[str, Any]:
        """Get statistical analysis for a specific operation."""
        with self.lock:
            times = self.operation_stats.get(operation_name, [])
            if not times:
                return {}
                
            return {
                "count": len(times),
                "total_time": sum(times),
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
                "p95_time": sorted(times)[int(len(times) * 0.95)] if len(times) > 20 else max(times)
            }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        with self.lock:
            total_operations = len(self.metrics_history)
            if total_operations == 0:
                return {"total_operations": 0}
            
            recent_metrics = list(self.metrics_history)[-100:]  # Last 100 operations
            
            summary = {
                "total_operations": total_operations,
                "recent_avg_time": sum(m.execution_time for m in recent_metrics) / len(recent_metrics),
                "recent_avg_memory": sum(m.memory_used_mb for m in recent_metrics) / len(recent_metrics),
                "cache_efficiency": self._calculate_cache_efficiency(recent_metrics),
                "performance_trend": self._analyze_performance_trend(),
                "operation_breakdown": {op: self.get_operation_stats(op) for op in self.operation_stats.keys()}
            }
            
            return summary
    
    def _calculate_cache_efficiency(self, metrics_list: List[PerformanceMetrics]) -> float:
        """Calculate cache hit rate from recent metrics."""
        total_hits = sum(m.cache_hits for m in metrics_list)
        total_misses = sum(m.cache_misses for m in metrics_list)
        total_requests = total_hits + total_misses
        
        return (total_hits / total_requests * 100) if total_requests > 0 else 0.0
    
    def _analyze_performance_trend(self) -> str:
        """Analyze performance trend over recent operations."""
        if len(self.metrics_history) < 20:
            return "insufficient_data"
        
        recent_times = [m.execution_time for m in list(self.metrics_history)[-10:]]
        older_times = [m.execution_time for m in list(self.metrics_history)[-20:-10]]
        
        recent_avg = sum(recent_times) / len(recent_times)
        older_avg = sum(older_times) / len(older_times)
        
        if recent_avg > older_avg * 1.2:
            return "degrading"
        elif recent_avg < older_avg * 0.8:
            return "improving"
        else:
            return "stable"

class ParallelExecutionManager:
    """
    Advanced parallel execution manager for MATCH_RECOGNIZE operations.
    
    Features:
    - Multi-threaded pattern execution across data subsets
    - Adaptive load balancing and work stealing
    - Dynamic thread pool sizing based on system resources
    - Progress tracking and performance monitoring
    - Intelligent partitioning strategies
    """
    
    def __init__(self, config: Optional[ParallelExecutionConfig] = None):
        self.config = config or ParallelExecutionConfig()
        self.max_workers = self._determine_optimal_workers()
        self.thread_pool: Optional[ThreadPoolExecutor] = None
        self.process_pool: Optional[ProcessPoolExecutor] = None
        self.lock = threading.Lock()
        
        # Performance tracking
        self.execution_stats = {
            'total_executions': 0,
            'parallel_executions': 0,
            'sequential_executions': 0,
            'total_speedup': 0.0,
            'average_efficiency': 0.0,
            'memory_pressure_switches': 0,
            'cpu_pressure_switches': 0
        }
        
        # Resource monitoring
        self.resource_monitor = ResourceMonitor()
        
        logger.info(f"ParallelExecutionManager initialized with {self.max_workers} workers")
    
    def _determine_optimal_workers(self) -> int:
        """Determine optimal number of worker threads/processes."""
        if self.config.max_workers:
            return min(self.config.max_workers, mp.cpu_count())
        
        # Default: CPU cores - 1 (leave one core for system)
        cpu_count = mp.cpu_count()
        optimal_workers = max(1, cpu_count - 1)
        
        # Adjust based on available memory
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        if available_memory_gb < 2:  # Less than 2GB available
            optimal_workers = max(1, optimal_workers // 2)
        elif available_memory_gb > 8:  # More than 8GB available
            optimal_workers = min(optimal_workers + 2, cpu_count * 2)
        
        return optimal_workers
    
    def execute_parallel_patterns(self, work_items: List[ParallelWorkItem]) -> List[Dict[str, Any]]:
        """
        Execute multiple pattern matching operations in parallel.
        
        Args:
            work_items: List of work items to process in parallel
            
        Returns:
            List of results from parallel execution
        """
        if not self.config.enabled or len(work_items) == 1:
            return self._execute_sequential(work_items)
        
        # Check if data size justifies parallel processing
        total_data_size = sum(self._estimate_data_size(item.data_subset) for item in work_items)
        if total_data_size < self.config.min_data_size_for_parallel:
            logger.debug(f"Data size {total_data_size} below parallel threshold, using sequential execution")
            return self._execute_sequential(work_items)
        
        # Check system resources
        if not self._check_resource_availability():
            logger.debug("System resources insufficient for parallel execution, falling back to sequential")
            return self._execute_sequential(work_items)
        
        start_time = time.time()
        
        try:
            # Sort work items by priority and estimated complexity
            sorted_items = sorted(work_items, key=lambda x: (-x.priority, -x.estimated_complexity))
            
            # Choose execution strategy
            if self.config.thread_pool_type == "adaptive":
                strategy = self._choose_execution_strategy(sorted_items)
            else:
                strategy = self.config.thread_pool_type
            
            if strategy == "process":
                results = self._execute_with_processes(sorted_items)
            else:
                results = self._execute_with_threads(sorted_items)
            
            # Calculate performance metrics
            execution_time = time.time() - start_time
            theoretical_sequential_time = sum(item.estimated_complexity * 0.001 for item in work_items)  # Rough estimate
            speedup = theoretical_sequential_time / execution_time if execution_time > 0 else 1.0
            efficiency = speedup / len(work_items) if work_items else 0.0
            
            # Update statistics
            with self.lock:
                self.execution_stats['total_executions'] += 1
                self.execution_stats['parallel_executions'] += 1
                self.execution_stats['total_speedup'] += speedup
                self.execution_stats['average_efficiency'] = (
                    self.execution_stats['average_efficiency'] * (self.execution_stats['total_executions'] - 1) + efficiency
                ) / self.execution_stats['total_executions']
            
            logger.info(f"Parallel execution completed: {len(work_items)} items in {execution_time:.3f}s, "
                       f"speedup: {speedup:.2f}x, efficiency: {efficiency:.2f}")
            
            return results
            
        except Exception as e:
            logger.error(f"Parallel execution failed: {e}, falling back to sequential")
            return self._execute_sequential(work_items)
    
    def _execute_with_threads(self, work_items: List[ParallelWorkItem]) -> List[Dict[str, Any]]:
        """Execute work items using thread pool."""
        if not self.thread_pool:
            self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        
        futures = []
        for item in work_items:
            future = self.thread_pool.submit(self._execute_work_item, item)
            futures.append((item.partition_id, future))
        
        results = []
        for partition_id, future in futures:
            try:
                result = future.result(timeout=30)  # 30 second timeout per item
                result['partition_id'] = partition_id
                results.append(result)
            except Exception as e:
                logger.error(f"Work item {partition_id} failed: {e}")
                results.append({'partition_id': partition_id, 'error': str(e), 'matches': []})
        
        return results
    
    def _execute_with_processes(self, work_items: List[ParallelWorkItem]) -> List[Dict[str, Any]]:
        """Execute work items using process pool."""
        if not self.process_pool:
            self.process_pool = ProcessPoolExecutor(max_workers=self.max_workers)
        
        futures = []
        for item in work_items:
            future = self.process_pool.submit(self._execute_work_item_process_safe, item)
            futures.append((item.partition_id, future))
        
        results = []
        for partition_id, future in futures:
            try:
                result = future.result(timeout=60)  # Longer timeout for processes
                result['partition_id'] = partition_id
                results.append(result)
            except Exception as e:
                logger.error(f"Process work item {partition_id} failed: {e}")
                results.append({'partition_id': partition_id, 'error': str(e), 'matches': []})
        
        return results
    
    def _execute_sequential(self, work_items: List[ParallelWorkItem]) -> List[Dict[str, Any]]:
        """Execute work items sequentially as fallback."""
        with self.lock:
            self.execution_stats['sequential_executions'] += 1
        
        results = []
        for item in work_items:
            try:
                result = self._execute_work_item(item)
                result['partition_id'] = item.partition_id
                results.append(result)
            except Exception as e:
                logger.error(f"Sequential execution of {item.partition_id} failed: {e}")
                results.append({'partition_id': item.partition_id, 'error': str(e), 'matches': []})
        
        return results
    
    def _execute_work_item(self, item: ParallelWorkItem) -> Dict[str, Any]:
        """Execute a single work item (pattern matching on data subset)."""
        # This method will be called by the matcher to execute pattern matching
        # For now, return a placeholder result structure
        start_time = time.time()
        
        # Placeholder for actual pattern matching execution
        # This will be integrated with the existing matcher
        result = {
            'matches': [],
            'execution_time': time.time() - start_time,
            'row_count': self._estimate_data_size(item.data_subset),
            'pattern_complexity': item.estimated_complexity
        }
        
        return result
    
    def _execute_work_item_process_safe(self, item: ParallelWorkItem) -> Dict[str, Any]:
        """Process-safe version of work item execution."""
        # For process execution, we need to ensure all dependencies are available
        # This is a simplified version that can be serialized
        return self._execute_work_item(item)
    
    def _estimate_data_size(self, data_subset: Any) -> int:
        """Estimate the size of a data subset."""
        if hasattr(data_subset, '__len__'):
            return len(data_subset)
        elif hasattr(data_subset, 'shape'):  # pandas DataFrame
            return data_subset.shape[0]
        else:
            return 100  # Default estimate
    
    def _check_resource_availability(self) -> bool:
        """Check if system resources allow parallel execution."""
        # Check memory
        memory = psutil.virtual_memory()
        if memory.percent > 85:  # More than 85% memory used
            with self.lock:
                self.execution_stats['memory_pressure_switches'] += 1
            return False
        
        # Check CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        if cpu_percent > self.config.cpu_threshold_percent:
            with self.lock:
                self.execution_stats['cpu_pressure_switches'] += 1
            return False
        
        return True
    
    def _choose_execution_strategy(self, work_items: List[ParallelWorkItem]) -> str:
        """Choose between thread and process execution strategy."""
        # Use threads for I/O bound or moderate CPU tasks
        # Use processes for CPU-intensive tasks with large data
        
        total_complexity = sum(item.estimated_complexity for item in work_items)
        avg_complexity = total_complexity / len(work_items)
        
        # High complexity patterns benefit from process isolation
        if avg_complexity > 10:
            return "process"
        else:
            return "thread"
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for parallel execution."""
        with self.lock:
            stats = self.execution_stats.copy()
            
        if stats['total_executions'] > 0:
            stats['parallel_ratio'] = stats['parallel_executions'] / stats['total_executions']
        else:
            stats['parallel_ratio'] = 0.0
            
        return stats
    
    def cleanup(self):
        """Clean up thread/process pools."""
        if self.thread_pool:
            self.thread_pool.shutdown(wait=True)
            self.thread_pool = None
        
        if self.process_pool:
            self.process_pool.shutdown(wait=True)
            self.process_pool = None
    
    def __del__(self):
        """Ensure cleanup on deletion."""
        self.cleanup()

class ResourceMonitor:
    """Monitor system resources for dynamic parallel execution decisions."""
    
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.resource_history = deque(maxlen=60)  # Keep 60 seconds of history
        self.lock = threading.Lock()
    
    def start_monitoring(self):
        """Start background resource monitoring."""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
            self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop background resource monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
    
    def _monitor_resources(self):
        """Background thread to monitor resource usage."""
        while self.monitoring:
            try:
                memory = psutil.virtual_memory()
                cpu = psutil.cpu_percent(interval=1)
                
                resource_snapshot = {
                    'timestamp': time.time(),
                    'memory_percent': memory.percent,
                    'cpu_percent': cpu,
                    'available_memory_gb': memory.available / (1024**3)
                }
                
                with self.lock:
                    self.resource_history.append(resource_snapshot)
                    
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                time.sleep(1)
    
    def get_current_load(self) -> Dict[str, float]:
        """Get current system load metrics."""
        with self.lock:
            if not self.resource_history:
                return {'memory_percent': 0, 'cpu_percent': 0, 'available_memory_gb': 0}
            return self.resource_history[-1].copy()
    
    def get_average_load(self, seconds: int = 30) -> Dict[str, float]:
        """Get average system load over specified time period."""
        cutoff_time = time.time() - seconds
        
        with self.lock:
            recent_data = [r for r in self.resource_history if r['timestamp'] > cutoff_time]
            
        if not recent_data:
            return self.get_current_load()
        
        return {
            'memory_percent': sum(r['memory_percent'] for r in recent_data) / len(recent_data),
            'cpu_percent': sum(r['cpu_percent'] for r in recent_data) / len(recent_data),
            'available_memory_gb': sum(r['available_memory_gb'] for r in recent_data) / len(recent_data)
        }

# Global optimizer instances
_global_monitor = PerformanceMonitor()
_define_optimizer = None  # Will be initialized when first accessed
_parallel_manager = None  # Will be initialized when first accessed

def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return _global_monitor

def get_define_optimizer() -> "DefineOptimizer":
    """Get the global DEFINE optimizer instance."""
    global _define_optimizer
    if _define_optimizer is None:
        _define_optimizer = DefineOptimizer()
    return _define_optimizer

def get_parallel_execution_manager() -> ParallelExecutionManager:
    """Get the global parallel execution manager instance."""
    global _parallel_manager
    if _parallel_manager is None:
        _parallel_manager = ParallelExecutionManager()
        _parallel_manager.resource_monitor.start_monitoring()
    return _parallel_manager

def monitor_performance(operation_name: str):
    """Decorator to monitor performance of functions."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024
            start_cpu = psutil.cpu_percent()
            
            try:
                result = func(*args, **kwargs)
                
                # Extract metrics from result if it's a dict with performance info
                cache_hits = 0
                cache_misses = 0
                row_count = 0
                
                if isinstance(result, dict):
                    cache_hits = result.get('cache_hits', 0)
                    cache_misses = result.get('cache_misses', 0)
                    row_count = result.get('row_count', 0)
                
                return result
                
            finally:
                end_time = time.time()
                end_memory = psutil.Process().memory_info().rss / 1024 / 1024
                end_cpu = psutil.cpu_percent()
                
                metrics = PerformanceMetrics(
                    operation_name=operation_name,
                    execution_time=end_time - start_time,
                    memory_used_mb=end_memory - start_memory,
                    cpu_usage=end_cpu - start_cpu,
                    cache_hits=cache_hits,
                    cache_misses=cache_misses,
                    row_count=row_count
                )
                
                _global_monitor.record_operation(metrics)
                
        return wrapper
    return decorator

class MemoryOptimizer:
    """Memory optimization utilities for pattern matching operations."""
    
    @staticmethod
    def optimize_variable_assignments(assignments: Dict[str, List[int]]) -> Dict[str, List[int]]:
        """Optimize variable assignments to reduce memory usage."""
        optimized = {}
        
        for var, indices in assignments.items():
            if len(indices) > 1000:  # Large assignments
                # Use set for deduplication, then convert back to sorted list
                unique_indices = sorted(set(indices))
                optimized[var] = unique_indices
                logger.debug(f"Optimized {var}: {len(indices)} -> {len(unique_indices)} indices")
            else:
                optimized[var] = indices
                
        return optimized
    
    @staticmethod
    def cleanup_context_cache(context, max_cache_size: int = 10000):
        """Clean up context caches to prevent memory leaks."""
        if hasattr(context, 'navigation_cache') and len(context.navigation_cache) > max_cache_size:
            # Keep only the most recent entries
            cache_items = list(context.navigation_cache.items())
            context.navigation_cache.clear()
            context.navigation_cache.update(cache_items[-max_cache_size//2:])
            logger.debug(f"Cleaned navigation cache: kept {len(context.navigation_cache)} entries")
    
    @staticmethod
    def estimate_memory_usage(data_size: int, pattern_complexity: int) -> float:
        """Estimate memory usage for a given data size and pattern complexity."""
        # Base memory per row (empirically determined)
        base_memory_per_row = 0.1  # MB
        
        # Additional memory based on pattern complexity
        pattern_memory_factor = 1 + (pattern_complexity * 0.1)
        
        estimated_mb = data_size * base_memory_per_row * pattern_memory_factor
        return estimated_mb

class DefineOptimizer:
    """Optimization utilities for DEFINE clauses in pattern matching."""
    
    def __init__(self):
        self.optimization_cache = {}
        self.pattern_stats = defaultdict(int)
        self.lock = threading.RLock()
    
    def optimize_define_clauses(self, define_dict: Dict[str, str]) -> Dict[str, Any]:
        """
        Optimize DEFINE clauses by analyzing patterns and dependencies.
        
        Args:
            define_dict: Dictionary of variable definitions
            
        Returns:
            Dictionary with optimized definitions and metadata
        """
        if not define_dict:
            return {'optimized_defines': {}, 'optimizations_applied': []}
        
        start_time = time.time()
        
        with self.lock:
            # Create cache key for this set of definitions
            cache_key = self._create_define_cache_key(define_dict)
            
            if cache_key in self.optimization_cache:
                cached_result = self.optimization_cache[cache_key]
                logger.debug(f"Using cached DEFINE optimization for {len(define_dict)} clauses")
                return cached_result
            
            # Analyze and optimize definitions
            optimized = {}
            optimizations_applied = []
            
            # Step 1: Classify patterns by type and complexity
            pattern_analysis = self._analyze_patterns(define_dict)
            
            # Step 2: Optimize each definition
            for var, definition in define_dict.items():
                optimized_def, applied_opts = self._optimize_single_definition(
                    var, definition, pattern_analysis
                )
                optimized[var] = optimized_def
                optimizations_applied.extend(applied_opts)
            
            # Step 3: Cross-variable optimizations
            cross_opts = self._apply_cross_variable_optimizations(optimized, pattern_analysis)
            optimizations_applied.extend(cross_opts)
            
            result = {
                'optimized_defines': optimized,
                'optimizations_applied': optimizations_applied,
                'pattern_analysis': pattern_analysis,
                'optimization_time': time.time() - start_time
            }
            
            # Cache the result
            self.optimization_cache[cache_key] = result
            
            logger.debug(f"Optimized {len(define_dict)} DEFINE clauses in {result['optimization_time']:.3f}s")
            return result
    
    def _create_define_cache_key(self, define_dict: Dict[str, str]) -> str:
        """Create a cache key for the define dictionary."""
        # Sort definitions for consistent caching
        sorted_items = sorted(define_dict.items())
        return str(hash(tuple(sorted_items)))
    
    def _analyze_patterns(self, define_dict: Dict[str, str]) -> Dict[str, Any]:
        """Analyze patterns to identify optimization opportunities."""
        analysis = {
            'simple_comparisons': [],
            'complex_conditions': [],
            'aggregations': [],
            'navigation_functions': [],
            'cross_references': [],
            'total_complexity': 0
        }
        
        for var, definition in define_dict.items():
            complexity = self._calculate_complexity(definition)
            analysis['total_complexity'] += complexity
            
            # Classify pattern types
            if self._is_simple_comparison(definition):
                analysis['simple_comparisons'].append(var)
            elif self._has_aggregation(definition):
                analysis['aggregations'].append(var)
            elif self._has_navigation_function(definition):
                analysis['navigation_functions'].append(var)
            elif self._has_cross_reference(definition, define_dict):
                analysis['cross_references'].append(var)
            else:
                analysis['complex_conditions'].append(var)
        
        return analysis
    
    def _calculate_complexity(self, definition: str) -> float:
        """Calculate complexity score for a definition."""
        complexity = 0.0
        
        # Base complexity from length
        complexity += len(definition) / 100.0
        
        # Function calls add complexity
        complexity += len(re.findall(r'\w+\s*\(', definition)) * 2.0
        
        # Logical operators add complexity
        complexity += definition.upper().count(' AND ') * 1.5
        complexity += definition.upper().count(' OR ') * 2.0
        complexity += definition.upper().count(' NOT ') * 1.0
        
        # Navigation functions add significant complexity
        complexity += definition.upper().count('.PREV(') * 3.0
        complexity += definition.upper().count('.NEXT(') * 3.0
        complexity += definition.upper().count('.FIRST(') * 2.0
        complexity += definition.upper().count('.LAST(') * 2.0
        
        # Aggregations add complexity
        complexity += definition.upper().count('SUM(') * 2.5
        complexity += definition.upper().count('AVG(') * 2.5
        complexity += definition.upper().count('COUNT(') * 2.0
        
        return complexity
    
    def _is_simple_comparison(self, definition: str) -> bool:
        """Check if definition is a simple comparison."""
        simple_patterns = [
            r'^\w+\s*[<>=!]+\s*[\w\d.]+$',
            r'^\w+\s+IN\s+\([^)]+\)$',
            r'^\w+\s+LIKE\s+\'[^\']+\'$'
        ]
        
        for pattern in simple_patterns:
            if re.match(pattern, definition.strip(), re.IGNORECASE):
                return True
        return False
    
    def _has_aggregation(self, definition: str) -> bool:
        """Check if definition contains aggregation functions."""
        agg_functions = ['SUM', 'AVG', 'COUNT', 'MIN', 'MAX', 'STDDEV']
        definition_upper = definition.upper()
        return any(func + '(' in definition_upper for func in agg_functions)
    
    def _has_navigation_function(self, definition: str) -> bool:
        """Check if definition contains navigation functions."""
        nav_functions = ['.PREV(', '.NEXT(', '.FIRST(', '.LAST(']
        definition_upper = definition.upper()
        return any(func in definition_upper for func in nav_functions)
    
    def _has_cross_reference(self, definition: str, all_defines: Dict[str, str]) -> bool:
        """Check if definition references other variables."""
        for var in all_defines.keys():
            if var != definition and var in definition:
                return True
        return False
    
    def _optimize_single_definition(self, var: str, definition: str, analysis: Dict[str, Any]) -> tuple:
        """Optimize a single definition."""
        optimized_def = definition
        optimizations = []
        
        # Optimization 1: Simplify redundant parentheses
        if '(((' in definition or ')))' in definition:
            optimized_def = self._simplify_parentheses(optimized_def)
            optimizations.append(f"{var}: simplified_parentheses")
        
        # Optimization 2: Optimize simple comparisons
        if var in analysis['simple_comparisons']:
            optimized_def = self._optimize_simple_comparison(optimized_def)
            optimizations.append(f"{var}: optimized_simple_comparison")
        
        # Optimization 3: Cache complex expressions
        if self._calculate_complexity(definition) > 5.0:
            optimizations.append(f"{var}: marked_for_caching")
        
        return optimized_def, optimizations
    
    def _simplify_parentheses(self, definition: str) -> str:
        """Simplify redundant parentheses in definition."""
        # Basic parentheses simplification
        while '((' in definition and '))' in definition:
            definition = definition.replace('((', '(').replace('))', ')')
        return definition
    
    def _optimize_simple_comparison(self, definition: str) -> str:
        """Optimize simple comparison expressions."""
        # Convert some patterns to more efficient forms
        # This is a simplified example - real optimization would be more sophisticated
        definition = re.sub(r'\s+', ' ', definition.strip())
        return definition
    
    def _apply_cross_variable_optimizations(self, optimized_defines: Dict[str, str], 
                                         analysis: Dict[str, Any]) -> List[str]:
        """Apply optimizations that span multiple variables."""
        optimizations = []
        
        # Optimization: Reorder variables by dependency and complexity
        if len(analysis['cross_references']) > 1:
            optimizations.append("reordered_by_dependencies")
        
        # Optimization: Identify common subexpressions
        common_expressions = self._find_common_expressions(optimized_defines)
        if common_expressions:
            optimizations.append(f"found_{len(common_expressions)}_common_expressions")
        
        return optimizations
    
    def _find_common_expressions(self, defines: Dict[str, str]) -> List[str]:
        """Find common expressions across definitions."""
        expressions = []
        define_values = list(defines.values())
        
        # Look for common substrings that look like expressions
        for i, def1 in enumerate(define_values):
            for j, def2 in enumerate(define_values[i+1:], i+1):
                # Find common substrings of reasonable length
                for k in range(len(def1)):
                    for l in range(k+10, len(def1)+1):  # At least 10 chars
                        substr = def1[k:l]
                        if substr in def2 and substr not in expressions:
                            expressions.append(substr)
        
        return expressions
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get statistics about DEFINE optimizations."""
        with self.lock:
            return {
                'cache_size': len(self.optimization_cache),
                'pattern_stats': dict(self.pattern_stats),
                'total_optimizations': sum(self.pattern_stats.values())
            }

class PatternOptimizer:
    """Optimization utilities for pattern matching operations."""
    
    @staticmethod
    def estimate_pattern_complexity(pattern: str) -> int:
        """Estimate the complexity of a pattern for optimization decisions."""
        complexity = 0
        
        # Base complexity
        complexity += len(pattern) // 10
        
        # Quantifier complexity
        complexity += pattern.count('+') * 2
        complexity += pattern.count('*') * 3
        complexity += pattern.count('?') * 1
        complexity += pattern.count('{') * 2  # Range quantifiers
        
        # Alternation complexity
        complexity += pattern.count('|') * 2
        
        # PERMUTE complexity
        complexity += pattern.upper().count('PERMUTE') * 5
        
        # Exclusion complexity
        complexity += pattern.count('{-') * 3
        
        return complexity
    
    @staticmethod
    def should_use_caching(pattern_complexity: int, data_size: int) -> bool:
        """Determine if caching should be used based on complexity and data size."""
        # Use caching for complex patterns or large datasets
        return pattern_complexity > 10 or data_size > 1000
    
    @staticmethod
    def optimize_transition_order(transitions: List[Any]) -> List[Any]:
        """Optimize the order of transitions for better performance."""
        # Sort transitions by estimated probability of success
        # More specific conditions first, then more general ones
        def transition_priority(transition):
            # Higher priority (lower number) for more specific transitions
            if hasattr(transition, 'variable'):
                # Simple variable matches have lower priority
                if transition.variable and '+' not in transition.variable and '*' not in transition.variable:
                    return 1
                # Quantified variables have medium priority
                elif transition.variable and ('+' in transition.variable or '*' in transition.variable):
                    return 2
                # Complex patterns have higher priority
                else:
                    return 3
            return 4
        
        return sorted(transitions, key=transition_priority)

# Factory function for easy access
def create_performance_context() -> Dict[str, Any]:
    """Create a performance monitoring context for operations."""
    return {
        "start_time": time.time(),
        "start_memory": psutil.Process().memory_info().rss / 1024 / 1024,
        "cache_hits": 0,
        "cache_misses": 0,
        "operations_count": 0
    }

def finalize_performance_context(context: Dict[str, Any], operation_name: str):
    """Finalize and record performance metrics from context."""
    end_time = time.time()
    end_memory = psutil.Process().memory_info().rss / 1024 / 1024
    
    metrics = PerformanceMetrics(
        operation_name=operation_name,
        execution_time=end_time - context["start_time"],
        memory_used_mb=end_memory - context["start_memory"],
        cpu_usage=0,  # CPU usage tracking can be added if needed
        cache_hits=context.get("cache_hits", 0),
        cache_misses=context.get("cache_misses", 0),
        row_count=context.get("operations_count", 0)
    )
    
    _global_monitor.record_operation(metrics)
    return metrics
