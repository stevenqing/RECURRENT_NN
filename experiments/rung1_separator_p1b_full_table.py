"""P1b full-table controlled capacity-law run under graded operator fallibility."""

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
from experiments.rung1_separator_scaling import DEFAULT_COMM_BUDGET_C, DEFAULT_NODE_CAP, DEFAULT_REGISTER_CAPACITY_D, LOW_SOLVE_THRESHOLD, COLLAPSE_TOLERANCE, _instance_from_row, _solve_monolith
from experiments.rung1_separator_llm_po_forward_gate import SEPARATOR_RESULTS_PATH


RESULTS_ROOT = REPO_ROOT / "results/rung1_separator_fallibility_rungs"
GRADED_PATH = RESULTS_ROOT / "p1b_graded_recompute.json"
PILOT_PATH = RESULTS_ROOT / "p1b_truncation_pilot.json"
OUTPUT_PATH = RESULTS_ROOT / "p1b_full_table.json"
SCHEMA_VERSION = "rung1_separator_p1b_full_table_controlled_v0"
STATUS_PASS = "RUNG1_SEPARATOR_P1B_FULL_TABLE_INFLATED_KEFF_TRACK_PASS"
STATUS_KILL = "RUNG1_SEPARATOR_P1B_FULL_TABLE_KILL_LAW_NOT_TRACK_INFLATION"
COMM_BUDGET_SWEEP = [64, 128, 192, 256, 384, 512, 768, 1024]
DEFAULT_N_PER_CELL = 24


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _cell_name(d_global: int, b_value: int) -> str:
    return f"d{d_global}_b{b_value}"


def _allowed_b_values(graded: dict[str, Any]) -> list[int]:
    out = []
    for cell in graded.get("acceptance", {}).get("p1b_step3_allowed_cells", []):
        try:
            out.append(int(str(cell).split("_b", 1)[1]))
        except Exception:
            continue
    return sorted(set(out))


def _call_cap_by_b(pilot: dict[str, Any]) -> dict[int, int]:
    out = {}
    for row in pilot.get("call_cap_recommendation", []):
        out[int(row["b_bin"])] = int(row["recommended_call_cap"])
    return out


def _operator_by_b(graded: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out = {}
    for row in graded.get("graded_functional_gate_by_cell", []):
        out[int(row["b_bin"])] = row
    return out


def _select_manifest(separator: dict[str, Any], allowed_b: list[int], n_per_cell: int) -> list[dict[str, Any]]:
    by_cell: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in separator.get("instance_manifest", []):
        b_value = int(row["b"])
        if b_value in allowed_b:
            by_cell[(int(row["d_global_reference"]), b_value)].append(row)
    selected = []
    for key in sorted(by_cell):
        rows = sorted(by_cell[key], key=lambda row: (int(row["seed"]), int(row["source_index"]), str(row["instance_id"])))
        selected.extend(rows[:n_per_cell])
    return selected


def _group(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    out: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[tuple(row[key] for key in keys)].append(row)
    return out


def _instance_rows(manifest: list[dict[str, Any]], operator_by_b: dict[int, dict[str, Any]], call_cap_by_b: dict[int, int], register_capacity_d: int, node_cap: int) -> list[dict[str, Any]]:
    rows = []
    for row in manifest:
        b_value = int(row["b"])
        d_global = int(row["d_global_reference"])
        operator = operator_by_b[b_value]
        k_eff = float(operator["graded_keff_inflated"])
        clean = float(operator["k_eff_clean"])
        result = _solve_monolith(_instance_from_row(row), node_cap, register_capacity_d, k_eff)
        rows.append({
            "instance_id": row["instance_id"],
            "cell": _cell_name(d_global, b_value),
            "cell_id": row["cell_id"],
            "sweep": row["sweep"],
            "d_global_reference": d_global,
            "b": b_value,
            "rung": "P1b_llm_propagation_guarded",
            "arm": "monolith_cbj_p1b_guarded_inflated_keff_control",
            "solved": bool(result["solved"]),
            "status": result["status"],
            "steps_to_solve_or_cap": int(result["steps"]),
            "comm_tokens": int(result["comm_tokens"]),
            "total_retractions": int(result["total_retractions"]),
            "peak_register_entries": int(result["peak_register_entries"]),
            "overflowed": bool(result["overflowed"]),
            "register_capacity_D": register_capacity_d,
            "node_cap": node_cap,
            "call_cap": int(call_cap_by_b.get(b_value, 0)),
            "call_cap_rule": "ceil(source_p1b_v1_1_p90_calls_per_instance * 2)",
            "llm_calls_made_in_step3": 0,
            "no_new_qwen_calls": True,
            "k_eff_clean": clean,
            "k_eff_inflated": k_eff,
            "graded_keff_inflated": k_eff,
            "rho_graded": float(operator["rho_graded"]),
            "prune_precision": float(operator["prune_precision"]),
            "prune_recall": float(operator["prune_recall"]),
            "operator_calibration_cell": operator["cell"],
            "controlled_substrate_note": "same symbolic separator instances with P1b v1.1 graded operator fallibility injected through K_eff inflation",
            "source": SOURCE,
            "provenance": "qwen35_p1b_full_table_controlled_instance_v0",
        })
    return rows


def _capacity_leg(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (d_global, b_value), subset in sorted(_group(rows, "d_global_reference", "b").items()):
        solved_comm = sorted(float(row["comm_tokens"]) for row in subset if row["solved"])
        budget_rates = {str(budget): mean(float(row["solved"] and float(row["comm_tokens"]) <= budget) for row in subset) for budget in COMM_BUDGET_SWEEP}
        out.append({
            "rung": "P1b_llm_propagation_guarded",
            "d_global_bin": str(d_global),
            "b_bin": str(b_value),
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "overflow_rate": mean(float(row["overflowed"]) for row in subset),
            "mean_peak_register_entries": mean(float(row["peak_register_entries"]) for row in subset),
            "k_eff_inflated": mean(float(row["k_eff_inflated"]) for row in subset),
            "D_over_ln_K_eff_inflated": float(subset[0]["register_capacity_D"]) / math.log(max(mean(float(row["k_eff_inflated"]) for row in subset), 1.0001)),
            "budget_solve_rates": budget_rates,
            "budget_at_95_solve": next((budget for budget in COMM_BUDGET_SWEEP if budget_rates[str(budget)] >= 0.95), None),
            "posterior_p95_comm_to_solve": solved_comm[min(len(solved_comm) - 1, math.ceil(0.95 * len(solved_comm)) - 1)] if solved_comm else None,
            "source": SOURCE,
            "provenance": "qwen35_p1b_full_table_capacity_leg_v0",
        })
    return out


def _keff_inflation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (d_global, b_value), subset in sorted(_group(rows, "d_global_reference", "b").items()):
        out.append({
            "rung": "P1b_llm_propagation_guarded",
            "d_global_bin": str(d_global),
            "b_bin": str(b_value),
            "n": len(subset),
            "K_eff_clean": mean(float(row["k_eff_clean"]) for row in subset),
            "K_eff_inflated": mean(float(row["k_eff_inflated"]) for row in subset),
            "rho": mean(float(row["rho_graded"]) for row in subset),
            "rho_graded": mean(float(row["rho_graded"]) for row in subset),
            "source": SOURCE,
            "provenance": "qwen35_p1b_full_table_keff_inflation_v0",
        })
    return out


def _operator_error_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (d_global, b_value), subset in sorted(_group(rows, "d_global_reference", "b").items()):
        out.append({
            "rung": "P1b_llm_propagation_guarded",
            "d_global_bin": str(d_global),
            "b_bin": str(b_value),
            "n": len(subset),
            "prune_precision": mean(float(row["prune_precision"]) for row in subset),
            "prune_recall": mean(float(row["prune_recall"]) for row in subset),
            "correct_propagation_rate": None,
            "exact_match_correct_propagation_rate_retired_to_diagnostic": True,
            "missed_propagation": "calibrated_from_step1_graded_recompute",
            "unsound_propagation_rejected": "calibrated_from_step1_graded_recompute",
            "generation_truncated_no_answer": 0,
            "generation_parsable_invalid": 0,
            "generation_valid": len(subset),
            "llm_calls_made_in_step3": 0,
            "source": SOURCE,
            "provenance": "qwen35_p1b_full_table_operator_error_breakdown_v0",
        })
    return out


def _dstar_rows(capacity: list[dict[str, Any]], register_capacity_d: int) -> list[dict[str, Any]]:
    out = []
    by_b = _group(capacity, "b_bin")
    for (b_bin,), subset in sorted(by_b.items(), key=lambda item: int(item[0][0])):
        ordered = sorted(subset, key=lambda row: int(row["d_global_bin"]))
        collapse = next((row for row in ordered if float(row["solve_rate"]) <= LOW_SOLVE_THRESHOLD), None)
        k_eff = mean(float(row["k_eff_inflated"]) for row in ordered)
        predicted = register_capacity_d / math.log(max(k_eff, 1.0001))
        observed = int(collapse["d_global_bin"]) if collapse else None
        residual = None if observed is None else observed - predicted
        track_pass = observed is not None and abs(float(residual)) <= COLLAPSE_TOLERANCE
        out.append({
            "rung": "P1b_llm_propagation_guarded",
            "b_bin": b_bin,
            "d_star_observed": observed,
            "D_over_ln_K_eff_inflated": predicted,
            "residual": residual,
            "track_pass": track_pass,
            "collapse_threshold_solve_rate": LOW_SOLVE_THRESHOLD,
            "tolerance": COLLAPSE_TOLERANCE,
            "K_eff_inflated": k_eff,
            "register_capacity_D": register_capacity_d,
            "supporting_depths": [int(row["d_global_bin"]) for row in ordered],
            "supporting_solve_rates": {row["d_global_bin"]: row["solve_rate"] for row in ordered},
            "source": SOURCE,
            "provenance": "qwen35_p1b_full_table_dstar_vs_inflated_keff_v0",
        })
    return out


def _budget_at_95(capacity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in capacity:
        out.append({
            "rung": row["rung"],
            "d_global_bin": row["d_global_bin"],
            "b_bin": row["b_bin"],
            "budget_at_95_solve": row["budget_at_95_solve"],
            "max_budget": max(COMM_BUDGET_SWEEP),
            "max_budget_solve_rate": row["budget_solve_rates"][str(max(COMM_BUDGET_SWEEP))],
            "posterior_p95_comm_to_solve": row["posterior_p95_comm_to_solve"],
            "budget_solve_rates": row["budget_solve_rates"],
            "comm_budget_sweep_mode": "offline_posthoc_no_extra_qwen_calls",
            "source": SOURCE,
            "provenance": "qwen35_p1b_full_table_budget95_offline_v0",
        })
    return out


def _verdict(dstar_rows: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    law_tracks = bool(dstar_rows) and all(bool(row["track_pass"]) for row in dstar_rows)
    no_new_qwen = all(bool(row["no_new_qwen_calls"]) and int(row["llm_calls_made_in_step3"]) == 0 for row in rows)
    return [
        {"check": "p1b_entry_gates", "predicted": "Step1A graded recompute allows P1b full table on passing b bins", "observed": f"n_rows={len(rows)}; b_bins={sorted({row['b'] for row in rows})}", "pass": bool(rows), "source": SOURCE, "provenance": "qwen35_p1b_full_table_verdict_v0"},
        {"check": "p1b_law_tracks_inflated_keff", "predicted": f"each b-bin d*_observed within {COLLAPSE_TOLERANCE} of D/ln K_eff_inflated", "observed": str(dstar_rows), "pass": law_tracks, "source": SOURCE, "provenance": "qwen35_p1b_full_table_verdict_v0"},
        {"check": "kill_law_not_track_inflation", "predicted": "must be false before P1c launch", "observed": "not triggered" if law_tracks else "triggered", "pass": law_tracks, "source": SOURCE, "provenance": "qwen35_p1b_full_table_kill_v0"},
        {"check": "no_new_qwen_calls_in_step3_controlled_recompute", "predicted": "Step3 controlled table reuses Step1 graded operator calibration and makes zero new Qwen calls", "observed": f"no_new_qwen={no_new_qwen}", "pass": no_new_qwen, "source": SOURCE, "provenance": "qwen35_p1b_full_table_honesty_v0"},
    ]


def run(n_per_cell: int = DEFAULT_N_PER_CELL, output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    graded = _read_json(GRADED_PATH)
    pilot = _read_json(PILOT_PATH)
    separator = _read_json(SEPARATOR_RESULTS_PATH)
    acceptance = graded.get("acceptance", {})
    if graded.get("status") != "RUNG1_SEPARATOR_P1B_GRADED_RECOMPUTE_STEP1A_PASS" or acceptance.get("step1_branch") != "1A":
        raise RuntimeError("entry gate failed: Step1 graded recompute is not branch 1A")
    if not acceptance.get("p1b_step3_allowed_cells"):
        raise RuntimeError("entry gate failed: no P1b Step3 allowed cells")
    allowed_b = _allowed_b_values(graded)
    operator = _operator_by_b(graded)
    call_caps = _call_cap_by_b(pilot)
    manifest = _select_manifest(separator, allowed_b, n_per_cell)
    register_capacity_d = int(separator.get("generation_config", {}).get("register_capacity_D", DEFAULT_REGISTER_CAPACITY_D))
    node_cap = int(separator.get("generation_config", {}).get("node_cap", DEFAULT_NODE_CAP))
    rows = _instance_rows(manifest, operator, call_caps, register_capacity_d, node_cap)
    capacity = _capacity_leg(rows)
    dstar = _dstar_rows(capacity, register_capacity_d)
    verdict = _verdict(dstar, rows)
    law_tracks = bool({row["check"]: row for row in verdict}["p1b_law_tracks_inflated_keff"]["pass"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": STATUS_PASS if law_tracks else STATUS_KILL,
        "generation_config": {
            "source_p1b_graded_recompute_path": _rel(GRADED_PATH),
            "source_p1b_truncation_pilot_path": _rel(PILOT_PATH),
            "source_separator_path": _rel(SEPARATOR_RESULTS_PATH),
            "allowed_step3_cells": acceptance.get("p1b_step3_allowed_cells", []),
            "allowed_b_bins": allowed_b,
            "n_per_cell": n_per_cell,
            "register_capacity_D": register_capacity_d,
            "comm_budget_C_shared_channel": int(separator.get("generation_config", {}).get("comm_budget_C_shared_channel", DEFAULT_COMM_BUDGET_C)),
            "node_cap": node_cap,
            "call_cap_by_b": call_caps,
            "call_cap_rule": "ceil(source_p1b_v1_1_p90_calls_per_instance * 2)",
            "comm_budget_sweep": COMM_BUDGET_SWEEP,
            "comm_budget_sweep_mode": "offline_posthoc_no_extra_qwen_calls",
            "controlled_substrate": "symbolic separator v0.2.3 full table over b bins admitted by Step1A; P1b fallibility enters only through graded K_eff inflation",
            "no_new_qwen_calls": True,
            "source": SOURCE,
            "provenance": "qwen35_p1b_full_table_config_v0",
        },
        "acceptance": {
            "p1b_full_table_complete": bool(rows),
            "p1b_law_tracks_inflated_keff": law_tracks,
            "kill_law_not_track_inflation": not law_tracks,
            "p1c_entry_allowed_by_p1b": law_tracks,
        },
        "operator_error_breakdown": _operator_error_breakdown(rows),
        "keff_inflation": _keff_inflation(rows),
        "capacity_leg": capacity,
        "budget_at_95_solve": _budget_at_95(capacity),
        "dstar_vs_inflated_keff": dstar,
        "instance_arm_metrics": rows,
        "verdict": verdict,
    }
    _write_json(output_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-per-cell", type=int, default=DEFAULT_N_PER_CELL)
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()
    output = Path(args.output) if Path(args.output).is_absolute() else REPO_ROOT / args.output
    run(args.n_per_cell, output)


if __name__ == "__main__":
    main()
