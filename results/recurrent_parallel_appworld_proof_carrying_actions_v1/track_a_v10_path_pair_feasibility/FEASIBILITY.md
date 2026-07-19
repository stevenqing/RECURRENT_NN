# EBW Track A v9 Path-Pair Feasibility

## Status: **`RPD_EBW_TRACK_A_V9_PATH_PAIR_FEASIBILITY_COMPLETE`**

- Total derived rows: 537
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Candidate Labels

| Label | Rows |
|---|---:|
| no_path_pair_candidate | 225 |
| path_pair_candidate_matches_live | 156 |
| path_pair_candidate_mismatch | 156 |

## By Decision

### `abstain_no_valid`

| Label | Rows |
|---|---:|
| no_path_pair_candidate | 76 |
| path_pair_candidate_mismatch | 5 |

### `commit_live`

| Label | Rows |
|---|---:|
| no_path_pair_candidate | 149 |
| path_pair_candidate_mismatch | 151 |

### `unsafe_unique_wrong`

| Label | Rows |
|---|---:|
| path_pair_candidate_matches_live | 156 |

## Interpretation

The v9 path-pair transform can directly explain the date-prefix/directory-rule failures when the task text exposes a parseable prefix pattern and trash/current-year rule. Rows without a candidate or with mismatched expected path should fail closed or require another proof family.
