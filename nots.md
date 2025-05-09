# Test 7: PERMUTE with Edge Cases
# Test 6: PERMUTE with Complex Conditions
# Test 5: Nested PERMUTE patterns
# Test 4: PERMUTE with Subset Variables
# Test 3: PERMUTE with ALL ROWS PER MATCH
# Test 2: PERMUTE with Quantifier
# Test 1: Basic PERMUTE with Simple Variables

Main Components:
a) PARTITION BY:

Breaks input data into separate groups for independent pattern matching
Similar to GROUP BY functionality
Optional - if omitted, entire table is treated as one partition
b) ORDER BY:

Defines the sequence order for pattern matching
Critical for time-series or sequential data analysis
c) MEASURES:

Specifies what information to extract from matched sequences
Can use special functions like:
CLASSIFIER() - returns pattern variable name
MATCH_NUMBER() - returns sequential match number
Navigation functions: FIRST(), LAST(), PREV(), NEXT()
d) ROWS PER MATCH:

Controls output format with options:
ONE ROW PER MATCH (default)
ALL ROWS PER MATCH
ALL ROWS PER MATCH SHOW EMPTY MATCHES
ALL ROWS PER MATCH OMIT EMPTY MATCHES
ALL ROWS PER MATCH WITH UNMATCHED ROWS
e) PATTERN:

Defines the pattern to match using regular expression-like syntax
Supports:
Basic variables (A, B, C)
Quantifiers (*, +, ?, {n}, {n,m})
Alternation (|)
Grouping (())
PERMUTE for matching in any order
Anchors (^, $)
Exclusions ({- pattern -})
f) SUBSET:

Defines union variables combining multiple pattern variables
Example: SUBSET U = (A, B) creates variable U matching either A or B
g) DEFINE:

Specifies conditions for pattern variables
Uses boolean expressions that can reference:
Current row values
Previous/next row values via PREV/NEXT
Values from other pattern variables
