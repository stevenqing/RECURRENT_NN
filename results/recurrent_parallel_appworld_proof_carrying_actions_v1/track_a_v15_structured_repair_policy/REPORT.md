# EBW Track A v15 Structured Repair Policy

## Status: **`RPD_EBW_TRACK_A_V15_STRUCTURED_REPAIR_POLICY_PASS`**

- Scope: CPU-only structured proposal policy over v12 typed residual packets
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Structured Selections

| Residual | Template | Selected primitives |
|---|---|---|
| `R_TITLE_SLUG_SOURCE_BINDING_AMBIGUITY_V11` | `template.frontier_grammar.title_slug_export_path_binding` | `source_binding.latest_matching_pre_write_show_note, slug_transform.whitespace_to_underscore, destination_directory.task_literal_backup_directory, extension.md_dot, parser_policy.strict` |
| `R_OUTPUT_CONTRACT_OBLIGATION_KEY_V11B` | `template.response_contract.output_obligation_key` | `response_contract.require_obligation_forbid_required_obligation, parser_policy.strict` |

## MetaVerifier Results

| Proposal | Accepted | Reason |
|---|---:|---|
| `structured_title_slug_latest_show_note` | True | `accepted_latest_read_frontier` |
| `structured_output_contract_obligation_key` | True | `accepted_contract_repair` |
| `control_title_slug_content_only` | False | `rejected_content_only_source_binding` |
| `control_title_slug_residual_shuffled` | False | `rejected_residual_family_mismatch` |
| `control_output_contract_tolerant_parser` | False | `rejected_parser_relaxation` |
| `control_prompt_only_no_frontier` | False | `rejected_prompt_only_no_frontier` |

## Interpretation

A deterministic structured proposal policy can recover the two accepted repairs from typed residual packets while the same MetaVerifier rejects shortcut controls. This establishes the primitive vocabulary and compiler for the next model-in-the-loop step: ask Qwen to select primitives, not to free-form invent patch JSON.
