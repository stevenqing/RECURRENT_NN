# EBW Track A Raw JSON Index and Data Analysis

## Status: `RPD_EBW_TRACK_A_RAW_JSON_INDEX_READY`

Date: 2026-07-19

This document indexes the raw JSON artifacts behind the EBW Track A v8-v19 results and explains how to read them. It does not duplicate large raw payloads inline. Instead, it gives stable paths, the role of each JSON file, and the aggregate analysis needed to interpret the data.

Sealed AppWorld variations 10-12 remain closed in the artifacts indexed here.

## JSON File Types

| JSON type | Meaning | How to read it |
|---|---|---|
| `evaluation_manifest.json` | A protected-clean row selection for a staged gate. | Contains row IDs, task IDs, call indexes, target fields, and required obligation overrides. It avoids exporting protected argument/response values. |
| `prompt_manifest.json` | Model-facing prompt rows plus compact context and deterministic candidate frontiers. | This is the prompt/input audit trail. It may be large. It records row-level candidates such as `path_pair_transform_candidates`, `title_slug_export_path_candidates`, and `directory_basename_archive_path_candidates`. |
| `raw_model_outputs.json` | Raw model-generated proof sketches or RepairAgent proposals. | This is the primary raw model output. It should be interpreted only through the strict parser and verifier, not by visual inspection alone. |
| `rows.json` | Row-level verifier decisions after parsing raw model output. | Contains `commit_live`, `abstain_no_valid`, `unsafe_unique_wrong`, parse flags, and row IDs. This is the row-level decision ledger. |
| `results.json` | Aggregate result summary for a run/rescore/gate. | Contains counts, parse rate, prompt protocol, hashes, sealed status, and process-action flags. Use this for headline numbers. |
| `merge.json` | Row-independent compositional merge manifest. | Explains which rows came from which prior run before CPU rescore. This is essential for v10/v11b/v17 full executable gates. |
| `feasibility.json` | CPU-only deterministic frontier feasibility result. | Shows whether a proposed proof family can explain a residual class before any model call. |
| `metaverifier.json` | RepairAgent/MetaVerifier proposal acceptance ledger. | Shows accepted repairs, rejected controls, and why each proposal passed or failed. |
| `primitive_library.json` | Structured RepairAgent action vocabulary. | Defines allowed primitive IDs and templates for model-in-the-loop primitive selection. |

## Core Full-Executable Progression

All rows below refer to the same 847-row opened executable scope unless noted otherwise.

| Stage | Key aggregate JSON | Raw/model source | Decision counts | Safety interpretation |
|---|---|---|---|---|
| v8 full executable | `track_a_model_run_full_opened_v8_executable/results.json` | `track_a_model_run_full_opened_v8_executable/raw_model_outputs.json` | `commit_live=601`, `abstain_no_valid=90`, `unsafe_unique_wrong=156` | Unsafe. The 156 unsafe rows are all derived-path writes. |
| v10 full compositional | `track_a_rescore_full_opened_v10_merged/results.json` | `track_a_v10_full_merged_outputs/raw_model_outputs.json` | `commit_live=757`, `abstain_no_valid=90`, `unsafe_unique_wrong=0` | Safe over executable scope by replacing the 156 derived-path unsafe rows with v10 path-pair outputs. |
| v11b full compositional | `track_a_rescore_full_opened_v11b_merged/results.json` | `track_a_v11b_full_merged_outputs/raw_model_outputs.json` | `commit_live=822`, `abstain_no_valid=25`, `unsafe_unique_wrong=0` | Safe over executable scope after title-slug proof repair. |
| v17 full compositional | `track_a_rescore_full_opened_v17_merged/results.json` | `track_a_v17_full_merged_outputs/raw_model_outputs.json` | `commit_live=831`, `abstain_no_valid=16`, `unsafe_unique_wrong=0` | Current strongest full executable compositional gate. |

Important boundary: v10/v11b/v17 full executable gates are compositional row-level gates, not fresh monolithic GPU reruns. This is valid because rows are generated independently and greedily, but it should be reported as compositional unless a fresh full GPU rerun is explicitly launched.

## Stage Index

### v8 Full Executable Unsafe Baseline

| Artifact | Path |
|---|---|
| Prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v8_executable/prompt_manifest.json` |
| Raw model outputs | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/raw_model_outputs.json` |
| Row decisions | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/rows.json` |
| Aggregate results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/results.json` |
| Human report | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/REPORT.md` |

Analysis: v8 is the failure baseline. It processed 847 executable rows with strict parse rate 0.994 and produced 156 unsafe unique-wrong commits. Every unsafe row was a derived-path write where basename-only proof was an insufficient grammar.

### v9-v10 Path-Pair Repair

| Artifact | Path | Use |
|---|---|---|
| v9 feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_path_pair_feasibility/feasibility.json` | Shows initial path-pair coverage: 120/156 unsafe rows matched before normalization. |
| v9 deterministic gate rows/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_path_pair_gate/rows.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_path_pair_gate/results.json` | CPU-only 120-row path-pair proof gate. |
| v9 target shard | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_target_shard/evaluation_manifest.json` | 120-row model target selection. |
| v9 target prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v9_target_shard/prompt_manifest.json` | Model-facing prompts for 120 covered rows. |
| v9 target raw outputs/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v9_target_shard/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v9_target_shard/results.json` | Qwen synthesized 120/120 path-pair sketches. |
| v10 normalized feasibility/gate | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_path_rule_normalized_gate/results.json` | Normalizes path literals such as `~/trash/.` and covers all 156 unsafe rows. |
| v10 target prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v10_path_rule_normalized/prompt_manifest.json` | 156-row model-facing prompt set. |
| v10 target raw outputs/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v10_path_rule_normalized/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v10_path_rule_normalized/results.json` | Qwen synthesized 156/156 path-pair sketches. |
| v10 full merged raw/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_full_merged_outputs/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v10_merged/results.json` | Full executable compositional safety gate: 757 commit, 90 abstain, 0 unsafe. |

Analysis: v9-v10 validates the grammar-completeness hypothesis. The unsafe class was not random model error; it was lossy proof projection. Adding a path-pair proof family and normalizing path literals eliminates the derived-path unsafe class.

### v11-v11b Title-Slug Repair

| Artifact | Path | Use |
|---|---|---|
| v11 residual taxonomy | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_residual_taxonomy/taxonomy.json` | Identifies post-v10 abstain classes: 65 title-slug, 9 archive-path, 7 prior-effect, 5 source-path identity, 2 literal export, 2 ordered note identity. |
| v11 feasibility v1/v2 | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_title_slug_feasibility/feasibility.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_title_slug_feasibility_v2/feasibility.json` | v1 exposes content-only ambiguity; v2 fixes source binding using latest matching pre-write `show_note`. |
| v11 target prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v11_title_slug_target/prompt_manifest.json` | 65-row model target for title-slug sketches. |
| v11 raw outputs/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/results.json` | 60/65 strict commits; 5 output-contract parse failures. |
| v11b retry raw/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11b_contract_retry/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11b_contract_retry/results.json` | Reruns only 5 output-contract failures and recovers 5/5. |
| v11b title merged raw/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11b_title_slug_merged_outputs/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v11b_title_slug_merged/results.json` | 65-row title-slug merged target: 65/65 commit. |
| v11b full merged raw/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11b_full_merged_outputs/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v11b_merged/results.json` | Full executable compositional gate: 822 commit, 25 abstain, 0 unsafe. |

Analysis: title-slug repair demonstrates typed residual refinement. The first deterministic attempt failed on 17 rows because habit tracker note content can repeat. The corrected proof binds the latest matching `show_note` read, not any content match. The model then learned the semantic proof family, but a response-contract residual required v11b: output key must be `obligation`, not `required_obligation`.

### v12-v16b RepairAgent / MetaVerifier

| Artifact | Path | Use |
|---|---|---|
| v12 repair packets | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/repair_packets.json` | Typed residual packets for title-slug source ambiguity and output-contract leakage. |
| v12 MetaVerifier | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/metaverifier.json` | Accepts correct repairs; rejects content-only, residual-shuffled, parser-relaxation, prompt-only controls. |
| v13 prompts/oracle eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v13_repairagent_prompt_manifest/prompt_manifest.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v13_repairagent_oracle_eval/results.json` | Free-form patch proposal prompt and oracle sanity check. |
| v14 blind raw/eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v14_repairagent_blind/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v14_repairagent_blind/results.json` | Qwen free-form RepairAgent no-go: 2 parseable proposals, 0 accepted. |
| v15 primitive library/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v15_structured_repair_policy/primitive_library.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v15_structured_repair_policy/results.json` | CPU structured primitive policy: accepted repairs recovered, controls rejected. |
| v16 raw/eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v16_primitive_selection/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16_primitive_selection_model/results.json` | Model primitive selection: 1/2 accepted, contract selection misses `parser_policy.strict`. |
| v16b retry/merged eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v16b_primitive_selection_retry/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16b_primitive_selection_merged/results.json` | Targeted retry fixes missing slot; merged primitive-selection gate accepts 2/2. |

Analysis: v14 proves free-form patch generation is too unconstrained. v15-v16b shows the right abstraction: model-in-the-loop primitive selection, deterministic compilation, unchanged MetaVerifier. This is the first agent-in-the-loop repair success, but within a defined primitive vocabulary.

### v17-v19 Archive-Path Repair

| Artifact | Path | Use |
|---|---|---|
| v17 feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_archive_path_feasibility/feasibility.json` | CPU gate: 9/9 archive-path candidates match live and commit. |
| v17 prompt manifest | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v17_archive_path_target/prompt_manifest.json` | 9-row model-facing archive-path target. |
| v17 raw outputs/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v17_archive_path_target/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v17_archive_path_target/results.json` | Qwen synthesizes 9/9 archive-path sketches, parse 1.0. |
| v17 full merged raw/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_full_merged_outputs/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v17_merged/results.json` | Full executable compositional gate: 831 commit, 16 abstain, 0 unsafe. |
| v18 archive primitive library/results | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v18_archive_structured_repair_policy/primitive_library.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v18_archive_structured_repair_policy/results.json` | CPU structured archive repair policy, positive accepted and six controls rejected. |
| v19 archive selection raw/eval | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v19_archive_selection/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v19_archive_selection_model/results.json` | Qwen selects archive primitives correctly; MetaVerifier accepts 1/1. |
| v20 residual taxonomy | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v20_residual_taxonomy/taxonomy.json` | Rebuilds taxonomy over the 16 remaining safe abstentions after v17/v19. |
| v21 source-path identity feasibility | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v21_source_path_identity_feasibility/feasibility.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v21_source_path_identity_feasibility/rows.json` | CPU proof gate for the 5 `move_file.source_file_path` residuals; 5 commit-live, 0 unsafe. |
| v22-v28 deterministic closure | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v28_prior_effect_merged/results.json` | Final deterministic compiled-proof rescore: 847 commit-live, 0 abstain, 0 unsafe over opened executable rows. |
| v29/v29b frontier RepairAgent selection | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v29_frontier_selection/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v29b_frontier_selection_retry/raw_model_outputs.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29b_frontier_selection_merged/results.json` | Model-in-the-loop primitive selection over the four v21-v28 residual packets; merged v29b accepts 4/4. |
| v30 TTC freeze/replay | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_freeze/freeze.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_replay/replay.json` | Freezes the TTC protocol and records opened-data retrospective replay: 831/16/0 to 847/0/0 in one repair round. |
| v31-v33 held-out TTC | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v31_heldout_instance_preflight/preflight.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v32_heldout_no_repair/results.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v33_heldout_ttc/results.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v33_heldout_ttc/results.json` | Prospective held-out TTC first pass: no-repair 62/65, structured RepairAgent+MetaVerifier 65/65, 0 unsafe. |
| v34 held-out best-of-N no-repair | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v34_heldout_best_of_n_no_repair/results.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v34_heldout_best_of_n_no_repair/raw_model_outputs.json` | Negative control: 8 sampled proof sketches per v32 abstain, 3/3 rows remain abstain, 0 unsafe. |
| v35-v37 held-out controls | `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v35_heldout_freeform_repair/results.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v36_heldout_no_metaverifier_control/results.json`, `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v37_heldout_control_summary/summary.json` | Free-form patch rejected; no-MetaVerifier compiler-only accepts bad controls; structured+MetaVerifier uniquely closes gap. |

Analysis: archive-path is a third proof family repaired by the same loop. It uses immutable directory-list evidence, extracts the source directory basename as `<vacation_spot>`, and fills the task literal archive path template and extension. v19 extends model-in-the-loop primitive selection beyond title-slug/output-contract to a new transform family.

## Quantitative Analysis

### Safety

| Stage | Unsafe rows | Safety status |
|---|---:|---|
| v8 full executable | 156 | Fails safety. |
| v10 full compositional | 0 | Derived-path unsafe class repaired. |
| v11b full compositional | 0 | Title-slug residual repaired without introducing unsafe. |
| v17 full compositional | 0 | Archive-path residual repaired without introducing unsafe. |
| v28 deterministic closure | 0 | All remaining opened executable residuals repaired by deterministic compiled proofs. |

The core safety transition is from v8's 156 unsafe rows to v10/v11b/v17's 0 unsafe rows. No later repair reintroduces unsafe commits.

### Recovery

| Stage | Commit live | Abstain | Delta commit vs v8 | Delta abstain vs previous full gate |
|---|---:|---:|---:|---:|
| v8 full executable | 601 | 90 | 0 | n/a |
| v10 full compositional | 757 | 90 | +156 | 0 |
| v11b full compositional | 822 | 25 | +221 | -65 |
| v17 full compositional | 831 | 16 | +230 | -9 |
| v22 source identity compositional | 836 | 11 | +235 | -5 |
| v24 literal export compositional | 838 | 9 | +237 | -2 |
| v26 ordered note compositional | 840 | 7 | +239 | -2 |
| v28 prior-effect compositional | 847 | 0 | +246 | -7 |

The repair sequence converts unsafe or abstain rows into verified commits while preserving the unique-validity barrier. The v10 repair converts the 156 unsafe derived-path rows into commits. v11b converts 65 title-slug abstains into commits. v17 converts 9 archive-path abstains into commits.

### Remaining v17 Residuals

After v17 full compositional rescore, the remaining 16 safe abstentions are:

| Residual family proxy | Rows | Representative tasks |
|---|---:|---|
| `prior_effect_binding` | 7 | `6171bbc_1`, `6171bbc_2`, `e3d6c94_2` |
| `derived_path_binding` | 7 | `68ee2c9_1`, `68ee2c9_2`, `6104387_1`, `6104387_2` |
| `ordered_role_binding` | 2 | `cf6abd2_1`, `cf6abd2_2` |

The v20 taxonomy is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v20_residual_taxonomy/TAXONOMY.md`. It selects `source_path_identity_binding` as the next CPU-first target, ahead of the larger but more complex prior-effect playlist residual. v21 then proves CPU feasibility for that target: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v21_source_path_identity_feasibility/FEASIBILITY.md` reports 5/5 commit-live and 0 unsafe. v22-v28 close the remaining opened executable residuals deterministically; the final v28 rescore reports 847/847 commit-live and 0 unsafe.

## Research Interpretation

The raw JSON supports a research method, not a prompt-tuning story:

1. Strict parser and deterministic verifier expose typed failures.
2. Typed failures become candidate proof-frontier repairs.
3. CPU feasibility gates test whether a repair is semantically complete before model calls.
4. Qwen is used for proof sketch synthesis or primitive selection only after deterministic frontiers pass.
5. MetaVerifier rejects shortcut repairs such as parser relaxation, prompt-only patches, residual-family mismatch, and lossy content-only binding.

The strongest current result is:

```text
v28 deterministic full executable compositional gate:
  847 executable opened rows
  847 commit_live
  0 abstain_no_valid
  0 unsafe_unique_wrong
```

The strongest current RepairAgent result is:

```text
model-in-the-loop primitive selection:
  title-slug/output-contract: v16b accepts 2/2
  archive-path: v19 accepts 1/1
  v21-v28 frontier closure packets: v29b accepts 4/4
  unchanged MetaVerifier
```

Claim boundary:

- Safe full-opened v8 should not be claimed.
- The current strongest safe full-executable opened-scope claim belongs to v28 deterministic compositional closure.
- v29b supports model-in-the-loop primitive selection under a fixed vocabulary and deterministic compiler for all four post-v20 residual families.
- v21-v28 do not by themselves prove Qwen synthesis for those new residual packets; v29b is the corresponding primitive-selection model result.
- v30 retrospective replay does not prove held-out test-time compute; it freezes the protocol and validates mechanics before prospective evaluation.
- v31-v33 provide the first prospective held-out TTC evidence, but required baselines remain before a headline claim.
- v34 shows best-of-N proof-sketch sampling without RepairAgent does not close the held-out residuals.
- v35-v37 complete the initial held-out control suite and isolate the mechanism to structured primitive selection with MetaVerifier.
- It does not yet prove fully open-ended autonomous repair.

## Push/Commit Guidance

The raw JSON files under `results/**` are ignored by repository policy and can be large. For GitHub, commit this Markdown index, the closeout/framing documents, specs, and the scripts that reproduce or interpret the JSON. Keep bulk raw JSON local unless a specific artifact must be force-added.
