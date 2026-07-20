# EBW Track A v42 Hard Typed vs Untyped Eval

## Status: **`RPD_EBW_TRACK_A_V42_HARD_TYPED_VS_UNTYPED_EVAL_COMPLETE`**

- Claim boundary: exploratory hard pass-subset only; v39 hard held-out protocol was blocked.
- Target rows: 3

| Condition | Accepted | Reason | Selection |
|---|---:|---|---|
| `typed` | True | `accepted_hard_frontier` | `{'residual_id': 'R_HARD_ORDERED_NOTE_TYPED_V42', 'template_id': 'template.frontier_grammar.ordered_note_title_identity_binding', 'selected_primitives': ['source_binding.show_note_response_note_id', 'role_constraint.bucket_list_title', 'content_binding.quoted_task_item_in_prewrite_content', 'parser_policy.strict']}` |
| `untyped` | False | `metaverifier_reject_wrong_slots` | `{'residual_id': 'R_HARD_ORDERED_NOTE_UNTYPED_V42', 'template_id': 'template.frontier_grammar.ordered_note_title_identity_binding', 'selected_primitives': ['source_binding.show_note_response_note_id', 'role_constraint.bucket_list_title', 'content_binding.output_content_contains_item', 'parser_policy.strict']}` |
