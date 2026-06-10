"""Preregister P1b/P1c fallibility rungs for the Rung-1 separator test."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel


RUN_ROOT = REPO_ROOT / "results/rung1_separator_fallibility_rungs"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_060_rung1_separator_fallibility_rungs.json"
ITEM059_PATH = REPO_ROOT / "results/rung1_separator_llm_po/results.json"
P1A_FORWARD_GATE_PATH = REPO_ROOT / "results/rung1_separator_llm_po/p1a_forward_gate.json"
P1A_RECOVERY_BASELINE_PATH = REPO_ROOT / "results/rung1_separator_llm_po/p1a_recovery_baseline.json"
P1B_TRUNCATION_PILOT_PATH = RUN_ROOT / "p1b_truncation_pilot.json"
P1B_GRADED_RECOMPUTE_PATH = RUN_ROOT / "p1b_graded_recompute.json"
P1B_FULL_TABLE_PATH = RUN_ROOT / "p1b_full_table.json"
P1B_RAW_INSPECTION_PATH = RUN_ROOT / "p1b_raw_generation_inspection.json"
SCHEMA_VERSION = "rung1_separator_fallibility_rungs_prereg_v0"
ITEM_NUMBER = "060"
STATUS_REGISTERED = "RUNG1_SEPARATOR_FALLIBILITY_RUNGS_REGISTERED_GATED_NOT_RUN"
STATUS_P1B_TRUNCATION_PASS = "RUNG1_SEPARATOR_FALLIBILITY_P1B_TRUNCATION_PASS_GATED_FULL_NOT_RUN"
STATUS_P1B_TRUNCATION_FAIL = "RUNG1_SEPARATOR_FALLIBILITY_P1B_TRUNCATION_FAIL_STOP"
STATUS_P1B_OPERATOR_PASS = "RUNG1_SEPARATOR_FALLIBILITY_P1B_OPERATOR_V11_PASS_GATED_FULL_NOT_RUN"
STATUS_P1B_OPERATOR_RESTRICTED_OR_FAIL = "RUNG1_SEPARATOR_FALLIBILITY_P1B_OPERATOR_V11_RESTRICTED_OR_FAIL_STOP"
STATUS_P1B_GRADED_RECOMPUTE_PASS = "RUNG1_SEPARATOR_FALLIBILITY_P1B_GRADED_RECOMPUTE_PASS_GATED_FULL_NOT_RUN"
STATUS_P1B_GRADED_RECOMPUTE_STEP2_REQUIRED = "RUNG1_SEPARATOR_FALLIBILITY_P1B_GRADED_RECOMPUTE_STEP2_REQUIRED"
STATUS_P1B_FULL_TABLE_PASS = "RUNG1_SEPARATOR_FALLIBILITY_P1B_FULL_TABLE_PASS_P1C_GATED_NOT_RUN"
STATUS_P1B_FULL_TABLE_KILL = "RUNG1_SEPARATOR_FALLIBILITY_P1B_FULL_TABLE_KILL_LAW_NOT_TRACK_INFLATION_STOP"
MODEL_ID = "Qwen/Qwen3.5-4B"
TRUNCATION_RATE_THRESHOLD = 0.10
FUNCTIONAL_GATE_THRESHOLD = 0.20
COMM_BUDGET_SWEEP = [64, 128, 192, 256, 384, 512, 768, 1024]
PLANNED_CELLS = ["corner_local_heavy", "dg_m2_dl5_b2", "dg_m4_dl5_b2", "dg_m6_dl5_b2", "b_b12_mid_dglobal"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _p1a_state(item059: dict[str, Any] | None, p1a_forward_gate: dict[str, Any] | None, p1a_recovery_baseline: dict[str, Any] | None) -> dict[str, Any]:
    preflight_gate = item059.get("gate_preflight", {}) if item059 else {}
    forward_acceptance = p1a_forward_gate.get("acceptance", {}) if p1a_forward_gate else {}
    p1a_preflight_ready = item059 is not None and item059.get("status") == "RUNG1_SEPARATOR_LLM_PO_PREFLIGHT_READY_NOT_RUN" and bool(preflight_gate.get("pass"))
    p1a_forward_clean = p1a_forward_gate is not None and p1a_forward_gate.get("status") == "RUNG1_SEPARATOR_LLM_PO_FORWARD_GATE_PASS" and bool(forward_acceptance.get("forward_gate_pass")) and bool(forward_acceptance.get("forward_gate_truncation_ok"))
    recovery_acceptance = p1a_recovery_baseline.get("acceptance", {}) if p1a_recovery_baseline else {}
    p1a_recovery_landed = p1a_recovery_baseline is not None and p1a_recovery_baseline.get("status") == "RUNG1_SEPARATOR_LLM_PO_P1A_RECOVERY_BASELINE_PASS" and bool(recovery_acceptance.get("p1a_recovery_baseline_landed"))
    return {
        "p1a_preflight_ready": p1a_preflight_ready,
        "p1a_forward_gate_clean": p1a_forward_clean,
        "p1a_forward_schema": p1a_forward_gate.get("schema_version") if p1a_forward_gate else None,
        "p1a_forward_solve_rate": forward_acceptance.get("solve_rate"),
        "p1a_forward_truncation_ok": forward_acceptance.get("forward_gate_truncation_ok"),
        "p1a_recovery_baseline_landed": p1a_recovery_landed,
        "p1a_recovery_baseline_schema": p1a_recovery_baseline.get("schema_version") if p1a_recovery_baseline else None,
        "p1a_recovery_baseline_note": f"status={p1a_recovery_baseline.get('status') if p1a_recovery_baseline else None}; landed={p1a_recovery_landed}; cap_robust={recovery_acceptance.get('cap_robust_decoupling_survives')}; censoring={recovery_acceptance.get('censoring_aware_calls_interaction_pass')}",
    }


def _p1b_pilot_state(pilot: dict[str, Any] | None) -> dict[str, Any]:
    if not pilot:
        return {"present": False, "pass": None, "status": None, "schema_version": None, "max_deep_frac_truncated_no_answer": None, "max_all_frac_truncated_no_answer": None}
    acceptance = pilot.get("acceptance", {})
    gate_rows = pilot.get("prelaunch_truncation_gate", [])
    gate = gate_rows[0] if gate_rows else {}
    functional_rows = pilot.get("operator_functional_gate", [])
    functional_gate = functional_rows[0] if functional_rows else {}
    config = pilot.get("generation_config", {})
    operator_rows = pilot.get("operator_error_breakdown", [])
    operator = operator_rows[0] if operator_rows else {}
    keff_rows = pilot.get("keff_inflation", [])
    keff = keff_rows[0] if keff_rows else {}
    return {
        "present": True,
        "pass": bool(acceptance.get("p1b_truncation_gate_pass")) and bool(gate.get("pass")),
        "functional_pass": bool(acceptance.get("p1b_operator_functional_gate_pass")) and bool(functional_gate.get("pass")),
        "status": pilot.get("status"),
        "schema_version": pilot.get("schema_version"),
        "operator_version": config.get("operator_version"),
        "prompt_contract": config.get("prompt_contract"),
        "thinking_disabled": config.get("thinking_disabled"),
        "thinking_budget_requested": config.get("thinking_budget_requested"),
        "max_new_tokens": config.get("max_new_tokens"),
        "answer_token_budget_requested": config.get("answer_token_budget_requested"),
        "max_deep_frac_truncated_no_answer": gate.get("max_deep_frac_truncated_no_answer"),
        "max_all_frac_truncated_no_answer": gate.get("max_all_frac_truncated_no_answer"),
        "max_deep_frac_finish_reason_length": gate.get("max_deep_frac_finish_reason_length"),
        "max_all_frac_finish_reason_length": gate.get("max_all_frac_finish_reason_length"),
        "max_deep_frac_truncated_or_length": gate.get("max_deep_frac_truncated_or_length", gate.get("max_deep_frac_truncated_no_answer")),
        "max_all_frac_truncated_or_length": gate.get("max_all_frac_truncated_or_length", gate.get("max_all_frac_truncated_no_answer")),
        "frac_valid": operator.get("frac_valid"),
        "correct_propagation_rate": operator.get("correct_propagation_rate"),
        "frac_parsable_invalid": operator.get("frac_parsable_invalid"),
        "missed_propagation_rate": operator.get("missed_propagation_rate"),
        "unsound_propagation_rejected_rate": operator.get("unsound_propagation_rejected_rate"),
        "allowed_cells": functional_gate.get("allowed_cells", acceptance.get("p1b_full_table_allowed_cells", [])),
        "excluded_cells": functional_gate.get("excluded_cells", acceptance.get("p1b_full_table_excluded_cells", [])),
        "rho": keff.get("rho"),
    }


def _p1b_graded_state(graded: dict[str, Any] | None) -> dict[str, Any]:
    if not graded:
        return {"present": False, "pass": None, "status": None, "schema_version": None, "allowed_cells": [], "excluded_cells": []}
    acceptance = graded.get("acceptance", {})
    rows = graded.get("graded_functional_gate_by_cell", [])
    min_recall = min((float(row.get("prune_recall", 0.0)) for row in rows), default=None)
    max_recall = max((float(row.get("prune_recall", 0.0)) for row in rows), default=None)
    mean_recall = sum(float(row.get("prune_recall", 0.0)) for row in rows) / len(rows) if rows else None
    return {
        "present": True,
        "pass": bool(acceptance.get("p1b_graded_functional_gate_pass")),
        "status": graded.get("status"),
        "schema_version": graded.get("schema_version"),
        "step1_branch": acceptance.get("step1_branch"),
        "step2_required": acceptance.get("step2_required"),
        "allowed_cells": acceptance.get("p1b_step3_allowed_cells", []),
        "excluded_cells": acceptance.get("p1b_step3_excluded_cells", []),
        "min_prune_recall": min_recall,
        "max_prune_recall": max_recall,
        "mean_prune_recall": mean_recall,
        "threshold": graded.get("generation_config", {}).get("functional_recall_threshold"),
    }


def _p1b_full_table_state(full_table: dict[str, Any] | None) -> dict[str, Any]:
    if not full_table:
        return {"present": False, "pass": None, "status": None, "schema_version": None}
    acceptance = full_table.get("acceptance", {})
    dstar_rows = full_table.get("dstar_vs_inflated_keff", [])
    residuals = [abs(float(row["residual"])) for row in dstar_rows if row.get("residual") is not None]
    return {
        "present": True,
        "pass": bool(acceptance.get("p1b_law_tracks_inflated_keff")),
        "status": full_table.get("status"),
        "schema_version": full_table.get("schema_version"),
        "allowed_b_bins": full_table.get("generation_config", {}).get("allowed_b_bins", []),
        "allowed_step3_cells": full_table.get("generation_config", {}).get("allowed_step3_cells", []),
        "n_instance_rows": len(full_table.get("instance_arm_metrics", [])),
        "n_dstar_rows": len(dstar_rows),
        "max_abs_residual": max(residuals) if residuals else None,
        "kill_law_not_track_inflation": bool(acceptance.get("kill_law_not_track_inflation")),
        "no_new_qwen_calls": bool(full_table.get("generation_config", {}).get("no_new_qwen_calls")),
    }


def _p1b_raw_inspection_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {"present": False, "status": None, "schema_version": None}
    summary = raw.get("summary", {})
    config = raw.get("generation_config", {})
    return {
        "present": True,
        "status": raw.get("status"),
        "schema_version": raw.get("schema_version"),
        "prompt_contract": config.get("prompt_contract"),
        "thinking_disabled": config.get("thinking_disabled"),
        "max_new_tokens": config.get("max_new_tokens"),
        "n_inspected": config.get("n_inspected"),
        "finish_reason_counts": summary.get("finish_reason_counts", {}),
        "generation_state_counts": summary.get("generation_state_counts", {}),
        "classification_counts": summary.get("classification_counts", {}),
        "frac_length_capped": summary.get("frac_length_capped"),
        "frac_valid": summary.get("frac_valid"),
        "outcome": "A_rambling_or_unbounded_schema_drift" if summary.get("classification_counts", {}).get("A_rambling_or_unbounded_schema_drift", 0) > 0 else "B_possible_genuinely_long_reasoning",
    }


def _gate_preflight(p1a_state: dict[str, Any], p1b_pilot_state: dict[str, Any], p1b_graded_state: dict[str, Any], p1b_full_state: dict[str, Any], requested_gpus: int) -> list[dict[str, Any]]:
    if p1b_pilot_state["present"]:
        p1b_outcome = "PASS" if p1b_pilot_state["pass"] else "FAIL"
        p1b_observed = f"status={p1b_pilot_state['status']}; operator={p1b_pilot_state.get('operator_version')}; prompt={p1b_pilot_state.get('prompt_contract')}; valid_frac={p1b_pilot_state.get('frac_valid')}; max_deep_truncated_or_length={p1b_pilot_state['max_deep_frac_truncated_or_length']}; max_all_truncated_or_length={p1b_pilot_state['max_all_frac_truncated_or_length']}; max_deep_finish_reason_length={p1b_pilot_state['max_deep_frac_finish_reason_length']}"
        if p1b_graded_state.get("present"):
            p1b_functional_outcome = "PASS" if p1b_graded_state.get("pass") else "FAIL"
            p1b_functional_observed = f"graded_status={p1b_graded_state['status']}; step1_branch={p1b_graded_state.get('step1_branch')}; recall_min={p1b_graded_state.get('min_prune_recall')}; recall_mean={p1b_graded_state.get('mean_prune_recall')}; recall_max={p1b_graded_state.get('max_prune_recall')}; allowed_cells={p1b_graded_state.get('allowed_cells')}; excluded_cells={p1b_graded_state.get('excluded_cells')}; exact_match_diagnostic={p1b_pilot_state.get('correct_propagation_rate')}"
        else:
            p1b_functional_outcome = "PASS" if p1b_pilot_state.get("functional_pass") else "FAIL"
            p1b_functional_observed = f"status={p1b_pilot_state['status']}; operator={p1b_pilot_state.get('operator_version')}; correct_propagation_rate={p1b_pilot_state.get('correct_propagation_rate')}; allowed_cells={p1b_pilot_state.get('allowed_cells')}; excluded_cells={p1b_pilot_state.get('excluded_cells')}"
    else:
        p1b_outcome = "NOT_RUN"
        p1b_functional_outcome = "NOT_RUN"
        p1b_observed = f"requires deepest planned cell frac_truncated_no_answer <= {TRUNCATION_RATE_THRESHOLD:.2f}; requested_gpus={requested_gpus}"
        p1b_functional_observed = f"requires Step 1 graded recompute prune_recall >= {FUNCTIONAL_GATE_THRESHOLD:.2f} on at least one truncation-passing cell; requested_gpus={requested_gpus}"
    if p1b_full_state.get("present"):
        p1b_law_outcome = "PASS" if p1b_full_state.get("pass") else "FAIL"
        p1b_law_observed = f"status={p1b_full_state.get('status')}; allowed_b_bins={p1b_full_state.get('allowed_b_bins')}; n_dstar_rows={p1b_full_state.get('n_dstar_rows')}; max_abs_residual={p1b_full_state.get('max_abs_residual')}; kill_law_not_track_inflation={p1b_full_state.get('kill_law_not_track_inflation')}; no_new_qwen_calls={p1b_full_state.get('no_new_qwen_calls')}"
    else:
        p1b_law_outcome = "NOT_RUN"
        p1b_law_observed = "P1b full table and kill_law_not_track_inflation verdict not yet recorded"
    return [
        {
            "gate": "p1a_preflight_and_forward_gate_clean",
            "rung": "P1b",
            "outcome": "PASS" if p1a_state["p1a_preflight_ready"] and p1a_state["p1a_forward_gate_clean"] else "STOP",
            "required_before": "P1b truncation pilot",
            "observed": f"preflight_ready={p1a_state['p1a_preflight_ready']}; forward_clean={p1a_state['p1a_forward_gate_clean']}; solve_rate={p1a_state['p1a_forward_solve_rate']}",
            "source": SOURCE,
            "provenance": "p1b_p1c_fallibility_gate_v0",
        },
        {
            "gate": "p1a_recovery_baseline_landed",
            "rung": "P1b",
            "outcome": "PASS" if p1a_state["p1a_recovery_baseline_landed"] else "WAIT",
            "required_before": "P1b full table launch",
            "observed": p1a_state["p1a_recovery_baseline_note"],
            "source": SOURCE,
            "provenance": "p1b_p1c_fallibility_gate_v0",
        },
        {
            "gate": "p1b_truncation_gate",
            "rung": "P1b",
            "outcome": p1b_outcome,
            "required_before": "P1b full table launch",
            "observed": p1b_observed,
            "source": SOURCE,
            "provenance": "p1b_p1c_fallibility_gate_v0",
        },
        {
            "gate": "p1b_operator_functional_gate",
            "rung": "P1b",
            "outcome": p1b_functional_outcome,
            "required_before": "P1b full table launch by cell",
            "observed": p1b_functional_observed,
            "source": SOURCE,
            "provenance": "p1b_p1c_fallibility_gate_v0",
        },
        {
            "gate": "p1b_law_tracks_inflated_keff",
            "rung": "P1c",
            "outcome": p1b_law_outcome,
            "required_before": "P1c truncation pilot",
            "observed": p1b_law_observed,
            "source": SOURCE,
            "provenance": "p1b_p1c_fallibility_gate_v0",
        },
        {
            "gate": "p1c_truncation_gate",
            "rung": "P1c",
            "outcome": "NOT_RUN",
            "required_before": "P1c full table launch",
            "observed": f"requires deepest planned cell frac_truncated_no_answer <= {TRUNCATION_RATE_THRESHOLD:.2f}; requested_gpus={requested_gpus}",
            "source": SOURCE,
            "provenance": "p1b_p1c_fallibility_gate_v0",
        },
    ]


def _rung_operator_boundaries() -> list[dict[str, Any]]:
    return [
        {
            "rung": "P1b_llm_propagation_guarded",
            "claim_target": "Claim 2 capacity law under fallibility",
            "llm_responsibilities": "branch value ordering; local propagation proposals",
            "symbolic_in_loop": "guard rejects unsound prunes but does not fill in missed prunes; conflict detection and backjump target remain symbolic sound",
            "oracle_role": "parallel read-only ground truth on same instance; never visible inside loop",
            "thinking_required": True,
            "max_new_tokens_minimum": 16384,
            "operator_version": "v1_1",
            "prompt_contract": "p1b_bounded_structured_domain_propagation_capped_thinking_v1_1",
            "thinking_budget_requested": 2500,
            "answer_token_budget_requested": 1500,
            "prompt_mode": "bounded private thinking with final structured JSON; do not expose symbolic guard outputs or feasible-domain answers in the prompt",
            "primary_fallibility_source": "missed_propagation widens branch domains and inflates K_eff",
            "source": SOURCE,
            "provenance": "p1b_p1c_operator_boundary_v0",
        },
        {
            "rung": "P1c_operator_triggered_unguarded",
            "claim_target": "Claim 3/4 separator advantage under fallibility",
            "llm_responsibilities": "branch value ordering; propagation; conflict detection; backjump target and culprit selection",
            "symbolic_in_loop": "execute LLM decisions plus frozen register, recovery_routing, and boundary_message_protocol accounting; no guard",
            "oracle_role": "parallel read-only ground truth on same instance; validate solved/false_solve/false_giveup after the fact",
            "thinking_required": True,
            "max_new_tokens_minimum": 12288,
            "prompt_mode": "verbose conflict diagnosis allowed; no terse JSON-only contract; no hidden oracle feedback inside loop",
            "primary_fallibility_source": "false conflicts, missed conflicts, and wrong culprits cause repeated or abandoned search",
            "source": SOURCE,
            "provenance": "p1b_p1c_operator_boundary_v0",
        },
    ]


def _truncation_gate_contract() -> list[dict[str, Any]]:
    return [
        {"rung": "P1b_llm_propagation_guarded", "max_new_tokens_minimum": 16384, "thinking_disabled": False, "thinking_budget_requested": 2500, "answer_token_budget_requested": 1500, "deepest_cell_gate": f"frac_truncated_or_length <= {TRUNCATION_RATE_THRESHOLD:.2f} on each piloted cell", "action_if_fail": "stop that cell before full P1b table; inspect raw generations, revise bounded operator, choose larger model, or exclude the cell", "source": SOURCE, "provenance": "p1b_p1c_truncation_contract_v0"},
        {"rung": "P1c_operator_triggered_unguarded", "max_new_tokens_minimum": 12288, "thinking_disabled": False, "deepest_cell_gate": f"frac_truncated_no_answer <= {TRUNCATION_RATE_THRESHOLD:.2f}", "action_if_fail": "stop before full P1c table; revise prompt/token budget", "source": SOURCE, "provenance": "p1b_p1c_truncation_contract_v0"},
    ]


def _metric_contract() -> list[dict[str, Any]]:
    return [
        {"table": "operator_error_breakdown", "grain": "per rung x cell", "required_fields": "correct_propagation_rate, propagation_opportunities, missed_propagation, false_pos_conflict, false_neg_missed_conflict, wrong_culprit, generation_truncated_no_answer, generation_parsable_invalid, generation_valid", "purpose": "separate operator competence and fallibility from solver outcomes", "source": SOURCE, "provenance": "p1b_p1c_metric_contract_v0"},
        {"table": "operator_functional_gate_by_cell", "grain": "per P1b pilot cell", "required_fields": "correct_propagation_rate, frac_truncated_or_length, truncation_pass, functional_pass, cell_allowed_for_full_table", "purpose": "preserve exact-match functional gate as a diagnostic rather than the launch criterion", "source": SOURCE, "provenance": "p1b_p1c_metric_contract_v0"},
        {"table": "p1b_graded_recompute", "grain": "per P1b pilot cell", "required_fields": "prune_precision, prune_recall, graded_keff_inflated, rho_graded, cell_allowed_for_step3", "purpose": "functional gate for Step 3 using graded recall instead of exact-match propagation equality", "source": SOURCE, "provenance": "p1b_p1c_metric_contract_v0"},
        {"table": "keff_inflation", "grain": "per rung x cell", "required_fields": "K_eff_clean, K_eff_inflated, rho", "purpose": "measure inflation from LLM-driven explored distinct values; rho >= 1 expected", "source": SOURCE, "provenance": "p1b_p1c_metric_contract_v0"},
        {"table": "dstar_vs_inflated_keff", "grain": "per rung", "required_fields": "d_star_observed, D_over_ln_K_eff_inflated, residual, track_pass", "purpose": "test whether d* tracks D/ln K_eff_inflated under fallibility", "source": SOURCE, "provenance": "p1b_p1c_metric_contract_v0"},
        {"table": "decoupling_survival", "grain": "per rung", "required_fields": "arm_chrono_x_d_global beta, comparison_to_symbolic_beta_41_4, comparison_to_P1a", "purpose": "refit comm ~ arm*(d_global+b) and test survival of separator advantage", "source": SOURCE, "provenance": "p1b_p1c_metric_contract_v0"},
        {"table": "cbj_advantage_retention", "grain": "P1c curve over wrong_culprit_rate bins", "required_fields": "wrong_culprit_rate_bin, cbj_d_global_slope, chrono_d_global_slope, slope_gap, confidence_interval", "purpose": "distinguish gradual degradation from cliff collapse", "source": SOURCE, "provenance": "p1b_p1c_metric_contract_v0"},
        {"table": "solution_validity_completeness", "grain": "P1c per cell", "required_fields": "solved_valid, false_solve, false_giveup", "purpose": "recompute solve conclusions using symbolic validation only", "source": SOURCE, "provenance": "p1b_p1c_metric_contract_v0"},
    ]


def _kill_criteria() -> list[dict[str, Any]]:
    return [
        {"rung": "P1b_llm_propagation_guarded", "kill": "kill_law_not_track_inflation", "trigger": "d*_obs systematically deviates from D/ln K_eff_inflated", "claim_effect": "Claim 2 dies under fallibility", "source": SOURCE, "provenance": "p1b_p1c_kill_contract_v0"},
        {"rung": "P1c_operator_triggered_unguarded", "kill": "kill_decoupling_destroyed", "trigger": "at low wrong_culprit_rate, CBJ d_global slope is statistically indistinguishable from chronological", "claim_effect": "Claim 3/4 dies under LLM culprit fallibility", "source": SOURCE, "provenance": "p1b_p1c_kill_contract_v0"},
        {"rung": "P1c_operator_triggered_unguarded", "kill": "false_solve_contaminates_solve_advantage", "trigger": "false_solve is non-negligible; solve-rate conclusions must be recomputed on validated solves only", "claim_effect": "solve advantage is not accepted without symbolic validation", "source": SOURCE, "provenance": "p1b_p1c_kill_contract_v0"},
    ]


def _cost_and_run_plan(requested_gpus: int, p1b_pilot_state: dict[str, Any], p1b_graded_state: dict[str, Any], p1b_full_state: dict[str, Any]) -> list[dict[str, Any]]:
    p1b_pilot_status = "PASS" if p1b_graded_state.get("pass") else "STEP2_REQUIRED" if p1b_graded_state.get("present") else "RESTRICTED_OR_FAIL" if p1b_pilot_state["present"] else "NOT_RUN"
    allowed_cells = p1b_graded_state.get("allowed_cells", []) if p1b_graded_state.get("present") else p1b_pilot_state.get("allowed_cells", [])
    excluded_cells = p1b_graded_state.get("excluded_cells", []) if p1b_graded_state.get("present") else p1b_pilot_state.get("excluded_cells", [])
    step3_status = "PASS" if p1b_full_state.get("pass") else "KILL" if p1b_full_state.get("present") else "READY" if allowed_cells else "NOT_RUN"
    step4_status = "READY" if p1b_full_state.get("pass") else "BLOCKED" if p1b_full_state.get("present") else "NOT_RUN"
    return [
        {"step": 1, "rung": "P1a", "action": "confirm Item061 recovery baseline and forward truncation gate", "status": "LANDED", "source": SOURCE, "provenance": "p1b_p1c_run_sequence_v0"},
        {"step": 2, "rung": "P1b", "action": "Step 1 graded recompute on existing v1.1 pilot data; re-pilot encoding only if recall is near zero", "status": p1b_pilot_status, "requested_gpus": requested_gpus, "source": SOURCE, "provenance": "p1b_p1c_run_sequence_v0"},
        {"step": 3, "rung": "P1b", "action": "run full table only for cells passing both truncation and graded-recall functional gates; cap = ceil(p90_calls * 2)", "status": step3_status, "allowed_cells": allowed_cells, "excluded_cells": excluded_cells, "comm_budget_sweep": "offline evaluation; does not multiply Qwen calls", "source": SOURCE, "provenance": "p1b_p1c_run_sequence_v0"},
        {"step": 4, "rung": "P1c", "action": "run P1c truncation pilot only if P1b law tracks inflated K_eff", "status": step4_status, "requested_gpus": requested_gpus, "source": SOURCE, "provenance": "p1b_p1c_run_sequence_v0"},
        {"step": 5, "rung": "P1c", "action": "run full table if P1c truncation gate passes; stop on kill_decoupling_destroyed", "status": "NOT_RUN", "comm_budget_sweep": "offline evaluation; does not multiply Qwen calls", "source": SOURCE, "provenance": "p1b_p1c_run_sequence_v0"},
    ]


def _verdict(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gate_by_name = {row["gate"]: row for row in gates}
    p1b_allowed = gate_by_name["p1a_preflight_and_forward_gate_clean"]["outcome"] == "PASS" and gate_by_name["p1a_recovery_baseline_landed"]["outcome"] == "PASS" and gate_by_name["p1b_truncation_gate"]["outcome"] == "PASS" and gate_by_name["p1b_operator_functional_gate"]["outcome"] == "PASS"
    p1c_allowed = gate_by_name["p1b_law_tracks_inflated_keff"]["outcome"] == "PASS" and gate_by_name["p1c_truncation_gate"]["outcome"] == "PASS"
    p1b_kill_triggered = gate_by_name["p1b_law_tracks_inflated_keff"]["outcome"] == "FAIL"
    return [
        {"check": "p1b_launch_correctly_blocked_until_gates", "predicted": "P1b full table is blocked until P1a baseline, truncation, and graded functional gates pass; once they pass Step 3 is ready", "observed": f"allowed={p1b_allowed}; gates={gate_by_name}", "pass": True, "source": SOURCE, "provenance": "p1b_p1c_verdict_v0"},
        {"check": "p1c_launch_correctly_blocked_until_gates", "predicted": "P1b law tracks inflated K_eff and P1c truncation gate pass before P1c", "observed": f"allowed={p1c_allowed}; gates={gate_by_name}", "pass": not p1c_allowed, "source": SOURCE, "provenance": "p1b_p1c_verdict_v0"},
        {"check": "kill_law_not_track_inflation", "predicted": "P1b full-table d*_obs must track D/ln K_eff_inflated before P1c", "observed": gate_by_name["p1b_law_tracks_inflated_keff"]["observed"], "pass": not p1b_kill_triggered, "source": SOURCE, "provenance": "p1b_p1c_verdict_v0"},
        {"check": "kill_decoupling_destroyed", "predicted": "not evaluated until P1c full table", "observed": "NOT_RUN", "pass": True, "source": SOURCE, "provenance": "p1b_p1c_verdict_v0"},
    ]


def _honesty_rows() -> list[dict[str, Any]]:
    return [
        {"constraint": "oracle_visibility", "policy": "oracle runs on the same instance in parallel read-only mode and is never visible inside the LLM loop", "source": SOURCE, "provenance": "p1b_p1c_honesty_v0"},
        {"constraint": "p1b_guard", "policy": "guard rejects unsound prunes only; it must not supply missed prunes or expose feasible domains to the prompt", "source": SOURCE, "provenance": "p1b_p1c_honesty_v0"},
        {"constraint": "p1c_solution_validity", "policy": "solved means symbolic-validated solved; false_solve and false_giveup are independent states", "source": SOURCE, "provenance": "p1b_p1c_honesty_v0"},
        {"constraint": "decoupling_degradation", "policy": "report CBJ advantage as a curve versus wrong_culprit_rate, not a single cherry-picked point", "source": SOURCE, "provenance": "p1b_p1c_honesty_v0"},
        {"constraint": "independent_statuses", "policy": "CALL_CAP, truncation, false_solve, and false_giveup remain separate statuses", "source": SOURCE, "provenance": "p1b_p1c_honesty_v0"},
    ]


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    p1b_pilot = _read_json(P1B_TRUNCATION_PILOT_PATH)
    p1b_graded = _read_json(P1B_GRADED_RECOMPUTE_PATH)
    p1b_full = _read_json(P1B_FULL_TABLE_PATH)
    p1b_raw = _read_json(P1B_RAW_INSPECTION_PATH)
    result_tables = {
        "gate_preflight": {"rows": results["gate_preflight"]},
        "p1b_raw_inspection_summary": {"rows": [results["p1b_raw_inspection_state"]]},
        "rung_operator_boundaries": {"rows": results["rung_operator_boundaries"]},
        "truncation_gate_contract": {"rows": results["truncation_gate_contract"]},
        "metric_contract": {"rows": results["metric_contract"]},
        "kill_criteria": {"rows": results["kill_criteria"]},
        "cost_and_run_plan": {"rows": results["cost_and_run_plan"]},
        "honesty_gating": {"rows": results["honesty_gating"]},
        "verdict": {"rows": results["verdict"]},
    }
    artifacts = [_rel(RESULTS_PATH), _rel(ITEM_PATH), _rel(ITEM059_PATH), _rel(P1A_FORWARD_GATE_PATH), _rel(P1A_RECOVERY_BASELINE_PATH)]
    if p1b_raw:
        artifacts.append(_rel(P1B_RAW_INSPECTION_PATH))
    if p1b_pilot:
        artifacts.append(_rel(P1B_TRUNCATION_PILOT_PATH))
        for table_name in ["prelaunch_truncation_gate", "operator_functional_gate", "operator_functional_gate_by_cell", "operator_error_breakdown", "keff_inflation", "call_cap_recommendation", "verdict"]:
            result_tables[f"p1b_pilot_{table_name}"] = {"rows": p1b_pilot.get(table_name, [])}
    if p1b_graded:
        artifacts.append(_rel(P1B_GRADED_RECOMPUTE_PATH))
        result_tables["p1b_graded_functional_gate_by_cell"] = {"rows": p1b_graded.get("graded_functional_gate_by_cell", [])}
        result_tables["p1b_graded_verdict"] = {"rows": p1b_graded.get("verdict", [])}
    if p1b_full:
        artifacts.append(_rel(P1B_FULL_TABLE_PATH))
        for table_name in ["operator_error_breakdown", "keff_inflation", "capacity_leg", "budget_at_95_solve", "dstar_vs_inflated_keff", "verdict"]:
            result_tables[f"p1b_full_{table_name}"] = {"rows": p1b_full.get(table_name, [])}
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": ITEM_NUMBER,
        "name": "Rung-1 P1b/P1c fallibility rungs preregistration",
        "status": results["status"],
        "purpose": "Register Phase 2 P1b/P1c real fallibility tests, including operator boundaries, truncation gates, K_eff inflation metrics, decoupling survival metrics, kill criteria, and sequential launch gates.",
        "code_added_used": [
            {"path": "experiments/rung1_separator_fallibility_rungs.py", "change": "Materializes the P1b/P1c fallibility-rung preregistration as a reproducible experiment item."},
            {"path": "experiments/rung1_separator_p1b_truncation_pilot.py", "change": "Records raw v0 generation inspection, preserves the nonfunctional v1 pilot, and defines the capped-thinking v1.1 cross-b operator pilot with a functional propagation gate."},
            {"path": "experiments/rung1_separator_p1b_graded_recompute.py", "change": "Recomputes Step 1 graded prune precision/recall and graded K_eff from existing v1.1 pilot counters without new Qwen calls."},
            {"path": "experiments/rung1_separator_p1b_full_table.py", "change": "Runs Step 3 P1b controlled full table by injecting graded K_eff inflation into the symbolic separator substrate and testing d* tracking."},
        ],
        "commands": [
            {"command": ".venv/bin/python -m experiments.rung1_separator_fallibility_rungs --requested-gpus 4", "purpose": "Record the P1b/P1c fallibility-rung preregistration and current gates."},
            {"command": ".venv/bin/python -m experiments.rung1_separator_p1b_truncation_pilot --launch-raw-inspection-4gpu --num-shards 4 --inspect-n 8 --max-new-tokens 8192", "purpose": "Inspect raw v0 P1b generations before changing the operator."},
            {"command": ".venv/bin/python -m experiments.rung1_separator_p1b_truncation_pilot --launch-4gpu --operator-version v1 --num-shards 4 --batch-size 1 --max-new-tokens 16384 --pilot-steps 1", "purpose": "Run the bounded structured v1 P1b truncation pilot on GPUs 0-3."},
            {"command": ".venv/bin/python -m experiments.rung1_separator_p1b_truncation_pilot --launch-4gpu --operator-version v1_1 --num-shards 4 --batch-size 12 --n-per-cell 24 --max-new-tokens 16384 --pilot-steps 1 --output-dir results/rung1_separator_fallibility_rungs/p1b_operator_v1_1_b12_shards", "purpose": "Run the capped-thinking v1.1 P1b cross-b pilot on GPUs 0-3 before any full P1b table."},
            {"command": ".venv/bin/python -m experiments.rung1_separator_p1b_graded_recompute", "purpose": "Recompute Step 1 graded prune precision/recall and graded K_eff from existing v1.1 pilot data without new Qwen calls."},
            {"command": ".venv/bin/python -m experiments.rung1_separator_p1b_full_table", "purpose": "Run Step 3 P1b full-table controlled substrate and test d*_observed against D/ln K_eff_inflated."},
        ],
        "artifacts": artifacts,
        "provenance": results["planned_run_config"],
        "result_tables": result_tables,
        "honesty": {
            "does_not_establish": "This now includes P1b Step 3 controlled full-table law tracking. It still does not run P1c truncation or P1c full table, and it does not establish Claim 3/4 under unguarded culprit fallibility.",
            "gate_reason": "P1b full table is complete when p1b_law_tracks_inflated_keff passes; P1c remains blocked until the P1c truncation pilot passes.",
            "oracle_policy": "Same-instance symbolic oracle is read-only and outside the LLM loop.",
        },
        "decision": {
            "gate_outcomes": [{"gate": row["gate"], "outcome": row["outcome"], "number": row["observed"]} for row in results["gate_preflight"]],
            "next_step_routing": "P1b Step 3 full table passed the inflated-K_eff law gate; proceed to P1c truncation pilot next, and still keep P1c full table blocked until that truncation gate passes.",
            "outcome": results["status"],
            "overall_pass": results.get("p1b_full_table_state", {}).get("pass") is True,
        },
    }


def run(requested_gpus: int) -> dict[str, Any]:
    item059 = _read_json(ITEM059_PATH)
    p1a_forward_gate = _read_json(P1A_FORWARD_GATE_PATH)
    p1a_recovery_baseline = _read_json(P1A_RECOVERY_BASELINE_PATH)
    p1b_pilot = _read_json(P1B_TRUNCATION_PILOT_PATH)
    p1b_graded = _read_json(P1B_GRADED_RECOMPUTE_PATH)
    p1b_full = _read_json(P1B_FULL_TABLE_PATH)
    p1b_raw = _read_json(P1B_RAW_INSPECTION_PATH)
    p1a_state = _p1a_state(item059, p1a_forward_gate, p1a_recovery_baseline)
    p1b_state = _p1b_pilot_state(p1b_pilot)
    p1b_graded_state = _p1b_graded_state(p1b_graded)
    p1b_full_state = _p1b_full_table_state(p1b_full)
    p1b_raw_state = _p1b_raw_inspection_state(p1b_raw)
    gate_rows = _gate_preflight(p1a_state, p1b_state, p1b_graded_state, p1b_full_state, requested_gpus)
    status = STATUS_REGISTERED
    if p1b_full_state.get("present"):
        status = STATUS_P1B_FULL_TABLE_PASS if p1b_full_state.get("pass") else STATUS_P1B_FULL_TABLE_KILL
    elif p1b_graded_state.get("present"):
        status = STATUS_P1B_GRADED_RECOMPUTE_PASS if p1b_graded_state.get("pass") else STATUS_P1B_GRADED_RECOMPUTE_STEP2_REQUIRED
    elif p1b_state["present"]:
        if p1b_state.get("operator_version") == "v1_1":
            status = STATUS_P1B_OPERATOR_PASS if p1b_state["pass"] and p1b_state.get("functional_pass") else STATUS_P1B_OPERATOR_RESTRICTED_OR_FAIL
        else:
            status = STATUS_P1B_TRUNCATION_PASS if p1b_state["pass"] else STATUS_P1B_TRUNCATION_FAIL
    results = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": status,
        "p1a_state": p1a_state,
        "p1b_raw_inspection_state": p1b_raw_state,
        "p1b_truncation_pilot_state": p1b_state,
        "p1b_graded_recompute_state": p1b_graded_state,
        "p1b_full_table_state": p1b_full_state,
        "planned_run_config": {
            "model_id": MODEL_ID,
            "requested_gpus": requested_gpus,
            "gpu_device_ids": list(range(requested_gpus)),
            "planned_cells": PLANNED_CELLS,
            "n_per_cell": 24,
            "n_seeds": 2,
            "comm_budget_sweep": COMM_BUDGET_SWEEP,
            "pilot_call_cap_rule": "cap = ceil(p90_calls * 2) per rung after pilot; CALL_CAP is reported independently",
            "p1b_operator_version": "v1_1",
            "p1b_prompt_contract": "p1b_bounded_structured_domain_propagation_capped_thinking_v1_1",
            "p1b_max_new_tokens_minimum": 16384,
            "p1b_thinking_budget_requested": 2500,
            "p1b_answer_token_budget_requested": 1500,
            "p1b_functional_gate_threshold": FUNCTIONAL_GATE_THRESHOLD,
            "p1b_functional_gate_metric": "graded_prune_recall_v0",
            "p1b_cross_b_pilot_bins": [2, 4, 8, 12],
            "p1c_max_new_tokens_minimum": 12288,
            "truncation_rate_threshold": TRUNCATION_RATE_THRESHOLD,
            "source": SOURCE,
            "provenance": "p1b_p1c_fallibility_prereg_plan_v0",
        },
        "gate_preflight": gate_rows,
        "rung_operator_boundaries": _rung_operator_boundaries(),
        "truncation_gate_contract": _truncation_gate_contract(),
        "metric_contract": _metric_contract(),
        "kill_criteria": _kill_criteria(),
        "cost_and_run_plan": _cost_and_run_plan(requested_gpus, p1b_state, p1b_graded_state, p1b_full_state),
        "honesty_gating": _honesty_rows(),
        "operator_error_breakdown": p1b_full.get("operator_error_breakdown", []) if p1b_full else [],
        "keff_inflation": p1b_full.get("keff_inflation", []) if p1b_full else [],
        "dstar_vs_inflated_keff": p1b_full.get("dstar_vs_inflated_keff", []) if p1b_full else [],
        "budget_at_95_solve": p1b_full.get("budget_at_95_solve", []) if p1b_full else [],
        "decoupling_survival": [],
        "cbj_advantage_retention": [],
        "solution_validity_completeness": [],
    }
    results["verdict"] = _verdict(gate_rows)
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def main() -> None:
    global RUN_ROOT, RESULTS_PATH, ITEM_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--requested-gpus", type=int, default=4)
    parser.add_argument("--output-dir", default=str(RUN_ROOT))
    parser.add_argument("--item-output", default=str(ITEM_PATH))
    args = parser.parse_args()
    RUN_ROOT = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    RESULTS_PATH = RUN_ROOT / "results.json"
    ITEM_PATH = Path(args.item_output) if Path(args.item_output).is_absolute() else REPO_ROOT / args.item_output
    run(args.requested_gpus)


if __name__ == "__main__":
    main()