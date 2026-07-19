# EBW Track A v10 Full Executable Manifest

## Status: **`RPD_EBW_TRACK_A_V10_FULL_EXECUTABLE_MANIFEST_READY`**

- Rows: 847
- Path-pair overrides: 156
- Target selection: full-v8 executable rows, overriding only live-matching normalized path-pair candidates
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Output Obligations

| Obligation | Rows |
|---|---:|
| `derived_path_binding` | 381 |
| `literal_intent_binding` | 12 |
| `ordered_role_binding` | 290 |
| `path_pair_transform_binding` | 156 |
| `prior_effect_binding` | 8 |

## Override Source Decisions

| Previous v8 decision | Rows |
|---|---:|
| `unsafe_unique_wrong` | 156 |

## Interpretation

This manifest preserves the v8 candidate-bound executable scope and changes only the derived-path rows whose normalized path-pair candidate matches the live destination. The override set is exactly the previously unsafe derived-path class, so this is a targeted full-executable rerun rather than a broader coverage claim.
