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
    "log_item_contract_spec": "specs/log_item_contract.md",
}


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
    continuation = _read_json("continuation_post_027")
    _exists(checks, "stage_a_manifest", "tier_b")
    _exists(checks, "stage_a_results", "tier_b")
    _exists(checks, "stage_a_report", "tier_b")
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
    _check(checks, bool(sudoku6) and float(sudoku6.get("G1", 0.0)) > 0.0, "stage_a_sudoku6_g1_pass", "expected to fail until P1 fixes bridge G1", "tier_b")
    _check(checks, bool(sudoku6) and sudoku6.get("reverts_nonzero_on_L4") is True, "stage_a_reverts_nonzero_on_L4", "expected restored registry check", "tier_b")
    _check(checks, bool(sudoku6) and sudoku6.get("forward_floor_on_L4") is True, "stage_a_forward_floor_on_L4", "expected restored registry check", "tier_b")


def _w3_checks(checks: list[dict[str, Any]]) -> None:
    _exists(checks, "w3_qwen35_probe_spec", "tier_c")
    _exists(checks, "w3_qwen35_probe", "tier_c")
    probe = _read_json("w3_qwen35_probe")
    if probe:
        verdicts = probe.get("verdicts", {})
        _check(checks, probe.get("model_id") == "Qwen/Qwen3.5-4B", "w3_qwen35_model_id", f"model_id={probe.get('model_id')}", "tier_c")
        _check(checks, verdicts.get("W3.0_checkpoint_pin") == "PASS", "w3_checkpoint_pin_pass", f"verdict={verdicts.get('W3.0_checkpoint_pin')}", "tier_c")
        _check(checks, probe.get("integration_grade") == "do_not_integrate_yet", "w3_metadata_only_not_overclaimed", f"integration_grade={probe.get('integration_grade')}", "tier_c")


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
        missing_artifacts = [artifact for artifact in artifact_paths if not (REPO_ROOT / artifact).exists()]
        _check(checks, not missing_artifacts, f"log_item_{item_number}_artifacts_exist", f"missing={missing_artifacts}", "contract")
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


def _legacy_checks(checks: list[dict[str, Any]]) -> None:
    for name in ["ttt_legacy", "legacy_two_by_two", "legacy_d_stage_1", "legacy_d_stage_2", "legacy_d_stage_3", "legacy_verifier"]:
        _exists(checks, name, "legacy")
    ttt = _read_json("ttt_legacy")
    if ttt:
        _check(checks, ttt.get("ttt_restore_error", 0) > ttt.get("structured_restore_error", 0), "ttt_irreversibility_real", f"ttt={ttt.get('ttt_restore_error')}, structured={ttt.get('structured_restore_error')}", "legacy")


def _canonical_checks(checks: list[dict[str, Any]]) -> None:
    _check(checks, REPO_ROOT == Path("/home/aiscuser/RECURRENT_NN"), "canonical_repo_is_recurrent_nn", f"repo_root={REPO_ROOT}", "p0")
    old_repo = Path("/home/aiscuser/stage_d_llm")
    _check(checks, not old_repo.exists(), "old_stage_d_llm_not_present", f"exists={old_repo.exists()}", "p0")


def _write_markdown(path: Path, checks: list[dict[str, Any]], generated_at: str) -> None:
    passed_count = sum(check["status"] == "PASS" for check in checks)
    failed_count = len(checks) - passed_count
    lines = [
        "# RECURRENT_NN Validation Report",
        "",
        f"Generated at: {generated_at}",
        "",
        f"Summary: {passed_count} PASS / {failed_count} FAIL / {len(checks)} total.",
        "",
        "The current expected state is not all-green: Stage A post-027 blockers should be visible as explicit red checks, not hidden behind a single required-files failure.",
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
