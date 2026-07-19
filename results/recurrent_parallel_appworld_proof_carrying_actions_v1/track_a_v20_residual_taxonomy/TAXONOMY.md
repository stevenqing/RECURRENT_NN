# EBW Track A v20 Residual Taxonomy

## Status: **`RPD_EBW_TRACK_A_V20_RESIDUAL_TAXONOMY_COMPLETE`**

- Scope: CPU-only taxonomy after v17 full executable compositional gate
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## v17 Full-Executable Decisions

| Decision | Rows |
|---|---:|
| `abstain_no_valid` | 16 |
| `commit_live` | 831 |

## Remaining Abstain Residuals

| Residual class | Rows |
|---|---:|
| `prior_effect_playlist_id_binding_abstain` | 7 |
| `source_path_identity_binding_missing` | 5 |
| `literal_export_path_binding_missing` | 2 |
| `ordered_note_title_identity_binding_abstain` | 2 |

## Recommended Next Proof Families

### 1. `source_path_identity_binding`

- Residual class: `source_path_identity_binding_missing`
- Rows: 5
- Why: Small, clean complement to path-pair repair: move_file.source_file_path should be proven by immutable source path evidence, not by destination path grammar. It is likely CPU-feasible and keeps the proof-family progression coherent.
- Gate: Build deterministic source-path identity candidates over the 5 move_file source_file_path abstains; require exact source path evidence and path-shaped adversaries fail.

### 2. `literal_export_path_binding`

- Residual class: `literal_export_path_binding_missing`
- Rows: 2
- Why: Very small but clean task-text literal path proof: backup CSV path is quoted in the user instruction. Good parser/control exercise after source identity.
- Gate: Bind quoted file path literal span to create_file.file_path with exact span evidence and adversarial path alternatives.

### 3. `ordered_note_title_identity_binding`

- Residual class: `ordered_note_title_identity_binding_abstain`
- Rows: 2
- Why: Tests relation between quoted task item and Simple Note identity. Small count but more semantically meaningful than literal path extraction.
- Gate: Bind quoted bucket-list item to a note whose content/title contains that item before patching note_id.

### 4. `prior_effect_playlist_id_binding`

- Residual class: `prior_effect_playlist_id_binding_abstain`
- Rows: 7
- Why: Largest remaining post-v17 abstain class, but likely needs relation between newly created playlist effect and multiple subsequent add_song_to_playlist writes; tackle after simpler identity/literal proofs clarify the residual protocol.
- Gate: Audit prior_effect rows to distinguish missing effect binding from ambiguity under repeated playlist_id use before model calls.

## Research Interpretation

The remaining v17 abstentions are safe frontier gaps, not safety failures. The next best CPU-first proof family is source-path identity binding for move_file.source_file_path, because it is a direct complement to the destination path-pair grammar and should be decidable from immutable source path evidence. The largest remaining class is prior-effect playlist binding, but it likely needs relation/cursor reasoning over repeated writes and should be handled after simpler identity/literal frontiers are exhausted.
