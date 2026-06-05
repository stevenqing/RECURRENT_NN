# Stage D Validation Report

Generated at: 2026-06-05T11:09:21.890223+00:00

## Checks

| check | status | detail |
| --- | --- | --- |
| required_files_present | PASS | missing=[] |
| oracle_dataset_line_count | PASS | jsonl=2456, summary=2456 |
| oracle_dataset_actions_valid | PASS | invalid={} |
| oracle_dataset_has_all_actions | PASS | counts={'propagate': 1392, 'done': 184, 'branch': 680, 'revert': 200} |
| oracle_dataset_supervision | PASS | supervision=symbolic_oracle_trace |
| operator_cache_example_count | PASS | cache=2456, dataset=2456 |
| operator_cache_file_exists | PASS | results/operator_cache/operator_cache.pt |
| model_readiness_recorded | PASS | transformers_available=True, cuda_available=True |
| uv_transformers_available | PASS | transformers available in uv environment |
| qwen_instruct_downloaded | PASS | path=/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554 |
| qwen_thinking_downloaded | PASS | path=/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea |
| qwen_probe_cache_valid | PASS | hidden_dim=2560, n_examples=8 |
| qwen_128_cache_valid | PASS | hidden_dim=2560, n_examples=128 |
| qwen_128_learned_wiring_recorded | PASS | action_accuracy=0.5703, verifier_accuracy=0.8359 |
| qwen_balanced_320_cache_valid | PASS | seed_counts={'42': 64, '137': 64, '256': 64, '314': 64, '999': 64} |
| qwen_balanced_320_holdout_action | PASS | holdout_action_accuracy=0.8906 |
| module1_quick_result_present | PASS | rows=84, summary=18 |
| module1_rotation_nonzero_frontier | PASS | frontiers=[3, 3, 15, 1, 4, 9] |
| module1_rotation_beats_gru_proxy | PASS | rotation frontier >= matched GRU proxy frontier |
| module1_tape_upper_bound | PASS | tape frontier >= rotation frontier |
| module1_full_gpu_result_present | PASS | rows=432, summary=30, seeds=[42, 137, 256] |
| module1_full_rotation_beats_gru_proxy | PASS | rotation frontier >= matched GRU proxy frontier |
| module1_full_tape_upper_bound | PASS | tape frontier >= rotation frontier |
| module1_capacity_benchmark_full_sharded_present | PASS | rows=1476, summary=100 |
| module1_constant_calibrated | PASS | c=8.545489937800552 |
| module1_k_direction_recorded | PASS | decision=k_inversion_or_nonmonotonic_open, open=True |
| module1_k_direction_ceiling_corrected | PASS | target=theory_consistent, dropped=[(9, 9), (20, 20)] |
| module1_diagnostic_full_sharded_present | PASS | rows=648, summary=36 |
| module1_diagnostic_k_direction_recorded | PASS | decision=k_direction_open_or_inverted, open=True |
| module1_perdepth_k_direction_negative | PASS | decision=k_direction_negative, open=False |
| module1_perdepth_with_without_agree | PASS | all joint/var/val directions are non-increasing for with/without replacement |
| module1_perdepth_keff_fit_recorded | PASS | best={('bound_single', 'with_replacement'): 'D_over_ln_product', ('bound_single', 'without_replacement'): 'D_over_ln_product', ('factored', 'with_replacement'): 'D_over_ln_Kvar', ('factored', 'without_replacement'): 'D_over_ln_Kvar'} |
| module1_batching_recorded | PASS | best_batches=[8192, 8192, 8192, 16384] |
| module1_gru_smoke_converged | PASS | frontier=0.0, checkpoint=results/gru_stack_smoke/gru_stack_best.pt |
| learned_wiring_example_count | PASS | learned=2456, cache=2456 |
| learned_wiring_model_exists | PASS | results/learned_wiring/heads.pt |
| learned_wiring_action_accuracy | PASS | action_accuracy=0.9855 |
| learned_wiring_verifier_accuracy | PASS | verifier_accuracy=0.9865 |
| two_by_two_schema | PASS | required metric fields non-null |
| d_stage_1_schema | PASS | required metric fields non-null |
| d_stage_2_schema | PASS | required metric fields non-null |
| d_stage_3_schema | PASS | required metric fields non-null |
| verifier_schema | PASS | required metric fields non-null |
| d3_two_by_two_gate | PASS | structured helps only backtracking column |
| d_stage_1_gate | PASS | structured reverts; GRU/no-revert collapse |
| d_stage_3_ordering | PASS | latent_structured >= CoT >= naive last solved depth |
| d5_verifier_monotonic | PASS | oracle >= learned >= noisy >= disabled |
| d6_ttt_reversibility | PASS | TTT restore error greater than structured |

## Oracle Dataset Actions

| action | count |
| --- | --- |
| branch | 680 |
| done | 184 |
| propagate | 1392 |
| revert | 200 |
