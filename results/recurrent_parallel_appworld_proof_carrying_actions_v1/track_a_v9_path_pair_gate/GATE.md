# EBW Track A v9 Path-Pair Gate

## Status: **`RPD_EBW_TRACK_A_V9_PATH_PAIR_GATE_COMPLETE`**

- Target rows: 120
- Target selection: derived-path full-v8 unsafe rows with matching v9 path-pair candidate
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Decision Counts

| Decision | Rows |
|---|---:|
| commit_live | 120 |

## Interpretation

A deterministic path-pair proof is sufficient to turn the directly covered full-v8 derived unsafe rows into commit-live decisions under path-shaped adversaries. Remaining unsafe requires richer path-rule parsing, not another basename proof.
