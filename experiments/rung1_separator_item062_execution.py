"""Item062 guarded execution: P1b refit/extended-D and P1c competence gate."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any

import torch

from experiments.gen_separator_scaling import generate_separator_scaling_pool
from experiments.rung1_distributed_graph_coloring import Instance, REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_separator_llm_po_forward_gate import _last_json, _load_model
from experiments.rung1_separator_p1b_full_table import GRADED_PATH, _operator_by_b
from experiments.rung1_separator_p1b_full_table_controlled_v1 import _interpolate_dstar, _ols_slope
from experiments.rung1_separator_p1c_truncation_pilot import (
    OPERATOR_VERSION_V1,
    OPERATOR_VERSION_V2,
    PILOT_RESULTS_PATH as P1C_PILOT_PATH,
    _collect_pilot_instances,
    _generate_batch_p1c,
    _initial_domains,
    _prompt_for_operator,
    _visible_context,
)
from experiments.rung1_separator_scaling import DEFAULT_NODE_CAP, _instance_from_row


RESULTS_ROOT = REPO_ROOT / "results/rung1_separator_fallibility_rungs"
OUTPUT_PATH = RESULTS_ROOT / "item062_execution.json"
SCHEMA_VERSION = "rung1_separator_item062_execution_v0"
STATUS_COMPLETE = "RUNG1_SEPARATOR_ITEM062_EXECUTION_GUARDED_PARTIAL_COMPLETE"
RESOURCE_D_EXTENDED = (4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 50)
DEPTH_EXTENDED = (4, 5, 6, 7, 9, 10, 12, 16, 20, 24, 30, 36, 42)
B_VALUES = (2, 4, 8, 12)
STEADY_STATE_MIN_EVENTS = 1
FUNCTIONAL_GATE_THRESHOLD = 0.20
P1C_COMPETENCE_OPERATOR_VERSIONS = (OPERATOR_VERSION_V1, OPERATOR_VERSION_V2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _group(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    out: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[tuple(row[key] for key in keys)].append(row)
    return out


def _generate_deep_manifest(n_per_cell: int, depths: tuple[int, ...], b_values: tuple[int, ...], seeds: tuple[int, ...]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    counts = [n_per_cell // len(seeds) + int(index < n_per_cell % len(seeds)) for index in range(len(seeds))]
    for b_value in b_values:
        for depth in depths:
            cell_manifest: list[dict[str, Any]] = []
            cell_attempts = 0
            rejection_counters: dict[str, int] = defaultdict(int)
            for seed, target_n in zip(seeds, counts):
                if target_n <= 0:
                    continue
                cell_id = f"item062_b{b_value}_d{depth}"
                cell = generate_separator_scaling_pool(
                    m_blocks=4,
                    n_per_block=12,
                    k=4,
                    d_local=5,
                    b=b_value,
                    d_boundary=2,
                    n_instances=target_n,
                    seed=seed + depth * 101 + b_value * 17,
                    target_d_global=depth,
                    cell_id=cell_id,
                    sweep="item062_extended_depth_resource_D",
                )
                cell_manifest.extend(cell.get("instance_manifest", []))
                cell_attempts += int(cell.get("cell", {}).get("attempts", 0))
                for key, value in cell.get("cell", {}).get("rejection_counters", {}).items():
                    rejection_counters[key] += int(value)
            target_met = len(cell_manifest) == n_per_cell
            for row in cell_manifest:
                row["target_met"] = target_met
            manifest.extend(cell_manifest)
            cell_rows.append({
                "b_bin": str(b_value),
                "d_global_bin": str(depth),
                "n_instances_target": n_per_cell,
                "n_instances": len(cell_manifest),
                "target_met": target_met,
                "attempts": cell_attempts,
                "rejection_counters": dict(rejection_counters),
                "source": SOURCE,
                "provenance": "item062_deep_instance_generation",
            })
    return manifest, cell_rows


def _boundary_active_vertices(instance: Instance) -> set[int]:
    out = set()
    for u, v in instance.edges:
        if instance.partitions[u] != instance.partitions[v]:
            out.add(u)
            out.add(v)
    return out


def _solve_monolith_instrumented(instance: Instance, node_cap: int, register_capacity_d: int, keff_hat: float) -> dict[str, Any]:
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    position = {vertex: index for index, vertex in enumerate(order)}
    boundary_active = _boundary_active_vertices(instance)
    assignment: dict[int, int] = {}
    register: list[dict[str, int]] = []
    next_choice_index = {vertex: 0 for vertex in order}
    steps = 0
    retractions = 0
    max_backjump_distance = 0
    first_conflict_depth = int(instance.reference_depth)
    cursor = 0
    cap_boundary_entries: list[int] = []
    cap_register_entries: list[int] = []

    def effective_peak_value() -> int:
        return math.ceil(max(first_conflict_depth, max_backjump_distance) * math.log(max(keff_hat, 1.0001)))

    def record_cap_pressure(effective_peak: int) -> None:
        if effective_peak >= register_capacity_d:
            cap_register_entries.append(len(register))
            cap_boundary_entries.append(sum(1 for entry in register if int(entry["vertex"]) in boundary_active))

    while True:
        effective_peak = effective_peak_value()
        record_cap_pressure(effective_peak)
        if steps >= node_cap:
            return _instrumented_result(False, "NODE_CAP", steps, retractions, effective_peak, False, cap_boundary_entries, cap_register_entries)
        if cursor >= len(order):
            if effective_peak > register_capacity_d:
                return _instrumented_result(False, "OVERFLOW_FAIL", steps, retractions, effective_peak, True, cap_boundary_entries, cap_register_entries)
            return _instrumented_result(True, "SOLVED", steps, retractions, effective_peak, False, cap_boundary_entries, cap_register_entries)
        vertex = order[cursor]
        steps += 1
        blockers_by_color: dict[int, list[int]] = {}
        feasible: set[int] = set()
        for color in range(1, instance.k + 1):
            blockers = [neighbor for neighbor in adj[vertex] if neighbor in assignment and assignment[neighbor] == color]
            if blockers:
                blockers_by_color[color] = blockers
            else:
                feasible.add(color)
        ordered_feasible = [color for color in instance.color_orders.get(vertex, tuple(range(1, instance.k + 1))) if color in feasible]
        choice_index = next_choice_index.get(vertex, 0)
        if choice_index < len(ordered_feasible):
            color = ordered_feasible[choice_index]
            next_choice_index[vertex] = choice_index + 1
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            cursor += 1
            continue
        nogood = {min(blockers, key=lambda item: position[item]) for blockers in blockers_by_color.values()}
        earliest = min((position[item] for item in nogood), default=cursor)
        first_conflict_depth = max(first_conflict_depth, cursor - earliest)
        effective_peak = math.ceil(first_conflict_depth * math.log(max(keff_hat, 1.0001)))
        record_cap_pressure(effective_peak)
        if effective_peak > register_capacity_d:
            return _instrumented_result(False, "OVERFLOW_FAIL", steps, retractions, effective_peak, True, cap_boundary_entries, cap_register_entries)
        if not register:
            return _instrumented_result(False, "FORWARD_DEAD_END", steps, retractions, effective_peak, False, cap_boundary_entries, cap_register_entries)
        target_vertex = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        target_index = max(index for index, entry in enumerate(register) if entry["vertex"] == target_vertex)
        popped = register[target_index:]
        max_backjump_distance = max(max_backjump_distance, len(popped))
        retractions += len(popped)
        for entry in popped:
            assignment.pop(entry["vertex"], None)
        for entry in popped[1:]:
            next_choice_index[entry["vertex"]] = 0
        next_choice_index[vertex] = 0
        cursor = register[target_index]["order_index"]
        register = register[:target_index]


def _instrumented_result(solved: bool, status: str, steps: int, retractions: int, peak: int, overflowed: bool, boundary_entries: list[int], register_entries: list[int]) -> dict[str, Any]:
    return {
        "solved": solved,
        "status": status,
        "steps": steps,
        "total_retractions": retractions,
        "comm_tokens": 0,
        "peak_register_entries": peak,
        "overflowed": overflowed,
        "cap_pressure_event_count": len(boundary_entries),
        "steady_state_boundary_reservation_mean": mean(boundary_entries) if boundary_entries else 0.0,
        "steady_state_boundary_reservation_median": median(boundary_entries) if boundary_entries else 0.0,
        "steady_state_boundary_reservation_max": max(boundary_entries) if boundary_entries else 0,
        "active_register_entries_at_cap_mean": mean(register_entries) if register_entries else 0.0,
    }


def _run_extended_sweep(manifest: list[dict[str, Any]], operator_by_b: dict[int, dict[str, Any]], d_values: tuple[int, ...], node_cap: int) -> list[dict[str, Any]]:
    rows = []
    for register_capacity_d in d_values:
        for item in manifest:
            b_value = int(item["b"])
            operator = operator_by_b[b_value]
            k_eff = float(operator["graded_keff_inflated"])
            result = _solve_monolith_instrumented(_instance_from_row(item), node_cap, register_capacity_d, k_eff)
            rows.append({
                "instance_id": item["instance_id"],
                "cell_id": item["cell_id"],
                "d_global_reference": int(item["d_global_reference"]),
                "b": b_value,
                "register_capacity_D": register_capacity_d,
                "solved": bool(result["solved"]),
                "status": result["status"],
                "overflowed": bool(result["overflowed"]),
                "steps_to_solve_or_cap": int(result["steps"]),
                "peak_register_entries": int(result["peak_register_entries"]),
                "cap_pressure_event_count": int(result["cap_pressure_event_count"]),
                "steady_state_boundary_reservation_mean": float(result["steady_state_boundary_reservation_mean"]),
                "steady_state_boundary_reservation_median": float(result["steady_state_boundary_reservation_median"]),
                "steady_state_boundary_reservation_max": int(result["steady_state_boundary_reservation_max"]),
                "active_register_entries_at_cap_mean": float(result["active_register_entries_at_cap_mean"]),
                "k_eff_inflated": k_eff,
                "rho_graded": float(operator["rho_graded"]),
                "source": SOURCE,
                "provenance": "item062_extended_D_deep_sweep_instance",
            })
    return rows


def _capacity_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (register_capacity_d, d_global, b_value), subset in sorted(_group(rows, "register_capacity_D", "d_global_reference", "b").items()):
        out.append({
            "register_capacity_D": int(register_capacity_d),
            "d_global_bin": str(d_global),
            "b_bin": str(b_value),
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "overflow_rate": mean(float(row["overflowed"]) for row in subset),
            "mean_peak_register_entries": mean(float(row["peak_register_entries"]) for row in subset),
            "mean_cap_pressure_event_count": mean(float(row["cap_pressure_event_count"]) for row in subset),
            "mean_steady_state_boundary_reservation": mean(float(row["steady_state_boundary_reservation_mean"]) for row in subset),
            "k_eff_inflated": mean(float(row["k_eff_inflated"]) for row in subset),
            "source": SOURCE,
            "provenance": "item062_extended_D_deep_sweep_capacity",
        })
    return out


def _dstar_rows(capacity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for (register_capacity_d, b_bin), subset in sorted(_group(capacity, "register_capacity_D", "b_bin").items(), key=lambda item: (int(item[0][0]), int(item[0][1]))):
        depth_rates = [(int(row["d_global_bin"]), float(row["solve_rate"])) for row in subset]
        rows.append({
            "register_capacity_D": int(register_capacity_d),
            "b_bin": str(b_bin),
            "k_eff_inflated": mean(float(row["k_eff_inflated"]) for row in subset),
            "source": SOURCE,
            "provenance": "item062_extended_D_observed_dstar",
            **_interpolate_dstar(depth_rates),
        })
    return rows


def _steady_state_footprint(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (b_value,), subset in sorted(_group(rows, "b").items(), key=lambda item: int(item[0][0])):
        pressured = [row for row in subset if int(row["cap_pressure_event_count"]) >= STEADY_STATE_MIN_EVENTS]
        values = [float(row["steady_state_boundary_reservation_mean"]) for row in pressured]
        out.append({
            "b_bin": str(b_value),
            "n_pressured_rows": len(pressured),
            "steady_state_boundary_reservation_footprint": median(values) if values else 0.0,
            "mean_steady_state_boundary_reservation": mean(values) if values else 0.0,
            "max_steady_state_boundary_reservation": max(values) if values else 0.0,
            "measurement_policy": "median boundary-active register entries when effective peak is at or above D",
            "source": SOURCE,
            "provenance": "item062_steady_state_boundary_reservation_measurement",
        })
    return out


def _prediction_rows(dstar_rows: list[dict[str, Any]], footprint_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    footprint_by_b = {row["b_bin"]: float(row["steady_state_boundary_reservation_footprint"]) for row in footprint_rows}
    out = []
    for row in dstar_rows:
        footprint = footprint_by_b.get(row["b_bin"], 0.0)
        k_eff = float(row["k_eff_inflated"])
        observed = row.get("dstar_observed")
        predicted = (float(row["register_capacity_D"]) - footprint) / math.log(max(k_eff, 1.0001))
        out.append({
            **row,
            "steady_state_footprint_b": footprint,
            "dstar_predicted_steady_state_penalty": predicted,
            "residual_steady_state_penalty": None if observed is None else float(observed) - predicted,
            "source": SOURCE,
            "provenance": "item062_steady_state_penalty_prediction",
        })
    return out


def _fit_rows(prediction_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    uncensored = [row for row in prediction_rows if row.get("dstar_observed") is not None and row.get("censoring") == "uncensored_interpolated"]
    all_points = [(float(row["dstar_predicted_steady_state_penalty"]), float(row["dstar_observed"])) for row in uncensored]
    overall_fit = _ols_slope(all_points)
    per_b = []
    for (b_bin,), subset in sorted(_group(uncensored, "b_bin").items(), key=lambda item: int(item[0][0])):
        fit = _ols_slope([(float(row["dstar_predicted_steady_state_penalty"]), float(row["dstar_observed"])) for row in subset])
        per_b.append({
            "b_bin": str(b_bin),
            "n_uncensored": len(subset),
            **fit,
            "source": SOURCE,
            "provenance": "item062_steady_state_penalty_per_b_slope",
        })
    return [{
        "fit_axis": "dstar_observed_vs_(D-steady_state_boundary_reservation)/ln_K_eff_inflated",
        "n_uncensored": len(uncensored),
        **overall_fit,
        "source": SOURCE,
        "provenance": "item062_steady_state_penalty_global_slope",
    }], per_b


def _alpha_beta_fit(prediction_rows: list[dict[str, Any]], transient_footprint_by_b: dict[str, float]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    uncensored = [row for row in prediction_rows if row.get("dstar_observed") is not None and row.get("censoring") == "uncensored_interpolated"]
    best = None
    for step in range(1001):
        alpha = step / 1000.0
        residual_base = []
        for row in uncensored:
            k_eff = float(row["k_eff_inflated"])
            footprint = transient_footprint_by_b.get(row["b_bin"], 0.0)
            base = (float(row["register_capacity_D"]) - alpha * footprint) / math.log(max(k_eff, 1.0001))
            residual_base.append(float(row["dstar_observed"]) - base)
        beta = mean(residual_base) if residual_base else 0.0
        sse = sum((value - beta) ** 2 for value in residual_base)
        if best is None or sse < best["sse"]:
            best = {"alpha": alpha, "beta": beta, "sse": sse}
    best = best or {"alpha": 0.0, "beta": 0.0, "sse": None}
    residuals = []
    for row in prediction_rows:
        k_eff = float(row["k_eff_inflated"])
        footprint = transient_footprint_by_b.get(row["b_bin"], 0.0)
        predicted = (float(row["register_capacity_D"]) - best["alpha"] * footprint) / math.log(max(k_eff, 1.0001)) + best["beta"]
        observed = row.get("dstar_observed")
        residuals.append({
            "register_capacity_D": row["register_capacity_D"],
            "b_bin": row["b_bin"],
            "censoring": row.get("censoring"),
            "dstar_observed": observed,
            "dstar_predicted_global_alpha_beta": predicted,
            "residual_global_alpha_beta": None if observed is None else float(observed) - predicted,
            "source": SOURCE,
            "provenance": "item062_global_alpha_beta_residual",
        })
    fit = {
        "model": "dstar = (D - alpha * transient_peak_footprint_b) / ln(K_eff_inflated) + beta",
        "alpha_global": best["alpha"],
        "beta_global": best["beta"],
        "sse": best["sse"],
        "n_uncensored": len(uncensored),
        "constraint": "single global alpha in [0,1] and single global beta fit jointly across all (D,b) cells",
        "source": SOURCE,
        "provenance": "item062_global_alpha_beta_fit",
    }
    return fit, residuals


def _p1c_offline_recompute_check() -> dict[str, Any]:
    pilot = _read_json(P1C_PILOT_PATH) or {}
    rows = pilot.get("instance_rows", [])
    keys = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    has_generation_text = any(any(key in row for key in ("text", "raw_generation", "generation", "parsed")) for row in rows)
    return {
        "status": "OFFLINE_RECOMPUTE_READY" if has_generation_text else "OFFLINE_RECOMPUTE_BLOCKED_NO_GENERATION_TEXT",
        "source_artifact": _rel(P1C_PILOT_PATH),
        "n_rows": len(rows),
        "row_keys": keys,
        "has_generation_text": has_generation_text,
        "action": "grade existing generations" if has_generation_text else "run a small new competence pilot",
        "source": SOURCE,
        "provenance": "item062_p1c_offline_recompute_precheck",
    }


def _parse_last_json(text: str) -> dict[str, Any]:
    parsed = _last_json(text)
    if isinstance(parsed, tuple):
        return parsed[0] or {}
    return parsed or {}


def _greedy_assignment_until(row: dict[str, Any], cursor: int) -> dict[int, int] | None:
    adjacency = _adjacency(int(row["n_vertices"]), tuple(tuple(int(x) for x in edge) for edge in row["edges"]))
    assignment: dict[int, int] = {}
    for vertex in list(row["order"])[:cursor]:
        feasible = [color for color in range(1, int(row["k"]) + 1) if all(assignment.get(neighbor) != color for neighbor in adjacency[int(vertex)])]
        if not feasible:
            return None
        assignment[int(vertex)] = feasible[0]
    return assignment


def _visible_conflict_oracle(row: dict[str, Any], assignment: dict[int, int], vertex: int) -> tuple[bool, set[int]]:
    episode = {"row": row, "assignment": assignment}
    context = _visible_context(episode, vertex)
    visible_assignment = {int(k): int(v) for k, v in context["visible_assignment"].items()}
    blockers: set[int] = set()
    colors_blocked = set()
    adjacency = _adjacency(int(row["n_vertices"]), tuple(tuple(int(x) for x in edge) for edge in row["edges"]))
    for color in range(1, int(row["k"]) + 1):
        color_blockers = [neighbor for neighbor in adjacency[vertex] if neighbor in visible_assignment and visible_assignment[neighbor] == color]
        if color_blockers:
            colors_blocked.add(color)
            blockers.update(color_blockers)
    return len(colors_blocked) == int(row["k"]), blockers


def _competence_episodes(instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    episodes = []
    for row in instances:
        order = [int(vertex) for vertex in row["order"]]
        found_conflict = False
        found_nonconflict = False
        for cursor, vertex in enumerate(order):
            assignment = _greedy_assignment_until(row, cursor)
            if assignment is None:
                break
            conflict, culprits = _visible_conflict_oracle(row, assignment, vertex)
            if conflict and not found_conflict:
                episodes.append({"row": row, "order": order, "domains": _initial_domains(row), "assignment": assignment, "cursor": cursor, "oracle_conflict": True, "oracle_culprits": sorted(culprits), "episode_type": "conflict"})
                found_conflict = True
            if not conflict and cursor > 0 and not found_nonconflict:
                episodes.append({"row": row, "order": order, "domains": _initial_domains(row), "assignment": assignment, "cursor": cursor, "oracle_conflict": False, "oracle_culprits": [], "episode_type": "nonconflict"})
                found_nonconflict = True
            if found_conflict and found_nonconflict:
                break
    return episodes


@torch.no_grad()
def _run_p1c_competence(device: str, num_instances: int, max_new_tokens: int, operator_version: str) -> dict[str, Any]:
    instances = _collect_pilot_instances(num_instances)
    episodes = _competence_episodes(instances)
    if not episodes:
        return {"status": "P1C_COMPETENCE_NO_EPISODES", "competence_rows": [], "summary": {}}
    model, tokenizer, _ = _load_model(device, "auto")
    rows = []
    try:
        for index, episode in enumerate(episodes):
            prompt = _prompt_for_operator(episode, operator_version)
            generation = _generate_batch_p1c(model, tokenizer, [prompt], max_new_tokens, operator_version)[0]
            parsed = _parse_last_json(generation.get("text", ""))
            predicted_conflict = bool(parsed.get("conflict_detected"))
            culprit = parsed.get("culprit")
            try:
                culprit_int = None if culprit is None else int(culprit)
            except (TypeError, ValueError):
                culprit_int = None
            oracle_conflict = bool(episode["oracle_conflict"])
            oracle_culprits = set(int(value) for value in episode["oracle_culprits"])
            rows.append({
                "episode_index": index,
                "instance_id": episode["row"].get("instance_id"),
                "episode_type": episode["episode_type"],
                "current_vertex": int(episode["order"][episode["cursor"]]),
                "oracle_conflict": oracle_conflict,
                "oracle_culprits": sorted(oracle_culprits),
                "predicted_conflict": predicted_conflict,
                "predicted_culprit": culprit_int,
                "culprit_correct": bool(oracle_conflict and culprit_int in oracle_culprits),
                "parsable": bool(parsed),
                "finish_reason": generation.get("finish_reason"),
                "output_tokens": generation.get("output_tokens"),
                "raw_generation": generation.get("text", ""),
                "parsed": parsed,
                "source": SOURCE,
                "provenance": "item062_p1c_competence_generation",
            })
    finally:
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    tp = sum(1 for row in rows if row["oracle_conflict"] and row["predicted_conflict"])
    fp = sum(1 for row in rows if not row["oracle_conflict"] and row["predicted_conflict"])
    fn = sum(1 for row in rows if row["oracle_conflict"] and not row["predicted_conflict"])
    true_conflicts = sum(1 for row in rows if row["oracle_conflict"])
    conflict_precision = tp / max(1, tp + fp)
    conflict_recall = tp / max(1, tp + fn)
    culprit_accuracy = sum(1 for row in rows if row["culprit_correct"]) / max(1, true_conflicts)
    summary = {
        "n_episodes": len(rows),
        "n_true_conflicts": true_conflicts,
        "n_true_nonconflicts": sum(1 for row in rows if not row["oracle_conflict"]),
        "conflict_precision": conflict_precision,
        "conflict_recall": conflict_recall,
        "culprit_accuracy": culprit_accuracy,
        "min_competence_metric": min(conflict_precision, conflict_recall, culprit_accuracy),
        "functional_gate_threshold": FUNCTIONAL_GATE_THRESHOLD,
        "functional_gate_pass": min(conflict_precision, conflict_recall, culprit_accuracy) >= FUNCTIONAL_GATE_THRESHOLD,
        "operator_version": operator_version,
        "thinking_disabled": operator_version == OPERATOR_VERSION_V1,
        "thinking_budget_requested": 3000 if operator_version == OPERATOR_VERSION_V2 else 0,
        "answer_token_budget_requested": 1500 if operator_version == OPERATOR_VERSION_V2 else None,
        "source": SOURCE,
        "provenance": "item062_p1c_competence_summary",
    }
    return {"status": "P1C_COMPETENCE_PASS" if summary["functional_gate_pass"] else "P1C_COMPETENCE_FAIL", "competence_rows": rows, "summary": summary}


def _run_part_a(n_per_cell: int, node_cap: int) -> dict[str, Any]:
    graded = _read_json(GRADED_PATH)
    corrected = _read_json(RESULTS_ROOT / "p1b_full_table_v1.json") or {}
    operator = _operator_by_b(graded)
    manifest, generation = _generate_deep_manifest(n_per_cell, DEPTH_EXTENDED, B_VALUES, (1458, 2039))
    rows = _run_extended_sweep(manifest, operator, RESOURCE_D_EXTENDED, node_cap)
    capacity = _capacity_rows(rows)
    dstar = _dstar_rows(capacity)
    steady_footprint = _steady_state_footprint(rows)
    prediction = _prediction_rows(dstar, steady_footprint)
    steady_global_fit, steady_per_b_fit = _fit_rows(prediction)
    alpha_beta_fit, alpha_beta_residuals = _alpha_beta_fit(prediction, {str(k): float(v) for k, v in corrected.get("separator_footprint_by_b", {}).items()})
    right_censored = sum(1 for row in dstar if row.get("censoring") == "right_censored_at_max_depth")
    uncensored = sum(1 for row in dstar if row.get("censoring") == "uncensored_interpolated")
    return {
        "status": "PART_A_EXTENDED_D_SWEEP_COMPLETE",
        "generation_cells": generation,
        "instance_arm_metrics": rows,
        "capacity_leg": capacity,
        "observed_dstar_by_resource_D_b": dstar,
        "steady_state_boundary_reservation": steady_footprint,
        "steady_state_penalty_predictions": prediction,
        "steady_state_global_slope": steady_global_fit,
        "steady_state_per_b_slope": steady_per_b_fit,
        "global_alpha_beta_fit": [alpha_beta_fit],
        "global_alpha_beta_residuals": alpha_beta_residuals,
        "censoring_summary": {
            "n_dstar_rows": len(dstar),
            "n_uncensored_interpolated": uncensored,
            "n_right_censored_at_max_depth": right_censored,
            "n_left_censored_below_min_depth": sum(1 for row in dstar if row.get("censoring") == "left_censored_below_min_depth"),
            "right_censored_excluded_from_slope_fit": True,
            "source": SOURCE,
            "provenance": "item062_extended_D_censoring_summary",
        },
    }


def run(run_part_a: bool, run_p1c_competence: bool, n_per_cell: int, node_cap: int, p1c_device: str, p1c_num_instances: int, p1c_max_new_tokens: int, p1c_operator_version: str, output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    output_path = output_path if output_path.is_absolute() else REPO_ROOT / output_path
    existing = _read_json(output_path) or {}
    offline = _p1c_offline_recompute_check()
    part_a = _run_part_a(n_per_cell, node_cap) if run_part_a else existing.get("part_a", {"status": "PART_A_NOT_RUN"})
    p1c_competence = existing.get("p1c_competence", {"status": "P1C_COMPETENCE_NOT_RUN"})
    p1c_competence_retries = existing.get("p1c_competence_retries", {})
    if run_p1c_competence and not offline["has_generation_text"]:
        retry = _run_p1c_competence(p1c_device, p1c_num_instances, p1c_max_new_tokens, p1c_operator_version)
        if p1c_operator_version == OPERATOR_VERSION_V1:
            p1c_competence = retry
        else:
            p1c_competence_retries[p1c_operator_version] = retry
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": STATUS_COMPLETE,
        "generation_config": {
            "run_part_a": run_part_a,
            "run_p1c_competence": run_p1c_competence,
            "n_per_cell": n_per_cell,
            "node_cap": node_cap,
            "resource_D_extended": list(RESOURCE_D_EXTENDED),
            "depth_extended": list(DEPTH_EXTENDED),
            "b_values": list(B_VALUES),
            "p1c_device": p1c_device,
            "p1c_num_instances": p1c_num_instances,
            "p1c_max_new_tokens": p1c_max_new_tokens,
            "p1c_operator_version": p1c_operator_version,
            "source": SOURCE,
            "provenance": "item062_execution_config",
        },
        "execution_cautions_applied": [
            {"caution": "global_penalty_only", "applied": True, "detail": "alpha and beta are fit once globally across all uncensored (D,b) cells", "source": SOURCE, "provenance": "item062_caution_guard"},
            {"caution": "prefer_measurement", "applied": True, "detail": "steady-state boundary reservation is measured and tested before alpha/beta fallback", "source": SOURCE, "provenance": "item062_caution_guard"},
            {"caution": "deepen_with_D", "applied": True, "detail": "extended D sweep uses d_global targets through 42 and excludes right-censored max-depth rows from slope fits", "source": SOURCE, "provenance": "item062_caution_guard"},
            {"caution": "p1c_offline_first", "applied": True, "detail": offline["status"], "source": SOURCE, "provenance": "item062_caution_guard"},
        ],
        "p1c_offline_recompute_check": [offline],
        "part_a": part_a,
        "p1c_competence": p1c_competence,
        "p1c_competence_retries": p1c_competence_retries,
    }
    _write_json(output_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run guarded Item062 execution steps.")
    parser.add_argument("--part-a", action="store_true")
    parser.add_argument("--p1c-competence", action="store_true")
    parser.add_argument("--n-per-cell", type=int, default=8)
    parser.add_argument("--node-cap", type=int, default=max(DEFAULT_NODE_CAP, 2000))
    parser.add_argument("--p1c-device", default="cuda:0")
    parser.add_argument("--p1c-num-instances", type=int, default=12)
    parser.add_argument("--p1c-max-new-tokens", type=int, default=2048)
    parser.add_argument("--p1c-operator-version", choices=P1C_COMPETENCE_OPERATOR_VERSIONS, default=OPERATOR_VERSION_V1)
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()
    run(args.part_a, args.p1c_competence, args.n_per_cell, args.node_cap, args.p1c_device, args.p1c_num_instances, args.p1c_max_new_tokens, args.p1c_operator_version, Path(args.output))


if __name__ == "__main__":
    main()
