"""Gated preflight for the Rung-1 LLM-operator PO separator experiment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel

RUN_ROOT = REPO_ROOT / "results/rung1_separator_llm_po"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_059_rung1_separator_llm_po.json"
FORWARD_GATE_RESULTS_PATH = RUN_ROOT / "p1a_forward_gate.json"
SEPARATOR_GATE_PATH = REPO_ROOT / "results/rung1_separator_scaling/results.json"
QWEN35_DOWNLOAD_PATH = REPO_ROOT / "results/model_download/qwen3_5_4b/qwen_download.json"
SCHEMA_VERSION = "rung1_separator_llm_po_preflight_v0"
ITEM_NUMBER = "059"
STATUS_GATED_STOP = "RUNG1_SEPARATOR_LLM_PO_GATED_STOP"
STATUS_READY_NOT_RUN = "RUNG1_SEPARATOR_LLM_PO_PREFLIGHT_READY_NOT_RUN"
MODEL_ID = "Qwen/Qwen3.5-4B"
REQUIRED_SYMBOLIC_SCHEMA = "rung1_separator_scaling_symbolic_v0_2_3"
REQUIRED_FORWARD_GATE_SCHEMA = "rung1_separator_llm_po_forward_gate_v1"
P1A_MAX_NEW_TOKENS = 8192
P1A_PROMPT_CONTRACT = "p1a_json_only_branch_value_no_reasoning_v1"
FORWARD_GATE_TRUNCATION_THRESHOLD = 0.10
COMM_BUDGET_SWEEP = [64, 128, 192, 256, 384, 512, 768, 1024]
PLANNED_RUNGS = ["P1a_branch_only_sound", "P1b_llm_propagation_guarded", "P1c_operator_triggered_unguarded"]
PLANNED_CELLS = [
    "corner_local_heavy",
    "dg_m2_dl5_b2",
    "dg_m4_dl5_b2",
    "dg_m6_dl5_b2",
    "b_b12_mid_dglobal",
]


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


def _gpu_inventory() -> dict[str, Any]:
    command = ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used", "--format=csv,noheader"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return {"available": False, "error": str(exc), "gpus": [], "n_visible": 0, "source": SOURCE, "provenance": "nvidia_smi_preflight_v0"}
    rows = []
    if completed.returncode == 0:
        for line in completed.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 4:
                rows.append({"index": int(parts[0]), "name": parts[1], "memory_total": parts[2], "memory_used": parts[3]})
    return {"available": completed.returncode == 0, "returncode": completed.returncode, "stderr": completed.stderr.strip(), "gpus": rows, "n_visible": len(rows), "source": SOURCE, "provenance": "nvidia_smi_preflight_v0"}


def _forward_gate_state(forward_gate: dict[str, Any] | None) -> dict[str, Any]:
    if not forward_gate:
        return {"present": False, "schema_ok": False, "hardness_ok": False, "truncation_ok": False, "config_ok": False, "status": None, "blockers": ["missing_p1a_forward_gate_v1"]}
    acceptance = forward_gate.get("acceptance", {})
    config = forward_gate.get("generation_config", {})
    truncation_rows = forward_gate.get("prelaunch_truncation_gate", [])
    truncation_gate = truncation_rows[0] if truncation_rows else {}
    schema_ok = forward_gate.get("schema_version") == REQUIRED_FORWARD_GATE_SCHEMA
    hardness_ok = forward_gate.get("status") == "RUNG1_SEPARATOR_LLM_PO_FORWARD_GATE_PASS" and bool(acceptance.get("forward_gate_pass"))
    truncation_ok = bool(acceptance.get("forward_gate_truncation_ok")) and bool(truncation_gate.get("pass"))
    config_ok = int(config.get("max_new_tokens") or 0) >= P1A_MAX_NEW_TOKENS and config.get("prompt_contract") == P1A_PROMPT_CONTRACT
    blockers = []
    if not schema_ok:
        blockers.append("p1a_forward_gate_schema_not_v1")
    if not hardness_ok:
        blockers.append("p1a_forward_gate_hardness_not_passed")
    if not truncation_ok:
        blockers.append("p1a_forward_gate_truncation_not_ok")
    if not config_ok:
        blockers.append("p1a_forward_gate_operator_config_stale")
    return {
        "present": True,
        "schema_ok": schema_ok,
        "hardness_ok": hardness_ok,
        "truncation_ok": truncation_ok,
        "config_ok": config_ok,
        "status": forward_gate.get("status"),
        "schema_observed": forward_gate.get("schema_version"),
        "max_new_tokens": config.get("max_new_tokens"),
        "prompt_contract": config.get("prompt_contract"),
        "solve_rate": acceptance.get("solve_rate"),
        "max_deep_frac_truncated_no_answer": truncation_gate.get("max_deep_frac_truncated_no_answer"),
        "max_all_frac_truncated_no_answer": truncation_gate.get("max_all_frac_truncated_no_answer"),
        "blockers": blockers,
    }


def _gate_preflight(separator_gate: dict[str, Any] | None, qwen_download: dict[str, Any] | None, gpu_inventory: dict[str, Any], forward_gate: dict[str, Any] | None, requested_gpus: int) -> dict[str, Any]:
    acceptance = separator_gate.get("acceptance", {}) if separator_gate else {}
    schema = separator_gate.get("schema_version") if separator_gate else None
    status = separator_gate.get("status") if separator_gate else None
    overall_pass = bool(acceptance.get("overall_pass"))
    llm_allowed = bool(acceptance.get("llm_version_allowed"))
    fairness_corner_clean = bool(acceptance.get("fairness_corner_clean"))
    schema_ok = schema == REQUIRED_SYMBOLIC_SCHEMA
    model_ok = bool(qwen_download) and qwen_download.get("model_id") == MODEL_ID
    gpu_ok = gpu_inventory.get("n_visible", 0) >= requested_gpus
    forward_state = _forward_gate_state(forward_gate)
    forward_ok = forward_state["schema_ok"] and forward_state["hardness_ok"] and forward_state["truncation_ok"] and forward_state["config_ok"]
    gate_pass = overall_pass and llm_allowed and fairness_corner_clean and schema_ok and model_ok and gpu_ok and forward_ok
    blockers = []
    if separator_gate is None:
        blockers.append("missing_symbolic_separator_gate")
    if not schema_ok:
        blockers.append(f"symbolic_schema_not_{REQUIRED_SYMBOLIC_SCHEMA}")
    if not overall_pass:
        blockers.append("symbolic_overall_pass_false")
    if not llm_allowed:
        blockers.append("symbolic_llm_version_allowed_false")
    if not fairness_corner_clean:
        blockers.append("symbolic_fairness_corner_clean_false")
    if not model_ok:
        blockers.append("qwen35_download_record_missing_or_mismatch")
    if not gpu_ok:
        blockers.append("fewer_than_requested_gpus_visible")
    blockers.extend(forward_state["blockers"])
    return {
        "gate": "symbolic_separator_v0_2_3_fairness_and_p1a_forward_truncation_required_before_recovery",
        "pass": gate_pass,
        "blockers": blockers,
        "requested_gpus": requested_gpus,
        "visible_gpus": gpu_inventory.get("n_visible", 0),
        "symbolic_schema_required": REQUIRED_SYMBOLIC_SCHEMA,
        "symbolic_schema_observed": schema,
        "symbolic_status_observed": status,
        "symbolic_overall_pass": overall_pass,
        "symbolic_llm_version_allowed": llm_allowed,
        "symbolic_fairness_corner_clean": fairness_corner_clean,
        "qwen35_download_recorded": model_ok,
        "p1a_forward_gate_schema_required": REQUIRED_FORWARD_GATE_SCHEMA,
        "p1a_forward_gate_schema_observed": forward_state.get("schema_observed"),
        "p1a_forward_gate_status_observed": forward_state.get("status"),
        "p1a_forward_gate_hardness_ok": bool(forward_state["hardness_ok"]),
        "p1a_forward_gate_truncation_ok": bool(forward_state["truncation_ok"]),
        "p1a_forward_gate_config_ok": bool(forward_state["config_ok"]),
        "p1a_forward_gate_max_new_tokens": forward_state.get("max_new_tokens"),
        "p1a_forward_gate_prompt_contract": forward_state.get("prompt_contract"),
        "p1a_forward_gate_solve_rate": forward_state.get("solve_rate"),
        "p1a_forward_gate_max_deep_frac_truncated_no_answer": forward_state.get("max_deep_frac_truncated_no_answer"),
        "p1a_forward_gate_max_all_frac_truncated_no_answer": forward_state.get("max_all_frac_truncated_no_answer"),
        "source": SOURCE,
        "provenance": "rung1_separator_llm_po_fail_closed_gate_v0",
    }


def _planned_run_config(requested_gpus: int) -> dict[str, Any]:
    return {
        "model_id": MODEL_ID,
        "temperature": 0,
        "max_new_tokens_minimum": P1A_MAX_NEW_TOKENS,
        "requested_gpus": requested_gpus,
        "gpu_device_ids": list(range(requested_gpus)),
        "recommended_initial_batch_size_per_gpu": 2,
        "oom_retry_batch_size_per_gpu": 1,
        "rungs": PLANNED_RUNGS,
        "first_rung": "P1a_branch_only_sound",
        "planned_cells": PLANNED_CELLS,
        "n_per_cell": 24,
        "n_seeds": 2,
        "per_instance_llm_call_cap": 200,
        "comm_budget_sweep": COMM_BUDGET_SWEEP,
        "p1a_prompt_contract": P1A_PROMPT_CONTRACT,
        "p1a_thinking_disabled": True,
        "forward_gate_truncation_threshold": FORWARD_GATE_TRUNCATION_THRESHOLD,
        "required_forward_gate_schema": REQUIRED_FORWARD_GATE_SCHEMA,
        "po_visibility": "agent sees own block, incident boundary edges, and messaged boundary-neighbor colors only; no global graph view",
        "frozen_symbolic_components": ["register", "recovery_routing", "boundary_message_protocol", "symbolic_guard_for_P1a"],
        "generation_contract": "P1a returns compact JSON-only branch values; extract last parseable JSON; record truncated_no_answer/parsable_invalid/valid plus finish_reason, output_tokens, thinking_tokens",
        "source": SOURCE,
        "provenance": "rung1_separator_llm_po_phase2_plan_v1",
    }


def _verdict(gate: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "check": "symbolic_separator_v0_2_3_fairness_gate",
            "predicted": "must pass before any Qwen call",
            "observed": f"pass={gate['pass']}; blockers={gate['blockers']}",
            "pass": bool(gate["pass"]),
            "source": SOURCE,
            "provenance": "rung1_separator_llm_po_preflight_verdict_v0",
        },
        {
            "check": "forward_gate_truncation_ok",
            "predicted": f"P1a forward gate v1 must pass with max truncated_no_answer <= {FORWARD_GATE_TRUNCATION_THRESHOLD:.2f}",
            "observed": f"hardness_ok={gate['p1a_forward_gate_hardness_ok']}; truncation_ok={gate['p1a_forward_gate_truncation_ok']}; max_deep={gate['p1a_forward_gate_max_deep_frac_truncated_no_answer']}; max_all={gate['p1a_forward_gate_max_all_frac_truncated_no_answer']}",
            "pass": bool(gate["p1a_forward_gate_hardness_ok"] and gate["p1a_forward_gate_truncation_ok"] and gate["p1a_forward_gate_config_ok"]),
            "source": SOURCE,
            "provenance": "rung1_separator_llm_po_preflight_verdict_v1",
        },
        {
            "check": "llm_run_started",
            "predicted": "preflight records readiness only; recovery body is not launched by this command",
            "observed": f"llm_run_started=False; recovery_prelaunch_ready={bool(gate['pass'])}",
            "pass": True,
            "source": SOURCE,
            "provenance": "rung1_separator_llm_po_preflight_verdict_v1",
        },
    ]


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    gate = results["gate_preflight"]
    forward_gate = _read_json(FORWARD_GATE_RESULTS_PATH)
    artifacts = [_rel(RESULTS_PATH), _rel(ITEM_PATH)]
    code_added_used = [
        {"path": "experiments/rung1_separator_llm_po.py", "change": "Adds a gated preflight entrypoint for the LLM-native PO separator experiment."}
    ]
    commands = [
        {"command": ".venv/bin/python -m experiments.rung1_separator_llm_po --requested-gpus 8", "purpose": "Check Phase 2 gate and record whether the 8-GPU LLM run may start."}
    ]
    result_tables = {
        "gate_preflight": {"rows": [results["gate_preflight"]]},
        "gpu_inventory": {"rows": results["gpu_inventory"].get("gpus", [])},
        "planned_run_config": {"rows": [results["planned_run_config"]]},
        "verdict": {"rows": results["verdict"]},
    }
    if gate["pass"] and forward_gate:
        artifacts.append(_rel(FORWARD_GATE_RESULTS_PATH))
        code_added_used.append({"path": "experiments/rung1_separator_llm_po_forward_gate.py", "change": "Runs the Qwen3.5 P1a forward-only PO hardness gate across 8 GPU shards."})
        commands.append({"command": f".venv/bin/python -m experiments.rung1_separator_llm_po_forward_gate --launch-8gpu --num-shards {gate['requested_gpus']} --batch-size 2 --max-new-tokens 8192", "purpose": "Run the P1a forward-only Qwen hardness and truncation prelaunch gate on the requested GPU IDs."})
        for table_name in ["prelaunch_truncation_gate", "recovery_sweep_cost_estimate", "operator_error_breakdown", "keff_inflation", "budget_at_95_solve", "verdict"]:
            result_tables[f"forward_gate_{table_name}"] = {"rows": forward_gate.get(table_name, [])}
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": ITEM_NUMBER,
        "name": "Rung-1 LLM-operator PO separator experiment gated preflight",
        "status": results["status"],
        "purpose": "Fail-closed preflight for the 8-GPU Qwen3.5 PO separator Phase 2 experiment. It records GPU/model readiness and refuses to launch recovery sweeps unless symbolic separator-scaling v0.2.3 and the P1a forward truncation gate both pass.",
        "code_added_used": code_added_used,
        "commands": commands,
        "artifacts": artifacts,
        "provenance": results["planned_run_config"],
        "result_tables": result_tables,
        "honesty": {
            "does_not_establish": "A preflight-only status does not establish decoupling survival or d* under fallible operators. If the forward-gate artifact is present, it measures only the P1a forward-only hardness gate, not recovery sweeps.",
            "gate_reason": "; ".join(gate["blockers"]) if gate["blockers"] else "gate_passed_but_llm_body_not_implemented_in_this_preflight",
            "gpu_note": f"requested={gate['requested_gpus']}; visible={gate['visible_gpus']}",
        },
        "decision": {
            "gate_outcomes": [
                {"gate": "symbolic_separator_v0_2_3_fairness_gate", "outcome": "PASS" if gate["pass"] else "STOP", "number": f"blockers={gate['blockers']}"},
                {"gate": "forward_gate_truncation_ok", "outcome": "PASS" if gate["p1a_forward_gate_truncation_ok"] else "STOP", "number": f"max_deep={gate['p1a_forward_gate_max_deep_frac_truncated_no_answer']}; max_all={gate['p1a_forward_gate_max_all_frac_truncated_no_answer']}"},
                {"gate": "qwen35_model_record", "outcome": "PASS" if gate["qwen35_download_recorded"] else "FAIL", "number": f"model_id={MODEL_ID}"},
                {"gate": "requested_gpus_visible", "outcome": "PASS" if gate["visible_gpus"] >= gate["requested_gpus"] else "FAIL", "number": f"requested={gate['requested_gpus']}; visible={gate['visible_gpus']}"},
            ],
            "next_step_routing": "Launch the P1a recovery sweep only after symbolic v0.2.3 and forward_gate_truncation_ok both pass; this preflight does not start the recovery body.",
            "outcome": results["status"],
            "overall_pass": bool(gate["pass"]),
        },
    }


def run(requested_gpus: int) -> dict[str, Any]:
    separator_gate = _read_json(SEPARATOR_GATE_PATH)
    qwen_download = _read_json(QWEN35_DOWNLOAD_PATH)
    forward_gate = _read_json(FORWARD_GATE_RESULTS_PATH)
    gpu_inventory = _gpu_inventory()
    gate = _gate_preflight(separator_gate, qwen_download, gpu_inventory, forward_gate, requested_gpus)
    status = STATUS_READY_NOT_RUN if gate["pass"] else STATUS_GATED_STOP
    results = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": status,
        "gate_preflight": gate,
        "gpu_inventory": gpu_inventory,
        "planned_run_config": _planned_run_config(requested_gpus),
        "operator_error_breakdown": [],
        "keff_inflation": [],
        "efficiency_gap_survival": [],
        "dstar_vs_inflated_keff": [],
        "budget_at_95_solve": [],
        "instance_arm_metrics": [],
        "verdict": _verdict(gate),
    }
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def main() -> None:
    global RUN_ROOT, RESULTS_PATH, ITEM_PATH, FORWARD_GATE_RESULTS_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--requested-gpus", type=int, default=8)
    parser.add_argument("--output-dir", default=str(RUN_ROOT))
    parser.add_argument("--item-output", default=str(ITEM_PATH))
    args = parser.parse_args()
    RUN_ROOT = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    RESULTS_PATH = RUN_ROOT / "results.json"
    FORWARD_GATE_RESULTS_PATH = RUN_ROOT / "p1a_forward_gate.json"
    ITEM_PATH = Path(args.item_output) if Path(args.item_output).is_absolute() else REPO_ROOT / args.item_output
    run(args.requested_gpus)


if __name__ == "__main__":
    main()
