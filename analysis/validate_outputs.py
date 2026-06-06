"""Validate Stage D scaffold outputs before writing the experiment log."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


REQUIRED_FILES = {
    "preregistration": "results/preregistration/preregistration.json",
    "oracle_dataset_summary": "results/oracle_dataset/summary.json",
    "oracle_dataset_examples": "results/oracle_dataset/examples.jsonl",
    "operator_cache": "results/operator_cache/summary.json",
    "model_readiness": "results/model_readiness/readiness.json",
    "qwen_instruct_download": "results/model_download/qwen_download.json",
    "qwen_thinking_download": "results/model_download/thinking/qwen_download.json",
    "qwen_probe_cache": "results/operator_cache/qwen_probe_cache_summary.json",
    "qwen_128_cache": "results/operator_cache/qwen_128_cache_summary.json",
    "learned_wiring_qwen_128": "results/learned_wiring_qwen_128/results.json",
    "qwen_balanced_320_cache": "results/operator_cache/qwen_balanced_320_cache_summary.json",
    "learned_wiring_qwen_balanced_320": "results/learned_wiring_qwen_balanced_320/results.json",
    "module1_stack_capacity": "results/module1_stack_capacity/results.json",
    "module1_stack_capacity_full": "results/module1_stack_capacity_full/results.json",
    "module1_capacity_benchmark_full_shards": "results/module1_capacity_benchmark_full_shards/results.json",
    "module1_k_direction_corrected": "results/module1_capacity_benchmark_full_shards/k_direction_corrected.json",
    "module1_capacity_diagnostic_full_shards": "results/module1_capacity_diagnostic_full_shards/results.json",
    "module1_capacity_perdepth_shards": "results/module1_capacity_perdepth_shards/results.json",
    "module1_capacity_batching_large": "results/module1_capacity_batching_large/results.json",
    "module1_gru_smoke": "results/gru_stack_smoke/results.json",
    "module1_gru_grid_full": "results/gru_stack_grid_full/results.json",
    "module1_gru_degeneracy_diagnostic": "results/gru_degeneracy_diagnostic/results.json",
    "module1_gru_grid_fair": "results/gru_stack_grid_fair/results.json",
    "module1_gru_vs_structured_closeout": "results/gru_vs_structured_closeout/results.json",
    "learned_wiring": "results/learned_wiring/results.json",
    "two_by_two": "results/two_by_two/results.json",
    "d_stage_0": "results/d_stage_0/results.json",
    "d_stage_1": "results/d_stage_1/results.json",
    "d_stage_2": "results/d_stage_2/results.json",
    "d_stage_3": "results/d_stage_3/results.json",
    "verifier": "results/verifier/results.json",
    "ttt": "results/ttt/results.json",
    "analysis_summary": "results/analysis/summary.md",
}

ALLOWED_ACTIONS = {"propagate", "branch", "revert", "done"}


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _check(condition: bool, name: str, detail: str, checks: list[dict[str, Any]]) -> None:
    checks.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})


def _row_field_check(rows: list[dict[str, Any]], fields: list[str]) -> bool:
    return all(field in row and row[field] is not None for row in rows for field in fields)


def _load_required() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    missing = [path for path in REQUIRED_FILES.values() if not os.path.exists(path)]
    _check(not missing, "required_files_present", f"missing={missing}", checks)
    if missing:
        return {}, checks
    data = {name: _read_json(path) for name, path in REQUIRED_FILES.items() if path.endswith(".json")}
    return data, checks


def _dataset_action_checks(summary: dict[str, Any], examples_path: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts: Counter[str] = Counter()
    invalid_actions: Counter[str] = Counter()
    n_lines = 0
    with open(examples_path, "r", encoding="utf-8") as handle:
        for line in handle:
            n_lines += 1
            row = json.loads(line)
            action = row.get("target_action")
            action_counts[action] += 1
            if action not in ALLOWED_ACTIONS:
                invalid_actions[action] += 1
    _check(n_lines == summary["n_examples"], "oracle_dataset_line_count", f"jsonl={n_lines}, summary={summary['n_examples']}", checks)
    _check(not invalid_actions, "oracle_dataset_actions_valid", f"invalid={dict(invalid_actions)}", checks)
    _check(ALLOWED_ACTIONS.issubset(set(action_counts)), "oracle_dataset_has_all_actions", f"counts={dict(action_counts)}", checks)
    _check(summary.get("supervision") == "symbolic_oracle_trace", "oracle_dataset_supervision", f"supervision={summary.get('supervision')}", checks)
    return {"n_examples_seen": n_lines, "action_counts": dict(action_counts)}


def _two_by_two_status(rows: list[dict[str, Any]]) -> bool:
    latent_prop = next(row for row in rows if row["method"] == "latent_only" and row["column"] == "propagation_only")
    structured_prop = next(row for row in rows if row["method"] == "latent_plus_structured_register" and row["column"] == "propagation_only")
    latent_bt = next(row for row in rows if row["method"] == "latent_only" and row["column"] == "backtracking_required")
    structured_bt = next(row for row in rows if row["method"] == "latent_plus_structured_register" and row["column"] == "backtracking_required")
    return structured_bt["solve_rate"] > latent_bt["solve_rate"] and structured_prop["solve_rate"] == latent_prop["solve_rate"]


def _depth1_status(rows: list[dict[str, Any]]) -> bool:
    by_method = {row["method"]: row for row in rows}
    structured = by_method["structured_register"]
    latent = by_method["latent_only"]
    return structured["applied_reverts"] > 0 and structured["solve_rate"] > latent["solve_rate"] and by_method["gru_register"]["solve_rate"] == latent["solve_rate"] and by_method["no_revert_ablation"]["solve_rate"] == latent["solve_rate"]


def _verifier_status(rows: list[dict[str, Any]]) -> bool:
    by_mode = {row["mode"]: row for row in rows}
    return by_mode["oracle"]["solve_rate"] >= by_mode["learned"]["solve_rate"] >= by_mode["noisy"]["solve_rate"] >= by_mode["disabled"]["solve_rate"]


def _stage3_status(rows: list[dict[str, Any]]) -> bool:
    grouped: dict[tuple[int, int], dict[str, int]] = {}
    for row in rows:
        last_solved = max(point["depth"] for point in row["solve_curve"] if point["solve_rate"] > 0)
        grouped.setdefault((row["D"], row["K"]), {})[row["method"]] = last_solved
    return all(methods["latent_structured"] >= methods["qwen_thinking_cot"] >= methods["naive_pass_scaling"] for methods in grouped.values())


def _write_markdown(path: Path, checks: list[dict[str, Any]], dataset_stats: dict[str, Any], generated_at: str) -> None:
    lines = [
        "# Stage D Validation Report",
        "",
        f"Generated at: {generated_at}",
        "",
        "## Checks",
        "",
        "| check | status | detail |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {check['name']} | {check['status']} | {check['detail']} |" for check in checks)
    lines.extend([
        "",
        "## Oracle Dataset Actions",
        "",
        "| action | count |",
        "| --- | --- |",
    ])
    lines.extend(f"| {action} | {count} |" for action, count in sorted(dataset_stats.get("action_counts", {}).items()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_outputs(output_dir: str = "results/validation") -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    data, checks = _load_required()
    dataset_stats: dict[str, Any] = {}
    if data:
        dataset_stats = _dataset_action_checks(data["oracle_dataset_summary"], REQUIRED_FILES["oracle_dataset_examples"], checks)
        _check(data["operator_cache"]["n_examples"] == data["oracle_dataset_summary"]["n_examples"], "operator_cache_example_count", f"cache={data['operator_cache']['n_examples']}, dataset={data['oracle_dataset_summary']['n_examples']}", checks)
        _check(os.path.exists(data["operator_cache"]["cache"]), "operator_cache_file_exists", data["operator_cache"]["cache"], checks)
        _check("transformers_available" in data["model_readiness"], "model_readiness_recorded", f"transformers_available={data['model_readiness'].get('transformers_available')}, cuda_available={data['model_readiness'].get('cuda_available')}", checks)
        _check(data["model_readiness"].get("transformers_available") is True, "uv_transformers_available", "transformers available in uv environment", checks)
        _check(data["qwen_instruct_download"]["total_gib"] > 1.0, "qwen_instruct_downloaded", f"path={data['qwen_instruct_download']['snapshot_path']}", checks)
        _check(data["qwen_thinking_download"]["total_gib"] > 1.0, "qwen_thinking_downloaded", f"path={data['qwen_thinking_download']['snapshot_path']}", checks)
        _check(data["qwen_probe_cache"]["feature_source"] == "Qwen/Qwen3-4B-Instruct-2507" and data["qwen_probe_cache"]["hidden_dim"] == 2560, "qwen_probe_cache_valid", f"hidden_dim={data['qwen_probe_cache']['hidden_dim']}, n_examples={data['qwen_probe_cache']['n_examples']}", checks)
        _check(data["qwen_128_cache"]["feature_source"] == "Qwen/Qwen3-4B-Instruct-2507" and data["qwen_128_cache"]["n_examples"] == 128, "qwen_128_cache_valid", f"hidden_dim={data['qwen_128_cache']['hidden_dim']}, n_examples={data['qwen_128_cache']['n_examples']}", checks)
        _check(data["learned_wiring_qwen_128"]["feature_source"] == "Qwen/Qwen3-4B-Instruct-2507" and data["learned_wiring_qwen_128"]["n_examples"] == 128, "qwen_128_learned_wiring_recorded", f"action_accuracy={data['learned_wiring_qwen_128']['action_accuracy']:.4f}, verifier_accuracy={data['learned_wiring_qwen_128']['verifier_accuracy']:.4f}", checks)
        _check(data["qwen_balanced_320_cache"]["feature_source"] == "Qwen/Qwen3-4B-Instruct-2507" and data["qwen_balanced_320_cache"]["n_examples"] == 320 and len(data["qwen_balanced_320_cache"].get("seed_counts", {})) == 5, "qwen_balanced_320_cache_valid", f"seed_counts={data['qwen_balanced_320_cache'].get('seed_counts')}", checks)
        _check(data["learned_wiring_qwen_balanced_320"]["holdout_action_accuracy"] >= 0.8 and data["learned_wiring_qwen_balanced_320"]["n_holdout_examples"] > 0, "qwen_balanced_320_holdout_action", f"holdout_action_accuracy={data['learned_wiring_qwen_balanced_320']['holdout_action_accuracy']:.4f}", checks)
        module1 = data["module1_stack_capacity"]
        rotation_rows = [row for row in module1["summary"] if row["method"] == "rotation_vsa"]
        tape_rows = [row for row in module1["summary"] if row["method"] == "tape"]
        gru_rows = [row for row in module1["summary"] if row["method"] == "gru_proxy_last_pop"]
        _check(module1["module"] == "module1_bounded_reversible_stack" and module1["mode"] == "quick", "module1_quick_result_present", f"rows={len(module1['rows'])}, summary={len(module1['summary'])}", checks)
        _check(all(row["frontier_decode_095"] >= 1 for row in rotation_rows), "module1_rotation_nonzero_frontier", f"frontiers={[row['frontier_decode_095'] for row in rotation_rows]}", checks)
        _check(all(row["frontier_decode_095"] >= max(gru["frontier_decode_095"] for gru in gru_rows if gru["D"] == row["D"] and gru["K"] == row["K"]) for row in rotation_rows), "module1_rotation_beats_gru_proxy", "rotation frontier >= matched GRU proxy frontier", checks)
        _check(all(row["frontier_decode_095"] >= max(rot["frontier_decode_095"] for rot in rotation_rows if rot["D"] == row["D"] and rot["K"] == row["K"]) for row in tape_rows), "module1_tape_upper_bound", "tape frontier >= rotation frontier", checks)
        module1_full = data["module1_stack_capacity_full"]
        full_rotation_rows = [row for row in module1_full["summary"] if row["method"] == "rotation_vsa"]
        full_tape_rows = [row for row in module1_full["summary"] if row["method"] == "tape"]
        full_gru_rows = [row for row in module1_full["summary"] if row["method"] in {"gru_proxy_sequence", "gru_proxy_last_pop"}]
        _check(module1_full["mode"] == "full" and module1_full.get("device") == "cuda:0" and len(module1_full["seeds"]) >= 3, "module1_full_gpu_result_present", f"rows={len(module1_full['rows'])}, summary={len(module1_full['summary'])}, seeds={module1_full['seeds']}", checks)
        _check(all(row["frontier_decode_095"] >= max(gru["frontier_decode_095"] for gru in full_gru_rows if gru["D"] == row["D"] and gru["K"] == row["K"]) for row in full_rotation_rows), "module1_full_rotation_beats_gru_proxy", "rotation frontier >= matched GRU proxy frontier", checks)
        _check(all(row["frontier_decode_095"] >= max(rot["frontier_decode_095"] for rot in full_rotation_rows if rot["D"] == row["D"] and rot["K"] == row["K"]) for row in full_tape_rows), "module1_full_tape_upper_bound", "tape frontier >= rotation frontier", checks)
        benchmark = data["module1_capacity_benchmark_full_shards"]
        _check(benchmark["mode"] == "full" and benchmark["device"] == "8x_cuda_sharded" and benchmark["num_shards"] == 8, "module1_capacity_benchmark_full_sharded_present", f"rows={len(benchmark['rows'])}, summary={len(benchmark['summary'])}", checks)
        _check(benchmark["theory"]["calibrated_c"] is not None, "module1_constant_calibrated", f"c={benchmark['theory']['calibrated_c']}", checks)
        open_ok = benchmark["theory"].get("open") is True or benchmark["theory"]["decision"] == "theory_direction_holds"
        _check(open_ok, "module1_k_direction_recorded", f"decision={benchmark['theory']['decision']}, open={benchmark['theory'].get('open')}", checks)
        corrected = data["module1_k_direction_corrected"]
        _check(corrected["expected_target_passed"] is True, "module1_k_direction_ceiling_corrected", f"target={corrected['expected_target']['classification']}, dropped={[(p['K_var'], p['frontier']) for p in corrected['expected_target']['dropped_points']]}", checks)
        diagnostic = data["module1_capacity_diagnostic_full_shards"]
        _check(diagnostic["mode"] == "full" and diagnostic["device"] == "8x_cuda_sharded" and diagnostic["num_shards"] == 8, "module1_diagnostic_full_sharded_present", f"rows={len(diagnostic['rows'])}, summary={len(diagnostic['summary'])}", checks)
        _check(diagnostic.get("open") is True or diagnostic["decision"] == "k_direction_negative", "module1_diagnostic_k_direction_recorded", f"decision={diagnostic['decision']}, open={diagnostic.get('open')}", checks)
        perdepth = data["module1_capacity_perdepth_shards"]
        _check(perdepth["decision"] == "k_direction_negative" and perdepth["open"] is False, "module1_perdepth_k_direction_negative", f"decision={perdepth['decision']}, open={perdepth['open']}", checks)
        _check(all(all(sign <= 0 for sign in item["signs"]) for item in perdepth["directions"]), "module1_perdepth_with_without_agree", "all joint/var/val directions are non-increasing for with/without replacement", checks)
        fit_best = {(fit["variant"], fit["replacement"]): fit["best_k_eff"] for fit in perdepth["fits"] if fit["metric"] == "joint"}
        _check(fit_best.get(("bound_single", "with_replacement")) == "D_over_ln_product" and fit_best.get(("factored", "with_replacement")) == "D_over_ln_Kvar", "module1_perdepth_keff_fit_recorded", f"best={fit_best}", checks)
        batching = data["module1_capacity_batching_large"]
        _check(max(row["trials_per_sec"] for row in batching["rows"]) > 0 and any(row["batch_size"] >= 8192 for row in batching["best_by_case"]), "module1_batching_recorded", f"best_batches={[row['batch_size'] for row in batching['best_by_case']]}", checks)
        gru_smoke = data["module1_gru_smoke"]
        _check(gru_smoke["converged"] is True and gru_smoke["selection"] == "val_loss_min" and os.path.exists(gru_smoke["checkpoint"]), "module1_gru_smoke_converged", f"frontier={gru_smoke['frontier_joint_095']}, checkpoint={gru_smoke['checkpoint']}", checks)
        gru_grid = data["module1_gru_grid_full"]
        _check(gru_grid["all_converged"] is True and gru_grid["n_cells"] == 144, "module1_gru_light_run_recorded", f"cells={gru_grid['n_cells']}, summary={len(gru_grid['summary'])}, light run is not headline evidence", checks)
        diagnostic_gru = data["module1_gru_degeneracy_diagnostic"]
        _check(diagnostic_gru["verdict"] in {"degenerate_recency", "undertrained", "genuine_limit_candidate"}, "module1_gru_diagnostic_verdict_recorded", f"verdict={diagnostic_gru['verdict']}, proceed_to_task_b={diagnostic_gru['proceed_to_task_b']}", checks)
        fair_gru = data["module1_gru_grid_fair"]
        fair_scaling = fair_gru.get("capacity_vs_D", [])
        fair_slope_recorded = bool(fair_scaling) and all("slope" in row and "slope_positive" in row for row in fair_scaling)
        _check(fair_slope_recorded, "module1_gru_D_scaling_recorded", f"groups={len(fair_scaling)}, slopes={[row.get('slope') for row in fair_scaling]}", checks)
        fair_shallow = fair_gru.get("shallow_sanity_D1024", {})
        _check(fair_shallow.get("depth2_passes_095") is True, "module1_gru_shallow_sanity", f"min_depth2={fair_shallow.get('min_depth2_joint_accuracy')}, min_depth3={fair_shallow.get('min_depth3_joint_accuracy')}", checks)
        fair_training = fair_gru.get("training_sufficiency", {})
        _check(fair_training.get("all_training_sufficient") is True, "module1_gru_training_sufficient", f"min_steps={fair_training.get('min_steps_requested')}, min_patience={fair_training.get('min_patience_requested')}, min_train_depth={fair_training.get('min_train_max_depth')}, required={fair_training.get('eval_depth_required')}", checks)
        _check(fair_gru.get("all_converged") is True and fair_gru.get("n_cells") == 144, "module1_gru_fair_grid_converged", f"cells={fair_gru.get('n_cells')}, summary={len(fair_gru.get('summary', []))}", checks)
        _check(fair_gru.get("all_gru_below_structured") is True and fair_training.get("all_training_sufficient") is True and fair_shallow.get("depth2_passes_095") is True, "module1_gru_below_structured_demoted", "ordering contributes only after fair training and shallow sanity pass", checks)
        closeout = data["module1_gru_vs_structured_closeout"]
        _check(closeout.get("classification") in {"CLEAN_NEGATIVE_SUBLINEAR", "RECENCY_COLLAPSE", "GRU_RISES"}, "module1_gru_closeout_classified", f"classification={closeout.get('classification')}, lock={closeout.get('lock_structured_headline')}", checks)
        _check(data["learned_wiring"]["n_examples"] == data["operator_cache"]["n_examples"], "learned_wiring_example_count", f"learned={data['learned_wiring']['n_examples']}, cache={data['operator_cache']['n_examples']}", checks)
        _check(os.path.exists(data["learned_wiring"]["model"]), "learned_wiring_model_exists", data["learned_wiring"]["model"], checks)
        _check(data["learned_wiring"]["action_accuracy"] >= 0.95, "learned_wiring_action_accuracy", f"action_accuracy={data['learned_wiring']['action_accuracy']:.4f}", checks)
        _check(data["learned_wiring"]["verifier_accuracy"] >= 0.95, "learned_wiring_verifier_accuracy", f"verifier_accuracy={data['learned_wiring']['verifier_accuracy']:.4f}", checks)
        _check(_row_field_check(data["two_by_two"], ["method", "column", "n_tasks", "solve_rate", "applied_reverts", "max_required_depth", "evaluation_mode"]), "two_by_two_schema", "required metric fields non-null", checks)
        _check(_row_field_check(data["d_stage_1"], ["method", "n_tasks", "solve_rate", "applied_reverts", "max_required_depth", "evaluation_mode"]), "d_stage_1_schema", "required metric fields non-null", checks)
        _check(_row_field_check(data["d_stage_2"], ["register_type", "D", "K", "observed_frontier", "evaluation_mode"]), "d_stage_2_schema", "required metric fields non-null", checks)
        _check(_row_field_check(data["d_stage_3"], ["D", "K", "method", "predicted_d_star", "matched_compute", "solve_curve", "evaluation_mode"]), "d_stage_3_schema", "required metric fields non-null", checks)
        _check(_row_field_check(data["verifier"], ["mode", "n_tasks", "solve_rate", "false_positive_reverts", "false_negative_misses", "evaluation_mode"]), "verifier_schema", "required metric fields non-null", checks)
        _check(_two_by_two_status(data["two_by_two"]), "d3_two_by_two_gate", "structured helps only backtracking column", checks)
        _check(_depth1_status(data["d_stage_1"]), "d_stage_1_gate", "structured reverts; GRU/no-revert collapse", checks)
        _check(_stage3_status(data["d_stage_3"]), "d_stage_3_ordering", "latent_structured >= CoT >= naive last solved depth", checks)
        _check(_verifier_status(data["verifier"]), "d5_verifier_monotonic", "oracle >= learned >= noisy >= disabled", checks)
        _check(data["ttt"]["ttt_restore_error"] > data["ttt"]["structured_restore_error"], "d6_ttt_reversibility", "TTT restore error greater than structured", checks)

    m2_report_path = "results/m2_operator_probe/report_fix_rescale.json"
    if os.path.exists(m2_report_path):
        m2 = _read_json(m2_report_path)
        verdicts = {task: row.get("verdict") for task, row in m2.get("by_task", {}).items()}
        valid_verdicts = {"PREMISE_HOLDS", "VERIFIER_LOAD_BEARING", "NEEDS_OPERATOR_FIX"}
        _check(bool(verdicts) and all(verdict in valid_verdicts for verdict in verdicts.values()), "m2_per_task_verdicts_recorded", f"verdicts={verdicts}", checks)
        single = m2.get("overall", {}).get("single_iterated", {})
        list_all = m2.get("overall", {}).get("list_all", {})
        _check(bool(single) and bool(list_all), "m2_iterated_ablation_recorded", f"single_keys={list(single)}, list_all_keys={list(list_all)}", checks)
        _check(m2.get("branch_decision") in {"symbolic_mrv_default", "qwen_guess_beats_mrv_reconsider"}, "m2_branch_decision_recorded", f"branch_decision={m2.get('branch_decision')}", checks)

    passed = all(check["status"] == "PASS" for check in checks)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": generated_at, "passed": passed, "checks": checks, "dataset_stats": dataset_stats}
    json_path = out / "validation.json"
    markdown_path = out / "validation.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(markdown_path, checks, dataset_stats, generated_at)
    return {"json": str(json_path), "markdown": str(markdown_path), **payload}


if __name__ == "__main__":
    result = validate_outputs()
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)