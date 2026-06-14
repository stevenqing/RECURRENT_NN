"""Generate the canonical RECURRENT_NN experiment ledger."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

ARTIFACT_INDEX = {
    "canonical_repo_note": "CANONICAL_REPO.md",
    "environment_spec": "ENV_SPEC.md",
    "post_027_continuation_state": "results/continuation_state/post_027.json",
    "item_028_p0_housekeeping": "results/experiment_items/item_028_p0_housekeeping.json",
    "item_029_p1_1a_g1_diagnosis": "results/experiment_items/item_029_p1_1a_g1_diagnosis.json",
    "item_030_p2_w3_hook_capacity": "results/experiment_items/item_030_p2_w3_hook_capacity.json",
    "item_031_p2_w3_survival_delta_propagation": "results/experiment_items/item_031_p2_w3_survival_delta_propagation.json",
    "item_032_validation_green_closeout": "results/experiment_items/item_032_validation_green_closeout.json",
    "item_033_validation_object_binding": "results/experiment_items/item_033_validation_object_binding.json",
    "item_034_t2_t3_cached_state_and_learned_preflight": "results/experiment_items/item_034_t2_t3_cached_state_and_learned_preflight.json",
    "item_035_g1_anomaly_true_dims_w3_scale": "results/experiment_items/item_035_g1_anomaly_true_dims_w3_scale.json",
    "item_036_overnight_t2_w3_50x2_closeout": "results/experiment_items/item_036_overnight_t2_w3_50x2_closeout.json",
    "item_037_two_track_decoupling_track_a_symbolic": "results/experiment_items/item_037_two_track_decoupling_track_a_symbolic.json",
    "item_038_track_a_budgeted_parallel_symbolic_l4": "results/experiment_items/item_038_track_a_budgeted_parallel_symbolic_l4.json",
    "item_039_track_b_trm_operator_smoke": "results/experiment_items/item_039_track_b_trm_operator_smoke.json",
    "item_040_track_b_trm_full_3x8gpu_negative": "results/experiment_items/item_040_track_b_trm_full_3x8gpu_negative.json",
    "item_041_gpu_efficiency_p0_profile_and_sudoku_engine": "results/experiment_items/item_041_gpu_efficiency_p0_profile_and_sudoku_engine.json",
    "item_042_register_batched_ops_equivalence": "results/experiment_items/item_042_register_batched_ops_equivalence.json",
    "item_043_track_b_retry_plan": "results/experiment_items/item_043_track_b_retry_plan.json",
    "item_044_trainer_prelaunch_gates": "results/experiment_items/item_044_trainer_prelaunch_gates.json",
    "item_045_track_b_ddp_sharded_retry_launch": "results/experiment_items/item_045_track_b_ddp_sharded_retry_launch.json",
    "item_046_track_b_ddp_sharded_seed102_final": "results/experiment_items/item_046_track_b_ddp_sharded_seed102_final.json",
    "item_047_deep_band_track_a_headline_overnight": "results/experiment_items/item_047_deep_band_track_a_headline_overnight.json",
    "item_048_item047_headline_closeout": "results/experiment_items/item_048_item047_headline_closeout.json",
    "item_049_track_b_value_head_retrain": "results/experiment_items/item_049_track_b_value_head_retrain.json",
    "item_050_post_review_e1_cross_task_generalization": "results/experiment_items/item_050_post_review_e1_cross_task_generalization.json",
    "item_051_rung1_distributed_graph_coloring": "results/experiment_items/item_051_rung1_distributed_graph_coloring.json",
    "item_052_rung1_gate_distributed_coloring_v01": "results/experiment_items/item_052_rung1_gate_distributed_coloring_v01.json",
    "item_053_rung1_gate_distributed_coloring_v02": "results/experiment_items/item_053_rung1_gate_distributed_coloring_v02.json",
    "item_054_rung1_phase1_spec_v01": "results/experiment_items/item_054_rung1_phase1_spec_v01.json",
    "item_055_rung1_phase1_r4_natural_pool": "results/experiment_items/item_055_rung1_phase1_r4_natural_pool.json",
    "item_056_rung1_phase1_r3_qwen_oneshot": "results/experiment_items/item_056_rung1_phase1_r3_qwen_oneshot.json",
    "item_057_rung1_phase1_r2_budget_sweep": "results/experiment_items/item_057_rung1_phase1_r2_budget_sweep.json",
    "item_058_rung1_separator_scaling": "results/experiment_items/item_058_rung1_separator_scaling.json",
    "item_059_rung1_separator_llm_po": "results/experiment_items/item_059_rung1_separator_llm_po.json",
    "item_060_rung1_separator_fallibility_rungs": "results/experiment_items/item_060_rung1_separator_fallibility_rungs.json",
    "item_061_rung1_separator_p1a_recovery_baseline": "results/experiment_items/item_061_rung1_separator_p1a_recovery_baseline.json",
    "item_062_rung1_separator_capacity_scoped_positive_p1c_competence_gate": "results/experiment_items/item_062_rung1_separator_capacity_scoped_positive_p1c_competence_gate.json",
    "item_063_rung1_separator_llm_inloop_smoke": "results/experiment_items/item_063_rung1_separator_llm_inloop_smoke.json",
    "item_064_rung1_overnight_batch": "results/experiment_items/item_064_rung1_overnight_batch.json",
    "item_065_rung1_fallible_1d_rerun": "results/experiment_items/item_065_rung1_fallible_1d_rerun.json",
    "item_066_rung1_paired_register_requirement": "results/experiment_items/item_066_rung1_paired_register_requirement.json",
    "item_067_rung1_rho_sweep_register_requirement": "results/experiment_items/item_067_rung1_rho_sweep_register_requirement.json",
    "item_068_rung1_culprit_erosion_sweep": "results/experiment_items/item_068_rung1_culprit_erosion_sweep.json",
    "item_069_rung1_llm_native_benchmark_harness_alignment": "results/experiment_items/item_069_rung1_llm_native_benchmark_harness_alignment.json",
    "item_070_rung1_paradigm_overnight_real_llm": "results/experiment_items/item_070_rung1_paradigm_overnight_real_llm.json",
    "item_071_rung1_multiagent_graphcolor_controlled_dryrun": "results/experiment_items/item_071_rung1_multiagent_graphcolor_controlled_dryrun.json",
    "item_072_rung1_multiagent_graphcolor_engineered_slice": "results/experiment_items/item_072_rung1_multiagent_graphcolor_engineered_slice.json",
    "item_073_rung1_multiagent_accounting_anchor": "results/experiment_items/item_073_rung1_multiagent_accounting_anchor.json",
    "item_074_rung1_multiagent_cascade_fixed": "results/experiment_items/item_074_rung1_multiagent_cascade_fixed.json",
    "item_075_rung1_multiagent_two_track": "results/experiment_items/item_075_rung1_multiagent_two_track.json",
    "item_076_rung1_multiagent_solvability": "results/experiment_items/item_076_rung1_multiagent_solvability.json",
    "item_077_externalization_validation_preflight": "results/experiment_items/item_077_externalization_validation_preflight.json",
    "item_078_externalization_power_calibration": "results/experiment_items/item_078_externalization_power_calibration.json",
    "item_079_externalization_full_execution_v1": "results/experiment_items/item_079_externalization_full_execution_v1.json",
    "item_080_externalization_graph_color_ceiling_llm": "results/experiment_items/item_080_externalization_graph_color_ceiling_llm.json",
    "item_081_externalization_next_batch_status": "results/experiment_items/item_081_externalization_next_batch_status.json",
    "item_082_externalization_honest_token_accounting": "results/experiment_items/item_082_externalization_honest_token_accounting.json",
    "item_083_externalization_graph_color_middle_band_llm": "results/experiment_items/item_083_externalization_graph_color_middle_band_llm.json",
    "item_084_externalization_multiagent_real_llm_v1_pilot": "results/experiment_items/item_084_externalization_multiagent_real_llm_v1_pilot.json",
    "item_085_externalization_multiagent_real_llm_prelaunch": "results/experiment_items/item_085_externalization_multiagent_real_llm_prelaunch.json",
    "item_086_externalization_multiagent_scheduler_patch": "results/experiment_items/item_086_externalization_multiagent_scheduler_patch.json",
    "item_087_externalization_multiagent_row_isolation": "results/experiment_items/item_087_externalization_multiagent_row_isolation.json",
    "item_088_reasoning_gym_baseline_first": "results/experiment_items/item_088_reasoning_gym_baseline_first.json",
    "item_089_reasoning_gym_llm_baseline_timeout_patch": "results/experiment_items/item_089_reasoning_gym_llm_baseline_timeout_patch.json",
    "item_090_reasoning_gym_l1_direct_baselines": "results/experiment_items/item_090_reasoning_gym_l1_direct_baselines.json",
    "item_091_reasoning_gym_baseline_metrics": "results/experiment_items/item_091_reasoning_gym_baseline_metrics.json",
    "item_092_reasoning_gym_graph_color_bon5": "results/experiment_items/item_092_reasoning_gym_graph_color_bon5.json",
    "item_093_reasoning_gym_graph_color_thinking_only": "results/experiment_items/item_093_reasoning_gym_graph_color_thinking_only.json",
    "item_094_reasoning_gym_graph_color_two_stage_thinking": "results/experiment_items/item_094_reasoning_gym_graph_color_two_stage_thinking.json",
    "item_095_reasoning_gym_graph_color_mregister_method_pilot": "results/experiment_items/item_095_reasoning_gym_graph_color_mregister_method_pilot.json",
    "item_096_multiagent_internalization_itemized_plan": "results/experiment_items/item_096_multiagent_internalization_itemized_plan.json",
    "item_097_graph_color_single_agent_internalization_trace_smoke": "results/experiment_items/item_097_graph_color_single_agent_internalization_trace_smoke.json",
    "item_098_graph_color_multiagent_internalization_trace_pilot": "results/experiment_items/item_098_graph_color_multiagent_internalization_trace_pilot.json",
    "item_099_internalization_ttt_lora_training_design": "results/experiment_items/item_099_internalization_ttt_lora_training_design.json",
    "item_100_kvcache_checkpoint_km3_exactness": "results/experiment_items/item_100_kvcache_checkpoint_km3_exactness.json",
    "item_101_qwen35_full_cache_checkpoint_gate": "results/experiment_items/item_101_qwen35_full_cache_checkpoint_gate.json",
    "item_102_pure_kv_qwen3_km3_exactness": "results/experiment_items/item_102_pure_kv_qwen3_km3_exactness.json",
    "log_item_contract_spec": "specs/log_item_contract.md",
    "rung1_phase1_spec_v01": "specs/rung1_phase1_spec_v01.md",
    "model_readiness": "results/model_readiness/readiness.json",
    "qwen3_4b_instruct_download": "results/model_download/qwen_download.json",
    "qwen3_4b_thinking_download": "results/model_download/thinking/qwen_download.json",
    "qwen3_5_4b_download": "results/model_download/qwen3_5_4b/qwen_download.json",
    "module1_capacity_perdepth": "results/module1_capacity_perdepth_shards/results.json",
    "module1_k_direction_corrected": "results/module1_capacity_benchmark_full_shards/k_direction_corrected.json",
    "module1_capacity_batching": "results/module1_capacity_batching_large/results.json",
    "gru_stack_smoke": "results/gru_stack_smoke/results.json",
    "gru_stack_grid_full_legacy": "results/gru_stack_grid_full/results.json",
    "gru_degeneracy_diagnostic": "results/gru_degeneracy_diagnostic/results.json",
    "gru_stack_grid_fair": "results/gru_stack_grid_fair/results.json",
    "gru_vs_structured_closeout": "results/gru_vs_structured_closeout/results.json",
    "m2_operator_probe": "results/m2_operator_probe/report.json",
    "m2_operator_fix_rescale": "results/m2_operator_probe/report_fix_rescale.json",
    "g1_fix_spec": "specs/g1_fix_spec.md",
    "stage_a_reconstructed_artifacts": "artifacts/stage_a/manifest.json",
    "stage_a_backtrack": "results/stage_a_backtrack/report.json",
    "stage_a_symbolic_budgeted_grid_script": "experiments/stage_a_symbolic_budgeted_grid.py",
    "stage_a_symbolic_results": "results/stage_a_symbolic/results.json",
    "stage_a_symbolic_report": "results/stage_a_symbolic/report.json",
    "stage_a_symbolic_oracle_statelessness": "results/stage_a_symbolic/oracle_statelessness_ci.json",
    "post025_adapter_wiring": "results/stage_a_adapter_wiring/results.json",
    "post026_banded_gate_refusal": "results/stage_a_banded_gate_refusal/results.json",
    "post027_sudoku6_bridge": "results/stage_a_sudoku6_bridge/results.json",
    "w3_qwen35_probe_spec": "specs/w3_qwen35_probe_spec.md",
    "w3_qwen35_probe": "results/w3_qwen35_probe/results.json",
    "t2_recurrent_operator_8gpu_acceptance": "results/recurrent_operator_8gpu/acceptance.json",
    "track_b_trm_operator_trainer": "experiments/train_trm_operator.py",
    "track_b_trm_operator_smoke_acceptance": "results/trm_operator_smoke/acceptance.json",
    "track_b_trm_full_3x8gpu_monitor": "results/track_b_trm_3x8gpu_20260608T042649Z/monitor_summary.json",
    "track_b_trm_full_seed102_acceptance": "results/track_b_trm_3x8gpu_20260608T042649Z/seed102_8gpu/acceptance.json",
    "track_b_trm_full_seed137_acceptance": "results/track_b_trm_3x8gpu_20260608T042649Z/seed137_8gpu/acceptance.json",
    "track_b_trm_full_seed256_acceptance": "results/track_b_trm_3x8gpu_20260608T042649Z/seed256_8gpu/acceptance.json",
    "track_b_p0_profile_report": "results/profile_gate/track_b_current_20260608T_p0_single/profile_report.json",
    "track_b_p0_profiler_key_averages": "results/profile_gate/track_b_current_20260608T_p0_single/torch_profiler_key_averages.txt",
    "track_b_p0_gpu_util_samples": "results/profile_gate/track_b_current_20260608T_p0_single/gpu_util_samples.jsonl",
    "sudoku_engine_gpu": "sudoku_engine_gpu.py",
    "sudoku_engine_gpu_equivalence": "results/sudoku_engine_gpu/equivalence_1000.json",
    "register_batched_ops": "register/batched_ops.py",
    "register_batched_ops_equivalence": "results/batched_ops/equivalence_100.json",
    "track_b_retry_plan": "specs/track_b_retry_plan.md",
    "track_b_prelaunch_smoke_acceptance": "results/trm_operator_prelaunch_smoke/acceptance.json",
    "track_b_compile_smoke_acceptance": "results/trm_operator_compile_smoke/acceptance.json",
    "track_b_value_head_retrain_acceptance": "results/track_b_value_head_retrain_20260609/acceptance.json",
    "post_review_e1_cross_task_generalization": "results/post_review_e1_cross_task_generalization/results.json",
    "rung1_distributed_graph_coloring": "results/rung1_distributed_graph_coloring/results.json",
    "rung1_gate_distributed_coloring_v01": "results/rung1_gate_distributed_coloring_v01/results.json",
    "rung1_gate_distributed_coloring_v02": "results/rung1_gate_distributed_coloring_v02/results.json",
    "rung1_phase1_r4_natural_pool": "results/rung1_phase1_r4_natural_pool/results.json",
    "rung1_phase1_r3_qwen_oneshot": "results/rung1_phase1_r3_qwen_oneshot/results.json",
    "rung1_phase1_r2_budget_sweep": "results/rung1_phase1_r2_budget_sweep/results.json",
    "rung1_separator_scaling": "results/rung1_separator_scaling/results.json",
    "rung1_separator_llm_po": "results/rung1_separator_llm_po/results.json",
    "rung1_separator_llm_po_forward_gate": "results/rung1_separator_llm_po/p1a_forward_gate.json",
    "rung1_separator_llm_po_p1a_recovery_baseline": "results/rung1_separator_llm_po/p1a_recovery_baseline.json",
    "rung1_separator_fallibility_rungs": "results/rung1_separator_fallibility_rungs/results.json",
    "rung1_separator_p1b_raw_generation_inspection": "results/rung1_separator_fallibility_rungs/p1b_raw_generation_inspection.json",
    "rung1_separator_p1b_truncation_pilot": "results/rung1_separator_fallibility_rungs/p1b_truncation_pilot.json",
    "rung1_separator_p1b_graded_recompute": "results/rung1_separator_fallibility_rungs/p1b_graded_recompute.json",
    "rung1_separator_p1b_full_table": "results/rung1_separator_fallibility_rungs/p1b_full_table.json",
    "rung1_separator_p1b_full_table_v1_addendum": "results/rung1_separator_fallibility_rungs/p1b_full_table_v1.json",
    "rung1_separator_p1c_truncation_pilot": "results/rung1_separator_fallibility_rungs/p1c_truncation_pilot.json",
    "rung1_separator_p1c_truncation_pilot_v2": "results/rung1_separator_fallibility_rungs/p1c_truncation_pilot_v2/p1c_truncation_pilot.json",
    "rung1_separator_item062_execution": "results/rung1_separator_fallibility_rungs/item062_execution.json",
    "rung1_separator_llm_inloop": "results/rung1_separator_llm_inloop/results.json",
    "rung1_separator_llm_inloop_preflight": "results/rung1_separator_llm_inloop/preflight_full_scope.json",
    "rung1_separator_llm_inloop_sharded_smoke": "results/rung1_separator_llm_inloop/sharded_smoke/results.json",
    "rung1_separator_llm_inloop_vllm_smoke": "results/rung1_separator_llm_inloop/vllm_smoke/results.json",
    "rung1_separator_llm_inloop_vllm_structured_smoke": "results/rung1_separator_llm_inloop/vllm_structured_smoke/results.json",
    "rung1_separator_llm_inloop_vllm_structured_grid_pilot": "results/rung1_separator_llm_inloop/vllm_structured_grid_pilot/results.json",
    "rung1_separator_llm_inloop_full_slice_vllm_structured": "results/rung1_separator_llm_inloop/full_slice_vllm_structured/results.json",
    "rung1_separator_llm_inloop_divergence_analysis": "results/rung1_separator_llm_inloop/divergence_analysis/item063_inloop_divergence.json",
    "rung1_separator_llm_inloop_explicit_state_pilot": "results/rung1_separator_llm_inloop/explicit_state_pilot/results.json",
    "rung1_separator_llm_inloop_full_slice_vllm_explicit_state": "results/rung1_separator_llm_inloop/full_slice_vllm_explicit_state/results.json",
    "rung1_overnight_batch": "results/rung1_overnight_batch/results.json",
    "rung1_fallible_1d_rerun": "results/rung1_fallible_1d_rerun/results.json",
    "rung1_paired_register_requirement": "results/rung1_paired_register_requirement/results.json",
    "rung1_rho_sweep_register_requirement": "results/rung1_rho_sweep_register_requirement/results.json",
    "rung1_culprit_erosion_sweep": "results/rung1_culprit_erosion_sweep/results.json",
    "rung1_llm_search_decision_paradigm_dry_run": "results/rung1_llm_search_decision_paradigm/dry_run.json",
    "rung1_reasoning_gym_bounded_register_dry_run": "results/rung1_reasoning_gym_bounded_register/dry_run.json",
    "rung1_reasoning_gym_bounded_register_method_comparison_graph_color_pilot": "results/rung1_reasoning_gym_bounded_register/method_comparison_graph_color_pilot.json",
    "rung1_reasoning_gym_bounded_register_method_comparison_graph_color_pilot_checkpoint": "results/rung1_reasoning_gym_bounded_register/method_comparison_graph_color_pilot_checkpoint.json",
    "rung1_reasoning_gym_bounded_register_method_comparison_graph_color_pilot_preflight": "results/rung1_reasoning_gym_bounded_register/method_comparison_graph_color_pilot_preflight.json",
    "rung1_reasoning_gym_bounded_register_method_comparison_graph_color_pilot_preflight_checkpoint": "results/rung1_reasoning_gym_bounded_register/method_comparison_graph_color_pilot_preflight_checkpoint.json",
    "internalization_trace_harvester": "analysis/internalization_trace_harvester.py",
    "internalization_graph_color_single_agent_mregister_trace_smoke": "results/internalization_traces/graph_color_single_agent_mregister_trace_smoke.json",
    "internalization_graph_color_single_agent_mregister_trace_smoke_jsonl": "results/internalization_traces/graph_color_single_agent_mregister_trace_smoke.jsonl",
    "internalization_multiagent_trace_harvester": "analysis/internalization_multiagent_trace_harvester.py",
    "internalization_graph_color_multiagent_trace_pilot": "results/internalization_traces/graph_color_multiagent_trace_pilot.json",
    "internalization_graph_color_multiagent_trace_pilot_jsonl": "results/internalization_traces/graph_color_multiagent_trace_pilot.jsonl",
    "rung1_paradigm_overnight": "results/rung1_paradigm_overnight/results.json",
    "rung1_paradigm_overnight_track123": "results/rung1_paradigm_overnight/track123.json",
    "rung1_paradigm_overnight_smoke": "results/rung1_paradigm_overnight/smoke.json",
    "rung1_paradigm_overnight_multiagent_dry_run": "results/rung1_paradigm_overnight/multiagent_dry_run.json",
    "rung1_multiagent_graphcolor_dry_run": "results/rung1_multiagent_graphcolor/dry_run.json",
    "rung1_multiagent_graphcolor_engineered_dry_run": "results/rung1_multiagent_graphcolor/engineered_dry_run.json",
    "rung1_multiagent_accounting_anchor": "results/rung1_multiagent_accounting_anchor/results.json",
    "rung1_multiagent_cascade_fixed": "results/rung1_multiagent_cascade_fixed/results.json",
    "rung1_multiagent_two_track": "results/rung1_multiagent_two_track/results.json",
    "rung1_multiagent_solvability": "results/rung1_multiagent_solvability/results.json",
    "rung1_multiagent_solvability_closeout": "results/rung1_multiagent_solvability/closeout.json",
    "rung1_multiagent_solvability_distance_slope_reanalysis": "results/rung1_multiagent_solvability/distance_slope_reanalysis.json",
    "externalization_paper_validation_spec_v0": "specs/externalization_paper_validation_v0.md",
    "externalization_validation_preflight": "results/externalization_validation_v0/preflight.json",
    "externalization_power_calibration": "results/externalization_validation_v0/power_calibration.json",
    "externalization_two_rail_gate": "results/externalization_validation_v0/two_rail_gate.json",
    "externalization_paper_full_execution_spec_v1": "specs/externalization_paper_full_execution_v1.md",
    "multiagent_real_llm_internalization_spec_v1": "specs/multiagent_real_llm_internalization_v1.md",
    "multiagent_internalization_itemized_plan_v1": "specs/multiagent_internalization_itemized_plan_v1.md",
    "internalization_ttt_lora_training_design_v1": "specs/internalization_ttt_lora_training_design_v1.md",
    "kvcache_checkpoint_search_spec_v1": "specs/kvcache_checkpoint_search_v1.md",
    "kvcache_exactness_gate_script": "analysis/kvcache_exactness_gate.py",
    "kvcache_full_checkpoint_gate_script": "analysis/kvcache_full_checkpoint_gate.py",
    "kvcache_exactness_km3_result": "results/kvcache_exactness/km3_result.json",
    "kvcache_full_checkpoint_qwen35_bf16": "results/kvcache_exactness/km3_full_checkpoint_qwen35.json",
    "kvcache_full_checkpoint_qwen35_fp32_tol1e3": "results/kvcache_exactness/km3_full_checkpoint_qwen35_fp32_tol1e3.json",
    "kvcache_pure_kv_qwen3_bf16": "results/kvcache_exactness/km3_pure_kv_qwen3_4b_instruct.json",
    "kvcache_pure_kv_qwen3_fp32_strict": "results/kvcache_exactness/km3_pure_kv_qwen3_4b_instruct_fp32.json",
    "kvcache_pure_kv_qwen3_fp32_tol1e3": "results/kvcache_exactness/km3_pure_kv_qwen3_4b_instruct_fp32_tol1e3.json",
    "reasoning_gym_baseline_first_spec_v1": "specs/reasoning_gym_baseline_first_v1.md",
    "externalization_full_execution_manifest": "results/externalization_validation_v0/full_execution_manifest.json",
    "externalization_graph_color_ceiling_llm": "results/externalization_validation_v0/graph_color_ceiling_llm.json",
    "externalization_next_batch_status": "results/externalization_validation_v0/next_batch_status.json",
    "externalization_graph_color_middle_band_calibration": "results/externalization_validation_v0/graph_color_middle_band_calibration.json",
    "externalization_graph_color_middle_band_llm": "results/externalization_validation_v0/graph_color_middle_band_llm.json",
    "externalization_graph_color_middle_band_llm_checkpoint": "results/externalization_validation_v0/graph_color_middle_band_llm_checkpoint.json",
    "externalization_multiagent_real_llm_v1_pilot": "results/externalization_validation_v0/multiagent_real_llm_v1_pilot.json",
    "externalization_multiagent_real_llm_v1_pilot_checkpoint": "results/externalization_validation_v0/multiagent_real_llm_v1_pilot_checkpoint.json",
    "externalization_multiagent_real_llm_v1_prelaunch_partial": "results/externalization_validation_v0/multiagent_real_llm_v1_prelaunch_partial.json",
    "externalization_multiagent_real_llm_v1_prelaunch_checkpoint": "results/externalization_validation_v0/multiagent_real_llm_v1_prelaunch_checkpoint.json",
    "externalization_multiagent_real_llm_v1_scheduler_patch": "results/externalization_validation_v0/multiagent_real_llm_v1_scheduler_patch.json",
    "externalization_multiagent_real_llm_v1_scheduler_check": "results/externalization_validation_v0/multiagent_real_llm_v1_scheduler_check.json",
    "externalization_multiagent_real_llm_v1_scheduler_check_checkpoint": "results/externalization_validation_v0/multiagent_real_llm_v1_scheduler_check_checkpoint.json",
    "externalization_multiagent_real_llm_v1_row_isolation_patch": "results/externalization_validation_v0/multiagent_real_llm_v1_row_isolation_patch.json",
    "externalization_multiagent_real_llm_v1_filter_check": "results/externalization_validation_v0/multiagent_real_llm_v1_filter_check.json",
    "externalization_multiagent_real_llm_v1_filter_check_checkpoint": "results/externalization_validation_v0/multiagent_real_llm_v1_filter_check_checkpoint.json",
    "reasoning_gym_baseline_first_status": "results/reasoning_gym_baselines/baseline_first_status.json",
    "reasoning_gym_baseline_matrix_smoke": "results/reasoning_gym_baselines/baseline_matrix_smoke.json",
    "reasoning_gym_baseline_matrix_llm_timeout_smoke": "results/reasoning_gym_baselines/baseline_matrix_llm_timeout_smoke.json",
    "reasoning_gym_baseline_matrix_llm_timeout_smoke_checkpoint": "results/reasoning_gym_baselines/baseline_matrix_llm_timeout_smoke_checkpoint.json",
    "reasoning_gym_l1_direct_baseline_batch": "results/reasoning_gym_baselines/l1_direct_baseline_batch.json",
    "reasoning_gym_baseline_graph_color_l1_direct": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_direct.json",
    "reasoning_gym_baseline_graph_color_l1_direct_checkpoint": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_direct_checkpoint.json",
    "reasoning_gym_baseline_sudoku_l1_direct": "results/reasoning_gym_baselines/baseline_matrix_sudoku_l1_direct.json",
    "reasoning_gym_baseline_sudoku_l1_direct_checkpoint": "results/reasoning_gym_baselines/baseline_matrix_sudoku_l1_direct_checkpoint.json",
    "reasoning_gym_baseline_zebra_l1_direct": "results/reasoning_gym_baselines/baseline_matrix_zebra_l1_direct.json",
    "reasoning_gym_baseline_zebra_l1_direct_checkpoint": "results/reasoning_gym_baselines/baseline_matrix_zebra_l1_direct_checkpoint.json",
    "reasoning_gym_baseline_metrics_dashboard": "results/reasoning_gym_baselines/baseline_metrics_dashboard.json",
    "reasoning_gym_baseline_graph_color_l1_thinking_pilot": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_thinking_pilot.json",
    "reasoning_gym_baseline_graph_color_l1_thinking_pilot_checkpoint": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_thinking_pilot_checkpoint.json",
    "reasoning_gym_baseline_graph_color_l1_direct_bon5": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_direct_bon5.json",
    "reasoning_gym_baseline_graph_color_l1_direct_bon5_checkpoint": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_direct_bon5_checkpoint.json",
    "reasoning_gym_baseline_metrics_dashboard_bon5": "results/reasoning_gym_baselines/baseline_metrics_dashboard_bon5.json",
    "reasoning_gym_baseline_graph_color_l1_thinking_only_pilot": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_thinking_only_pilot.json",
    "reasoning_gym_baseline_graph_color_l1_thinking_only_pilot_checkpoint": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_thinking_only_pilot_checkpoint.json",
    "reasoning_gym_baseline_metrics_dashboard_thinking_only": "results/reasoning_gym_baselines/baseline_metrics_dashboard_thinking_only.json",
    "reasoning_gym_baseline_graph_color_l1_thinking_two_stage_pilot": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_thinking_two_stage_pilot.json",
    "reasoning_gym_baseline_graph_color_l1_thinking_two_stage_pilot_checkpoint": "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_thinking_two_stage_pilot_checkpoint.json",
    "reasoning_gym_baseline_metrics_dashboard_two_stage_thinking": "results/reasoning_gym_baselines/baseline_metrics_dashboard_two_stage_thinking.json",
    "externalization_sudoku_adapter_preflight": "results/externalization_validation_v0/sudoku_adapter_preflight.json",
    "externalization_graph_color_oneshot_thinking_checkpoint": "results/externalization_validation_v0/graph_color_ceiling_oneshot_thinking_checkpoint.json",
    "externalization_honest_token_accounting_addendum": "results/externalization_validation_v0/honest_token_accounting_addendum.json",
    "validation": "results/validation/validation.json",
}

LEGACY_ARCHIVE = {
    "preregistration": "results/preregistration/preregistration.json",
    "oracle_dataset": "results/oracle_dataset/summary.json",
    "operator_cache": "results/operator_cache/summary.json",
    "qwen_probe_cache": "results/operator_cache/qwen_probe_cache_summary.json",
    "qwen_128_cache": "results/operator_cache/qwen_128_cache_summary.json",
    "learned_wiring_qwen_128": "results/learned_wiring_qwen_128/results.json",
    "qwen_balanced_320_cache": "results/operator_cache/qwen_balanced_320_cache_summary.json",
    "learned_wiring_qwen_balanced_320": "results/learned_wiring_qwen_balanced_320/results.json",
    "two_by_two": "results/two_by_two/results.json",
    "d_stage_0": "results/d_stage_0/results.json",
    "d_stage_1": "results/d_stage_1/results.json",
    "d_stage_2": "results/d_stage_2/results.json",
    "d_stage_3": "results/d_stage_3/results.json",
    "verifier": "results/verifier/results.json",
    "ttt_scaffold": "results/ttt/results.json",
}


def _path(path_text: str) -> Path:
    return REPO_ROOT / path_text


def _read_json(path_text: str) -> Any | None:
    path = _path(path_text)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(_cell(header) for header in headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return lines


def _cell(value: Any) -> str:
    if isinstance(value, float):
        text = _fmt(value)
    elif isinstance(value, (dict, list)):
        text = _compact_value(value)
    else:
        text = str(value)
    return text.replace("\n", "<br>").replace("|", "\\|")


def _fmt(value: Any, digits: int = 4) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def _mean(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)
    if isinstance(value, dict):
        return value.get("mean")
    return value


def _artifact_rows(index: dict[str, str]) -> list[list[str]]:
    return [[name, path, "yes" if _path(path).exists() else "missing"] for name, path in index.items()]


def _validation_rows(validation: dict[str, Any]) -> list[list[Any]]:
    checks = validation.get("checks", [])
    tiers = sorted({check.get("tier", "") for check in checks})
    rows = []
    for tier in tiers:
        tier_checks = [check for check in checks if check.get("tier") == tier]
        rows.append([tier, sum(check.get("status") == "PASS" for check in tier_checks), sum(check.get("status") == "FAIL" for check in tier_checks)])
    return rows


def _compact_value(value: Any) -> str:
    if value is None or isinstance(value, (bool, int, float, str)):
        return _fmt(value)
    if isinstance(value, list):
        if len(value) <= 8 and all(item is None or isinstance(item, (bool, int, float, str)) for item in value):
            return json.dumps(value, sort_keys=True)
        return f"{len(value)} items"
    if isinstance(value, dict):
        scalar_items = [(key, val) for key, val in value.items() if val is None or isinstance(val, (bool, int, float, str))]
        if 0 < len(scalar_items) <= 8 and len(scalar_items) == len(value):
            return "; ".join(f"{key}={_fmt(val)}" for key, val in scalar_items)
        return f"{len(value)} keys: {', '.join(list(value)[:8])}"
    return str(type(value).__name__)


def _short_text(value: Any, limit: int = 120) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _infer_columns(rows: list[Any]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def _markdown_result_table(name: str, table: dict[str, Any], max_rows: int = 24) -> list[str]:
    rows = table.get("rows", [])
    columns = table.get("columns") or _infer_columns(rows)
    lines = [f"##### {name}", ""]
    if not columns or not rows:
        lines.append("No rows recorded.")
        lines.append("")
        return lines
    rendered_rows = []
    for row in rows[:max_rows]:
        if isinstance(row, dict):
            rendered_rows.append([row.get(column, "") for column in columns])
        else:
            rendered_rows.append([row])
    lines.extend(_table(columns, rendered_rows))
    if len(rows) > max_rows:
        lines.append("")
        lines.append(f"Truncated to {max_rows} of {len(rows)} rows.")
    lines.append("")
    return lines


def _json_summary_rows(data: dict[str, Any]) -> list[list[str]]:
    skip = {"result_tables", "checks", "items", "steps", "detail_data", "data"}
    priority = [
        "module",
        "status",
        "verdict",
        "decision",
        "classification",
        "integration_grade",
        "passed",
        "G1",
        "single_step_forced_accuracy",
        "n_sudoku6_tasks",
        "reverts_nonzero_on_L4",
        "forward_floor_on_L4",
        "n_cells",
        "preflight_failed",
        "device",
        "num_shards",
        "model_id",
        "total_gib",
    ]
    rows: list[list[str]] = []
    seen = set()
    for key in priority:
        if key in data:
            rows.append([key, _compact_value(data[key])])
            seen.add(key)
    for key, value in data.items():
        if key in seen or key in skip:
            continue
        if value is None or isinstance(value, (bool, int, float, str)):
            rows.append([key, _compact_value(value)])
        elif key in {"summary", "gates", "verdicts", "routing", "banded_datasets", "training_curve_summary", "decision_branch", "honesty", "l4_structural_probe"}:
            rows.append([key, _compact_value(value)])
        if len(rows) >= 18:
            break
    return rows


def _list_table_lines(name: str, rows: list[Any], max_rows: int = 12) -> list[str]:
    if not rows or not all(isinstance(row, dict) for row in rows[:max_rows]):
        return []
    columns = _infer_columns(rows[:max_rows])
    if not columns:
        return []
    table = {"columns": columns, "rows": rows}
    return _markdown_result_table(name, table, max_rows=max_rows)


def _artifact_result_lines(path_text: str, payload: dict[str, Any]) -> list[str]:
    if not payload.get("embedded") or payload.get("format") != "json":
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    lines = [f"##### {path_text}", ""]
    summary_rows = _json_summary_rows(data)
    if summary_rows:
        lines.extend(_table(["field", "value"], summary_rows))
        lines.append("")
    result_tables = data.get("result_tables")
    if isinstance(result_tables, dict):
        for table_name, table in result_tables.items():
            if isinstance(table, dict):
                lines.extend(_markdown_result_table(table_name, table))
    for key in ["single_step_forced_precision_recall_by_depth", "fail_closed_cases", "capacity_estimates", "p2_tables"]:
        value = data.get(key)
        if isinstance(value, list):
            lines.extend(_list_table_lines(key, value))
        elif isinstance(value, dict) and key == "p2_tables":
            for table_name, table in value.items():
                if isinstance(table, dict):
                    lines.extend(_markdown_result_table(table_name, table))
    return lines if len(lines) > 2 else []


def _record_result_lines(record: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    contract = record.get("contract_data")
    if isinstance(contract, dict):
        result_tables = contract.get("result_tables", {})
        if isinstance(result_tables, dict) and result_tables:
            lines.extend(["#### Contract Result Tables", ""])
            for table_name, table in result_tables.items():
                if isinstance(table, dict):
                    lines.extend(_markdown_result_table(table_name, table))
    return lines


def _artifact_ref(path: str) -> dict[str, Any]:
    artifact_path = _path(path)
    ref: dict[str, Any] = {"path": path, "present": "yes" if artifact_path.exists() else "missing"}
    if artifact_path.exists():
        ref["size_bytes"] = artifact_path.stat().st_size
    return ref


def _artifact_payload(path_text: str) -> dict[str, Any]:
    path = _path(path_text)
    if not path.exists():
        return {"present": False, "path": path_text}
    payload: dict[str, Any] = {"present": True, "path": path_text, "size_bytes": path.stat().st_size}
    if path.suffix:
        payload["format"] = path.suffix.lstrip(".")
    if path.suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            payload["json_item_number"] = data.get("item_number")
            payload["json_summary"] = _json_summary_rows(data)
            payload["result_table_summaries"] = _result_table_summaries(data)
    payload.update({"embedded": False, "reason": "ref_only"})
    return payload


def _result_table_summaries(data: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    result_tables = data.get("result_tables")
    if isinstance(result_tables, dict):
        for table_name, table in result_tables.items():
            if not isinstance(table, dict):
                continue
            rows = table.get("rows", [])
            columns = table.get("columns") or _infer_columns(rows if isinstance(rows, list) else [])
            summaries.append({"table": table_name, "rows": len(rows) if isinstance(rows, list) else 0, "columns": len(columns)})
    for key in ["single_step_forced_precision_recall_by_depth", "fail_closed_cases", "capacity_estimates"]:
        value = data.get(key)
        if isinstance(value, list):
            summaries.append({"table": key, "rows": len(value), "columns": len(_infer_columns(value))})
    p2_tables = data.get("p2_tables")
    if isinstance(p2_tables, dict):
        for table_name, table in p2_tables.items():
            if isinstance(table, dict):
                rows = table.get("rows", [])
                columns = table.get("columns") or _infer_columns(rows if isinstance(rows, list) else [])
                summaries.append({"table": table_name, "rows": len(rows) if isinstance(rows, list) else 0, "columns": len(columns)})
    return summaries


def _referenced_result_rows(record: dict[str, Any], max_refs: int = 16) -> list[list[Any]]:
    contract = record.get("contract_data")
    contract_item_number = str(contract.get("item_number")) if isinstance(contract, dict) else None
    rows: list[list[Any]] = []
    detail_data = record.get("detail_data", {})
    for path_text, payload in detail_data.items():
        if not payload.get("present"):
            rows.append([path_text, "missing", "", ""])
            continue
        if contract_item_number and str(payload.get("json_item_number")) == contract_item_number:
            continue
        summary = payload.get("json_summary") or []
        table_summaries = payload.get("result_table_summaries") or []
        if not summary and not table_summaries:
            continue
        summary_map = {field: value for field, value in summary}
        status = summary_map.get("status") or summary_map.get("verdict") or summary_map.get("decision") or summary_map.get("integration_grade") or summary_map.get("passed") or "recorded"
        key_values = []
        for field, value in summary:
            if field in {"module", "status", "verdict", "decision", "integration_grade", "passed", "generated_at", "honesty", "note"}:
                continue
            key_values.append(f"{field}={_short_text(value)}")
            if len(key_values) >= 6:
                break
        table_values = [f"{table['table']}:{table['rows']}r/{table['columns']}c" for table in table_summaries[:6]]
        rows.append([path_text, _short_text(status, 80), "; ".join(key_values), "; ".join(table_values)])
        if len(rows) >= max_refs:
            break
    return rows


def _external_item_records() -> list[dict[str, Any]]:
    records = []
    for path in sorted((REPO_ROOT / "results/experiment_items").glob("item_*.json")):
        with path.open("r", encoding="utf-8") as handle:
            item = json.load(handle)
        item_number = str(item.get("item_number", path.stem))
        artifacts = list(dict.fromkeys([str(path.relative_to(REPO_ROOT)), *item.get("artifacts", [])]))
        details = [
            f"purpose={item.get('purpose')}",
            f"commands={len(item.get('commands', []))}",
            f"result_tables={list((item.get('result_tables') or {}).keys())}",
            f"honesty={item.get('honesty', {}).get('does_not_establish')}",
        ]
        return_record = {
            "item": item_number,
            "name": item.get("name", path.stem),
            "status": item.get("status", "UNKNOWN"),
            "key_result": item.get("decision", {}).get("next_step_routing", item.get("purpose", "")),
            "purpose": item.get("purpose", ""),
            "details": details,
            "artifacts": [_artifact_ref(artifact) for artifact in artifacts],
            "detail_data": {artifact: _artifact_payload(artifact) for artifact in artifacts},
            "contract_data": item,
            "next_action": item.get("decision", {}).get("next_step_routing", ""),
        }
        records.append(return_record)
    return records


def _item_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    continuation = data.get("continuation") or {}
    items = {item.get("item"): item for item in continuation.get("items", [])}
    validation = data.get("validation") or {}
    closeout = data.get("gru_closeout") or {}
    stage_a = data.get("stage_a_report") or {}
    manifest = data.get("stage_a_manifest") or {}
    perdepth = data.get("perdepth") or {}
    m2_probe = data.get("m2_probe") or {}
    m2 = data.get("m2_fix") or {}
    qwen35 = data.get("qwen35") or {}
    adapter = data.get("post025_adapter_wiring") or {}
    refusal = data.get("post026_banded_gate_refusal") or {}
    sudoku6 = data.get("post027_sudoku6_bridge") or {}
    w3 = data.get("w3_probe") or {}
    validation_summary = validation.get("summary", {})
    m2_overall = m2.get("overall", {})
    branch = m2_overall.get("branch", {})
    qwen_branch = branch.get("qwen_guess", {})
    mrv_branch = branch.get("mrv", {})
    w3_config = w3.get("config", {})
    w3_verdicts = w3.get("verdicts", {})
    refusal_cases = refusal.get("fail_closed_cases", [])
    sudoku6_gates = sudoku6.get("gates", {})

    def record(item: str, name: str, status: str, key_result: str, details: list[str], artifacts: list[str], next_action: str = "") -> dict[str, Any]:
        return {
            "item": item,
            "name": name,
            "status": status,
            "key_result": key_result,
            "details": details,
            "artifacts": [_artifact_ref(path) for path in artifacts],
            "detail_data": {path: _artifact_payload(path) for path in artifacts},
            "next_action": next_action,
        }

    records = [
        record(
            "001-018",
            "legacy scaffold and early Module 1 setup",
            "Archived",
            "Retained in reference archive; not front-page gate evidence.",
            [
                "These items belong to the old scaffold/oracle-trace era and are no longer the current front-page gate evidence.",
                "Missing legacy files remain visible in validation as legacy failures rather than being silently treated as current blockers.",
            ],
            list(LEGACY_ARCHIVE.values()),
            "Do not use these archived scaffold rows as proof of the current Stage A claim.",
        ),
        record(
            "019-020",
            "scaffold gates and old validation",
            "Demoted",
            "Constructed-true 2x2/D-stage/verifier gates moved to legacy archive.",
            [
                "The validator now reports missing legacy artifacts individually.",
                "Current validation is registry-style and does not collapse missing history into one opaque required-files failure.",
            ],
            ["analysis/validate_outputs.py", "results/validation/validation.json", "results/validation/validation.md"],
            "Keep these checks archived unless the old scaffold artifacts are intentionally regenerated.",
        ),
        record(
            "021",
            "M2.0 frozen operator probe",
            "Done",
            "verdict=NEEDS_OPERATOR_FIX; low forced recall/precision blocks direct loop.",
            [
                f"original_verdict={m2_probe.get('verdict')}",
                "Frozen Qwen current-node operator was not accepted as a direct solver component.",
                "Per-task routing discipline remains required; no ordering-only pass is accepted.",
            ],
            ["results/m2_operator_probe/report.json"],
            "Use this as negative evidence when deciding whether Qwen can carry structured propagation unaided.",
        ),
        record(
            "022",
            "M2.0 fix-rescale probe",
            "Done",
            f"verdict={m2.get('verdict')}; branch_decision={m2.get('branch_decision')}",
            [
                f"qwen_guess mean_nodes={_fmt(qwen_branch.get('mean_nodes_to_solve_or_cap'))}; invalid_guess_rate={_fmt(qwen_branch.get('invalid_guess_rate'))}",
                f"mrv mean_nodes={_fmt(mrv_branch.get('mean_nodes_to_solve_or_cap'))}; invalid_guess_rate={_fmt(mrv_branch.get('invalid_guess_rate'))}",
                f"routing={m2.get('routing')}",
            ],
            ["results/m2_operator_probe/report_fix_rescale.json", "results/m2_operator_probe/report_fix_rescale.md"],
            "Treat Qwen guess results as routing evidence, not as an autonomous pass.",
        ),
        record(
            "023",
            "Module 1 fair GRU closeout",
            "Done, not locked",
            f"classification={closeout.get('classification')}; max_ratio={_fmt(closeout.get('max_gru_to_structured_ratio'))}; lock={closeout.get('lock_structured_headline')}",
            [
                "Fair GRU grid completed and all GRU cells remained below structured frontier in the recorded closeout.",
                "Headline remains unlocked because the in-loop arbiter/Stage A proof is still unavailable.",
            ],
            ["results/gru_stack_grid_fair/results.json", "results/gru_vs_structured_closeout/results.json"],
            "Revisit only after Stage A has autonomous cells instead of parent-adapter-required stops.",
        ),
        record(
            "024",
            "Stage A reconstructed handoff",
            "Blocked",
            f"verdict={stage_a.get('verdict')}; statuses={stage_a.get('statuses')}; n_cells={stage_a.get('n_cells')}",
            [
                f"artifact_policy={manifest.get('artifact_policy')}; manifest_status={manifest.get('status')}",
                f"stage_a_statuses={stage_a.get('statuses')}; n_cells={stage_a.get('n_cells')}",
                "Parent artifacts are reconstructed in-repo but autonomous Stage A cells are still unavailable.",
            ],
            ["artifacts/stage_a/manifest.json", "results/stage_a_backtrack/report.json", "results/stage_a_backtrack/results.json"],
            "Wire the parent adapter and keep fail-closed preflight before launching autonomous solve metrics.",
        ),
        record(
            "025",
            "adapter wiring pass",
            items.get("025", {}).get("status", "missing"),
            items.get("025", {}).get("summary", "not found in continuation state"),
            [
                f"materialized_status={adapter.get('status')}; preflight_status={adapter.get('preflight_status')}; register_smoke_status={adapter.get('register_smoke_status')}",
                f"grid_cells={adapter.get('grid_cells')}; autonomous_solve_status={adapter.get('autonomous_solve_status')}",
                f"operator_exists={adapter.get('operator_ckpt', {}).get('exists')}; bridge_exists={adapter.get('bridge_decoder', {}).get('exists')}; teacher_trace_tasks={adapter.get('teacher_trace', {}).get('tasks')}",
            ],
            ["results/continuation_state/post_027.json", "results/stage_a_adapter_wiring/results.json"],
            "This is a wiring/preflight item only; it does not prove autonomous solving.",
        ),
        record(
            "026",
            "banded Sudoku9 plus gate refusal",
            items.get("026", {}).get("status", "missing"),
            items.get("026", {}).get("summary", "not found in continuation state"),
            [
                f"materialized_status={refusal.get('status')}; fail_closed_cases={len(refusal_cases)}; refused_all={bool(refusal_cases) and all(case.get('refused') for case in refusal_cases)}",
                f"sudoku9_status={refusal.get('banded_datasets', {}).get('sudoku9_status')}; sudoku9_generated_count={refusal.get('banded_datasets', {}).get('sudoku9_generated_count')}",
                f"sudoku6_status={refusal.get('banded_datasets', {}).get('sudoku6_status')}",
            ],
            ["results/continuation_state/post_027.json", "results/stage_a_banded_gate_refusal/results.json"],
            "Replace continuation-recorded Sudoku6 readiness with concrete generator/data artifacts during the G1 fix.",
        ),
        record(
            "027",
            "Sudoku6 bridge G1 pre-fix record",
            items.get("027", {}).get("status", "missing"),
            f"historical_continuation_G1={items.get('027', {}).get('g1')}; current_diagnostic_G1={sudoku6.get('G1')}",
            [
                f"materialized_status={sudoku6.get('status')}; G1={sudoku6.get('G1')}; single_step_forced_accuracy={sudoku6.get('single_step_forced_accuracy')}",
                f"gates={sudoku6_gates}",
                f"stick_reasons={sudoku6.get('iterative_stick_reason_histogram')}",
                f"teacher_trace_probe={sudoku6.get('teacher_trace_probe')}",
            ],
            ["results/continuation_state/post_027.json", "results/stage_a_sudoku6_bridge/results.json", "specs/g1_fix_spec.md"],
            "Item 032 closes the validation G1/L4 diagnostic failures; do not treat this as full autonomous Stage A proof.",
        ),
        record(
            "P0",
            "ledger and validation housekeeping",
            "Updated",
            f"validation_checks={validation_summary.get('n_checks')}; validation_passed={validation.get('passed')}",
            [
                "Canonical repo is /home/aiscuser/RECURRENT_NN; old /home/aiscuser/stage_d_llm is absent locally.",
                f"validation_pass={validation_summary.get('n_pass')}; validation_fail={validation_summary.get('n_fail')}",
                "Current validation is all-green; Stage A full autonomous proof remains a separate evidence question, not a validation failure.",
            ],
            ["CANONICAL_REPO.md", "analysis/validate_outputs.py", "results/validation/validation.json", "results/experiment_log/experiment_log.json"],
            "Keep future reports item-first and preserve explicit red checks.",
        ),
        record(
            "W3.0",
            "Qwen3.5 checkpoint pin",
            "Done",
            f"model_id={qwen35.get('model_id')}; total_gib={_fmt(qwen35.get('total_gib'))}",
            [
                f"snapshot_path={qwen35.get('snapshot_path')}",
                f"n_files={qwen35.get('n_files')}; total_bytes={qwen35.get('total_bytes')}",
                "This pins availability of the external model asset but does not run hidden-hook or propagation probes.",
            ],
            ["results/model_download/qwen3_5_4b/qwen_download.json"],
            "Use W3/P2 records before considering any Qwen3.5 integration route.",
        ),
        record(
            "P1",
            "G1 fix spec and diagnostics",
            "Diagnostic pass, autonomous grid not proven",
            f"Sudoku6 diagnostic G1={sudoku6.get('G1')}; L4_reverts={sudoku6.get('reverts_nonzero_on_L4')}; L4_forward={sudoku6.get('forward_floor_on_L4')}",
            [
                "Task A diagnosis and Task B deep-supervision bridge retrain are specified.",
                f"Current diagnostic status={sudoku6.get('status')}; single_step_forced_accuracy={sudoku6.get('single_step_forced_accuracy')}; n_sudoku6_tasks={sudoku6.get('n_sudoku6_tasks')}",
                "Stage A parent binaries are regenerated workflow artifacts, not tracked binaries.",
            ],
            ["specs/g1_fix_spec.md", "results/stage_a_adapter_wiring/results.json", "results/stage_a_banded_gate_refusal/results.json", "results/stage_a_sudoku6_bridge/results.json"],
            "Use the generated Sudoku6 diagnostic states to train/verify the learned bridge before claiming full autonomous Stage A.",
        ),
        record(
            "P2",
            "W3 Qwen3.5 probe",
            w3.get("integration_grade", "missing"),
            f"W3.0={w3_verdicts.get('W3.0_checkpoint_pin')}; survival={w3_verdicts.get('W3.1_gating_decay_stack_survival')}; native_delta={w3_verdicts.get('W3.1_native_delta_rule_as_stack_gap')}; propagation={w3_verdicts.get('W3.2_qwen3_4b_delta_table')}",
            [
                f"hidden_size={w3_config.get('hidden_size')}; layers={w3_config.get('num_hidden_layers')}; full_attention_layers={w3_config.get('full_attention_layers')}; linear_layers={w3_config.get('linear_layers')}",
                f"capacity_estimates={len(w3.get('capacity_estimates', []))}; hidden_hook={w3.get('hidden_hook_probe')}",
                f"verdicts={w3_verdicts}",
            ],
            ["specs/w3_qwen35_probe_spec.md", "results/w3_qwen35_probe/results.json", "results/w3_qwen35_probe/verdicts.json"],
            "Treat Qwen3.5 as alongside-only measured evidence unless future cached-state or larger propagation probes overturn this result.",
        ),
        record(
            "P3",
            "TRM defensive analysis",
            "Not launched",
            "No TRM checkpoint/test-set grading code is present in this repo yet.",
            [
                "TRM is allowed only as recipe guidance, never as a checkpoint inside controlled comparisons.",
                "No defensive depth-ceiling test-set artifact exists in the current workspace.",
            ],
            ["specs/g1_fix_spec.md"],
            "Create explicit TRM defensive analysis artifacts before reporting P3 evidence.",
        ),
        record(
            "Module1 law",
            "per-depth capacity",
            "Writable now",
            f"decision={perdepth.get('decision')}; open={perdepth.get('open')}; shards={perdepth.get('num_shards')}",
            [
                "Per-depth capacity law is the current Tier A quantitative anchor.",
                "K-direction is negative/nonincreasing in the recorded per-depth artifact.",
                "Bound-single and factored fitted K_eff choices are validated separately in the registry.",
            ],
            ["results/module1_capacity_perdepth_shards/results.json", "results/module1_capacity_perdepth_shards/curves.json", "results/module1_capacity_benchmark_full_shards/k_direction_corrected.json"],
            "Use this law as support for structured register capacity, not as a substitute for Stage A autonomous proof.",
        ),
    ]
    records.extend(_external_item_records())
    return records


def _item_rows(records: list[dict[str, Any]]) -> list[list[str]]:
    return [[record["item"], record["name"], record["status"], record["key_result"]] for record in records]


def _item_detail_lines(records: list[dict[str, Any]]) -> list[str]:
    lines = ["", "## Item Details", ""]
    for record in records:
        lines.extend([
            f"### Item {record['item']} - {record['name']}",
            "",
            f"- Status: {record['status']}",
            f"- Key result: {record['key_result']}",
        ])
        if record.get("purpose"):
            lines.append(f"- Purpose: {record['purpose']}")
        details = record.get("details", [])
        if details:
            lines.append("- Details:")
            lines.extend(f"  - {detail}" for detail in details)
        artifacts = record.get("artifacts", [])
        if artifacts:
            lines.append("- Artifact refs:")
            for artifact in artifacts:
                size = f", {artifact['size_bytes']} bytes" if artifact.get("size_bytes") is not None else ""
                lines.append(f"  - {artifact['path']} ({artifact['present']}{size})")
        referenced_rows = _referenced_result_rows(record)
        if referenced_rows:
            lines.extend(["#### Referenced Result Summaries", ""])
            lines.extend(_table(["artifact", "status", "key values", "tables"], referenced_rows))
            lines.append("")
        result_lines = _record_result_lines(record)
        if result_lines:
            lines.extend(result_lines)
        if record.get("next_action"):
            lines.append(f"- Next action: {record['next_action']}")
        lines.append("")
    return lines


def generate_experiment_log(output_dir: str = "results/experiment_log") -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    data = {
        "continuation": _read_json("results/continuation_state/post_027.json"),
        "readiness": _read_json("results/model_readiness/readiness.json"),
        "qwen_instruct": _read_json("results/model_download/qwen_download.json"),
        "qwen_thinking": _read_json("results/model_download/thinking/qwen_download.json"),
        "qwen35": _read_json("results/model_download/qwen3_5_4b/qwen_download.json"),
        "perdepth": _read_json("results/module1_capacity_perdepth_shards/results.json"),
        "gru_closeout": _read_json("results/gru_vs_structured_closeout/results.json"),
        "m2_probe": _read_json("results/m2_operator_probe/report.json"),
        "m2_fix": _read_json("results/m2_operator_probe/report_fix_rescale.json"),
        "stage_a_manifest": _read_json("artifacts/stage_a/manifest.json"),
        "stage_a_report": _read_json("results/stage_a_backtrack/report.json"),
        "stage_a_symbolic_results": _read_json("results/stage_a_symbolic/results.json"),
        "stage_a_symbolic_report": _read_json("results/stage_a_symbolic/report.json"),
        "post025_adapter_wiring": _read_json("results/stage_a_adapter_wiring/results.json"),
        "post026_banded_gate_refusal": _read_json("results/stage_a_banded_gate_refusal/results.json"),
        "post027_sudoku6_bridge": _read_json("results/stage_a_sudoku6_bridge/results.json"),
        "w3_probe": _read_json("results/w3_qwen35_probe/results.json"),
        "validation": _read_json("results/validation/validation.json"),
    }
    continuation = data["continuation"] or {}
    validation = data["validation"] or {}
    m2 = data["m2_fix"] or {}
    overall = m2.get("overall", {})
    qwen_branch = overall.get("branch", {}).get("qwen_guess", {})
    mrv_branch = overall.get("branch", {}).get("mrv", {})
    items = {item.get("item"): item for item in continuation.get("items", [])}
    g1 = items.get("027", {}).get("g1")
    item_records = _item_records(data)
    item_rows = _item_rows(item_records)

    tier_a = [
        "Module 1 capacity law: per-depth ceiling-free K-direction negative; bound_single best K_eff = D_over_ln_product with R2 about 0.99; factored best K_eff = D_over_ln_Kvar/max-factor with R2 about 0.98; capacity is linear in D for the measured construction.",
        "Ceiling-artifact resolution narrative for low-K frontier artifacts.",
        "Fair GRU 144-cell grid completed; all cells below structured; max GRU/structured ratio 0.9025; closeout honestly NOT_READY pending in-loop arbiter.",
        "TTT irreversibility remains real mechanism evidence when its non-scaffold artifact is present; the constructed scaffold gate is archived.",
        "M2.0 negatives: frozen Qwen operator still needs a fix; invalid qwen_guess rate and spike precision/recall asymmetry block direct loop use.",
    ]
    tier_b = [
        "Stage A diagnostic G1/L4 checks are green, but the full autonomous in-loop grid still blocks the core claim.",
        "Banded Sudoku9/6 readiness and fail-closed refusal are materialized in post-026 artifacts; Sudoku6 diagnostic data is now generated in-repo.",
        "Fail-closed preflight is proven for missing/quarantined parent paths; unsafe paths are refused.",
        "Current blocker: learned recurrent bridge/autonomous Stage A cells are not yet proven.",
    ]
    tier_c = [
        "W3 Qwen3.5 probe: checkpoint and metadata/capacity estimate are implemented; hidden-hook, gating-survival, native-delta, and W3.2 propagation probes are not launched.",
        "S2 accounting rides on the controlled relaunch.",
        "TRM defensive depth-ceiling analysis is not started.",
        "S3.1 integration is not started.",
    ]

    lines: list[str] = [
        "# RECURRENT_NN Experiment Log",
        "",
        f"Generated at: {generated_at}",
        "",
        "Scope: item-first continuation log for `/home/aiscuser/RECURRENT_NN`. Each row is an experiment item or runbook item; status summaries and artifact indices are derived context below the item ledger.",
        "",
        "## Items",
        "",
    ]
    lines.extend(_table(["item", "name", "status", "key result"], item_rows))
    lines.extend(_item_detail_lines(item_records))
    lines.extend([
        "",
        "## Canonical Repo Decision",
        "",
        "- Canonical repo: `/home/aiscuser/RECURRENT_NN`",
        "- Legacy path `/home/aiscuser/stage_d_llm`: not present locally; old commands using that path are historical provenance text.",
        "- Module 1 artifacts are referenced from the current repo only; no local duplicate `stage_d_llm/results/` tree exists to de-duplicate.",
        "",
        "## Evidence Tiers",
        "",
        "### Tier A - Writable Now",
    ])
    lines.extend(f"- {item}" for item in tier_a)
    lines.extend(["", "### Tier B - In Flight, Blocks Core Claim"])
    lines.extend(f"- {item}" for item in tier_b)
    lines.extend(["", "### Tier C - Not Started"])
    lines.extend(f"- {item}" for item in tier_c)

    lines.extend(["", "## Current Gate And Blocker Status", ""])
    lines.extend(_table(["area", "status", "evidence"], [
        ["Module 1 capacity law", "GREEN", f"decision={data.get('perdepth', {}).get('decision')}; open={data.get('perdepth', {}).get('open')}; K_eff fits recorded"],
        ["Fair GRU closeout", "YELLOW", f"classification={data.get('gru_closeout', {}).get('classification')}; max_ratio={_fmt(data.get('gru_closeout', {}).get('max_gru_to_structured_ratio'))}; headline_locked={data.get('gru_closeout', {}).get('lock_structured_headline')}"] ,
        ["M2.0 frozen Qwen operator", "RED", f"verdict={m2.get('verdict')}; list_all_recall={_fmt(_mean(overall.get('list_all', {}), 'forced_recall'))}; single_precision={_fmt(_mean(overall.get('single_iterated', {}), 'per_call_precision'))}"],
        ["Branch policy", "YELLOW", f"qwen_nodes={_fmt(qwen_branch.get('mean_nodes_to_solve_or_cap'))}; mrv_nodes={_fmt(mrv_branch.get('mean_nodes_to_solve_or_cap'))}; qwen_invalid_rate={_fmt(qwen_branch.get('invalid_guess_rate'))}"],
        ["Stage A Track A symbolic", "YELLOW", f"track={data.get('stage_a_symbolic_results', {}).get('track')}; operator={data.get('stage_a_symbolic_results', {}).get('operator')}; autonomous_cells={data.get('stage_a_symbolic_results', {}).get('n_cells')}; symbolic_core={data.get('stage_a_symbolic_report', {}).get('symbolic_core_evidence')}"],
        ["Stage A learned track", "RED", f"diagnostic_G1={data.get('post027_sudoku6_bridge', {}).get('G1', g1)}; learned_autonomous_cells={data.get('stage_a_report', {}).get('n_cells')}; statuses={data.get('stage_a_report', {}).get('statuses')}"],
        ["W3 Qwen3.5", "YELLOW", f"integration_grade={data.get('w3_probe', {}).get('integration_grade')}; W3.0={data.get('w3_probe', {}).get('verdicts', {}).get('W3.0_checkpoint_pin')}"],
        ["Validation", "RED" if not validation.get("passed") else "GREEN", f"checks={validation.get('summary', {}).get('n_checks')}; pass={validation.get('summary', {}).get('n_pass')}; fail={validation.get('summary', {}).get('n_fail')}"] ,
    ]))

    lines.extend(["", "## Artifact Index", ""])
    lines.extend(_table(["artifact", "path", "present"], _artifact_rows(ARTIFACT_INDEX)))
    lines.extend(["", "## Validation Summary", ""])
    lines.extend(_table(["tier", "pass", "fail"], _validation_rows(validation)))
    lines.extend([
        "",
        "## P0/P1/P2/P3 Execution Notes",
        "",
        "- P0.1: `RECURRENT_NN` is declared canonical in `CANONICAL_REPO.md`; the old `stage_d_llm` path is not present locally.",
        "- P0.2: validation now emits many checks, including explicit red Stage A blockers, rather than one collapsed required-files failure.",
        "- P0.3: the front page now leads with evidence tiers and current blockers; constructed scaffold gates are demoted to the legacy archive.",
        "- P1: `specs/g1_fix_spec.md` plus adapter wiring, gate refusal, and Sudoku6 bridge diagnostic artifacts are present; diagnostic G1/L4 checks pass, while learned autonomous Stage A remains unproven.",
        "- P2: `specs/w3_qwen35_probe_spec.md` and W3 Qwen3.5 measured probes are present; current result is alongside-only measured evidence, not in-state acceptance.",
        "- P3: TRM defensive analysis is not launched; no TRM checkpoint/test-set grading code is present in this repo yet.",
        "",
        "## Legacy Scaffold Archive",
        "",
        "The older 2x2, D-stage, verifier, and scaffold TTT entries are no longer front-page gate evidence. They were constructed scaffold outputs and are retained only as historical support/provenance. The real TTT irreversibility diagnostic remains Tier A mechanism evidence when its non-scaffold artifact is present.",
        "",
    ])
    lines.extend(_table(["legacy artifact", "path", "present"], _artifact_rows(LEGACY_ARCHIVE)))
    lines.extend(["", "## Standing Rules", ""])
    lines.extend(f"- {rule}" for rule in continuation.get("standing_rules", []))

    out = _path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "experiment_log.md"
    json_path = out / "experiment_log.json"
    payload = {
        "generated_at": generated_at,
        "artifact_index": ARTIFACT_INDEX,
        "legacy_archive": LEGACY_ARCHIVE,
        "evidence_tiers": {"tier_a": tier_a, "tier_b": tier_b, "tier_c": tier_c},
        "items": item_records,
        "incremental_items": item_rows,
        "validation_summary": validation.get("summary", {}),
        "current_status": {
            "canonical_repo": "/home/aiscuser/RECURRENT_NN",
            "stage_a_headline_track": "Track A symbolic-oracle evidence is declared separately from learned-track evidence",
            "stage_a_blocker": "learned autonomous Stage A cells remain unavailable; Track A symbolic L4 reverts/floor depend on measured symbolic report rows",
            "stage_a_symbolic": data.get("stage_a_symbolic_report", {}),
            "w3_qwen35_checkpoint": data.get("qwen35", {}),
            "w3_qwen35_probe": data.get("w3_probe", {}),
            "p1_launched": False,
            "p2_launched": False,
            "p3_launched": False,
        },
    }
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"markdown": str(md_path.relative_to(REPO_ROOT)), "json": str(json_path.relative_to(REPO_ROOT)), **payload}


if __name__ == "__main__":
    print(json.dumps(generate_experiment_log(), indent=2, sort_keys=True))
