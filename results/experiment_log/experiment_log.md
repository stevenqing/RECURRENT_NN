# RECURRENT_NN Experiment Log

Generated at: 2026-06-07T10:36:27.711468+00:00

Scope: item-first continuation log for `/home/aiscuser/RECURRENT_NN`. Each row is an experiment item or runbook item; status summaries and artifact indices are derived context below the item ledger.

## Items

| item | name | status | key result |
| --- | --- | --- | --- |
| 001-018 | legacy scaffold and early Module 1 setup | Archived | Retained in reference archive; not front-page gate evidence. |
| 019-020 | scaffold gates and old validation | Demoted | Constructed-true 2x2/D-stage/verifier gates moved to legacy archive. |
| 021 | M2.0 frozen operator probe | Done | verdict=NEEDS_OPERATOR_FIX; low forced recall/precision blocks direct loop. |
| 022 | M2.0 fix-rescale probe | Done | verdict=PER_TASK_ROUTING; branch_decision=qwen_guess_beats_mrv_reconsider |
| 023 | Module 1 fair GRU closeout | Done, not locked | classification=NOT_READY; max_ratio=0.9025; lock=False |
| 024 | Stage A reconstructed handoff | Blocked | verdict=NEEDS_REVIEW; statuses=['PARENT_ADAPTER_REQUIRED']; n_cells=0 |
| 025 | adapter wiring pass | RECORDED_FROM_RUNBOOK | Adapter wiring pass exists in the post-024 continuation state; source artifact was not found in this workspace scan. |
| 026 | banded Sudoku9 plus gate refusal | RECORDED_FROM_RUNBOOK | Banded Sudoku9/Sudoku6 datasets are treated as ready by the continuation state; fail-closed gate refusal is part of the current truth. |
| 027 | Sudoku6 bridge G1 | BLOCKER | G1=0.0; The Stage A critical blocker is G1 = 0.0 on the Sudoku6 bridge operator. |
| P0 | ledger and validation housekeeping | Updated | validation_checks=126; validation_passed=False |
| W3.0 | Qwen3.5 checkpoint pin | Done | model_id=Qwen/Qwen3.5-4B; total_gib=8.701 |
| P1 | G1 fix spec and diagnostics | Specified | g1_fix_spec plus Stage A adapter/gate/Sudoku6 diagnostic artifacts are present; retraining not launched. |
| P2 | W3 Qwen3.5 probe | alongside_candidate_pending_survival_and_delta_probes | W3.0=PASS; W3.1/W3.2 heavy probes not launched. |
| P3 | TRM defensive analysis | Not launched | No TRM checkpoint/test-set grading code is present in this repo yet. |
| Module1 law | per-depth capacity | Writable now | decision=k_direction_negative; open=False; shards=8 |
| 028 | P0 ledger and validation housekeeping | COMPLETE_RED_EXPECTED | P1.1a Task A diagnosis and P2 W3 hidden-hook/probe work remain next; P1/P2 should produce items 029+ using this contract. |
| 029 | P1.1a G1 diagnosis Task A | COMPLETE_BLOCKED_OBJECTIVE_WIRING | Implement Sudoku6 dataset/encoding artifacts and parent adapter wiring before P1.1b retrain; route to objective_wiring rather than budget-only. |
| 030 | P2 W3 Qwen3.5 hook and capacity probe | PARTIAL_NOT_ACCEPTED | Continue P2 with decay survival, native-delta gap, and W3.2 propagation delta probes; current grade is alongside_candidate_pending_survival_and_delta_probes, not accepted P2 completion. |

## Item Details

### Item 001-018 - legacy scaffold and early Module 1 setup

- Status: Archived
- Key result: Retained in reference archive; not front-page gate evidence.
- Details:
  - These items belong to the old scaffold/oracle-trace era and are no longer the current front-page gate evidence.
  - Missing legacy files remain visible in validation as legacy failures rather than being silently treated as current blockers.
- Artifacts:
  - results/preregistration/preregistration.json (missing)
  - results/oracle_dataset/summary.json (missing)
  - results/operator_cache/summary.json (missing)
  - results/operator_cache/qwen_probe_cache_summary.json (missing)
  - results/operator_cache/qwen_128_cache_summary.json (missing)
  - results/learned_wiring_qwen_128/results.json (missing)
  - results/operator_cache/qwen_balanced_320_cache_summary.json (missing)
  - results/learned_wiring_qwen_balanced_320/results.json (missing)
  - results/two_by_two/results.json (missing)
  - results/d_stage_0/results.json (missing)
  - results/d_stage_1/results.json (missing)
  - results/d_stage_2/results.json (missing)
  - results/d_stage_3/results.json (missing)
  - results/verifier/results.json (missing)
  - results/ttt/results.json (missing)
- Detail data:
  - results/preregistration/preregistration.json: missing
  - results/oracle_dataset/summary.json: missing
  - results/operator_cache/summary.json: missing
  - results/operator_cache/qwen_probe_cache_summary.json: missing
  - results/operator_cache/qwen_128_cache_summary.json: missing
  - results/learned_wiring_qwen_128/results.json: missing
  - results/operator_cache/qwen_balanced_320_cache_summary.json: missing
  - results/learned_wiring_qwen_balanced_320/results.json: missing
  - results/two_by_two/results.json: missing
  - results/d_stage_0/results.json: missing
  - results/d_stage_1/results.json: missing
  - results/d_stage_2/results.json: missing
  - results/d_stage_3/results.json: missing
  - results/verifier/results.json: missing
  - results/ttt/results.json: missing
- Next action: Do not use these archived scaffold rows as proof of the current Stage A claim.

### Item 019-020 - scaffold gates and old validation

- Status: Demoted
- Key result: Constructed-true 2x2/D-stage/verifier gates moved to legacy archive.
- Details:
  - The validator now reports missing legacy artifacts individually.
  - Current validation is registry-style and does not collapse missing history into one opaque required-files failure.
- Artifacts:
  - analysis/validate_outputs.py (yes)
  - results/validation/validation.json (yes)
  - results/validation/validation.md (yes)
- Detail data:
  - analysis/validate_outputs.py: embedded py (23867 bytes)
  - results/validation/validation.json: embedded json (21307 bytes)
  - results/validation/validation.md: embedded md (12173 bytes)
- Next action: Keep these checks archived unless the old scaffold artifacts are intentionally regenerated.

### Item 021 - M2.0 frozen operator probe

- Status: Done
- Key result: verdict=NEEDS_OPERATOR_FIX; low forced recall/precision blocks direct loop.
- Details:
  - original_verdict=NEEDS_OPERATOR_FIX
  - Frozen Qwen current-node operator was not accepted as a direct solver component.
  - Per-task routing discipline remains required; no ordering-only pass is accepted.
- Artifacts:
  - results/m2_operator_probe/report.json (yes)
- Detail data:
  - results/m2_operator_probe/report.json: embedded json (5050 bytes)
- Next action: Use this as negative evidence when deciding whether Qwen can carry structured propagation unaided.

### Item 022 - M2.0 fix-rescale probe

- Status: Done
- Key result: verdict=PER_TASK_ROUTING; branch_decision=qwen_guess_beats_mrv_reconsider
- Details:
  - qwen_guess mean_nodes=4.939; invalid_guess_rate=0.2316
  - mrv mean_nodes=5.067; invalid_guess_rate=0
  - routing={'fix_tasks': ['general_sat', 'graph_coloring', 'horn_sat', 'logic_grid', 'sudoku_4x4'], 'pass_tasks': []}
- Artifacts:
  - results/m2_operator_probe/report_fix_rescale.json (yes)
  - results/m2_operator_probe/report_fix_rescale.md (yes)
- Detail data:
  - results/m2_operator_probe/report_fix_rescale.json: embedded json (13951 bytes)
  - results/m2_operator_probe/report_fix_rescale.md: embedded md (8821 bytes)
- Next action: Treat Qwen guess results as routing evidence, not as an autonomous pass.

### Item 023 - Module 1 fair GRU closeout

- Status: Done, not locked
- Key result: classification=NOT_READY; max_ratio=0.9025; lock=False
- Details:
  - Fair GRU grid completed and all GRU cells remained below structured frontier in the recorded closeout.
  - Headline remains unlocked because the in-loop arbiter/Stage A proof is still unavailable.
- Artifacts:
  - results/gru_stack_grid_fair/results.json (yes)
  - results/gru_vs_structured_closeout/results.json (yes)
- Detail data:
  - results/gru_stack_grid_fair/results.json: embedded json (1885517 bytes)
  - results/gru_vs_structured_closeout/results.json: embedded json (55526 bytes)
- Next action: Revisit only after Stage A has autonomous cells instead of parent-adapter-required stops.

### Item 024 - Stage A reconstructed handoff

- Status: Blocked
- Key result: verdict=NEEDS_REVIEW; statuses=['PARENT_ADAPTER_REQUIRED']; n_cells=0
- Details:
  - artifact_policy=reconstructed_in_repo_not_inherited; manifest_status=READY
  - stage_a_statuses=['PARENT_ADAPTER_REQUIRED']; n_cells=0
  - Parent artifacts are reconstructed in-repo but autonomous Stage A cells are still unavailable.
- Artifacts:
  - artifacts/stage_a/manifest.json (yes)
  - results/stage_a_backtrack/report.json (yes)
  - results/stage_a_backtrack/results.json (yes)
- Detail data:
  - artifacts/stage_a/manifest.json: embedded json (3488 bytes)
  - results/stage_a_backtrack/report.json: embedded json (193 bytes)
  - results/stage_a_backtrack/results.json: embedded json (156488 bytes)
- Next action: Wire the parent adapter and keep fail-closed preflight before launching autonomous solve metrics.

### Item 025 - adapter wiring pass

- Status: RECORDED_FROM_RUNBOOK
- Key result: Adapter wiring pass exists in the post-024 continuation state; source artifact was not found in this workspace scan.
- Details:
  - materialized_status=PASS; preflight_status=READY; register_smoke_status=SMOKE_PASS
  - grid_cells=36; autonomous_solve_status=NOT_RUN
  - operator_exists=True; bridge_exists=True; teacher_trace_tasks=1024
- Artifacts:
  - results/continuation_state/post_027.json (yes)
  - results/stage_a_adapter_wiring/results.json (yes)
- Detail data:
  - results/continuation_state/post_027.json: embedded json (1453 bytes)
  - results/stage_a_adapter_wiring/results.json: embedded json (2413 bytes)
- Next action: This is a wiring/preflight item only; it does not prove autonomous solving.

### Item 026 - banded Sudoku9 plus gate refusal

- Status: RECORDED_FROM_RUNBOOK
- Key result: Banded Sudoku9/Sudoku6 datasets are treated as ready by the continuation state; fail-closed gate refusal is part of the current truth.
- Details:
  - materialized_status=PASS; fail_closed_cases=3; refused_all=True
  - sudoku9_status=READY_STUB_EMPTY; sudoku9_generated_count=0
  - sudoku6_status=RECORDED_READY_FROM_RUNBOOK_NOT_GENERATED_IN_REPO
- Artifacts:
  - results/continuation_state/post_027.json (yes)
  - results/stage_a_banded_gate_refusal/results.json (yes)
- Detail data:
  - results/continuation_state/post_027.json: embedded json (1453 bytes)
  - results/stage_a_banded_gate_refusal/results.json: embedded json (3420 bytes)
- Next action: Replace continuation-recorded Sudoku6 readiness with concrete generator/data artifacts during the G1 fix.

### Item 027 - Sudoku6 bridge G1

- Status: BLOCKER
- Key result: G1=0.0; The Stage A critical blocker is G1 = 0.0 on the Sudoku6 bridge operator.
- Details:
  - materialized_status=BLOCKED_G1_ZERO; G1=0.0; single_step_forced_accuracy=0.0
  - gates={'G1_depth1_bridge': 'FAIL', 'G2_depth_frontier': 'NOT_RUN', 'L4_forward_floor': 'FAIL_NOT_RUN', 'L4_reverts_nonzero': 'FAIL_NOT_RUN'}
  - stick_reasons={'criterion_never_met': 1, 'missing_bridge_trainer': 1, 'missing_sudoku6_dataset_generator': 1, 'no_commit': 0, 'parent_adapter_not_integrated': 1, 'wrong_commit': 0}
  - teacher_trace_probe={'exists': True, 'path': 'artifacts/stage_a/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl', 'sampled_action_counts': {'branch': 76, 'propagate': 4020, 'solved': 256}, 'sampled_max_backtrack_depth': 3, 'sampled_tasks': 256}
- Artifacts:
  - results/continuation_state/post_027.json (yes)
  - results/stage_a_sudoku6_bridge/results.json (yes)
  - specs/g1_fix_spec.md (yes)
- Detail data:
  - results/continuation_state/post_027.json: embedded json (1453 bytes)
  - results/stage_a_sudoku6_bridge/results.json: embedded json (2412 bytes)
  - specs/g1_fix_spec.md: embedded md (2587 bytes)
- Next action: Implement the G1 fix; do not soften G2 or L4 checks.

### Item P0 - ledger and validation housekeeping

- Status: Updated
- Key result: validation_checks=126; validation_passed=False
- Details:
  - Canonical repo is /home/aiscuser/RECURRENT_NN; old /home/aiscuser/stage_d_llm is absent locally.
  - validation_pass=117; validation_fail=9
  - Current expected failures are Stage A G1/L4 and missing legacy scaffold artifacts.
- Artifacts:
  - CANONICAL_REPO.md (yes)
  - analysis/validate_outputs.py (yes)
  - results/validation/validation.json (yes)
  - results/experiment_log/experiment_log.json (yes)
- Detail data:
  - CANONICAL_REPO.md: embedded md (532 bytes)
  - analysis/validate_outputs.py: embedded py (23867 bytes)
  - results/validation/validation.json: embedded json (21307 bytes)
  - results/experiment_log/experiment_log.json: not embedded (self_output_not_embedded)
- Next action: Keep future reports item-first and preserve explicit red checks.

### Item W3.0 - Qwen3.5 checkpoint pin

- Status: Done
- Key result: model_id=Qwen/Qwen3.5-4B; total_gib=8.701
- Details:
  - snapshot_path=/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
  - n_files=14; total_bytes=9342907469
  - This pins availability of the external model asset but does not run hidden-hook or propagation probes.
- Artifacts:
  - results/model_download/qwen3_5_4b/qwen_download.json (yes)
- Detail data:
  - results/model_download/qwen3_5_4b/qwen_download.json: embedded json (326 bytes)
- Next action: Use W3/P2 records before considering any Qwen3.5 integration route.

### Item P1 - G1 fix spec and diagnostics

- Status: Specified
- Key result: g1_fix_spec plus Stage A adapter/gate/Sudoku6 diagnostic artifacts are present; retraining not launched.
- Details:
  - Task A diagnosis and Task B deep-supervision bridge retrain are specified.
  - Current diagnostics still record G1=0.0 and L4 checks failing/not-run.
  - Stage A parent binaries are regenerated workflow artifacts, not tracked binaries.
- Artifacts:
  - specs/g1_fix_spec.md (yes)
  - results/stage_a_adapter_wiring/results.json (yes)
  - results/stage_a_banded_gate_refusal/results.json (yes)
  - results/stage_a_sudoku6_bridge/results.json (yes)
- Detail data:
  - specs/g1_fix_spec.md: embedded md (2587 bytes)
  - results/stage_a_adapter_wiring/results.json: embedded json (2413 bytes)
  - results/stage_a_banded_gate_refusal/results.json: embedded json (3420 bytes)
  - results/stage_a_sudoku6_bridge/results.json: embedded json (2412 bytes)
- Next action: Launch the actual bridge retrain only after concrete Sudoku6 data/training entrypoints exist.

### Item P2 - W3 Qwen3.5 probe

- Status: alongside_candidate_pending_survival_and_delta_probes
- Key result: W3.0=PASS; W3.1/W3.2 heavy probes not launched.
- Details:
  - hidden_size=2560; layers=32; full_attention_layers=8; linear_layers=24
  - capacity_estimates=6; hidden_hook={'device': 'cuda:0', 'hidden_dim': 2560, 'hidden_shape': [1, 29, 2560], 'last_token_norm': 154.2971649169922, 'load_model': True, 'state_hook_round_trip': {'note': 'This verifies hidden-state tensor access and perturbability, not a full cached-state generation intervention.', 'perturbation_affected_next_step': True, 'perturbation_injected': True, 'perturbation_norm': 0.03163394331932068}}
  - verdicts={'W3.0_checkpoint_pin': 'PASS', 'W3.1_capacity_at_real_gdn_dims': 'PLANNING_ESTIMATE_ONLY', 'W3.1_gating_decay_stack_survival': 'HOOK_ONLY_NOT_SURVIVAL_CURVE', 'W3.1_native_delta_rule_as_stack_gap': 'NOT_RUN', 'W3.2_qwen3_4b_delta_table': 'NOT_RUN'}
- Artifacts:
  - specs/w3_qwen35_probe_spec.md (yes)
  - results/w3_qwen35_probe/results.json (yes)
  - results/w3_qwen35_probe/verdicts.json (yes)
- Detail data:
  - specs/w3_qwen35_probe_spec.md: embedded md (1807 bytes)
  - results/w3_qwen35_probe/results.json: embedded json (9321 bytes)
  - results/w3_qwen35_probe/verdicts.json: embedded json (459 bytes)
- Next action: Run hidden-hook, gating-survival, native-delta, and W3.2 propagation probes before integration.

### Item P3 - TRM defensive analysis

- Status: Not launched
- Key result: No TRM checkpoint/test-set grading code is present in this repo yet.
- Details:
  - TRM is allowed only as recipe guidance, never as a checkpoint inside controlled comparisons.
  - No defensive depth-ceiling test-set artifact exists in the current workspace.
- Artifacts:
  - specs/g1_fix_spec.md (yes)
- Detail data:
  - specs/g1_fix_spec.md: embedded md (2587 bytes)
- Next action: Create explicit TRM defensive analysis artifacts before reporting P3 evidence.

### Item Module1 law - per-depth capacity

- Status: Writable now
- Key result: decision=k_direction_negative; open=False; shards=8
- Details:
  - Per-depth capacity law is the current Tier A quantitative anchor.
  - K-direction is negative/nonincreasing in the recorded per-depth artifact.
  - Bound-single and factored fitted K_eff choices are validated separately in the registry.
- Artifacts:
  - results/module1_capacity_perdepth_shards/results.json (yes)
  - results/module1_capacity_perdepth_shards/curves.json (yes)
  - results/module1_capacity_benchmark_full_shards/k_direction_corrected.json (yes)
- Detail data:
  - results/module1_capacity_perdepth_shards/results.json: embedded json (7251562 bytes)
  - results/module1_capacity_perdepth_shards/curves.json: embedded json (1568381 bytes)
  - results/module1_capacity_benchmark_full_shards/k_direction_corrected.json: embedded json (53731 bytes)
- Next action: Use this law as support for structured register capacity, not as a substitute for Stage A autonomous proof.

### Item 028 - P0 ledger and validation housekeeping

- Status: COMPLETE_RED_EXPECTED
- Key result: P1.1a Task A diagnosis and P2 W3 hidden-hook/probe work remain next; P1/P2 should produce items 029+ using this contract.
- Purpose: Executes P0.1-P0.3 from the master runbook: declare RECURRENT_NN canonical, fold post-027 state into the itemized ledger, restore a full validation registry, and demote stale scaffold gates into legacy archive context. This item bears on report correctness and prevents stale stage_d_llm-generated ledgers from masking Stage A blockers.
- Details:
  - purpose=Executes P0.1-P0.3 from the master runbook: declare RECURRENT_NN canonical, fold post-027 state into the itemized ledger, restore a full validation registry, and demote stale scaffold gates into legacy archive context. This item bears on report correctness and prevents stale stage_d_llm-generated ledgers from masking Stage A blockers.
  - commands=8
  - result_tables=['validation_registry_before_after', 'ledger_reconciliation', 'report_front_page']
  - honesty=this item does NOT establish that the Stage A bridge solves autonomously, that G1 passes, that L4 separation is restored, or that Qwen3.5 integration is viable.
- Artifacts:
  - results/experiment_items/item_028_p0_housekeeping.json (yes)
  - CANONICAL_REPO.md (yes)
  - ENV_SPEC.md (yes)
  - REPRODUCIBILITY.md (yes)
  - scripts/reproduce_continuation_state.sh (yes)
  - results/continuation_state/post_027.json (yes)
  - results/validation/validation.json (yes)
  - results/validation/validation.md (yes)
  - results/experiment_log/experiment_log.json (yes)
  - results/experiment_log/experiment_log.md (yes)
  - specs/log_item_contract.md (yes)
  - results/stage_a_adapter_wiring/results.json (yes)
  - results/stage_a_banded_gate_refusal/results.json (yes)
  - results/stage_a_sudoku6_bridge/results.json (yes)
  - results/w3_qwen35_probe/results.json (yes)
  - results/w3_qwen35_probe/verdicts.json (yes)
- Detail data:
  - results/experiment_items/item_028_p0_housekeeping.json: embedded json (8393 bytes)
  - CANONICAL_REPO.md: embedded md (532 bytes)
  - ENV_SPEC.md: embedded md (7465 bytes)
  - REPRODUCIBILITY.md: embedded md (3563 bytes)
  - scripts/reproduce_continuation_state.sh: embedded sh (1972 bytes)
  - results/continuation_state/post_027.json: embedded json (1453 bytes)
  - results/validation/validation.json: embedded json (21307 bytes)
  - results/validation/validation.md: embedded md (12173 bytes)
  - results/experiment_log/experiment_log.json: not embedded (self_output_not_embedded)
  - results/experiment_log/experiment_log.md: not embedded (self_output_not_embedded)
  - specs/log_item_contract.md: embedded md (3662 bytes)
  - results/stage_a_adapter_wiring/results.json: embedded json (2413 bytes)
  - results/stage_a_banded_gate_refusal/results.json: embedded json (3420 bytes)
  - results/stage_a_sudoku6_bridge/results.json: embedded json (2412 bytes)
  - results/w3_qwen35_probe/results.json: embedded json (9321 bytes)
  - results/w3_qwen35_probe/verdicts.json: embedded json (459 bytes)
- Next action: P1.1a Task A diagnosis and P2 W3 hidden-hook/probe work remain next; P1/P2 should produce items 029+ using this contract.

### Item 029 - P1.1a G1 diagnosis Task A

- Status: COMPLETE_BLOCKED_OBJECTIVE_WIRING
- Key result: Implement Sudoku6 dataset/encoding artifacts and parent adapter wiring before P1.1b retrain; route to objective_wiring rather than budget-only.
- Purpose: Executes P1.1 Task A from specs/g1_fix_spec.md: diagnose why the Sudoku6 bridge G1 is zero before any retraining. This item bears on the Stage A critical path by deciding whether the next fix is objective/wiring, commit criterion, or budget.
- Details:
  - purpose=Executes P1.1 Task A from specs/g1_fix_spec.md: diagnose why the Sudoku6 bridge G1 is zero before any retraining. This item bears on the Stage A critical path by deciding whether the next fix is objective/wiring, commit criterion, or budget.
  - commands=2
  - result_tables=['training_curve_summary', 'single_step_forced_precision_recall_by_depth', 'iterative_stick_reason_histogram', 'train_vs_eval_encoding_byte_diff', 'decision_branch']
  - honesty=this item does NOT establish that the bridge objective is correct, that G1 can be fixed by longer training, or that any autonomous Sudoku6 solve works.
- Artifacts:
  - results/experiment_items/item_029_p1_1a_g1_diagnosis.json (yes)
  - results/stage_a_sudoku6_bridge/results.json (yes)
  - specs/g1_fix_spec.md (yes)
  - experiments/stage_a_sudoku6_bridge.py (yes)
- Detail data:
  - results/experiment_items/item_029_p1_1a_g1_diagnosis.json: embedded json (5525 bytes)
  - results/stage_a_sudoku6_bridge/results.json: embedded json (2412 bytes)
  - specs/g1_fix_spec.md: embedded md (2587 bytes)
  - experiments/stage_a_sudoku6_bridge.py: embedded py (5224 bytes)
- Next action: Implement Sudoku6 dataset/encoding artifacts and parent adapter wiring before P1.1b retrain; route to objective_wiring rather than budget-only.

### Item 030 - P2 W3 Qwen3.5 hook and capacity probe

- Status: PARTIAL_NOT_ACCEPTED
- Key result: Continue P2 with decay survival, native-delta gap, and W3.2 propagation delta probes; current grade is alongside_candidate_pending_survival_and_delta_probes, not accepted P2 completion.
- Purpose: Starts P2 from specs/w3_qwen35_probe_spec.md by loading Qwen/Qwen3.5-4B on GPU 6, recording model-card facts from the HF snapshot, verifying hidden-state tensor access/perturbability, and deriving capacity-law overlays at the real hidden dimension. This item bears on the S3.1 integration grade but does not complete P2 because survival, native-delta gap, and propagation delta probes remain unrun.
- Details:
  - purpose=Starts P2 from specs/w3_qwen35_probe_spec.md by loading Qwen/Qwen3.5-4B on GPU 6, recording model-card facts from the HF snapshot, verifying hidden-state tensor access/perturbability, and deriving capacity-law overlays at the real hidden dimension. This item bears on the S3.1 integration grade but does not complete P2 because survival, native-delta gap, and propagation delta probes remain unrun.
  - commands=1
  - result_tables=['model_card', 'state_hook_round_trip', 'capacity_at_real_gdn_dims', 'decay_survival', 'native_rule_gap', 'propagation_per_task_delta', 'verdicts_echo']
  - honesty=this item does NOT establish that Qwen3.5 has stable in-state stack memory, that native hidden deltas implement keyed register operations, or that propagation improves over Qwen3-4B.
- Artifacts:
  - results/experiment_items/item_030_p2_w3_hook_capacity.json (yes)
  - results/w3_qwen35_probe/results.json (yes)
  - results/w3_qwen35_probe/verdicts.json (yes)
  - specs/w3_qwen35_probe_spec.md (yes)
  - experiments/w3_qwen35_probe.py (yes)
  - results/model_download/qwen3_5_4b/qwen_download.json (yes)
  - results/module1_capacity_perdepth_shards/results.json (yes)
- Detail data:
  - results/experiment_items/item_030_p2_w3_hook_capacity.json: embedded json (7570 bytes)
  - results/w3_qwen35_probe/results.json: embedded json (9321 bytes)
  - results/w3_qwen35_probe/verdicts.json: embedded json (459 bytes)
  - specs/w3_qwen35_probe_spec.md: embedded md (1807 bytes)
  - experiments/w3_qwen35_probe.py: embedded py (11713 bytes)
  - results/model_download/qwen3_5_4b/qwen_download.json: embedded json (326 bytes)
  - results/module1_capacity_perdepth_shards/results.json: embedded json (7251562 bytes)
- Next action: Continue P2 with decay survival, native-delta gap, and W3.2 propagation delta probes; current grade is alongside_candidate_pending_survival_and_delta_probes, not accepted P2 completion.


## Canonical Repo Decision

- Canonical repo: `/home/aiscuser/RECURRENT_NN`
- Legacy path `/home/aiscuser/stage_d_llm`: not present locally; old commands using that path are historical provenance text.
- Module 1 artifacts are referenced from the current repo only; no local duplicate `stage_d_llm/results/` tree exists to de-duplicate.

## Evidence Tiers

### Tier A - Writable Now
- Module 1 capacity law: per-depth ceiling-free K-direction negative; bound_single best K_eff = D_over_ln_product with R2 about 0.99; factored best K_eff = D_over_ln_Kvar/max-factor with R2 about 0.98; capacity is linear in D for the measured construction.
- Ceiling-artifact resolution narrative for low-K frontier artifacts.
- Fair GRU 144-cell grid completed; all cells below structured; max GRU/structured ratio 0.9025; closeout honestly NOT_READY pending in-loop arbiter.
- TTT irreversibility remains real mechanism evidence when its non-scaffold artifact is present; the constructed scaffold gate is archived.
- M2.0 negatives: frozen Qwen operator still needs a fix; invalid qwen_guess rate and spike precision/recall asymmetry block direct loop use.

### Tier B - In Flight, Blocks Core Claim
- Stage A in-loop proof blocks the core claim.
- Banded Sudoku9/6 readiness and fail-closed refusal are materialized in post-026 artifacts, with Sudoku6 data still recorded as continuation-state readiness rather than generated in-repo data.
- Fail-closed preflight is proven for missing/quarantined parent paths; unsafe paths are refused.
- Current blocker: G1 = 0.0 on the Sudoku6 bridge operator.

### Tier C - Not Started
- W3 Qwen3.5 probe: checkpoint and metadata/capacity estimate are implemented; hidden-hook, gating-survival, native-delta, and W3.2 propagation probes are not launched.
- S2 accounting rides on the controlled relaunch.
- TRM defensive depth-ceiling analysis is not started.
- S3.1 integration is not started.

## Current Gate And Blocker Status

| area | status | evidence |
| --- | --- | --- |
| Module 1 capacity law | GREEN | decision=k_direction_negative; open=False; K_eff fits recorded |
| Fair GRU closeout | YELLOW | classification=NOT_READY; max_ratio=0.9025; headline_locked=False |
| M2.0 frozen Qwen operator | RED | verdict=PER_TASK_ROUTING; list_all_recall=0.3771; single_precision=0.4322 |
| Branch policy | YELLOW | qwen_nodes=4.939; mrv_nodes=5.067; qwen_invalid_rate=0.2316 |
| Stage A in-loop proof | RED | n_cells=0; statuses=['PARENT_ADAPTER_REQUIRED']; G1=0.0 |
| W3 Qwen3.5 | YELLOW | integration_grade=alongside_candidate_pending_survival_and_delta_probes; W3.0=PASS |
| Validation | RED | checks=126; pass=117; fail=9 |

## Artifact Index

| artifact | path | present |
| --- | --- | --- |
| canonical_repo_note | CANONICAL_REPO.md | yes |
| environment_spec | ENV_SPEC.md | yes |
| post_027_continuation_state | results/continuation_state/post_027.json | yes |
| item_028_p0_housekeeping | results/experiment_items/item_028_p0_housekeeping.json | yes |
| item_029_p1_1a_g1_diagnosis | results/experiment_items/item_029_p1_1a_g1_diagnosis.json | yes |
| item_030_p2_w3_hook_capacity | results/experiment_items/item_030_p2_w3_hook_capacity.json | yes |
| log_item_contract_spec | specs/log_item_contract.md | yes |
| model_readiness | results/model_readiness/readiness.json | yes |
| qwen3_4b_instruct_download | results/model_download/qwen_download.json | yes |
| qwen3_4b_thinking_download | results/model_download/thinking/qwen_download.json | yes |
| qwen3_5_4b_download | results/model_download/qwen3_5_4b/qwen_download.json | yes |
| module1_capacity_perdepth | results/module1_capacity_perdepth_shards/results.json | yes |
| module1_k_direction_corrected | results/module1_capacity_benchmark_full_shards/k_direction_corrected.json | yes |
| module1_capacity_batching | results/module1_capacity_batching_large/results.json | yes |
| gru_stack_smoke | results/gru_stack_smoke/results.json | yes |
| gru_stack_grid_full_legacy | results/gru_stack_grid_full/results.json | yes |
| gru_degeneracy_diagnostic | results/gru_degeneracy_diagnostic/results.json | yes |
| gru_stack_grid_fair | results/gru_stack_grid_fair/results.json | yes |
| gru_vs_structured_closeout | results/gru_vs_structured_closeout/results.json | yes |
| m2_operator_probe | results/m2_operator_probe/report.json | yes |
| m2_operator_fix_rescale | results/m2_operator_probe/report_fix_rescale.json | yes |
| g1_fix_spec | specs/g1_fix_spec.md | yes |
| stage_a_reconstructed_artifacts | artifacts/stage_a/manifest.json | yes |
| stage_a_backtrack | results/stage_a_backtrack/report.json | yes |
| post025_adapter_wiring | results/stage_a_adapter_wiring/results.json | yes |
| post026_banded_gate_refusal | results/stage_a_banded_gate_refusal/results.json | yes |
| post027_sudoku6_bridge | results/stage_a_sudoku6_bridge/results.json | yes |
| w3_qwen35_probe_spec | specs/w3_qwen35_probe_spec.md | yes |
| w3_qwen35_probe | results/w3_qwen35_probe/results.json | yes |
| validation | results/validation/validation.json | yes |

## Validation Summary

| tier | pass | fail |
| --- | --- | --- |
| contract | 43 | 0 |
| env | 13 | 0 |
| legacy | 0 | 6 |
| p0 | 2 | 0 |
| tier_a | 35 | 0 |
| tier_b | 17 | 3 |
| tier_c | 7 | 0 |

## P0/P1/P2/P3 Execution Notes

- P0.1: `RECURRENT_NN` is declared canonical in `CANONICAL_REPO.md`; the old `stage_d_llm` path is not present locally.
- P0.2: validation now emits many checks, including explicit red Stage A blockers, rather than one collapsed required-files failure.
- P0.3: the front page now leads with evidence tiers and current blockers; constructed scaffold gates are demoted to the legacy archive.
- P1: `specs/g1_fix_spec.md` plus adapter wiring, gate refusal, and Sudoku6 bridge diagnostic artifacts are present; the actual bridge retrain is not launched and G1 remains 0.0.
- P2: `specs/w3_qwen35_probe_spec.md` and metadata-only W3 probe are present for `Qwen/Qwen3.5-4B`; hidden-hook and heavy propagation probes are still explicit follow-up jobs.
- P3: TRM defensive analysis is not launched; no TRM checkpoint/test-set grading code is present in this repo yet.

## Legacy Scaffold Archive

The older 2x2, D-stage, verifier, and scaffold TTT entries are no longer front-page gate evidence. They were constructed scaffold outputs and are retained only as historical support/provenance. The real TTT irreversibility diagnostic remains Tier A mechanism evidence when its non-scaffold artifact is present.

| legacy artifact | path | present |
| --- | --- | --- |
| preregistration | results/preregistration/preregistration.json | missing |
| oracle_dataset | results/oracle_dataset/summary.json | missing |
| operator_cache | results/operator_cache/summary.json | missing |
| qwen_probe_cache | results/operator_cache/qwen_probe_cache_summary.json | missing |
| qwen_128_cache | results/operator_cache/qwen_128_cache_summary.json | missing |
| learned_wiring_qwen_128 | results/learned_wiring_qwen_128/results.json | missing |
| qwen_balanced_320_cache | results/operator_cache/qwen_balanced_320_cache_summary.json | missing |
| learned_wiring_qwen_balanced_320 | results/learned_wiring_qwen_balanced_320/results.json | missing |
| two_by_two | results/two_by_two/results.json | missing |
| d_stage_0 | results/d_stage_0/results.json | missing |
| d_stage_1 | results/d_stage_1/results.json | missing |
| d_stage_2 | results/d_stage_2/results.json | missing |
| d_stage_3 | results/d_stage_3/results.json | missing |
| verifier | results/verifier/results.json | missing |
| ttt_scaffold | results/ttt/results.json | missing |

## Standing Rules

- Fail-closed preflight.
- Autonomous solve only.
- No gate softening.
- Curriculum is training-only.
- Use TRM recipe only; never load a TRM checkpoint into controlled comparisons.
- kv_snapshot must be a true snapshot-and-truncate control.
- Per-task verdicts required.
- No ordering-only passes.
