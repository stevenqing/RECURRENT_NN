# EBW Track A v10 Path-Rule Normalized Gate

## Status: **`RPD_EBW_TRACK_A_V10_PATH_RULE_NORMALIZED_GATE_COMPLETE`**

- Target rows: 156
- Target selection: full-v8 derived unsafe rows with normalized path-pair candidates
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Decision Counts

| Decision | Rows |
|---|---:|
| commit_live | 156 |

## Interpretation

The remaining full-v8 derived unsafe mismatch rows were caused by path-rule parser normalization: task text like `~/trash/.` denotes the same directory as `~/trash`, but v9 compared the unnormalized path literally. After canonicalizing directory literals and dot segments, all 156 full-v8 derived unsafe rows are covered by the path-pair proof family and pass the deterministic barrier under path-shaped adversaries.
