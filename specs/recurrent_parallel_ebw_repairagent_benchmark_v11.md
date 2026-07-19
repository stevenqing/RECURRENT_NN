# EBW RepairAgent Benchmark v11

## Status

`RPD_EBW_REPAIRAGENT_BENCHMARK_V11_DRAFT`

This is a research-plan spec, not a new model result.

Inputs:

- v10 full executable compositional gate: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v10_merged/REPORT.md`
- v11 residual taxonomy: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_residual_taxonomy/TAXONOMY.md`
- v11 title-slug CPU feasibility: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_title_slug_feasibility_v2/FEASIBILITY.md`
- v11 title-slug model synthesis: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/REPORT.md`
- v11b title-slug contract retry: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11b_contract_retry/REPORT.md`
- v11b full executable compositional rescore: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v11b_merged/REPORT.md`
- v12 RepairAgent/MetaVerifier preflight: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/REPORT.md`
- v14 answer-blinded RepairAgent model eval: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v14_repairagent_blind/REPORT.md`
- v15 structured repair policy: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v15_structured_repair_policy/REPORT.md`
- v16 primitive-selection model eval: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16_primitive_selection_model/REPORT.md`
- v16b primitive-selection merged eval: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16b_primitive_selection_merged/REPORT.md`
- v17 archive-path CPU feasibility: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_archive_path_feasibility/FEASIBILITY.md`
- v17 archive-path model run: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v17_archive_path_target/REPORT.md`
- v17 full executable compositional rescore: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v17_merged/REPORT.md`
- v18 archive structured repair policy: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v18_archive_structured_repair_policy/REPORT.md`
- v19 archive model-in-the-loop primitive selection: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v19_archive_selection_model/REPORT.md`

Sealed AppWorld variations 10-12 remain closed.

## Objective

Turn the v9/v10 researcher-in-loop repair into a testable recurrent repair protocol:

```text
ProofAgents propose sketches
Verifier emits typed residuals
RepairAgent proposes a grammar/frontier patch
MetaVerifier tests the patch against adversarial candidates
Accepted patch becomes recurrent state for the next gate
```

The research claim is not that a prompt can be patched. The claim is that typed verifier residuals can serve as text-gradients for proof-carrying action systems, while MetaVerifier prevents unsafe shortcut patches.

## Starting Residual Taxonomy

Post-v10 full executable compositional gate:

| Residual source | Rows |
|---|---:|
| `title_slug_export_path_binding_missing` | 65 |
| `directory_basename_archive_path_binding_missing` | 9 |
| `prior_effect_playlist_membership_binding_abstain` | 7 |
| `source_path_identity_binding_missing` | 5 |
| `literal_export_path_binding_missing` | 2 |
| `ordered_note_identity_binding_abstain` | 2 |

Full-v8 executable-scope coverage skips:

| Residual source | Rows |
|---|---:|
| `coverage_ordered_role_candidate_missing` | 277 |
| `coverage_literal_span_missing` | 90 |
| `coverage_literal_span_ordinal_not_live` | 12 |

## Primary Target

### `title_slug_export_path_binding`

Why this target first:

- It is the largest post-v10 abstain class: 65 rows.
- It is a clean real-agent write proof: Simple Note title evidence determines filesystem path.
- The required transform is interpretable: task-specified backup directory, title whitespace to `_`, extension `.md`.
- It is less vulnerable to the criticism that v10 was only path punctuation normalization.

Expected proof primitive:

```json
{
  "obligation": "title_slug_export_path_binding",
  "source_read_id": "read_k",
  "title_field": "response.title",
  "content_field": "response.content",
  "destination_directory_rule_id": "task_literal_backup_directory",
  "slug_transform": "whitespace_to_underscore",
  "extension": ".md",
  "target_arg": "file_path"
}
```

The exact schema should be accepted only after CPU feasibility and MetaVerifier adversarial tests.

R1 CPU feasibility result:

| Decision | Rows |
|---|---:|
| `commit_live` | 65 |
| `unsafe_unique_wrong` | 0 |

Important residual lesson: title/content is not always unique across notes. The frontier must bind the source note to the latest matching pre-write `show_note` read, not merely any note with identical content. The first feasibility attempt exposed this ambiguity; v2 fixes it by using latest-read evidence.

## Controls

Required controls before any headline claim:

| Control | Expected outcome |
|---|---|
| `human_patch_upper_bound` | Deterministic frontier proves the target class with 0 unsafe. |
| `repairagent_patch_with_metaverifier` | Patch is accepted only if adversarial candidate uniqueness holds. |
| `repairagent_patch_without_metaverifier` | Must be reported separately; unsafe or overbroad patches invalidate shortcut claims. |
| `prompt_only_repair` | Should not count as proof-grammar repair unless deterministic frontier changes. |
| `residual_shuffled` | Feeding title-slug residuals to unrelated proof families should fail closed. |
| `oracle_frontier` | Measures model synthesis given a correct frontier, separate from repair discovery. |
| `family_resampling` | Same-family independent samples must not be confused with parallel proof-family search. |

## Gate Ladder

1. **R0 taxonomy gate:** complete. v11 taxonomy identifies residual classes and target ranking.
2. **R1 CPU feasibility gate:** complete. Deterministic title-slug candidates cover 65/65 target rows with 0 unsafe after latest-`show_note` source binding.
3. **R2 grammar gate:** complete. Strict parser, prompt assets, and 65-row manifest support `title_slug_export_path_binding`.
4. **R3 model synthesis gate:** complete after v11b output-contract repair. Initial v11 produced 60/65 strict commits and 5 output-contract abstains; v11b reran only those 5 rows with a stronger response contract and committed 5/5. The merged title-slug target gate is 65/65 commit-live with parse rate 1.0 and 0 unsafe.
5. **R4 merged full-executable gate:** complete. Merging v11b title-slug outputs into the v10 full executable compositional gate yields 822 `commit_live`, 25 `abstain_no_valid`, and 0 unsafe over 847 executable rows.
6. **R5a MetaVerifier preflight:** complete. Typed residual packets are materialized and MetaVerifier accepts the two correct patch proposals while rejecting content-only source binding, residual-family mismatch, parser relaxation, and prompt-only repair.
7. **R5b RepairAgent proposal gate:** attempted, no-go. Answer-blinded Qwen proposals parse 2/2 but are accepted 0/2 by the unchanged MetaVerifier. The model proposes content-only/incorrect title-slug binding and the wrong output-contract key. This validates the MetaVerifier but does not establish autonomous repair.
8. **R5c structured proposal policy:** complete. A deterministic primitive-vocabulary selector recovers the two accepted repairs and rejects the same shortcut controls with the unchanged MetaVerifier. This establishes the structured action space for model-in-the-loop primitive selection.
9. **R5d model-in-the-loop primitive selection:** complete after v16b retry. Qwen selects primitive IDs rather than free-form patch JSON. Initial v16 accepts 1/2 and misses `parser_policy.strict` for the contract residual; v16b retries that one compile failure with slot-completeness instruction and accepts 1/1. The merged v16b primitive-selection gate accepts 2/2 with parse and compile rate 1.0.
10. **R6 next-family proof gate:** complete for `directory_basename_archive_path_binding`. Deterministic archive-path candidates cover 9/9 vacation-directory compression abstains with 0 unsafe; strict parser/prompt/runner integration passes; Qwen synthesizes archive-path sketches for 9/9 with parse rate 1.0; full executable compositional rescore reaches 831 commit-live, 16 abstain, and 0 unsafe.
11. **R6b archive structured policy:** complete. The archive proof family is represented in the primitive-selection action space; the correct proposal is accepted and six shortcut controls are rejected.
12. **R6c archive model-in-the-loop primitive selection:** complete. Qwen selects the full archive primitive set and the unchanged archive MetaVerifier accepts 1/1.

R5c structured policy result:

| Proposal | Accepted | Reason |
|---|---:|---|
| `structured_title_slug_latest_show_note` | True | `accepted_latest_read_frontier` |
| `structured_output_contract_obligation_key` | True | `accepted_contract_repair` |
| `control_title_slug_content_only` | False | `rejected_content_only_source_binding` |
| `control_title_slug_residual_shuffled` | False | `rejected_residual_family_mismatch` |
| `control_output_contract_tolerant_parser` | False | `rejected_parser_relaxation` |
| `control_prompt_only_no_frontier` | False | `rejected_prompt_only_no_frontier` |

R5a CPU-only MetaVerifier result:

| Proposal | Accepted | Reason |
|---|---:|---|
| `P_TITLE_SLUG_LATEST_SHOW_NOTE` | True | `accepted_latest_read_frontier` |
| `P_OUTPUT_CONTRACT_OBLIGATION_KEY` | True | `accepted_contract_repair` |
| `C_TITLE_SLUG_CONTENT_ONLY` | False | `rejected_content_only_source_binding` |
| `C_TITLE_SLUG_RESIDUAL_SHUFFLED` | False | `rejected_residual_family_mismatch` |
| `C_OUTPUT_CONTRACT_TOLERANT_PARSER` | False | `rejected_parser_relaxation` |
| `C_PROMPT_ONLY_NO_FRONTIER` | False | `rejected_prompt_only_no_frontier` |

## Metrics

Report:

- unsafe unique-wrong;
- safe commit recovery;
- abstain reduction;
- parse rate;
- frontier coverage;
- adversarial uniqueness pass rate;
- residual-to-patch acceptance rate;
- repair rounds;
- model/GPU/Docker/external process actions;
- sealed variation status.

## Claim Boundary

Passing R1-R4 shows that the next residual class can be repaired by the same proof-grammar loop. R5a shows that the MetaVerifier contract is explicit and rejects shortcut repairs. It still does not show autonomous repair. Passing R5b with model-generated patch proposals is the first result that can support an agent-in-the-loop recurrent repair claim.

Current R5b status: `NO_GO`. The model-generated proposal source must improve before any autonomous RepairAgent claim. The next experiment should test a structured repair proposal policy, not loosen the MetaVerifier.

Current R5c status: `PASS`. The next model experiment should ask the model to select primitive IDs from the v15 library and then use the deterministic compiler + unchanged MetaVerifier. It should not ask the model to free-form invent patch JSON.

Current R5d status: `PASS after targeted retry`. This is the first model-in-the-loop RepairAgent success under the fixed MetaVerifier: the model supplies primitive selections, while deterministic compiler and MetaVerifier enforce safety.

Current R6 status: `MODEL_SYNTHESIS_PASS`. Do not claim autonomous RepairAgent selection for archive-path yet. The next gate is adding archive primitives to the structured RepairAgent vocabulary and proving primitive selection under unchanged MetaVerifier.

Current R6b status: `STRUCTURED_POLICY_PASS`. The next gate is model-in-the-loop primitive selection for the single archive residual packet.

Current R6c status: `MODEL_PRIMITIVE_SELECTION_PASS`. The next gate is a fresh residual taxonomy over the remaining 16 abstentions.