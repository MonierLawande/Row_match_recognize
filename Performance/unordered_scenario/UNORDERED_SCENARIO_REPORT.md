# Shuffled-input sensitivity campaign

The proposed engine was refreshed on commit
`179c286fb020160a6a63c0e6eda60456971923d0` inside a dedicated cgroup.
Oracle and Trino were not rerun. Their accepted shuffled-input results were
retained from the earlier campaign under the same protocol.

## Protocol

- 1 CPU core and 32 GB memory per system.
- Five warm-up runs and twenty measured runs per cell.
- The same six sizes, five patterns, rows, and query bodies as the ordered
  matrix.
- A deterministic shuffle before `ORDER BY seq_id`.
- Sequential system execution and the same IQR and memory rules as the main
  matrix.

## Results

| System | Successful cells | Ordered mean (s) | Shuffled mean (s) | Slowdown |
|---|---:|---:|---:|---:|
| Proposed engine | 30/30 | 0.167 | 0.240 | 1.43× |
| Oracle XE 21c | 30/30 | 1.045 | 1.083 | 1.04× |
| Trino 473 | 30/30 | 1.978 | 2.193 | 1.11× |

Every shuffled engine output was byte-identical to the retained output from
each database. Ordered and shuffled match counts also agree in all 90 paired
cells. The experiment measures sensitivity to physical input order. It does
not isolate or infer the internal database sort plan.

Detailed values are stored in `matrix_1cpu_32gb_summary.csv` and
`comparison_ordered_vs_unordered.csv`.
