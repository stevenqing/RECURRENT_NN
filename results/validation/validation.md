# Stage D Validation Report

Generated at: 2026-06-06T09:45:09.532162+00:00

## Checks

| check | status | detail |
| --- | --- | --- |
| required_files_present | FAIL | missing=['results/preregistration/preregistration.json', 'results/oracle_dataset/summary.json', 'results/oracle_dataset/examples.jsonl', 'results/operator_cache/summary.json', 'results/operator_cache/qwen_probe_cache_summary.json', 'results/operator_cache/qwen_128_cache_summary.json', 'results/learned_wiring_qwen_128/results.json', 'results/operator_cache/qwen_balanced_320_cache_summary.json', 'results/learned_wiring_qwen_balanced_320/results.json', 'results/module1_stack_capacity/results.json', 'results/module1_stack_capacity_full/results.json', 'results/module1_capacity_benchmark_full_shards/results.json', 'results/module1_capacity_diagnostic_full_shards/results.json', 'results/learned_wiring/results.json', 'results/two_by_two/results.json', 'results/d_stage_0/results.json', 'results/d_stage_1/results.json', 'results/d_stage_2/results.json', 'results/d_stage_3/results.json', 'results/verifier/results.json', 'results/ttt/results.json', 'results/analysis/summary.md'] |
| m2_per_task_verdicts_recorded | PASS | verdicts={'general_sat': 'NEEDS_OPERATOR_FIX', 'graph_coloring': 'NEEDS_OPERATOR_FIX', 'horn_sat': 'NEEDS_OPERATOR_FIX', 'logic_grid': 'NEEDS_OPERATOR_FIX', 'sudoku_4x4': 'NEEDS_OPERATOR_FIX'} |
| m2_iterated_ablation_recorded | PASS | single_keys=['accepted_moves', 'calls', 'fixpoint_reach_rate', 'mean_rounds_to_fixpoint', 'n', 'parse_success_rate', 'per_call_precision', 'rejected_moves'], list_all_keys=['filter_dropped', 'forced_recall', 'n', 'parse_success_rate', 'raw_precision'] |
| m2_branch_decision_recorded | PASS | branch_decision=qwen_guess_beats_mrv_reconsider |

## Oracle Dataset Actions

| action | count |
| --- | --- |
