# EBW Track A v24 Literal Export Path Merged Outputs

## Status: **`RPD_EBW_TRACK_A_V24_LITERAL_EXPORT_PATH_MERGED_OUTPUTS_READY`**

- Rows: 847
- Merge policy: v22 source-path identity compositional outputs plus deterministic v24 literal export path proofs
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Source Counts

| Source | Rows |
|---|---:|
| `v22_source_identity_base` | 845 |
| `v24_literal_export_path_deterministic` | 2 |

## Interpretation

This merge is deterministic, not a Qwen synthesis result. It replaces only the two literal export path residual rows that passed the v23 CPU proof gate, allowing the existing strict literal-intent parser and verifier path to be tested by a full executable compositional rescore.
