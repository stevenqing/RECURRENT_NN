# RECURRENT_NN Validation Report

Generated at: 2026-06-09T02:39:36.842883+00:00

Summary: 268 PASS / 3 FAIL / 271 total.

The current expected state is not all-green: explicit red checks mark remaining blockers rather than hiding them behind a collapsed required-files failure.

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
| tier_b | stage_a_symbolic_results_present | PASS | results/stage_a_symbolic/results.json |
| tier_b | stage_a_symbolic_report_present | PASS | results/stage_a_symbolic/report.json |
| tier_b | stage_a_symbolic_statelessness_present | PASS | results/stage_a_symbolic/oracle_statelessness_ci.json |
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
| tier_b | stage_a_g1_pass | FAIL | operator_type=symbolic_baseline; G1=1.0; required_operator_type=learned_recurrent; required_G1>=0.95 |
| tier_b | stage_a_symbolic_control_pass | PASS | operator_type=symbolic_baseline; G1=1.0 |
| tier_b | stage_a_reverts_nonzero_on_L4 | FAIL | source=fixture; run_id=deterministic_l4_fixture; real_grid_cells=0; required_source=autonomous_stage_a_run |
| tier_b | stage_a_forward_floor_on_L4 | FAIL | source=fixture; run_id=deterministic_l4_fixture; real_grid_cells=0; required_source=autonomous_stage_a_run |
| tier_b | stage_a_l4_harness_fixture_pass | PASS | source=fixture; reverts=True; forward=True |
| tier_b | stage_a_symbolic_oracle_stateless_ci | PASS | status=PASS; byte_identical=True |
| tier_b | stage_a_track_labels_symbolic | PASS | top_track=A_symbolic; top_operator=symbolic_oracle; labeled_cells=43 |
| tier_b | stage_a_autonomous_cells_symbolic | PASS | track=A_symbolic; operator=symbolic_oracle; autonomous_cells=43 |
| tier_b | stage_a_symbolic_reverts_nonzero_on_L4 | PASS | track=A_symbolic; source=autonomous_stage_a_run; reverts=True; autonomous_cells=43 |
| tier_b | stage_a_symbolic_forward_floor_on_L4 | PASS | track=A_symbolic; source=autonomous_stage_a_run; forward_floor=True; kv_depth=3; no_revert_depth=3 |
| meta | all_green_requires_core_evidence | PASS | learned_autonomous_cells=0; symbolic_autonomous_cells=43; declared_track_core_cells=43 |
| tier_c | w3_qwen35_probe_spec_present | PASS | specs/w3_qwen35_probe_spec.md |
| tier_c | w3_qwen35_probe_present | PASS | results/w3_qwen35_probe/results.json |
| tier_c | w3_qwen35_model_id | PASS | model_id=Qwen/Qwen3.5-4B |
| tier_c | w3_checkpoint_pin_pass | PASS | verdict=PASS |
| tier_c | w3_measured_object_cached_gdn_state | PASS | measured_object=cached_gdn_recurrent_state; reason=missing_or_unrecognized_measured_object |
| tier_c | w3_integration_grade_reissued_on_true_state | PASS | integration_grade=cached_gdn_state_measured_with_propagation_delta; measured_object=cached_gdn_recurrent_state |
| tier_c | w3_capacity_true_state_dims_measured | PASS | verdict=MEASURED_TRUE_STATE_MATRIX_GEOMETRY; measured_rows=8; families=['sudoku_6x6', 'sudoku_9x9']; measured_object=cached_gdn_recurrent_state |
| tier_c | w3_cached_state_round_trip | PASS | round_trip={'note': 'This verifies hidden-state tensor access and perturbability, not a full cached-state generation intervention.', 'perturbation_affected_next_step': True, 'perturbation_injected': True, 'perturbation_norm': 0.05059561878442764}; measured_object=cached_gdn_recurrent_state |
| tier_c | w3_cached_state_survival_measured | PASS | verdict=MEASURED_CACHED_GDN_RECURRENT_STATE_SURVIVAL; rows=5; measured_object=cached_gdn_recurrent_state |
| tier_c | w3_cached_state_native_rule_gap_measured | PASS | verdict=MEASURED_CACHED_GDN_NATIVE_RULE_GAP; rows=3; measured_object=cached_gdn_recurrent_state |
| tier_c | w3_propagation_scale_not_mixed | PASS | verdict=MEASURED_50X2_PROPAGATION_DELTA_NOT_ACCEPTED |
| tier_c | w3_propagation_per_task_delta_measured | PASS | rows=5 |
| contract | log_item_contract_spec_present | PASS | specs/log_item_contract.md |
| contract | log_item_artifacts_present | PASS | count=21 |
| contract | log_item_028_required_fields | PASS | missing=[] |
| contract | log_item_028_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_028_number_continues_from_028 | PASS | item_number=028 |
| contract | log_item_028_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_028_honesty_does_not_establish | PASS | this item does NOT establish that the Stage A bridge solves autonomously, that G1 passes, that L4 separation is restored, or that Qwen3.5 integration is viable. |
| contract | log_item_028_decision_numbers_and_routing | PASS | gates=4; routing=P1.1a Task A diagnosis and P2 W3 hidden-hook/probe work remain next; P1/P2 should produce items 029+ using this contract. |
| contract | log_item_029_required_fields | PASS | missing=[] |
| contract | log_item_029_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_029_number_continues_from_028 | PASS | item_number=029 |
| contract | log_item_029_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_029_honesty_does_not_establish | PASS | this item does NOT establish that the bridge objective is correct, that G1 can be fixed by longer training, or that any autonomous Sudoku6 solve works. |
| contract | log_item_029_decision_numbers_and_routing | PASS | gates=3; routing=Implement Sudoku6 dataset/encoding artifacts and parent adapter wiring before P1.1b retrain; route to objective_wiring rather than budget-only. |
| contract | log_item_030_required_fields | PASS | missing=[] |
| contract | log_item_030_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_030_number_continues_from_028 | PASS | item_number=030 |
| contract | log_item_030_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_030_honesty_does_not_establish | PASS | this item does NOT establish that Qwen3.5 has stable in-state stack memory, that native hidden deltas implement keyed register operations, or that propagation i |
| contract | log_item_030_decision_numbers_and_routing | PASS | gates=5; routing=Continue P2 with decay survival, native-delta gap, and W3.2 propagation delta probes; current grade is alongside_candidate_pending_survival_and_delta_probes, not accepted P2 completion. |
| contract | log_item_031_required_fields | PASS | missing=[] |
| contract | log_item_031_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_031_number_continues_from_028 | PASS | item_number=031 |
| contract | log_item_031_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_031_honesty_does_not_establish | PASS | This item does not establish stable cached recurrent stack memory in Qwen3.5, does not establish native hidden deltas as keyed register push/pop, does not show  |
| contract | log_item_031_decision_numbers_and_routing | PASS | gates=4; routing=Treat Qwen3.5 as alongside-only measured evidence, not in-state integration. If P2 continues, scale propagation or design a true cached-state intervention; do not integrate Qwen3.5 into the structured state path from this item. |
| contract | log_item_032_required_fields | PASS | missing=[] |
| contract | log_item_032_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_032_number_continues_from_028 | PASS | item_number=032 |
| contract | log_item_032_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=['results/two_by_two/results.json', 'results/d_stage_1/results.json', 'results/d_stage_2/results.json', 'results/d_stage_3/results.json', 'results/verifier/results.json'] |
| contract | log_item_032_honesty_does_not_establish | PASS | This item does not establish the full learned recurrent Stage A autonomous grid, does not run G2, and does not turn scaffold legacy artifacts into front-page pr |
| contract | log_item_032_decision_numbers_and_routing | PASS | gates=4; routing=Proceed to learned recurrent Stage A bridge/autonomous grid work; validation is green, but the core claim still needs full autonomous Stage A evidence. |
| contract | log_item_033_required_fields | PASS | missing=[] |
| contract | log_item_033_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_033_number_continues_from_028 | PASS | item_number=033 |
| contract | log_item_033_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_033_honesty_does_not_establish | PASS | This corrective item does not train the learned recurrent operator, does not produce autonomous Stage A cells, and does not redo W3 on cached GDN recurrent stat |
| contract | log_item_033_decision_numbers_and_routing | PASS | gates=3; routing=Proceed to T2 learned recurrent operator/data/trainer and T3 cached GDN recurrent-state probe; do not treat validation red as environment failure. |
| contract | log_item_034_required_fields | PASS | missing=[] |
| contract | log_item_034_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_034_number_continues_from_028 | PASS | item_number=034 |
| contract | log_item_034_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_034_honesty_does_not_establish | PASS | The T2 smoke checkpoint, the formal single-GPU checkpoint, and the accelerated 8-GPU checkpoint do not meet G1>=0.95 and do not produce autonomous Stage A cells |
| contract | log_item_034_decision_numbers_and_routing | PASS | gates=7; routing=T2 should shift from simply adding steps/GPUs to correcting the learned target/interface or architecture, because the accelerated 8-GPU run still plateaus far below G1>=0.95. Broaden W3.2 propagation beyond the small n=1/task shard before final integration claims. |
| contract | log_item_035_required_fields | PASS | missing=[] |
| contract | log_item_035_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_035_number_continues_from_028 | PASS | item_number=035 |
| contract | log_item_035_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_035_honesty_does_not_establish | PASS | T2 forced-only semantics eliminate the unforced-guess G1≈G2 anomaly but do not establish G1>=0.95, autonomous Stage A cells, or useful learned propagation; all  |
| contract | log_item_035_decision_numbers_and_routing | PASS | gates=4; routing=Do not scale T2 budget until forced-mask recall is repaired. After this partial-evidence commit, finish all remaining W3.2 50x2 shards, merge only when every shard has n_instances>=50 and at least two seeds, rerun validation/log generation, then make a final W3.2 completion commit. |
| contract | log_item_036_required_fields | PASS | missing=[] |
| contract | log_item_036_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_036_number_continues_from_028 | PASS | item_number=036 |
| contract | log_item_036_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_036_honesty_does_not_establish | PASS | The overnight T2 runs improve forced-mask recall from the zero-recall smoke but do not meet G1>=0.95, do not unlock Stage A, and do not produce autonomous Stage |
| contract | log_item_036_decision_numbers_and_routing | PASS | gates=6; routing=Do not launch Stage A from this T2 checkpoint. Route T2 to forced-mask target/interface repair using the nonzero recall but low G1 evidence. Log W3.2 as complete 50x2 NOT_ACCEPTED and keep Qwen3.5 alongside-only unless a true structured cached-state push/pop decoder is implemented. |
| contract | log_item_037_required_fields | PASS | missing=[] |
| contract | log_item_037_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_037_number_continues_from_028 | PASS | item_number=037 |
| contract | log_item_037_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_037_honesty_does_not_establish | PASS | This item establishes Track A wiring, stateless oracle CI, labels, validation split, and a 6x6 chain-validation artifact with autonomous symbolic cells. It does |
| contract | log_item_037_decision_numbers_and_routing | PASS | gates=5; routing=Launch the real Track A 9x9/deepened L4 grid with this runner after D3 bins land; keep learned-track reds visible; implement Track B per-cell-token TRM-class operator in parallel; keep D1/D2/D3 quarantines until their artifacts exist. |
| contract | log_item_038_required_fields | PASS | missing=[] |
| contract | log_item_038_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_038_number_continues_from_028 | PASS | item_number=038 |
| contract | log_item_038_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_038_honesty_does_not_establish | PASS | This item establishes a faster fail-closed Track A execution path and measured symbolic-oracle L4 revert/floor evidence on sudoku6 depth histogram {'1':3,'2':2, |
| contract | log_item_038_decision_numbers_and_routing | PASS | gates=5; routing=Use CPU parallel budgeted Track A for remaining symbolic shards; reserve GPUs for Track B learned/TRM-class operator and D1. Next, implement Track B or the D1/D2/D3 debts without promoting symbolic Track A rows into learned-track evidence. |
| contract | log_item_039_required_fields | PASS | missing=[] |
| contract | log_item_039_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_039_number_continues_from_028 | PASS | item_number=039 |
| contract | log_item_039_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_039_honesty_does_not_establish | PASS | This item establishes the Track B code path and one tiny GPU smoke artifact only. It does not establish Track B acceptance, does not pass the leading-indicator  |
| contract | log_item_039_decision_numbers_and_routing | PASS | gates=4; routing=When GPUs are free, run seeds 102/137/256 with the default or scaled Track B config on separate GPUs and log acceptance per seed. Keep Track B learned rows side by side with Track A only after learned_recurrent gates pass and an autonomous Stage A learned run exists. |
| contract | log_item_040_required_fields | PASS | missing=[] |
| contract | log_item_040_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_040_number_continues_from_028 | PASS | item_number=040 |
| contract | log_item_040_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_040_honesty_does_not_establish | PASS | This item does not establish Track B learned acceptance, does not establish autonomous learned Stage A cells, does not establish L4 solve transfer, and does not |
| contract | log_item_040_decision_numbers_and_routing | PASS | gates=5; routing=Treat this Track B recipe as a clean negative result. Do not route learned_recurrent into Stage A or mark learned gates green. Future Track B work should change the objective/curriculum or recurrent control path rather than merely extending this L1-L2 forced-step run, because 20k steps left G2 at 0.0 and G1 far below threshold. |
| contract | log_item_041_required_fields | PASS | missing=[] |
| contract | log_item_041_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_041_number_continues_from_028 | PASS | item_number=041 |
| contract | log_item_041_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_041_honesty_does_not_establish | PASS | This item does not claim a speedup, does not establish learned Track B gate success, and does not change experimental semantics. It records a before-optimizatio |
| contract | log_item_041_decision_numbers_and_routing | PASS | gates=4; routing=Proceed to GPU pipeline optimization only behind the recorded equivalence guard. The next implementation should wire GPU-resident/batched Sudoku operations into data preparation or rollout evaluation, then report before/after against this P0 baseline without changing Track B semantics. |
| contract | log_item_042_required_fields | PASS | missing=[] |
| contract | log_item_042_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_042_number_continues_from_028 | PASS | item_number=042 |
| contract | log_item_042_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_042_honesty_does_not_establish | PASS | This item does not claim a speedup, does not change Track B training, and does not establish learned gate success. It only establishes that the register-level b |
| contract | log_item_042_decision_numbers_and_routing | PASS | gates=2; routing=Use register.batched_ops as the guarded integration layer for the next GPU pipeline optimization. The next code change should wire batched operations into the trainer data preparation or rollout path and compare timing against item041 P0. |
| contract | log_item_043_required_fields | PASS | missing=[] |
| contract | log_item_043_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_043_number_continues_from_028 | PASS | item_number=043 |
| contract | log_item_043_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_043_honesty_does_not_establish | PASS | This item does not run training, does not claim speedup, and does not establish learned Track B acceptance. It only records the next faithful retry plan and the |
| contract | log_item_043_decision_numbers_and_routing | PASS | gates=3; routing=Implement the prelaunch trainer gates, rerun equivalence checks, then launch one seed per GPU and report before/after throughput against item041 plus per-seed learned metrics as in item040. |
| contract | log_item_044_required_fields | PASS | missing=[] |
| contract | log_item_044_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_044_number_continues_from_028 | PASS | item_number=044 |
| contract | log_item_044_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_044_honesty_does_not_establish | PASS | This item does not establish a speedup, does not run the full retry, and does not establish learned Track B acceptance. It only validates that the trainer now s |
| contract | log_item_044_decision_numbers_and_routing | PASS | gates=2; routing=Launch the item043 one-GPU-per-seed retry when ready, using the selected 6.91M-parameter shape and the new prelaunch flags, then compare throughput against item041 and report learned metrics as in item040. |
| contract | log_item_045_required_fields | PASS | missing=[] |
| contract | log_item_045_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_045_number_continues_from_028 | PASS | item_number=045 |
| contract | log_item_045_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_045_honesty_does_not_establish | PASS | This item does not establish final learned Track B acceptance. The seed102 DDP run is still active, and G1/G2 rollout metrics are intentionally null in progress |
| contract | log_item_045_decision_numbers_and_routing | PASS | gates=2; routing=Continue monitoring the active seed102 DDP run until completion, then record final acceptance.json and compare final learned G1/G2 against item040 and item043 expectations. |
| contract | log_item_046_required_fields | PASS | missing=[] |
| contract | log_item_046_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_046_number_continues_from_028 | PASS | item_number=046 |
| contract | log_item_046_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_046_honesty_does_not_establish | PASS | This item does not establish learned Track B success, Stage A autonomous learned evidence, or Qwen integration. It establishes a completed negative seed102 DDP  |
| contract | log_item_046_decision_numbers_and_routing | PASS | gates=3; routing=Do not continue this supervised-imitation recipe as-is. Use the checkpoint and failure evidence to design a DAgger/RL-style rollout-refinement run with periodic checkpoints and mid-run acceptance probes. |
| contract | log_item_047_required_fields | PASS | missing=[] |
| contract | log_item_047_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_047_number_continues_from_028 | PASS | item_number=047 |
| contract | log_item_047_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_047_honesty_does_not_establish | PASS | This preregistration alone establishes no observed separation; the observed tables must be written later under the same item/run root. If a required engine or a |
| contract | log_item_047_decision_numbers_and_routing | PASS | gates=1; routing=Inspect Line 1 R3+ table, Line 2 close/fix decision, Line 3 Grade 2 verdict, and D3 frontier audit. |
| contract | log_item_048_required_fields | PASS | missing=[] |
| contract | log_item_048_schema_version | PASS | schema=log_item_contract_v1 |
| contract | log_item_048_number_continues_from_028 | PASS | item_number=048 |
| contract | log_item_048_artifacts_exist | PASS | missing=[]; archived_or_absent_ok=[] |
| contract | log_item_048_honesty_does_not_establish | PASS | The closeout locks the causal structured-register headline with certified figure/spill accounting, resolves Track B as an off-critical-path mask-head learnabili |
| contract | log_item_048_decision_numbers_and_routing | PASS | gates=4; routing=Closeout acceptance gates are resolved; keep Track B out of the critical path and quote GRU only through the real in-loop rerun artifact. |
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
| closeout_047 | item_048_item047_headline_closeout_present | PASS | results/experiment_items/item_048_item047_headline_closeout.json |
| closeout_047 | closeout_047_status_present | PASS | results/closeout_047/status_corrections.json |
| closeout_047 | closeout_047_headline_figure_present | PASS | results/closeout_047/headline_figure/headline_figure_certification.json |
| closeout_047 | item047_rot_vs_no_revert_solid | PASS | label=SOLID |
| closeout_047 | item047_gru_in_loop_audit_pass | PASS | gru_label=GRU_IN_LOOP_R3PLUS_RERUN_AUDIT_PASS; quotable=True |
| closeout_047 | item047_track_b_split_diagnosis_resolved | PASS | track_b_label=MASK_HEAD_LOW_CLOSE_AS_OPERATOR_LEARNABILITY_FINDING_NO_DAGGER_RL |
| closeout_047 | item047_headline_figure_certified | PASS | headline_figure=HEADLINE_FIGURE_CERTIFIED |
| closeout_047 | item047_overlay_certified_with_footnote | PASS | status=HEADLINE_FIGURE_CERTIFIED_WITH_FACTORED_CODEBOOK_FOOTNOTE |
| closeout_047 | item047_spilloff_matches_dstar | PASS | value=True |
| closeout_047 | item047_spillon_overflow_accounted | PASS | value=True |
| closeout_047 | item047_track_b_not_old_close_label | PASS | status=MASK_HEAD_LOW_CLOSE_AS_OPERATOR_LEARNABILITY_FINDING_NO_DAGGER_RL |
| closeout_047 | item047_track_b_mask_full_train_eval_present | PASS | splits=['eval', 'train'] |
| closeout_047 | item047_gru_rows_real_bytes_curve_converged | PASS | rows=12; status=GRU_IN_LOOP_R3PLUS_RERUN_AUDIT_PASS |
| legacy | ttt_legacy_present | PASS | results/ttt/results.json |
| legacy | legacy_two_by_two_archived_or_absent_ok | PASS | state=absent_ok; path=results/two_by_two/results.json |
| legacy | legacy_d_stage_1_archived_or_absent_ok | PASS | state=absent_ok; path=results/d_stage_1/results.json |
| legacy | legacy_d_stage_2_archived_or_absent_ok | PASS | state=absent_ok; path=results/d_stage_2/results.json |
| legacy | legacy_d_stage_3_archived_or_absent_ok | PASS | state=absent_ok; path=results/d_stage_3/results.json |
| legacy | legacy_verifier_archived_or_absent_ok | PASS | state=absent_ok; path=results/verifier/results.json |
| legacy | ttt_irreversibility_real | PASS | ttt=0.1013166606426239, structured=3.0798228181083687e-06 |
