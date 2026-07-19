# EBW Track A v18 Archive Structured Repair Policy

## Status: **`RPD_EBW_TRACK_A_V18_ARCHIVE_STRUCTURED_REPAIR_POLICY_PASS`**

- Scope: CPU-only structured proposal policy for archive-path residuals
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Structured Selection

| Residual | Template | Selected primitives |
|---|---|---|
| `R_ARCHIVE_PATH_DIRECTORY_BASENAME_V17` | `template.frontier_grammar.directory_basename_archive_path_binding` | `source_binding.immutable_directory_list_entry, basename_transform.directory_basename, destination_template.task_literal_vacation_spot_archive_template, extension_policy.task_template_extension, parser_policy.strict` |

## MetaVerifier Results

| Proposal | Accepted | Reason |
|---|---:|---|
| `structured_archive_directory_basename` | True | `accepted_archive_directory_basename_frontier` |
| `control_archive_generic_basename_projection` | False | `rejected_source_binding` |
| `control_archive_wrong_template` | False | `rejected_destination_template` |
| `control_archive_wrong_transform` | False | `rejected_basename_transform` |
| `control_archive_wrong_extension_policy` | False | `rejected_extension_policy` |
| `control_archive_parser_relaxation` | False | `rejected_parser_relaxation` |
| `control_archive_prompt_only` | False | `rejected_prompt_only_no_frontier` |

## Interpretation

The archive-path proof family can be represented in the same structured RepairAgent action space: typed residual packet, primitive selection, deterministic compilation, and MetaVerifier acceptance. Negative controls reject generic basename projection, wrong task template, wrong transform, wrong extension policy, parser relaxation, and prompt-only repair.
