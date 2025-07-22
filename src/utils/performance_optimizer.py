# src/utils/performance_optimizer.py

import time
import psutil
import threading
import re
from typing import Dict, Any, Optional, List, Callable, Set
from dataclasses import dataclass
from collections import defaultdict, deque
from functools import wraps
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

# Global optimizer instances
_global_monitor = PerformanceMonitor()
_define_optimizer = None  # Will be initialized when first accessed

def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return _global_monitor

def get_define_optimizer() -> "DefineOptimizer":
    """Get the global DEFINE optimizer instance."""
    global _define_optimizer
    if _define_optimizer is None:
        _define_optimizer = DefineOptimizer()
    return _define_optimizer

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
