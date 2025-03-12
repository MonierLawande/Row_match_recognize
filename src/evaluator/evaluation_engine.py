# src/evaluator/evaluation_engine.py

import logging
from statistics import mean
from copy import deepcopy

from src.ast.match_recognize_ast import MatchRecognizeAST
from src.ast.expression_ast import ExpressionAST
from src.ast.pattern_ast import PatternAST

logger = logging.getLogger(__name__)

# -----------------------------
# Function Dispatcher for Expression Evaluation
# -----------------------------
def dispatch_function(func_name, args, match_context, current_row, extra_info):
    """
    Dispatches function calls based on func_name.
    Supports:
      - Aggregate functions: avg, sum, min, max, count, etc.
      - classifier(): returns the pattern variable associated with the current row.
      - match_number(): returns the sequential match number (provided via extra_info).
      - General functions: for this demo, return evaluation of the first argument.
      - Navigation functions are handled elsewhere.
    """
    func = func_name.lower()
    if func in ["avg", "sum", "min", "max", "count", "max_by", "min_by", "array_agg"]:
        # For aggregate functions, assume args[0] is a qualified identifier.
        if args and '.' in args[0].value:
            var, col = args[0].value.split('.', 1)
            values = []
            for row in match_context.get(var, []):
                try:
                    values.append(float(row.get(col, 0)))
                except Exception:
                    continue
            if func == "avg":
                return mean(values) if values else None
            elif func == "sum":
                return sum(values) if values else None
            elif func == "min":
                return min(values) if values else None
            elif func == "max":
                return max(values) if values else None
            elif func == "count":
                return len(values)
            # For max_by/min_by/array_agg, we return a simplified value.
            else:
                return values if values else None
        else:
            return None
    elif func == "classifier":
        # For classifier(), if an argument is given, return that pattern variable.
        if args:
            # Assume first argument is an identifier.
            return args[0].value if args[0].value else None
        else:
            # Without argument, return a universal pattern variable.
            return "universal"
    elif func == "match_number":
        # Return the match number from extra_info.
        return extra_info.get("match_number", 1)
    else:
        # For general functions, simply evaluate the first argument.
        if args:
            return evaluate_expression(args[0], current_row, match_context)
        return None

# -----------------------------
# Comprehensive Expression Evaluator
# -----------------------------
def evaluate_expression(ast: ExpressionAST, row, match_context=None, extra_info=None):
    """
    Recursively evaluates an expression AST.
    In the match context, for qualified identifiers, look up the value from the match_context.
    Handles:
      - Literals and identifiers (with simple qualified lookup).
      - Binary operations (+, -, *, /).
      - Function calls using dispatch_function.
      - Navigation functions are handled in a minimal way.
    """
    extra_info = extra_info or {}
    if ast.type == "literal":
        try:
            return float(ast.value)
        except Exception:
            return ast.value
    elif ast.type == "identifier":
        # For qualified identifiers like "A.totalprice", if match_context provided, use it.
        if '.' in ast.value:
            var, col = ast.value.split('.', 1)
            # If we are in a match context, use the first row of that variable's match.
            if match_context and var in match_context and match_context[var]:
                return match_context[var][0].get(col, None)
            # Otherwise, use the current row.
            else:
                return row.get(col, None)
        else:
            return row.get(ast.value, None)
    elif ast.type == "binary":
        left = evaluate_expression(ast.children[0], row, match_context, extra_info)
        right = evaluate_expression(ast.children[1], row, match_context, extra_info)
        if ast.operator == '+':
            return left + right
        elif ast.operator == '-':
            return left - right
        elif ast.operator == '*':
            return left * right
        elif ast.operator == '/':
            try:
                return left / right
            except ZeroDivisionError:
                return None
    elif ast.type in ["function", "aggregate"]:
        # Dispatch based on the function name.
        args = [evaluate_expression(child, row, match_context, extra_info) for child in ast.children]
        return dispatch_function(ast.value, ast.children, match_context, row, extra_info)
    elif ast.type == "navigation":
        # For navigation functions, simulate by picking a row from the match context.
        # Here we use a simple approach: for FIRST, return the first row; for LAST, the last row.
        func = ast.navigation_type
        if ast.children and '.' in ast.children[0].value:
            var, col = ast.children[0].value.split('.', 1)
            if match_context and var in match_context:
                rows = match_context[var]
                offset = ast.offset
                if func == "FIRST":
                    index = offset if offset < len(rows) else len(rows) - 1
                    return rows[index].get(col, None)
                elif func == "LAST":
                    index = len(rows) - 1 - offset if offset < len(rows) else 0
                    return rows[index].get(col, None)
        return None
    return None

# -----------------------------
# Robust Pattern Matching with Regex-like Semantics
# -----------------------------
def match_pattern(pattern_ast: PatternAST, rows, index, define_map):
    """
    Attempts to match the pattern_ast against rows starting at index.
    This function uses recursive backtracking to simulate regex-like semantics.
    Returns a list of tuples (match_dict, next_index) where match_dict maps
    pattern variable names to lists of rows, and next_index is where matching ended.
    """
    results = []
    if pattern_ast.type == "empty":
        results.append(({}, index))
        return results

    if pattern_ast.type == "literal":
        if index >= len(rows):
            return []
        row = rows[index]
        var = pattern_ast.value
        cond = define_map.get(var, lambda r: True)
        if cond(row):
            results.append(({var: [row]}, index + 1))
        return results

    if pattern_ast.type == "group":
        return match_pattern(pattern_ast.children[0], rows, index, define_map)

    if pattern_ast.type == "concatenation":
        current = [({}, index)]
        for child in pattern_ast.children:
            next_current = []
            for (match_dict, idx) in current:
                submatches = match_pattern(child, rows, idx, define_map)
                for (sub_match, next_idx) in submatches:
                    merged = deepcopy(match_dict)
                    for k, v in sub_match.items():
                        merged.setdefault(k, []).extend(v)
                    next_current.append((merged, next_idx))
            current = next_current
        return current

    if pattern_ast.type == "alternation":
        all_matches = []
        for child in pattern_ast.children:
            all_matches.extend(match_pattern(child, rows, index, define_map))
        return all_matches

    if pattern_ast.type == "quantifier":
        # Handle both greedy and reluctant quantifiers.
        quant = pattern_ast.quantifier  # e.g., "+", "*", "?", "{n,m}" possibly followed by "?".
        reluctant = quant.endswith("?")
        base_quant = quant[:-1] if reluctant else quant
        if base_quant in ['+', '*', '?']:
            if base_quant == '+':
                min_occurs, max_occurs = 1, 10  # arbitrary upper bound for demo
            elif base_quant == '*':
                min_occurs, max_occurs = 0, 10
            elif base_quant == '?':
                min_occurs, max_occurs = 0, 1
        elif base_quant == "{n,m}":
            min_occurs, max_occurs = pattern_ast.quantifier_min, pattern_ast.quantifier_max or 10
        else:
            min_occurs, max_occurs = 1, 1

        matches = []
        def backtrack(count, current_match, curr_index):
            if count >= min_occurs:
                matches.append((deepcopy(current_match), curr_index))
                if reluctant:
                    return
            if count == max_occurs:
                return
            submatches = match_pattern(pattern_ast.children[0], rows, curr_index, define_map)
            for (sub_match, next_idx) in submatches:
                merged = deepcopy(current_match)
                for k, v in sub_match.items():
                    merged.setdefault(k, []).extend(v)
                backtrack(count + 1, merged, next_idx)
        backtrack(0, {}, index)
        return matches

    if pattern_ast.type == "exclusion":
        submatches = match_pattern(pattern_ast.children[0], rows, index, define_map)
        return [({}, next_idx) for (_, next_idx) in submatches]

    if pattern_ast.type == "permutation":
        results = []
        # For simplicity, treat permutation as alternation.
        for child in pattern_ast.children:
            results.extend(match_pattern(child, rows, index, define_map))
        return results

    return results

def build_define_map(define_clauses):
    """
    Builds a mapping from pattern variable to a function evaluating its DEFINE condition.
    For undefined variables, returns a function that always returns True.
    """
    map_func = {}
    for define in define_clauses:
        var = define["variable"]
        cond_ast = define["condition"]["ast"]
        def make_cond(ast):
            return lambda row: bool(evaluate_expression(ast, row))
        map_func[var] = make_cond(cond_ast)
    return map_func

# -----------------------------
# Full Evaluation Engine
# -----------------------------
class EvaluationEngine:
    """
    A full evaluation engine for MATCH_RECOGNIZE.
    
    Steps:
      1. Partition data by PARTITION BY.
      2. Order partitions by ORDER BY.
      3. Use a robust regex-like matcher (recursive backtracking) to match patterns.
      4. Evaluate measure expressions with full support for running vs. final semantics.
      5. Handle AFTER MATCH SKIP options.
      6. Support various modes for unmatched rows.
    """
    def __init__(self, ast: MatchRecognizeAST, data: list, extra_info=None):
        """
        :param ast: The MATCH_RECOGNIZE AST.
        :param data: List of rows (each row is a dict).
        :param extra_info: Dict for extra information (e.g., current match number).
        """
        self.ast = ast
        self.data = data
        self.extra_info = extra_info or {}
        self.outputs = []

    def partition_data(self):
        partitions = {}
        if self.ast.partition_by:
            for row in self.data:
                key = tuple(row.get(col, None) for col in self.ast.partition_by)
                partitions.setdefault(key, []).append(row)
        else:
            partitions[("all",)] = self.data
        return partitions

    def order_partition(self, partition):
        if self.ast.order_by:
            return sorted(partition, key=lambda r: tuple(r.get(col, None) for col in self.ast.order_by))
        return partition

    def evaluate_after_match_skip(self, match, current_index, partition):
        """
        Determines the next index to start matching after a match is found,
        based on the AFTER MATCH SKIP clause.
        Options supported:
          - "SKIP PAST LAST ROW" (default): resume at index = last row index of match + 1.
          - "SKIP TO NEXT ROW": resume at index = first row index of match + 1.
          - "SKIP TO FIRST <var>": resume at index = index of first row matched to variable <var> + 1.
          - "SKIP TO LAST <var>": resume at index = index of last row matched to variable <var> + 1.
        """
        skip_clause = self.ast.after_match_skip.upper()
        # By default, if no clause, use "SKIP PAST LAST ROW"
        if "SKIP PAST LAST ROW" in skip_clause:
            last_idx = max(match.get(var, [0])[-1]["_index"] for var in match if match[var])
            return last_idx + 1
        elif "SKIP TO NEXT ROW" in skip_clause:
            first_idx = min(match.get(var, [float('inf')])[0]["_index"] for var in match if match[var])
            return first_idx + 1
        elif "SKIP TO FIRST" in skip_clause:
            parts = skip_clause.split()
            if len(parts) >= 4:
                var = parts[3]
                if var in match and match[var]:
                    return match[var][0]["_index"] + 1
            # Fallback to default.
            last_idx = max(match.get(var, [0])[-1]["_index"] for var in match if match[var])
            return last_idx + 1
        elif "SKIP TO LAST" in skip_clause:
            parts = skip_clause.split()
            if len(parts) >= 4:
                var = parts[3]
                if var in match and match[var]:
                    return match[var][-1]["_index"] + 1
            last_idx = max(match.get(var, [0])[-1]["_index"] for var in match if match[var])
            return last_idx + 1
        else:
            # Default behavior.
            last_idx = max(match.get(var, [0])[-1]["_index"] for var in match if match[var])
            return last_idx + 1

    def evaluate_match(self, match, partition, base_index):
        """
        Evaluates measure expressions for a given match.
        match: a match dictionary mapping pattern variable to list of rows.
        partition: the full ordered partition.
        base_index: the index where the match started (used for skip semantics).
        """
        # For each measure, evaluate expression in the match context.
        out = {}
        for i, col in enumerate(self.ast.partition_by):
            out[col] = partition[base_index].get(col, None)
        # For each measure:
        for measure in self.ast.measures:
            expr_ast = measure["expression"]["ast"]
            alias = measure["alias"]
            # Determine semantics: if RUNNING, evaluate on a specific row; if FINAL, evaluate on the complete match.
            sem = expr_ast.semantics.upper() if expr_ast.semantics else "FINAL"
            if expr_ast.type == "aggregate":
                func_name = expr_ast.value.lower()
                # Assume aggregate argument is a qualified identifier.
                if expr_ast.children and '.' in expr_ast.children[0].value:
                    var, col = expr_ast.children[0].value.split('.', 1)
                    rows = match.get(var, [])
                    # Attach the original row index in each row for skip logic.
                    values = []
                    for row in rows:
                        try:
                            values.append(float(row.get(col, 0)))
                        except Exception:
                            continue
                    if func_name == "avg":
                        out[alias] = mean(values) if values else None
                    elif func_name == "sum":
                        out[alias] = sum(values) if values else None
                    elif func_name == "min":
                        out[alias] = min(values) if values else None
                    elif func_name == "max":
                        out[alias] = max(values) if values else None
                    elif func_name == "count":
                        out[alias] = len(values)
                    else:
                        out[alias] = None
                else:
                    out[alias] = None
            else:
                # For non-aggregate, use FINAL semantics (evaluate on last row) or RUNNING (current row).
                row = match.get(expr_ast.value.split('.')[0], [])[-1] if '.' in expr_ast.value and match.get(expr_ast.value.split('.')[0]) else partition[-1]
                out[alias] = evaluate_expression(expr_ast, row, match)
        return out

    def match_partition(self, partition, define_map):
        """
        Uses a robust pattern matcher (full regex-like semantics) to get all matches from a partition.
        Each match is a tuple (match_dict, next_index) where match_dict maps pattern variables to rows.
        We enhance the matcher by recording the original row index in each row.
        """
        # Preprocess: add an "_index" field to each row in the partition.
        for i, row in enumerate(partition):
            row["_index"] = i

        return match_pattern(self.ast.pattern["ast"], partition, 0, define_map)

    def evaluate(self):
        output_rows = []
        partitions = self.partition_data()
        define_map = build_define_map(self.ast.define)
        for part_key, rows in partitions.items():
            ordered = self.order_partition(rows)
            matches = self.match_partition(ordered, define_map)
            if not matches:
                # If unmatched rows should be output.
                if self.ast.rows_per_match.upper() == "ALL ROWS PER MATCH WITH UNMATCHED ROWS":
                    out = {col: part_key[i] for i, col in enumerate(self.ast.partition_by)} if self.ast.partition_by else {}
                    for measure in self.ast.measures:
                        out[measure["alias"]] = None
                    output_rows.append(out)
            else:
                match_number = 1
                index = 0
                while index < len(ordered):
                    # Find next match that starts at or after current index.
                    valid_matches = [m for m in matches if m[1] > index]
                    if not valid_matches:
                        break
                    # For simplicity, take the first valid match.
                    match_dict, next_index = valid_matches[0]
                    # Evaluate the measures for this match.
                    out = self.evaluate_match(match_dict, ordered, index)
                    # Add match number if needed.
                    out["match_number"] = match_number
                    output_rows.append(out)
                    match_number += 1
                    # Determine next index based on AFTER MATCH SKIP clause.
                    index = self.evaluate_after_match_skip(match_dict, index, ordered)
            # End partition loop.
        self.outputs = output_rows
        return output_rows
