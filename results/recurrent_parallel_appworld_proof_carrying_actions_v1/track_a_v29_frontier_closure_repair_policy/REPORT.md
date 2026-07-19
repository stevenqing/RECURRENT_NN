# EBW Track A v29 Frontier Closure Repair Policy

## Status: **`RPD_EBW_TRACK_A_V29_FRONTIER_CLOSURE_REPAIR_POLICY_PASS`**

- Scope: CPU-only structured RepairAgent policy for v21-v28 deterministic residual closure
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Structured Selections

| Residual | Template | Selected primitives | Accepted | Reason |
|---|---|---|---:|---|
| `R_SOURCE_PATH_IDENTITY_V21` | `template.frontier_grammar.source_path_identity_binding` | `source_binding.pre_write_response_path_exact, identity_transform.exact_path, parser_policy.strict` | True | `accepted_source_path_identity_frontier` |
| `R_LITERAL_EXPORT_PATH_V23` | `template.frontier_candidate.literal_export_path_binding` | `span_source.quoted_task_path_exact, target_arg.file_path, parser_policy.strict` | True | `accepted_literal_export_path_frontier` |
| `R_ORDERED_NOTE_TITLE_IDENTITY_V25` | `template.frontier_grammar.ordered_note_title_identity_binding` | `source_binding.show_note_response_note_id, role_constraint.bucket_list_title, content_binding.quoted_task_item_in_prewrite_content, parser_policy.strict` | True | `accepted_ordered_note_title_identity_frontier` |
| `R_PRIOR_EFFECT_PLAYLIST_V27` | `template.frontier_candidate.prior_effect_playlist_binding` | `effect_binding.create_playlist_response_playlist_id, effect_field.playlist_id, parser_policy.strict` | True | `accepted_prior_effect_playlist_frontier` |

## Interpretation

The v21-v28 deterministic closure can be represented as four typed residual packets, a primitive library, deterministic compilation, and a MetaVerifier. This establishes the target for the GPU model-in-the-loop experiment: Qwen should select primitive IDs only; it should not emit free-form patch JSON.
