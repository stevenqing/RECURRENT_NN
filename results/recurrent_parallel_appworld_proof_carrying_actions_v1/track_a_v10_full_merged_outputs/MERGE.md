# EBW Track A v10 Full Merged Outputs

## Status: **`RPD_EBW_TRACK_A_V10_FULL_MERGED_OUTPUTS_READY`**

- Rows: 847
- Merge policy: row-independent greedy outputs from full-v8 plus v10 path-pair overrides
- Model/GPU/Docker/external process actions: No
- Sealed variations 10-12 opened: No

## Source Counts

| Source | Rows |
|---|---:|
| `v10_path_pair_override` | 156 |
| `v8_original` | 691 |

## Interpretation

Because each EBW row is generated independently with greedy decoding, this merge reuses already completed row-level model calls: unchanged rows come from the full-v8 executable run, and the diagnosed derived-path unsafe rows come from the v10 normalized path-pair target run. The follow-up CPU rescore is a compositional full-executable gate, not a new GPU full-run.
