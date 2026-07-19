# EBW Track A v22 Source-Path Identity Merged Outputs

## Status: **`RPD_EBW_TRACK_A_V22_SOURCE_PATH_IDENTITY_MERGED_OUTPUTS_READY`**

- Rows: 847
- Merge policy: v17 full compositional outputs plus deterministic v22 source-path identity proofs
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Source Counts

| Source | Rows |
|---|---:|
| `v17_full_base` | 842 |
| `v22_source_path_identity_deterministic` | 5 |

## Interpretation

This merge is deterministic, not a Qwen synthesis result. It replaces only the five source-path identity residual rows that passed the v21 CPU proof gate, allowing the strict parser and verifier integration to be tested by a full executable compositional rescore.
