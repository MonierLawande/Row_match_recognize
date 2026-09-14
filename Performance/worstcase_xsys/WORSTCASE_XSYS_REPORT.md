# State-dependent predicate campaign

This campaign evaluates
`B AS category = 'B' AND price > AVG(A.price)` with the
`simple_sequence` pattern. The proposed engine was refreshed on commit
`179c286fb020160a6a63c0e6eda60456971923d0`. Oracle and Trino were not
rerun.

## Protocol

- 1 CPU core and 32 GB memory per system.
- Six ordered dataset sizes from 100,000 to 2,222,742 rows.
- Engine: five warm-up runs and twenty measured runs per size.
- Retained databases: one warm-up run and two measured runs per size.
- Sequential system execution.

## Results

| Rows | Proposed engine (s) | Oracle XE 21c (s) | Trino 473 (s) | Matches |
|---:|---:|---:|---:|---:|
| 100,000 | 0.060 | 0.073 | 0.713 | 9,067 |
| 200,000 | 0.107 | 0.133 | 0.535 | 16,093 |
| 400,000 | 0.229 | 0.349 | 3.649 | 34,391 |
| 800,000 | 0.463 | 0.666 | 5.136 | 66,330 |
| 1,600,000 | 0.921 | 1.630 | 6.432 | 130,338 |
| 2,222,742 | 1.279 | 2.324 | 8.666 | 181,147 |

All six engine outputs are byte-identical to both retained database outputs.
The engine's compiled incremental running-average plan replaces the older
64.41 s full-size result. This result covers that compiled form only; it is
not a linear-time claim for every state-dependent expression. The different
database repetition count is a limitation of this comparison.
