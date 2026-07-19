# EBW Track A v11 Residual Taxonomy

## Status: **`RPD_EBW_TRACK_A_V11_RESIDUAL_TAXONOMY_COMPLETE`**

- Scope: CPU-only taxonomy after v10 full executable compositional gate
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## v10 Full-Executable Decisions

| Decision | Rows |
|---|---:|
| `abstain_no_valid` | 90 |
| `commit_live` | 757 |

## Post-v10 Abstain Residuals

| Residual class | Rows |
|---|---:|
| `title_slug_export_path_binding_missing` | 65 |
| `directory_basename_archive_path_binding_missing` | 9 |
| `prior_effect_playlist_membership_binding_abstain` | 7 |
| `source_path_identity_binding_missing` | 5 |
| `literal_export_path_binding_missing` | 2 |
| `ordered_note_identity_binding_abstain` | 2 |

## Coverage Skips From Full-v8 Executable Scope

| Residual class | Rows |
|---|---:|
| `coverage_ordered_role_candidate_missing` | 277 |
| `coverage_literal_span_missing` | 90 |
| `coverage_literal_span_ordinal_not_live` | 12 |

## Recommended RepairAgent Benchmark Targets

### 1. `title_slug_export_path_binding`

- Residual source: `post_v10_abstain`
- Rows currently exposed: 65
- Why: A deterministic transform from immutable note title to backup file path: replace whitespace with underscores, choose task-specified directory, append .md. This is a clean text-gradient target and less likely to be dismissed as path punctuation normalization.
- Gate: CPU feasibility over Simple Note export abstains, then model-facing proof synthesis, then merged full-executable rescore.

### 2. `ordered_role_candidate_repair`

- Residual source: `coverage_skip`
- Rows currently exposed: 277
- Why: Largest remaining coverage gap. Needs relation/cursor candidate construction rather than another prompt rule, so it tests whether RepairAgent can ask for a new frontier primitive.
- Gate: Development-only candidate frontier feasibility before any model run; residual_shuffled control should fail.

### 3. `literal_span_sequence_binding`

- Residual source: `coverage_skip`
- Rows currently exposed: 102
- Why: Directly tests typed residuals for task-text evidence binding across multi-write instructions. Good control against prompt-only repair because the barrier can require exact span/ordinal evidence.
- Gate: Build deterministic span-sequence candidates, then compare RepairAgent patch against prompt-only and residual-shuffled controls.

### 4. `directory_basename_archive_path_binding`

- Residual source: `post_v10_abstain`
- Rows currently exposed: 9
- Why: Small but clean filesystem proof family: directory basename determines archive basename and task-specified extension/destination directory.
- Gate: CPU feasibility only unless bundled with title_slug_export_path_binding.

## Research Interpretation

The next research step should not be another v10 score chase. The v10 gate already solved the diagnosed unsafe class. The useful contribution is a repair benchmark where typed residuals propose new frontier primitives, a MetaVerifier rejects prompt-only shortcuts, and controls show that shuffled or family-mismatched residuals do not repair the gate.
