#!/usr/bin/env python3

"""
Fix for the SQL:2016 partition handling issue in match_recognize implementation.

This module contains the fix for the partition boundary handling bug in the 
condition evaluator that was causing test_sql2016_partition_handling to fail.
"""

import os
import sys

# Add the src directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.matcher.condition_evaluator import ConditionEvaluator
from src.utils.logging_config import get_logger

# Module logger
logger = get_logger(__name__)

def apply_partition_fix():
    """
    Apply the fix for partition boundary handling in condition evaluation.
    
    This fix addresses the issue where the first row in each partition wasn't
    being properly evaluated for the initial pattern variable (typically 'A'),
    causing the pattern matching to fail at partition boundaries.
    """
    # Store the original method for reference
    original_method = ConditionEvaluator._get_variable_column_value
    
    def fixed_get_variable_column_value(self, var_name, col_name, ctx):
        """
        Enhanced implementation that properly handles partition boundaries.
        
        This fixed implementation ensures that when evaluating the first row in
        a partition, we correctly use the current row's value regardless of 
        whether it's a self-reference or has been previously matched.
        """
        # Check if we're in DEFINE evaluation mode
        is_define_mode = self.evaluation_mode == 'DEFINE'
        
        # DEBUG: Enhanced logging to trace exact values
        current_var = getattr(ctx, 'current_var', None)
        logger.debug(f"[DEBUG] _get_variable_column_value: var_name={var_name}, col_name={col_name}, is_define_mode={is_define_mode}, current_var={current_var}")
        logger.debug(f"[DEBUG] ctx.current_idx={ctx.current_idx}, ctx.variables={ctx.variables}")
        
        # CRITICAL FIX: In DEFINE mode, we need special handling for pattern variable references
        if is_define_mode:
            # Check if this is the first row in a partition
            is_partition_boundary = False
            if ctx.partition_boundaries and ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                for start, end in ctx.partition_boundaries:
                    if ctx.current_idx == start:
                        is_partition_boundary = True
                        logger.debug(f"[DEBUG] Found partition boundary at idx={ctx.current_idx}")
                        break
            
            # CRITICAL FIX: At partition boundaries, always use current row's value
            # This ensures the first row in each partition can correctly match the pattern
            if is_partition_boundary:
                logger.debug(f"[DEBUG] PARTITION BOUNDARY: Using current row for {var_name}.{col_name} at idx={ctx.current_idx}")
                if ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                    value = ctx.rows[ctx.current_idx].get(col_name)
                    logger.debug(f"[DEBUG] Partition boundary value: {var_name}.{col_name} = {value} (from row {ctx.current_idx})")
                    return value
            
            # Self-reference handling (for the variable currently being evaluated)
            if var_name == current_var:
                # Self-reference: use current row being tested
                logger.debug(f"[DEBUG] DEFINE mode - self-reference for {var_name}.{col_name}")
                if ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                    value = ctx.rows[ctx.current_idx].get(col_name)
                    logger.debug(f"[DEBUG] Self-reference value: {var_name}.{col_name} = {value} (from row {ctx.current_idx})")
                    return value
                else:
                    logger.debug(f"[DEBUG] Self-reference: current_idx {ctx.current_idx} out of bounds")
                    return None
            
            # Reference to previously matched variable
            if var_name in ctx.variables:
                # Get all indices matched to this variable
                indices = ctx.variables[var_name]
                if not indices:
                    logger.debug(f"[DEBUG] No indices found for variable {var_name}")
                    return None
                
                # Get the value from the most recent row matched to this variable
                # that occurs before the current position
                for idx in sorted(indices, reverse=True):
                    if idx < ctx.current_idx and idx >= 0 and idx < len(ctx.rows):
                        value = ctx.rows[idx].get(col_name)
                        logger.debug(f"[DEBUG] Previous match value: {var_name}.{col_name} = {value} (from row {idx})")
                        return value
                
                # If no matching row found before current position, use the first matched row
                if indices and indices[0] >= 0 and indices[0] < len(ctx.rows):
                    value = ctx.rows[indices[0]].get(col_name)
                    logger.debug(f"[DEBUG] First match value: {var_name}.{col_name} = {value} (from row {indices[0]})")
                    return value
            
            # Subset variable handling
            if var_name in ctx.subsets:
                logger.debug(f"[DEBUG] Handling subset variable: {var_name}")
                # For subset variables, try each component
                for component in ctx.subsets[var_name]:
                    component_value = self._get_variable_column_value(component, col_name, ctx)
                    if component_value is not None:
                        logger.debug(f"[DEBUG] Subset component value: {component}.{col_name} = {component_value}")
                        return component_value
            
            logger.debug(f"[DEBUG] No value found for {var_name}.{col_name}")
            return None
        
        # MEASURES mode (logical navigation)
        else:
            # In measures mode, we handle variables differently
            if var_name in ctx.variables:
                indices = ctx.variables[var_name]
                if not indices:
                    return None
                
                # Use the last row matched to this variable
                last_idx = sorted(indices)[-1]
                if last_idx >= 0 and last_idx < len(ctx.rows):
                    return ctx.rows[last_idx].get(col_name)
            
            # Subset variable handling for measures
            if var_name in ctx.subsets:
                # For subset variables, use the last component
                for component in reversed(ctx.subsets[var_name]):
                    if component in ctx.variables:
                        return self._get_variable_column_value(component, col_name, ctx)
            
            return None
    
    # Apply the fix by replacing the method
    ConditionEvaluator._get_variable_column_value = fixed_get_variable_column_value
    logger.info("Applied partition boundary handling fix to ConditionEvaluator")
    
    return True

if __name__ == "__main__":
    # Apply the fix when run directly
    success = apply_partition_fix()
    print(f"Partition handling fix applied: {success}")
