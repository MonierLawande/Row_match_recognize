# Ordered and shuffled input

The two campaigns use the same data, queries, sizes, patterns, resource
limits, and repetition counts. Only the physical row order changes.

- In the ordered campaign, `seq_id` is already monotonic.
- In the shuffled campaign, rows are shuffled deterministically and
  `ORDER BY seq_id` restores the same logical sequence.
- All paired match counts and normalized outputs are identical.

The proposed engine increases from 0.167 s to 0.240 s on average
(1.43×). Oracle changes from 1.045 s to 1.083 s (1.04×), and Trino
changes from 1.978 s to 2.193 s (1.11×). These figures show sensitivity
to input order. They should not be treated as direct measurements of each
database's internal sort operator.

The refreshed engine series and retained database series are distinguished in
`_provenance.json`.
