# RECURRENT_NN Validation Report

Generated at: 2026-06-07T10:03:49.107590+00:00

Summary: 72 PASS / 9 FAIL / 81 total.

The current expected state is not all-green: Stage A post-027 blockers should be visible as explicit red checks, not hidden behind a single required-files failure.

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
| tier_b | stage_a_sudoku6_g1_pass | FAIL | expected to fail until P1 fixes bridge G1 |
| tier_b | stage_a_reverts_nonzero_on_L4 | FAIL | expected restored registry check |
| tier_b | stage_a_forward_floor_on_L4 | FAIL | expected restored registry check |
| tier_c | w3_qwen35_probe_spec_present | PASS | specs/w3_qwen35_probe_spec.md |
| tier_c | w3_qwen35_probe_present | PASS | results/w3_qwen35_probe/results.json |
| tier_c | w3_qwen35_model_id | PASS | model_id=Qwen/Qwen3.5-4B |
| tier_c | w3_checkpoint_pin_pass | PASS | verdict=PASS |
| tier_c | w3_metadata_only_not_overclaimed | PASS | integration_grade=do_not_integrate_yet |
| legacy | ttt_legacy_present | FAIL | results/ttt/results.json |
| legacy | legacy_two_by_two_present | FAIL | results/two_by_two/results.json |
| legacy | legacy_d_stage_1_present | FAIL | results/d_stage_1/results.json |
| legacy | legacy_d_stage_2_present | FAIL | results/d_stage_2/results.json |
| legacy | legacy_d_stage_3_present | FAIL | results/d_stage_3/results.json |
| legacy | legacy_verifier_present | FAIL | results/verifier/results.json |
