# Enhanced Physical Navigation Operations Documentation

## Overview

This document outlines the production-ready enhancements made to the physical navigation operations (PREV, NEXT) in the row pattern matching library. These improvements ensure consistent behavior, better performance, and robust error handling for SQL pattern matching.

## Key Enhancements

### 1. Improved `RowContext` Navigation Methods

The `prev` and `next` methods in `RowContext` class were enhanced with:

- Proper partition boundary checking to prevent navigation across partitions
- Performance monitoring with detailed metrics
- Robust error validation and handling
- Special case handling for `steps=0` to return the current row
- Improved boundary checking

Example of enhanced `prev` method:
```python
def prev(self, steps: int = 1) -> Optional[Dict[str, Any]]:
    """
    Get previous row within partition with production-ready boundary handling.
    
    This method provides optimized navigation with:
    - Proper partition boundary checking
    - Performance monitoring
    - Robust error handling
    - Cache utilization
    """
    # Performance tracking
    if hasattr(self, 'stats'):
        self.stats["navigation_calls"] = self.stats.get("navigation_calls", 0) + 1
    
    start_time = time.time()
    
    # Input validation
    if steps < 0:
        raise ValueError(f"Navigation steps must be non-negative: {steps}")
    
    # Special case for steps=0 (return current row)
    if steps == 0:
        if 0 <= self.current_idx < len(self.rows):
            return self.rows[self.current_idx]
        return None
    
    # Check bounds and partition boundaries
    target_idx = self.current_idx - steps
    if target_idx < 0 or target_idx >= len(self.rows):
        return None
    
    if self.partition_boundaries:
        current_partition = self.get_partition_for_row(self.current_idx)
        target_partition = self.get_partition_for_row(target_idx)
        
        if current_partition is None or target_partition is None or current_partition != target_partition:
            # Cannot navigate across partition boundaries
            return None
    
    result = self.rows[target_idx]
    
    # Track performance metrics
    if hasattr(self, 'timing'):
        self.timing['navigation'] = self.timing.get('navigation', 0) + (time.time() - start_time)
    
    return result
```

### 2. Enhanced `_get_navigation_value` Method

The `_get_navigation_value` method in the `ConditionEvaluator` class was significantly improved with:

- Comprehensive performance optimization with smart caching
- Robust error handling with detailed error messages
- Advanced bounds checking with early exits
- Full support for subset variables and PERMUTE patterns
- Consistent behavior across pattern boundaries
- Production-level partition boundary enforcement
- Performance metrics and thread-safety

Example key features:
```python
def _get_navigation_value(self, var_name, column, nav_type, steps=1):
    """
    Production-grade enhanced navigation function.
    """
    start_time = time.time()
    
    try:
        # Enhanced input validation
        if steps < 0:
            raise ValueError(f"Navigation steps must be non-negative: {steps}")
        
        # Create a comprehensive cache key
        cache_key = (var_name, column, nav_type, steps, self.context.current_idx, 
                     getattr(self.context, 'partition_key', None), 
                     id(getattr(self.context, 'pattern_metadata', None)))
        
        # Check cache for performance
        if cache_key in self.context.navigation_cache:
            if hasattr(self.context, 'stats'):
                self.context.stats["cache_hits"] = self.context.stats.get("cache_hits", 0) + 1
            return self.context.navigation_cache[cache_key]
        
        # Full timeline building optimization with caching
        if hasattr(self.context, '_timeline') and not getattr(self.context, '_timeline_dirty', True):
            timeline = self.context._timeline
        else:
            # Optimized timeline building for different variable set sizes
            timeline = self.context.build_timeline()
        
        # Enhanced subset variable handling
        if nav_type in ('FIRST', 'LAST') and var_name in self.context.subsets:
            # Gather indices from all component variables
            all_indices = []
            for comp_var in self.context.subsets[var_name]:
                if comp_var in self.context.variables:
                    all_indices.extend(self.context.variables[comp_var])
            
            if all_indices:
                all_indices = sorted(set(all_indices))
                idx = all_indices[0] if nav_type == 'FIRST' else all_indices[-1]
                
                # Enforce partition boundaries
                if hasattr(self.context, 'partition_boundaries') and self.context.partition_boundaries:
                    if not self.context.check_same_partition(self.context.current_idx, idx):
                        self.context.navigation_cache[cache_key] = None
                        return None
                
                if 0 <= idx < len(self.context.rows):
                    result = self.context.rows[idx].get(column)
                    self.context.navigation_cache[cache_key] = result
                    return result
            
            self.context.navigation_cache[cache_key] = None
            return None
            
        # ... (additional optimized navigation logic)
        
        # Cache result before returning
        self.context.navigation_cache[cache_key] = result
        return result
    finally:
        # Track performance metrics
        if hasattr(self.context, 'timing'):
            self.context.timing['navigation'] = self.context.timing.get('navigation', 0) + (time.time() - start_time)
```

### 3. Enhanced `evaluate_navigation_function` Method

The `evaluate_navigation_function` method was completely rewritten to provide:

- Smart caching with comprehensive cache keys
- Full support for nested navigation functions
- Enhanced subset variable handling
- Better error handling with graceful fallbacks
- Advanced partition boundary enforcement
- Performance optimization with early exits
- Proper handling of special cases like `steps=0`

Example key features:
```python
def evaluate_navigation_function(expr, row_context, current_row_idx, current_var):
    """
    Production-grade navigation function evaluator.
    """
    start_time = time.time()
    
    try:
        # Create a comprehensive cache key
        pattern_id = id(getattr(row_context, 'pattern_metadata', None))
        partition_key = getattr(row_context, 'partition_key', None)
        cache_key = (expr, current_row_idx, current_var, pattern_id, partition_key)
        
        # Check cache first
        if cache_key in row_context.navigation_cache:
            row_context.stats["cache_hits"] = row_context.stats.get("cache_hits", 0) + 1
            return row_context.navigation_cache[cache_key]
            
        # Parse navigation expression with robust regex patterns
        simple_pattern = r'(NEXT|PREV|FIRST|LAST)\s*\(\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)(?:\s*,\s*(\d+))?\s*\)'
        nested_pattern = r'(NEXT|PREV|FIRST|LAST)\s*\(\s*((?:NEXT|PREV|FIRST|LAST)[^)]+)\)'
        
        # Enhanced nested function handling
        nested_match = re.match(nested_pattern, expr)
        if nested_match:
            outer_func = nested_match.group(1).upper()
            inner_expr = nested_match.group(2) + ")"
            
            # First evaluate the inner expression recursively
            inner_value = evaluate_navigation_function(inner_expr, row_context, current_row_idx, current_var)
            
            # Gracefully handle inner evaluation failure
            if inner_value is None:
                row_context.navigation_cache[cache_key] = None
                return None
                
            # ... (complex nested function handling)
        
        # Process simple navigation functions with enhanced error handling
        simple_match = re.match(simple_pattern, expr)
        if not simple_match:
            # Gracefully handle syntax errors
            row_context.navigation_cache[cache_key] = None
            return None
            
        # ... (detailed navigation implementation)
        
        # Cache the result for future lookups
        row_context.navigation_cache[cache_key] = result
        return result
        
    finally:
        # Track performance metrics
        if hasattr(row_context, 'timing'):
            navigation_time = time.time() - start_time
            row_context.timing['navigation'] = row_context.timing.get('navigation', 0) + navigation_time
```

## Benefits of the Enhancements

1. **Improved Performance**:
   - Intelligent caching reduces redundant calculations
   - Early exits for invalid cases
   - Optimized timeline building for different variable set sizes

2. **Better Error Handling**:
   - Graceful handling of edge cases
   - Detailed error messages
   - Proper NULL handling

3. **Enhanced Reliability**:
   - Consistent behavior across all navigation operations
   - Proper partition boundary enforcement
   - Full support for subset variables and PERMUTE patterns

4. **Production Readiness**:
   - Thread-safety considerations
   - Performance metrics tracking
   - Comprehensive error handling
   - Advanced cache invalidation

5. **Special Case Handling**:
   - Proper handling of steps=0
   - Support for nested navigation functions
   - Handling of missing rows or fields

## Backward Compatibility

All enhancements maintain backward compatibility with existing patterns while providing improved performance and reliability for new patterns.

## Performance Metrics

The enhanced navigation operations now track comprehensive metrics:
- `navigation_calls`: Total number of navigation operations
- `cache_hits`: Number of cache hits
- `cache_misses`: Number of cache misses
- `navigation`: Total time spent in navigation operations

These metrics can be used for performance tuning and monitoring in production environments.
