"""Preregistered symbolic preflight for the multi-agent capacity-coupling paper.

This module constructs a fixed-density capacity-under/over by coupling-low/high
phase map and evaluates five recovery-window arms. It is a no-LLM generator and
fairness preflight only; no downstream LLM claim is eligible from its outputs.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any

from experiments.capacity.stats import mcnemar_exact
from experiments.gen_separator_scaling import generate_separator_scaling_pool
from experiments.rung1_distributed_graph_coloring import (
    Instance,
    REFERENCE_NODE_CAP,
    REPO_ROOT,
    _default_color_orders,
    _solve,
)


SCHEMA_VERSION = "multiagent_capacity_coupling_preflight_v1"
STATUS_GO = "MULTIAGENT_CORE_2X2_PREFLIGHT_GO"
STATUS_NO_GO = "MULTIAGENT_CORE_2X2_PREFLIGHT_NO_GO"
ARMS = (
    "team_cbj",
    "team_chronological",
    "monolith_R",
    "monolith_MR",
    "centralized_sharded_MR",
)
CAPACITY_LEVELS = ("under", "over_local_fit")
COUPLING_LEVELS = ("low", "high")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path.relative_to(REPO_ROOT)), "status": payload.get("status")}), flush=True)


def _adjacency(n: int, edges: list[tuple[int, int]] | tuple[tuple[int, int], ...]) -> list[set[int]]:
    adjacency = [set() for _ in range(int(n))]
    for left, right in edges:
        adjacency[int(left)].add(int(right))
        adjacency[int(right)].add(int(left))
    return adjacency


def _find_coloring(n: int, edges: set[tuple[int, int]], k: int) -> dict[int, int] | None:
    adjacency = _adjacency(n, sorted(edges))
    order = sorted(range(int(n)), key=lambda vertex: (-len(adjacency[vertex]), vertex))
    assignment: dict[int, int] = {}

    def recurse(index: int) -> bool:
        if index == len(order):
            return True
        vertex = order[index]
        blocked = {assignment[neighbor] for neighbor in adjacency[vertex] if neighbor in assignment}
        for color in range(1, int(k) + 1):
            if color in blocked:
                continue
            assignment[vertex] = color
            if recurse(index + 1):
                return True
            assignment.pop(vertex, None)
        return False

    return dict(assignment) if recurse(0) else None


def _instance_from_row(row: dict[str, Any]) -> Instance:
    n = int(row["n_vertices"])
    k = int(row["k"])
    return Instance(
        instance_id=str(row["instance_id"]),
        seed=int(row["seed"]),
        source_index=int(row["source_index"]),
        source_kind=str(row["source_kind"]),
        n=n,
        k=k,
        chromatic_number=k,
        edges=tuple(sorted(tuple(map(int, edge)) for edge in row["edges"])),
        partitions=tuple(int(value) for value in row["partitions"]),
        order=tuple(int(value) for value in row["order"]),
        color_orders=_default_color_orders(n, k),
        reference_depth=int(row.get("reference_cross_agent_conflict_depth", 0)),
        band=str(row.get("cell_id", "phase_map")),
        boundary_conflict_exact=bool(row.get("boundary_conflict_exact", True)),
    )


def _normalize_fixed_density(row: dict[str, Any], edge_budget: int) -> dict[str, Any] | None:
    n = int(row["n_vertices"])
    k = int(row["k"])
    partitions = [int(value) for value in row["partitions"]]
    edges = {tuple(sorted(map(int, edge))) for edge in row["edges"]}
    if len(edges) > int(edge_budget):
        return None
    coloring = _find_coloring(n, edges, k)
    if coloring is None:
        return None
    candidates = [
        (left, right)
        for left in range(n)
        for right in range(left + 1, n)
        if partitions[left] == partitions[right]
        and coloring[left] != coloring[right]
        and (left, right) not in edges
    ]
    generator = random.Random(int(row["source_index"]) + 7717 + int(edge_budget) * 31)
    generator.shuffle(candidates)
    needed = int(edge_budget) - len(edges)
    if len(candidates) < needed:
        return None
    edges.update(candidates[:needed])
    normalized = dict(row)
    normalized["edges"] = [list(edge) for edge in sorted(edges)]
    normalized["n_edges"] = len(edges)
    normalized["normalization_added_intra_edges"] = needed
    normalized["n_boundary_edges"] = sum(partitions[left] != partitions[right] for left, right in edges)
    normalized["n_intra_block_edges"] = len(edges) - int(normalized["n_boundary_edges"])
    normalized["rho_actual"] = int(normalized["n_boundary_edges"]) / max(len(edges), 1)
    normalized["density"] = len(edges) / max(n * (n - 1) / 2, 1)
    instance = _instance_from_row(normalized)
    reference = _solve(instance, "cbj_bounded", node_cap=REFERENCE_NODE_CAP, register_capacity=max(n, 64))
    if not reference.solved:
        return None
    if int(reference.first_conflict_depth or 0) != int(row["target_d_global"]):
        return None
    normalized["reference_cross_agent_conflict_depth"] = int(reference.first_conflict_depth or 0)
    normalized["reference_boundary_conflict_exact"] = bool(reference.boundary_conflict_exact)
    return normalized


def _arm_config(arm: str, partitions: list[int], m_agents: int, r_value: int) -> tuple[list[int], dict[int, int], str, bool]:
    if arm == "monolith_R":
        return [0 for _ in partitions], {0: int(r_value)}, "cbj", False
    if arm == "monolith_MR":
        return [0 for _ in partitions], {0: int(m_agents) * int(r_value)}, "cbj", False
    if arm == "team_chronological":
        return list(partitions), {agent: int(r_value) for agent in range(int(m_agents))}, "chronological", True
    if arm == "team_cbj":
        return list(partitions), {agent: int(r_value) for agent in range(int(m_agents))}, "cbj", True
    if arm == "centralized_sharded_MR":
        return list(partitions), {agent: int(r_value) for agent in range(int(m_agents))}, "cbj", False
    raise ValueError(f"unknown arm: {arm}")


def _valid_solution(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> bool:
    if len(assignment) != int(n):
        return False
    if any(int(assignment.get(vertex, 0)) not in range(1, int(k) + 1) for vertex in range(int(n))):
        return False
    return all(int(assignment[left]) != int(assignment[right]) for left, right in edges)


def _run_search(
    row: dict[str, Any],
    arm: str,
    m_agents: int,
    r_value: int,
    node_cap: int,
    *,
    enforce_window: bool = True,
) -> dict[str, Any]:
    n = int(row["n_vertices"])
    k = int(row["k"])
    edges = [tuple(map(int, edge)) for edge in row["edges"]]
    partitions, windows, route_mode, count_communication = _arm_config(
        arm, [int(value) for value in row["partitions"]], m_agents, r_value
    )
    adjacency = _adjacency(n, edges)
    order = [int(value) for value in row["order"]]
    position = {vertex: index for index, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    next_choice = {vertex: 0 for vertex in order}
    conflict_sets: dict[int, set[int]] = {vertex: set() for vertex in order}
    trail: list[dict[str, int]] = []
    registers: dict[int, list[dict[str, int]]] = defaultdict(list)
    cursor = 0
    steps = 0
    retractions = 0
    recoveries = 0
    cross_block_messages = 0
    boundary_commit_messages = 0
    communication_tokens = 0
    max_global_recovery_distance = 0
    max_local_recovery_distance = 0
    max_nogood_size = 0
    max_register_lengths: Counter[int] = Counter()
    peak_total_register_entries = 0

    def finish(status: str) -> dict[str, Any]:
        solved = status == "SOLVED" and _valid_solution(n, k, edges, assignment)
        final_status = "SOLVED" if solved else ("OFFICIAL_SCORE_FAIL" if status == "SOLVED" else status)
        return {
            "instance_id": str(row["instance_id"]),
            "cell": str(row.get("cell", "reference")),
            "capacity": str(row.get("capacity", "reference")),
            "coupling": str(row.get("coupling", "reference")),
            "arm": arm,
            "solved": solved,
            "status": final_status,
            "steps": steps,
            "recoveries": recoveries,
            "retractions": retractions,
            "cross_block_messages": cross_block_messages,
            "boundary_commit_messages": boundary_commit_messages,
            "communication_tokens": communication_tokens,
            "max_global_recovery_distance": max_global_recovery_distance,
            "max_local_recovery_distance": max_local_recovery_distance,
            "max_nogood_size": max_nogood_size,
            "max_register_length_per_agent": max(max_register_lengths.values(), default=0),
            "total_register_entries_peak_proxy": peak_total_register_entries,
            "declared_window_per_agent": int(r_value),
            "declared_total_window": sum(windows.values()),
            "node_cap": int(node_cap),
            "reference_mode": not enforce_window,
            "evaluation_mode": "symbolic_capacity_coupling_preflight_v1",
            "headline_eligible": False,
        }

    while True:
        if steps >= int(node_cap):
            return finish("NODE_CAP")
        if cursor >= len(order):
            return finish("SOLVED")
        vertex = order[cursor]
        if vertex in assignment:
            cursor += 1
            continue
        chosen_color = None
        while next_choice[vertex] < k:
            color = next_choice[vertex] + 1
            next_choice[vertex] += 1
            blockers = {neighbor for neighbor in adjacency[vertex] if assignment.get(neighbor) == color}
            if not blockers:
                chosen_color = color
                break
            conflict_sets[vertex].update(blockers)
        steps += 1
        if chosen_color is not None:
            assignment[vertex] = int(chosen_color)
            agent = int(partitions[vertex])
            item = {"vertex": vertex, "agent": agent, "order_index": cursor}
            trail.append(item)
            registers[agent].append(item)
            max_register_lengths[agent] = max(max_register_lengths[agent], len(registers[agent]))
            peak_total_register_entries = max(peak_total_register_entries, sum(len(register) for register in registers.values()))
            if count_communication and any(partitions[neighbor] != agent for neighbor in adjacency[vertex]):
                boundary_commit_messages += 1
                communication_tokens += 4
            cursor += 1
            continue

        blockers = {item for item in conflict_sets[vertex] if item in assignment and position[item] < cursor}
        next_choice[vertex] = 0
        if not blockers or not trail:
            return finish("EXHAUSTED")
        cross_block = any(partitions[blocker] != partitions[vertex] for blocker in blockers)
        max_nogood_size = max(max_nogood_size, len(blockers))
        if count_communication and cross_block:
            cross_block_messages += 1
            communication_tokens += 2 + 2 * len(blockers)
        target_vertex = trail[-1]["vertex"] if route_mode == "chronological" else max(blockers, key=lambda item: position[item])
        target_agent = int(partitions[target_vertex])
        target_register = registers[target_agent]
        absolute_index = max(
            (index for index, item in enumerate(target_register) if item["vertex"] == target_vertex),
            default=-1,
        )
        if absolute_index < 0:
            return finish("NO_RECOVERY_TARGET")
        local_distance = len(target_register) - absolute_index
        target_trail_index = max(index for index, item in enumerate(trail) if item["vertex"] == target_vertex)
        global_distance = len(trail) - target_trail_index
        max_local_recovery_distance = max(max_local_recovery_distance, local_distance)
        max_global_recovery_distance = max(max_global_recovery_distance, global_distance)
        if enforce_window:
            start = max(0, len(target_register) - int(windows[target_agent]))
            if absolute_index < start:
                return finish("NO_RECOVERY_TARGET")
        if route_mode == "cbj":
            conflict_sets[target_vertex].update(blocker for blocker in blockers if blocker != target_vertex)
        popped = trail[target_trail_index:]
        popped_vertices = {item["vertex"] for item in popped}
        recoveries += 1
        retractions += len(popped)
        for item in popped:
            assignment.pop(item["vertex"], None)
        trail = trail[:target_trail_index]
        for agent in list(registers):
            registers[agent] = [item for item in registers[agent] if item["vertex"] not in popped_vertices]
        for item in popped[1:]:
            next_choice[item["vertex"]] = 0
            conflict_sets[item["vertex"]].clear()
        conflict_sets[vertex].clear()
        cursor = popped[0]["order_index"]


def _reference_metrics(row: dict[str, Any], m_agents: int, r_value: int, node_cap: int) -> dict[str, Any] | None:
    global_row = _run_search(row, "monolith_MR", m_agents, max(int(row["n_vertices"]), r_value), node_cap, enforce_window=False)
    local_row = _run_search(row, "centralized_sharded_MR", m_agents, max(int(row["n_vertices"]), r_value), node_cap, enforce_window=False)
    if not global_row["solved"] or not local_row["solved"]:
        return None
    return {
        "global_recovery_distance": int(global_row["max_global_recovery_distance"]),
        "local_recovery_distance": int(local_row["max_local_recovery_distance"]),
        "reference_steps": int(global_row["steps"]),
        "reference_recoveries": int(global_row["recoveries"]),
        "reference_retractions": int(global_row["retractions"]),
        "reference_solved": True,
    }


def _desired_capacity(row: dict[str, Any], capacity: str, r_value: int) -> bool:
    global_distance = int(row["global_recovery_distance"])
    local_distance = int(row["local_recovery_distance"])
    if capacity == "under":
        return global_distance <= int(r_value)
    if capacity == "over_local_fit":
        return global_distance > int(r_value) and local_distance <= int(r_value)
    raise ValueError(capacity)


def _cell_specs(low_b: int, high_b: int, under_depth: int, over_depth: int) -> list[dict[str, Any]]:
    return [
        {"cell": "under_low", "capacity": "under", "coupling": "low", "b": int(low_b), "target_depth": int(under_depth)},
        {"cell": "under_high", "capacity": "under", "coupling": "high", "b": int(high_b), "target_depth": int(under_depth)},
        {"cell": "over_low", "capacity": "over_local_fit", "coupling": "low", "b": int(low_b), "target_depth": int(over_depth)},
        {"cell": "over_high", "capacity": "over_local_fit", "coupling": "high", "b": int(high_b), "target_depth": int(over_depth)},
    ]


def _generate_pool(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_rows: list[dict[str, Any]] = []
    generation_rows: list[dict[str, Any]] = []
    for cell_index, spec in enumerate(_cell_specs(args.low_b, args.high_b, args.under_depth, args.over_depth)):
        accepted: list[dict[str, Any]] = []
        seen: set[str] = set()
        generated = 0
        normalized = 0
        reference_solved = 0
        for batch in range(int(args.max_batches)):
            if len(accepted) >= int(args.instances_per_cell):
                break
            seed = int(args.seed) + 10_000 * cell_index + batch
            payload = generate_separator_scaling_pool(
                m_blocks=int(args.agents),
                n_per_block=int(args.n_per_block),
                k=int(args.k),
                d_local=int(args.d_local),
                b=int(spec["b"]),
                d_boundary=int(args.d_boundary),
                n_instances=int(args.candidate_batch_size),
                seed=seed,
                target_d_global=int(spec["target_depth"]),
                cell_id=f"preflight_{spec['cell']}_b{batch}",
                sweep="multiagent_core_2x2_preflight_v1",
            )
            generated += len(payload["instance_manifest"])
            for source in payload["instance_manifest"]:
                normalized_row = _normalize_fixed_density(source, int(args.edge_budget))
                if normalized_row is None:
                    continue
                normalized += 1
                metrics = _reference_metrics(normalized_row, int(args.agents), int(args.register), int(args.reference_node_cap))
                if metrics is None:
                    continue
                reference_solved += 1
                candidate = {
                    **normalized_row,
                    **metrics,
                    **spec,
                    "M": int(args.agents),
                    "R": int(args.register),
                    "MR": int(args.agents) * int(args.register),
                    "selection_rule": "reference_recovery_distance_only_no_evaluated_arm_outcomes",
                    "headline_eligible": False,
                }
                if not _desired_capacity(candidate, str(spec["capacity"]), int(args.register)):
                    continue
                if candidate["instance_id"] in seen:
                    continue
                seen.add(str(candidate["instance_id"]))
                accepted.append(candidate)
                if len(accepted) >= int(args.instances_per_cell):
                    break
        accepted_rows.extend(accepted[: int(args.instances_per_cell)])
        generation_rows.append({
            **spec,
            "target": int(args.instances_per_cell),
            "accepted": min(len(accepted), int(args.instances_per_cell)),
            "generated_candidates": generated,
            "fixed_density_candidates": normalized,
            "reference_solved_candidates": reference_solved,
            "complete": len(accepted) >= int(args.instances_per_cell),
        })
    return accepted_rows, generation_rows


def _summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cell, arm in sorted({(row["cell"], row["arm"]) for row in rows}):
        subset = [row for row in rows if row["cell"] == cell and row["arm"] == arm]
        output.append({
            "cell": cell,
            "capacity": subset[0]["capacity"],
            "coupling": subset[0]["coupling"],
            "arm": arm,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_steps": mean(float(row["steps"]) for row in subset),
            "mean_recoveries": mean(float(row["recoveries"]) for row in subset),
            "mean_retractions": mean(float(row["retractions"]) for row in subset),
            "mean_cross_block_messages": mean(float(row["cross_block_messages"]) for row in subset),
            "mean_communication_tokens": mean(float(row["communication_tokens"]) for row in subset),
            "mean_max_global_recovery_distance": mean(float(row["max_global_recovery_distance"]) for row in subset),
            "mean_max_local_recovery_distance": mean(float(row["max_local_recovery_distance"]) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def _summary_lookup(summary: list[dict[str, Any]], cell: str, arm: str) -> dict[str, Any]:
    return next(row for row in summary if row["cell"] == cell and row["arm"] == arm)


def _paired_tests(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    contrasts = (
        ("team_cbj", "monolith_R"),
        ("team_cbj", "monolith_MR"),
        ("team_cbj", "team_chronological"),
    )
    for cell in sorted({row["cell"] for row in rows}):
        index = {(row["instance_id"], row["arm"]): bool(row["solved"]) for row in rows if row["cell"] == cell}
        instance_ids = sorted({row["instance_id"] for row in rows if row["cell"] == cell})
        for left_arm, right_arm in contrasts:
            left = [index[(instance_id, left_arm)] for instance_id in instance_ids]
            right = [index[(instance_id, right_arm)] for instance_id in instance_ids]
            output.append({
                "cell": cell,
                "left_arm": left_arm,
                "right_arm": right_arm,
                "n_pairs": len(instance_ids),
                "left_solve_rate": mean(map(float, left)),
                "right_solve_rate": mean(map(float, right)),
                "solve_rate_difference": mean(map(float, left)) - mean(map(float, right)),
                "left_only": sum(a and not b for a, b in zip(left, right)),
                "right_only": sum(b and not a for a, b in zip(left, right)),
                "p_two_sided_exact_mcnemar": mcnemar_exact(left, right),
                "confirmatory": False,
            })
    return output


def _gates(
    manifest: list[dict[str, Any]],
    generation: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    low_rhos = [float(row["rho_actual"]) for row in manifest if row["coupling"] == "low"]
    high_rhos = [float(row["rho_actual"]) for row in manifest if row["coupling"] == "high"]
    rho_difference = mean(high_rhos) - mean(low_rhos) if low_rhos and high_rhos else 0.0
    expected_summaries = {
        (cell, arm)
        for cell in ("under_low", "under_high", "over_low", "over_high")
        for arm in ARMS
    }
    available_summaries = {(row["cell"], row["arm"]) for row in summary}
    if expected_summaries - available_summaries:
        return {
            "pool_complete": False,
            "fixed_density": bool(manifest) and all(int(row["n_edges"]) == int(args.edge_budget) for row in manifest),
            "capacity_strata_exact": bool(manifest) and all(_desired_capacity(row, str(row["capacity"]), int(args.register)) for row in manifest),
            "coupling_separated": rho_difference >= 0.15,
            "reference_solved": bool(manifest) and all(bool(row["reference_solved"]) for row in manifest),
            "centralized_equivalence": False,
            "monolith_under_readable": False,
            "capacity_relief_signal": False,
            "equal_memory_control": False,
            "coupling_interaction_signal": False,
            "coordination_signal": False,
            "core_pass": False,
            "signal_pass_count": 0,
            "go_real_qwen": False,
            "missing_cell_arm_summaries": sorted([list(item) for item in expected_summaries - available_summaries]),
            "observed": {
                "mean_rho_low": mean(low_rhos) if low_rhos else None,
                "mean_rho_high": mean(high_rhos) if high_rhos else None,
                "rho_high_minus_low": rho_difference,
            },
        }
    centralized_match = all(
        next(row for row in rows if row["instance_id"] == instance_id and row["arm"] == "team_cbj")["solved"]
        == next(row for row in rows if row["instance_id"] == instance_id and row["arm"] == "centralized_sharded_MR")["solved"]
        and next(row for row in rows if row["instance_id"] == instance_id and row["arm"] == "team_cbj")["status"]
        == next(row for row in rows if row["instance_id"] == instance_id and row["arm"] == "centralized_sharded_MR")["status"]
        for instance_id in sorted({row["instance_id"] for row in rows})
    )
    under_mono = mean(
        _summary_lookup(summary, cell, "monolith_R")["solve_rate"]
        for cell in ("under_low", "under_high")
    )
    over_low_team = _summary_lookup(summary, "over_low", "team_cbj")["solve_rate"]
    over_low_mono_r = _summary_lookup(summary, "over_low", "monolith_R")["solve_rate"]
    over_low_mono_mr = _summary_lookup(summary, "over_low", "monolith_MR")["solve_rate"]
    over_high_team = _summary_lookup(summary, "over_high", "team_cbj")["solve_rate"]
    over_high_mono_r = _summary_lookup(summary, "over_high", "monolith_R")["solve_rate"]
    over_cbj_chrono = max(
        _summary_lookup(summary, cell, "team_cbj")["solve_rate"]
        - _summary_lookup(summary, cell, "team_chronological")["solve_rate"]
        for cell in ("over_low", "over_high")
    )
    core = {
        "pool_complete": all(bool(row["complete"]) for row in generation),
        "fixed_density": bool(manifest) and all(int(row["n_edges"]) == int(args.edge_budget) for row in manifest),
        "capacity_strata_exact": bool(manifest) and all(_desired_capacity(row, str(row["capacity"]), int(args.register)) for row in manifest),
        "coupling_separated": rho_difference >= 0.15,
        "reference_solved": bool(manifest) and all(bool(row["reference_solved"]) for row in manifest),
        "centralized_equivalence": centralized_match,
        "monolith_under_readable": under_mono >= 0.50,
    }
    signals = {
        "capacity_relief_signal": over_low_team - over_low_mono_r >= 0.20,
        "equal_memory_control": abs(over_low_team - over_low_mono_mr) <= 0.10,
        "coupling_interaction_signal": (over_low_team - over_low_mono_r) - (over_high_team - over_high_mono_r) >= 0.05,
        "coordination_signal": over_cbj_chrono >= 0.10,
    }
    return {
        **core,
        **signals,
        "core_pass": all(core.values()),
        "signal_pass_count": sum(bool(value) for value in signals.values()),
        "go_real_qwen": all(core.values()) and sum(bool(value) for value in signals.values()) >= 2,
        "observed": {
            "mean_rho_low": mean(low_rhos),
            "mean_rho_high": mean(high_rhos),
            "rho_high_minus_low": rho_difference,
            "mean_monolith_R_under_solve": under_mono,
            "over_low_team_minus_monolith_R": over_low_team - over_low_mono_r,
            "over_low_team_minus_monolith_MR": over_low_team - over_low_mono_mr,
            "over_high_team_minus_monolith_R": over_high_team - over_high_mono_r,
            "capacity_by_coupling_gap_difference": (over_low_team - over_low_mono_r) - (over_high_team - over_high_mono_r),
            "max_over_cell_team_cbj_minus_chronological": over_cbj_chrono,
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest, generation = _generate_pool(args)
    metric_rows: list[dict[str, Any]] = []
    for row in manifest:
        for arm in ARMS:
            metric_rows.append(
                _run_search(
                    row,
                    arm,
                    int(args.agents),
                    int(args.register),
                    int(args.node_cap),
                    enforce_window=True,
                )
            )
    summary = _summaries(metric_rows) if metric_rows else []
    paired = _paired_tests(metric_rows) if metric_rows else []
    gates = _gates(manifest, generation, metric_rows, summary, args) if metric_rows else {
        "core_pass": False,
        "signal_pass_count": 0,
        "go_real_qwen": False,
        "reason": "empty preflight pool",
    }
    status = STATUS_GO if gates.get("go_real_qwen") else STATUS_NO_GO
    return {
        "schema": SCHEMA_VERSION,
        "status": status,
        "evaluation_mode": "symbolic_capacity_coupling_preflight_v1",
        "headline_eligible": False,
        "preregistration": "specs/multiagent_core_2x2_preregistration_v1.json",
        "config": vars(args),
        "generation": generation,
        "instance_manifest": manifest,
        "rows": metric_rows,
        "summary": summary,
        "paired_tests": paired,
        "gates": gates,
        "honesty": {
            "does_not_establish": "This no-LLM preflight validates generator power, recovery-window fairness, and phase-map signals only. It establishes no frozen-Qwen multi-agent claim.",
            "selection": "Instances are selected only by preregistered reference recovery distances, fixed-density normalization, and target depth; evaluated arm outcomes are not used.",
            "centralized_control": "team_cbj and centralized_sharded_MR are intentionally search-equivalent in the symbolic preflight; real-Qwen context/architecture is tested only in a later stage.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run preregistered multi-agent capacity-coupling symbolic preflight.")
    parser.add_argument("--output-dir", default="results/multiagent_core_2x2_preflight")
    parser.add_argument("--seed", type=int, default=6000)
    parser.add_argument("--instances-per-cell", type=int, default=16)
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--n-per-block", type=int, default=12)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--d-local", type=int, default=5)
    parser.add_argument("--d-boundary", type=int, default=2)
    parser.add_argument("--under-depth", type=int, default=4)
    parser.add_argument("--over-depth", type=int, default=12)
    parser.add_argument("--low-b", type=int, default=2)
    parser.add_argument("--high-b", type=int, default=8)
    parser.add_argument("--edge-budget", type=int, default=96)
    parser.add_argument("--node-cap", type=int, default=5000)
    parser.add_argument("--reference-node-cap", type=int, default=20000)
    parser.add_argument("--candidate-batch-size", type=int, default=24)
    parser.add_argument("--max-batches", type=int, default=12)
    args = parser.parse_args()
    payload = run(args)
    root = Path(args.output_dir)
    if not root.is_absolute():
        root = REPO_ROOT / root
    _write_json(root / "results.json", payload)
    _write_json(root / "summary.json", {key: value for key, value in payload.items() if key not in {"rows", "instance_manifest"}})
    _write_json(root / "instance_manifest.json", {"schema": "multiagent_core_2x2_instance_manifest_v1", "status": payload["status"], "rows": payload["instance_manifest"]})


if __name__ == "__main__":
    main()
