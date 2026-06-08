# Track A Symbolic Stage A Report
Status: `TRACK_A_SYMBOLIC_RESULTS_AVAILABLE`
Track: `A_symbolic`
Operator: `symbolic_oracle`
Cells: `43`

## L4 Separation
| arm | D | spill | n_cells | mean_solve_rate | applied_reverts | max_solve_depth |
| --- | --- | --- | --- | --- | --- | --- |
| gru | 128 | spill_off | 2 | 0.0 | 0 | 0 |
| gru | 256 | spill_off | 2 | 0.0 | 0 | 0 |
| gru | 512 | spill_off | 2 | 0.0 | 0 | 0 |
| kv_snapshot | 128 | spill_off | 2 | 1.0 | 2 | 3 |
| kv_snapshot | 256 | spill_off | 2 | 1.0 | 2 | 3 |
| kv_snapshot | 512 | spill_off | 2 | 1.0 | 2 | 3 |
| rot_bound_single | 128 | spill_off | 2 | 1.0 | 2 | 3 |
| rot_bound_single | 128 | spill_on | 2 | 1.0 | 2 | 3 |
| rot_bound_single | 256 | spill_off | 2 | 1.0 | 2 | 3 |
| rot_bound_single | 256 | spill_on | 3 | 1.0 | 3 | 3 |
| rot_bound_single | 512 | spill_off | 2 | 1.0 | 2 | 3 |
| rot_bound_single | 512 | spill_on | 2 | 1.0 | 2 | 3 |
| rot_factored | 128 | spill_off | 2 | 1.0 | 2 | 3 |
| rot_factored | 128 | spill_on | 2 | 1.0 | 2 | 3 |
| rot_factored | 256 | spill_off | 2 | 1.0 | 2 | 3 |
| rot_factored | 256 | spill_on | 2 | 1.0 | 2 | 3 |
| rot_factored | 512 | spill_off | 2 | 1.0 | 2 | 3 |
| rot_factored | 512 | spill_on | 2 | 1.0 | 2 | 3 |
| rot_no_revert | 128 | spill_off | 2 | 0.875 | 0 | 3 |
| rot_no_revert | 256 | spill_off | 2 | 0.875 | 0 | 3 |
| rot_no_revert | 512 | spill_off | 2 | 0.875 | 0 | 3 |

## Honesty Boundary
Track A rows are symbolic-oracle rows only. They are not learned-operator rows, and learned-track validation reds remain separate. The oracle is freshly constructed per call and consumes only givens plus current assignments.
