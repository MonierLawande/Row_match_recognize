import logging
from src.utils.logging_config import get_logger

# Set up logger
logger = get_logger(__name__)
logger.setLevel(logging.DEBUG)

# Add a file handler
file_handler = logging.FileHandler('partition_fix.log')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

def fix_condition_evaluator():
    """
    Function to patch the condition evaluator to fix partition boundary handling.
    This is a diagnostic tool to verify the issue and proposed fix.
    """
    logger.info("Starting condition evaluator patch")
    
    try:
        # Import necessary modules
        from src.matcher.condition_evaluator import ConditionEvaluator
        from src.matcher.row_context import RowContext
        
        # Get the original method
        original_method = ConditionEvaluator._get_variable_column_value
        
        # Define the patched method
        def patched_get_variable_column_value(self, var_name, col_name, ctx):
            """Patched version with fixed partition boundary handling"""
            # Check if we're in DEFINE evaluation mode
            is_define_mode = self.evaluation_mode == 'DEFINE'
            
            # DEBUG: Enhanced logging to trace exact values
            current_var = getattr(ctx, 'current_var', None)
            logger.debug(f"[PATCH] _get_variable_column_value: var_name={var_name}, col_name={col_name}, is_define_mode={is_define_mode}, current_var={current_var}")
            logger.debug(f"[PATCH] ctx.current_idx={ctx.current_idx}, ctx.variables={ctx.variables}")
            logger.debug(f"[PATCH] ctx.partition_boundaries={ctx.partition_boundaries}")
            
            # CRITICAL FIX: In DEFINE mode, we need special handling for pattern variable references
            if is_define_mode:
                # CRITICAL FIX: When evaluating B's condition, B.price should use the current row
                # but A.price should use A's previously matched row
                if var_name == current_var:
                    # Self-reference: use current row being tested
                    logger.debug(f"[PATCH] DEFINE mode - self-reference for {var_name}.{col_name}")
                    if ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                        value = ctx.rows[ctx.current_idx].get(col_name)
                        logger.debug(f"[PATCH] Self-reference value: {var_name}.{col_name} = {value} (from row {ctx.current_idx})")
                        return value
                    else:
                        logger.debug(f"[PATCH] Self-reference: current_idx {ctx.current_idx} out of bounds")
                        return None
                
                # Critical fix for partition boundary handling
                # Check if this is the first row in a partition
                is_partition_boundary = False
                if ctx.partition_boundaries and ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                    for start, end in ctx.partition_boundaries:
                        if ctx.current_idx == start:
                            is_partition_boundary = True
                            logger.debug(f"[PATCH] Found partition boundary at idx={ctx.current_idx}")
                            break
                
                # CRITICAL FIX: At partition boundary, we need to use the current row's value
                # This happens when evaluating the first row in each partition
                if is_partition_boundary:
                    logger.debug(f"[PATCH] PARTITION BOUNDARY: Using current row for {var_name}.{col_name} at idx={ctx.current_idx}")
                    if ctx.current_idx >= 0 and ctx.current_idx < len(ctx.rows):
                        value = ctx.rows[ctx.current_idx].get(col_name)
                        logger.debug(f"[PATCH] Partition boundary value: {var_name}.{col_name} = {value} (from row {ctx.current_idx})")
                        return value
                
                # Rest of the method remains the same...
                return original_method(self, var_name, col_name, ctx)
            else:
                return original_method(self, var_name, col_name, ctx)
        
        # Apply the patch
        ConditionEvaluator._get_variable_column_value = patched_get_variable_column_value
        logger.info("Condition evaluator patched successfully")
        
        return True
    except Exception as e:
        logger.error(f"Error patching condition evaluator: {e}")
        return False

if __name__ == "__main__":
    fix_condition_evaluator()
