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
- v20 residual taxonomy: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v20_residual_taxonomy/TAXONOMY.md`
- v21 source-path identity feasibility: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v21_source_path_identity_feasibility/FEASIBILITY.md`
- v22 source-path identity compositional rescore: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v22_source_identity_merged/REPORT.md`
- v23/v24 literal export path feasibility/rescore: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v23_literal_export_path_feasibility/FEASIBILITY.md`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v24_literal_export_merged/REPORT.md`
- v25/v26 ordered note title identity feasibility/rescore: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v25_ordered_note_title_identity_feasibility/FEASIBILITY.md`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v26_ordered_note_merged/REPORT.md`
- v27/v28 prior-effect playlist feasibility/rescore: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v27_prior_effect_playlist_feasibility/FEASIBILITY.md`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v28_prior_effect_merged/REPORT.md`
- v29/v29b frontier RepairAgent selection: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy/REPORT.md`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29b_frontier_selection_merged/REPORT.md`
- v30 test-time compute freeze/replay: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_freeze/FREEZE.md`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_replay/REPLAY.md`
- v31-v33 held-out TTC: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v31_heldout_instance_preflight/PREFLIGHT.md`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v32_heldout_no_repair/REPORT.md`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v33_heldout_ttc/REPORT.md`

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
13. **R7 residual taxonomy after archive repair:** complete. The remaining 16 safe abstentions split into 7 prior-effect playlist, 5 source-path identity, 2 literal export path, and 2 ordered note identity residuals. The next CPU-first target is `source_path_identity_binding`.
14. **R8 source-path identity proof gate:** CPU feasibility complete. Deterministic source-path identity candidates cover 5/5 `move_file.source_file_path` abstains with 5 commit-live and 0 unsafe; exact `response.path` identity is ready for strict grammar integration.
15. **R8b source-path identity compositional gate:** complete. Strict integration plus deterministic compiled sketches improves the full executable opened gate to 836 commit, 11 abstain, 0 unsafe.
16. **R9 literal export path gate:** complete. The existing strict `literal_intent_binding` schema covers 2/2 quoted Spotify CSV file paths; full executable rescore reaches 838 commit, 9 abstain, 0 unsafe.
17. **R10 ordered note title identity gate:** complete. New `ordered_note_title_identity_binding` covers 2/2 Bucket List note updates; full executable rescore reaches 840 commit, 7 abstain, 0 unsafe.
18. **R11 prior-effect playlist gate:** complete. Candidate-bound `prior_effect_binding` covers 7/7 playlist writes from `create_playlist.response.playlist_id`; full executable rescore reaches 847 commit, 0 abstain, 0 unsafe.
19. **R12 multi-family model-in-the-loop primitive selection:** complete after v29b retry. Qwen selects primitive IDs for the four v21-v28 residual packets. Initial v29 accepts 3/4 and uses an invalid parser-policy primitive alias for source-path identity; targeted v29b retry accepts 1/1. The merged v29b gate accepts 4/4 with parse and compile rate 1.0 under the unchanged deterministic compiler and MetaVerifier.
20. **R13 test-time compute freeze/replay:** started. The TTC protocol is frozen before prospective held-out outcomes. Retrospective opened-data replay validates the loop mechanics, improving 831 commit / 16 abstain / 0 unsafe to 847 commit / 0 abstain / 0 unsafe in one parallel repair round with 5 recorded model calls. This is not yet the held-out TTC claim.
21. **R14 prospective held-out TTC:** first pass complete. On fresh variations 10-12, v32 no-repair commits 62/65 executable rows with 3 safe abstentions and 0 unsafe. v33 forms one frozen-library residual packet, Qwen selects primitive IDs, MetaVerifier accepts the literal export path repair, and the merged rescore reaches 65/65 commit-live with 0 unsafe.

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

Current R7 status: `TAXONOMY_READY`. The next gate is CPU feasibility for `source_path_identity_binding`; do not start with Qwen.

Current R8 status: `CPU_FEASIBILITY_PASS`. The next gate is parser/prompt/runner integration plus CPU compositional rescore; do not report it as a full executable improvement until the merged rescore is run.

Current R11 status: `DETERMINISTIC_FRONTIER_CLOSURE_PASS`. The opened executable scope is closed under deterministic compiled proofs. The next benchmark should not add more hand repairs; it should test model-in-the-loop primitive selection for the v21-v28 residual packets under an unchanged compiler and MetaVerifier.

Current R12 status: `MODEL_PRIMITIVE_SELECTION_PASS after targeted retry`. This extends model-in-the-loop RepairAgent primitive selection to all four residual families that closed the opened executable scope. The next step should be robustness rather than more hand-designed frontier patches.

Current R13 status: `RETROSPECTIVE_TTC_REPLAY_PASS`. The next gate is prospective held-out TTC under the frozen protocol; no new primitives, proof families, parser edits, or manual residual taxonomy are allowed after held-out outcomes are observed.

Current R14 status: `HELDOUT_TTC_FIRST_PASS`. The next gate is not another frontier patch; it is required controls on the same held-out executable subset: best-of-N no repair, free-form RepairAgent patch JSON, and structured RepairAgent without MetaVerifier.