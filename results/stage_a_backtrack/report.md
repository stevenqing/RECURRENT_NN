# Stage A Backtracking In The Head Report
Verdict: `NEEDS_REVIEW`
Shards: `8`
Cells with results: `0`
Shard statuses: `['PARENT_ADAPTER_REQUIRED']`
## Gate Table
| grid | stack | D | n | gate_pass_rate | mean_max_solve_depth |
| --- | --- | --- | --- | --- | --- |
## Decision Rule
Stage A is confirmed only if rot_* passes the depth-1 gate and solve depth tracks Module-1 capacity while beating gru and rot_no_revert. A rot_* depth-1 failure is treated as wiring bug, not capacity evidence.
