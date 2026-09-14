# Cross-system matrix

The proposed engine was refreshed on commit
`179c286fb020160a6a63c0e6eda60456971923d0`. Oracle and Trino were not
rerun. Their accepted measurements were retained from the earlier campaign
under the same resource and repetition protocol. The three systems ran
sequentially.

## Protocol

- 1 CPU core and 32 GB memory per system.
- Five warm-up runs and twenty measured runs per cell.
- Six nested dataset sizes from 100,000 to 2,222,742 rows.
- Five identical pattern families.
- A five-second pre-query memory baseline and 50 ms cgroup sampling.
- The 1.5× IQR rule applied per cell and metric.

## Results

| System | Successful cells | Mean time (s) | Mean throughput (rows/s) | Maximum query memory (MB) | Maximum footprint (MB) |
|---|---:|---:|---:|---:|---:|
| Proposed engine | 30/30 | 0.167 | 6,110,392 | 189.05 | 523.97 |
| Oracle XE 21c | 30/30 | 1.045 | 1,156,106 | 58.71 | 2,057.17 |
| Trino 473 | 30/30 | 1.978 | 602,098 | 20.75 | 14,992.90 |

All thirty engine outputs were byte-identical to the retained Oracle and
Trino outputs after normalization. The comparison has mixed collection dates,
but the resource limits, data, queries, repetition counts, and measurement
rules are unchanged. Detailed per-cell values are stored in
`matrix_1cpu_32gb_summary.csv`; `_provenance.json` records the campaign
boundary.
