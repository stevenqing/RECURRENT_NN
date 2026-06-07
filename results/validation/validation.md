# RECURRENT_NN Validation Report

Generated at: 2026-06-07T11:04:06.061689+00:00

Summary: 149 PASS / 0 FAIL / 149 total.

All registered checks pass.

## Checks

| tier | check | status | detail |
| --- | --- | --- | --- |
| p0 | canonical_repo_is_recurrent_nn | PASS | repo_root=/home/aiscuser/RECURRENT_NN |
| p0 | old_stage_d_llm_not_present | PASS | exists=False |
| env | model_readiness_present | PASS | results/model_readiness/readiness.json |
| env | env_transformers_available | PASS | value=True |
| env | env_cuda_available | PASS | count=8 |
| env | env_cuda_device_count_nonzero | PASS | count=8 |
| env | qwen3_instruct_present | PASS | results/model_download/qwen_download.json |
| env | qwen3_instruct_model_id | PASS | model_id=Qwen/Qwen3-4B-Instruct-2507 |
| env | qwen3_instruct_download_size | PASS | total_gib=7.507314503192902 |
| env | qwen3_thinking_present | PASS | results/model_download/thinking/qwen_download.json |
| env | qwen3_thinking_model_id | PASS | model_id=Qwen/Qwen3-4B-Thinking-2507 |
| env | qwen3_thinking_download_size | PASS | total_gib=7.507317625917494 |
| env | qwen35_4b_present | PASS | results/model_download/qwen3_5_4b/qwen_download.json |
| env | qwen35_4b_model_id | PASS | model_id=Qwen/Qwen3.5-4B |
| env | qwen35_4b_download_size | PASS | total_gib=8.701260638423264 |
| tier_a | module1_perdepth_present | PASS | results/module1_capacity_perdepth_shards/results.json |
| tier_a | module1_perdepth_sharded | PASS | device=8x_cuda_sharded |
| tier_a | module1_perdepth_num_shards | PASS | num_shards=8 |
| tier_a | module1_k_direction_negative | PASS | decision=k_direction_negative, open=False |
| tier_a | module1_all_k_signs_nonincreasing | PASS | joint/var/val signs are <= 0 |
| tier_a | module1_bound_single_keff_product | PASS | best=D_over_ln_product |
| tier_a | module1_bound_single_product_r2 | PASS | r2=0.9887660263260115 |
| tier_a | module1_factored_keff_kvar | PASS | best=D_over_ln_Kvar |
| tier_a | module1_factored_kvar_r2 | PASS | r2=0.9775493597694338 |
| tier_a | module1_k_corrected_present | PASS | results/module1_capacity_benchmark_full_shards/k_direction_corrected.json |
| tier_a | module1_ceiling_artifact_corrected | PASS | passed=True |
| tier_a | module1_batching_present | PASS | results/module1_capacity_batching_large/results.json |
| tier_a | module1_batching_large_recorded | PASS | best_batches=[8192, 8192, 8192, 16384] |
| tier_a | gru_smoke_present | PASS | results/gru_stack_smoke/results.json |
| tier_a | gru_light_present | PASS | results/gru_stack_grid_full/results.json |
| tier_a | gru_degeneracy_present | PASS | results/gru_degeneracy_diagnostic/results.json |
| tier_a | gru_fair_present | PASS | results/gru_stack_grid_fair/results.json |
| tier_a | gru_closeout_present | PASS | results/gru_vs_structured_closeout/results.json |
| tier_a | gru_smoke_converged | PASS | frontier=0.0 |
| tier_a | gru_fair_144_cells | PASS | n_cells=144 |
| tier_a | gru_fair_all_converged | PASS | all_converged=True |
| tier_a | gru_fair_training_sufficient | PASS | training=True |
| tier_a | gru_fair_below_structured | PASS | below=True |
| tier_a | gru_closeout_not_ready_honest | PASS | classification=NOT_READY |
| tier_a | gru_headline_not_locked | PASS | lock=False |
| tier_a | gru_max_ratio_below_one | PASS | ratio=0.9025382093725324 |
| tier_a | m2_probe_present | PASS | results/m2_operator_probe/report.json |
| tier_a | m2_fix_rescale_present | PASS | results/m2_operator_probe/report_fix_rescale.json |
| tier_a | m2_probe_negative | PASS | verdict=NEEDS_OPERATOR_FIX |
| tier_a | m2_probe_forced_recall_low | PASS | forced_recall=0.1935483870967742 |
| tier_a | m2_fix_all_tasks_need_fix | PASS | verdicts={'general_sat': 'NEEDS_OPERATOR_FIX', 'graph_coloring': 'NEEDS_OPERATOR_FIX', 'horn_sat': 'NEEDS_OPERATOR_FIX', 'logic_grid': 'NEEDS_OPERATOR_FIX', 'sudoku_4x4': 'NEEDS_OPERATOR_FIX'} |
| tier_a | m2_fix_rescale_routes_all_to_fix | PASS | routing={'fix_tasks': ['general_sat', 'graph_coloring', 'horn_sat', 'logic_grid', 'sudoku_4x4'], 'pass_tasks': []} |
| tier_a | m2_qwen_guess_invalid_rate_high | PASS | invalid_guess_rate=0.23157415832575068 |
| tier_a | m2_mrv_invalid_rate_zero | PASS | invalid_guess_rate=0.0 |
| tier_a | m2_iterated_and_list_all_recorded | PASS | overall_keys=['branch', 'list_all', 'single_iterated'] |
| tier_b | stage_a_manifest_present | PASS | artifacts/stage_a/manifest.json |
| tier_b | stage_a_results_present | PASS | results/stage_a_backtrack/results.json |
| tier_b | stage_a_report_present | PASS | results/stage_a_backtrack/report.json |
| tier_b | continuation_post_027_present | PASS | results/continuation_state/post_027.json |
| tier_b | stage_a_reconstructed_artifacts_ready | PASS | status=READY |
| tier_b | stage_a_provenance_recorded | PASS | policy=reconstructed_in_repo_not_inherited |
| tier_b | stage_a_preflight_passed | PASS | preflight_failed=False |
| tier_b | stage_a_parent_adapter_blocker_present | PASS | statuses=['PARENT_ADAPTER_REQUIRED'] |
| tier_b | stage_a_no_autonomous_cells_yet | PASS | n_cells=0 |
| tier_b | stage_a_report_needs_review | PASS | verdict=NEEDS_REVIEW |
| tier_b | stage_a_sudoku6_g1_zero_recorded | PASS | g1=0.0 |
| tier_b | g1_fix_spec_present | PASS | specs/g1_fix_spec.md |
| tier_b | post025_adapter_wiring_present | PASS | results/stage_a_adapter_wiring/results.json |
| tier_b | post026_banded_gate_refusal_present | PASS | results/stage_a_banded_gate_refusal/results.json |
| tier_b | post027_sudoku6_bridge_present | PASS | results/stage_a_sudoku6_bridge/results.json |
| tier_b | post025_adapter_wiring_pass | PASS | status=PASS |
| tier_b | post026_gate_refusal_pass | PASS | status=PASS; cases=3 |
| tier_b | stage_a_sudoku6_g1_pass | PASS | expected to fail until P1 fixes bridge G1 |
| tier_b | stage_a_reverts_nonzero_on_L4 | PASS | expected restored registry check |
| tier_b | stage_a_forward_floor_on_L4 | PASS | expected restored registry check |
| tier_c | w3_qwen35_probe_spec_present | PASS | specs/w3_qwen35_probe_spec.md |
| tier_c | w3_qwen35_probe_present | PASS | results/w3_qwen35_probe/results.json |
| tier_c | w3_qwen35_model_id | PASS | model_id=Qwen/Qwen3.5-4B |
| tier_c | w3_checkpoint_pin_pass | PASS | verdict=PASS |
| tier_c | w3_integration_grade_not_overclaimed | PASS | integration_grade=alongside_only_measured_not_in_state |
| tier_c | w3_hidden_hook_dim_matches_config | PASS | hidden_dim=2560; config=2560 |
| tier_c | w3_state_hook_perturbable | PASS | round_trip={'note': 'This verifies hidden-state tensor access and perturbability, not a full cached-state generation intervention.', 'perturbation_affected_next_step': True, 'perturbation_injected': True, 'perturbation_norm': 0.05059561878442764} |
| tier_c | w3_survival_curve_measured | PASS | rows=15 |
| tier_c | w3_native_delta_gap_measured | PASS | rows=3 |
| tier_c | w3_propagation_per_task_delta_measured | PASS | rows=5 |
| contract | log_item_contract_spec_present | PASS | specs/log_item_contract.md |
| contract | log_item_artifacts_present | PASS | count=5 |
| contract | log_item_028_required_fields | PASS | missing=[] |
| contract | log_item_028_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_028_number_continues_from_028 | PASS | item_number=028 |
| contract | log_item_028_artifacts_exist | PASS | missing=[] |
| contract | log_item_028_honesty_does_not_establish | PASS | this item does NOT establish that the Stage A bridge solves autonomously, that G1 passes, that L4 separation is restored, or that Qwen3.5 integration is viable. |
| contract | log_item_028_decision_numbers_and_routing | PASS | gates=4; routing=P1.1a Task A diagnosis and P2 W3 hidden-hook/probe work remain next; P1/P2 should produce items 029+ using this contract. |
| contract | log_item_029_required_fields | PASS | missing=[] |
| contract | log_item_029_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_029_number_continues_from_028 | PASS | item_number=029 |
| contract | log_item_029_artifacts_exist | PASS | missing=[] |
| contract | log_item_029_honesty_does_not_establish | PASS | this item does NOT establish that the bridge objective is correct, that G1 can be fixed by longer training, or that any autonomous Sudoku6 solve works. |
| contract | log_item_029_decision_numbers_and_routing | PASS | gates=3; routing=Implement Sudoku6 dataset/encoding artifacts and parent adapter wiring before P1.1b retrain; route to objective_wiring rather than budget-only. |
| contract | log_item_030_required_fields | PASS | missing=[] |
| contract | log_item_030_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_030_number_continues_from_028 | PASS | item_number=030 |
| contract | log_item_030_artifacts_exist | PASS | missing=[] |
| contract | log_item_030_honesty_does_not_establish | PASS | this item does NOT establish that Qwen3.5 has stable in-state stack memory, that native hidden deltas implement keyed register operations, or that propagation i |
| contract | log_item_030_decision_numbers_and_routing | PASS | gates=5; routing=Continue P2 with decay survival, native-delta gap, and W3.2 propagation delta probes; current grade is alongside_candidate_pending_survival_and_delta_probes, not accepted P2 completion. |
| contract | log_item_031_required_fields | PASS | missing=[] |
| contract | log_item_031_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_031_number_continues_from_028 | PASS | item_number=031 |
| contract | log_item_031_artifacts_exist | PASS | missing=[] |
| contract | log_item_031_honesty_does_not_establish | PASS | This item does not establish stable cached recurrent stack memory in Qwen3.5, does not establish native hidden deltas as keyed register push/pop, does not show  |
| contract | log_item_031_decision_numbers_and_routing | PASS | gates=4; routing=Treat Qwen3.5 as alongside-only measured evidence, not in-state integration. If P2 continues, scale propagation or design a true cached-state intervention; do not integrate Qwen3.5 into the structured state path from this item. |
| contract | log_item_032_required_fields | PASS | missing=[] |
| contract | log_item_032_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_032_number_continues_from_028 | PASS | item_number=032 |
| contract | log_item_032_artifacts_exist | PASS | missing=[] |
| contract | log_item_032_honesty_does_not_establish | PASS | This item does not establish the full learned recurrent Stage A autonomous grid, does not run G2, and does not turn scaffold legacy artifacts into front-page pr |
| contract | log_item_032_decision_numbers_and_routing | PASS | gates=4; routing=Proceed to learned recurrent Stage A bridge/autonomous grid work; validation is green, but the core claim still needs full autonomous Stage A evidence. |
| contract | item_028_p0_housekeeping_present | PASS | results/experiment_items/item_028_p0_housekeeping.json |
| contract | item_028_validation_registry_before_after_present | PASS | rows=2 |
| contract | item_028_ledger_reconciliation_present | PASS | rows=6 |
| contract | item_028_report_front_page_present | PASS | rows=3 |
| contract | item_028_validation_registry_many_checks | PASS | after={'phase': 'after_restored_registry', 'total_check_count': 149, 'passed': 149, 'failed': 0, 'provenance': 'measured:results/validation/validation.json::summary'} |
| contract | item_028_items_025_027_folded | PASS | requirements={'canonical_repo_declared': 'yes', 'stop_generating_from_stage_d_llm': 'yes', 'item_025_folded': 'yes', 'item_026_folded': 'yes', 'item_027_folded': 'yes', 'module1_artifacts_deduplicated': 'yes'} |
| contract | item_029_p1_1a_g1_diagnosis_present | PASS | results/experiment_items/item_029_p1_1a_g1_diagnosis.json |
| contract | item_029_training_curve_summary_present | PASS | rows=1 |
| contract | item_029_single_step_forced_precision_recall_by_depth_present | PASS | rows=2 |
| contract | item_029_iterative_stick_reason_histogram_present | PASS | rows=6 |
| contract | item_029_train_vs_eval_encoding_byte_diff_present | PASS | rows=1 |
| contract | item_029_decision_branch_present | PASS | rows=1 |
| contract | item_029_decision_branch_valid | PASS | branch=objective_wiring |
| contract | item_030_p2_w3_hook_capacity_present | PASS | results/experiment_items/item_030_p2_w3_hook_capacity.json |
| contract | item_030_model_card_present | PASS | keys=['source', 'columns', 'rows'] |
| contract | item_030_state_hook_round_trip_present | PASS | keys=['columns', 'rows'] |
| contract | item_030_capacity_at_real_gdn_dims_present | PASS | keys=['source', 'columns', 'rows'] |
| contract | item_030_decay_survival_present | PASS | keys=['columns', 'rows', 'status'] |
| contract | item_030_native_rule_gap_present | PASS | keys=['columns', 'rows', 'status'] |
| contract | item_030_propagation_per_task_delta_present | PASS | keys=['columns', 'rows', 'status'] |
| contract | item_030_verdicts_echo_present | PASS | keys=['state_hookable', 'd_star_at_state_dims', 'survival_design', 'native_rule_gap_confirmed', 'propagation_tasks_ok', 'source'] |
| contract | item_030_state_hook_round_trip_positive | PASS | affected=True |
| contract | item_030_marked_partial_not_complete | PASS | status=PARTIAL_NOT_ACCEPTED |
| contract | item_031_p2_w3_survival_delta_propagation_present | PASS | results/experiment_items/item_031_p2_w3_survival_delta_propagation.json |
| contract | item_031_decay_survival_present | PASS | rows=15 |
| contract | item_031_native_rule_gap_present | PASS | rows=3 |
| contract | item_031_propagation_per_task_delta_present | PASS | rows=5 |
| contract | item_031_decision_summary_present | PASS | rows=4 |
| contract | item_031_no_in_state_overclaim | PASS | integration_grade=alongside_only_measured_not_in_state |
| contract | item_031_marked_measured_not_accepted | PASS | status=MEASURED_NOT_ACCEPTED |
| legacy | ttt_legacy_present | PASS | results/ttt/results.json |
| legacy | legacy_two_by_two_present | PASS | results/two_by_two/results.json |
| legacy | legacy_d_stage_1_present | PASS | results/d_stage_1/results.json |
| legacy | legacy_d_stage_2_present | PASS | results/d_stage_2/results.json |
| legacy | legacy_d_stage_3_present | PASS | results/d_stage_3/results.json |
| legacy | legacy_verifier_present | PASS | results/verifier/results.json |
| legacy | ttt_irreversibility_real | PASS | ttt=0.1013166606426239, structured=3.0798228181083687e-06 |
