# EBW Track A v3/v4/v5/v6/v7/v8 Smoke Closeout

## Status: **`RPD_EBW_TRACK_A_FULL_OPENED_V8_UNSAFE_BLOCKED`**

Date: 2026-07-13

## What Changed

- Added prompt v3: chat-template execution, assistant `{` prefill, strict-parser stop, output-only examples.
- Added prompt v4: v3 plus row-level role constraint from value-free proof-family metadata.
- Updated prompt manifest build to preserve `write_ordinal_for_schema` from `results/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1/instance_manifest.json`; it no longer silently defaults missing ordinals to 0.
- Added deterministic raw-output rescore so verifier-only metadata fixes can be audited without rerunning the model.
- Added prompt v5: v4 plus deterministic quoted-span candidates for literal intent bindings.
- Added prompt v6: v5 plus deterministic source-path candidates for derived path bindings.
- Updated derived-path verifier semantics to resolve dotted `response.N.field` paths and list indices before falling back to recursive key search.
- Added verifier policy v7: derived-path adversarial candidates preserve target path shape and mutate only basename, rather than using a bare evidence basename as an action candidate.
- Added v7 freeze-readiness audit and an opened-pool candidate-ready shard gate.
- Added prompt/protocol v8: candidate-bound literal and ordered-role constraints. Literal rows require the row ordinal's span to equal the live target value; ordered rows require a source candidate that proves the live value at the row ordinal. Ineligible rows fail closed at manifest build time.

## Key Artifacts

| Artifact | Path |
|---|---|
| Parser standard audit | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/parser_standard_audit_v1/PARSER_STANDARD_AUDIT.md` |
| Prompt v3 freeze | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v3/PROMPT_FREEZE_V3.md` |
| Prompt v3 smoke | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_smoke_v3/REPORT.md` |
| Prompt v4 freeze | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v4/PROMPT_FREEZE_V4.md` |
| Prompt v4 smoke | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_smoke_v4/REPORT.md` |
| v4 ordinal-fixed manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_smoke_v4_ordfix/PROMPT_MANIFEST.md` |
| v4 ordinal-fixed rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_smoke_v4_ordfix_rescore/REPORT.md` |
| Prompt v5 freeze | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v5/PROMPT_FREEZE_V5.md` |
| Prompt v5 smoke | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_smoke_v5/REPORT.md` |
| Prompt v5 dev40 | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_dev40_v5/REPORT.md` |
| Prompt v5 pathfix rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_dev40_v5_pathfix_rescore/REPORT.md` |
| Prompt v6 freeze | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v6/PROMPT_FREEZE_V6.md` |
| Prompt v6 dev40 | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_dev40_v6/REPORT.md` |
| Verifier policy v7 | `specs/recurrent_parallel_ebw_track_a_verifier_policy_v7.json` |
| v7 dev40 rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_dev40_v7_rescore/REPORT.md` |
| v7 freeze readiness | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v7_freeze_readiness/READINESS.md` |
| v7 opened shard | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_opened_shard_v7_candidate_ready/SHARD.md` |
| v7 opened shard model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_opened_shard_v7_candidate_ready/REPORT.md` |
| Prompt v8 freeze | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v8/PROMPT_FREEZE_V8.md` |
| v8 opened shard manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_opened_shard_v8_candidate_bound_v2/PROMPT_MANIFEST.md` |
| v8 opened shard policy rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_opened_shard_v8_policy_rescore_v2/REPORT.md` |
| v8 opened shard model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_opened_shard_v8_candidate_bound_v2/REPORT.md` |
| v8 freeze readiness | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v8_freeze_readiness/READINESS.md` |
| v8 full opened executable manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v8_executable/PROMPT_MANIFEST.md` |
| v8 full opened executable model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/REPORT.md` |
| v9 path-pair feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_path_pair_feasibility/FEASIBILITY.md` |
| v9 path-pair deterministic gate | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_path_pair_gate/GATE.md` |
| Prompt v9 freeze | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v9/PROMPT_FREEZE_V9.md` |
| v9 target shard | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_target_shard/SHARD.md` |
| v9 target model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v9_target_shard/REPORT.md` |
| v10 path-rule normalized gate | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_path_rule_normalized_gate/GATE.md` |
| v10 normalized prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v10_path_rule_normalized/PROMPT_MANIFEST.md` |
| v10 normalized model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v10_path_rule_normalized/REPORT.md` |
| v10 full executable manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_full_executable_manifest/MANIFEST.md` |
| v10 full merged outputs | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_full_merged_outputs/MERGE.md` |
| v10 full merged rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v10_merged/REPORT.md` |
| v11 residual taxonomy | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_residual_taxonomy/TAXONOMY.md` |
| v11 title-slug feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_title_slug_feasibility_v2/FEASIBILITY.md` |
| v11 title-slug model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/REPORT.md` |
| v11b contract retry | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11b_contract_retry/REPORT.md` |
| v11b title-slug merged rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v11b_title_slug_merged/REPORT.md` |
| v11b full merged rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v11b_merged/REPORT.md` |
| v12 RepairAgent/MetaVerifier preflight | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/REPORT.md` |
| v13 RepairAgent prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v13_repairagent_prompt_manifest/PROMPT_MANIFEST.md` |
| v14 blind RepairAgent prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v14_repairagent_prompt_manifest/PROMPT_MANIFEST.md` |
| v14 blind RepairAgent model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v14_repairagent_blind/REPORT.md` |
| v14 blind RepairAgent eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v14_repairagent_blind/REPORT.md` |
| v15 structured repair policy | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v15_structured_repair_policy/REPORT.md` |
| v16 primitive-selection model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v16_primitive_selection/REPORT.md` |
| v16 primitive-selection eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16_primitive_selection_model/REPORT.md` |
| v16b primitive-selection retry eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16b_primitive_selection_retry/REPORT.md` |
| v16b primitive-selection merged eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16b_primitive_selection_merged/REPORT.md` |
| v17 archive-path feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_archive_path_feasibility/FEASIBILITY.md` |
| Prompt v17 freeze | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v17/PROMPT_FREEZE_V17.md` |
| v17 archive-path prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v17_archive_path_target/PROMPT_MANIFEST.md` |
| v17 archive-path model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v17_archive_path_target/REPORT.md` |
| v17 full merged outputs | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_full_merged_outputs/MERGE.md` |
| v17 full merged rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v17_merged/REPORT.md` |
| v18 archive structured repair policy | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v18_archive_structured_repair_policy/REPORT.md` |
| v19 archive selection prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v19_archive_selection_prompt_manifest/PROMPT_MANIFEST.md` |
| v19 archive selection model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v19_archive_selection/REPORT.md` |
| v19 archive selection eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v19_archive_selection_model/REPORT.md` |
| v20 residual taxonomy | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v20_residual_taxonomy/TAXONOMY.md` |
| v21 source-path identity feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v21_source_path_identity_feasibility/FEASIBILITY.md` |
| v22 source-path identity merged rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v22_source_identity_merged/REPORT.md` |
| v23 literal export path feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v23_literal_export_path_feasibility/FEASIBILITY.md` |
| v24 literal export path merged rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v24_literal_export_merged/REPORT.md` |
| v25 ordered note title identity feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v25_ordered_note_title_identity_feasibility/FEASIBILITY.md` |
| v26 ordered note title identity merged rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v26_ordered_note_merged/REPORT.md` |
| v27 prior-effect playlist feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v27_prior_effect_playlist_feasibility/FEASIBILITY.md` |
| v28 prior-effect playlist merged rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v28_prior_effect_merged/REPORT.md` |
| v29 frontier closure repair policy | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy/REPORT.md` |
| v29 frontier selection model run | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v29_frontier_selection/REPORT.md` |
| v29 frontier selection eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29_frontier_selection_model/REPORT.md` |
| v29b frontier selection retry eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29b_frontier_selection_retry/REPORT.md` |
| v29b frontier selection merged eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29b_frontier_selection_merged/REPORT.md` |
| v30 test-time compute freeze | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_freeze/FREEZE.md` |
| v30 retrospective TTC replay | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_replay/REPLAY.md` |
| v31 held-out instance preflight | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v31_heldout_instance_preflight/PREFLIGHT.md` |
| v32 held-out no-repair rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v32_heldout_no_repair/REPORT.md` |
| v33 held-out TTC eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v33_heldout_ttc/REPORT.md` |
| v33 held-out TTC rescore | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v33_heldout_ttc/REPORT.md` |
| v34 held-out best-of-N no-repair control | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v34_heldout_best_of_n_no_repair/REPORT.md` |
| v35 held-out free-form RepairAgent control | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v35_heldout_freeform_repair/REPORT.md` |
| v36 held-out no-MetaVerifier control | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v36_heldout_no_metaverifier_control/REPORT.md` |
| v38 held-out no-typed-residual control | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v38_heldout_no_typed_residual/REPORT.md` |
| v37 held-out control summary | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v37_heldout_control_summary/SUMMARY.md` |
| v39 hard held-out preflight/generation | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v39_hard_heldout_preflight/PREFLIGHT.md`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v39_hard_heldout_generation/REPORT.md` |
| v40 hard pass-subset preflight | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v40_hard_pass_subset_instance_preflight/PREFLIGHT.md` |
| v42 hard typed-vs-untyped eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v42_hard_typed_vs_untyped/REPORT.md` |
| Raw JSON index and analysis | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/TRACK_A_RAW_JSON_INDEX_AND_ANALYSIS.md` |

## Results

| Run | Parser | Prompt protocol | Decision counts | Parse rate | Interpretation |
|---|---|---|---|---:|---|
| v1/v2 smoke | strict full-text JSON | raw Markdown completion | `{'abstain_no_valid': 4}` | 0.000 | Parser blocked by fenced JSON and prompt continuation. |
| v3 smoke | strict full-text JSON | `chat_template_json_prefill_v3` | `{'abstain_no_valid': 1, 'unsafe_unique_wrong': 3}` | 1.000 | Generation protocol fixed parse, but free role choice was semantically unsafe. |
| v4 smoke | strict full-text JSON | `chat_template_json_prefill_role_constrained_v4` | `{'commit_live': 2, 'unsafe_unique_wrong': 2}` | 1.000 | Role constraint helped, but stale ordinal metadata caused one false unsafe. |
| v4 ordinal-fixed rescore | strict full-text JSON | `chat_template_json_prefill_role_constrained_v4` | `{'commit_live': 3, 'unsafe_unique_wrong': 1}` | 1.000 | Ordered-role cases now recover; remaining unsafe is literal-span synthesis. |
| v5 smoke | strict full-text JSON | `chat_template_json_prefill_role_literal_span_v5` | `{'commit_live': 4}` | 1.000 | Literal quoted-span candidates remove the last 4-row smoke unsafe. |
| v5 dev40 | strict full-text JSON | `chat_template_json_prefill_role_literal_span_v5` | `{'abstain_no_valid': 18, 'ambiguous_both_valid': 3, 'commit_live': 19}` | 1.000 | First 40-row gate: 0 unsafe, 19/40 commit-live. |
| v5 dev40 pathfix rescore | strict full-text JSON | `chat_template_json_prefill_role_literal_span_v5` | `{'abstain_no_valid': 17, 'ambiguous_both_valid': 3, 'commit_live': 19, 'unsafe_unique_wrong': 1}` | 1.000 | Correct dotted-path verifier revealed one unsafe derived-path sketch. |
| v6 dev40 | strict full-text JSON | `chat_template_json_prefill_role_literal_derived_v6` | `{'abstain_no_valid': 10, 'ambiguous_both_valid': 10, 'commit_live': 20}` | 1.000 | Source-path candidates remove unsafe again; 20/40 commit-live. |
| v7 dev40 rescore | strict full-text JSON | `chat_template_json_prefill_role_literal_derived_v6` + `path_shape_preserving_basename_mutation_v7` | `{'abstain_no_valid': 10, 'commit_live': 30}` | 1.000 | Fixes derived-path adversarial shape; 30/40 commit-live, 0 unsafe. |
| v7 opened shard | strict full-text JSON | `chat_template_json_prefill_role_literal_derived_v6` + `path_shape_preserving_basename_mutation_v7` | `{'abstain_no_valid': 27, 'commit_live': 57, 'unsafe_unique_wrong': 14}` | 1.000 | Opened-pool shard fails safety; do not full-run. |
| v8 opened shard policy rescore | strict full-text JSON | `chat_template_json_prefill_candidate_bound_v8` + `path_shape_preserving_basename_mutation_v7` | `{'abstain_no_valid': 9, 'commit_live': 48}` | 1.000 | CPU-only rescore of old raw outputs after candidate-bound filtering; 0 unsafe. |
| v8 opened shard model run | strict full-text JSON | `chat_template_json_prefill_candidate_bound_v8` + `path_shape_preserving_basename_mutation_v7` | `{'abstain_no_valid': 7, 'commit_live': 54}` | 1.000 | Candidate-bound prompt run passes safety on executable opened-shard subset. |
| v8 full executable run | strict full-text JSON | `chat_template_json_prefill_candidate_bound_v8` + `path_shape_preserving_basename_mutation_v7` | `{'abstain_no_valid': 90, 'commit_live': 601, 'unsafe_unique_wrong': 156}` | 0.994 | Full executable opened-pool run fails safety; unsafe concentrated in derived-path rows. |
| v9 path-pair deterministic gate | deterministic verifier | `path_pair_transform_binding` | `{'commit_live': 120}` | n/a | Covered full-v8 derived unsafe rows become commit-live; no model/GPU action. |
| v9 target model run | strict full-text JSON | `chat_template_json_prefill_path_pair_v9` | `{'commit_live': 120}` | 1.000 | Qwen synthesizes path-pair sketches for all covered unsafe rows; 0 unsafe. |
| v10 path-rule normalized gate | deterministic verifier | `path_pair_transform_binding` + canonical path literals | `{'commit_live': 156}` | n/a | All full-v8 derived unsafe rows are covered after normalizing `~/trash/.`-style directory literals; no model/GPU action. |
| v10 normalized model run | strict full-text JSON | `chat_template_json_prefill_path_pair_v9` | `{'commit_live': 156}` | 1.000 | Qwen synthesizes path-pair sketches for all full-v8 derived unsafe rows; 0 unsafe. |
| v10 full merged rescore | strict full-text JSON | `mixed_candidate_bound_v8_path_pair_v10` | `{'abstain_no_valid': 90, 'commit_live': 757}` | 0.994 | CPU compositional full-executable gate: v8 unchanged rows plus v10 path-pair overrides; 0 unsafe. |
| v11 title-slug model run | strict full-text JSON | `chat_template_json_prefill_title_slug_v11` | `{'abstain_no_valid': 5, 'commit_live': 60}` | 0.923 | Model learns title-slug proof family but leaks output-contract key on 5 rows; 0 unsafe. |
| v11b title-slug merged rescore | strict full-text JSON | `mixed_title_slug_v11_v11b_contract_retry` | `{'commit_live': 65}` | 1.000 | Output-contract repair reruns only 5 failures; title-slug target fully commits with 0 unsafe. |
| v11b full merged rescore | strict full-text JSON | `mixed_v10_full_title_slug_v11b` | `{'abstain_no_valid': 25, 'commit_live': 822}` | 0.994 | CPU full-executable compositional gate after title-slug repair; 0 unsafe. |
| v12 MetaVerifier preflight | deterministic MetaVerifier | typed residual packets + patch proposals | `2 accepted, 4 rejected controls` | n/a | Correct frontier/contract repairs accepted; content-only, shuffled, parser-relaxation, and prompt-only controls rejected. |
| v14 blind RepairAgent eval | strict patch JSON + deterministic MetaVerifier | `chat_template_json_prefill_repairagent_blind_v14` | `{'accepted': 0, 'processed': 2}` | 1.000 | Qwen proposals parse but fail MetaVerifier; no autonomous RepairAgent claim. |
| v15 structured repair policy | deterministic compiler + MetaVerifier | primitive selection over typed residuals | `2 accepted, 4 rejected controls` | n/a | Structured primitive policy recovers accepted repairs and rejects shortcuts; CPU-only. |
| v16 primitive-selection model eval | primitive selection + deterministic compiler | `chat_template_json_prefill_primitive_selection_v16` | `{'accepted': 1, 'processed': 2}` | 1.000 | Qwen selects title-slug primitives correctly but omits `parser_policy.strict` for contract residual. |
| v16b primitive-selection merged eval | primitive selection + deterministic compiler | `chat_template_json_prefill_primitive_selection_retry_v16b` | `{'accepted': 2, 'processed': 2}` | 1.000 | Targeted retry fixes missing slot; model-in-the-loop structured RepairAgent passes. |
| v17 archive-path feasibility | deterministic verifier | `directory_basename_archive_path_binding` | `{'commit_live': 9}` | n/a | CPU-only feasibility: source directory evidence basename fills task literal archive template; 0 unsafe. |
| v17 archive-path model run | strict full-text JSON | `chat_template_json_prefill_archive_path_v17` | `{'commit_live': 9}` | 1.000 | Qwen synthesizes archive-path sketches for all 9 target rows; 0 unsafe. |
| v17 full merged rescore | strict full-text JSON | `mixed_v11b_full_archive_path_v17` | `{'abstain_no_valid': 16, 'commit_live': 831}` | 0.994 | CPU full-executable compositional gate after archive-path repair; 0 unsafe. |
| v18 archive structured repair policy | deterministic compiler + MetaVerifier | archive primitive selection | `1 accepted, 6 rejected controls` | n/a | Archive proof family fits structured RepairAgent action space; CPU-only. |
| v19 archive primitive-selection eval | primitive selection + deterministic compiler | `chat_template_json_prefill_archive_selection_v19` | `{'accepted': 1, 'processed': 1}` | 1.000 | Qwen selects archive primitives correctly; unchanged MetaVerifier accepts. |
| v20 residual taxonomy | deterministic taxonomy | post-v17 abstain analysis | `{'abstain_no_valid': 16, 'commit_live': 831}` | n/a | Remaining abstains split into source identity, prior-effect playlist, literal export, and ordered note identity. |
| v21 source-path identity feasibility | deterministic proof candidate + barrier | post-v17 source-path residuals | `{'commit_live': 5}` | n/a | Exact `response.path` identity covers all 5 `move_file.source_file_path` abstains; adversarial source paths fail. |
| v22 source-path identity merged rescore | strict full-text JSON | `mixed_v17_full_source_path_identity_deterministic_v22` | `{'abstain_no_valid': 11, 'commit_live': 836}` | 1.000 | Deterministic source-path compiled sketches integrate with strict parser/rescorer; 0 unsafe. |
| v23 literal export path feasibility | deterministic proof candidate + barrier | quoted task path literal | `{'commit_live': 2}` | n/a | Existing `literal_intent_binding` covers the two Spotify CSV export paths; header-string adversaries fail. |
| v24 literal export path merged rescore | strict full-text JSON | `mixed_v22_source_identity_literal_export_path_deterministic_v24` | `{'abstain_no_valid': 9, 'commit_live': 838}` | 1.000 | Deterministic literal compiled sketches integrate with the full executable rescore; 0 unsafe. |
| v25 ordered note title identity feasibility | deterministic proof candidate + barrier | `ordered_note_title_identity_binding` | `{'commit_live': 2}` | n/a | `show_note.response.note_id` plus Bucket List title/content and quoted item covers both note updates. |
| v26 ordered note title identity merged rescore | strict full-text JSON | `mixed_v24_literal_export_ordered_note_title_identity_deterministic_v26` | `{'abstain_no_valid': 7, 'commit_live': 840}` | 1.000 | New ordered-note schema integrates with the full executable rescore; 0 unsafe. |
| v27 prior-effect playlist feasibility | deterministic proof candidate + barrier | `prior_effect_binding` candidate policy | `{'commit_live': 7}` | n/a | `create_playlist.response.playlist_id` prior effects cover all remaining playlist writes; song/id adversaries fail. |
| v28 prior-effect playlist merged rescore | strict full-text JSON | `mixed_v26_ordered_note_prior_effect_playlist_deterministic_v28` | `{'commit_live': 847}` | 1.000 | Deterministic recurrent proof-frontier closure of all 847 opened executable rows; 0 abstain, 0 unsafe. |
| v29 frontier closure policy | deterministic compiler + MetaVerifier | v21-v28 residual packets | `4 accepted / 4 processed` | n/a | Four deterministic frontier repairs are represented as typed residual packets and primitive selections. |
| v29 frontier selection eval | primitive selection + deterministic compiler | `chat_template_json_prefill_frontier_selection_v29` | `{'accepted': 3, 'processed': 4}` | 0.750 | Qwen selects three frontier repairs; source-path row uses invalid primitive ID alias. |
| v29b frontier selection merged eval | primitive selection + deterministic compiler | `mixed_v29_frontier_selection_v29b_retry` | `{'accepted': 4, 'processed': 4}` | 1.000 | Targeted retry fixes the primitive-ID slot; unchanged compiler/MetaVerifier accept all v21-v28 residual packets. |
| v30 retrospective TTC replay | frozen RepairAgent loop replay | opened-data v17 to v28 replay | `831/16/0 -> 847/0/0` | n/a | Mechanics check only: one retrospective repair round with 5 model calls closes opened executable rows; not a held-out TTC claim. |
| v31 held-out instance preflight | value-free manifest | fresh variations 10-12 | `169 target instances, 65 executable prompts` | n/a | Opens held-out structure after v30 freeze; no argument/response values exported at preflight. |
| v32 held-out no-repair baseline | strict full-text JSON | `chat_template_json_prefill_archive_path_v17` | `{'abstain_no_valid': 3, 'commit_live': 62}` | 0.954 | First prospective held-out baseline over 65 executable rows; 0 unsafe. |
| v33 held-out TTC repair | primitive selection + deterministic compiler | frozen v29 literal export primitive | `{'commit_live': 65}` | 1.000 | One held-out RepairAgent model call selects quoted-path primitive and closes the 3 v32 abstains; 0 unsafe. |
| v34 held-out best-of-N no-repair | sampled proof sketches, no RepairAgent | 8 samples on v32 abstains | `{'abstain_no_valid': 3}` | 0.125 sample parse | Extra proof-sketch compute alone does not close the held-out literal-export gap. |
| v35 held-out free-form RepairAgent | free-form patch JSON + MetaVerifier | held-out literal export residual | `0 accepted / 1 processed` | 1.000 parse | Model writes parseable patch but wrong slot (`span_source=derived_path_binding`); MetaVerifier rejects. |
| v36 held-out no-MetaVerifier | compiler-only structured selection | model + negative slot controls | `3 accepted without MetaVerifier; 2 bad controls accepted` | n/a | Compiler-only acceptance admits wrong span-source and parser-relaxation controls. |
| v38 held-out no-typed-residual | primitive selection + MetaVerifier | typed fields withheld | `{'commit_live': 65}` | 1.000 | Model still infers the correct frozen literal-path primitive from untyped API/field failure metadata on this narrow slice. |
| v37 held-out control summary | summary | v32-v36 | structured+MetaVerifier uniquely closes held-out gap | n/a | One-shot, best-of-N, free-form, and no-MetaVerifier controls do not support the same safety claim. |
| v39 hard held-out generation | preregistered hard generators | source/order/prior target families | `BLOCKED` | n/a | Four-generator hard held-out protocol is not headline eligible: `6171bbc` failed generation and audit did not match parent. |
| v42 hard typed-vs-untyped | exploratory pass-subset | ordered-note residual | typed: `15/15`; untyped: `12/15` | 1.000 | On hard ordered-note pass-subset, typed residual selects pre-write content binding; untyped selects output-content binding and is rejected. |

## v6 Dev40 Breakdown

| Required obligation | Commit live | Abstain no valid | Ambiguous both valid | Unsafe unique wrong |
|---|---:|---:|---:|---:|
| `derived_path_binding` | 0 | 0 | 10 | 0 |
| `literal_intent_binding` | 10 | 0 | 0 | 0 |
| `ordered_role_binding` | 7 | 3 | 0 | 0 |
| `prior_effect_binding` | 3 | 7 | 0 | 0 |

## v7 Dev40 Breakdown

| Required obligation | Commit live | Abstain no valid | Ambiguous both valid | Unsafe unique wrong |
|---|---:|---:|---:|---:|
| `derived_path_binding` | 10 | 0 | 0 | 0 |
| `literal_intent_binding` | 10 | 0 | 0 | 0 |
| `ordered_role_binding` | 7 | 3 | 0 | 0 |
| `prior_effect_binding` | 3 | 7 | 0 | 0 |

## v7 Opened-Shard Breakdown

| Required obligation | Commit live | Abstain no valid | Unsafe unique wrong |
|---|---:|---:|---:|
| `derived_path_binding` | 30 | 0 | 0 |
| `literal_intent_binding` | 17 | 0 | 13 |
| `ordered_role_binding` | 9 | 20 | 1 |
| `prior_effect_binding` | 1 | 7 | 0 |

## v8 Opened-Shard Breakdown

| Required obligation | Commit live | Abstain no valid | Unsafe unique wrong |
|---|---:|---:|---:|
| `derived_path_binding` | 30 | 0 | 0 |
| `literal_intent_binding` | 12 | 0 | 0 |
| `ordered_role_binding` | 11 | 0 | 0 |
| `prior_effect_binding` | 1 | 7 | 0 |

## v8 Manifest Scope

| Required obligation | Executable rows |
|---|---:|
| `derived_path_binding` | 30 |
| `literal_intent_binding` | 12 |
| `ordered_role_binding` | 11 |
| `prior_effect_binding` | 8 |

- Skipped rows: 31
- Skip reasons: 12 `required_literal_span_not_live_value`, 19 `missing_ordered_role_candidate`

## v8 Full Opened-Pool Executable Coverage

| Required obligation | Reportable rows | Executable rows | Skipped rows |
|---|---:|---:|---:|
| `derived_path_binding` | 537 | 537 | 0 |
| `literal_intent_binding` | 114 | 12 | 102 |
| `ordered_role_binding` | 567 | 290 | 277 |
| `prior_effect_binding` | 8 | 8 | 0 |
| **Total** | **1226** | **847** | **379** |

- Executable coverage: 847/1226 = 0.691
- Skip reasons: 90 `missing_required_literal_span`, 277 `missing_ordered_role_candidate`, 12 `required_literal_span_not_live_value`

## v8 Full Executable Run Breakdown

| Required obligation | Commit live | Abstain no valid | Unsafe unique wrong |
|---|---:|---:|---:|
| `derived_path_binding` | 300 | 81 | 156 |
| `literal_intent_binding` | 12 | 0 | 0 |
| `ordered_role_binding` | 288 | 2 | 0 |
| `prior_effect_binding` | 1 | 7 | 0 |

- Processed executable rows: 847
- Parse rate: 0.994
- Commit-live: 601
- Unsafe unique-wrong: 156

## Diagnosed Root Causes

1. Parser standard mismatch:
   Prior baselines often used tolerant JSON extraction, but EBW primary correctly keeps strict full-text JSON because prompt echo can produce misleading parseable JSON. Tolerant extraction should remain diagnostic only.

2. v1/v2 generation protocol:
   Feeding a Markdown template as raw completion made Qwen continue the document. Chat-template execution plus assistant prefill fixes this parser-level blocker.

3. v3 semantic unsafe:
   Without role constraints, the model chose syntactically legal but semantically wrong obligations, such as binding `artist_id` to a prior login `access_token` effect.

4. v4 ordinal metadata bug:
   Track A execution preflight omitted `write_ordinal_for_schema`; the manifest builder defaulted missing values to 0. This was fixed by binding to the original broad value-bound ordinal manifest.

5. v4 remaining blocker:
   Literal span synthesis is still unsafe. The remaining unsafe instance is `db15f46742023720eb01`: the true live message is `Please get on venmo.`, but the model emitted `user_span: {"start": 39, "end": 48}`, selecting the wrong substring from the instruction.

6. v5 repair:
   For literal-intent rows, the prompt now includes deterministic `literal_span_candidates` from quoted task text and requires `user_span` to match one candidate. On the same 4-row smoke slice, Qwen emitted `user_span: {"start": 95, "end": 115}` for `Please get on venmo.`, yielding 4/4 `commit_live` and 0 unsafe.

7. dev40 v5 safety:
   On the frozen 40-row dev slice, v5 preserved strict parse 1.0 and had 0 unsafe. It recovered 19/40 safe commits, but derived path bindings were not recovered because the verifier originally did not resolve dotted `response.N` paths.

8. pathfix + v6 repair:
   Resolving dotted paths exposed one unsafe derived-path sketch, so v6 adds deterministic `derived_path_candidates`. v6 returns to 0 unsafe and recovers 20/40 commits. The remaining derived-path cases are conservative `ambiguous_both_valid`, not unsafe.

9. v7 verifier-policy repair:
   The v6 ambiguity was an artifact of adversarial candidate generation: the verifier compared a full destination path against a bare basename from evidence. v7 makes derived-path adversaries action-shaped by preserving the live target directory and mutating only the basename. Re-scoring the same v6 raw model outputs yields 30/40 commit-live and 0 unsafe without another model call.

10. opened-shard failure:
   The 98-row candidate-ready opened shard fails the safety gate with 14 unsafe unique-wrong cases. The failures are concentrated in literal-intent rows: 13/14 unsafe are literal bindings, often multi-write tasks where the model repeatedly selects the first quoted span while the write ordinal requires later spans. This is not a parser failure; parse remains 1.0.

11. v8 candidate-bound repair:
   v8 tightens the executable shard rather than pretending all value-free labels are proofable. Literal rows are included only when the row ordinal's quoted span equals the live target value; ordered rows are included only when a deterministic source candidate proves the live value at the row ordinal. On the resulting 61-row opened shard, Qwen gets 54 commit-live, 7 safe abstain, and 0 unsafe.

12. full opened-pool executable coverage:
   Applying the same v8 candidate-bound filters to all 1226 reportable opened rows yields 847 executable rows. Coverage is complete for derived-path and prior-effect rows, but limited for literal and ordered rows. This turns Track A from a universal row claim into an explicit coverage/recovery/safety claim.

13. full executable run failure:
   Running Qwen on all 847 executable rows fails the safety gate. The 156 unsafe unique-wrong cases are entirely derived-path bindings. The shard passed because it did not expose the broader filesystem pattern where basename evidence is insufficient without constraining the destination directory/parent path. v9 must add a destination-directory binding or a stricter path-pair proof, not just basename derivation.

14. v9 deterministic gate:
   A CPU-only gate over the 120 full-v8 unsafe rows with matching path-pair candidates converts all 120 to `commit_live` with 0 unsafe. This supports the grammar-completeness hypothesis for the covered subset. The remaining 36 unsafe rows need a richer deterministic path-rule parser.

15. v9 model-facing target gate:
   Qwen emits `path_pair_transform_binding` for all 120 covered unsafe rows. The deterministic verifier commits all 120 live actions with 0 unsafe. This closes the loop from typed residual to new proof grammar to model-synthesized proof sketch for the covered failure class.

16. v10 path-rule normalization gate:
   Inspecting the 36 v9 mismatches showed that the parser captured terminal sentence punctuation in directory literals such as `~/trash/.`, while the live action used canonical `~/trash`. After normalizing directory literals and dot segments, a CPU-only gate covers all 156 full-v8 derived unsafe rows and commits all 156 with 0 unsafe.

17. v10 model-facing target gate:
   Qwen emits `path_pair_transform_binding` for all 156 normalized rows. The deterministic verifier commits all 156 live actions with 0 unsafe and parse rate 1.0. This closes the full derived-path unsafe class from full-v8 under the current normalized path-pair grammar.

18. v10 full executable compositional gate:
   A full 847-row executable manifest preserves v8 candidate-bound scope and overrides exactly the 156 previously unsafe derived-path rows to `path_pair_transform_binding`. Reusing row-independent greedy outputs from the full-v8 run for the unchanged 691 rows and the v10 target run for the 156 overrides, CPU rescore yields 757 `commit_live`, 90 `abstain_no_valid`, and 0 unsafe. This is a compositional full-executable gate, not a new GPU full-run.

19. v11 residual taxonomy:
   A CPU-only taxonomy over the v10 full-executable compositional gate finds no remaining unsafe. The 90 post-v10 abstains split into 65 `title_slug_export_path_binding_missing`, 9 `directory_basename_archive_path_binding_missing`, 7 `prior_effect_playlist_membership_binding_abstain`, 5 `source_path_identity_binding_missing`, 2 `literal_export_path_binding_missing`, and 2 `ordered_note_identity_binding_abstain`. Full-v8 executable-scope coverage skips remain 277 ordered-role candidates and 102 literal-span cases. The recommended next RepairAgent benchmark target is `title_slug_export_path_binding`.

20. v11 title-slug feasibility:
   The first title-slug feasibility attempt exposed a useful typed residual: note content is not unique, so matching any `show_note` by content can bind the wrong title. The corrected v2 frontier binds the source note to the latest matching pre-write `show_note` read, then applies task literal backup directory + whitespace-to-underscore title slug + `.md`. CPU barrier commits all 65 target rows with 0 unsafe.

21. v11 title-slug model-facing gate:
   Qwen emits strict valid `title_slug_export_path_binding` sketches for 60/65 rows. The remaining 5 abstain under the strict parser because the output contract leaks `required_obligation` or omits `obligation`; a CPU diagnostic that repairs only that key commits 65/65 with 0 unsafe. This is not a verifier failure, but R3 does not meet parse-rate 1.0 yet.

22. v11b output-contract repair:
   v11b strengthens only the response contract: output key must be `obligation`, never `required_obligation`. Rerunning only the 5 strict parse/contract failures yields 5/5 `commit_live`, parse rate 1.0, and 0 unsafe. Merging v11 original rows with v11b retry rows gives 65/65 title-slug commits. Merging title-slug repairs into the full v10 executable compositional gate gives 822 `commit_live`, 25 `abstain_no_valid`, and 0 unsafe over 847 executable rows.

23. v12 MetaVerifier preflight:
   A CPU-only gate materializes two typed residual packets: title-slug source-binding ambiguity and output-contract obligation-key leakage. MetaVerifier accepts the two correct repair proposals and rejects four negative controls: content-only source binding, residual-family mismatch, parser relaxation, and prompt-only repair. This is the substrate for the next RepairAgent experiment, not yet autonomous patch discovery.

24. v14 answer-blinded RepairAgent attempt:
   Qwen receives answer-blinded typed residual packets and emits parseable patch JSON for both residuals. The unchanged MetaVerifier accepts 0/2 proposals: the title-slug proposal reuses the failed content-only binding family, and the contract proposal chooses `required_obligation` as the required key. This is a useful no-go for autonomous RepairAgent under the current prompt, and it validates that MetaVerifier rejects shortcut repairs.

25. v15 structured repair policy:
   A CPU-only primitive-vocabulary policy selects repair primitives from typed residual packets, compiles them into patch JSON, and runs the unchanged MetaVerifier. The structured positives are accepted, and the same shortcut controls are rejected. This defines the action space for the next model-in-the-loop RepairAgent experiment.

26. v16/v16b model-in-the-loop primitive selection:
   Qwen is asked to select primitive IDs rather than free-form patch JSON. Initial v16 accepts the title-slug repair but misses one required contract primitive (`parser_policy.strict`) for the output-contract residual. v16b retries only that compile failure with an explicit slot-completeness instruction and accepts it. The merged v16b primitive-selection gate accepts both residual repairs with parse and compile rate 1.0.

27. v17 archive-path feasibility:
   The next post-v11b abstain family is `directory_basename_archive_path_binding_missing`. A CPU-only feasibility gate over the 9 vacation-directory compression rows binds immutable directory-list evidence, extracts the source directory basename as `<vacation_spot>`, fills the task literal archive template and extension, and commits all 9 rows with 0 unsafe. This authorizes archive-path as the next structured RepairAgent proof family, but no model-facing grammar/prompt run has been launched yet.

28. v17 archive-path model and full gate:
   The strict parser, prompt assets, manifest builder, and runner verifier now support `directory_basename_archive_path_binding`. Qwen emits valid archive-path sketches for all 9 target rows with parse rate 1.0 and 0 unsafe. Merging these 9 repairs into the full v11b executable compositional gate yields 831 `commit_live`, 16 `abstain_no_valid`, and 0 unsafe over 847 executable rows.

29. v18 archive structured repair policy:
   The archive-path proof family is added to the structured RepairAgent action space. A CPU-only policy selects immutable directory-list source binding, directory-basename transform, task literal archive template, task-template extension, and strict parser. MetaVerifier accepts the structured archive proposal and rejects generic basename projection, wrong template, wrong transform, wrong extension policy, parser relaxation, and prompt-only controls.

30. v19 archive model-in-the-loop primitive selection:
   Qwen receives the v18 archive residual packet and primitive library, selects primitive IDs only, and the deterministic compiler plus unchanged archive MetaVerifier accept the proposal. The selected primitives are immutable directory-list source binding, directory-basename transform, task literal vacation archive template, task-template extension policy, and strict parser. This extends the v16/v16b primitive-selection success to a third proof family.

31. v20 residual taxonomy:
   A CPU-only taxonomy over the v17 full executable compositional gate confirms 16 remaining safe abstentions: 7 `prior_effect_playlist_id_binding_abstain`, 5 `source_path_identity_binding_missing`, 2 `literal_export_path_binding_missing`, and 2 `ordered_note_title_identity_binding_abstain`. The recommended next CPU-first proof family is `source_path_identity_binding`, because it directly complements the destination path-pair repair for `move_file.source_file_path`.

32. v21 source-path identity feasibility:
   The CPU-only source-path frontier covers all 5 `move_file.source_file_path` residuals. The proof candidate binds the write argument to immutable pre-write `response.path` evidence using exact path identity; sibling source paths, destination paths, and mutated path-shaped alternatives fail the unique-validity barrier. This makes `source_path_identity_binding` ready for parser/prompt/runner integration before any Qwen call.

33. v22 source-path identity compositional closure:
   The strict parser, prompt manifest builder, runner/rescorer, and tests now support `source_path_identity_binding`. A deterministic merged-output rescore replaces only the 5 v21-proven rows and improves the full executable opened gate to 836 `commit_live`, 11 `abstain_no_valid`, and 0 unsafe. This is deterministic compiled proof, not Qwen synthesis.

34. v23/v24 literal export path repair:
   The two Spotify CSV `create_file.file_path` residuals are proven by exact quoted task path spans using the existing strict `literal_intent_binding` schema. The v24 deterministic compositional rescore reaches 838 `commit_live`, 9 `abstain_no_valid`, and 0 unsafe.

35. v25/v26 ordered note title/content identity repair:
   A new `ordered_note_title_identity_binding` schema binds `update_note.note_id` to immutable `show_note.response.note_id`, requires the Bucket List title role, and requires the quoted task item to appear in pre-write note content. The v26 deterministic compositional rescore reaches 840 `commit_live`, 7 `abstain_no_valid`, and 0 unsafe.

36. v27/v28 prior-effect playlist repair:
   The remaining 7 `add_song_to_playlist.playlist_id` residuals are frontier/candidate gaps for the existing `prior_effect_binding` schema. Binding each write to the earlier `create_playlist.response.playlist_id` prior effect passes the CPU barrier, and the v28 deterministic compositional rescore reaches 847 `commit_live`, 0 `abstain_no_valid`, and 0 unsafe over the opened executable rows.

37. v29/v29b model-in-the-loop frontier primitive selection:
   The v21-v28 deterministic closure is converted into four answer-blinded residual packets and a primitive library. Qwen first accepts 3/4 under the unchanged deterministic compiler and MetaVerifier; the only miss is a primitive-ID alias (`parser_policy.strict_json_no_regex_repair` instead of `parser_policy.strict`) on source-path identity. A targeted v29b retry fixes that one slot, and the merged eval accepts 4/4: source-path identity, literal export path, ordered-note title identity, and prior-effect playlist.

38. v30 test-time compute freeze and retrospective replay:
   The test-time compute protocol is now frozen before prospective held-out outcomes. Allowed test-time actions are proof search, typed residual emission, primitive-ID selection from the frozen v29 library, deterministic compilation, MetaVerifier acceptance, and rerun/continue under accepted frontiers. The v30 retrospective replay validates mechanics on opened data: v17 starts at 831 commit / 16 abstain / 0 unsafe, and one parallel v29b repair round reaches v28's 847 commit / 0 abstain / 0 unsafe with 5 recorded model calls. This is explicitly not a held-out test-time-compute claim.

39. v31-v33 prospective held-out TTC:
   After the v30 freeze, fresh AppWorld variations 10-12 are used as held-out structure. v31 builds a value-free manifest with 24 fresh tasks and 169 target field instances; v32 builds 65 executable no-repair prompts and the held-out proof-agent baseline commits 62/65 with 3 safe abstentions and 0 unsafe. v33 automatically forms one frozen-library residual packet (`literal_export_path_binding_missing`), Qwen selects the frozen quoted-path primitive IDs, the held-out MetaVerifier accepts 3/3 target rows, and the merged rescore reaches 65/65 commit-live with 0 unsafe. This is the first prospective held-out TTC evidence under the frozen protocol.

40. v34 held-out best-of-N no-repair control:
   To test whether generic extra proof-sketch compute explains v33, the 3 v32 held-out abstains are rerun with 8 sampled proof sketches each and no RepairAgent. All 24 samples remain `abstain_no_valid` and sample parse rate is 0.125. The control stays at 3/3 abstain, so the v33 gain is not reproduced by best-of-N proof sketch sampling without the frozen residual-to-primitive repair path.

41. v35-v38 held-out controls:
   v35 tests free-form RepairAgent patch JSON on the same held-out residual. The model emits parseable patch JSON, but chooses the wrong slot (`span_source=derived_path_binding`), and the fixed MetaVerifier rejects it. v36 tests structured selection without MetaVerifier: compiler-only acceptance admits the correct model selection and two bad controls, including wrong span source and parser relaxation. v37 summarizes the held-out control table: only structured primitive selection with MetaVerifier closes the held-out gap safely.
   v38 withholds `residual_class`, `typed_reason`, `failed_frontier`, and `counterexample_summary`, but keeps API/field failure metadata and the frozen primitive library visible. Qwen still selects the correct literal-path primitive and MetaVerifier accepts. Therefore this narrow held-out slice supports the need for structured MetaVerified repair, but does not by itself prove typed residual labels are necessary.

42. v39-v42 exploratory hard residual test:
   A preregistered hard-residual held-out protocol targets source-path identity (`68ee2c9`), ordered-note identity (`cf6abd2`), and prior-effect playlist (`6171bbc`, `e3d6c94`). The formal v39 four-generator generation is blocked, because `6171bbc` does not generate variations 10-12 and audit variations do not semantically match the broad-schema parent. As an explicitly non-headline exploratory pass-subset, v40 uses the generated `68ee2c9`, `cf6abd2`, and `e3d6c94` fresh tasks. v41 selects a balanced 15-row hard target; no-repair commits 12/15 and leaves 3 ordered-note abstains. v42 shows typed residual packets solve those 3 rows, reaching 15/15, while no-typed residual packets select `content_binding.output_content_contains_item`, fail MetaVerifier, and remain 12/15. This supports typed residual usefulness on a harder ordered-note slice, but it is exploratory rather than headline-held-out.

## External Process State

- DPO equivalent workload was paused only to run Qwen smoke/dev-slice/target tests on GPU0/1.
- DPO was restarted after each smoke with the equivalent command: `/opt/conda/envs/ptca/bin/python -u /home/aiscuser/yifeisun/project_1128/DPO_train.py --gpu 0,1`.
- Current restarted DPO PID observed: `943277`.
- GPU0/1 DPO process is restored; utilization may be phase-dependent.
- v7 rescore was CPU-only and did not pause or restart DPO.

## Safety / Scope

- Sealed AppWorld variations 10-12 opened: No.
- Full Track A 1226-instance run launched: No.
- v3/v4/v5/v6/v7 are development artifacts only and should not be used as a main result without a new freeze decision.
- v5 passed the 4-row smoke gate with `unsafe_unique_wrong == 0`.
- v6 passed the frozen dev40 gate with `unsafe_unique_wrong == 0` and strict parse 1.0.
- v7 passed frozen dev40 rescore with `unsafe_unique_wrong == 0`, strict parse 1.0, and 30/40 commit-live.
- v7 fails the candidate-ready opened-shard gate with `unsafe_unique_wrong == 14`.
- v8 passes the executable candidate-bound opened-shard gate with `unsafe_unique_wrong == 0`, strict parse 1.0, and 54/61 commit-live.
- v8 full opened-pool executable manifest is built: 847 executable rows, 379 skipped rows, sealed variations still closed.
- v8 full opened-pool executable model run fails with `unsafe_unique_wrong == 156`.
- v9 deterministic path-pair gate passes on 120 covered unsafe rows with `unsafe_unique_wrong == 0`.
- v9 model-facing target shard passes on the same 120 rows with `unsafe_unique_wrong == 0` and parse rate 1.0.
- v10 path-rule normalized deterministic gate passes on all 156 full-v8 derived unsafe rows with `unsafe_unique_wrong == 0`.
- v10 model-facing target shard passes on all 156 full-v8 derived unsafe rows with `unsafe_unique_wrong == 0` and parse rate 1.0.
- v10 full executable compositional rescore passes on all 847 executable opened rows with `unsafe_unique_wrong == 0`, preserving 90 safe abstentions.
- v11 residual taxonomy is CPU-only and selects `title_slug_export_path_binding` as the next RepairAgent benchmark target.
- v11 title-slug CPU feasibility passes on all 65 target rows with `unsafe_unique_wrong == 0` after latest-`show_note` source binding.
- v11 title-slug model-facing gate has 60/65 strict commits, 5 strict parse/contract abstains, and 0 unsafe. Diagnostic contract-key repair recovers 65/65, but primary parser remains strict.
- v11b output-contract retry passes on the 5 strict failures; title-slug merged target is 65/65 commit-live with parse rate 1.0 and 0 unsafe.
- v11b full executable compositional rescore passes on all 847 executable rows with 822 commit-live, 25 safe abstentions, and 0 unsafe.
- v12 MetaVerifier preflight is CPU-only and accepts only the correct latest-read frontier and strict-contract repairs while rejecting shortcut controls.
- v14 answer-blinded RepairAgent proposal gate is a no-go: Qwen outputs parseable proposals but MetaVerifier accepts 0/2. Do not claim autonomous repair yet.
- v15 structured repair policy is CPU-only and passes: primitive selection + deterministic compilation recovers accepted repairs and rejects controls.
- v16b model-in-the-loop structured RepairAgent passes after targeted retry: Qwen-selected primitives compile to both accepted repairs under the unchanged MetaVerifier.
- v17 archive-path CPU feasibility passes on all 9 target rows with `unsafe_unique_wrong == 0`.
- v17 archive-path model-facing target passes on all 9 rows with `unsafe_unique_wrong == 0` and parse rate 1.0.
- v17 full executable compositional rescore passes on all 847 executable rows with 831 commit-live, 16 safe abstentions, and 0 unsafe.
- v18 archive structured repair policy is CPU-only and passes: archive primitive selection is accepted and six shortcut controls are rejected.
- v19 archive model-in-the-loop structured RepairAgent passes: Qwen-selected archive primitives compile and MetaVerifier accepts 1/1.
- v20 residual taxonomy is CPU-only and selects `source_path_identity_binding` as the next proof-family target over the remaining 16 safe abstentions.
- v21 source-path identity feasibility is CPU-only and passes on all 5 target rows with 5 commit-live and 0 unsafe.
- v22/v24/v26/v28 deterministic compiled-proof compositional rescores are CPU-only and improve the opened executable gate to 836/838/840/847 commit-live respectively with 0 unsafe.
- Do not report v8 as a safe full-opened result. The safe full-executable claim belongs only to the v10/v11b/v17/v22/v24/v26/v28 compositional gates unless a fresh GPU full-run is separately launched.
- Do not report v21-v28 as Qwen synthesis. They are deterministic recurrent proof-frontier repairs; v29b is the model-in-loop primitive-selection result over those v21-v28 residual packets.
- Do not report v30 retrospective replay as held-out test-time compute. It validates the frozen loop mechanics only; the stronger claim requires a preregistered prospective held-out run.
- v31-v33 are prospective held-out TTC under the v30 freeze: fresh variations 10-12 are opened after freeze; no new primitives/proof families/parser edits are introduced; the first held-out repair closes 3 abstains with one model repair call.
- v34 best-of-N no-repair is a held-out negative control: 8 sampled proof sketches per v32 abstain do not recover any of the 3 abstains and introduce no unsafe commits.
- v35-v38 complete the first held-out control suite: free-form patch JSON is rejected by MetaVerifier, compiler-only structured repair accepts bad controls without MetaVerifier, and withholding typed residual labels does not break this narrow literal-path case.
- v39-v42 add an exploratory hard-residual pass-subset: typed labels help on ordered-note identity, but the preregistered hard-heldout protocol was blocked and should not be reported as headline held-out.

## Next Step

Next, either fix/preregister a clean hard held-out generator set that passes semantic audit, or report v42 only as exploratory evidence that typed residual labels help on ordered-note identity.