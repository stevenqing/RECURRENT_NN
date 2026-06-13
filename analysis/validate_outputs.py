"""Validate the current RECURRENT_NN experiment ledger state.

This validator is intentionally registry-style: missing historical artifacts are
reported as individual red checks instead of collapsing the whole report into one
opaque `required_files_present` failure.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

PATHS = {
    "model_readiness": "results/model_readiness/readiness.json",
    "qwen3_instruct": "results/model_download/qwen_download.json",
    "qwen3_thinking": "results/model_download/thinking/qwen_download.json",
    "qwen35_4b": "results/model_download/qwen3_5_4b/qwen_download.json",
    "module1_batching": "results/module1_capacity_batching_large/results.json",
    "module1_k_corrected": "results/module1_capacity_benchmark_full_shards/k_direction_corrected.json",
    "module1_perdepth": "results/module1_capacity_perdepth_shards/results.json",
    "gru_smoke": "results/gru_stack_smoke/results.json",
    "gru_light": "results/gru_stack_grid_full/results.json",
    "gru_degeneracy": "results/gru_degeneracy_diagnostic/results.json",
    "gru_fair": "results/gru_stack_grid_fair/results.json",
    "gru_closeout": "results/gru_vs_structured_closeout/results.json",
    "m2_probe": "results/m2_operator_probe/report.json",
    "m2_fix_rescale": "results/m2_operator_probe/report_fix_rescale.json",
    "stage_a_manifest": "artifacts/stage_a/manifest.json",
    "stage_a_results": "results/stage_a_backtrack/results.json",
    "stage_a_report": "results/stage_a_backtrack/report.json",
    "stage_a_symbolic_results": "results/stage_a_symbolic/results.json",
    "stage_a_symbolic_report": "results/stage_a_symbolic/report.json",
    "stage_a_symbolic_statelessness": "results/stage_a_symbolic/oracle_statelessness_ci.json",
    "ttt_legacy": "results/ttt/results.json",
    "legacy_two_by_two": "results/two_by_two/results.json",
    "legacy_d_stage_1": "results/d_stage_1/results.json",
    "legacy_d_stage_2": "results/d_stage_2/results.json",
    "legacy_d_stage_3": "results/d_stage_3/results.json",
    "legacy_verifier": "results/verifier/results.json",
    "post025_adapter_wiring": "results/stage_a_adapter_wiring/results.json",
    "post026_banded_gate_refusal": "results/stage_a_banded_gate_refusal/results.json",
    "post027_sudoku6_bridge": "results/stage_a_sudoku6_bridge/results.json",
    "g1_fix_spec": "specs/g1_fix_spec.md",
    "w3_qwen35_probe_spec": "specs/w3_qwen35_probe_spec.md",
    "w3_qwen35_probe": "results/w3_qwen35_probe/results.json",
    "continuation_post_027": "results/continuation_state/post_027.json",
    "item_028_p0_housekeeping": "results/experiment_items/item_028_p0_housekeeping.json",
    "item_029_p1_1a_g1_diagnosis": "results/experiment_items/item_029_p1_1a_g1_diagnosis.json",
    "item_030_p2_w3_hook_capacity": "results/experiment_items/item_030_p2_w3_hook_capacity.json",
    "item_031_p2_w3_survival_delta_propagation": "results/experiment_items/item_031_p2_w3_survival_delta_propagation.json",
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
    "closeout_047_status": "results/closeout_047/status_corrections.json",
    "closeout_047_headline_figure": "results/closeout_047/headline_figure/headline_figure_certification.json",
    "closeout_047_track_b_split": "results/closeout_047/track_b_mask_commit/track_b_mask_commit_split_diagnostic.json",
    "closeout_047_gru_rerun": "results/closeout_047/gru_in_loop/gru_in_loop_r3plus_rerun.json",
    "track_b_value_head_retrain_acceptance": "results/track_b_value_head_retrain_20260609/acceptance.json",
    "post_review_e1_cross_task_generalization": "results/post_review_e1_cross_task_generalization/results.json",
    "post_review_e1_sudoku_d128_bound_single_curve": "results/post_review_e1_cross_task_generalization/sudoku_d128_bound_single_module1_curve.json",
    "rung1_distributed_graph_coloring": "results/rung1_distributed_graph_coloring/results.json",
    "rung1_gate_distributed_coloring_v01": "results/rung1_gate_distributed_coloring_v01/results.json",
    "rung1_gate_distributed_coloring_v02": "results/rung1_gate_distributed_coloring_v02/results.json",
    "rung1_phase1_spec_v01": "specs/rung1_phase1_spec_v01.md",
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
    "externalization_sudoku_adapter_preflight": "results/externalization_validation_v0/sudoku_adapter_preflight.json",
    "externalization_graph_color_oneshot_thinking_checkpoint": "results/externalization_validation_v0/graph_color_ceiling_oneshot_thinking_checkpoint.json",
    "externalization_honest_token_accounting_addendum": "results/externalization_validation_v0/honest_token_accounting_addendum.json",
    "log_item_contract_spec": "specs/log_item_contract.md",
}

LEGACY_SCAFFOLD_NAMES = (
    "legacy_two_by_two",
    "legacy_d_stage_1",
    "legacy_d_stage_2",
    "legacy_d_stage_3",
    "legacy_verifier",
)

ARCHIVED_OR_ABSENT_OK_ARTIFACTS = {PATHS[name] for name in LEGACY_SCAFFOLD_NAMES}


def _path(name: str) -> Path:
    return REPO_ROOT / PATHS[name]


def _read_json(name: str) -> Any | None:
    path = _path(name)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _check(checks: list[dict[str, Any]], condition: bool, name: str, detail: str, tier: str = "core") -> None:
    checks.append({"name": name, "status": "PASS" if condition else "FAIL", "tier": tier, "detail": detail})


def _exists(checks: list[dict[str, Any]], name: str, tier: str = "artifact") -> bool:
    path = _path(name)
    ok = path.exists()
    _check(checks, ok, f"{name}_present", str(path.relative_to(REPO_ROOT)), tier)
    return ok


def _archived_or_absent_ok(checks: list[dict[str, Any]], name: str, tier: str = "legacy") -> bool:
    path = _path(name)
    ok = not path.exists()
    detail = f"state={'absent_ok' if ok else 'regenerated_present_wrong_object'}; path={path.relative_to(REPO_ROOT)}"
    _check(checks, ok, f"{name}_archived_or_absent_ok", detail, tier)
    return ok


def _all_nonincreasing(items: list[dict[str, Any]]) -> bool:
    return bool(items) and all(all(sign <= 0 for sign in item.get("signs", [])) for item in items)


def _joint_fit(fits: list[dict[str, Any]], variant: str, replacement: str) -> dict[str, Any]:
    for fit in fits:
        if fit.get("variant") == variant and fit.get("replacement") == replacement and fit.get("metric") == "joint":
            return fit
    return {}


def _model_download_checks(checks: list[dict[str, Any]]) -> None:
    readiness = _read_json("model_readiness")
    _exists(checks, "model_readiness", "env")
    if readiness:
        _check(checks, readiness.get("transformers_available") is True, "env_transformers_available", f"value={readiness.get('transformers_available')}", "env")
        _check(checks, readiness.get("cuda_available") is True, "env_cuda_available", f"count={readiness.get('cuda_device_count')}", "env")
        _check(checks, int(readiness.get("cuda_device_count", 0)) >= 1, "env_cuda_device_count_nonzero", f"count={readiness.get('cuda_device_count')}", "env")

    for name, expected in [
        ("qwen3_instruct", "Qwen/Qwen3-4B-Instruct-2507"),
        ("qwen3_thinking", "Qwen/Qwen3-4B-Thinking-2507"),
        ("qwen35_4b", "Qwen/Qwen3.5-4B"),
    ]:
        data = _read_json(name)
        _exists(checks, name, "env")
        if data:
            _check(checks, data.get("model_id") == expected, f"{name}_model_id", f"model_id={data.get('model_id')}", "env")
            _check(checks, float(data.get("total_gib", 0.0)) > 1.0, f"{name}_download_size", f"total_gib={data.get('total_gib')}", "env")


def _module1_checks(checks: list[dict[str, Any]]) -> None:
    perdepth = _read_json("module1_perdepth")
    _exists(checks, "module1_perdepth", "tier_a")
    if perdepth:
        _check(checks, perdepth.get("device") == "8x_cuda_sharded", "module1_perdepth_sharded", f"device={perdepth.get('device')}", "tier_a")
        _check(checks, perdepth.get("num_shards") == 8, "module1_perdepth_num_shards", f"num_shards={perdepth.get('num_shards')}", "tier_a")
        _check(checks, perdepth.get("decision") == "k_direction_negative" and perdepth.get("open") is False, "module1_k_direction_negative", f"decision={perdepth.get('decision')}, open={perdepth.get('open')}", "tier_a")
        _check(checks, _all_nonincreasing(perdepth.get("directions", [])), "module1_all_k_signs_nonincreasing", "joint/var/val signs are <= 0", "tier_a")
        bound = _joint_fit(perdepth.get("fits", []), "bound_single", "with_replacement")
        factored = _joint_fit(perdepth.get("fits", []), "factored", "with_replacement")
        _check(checks, bound.get("best_k_eff") == "D_over_ln_product", "module1_bound_single_keff_product", f"best={bound.get('best_k_eff')}", "tier_a")
        _check(checks, bound.get("fits", {}).get("D_over_ln_product", {}).get("r2", 0) >= 0.98, "module1_bound_single_product_r2", f"r2={bound.get('fits', {}).get('D_over_ln_product', {}).get('r2')}", "tier_a")
        _check(checks, factored.get("best_k_eff") == "D_over_ln_Kvar", "module1_factored_keff_kvar", f"best={factored.get('best_k_eff')}", "tier_a")
        _check(checks, factored.get("fits", {}).get("D_over_ln_Kvar", {}).get("r2", 0) >= 0.97, "module1_factored_kvar_r2", f"r2={factored.get('fits', {}).get('D_over_ln_Kvar', {}).get('r2')}", "tier_a")

    corrected = _read_json("module1_k_corrected")
    _exists(checks, "module1_k_corrected", "tier_a")
    if corrected:
        _check(checks, corrected.get("expected_target_passed") is True, "module1_ceiling_artifact_corrected", f"passed={corrected.get('expected_target_passed')}", "tier_a")

    batching = _read_json("module1_batching")
    _exists(checks, "module1_batching", "tier_a")
    if batching:
        best_batches = [row.get("batch_size", 0) for row in batching.get("best_by_case", [])]
        _check(checks, any(batch >= 8192 for batch in best_batches), "module1_batching_large_recorded", f"best_batches={best_batches}", "tier_a")


def _gru_checks(checks: list[dict[str, Any]]) -> None:
    for name in ["gru_smoke", "gru_light", "gru_degeneracy", "gru_fair", "gru_closeout"]:
        _exists(checks, name, "tier_a")

    smoke = _read_json("gru_smoke")
    if smoke:
        _check(checks, smoke.get("converged") is True and smoke.get("selection") == "val_loss_min", "gru_smoke_converged", f"frontier={smoke.get('frontier_joint_095')}", "tier_a")

    fair = _read_json("gru_fair")
    if fair:
        training = fair.get("training_sufficiency", {})
        _check(checks, fair.get("n_cells") == 144, "gru_fair_144_cells", f"n_cells={fair.get('n_cells')}", "tier_a")
        _check(checks, fair.get("all_converged") is True, "gru_fair_all_converged", f"all_converged={fair.get('all_converged')}", "tier_a")
        _check(checks, training.get("all_training_sufficient") is True, "gru_fair_training_sufficient", f"training={training.get('all_training_sufficient')}", "tier_a")
        _check(checks, fair.get("all_gru_below_structured") is True, "gru_fair_below_structured", f"below={fair.get('all_gru_below_structured')}", "tier_a")

    closeout = _read_json("gru_closeout")
    if closeout:
        _check(checks, closeout.get("classification") == "NOT_READY", "gru_closeout_not_ready_honest", f"classification={closeout.get('classification')}", "tier_a")
        _check(checks, closeout.get("lock_structured_headline") is False, "gru_headline_not_locked", f"lock={closeout.get('lock_structured_headline')}", "tier_a")
        _check(checks, float(closeout.get("max_gru_to_structured_ratio", 99.0)) <= 1.0, "gru_max_ratio_below_one", f"ratio={closeout.get('max_gru_to_structured_ratio')}", "tier_a")


def _m2_checks(checks: list[dict[str, Any]]) -> None:
    m2 = _read_json("m2_probe")
    fixed = _read_json("m2_fix_rescale")
    _exists(checks, "m2_probe", "tier_a")
    _exists(checks, "m2_fix_rescale", "tier_a")
    if m2:
        _check(checks, m2.get("verdict") == "NEEDS_OPERATOR_FIX", "m2_probe_negative", f"verdict={m2.get('verdict')}", "tier_a")
        overall = m2.get("overall", {})
        _check(checks, overall.get("forced_recall", 1.0) < 0.3, "m2_probe_forced_recall_low", f"forced_recall={overall.get('forced_recall')}", "tier_a")
    if fixed:
        by_task = fixed.get("by_task", {})
        verdicts = {task: row.get("verdict") for task, row in by_task.items()}
        _check(checks, bool(by_task) and all(verdict == "NEEDS_OPERATOR_FIX" for verdict in verdicts.values()), "m2_fix_all_tasks_need_fix", f"verdicts={verdicts}", "tier_a")
        routing = fixed.get("routing", {})
        _check(checks, len(routing.get("fix_tasks", [])) == 5 and not routing.get("pass_tasks"), "m2_fix_rescale_routes_all_to_fix", f"routing={routing}", "tier_a")
        branch = fixed.get("overall", {}).get("branch", {})
        qwen = branch.get("qwen_guess", {})
        mrv = branch.get("mrv", {})
        _check(checks, qwen.get("invalid_guess_rate", 0) > 0.2, "m2_qwen_guess_invalid_rate_high", f"invalid_guess_rate={qwen.get('invalid_guess_rate')}", "tier_a")
        _check(checks, mrv.get("invalid_guess_rate") == 0.0, "m2_mrv_invalid_rate_zero", f"invalid_guess_rate={mrv.get('invalid_guess_rate')}", "tier_a")
        _check(checks, "single_iterated" in fixed.get("overall", {}) and "list_all" in fixed.get("overall", {}), "m2_iterated_and_list_all_recorded", f"overall_keys={list(fixed.get('overall', {}))}", "tier_a")


def _stage_a_checks(checks: list[dict[str, Any]]) -> None:
    manifest = _read_json("stage_a_manifest")
    results = _read_json("stage_a_results")
    report = _read_json("stage_a_report")
    symbolic_results = _read_json("stage_a_symbolic_results")
    symbolic_report = _read_json("stage_a_symbolic_report")
    symbolic_statelessness = _read_json("stage_a_symbolic_statelessness")
    continuation = _read_json("continuation_post_027")
    _exists(checks, "stage_a_manifest", "tier_b")
    _exists(checks, "stage_a_results", "tier_b")
    _exists(checks, "stage_a_report", "tier_b")
    _exists(checks, "stage_a_symbolic_results", "tier_b")
    _exists(checks, "stage_a_symbolic_report", "tier_b")
    _exists(checks, "stage_a_symbolic_statelessness", "tier_b")
    _exists(checks, "continuation_post_027", "tier_b")
    if manifest:
        _check(checks, manifest.get("status") == "READY", "stage_a_reconstructed_artifacts_ready", f"status={manifest.get('status')}", "tier_b")
        _check(checks, manifest.get("artifact_policy") == "reconstructed_in_repo_not_inherited", "stage_a_provenance_recorded", f"policy={manifest.get('artifact_policy')}", "tier_b")
    if results:
        statuses = set(results.get("statuses", []))
        _check(checks, results.get("preflight_failed") is False, "stage_a_preflight_passed", f"preflight_failed={results.get('preflight_failed')}", "tier_b")
        _check(checks, "PARENT_ADAPTER_REQUIRED" in statuses, "stage_a_parent_adapter_blocker_present", f"statuses={sorted(statuses)}", "tier_b")
        _check(checks, results.get("n_cells") == 0, "stage_a_no_autonomous_cells_yet", f"n_cells={results.get('n_cells')}", "tier_b")
    if report:
        _check(checks, report.get("verdict") == "NEEDS_REVIEW", "stage_a_report_needs_review", f"verdict={report.get('verdict')}", "tier_b")
    if continuation:
        items = {item.get("item"): item for item in continuation.get("items", [])}
        _check(checks, items.get("027", {}).get("g1") == 0.0, "stage_a_sudoku6_g1_zero_recorded", f"g1={items.get('027', {}).get('g1')}", "tier_b")

    _exists(checks, "g1_fix_spec", "tier_b")
    for name in ["post025_adapter_wiring", "post026_banded_gate_refusal", "post027_sudoku6_bridge"]:
        _exists(checks, name, "tier_b")
    adapter = _read_json("post025_adapter_wiring")
    if adapter:
        _check(checks, adapter.get("status") == "PASS", "post025_adapter_wiring_pass", f"status={adapter.get('status')}", "tier_b")
    refusal = _read_json("post026_banded_gate_refusal")
    if refusal:
        cases = refusal.get("fail_closed_cases", [])
        _check(checks, refusal.get("status") == "PASS" and cases and all(row.get("refused") for row in cases), "post026_gate_refusal_pass", f"status={refusal.get('status')}; cases={len(cases)}", "tier_b")
    sudoku6 = _read_json("post027_sudoku6_bridge")
    operator_type = sudoku6.get("operator_type") if sudoku6 else None
    g1 = float(sudoku6.get("G1", 0.0)) if sudoku6 else 0.0
    _check(
        checks,
        bool(sudoku6) and operator_type == "learned_recurrent" and g1 >= 0.95,
        "stage_a_g1_pass",
        f"operator_type={operator_type}; G1={g1}; required_operator_type=learned_recurrent; required_G1>=0.95",
        "tier_b",
    )
    _check(
        checks,
        bool(sudoku6) and operator_type == "symbolic_baseline" and g1 > 0.0,
        "stage_a_symbolic_control_pass",
        f"operator_type={operator_type}; G1={g1}",
        "tier_b",
    )
    l4_probe = sudoku6.get("l4_structural_probe", {}) if sudoku6 else {}
    l4_source = l4_probe.get("source") or sudoku6.get("source") if sudoku6 else None
    l4_run_id = l4_probe.get("run_id") or sudoku6.get("run_id") if sudoku6 else None
    real_grid_cells = int(l4_probe.get("real_grid_cells") or sudoku6.get("stage_a_autonomous_cells") or 0) if sudoku6 else 0
    autonomous_l4_source = l4_source == "autonomous_stage_a_run" and bool(l4_run_id) and real_grid_cells > 0
    _check(
        checks,
        bool(sudoku6) and sudoku6.get("reverts_nonzero_on_L4") is True and autonomous_l4_source,
        "stage_a_reverts_nonzero_on_L4",
        f"source={l4_source}; run_id={l4_run_id}; real_grid_cells={real_grid_cells}; required_source=autonomous_stage_a_run",
        "tier_b",
    )
    _check(
        checks,
        bool(sudoku6) and sudoku6.get("forward_floor_on_L4") is True and autonomous_l4_source,
        "stage_a_forward_floor_on_L4",
        f"source={l4_source}; run_id={l4_run_id}; real_grid_cells={real_grid_cells}; required_source=autonomous_stage_a_run",
        "tier_b",
    )
    _check(
        checks,
        bool(sudoku6) and l4_source == "fixture" and sudoku6.get("reverts_nonzero_on_L4") is True and sudoku6.get("forward_floor_on_L4") is True,
        "stage_a_l4_harness_fixture_pass",
        f"source={l4_source}; reverts={sudoku6.get('reverts_nonzero_on_L4') if sudoku6 else None}; forward={sudoku6.get('forward_floor_on_L4') if sudoku6 else None}",
        "tier_b",
    )

    symbolic_core = symbolic_report.get("symbolic_core_evidence", {}) if symbolic_report else {}
    symbolic_cells = int(symbolic_core.get("autonomous_cells") or (symbolic_results.get("n_cells", 0) if symbolic_results else 0))
    symbolic_track_ok = symbolic_results and symbolic_results.get("track") == "A_symbolic" and symbolic_results.get("operator") == "symbolic_oracle"
    symbolic_cell_rows = symbolic_results.get("cells", []) if symbolic_results else []
    labels_ok = bool(symbolic_cell_rows) and all(row.get("track") == "A_symbolic" and row.get("operator") == "symbolic_oracle" and row.get("source") == "autonomous_stage_a_run" for row in symbolic_cell_rows)
    _check(
        checks,
        bool(symbolic_statelessness) and symbolic_statelessness.get("status") == "PASS" and symbolic_statelessness.get("byte_identical_outputs") is True,
        "stage_a_symbolic_oracle_stateless_ci",
        f"status={symbolic_statelessness.get('status') if symbolic_statelessness else None}; byte_identical={symbolic_statelessness.get('byte_identical_outputs') if symbolic_statelessness else None}",
        "tier_b",
    )
    _check(
        checks,
        bool(symbolic_track_ok) and labels_ok,
        "stage_a_track_labels_symbolic",
        f"top_track={symbolic_results.get('track') if symbolic_results else None}; top_operator={symbolic_results.get('operator') if symbolic_results else None}; labeled_cells={len(symbolic_cell_rows)}",
        "tier_b",
    )
    _check(
        checks,
        bool(symbolic_track_ok) and symbolic_cells > 0,
        "stage_a_autonomous_cells_symbolic",
        f"track={symbolic_results.get('track') if symbolic_results else None}; operator={symbolic_results.get('operator') if symbolic_results else None}; autonomous_cells={symbolic_cells}",
        "tier_b",
    )
    _check(
        checks,
        bool(symbolic_core) and bool(symbolic_results) and symbolic_core.get("reverts_nonzero_on_L4") is True and symbolic_results.get("source") == "autonomous_stage_a_run",
        "stage_a_symbolic_reverts_nonzero_on_L4",
        f"track={symbolic_core.get('declared_track')}; source={symbolic_results.get('source') if symbolic_results else None}; reverts={symbolic_core.get('reverts_nonzero_on_L4')}; autonomous_cells={symbolic_cells}",
        "tier_b",
    )
    _check(
        checks,
        bool(symbolic_core) and bool(symbolic_results) and symbolic_core.get("forward_floor_on_L4") is True and symbolic_results.get("source") == "autonomous_stage_a_run",
        "stage_a_symbolic_forward_floor_on_L4",
        f"track={symbolic_core.get('declared_track')}; source={symbolic_results.get('source') if symbolic_results else None}; forward_floor={symbolic_core.get('forward_floor_on_L4')}; kv_depth={symbolic_core.get('kv_snapshot_max_depth')}; no_revert_depth={symbolic_core.get('rot_no_revert_max_depth')}",
        "tier_b",
    )
    stage_a_autonomous_cells = int(results.get("n_cells", 0)) if results else 0
    declared_track_core_cells = stage_a_autonomous_cells + (symbolic_cells if symbolic_track_ok else 0)
    _check(
        checks,
        declared_track_core_cells > 0,
        "all_green_requires_core_evidence",
        f"learned_autonomous_cells={stage_a_autonomous_cells}; symbolic_autonomous_cells={symbolic_cells if symbolic_track_ok else 0}; declared_track_core_cells={declared_track_core_cells}",
        "meta",
    )


def _w3_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "w3_qwen35_probe_spec", "tier_c")
    _exists(checks, "w3_qwen35_probe", "tier_c")
    probe = _read_json("w3_qwen35_probe")
    if probe:
        verdicts = probe.get("verdicts", {})
        measured_object = probe.get("measured_object")
        true_object = measured_object == "cached_gdn_recurrent_state"
        wrong_object_reason = "wrong_object" if measured_object == "prompt_hidden" else "missing_or_unrecognized_measured_object"
        _check(checks, probe.get("model_id") == "Qwen/Qwen3.5-4B", "w3_qwen35_model_id", f"model_id={probe.get('model_id')}", "tier_c")
        _check(checks, verdicts.get("W3.0_checkpoint_pin") == "PASS", "w3_checkpoint_pin_pass", f"verdict={verdicts.get('W3.0_checkpoint_pin')}", "tier_c")
        _check(checks, true_object, "w3_measured_object_cached_gdn_state", f"measured_object={measured_object}; reason={wrong_object_reason}", "tier_c")
        _check(checks, true_object and probe.get("integration_grade") != "alongside_only_measured_not_in_state", "w3_integration_grade_reissued_on_true_state", f"integration_grade={probe.get('integration_grade')}; measured_object={measured_object}", "tier_c")
        hook = probe.get("hidden_hook_probe", {})
        tables = probe.get("p2_tables", {})
        capacity_rows = tables.get("capacity_at_real_gdn_dims", {}).get("rows", [])
        survival_rows = tables.get("decay_survival", {}).get("rows", [])
        native_rows = tables.get("native_rule_gap", {}).get("rows", [])
        propagation_rows = tables.get("propagation_per_task_delta", {}).get("rows", [])
        measured_capacity_rows = [
            row for row in capacity_rows
            if str(row.get("provenance", "")).startswith("measured:")
            and int(row.get("state_rows") or 0) == 128
            and int(row.get("state_cols") or 0) == 128
            and int(row.get("heads") or 0) in {1, 2, 4, 8}
            and "cached_state_probe.inventory" in str(row.get("matrix_geometry_source", ""))
        ]
        measured_capacity_families = {row.get("task_family") for row in measured_capacity_rows}
        _check(
            checks,
            true_object and {"sudoku_6x6", "sudoku_9x9"}.issubset(measured_capacity_families) and len(measured_capacity_rows) >= 8,
            "w3_capacity_true_state_dims_measured",
            f"verdict={verdicts.get('W3.1_capacity_at_real_gdn_dims')}; measured_rows={len(measured_capacity_rows)}; families={sorted(measured_capacity_families)}; measured_object={measured_object}",
            "tier_c",
        )
        _check(checks, true_object and hook.get("state_hook_round_trip", {}).get("perturbation_affected_next_step") is True, "w3_cached_state_round_trip", f"round_trip={hook.get('state_hook_round_trip')}; measured_object={measured_object}", "tier_c")
        _check(checks, true_object and bool(survival_rows) and verdicts.get("W3.1_gating_decay_stack_survival") != "MEASURED_PROMPT_HIDDEN_SURVIVAL_NOT_CACHED_STATE", "w3_cached_state_survival_measured", f"verdict={verdicts.get('W3.1_gating_decay_stack_survival')}; rows={len(survival_rows)}; measured_object={measured_object}", "tier_c")
        _check(checks, true_object and bool(native_rows) and verdicts.get("W3.1_native_delta_rule_as_stack_gap") != "MEASURED_NATIVE_HIDDEN_DELTA_GAP", "w3_cached_state_native_rule_gap_measured", f"verdict={verdicts.get('W3.1_native_delta_rule_as_stack_gap')}; rows={len(native_rows)}; measured_object={measured_object}", "tier_c")
        _check(checks, verdicts.get("W3.2_qwen3_4b_delta_table") != "MEASURED_MIXED_SCALE_PROPAGATION_DELTA_NOT_ACCEPTED", "w3_propagation_scale_not_mixed", f"verdict={verdicts.get('W3.2_qwen3_4b_delta_table')}", "tier_c")
        if verdicts.get("W3.2_qwen3_4b_delta_table") in {"MEASURED_SMALL_PROPAGATION_DELTA_NOT_ACCEPTED", "MEASURED_50X2_PROPAGATION_DELTA_NOT_ACCEPTED"}:
            _check(checks, bool(propagation_rows) and all(row.get("qwen35_verdict") for row in propagation_rows), "w3_propagation_per_task_delta_measured", f"rows={len(propagation_rows)}", "tier_c")


def _item_contract_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "log_item_contract_spec", "contract")
    item_dir = REPO_ROOT / "results/experiment_items"
    item_paths = sorted(item_dir.glob("item_*.json")) if item_dir.exists() else []
    _check(checks, bool(item_paths), "log_item_artifacts_present", f"count={len(item_paths)}", "contract")
    required_top = [
        "schema_version",
        "item_number",
        "name",
        "purpose",
        "code_added_used",
        "commands",
        "artifacts",
        "provenance",
        "result_tables",
        "honesty",
        "decision",
    ]
    for path in item_paths:
        with path.open("r", encoding="utf-8") as handle:
            item = json.load(handle)
        item_number = str(item.get("item_number", path.stem))
        missing = [field for field in required_top if field not in item]
        _check(checks, not missing, f"log_item_{item_number}_required_fields", f"missing={missing}", "contract")
        _check(checks, item.get("schema_version") == "log_item_contract_v1", f"log_item_{item_number}_schema_version", f"schema={item.get('schema_version')}", "contract")
        try:
            number_ok = int(item_number) >= 28
        except ValueError:
            number_ok = False
        _check(checks, number_ok, f"log_item_{item_number}_number_continues_from_028", f"item_number={item_number}", "contract")
        artifact_paths = item.get("artifacts", [])
        missing_artifacts = [artifact for artifact in artifact_paths if not (REPO_ROOT / artifact).exists() and artifact not in ARCHIVED_OR_ABSENT_OK_ARTIFACTS]
        archived_or_absent = [artifact for artifact in artifact_paths if not (REPO_ROOT / artifact).exists() and artifact in ARCHIVED_OR_ABSENT_OK_ARTIFACTS]
        _check(checks, not missing_artifacts, f"log_item_{item_number}_artifacts_exist", f"missing={missing_artifacts}; archived_or_absent_ok={archived_or_absent}", "contract")
        honesty = item.get("honesty", {})
        _check(checks, bool(honesty.get("does_not_establish")), f"log_item_{item_number}_honesty_does_not_establish", str(honesty.get("does_not_establish", ""))[:160], "contract")
        decision = item.get("decision", {})
        _check(checks, bool(decision.get("gate_outcomes")) and bool(decision.get("next_step_routing")), f"log_item_{item_number}_decision_numbers_and_routing", f"gates={len(decision.get('gate_outcomes', []))}; routing={decision.get('next_step_routing')}", "contract")

    item028 = _read_json("item_028_p0_housekeeping")
    _exists(checks, "item_028_p0_housekeeping", "contract")
    if item028:
        tables = item028.get("result_tables", {})
        for table_name in ["validation_registry_before_after", "ledger_reconciliation", "report_front_page"]:
            table = tables.get(table_name, {})
            _check(checks, bool(table.get("columns")) and bool(table.get("rows")), f"item_028_{table_name}_present", f"rows={len(table.get('rows', []))}", "contract")
        validation_table = tables.get("validation_registry_before_after", {})
        after_rows = [row for row in validation_table.get("rows", []) if row.get("phase") == "after_restored_registry"]
        after = after_rows[0] if after_rows else {}
        _check(checks, int(after.get("total_check_count", 0)) >= 80, "item_028_validation_registry_many_checks", f"after={after}", "contract")
        reconciliation = tables.get("ledger_reconciliation", {})
        requirements = {row.get("requirement"): row.get("status") for row in reconciliation.get("rows", [])}
        _check(checks, all(requirements.get(key) == "yes" for key in ["item_025_folded", "item_026_folded", "item_027_folded"]), "item_028_items_025_027_folded", f"requirements={requirements}", "contract")

    item029 = _read_json("item_029_p1_1a_g1_diagnosis")
    _exists(checks, "item_029_p1_1a_g1_diagnosis", "contract")
    if item029:
        tables = item029.get("result_tables", {})
        for table_name in ["training_curve_summary", "single_step_forced_precision_recall_by_depth", "iterative_stick_reason_histogram", "train_vs_eval_encoding_byte_diff", "decision_branch"]:
            table = tables.get(table_name, {})
            _check(checks, bool(table.get("columns")) and bool(table.get("rows")), f"item_029_{table_name}_present", f"rows={len(table.get('rows', []))}", "contract")
        branch_rows = tables.get("decision_branch", {}).get("rows", [])
        branch = branch_rows[0].get("branch") if branch_rows else None
        _check(checks, branch in {"objective_wiring", "commit_criterion", "budget"}, "item_029_decision_branch_valid", f"branch={branch}", "contract")

    item030 = _read_json("item_030_p2_w3_hook_capacity")
    _exists(checks, "item_030_p2_w3_hook_capacity", "contract")
    if item030:
        tables = item030.get("result_tables", {})
        for table_name in ["model_card", "state_hook_round_trip", "capacity_at_real_gdn_dims", "decay_survival", "native_rule_gap", "propagation_per_task_delta", "verdicts_echo"]:
            table = tables.get(table_name, {})
            _check(checks, bool(table), f"item_030_{table_name}_present", f"keys={list(table) if isinstance(table, dict) else type(table)}", "contract")
        state_rows = tables.get("state_hook_round_trip", {}).get("rows", [])
        affected = state_rows[0].get("perturbation_affected_next_step") if state_rows else None
        _check(checks, affected is True, "item_030_state_hook_round_trip_positive", f"affected={affected}", "contract")
        _check(checks, item030.get("status") == "PARTIAL_NOT_ACCEPTED", "item_030_marked_partial_not_complete", f"status={item030.get('status')}", "contract")

    item031 = _read_json("item_031_p2_w3_survival_delta_propagation")
    _exists(checks, "item_031_p2_w3_survival_delta_propagation", "contract")
    if item031:
        tables = item031.get("result_tables", {})
        for table_name in ["decay_survival", "native_rule_gap", "propagation_per_task_delta", "decision_summary"]:
            table = tables.get(table_name, {})
            _check(checks, bool(table.get("columns")) and bool(table.get("rows")), f"item_031_{table_name}_present", f"rows={len(table.get('rows', []))}", "contract")
        decision_rows = tables.get("decision_summary", {}).get("rows", [])
        integration_rows = [row for row in decision_rows if row.get("gate") == "integration_grade"]
        decision = integration_rows[0].get("outcome") if integration_rows else None
        _check(checks, decision == "alongside_only_measured_not_in_state", "item_031_no_in_state_overclaim", f"integration_grade={decision}", "contract")
        _check(checks, item031.get("status") == "MEASURED_NOT_ACCEPTED", "item_031_marked_measured_not_accepted", f"status={item031.get('status')}", "contract")


def _legacy_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "ttt_legacy", "legacy")
    for name in LEGACY_SCAFFOLD_NAMES:
        _archived_or_absent_ok(checks, name, "legacy")
    ttt = _read_json("ttt_legacy")
    if ttt:
        _check(checks, ttt.get("ttt_restore_error", 0) > ttt.get("structured_restore_error", 0), "ttt_irreversibility_real", f"ttt={ttt.get('ttt_restore_error')}, structured={ttt.get('structured_restore_error')}", "legacy")


def _closeout_047_checks(checks: list[dict[str, Any]]) -> None:
    corrected_track_b_label = "VALUE_HEAD_COMMIT_CONJUNCTION_BUG_DIAGNOSED_ONE_RETRAIN_ALLOWED_NO_DAGGER_RL"
    wrong_track_b_labels = {
        "CLOSE_AS_TARGET_METRIC_OR_OPERATOR_LEARNABILITY_FINDING_NO_DAGGER_RL",
        "MASK_HEAD_LOW_CLOSE_AS_OPERATOR_LEARNABILITY_FINDING_NO_DAGGER_RL",
    }
    _exists(checks, "item_048_item047_headline_closeout", "closeout_047")
    status = _read_json("closeout_047_status")
    figure = _read_json("closeout_047_headline_figure")
    track_b = _read_json("closeout_047_track_b_split")
    gru = _read_json("closeout_047_gru_rerun")
    _exists(checks, "closeout_047_status", "closeout_047")
    _exists(checks, "closeout_047_headline_figure", "closeout_047")
    if status:
        labels = status.get("labels", {})
        _check(checks, labels.get("rot_vs_no_revert_causal_result") == "SOLID", "item047_rot_vs_no_revert_solid", f"label={labels.get('rot_vs_no_revert_causal_result')}", "closeout_047")
        _check(checks, labels.get("gru_rows_quotable") is True, "item047_gru_in_loop_audit_pass", f"gru_label={labels.get('gru_in_loop_arm')}; quotable={labels.get('gru_rows_quotable')}", "closeout_047")
        _check(checks, labels.get("track_b") == corrected_track_b_label, "item047_track_b_value_commit_bug_label", f"track_b_label={labels.get('track_b')}", "closeout_047")
        _check(checks, labels.get("headline_figure") == "HEADLINE_FIGURE_CERTIFIED", "item047_headline_figure_certified", f"headline_figure={labels.get('headline_figure')}", "closeout_047")
    if figure:
        figure_checks = figure.get("checks", {})
        _check(checks, figure.get("status") == "HEADLINE_FIGURE_CERTIFIED_WITH_FACTORED_CODEBOOK_FOOTNOTE", "item047_overlay_certified_with_footnote", f"status={figure.get('status')}", "closeout_047")
        _check(checks, figure_checks.get("spill_off_solve_matches_depth_le_dstar") is True, "item047_spilloff_matches_dstar", f"value={figure_checks.get('spill_off_solve_matches_depth_le_dstar')}", "closeout_047")
        _check(checks, figure_checks.get("spill_on_overflow_entries_match_depth_minus_dstar") is True, "item047_spillon_overflow_accounted", f"value={figure_checks.get('spill_on_overflow_entries_match_depth_minus_dstar')}", "closeout_047")
    if track_b:
        _check(checks, track_b.get("status") == corrected_track_b_label, "item047_track_b_split_corrected_label", f"status={track_b.get('status')}", "closeout_047")
        _check(checks, track_b.get("status") not in wrong_track_b_labels, "item047_track_b_wrong_labels_absent", f"status={track_b.get('status')}", "closeout_047")
        rows = track_b.get("result_tables", {}).get("mask_only_vs_full_commit_pr", {}).get("rows", [])
        splits = {row.get("split") for row in rows}
        _check(checks, {"train", "eval"}.issubset(splits), "item047_track_b_mask_full_train_eval_present", f"splits={sorted(splits)}", "closeout_047")
        eval_rows = [row for row in rows if row.get("split") == "eval"]
        if eval_rows:
            eval_row = eval_rows[0]
            mask_high = float(eval_row.get("mask_only_precision") or 0.0) >= 0.8 and float(eval_row.get("mask_only_recall") or 0.0) >= 0.8
            full_low = float(eval_row.get("full_commit_precision") or 0.0) < 0.9 or float(eval_row.get("full_commit_recall") or 0.0) < 0.9
            _check(checks, mask_high and full_low, "item047_track_b_mask_high_full_commit_low", f"eval_mask_p={eval_row.get('mask_only_precision')}; eval_mask_r={eval_row.get('mask_only_recall')}; eval_full_p={eval_row.get('full_commit_precision')}; eval_full_r={eval_row.get('full_commit_recall')}", "closeout_047")
    else:
        _check(checks, False, "item047_track_b_mask_full_train_eval_present", "diagnosis_pending; artifact not written yet", "closeout_047")
    if gru:
        rows = gru.get("result_tables", {}).get("gru_r3plus_rerun", {}).get("rows", [])
        audit_ok = bool(rows) and all(row.get("gru_audit_pass") is True and int(row.get("peak_register_bytes") or 0) > 0 and row.get("gru_training_curve_ref") and row.get("gru_converged") is True for row in rows)
        _check(checks, audit_ok, "item047_gru_rows_real_bytes_curve_converged", f"rows={len(rows)}; status={gru.get('status')}", "closeout_047")
    else:
        _check(checks, False, "item047_gru_rows_real_bytes_curve_converged", "INCOMPLETE_AUDIT_RED; GRU in-loop rerun artifact not written yet", "closeout_047")


def _track_b_value_head_retrain_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_049_track_b_value_head_retrain", "track_b_value_head")
    _exists(checks, "track_b_value_head_retrain_acceptance", "track_b_value_head")
    acceptance = _read_json("track_b_value_head_retrain_acceptance")
    item = _read_json("item_049_track_b_value_head_retrain")
    if acceptance:
        _check(checks, acceptance.get("attempt_count") == 1, "track_b_value_head_single_attempt", f"attempt_count={acceptance.get('attempt_count')}", "track_b_value_head")
        _check(checks, acceptance.get("no_second_retrain") is True and acceptance.get("no_dagger_rl") is True, "track_b_value_head_no_second_no_dagger", f"no_second={acceptance.get('no_second_retrain')}; no_dagger_rl={acceptance.get('no_dagger_rl')}", "track_b_value_head")
        _check(checks, acceptance.get("headline_locked_without_track_b") is True, "track_b_value_head_off_critical_path", f"headline_locked_without_track_b={acceptance.get('headline_locked_without_track_b')}", "track_b_value_head")
        rows = acceptance.get("result_tables", {}).get("seed_acceptance_summary", {}).get("rows", [])
        seeds = {row.get("seed") for row in rows if row.get("present")}
        _check(checks, seeds == {102, 137, 256}, "track_b_value_head_three_seed_acceptances", f"seeds={sorted(seeds)}", "track_b_value_head")
        has_tau_and_pr = bool(rows) and all(row.get("calibrated_tau") is not None and row.get("eval_mask_only_precision") is not None and row.get("eval_full_commit_precision") is not None for row in rows)
        _check(checks, has_tau_and_pr, "track_b_value_head_tau_and_pr_recorded", f"rows={len(rows)}", "track_b_value_head")
        status = acceptance.get("status")
        allowed = {"TRACK_B_VALUE_HEAD_RETRAIN_GATE_PASSED", "APPENDIX_VALUE_HEAD_LEARNABILITY_FINDING_NO_SECOND_RETRAIN_NO_DAGGER_RL"}
        _check(checks, status in allowed, "track_b_value_head_gate_or_appendix_decision", f"status={status}", "track_b_value_head")
        if status != "TRACK_B_VALUE_HEAD_RETRAIN_GATE_PASSED":
            _check(checks, all(not bool(row.get("G1_pass")) for row in rows), "track_b_value_head_nonpassing_reflected", f"G1_passes={[row.get('G1_pass') for row in rows]}", "track_b_value_head")
    if item:
        _check(checks, item.get("item_number") == "049", "item049_number_present", f"item_number={item.get('item_number')}", "track_b_value_head")


def _post_review_e1_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_050_post_review_e1_cross_task_generalization", "post_review_e1")
    _exists(checks, "post_review_e1_cross_task_generalization", "post_review_e1")
    item = _read_json("item_050_post_review_e1_cross_task_generalization")
    results = _read_json("post_review_e1_cross_task_generalization")
    sudoku_d128_curve = _read_json("post_review_e1_sudoku_d128_bound_single_curve")
    allowed_statuses = {"E1_SCALAR_FIGURE4_READY_WITH_GRU_AUDIT_RED", "E1_SCALAR_FIGURE4_DEVIATION_RECORDED"}
    _exists(checks, "post_review_e1_sudoku_d128_bound_single_curve", "post_review_e1")
    if item:
        _check(checks, item.get("item_number") == "050", "item050_number_present", f"item_number={item.get('item_number')}", "post_review_e1")
        _check(checks, item.get("status") in allowed_statuses, "item050_scalar_status", f"status={item.get('status')}", "post_review_e1")
        gates = item.get("decision", {}).get("gate_outcomes", [])
        gate_map = {row.get("gate"): row.get("outcome") for row in gates}
        _check(checks, gate_map.get("stateless_oracle_ci") == "PASS", "item050_stateless_gate_pass", f"gates={gate_map}", "post_review_e1")
        _check(checks, gate_map.get("small_d_knee_exercised") == "PASS", "item050_small_d_knee_gate_pass", f"gates={gate_map}", "post_review_e1")
        _check(checks, gate_map.get("storage_dstar_measured") == "PASS", "item050_storage_dstar_gate_pass", f"gates={gate_map}", "post_review_e1")
        _check(checks, gate_map.get("gru_audit") == "INCOMPLETE_AUDIT_RED", "item050_gru_audit_red_gate", f"gates={gate_map}", "post_review_e1")
        if item.get("status") == "E1_SCALAR_FIGURE4_DEVIATION_RECORDED":
            _check(checks, "FAIL" in gate_map.values(), "item050_deviation_gate_recorded", f"gates={gate_map}", "post_review_e1")
    if results:
        status = results.get("status")
        discipline = results.get("discipline", {})
        task_rows = results.get("task_pool_summary", [])
        node_caps = {row.get("task"): row.get("node_cap") for row in task_rows}
        stateless_rows = results.get("stateless_oracle_ci", [])
        figure_rows = results.get("figure4_separation", [])
        law_rows = results.get("law_transfer", [])
        live_load_rows = results.get("live_load_predictors", [])
        live_load_law_rows = results.get("live_load_predictor_law_transfer", [])
        live_load_summary = results.get("live_load_predictor_summary", [])
        sudoku_live_rows = results.get("sudoku_live_load_predictors", [])
        sudoku_confirmation_rows = results.get("sudoku_live_load_confirmation", [])
        sudoku_summary = results.get("sudoku_live_load_summary", [])
        compositional_rules = results.get("compositional_read_rules", [])
        compositional_product_rows = results.get("compositional_product_predictions", [])
        compositional_law_rows = results.get("compositional_product_law_transfer", [])
        compositional_summary = results.get("compositional_product_summary", [])
        sudoku_comp_curve_rows = results.get("sudoku_compositional_storage_curve", [])
        sudoku_comp_trace_rows = results.get("sudoku_compositional_trace_subsample", [])
        sudoku_comp_product_rows = results.get("sudoku_compositional_product_predictions", [])
        sudoku_comp_law_rows = results.get("sudoku_compositional_law_transfer", [])
        sudoku_comp_summary = results.get("sudoku_compositional_summary", [])
        episode_rows = results.get("episode_records", [])
        depth_hist_rows = results.get("required_depth_histogram", [])
        small_d_selection = results.get("small_d_selection", [])
        storage_rows = results.get("storage_dstar_summary", [])
        storage_curve_rows = results.get("storage_dstar_curve", [])
        d_grid = results.get("generation_config", {}).get("D_grid", [])
        acceptance = results.get("acceptance", {})
        _check(checks, discipline.get("binning_key") == "reverts_needed", "e1_bins_by_reverts_needed", f"binning_key={discipline.get('binning_key')}", "post_review_e1")
        _check(checks, discipline.get("law_transfer_depth_key") == "required_depth", "e1_law_uses_required_depth", f"law_transfer_depth_key={discipline.get('law_transfer_depth_key')}", "post_review_e1")
        _check(checks, discipline.get("law_transfer_d_star_source") == "measured_pure_storage_frontier", "e1_law_uses_measured_dstar", f"law_transfer_d_star_source={discipline.get('law_transfer_d_star_source')}", "post_review_e1")
        _check(checks, status in allowed_statuses, "e1_scalar_status", f"status={status}", "post_review_e1")
        _check(checks, discipline.get("source") == "autonomous_stage_a_run", "e1_autonomous_source", f"source={discipline.get('source')}", "post_review_e1")
        _check(checks, discipline.get("batched_engine_required") is False, "e1_no_batched_engine_required", f"batched_engine_required={discipline.get('batched_engine_required')}", "post_review_e1")
        _check(checks, discipline.get("batched_equivalence_gate_applies") is False, "e1_no_batched_equivalence_gate", f"batched_equivalence_gate_applies={discipline.get('batched_equivalence_gate_applies')}", "post_review_e1")
        _check(checks, {64, 96, 128, 256, 512}.issubset(set(d_grid)), "e1_small_d_grid_present", f"D_grid={d_grid}", "post_review_e1")
        _check(checks, bool(small_d_selection) and any(row.get("include_D32") is True for row in small_d_selection) and 32 in d_grid, "e1_d32_adaptive_rule_recorded", f"D_grid={d_grid}; rows={small_d_selection}", "post_review_e1")
        _check(checks, node_caps == {"sat_3sat": 162, "graph_coloring": 144}, "e1_item050_node_caps_reused", f"node_caps={node_caps}", "post_review_e1")
        _check(checks, bool(task_rows) and all(row.get("selected_instances") == 256 and row.get("pool_complete") is True for row in task_rows), "e1_item050_pools_reused", f"rows={task_rows}", "post_review_e1")
        _check(checks, bool(stateless_rows) and {row.get("task") for row in stateless_rows} == {"sat_3sat", "graph_coloring"} and all(row.get("passed") is True for row in stateless_rows), "e1_stateless_oracle_ci_pass", f"rows={len(stateless_rows)}", "post_review_e1")
        _check(checks, all(row.get("source") == "autonomous_stage_a_run" and row.get("provenance") == "autonomous_stage_a_run" for row in stateless_rows), "e1_stateless_rows_sourced", f"rows={len(stateless_rows)}", "post_review_e1")
        band_rows = results.get("band_summary", [])
        band_keys_ok = bool(band_rows) and all("min_reverts_needed" in row and "max_reverts_needed" in row for row in band_rows)
        _check(checks, band_keys_ok, "e1_band_rows_revert_metrics_present", f"rows={len(band_rows)}", "post_review_e1")
        hist_tasks = {(row.get("task"), row.get("band")) for row in depth_hist_rows}
        _check(checks, bool(depth_hist_rows) and hist_tasks == {(task, band) for task in {"sat_3sat", "graph_coloring"} for band in {"R0", "R1-2", "R3-5", "R6+"}}, "e1_required_depth_histogram_present", f"rows={len(depth_hist_rows)}", "post_review_e1")
        storage_keys = {(row.get("task"), row.get("codebook"), row.get("D")) for row in storage_rows}
        expected_storage_keys = {(task, codebook, D) for task in {"sat_3sat", "graph_coloring"} for codebook in {"bound_single", "factored"} for D in {32, 64, 96, 128, 256, 512}}
        _check(checks, storage_keys == expected_storage_keys and all(row.get("d_star_measured") is not None and row.get("threshold") == 0.95 for row in storage_rows), "e1_storage_dstar_summary_complete", f"rows={len(storage_rows)}", "post_review_e1")
        _check(checks, bool(storage_curve_rows) and all(row.get("provenance") == "pure_storage_lifo_push_pop_no_solving" for row in storage_curve_rows[:25]), "e1_storage_curve_no_solving_provenance", f"rows={len(storage_curve_rows)}", "post_review_e1")
        arms = {row.get("arm") for row in figure_rows}
        _check(checks, {"rot_bound_single", "rot_factored", "rot_no_revert", "kv_snapshot", "gru"}.issubset(arms), "e1_figure4_arm_rows_present", f"arms={sorted(arms)}", "post_review_e1")
        _check(checks, bool(figure_rows) and all(row.get("source") == "autonomous_stage_a_run" and row.get("provenance") == "autonomous_stage_a_run" for row in figure_rows), "e1_figure4_rows_sourced", f"rows={len(figure_rows)}", "post_review_e1")
        gru_rows = [row for row in figure_rows if row.get("arm") == "gru"]
        _check(checks, bool(gru_rows) and all(row.get("status") == "INCOMPLETE_AUDIT_RED" and row.get("figure_included") is False and row.get("solve_rate") is None for row in gru_rows), "e1_gru_audit_red_excluded", f"rows={len(gru_rows)}", "post_review_e1")
        _check(checks, bool(law_rows) and all(row.get("source") == "autonomous_stage_a_run" and row.get("provenance") == "autonomous_stage_a_run" for row in law_rows), "e1_law_rows_sourced", f"rows={len(law_rows)}", "post_review_e1")
        _check(checks, bool(law_rows) and all(row.get("observed_spill_off_solve_rate") is not None and row.get("n_seeds_joined") == 2 for row in law_rows), "e1_law_seed_join_fixed", f"rows={len(law_rows)}", "post_review_e1")
        _check(checks, bool(law_rows) and all(row.get("d_star_source") == "pure_storage_lifo_push_pop_no_solving" and row.get("measured_d_star") is not None and row.get("law_transfer_tolerance") == 0.05 for row in law_rows), "e1_law_uses_storage_dstar_rows", f"rows={len(law_rows)}", "post_review_e1")
        law_strict_tolerance = bool(law_rows) and all(row.get("on_y_equals_x") == (row.get("law_transfer_abs_diff") is not None and float(row.get("law_transfer_abs_diff")) < 0.05) for row in law_rows)
        _check(checks, law_strict_tolerance, "e1_law_transfer_strict_tolerance", f"rows={len(law_rows)}", "post_review_e1")
        _check(checks, discipline.get("path_b_candidate_depth_keys") == ["D_peak", "D_pop", "D_readpop"], "e1_path_b_depth_keys_recorded", f"keys={discipline.get('path_b_candidate_depth_keys')}", "post_review_e1")
        _check(checks, len(live_load_rows) == 512 and all(row.get("D_readpop_equals_D_pop") is True for row in live_load_rows), "e1_live_load_predictors_present", f"rows={len(live_load_rows)}", "post_review_e1")
        _check(checks, bool(live_load_law_rows) and {row.get("predictor") for row in live_load_law_rows} == {"D_peak", "D_pop", "D_readpop"}, "e1_live_load_law_transfer_present", f"rows={len(live_load_law_rows)}", "post_review_e1")
        e1_best = next((row for row in live_load_summary if row.get("is_best_by_mean_abs_diff") is True), None)
        _check(checks, e1_best is not None and e1_best.get("predictor") == "D_pop" and acceptance.get("live_load_path_b_best_predictor") == "D_pop", "e1_path_b_dpop_winner", f"best={e1_best}; acceptance={acceptance.get('live_load_path_b_best_predictor')}", "post_review_e1")
        _check(checks, bool(sudoku_live_rows) and all(row.get("live_load_status") in {"measured", "timeout", "prescreen_timeout", "summary_proxy"} for row in sudoku_live_rows), "e1_sudoku_live_load_predictors_recorded", f"rows={len(sudoku_live_rows)}", "post_review_e1")
        _check(checks, bool(sudoku_confirmation_rows) and bool(sudoku_summary), "e1_sudoku_live_load_confirmation_present", f"rows={len(sudoku_confirmation_rows)}; summary={sudoku_summary}", "post_review_e1")
        _check(checks, discipline.get("path_b_deeper_law") == "product_decode_accuracy_over_structural_choice_reads" and discipline.get("path_b_deeper_pre_registered_candidate") == "P_choice" and discipline.get("path_b_deeper_no_free_parameters") is True and "floor(_capacity_dstar" in str(discipline.get("path_b_deeper_write_drop_rule")), "e1_compositional_law_preregistered", f"discipline={discipline}", "post_review_e1")
        rule_names = {row.get("rule") for row in compositional_rules}
        _check(checks, {"register_entry_classification", "pop_read", "forward_read", "spill_off_write_drop", "write_drop_mask", "final_solution_readback"}.issubset(rule_names), "e1_compositional_read_rules_recorded", f"rules={rule_names}", "post_review_e1")
        comp_candidates = {row.get("candidate") for row in compositional_law_rows}
        _check(checks, bool(compositional_law_rows) and {"P_all", "P_choice", "P_pop", "P_all_unmasked", "P_choice_unmasked", "P_pop_unmasked", "threshold_D_peak", "threshold_D_pop"}.issubset(comp_candidates), "e1_compositional_candidates_present", f"candidates={comp_candidates}; rows={len(compositional_law_rows)}", "post_review_e1")
        masked_product_rows = [row for row in compositional_product_rows if row.get("candidate") in {"P_all", "P_choice", "P_pop"}]
        _check(checks, bool(masked_product_rows) and all(row.get("mask_applied") is True and row.get("hard_capacity_C") is not None and {"n_dropped_reads", "n_surviving_reads"}.issubset(row) for row in masked_product_rows), "e1_compositional_write_drop_mask_fields", f"rows={len(masked_product_rows)}", "post_review_e1")
        _check(checks, bool(compositional_law_rows) and all({"residual_observed_minus_predicted", "residual_nonnegative", "residual_within_tolerance", "residual_one_sided_tight"}.issubset(row) for row in compositional_law_rows), "e1_compositional_residual_fields_recorded", f"rows={len(compositional_law_rows)}", "post_review_e1")
        comp_choice = next((row for row in compositional_summary if row.get("candidate") == "P_choice"), None)
        _check(checks, comp_choice is not None and comp_choice.get("pre_registered_hypothesis") is True and comp_choice.get("mask_applied") is True and comp_choice.get("fraction_residual_nonnegative") is not None and acceptance.get("compositional_pre_registered_candidate") == "P_choice" and acceptance.get("compositional_no_free_parameters") is True, "e1_compositional_pchoice_preregistered", f"P_choice={comp_choice}; acceptance={acceptance}", "post_review_e1")
        sudoku_comp_trace_statuses = {row.get("status") for row in sudoku_comp_trace_rows}
        _check(checks, bool(sudoku_comp_trace_rows) and len(sudoku_comp_trace_rows) == 64 and "measured" in sudoku_comp_trace_statuses and sudoku_comp_trace_statuses.issubset({"measured", "timeout"}) and all("summary_proxy" not in str(row.get("provenance")) for row in sudoku_comp_trace_rows), "e1_sudoku_compositional_real_trace_subsample", f"rows={len(sudoku_comp_trace_rows)}; statuses={sudoku_comp_trace_statuses}", "post_review_e1")
        sudoku_curve_ds = {(row.get("arm"), row.get("D")) for row in sudoku_comp_curve_rows}
        sudoku_d128_rows = [row for row in sudoku_comp_curve_rows if row.get("arm") == "rot_bound_single" and row.get("D") == 128]
        _check(checks, ("rot_bound_single", 128) in sudoku_curve_ds and ("rot_bound_single", 256) in sudoku_curve_ds and ("rot_factored", 512) in sudoku_curve_ds and {row.get("depth") for row in sudoku_d128_rows} == set(range(1, 59)) and all(row.get("K_eff") == 729 and row.get("threshold") == 0.95 for row in sudoku_d128_rows), "e1_sudoku_compositional_curve_sources_recorded", f"curve_keys_sample={sorted(sudoku_curve_ds)[:8]}; d128_depths={len(sudoku_d128_rows)}; rows={len(sudoku_comp_curve_rows)}", "post_review_e1")
        sudoku_comp_candidates = {row.get("candidate") for row in sudoku_comp_law_rows}
        d128_bound_recorded = any(row.get("arm") == "rot_bound_single" and row.get("D") == 128 and row.get("status") == "RECORDED" for row in sudoku_comp_law_rows)
        _check(checks, bool(sudoku_comp_law_rows) and sudoku_comp_candidates == {"P_all", "P_choice", "P_pop", "P_all_unmasked", "P_choice_unmasked", "P_pop_unmasked"} and all("summary_proxy" not in str(row.get("provenance")) for row in sudoku_comp_law_rows) and d128_bound_recorded, "e1_sudoku_compositional_no_proxy_d128_measured", f"candidates={sudoku_comp_candidates}; d128_bound_recorded={d128_bound_recorded}; rows={len(sudoku_comp_law_rows)}", "post_review_e1")
        sudoku_masked_product_rows = [row for row in sudoku_comp_product_rows if row.get("candidate") in {"P_all", "P_choice", "P_pop"}]
        _check(checks, bool(sudoku_masked_product_rows) and all(row.get("mask_applied") is True and row.get("hard_capacity_C") is not None and {"n_dropped_reads", "n_surviving_reads"}.issubset(row) for row in sudoku_masked_product_rows), "e1_sudoku_compositional_write_drop_mask_fields", f"rows={len(sudoku_masked_product_rows)}", "post_review_e1")
        _check(checks, bool(sudoku_comp_law_rows) and all(row.get("status") in {"RECORDED", "MISSING_DECODE_CURVE_OR_TRACE"} and "n_timeout_excluded" in row and {"residual_observed_minus_predicted", "residual_nonnegative", "residual_within_tolerance", "residual_one_sided_tight"}.issubset(row) for row in sudoku_comp_law_rows), "e1_sudoku_compositional_residual_timeout_fields", f"rows={len(sudoku_comp_law_rows)}", "post_review_e1")
        sudoku_comp_choice = next((row for row in sudoku_comp_summary if row.get("candidate") == "P_choice"), None)
        _check(checks, sudoku_comp_choice is not None and sudoku_comp_choice.get("pre_registered_hypothesis") is True and sudoku_comp_choice.get("model_family") == "decode_curve_product" and sudoku_comp_choice.get("mask_applied") is True and sudoku_comp_choice.get("fraction_residual_nonnegative") is not None, "e1_sudoku_compositional_pchoice_recorded", f"P_choice={sudoku_comp_choice}; summary_rows={len(sudoku_comp_summary)}", "post_review_e1")
    if sudoku_d128_curve:
        summary = sudoku_d128_curve.get("summary", {})
        raw_rows = sudoku_d128_curve.get("raw_rows", [])
        depths = {int(row.get("depth", -1)) for row in raw_rows}
        seeds = {int(row.get("seed", -1)) for row in raw_rows}
        _check(checks, summary.get("variant") == "bound_single" and summary.get("replacement") == "with_replacement" and int(summary.get("D", -1)) == 128 and int(summary.get("K_var", -1)) == 81 and int(summary.get("K_val", -1)) == 9, "e1_sudoku_d128_curve_identity", f"summary={summary}", "post_review_e1")
        _check(checks, sudoku_d128_curve.get("threshold") == 0.95 and depths == set(range(1, 59)) and seeds == {42, 137, 256} and len(raw_rows) == 174, "e1_sudoku_d128_curve_full_protocol", f"threshold={sudoku_d128_curve.get('threshold')}; depths={len(depths)}; seeds={sorted(seeds)}; raw_rows={len(raw_rows)}", "post_review_e1")
    if results:
        small_d_knee_rows = [row for row in law_rows if row.get("D", 999) < 128 and 0.05 <= float(row.get("fraction_required_depth_le_dstar", 0.0)) <= 0.95]
        _check(checks, bool(small_d_knee_rows) and acceptance.get("small_d_knee_exercised") is True, "e1_small_d_knee_exercised", f"rows={len(small_d_knee_rows)}", "post_review_e1")
        law_ready = bool(law_rows) and all(row.get("on_y_equals_x") is True for row in law_rows)
        law_deviation_recorded = status == "E1_SCALAR_FIGURE4_DEVIATION_RECORDED" and bool(law_rows) and any(row.get("on_y_equals_x") is False for row in law_rows) and acceptance.get("law_transfer_on_y_equals_x") is False
        _check(checks, law_ready or law_deviation_recorded, "e1_law_transfer_ready_or_deviation_recorded", f"status={status}; law_ready={law_ready}; deviation={law_deviation_recorded}", "post_review_e1")
        required_episode_keys = {"solve", "applied_reverts", "revert_success", "peak_register_bytes", "overflow_entries", "node_cap_exhaustion"}
        episode_keys_ok = bool(episode_rows) and all(required_episode_keys.issubset(row) for row in episode_rows[:25])
        _check(checks, episode_keys_ok, "e1_episode_metric_keys_present", f"rows={len(episode_rows)}", "post_review_e1")
        panels = results.get("panel_artifacts", {})
        panels_present = bool(panels) and all((REPO_ROOT / path).exists() for path in panels.values())
        _check(checks, panels_present, "e1_figure4_panel_artifacts_present", f"panels={panels}", "post_review_e1")


def _rung1_distributed_graph_coloring_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_051_rung1_distributed_graph_coloring", "rung1")
    _exists(checks, "rung1_distributed_graph_coloring", "rung1")
    item = _read_json("item_051_rung1_distributed_graph_coloring")
    results = _read_json("rung1_distributed_graph_coloring")
    if item:
        _check(checks, item.get("item_number") == "051", "item051_number_present", f"item_number={item.get('item_number')}", "rung1")
        _check(checks, item.get("status") in {"RUNG1_PHASE0_SYMBOLIC_GATE_PASSED", "RUNG1_PHASE0_SYMBOLIC_DEEPEN_AND_RERUN"}, "item051_status_valid", f"status={item.get('status')}", "rung1")
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        _check(checks, {"deep_cbj_solve_rate_gt_chronological", "deep_cbj_total_retractions_less", "deep_cbj_comm_tokens_less", "deep_forward_markov_near_zero"}.issubset(gates), "item051_gate_rows_present", f"gates={gates}", "rung1")
    if results:
        discipline = results.get("discipline", {})
        acceptance = results.get("acceptance", {})
        pool_rows = results.get("pool_summary", [])
        arm_rows = results.get("arm_band_summary", [])
        pair_rows = results.get("paired_cbj_vs_chronological", [])
        metric_rows = results.get("instance_arm_metrics", [])
        manifest_rows = results.get("instance_manifest", [])
        generation = results.get("generation_config", {})
        _check(checks, results.get("schema_version") == "rung1_distributed_graph_coloring_v0", "rung1_schema_version", f"schema={results.get('schema_version')}", "rung1")
        _check(checks, discipline.get("only_variable") == "RECOVERY backjump target rule" and discipline.get("shared_register") == "bounded reversible boundary commitment register" and discipline.get("phase") == "0_symbolic_operator", "rung1_shared_register_discipline", f"discipline={discipline}", "rung1")
        gym_manifest_ok = bool(manifest_rows) and all(str(row.get("source_kind", "")).startswith("reasoning_gym_graph_color_generator:") and row.get("provenance") == "reasoning_gym_graph_color_generator_rejection_sample" for row in manifest_rows)
        _check(checks, generation.get("generator_package") == "reasoning-gym" and str(generation.get("generator_version", "")) and generation.get("generator_api") == "reasoning_gym.algorithmic.graph_color.generate_graph_coloring_puzzle" and gym_manifest_ok, "rung1_reasoning_gym_generation_used", f"generator={generation.get('generator_package')} {generation.get('generator_version')}; rows={len(manifest_rows)}; gym_manifest_ok={gym_manifest_ok}", "rung1")
        pool_by_band = {row.get("band"): row for row in pool_rows}
        _check(checks, set(pool_by_band) == {"R0", "R1-2", "R3+"} and all(row.get("n") == 64 and row.get("target_met") is True for row in pool_by_band.values()), "rung1_pool_bands_complete", f"pool={pool_rows}", "rung1")
        deep_manifest = [row for row in manifest_rows if row.get("band") == "R3+"]
        _check(checks, bool(deep_manifest) and all(int(row.get("reference_cross_agent_conflict_depth", 0)) >= 3 and row.get("boundary_conflict_exact") is True for row in deep_manifest), "rung1_deep_band_boundary_exact", f"deep_rows={len(deep_manifest)}", "rung1")
        arms = {(row.get("band"), row.get("arm")) for row in arm_rows}
        _check(checks, {(band, arm) for band in {"R0", "R1-2", "R3+"} for arm in {"forward_markov_team", "chronological_rollback", "cbj_bounded"}}.issubset(arms), "rung1_arm_band_rows_complete", f"arms={sorted(arms)}", "rung1")
        deep_arm = {row.get("arm"): row for row in arm_rows if row.get("band") == "R3+"}
        deep_pair = next((row for row in pair_rows if row.get("band") == "R3+"), {})
        _check(checks, float(deep_arm.get("cbj_bounded", {}).get("solve_rate", 0.0)) > float(deep_arm.get("chronological_rollback", {}).get("solve_rate", 1.0)) and float(deep_pair.get("solve_rate_delta_cbj_minus_chronological", 0.0)) >= 0.20, "rung1_deep_cbj_solve_gt_chronological", f"deep_arm={deep_arm}; pair={deep_pair}", "rung1")
        _check(checks, float(deep_pair.get("mean_retraction_delta_cbj_minus_chronological", 1.0)) < 0 and float(deep_pair.get("mean_comm_token_delta_cbj_minus_chronological", 1.0)) < 0, "rung1_deep_cbj_less_retractions_and_comm", f"pair={deep_pair}", "rung1")
        _check(checks, float(deep_arm.get("forward_markov_team", {}).get("solve_rate", 1.0)) <= 0.05, "rung1_deep_forward_near_zero", f"forward={deep_arm.get('forward_markov_team')}", "rung1")
        _check(checks, acceptance.get("rung1_gate_pass") is True and results.get("status") == "RUNG1_PHASE0_SYMBOLIC_GATE_PASSED", "rung1_phase0_gate_passed", f"acceptance={acceptance}; status={results.get('status')}", "rung1")
        _check(checks, bool(metric_rows) and all(row.get("register_capacity") == 16 and row.get("node_cap") == 120 and row.get("provenance") == "phase0_symbolic_priority_ordered_distributed_graph_coloring" for row in metric_rows[:50]), "rung1_metric_rows_register_accounting", f"rows={len(metric_rows)}", "rung1")


def _rung1_gate_distributed_coloring_v01_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_052_rung1_gate_distributed_coloring_v01", "rung1_v01")
    _exists(checks, "rung1_gate_distributed_coloring_v01", "rung1_v01")
    item = _read_json("item_052_rung1_gate_distributed_coloring_v01")
    results = _read_json("rung1_gate_distributed_coloring_v01")
    if item:
        _check(checks, item.get("item_number") == "052", "item052_number_present", f"item_number={item.get('item_number')}", "rung1_v01")
        _check(checks, item.get("status") in {"RUNG1_V01_FIXED_SIZE_DEPTH_CURVE_PASSED", "RUNG1_V01_FIXED_SIZE_DEPTH_CURVE_REVIEW"}, "item052_status_valid", f"status={item.get('status')}", "rung1_v01")
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        required_gates = {"fixed_size_attainable_bins_filled", "structural_shallow_holes_recorded", "solve_gap_monotonic_and_crossover", "forward_ge1_near_zero", "cbj_cap_sweep_complete"}
        _check(checks, required_gates.issubset(gates) and all(gates.get(gate) == "PASS" for gate in required_gates), "item052_gate_rows_pass", f"gates={gates}", "rung1_v01")
    if results:
        discipline = results.get("discipline", {})
        generation = results.get("generation_config", {})
        acceptance = results.get("acceptance", {})
        pool_rows = results.get("pool_depth_summary", [])
        gap_rows = results.get("gap_vs_depth_curve", [])
        arm_rows = results.get("arm_depth_summary", [])
        cap_rows = results.get("cbj_register_capacity_sweep", [])
        metric_rows = results.get("instance_arm_metrics", [])
        manifest_rows = results.get("instance_manifest", [])
        pool_by_bin = {row.get("depth_bin"): row for row in pool_rows}
        attainable_bins = {"0", "4", "5", "6", "7", "8", "9+"}
        structural_bins = {"1", "2", "3"}
        _check(checks, results.get("schema_version") == "rung1_gate_distributed_coloring_v0_1", "rung1_v01_schema_version", f"schema={results.get('schema_version')}", "rung1_v01")
        frozen = set(discipline.get("frozen_from_item051", []))
        _check(checks, discipline.get("phase") == "0_symbolic_operator" and {"register mechanism", "recovery target rules", "priority ordered protocol", "symbolic conflict set", "solve loop"}.issubset(frozen), "rung1_v01_frozen_loop_discipline", f"discipline={discipline}", "rung1_v01")
        _check(checks, generation.get("n_vertices") == 16 and generation.get("k") == 4 and generation.get("n_agents") == 4 and generation.get("target_per_depth_bin") == 48 and generation.get("generator_package") == "reasoning-gym", "rung1_v01_fixed_size_generation", f"generation={generation}", "rung1_v01")
        attainable_ok = attainable_bins.issubset(pool_by_bin) and all(pool_by_bin[bin_name].get("n") == 48 and pool_by_bin[bin_name].get("target_met") is True and pool_by_bin[bin_name].get("n_vertices") == 16 and pool_by_bin[bin_name].get("k") == 4 and pool_by_bin[bin_name].get("n_agents") == 4 for bin_name in attainable_bins)
        holes_ok = structural_bins.issubset(pool_by_bin) and all(pool_by_bin[bin_name].get("structural_hole") is True and pool_by_bin[bin_name].get("n") == 0 for bin_name in structural_bins)
        _check(checks, attainable_ok and holes_ok, "rung1_v01_depth_bins_filled_or_structural", f"attainable_ok={attainable_ok}; holes_ok={holes_ok}; pool={pool_rows}", "rung1_v01")
        chi_ok = bool(manifest_rows) and all(row.get("n_vertices") == 16 and row.get("k") == 4 and row.get("chromatic_number") == 4 and row.get("boundary_conflict_exact") is True for row in manifest_rows)
        _check(checks, chi_ok, "rung1_v01_manifest_fixed_chi4_boundary_exact", f"rows={len(manifest_rows)}", "rung1_v01")
        gaps = [float(row.get("solve_rate_gap_cbj_minus_chronological", -1.0)) for row in gap_rows]
        monotonic = bool(gaps) and all(gaps[index] <= gaps[index + 1] + 1e-12 for index in range(len(gaps) - 1))
        post_crossover = [row for row in gap_rows if row.get("depth_bin") in {"7", "8", "9+"}]
        post_sig = bool(post_crossover) and all(row.get("mcnemar_one_sided_p_cbj_gt_chronological") is not None and float(row.get("mcnemar_one_sided_p_cbj_gt_chronological")) <= 0.05 for row in post_crossover)
        forward_ok = bool(gap_rows) and all(float(row.get("forward_solve_rate", 1.0)) <= 0.05 for row in gap_rows if row.get("depth_bin") != "0")
        _check(checks, monotonic and post_sig and forward_ok and acceptance.get("crossover_depth_bin") == "7", "rung1_v01_gap_curve_pass", f"gaps={gaps}; crossover={acceptance.get('crossover_depth_bin')}; post_sig={post_sig}; forward_ok={forward_ok}", "rung1_v01")
        overflow_columns_ok = bool(arm_rows) and all("mean_overflow_entries" in row and "fraction_instances_overflowed" in row for row in arm_rows)
        _check(checks, overflow_columns_ok, "rung1_v01_overflow_summary_columns", f"rows={len(arm_rows)}", "rung1_v01")
        sweep_caps = {row.get("register_capacity") for row in cap_rows if row.get("depth_bin") == "9+" and row.get("arm") == "cbj_bounded"}
        sweep_ok = sweep_caps == {16, 32} and all(row.get("n") == 48 and row.get("solve_rate") == 1.0 for row in cap_rows)
        _check(checks, sweep_ok, "rung1_v01_cbj_cap_sweep_complete", f"cap_rows={cap_rows}", "rung1_v01")
        metric_ok = bool(metric_rows) and all(row.get("register_capacity") == 16 and row.get("node_cap") == 120 and row.get("provenance") == "phase0_symbolic_priority_ordered_distributed_graph_coloring_loop_frozen_from_item051" for row in metric_rows[:50])
        _check(checks, metric_ok and acceptance.get("rung1_v01_gate_pass") is True and results.get("status") == "RUNG1_V01_FIXED_SIZE_DEPTH_CURVE_PASSED", "rung1_v01_gate_passed", f"acceptance={acceptance}; metric_rows={len(metric_rows)}", "rung1_v01")


def _rung1_gate_distributed_coloring_v02_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_053_rung1_gate_distributed_coloring_v02", "rung1_v02")
    _exists(checks, "rung1_gate_distributed_coloring_v02", "rung1_v02")
    item = _read_json("item_053_rung1_gate_distributed_coloring_v02")
    results = _read_json("rung1_gate_distributed_coloring_v02")
    target_bins = {"7", "8", "9+"}
    if item:
        _check(checks, item.get("item_number") == "053", "item053_number_present", f"item_number={item.get('item_number')}", "rung1_v02")
        _check(checks, item.get("status") == "RUNG1_V02_RG_NATIVE_HARD_BASELINE_RECORDED", "item053_status_valid", f"status={item.get('status')}", "rung1_v02")
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        required_gates = {"rg_native_bins_filled", "reverse_greedy_one_shot_zero", "cbj_solves_all_hard_bins", "all_hard_bins_significant"}
        _check(checks, required_gates.issubset(gates) and all(gates.get(gate) == "PASS" for gate in required_gates - {"all_hard_bins_significant"}) and gates.get("all_hard_bins_significant") in {"PASS", "RECORDED"}, "item053_gate_rows_recorded", f"gates={gates}", "rung1_v02")
    if results:
        discipline = results.get("discipline", {})
        generation = results.get("generation_config", {})
        acceptance = results.get("acceptance", {})
        pool_rows = results.get("pool_depth_summary", [])
        gap_rows = results.get("gap_vs_depth_curve", [])
        arm_rows = results.get("arm_depth_summary", [])
        metric_rows = results.get("instance_arm_metrics", [])
        manifest_rows = results.get("instance_manifest", [])
        pool_by_bin = {row.get("depth_bin"): row for row in pool_rows}
        _check(checks, results.get("schema_version") == "rung1_gate_distributed_coloring_v0_2", "rung1_v02_schema_version", f"schema={results.get('schema_version')}", "rung1_v02")
        frozen = set(discipline.get("frozen_from_item051", []))
        _check(checks, discipline.get("phase") == "0_symbolic_operator" and {"register mechanism", "recovery target rules", "priority ordered protocol", "symbolic conflict set", "solve loop"}.issubset(frozen), "rung1_v02_frozen_loop_discipline", f"discipline={discipline}", "rung1_v02")
        _check(checks, generation.get("n_vertices") == 16 and generation.get("k") == 4 and generation.get("n_agents") == 4 and generation.get("target_per_depth_bin") == 48 and generation.get("generator_api") == "reasoning_gym.algorithmic.graph_color.generate_random_graph" and generation.get("verifier_api") == "reasoning_gym.algorithmic.graph_color.verify_graph_coloring_solution" and generation.get("one_shot_baseline") == "reasoning_gym.algorithmic.graph_color.greedy_graph_coloring", "rung1_v02_rg_native_generation", f"generation={generation}", "rung1_v02")
        bins_ok = set(pool_by_bin) == target_bins and all(pool_by_bin[bin_name].get("n") == 48 and pool_by_bin[bin_name].get("target_met") is True and pool_by_bin[bin_name].get("n_vertices") == 16 and pool_by_bin[bin_name].get("k") == 4 and pool_by_bin[bin_name].get("n_agents") == 4 for bin_name in target_bins)
        _check(checks, bins_ok, "rung1_v02_target_hard_bins_filled", f"pool={pool_rows}", "rung1_v02")
        manifest_ok = bool(manifest_rows) and all(row.get("n_vertices") == 16 and row.get("k") == 4 and row.get("chromatic_number") == 4 and row.get("boundary_conflict_exact") is True and row.get("rg_verified_sat") is True and row.get("rg_greedy_one_shot_solved") is False and str(row.get("source_kind", "")).startswith("reasoning_gym_generate_random_graph:") and "chain" not in str(row.get("fill_method", "")) for row in manifest_rows)
        _check(checks, manifest_ok, "rung1_v02_manifest_rg_native_reverse_greedy", f"rows={len(manifest_rows)}", "rung1_v02")
        arms = {(row.get("depth_bin"), row.get("arm")) for row in arm_rows}
        required_arms = {(bin_name, arm) for bin_name in target_bins for arm in {"forward_markov_team", "chronological_rollback", "cbj_bounded", "rg_greedy_one_shot"}}
        _check(checks, required_arms.issubset(arms), "rung1_v02_arm_rows_complete", f"arms={sorted(arms)}", "rung1_v02")
        one_shot_zero = bool(gap_rows) and all(float(row.get("rg_greedy_one_shot_solve_rate", 1.0)) == 0.0 for row in gap_rows)
        forward_zero = bool(gap_rows) and all(float(row.get("forward_solve_rate", 1.0)) == 0.0 for row in gap_rows)
        cbj_all = bool(gap_rows) and all(float(row.get("cbj_solve_rate", 0.0)) == 1.0 for row in gap_rows)
        deepest = next((row for row in gap_rows if row.get("depth_bin") == "9+"), {})
        deepest_sig = deepest.get("mcnemar_one_sided_p_cbj_gt_chronological") is not None and float(deepest.get("mcnemar_one_sided_p_cbj_gt_chronological")) <= 0.05 and float(deepest.get("solve_rate_gap_cbj_minus_chronological", 0.0)) > 0
        _check(checks, one_shot_zero and forward_zero and cbj_all and deepest_sig, "rung1_v02_hard_pool_baseline_and_9plus_gap", f"one_shot_zero={one_shot_zero}; forward_zero={forward_zero}; cbj_all={cbj_all}; deepest={deepest}", "rung1_v02")
        metric_ok = bool(metric_rows) and all((row.get("arm") == "rg_greedy_one_shot" and row.get("provenance") == "reasoning_gym_greedy_graph_coloring_one_shot_verified_by_rg") or (row.get("arm") != "rg_greedy_one_shot" and row.get("register_capacity") == 16 and row.get("node_cap") == 120 and row.get("provenance") == "phase0_symbolic_loop_frozen_from_item051_rg_native_pool") for row in metric_rows[:80])
        _check(checks, metric_ok and acceptance.get("rung1_v02_recorded") is True and results.get("status") == "RUNG1_V02_RG_NATIVE_HARD_BASELINE_RECORDED", "rung1_v02_recorded_status", f"acceptance={acceptance}; metric_rows={len(metric_rows)}", "rung1_v02")


def _rung1_phase1_spec_v01_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_054_rung1_phase1_spec_v01", "rung1_phase1_spec")
    _exists(checks, "rung1_phase1_spec_v01", "rung1_phase1_spec")
    item = _read_json("item_054_rung1_phase1_spec_v01")
    spec_path = _path("rung1_phase1_spec_v01")
    spec_text = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
    if item:
        _check(checks, item.get("item_number") == "054", "item054_number_present", f"item_number={item.get('item_number')}", "rung1_phase1_spec")
        _check(checks, item.get("status") == "RUNG1_PHASE1_SPEC_V01_ACCEPTED", "item054_status_valid", f"status={item.get('status')}", "rung1_phase1_spec")
        tables = item.get("result_tables", {})
        required_tables = {"claim_reorder", "node_cap_policy", "baseline_policy", "pool_policy", "operator_ladder_refocus", "run_order"}
        _check(checks, required_tables.issubset(tables), "item054_required_tables_present", f"tables={sorted(tables)}", "rung1_phase1_spec")
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        required_gates = {"primary_metric_reordered_to_efficiency", "solve_rate_marked_budget_contingent", "qwen_one_shot_replaces_greedy_report_baseline", "distribution_roles_separated", "operator_ladder_refocused"}
        _check(checks, required_gates.issubset(gates) and all(gates.get(gate) == "PASS" for gate in required_gates), "item054_revision_gates_pass", f"gates={gates}", "rung1_phase1_spec")
        policy_rows = tables.get("node_cap_policy", {}).get("rows", [])
        caps = policy_rows[0].get("node_caps") if policy_rows else []
        _check(checks, caps == [60, 120, 240, 480, 960] and policy_rows and policy_rows[0].get("derived_metric") == "budget@95%_solve", "item054_node_cap_policy", f"caps={caps}; rows={policy_rows}", "rung1_phase1_spec")
    required_phrases = [
        "Primary metrics",
        "comm_tokens",
        "total_retractions",
        "budget@95%_solve",
        "qwen_one_shot",
        "direct-answer",
        "with-CoT",
        "depth 4, 5, 6, and exact 9",
        "efficiency-gap survival",
        "Do not use Item052 chain-planted solve gaps as the headline figure",
    ]
    missing = [phrase for phrase in required_phrases if phrase not in spec_text]
    _check(checks, not missing, "rung1_phase1_spec_v01_required_content", f"missing={missing}", "rung1_phase1_spec")
    _check(checks, "Headline pool: Item053 RG-native" in spec_text and "Stress isolation pool: Item052 chain-planted" in spec_text and "Do not mix chain-planted and RG-native rows" in spec_text, "rung1_phase1_spec_pool_roles_separated", "Item053 headline, Item052 stress only", "rung1_phase1_spec")


def _rung1_phase1_r4_natural_pool_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_055_rung1_phase1_r4_natural_pool", "rung1_phase1_r4")
    _exists(checks, "rung1_phase1_r4_natural_pool", "rung1_phase1_r4")
    item = _read_json("item_055_rung1_phase1_r4_natural_pool")
    results = _read_json("rung1_phase1_r4_natural_pool")
    target_bins = {"4", "5", "6", "7", "8", "9", "9+"}
    if item:
        _check(checks, item.get("item_number") == "055", "item055_number_present", f"item_number={item.get('item_number')}", "rung1_phase1_r4")
        _check(checks, item.get("status") == "RUNG1_PHASE1_R4_NATURAL_POOL_READY", "item055_status_valid", f"status={item.get('status')}", "rung1_phase1_r4")
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        _check(checks, gates.get("rg_native_depth_bins_filled") == "PASS" and gates.get("edge_manifest_saved") == "PASS", "item055_gate_rows_pass", f"gates={gates}", "rung1_phase1_r4")
    if results:
        generation = results.get("generation_config", {})
        acceptance = results.get("acceptance", {})
        pool_rows = results.get("pool_depth_summary", [])
        manifest_rows = results.get("instance_manifest", [])
        pool_by_bin = {row.get("depth_bin"): row for row in pool_rows}
        _check(checks, results.get("schema_version") == "rung1_phase1_r4_natural_pool_v0", "rung1_phase1_r4_schema_version", f"schema={results.get('schema_version')}", "rung1_phase1_r4")
        _check(checks, generation.get("target_per_depth_bin") == 48 and generation.get("generator_api") == "reasoning_gym.algorithmic.graph_color.generate_random_graph" and generation.get("verifier_api") == "reasoning_gym.algorithmic.graph_color.verify_graph_coloring_solution", "rung1_phase1_r4_rg_native_generation", f"generation={generation}", "rung1_phase1_r4")
        bins_ok = set(pool_by_bin) == target_bins and all(pool_by_bin[bin_name].get("n") == 48 and pool_by_bin[bin_name].get("target_met") is True for bin_name in target_bins)
        _check(checks, bins_ok, "rung1_phase1_r4_bins_complete", f"pool={pool_rows}", "rung1_phase1_r4")
        manifest_ok = bool(manifest_rows) and len(manifest_rows) == 336 and all(row.get("n_vertices") == 16 and row.get("k") == 4 and row.get("chromatic_number") == 4 and row.get("rg_verified_sat") is True and row.get("rg_greedy_one_shot_solved") is False and len(row.get("edges", [])) > 0 and str(row.get("source_kind", "")).startswith("reasoning_gym_generate_random_graph:") for row in manifest_rows)
        _check(checks, manifest_ok and acceptance.get("all_bins_filled") is True and results.get("status") == "RUNG1_PHASE1_R4_NATURAL_POOL_READY", "rung1_phase1_r4_edge_manifest_ready", f"rows={len(manifest_rows)}; acceptance={acceptance}", "rung1_phase1_r4")


def _rung1_phase1_r3_qwen_oneshot_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_056_rung1_phase1_r3_qwen_oneshot", "rung1_phase1_r3")
    _exists(checks, "rung1_phase1_r3_qwen_oneshot", "rung1_phase1_r3")
    item = _read_json("item_056_rung1_phase1_r3_qwen_oneshot")
    results = _read_json("rung1_phase1_r3_qwen_oneshot")
    allowed_statuses = {"RUNG1_PHASE1_R3_QWEN_ONESHOT_RECORDED_V1", "RUNG1_PHASE1_R3_QWEN_ONESHOT_HEALTH_FAIL_RERUN", "RUNG1_PHASE1_R3_QWEN_ONESHOT_TOO_EASY_STOP"}
    if item:
        _check(checks, item.get("item_number") == "056", "item056_number_present", f"item_number={item.get('item_number')}", "rung1_phase1_r3")
        _check(checks, item.get("status") in allowed_statuses, "item056_status_valid", f"status={item.get('status')}", "rung1_phase1_r3")
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        _check(checks, gates.get("generation_health") in {"PASS", "RERUN"} and gates.get("task_hardness_gate") in {"PASS", "STOP", "NO_CONCLUSION"}, "item056_gate_rows_recorded", f"gates={gates}", "rung1_phase1_r3")
    if results:
        generation = results.get("generation_config", {})
        acceptance = results.get("acceptance", {})
        outcome_rows = results.get("oneshot_outcome_breakdown", [])
        health_rows = results.get("oneshot_generation_health", [])
        wrongness_rows = results.get("oneshot_wrongness", [])
        instance_rows = results.get("oneshot_instance_rows", [])
        raw_text_samples = results.get("raw_text_samples", [])
        variants = {row.get("variant") for row in instance_rows}
        depth_bins = {row.get("depth_bin") for row in instance_rows}
        _check(checks, results.get("schema_version") == "rung1_phase1_r3_qwen_oneshot_v1" and results.get("status") in allowed_statuses, "rung1_phase1_r3_schema_status", f"schema={results.get('schema_version')}; status={results.get('status')}", "rung1_phase1_r3")
        _check(checks, generation.get("model_id") == "Qwen/Qwen3.5-4B" and generation.get("temperature") == 0 and generation.get("scoring_api") == "reasoning_gym.algorithmic.graph_color.GraphColorDataset.score_answer", "rung1_phase1_r3_model_scoring", f"generation={generation}", "rung1_phase1_r3")
        required_row_keys = {"instance_id", "seed", "depth_bin", "variant", "max_tokens", "finish_reason", "output_tokens", "thinking_tokens", "json_extracted", "assignment_complete", "num_conflicting_edges", "colors_used", "rg_score", "solved", "model_id", "fallback_used", "first_finish_reason"}
        row_keys_ok = bool(instance_rows) and all(required_row_keys.issubset(set(row)) and row.get("rg_score") in {0.0, 0.01, 1.0} and row.get("model_id") == "Qwen/Qwen3.5-4B" and row.get("finish_reason") in {"stop", "length", "unknown"} for row in instance_rows)
        table_ok = bool(outcome_rows) and bool(health_rows) and bool(wrongness_rows) and isinstance(raw_text_samples, list)
        variants_ok = variants.issubset({"direct_answer", "with_cot"}) and "with_cot" in variants
        depth_ok = {"4", "5", "6", "7", "8", "9", "9+"}.issubset(depth_bins)
        health_status_ok = (acceptance.get("health_pass") is False) == (results.get("status") == "RUNG1_PHASE1_R3_QWEN_ONESHOT_HEALTH_FAIL_RERUN")
        too_easy_status_ok = (acceptance.get("too_easy") is True) == (results.get("status") == "RUNG1_PHASE1_R3_QWEN_ONESHOT_TOO_EASY_STOP") if acceptance.get("health_pass") is not False else results.get("status") == "RUNG1_PHASE1_R3_QWEN_ONESHOT_HEALTH_FAIL_RERUN"
        _check(checks, row_keys_ok and table_ok and variants_ok and depth_ok and health_status_ok and too_easy_status_ok, "rung1_phase1_r3_qwen_rows_recorded_v1", f"rows={len(instance_rows)}; variants={variants}; acceptance={acceptance}", "rung1_phase1_r3")


def _rung1_phase1_r2_budget_sweep_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_057_rung1_phase1_r2_budget_sweep", "rung1_phase1_r2")
    _exists(checks, "rung1_phase1_r2_budget_sweep", "rung1_phase1_r2")
    item = _read_json("item_057_rung1_phase1_r2_budget_sweep")
    results = _read_json("rung1_phase1_r2_budget_sweep")
    expected_caps = {60, 120, 240, 480, 960}
    if item:
        _check(checks, item.get("item_number") == "057", "item057_number_present", f"item_number={item.get('item_number')}", "rung1_phase1_r2")
        _check(checks, item.get("status") == "RUNG1_PHASE1_R2_SYMBOLIC_BUDGET_SWEEP_RECORDED", "item057_status_valid", f"status={item.get('status')}", "rung1_phase1_r2")
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        _check(checks, gates.get("node_cap_sweep_complete") == "PASS", "item057_node_cap_gate_pass", f"gates={gates}", "rung1_phase1_r2")
    if results:
        generation = results.get("generation_config", {})
        metric_rows = results.get("instance_arm_node_cap_metrics", [])
        budget_rows = results.get("solve_rate_vs_node_cap", [])
        efficiency_rows = results.get("efficiency_gap_by_depth", [])
        caps = {int(row.get("node_cap")) for row in metric_rows}
        arms = {row.get("arm") for row in metric_rows}
        _check(checks, results.get("schema_version") == "rung1_phase1_r2_budget_sweep_v0" and generation.get("node_caps") == [60, 120, 240, 480, 960] and generation.get("reference_node_cap") == 120, "rung1_phase1_r2_schema_generation", f"schema={results.get('schema_version')}; generation={generation}", "rung1_phase1_r2")
        metric_ok = caps == expected_caps and arms == {"forward_markov_team", "chronological_rollback", "cbj_bounded"} and bool(metric_rows) and all(row.get("register_capacity") == 16 and row.get("provenance") == "phase0_symbolic_loop_frozen_from_item051_r4_natural_pool_node_cap_sweep" for row in metric_rows[:100])
        _check(checks, metric_ok, "rung1_phase1_r2_metric_rows_complete", f"rows={len(metric_rows)}; caps={sorted(caps)}; arms={sorted(arms)}", "rung1_phase1_r2")
        budget_ok = bool(budget_rows) and all(row.get("budget_at_95_solve") is not None for row in budget_rows)
        efficiency_ok = bool(efficiency_rows) and all(row.get("node_cap") == 120 and "comm_token_advantage_chronological_minus_cbj" in row and "retraction_advantage_chronological_minus_cbj" in row for row in efficiency_rows)
        _check(checks, budget_ok and efficiency_ok and results.get("status") == "RUNG1_PHASE1_R2_SYMBOLIC_BUDGET_SWEEP_RECORDED", "rung1_phase1_r2_tables_recorded", f"budget_rows={len(budget_rows)}; efficiency_rows={len(efficiency_rows)}", "rung1_phase1_r2")


def _rung1_separator_scaling_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_058_rung1_separator_scaling", "rung1_separator_scaling")
    _exists(checks, "rung1_separator_scaling", "rung1_separator_scaling")
    item = _read_json("item_058_rung1_separator_scaling")
    results = _read_json("rung1_separator_scaling")
    result_schema = results.get("schema_version") if results else None
    allowed_statuses = {"RUNG1_SEPARATOR_SCALING_SYMBOLIC_PASS", "RUNG1_SEPARATOR_SCALING_SYMBOLIC_KILL_RECORDED", "RUNG1_SEPARATOR_SCALING_SYMBOLIC_POOL_PARTIAL", "RUNG1_SEPARATOR_SCALING_SYMBOLIC_AXES_DESIGN_STOP"}
    allowed_schemas = {"rung1_separator_scaling_symbolic_v0", "rung1_separator_scaling_symbolic_v0_1", "rung1_separator_scaling_symbolic_v0_2", "rung1_separator_scaling_symbolic_v0_2_1", "rung1_separator_scaling_symbolic_v0_2_2", "rung1_separator_scaling_symbolic_v0_2_3"}
    required_tables = {"axes_independence_check", "instance_manifest", "keff_by_cell", "instance_arm_metrics", "capacity_leg", "double_dissociation_detail", "double_dissociation_regression", "high_thrash_diagnostics", "verdict"}
    required_arms = {"monolith_cbj", "forward_markov_team", "chronological_rollback_team", "cbj_bounded_team"}
    allowed_metric_statuses = {"SOLVED", "OVERFLOW_FAIL", "FORWARD_DEAD_END", "NODE_CAP"}
    if item:
        _check(checks, item.get("item_number") == "058", "item058_number_present", f"item_number={item.get('item_number')}", "rung1_separator_scaling")
        _check(checks, item.get("status") in allowed_statuses, "item058_status_valid", f"status={item.get('status')}", "rung1_separator_scaling")
        tables = item.get("result_tables", {})
        item_required_tables = set(required_tables)
        if result_schema == "rung1_separator_scaling_symbolic_v0_2_2":
            item_required_tables.add("recovery_dynamics_v02_vs_v022")
        if result_schema == "rung1_separator_scaling_symbolic_v0_2_3":
            item_required_tables.add("recovery_dynamics_v02_vs_v023")
        _check(checks, item_required_tables.issubset(set(tables)), "item058_required_tables_present", f"tables={sorted(tables)}", "rung1_separator_scaling")
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        _check(checks, "overall_pass" in gates and item.get("decision", {}).get("overall_pass") is not None, "item058_verdict_gate_recorded", f"gates={gates}", "rung1_separator_scaling")
    if results:
        generation = results.get("generation_config", {})
        acceptance = results.get("acceptance", {})
        manifest = results.get("instance_manifest", [])
        keff_rows = results.get("keff_by_cell", [])
        metrics = results.get("instance_arm_metrics", [])
        capacity_rows = results.get("capacity_leg", [])
        recovery_rows = results.get("recovery_dynamics_v02_vs_v023" if result_schema == "rung1_separator_scaling_symbolic_v0_2_3" else "recovery_dynamics_v02_vs_v022", [])
        dd_detail = results.get("double_dissociation_detail", [])
        dd_regression = results.get("double_dissociation_regression", [])
        thrash_rows = results.get("high_thrash_diagnostics", [])
        axes_check = results.get("axes_independence_check", {})
        verdict = results.get("verdict", [])
        arms = {row.get("arm") for row in metrics}
        metric_statuses = {row.get("status") for row in metrics}
        verdict_by_check = {row.get("check"): row for row in verdict}
        expected_metric_rows = len(manifest) * len(required_arms)
        axes_stop = results.get("status") == "RUNG1_SEPARATOR_SCALING_SYMBOLIC_AXES_DESIGN_STOP"
        _check(checks, results.get("schema_version") in allowed_schemas and results.get("status") in allowed_statuses, "rung1_separator_schema_status", f"schema={results.get('schema_version')}; status={results.get('status')}", "rung1_separator_scaling")
        team_provenance_ok = generation.get("team_loop_provenance") in {"phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0", "phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0_per_component_capacity_v02", "phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0_per_agent_fairness_v021", "phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0_read_only_trail_fairness_v022", "phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0_enforced_capacity_register_fairness_v023"}
        _check(checks, generation.get("arms") == ["monolith_cbj", "forward_markov_team", "chronological_rollback_team", "cbj_bounded_team"] and team_provenance_ok, "rung1_separator_generation_config", f"generation={generation}", "rung1_separator_scaling")
        manifest_ok = bool(manifest) and all({"instance_id", "seed", "m_blocks", "n_per_block", "k", "d_local", "b", "d_boundary", "target_d_global", "d_global_reference", "reference_cross_agent_conflict_depth", "local_contribution", "cell_id", "sweep", "n_intra_block_edges", "n_boundary_edges", "d_local_capacity_ok", "register_capacity_D", "comm_budget_C", "density", "target_met"}.issubset(row) for row in manifest)
        _check(checks, manifest_ok, "rung1_separator_manifest_schema", f"rows={len(manifest)}", "rung1_separator_scaling")
        axes_ok = {"corr_d_global_b", "vif_d_global_b", "min_unique_d_global_per_b", "min_unique_b_per_d_global", "axes_independent"}.issubset(axes_check)
        _check(checks, axes_ok and (axes_stop or axes_check.get("axes_independent") == acceptance.get("axes_independent")), "rung1_separator_axes_independence_recorded", f"axes={axes_check}", "rung1_separator_scaling")
        keff_ok = bool(keff_rows) and all({"d_global_bin", "b_bin", "mean_live_domain_at_decision", "density", "n", "keff_constant_flag"}.issubset(row) for row in keff_rows)
        _check(checks, keff_ok, "rung1_separator_keff_recorded", f"rows={len(keff_rows)}; flags={[row.get('keff_constant_flag') for row in keff_rows]}", "rung1_separator_scaling")
        base_metric_keys = {"instance_id", "arm", "cell_id", "sweep", "d_global_reference", "b", "d_boundary", "d_local", "m_blocks", "local_contribution", "solved", "status", "peak_register_entries", "comm_tokens", "total_retractions", "overflowed", "steps_to_solve_or_cap", "register_capacity_D", "comm_budget_C", "team_global_register_capacity", "node_cap", "seed"}
        fairness_schema = results.get("schema_version") in {"rung1_separator_scaling_symbolic_v0_2_1", "rung1_separator_scaling_symbolic_v0_2_2", "rung1_separator_scaling_symbolic_v0_2_3"}
        fairness_metric_ok = not fairness_schema or all((row.get("arm") == "monolith_cbj" and {"single_register_capacity", "single_register_peak"}.issubset(row)) or (row.get("arm") != "monolith_cbj" and {"local_register_capacity_per_agent", "peak_local_register_per_agent", "shared_channel_capacity", "peak_shared_channel", "sum_local_register_across_agents"}.issubset(row)) for row in metrics)
        v022_metric_ok = results.get("schema_version") != "rung1_separator_scaling_symbolic_v0_2_2" or all((row.get("arm") == "monolith_cbj" and {"trail_predicate_single_register_peak", "trail_predicate_reproduces_monolith_peak"}.issubset(row)) or (row.get("arm") != "monolith_cbj" and {"v02_reference_comm_tokens", "v02_reference_total_retractions", "recovery_loop_match_v02"}.issubset(row)) for row in metrics)
        v023_metric_ok = results.get("schema_version") != "rung1_separator_scaling_symbolic_v0_2_3" or all((row.get("arm") == "monolith_cbj" and {"capacity_law_single_register_peak", "fairness_register_peak", "fairness_register_reproduces_capacity_law_peak"}.issubset(row) and row.get("single_register_peak") == row.get("capacity_law_single_register_peak")) or (row.get("arm") != "monolith_cbj" and {"v02_reference_comm_tokens", "v02_reference_total_retractions", "recovery_loop_match_v02", "instrumentation_reads_enforced_register", "raw_peak_local_register_per_agent", "non_fairness_diagnostic_only"}.issubset(row)) for row in metrics)
        metrics_ok = (axes_stop and not metrics) or (len(metrics) == expected_metric_rows and arms == required_arms and metric_statuses.issubset(allowed_metric_statuses) and all(base_metric_keys.issubset(row) for row in metrics) and fairness_metric_ok and v022_metric_ok and v023_metric_ok)
        _check(checks, metrics_ok, "rung1_separator_metric_rows_complete", f"rows={len(metrics)}; expected={expected_metric_rows}; arms={sorted(arms)}; statuses={sorted(metric_statuses)}", "rung1_separator_scaling")
        capacity_ok = (axes_stop and not capacity_rows) or (bool(capacity_rows) and all({"d_global_bin", "b_bin", "arm", "n", "solve_rate", "mean_peak_register_entries", "overflow_rate", "predicted_collapse_d", "observed_solve_at_this_dglobal"}.issubset(row) for row in capacity_rows))
        recovery_ok = result_schema not in {"rung1_separator_scaling_symbolic_v0_2_2", "rung1_separator_scaling_symbolic_v0_2_3"} or (bool(recovery_rows) and all(({"d_global_bin", "b_bin", "arm", "n", "v02_mean_comm_tokens", "v02_mean_total_retractions", "all_rows_match_v02"}.issubset(row) and ((result_schema == "rung1_separator_scaling_symbolic_v0_2_2" and {"v022_mean_comm_tokens", "v022_mean_total_retractions"}.issubset(row)) or (result_schema == "rung1_separator_scaling_symbolic_v0_2_3" and {"v023_mean_comm_tokens", "v023_mean_total_retractions"}.issubset(row)))) for row in recovery_rows))
        dd_ok = (axes_stop and not dd_detail and not dd_regression) or (bool(dd_detail) and {row.get("arm") for row in dd_detail} == {"cbj_bounded_team", "chronological_rollback_team"} and {row.get("term") for row in dd_regression}.issuperset({"arm_chrono_x_d_global", "arm_chrono_x_b"}))
        thrash_ok = (axes_stop and not thrash_rows) or (bool(thrash_rows) and all({"d_global_bin", "b_bin", "arm", "n", "median_steps", "iqr_steps", "high_thrash_count", "culprit_trace_available"}.issubset(row) for row in thrash_rows))
        _check(checks, capacity_ok and recovery_ok and dd_ok and thrash_ok, "rung1_separator_analysis_tables_recorded", f"capacity_rows={len(capacity_rows)}; recovery_rows={len(recovery_rows)}; dd_detail={len(dd_detail)}; dd_regression={len(dd_regression)}; thrash_rows={len(thrash_rows)}", "rung1_separator_scaling")
        required_verdict = {"axes_independence_check", "pool_targets_met", "local_contribution_positive", "keff_constant", "cap_monolith_collapse", "cap_team_survives", "dd_interaction_chrono_dglobal_positive", "dd_interaction_chrono_b_negative", "quant_collapse_matches_law", "kill_interaction_dglobal_not_positive", "kill_capacity_law_mismatch", "kill_forced_not_better", "overall_pass"}
        if results.get("schema_version") in {"rung1_separator_scaling_symbolic_v0_2_1", "rung1_separator_scaling_symbolic_v0_2_2", "rung1_separator_scaling_symbolic_v0_2_3"}:
            required_verdict |= {"fairness_per_agent_cap_equals_D", "fairness_team_within_D_on_solved", "fairness_shared_channel_accounted", "fairness_corner_clean", "kill_team_exceeds_D"}
        if results.get("schema_version") == "rung1_separator_scaling_symbolic_v0_2_2":
            required_verdict |= {"recovery_loop_regression_ok", "trail_predicate_reproduces_monolith", "peak_local_not_pinned_to_block_size"}
        if results.get("schema_version") == "rung1_separator_scaling_symbolic_v0_2_3":
            required_verdict |= {"recovery_loop_regression_ok", "fairness_register_reproduces_capacity_law", "instrumentation_reads_enforced_register", "peak_local_not_pinned_to_block_size"}
        if axes_stop:
            required_verdict = {"axes_independence_check", "overall_pass"}
        fairness_ok = results.get("schema_version") not in {"rung1_separator_scaling_symbolic_v0_2_1", "rung1_separator_scaling_symbolic_v0_2_2", "rung1_separator_scaling_symbolic_v0_2_3"} or acceptance.get("fairness_corner_clean") == verdict_by_check.get("fairness_corner_clean", {}).get("pass")
        verdict_ok = required_verdict.issubset(verdict_by_check) and acceptance.get("overall_pass") == verdict_by_check.get("overall_pass", {}).get("pass") and acceptance.get("llm_version_allowed") == acceptance.get("overall_pass") and fairness_ok
        _check(checks, verdict_ok, "rung1_separator_verdict_and_gate", f"acceptance={acceptance}; verdict_checks={sorted(verdict_by_check)}", "rung1_separator_scaling")


def _rung1_separator_llm_po_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_059_rung1_separator_llm_po", "rung1_separator_llm_po")
    _exists(checks, "rung1_separator_llm_po", "rung1_separator_llm_po")
    item = _read_json("item_059_rung1_separator_llm_po")
    results = _read_json("rung1_separator_llm_po")
    allowed_statuses = {"RUNG1_SEPARATOR_LLM_PO_GATED_STOP", "RUNG1_SEPARATOR_LLM_PO_PREFLIGHT_READY_NOT_RUN"}
    if item:
        _check(checks, item.get("item_number") == "059", "item059_number_present", f"item_number={item.get('item_number')}", "rung1_separator_llm_po")
        _check(checks, item.get("status") in allowed_statuses, "item059_status_valid", f"status={item.get('status')}", "rung1_separator_llm_po")
        tables = item.get("result_tables", {})
        _check(checks, {"gate_preflight", "gpu_inventory", "planned_run_config", "verdict"}.issubset(tables), "item059_required_tables_present", f"tables={sorted(tables)}", "rung1_separator_llm_po")
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        _check(checks, gates.get("symbolic_separator_v0_2_3_fairness_gate") in {"PASS", "STOP"} and gates.get("requested_gpus_visible") in {"PASS", "FAIL"}, "item059_gate_rows_recorded", f"gates={gates}", "rung1_separator_llm_po")
    if results:
        gate = results.get("gate_preflight", {})
        planned = results.get("planned_run_config", {})
        gpu = results.get("gpu_inventory", {})
        verdict_by_check = {row.get("check"): row for row in results.get("verdict", [])}
        gate_pass = bool(gate.get("pass"))
        gated_stop = results.get("status") == "RUNG1_SEPARATOR_LLM_PO_GATED_STOP"
        ready_not_run = results.get("status") == "RUNG1_SEPARATOR_LLM_PO_PREFLIGHT_READY_NOT_RUN"
        schema_status_ok = results.get("schema_version") == "rung1_separator_llm_po_preflight_v0" and results.get("status") in allowed_statuses
        gate_shape_ok = {"symbolic_schema_required", "symbolic_schema_observed", "symbolic_overall_pass", "symbolic_llm_version_allowed", "symbolic_fairness_corner_clean", "requested_gpus", "visible_gpus", "blockers", "p1a_forward_gate_schema_required", "p1a_forward_gate_hardness_ok", "p1a_forward_gate_truncation_ok", "p1a_forward_gate_config_ok"}.issubset(gate)
        no_llm_tables_empty = all(not results.get(name) for name in ["operator_error_breakdown", "keff_inflation", "efficiency_gap_survival", "dstar_vs_inflated_keff", "budget_at_95_solve", "instance_arm_metrics"])
        status_matches_gate = (gated_stop and not gate_pass and bool(gate.get("blockers"))) or (ready_not_run and gate_pass)
        planned_ok = planned.get("model_id") == "Qwen/Qwen3.5-4B" and planned.get("temperature") == 0 and planned.get("max_new_tokens_minimum") == 8192 and planned.get("p1a_prompt_contract") == "p1a_json_only_branch_value_no_reasoning_v1" and planned.get("recommended_initial_batch_size_per_gpu") == 2 and planned.get("oom_retry_batch_size_per_gpu") == 1 and planned.get("gpu_device_ids") == list(range(int(planned.get("requested_gpus", 0)))) and planned.get("comm_budget_sweep") == [64, 128, 192, 256, 384, 512, 768, 1024]
        gpu_ok = int(gpu.get("n_visible", 0)) >= int(gate.get("requested_gpus", 8))
        _check(checks, schema_status_ok and gate_shape_ok and status_matches_gate and no_llm_tables_empty, "rung1_separator_llm_po_gate_fail_closed", f"status={results.get('status')}; gate={gate}", "rung1_separator_llm_po")
        _check(checks, planned_ok and gpu_ok, "rung1_separator_llm_po_plan_and_gpu_recorded", f"planned={planned}; n_visible={gpu.get('n_visible')}", "rung1_separator_llm_po")
        _check(checks, {"symbolic_separator_v0_2_3_fairness_gate", "forward_gate_truncation_ok", "llm_run_started"}.issubset(verdict_by_check), "rung1_separator_llm_po_verdict_recorded", f"verdict_checks={sorted(verdict_by_check)}", "rung1_separator_llm_po")
    forward_gate_path = _path("rung1_separator_llm_po_forward_gate")
    if forward_gate_path.exists():
        forward_gate = _read_json("rung1_separator_llm_po_forward_gate")
        allowed_forward_statuses = {"RUNG1_SEPARATOR_LLM_PO_FORWARD_GATE_PASS", "RUNG1_SEPARATOR_LLM_PO_FORWARD_GATE_TOO_EASY_STOP"}
        if forward_gate:
            acceptance = forward_gate.get("acceptance", {})
            verdict_by_check = {row.get("check"): row for row in forward_gate.get("verdict", [])}
            metrics = forward_gate.get("instance_arm_metrics", [])
            truncation_rows = forward_gate.get("prelaunch_truncation_gate", [])
            cost_rows = forward_gate.get("recovery_sweep_cost_estimate", [])
            config = forward_gate.get("generation_config", {})
            schema_status_ok = forward_gate.get("schema_version") == "rung1_separator_llm_po_forward_gate_v1" and forward_gate.get("status") in allowed_forward_statuses
            tables_ok = all(forward_gate.get(name) for name in ["operator_error_breakdown", "keff_inflation", "budget_at_95_solve", "instance_arm_metrics", "prelaunch_truncation_gate", "recovery_sweep_cost_estimate"])
            verdict_ok = verdict_by_check.get("kill_po_too_easy", {}).get("pass") == bool(acceptance.get("forward_gate_pass")) and verdict_by_check.get("forward_gate_truncation_ok", {}).get("pass") == bool(acceptance.get("forward_gate_truncation_ok"))
            metric_shape_ok = bool(metrics) and all({"solved", "llm_calls", "generation_valid", "value_misselection", "rho", "model_id", "prompt_contract", "max_new_tokens", "n_per_cell", "batch_size_per_gpu"}.issubset(row) for row in metrics)
            observed_batches = [int(value) for value in config.get("batch_size_per_gpu_observed_values", [])]
            config_ok = config.get("max_new_tokens") == 8192 and config.get("prompt_contract") == "p1a_json_only_branch_value_no_reasoning_v1" and config.get("batch_size_per_gpu_max_allowed") == 2 and config.get("oom_retry_batch_size_per_gpu") == 1 and bool(observed_batches) and max(observed_batches) <= 2
            truncation_ok = bool(truncation_rows) and all(row.get("gate") == "forward_gate_truncation_ok" and row.get("max_deep_frac_truncated_no_answer") <= row.get("threshold") and row.get("max_all_frac_truncated_no_answer") <= row.get("threshold") for row in truncation_rows)
            cost_ok = bool(cost_rows) and all({"pilot_median_calls_per_instance", "estimated_qwen_calls_without_comm_budget_sweep", "estimated_qwen_calls_with_comm_budget_sweep"}.issubset(row) for row in cost_rows)
            _check(checks, schema_status_ok and tables_ok and verdict_ok and metric_shape_ok and config_ok and truncation_ok and cost_ok, "rung1_separator_llm_po_forward_gate_recorded", f"status={forward_gate.get('status')}; acceptance={acceptance}; n_metrics={len(metrics)}; truncation={truncation_rows}; cost={cost_rows[:1]}", "rung1_separator_llm_po")


def _rung1_separator_p1a_recovery_baseline_checks(checks: list[dict[str, Any]]) -> None:
    item_path = _path("item_061_rung1_separator_p1a_recovery_baseline")
    baseline_path = _path("rung1_separator_llm_po_p1a_recovery_baseline")
    if item_path.exists():
        item = _read_json("item_061_rung1_separator_p1a_recovery_baseline")
        if item:
            tables = item.get("result_tables", {})
            required_tables = {"decoupling_survival", "keff_inflation", "operator_error_breakdown", "arm_cell_summary", "budget_at_95_solve", "call_cap_truncation_rates", "calls_censoring_summary", "calls_censoring_interaction", "solve_gap_by_cell", "solve_rate_interaction", "legacy_comm_solved_only_regression", "verdict"}
            _check(checks, item.get("item_number") == "061", "item061_number_present", f"item_number={item.get('item_number')}", "rung1_separator_p1a_recovery_baseline")
            _check(checks, item.get("status") in {"RUNG1_SEPARATOR_LLM_PO_P1A_RECOVERY_BASELINE_PASS", "RUNG1_SEPARATOR_LLM_PO_P1A_RECOVERY_BASELINE_FAIL"}, "item061_status_valid", f"status={item.get('status')}", "rung1_separator_p1a_recovery_baseline")
            _check(checks, required_tables.issubset(tables), "item061_required_tables_present", f"tables={sorted(tables)}", "rung1_separator_p1a_recovery_baseline")
    if baseline_path.exists():
        baseline = _read_json("rung1_separator_llm_po_p1a_recovery_baseline")
        if baseline:
            config = baseline.get("generation_config", {})
            acceptance = baseline.get("acceptance", {})
            verdict_by_check = {row.get("check"): row for row in baseline.get("verdict", [])}
            metrics = baseline.get("instance_arm_metrics", [])
            op_rows = baseline.get("operator_error_breakdown", [])
            keff_rows = baseline.get("keff_inflation", [])
            decoupling = baseline.get("decoupling_survival", [])
            calls_censoring = baseline.get("calls_censoring_interaction", [])
            solve_interaction = baseline.get("solve_rate_interaction", [])
            solve_gap = baseline.get("solve_gap_by_cell", [])
            legacy_decoupling = baseline.get("legacy_comm_solved_only_regression", [])
            arm_cell = baseline.get("arm_cell_summary", [])
            budget = baseline.get("budget_at_95_solve", [])
            required_arms = {"cbj_bounded_team_qwen_p1a", "chronological_rollback_team_qwen_p1a", "forward_markov_team_qwen_p1a"}
            requested_cells = {"corner_local_heavy", "dg_m2_dl5_b2", "dg_m4_dl5_b2", "dg_m6_dl5_b2", "b_b12_mid_dglobal"}
            schema_status_ok = baseline.get("schema_version") in {"rung1_separator_llm_po_p1a_recovery_baseline_v0", "rung1_separator_llm_po_p1a_recovery_baseline_v1"} and baseline.get("status") in {"RUNG1_SEPARATOR_LLM_PO_P1A_RECOVERY_BASELINE_PASS", "RUNG1_SEPARATOR_LLM_PO_P1A_RECOVERY_BASELINE_FAIL"}
            config_ok = config.get("model_id") == "Qwen/Qwen3.5-4B" and config.get("temperature") == 0 and config.get("prompt_contract") == "p1a_json_only_branch_value_no_reasoning_v1" and config.get("thinking_disabled") is True and config.get("max_new_tokens") == 8192 and config.get("gpu_device_ids") == [0, 1, 2, 3] and set(config.get("arms", [])) == required_arms and set(config.get("requested_cells", [])) == requested_cells and config.get("per_instance_llm_call_cap") == 200 and config.get("comm_budget_sweep") == [64, 128, 192, 256, 384, 512, 768, 1024]
            metric_shape_ok = bool(metrics) and all({"arm", "requested_cell_id", "solved", "status", "llm_calls", "call_cap_hit", "comm_tokens_observed", "generation_valid", "generation_truncated_no_answer", "finish_reason_length_count", "value_misselection", "k_eff_clean", "k_eff_inflated", "rho", "oracle_read_only_parallel", "oracle_visible_to_llm_loop", "prompt_contract", "thinking_disabled"}.issubset(row) for row in metrics)
            if baseline.get("schema_version") == "rung1_separator_llm_po_p1a_recovery_baseline_v1":
                table_shape_ok = bool(op_rows) and bool(keff_rows) and bool(decoupling) and bool(arm_cell) and bool(budget) and bool(calls_censoring) and bool(solve_interaction) and bool(solve_gap) and bool(legacy_decoupling)
                verdict_ok = {"cap_robust_decoupling_survives", "censoring_aware_calls_interaction", "uncensored_solve_rate_interaction", "legacy_v0_comm_solved_only_not_decisive", "rho_near_one", "operator_clean", "call_cap_censoring_accounted", "p1a_recovery_baseline_landed"}.issubset(verdict_by_check) and verdict_by_check.get("p1a_recovery_baseline_landed", {}).get("p1a_recovery_baseline_landed") == bool(acceptance.get("p1a_recovery_baseline_landed")) and bool(acceptance.get("cap_robust_decoupling_survives")) and bool(acceptance.get("censoring_aware_calls_interaction_pass")) and bool(acceptance.get("uncensored_solve_rate_interaction_pass"))
            else:
                table_shape_ok = bool(op_rows) and bool(keff_rows) and bool(decoupling) and bool(arm_cell) and bool(budget)
                verdict_ok = {"decoupling_survives", "rho_near_one", "operator_clean", "call_cap_independent", "p1a_recovery_baseline_landed"}.issubset(verdict_by_check) and verdict_by_check.get("p1a_recovery_baseline_landed", {}).get("p1a_recovery_baseline_landed") == bool(acceptance.get("p1a_recovery_baseline_landed"))
            _check(checks, schema_status_ok and config_ok and metric_shape_ok and table_shape_ok and verdict_ok, "rung1_separator_p1a_recovery_baseline_recorded", f"status={baseline.get('status')}; acceptance={acceptance}; n_metrics={len(metrics)}; verdict={verdict_by_check}", "rung1_separator_p1a_recovery_baseline")


def _rung1_separator_fallibility_rungs_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "item_060_rung1_separator_fallibility_rungs", "rung1_separator_fallibility_rungs")
    _exists(checks, "rung1_separator_fallibility_rungs", "rung1_separator_fallibility_rungs")
    item = _read_json("item_060_rung1_separator_fallibility_rungs")
    results = _read_json("rung1_separator_fallibility_rungs")
    allowed_statuses = {"RUNG1_SEPARATOR_FALLIBILITY_RUNGS_REGISTERED_GATED_NOT_RUN", "RUNG1_SEPARATOR_FALLIBILITY_P1B_TRUNCATION_PASS_GATED_FULL_NOT_RUN", "RUNG1_SEPARATOR_FALLIBILITY_P1B_TRUNCATION_FAIL_STOP", "RUNG1_SEPARATOR_FALLIBILITY_P1B_OPERATOR_V11_PASS_GATED_FULL_NOT_RUN", "RUNG1_SEPARATOR_FALLIBILITY_P1B_OPERATOR_V11_RESTRICTED_OR_FAIL_STOP", "RUNG1_SEPARATOR_FALLIBILITY_P1B_GRADED_RECOMPUTE_PASS_GATED_FULL_NOT_RUN", "RUNG1_SEPARATOR_FALLIBILITY_P1B_GRADED_RECOMPUTE_STEP2_REQUIRED", "RUNG1_SEPARATOR_FALLIBILITY_P1B_FULL_TABLE_PASS_P1C_GATED_NOT_RUN", "RUNG1_SEPARATOR_FALLIBILITY_P1B_FULL_TABLE_KILL_LAW_NOT_TRACK_INFLATION_STOP", "RUNG1_SEPARATOR_FALLIBILITY_P1C_TRUNCATION_PASS_FULL_TABLE_READY", "RUNG1_SEPARATOR_FALLIBILITY_P1C_TRUNCATION_FAIL_STOP"}
    if item:
        required_tables = {"gate_preflight", "p1b_raw_inspection_summary", "rung_operator_boundaries", "truncation_gate_contract", "metric_contract", "kill_criteria", "cost_and_run_plan", "honesty_gating", "verdict"}
        if item.get("status") in {"RUNG1_SEPARATOR_FALLIBILITY_P1B_GRADED_RECOMPUTE_PASS_GATED_FULL_NOT_RUN", "RUNG1_SEPARATOR_FALLIBILITY_P1B_GRADED_RECOMPUTE_STEP2_REQUIRED"}:
            required_tables |= {"p1b_graded_functional_gate_by_cell", "p1b_graded_verdict"}
        if item.get("status") in {"RUNG1_SEPARATOR_FALLIBILITY_P1B_FULL_TABLE_PASS_P1C_GATED_NOT_RUN", "RUNG1_SEPARATOR_FALLIBILITY_P1B_FULL_TABLE_KILL_LAW_NOT_TRACK_INFLATION_STOP", "RUNG1_SEPARATOR_FALLIBILITY_P1C_TRUNCATION_PASS_FULL_TABLE_READY", "RUNG1_SEPARATOR_FALLIBILITY_P1C_TRUNCATION_FAIL_STOP"}:
            required_tables |= {"p1b_graded_functional_gate_by_cell", "p1b_graded_verdict", "p1b_full_operator_error_breakdown", "p1b_full_keff_inflation", "p1b_full_capacity_leg", "p1b_full_budget_at_95_solve", "p1b_full_dstar_vs_inflated_keff", "p1b_full_verdict"}
        if item.get("status") in {"RUNG1_SEPARATOR_FALLIBILITY_P1C_TRUNCATION_PASS_FULL_TABLE_READY", "RUNG1_SEPARATOR_FALLIBILITY_P1C_TRUNCATION_FAIL_STOP"}:
            required_tables |= {"p1c_truncation_pilot_state", "p1c_pilot_prelaunch_truncation_gate", "p1c_pilot_instance_rows", "p1c_pilot_verdict"}
        _check(checks, item.get("item_number") == "060", "item060_number_present", f"item_number={item.get('item_number')}", "rung1_separator_fallibility_rungs")
        _check(checks, item.get("status") in allowed_statuses, "item060_status_valid", f"status={item.get('status')}", "rung1_separator_fallibility_rungs")
        tables = item.get("result_tables", {})
        gates = {row.get("gate"): row.get("outcome") for row in item.get("decision", {}).get("gate_outcomes", [])}
        _check(checks, required_tables.issubset(tables), "item060_required_tables_present", f"tables={sorted(tables)}", "rung1_separator_fallibility_rungs")
        _check(checks, gates.get("p1b_truncation_gate") in {"NOT_RUN", "PASS", "FAIL"} and gates.get("p1b_operator_functional_gate") in {"NOT_RUN", "PASS", "FAIL"} and gates.get("p1c_truncation_gate") in {"NOT_RUN", "PASS", "FAIL"} and bool(item.get("honesty", {}).get("does_not_establish")), "item060_gates_fail_closed", f"gates={gates}", "rung1_separator_fallibility_rungs")
    if results:
        planned = results.get("planned_run_config", {})
        gates = {row.get("gate"): row for row in results.get("gate_preflight", [])}
        boundaries = {row.get("rung"): row for row in results.get("rung_operator_boundaries", [])}
        truncation = {row.get("rung"): row for row in results.get("truncation_gate_contract", [])}
        metric_tables = {row.get("table") for row in results.get("metric_contract", [])}
        kills = {row.get("kill") for row in results.get("kill_criteria", [])}
        verdict_by_check = {row.get("check"): row for row in results.get("verdict", [])}
        p1b_full_status = results.get("status") in {"RUNG1_SEPARATOR_FALLIBILITY_P1B_FULL_TABLE_PASS_P1C_GATED_NOT_RUN", "RUNG1_SEPARATOR_FALLIBILITY_P1B_FULL_TABLE_KILL_LAW_NOT_TRACK_INFLATION_STOP", "RUNG1_SEPARATOR_FALLIBILITY_P1C_TRUNCATION_PASS_FULL_TABLE_READY", "RUNG1_SEPARATOR_FALLIBILITY_P1C_TRUNCATION_FAIL_STOP"}
        p1b_full_tables_present = bool(results.get("operator_error_breakdown")) and bool(results.get("keff_inflation")) and bool(results.get("dstar_vs_inflated_keff")) and bool(results.get("budget_at_95_solve"))
        no_p1c_tables = all(not results.get(name) for name in ["decoupling_survival", "cbj_advantage_retention", "solution_validity_completeness"])
        table_state_ok = p1b_full_tables_present and no_p1c_tables if p1b_full_status else all(not results.get(name) for name in ["operator_error_breakdown", "keff_inflation", "dstar_vs_inflated_keff", "budget_at_95_solve", "decoupling_survival", "cbj_advantage_retention", "solution_validity_completeness"])
        schema_status_ok = results.get("schema_version") == "rung1_separator_fallibility_rungs_prereg_v0" and results.get("status") in allowed_statuses
        plan_ok = planned.get("model_id") == "Qwen/Qwen3.5-4B" and planned.get("requested_gpus") == 4 and planned.get("gpu_device_ids") == [0, 1, 2, 3] and planned.get("p1b_operator_version") == "v1_1" and planned.get("p1b_prompt_contract") == "p1b_bounded_structured_domain_propagation_capped_thinking_v1_1" and planned.get("p1b_max_new_tokens_minimum") == 16384 and planned.get("p1b_thinking_budget_requested") == 2500 and planned.get("p1b_answer_token_budget_requested") == 1500 and planned.get("p1b_functional_gate_threshold") == 0.20 and planned.get("p1b_cross_b_pilot_bins") == [2, 4, 8, 12] and planned.get("p1c_max_new_tokens_minimum") == 12288 and planned.get("truncation_rate_threshold") == 0.10
        gate_ok = gates.get("p1a_preflight_and_forward_gate_clean", {}).get("outcome") in {"PASS", "STOP"} and gates.get("p1a_recovery_baseline_landed", {}).get("outcome") in {"PASS", "WAIT"} and gates.get("p1b_truncation_gate", {}).get("outcome") in {"NOT_RUN", "PASS", "FAIL"} and gates.get("p1b_operator_functional_gate", {}).get("outcome") in {"NOT_RUN", "PASS", "FAIL"} and gates.get("p1b_law_tracks_inflated_keff", {}).get("outcome") in {"NOT_RUN", "PASS", "FAIL"} and gates.get("p1c_truncation_gate", {}).get("outcome") in {"NOT_RUN", "PASS", "FAIL"}
        boundary_ok = boundaries.get("P1b_llm_propagation_guarded", {}).get("max_new_tokens_minimum") == 16384 and boundaries.get("P1b_llm_propagation_guarded", {}).get("thinking_required") is True and boundaries.get("P1b_llm_propagation_guarded", {}).get("thinking_budget_requested") == 2500 and boundaries.get("P1b_llm_propagation_guarded", {}).get("operator_version") == "v1_1" and boundaries.get("P1b_llm_propagation_guarded", {}).get("prompt_contract") == "p1b_bounded_structured_domain_propagation_capped_thinking_v1_1" and boundaries.get("P1c_operator_triggered_unguarded", {}).get("max_new_tokens_minimum") == 12288 and boundaries.get("P1c_operator_triggered_unguarded", {}).get("thinking_required") is True
        truncation_ok = truncation.get("P1b_llm_propagation_guarded", {}).get("thinking_disabled") is False and truncation.get("P1b_llm_propagation_guarded", {}).get("thinking_budget_requested") == 2500 and truncation.get("P1b_llm_propagation_guarded", {}).get("answer_token_budget_requested") == 1500 and truncation.get("P1c_operator_triggered_unguarded", {}).get("thinking_disabled") is False
        metric_ok = {"operator_error_breakdown", "operator_functional_gate_by_cell", "p1b_graded_recompute", "keff_inflation", "dstar_vs_inflated_keff", "decoupling_survival", "cbj_advantage_retention", "solution_validity_completeness"}.issubset(metric_tables)
        kill_ok = {"kill_law_not_track_inflation", "kill_decoupling_destroyed", "false_solve_contaminates_solve_advantage"}.issubset(kills)
        p1c_verdict_present = "p1c_launch_correctly_blocked_until_gates" in verdict_by_check or "p1c_launch_correctly_gated" in verdict_by_check
        verdict_ok = {"p1b_launch_correctly_blocked_until_gates", "kill_law_not_track_inflation", "kill_decoupling_destroyed"}.issubset(verdict_by_check) and p1c_verdict_present
        _check(checks, schema_status_ok and plan_ok and gate_ok and boundary_ok and truncation_ok and metric_ok and kill_ok and verdict_ok and table_state_ok, "rung1_separator_fallibility_rungs_preregistered", f"status={results.get('status')}; gates={gates}; metric_tables={sorted(metric_tables)}; kills={sorted(kills)}; p1b_full_tables_present={p1b_full_tables_present}", "rung1_separator_fallibility_rungs")
    raw_path = _path("rung1_separator_p1b_raw_generation_inspection")
    if raw_path.exists():
        raw = _read_json("rung1_separator_p1b_raw_generation_inspection")
        if raw:
            summary = raw.get("summary", {})
            config = raw.get("generation_config", {})
            rows = raw.get("inspection_rows", [])
            classification_counts = summary.get("classification_counts", {})
            finish_counts = summary.get("finish_reason_counts", {})
            schema_status_ok = raw.get("schema_version") == "rung1_separator_p1b_raw_generation_inspection_v0" and raw.get("status") == "P1B_RAW_GENERATION_INSPECTION_COMPLETE"
            config_ok = config.get("prompt_contract") == "p1b_verbose_branch_and_local_propagation_guarded_v0" and config.get("thinking_disabled") is False and config.get("max_new_tokens") == 8192 and config.get("n_shards") == 4
            summary_ok = classification_counts.get("A_rambling_or_unbounded_schema_drift", 0) > 0 and finish_counts.get("length", 0) > 0 and summary.get("frac_length_capped") is not None
            rows_ok = bool(rows) and all({"prompt", "raw_generation", "finish_reason", "output_tokens", "generation_state", "classification", "prompt_contract"}.issubset(row) for row in rows)
            _check(checks, schema_status_ok and config_ok and summary_ok and rows_ok, "rung1_separator_p1b_raw_generation_inspection_recorded", f"status={raw.get('status')}; summary={summary}; n_rows={len(rows)}", "rung1_separator_fallibility_rungs")
    pilot_path = _path("rung1_separator_p1b_truncation_pilot")
    if pilot_path.exists():
        pilot = _read_json("rung1_separator_p1b_truncation_pilot")
        if pilot:
            config = pilot.get("generation_config", {})
            acceptance = pilot.get("acceptance", {})
            truncation_rows = pilot.get("prelaunch_truncation_gate", [])
            metrics = pilot.get("instance_arm_metrics", [])
            verdict_by_check = {row.get("check"): row for row in pilot.get("verdict", [])}
            observed_batches = [int(value) for value in config.get("batch_size_per_gpu_observed_values", [])]
            observed_pilot_steps = [int(value) for value in config.get("pilot_steps_per_instance_observed_values", [])]
            schema_status_ok = pilot.get("schema_version") in {"rung1_separator_p1b_truncation_pilot_v0", "rung1_separator_p1b_truncation_pilot_v1", "rung1_separator_p1b_truncation_pilot_v1_1"} and pilot.get("status") in {"RUNG1_SEPARATOR_P1B_TRUNCATION_GATE_PASS", "RUNG1_SEPARATOR_P1B_TRUNCATION_GATE_FAIL_STOP", "RUNG1_SEPARATOR_P1B_OPERATOR_V11_PILOT_PASS", "RUNG1_SEPARATOR_P1B_OPERATOR_V11_PILOT_RESTRICTED_OR_FAIL"}
            if pilot.get("schema_version") == "rung1_separator_p1b_truncation_pilot_v1":
                config_ok = config.get("max_new_tokens") == 16384 and config.get("thinking_disabled") is True and config.get("thinking_budget_requested") == 0 and config.get("answer_token_budget_requested") == 1500 and config.get("operator_version") == "v1" and config.get("prompt_contract") == "p1b_bounded_structured_domain_propagation_guarded_v1" and config.get("n_shards") == 4 and bool(observed_batches) and max(observed_batches) <= 1 and bool(observed_pilot_steps) and max(observed_pilot_steps) <= 1
            elif pilot.get("schema_version") == "rung1_separator_p1b_truncation_pilot_v1_1":
                config_ok = config.get("max_new_tokens") == 16384 and config.get("thinking_disabled") is False and config.get("thinking_budget_requested") == 2500 and config.get("answer_token_budget_requested") == 1500 and config.get("operator_version") == "v1_1" and config.get("prompt_contract") == "p1b_bounded_structured_domain_propagation_capped_thinking_v1_1" and config.get("n_shards") == 4 and config.get("cross_b_pilot_bins") == [2, 4, 8, 12] and bool(observed_batches) and max(observed_batches) <= 12 and bool(observed_pilot_steps) and max(observed_pilot_steps) <= 1
            else:
                config_ok = config.get("max_new_tokens") == 8192 and config.get("thinking_disabled") is False and config.get("prompt_contract") == "p1b_verbose_branch_and_local_propagation_guarded_v0" and config.get("n_shards") == 4 and bool(observed_batches) and max(observed_batches) <= 1 and bool(observed_pilot_steps) and max(observed_pilot_steps) <= 2
            v11 = pilot.get("schema_version") == "rung1_separator_p1b_truncation_pilot_v1_1"
            tables_ok = all(pilot.get(name) for name in ["operator_error_breakdown", "keff_inflation", "call_cap_recommendation", "instance_arm_metrics", "prelaunch_truncation_gate"]) and (not v11 or all(pilot.get(name) for name in ["operator_functional_gate", "operator_functional_gate_by_cell"]))
            base_metric_fields = {"missed_propagation", "unsound_propagation_rejected", "generation_truncated_no_answer", "generation_valid", "generation_parsable_invalid", "finish_reason", "output_tokens", "rho", "prompt_contract", "thinking_disabled", "batch_size_per_gpu", "pilot_steps_per_instance", "operator_version"}
            v11_metric_fields = {"propagation_opportunities", "correct_propagation_opportunities", "correct_propagation_rate", "thinking_budget_requested"}
            metric_shape_ok = bool(metrics) and all(base_metric_fields.issubset(row) and (not v11 or v11_metric_fields.issubset(row)) for row in metrics)
            truncation_ok = bool(truncation_rows) and all(row.get("gate") == "p1b_truncation_gate" and row.get("max_deep_frac_truncated_or_length", row.get("max_deep_frac_truncated_no_answer")) <= row.get("threshold") and row.get("max_all_frac_truncated_or_length", row.get("max_all_frac_truncated_no_answer")) <= row.get("threshold") for row in truncation_rows) == bool(acceptance.get("p1b_truncation_gate_pass"))
            verdict_ok = verdict_by_check.get("p1b_truncation_gate", {}).get("pass") == bool(acceptance.get("p1b_truncation_gate_pass")) and (not v11 or verdict_by_check.get("p1b_operator_functional_gate", {}).get("pass") == bool(acceptance.get("p1b_operator_functional_gate_pass")))
            operator_rows = pilot.get("operator_error_breakdown", [])
            operator_valid_ok = pilot.get("schema_version") != "rung1_separator_p1b_truncation_pilot_v1" or all(row.get("frac_valid") == 1.0 and row.get("frac_parsable_invalid") == 0.0 for row in operator_rows)
            functional_rows = pilot.get("operator_functional_gate_by_cell", [])
            functional_gate_rows = pilot.get("operator_functional_gate", [])
            functional_ok = not v11 or (bool(functional_rows) and bool(functional_gate_rows) and all({"correct_propagation_rate", "frac_truncated_or_length", "truncation_pass", "functional_pass", "cell_allowed_for_full_table"}.issubset(row) for row in functional_rows) and functional_gate_rows[0].get("pass") == bool(acceptance.get("p1b_operator_functional_gate_pass")))
            _check(checks, schema_status_ok and config_ok and tables_ok and metric_shape_ok and truncation_ok and verdict_ok and operator_valid_ok and functional_ok, "rung1_separator_p1b_truncation_pilot_recorded", f"status={pilot.get('status')}; acceptance={acceptance}; truncation={truncation_rows}; n_metrics={len(metrics)}; operator_rows={operator_rows}; functional_rows={functional_rows}", "rung1_separator_fallibility_rungs")
    graded_path = _path("rung1_separator_p1b_graded_recompute")
    if graded_path.exists():
        graded = _read_json("rung1_separator_p1b_graded_recompute")
        if graded:
            config = graded.get("generation_config", {})
            acceptance = graded.get("acceptance", {})
            cell_rows = graded.get("graded_functional_gate_by_cell", [])
            instance_rows = graded.get("instance_prune_metrics", [])
            verdict_by_check = {row.get("check"): row for row in graded.get("verdict", [])}
            schema_status_ok = graded.get("schema_version") == "rung1_separator_p1b_graded_recompute_v0" and graded.get("status") in {"RUNG1_SEPARATOR_P1B_GRADED_RECOMPUTE_STEP1A_PASS", "RUNG1_SEPARATOR_P1B_GRADED_RECOMPUTE_STEP1B_ENCODING_REPILOT_REQUIRED"}
            config_ok = config.get("source_pilot_schema_version") == "rung1_separator_p1b_truncation_pilot_v1_1" and config.get("source_operator_version") == "v1_1" and config.get("functional_recall_threshold") == 0.2 and config.get("graded_keff_method") == "k_eff_clean + (1 - prune_recall) * (unpruned_k_eff - k_eff_clean)"
            rows_ok = bool(cell_rows) and bool(instance_rows) and all({"prune_precision", "prune_recall", "graded_keff_inflated", "rho_graded", "cell_allowed_for_step3", "truncation_pass"}.issubset(row) for row in cell_rows) and all({"oracle_prune_count", "accepted_prune_count", "rejected_prune_count", "missed_prune_count", "prune_precision", "prune_recall"}.issubset(row) for row in instance_rows)
            pass_consistent = bool(acceptance.get("p1b_graded_functional_gate_pass")) == any(bool(row.get("cell_allowed_for_step3")) for row in cell_rows)
            branch_ok = acceptance.get("step1_branch") in {"1A", "1B"} and bool(acceptance.get("step2_required")) == (acceptance.get("step1_branch") == "1B")
            verdict_ok = verdict_by_check.get("graded_recall_functional_gate", {}).get("pass") == bool(acceptance.get("p1b_graded_functional_gate_pass"))
            _check(checks, schema_status_ok and config_ok and rows_ok and pass_consistent and branch_ok and verdict_ok, "rung1_separator_p1b_graded_recompute_recorded", f"status={graded.get('status')}; acceptance={acceptance}; cells={cell_rows}", "rung1_separator_fallibility_rungs")
    full_path = _path("rung1_separator_p1b_full_table")
    if full_path.exists():
        full = _read_json("rung1_separator_p1b_full_table")
        if full:
            config = full.get("generation_config", {})
            acceptance = full.get("acceptance", {})
            op_rows = full.get("operator_error_breakdown", [])
            keff_rows = full.get("keff_inflation", [])
            capacity_rows = full.get("capacity_leg", [])
            budget_rows = full.get("budget_at_95_solve", [])
            dstar_rows = full.get("dstar_vs_inflated_keff", [])
            metrics = full.get("instance_arm_metrics", [])
            verdict_by_check = {row.get("check"): row for row in full.get("verdict", [])}
            schema_status_ok = full.get("schema_version") == "rung1_separator_p1b_full_table_controlled_v0" and full.get("status") in {"RUNG1_SEPARATOR_P1B_FULL_TABLE_INFLATED_KEFF_TRACK_PASS", "RUNG1_SEPARATOR_P1B_FULL_TABLE_KILL_LAW_NOT_TRACK_INFLATION"}
            config_ok = config.get("source_p1b_graded_recompute_path") == "results/rung1_separator_fallibility_rungs/p1b_graded_recompute.json" and config.get("source_p1b_truncation_pilot_path") == "results/rung1_separator_fallibility_rungs/p1b_truncation_pilot.json" and config.get("allowed_b_bins") == [2, 4, 8, 12] and config.get("n_per_cell") == 24 and config.get("call_cap_rule") == "ceil(source_p1b_v1_1_p90_calls_per_instance * 2)" and config.get("comm_budget_sweep_mode") == "offline_posthoc_no_extra_qwen_calls" and config.get("no_new_qwen_calls") is True
            table_shape_ok = bool(op_rows) and bool(keff_rows) and bool(capacity_rows) and bool(budget_rows) and bool(dstar_rows) and bool(metrics)
            dstar_ok = all({"d_star_observed", "D_over_ln_K_eff_inflated", "residual", "track_pass"}.issubset(row) for row in dstar_rows) and bool(acceptance.get("p1b_law_tracks_inflated_keff")) == all(bool(row.get("track_pass")) for row in dstar_rows)
            metric_shape_ok = all({"instance_id", "d_global_reference", "b", "solved", "status", "k_eff_clean", "k_eff_inflated", "rho_graded", "prune_precision", "prune_recall", "no_new_qwen_calls", "llm_calls_made_in_step3"}.issubset(row) and row.get("no_new_qwen_calls") is True and int(row.get("llm_calls_made_in_step3", -1)) == 0 for row in metrics)
            verdict_ok = verdict_by_check.get("p1b_law_tracks_inflated_keff", {}).get("pass") == bool(acceptance.get("p1b_law_tracks_inflated_keff")) and verdict_by_check.get("kill_law_not_track_inflation", {}).get("pass") == (not bool(acceptance.get("kill_law_not_track_inflation")))
            _check(checks, schema_status_ok and config_ok and table_shape_ok and dstar_ok and metric_shape_ok and verdict_ok, "rung1_separator_p1b_full_table_recorded", f"status={full.get('status')}; acceptance={acceptance}; dstar={dstar_rows}; n_metrics={len(metrics)}", "rung1_separator_fallibility_rungs")


def _canonical_checks(checks: list[dict[str, Any]]) -> None:
    _check(checks, REPO_ROOT == Path("/home/aiscuser/RECURRENT_NN"), "canonical_repo_is_recurrent_nn", f"repo_root={REPO_ROOT}", "p0")
    old_repo = Path("/home/aiscuser/stage_d_llm")
    _check(checks, not old_repo.exists(), "old_stage_d_llm_not_present", f"exists={old_repo.exists()}", "p0")


def _write_markdown(path: Path, checks: list[dict[str, Any]], generated_at: str) -> None:
    passed_count = sum(check["status"] == "PASS" for check in checks)
    failed_count = len(checks) - passed_count
    state_line = "All registered checks pass." if failed_count == 0 else "The current expected state is not all-green: explicit red checks mark remaining blockers rather than hiding them behind a collapsed required-files failure."
    lines = [
        "# RECURRENT_NN Validation Report",
        "",
        f"Generated at: {generated_at}",
        "",
        f"Summary: {passed_count} PASS / {failed_count} FAIL / {len(checks)} total.",
        "",
        state_line,
        "",
        "## Checks",
        "",
        "| tier | check | status | detail |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(f"| {check['tier']} | {check['name']} | {check['status']} | {check['detail']} |" for check in checks)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_outputs(output_dir: str = "results/validation") -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    checks: list[dict[str, Any]] = []
    _canonical_checks(checks)
    _model_download_checks(checks)
    _module1_checks(checks)
    _gru_checks(checks)
    _m2_checks(checks)
    _stage_a_checks(checks)
    _w3_checks(checks)
    _item_contract_checks(checks)
    _closeout_047_checks(checks)
    _track_b_value_head_retrain_checks(checks)
    _post_review_e1_checks(checks)
    _rung1_distributed_graph_coloring_checks(checks)
    _rung1_gate_distributed_coloring_v01_checks(checks)
    _rung1_gate_distributed_coloring_v02_checks(checks)
    _rung1_phase1_spec_v01_checks(checks)
    _rung1_phase1_r4_natural_pool_checks(checks)
    _rung1_phase1_r3_qwen_oneshot_checks(checks)
    _rung1_phase1_r2_budget_sweep_checks(checks)
    _rung1_separator_scaling_checks(checks)
    _rung1_separator_llm_po_checks(checks)
    _rung1_separator_p1a_recovery_baseline_checks(checks)
    _rung1_separator_fallibility_rungs_checks(checks)
    _legacy_checks(checks)

    passed = all(check["status"] == "PASS" for check in checks)
    out = REPO_ROOT / output_dir
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "n_checks": len(checks),
        "n_pass": sum(check["status"] == "PASS" for check in checks),
        "n_fail": sum(check["status"] == "FAIL" for check in checks),
    }
    payload = {"generated_at": generated_at, "passed": passed, "summary": summary, "checks": checks}
    json_path = out / "validation.json"
    markdown_path = out / "validation.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(markdown_path, checks, generated_at)
    return {"json": str(json_path.relative_to(REPO_ROOT)), "markdown": str(markdown_path.relative_to(REPO_ROOT)), **payload}


if __name__ == "__main__":
    result = validate_outputs()
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)
