# Stage D Reference Archive

Generated at: 2026-06-05T13:35:20.799279+00:00

This file holds stable/reference tables that are useful for audit but noisy during incremental review. The main log is `results/experiment_log/experiment_log.md`.

## Preregistration Bands

| label | D | K | predicted d*_dyn |
| --- | --- | --- | --- |
| small_D_large_K | 256 | 729 | 19.42 |
| medium_D_large_K | 512 | 729 | 38.84 |
| small_D_medium_K | 256 | 60 | 31.26 |
| medium_D_medium_K | 512 | 60 | 62.53 |
| large_D_large_K | 1024 | 729 | 77.67 |
| offscreen_control | 4096 | 60 | 500.2 |

## Oracle Dataset

| task type | tasks | examples |
| --- | --- | --- |
| general_sat | 40 | 735 |
| graph_coloring | 40 | 360 |
| horn_sat | 24 | 216 |
| logic_grid | 40 | 465 |
| sudoku_4x4 | 40 | 680 |

## Operator Cache

| feature_source | hidden_dim | n_examples | cache |
| --- | --- | --- | --- |
| deterministic_hashed_prompt_fallback | 256 | 2456 | results/operator_cache/operator_cache.pt |

## Model Readiness

| field | value |
| --- | --- |
| transformers_available | True |
| cuda_available | True |
| cuda_device_count | 8 |
| recommended_cache_command | python -m analysis.operator_cache --load-model --limit 8 --output-name qwen_probe_cache |

## Model Downloads

| model | snapshot_path | n_files | total_gib |
| --- | --- | --- | --- |
| Qwen/Qwen3-4B-Instruct-2507 | /home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554 | 13 | 7.507 |
| Qwen/Qwen3-4B-Thinking-2507 | /home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea | 13 | 7.507 |

## Qwen Probe Cache

| feature_source | hidden_dim | n_examples | cache |
| --- | --- | --- | --- |
| Qwen/Qwen3-4B-Instruct-2507 | 2560 | 8 | results/operator_cache/qwen_probe_cache.pt |

## Qwen 128 Cache

| feature_source | hidden_dim | n_examples | cache |
| --- | --- | --- | --- |
| Qwen/Qwen3-4B-Instruct-2507 | 2560 | 128 | results/operator_cache/qwen_128_cache.pt |

## Qwen 128 Learned Wiring Smoke Test

| metric | value |
| --- | --- |
| action_accuracy | 0.5703 |
| var_accuracy | 0.3482 |
| val_accuracy | 0.4732 |
| verifier_accuracy | 0.8359 |
| n_examples | 128 |
| feature_source | Qwen/Qwen3-4B-Instruct-2507 |

## Qwen Balanced 320 Cache

| feature_source | hidden_dim | n_examples | seed_counts | cache |
| --- | --- | --- | --- | --- |
| Qwen/Qwen3-4B-Instruct-2507 | 2560 | 320 | {'42': 64, '137': 64, '256': 64, '314': 64, '999': 64} | results/operator_cache/qwen_balanced_320_cache.pt |

## Qwen Balanced 320 Learned Wiring

| metric | value |
| --- | --- |
| train_action_accuracy | 0.8398 |
| holdout_action_accuracy | 0.8906 |
| train_var_accuracy | 0.3612 |
| holdout_var_accuracy | 0.2982 |
| train_val_accuracy | 0.652 |
| holdout_val_accuracy | 0.4912 |
| train_verifier_accuracy | 0.9688 |
| holdout_verifier_accuracy | 1 |
| n_train_examples | 256 |
| n_holdout_examples | 64 |
| holdout_seed | 999 |

## Module 1 Stack Capacity Quick

| method | D | K | predicted_d_star | frontier_decode_095 |
| --- | --- | --- | --- | --- |
| gru_proxy_last_pop | 64 | 60 | 7.816 | 0 |
| gru_proxy_last_pop | 128 | 60 | 15.63 | 0 |
| gru_proxy_last_pop | 256 | 60 | 31.26 | 1 |
| gru_proxy_last_pop | 64 | 729 | 4.855 | 0 |
| gru_proxy_last_pop | 128 | 729 | 9.709 | 0 |
| gru_proxy_last_pop | 256 | 729 | 19.42 | 0 |
| rotation_vsa | 64 | 60 | 7.816 | 3 |
| rotation_vsa | 128 | 60 | 15.63 | 3 |
| rotation_vsa | 256 | 60 | 31.26 | 15 |
| rotation_vsa | 64 | 729 | 4.855 | 1 |
| rotation_vsa | 128 | 729 | 9.709 | 4 |
| rotation_vsa | 256 | 729 | 19.42 | 9 |
| tape | 64 | 60 | 7.816 | 11 |
| tape | 128 | 60 | 15.63 | 23 |
| tape | 256 | 60 | 31.26 | 47 |
| tape | 64 | 729 | 4.855 | 6 |
| tape | 128 | 729 | 9.709 | 14 |
| tape | 256 | 729 | 19.42 | 29 |

## Module 1 Stack Capacity Full GPU

| method | D | K | predicted_d_star | frontier_decode_095 |
| --- | --- | --- | --- | --- |
| gru_proxy_sequence | 64 | 60 | 7.816 | 1 |
| gru_proxy_sequence | 128 | 60 | 15.63 | 1 |
| gru_proxy_sequence | 256 | 60 | 31.26 | 1 |
| gru_proxy_sequence | 512 | 60 | 62.53 | 1 |
| gru_proxy_sequence | 1024 | 60 | 125.1 | 1 |
| gru_proxy_sequence | 64 | 729 | 4.855 | 0 |
| gru_proxy_sequence | 128 | 729 | 9.709 | 0 |
| gru_proxy_sequence | 256 | 729 | 19.42 | 0 |
| gru_proxy_sequence | 512 | 729 | 38.84 | 0 |
| gru_proxy_sequence | 1024 | 729 | 77.67 | 0 |
| rotation_vsa | 64 | 60 | 7.816 | 1 |
| rotation_vsa | 128 | 60 | 15.63 | 3 |
| rotation_vsa | 256 | 60 | 31.26 | 7 |
| rotation_vsa | 512 | 60 | 62.53 | 15 |
| rotation_vsa | 1024 | 60 | 125.1 | 31 |
| rotation_vsa | 64 | 729 | 4.855 | 1 |
| rotation_vsa | 128 | 729 | 9.709 | 4 |
| rotation_vsa | 256 | 729 | 19.42 | 9 |
| rotation_vsa | 512 | 729 | 38.84 | 19 |
| rotation_vsa | 1024 | 729 | 77.67 | 38 |
| tape | 64 | 60 | 7.816 | 11 |
| tape | 128 | 60 | 15.63 | 23 |
| tape | 256 | 60 | 31.26 | 47 |
| tape | 512 | 60 | 62.53 | 93 |
| tape | 1024 | 60 | 125.1 | 188 |
| tape | 64 | 729 | 4.855 | 6 |
| tape | 128 | 729 | 9.709 | 14 |
| tape | 256 | 729 | 19.42 | 29 |
| tape | 512 | 729 | 38.84 | 57 |
| tape | 1024 | 729 | 77.67 | 116 |

Module 1 full notes: GRU is a lightweight trained full-sequence decoder from the bounded final state, not an exact inverse and not fully hyperparameter-tuned.


## Learned Wiring Baseline

| metric | value |
| --- | --- |
| train_action_accuracy | 0.9855 |
| holdout_action_accuracy | 0.4724 |
| train_var_accuracy | 0.373 |
| holdout_var_accuracy | 0.09247 |
| train_val_accuracy | 0.4536 |
| holdout_val_accuracy | 0.2065 |
| train_verifier_accuracy | 0.9865 |
| holdout_verifier_accuracy | 0.901 |
| holdout_seed | 999 |
| feature_source | deterministic_hashed_prompt_fallback |

## D.3 2x2 Falsification

| method | column | n_tasks | solve_rate | applied_reverts | max_required_depth |
| --- | --- | --- | --- | --- | --- |
| latent_only | propagation_only | 8 | 1 | 0 | 0 |
| latent_only | backtracking_required | 15 | 0 | 0 | 5 |
| latent_plus_structured_register | propagation_only | 8 | 1 | 0 | 0 |
| latent_plus_structured_register | backtracking_required | 15 | 1 | 31 | 5 |

## D-stage 0 Propagation

| depth | task_kind | solve_rate |
| --- | --- | --- |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |

## D-stage 1 Depth-1 Gate

| method | n_tasks | solve_rate | applied_reverts | max_required_depth |
| --- | --- | --- | --- | --- |
| latent_only | 10 | 0 | 0 | 1 |
| structured_register | 10 | 1 | 10 | 1 |
| gru_register | 10 | 0 | 0 | 1 |
| no_revert_ablation | 10 | 0 | 0 | 1 |

## D-stage 2 Capacity Frontier

| register | D | K | predicted_d_star | observed_frontier |
| --- | --- | --- | --- | --- |
| structured | 64 | 60 | 7.816 | 7 |
| structured | 64 | 729 | 4.855 | 4 |
| structured | 128 | 60 | 15.63 | 15 |
| structured | 128 | 729 | 9.709 | 9 |
| structured | 256 | 60 | 31.26 | 31 |
| structured | 256 | 729 | 19.42 | 19 |
| structured | 512 | 60 | 62.53 | 62 |
| structured | 512 | 729 | 38.84 | 38 |
| structured | 1024 | 60 | 125.1 | 125 |
| structured | 1024 | 729 | 77.67 | 77 |
| gru | 64 | 60 | None | 2 |
| gru | 64 | 729 | None | 2 |
| gru | 128 | 60 | None | 3 |
| gru | 128 | 729 | None | 3 |
| gru | 256 | 60 | None | 5 |
| gru | 256 | 729 | None | 4 |
| gru | 512 | 60 | None | 7 |
| gru | 512 | 729 | None | 6 |
| gru | 1024 | 60 | None | 11 |
| gru | 1024 | 729 | None | 8 |

## D-stage 3 Vs CoT

| D | K | method | predicted_d_star | last_solved_depth | matched_compute |
| --- | --- | --- | --- | --- | --- |
| 256 | 60 | latent_structured | 31.26 | 31 | True |
| 256 | 60 | qwen_thinking_cot | 31.26 | 15 | True |
| 256 | 60 | naive_pass_scaling | 31.26 | 1 | True |
| 4096 | 60 | latent_structured | 500.2 | 500 | True |
| 4096 | 60 | qwen_thinking_cot | 500.2 | 250 | True |
| 4096 | 60 | naive_pass_scaling | 500.2 | 1 | True |

## D.5 Verifier Verification

| mode | n_tasks | solve_rate | false_positive_reverts | false_negative_misses |
| --- | --- | --- | --- | --- |
| oracle | 20 | 1 | 0 | 0 |
| learned | 20 | 0.7 | 1 | 6 |
| noisy | 20 | 0.3 | 3 | 14 |
| disabled | 20 | 0 | 0 | 54 |

## D.6 TTT Reversibility

| structured_restore_error | ttt_restore_error | ratio |
| --- | --- | --- |
| 2.992e-06 | 0.0995 | 3.326e+04 |

## Analysis Summary

# Stage D Scaffold Analysis

These figures summarize oracle-trace scaffold outputs, not trained-model evaluations.

## Gates

- 2x2 falsification backtracking column: latent-only solve rate 0.00, structured-register solve rate 1.00.
- D-stage 1 depth-1 gate: structured-register solve rate 1.00 with 10 applied reverts.
- Verifier ablation: oracle solve rate 1.00, disabled solve rate 0.00.
- TTT diagnostic: restore-error ratio 33260.48.


## Validation Checks

| check | status | detail |
| --- | --- | --- |
| required_files_present | FAIL | missing=['results/gru_stack_grid_fair/results.json', 'results/gru_vs_structured_closeout/results.json'] |
