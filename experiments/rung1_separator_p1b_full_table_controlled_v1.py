"""Corrected P1b capacity-law discrimination addendum.

This runner fixes the v1 addendum's D/d_global confusion. D is the swept
register-capacity resource, while d_global is the problem-depth axis whose
threshold d*(D, b) is measured at each resource value.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_separator_llm_po_forward_gate import SEPARATOR_RESULTS_PATH
from experiments.rung1_separator_p1b_full_table import (
    DEFAULT_N_PER_CELL,
    GRADED_PATH,
    OUTPUT_PATH as V0_PATH,
    PILOT_PATH,
    _allowed_b_values,
    _call_cap_by_b,
    _operator_by_b,
    _select_manifest,
)
from experiments.rung1_separator_scaling import (
    DEFAULT_NODE_CAP,
    LOW_SOLVE_THRESHOLD,
    _instance_from_row,
    _solve_monolith,
)


RESULTS_ROOT = REPO_ROOT / "results/rung1_separator_fallibility_rungs"
OUTPUT_PATH = RESULTS_ROOT / "p1b_full_table_v1.json"
SCHEMA_VERSION = "rung1_separator_p1b_full_table_controlled_v1_corrected_resource_sweep"
STATUS_PASS = "RUNG1_SEPARATOR_P1B_FULL_TABLE_V1_CORRECTED_DISCRIMINATES_PASS"
STATUS_FAIL = "RUNG1_SEPARATOR_P1B_FULL_TABLE_V1_CORRECTED_DISCRIMINATES_FAIL"
RESOURCE_D_SWEEP = (4, 6, 8, 10, 12, 16)
BASELINE_RESOURCE_D = 6
FIX1_RESIDUAL_TOLERANCE = 1.0
MIN_UNCENSORED_DSTAR_FOR_SLOPE = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _group(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    out: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[tuple(row[key] for key in keys)].append(row)
    return out


def _median_by_b(separator: dict[str, Any], key: str) -> dict[str, float]:
    values: dict[int, list[float]] = defaultdict(list)
    for row in separator.get("instance_manifest", []):
        if key in row and row[key] is not None:
            values[int(row["b"])].append(float(row[key]))
    return {str(b): median(items) for b, items in sorted(values.items()) if items}


def _run_resource_sweep(
    manifest: list[dict[str, Any]],
    operator_by_b: dict[int, dict[str, Any]],
    call_cap_by_b: dict[int, int],
    d_sweep: tuple[int, ...],
    node_cap: int,
) -> list[dict[str, Any]]:
    rows = []
    for register_capacity_d in d_sweep:
        for item in manifest:
            b_value = int(item["b"])
            d_global = int(item["d_global_reference"])
            operator = operator_by_b[b_value]
            k_eff = float(operator["graded_keff_inflated"])
            result = _solve_monolith(_instance_from_row(item), node_cap, register_capacity_d, k_eff)
            rows.append({
                "instance_id": item["instance_id"],
                "cell_id": item["cell_id"],
                "sweep": item["sweep"],
                "d_global_reference": d_global,
                "b": b_value,
                "register_capacity_D": register_capacity_d,
                "rung": "P1b_llm_propagation_guarded",
                "arm": "monolith_cbj_p1b_guarded_inflated_keff_control",
                "solved": bool(result["solved"]),
                "status": result["status"],
                "steps_to_solve_or_cap": int(result["steps"]),
                "comm_tokens": int(result["comm_tokens"]),
                "total_retractions": int(result["total_retractions"]),
                "peak_register_entries": int(result["peak_register_entries"]),
                "overflowed": bool(result["overflowed"]),
                "node_cap": node_cap,
                "call_cap": int(call_cap_by_b.get(b_value, 0)),
                "llm_calls_made_in_step3": 0,
                "no_new_qwen_calls": True,
                "k_eff_clean": float(operator["k_eff_clean"]),
                "k_eff_inflated": k_eff,
                "graded_keff_inflated": k_eff,
                "rho_graded": float(operator["rho_graded"]),
                "prune_precision": float(operator["prune_precision"]),
                "prune_recall": float(operator["prune_recall"]),
                "operator_calibration_cell": operator["cell"],
                "source": SOURCE,
                "provenance": "qwen35_p1b_full_table_corrected_D_sweep_instance_v1",
            })
    return rows


def _capacity_leg(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (register_capacity_d, d_global, b_value), subset in sorted(_group(rows, "register_capacity_D", "d_global_reference", "b").items()):
        k_eff = mean(float(row["k_eff_inflated"]) for row in subset)
        solved_comm = sorted(float(row["comm_tokens"]) for row in subset if row["solved"])
        out.append({
            "rung": "P1b_llm_propagation_guarded",
            "register_capacity_D": int(register_capacity_d),
            "d_global_bin": str(d_global),
            "b_bin": str(b_value),
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "overflow_rate": mean(float(row["overflowed"]) for row in subset),
            "mean_peak_register_entries": mean(float(row["peak_register_entries"]) for row in subset),
            "median_peak_register_entries": median(float(row["peak_register_entries"]) for row in subset),
            "k_eff_inflated": k_eff,
            "D_over_ln_K_eff_inflated_legacy_diagnostic": float(register_capacity_d) / math.log(max(k_eff, 1.0001)),
            "posterior_p95_comm_to_solve": solved_comm[min(len(solved_comm) - 1, math.ceil(0.95 * len(solved_comm)) - 1)] if solved_comm else None,
            "source": SOURCE,
            "provenance": "qwen35_p1b_full_table_corrected_D_sweep_capacity_leg_v1",
        })
    return out


def _separator_footprint_rows(capacity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Measure boundary/separator footprint as peak register minus trail anchor."""
    rows = []
    b_values = sorted({int(row["b_bin"]) for row in capacity_rows})
    for b_value in b_values:
        b_rows = [row for row in capacity_rows if int(row["b_bin"]) == b_value]
        anchor_depth = min(int(row["d_global_bin"]) for row in b_rows)
        anchor_candidates = [
            row for row in b_rows
            if int(row["register_capacity_D"]) == BASELINE_RESOURCE_D and int(row["d_global_bin"]) == anchor_depth
        ]
        if not anchor_candidates:
            anchor_candidates = [row for row in b_rows if int(row["d_global_bin"]) == anchor_depth]
        measured_peak = mean(float(row["mean_peak_register_entries"]) for row in anchor_candidates)
        footprint = max(0.0, measured_peak - float(anchor_depth))
        rows.append({
            "b_bin": str(b_value),
            "footprint_b": footprint,
            "measurement_register_capacity_D": int(anchor_candidates[0]["register_capacity_D"]),
            "anchor_d_global": anchor_depth,
            "anchor_mean_peak_register_entries": measured_peak,
            "trail_component_subtracted": float(anchor_depth),
            "measurement_note": "D-unit boundary/separator footprint = measured peak register entries at shallow anchor minus anchor d_global trail component",
            "source": SOURCE,
            "provenance": "p1b_full_table_v1_corrected_measured_separator_footprint",
        })
    return rows


def _interpolate_dstar(depth_rates: list[tuple[int, float]]) -> dict[str, Any]:
    ordered = sorted(depth_rates)
    if not ordered:
        return {"dstar_observed": None, "censoring": "no_depth_rows"}
    threshold = LOW_SOLVE_THRESHOLD
    first_depth, first_rate = ordered[0]
    if first_rate <= threshold:
        return {
            "dstar_observed": None,
            "censoring": "left_censored_below_min_depth",
            "dstar_upper_bound": float(first_depth),
            "supporting_solve_rates": {str(depth): rate for depth, rate in ordered},
        }
    previous_depth, previous_rate = ordered[0]
    for depth, rate in ordered[1:]:
        if rate <= threshold:
            if previous_rate == rate:
                crossing = float(previous_depth)
            else:
                crossing = float(previous_depth) + (threshold - previous_rate) * float(depth - previous_depth) / (rate - previous_rate)
            return {
                "dstar_observed": crossing,
                "censoring": "uncensored_interpolated",
                "supporting_solve_rates": {str(item_depth): item_rate for item_depth, item_rate in ordered},
            }
        previous_depth, previous_rate = depth, rate
    return {
        "dstar_observed": float(previous_depth),
        "censoring": "right_censored_at_max_depth",
        "dstar_lower_bound": float(previous_depth),
        "supporting_solve_rates": {str(depth): rate for depth, rate in ordered},
    }


def _observed_dstar_rows(capacity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for (register_capacity_d, b_bin), subset in sorted(_group(capacity_rows, "register_capacity_D", "b_bin").items(), key=lambda item: (int(item[0][0]), int(item[0][1]))):
        depth_rates = [(int(row["d_global_bin"]), float(row["solve_rate"])) for row in subset]
        interpolated = _interpolate_dstar(depth_rates)
        k_eff = mean(float(row["k_eff_inflated"]) for row in subset)
        rows.append({
            "rung": "P1b_llm_propagation_guarded",
            "register_capacity_D": int(register_capacity_d),
            "b_bin": str(b_bin),
            "k_eff_inflated": k_eff,
            "collapse_threshold_solve_rate": LOW_SOLVE_THRESHOLD,
            "source": SOURCE,
            "provenance": "p1b_full_table_v1_corrected_observed_dstar_by_D_b",
            **interpolated,
        })
    return rows


def _prediction_rows(dstar_rows: list[dict[str, Any]], footprint_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    footprint_by_b = {row["b_bin"]: float(row["footprint_b"]) for row in footprint_rows}
    out = []
    for row in dstar_rows:
        footprint = footprint_by_b[row["b_bin"]]
        k_eff = float(row["k_eff_inflated"])
        d_eff_unclamped = float(row["register_capacity_D"]) - footprint
        d_eff = max(0.0, d_eff_unclamped)
        predicted = d_eff / math.log(max(k_eff, 1.0001))
        observed = row.get("dstar_observed")
        residual = None if observed is None else float(observed) - predicted
        upper_bound = row.get("dstar_upper_bound")
        lower_bound = row.get("dstar_lower_bound")
        censored_bound_satisfied = None
        if observed is None and upper_bound is not None:
            censored_bound_satisfied = predicted <= float(upper_bound)
        elif observed is None and lower_bound is not None:
            censored_bound_satisfied = predicted >= float(lower_bound)
        out.append({
            **row,
            "footprint_b": footprint,
            "D_eff_unclamped": d_eff_unclamped,
            "D_eff": d_eff,
            "dstar_predicted_corrected": predicted,
            "residual_corrected": residual,
            "law_track_corrected": abs(residual) <= FIX1_RESIDUAL_TOLERANCE if residual is not None else bool(censored_bound_satisfied),
            "censored_bound_satisfied": censored_bound_satisfied,
            "residual_tolerance": FIX1_RESIDUAL_TOLERANCE,
            "provenance": "p1b_full_table_v1_corrected_refined_law_dstar_vs_Deff",
        })
    return out


def _ols_slope(points: list[tuple[float, float]]) -> dict[str, Any]:
    if len(points) < 2:
        return {"slope_estimate": None, "slope_se": None, "slope_ci_lower": None, "slope_ci_upper": None, "ci_excludes_zero": False}
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_mean = mean(xs)
    y_mean = mean(ys)
    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx <= 0:
        return {"slope_estimate": None, "slope_se": None, "slope_ci_lower": None, "slope_ci_upper": None, "ci_excludes_zero": False}
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / sxx
    intercept = y_mean - slope * x_mean
    residuals = [y - (intercept + slope * x) for x, y in points]
    sigma2 = sum(value * value for value in residuals) / max(len(points) - 2, 1)
    slope_se = math.sqrt(max(sigma2 / sxx, 0.0))
    ci_lower = slope - 1.96 * slope_se
    ci_upper = slope + 1.96 * slope_se
    return {
        "slope_estimate": slope,
        "intercept_estimate": intercept,
        "slope_se": slope_se,
        "slope_ci_lower": ci_lower,
        "slope_ci_upper": ci_upper,
        "ci_excludes_zero": ci_lower > 0 or ci_upper < 0,
    }


def _d_sweep_scaling_rows(prediction_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for (b_bin,), subset in sorted(_group(prediction_rows, "b_bin").items(), key=lambda item: int(item[0][0])):
        uncensored = [row for row in subset if row.get("dstar_observed") is not None and row.get("censoring") != "right_censored_at_max_depth"]
        points_prediction_axis = [(float(row["D_eff_unclamped"]) / math.log(max(float(row["k_eff_inflated"]), 1.0001)), float(row["dstar_observed"])) for row in uncensored]
        points_resource_axis = [(float(row["D_eff_unclamped"]), float(row["dstar_observed"])) for row in uncensored]
        fit_prediction_axis = _ols_slope(points_prediction_axis)
        fit_resource_axis = _ols_slope(points_resource_axis)
        k_eff = mean(float(row["k_eff_inflated"]) for row in subset)
        enough = len(uncensored) >= MIN_UNCENSORED_DSTAR_FOR_SLOPE
        rows.append({
            "b_bin": str(b_bin),
            "n_resource_D_values": len(subset),
            "resource_D_values_tested": [int(row["register_capacity_D"]) for row in subset],
            "n_uncensored_dstar": len(uncensored),
            "n_left_censored": sum(1 for row in subset if row.get("censoring") == "left_censored_below_min_depth"),
            "n_right_censored": sum(1 for row in subset if row.get("censoring") == "right_censored_at_max_depth"),
            "k_eff_inflated": k_eff,
            "expected_slope_on_prediction_axis": 1.0,
            "expected_slope_on_D_minus_footprint_axis": 1.0 / math.log(max(k_eff, 1.0001)),
            "fit_axis": "dstar_observed_vs_(D_minus_footprint)/ln_K_eff_inflated",
            "slope_estimate": fit_prediction_axis.get("slope_estimate"),
            "intercept_estimate": fit_prediction_axis.get("intercept_estimate"),
            "slope_se": fit_prediction_axis.get("slope_se"),
            "slope_ci_lower": fit_prediction_axis.get("slope_ci_lower"),
            "slope_ci_upper": fit_prediction_axis.get("slope_ci_upper"),
            "ci_excludes_zero": bool(fit_prediction_axis.get("ci_excludes_zero")),
            "resource_axis_slope_estimate": fit_resource_axis.get("slope_estimate"),
            "resource_axis_slope_ci_lower": fit_resource_axis.get("slope_ci_lower"),
            "resource_axis_slope_ci_upper": fit_resource_axis.get("slope_ci_upper"),
            "fix2_pass_for_b": enough and bool(fit_prediction_axis.get("ci_excludes_zero")),
            "insufficient_reason": None if enough else f"need >= {MIN_UNCENSORED_DSTAR_FOR_SLOPE} uncensored d* values",
            "source": SOURCE,
            "provenance": "p1b_full_table_v1_corrected_D_resource_sweep_fix2",
        })
    return rows


def _rho_sweep_placeholder() -> list[dict[str, Any]]:
    return [{
        "rho_target": 1.1,
        "operator_version": "v1_1_existing",
        "new_pilot_required": False,
        "status": "existing_step1A_operator_calibration_only",
        "source": SOURCE,
        "provenance": "p1b_full_table_v1_corrected_rho_sweep_fix3_placeholder",
    }, {
        "rho_target": 1.3,
        "operator_version": "v1_2_reduced_thinking",
        "new_pilot_required": True,
        "status": "placeholder_not_yet_implemented",
        "source": SOURCE,
        "provenance": "p1b_full_table_v1_corrected_rho_sweep_fix3_placeholder",
    }, {
        "rho_target": 1.6,
        "operator_version": "v1_3_minimal_thinking",
        "new_pilot_required": True,
        "status": "placeholder_not_yet_implemented",
        "source": SOURCE,
        "provenance": "p1b_full_table_v1_corrected_rho_sweep_fix3_placeholder",
    }]


def _is_nonincreasing(values: list[float]) -> bool:
    return all(left >= right for left, right in zip(values, values[1:]))


def _verdict_rows(prediction_rows: list[dict[str, Any]], d_sweep_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = [row for row in prediction_rows if int(row["register_capacity_D"]) == BASELINE_RESOURCE_D]
    baseline_sorted = sorted(baseline, key=lambda row: int(row["b_bin"]))
    direction_values = [float(row["dstar_observed"] if row.get("dstar_observed") is not None else row.get("dstar_upper_bound", 0.0)) for row in baseline_sorted]
    predicted_values = [float(row["dstar_predicted_corrected"]) for row in baseline_sorted]
    uncensored_baseline = [row for row in baseline_sorted if row.get("dstar_observed") is not None]
    max_abs_residual = max((abs(float(row["residual_corrected"])) for row in uncensored_baseline if row.get("residual_corrected") is not None), default=None)
    bound_ok = all(bool(row.get("law_track_corrected")) for row in baseline_sorted if row.get("dstar_observed") is None)
    fix1_pass = bool(baseline_sorted) and _is_nonincreasing(direction_values) and _is_nonincreasing(predicted_values) and bool(uncensored_baseline) and max_abs_residual is not None and max_abs_residual <= FIX1_RESIDUAL_TOLERANCE and bound_ok
    fix2_pass = bool(d_sweep_rows) and all(bool(row.get("fix2_pass_for_b")) for row in d_sweep_rows)
    fix3_pass = False
    overall = fix1_pass and fix2_pass and fix3_pass
    return [{
        "check": "fix1_separator_aware_law_tracks",
        "requirement": "one d*(D,b) per resource-D,b cell; footprint(b) measured from D-unit peak register boundary component; baseline b-direction tracks observed decrease",
        "observed": f"pass={fix1_pass}; observed_direction={direction_values}; predicted_direction={predicted_values}; max_abs_uncensored_residual={max_abs_residual}; tolerance={FIX1_RESIDUAL_TOLERANCE}; bound_ok={bound_ok}",
        "pass": fix1_pass,
        "source": SOURCE,
        "provenance": "p1b_full_table_v1_corrected_verdict_fix1",
    }, {
        "check": "fix2_resource_D_sweep_slope_ci_excludes_zero",
        "requirement": "sweep register capacity D in {4,6,8,10,12,16}; fit d*(D) against (D-footprint)/ln K_eff with enough uncensored thresholds",
        "observed": f"pass={fix2_pass}; per_b={[(row['b_bin'], row['n_uncensored_dstar'], row['ci_excludes_zero'], row['fix2_pass_for_b']) for row in d_sweep_rows]}",
        "pass": fix2_pass,
        "source": SOURCE,
        "provenance": "p1b_full_table_v1_corrected_verdict_fix2",
    }, {
        "check": "fix3_rho_sweep_paired_discrimination",
        "requirement": "paired inflated-vs-clean rho sweep at rho approx {1.1, 1.3, 1.6}",
        "observed": "not_yet_implemented_after_corrected_FIX1_FIX2",
        "pass": fix3_pass,
        "source": SOURCE,
        "provenance": "p1b_full_table_v1_corrected_verdict_fix3_placeholder",
    }, {
        "check": "p1b_law_discriminates",
        "requirement": "corrected FIX1, FIX2, and FIX3 all pass",
        "observed": f"fix1={fix1_pass}; fix2={fix2_pass}; fix3={fix3_pass}",
        "pass": overall,
        "source": SOURCE,
        "provenance": "p1b_full_table_v1_corrected_final_verdict",
    }]


def run(n_per_cell: int = DEFAULT_N_PER_CELL, output_dir: str | None = None) -> dict[str, Any]:
    global RESULTS_ROOT, OUTPUT_PATH
    if output_dir:
        RESULTS_ROOT = Path(output_dir).absolute()
        OUTPUT_PATH = RESULTS_ROOT / "p1b_full_table_v1.json"

    separator = _read_json(SEPARATOR_RESULTS_PATH)
    graded = _read_json(GRADED_PATH)
    pilot = _read_json(PILOT_PATH)
    v0 = _read_json(V0_PATH)
    if not all([separator, graded, pilot, v0]):
        result = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _now(),
            "status": "SKIP_MISSING_DEPENDENCIES",
            "message": f"separator={bool(separator)}; graded={bool(graded)}; pilot={bool(pilot)}; v0={bool(v0)}",
        }
        _write_json(OUTPUT_PATH, result)
        return result

    acceptance = graded.get("acceptance", {})
    if graded.get("status") != "RUNG1_SEPARATOR_P1B_GRADED_RECOMPUTE_STEP1A_PASS" or acceptance.get("step1_branch") != "1A":
        raise RuntimeError("entry gate failed: Step1 graded recompute is not branch 1A")

    allowed_b = _allowed_b_values(graded)
    operator = _operator_by_b(graded)
    call_caps = _call_cap_by_b(pilot)
    manifest = _select_manifest(separator, allowed_b, n_per_cell)
    node_cap = int(separator.get("generation_config", {}).get("node_cap", DEFAULT_NODE_CAP))

    instance_rows = _run_resource_sweep(manifest, operator, call_caps, RESOURCE_D_SWEEP, node_cap)
    capacity = _capacity_leg(instance_rows)
    footprint = _separator_footprint_rows(capacity)
    dstar = _observed_dstar_rows(capacity)
    refined = _prediction_rows(dstar, footprint)
    d_sweep = _d_sweep_scaling_rows(refined)
    rho_sweep = _rho_sweep_placeholder()
    verdict = _verdict_rows(refined, d_sweep)
    verdict_by_check = {row["check"]: row for row in verdict}
    overall_pass = bool(verdict_by_check["p1b_law_discriminates"]["pass"])

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": STATUS_PASS if overall_pass else STATUS_FAIL,
        "generation_config": {
            "model_id": "Qwen/Qwen3.5-4B",
            "source_p1b_graded_recompute_path": _rel(GRADED_PATH),
            "source_p1b_truncation_pilot_path": _rel(PILOT_PATH),
            "source_p1b_full_table_v0_path": _rel(V0_PATH),
            "source_separator_path": _rel(SEPARATOR_RESULTS_PATH),
            "allowed_b_bins": allowed_b,
            "n_per_cell": n_per_cell,
            "resource_D_sweep": list(RESOURCE_D_SWEEP),
            "baseline_resource_D_for_fix1_direction": BASELINE_RESOURCE_D,
            "node_cap": node_cap,
            "no_new_qwen_calls_for_fix1_fix2": True,
            "fix3_requires_bounded_pilots": True,
            "corrected_axis_contract": "D is register capacity resource; d_global is problem depth; one d*(D,b) threshold per resource-D,b cell",
            "discarded_invalid_v1_refined_law_reason": "previous v1 used d_global as D_eff and produced a per-d_global prediction ramp",
            "source": SOURCE,
            "provenance": "p1b_full_table_v1_corrected_config",
        },
        "acceptance": {
            "p1b_law_discriminates": overall_pass,
            "fix1_separator_aware_law_tracks": bool(verdict_by_check["fix1_separator_aware_law_tracks"]["pass"]),
            "fix2_d_sweep_slope_ci_excludes_zero": bool(verdict_by_check["fix2_resource_D_sweep_slope_ci_excludes_zero"]["pass"]),
            "fix2_resource_D_sweep_slope_ci_excludes_zero": bool(verdict_by_check["fix2_resource_D_sweep_slope_ci_excludes_zero"]["pass"]),
            "fix3_rho_sweep_paired_discrimination": False,
            "fix3_rho_sweep_not_yet_implemented": True,
            "invalid_previous_v1_passes_discarded": True,
        },
        "separator_footprint_by_b": {row["b_bin"]: row["footprint_b"] for row in footprint},
        "separator_footprint_measurement": footprint,
        "separator_boundary_edges_by_b_diagnostic": _median_by_b(separator, "n_boundary_edges"),
        "separator_d_boundary_by_b_diagnostic_not_used_as_footprint": _median_by_b(separator, "d_boundary"),
        "instance_arm_metrics": instance_rows,
        "capacity_leg": capacity,
        "observed_dstar_by_resource_D_b": dstar,
        "refined_law_dstar_vs_Deff": refined,
        "d_sweep_scaling": d_sweep,
        "rho_sweep_paired_discrimination": rho_sweep,
        "verdict_refined_law_discriminates": verdict,
        "comparison_to_v0": {
            "v0_status": v0.get("status"),
            "v0_law_tracked_but_not_discriminating": bool(v0.get("acceptance", {}).get("p1b_law_tracks_inflated_keff")),
            "corrected_v1_changes": [
                "uses resource register_capacity_D sweep instead of d_global ramp",
                "measures one observed d*(D,b) threshold per resource-D,b cell",
                "marks left-censored b bins as insufficient rather than passing",
                "keeps FIX3 rho sweep pending",
            ],
        },
    }
    _write_json(OUTPUT_PATH, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Corrected P1b capacity-law addendum with register-capacity D sweep.")
    parser.add_argument("--output-dir", default=str(RESULTS_ROOT))
    parser.add_argument("--n-per-cell", type=int, default=DEFAULT_N_PER_CELL)
    args = parser.parse_args()
    run(n_per_cell=args.n_per_cell, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
