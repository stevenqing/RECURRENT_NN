# EBW Track A v28 Prior-Effect Playlist Merged Outputs

## Status: **`RPD_EBW_TRACK_A_V28_PRIOR_EFFECT_PLAYLIST_MERGED_OUTPUTS_READY`**

- Rows: 847
- Merge policy: v26 ordered-note compositional outputs plus deterministic v28 prior-effect playlist proofs
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Source Counts

| Source | Rows |
|---|---:|
| `v26_ordered_note_base` | 840 |
| `v28_prior_effect_playlist_deterministic` | 7 |

## Interpretation

This merge is deterministic, not a Qwen synthesis result. It replaces the seven prior-effect playlist residual rows that passed the v27 CPU proof gate, allowing the existing strict prior-effect schema plus candidate policy to be tested by a full executable compositional rescore.
